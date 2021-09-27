import discord
from discord import Member
import re
from discord.ext.commands.converter import Greedy, RoleConverter

from redbot.core import Config, commands
from redbot.core.utils import mod
from redbot.core.utils.menus import menu, start_adding_reactions, DEFAULT_CONTROLS
from redbot.core.bot import Red
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.chat_formatting import humanize_list, humanize_number
from discord.ext.commands.view import StringView
import typing
from collections import namedtuple
from redbot.core.commands import RedHelpFormatter
import time
from .utils import *
import asyncio

class flags(commands.Converter):
    """
    This is a custom flag parsing class made by me with help from skelmis (ethan) from menudocs."""
    def __init__(self, *, delim=None, start=None):
        self.delim = delim or " "
        self.start = start or "--"

    async def convert(self, ctx, argument):
        x = True
        argless = []
        data = {None: []}
        argument = argument.split(self.start)

        if (length := len(argument)) == 1:
            # No flags
            argless.append(argument[0])
            x = False  # Don't loop

        i = 0
        while x:
            if i >= length:
                # Have consumed all
                break

            if self.delim in argument[i]:
                # Get the arg name minus start state
                arg = argument[i].split(self.delim, 1)

                if len(arg) == 1:
                    # Arg has no value, so its argless
                    # This still removes the start and delim however
                    argless.append(arg)
                    i += 1
                    continue

                arg_name = arg[0]
                arg_value = arg[1].strip()

                data[arg_name] = arg_value

            else:
                argless.append(argument[i])

            i += 1

        # Time to manipulate argless
        # into the same expected string pattern
        # as dpy's argparsing
        for arg in argless:
            view = StringView(arg)
            while not view.eof:
                word = view.get_quoted_word()
                data[None].append(word)
                view.skip_ws()

        if not bool(data[None]):
            data.pop(None)

        return data

        
