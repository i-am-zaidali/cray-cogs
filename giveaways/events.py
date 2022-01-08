import asyncio
import logging
from datetime import datetime
from typing import List, Tuple

import discord
from amari import AmariClient
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

from .confhandler import conf
from .models import EndedGiveaway, Giveaway, PendingGiveaway

log = logging.getLogger("red.craycogs.giveaways")


class main(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = conf(bot)
        self.edit_minutes_task = self.end_giveaways.start()
        self.giveaway_cache: List[Giveaway] = []
        self.ended_cache: List[EndedGiveaway] = []
        self.pending_cache: List[PendingGiveaway] = []
        self.backup_task: asyncio.Task = None

    async def backup_cache(self, interval: int):
        while True:
            await asyncio.sleep(interval)
            await self.config.cache_to_config()
            log.debug(f"Backing up cache every {humanize_timedelta(seconds=interval)}!")

    def cog_unload(self):
        async def stop() -> asyncio.Task:
            self.edit_minutes_task.cancel()
            self.config.cache = self.giveaway_cache
            self.config.ended_cache = self.ended_cache
            self.config.pending_cache = self.pending_cache
            if self.backup_task:
                self.backup_task.cancel()
            await self.config.cache_to_config()
            if getattr(self.bot, "amari", None):
                await self.bot.amari.close()

        self.bot.loop.create_task(stop())
        return

    @classmethod
    async def inititalze(cls, bot):
        s = cls(bot)
        if not getattr(bot, "amari", None):
            keys = await bot.get_shared_api_tokens("amari")
            auth = keys.get("auth")
            if auth:
                amari = AmariClient(bot, auth)
                bot.amari = amari

            else:
                if not await s.config._sent_message():
                    await bot.send_to_owners(
                        f"""
Thanks for installing and using my Giveaways cog.
This cog has a requirements system for the giveaways and one of
these requirements type is amari levels.
If you don't know what amari is, ignore this message.
But if u do, you need an Amari auth key for these to work,
go to this website: https://forms.gle/TEZ3YbbMPMEWYuuMA
and apply to get the key. You should probably get a response within
24 hours but if you don't, visit this server for information: https://discord.gg/6FJhupDHS6

You can then set the amari api key with the `[p]set api amari auth,<api key>` command"""
                    )

                    await s.config._sent_message(True)

        s.amari = getattr(bot, "amari", None)
        await s.config.config_to_cache(bot, s)
        s.giveaway_cache = s.config.cache
        s.ended_cache = s.config.ended_cache
        s.pending_cache = s.config.pending_cache

        if interval := await s.config.config.backup():
            s.backup_task = s.bot.loop.create_task(s.backup_cache(interval))
        return s

    async def get_active_giveaways(
        self, guild: discord.Guild = None
    ) -> Tuple[List[Giveaway], List[EndedGiveaway]]:
        data = self.giveaway_cache.copy()
        active = []
        failed = []
        for i in data:
            if guild is not None:
                if i.guild != guild:
                    continue
            if await i.get_message() is None:
                failed.append(await i.end())
            else:
                active.append(i)

        return active, failed

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        data = self.giveaway_cache
        if payload.member.bot or not payload.guild_id:
            return
        if payload.message_id in (e := [i.message_id for i in data]):
            if str(payload.emoji) == (emoji := (ind := data[e.index(payload.message_id)]).emoji):
                results = await ind.verify_entry(payload.member)
                if results is True:
                    return
                elif isinstance(results, tuple):
                    message = await ind.get_message()
                    description = results[1]
                    try:
                        await message.remove_reaction(emoji, payload.member)
                    except discord.Forbidden:
                        pass
                    embed = discord.Embed(
                        title="Entry Invalidated!",
                        description=description,
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow(),
                    ).set_thumbnail(url=message.guild.icon_url)
                    try:
                        return await payload.member.send(embed=embed)
                    except Exception:
                        return

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if message.author.bot:
            return

        giveaways = list(
            filter(
                lambda x: x.requirements.messages != 0,
                (await self.get_active_giveaways(message.guild))[0],
            )
        )

        if not giveaways:
            return

        for i in giveaways:
            bucket = i._message_cooldown.get_bucket(message)
            retry_after = bucket.update_rate_limit()
            if not retry_after:
                i._message_cache.setdefault(message.author.id, 0)
                i._message_cache[message.author.id] += 1

    @tasks.loop(seconds=5)
    async def end_giveaways(self):
        active_data = self.giveaway_cache.copy()
        pending_data = self.pending_cache.copy()
        for i in active_data:
            await i.edit_timer()
            if i.remaining_time == 0:
                try:
                    await i.end()
                except Exception as e:
                    log.exception("There was an exception while ending giveaways: \n", exc_info=e)

        for i in pending_data:
            if i.remaining_time_to_start == 0:
                await i.start_giveaway()
                self.pending_cache.remove(i)

    @end_giveaways.before_loop
    async def end_giveaways_after(self):
        await self.bot.wait_until_red_ready()
