from types import SimpleNamespace

import pytest

from bot.game.warfare import validate_expedition_route


def castle(name, coastal):
    return SimpleNamespace(name=name, is_coastal=coastal)


def test_land_route_allows_inland_origin_and_destination():
    validate_expedition_route(castle("Winterfell", False), castle("The Dreadfort", False), "land")


def test_land_route_allows_coastal_and_inland_mix():
    validate_expedition_route(castle("Seagard", True), castle("Winterfell", False), "land")


def test_sea_route_requires_coastal_origin():
    with pytest.raises(ValueError, match="مبدأ ساحلی"):
        validate_expedition_route(castle("Winterfell", False), castle("Pyke", True), "sea")


def test_sea_route_requires_coastal_destination():
    with pytest.raises(ValueError, match="مقصد ساحلی"):
        validate_expedition_route(castle("Pyke", True), castle("Winterfell", False), "sea")


def test_sea_route_allows_two_coastal_castles():
    validate_expedition_route(castle("Pyke", True), castle("Seagard", True), "sea")


def test_unknown_expedition_type_is_rejected():
    with pytest.raises(ValueError, match="land یا sea"):
        validate_expedition_route(castle("Pyke", True), castle("Seagard", True), "air")
