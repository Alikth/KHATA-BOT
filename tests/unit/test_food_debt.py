from bot.game.engine import calculate_food_debt_casualties


def test_food_debt_losses_are_proportional():
    assert calculate_food_debt_casualties(
        {"swordsman": 90, "archer": 30, "spearman": 20},
        14,
    ) == {"swordsman": 9, "archer": 3, "spearman": 2}


def test_food_debt_largest_remainder_ties_are_deterministic():
    assert calculate_food_debt_casualties(
        {"swordsman": 1, "archer": 1, "spearman": 1},
        1,
    ) == {"swordsman": 1, "archer": 0, "spearman": 0}


def test_food_debt_never_removes_more_troops_than_exist():
    assert calculate_food_debt_casualties(
        {"swordsman": 2, "archer": 1},
        99,
    ) == {"swordsman": 2, "archer": 1}


def test_zero_food_debt_produces_no_casualties():
    assert calculate_food_debt_casualties({"swordsman": 5}, 0) == {"swordsman": 0}
