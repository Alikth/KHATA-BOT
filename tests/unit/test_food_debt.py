from bot.game.engine import calculate_food_debt_casualties


def test_food_debt_casualties_are_proportional():
    assert calculate_food_debt_casualties({"swordsman": 90, "archer": 10}, 3) == {
        "swordsman": 3,
        "archer": 0,
    }


def test_food_debt_casualties_distribute_remainders_deterministically():
    assert calculate_food_debt_casualties({"swordsman": 1, "archer": 1, "spearman": 1}, 2) == {
        "swordsman": 1,
        "archer": 1,
        "spearman": 0,
    }


def test_food_debt_casualties_never_exceed_available_army():
    assert calculate_food_debt_casualties({"swordsman": 2, "archer": 1}, 20) == {
        "swordsman": 2,
        "archer": 1,
    }


def test_no_food_debt_causes_no_casualties():
    assert calculate_food_debt_casualties({"swordsman": 5}, 0) == {"swordsman": 0}
