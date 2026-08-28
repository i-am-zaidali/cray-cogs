from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from .utils import EmojiConverter

old_tick = commands.context.TICK


class TickChanger(commands.Cog):
    """
    Change the emoji that gets reacted with when `await ctx.tick()`
    is called anywhere in the bot
    """

    __author__ = ["crayyy_zee"]
    __version__ = "1.3.0"

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

    @classmethod
    async def initialize(cls, bot: Red):
        s = cls(bot)
        emoji = await s.config.tick_emoji()
        commands.context.TICK = emoji
        return s

    def cog_unload(self):
        commands.context.TICK = old_tick

    @commands.command(name="settickemoji", aliases=["ste"])
    @commands.is_owner()
    async def ste(self, ctx: commands.Context, emoji: EmojiConverter):
        """
        Change the emoji that gets reacted with when `await ctx.tick()`
        is called anywhere in the bot"""
        await self.config.tick_emoji.set(str(emoji))
        commands.context.TICK = emoji
        await ctx.tick()
        await ctx.send(f"{emoji} is now the tick emoji.")

    @commands.command(name="gettickemoji", aliases=["gte"])
    @commands.is_owner()
    async def gte(self, ctx: commands.Context):
        """
        See which emoji is currently set to react"""
        return await ctx.send(f"Your current tick emoji is {await self.config.tick_emoji()}")
