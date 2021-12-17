from typing import Optional

user_defaults = {"hp": 100, "accuracy": 10, "items": {"snowball": 1}}

global_defaults = {
    "items": {
        "SnowBall": {
            "price": 1000,
            "damage": 10,
            "uses": 1,
            "cooldown": 60,
            "accuracy": 15,
            "throwable": True,
            "emoji": "❄️",
        },
        "PaintBall Gun": {
            "price": 2500,
            "damage": 20,
            "uses": 1,
            "cooldown": 60,
            "accuracy": 15,
            "throwable": True,
            "emoji": "🔫",
        },
        "Grenade": {
            "price": 7500,
            "damage": 30,
            "uses": 1,
            "cooldown": 120,
            "accuracy": 20,
            "throwable": True,
            "emoji": "💣",
        },
        "Axe": {
            "price": 10000,
            "damage": 40,
            "uses": 2,
            "cooldown": 150,
            "accuracy": 10,
            "throwable": True,
            "emoji": "🪓",
        },
        "MedKit": {
            "price": 5000,
            "damage": 40,  # here damage will actually be the amount it can heal.
            "uses": 1,
            "cooldown": 200,
            "accuracy": 30,  # here accuracy will be the chance of healing completely.
            "throwable": False,
            "emoji": "🩹",
        },
    }
}

dc_fields = [
    ("uses", int),
    ("damage", int),
    ("cooldown", int),
    ("accuracy", int),
    ("throwable", bool),
    ("price", int),
    ("emoji", Optional[str]),
]
