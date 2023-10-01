import asyncio
import itertools
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .models import TimerObj, TimerSettings
from .utils import EmojiConverter, TimeConverter

guild_defaults = {"timers": [], "timer_settings": {"notify_users": True, "emoji": "\U0001f389"}}
log = logging.getLogger("red.craycogs.Timer.timers")

_T = TypeVar("_T")

Missing = object()


def all_min(
    iterable: Iterable[_T],
    key: Callable[[_T], Any] = lambda x: x,
    *,
    sortkey: Optional[Callable[[_T], Any]] = Missing,
):
    """A simple one liner function that returns all the least elements of an iterable instead of just one like the builtin `min()`.

    !!!!!! SORT THE DATA PRIOR TO USING THIS FUNCTION !!!!!!
    or pass the `sortkey` argument to this function which will be passed to the `sorted()` builtin to sort the iterable

    A small explanation of what it does from bard:
    - itertools.groupby() groups the elements in the iterable by their key value.
    - map() applies the function lambda x: (x[0], list(x[1])) to each group.
      This function returns a tuple containing the key of the group and a list of all of the elements in the group.
    - min() returns the tuple with the minimum key value.
    - [1] gets the second element of the tuple, which is the list of all of the minimum elements in the iterable.
    """
    if sortkey is not Missing:
        iterable = sorted(iterable, key=sortkey)
    try:
        return min(
            map(lambda x: (x[0], list(x[1])), itertools.groupby(iterable, key=key)),
            key=lambda x: x[0],
        )[1]

    except ValueError:
        return []


