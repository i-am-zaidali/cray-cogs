import asyncio

import discord
from amari import AmariClient
from discord.ext import tasks
from redbot.core import commands

from .confhandler import conf


class main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = conf(bot)
        self.edit_minutes_task = self.end_giveaways.start()
        self.giveaway_cache = []

    def cog_unload(self):
        async def stop() -> asyncio.Task:
            self.edit_minutes_task.cancel()
            self.config.cache = self.giveaway_cache
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
        return s

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        data = self.giveaway_cache
        if payload.member.bot or not payload.guild_id:
            return
        if payload.message_id in (e := [i.message_id for i in data]):
            if str(payload.emoji) == (emoji := (ind := data[e.index(payload.message_id)]).emoji):
                if ind.requirements.null:
                    return

                else:
                    message = await ind.get_message()
                    requirements = ind.requirements.as_role_dict()
                    for key, value in requirements.items():
                        if value:
                            if isinstance(value, list):
                                for i in value:
                                    if key == "bypass" and i in payload.member.roles:
                                        pass

                                    elif key == "blacklist" and i in payload.member.roles:
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou had a role that was blacklisted from this giveaway.\nBlacklisted role: `{i.name}`",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at,
                                        )

                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue

                                    elif key == "required" and i not in payload.member.roles:
                                        if requirements["bypass"]:
                                            for r in requirements["bypass"]:
                                                if r in payload.member.roles:
                                                    continue
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou did not have the required role to join it.\nRequired role: `{i.name}`",
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
                                    if requirements["bypass"]:
                                        for role in requirements["bypass"]:
                                            if role in payload.member.roles:
                                                continue
                                    if int(level) < int(value):
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou are amari level `{level}` which is `{value - level}` levels fewer than the required `{value}`.",
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
                                    if requirements["bypass"]:
                                        for role in requirements["bypass"]:
                                            if role in payload.member.roles:
                                                continue
                                    weeklyxp = int(user.weeklyxp) if user else 0
                                    if int(weeklyxp) < int(value):
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou have `{weeklyxp}` weekly amari xp which is `{value - weeklyxp}` xp fewer than the required `{value}`.",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at,
                                        )
                                        embed.set_thumbnail(url=message.guild.icon_url)
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue

                                elif key == "ash_level":
                                    level = await self.levels.get_member_level(payload.member)
                                    if requirements["bypass"]:
                                        for role in requirements["bypass"]:
                                            if role in payload.member.roles:
                                                continue
                                    if int(level) < int(value):
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou are level `{level}` which is `{value - level}` levels fewer than the required `{value}`.",
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
        data = self.giveaway_cache
        for i in data:
            if i.remaining_time == 0:
                await i.end()