class DonationLogging(commands.Cog):
    """
    Donation logging commands. Helps you in counting and tracking user donations and automatically assigning them roles.
    """
    
    __version__ = "1.5.0"
    __author__ = ["crayyy_zee#2900"]
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123_6969_420)
        self.cache = {}

        default_guild = {
            "managers" : [],
            "logchannel" : None,
            "donations" : {},
            "assignroles" : {},
            "currency": "⏣",
            "autoadd": False,
            "autoremove": False
        }
        default_member = {
            "donations": 0,
            "notes": {}
        }

        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)
        asyncio.create_task(self.to_cache())
        return
    
    def format_help_for_context(self, ctx: commands.Context):
        pre_processed = super().format_help_for_context(ctx)
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)
    
    def cog_unload(self):
        asyncio.create_task(self.to_config())
        
    async def red_delete_data_for_user(self, *, requester, user_id: int):
        if requester not in ("discord_deleted_user", "user"):
            return
        for guild, data in self.cache.items():
            try:
                del data[str(user_id)]
            except KeyError:
                continue
  
    async def to_cache(self):
        self.cache = await self.config.all_members()
        
    async def to_config(self):
        for guild, memberdata in self.cache.items():
            for member, data in memberdata.items():
                await self.config.member_from_ids(int(guild), int(member)).donations.set(data)

    async def GetMessage(self, ctx :commands.Context, contentOne, contentTwo, timeout=100):
        embed = discord.Embed(title=f"{contentOne}", description=f"{contentTwo}", color=await ctx.embed_color())
        sent = await ctx.send(embed=embed)
        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=timeout,
                check=lambda message: message.author == ctx.author
                and message.channel == ctx.channel,
            )
            if msg:
                return msg.content

        except asyncio.TimeoutError:
            return False

    def is_dmgr():
        async def predicate(ctx):
            data = await ctx.cog.config.guild(ctx.guild).managers()
            if data:
                for i in data:
                    role = ctx.guild.get_role(int(i))
                    if role and role in ctx.author.roles:
                        return True

            elif ctx.author.guild_permissions.administrator == True:
                return True
            
            elif await mod.is_mod_or_superior(ctx.bot, ctx.author) == True:
                return True

        return commands.check(predicate)

    async def open_account(self, user, guild):
        data = self.cache.get(str(guild.id))
        if data:
            if str(user.id) in data:
                return False

            else:
                data[str(user.id)] = 0
                return True
        else:
            self.cache[str(guild.id)] = {}
            self.cache[str(guild.id)][str(user.id)] = 0
            return True

    async def get_data(self, user, guild):
        await self.open_account(user, guild)
        data = self.cache.get(str(guild.id))

        if donos:=data.get(str(user.id)):
            return donos

        else:
            data[str(user.id)] = 0
            donos = data[str(user.id)]
            return donos

    async def donoroles(self, ctx, user:Member, amount):
        if not await self.config.guild(ctx.guild).autoadd():
            return f"Auto role adding is disabled for this server. Enable with `{ctx.prefix}donoset autorole add true`."
        try:
            data = await self.config.guild(ctx.guild).assignroles()

            roles = []
            for key, value in data.items():
                if amount >= int(key):
                    if isinstance(value, list):
                        #role = [ctx.guild.get_role(int(i)) for i in value]
                        for i in value:
                            role = ctx.guild.get_role(int(i))
                            if role not in user.roles:
                                try:
                                    await user.add_roles(role, reason=f"Automatic role adding based on donation logging, requested by {ctx.author}")
                                    roles.append(f"`{role.name}`")
                                except:
                                    pass
                            
                    elif isinstance(value, int):
                        role = ctx.guild.get_role(int(value))
                        if role not in user.roles:
                            try:
                                await user.add_roles(role, reason=f"Automatic role adding based on donation logging, requested by {ctx.author}")
                                roles.append(f"`{role.name}`")
                            except:
                                pass
            roleadded = f"The following roles were added to `{user.name}`: {humanize_list(roles)}" if roles else ""
            return roleadded

        except:
            pass
        
    async def remove_roles(self, ctx, user:Member, amount):
        if not await self.config.guild(ctx.guild).autoremove():
            return f"Auto role removing is disabled for this server. Enable with `{ctx.prefix}donoset autorole remove true`."
        try: 
            data = await self.config.guild(ctx.guild).assignroles()
        
            roles_removed = []
            
            for key, value in data.items():
                if amount < int(key):
                    if isinstance(value, list):
                        #role = [ctx.guild.get_role(int(i)) for i in value]
                        for i in value:
                            role = ctx.guild.get_role(int(i))
                            if role in user.roles:
                                try:
                                    await user.remove_roles(role, reason=f"Automatic role removing based on donation logging, requested by {ctx.author}")
                                    roles_removed.append(f"`{role.name}`")
                                except:
                                    pass
                            
                    elif isinstance(value, int):
                        role = ctx.guild.get_role(int(value))
                        if role in user.roles:
                            try:
                                await user.remove_roles(role, reason=f"Automatic role removing based on donation logging, requested by {ctx.author}")
                                roles_removed.append(f"`{role.name}`")
                            except:
                                pass
                        
            roleadded = f"The following roles were removed from `{user}` {humanize_list(roles_removed)}" if roles_removed else ""
            return roleadded
        except: pass

    @commands.group(name="dono", help="Donation logging. (most subcommands require admin perms or manager role) Run `{pre}dono setup` before using any commands.", description="Parameters:\n\nNone", invoke_without_command=True)
    async def dono(self, ctx):
        await ctx.send_help("dono")

    @dono.command(name="setup")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        """
        A step by step interactive setup command.
        
        This helps you setup the logging channel and the manager roles.
        Alternatively you can use the `[p]donoset managers` and `[p]donoset logchannel` commands."""
        await ctx.send("Ok so you want to setup donation logging for your server. Type 'yes' to start the process and `no` to cancel.")
        pred = MessagePredicate.yes_or_no(ctx, ctx.channel, ctx.author)
        try:
            message = await self.bot.wait_for("message", timeout=30, check=pred)
        except asyncio.TimeoutError:
            return await ctx.send("You didn't answer in time. Please try again and answer faster.")

        if pred.result:
            await ctx.send("ok lets do this. Please provide answers to the following questions properly.")
            
        else:
            return await ctx.send("Some other time i guess.")

        questions = [
            ["Which roles do you want to be able to manage donations?", "You can provide multiple roles. Send their ids all in one message separated by a space."],
            ["Which channel do you want the donations to be logged to?", "Type 'None' if you dont want that"]
        ]
        answers = {}

        for i, question in enumerate(questions):
            answer = await self.GetMessage(ctx, question[0], question[1])
            if not answer:
                await ctx.send("You didn't answer in time. Please try again and answer faster.")
                return

            answers[i] = answer

        try:
            roleids = answers[0].split()
            roles = []
            failed = []
            for id in roleids:
                role = ctx.guild.get_role(int(id))
                if not role:
                    failed.append(id)
                else:
                    roles.append(role)
        except:
            await ctx.send("You didn't provide a proper role id. Try again.")
            return

        if answers[1].lower() != "none":                    
            try:
                chan = re.findall(r"[0-9]+", answers[1])[0]
                channel = self.bot.get_channel(int(chan))
                ch = channel.id
            except:
                await ctx.send("You didn't provide a proper channel.")
                return

        else:
            ch = None

        emb = discord.Embed(title="Is all this information valid?", color=await ctx.embed_color())
        emb.add_field(name=f"Question: `{questions[0][0]}`", value=f"Answer: `{' '.join([role.name for role in roles])}\n{'Couldnt find roles with following ids'+' '.join([i for i in failed]) if failed else ''}`", inline=False)
        emb.add_field(name=f"Question: `{questions[1][0]}`", value="Answer: `{}`".format(f'#{channel.name}' if ch else "None"), inline=False)

        confirmation = await ctx.send(embed=emb)
        start_adding_reactions(confirmation, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(confirmation, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except:
            return await ctx.send("Request timed out.")
        
        if not pred.result:
            return await ctx.send("Aight, retry the command and do it correctly this time.")

        await self.config.guild(ctx.guild).logchannel.set(ch)
        await self.config.guild(ctx.guild).managers.set([role.id for role in roles])
        return await ctx.send(f"Alright. I've noted that down, Do you want to setup autoroles too? Use the `{ctx.prefix}donoset roles` command.")
        
    @dono.command(name="roles")
    @commands.guild_only()
    @commands.has_guild_permissions(administrator=True)
    async def roles(self, ctx):
        """
        Shows the donation autoroles setup for the server
        
        These can be setup with `[p]donoset roles`"""
        data = await self.config.guild(ctx.guild).assignroles()
        embed = discord.Embed(title=f"Donation autoroles for {ctx.guild.name}", color=await ctx.embed_color())
        embed.set_footer(text=f"{ctx.guild.name}", icon_url=ctx.author.avatar_url)
        emoji = await self.config.guild(ctx.guild).currency()
        if data:
            rolelist = ""
            for key, value in data.items():
                if isinstance(value, list):
                    role = [ctx.guild.get_role(int(i)).mention for i in value]
                    rolelist += "{} for amount: {} {:,}\n\n".format(humanize_list(role), emoji, int(key))
                    
                elif isinstance(value, int):
                    role = ctx.guild.get_role(int(value))
                    rolelist += "{} for amount: {} {:,}\n\n".format(role.mention, emoji, int(key))

            embed.description = f"{rolelist}"

        elif not data:
            embed.description = f"There are no autoroles setup for this guild.\nRun `{ctx.prefix}dono setroles` to set them up."
            
        if not await self.config.guild(ctx.guild).autoadd():
            embed.set_footer(text="These roles are dull and wont be automatically added/removed since auto adding of roles is disabled for this server.")

        await ctx.send(embed=embed)

    @dono.command(name="bal", aliases=["mydono"])
    @commands.guild_only()
    async def bal(self, ctx):
        """
        Check the amount you have donated in the current server
        
        For admins, if you want to check other's donations, use `[p]dono check`"""
        donos = await self.get_data(ctx.author, ctx.guild)
        emoji = await self.config.guild(ctx.guild).currency()
        
        embed = discord.Embed(title=f"Your donations in **__{ctx.guild.name}__**", description="Total amount donated: {} *{:,}*".format(emoji, donos), color=await ctx.embed_color())
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Thanks for donating. Keep donating for awesome perks. <3", icon_url=ctx.guild.icon_url)

        await ctx.send(embed=embed)
        
    async def dono_Add(self, ctx, user, amount):
        await self.open_account(user, ctx.guild)
        
        self.cache[str(ctx.guild.id)][str(user.id)] += amount
        
        return await self.get_data(user, ctx.guild)
    
    async def dono_log(self, ctx, action, user, amount, donos, role=None, note=None):
        emoji = await self.config.guild(ctx.guild).currency()
        embed = discord.Embed(title="***__Added!__***" if action.lower() == "add" else "***__Removed!__***", description=f"{emoji} {humanize_number(amount)} was {'added to' if action.lower() == 'add' else 'removed from'} {user.name}'s donations balance.\n", color=await ctx.embed_color())
        embed.add_field(name="Note: ", value=note if note else "No note taken.", inline=False)
        embed.add_field(name="Their total donations are: ", value="{} {:,}".format(emoji, donos))
        embed.add_field(name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})")
        embed.set_footer(text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url)

        chanid = await self.config.guild(ctx.guild).logchannel()
        
        if chanid and chanid != "none":
            if isinstance(chanid, str):
                log = discord.utils.find(lambda m: m.name==chanid, ctx.guild.channels)
            else:
                log = await self.bot.fetch_channel(int(chanid))
            if log:
                await log.send(role, embed=embed)
            else:
                await ctx.send(role + "\n Couldn't find the logging channel.", embed=embed)
            await ctx.message.add_reaction("✅")

        elif not chanid:
            await ctx.send(role, embed=embed)
            
    async def add_note(self, member, message, flag={}):
        if note := flag.get("note"):
            data = {"content": note, "message_id": message.id, "channel_id": message.channel.id, "author": message.author.id, "at": int(time.time())}
            async with self.config.member(member).notes() as notes:
                if not notes:
                    notes[1] = data

                else:
                    notes[len(notes)] = data
                            
            return data["content"]
        
        return

    @dono.command(name="add")
    @is_dmgr()
    @commands.guild_only()
    async def add(self, ctx, amount:MoniConverter, user:typing.Optional[discord.Member]=None, *, flag: flags=None):
        """
        Add an amount to someone's donation balance.
        
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author
        
        if not amount:
            return

        await self.open_account(user, ctx.guild)

        donos = await self.dono_Add(ctx, user, amount)
        
        note = await self.add_note(user, ctx.message, flag if flag else {})

        role = await self.donoroles(ctx, user, donos)
        
        await self.dono_log(ctx, "add", user, amount, donos, role, note)
        
    async def dono_Remove(self, ctx, user, amount):
        donation = await self.get_data(user, ctx.guild)

        self.cache[str(ctx.guild.id)][str(user.id)] -= amount

        return await self.get_data(user, ctx.guild)
    
    async def get_member_notes(self, member:discord.Member):
        async with self.config.member(member).notes() as notes:
            return notes

    @dono.command(name="remove")
    @is_dmgr()
    @commands.guild_only()
    async def remove(self, ctx, amount:MoniConverter, user:typing.Optional[discord.Member]=None, *, flag:flags=None):
        """
        Remove an amount from someone's donation balance.
        
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author
        
        if not amount:
            return

        donation = await self.dono_Remove(ctx, user, amount)
        
        role = await self.remove_roles(ctx, user, donation)
        note = await self.add_note(user, ctx.message, flag if flag else {})
        
        await self.dono_log(ctx, "remove", user, amount, donation, role, note)

    @dono.command(name="reset", description="Parameters:\n\n<user> user to reset the donation balance of.",
    help="Resets a person's donation balance. Requires the manager role.")
    @is_dmgr()
    @commands.guild_only()
    async def reset(self, ctx, user:discord.Member=None):
        """
        Reset someone's donation balance
        
        This will set their donations to 0.
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author
        donation = await self.get_data(user, ctx.guild)

        donation -= donation

        self.cache[str(ctx.guild.id)][str(user.id)] = 0
        emoji = await self.config.guild(ctx.guild).currency()

        embed = discord.Embed(title="***__Reset!__***", description=f"Resetted {user.name}'s donation bal. Their current donation amount is {emoji} 0", color=await ctx.embed_color())
        embed.add_field(name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})")
        embed.set_footer(text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url)

        chanid = await self.config.guild(ctx.guild).logchannel()
        
        role = await self.remove_roles(ctx, user, 0)

        if chanid and chanid != "none":
            channel = await self.bot.fetch_channel(chanid)
            await ctx.message.add_reaction("✅")
            await channel.send(role, embed=embed)
        else:
            await ctx.send(role, embed=embed)

    @dono.command(name="notes")
    @commands.guild_only()
    @is_dmgr()
    async def check_notes(self, ctx, member:typing.Optional[discord.Member]=None, number=None):
        EmbedField = namedtuple("EmbedField", "name value inline")
        member = member or ctx.author
        notes = await self.get_member_notes(member)
        if not notes:
            return await ctx.send(f"*{member}* has no notes!")
        if number != None:
            note = notes.get(str(number))
            print(number)
            if not note:
                return await ctx.send(f"That doesn't seem to a valid note! **{member}** only has *{len(notes)}* notes.")
            
            embed = discord.Embed(
                title=f"{member.display_name.capitalize()}'s Notes!",
                description=f"Note taken on <t:{int(note['at'])}:D>",
                color=discord.Color.green()
            )
            embed.add_field(name=f"**Note Number {number}**", value=f"*[{note['content']}]({(await (self.bot.get_channel(note['channel_id'])).fetch_message(int(note['message_id']))).jump_url})*", inline=False)
            embed.set_footer(text=f"Note taken by {await self.bot.get_or_fetch_member(ctx.guild, note['author'])}")
            return await ctx.send(embed=embed)
        fields = []
        embeds = []
        emb = {"embed": {"title": f"{member.name.capitalize()}'s Notes!",
                        "description": ""}, "footer": {"text": "", "icon_url": ctx.author.avatar_url}, "fields": []}
        for key, value in notes.items():
            field = EmbedField(f"**Note Number {key}.**",
                            f"*[{value['content'][:20] if len(value['content']) > 20 else value['content']}]({(await(self.bot.get_channel(value['channel_id'])).fetch_message(int(value['message_id']))).jump_url})*", False)
            fields.append(field)

        fieldgroups = RedHelpFormatter.group_embed_fields(fields, 200)
        page_len = len(fieldgroups)

        for i, group in enumerate(fieldgroups, 1):
            embed = discord.Embed(color=0x303036, **emb["embed"])
            emb["footer"]["text"] = f"Use `{ctx.prefix}notes {member} [number]` to look at a specific note.\nPage {i}/{page_len}."
            embed.set_footer(**emb["footer"])

            for field in group:
                embed.add_field(**field._asdict())

            embeds.append(embed)

        if len(embeds) > 1:
            return await menu(ctx, embeds, DEFAULT_CONTROLS)
        else:
            return await ctx.send(embed=embeds[0])

    @dono.command(name="check")
    @commands.guild_only()
    @is_dmgr()
    async def check(self, ctx, user:discord.Member=None):
        """
        Check someone's donation balance.
        
        This requires either one of the donation manager roles or the bot mod role."""
        if not user:
            await ctx.send("Please mention a user or provide their id to check their donations")
            return

        await self.open_account(user, ctx.guild)
        donos = await self.get_data(user, ctx.guild)
        emoji = await self.config.guild(ctx.guild).currency()
        notes = len(await self.config.member(user).notes())

        embed = discord.Embed(title=f"{user.name}'s donations in **__{ctx.guild.name}__**", description="Total amount donated: {}{:,}\n\nThey have **{}** notes".format(emoji, donos, notes), color=discord.Color.random())
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=f"{ctx.guild.name}", icon_url=ctx.guild.icon_url)

        await ctx.send(embed=embed)

    @dono.command(name="leaderboard", description="Parameters:\n\n<topnumber> The amount of people to show on the leaderboard. deafaults to 5.",
    help="Shows a leaderboard containing the top doantors in the guild.", aliases=["lb", "topdonators"])
    @commands.guild_only()
    async def leaderboard(self, ctx, topnumber=5):
        """
        See the top donators in the server.
        
        Use the <topnumber> parameter to see the top `x` donators. """
        data = await self.config.guild(ctx.guild).donations()

        data = await sortdict(data)

        embed = discord.Embed(title=f"Top {topnumber} donators ", color=discord.Color.random())
        emoji = await self.config.guild(ctx.guild).currency()
        
        index = 1
        for index, (key, value) in enumerate(data.items(), 1):
            if value != 0:
                user = await self.bot.fetch_user(int(key))
                embed.add_field(name=f"{index}. **{user.name}**", value="{} {:,}".format(emoji, value), inline=False)
            
            if (index) == topnumber:
                break

        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.set_author(name=ctx.guild.name)
        embed.set_footer(text=f"For a higher top number, do `{ctx.prefix}dono lb [amount]`")

        await ctx.send(embed=embed)
        
    @commands.group(name='donoset', invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    async def donoset(self, ctx):
        """
        Base command for changing donation settings for your server."""
        pass
    
    @donoset.group(name="autorole", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    async def autorole(self, ctx):
        """
        Change settings for Auto donation roles behaviour in your server."""
        await ctx.send_help("donoset autorole")
        
    @autorole.command(name="add")
    @commands.mod_or_permissions(administrator=True)
    async def ar_add(self, ctx, true_or_false:bool):
        """
        Set whether donation roles(set with `[p]donoset roles`) automatically get added to users or not.
        
        \n<true_or_false> is supposed to be either of True or False.
        True to enable and False to disable."""
        toggle = await self.config.guild(ctx.guild).autoadd()
        if toggle and true_or_false:
            return await ctx.send("Auto-role adding is already enabled for this server.")
        elif not toggle and not true_or_false:
            return await ctx.send("Auto-role adding is already disabled for this server.")
        
        await self.config.guild(ctx.guild).autoadd.set(true_or_false)
        return await ctx.send(f"{'Disabled' if true_or_false == False else 'Enabled'} auto role adding for this server")
    
    @autorole.command(name="remove")
    @commands.mod_or_permissions(administrator=True)
    async def ar_remove(self, ctx, true_or_false:bool):
        """
        Set whether donation roles (set with `[p]donoset roles`) automatically get removed from users or not.
        
        \n<true_or_false> is supposed to be either of True or False.
        True to enable and False to disable."""
        toggle = await self.config.guild(ctx.guild).autoremove()
        if toggle and true_or_false:
            return await ctx.send("Auto-role removing is already enabled for this server.")
        elif not toggle and not true_or_false:
            return await ctx.send("Auto-role removing is already disabled for this server.")
        
        await self.config.guild(ctx.guild).autoremove.set(true_or_false)
        return await ctx.send(f"{'Disabled' if true_or_false == False else 'Enabled'} auto role removing for this server")
    
    @donoset.command(name="currency")
    @commands.mod_or_permissions(administrator=True)
    async def currency(self, ctx, icon):
        """
        Change the currency symbol for donations in your server.
        
        This symbol/icon will show up next to the amounts in all dono commands.
        This defaults to ⏣"""
        old_icon = await self.config.guild(ctx.guild).currency()
        msg = await ctx.send(f"Your current icon is {old_icon}. Are you sure you want to change it to {icon}?")
        pred = ReactionPredicate.yes_or_no(msg, ctx.author)
        start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        try:
            await ctx.bot.wait_for("reaction_add", timeout=30, check=pred)
        except asyncio.TimeoutError:
            return await ctx.send("You took too long to respond. Aborting.")
        
        if pred.result:
            await self.config.guild(ctx.guild).currency.set(icon)
            return await ctx.send("New icon updated!")
        
        else:
            return await ctx.send("Okay. Thank you for wasting my time.")
        
    @donoset.command(name="addrole")
    @commands.mod_or_permissions(administrator=True)
    async def addrole(self, ctx, role:discord.Role, amount: MoniConverter):
        """
        Add a new autorole for a specific amount without going through the long setup command."""
        data = await self.config.guild(ctx.guild).assignroles()
        
        if role.position > ctx.bot.top_role.position:
            return await ctx.send("That role's position than me, I cannot manually assign it to people. Please move the role created by me, above the assigning roles.")
        elif role.is_bot_managed():
            return await ctx.send("That role is managed by a bot so it can't be assigned by me.")
        elif role.position > ctx.author.top_role.position:
            return await ctx.send("That role's postition is above you and can not be set to be assigned by you.")
        
        if str(amount) in data:
            msg = await ctx.send("There is already an auto-role for that amount. Do you want to replace it or add multiple?\nReact with the tick to replace and cross to add multiple.")
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            try:
                await ctx.bot.wait_for("reaction_add", timeout=30, check=pred)
            except asyncio.TimeoutError:
                return await ctx.send("You took too long to respond. Aborting.")
            
            if not pred.result:
                prev = data[str(amount)]
                if isinstance(prev, list):
                    return await ctx.send("You can't have more than 2 autoroles per amount!")
                elif isinstance(prev, int):
                    new = [prev, role.id]
                data[str(amount)] = new
                
            else:
                data[str(amount)] = role.id
                
            await ctx.send("Done!")
        
        else:
            await ctx.send(f"Added auto role: `@{role.name}` for amount: {humanize_number(amount)}")
            data[str(amount)] = role.id
            
        await self.config.guild(ctx.guild).assignroles.set(data)

    @donoset.command(name="roles")
    @commands.mod_or_permissions(administrator=True)
    async def setroles(self, ctx):
        """
        A step by step interactive process to set donation autoroles for your server.
        
        These roles will be automaitcally assigned upon reaching a certain amount of donation.
        """
        if not await self.config.guild(ctx.guild).autoadd():
            return await ctx.send("Auto-adding for roles is disabled here. Please enable that before using this command.")
        await ctx.send("Let's setup autoroles for donations. Send the amount and role to be assigned in the following format:\n*__Amount:roleid__*\nKeep doing that and when you are done, just type 'done' and the process will stop.")
        ardict = {}
        while True:
            try:
                message = await self.bot.wait_for("message", timeout=90, check=lambda message: message.author == ctx.author and message.channel == ctx.channel)
            except asyncio.TimeoutError:
                await ctx.send("I guess that's all you want. Timed out.")
                break
            
            try:
                key, value = message.content.split(":")
            except:
                if message.content.lower() == "done":
                    break
                else:
                    return await ctx.send("Messages must be in the format of ***__Amount:RoleID__***. Try again.")
            
            amount = await MoniConverter().convert(ctx, str(key))
            if not amount:
                return

            role = await RoleConverter().convert(ctx, value)

            if not role:
                return await ctx.send("Try again and provide a proper role id.")
            if role.position > ctx.me.top_role.position:
                return await ctx.send("That role's position is higher than me, I cannot manually assign it to people. Please move the role created by me, above the assigning roles.")
            elif role.is_bot_managed():
                return await ctx.send("That role is managed by a bot so it can't be assigned by me.")
            elif role.position > ctx.author.top_role.position:
                return await ctx.send("That role's postition is above you and can not be set to be assigned by you.")

            ardict[amount] = role.id

            await message.add_reaction("✅")


        embed = discord.Embed(title=f"Autoroles setup for {ctx.guild.name}: ", color=discord.Color.green())

        final = ""
        
        ardict = await sortdict(ardict, "key")
        for index, (key, value) in enumerate(ardict.items()):
            final += "**Dono Role {}**\n{:,} - {}\n\n".format(index+1, int(key), f'<@&{value}>')

        embed.description = final

        confirmation = await ctx.send(embed=embed)

        pred = ReactionPredicate.yes_or_no(confirmation, ctx.author)
        start_adding_reactions(confirmation, ReactionPredicate.YES_OR_NO_EMOJIS)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except:
            return await ctx.send("You took too long. Request timed out.")
        
        if pred.result:
            await ctx.send("alright done. Redo the command to setup roles again if there is any problem.")

            await self.config.guild(ctx.guild).assignroles.set(ardict)
            
        else:
            await ctx.send("Aight try again later.")
        
    @donoset.command(name="managers")
    @commands.mod_or_permissions(administrator=True)
    async def set_managers(self, ctx, add_or_remove, roles: Greedy[discord.Role]=None):
        """Adds or removes managers for your guild.

        This is an alternative to `[p]dono setup`. 
        You can use this to add or remove manager roles post setup.
        
        <add_or_remove> should be either `add` to add roles or `remove` to remove roles.
        """
        if roles is None:
            return await ctx.send("`Roles` is a required argument.")
        
        for role in roles:
            async with self.config.guild(ctx.guild).managers() as l:
                if add_or_remove.lower() == "add":
                    if not role.id in l:
                        l.append(role.id)
                        
                elif add_or_remove.lower() == "remove":
                    if role.id in l:
                        l.remove(role.id)
                        
        return await ctx.send(f"Successfully {'added' if add_or_remove.lower() == 'add' else 'removed'} {len([role for role in roles])} roles.")
    
    @donoset.command(name="logchannel")
    @commands.mod_or_permissions(administrator=True)
    async def set_channel(self, ctx, channel:discord.TextChannel=None):
        """Set the donation logging channel or reset it.

        This is an alternative to `[p]dono setup`. 
        You can use this to change or reset log channel post setup.
        """
        
        await self.config.guild(ctx.guild).logchannel.set(None if not channel else channel.id)
        return await ctx.send(f"Successfully set {channel.mention} as the donation logging channel." if channel else "Successfully reset the log channel.")
    
    @donoset.command(name="showsettings", aliases=["showset", "ss"])
    async def showsettings(self, ctx):
        data = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title=f"Donation Logging settings for {ctx.guild}",
            color=0x303036,
            timestamp=ctx.message.created_at
        )
        managers = humanize_list([(ctx.guild.get_role(i)).mention for i in data['managers']]) if data["managers"] and isinstance(data["managers"], list) else data["managers"]
        embed.add_field(name="Donation Managers: ", value=(managers) if data['managers'] else 'None', inline=False)
        embed.add_field(name="Log Channel: ", value=f"<#{data['logchannel']}>" if data['logchannel'] else 'None', inline=False)
        embed.add_field(name="Auto Add Roles: ", value=data["autoadd"], inline=False)
        embed.add_field(name="Auto Remove Roles: ", value=data["autoremove"])
        embed.add_field(name="Auto Assignable roles: ", value=f"Use `{ctx.prefix}dono roles` to see these.", inline=False)
        await ctx.send(embed=embed)
