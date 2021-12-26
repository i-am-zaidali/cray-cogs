import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from .util import EmojiConverter, FakeContext, old_get_context, old_tick


class TickChanger(commands.Cog):
    """
    Change the emoji that gets reacted with when `await ctx.tick()`
    is called anywhere in the bot"""

    __author__ = ["crayyy_zee#2900"]
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, 987654321, True, "Tick")
        self.config.register_global(tick_emoji=old_tick)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def get_context(self, message: discord.Message, *, cls=FakeContext) -> commands.Context:
        return await old_get_context(self.bot, message, cls=cls)

    @classmethod
    async def initialize(cls, bot: Red):
        s = cls(bot)
        emoji = await s.config.tick_emoji()
        FakeContext.tick_emoji = emoji
        bot.old_get_context = bot.get_context
        bot.get_context = s.get_context
        return s

    def cog_unload(self):
        self.bot.get_context = self.bot.old_get_context

    @commands.command(name="settickemoji", aliases=["ste"])
    @commands.is_owner()
    async def ste(self, ctx: FakeContext, emoji: EmojiConverter):
        """
        Change the emoji that gets reacted with when `await ctx.tick()`
        is called anywhere in the bot"""
        await self.config.tick_emoji.set(str(emoji))
        FakeContext.tick_emoji = emoji
        await ctx.tick()
        await ctx.send(f"{emoji} is now the tick emoji.")

    @commands.command(name="gettickemoji", aliases=["gte"])
    @commands.is_owner()
    async def ste(self, ctx: FakeContext):
        return await ctx.send(f"Your current tick emoji is {await self.config.tick_emoji()}")
