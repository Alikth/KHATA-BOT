from scripts.backup import connection_parts as backup_connection_parts
from scripts.restore import connection_parts as restore_connection_parts


def test_postgres_url_parsing_decodes_credentials():
    url = "postgresql+asyncpg://khata:p%40ss%3Aword@db.example:5433/khata_bot"
    expected = {
        "host": "db.example",
        "port": "5433",
        "user": "khata",
        "password": "p@ss:word",
        "database": "khata_bot",
    }
    assert backup_connection_parts(url) == expected
    assert restore_connection_parts(url) == expected
