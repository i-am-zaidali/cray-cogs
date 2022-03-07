from discord.ext.commands.converter import UserConverter
from fuzzywuzzy.process import extractOne
from redbot.core.commands import Converter

from .CONSTANTS import user_defaults
from .exceptions import ItemDoesntExist
from .models import Player


class ItemConverter(Converter):
    async def convert(self, ctx, name: str):
        items = ctx.cog.items
        match = extractOne(name, items.keys(), score_cutoff=80)
        if match:
            return items[match[0]]

        raise ItemDoesntExist(f"Item `{name}` doesn't exist.")


class PlayerConverter(UserConverter):
    async def convert(self, ctx, argument) -> Player:
        user = await super().convert(ctx, argument)
        for i in ctx.cog.cache:
            if user.id == i.id:
                return i

        item = await ItemConverter().convert(ctx, "snowball")
        defaults = user_defaults.copy()
        defaults.get("items", {}).update({item: 1})
        try:
            del defaults["items"]["snowball"]
        except KeyError:
            pass
        user = Player(ctx.bot, user.id, defaults)

        ctx.cog.cache.append(user)

        return user  # if user aint in cache, he hasn't played yet
