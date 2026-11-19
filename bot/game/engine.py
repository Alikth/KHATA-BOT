"""PostgreSQL game engine porting static economy rules from the uploaded KHATA-GAMES Worker source.
The catalog is exported from src/worker/data/game-rules.js and game-data.js.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import (Castle, Lord, ResourceBalance, ProductionLevel, CampLevel,
    SpecialCampLevel, ArmyUnit, EquipmentItem, FleetShip, CastleEconomyState, GameState, WarExpedition)

CATALOG = json.loads((Path(__file__).with_name("site_catalog.json")).read_text(encoding="utf-8"))
RESOURCE_KEYS = CATALOG["RESOURCE_KEYS"]
RESOURCE_LABELS = CATALOG["RESOURCE_LABELS"]
GENERAL_PRODUCTIONS = CATALOG["GENERAL_PRODUCTIONS"]
SPECIAL_PRODUCTIONS = CATALOG["SPECIAL_PRODUCTIONS"]
REGION_MULTIPLIERS = CATALOG["REGION_MULTIPLIERS"]
GENERAL_CAMPS = CATALOG["GENERAL_CAMPS"]
SPECIAL_CAMPS = CATALOG["SPECIAL_CAMPS"]
EQUIPMENT = CATALOG["EQUIPMENT"]
STARTING_RESOURCES = {"peasants":500,"coins":5000,"wood":500,"stone":500,"iron":500,"meat":500,"fish":500,"grain":6000,"horses":0,"dragon_glass":0,"wildfire":0,"tar":0,"grapes":50}
STARTING_ARMY = {"swordsman":500,"archer":200,"spearman":100,"cavalry":100}


def calculate_food_debt_casualties(army: dict[str, int], food_debt: int) -> dict[str, int]:
    """Allocate food-debt casualties proportionally using the largest-remainder method.

    Ties are resolved by the original mapping order, making results deterministic.
    The result always contains every army key and never removes more units than exist.
    """
    counts = {key: max(0, int(amount)) for key, amount in army.items()}
    casualties = {key: 0 for key in counts}
    total_troops = sum(counts.values())
    debt = max(0, int(food_debt))

    if total_troops == 0 or debt == 0:
        return casualties

    losses = min(debt, total_troops)
    exact_shares = {
        key: losses * count / total_troops
        for key, count in counts.items()
    }
    for key, share in exact_shares.items():
        casualties[key] = min(counts[key], math.floor(share))

    remaining = losses - sum(casualties.values())
    order = {key: index for index, key in enumerate(counts)}
    ranked = sorted(
        counts,
        key=lambda key: (-(exact_shares[key] - math.floor(exact_shares[key])), order[key]),
    )
    for key in ranked:
        if remaining <= 0:
            break
        if casualties[key] < counts[key]:
            casualties[key] += 1
            remaining -= 1

    return casualties

async def initialize_castle(session: AsyncSession, castle: Castle):
    """Seed only missing local mirror rows; never reset an existing castle inventory."""
    async def seed_levels(model, field: str, values: dict[str, int]):
        existing = set((await session.scalars(
            select(getattr(model, field)).where(model.castle_id == castle.id)
        )).all())
        for key, level in values.items():
            if key not in existing:
                session.add(model(castle_id=castle.id, **{field: key}, level=level))

    async def seed_counts(model, field: str, values: dict[str, int]):
        existing = set((await session.scalars(
            select(getattr(model, field)).where(model.castle_id == castle.id)
        )).all())
        for key, count in values.items():
            if key not in existing:
                session.add(model(castle_id=castle.id, **{field: key}, count=count))

    defaults = {"farm":1,"village":1,"lumber":0,"stone":0,"iron":0,"recreation":0,"market":0,"stable":0,"slaughterhouse":0}
    special = SPECIAL_PRODUCTIONS.get(castle.region)
    if special:
        defaults[special["key"]] = 0
    await seed_levels(ProductionLevel, "production_key", defaults)
    await seed_levels(CampLevel, "camp_key", {key:0 for key in GENERAL_CAMPS})
    await seed_levels(SpecialCampLevel, "camp_key", {row["key"]:0 for row in SPECIAL_CAMPS.get(castle.region, [])})
    await seed_counts(ArmyUnit, "unit_key", STARTING_ARMY)
    await seed_counts(EquipmentItem, "item_key", {key:0 for key in EQUIPMENT})
    naval_names={"Eastwatch","Karhold","Seagard","Gulltown","Pyke","Ten Towers","Hammerhorn","Casterly Rock","King's Landing","Dragonstone","Storm's End","Oldtown","Sunspear","Yronwood"}
    naval = castle.name in naval_names
    await seed_counts(FleetShip, "ship_key", {"transport":1 if naval else 0,"warship":1 if naval else 0})
    economy = await session.get(CastleEconomyState, castle.id)
    if economy is None:
        session.add(CastleEconomyState(castle_id=castle.id, port_enabled=naval))

async def _balances(session, lord_id: int):
    rows=(await session.scalars(select(ResourceBalance).where(ResourceBalance.lord_id==lord_id).with_for_update())).all()
    return {r.resource_code:r for r in rows}

async def _spend(session, lord_id: int, cost: dict):
    rows=await _balances(session,lord_id)
    for key, amount in cost.items():
        if key not in RESOURCE_KEYS or int(amount)<0: raise ValueError("تعریف هزینه نامعتبر است.")
        if key not in rows or rows[key].amount < int(amount): raise ValueError(f"منابع کافی نیست: {RESOURCE_LABELS.get(key,key)}")
    for key, amount in cost.items(): rows[key].amount -= int(amount)

async def ensure_castle_not_under_siege(session: AsyncSession, castle_id: int) -> None:
    active = await session.scalar(
        select(WarExpedition.id).where(
            WarExpedition.target_castle_id == castle_id,
            WarExpedition.command == "siege",
            WarExpedition.status.notin_(("completed", "cancelled", "failed")),
        ).limit(1)
    )
    if active:
        raise ValueError("قلعه در محاصره است و این عملیات تا پایان محاصره مجاز نیست.")


async def upgrade(session: AsyncSession, lord: Lord, category: str, key: str):
    await ensure_castle_not_under_siege(session, lord.castle_id)
    if category=="production":
        defs=GENERAL_PRODUCTIONS.copy(); special=SPECIAL_PRODUCTIONS.get((await session.get(Castle,lord.castle_id)).region)
        if special: defs[special["key"]]=special
        model=ProductionLevel; field="production_key"
    elif category=="camp":
        defs=GENERAL_CAMPS; model=CampLevel; field="camp_key"
    elif category=="special_camp":
        castle=await session.get(Castle,lord.castle_id); defs={x["key"]:x for x in SPECIAL_CAMPS.get(castle.region,[])}
        model=SpecialCampLevel; field="camp_key"
    else: raise ValueError("نوع ارتقا نامعتبر است.")
    definition=defs.get(key)
    if not definition: raise ValueError("این مورد برای منطقه یا قلعه تو تعریف نشده است.")
    row=await session.scalar(select(model).where(model.castle_id==lord.castle_id,getattr(model,field)==key).with_for_update())
    if not row: raise ValueError("ساختار این مورد در قلعه پیدا نشد.")
    if row.level>=int(definition.get("max",20)): raise ValueError("این مورد به حداکثر سطح رسیده است.")
    await _spend(session,lord.id,definition.get("cost",{})); row.level+=1
    return row.level, definition

async def recruit(session: AsyncSession, lord: Lord, unit_key: str, amount: int):
    if amount<=0 or amount>100000: raise ValueError("تعداد باید بین 1 تا 100000 باشد.")
    castle=await session.get(Castle,lord.castle_id)
    defs={**{v["unit"]:v for v in GENERAL_CAMPS.values()}, **{v["unit"]:v for v in SPECIAL_CAMPS.get(castle.region,[])}}
    definition=defs.get(unit_key)
    if not definition: raise ValueError("این نیرو در منطقه قلعه تو قابل سربازگیری نیست.")
    camp_model=CampLevel if unit_key in {v["unit"] for v in GENERAL_CAMPS.values()} else SpecialCampLevel
    camp_key=next(k for k,v in (GENERAL_CAMPS if camp_model is CampLevel else {x["key"]:x for x in SPECIAL_CAMPS.get(castle.region,[])}).items() if v["unit"]==unit_key)
    camp=await session.scalar(select(camp_model).where(camp_model.castle_id==castle.id, (camp_model.camp_key==camp_key)).with_for_update())
    if not camp or camp.level<1: raise ValueError("ابتدا کمپ مربوط به این نیرو را حداقل تا سطح ۱ ارتقا بده.")
    # Site weekly output is generated by camp level; direct recruitment is not exposed as a separate site action.
    raise ValueError("طبق قوانین سایت، نیروها با تولید هفتگی کمپ ایجاد می‌شوند؛ دستور سربازگیری مستقیم در سایت وجود ندارد.")

async def advance_world_clock(session: AsyncSession, reset_real_tick: bool=False):
    now=datetime.now(timezone.utc)
    state=await session.get(GameState,"world")
    if state is None:
        state=GameState(key="world",value={"paused":True,"world_time":now.isoformat(),"last_real_tick":now.isoformat()}); session.add(state); await session.flush()
    value=dict(state.value or {})
    try: world=datetime.fromisoformat(value.get("world_time",now.isoformat()))
    except Exception: world=now
    if reset_real_tick:
        value["last_real_tick"]=now.isoformat()
    elif not value.get("paused",True):
        try: last=datetime.fromisoformat(value.get("last_real_tick",now.isoformat()))
        except Exception: last=now
        world += max((now-last).total_seconds(),0) * __import__("datetime").timedelta(seconds=1)
        value["world_time"]=world.isoformat(); value["last_real_tick"]=now.isoformat()
    state.value=value
    return world

async def settle_expired_food_debts(session: AsyncSession, now=None) -> int:
    """Apply overdue food-debt casualties once, matching the website's 24-hour grace period."""
    now = now or datetime.now(timezone.utc)
    states = (await session.scalars(
        select(CastleEconomyState).where(
            CastleEconomyState.food_debt > 0,
            CastleEconomyState.food_debt_due_at.is_not(None),
            CastleEconomyState.food_debt_due_at <= now,
        ).with_for_update()
    )).all()
    settled = 0
    for economy in states:
        try:
            await ensure_castle_not_under_siege(session, economy.castle_id)
        except ValueError:
            continue
        units = (await session.scalars(
            select(ArmyUnit).where(ArmyUnit.castle_id == economy.castle_id).with_for_update()
        )).all()
        army = {row.unit_key: row.count for row in units}
        losses = calculate_food_debt_casualties(army, economy.food_debt)
        for row in units:
            row.count = max(0, row.count - losses.get(row.unit_key, 0))
        economy.food_debt = 0
        economy.food_debt_due_at = None
        settled += 1
    return settled