class Timer(commands.Cog):
    """Start countdowns that help you keep track of the time passed"""

    __author__ = ["crayyy_zee"]
    __version__ = "1.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, 1, True)
        self.config.register_guild(**guild_defaults)
        self.config.register_global(max_duration=3600 * 12)  # a day long duration by default

        self.cache: Dict[int, List[TimerObj]] = {}

        self.task = self.end_timer.start()
        self.to_end: List[TimerObj] = []

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        for timers in self.cache.values():
            for timer in timers:
                if timer._host == user_id:
                    await timer.end()
                    await self.remove_timer(timer)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {cf.humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def cog_load(self):
        guilds = await self.config.all_guilds()

        for guild_data in guilds.values():
            for x in guild_data.get("timers", []):
                x.update({"bot": self.bot})
                timer = TimerObj.from_json(x)
                await self.add_timer(timer)

        self.max_duration: int = await self.config.max_duration()

    async def get_timer(self, guild_id: int, timer_id: int):
        if not (guild := self.cache.get(guild_id)):
            return None

        for timer in guild:
            if timer.message_id == timer_id:
                return timer

    async def add_timer(self, timer: TimerObj):
        if await self.get_timer(timer.guild_id, timer.message_id):
            return
        self.cache.setdefault(timer.guild_id, []).append(timer)

    async def remove_timer(self, timer: TimerObj):
        if not (guild := self.cache.get(timer.guild_id)):
            return
        self.cache[timer.guild_id].remove(timer)

    async def get_guild_settings(self, guild_id: int):
        return TimerSettings(**await self.config.guild_from_id(guild_id).timer_settings())

    async def _back_to_config(self):
        for guild_id, timers in self.cache.items():
            await self.config.guild_from_id(guild_id).timers.set([x.json for x in timers])

    async def cog_unload(self):
        self.task.cancel()
        await self._back_to_config()

    @tasks.loop(seconds=1)
    async def end_timer(self):
        if self.end_timer._current_loop and self.end_timer._current_loop % 100 == 0:
            await self.to_config()

        results = await asyncio.gather(
            *[timer.end() for timer in self.to_end], return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                log.error(f"A timer ended with an error:", exc_info=result)

        self.to_end = all_min(
            itertools.chain.from_iterable(self.cache.values()),
            key=lambda x: x.remaining_time,
            sortkey=lambda x: x.remaining_time,
        )

        interval = getattr(next(iter(self.to_end), None), "remaining_time", 1)
        self.end_timer.change_interval(seconds=interval)

    @commands.group(name="timer")
    @commands.mod_or_permissions(manage_messages=True)
    async def timer(self, ctx: commands.Context):
        """
        Manage Timers."""

    @timer.command(name="start")
    @commands.bot_has_permissions(embed_links=True)
    async def timer_start(
        self, ctx: commands.Context, time: TimeConverter, *, name: str = "New Timer!"
    ):
        """
        Start a timer.

        `time`: The duration to start the timer. The duration uses basic time units
                `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks)
                The maximum duration is 12 hours. change that with `timerset maxduration`.

        `name`: The name of the timer.
        """

        timer = TimerObj(
            **{
                "message_id": None,
                "channel_id": ctx.channel.id,
                "guild_id": ctx.guild.id,
                "bot": ctx.bot,
                "name": name,
                "emoji": (await self.get_guild_settings(ctx.guild.id)).emoji,
                "host": ctx.author.id,
                "ends_at": time,
            }
        )

        await timer.start()
        await ctx.tick(message="Timer for `{}` started!".format(name))

    @timer.command(name="end")
    async def timer_end(self, ctx: commands.Context, timer_id: int):
        """
        End a timer.

        `timer_id`: The `msg-ID` of the timer to end.
        """

        timer = await self.get_timer(ctx.guild.id, timer_id)

        if timer is None:
            await ctx.send("Timer not found.")
            return

        await timer.end()
        await ctx.tick(message="Timer ended!")

    @timer.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def timer_list(self, ctx: commands.Context):
        """
        Get a list of all the active timers in this server."""
        if not self.cache.get(ctx.guild.id):
            await ctx.send("No timers found.")
            return

        embed = discord.Embed(
            title="Timers in **{}**".format(ctx.guild.name),
            description="\n".join(
                "{} - {}".format(
                    f"[{x.name}]({x.jump_url})", cf.humanize_timedelta(timedelta=x.remaining_time)
                )
                for x in self.cache[ctx.guild.id]
            ),
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=embed)

    @commands.group(name="timerset", aliases=["tset", "timersettings"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def tset(self, ctx: commands.Context):
        """
        Customize settings for timers."""

    @tset.command(name="emoji")
    async def tset_emoji(self, ctx: commands.Context, emoji: EmojiConverter):
        """
        Change the emoji used for timers.

        `emoji`: The emoji to use.
        """

        await self.config.guild_from_id(ctx.guild.id).timer_settings.emoji.set(emoji)
        await ctx.tick()

    @tset.command(name="maxduration", aliases=["duration", "md"])
    @commands.is_owner()
    async def tset_duration(self, ctx: commands.Context, duration: TimeConverter(True)):
        """
        Change the max duration for timers.

        `duration`: The duration to set.
        """

        await self.config.max_duration.set(duration.total_seconds())
        await ctx.tick()

    @tset.command(name="notifyusers", aliases=["notify"])
    async def tset_notify(self, ctx: commands.Context, notify: bool):
        """
        Toggle whether or not to notify users when a timer ends.

        `notify`: Whether or not to notify users. (`True`/`False`)
        """

        await self.config.guild_from_id(ctx.guild.id).timer_settings.notify_users.set(notify)
        await ctx.tick()

    @tset.command(name="showsettings", aliases=["ss", "showsetting", "show"])
    async def tset_showsettings(self, ctx: commands.Context):
        """
        See the configured settings for timers in your server."""
        settings = await self.get_guild_settings(ctx.guild.id)
        embed = discord.Embed(
            title=f"Timer Settings for **{ctx.guild.name}**",
            description=f"Emoji: `{settings.emoji}`\n"
            f"Notify users: `{settings.notify_users}`"
            + (
                f"\nMax duration: `{cf.humanize_timedelta(seconds=await self.config.max_duration())}`"
                if await ctx.bot.is_owner(ctx.author)
                else ""
            ),
        )

        await ctx.send(embed=embed)
