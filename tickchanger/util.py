from discord.ext.commands.converter import EmojiConverter as ec
from emoji import UNICODE_EMOJI_ENGLISH

class EmojiConverter(ec):
    async def convert(self, ctx, argument):
        argument = argument.strip()
        if not argument in UNICODE_EMOJI_ENGLISH.keys():
            return await super().convert(ctx, argument)
        return argument