async def weekly_settlement(session: AsyncSession, force: bool=False):
    """Settle one world week once per castle using the website's production/upkeep formula."""
    settled_debts = await settle_expired_food_debts(session)
    state=await session.get(GameState,"world")
    if state and state.value.get("paused",True): return {"paused":True,"processed":0,"food_debts_settled":settled_debts}
    now=await advance_world_clock(session)
    week=f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
    castles=(await session.scalars(select(Castle).where(Castle.active.is_(True)))).all(); processed=0
    for castle in castles:
        econ=await session.get(CastleEconomyState,castle.id)
        if not econ: continue
        if not force and econ.last_week_key==week: continue
        lords=(await session.scalars(select(Lord).where(Lord.castle_id==castle.id,Lord.status=="active"))).all()
        if not lords: econ.last_week_key=week; continue
        lord=lords[0]; changes={}
        prods=(await session.scalars(select(ProductionLevel).where(ProductionLevel.castle_id==castle.id))).all()
        camps=(await session.scalars(select(CampLevel).where(CampLevel.castle_id==castle.id))).all()
        scamps=(await session.scalars(select(SpecialCampLevel).where(SpecialCampLevel.castle_id==castle.id))).all()
        army=(await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==castle.id))).all()
        for row in prods:
            d=GENERAL_PRODUCTIONS.get(row.production_key)
            if not d and row.production_key==SPECIAL_PRODUCTIONS.get(castle.region,{}).get("key"): d=SPECIAL_PRODUCTIONS[castle.region]
            if d and row.level: changes[d["base"]]=changes.get(d["base"],0)+row.level*int(d["yield"])*int(REGION_MULTIPLIERS.get(castle.region,{}).get(row.production_key,1))
        for row in camps:
            d=GENERAL_CAMPS.get(row.camp_key)
            if d and row.level: changes[d["unit"]]=changes.get(d["unit"],0)+row.level*int(d["yield"])
        special_defs={x["key"]:x for x in SPECIAL_CAMPS.get(castle.region,[])}
        for row in scamps:
            d=special_defs.get(row.camp_key)
            if d and row.level: changes[d["unit"]]=changes.get(d["unit"],0)+row.level*int(d["yield"])
        balances=await _balances(session,lord.id)
        for key,gain in changes.items():
            amount=int(gain)
            if key in RESOURCE_KEYS:
                if key in ("grain","fish","meat") and econ.food_debt:
                    pay=min(amount,econ.food_debt); econ.food_debt-=pay; amount-=pay
                if amount and key in balances: balances[key].amount+=amount
            else:
                unit=await session.scalar(select(ArmyUnit).where(ArmyUnit.castle_id==castle.id,ArmyUnit.unit_key==key).with_for_update())
                if unit: unit.count+=amount
                else: session.add(ArmyUnit(castle_id=castle.id,unit_key=key,count=amount))
        if econ.port_enabled and econ.port_level>0:
            for ship_key in ("transport","warship"):
                ship=await session.scalar(select(FleetShip).where(FleetShip.castle_id==castle.id,FleetShip.ship_key==ship_key).with_for_update())
                if ship: ship.count+=econ.port_level
        # Website upkeep: grain first, then fish, meat, grapes.
        army=(await session.scalars(select(ArmyUnit).where(ArmyUnit.castle_id==castle.id))).all()
        army_map={x.unit_key:x.count for x in army}
        grain_need=sum(army_map.get(k,0) for k in ("swordsman","archer","spearman"))+2*army_map.get("cavalry",0)
        grain_need+=sum(n*2 for k,n in army_map.items() if k not in ("swordsman","archer","spearman","cavalry","giants"))
        remaining=grain_need
        for key, divisor in (("grain",1),("fish",2),("meat",2),("grapes",0.5)):
            row=balances.get(key); available=int(row.amount) if row else 0
            used=min(available, math.ceil(remaining/divisor) if divisor>=1 else math.ceil(remaining*2))
            if row: row.amount-=used
            remaining=max(0,remaining-used*divisor)
        if remaining:
            had_debt = econ.food_debt > 0
            econ.food_debt += int(remaining)
            if not had_debt or not econ.food_debt_due_at:
                econ.food_debt_due_at = now + timedelta(hours=24)
        econ.last_week_key=week; processed+=1
    return {"paused":False,"processed":processed,"week":week}

