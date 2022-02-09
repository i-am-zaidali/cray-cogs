import discord
from discord.ext.commands.converter import EmojiConverter as ec
from discord.ext.commands.converter import PartialEmojiConverter
from emoji import UNICODE_EMOJI_ENGLISH
from redbot.core import commands
from redbot.core.bot import Red

old_tick = commands.context.TICK

old_get_context = Red.get_context


class FakeContext(commands.Context):
    tick_emoji = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def tick(self, *, message: str = None) -> bool:
        """Add a tick reaction to the command message.

        Keyword Arguments
        -----------------
        message : str, optional
            The message to send if adding the reaction doesn't succeed.

        Returns
        -------
        bool
            :code:`True` if adding the reaction succeeded.

        """

        emoji = (
            self.tick_emoji if self.channel.permissions_for(self.me).external_emojis else old_tick
        )

        return await self.react_quietly(emoji, message=message)


class EmojiConverter(ec):
    async def convert(self, ctx, argument):
        argument = argument.strip()
        if not argument in UNICODE_EMOJI_ENGLISH.keys():
            return await super().convert(ctx, argument)
        return argument
