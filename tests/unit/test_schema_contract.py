from pathlib import Path


def test_initial_migration_has_data_safety_constraints():
    migration = Path("bot/database/migrations/0001_initial.sql").read_text(encoding="utf-8")
    assert "UNIQUE" in migration
    assert "CHECK (amount >= 0)" in migration
    assert "admin_audit_logs" in migration
    assert "idempotency_key" in migration
    assert "ON DELETE RESTRICT" in migration


def test_site_catalog_contains_site_resources_and_castles():
    import json
    catalog = json.loads(Path("bot/game/site_catalog.json").read_text(encoding="utf-8"))
    assert "peasants" in catalog["RESOURCE_KEYS"]
    assert "dragon_glass" in catalog["RESOURCE_KEYS"]
    assert "Winterfell" in catalog["castleInfo"]
    assert "Highgarden" in catalog["castleInfo"]


def test_models_have_one_group_per_castle_and_one_lord_per_castle():
    from bot.database.models import Castle, Lord, GroupRegistration
    assert "uq_castles_name" in {c.name for c in Castle.__table__.constraints}
    assert any(getattr(c, "name", None) == "uq_lords_telegram_user_id" for c in Lord.__table__.constraints)
    assert any(getattr(c, "name", None) == "uq_group_registrations_chat" for c in GroupRegistration.__table__.constraints)

def test_site_catalog_has_full_resource_and_production_definitions():
    import json
    from pathlib import Path
    catalog=json.loads((Path(__file__).parents[2]/"bot/game/site_catalog.json").read_text(encoding="utf-8"))
    assert len(catalog["RESOURCE_KEYS"]) == 13
    assert set(catalog["GENERAL_PRODUCTIONS"]) >= {"farm","lumber","stone","iron","village","market","stable"}
    assert "Riverlands" in catalog["SPECIAL_PRODUCTIONS"]
    assert "Reach" in catalog["SPECIAL_CAMPS"]
    assert "Highgarden" in catalog["WAR_LORDS"]
