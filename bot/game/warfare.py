"""Telegram warfare workflow modelled on KHATA-GAMES' uploaded Worker routes.
Battle outcomes are deliberately admin-adjudicated, matching the website's scenario/review flow.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import (Castle, Lord, WarExpedition, ArmyUnit, EquipmentItem,
    FleetShip, GarrisonAsset, MilitaryAlliance, WarScenario, TroopTransferRequest, CastleEconomyState, GameState)

ASSET_MODELS = {"army": (ArmyUnit, "unit_key"), "equipment": (EquipmentItem, "item_key"), "fleet": (FleetShip, "ship_key")}

def validate_expedition_origin(lord: Lord, origin_castle_id: int, use_garrison: bool) -> None:
    """Prevent a lord from dispatching another castle's public inventory.

    A lord may dispatch public inventory only from their own castle. At another
    castle they may use only GarrisonAsset rows explicitly owned by that lord.
    """
    if not use_garrison and origin_castle_id != lord.castle_id:
        raise ValueError("نمی‌توانی از موجودی عمومی قلعه‌ای که متعلق به تو نیست لشکر اعزام کنی.")

async def _asset_row(session, castle_id, kind, key, owner_lord_id=None, lock=True):
    if owner_lord_id is not None:
        q=select(GarrisonAsset).where(GarrisonAsset.castle_id==castle_id,GarrisonAsset.owner_lord_id==owner_lord_id,GarrisonAsset.asset_kind==kind,GarrisonAsset.asset_key==key)
    else:
        model, field=ASSET_MODELS[kind]
        q=select(model).where(model.castle_id==castle_id,getattr(model,field)==key)
    if lock: q=q.with_for_update()
    return await session.scalar(q)

async def _get_assets(session, castle_id, kinds=("army","equipment","fleet")):
    result={k:{} for k in kinds}
    for kind in kinds:
        model,field=ASSET_MODELS[kind]
        rows=(await session.scalars(select(model).where(model.castle_id==castle_id))).all()
        result[kind]={getattr(r,field):int(r.count) for r in rows if r.count}
    return result

async def launch_expedition(session: AsyncSession, lord: Lord, target_castle_name: str, expedition_type: str, duration_minutes: int, assets: dict, lord_present=True, use_garrison=False, source_castle_id=None):
    from bot.game.engine import advance_world_clock
    world_state=await session.get(GameState,"world")
    if world_state is None or bool((world_state.value or {}).get("paused",True)):
        raise ValueError("جهان بازی متوقف است؛ در زمان توقف امکان لشکرکشی وجود ندارد.")
    world_now=await advance_world_clock(session)
    if expedition_type not in ("land","sea"): raise ValueError("نوع لشکرکشی باید land یا sea باشد.")
    if not 1 <= duration_minutes <= 10080: raise ValueError("مدت سفر باید بین ۱ دقیقه تا ۷ روز باشد.")
    origin_id=source_castle_id or lord.castle_id
    validate_expedition_origin(lord, origin_id, use_garrison)
    origin=await session.get(Castle,origin_id)
    if not origin: raise ValueError("قلعه مبدأ پیدا نشد.")
    target=await session.scalar(select(Castle).where(Castle.name.ilike(target_castle_name),Castle.active.is_(True)))
    if not target or target.id==origin.id: raise ValueError("قلعه مقصد معتبر نیست.")
    busy=await session.scalar(select(WarExpedition.id).where(WarExpedition.target_castle_id==target.id,WarExpedition.status=="resolving").limit(1))
    if busy: raise ValueError("این قلعه در حال حاضر درگیر نبرد یا محاصره دیگری است.")
    if expedition_type=="sea":
        economy=await session.get(CastleEconomyState,origin.id)
        if not economy or not economy.port_enabled: raise ValueError("قلعه مبدأ بندر فعال ندارد.")
    clean={k:{} for k in ("army","equipment","fleet")}
    for kind in ("army","equipment","fleet"):
        if expedition_type=="land" and kind=="fleet": continue
        values=assets.get(kind,{})
        if not isinstance(values,dict): raise ValueError("ساختار دارایی‌های لشکر معتبر نیست.")
        for key,raw in sorted(values.items()):
            n=int(raw)
            if n<0 or n>1000000: raise ValueError("تعداد دارایی معتبر نیست.")
            if not n: continue
            row=await _asset_row(session,origin.id,kind,key,lord.id if use_garrison else None)
            if not row or row.count<n: raise ValueError(f"موجودی {key} در مبدأ کافی نیست.")
            clean[kind][key]=n
    if not any(clean[k] for k in clean): raise ValueError("حداقل یک نیرو، ادوات یا کشتی انتخاب کن.")
    if expedition_type=="sea":
        transport=clean["fleet"].get("transport",0); warship=clean["fleet"].get("warship",0)
        capacity=transport*600+warship*400
        weight=sum(n*(2 if key=="cavalry" else 1) for key,n in clean["army"].items())
        if transport+warship<1 or weight>capacity: raise ValueError("ظرفیت ناوگان برای ارتش انتخاب‌شده کافی نیست.")
    for kind,values in clean.items():
        for key,n in values.items():
            row=await _asset_row(session,origin.id,kind,key,lord.id if use_garrison else None); row.count-=n
    now=world_now
    expedition=WarExpedition(attacker_lord_id=lord.id,origin_castle_id=origin.id,target_castle_id=target.id,
        status="travelling",units=clean,assets=clean,expedition_type=expedition_type,lord_present=bool(lord_present),
        launched_at=now,arrival_at=now+timedelta(minutes=duration_minutes),asset_origin="garrison" if use_garrison else "castle")
    session.add(expedition); await session.flush(); return expedition

async def arrive_expeditions(session: AsyncSession):
    from bot.game.engine import advance_world_clock
    world_state=await session.get(GameState,"world")
    if world_state is None or bool((world_state.value or {}).get("paused",True)): return []
    now=await advance_world_clock(session)
    rows=(await session.scalars(select(WarExpedition).where(WarExpedition.status=="travelling",WarExpedition.arrival_at<=now).with_for_update())).all()
    for row in rows: row.status="arrived"
    return rows

async def set_arrival_choice(session: AsyncSession, expedition_id: int, lord: Lord, choice: str):
    row=await session.scalar(select(WarExpedition).where(WarExpedition.id==expedition_id).with_for_update())
    if not row or row.attacker_lord_id!=lord.id or row.status!="arrived": raise ValueError("لشکر پیدا نشد یا هنوز به مقصد نرسیده است.")
    if row.arrival_choice: raise ValueError("برای این لشکر قبلاً تصمیم ثبت شده است.")
    if choice not in ("garrison","alliance","transfer","deploy"): raise ValueError("گزینه نامعتبر است.")
    row.arrival_choice=choice
    if choice=="garrison":
        for kind,items in (row.assets or row.units).items():
            for key,n in items.items():
                a=await _asset_row(session,row.target_castle_id,kind,key,lord.id)
                if a: a.count+=int(n)
                else: session.add(GarrisonAsset(castle_id=row.target_castle_id,owner_lord_id=lord.id,asset_kind=kind,asset_key=key,count=int(n)))
        row.status="completed"
    elif choice=="transfer":
        defender=await session.scalar(select(Lord).where(Lord.castle_id==row.target_castle_id,Lord.status=="active"))
        if not defender: raise ValueError("قلعه مقصد لرد فعال ندارد و درخواست انتقال لازم نیست.")
        session.add(TroopTransferRequest(expedition_id=row.id,sender_lord_id=lord.id,receiver_lord_id=defender.id,assets=row.assets or row.units))
        row.status="resolving"
    elif choice=="alliance":
        defender=await session.scalar(select(Lord).where(Lord.castle_id==row.target_castle_id,Lord.status=="active"))
        if not defender: raise ValueError("برای اتحاد، قلعه مقصد باید لرد فعال داشته باشد.")
        if row.origin_castle_id < row.target_castle_id:
            castle_a, castle_b = row.origin_castle_id, row.target_castle_id
            owner_a, owner_b = lord.id, defender.id
        else:
            castle_a, castle_b = row.target_castle_id, row.origin_castle_id
            owner_a, owner_b = defender.id, lord.id
        existing = await session.scalar(
            select(MilitaryAlliance).where(
                MilitaryAlliance.castle_a_id == castle_a,
                MilitaryAlliance.castle_b_id == castle_b,
                MilitaryAlliance.status.in_(("pending", "accepted")),
            ).with_for_update()
        )
        if existing:
            raise ValueError("برای این دو قلعه درخواست اتحاد فعال یا پذیرفته‌شده وجود دارد.")
        session.add(MilitaryAlliance(castle_a_id=castle_a,castle_b_id=castle_b,
            owner_a_lord_id=owner_a,owner_b_lord_id=owner_b,status="pending",war_expedition_id=row.id))
        row.status="resolving"
    else: row.status="arrived"
    return row

async def issue_war_command(session: AsyncSession, expedition_id: int, lord: Lord, command: str):
    row=await session.scalar(select(WarExpedition).where(WarExpedition.id==expedition_id).with_for_update())
    if not row or row.attacker_lord_id!=lord.id or row.status!="arrived": raise ValueError("لشکر آماده دریافت دستور نیست.")
    if row.command or row.arrival_choice: raise ValueError("برای این لشکر قبلاً تصمیم یا دستور ثبت شده است.")
    if command not in ("attack","siege","deploy"): raise ValueError("دستور باید attack، siege یا deploy باشد.")
    from bot.game.engine import advance_world_clock
    now=await advance_world_clock(session)
    if row.arrival_at and now > row.arrival_at + timedelta(minutes=90): raise ValueError("مهلت ۹۰ دقیقه‌ای ثبت دستور لشکرکشی تمام شده است.")
    row.command=command; row.command_at=now
    if command=="attack": row.scenario_deadline_at=now+timedelta(hours=24)
    defender=await session.scalar(select(Lord).where(Lord.castle_id==row.target_castle_id,Lord.status=="active"))
    if defender: row.defender_assets=await _get_assets(session,row.target_castle_id,("army","equipment","fleet"))
    if command=="deploy":
        await set_arrival_choice(session,expedition_id,lord,"garrison")
    else: row.status="resolving"
    return row

async def submit_scenario(session: AsyncSession, expedition_id: int, lord: Lord, text: str):
    row=await session.get(WarExpedition,expedition_id)
    if not row or row.command!="attack" or not row.scenario_deadline_at: raise ValueError("برای این نبرد امکان ارسال سناریو وجود ندارد.")
    from bot.game.engine import advance_world_clock
    now=await advance_world_clock(session)
    if now>=row.scenario_deadline_at: raise ValueError("مهلت ۲۴ ساعته ارسال سناریو تمام شده است.")
    side="attacker" if lord.id==row.attacker_lord_id else "defender" if lord.castle_id==row.target_castle_id else None
    if not side: raise ValueError("تو در این نبرد مهاجم یا مدافع نیستی.")
    if not text.strip() or len(text)>8000: raise ValueError("متن سناریو باید بین ۱ تا ۸۰۰۰ نویسه باشد.")
    existing=await session.scalar(select(WarScenario).where(WarScenario.expedition_id==row.id,WarScenario.lord_id==lord.id))
    if existing: raise ValueError("برای این نبرد قبلاً سناریو فرستاده‌ای.")
    item=WarScenario(expedition_id=row.id,lord_id=lord.id,scenario_text=text.strip());session.add(item);return item

async def review_battle(session: AsyncSession, expedition_id: int, outcome: str, attacker_losses: dict, defender_losses: dict):
    row=await session.scalar(select(WarExpedition).where(WarExpedition.id==expedition_id).with_for_update())
    if not row or row.command not in ("attack","siege") or row.outcome: raise ValueError("نبرد برای داوری آماده نیست یا قبلاً نهایی شده است.")
    if outcome not in ("attacker","defender"): raise ValueError("نتیجه باید attacker یا defender باشد.")
    attacker_lord=await session.get(Lord,row.attacker_lord_id)
    defender=await session.scalar(select(Lord).where(Lord.castle_id==row.target_castle_id,Lord.status=="active"))
    if not defender: raise ValueError("لرد مدافع پیدا نشد.")
    snapshot=row.assets or row.units
    # Site allows attacker losses for army/equipment/fleet, while defender losses are army units.
    normalized={k:(v if isinstance(v,dict) else {"army":v}) for k,v in attacker_losses.items()}
    for kind in ("army","equipment","fleet"):
        losses=normalized.get(kind,{})
        brought=snapshot.get(kind,{})
        for key,nraw in losses.items():
            n=int(nraw); available=int(brought.get(key,0))
            if n<0 or n>available: raise ValueError(f"تلفات مهاجم برای {kind}/{key} خارج از موجودی است.")
    defender_snapshot=(row.defender_assets or {}).get("army",{})
    for key,nraw in defender_losses.items():
        n=int(nraw); available=int(defender_snapshot.get(key,0))
        if n<0 or n>available: raise ValueError(f"تلفات مدافع برای {key} خارج از موجودی است.")
        if n:
            army=await session.scalar(select(ArmyUnit).where(ArmyUnit.castle_id==row.target_castle_id,ArmyUnit.unit_key==key).with_for_update())
            if not army or army.count<n: raise ValueError("موجودی فعلی ارتش مدافع با گزارش تلفات سازگار نیست.")
            army.count-=n
    saved_attacker={k:{key:int(n) for key,n in normalized.get(k,{}).items()} for k in ("army","equipment","fleet")}
    row.outcome=outcome; row.casualties={"attacker":saved_attacker,"defender":{"army":defender_losses}}
    row.result={"outcome":outcome,"attacker_losses":saved_attacker,"defender_losses":defender_losses,"reviewed_at":datetime.now(timezone.utc).isoformat()}
    survivors={k:{key:max(0,int(n)-int(saved_attacker.get(k,{}).get(key,0))) for key,n in values.items()} for k,values in snapshot.items()}
    destination=row.target_castle_id if outcome=="attacker" else row.origin_castle_id
    keep_in_garrison=(outcome=="attacker" or row.asset_origin=="garrison")
    for kind,items in survivors.items():
        for key,n in items.items():
            if not n: continue
            if keep_in_garrison:
                a=await _asset_row(session,destination,kind,key,attacker_lord.id)
                if a:a.count+=n
                else:session.add(GarrisonAsset(castle_id=destination,owner_lord_id=attacker_lord.id,asset_kind=kind,asset_key=key,count=n))
            else:
                a=await _asset_row(session,destination,kind,key)
                if a:a.count+=n
                else:
                    model,field=ASSET_MODELS[kind];session.add(model(castle_id=destination,**{field:key},count=n))
    row.status="completed"
    return row

async def answer_alliance(session: AsyncSession, alliance_id: int, lord: Lord, accept: bool):
    row=await session.scalar(select(MilitaryAlliance).where(MilitaryAlliance.id==alliance_id).with_for_update())
    if not row or row.owner_b_lord_id!=lord.id or row.status!="pending": raise ValueError("درخواست اتحاد در دسترس نیست.")
    row.status="accepted" if accept else "rejected";row.responded_at=datetime.now(timezone.utc)
    if row.war_expedition_id:
        expedition=await session.get(WarExpedition,row.war_expedition_id)
        if expedition:
            if accept:
                for kind,items in (expedition.assets or expedition.units).items():
                    for key,n in items.items():
                        a=await _asset_row(session,expedition.target_castle_id,kind,key,expedition.attacker_lord_id)
                        if a:a.count+=int(n)
                        else:session.add(GarrisonAsset(castle_id=expedition.target_castle_id,owner_lord_id=expedition.attacker_lord_id,asset_kind=kind,asset_key=key,count=int(n)))
                expedition.status="completed"
            else:
                for kind,items in (expedition.assets or expedition.units).items():
                    for key,n in items.items():
                        a=await _asset_row(session,expedition.origin_castle_id,kind,key,expedition.attacker_lord_id if expedition.asset_origin=="garrison" else None)
                        if a:a.count+=int(n)
                        elif expedition.asset_origin=="garrison": session.add(GarrisonAsset(castle_id=expedition.origin_castle_id,owner_lord_id=expedition.attacker_lord_id,asset_kind=kind,asset_key=key,count=int(n)))
                        elif kind in ASSET_MODELS:
                            model,field=ASSET_MODELS[kind];session.add(model(castle_id=expedition.origin_castle_id,**{field:key},count=int(n)))
                expedition.status="completed"
    return row

async def answer_transfer(session: AsyncSession, request_id: int, lord: Lord, accept: bool):
    row=await session.scalar(select(TroopTransferRequest).where(TroopTransferRequest.id==request_id).with_for_update())
    if not row or row.receiver_lord_id!=lord.id or row.status!="pending": raise ValueError("درخواست انتقال پیدا نشد.")
    row.status="accepted" if accept else "rejected";row.responded_at=datetime.now(timezone.utc)
    expedition=await session.get(WarExpedition,row.expedition_id)
    if accept:
        for kind,items in row.assets.items():
            for key,n in items.items():
                # An accepted troop transfer changes ownership to the receiving lord.
                a=await _asset_row(session,expedition.target_castle_id,kind,key,row.receiver_lord_id)
                if a:a.count+=int(n)
                else:session.add(GarrisonAsset(castle_id=expedition.target_castle_id,owner_lord_id=row.receiver_lord_id,asset_kind=kind,asset_key=key,count=int(n)))
    else:
        for kind,items in row.assets.items():
            for key,n in items.items():
                a=await _asset_row(session,expedition.origin_castle_id,kind,key,expedition.attacker_lord_id if expedition.asset_origin=="garrison" else None)
                if a:a.count+=int(n)
                elif expedition.asset_origin=="garrison": session.add(GarrisonAsset(castle_id=expedition.origin_castle_id,owner_lord_id=expedition.attacker_lord_id,asset_kind=kind,asset_key=key,count=int(n)))
                elif kind in ASSET_MODELS:
                    model,field=ASSET_MODELS[kind];session.add(model(castle_id=expedition.origin_castle_id,**{field:key},count=int(n)))
    expedition.status="completed"
    return row

async def cancel_expedition(session: AsyncSession, expedition_id: int, lord: Lord):
    row=await session.scalar(select(WarExpedition).where(WarExpedition.id==expedition_id).with_for_update())
    if not row or row.attacker_lord_id!=lord.id or row.status!="travelling" or row.command:
        raise ValueError("فقط لشکر در حال حرکت و بدون دستور جنگی قابل لغو است.")
    from bot.game.engine import advance_world_clock
    now=await advance_world_clock(session)
    if row.arrival_at and now >= row.arrival_at:
        raise ValueError("مهلت لغو تمام شده است؛ لشکر به مقصد رسیده یا باید وضعیت رسیدن آن ثبت شود.")
    for kind,items in (row.assets or row.units).items():
        for key,n in items.items():
            a=await _asset_row(session,row.origin_castle_id,kind,key,lord.id if row.asset_origin=="garrison" else None)
            if a:a.count+=int(n)
            elif row.asset_origin=="garrison": session.add(GarrisonAsset(castle_id=row.origin_castle_id,owner_lord_id=lord.id,asset_kind=kind,asset_key=key,count=int(n)))
            elif kind in ASSET_MODELS:
                model,field=ASSET_MODELS[kind];session.add(model(castle_id=row.origin_castle_id,**{field:key},count=int(n)))
    row.status="cancelled";row.cancelled_at=now
    return row
