from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index,
                        Integer, JSON, Numeric, String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column
from bot.database.base import Base

class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Castle(Base):
    __tablename__ = "castles"
    __table_args__ = (UniqueConstraint("name", name="uq_castles_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    house: Mapped[str] = mapped_column(String(80), nullable=False)
    is_coastal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Lord(Base):
    __tablename__ = "lords"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", name="uq_lords_telegram_user_id"),
        CheckConstraint("status IN ('active', 'suspended', 'deleted')", name="ck_lords_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class GroupRegistration(Base):
    __tablename__ = "group_registrations"
    __table_args__ = (UniqueConstraint("telegram_chat_id", name="uq_group_registrations_chat"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    chat_type: Mapped[str] = mapped_column(String(16), nullable=False, default="supergroup")
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registered_by_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# Backward-compatible name used by the first prototype handlers.
RegisteredGroup = GroupRegistration

class GameSetting(Base):
    __tablename__ = "game_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class ResourceBalance(Base):
    __tablename__ = "resource_balances"
    __table_args__ = (UniqueConstraint("lord_id", "resource_code", name="uq_resource_balance_lord_resource"), CheckConstraint("amount >= 0", name="ck_resource_balance_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class CastleAsset(Base):
    __tablename__ = "castle_assets"
    __table_args__ = (UniqueConstraint("castle_id", "asset_type", "asset_code", name="uq_castle_asset"), CheckConstraint("quantity >= 0", name="ck_castle_asset_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(24), nullable=False)  # production, camp, army, equipment, fleet
    asset_code: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class GameEvent(Base):
    __tablename__ = "game_events"
    __table_args__ = (CheckConstraint("status IN ('pending','processing','completed','cancelled','failed')", name="ck_game_events_status"), UniqueConstraint("idempotency_key", name="uq_game_events_idempotency_key"), Index("ix_game_events_due", "status", "due_at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class WarExpedition(Base):
    __tablename__ = "war_expeditions"
    __table_args__ = (CheckConstraint("status IN ('prepared','travelling','arrived','resolving','returning','completed','cancelled','failed')", name="ck_war_expeditions_status"), Index("ix_war_expeditions_status_arrival", "status", "arrival_at"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attacker_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    origin_castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False)
    target_castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="prepared")
    units: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    return_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expedition_type: Mapped[str] = mapped_column(String(12), nullable=False, default="land")
    asset_origin: Mapped[str] = mapped_column(String(16), nullable=False, default="castle")
    assets: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    defender_assets: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    command: Mapped[str | None] = mapped_column(String(16))
    command_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scenario_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrival_choice: Mapped[str | None] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(16))
    casualties: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lord_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    return_after_arrival: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class TradeOffer(Base):
    __tablename__ = "trade_offers"
    __table_args__ = (CheckConstraint("status IN ('pending','accepted','rejected','cancelled','expired','completed')", name="ck_trade_offers_status"), CheckConstraint("sender_lord_id <> recipient_lord_id", name="ck_trade_different_lords"), Index("ix_trade_offers_recipient_status", "recipient_lord_id", "status"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    recipient_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    offered_resource: Mapped[str] = mapped_column(String(50), nullable=False)
    offered_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_resource: Mapped[str] = mapped_column(String(50), nullable=False)
    requested_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offered_assets: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    requested_assets: Mapped[dict[str, Any] | None] = mapped_column(JSON)

class MilitaryAlliance(Base):
    __tablename__ = "military_alliances"
    __table_args__ = (UniqueConstraint("castle_a_id", "castle_b_id", name="uq_alliance_castles"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_a_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False)
    castle_b_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="RESTRICT"), nullable=False)
    owner_a_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    owner_b_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    war_expedition_id: Mapped[int | None] = mapped_column(ForeignKey("war_expeditions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class GarrisonAsset(Base):
    __tablename__ = "garrison_assets"
    __table_args__ = (UniqueConstraint("castle_id", "owner_lord_id", "asset_kind", "asset_key", name="uq_garrison_asset"), CheckConstraint("count >= 0", name="ck_garrison_count"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    owner_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    asset_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class WarScenario(Base):
    __tablename__ = "war_scenarios"
    __table_args__ = (UniqueConstraint("expedition_id", "lord_id", name="uq_war_scenario_lord"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expedition_id: Mapped[int] = mapped_column(ForeignKey("war_expeditions.id", ondelete="CASCADE"), nullable=False)
    lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    scenario_text: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class TroopTransferRequest(Base):
    __tablename__ = "troop_transfer_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expedition_id: Mapped[int] = mapped_column(ForeignKey("war_expeditions.id", ondelete="CASCADE"), nullable=False, unique=True)
    sender_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    receiver_lord_id: Mapped[int] = mapped_column(ForeignKey("lords.id", ondelete="RESTRICT"), nullable=False)
    assets: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (Index("ix_admin_audit_logs_created", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80))
    target_id: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text)
    before_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlation_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class GameState(Base):
    __tablename__ = "game_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class ProductionLevel(Base):
    __tablename__ = "castle_production"
    __table_args__ = (UniqueConstraint("castle_id", "production_key", name="uq_castle_production"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    production_key: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class CampLevel(Base):
    __tablename__ = "castle_camps"
    __table_args__ = (UniqueConstraint("castle_id", "camp_key", name="uq_castle_camp"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    camp_key: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class SpecialCampLevel(Base):
    __tablename__ = "castle_special_camps"
    __table_args__ = (UniqueConstraint("castle_id", "camp_key", name="uq_castle_special_camp"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    camp_key: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class ArmyUnit(Base):
    __tablename__ = "castle_army"
    __table_args__ = (UniqueConstraint("castle_id", "unit_key", name="uq_castle_army_unit"), CheckConstraint("count >= 0", name="ck_castle_army_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    unit_key: Mapped[str] = mapped_column(String(80), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class EquipmentItem(Base):
    __tablename__ = "castle_equipment"
    __table_args__ = (UniqueConstraint("castle_id", "item_key", name="uq_castle_equipment"), CheckConstraint("count >= 0", name="ck_castle_equipment_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    item_key: Mapped[str] = mapped_column(String(80), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class FleetShip(Base):
    __tablename__ = "castle_fleet"
    __table_args__ = (UniqueConstraint("castle_id", "ship_key", name="uq_castle_fleet"), CheckConstraint("count >= 0", name="ck_castle_fleet_nonnegative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    ship_key: Mapped[str] = mapped_column(String(40), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class CastleEconomyState(Base):
    __tablename__ = "castle_economy_state"
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), primary_key=True)
    workshop_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    port_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    port_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_week_key: Mapped[str | None] = mapped_column(String(16))
    food_debt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    food_debt_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AdminLoginAttempt(Base):
    __tablename__ = "admin_login_attempts"
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class EquipmentBuildLimit(Base):
    __tablename__ = "castle_equipment_limits"
    __table_args__ = (UniqueConstraint("castle_id", "tracker_key", name="uq_equipment_limit_tracker"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    castle_id: Mapped[int] = mapped_column(ForeignKey("castles.id", ondelete="CASCADE"), nullable=False)
    tracker_key: Mapped[str] = mapped_column(String(120), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