async def upgrade_workshop(session: AsyncSession, lord: Lord):
    await ensure_castle_not_under_siege(session, lord.castle_id)
    econ=await session.get(CastleEconomyState,lord.castle_id,with_for_update=True)
    if not econ: raise ValueError("اطلاعات اقتصادی قلعه پیدا نشد.")
    if econ.workshop_level>=5: raise ValueError("کارگاه به حداکثر سطح ۵ رسیده است.")
    await _spend(session,lord.id,{"coins":int(CATALOG["EQUIPMENT_UPGRADE_COST"])})
    econ.workshop_level+=1
    return econ.workshop_level

async def build_equipment(session: AsyncSession, lord: Lord, key: str):
    from datetime import date
    from bot.database.models import EquipmentBuildLimit
    await ensure_castle_not_under_siege(session, lord.castle_id)
    definition=EQUIPMENT.get(key)
    if not definition: raise ValueError("نوع ادوات معتبر نیست.")
    econ=await session.get(CastleEconomyState,lord.castle_id,with_for_update=True)
    if not econ or econ.workshop_level<int(definition["level"]): raise ValueError(f"برای ساخت این ادوات، کارگاه باید حداقل سطح {definition['level']} باشد.")
    now=datetime.now(timezone.utc); period=f"{definition['period']}:{now.date().isoformat() if definition['period']=='day' else f'{now.isocalendar().year}-W{now.isocalendar().week:02d}'}:{key}"
    tracker=await session.scalar(select(EquipmentBuildLimit).where(EquipmentBuildLimit.castle_id==lord.castle_id,EquipmentBuildLimit.tracker_key==period).with_for_update())
    if not tracker:
        tracker=EquipmentBuildLimit(castle_id=lord.castle_id,tracker_key=period,used=0); session.add(tracker); await session.flush()
    if tracker.used>=int(definition["limit"]): raise ValueError("سقف ساخت این ادوات برای این بازه زمانی پر شده است.")
    await _spend(session,lord.id,definition["cost"])
    item=await session.scalar(select(EquipmentItem).where(EquipmentItem.castle_id==lord.castle_id,EquipmentItem.item_key==key).with_for_update())
    if not item: raise ValueError("ردیف ادوات قلعه پیدا نشد.")
    item.count+=1; tracker.used+=1
    return definition,item.count

async def upgrade_port(session: AsyncSession, lord: Lord):
    await ensure_castle_not_under_siege(session, lord.castle_id)
    econ=await session.get(CastleEconomyState,lord.castle_id,with_for_update=True)
    if not econ or not econ.port_enabled: raise ValueError("این قلعه بندر ندارد.")
    if econ.port_level>=15: raise ValueError("اسکله به حداکثر سطح ۱۵ رسیده است.")
    await _spend(session,lord.id,{"coins":1500,"wood":1000}); econ.port_level+=1
    return econ.port_level
