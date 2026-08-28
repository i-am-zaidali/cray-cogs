from discord.ext.commands.converter import EmojiConverter as ec
from emoji import EMOJI_DATA


class EmojiConverter(ec):
    async def convert(self, ctx, argument):
        argument = argument.strip()
        try:
            EMOJI_DATA[argument]
        except KeyError:
            return await super().convert(ctx, argument)

        else:
            return argument
