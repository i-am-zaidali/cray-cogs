import asyncio
from datetime import datetime
from typing import List

import discord
from amari import AmariClient
from discord.ext import tasks
from redbot.core import commands

from .confhandler import conf
from .models import EndedGiveaway, Giveaway, PendingGiveaway


class main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = conf(bot)
        self.edit_minutes_task = self.end_giveaways.start()
        self.giveaway_cache: List[Giveaway] = []
        self.ended_cache: List[EndedGiveaway] = []
        self.pending_cache: List[PendingGiveaway] = []

    def cog_unload(self):
        async def stop() -> asyncio.Task:
            self.edit_minutes_task.cancel()
            self.config.cache = self.giveaway_cache
            self.config.ended_cache = self.ended_cache
            self.config.pending_cache = self.pending_cache
            await self.config.cache_to_config()
            if getattr(self.bot, "amari", None):
                await self.bot.amari.close()

        asyncio.create_task(stop())
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
        return s

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        data = self.giveaway_cache
        if payload.member.bot or not payload.guild_id:
            return
        if payload.message_id in (e := [i.message_id for i in data]):
            if str(payload.emoji) == (emoji := (ind := data[e.index(payload.message_id)]).emoji):
                message = await ind.get_message()
                if not ind.donor_can_join and payload.member.id == ind._donor:
                    await message.remove_reaction(emoji, payload.member)
                    embed = discord.Embed(
                        title="Entry Invalidated!",
                        description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                        f"This giveaway used the `--no-donor` flag which disallows the donor/host to join  the giveaway.",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow(),
                    )
                    try:
                        return await ind.donor.send(embed=embed)
                    except Exception:
                        return

                if ind.requirements.null:
                    return

                else:
                    requirements = ind.requirements.as_role_dict()

                    if requirements["bypass"]:
                        maybe_bypass = any(
                            [role in payload.member.roles for role in requirements["bypass"]]
                        )
                        if maybe_bypass:
                            return  # All the below requirements can be overlooked if user has bypass role.

                    for key, value in requirements.items():
                        if value:
                            if isinstance(value, list):
                                for i in value:
                                    if key == "blacklist" and i in payload.member.roles:
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                            "You had a role that was blacklisted from this giveaway.\n"
                                            f"Blacklisted role: `{i.name}`",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at,
                                        )

                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue

                                    elif key == "required" and i not in payload.member.roles:
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                            "You did not have the required role to join it.\n"
                                            f"Required role: `{i.name}`",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at,
                                        )
                                        embed.set_thumbnail(url=message.guild.icon_url)
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue

                            else:
                                user = None
                                if key == "amari_level":
                                    try:
                                        user = await self.amari.getGuildUser(
                                            payload.member.id, payload.member.guild.id
                                        )
                                    except:
                                        pass
                                    level = int(user.level) if user else 0
                                    if int(level) < int(value):
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                            f"You are amari level `{level}` which is `{value - level}` levels fewer than the required `{value}`.",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at,
                                        )
                                        embed.set_thumbnail(url=message.guild.icon_url)
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue

                                elif key == "amari_weekly":
                                    try:
                                        user = await self.amari.getGuildUser(
                                            payload.member.id, payload.member.guild.id
                                        )
                                    except:
                                        pass
                                    weeklyxp = int(user.weeklyxp) if user else 0
                                    if int(weeklyxp) < int(value):
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                            f"You have `{weeklyxp}` weekly amari xp which is `{value - weeklyxp}` xp fewer than the required `{value}`.",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at,
                                        )
                                        embed.set_thumbnail(url=message.guild.icon_url)
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue

    @tasks.loop(seconds=5)
    async def end_giveaways(self):
        await self.bot.wait_until_red_ready()
        active_data = self.giveaway_cache.copy()
        pending_data = self.pending_cache.copy()
        for i in active_data:
            await i.edit_timer()
            if i.remaining_time == 0:
                await i.end()

        for i in pending_data:
            if i.remaining_time_to_start == 0:
                await i.start_giveaway()
                self.pending_cache.remove(i)
