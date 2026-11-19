import pytest

from bot.services import validate_castle_selection


def test_castle_registration_accepts_exact_official_catalog_tuple():
    validate_castle_selection("Winterfell", "North", "Stark")


@pytest.mark.parametrize(
    ("castle", "region", "house"),
    [
        ("Winterfell", "Vale", "Stark"),
        ("Winterfell", "North", "Bolton"),
        ("Winterfell", "North", "Unknown"),
        ("Made Up Castle", "North", "Stark"),
    ],
)
def test_castle_registration_rejects_non_catalog_tuple(castle, region, house):
    with pytest.raises(ValueError, match="کاتالوگ رسمی"):
        validate_castle_selection(castle, region, house)
