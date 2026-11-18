from bot.database.models.core import Base, WarExpedition, MilitaryAlliance, GarrisonAsset, WarScenario, TroopTransferRequest, TradeOffer

def test_warfare_and_trade_tables_registered():
    expected = {"war_expeditions", "military_alliances", "garrison_assets", "war_scenarios", "troop_transfer_requests", "trade_offers"}
    assert expected.issubset(set(Base.metadata.tables))

def test_expedition_has_site_workflow_fields():
    columns = WarExpedition.__table__.columns
    for name in ("expedition_type", "asset_origin", "assets", "defender_assets", "command", "command_at", "scenario_deadline_at", "arrival_choice", "outcome", "casualties"):
        assert name in columns

def test_multi_asset_trade_fields_exist():
    assert "offered_assets" in TradeOffer.__table__.columns
    assert "requested_assets" in TradeOffer.__table__.columns

def test_alliance_and_garrison_ownership_are_persisted():
    assert "owner_a_lord_id" in MilitaryAlliance.__table__.columns
    assert "owner_lord_id" in GarrisonAsset.__table__.columns
    assert "scenario_text" in WarScenario.__table__.columns
    assert "assets" in TroopTransferRequest.__table__.columns
