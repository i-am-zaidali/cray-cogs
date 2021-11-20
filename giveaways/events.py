import discord
import asyncio

from redbot.core import commands
from discord.ext import tasks
from .confhandler import conf
from amari import AmariClient
    
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
                    await bot.send_to_owners(f"""
                                            Thanks for installing and using my Giveaways cog.
                                            This cog has a requirements system for the giveaways and one of 
                                            these requirements type is amari levels.
                                            If you don't know what amari is, ignore this message.
                                            But if u do, you need an Amari auth key for these to work,
                                            go to this website: https://forms.gle/TEZ3YbbMPMEWYuuMAa
                                            and apply to get the key. You should probably get a response within 
                                            24 hours but if you don't, visit this server for information: https://discord.gg/6FJhupDHS6
                                            
                                            You can then set the amari api key with the `{ctx.prefix}set api amari auth,<api key>` command""")
                    
                    await s.config._sent_message(True)
                
        s.amari = getattr(bot, "amari", None)
        await s.config.config_to_cache(bot, s)
        s.giveaway_cache = s.config.cache
        return s
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload : discord.RawReactionActionEvent):
        data = self.giveaway_cache
        if payload.member.bot or not payload.guild_id:
            return
        if payload.message_id in (e:=[i.message_id for i in data]):
            if str(payload.emoji) == (emoji:=(ind:=data[e.index(payload.message_id)]).emoji):
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
                                            timestamp=message.created_at
                                        )
                                        
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue
                                    
                                    elif key == "required" and i not in payload.member.roles:
                                        if requirements["bypass"]:
                                            for r in requirements["bypass"]:
                                                if role in payload.member.roles:
                                                    continue
                                        await message.remove_reaction(emoji, payload.member)
                                        embed = discord.Embed(
                                            title="Entry Invalidated!",
                                            description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou did not have the required role to join it.\nRequired role: `{i.name}`",
                                            color=discord.Color.random(),
                                            timestamp=message.created_at
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
                                        user = await self.amari.getGuildUser(payload.member.id, payload.member.guild.id)
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
                                            timestamp=message.created_at
                                        )
                                        embed.set_thumbnail(url=message.guild.icon_url)
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue
                                    
                                elif key == "amari_weekly":
                                    try:
                                        user = await self.amari.getGuildUser(payload.member.id, payload.member.guild.id)
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
                                            timestamp=message.created_at
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
                                            timestamp=message.created_at
                                        )
                                        embed.set_thumbnail(url=message.guild.icon_url)
                                        try:
                                            await payload.member.send(embed=embed)
                                        except discord.HTTPException:
                                            pass
                                        continue
        # for key, value in data.items():
        #     if str(payload.message_id) == key:
        #         requirements = value["requirements"]
        #         chan_id = value["channel"]
        #         guild = self.bot.get_guild(payload.guild_id)
        #         channel = await self.bot.fetch_channel(int(chan_id))
        #         message = await channel.fetch_message(int(key))
        #         emoji = value["emoji"]
        #         if message and str(payload.emoji) == str(emoji) and payload.member != message.guild.me:
        #             for key, value in requirements.items():
        #                 if value:
        #                     if isinstance(value, list):
        #                         for i in value:
        #                             i = guild.get_role(int(i))
        #                             if key in ["bypass", "default_bypass"] and i in payload.member.roles:
        #                                 pass
                                    
        #                             elif key in ["blacklist", "default_blacklist"] and i in payload.member.roles:
        #                                 await message.remove_reaction(emoji, payload.member)
        #                                 embed = discord.Embed(
        #                                     title="Entry Invalidated!",
        #                                     description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou had a role that was blacklisted from this giveaway.\nBlacklisted role: `{i.name}`",
        #                                     color=discord.Color.random(),
        #                                     timestamp=message.created_at
        #                                 )
                                        
        #                                 try:
        #                                     await payload.member.send(embed=embed)
        #                                 except discord.HTTPException:
        #                                     pass
        #                                 continue
                                    
        #                             elif key == "required" and i not in payload.member.roles:
        #                                 if requirements["bypass"]:
        #                                     for r in requirements["bypass"]:
        #                                         role = guild.get_role(r)
        #                                         if role in payload.member.roles:
        #                                             continue
        #                                 await message.remove_reaction(emoji, payload.member)
        #                                 embed = discord.Embed(
        #                                     title="Entry Invalidated!",
        #                                     description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou did not have the required role to join it.\nRequired role: `{i.name}`",
        #                                     color=discord.Color.random(),
        #                                     timestamp=message.created_at
        #                                 )
        #                                 embed.set_thumbnail(url=message.guild.icon_url)
        #                                 try:
        #                                     await payload.member.send(embed=embed)
        #                                 except discord.HTTPException:
        #                                     pass
        #                                 continue
                                        
        #                     else:
        #                         user = None
        #                         if key == "alevel":
        #                             try:
        #                                 user = await self.amari.getGuildUser(payload.member.id, payload.member.guild.id)
        #                             except:
        #                                 pass
        #                             level = int(user.level) if user else 0
        #                             if requirements["bypass"]:
        #                                 for r in requirements["bypass"]:
        #                                     role = guild.get_role(r)
        #                                     if role in payload.member.roles:
        #                                         continue
        #                             if int(level) < int(value):
        #                                 await message.remove_reaction(emoji, payload.member)
        #                                 embed = discord.Embed(
        #                                     title="Entry Invalidated!",
        #                                     description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou are amari level `{level}` which is `{value - level}` levels fewer than the required `{value}`.",
        #                                     color=discord.Color.random(),
        #                                     timestamp=message.created_at
        #                                 )
        #                                 embed.set_thumbnail(url=message.guild.icon_url)
        #                                 try:
        #                                     await payload.member.send(embed=embed)
        #                                 except discord.HTTPException:
        #                                     pass
        #                                 continue
                                    
        #                         elif key == "aweekly":
        #                             try:
        #                                 user = await self.amari.getGuildUser(payload.member.id, payload.member.guild.id)
        #                             except:
        #                                 pass
        #                             if requirements["bypass"]:
        #                                 for r in requirements["bypass"]:
        #                                     role = guild.get_role(r)
        #                                     if role in payload.member.roles:
        #                                         continue
        #                             weeklyxp = int(user.weeklyxp) if user else 0
        #                             if int(weeklyxp) < int(value):
        #                                 await message.remove_reaction(emoji, payload.member)
        #                                 embed = discord.Embed(
        #                                     title="Entry Invalidated!",
        #                                     description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou have `{weeklyxp}` weekly amari xp which is `{value - weeklyxp}` xp fewer than the required `{value}`.",
        #                                     color=discord.Color.random(),
        #                                     timestamp=message.created_at
        #                                 )
        #                                 embed.set_thumbnail(url=message.guild.icon_url)
        #                                 try:
        #                                     await payload.member.send(embed=embed)
        #                                 except discord.HTTPException:
        #                                     pass
        #                                 continue
                                    
        #                         elif key == "level":
        #                             level = await self.levels.get_member_level(payload.member)
        #                             if requirements["bypass"]:
        #                                 for r in requirements["bypass"]:
        #                                     role = guild.get_role(r)
        #                                     if role in payload.member.roles:
        #                                         continue
        #                             if int(level) < int(value):
        #                                 await message.remove_reaction(emoji, payload.member)
        #                                 embed = discord.Embed(
        #                                     title="Entry Invalidated!",
        #                                     description=f"Your entry for [this]({message.jump_url}) giveaway has been removed.\nYou are level `{level}` which is `{value - level}` levels fewer than the required `{value}`.",
        #                                     color=discord.Color.random(),
        #                                     timestamp=message.created_at
        #                                 )
        #                                 embed.set_thumbnail(url=message.guild.icon_url)
        #                                 try:
        #                                     await payload.member.send(embed=embed)
        #                                 except discord.HTTPException:
        #                                     pass
        #                                 continue
                                        
                                        
    @tasks.loop(seconds=5)
    async def end_giveaways(self):
        await self.bot.wait_until_red_ready()
        data = self.giveaway_cache
        for i in data:
            if i.remaining_time == 0:
                await i.end()
        # for key, value in data.items():
        #     if time.time() >= value["end"]:
        #         chanid = value["channel"]
        #         channel = self.bot.get_channel(int(chanid))
        #         if channel is None:
        #             channel = await self.bot.fetch_channel(int(chanid))
        #         try:
        #             msg = await channel.fetch_message(int(key))
        #         except discord.NotFound as e:
        #             await channel.send(f"Can't find message with id: {key}. Removing id from active giveaways.")
        #             del data[key]
        #             return
        #         winners = value["winners"]
        #         embed = msg.embeds[0]
        #         prize = value["prize"]
        #         host = value["author"]
        #         winnerdm = await self.config.dm_winner(channel.guild)
        #         hostdm = await self.config.dm_host(channel.guild)
        #         endmsg :str = await self.config.get_guild_endmsg(channel.guild)
        #         channel = msg.channel
        #         gmsg = await channel.fetch_message(msg.id)
        #         entrants = await gmsg.reactions[0].users().flatten()
        #         try: entrants.pop(entrants.index(msg.guild.me))
        #         except: pass
        #         entrants = await self.config.get_list_multi(channel.guild, entrants)
        #         link = gmsg.jump_url

        #         if len(entrants) == 0 or winners == 0:
        #             embed = gmsg.embeds[0]
        #             embed.description = f"This giveaway has ended.\nThere were 0 winners.\n**Host:** <@{host}>"
        #             embed.set_footer(
        #                 text=f"{msg.guild.name} - Winners: {winners}", icon_url=msg.guild.icon_url)
        #             await gmsg.edit(embed=embed)

        #             await gmsg.reply(f"The giveaway for ***{prize}*** has ended. There were 0 winners.\nClick on my replied message to jump to the giveaway.")
        #             if hostdm == True:
        #                 await hdm(self, host, gmsg.jump_url, prize, "None")

        #             del data[str(key)]
        #             return

        #         w = ""
        #         w_list = []

        #         for i in range(winners):
        #             winner = random.choice(entrants)
        #             w_list.append(winner.id)
        #             w += f"{winner.mention} "

        #         formatdict = {
        #             "winner": w,
        #             "prize": prize,
        #             "link": link
        #         }

        #         embed = gmsg.embeds[0]
        #         embed.description = f"This giveaway has ended.\n**Winners:** {w}\n**Host:** <@{host}>"
        #         embed.set_footer(
        #             text=f"{msg.guild.name} - Winners: {winners}", icon_url=msg.guild.icon_url)
        #         await gmsg.edit(embed=embed)

        #         await gmsg.reply(endmsg.format_map(formatdict))

        #         winnerdm = await self.config.dm_winner(channel.guild)
        #         hostdm = await self.config.dm_host(channel.guild)
        #         if winnerdm == True:
        #             await wdm(self, w_list, gmsg.jump_url, prize, channel.guild)

        #         if hostdm == True:
        #             await hdm(self, host, gmsg.jump_url, prize, w)

        #         del self.giveaway_cache[str(key)]
        #         return
