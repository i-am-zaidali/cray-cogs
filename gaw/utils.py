from typing import Callable

import discord
from redbot.core import commands


async def dict_keys_to(d: dict, conv: Callable = int):
    """Convert a dict's keys to the given conv. This will convert keys upto one nested dict."""
    final = {}
    for key, value in d.items():
        if isinstance(value, dict):
            final[conv(key)] = {conv(k): v for k, v in value.items()}
            continue

        final[conv(key)] = value

    return final


class Coordinate(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class SafeMember:
    def __init__(self, member: discord.Member):
        self._org = member
        self.id = member.id
        self.name = member.name
        self.mention = member.mention
        self.avatar_url = member.avatar_url

    def __str__(self) -> str:
        return self._org.__str__()

    def __getattr__(
        self, value
    ):  # if anyone tries to be sneaky and tried to access things they cant
        return f"donor.{value}"  # since its only used in one place where the var name is donor.
