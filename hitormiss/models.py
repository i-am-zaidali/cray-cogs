import random
import secrets
from time import time
from typing import Dict, Optional, Type, Union

import discord

from .exceptions import ItemOnCooldown


def true_random():
    """
    idk man i was just bored of using random :p"""
    r1 = random.random() * 100
    r2 = secrets.randbelow(101)
    r3 = random.randrange(0, 101)
    r4 = random.randint(1, 100)

    return (r1 + r2 + r3 + r4) / 4


class BaseItem:
    """
    The point of this class is to simply be inherited from by all items,
    And to be checked with isinstance to make sure they are an item"""

    def __init__(
        self,
        damage: int,
        uses: int,
        accuracy: int,
        cooldown: int,
        throwable: bool,
        price: int,
        emoji: Optional[str],
    ) -> None:
        self.damage = int(damage)
        self.uses = int(uses)
        self.accuracy = int(accuracy)
        self.cooldown = int(cooldown)
        self.throwable = throwable
        self.price = int(price)
        self.emoji = emoji
        self.cache: Dict[int, Dict[str, Optional[Union[int, float]]]] = {}

    def __init_subclass__(cls) -> None:
        cls.name = cls.__name__.lower()

    def __str__(self) -> str:
        return self.name

    def _handle_usage(self, user):
        u = self.cache.setdefault(user.id, {"cooldown": None, "uses": self.uses})
        if u["cooldown"] is None or u["cooldown"] < time():
            u["cooldown"] = time() + self.cooldown
            u["uses"] -= 1
            if u["uses"] == 0:
                u["uses"] = self.uses  # reset the count for the next iteration of the item.
                user.inv.remove(self)
            return True

        else:
            raise ItemOnCooldown(
                f"{self.name} is on cooldown. Try again in {u['cooldown'] - time():.2f} seconds."
            )

    def get_remaining_uses(self, user):
        return self.cache.setdefault(user.id, {"cooldown": None, "uses": self.uses}).get("uses")

    def on_cooldown(self, user):
        u = self.cache.setdefault(user.id, {"cooldown": None, "uses": self.uses})
        return u.get("cooldown")


class Player:
    def __init__(self, user: discord.User, data: dict) -> None:
        self._user = user
        self.inv = Inventory(self, data.get("items", {}))
        self.hp: int = data.get("hp", 100)
        self.accuracy = data.get("accuracy", 10)
        self.throws = data.get("throws", 0)
        self.hits = data.get("hits", 0)
        self.misses = data.get("misses", 0)
        self.kills = data.get("kills", 0)
        self.deaths = data.get("deaths", 0)

    def __getattr__(self, attr):
        return getattr(self._user, attr)

    def __str__(self):
        return str(self._user)

    def to_dict(self):
        return {
            "hp": self.hp,
            "accuracy": self.accuracy,
            "throws": self.throws,
            "hits": self.hits,
            "misses": self.misses,
            "kills": self.kills,
            "deaths": self.deaths,
            "items": self.inv.to_dict(),
        }

    def reduce_hp(self, amount: int):
        if self.hp - amount <= 0:
            self.hp = 100
        else:
            self.hp -= amount

        return self.hp

    def increase_hp(self, amount: int):
        if self.hp == 100:
            return False
        self.hp += amount
        if self.hp > 100:
            self.hp = 100

        return self.hp

    def throw(self, other: "Player", item: BaseItem):
        if not self.inv.get(item.name):
            raise ValueError(f"You don't have a {item.name}")

        item._handle_usage(self)  # let the exceptions raise. The command gonna handle those.
        self.throws += 1

        if true_random() <= (item.damage + self.accuracy + (true_random() / 3)):
            self.hits += 1
            damage = random.randrange(1, item.damage)
            ohp = other.reduce_hp(damage)
            if true_random() > 75:
                self.accuracy += 0.5
            if ohp == 100:  # target's hp was 0 so it reset thus they were killed.
                oinv = other.inv.items
                for i in oinv:
                    self.inv.items.setdefault(i, 0)
                    self.inv.add(i, oinv[i])

                other.inv.clear(confirm=True)
                self.accuracy += 0.5  # increase your accuracy more when target is killed :p
                self.kills += 1
                other.deaths += 1
                return (
                    True,
                    f"You threw {item} at {other} and luck had it, that they got killed by it. You got all of the items they had.",
                )
            return (
                True,
                f"You threw {item} at {other} and they took {damage} damage. They now have {ohp} hp.",
            )

        self.misses += 1
        return (False, f"You threw {item} at {other} but you couldn't hit them.")

    @property
    def stats(self):
        items = (
            f"You own {len(self.inv.items)} items."
            if self.inv.items
            else "You don't own any items."
        )
        return (  # The docstring messed up the view on discord mobile ughhh
            f"Health Points (hp): **{self.hp}**\n\n"
            f"Accuracy: **{self.accuracy}**\n\n"
            f"Total Throws: **{self.throws}**\n\n"
            f"Total Hits: **{self.hits}**\n\n"
            f"Total Misses: **{self.misses}**\n\n"
            f"Total Kills: **{self.kills}**\n\n"
            f"Items: {items}"
        )

    @property
    def kdr(self):
        if self.deaths == 0:
            return 0
        return self.kills / self.deaths

    @property
    def new_player(self):
        """
        A property that shows if a player is new or not.
        This is for filtering purposes in the leaderboard."""
        return not self.throws  # if they haven't thrown yet, they are new.


class Inventory:
    def __init__(self, user: Player, items: Dict[Type[BaseItem], int]) -> None:
        self.user = user
        self.items = self._verify_items(items)

    def __call__(self):
        """
        Return a dict of items in a user's inventory with the keys being their names."""
        return {item.name: item for item in self.items}

    def _verify_items(self, items):
        """
        Just a safety methood to ensure that items are proper."""
        for item in items:
            if not isinstance(item, BaseItem):
                raise TypeError(
                    f"{item} is not a proper item. Items must inherit from `BaseItem`."
                )

        return items

    def get(self, item_name: str):
        return self.items.get(self().get(item_name))

    def add(self, item: BaseItem, amount: int = 1) -> None:
        self.items.setdefault(item, 0)
        self.items[item] += amount
        return self.items[item]

    def remove(self, item: BaseItem, amount: int = 1) -> None:
        self.items[item] -= amount if self.items[item] - amount >= 0 else self.items[item]
        if self.items[item] == 0:
            self.items.pop(item)
            return 0
        return self.items[item]

    def clear(self, *, confirm=False):
        if not confirm:
            raise RuntimeError(
                "You must confirm that you want to clear your inventory. Do so by passing the confirm kwarg as true."
            )

        self.items.clear()

    def to_dict(self):
        return {i.name: v for i, v in self.items.items()}
