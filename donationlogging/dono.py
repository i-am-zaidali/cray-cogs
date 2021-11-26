import discord
import time
import asyncio

from discord.ext.commands.converter import Greedy, RoleConverter, TextChannelConverter

from redbot.core import Config, commands
from redbot.core.utils.menus import menu, start_adding_reactions, DEFAULT_CONTROLS
from redbot.core.bot import Red
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from redbot.core.utils.chat_formatting import humanize_list, humanize_number
from redbot.core.commands import RedHelpFormatter

from collections import namedtuple
from typing import List, Optional

from donationlogging.models import DonationManager, DonoUser
from .utils import *

class DonationLogging(commands.Cog):
    """
    Donation logging commands. 
    Helps you in counting and tracking user donations (**for discord bot currencies**) and automatically assigning them roles.
    """
    
    __version__ = "2,0.0"
    __author__ = ["crayyy_zee#2900"]
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.cache : DonationManager = None
        self.config = Config.get_conf(None, 123_6969_420, True, "DonationLogging")
        
        default_guild = {
            "managers" : [],
            "logchannel" : None,
            "autoadd": False,
            "autoremove": False,
            "setup": False
            }
        
        self.config.register_global(migrated=False)
        self.config.register_guild(**default_guild)
        
    @classmethod
    async def initialize(cls, bot):
        s = cls(bot)
        
        s.cache = await DonationManager.initialize(bot)
        
        return s
        
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
        asyncio.create_task(self.cache._back_to_config())
        
    async def red_delete_data_for_user(self, *, requester, user_id: int):
        if requester not in ("discord_deleted_user", "user"):
            return
        self.cache.delete_all_user_data(user_id)
  
    # async def to_cache(self):
    #     data = await self.config.all_members()
    #     final = {}
    #     for guild, memberdata in data.items():
    #         final[guild] = {}
    #         for k, v in memberdata.items():
    #             final[guild][k] = v["donations"]
            
    #     self.cache = final
        
    # async def to_config(self):
    #     for guild, memberdata in self.cache.items():
    #         for member, data in memberdata.items():
    #             await self.config.member_from_ids(int(guild), int(member)).donations.set(data)

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

    # async def donoroles(self, ctx, user:Member, amount):
    #     if not await self.config.guild(ctx.guild).autoadd():
    #         return f"Auto role adding is disabled for this server. Enable with `{ctx.prefix}donoset autorole add true`."
    #     try:
    #         data = await self.config.guild(ctx.guild).assignroles()

    #         roles = []
    #         for key, value in data.items():
    #             if amount >= int(key):
    #                 if isinstance(value, list):
    #                     #role = [ctx.guild.get_role(int(i)) for i in value]
    #                     for i in value:
    #                         role = ctx.guild.get_role(int(i))
    #                         if role not in user.roles:
    #                             try:
    #                                 await user.add_roles(role, reason=f"Automatic role adding based on donation logging, requested by {ctx.author}")
    #                                 roles.append(f"`{role.name}`")
    #                             except:
    #                                 pass
                            
    #                 elif isinstance(value, int):
    #                     role = ctx.guild.get_role(int(value))
    #                     if role not in user.roles:
    #                         try:
    #                             await user.add_roles(role, reason=f"Automatic role adding based on donation logging, requested by {ctx.author}")
    #                             roles.append(f"`{role.name}`")
    #                         except:
    #                             pass
    #         roleadded = f"The following roles were added to `{user.name}`: {humanize_list(roles)}" if roles else ""
    #         return roleadded

    #     except:
    #         pass
        
    # async def remove_roles(self, ctx, user:Member, amount):
    #     if not await self.config.guild(ctx.guild).autoremove():
    #         return f"Auto role removing is disabled for this server. Enable with `{ctx.prefix}donoset autorole remove true`."
    #     try: 
    #         data = await self.config.guild(ctx.guild).assignroles()
        
    #         roles_removed = []
            
    #         for key, value in data.items():
    #             if amount < int(key):
    #                 if isinstance(value, list):
    #                     #role = [ctx.guild.get_role(int(i)) for i in value]
    #                     for i in value:
    #                         role = ctx.guild.get_role(int(i))
    #                         if role in user.roles:
    #                             try:
    #                                 await user.remove_roles(role, reason=f"Automatic role removing based on donation logging, requested by {ctx.author}")
    #                                 roles_removed.append(f"`{role.name}`")
    #                             except:
    #                                 pass
                            
    #                 elif isinstance(value, int):
    #                     role = ctx.guild.get_role(int(value))
    #                     if role in user.roles:
    #                         try:
    #                             await user.remove_roles(role, reason=f"Automatic role removing based on donation logging, requested by {ctx.author}")
    #                             roles_removed.append(f"`{role.name}`")
    #                         except:
    #                             pass
                        
    #         roleadded = f"The following roles were removed from `{user}` {humanize_list(roles_removed)}" if roles_removed else ""
    #         return roleadded
    #     except: pass

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
        
        This is a one time command per guild.
        
        Alternatively you can use the `[p]donoset managers` and `[p]donoset logchannel` commands."""
        if await self.config.guild(ctx.guild).setup():
            return await ctx.send("This setup is a one time process only.")
        await ctx.send("Ok so you want to setup donation logging for your server. Type `yes` to start the process and `no` to cancel.")
        pred = MessagePredicate.yes_or_no(ctx, ctx.channel, ctx.author)
        try:
            await self.bot.wait_for("message", timeout=30, check=pred)
        except asyncio.TimeoutError:
            return await ctx.send("You didn't answer in time. Please try again and answer faster.")

        if pred.result:
            await ctx.send("ok lets do this. Please provide answers to the following questions properly.")
            
        else:
            return await ctx.send("Some other time i guess.")

        questions = [
            ["Which roles do you want to be able to manage donations?", "You can provide multiple roles. Send their ids/mentions/names all in one message separated by a comma."],
            ["Which channel do you want the donations to be logged to?", "Type 'None' if you dont want that"],
            ["What would you like your first donation logging currency category to be named?", "Send its name and emoji (id only) separated by a comma."
             "You can use custom emojis as long as the bot has access to it.\nFor example: `dank,⏣`"],
            ["Are there any roles that you would like to be assigned at certain milestones in this category?",
             "Send amount and roles separate by a comma. Multiple roles should also be separated by a colon (:) or just send `none`\nFor example: `10000,someroleid:onemoreroleid 15k,@rolemention 20e4,arolename`"]
        ]
        answers = {}

        for i, question in enumerate(questions):
            answer = await self.GetMessage(ctx, question[0], question[1], timeout=180)
            if not answer:
                await ctx.send("You didn't answer in time. Please try again and answer faster.")
                return

            answers[i] = answer

        roleids = answers[0].split(",")
        roles = []
        failed = []
        rc = RoleConverter()
        cc = TextChannelConverter()
        for id in roleids:
            try:
                role = await rc.convert(ctx, id)
            except:
                failed.append(id)
            else:
                roles.append(role)

        if chan:=answers[1].lower() != "none":                    
            try:
                channel = await cc.convert(ctx, chan)
            except:
                await ctx.send("You didn't provide a proper channel.")
                return

        else:
            channel = None
            
        try:
            bank = await CategoryMaker().convert(ctx, answers[2])
        except Exception as e:
            raise e
        
        pairs = await AmountRoleConverter().convert(ctx, answers[3])
        
        emb = discord.Embed(title="Is all this information valid?", color=await ctx.embed_color())
        emb.add_field(
            name=f"Question: `{questions[0][0]}`", 
            value=f"Answer: `{' '.join([role.name for role in roles])}"
            f"{'Couldnt find roles with following ids'+' '.join([i for i in failed]) if failed else ''}`", 
            inline=False)
        emb.add_field(
            name=f"Question: `{questions[1][0]}`", 
            value=f"Answer: `{f'#{channel.name}' if channel else 'None'}`", 
            inline=False)
        emb.add_field(
            name=f"Question: `{questions[2][0]}`", 
            value=f"Answer: {bank.emoji} `{bank.name}`", 
            inline=False)
        ans4 = '\n'.join([f'{humanize_list([role.name for role in roles])} for {humanize_number(amount)} donations' for amount, roles in pairs.items()])
        emb.add_field(
            name=f"Question: `{questions[3][0]}`", 
            value=f"Answer: \n`{ans4}`"
            if pairs else f"Answer: None given.", 
            inline=False)

        confirmation = await ctx.send(embed=emb)
        start_adding_reactions(confirmation, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(confirmation, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except:
            return await ctx.send("Request timed out.")
        
        if not pred.result:
            return await ctx.send("Aight, retry the command and do it correctly this time.")

        await self.config.guild(ctx.guild).logchannel.set(channel.id if channel else None)
        await self.config.guild(ctx.guild).managers.set([role.id for role in roles])
        await self.config.guild(ctx.guild).setup.set(True)
        await bank.setroles(pairs)
        await self.cache.set_default_category(ctx.guild, bank.name)
        return await ctx.send(f"Alright. I've noted that down. You can now start logging donations.")
        
    @dono.command(name="roles")
    @commands.guild_only()
    @setup_done()
    @commands.has_guild_permissions(administrator=True)
    async def roles(self, ctx, category: CategoryConverter = None):
        """
        Shows the donation autoroles for the category provided.
        If the category isn't provided, shows all the category autoroles.
        
        These can be setup with `[p]donoset roles`"""
        if not category:
            categories = await self.cache.config.guild(ctx.guild).categories()
            cat_roles = {}
            for name, data in categories.items():
                data.pop("emoji")
                if not data:
                    continue
                bank = await self.cache.get_dono_bank(name, ctx.guild.id)
                cat_roles.update({bank: await bank.getroles()})
            embed = discord.Embed(
                title=f"All donations autoroles in {ctx.guild}!",
                color=0x303036
            )
            if not cat_roles:
                embed.description = "No roles setup for any category."
            for key, value in cat_roles.items():
                roles = '\n'.join([f'{humanize_list([role.name for role in roles])} for {humanize_number(amount)} donations' for amount, roles in value.items()])
                embed.add_field(
                    name=f"{key.name.title()}",
                    value=f"`{roles}`"
                    if value else "No roles setup for this category.",
                    inline=False
                )
                
                    
        else:
            data = await category.getroles()
            embed = discord.Embed(title=f"{category.name.title()}'s autoroles", color=await ctx.embed_color())
            embed.set_footer(text=f"{ctx.guild.name}", icon_url=ctx.author.avatar_url)
            if data:
                rolelist = ""
                for key, value in data.items():
                    rolelist += f"{humanize_list([role.name for role in value])} for {humanize_number(key)} donations\n"
                embed.description = f"{rolelist}"

            elif not data:
                embed.description = f"There are no autoroles setup for this guild.\nRun `{ctx.prefix}dono setroles` to set them up."
                
        if not await self.config.guild(ctx.guild).autoadd():
            embed.set_footer(text="These roles are dull and wont be automatically added/removed since auto adding of roles is disabled for this server.")

        await ctx.send(embed=embed)

    @dono.command(name="bal", aliases=["mydono"])
    @commands.guild_only()
    @setup_done()
    async def bal(self, ctx, category: CategoryConverter = None):
        """
        Check the amount you have donated in the current server
        
        For admins, if you want to check other's donations, use `[p]dono check`"""
        if category:
            donos = category.get_user(ctx.author.id).donations
            emoji = category.emoji
            
            embed = discord.Embed(
                title=f"Your donations in **__{ctx.guild.name}__** for **__{category.name}__**", 
                description=f"Donated: {emoji} *{humanize_number(donos)}*", 
                color=await ctx.embed_color()
                )
            
        else:
            banks = await self.cache.get_all_dono_banks(ctx.guild.id)
            embed = discord.Embed(
                title=f"All your donations in **__{ctx.guild.name}__**",
                description=f"Total amount donated overall: {humanize_number(sum([bank.get_user(ctx.author.id).donations for bank in banks]))}",
                color=await ctx.embed_color()
            )
            for bank in banks:
                donations = bank.get_user(ctx.author.id).donations
                embed.add_field(
                    name=f"*{bank.name.title()}*",
                    value=f"Donated: {bank.emoji} {humanize_number(donations)}",
                    inline=True
                )
                
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Thanks for donating <3", icon_url=ctx.guild.icon_url)

        await ctx.send(embed=embed)
        
    async def dono_log(self, ctx, action, user, amount, donos, bank, role=None, note=None): # API for giveaways.
        emoji = bank.emoji
        embed = discord.Embed(title="***__Added!__***" if action.lower() == "add" else "***__Removed!__***", 
                              description=f"{emoji} {humanize_number(amount)} was "
                              f"{'added to' if action.lower() == 'add' else 'removed from'} {user.name}'s donations balance.\n", 
                              color=await ctx.embed_color())
        embed.add_field(name="Category: ", value=f"**{bank.name.title()}**", inline=False)
        embed.add_field(name="Note: ", value=note if note else "No note taken.", inline=False)
        embed.add_field(name="Their total donations are: ", value=f"{emoji} {humanize_number(donos)}")
        embed.add_field(name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})")
        embed.set_footer(text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url)

        chanid = await self.config.guild(ctx.guild).logchannel()
        
        if chanid and chanid != "none":
            try:
                log = await self.bot.fetch_channel(int(chanid))
            except (discord.NotFound, discord.HTTPException):
                log = None
            if log:
                await log.send(role, embed=embed)
            else:
                await ctx.send(role + "\n Couldn't find the logging channel.", embed=embed)
            await ctx.tick()

        elif not chanid:
            await ctx.send(role, embed=embed)
            
    async def add_note(self, member, message, flag={}):
        if note := flag.get("note"):
            data = {"content": note, "message_id": message.id, "channel_id": message.channel.id, "author": message.author.id, "at": int(time.time())}
            async with self.config.member(member).notes() as notes:
                if not notes:
                    notes[1] = data

                else:
                    notes[len(notes) + 1] = data
                            
            return data["content"]
        
        return
    
    async def get_member_notes(self, member:discord.Member):
        async with self.config.member(member).notes() as notes:
            return notes

    @dono.command(name="add", usage="[category] <amount> [user] [--note]")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def add(self, ctx, category: Optional[CategoryConverter]=None, amount:MoniConverter=None, user:Optional[discord.Member]=None, *, flag: flags=None):
        """
        Add an amount to someone's donation balance.
        
        This requires either one of the donation manager roles or the bot mod role.
        [--note] parameter is a flag used for setting notes for a donation
        For example:
            `[p]dono add dank 1000 @Twentysix --note hes cute`"""
        user = user or ctx.author
        
        if not amount:
            return await ctx.send_help()
        
        category: DonoBank = category or await self.cache.get_default_category(ctx.guild.id)

        u = category.get_user(user.id)

        donos = u.add(amount)
        note = await self.add_note(user, ctx.message, flag if flag else {})

        role = await category.addroles(ctx, user)       
        await self.dono_log(ctx, "add", user, amount, donos, category, role, note)

    @dono.command(name="remove", usage="[category] <amount> [user] [--note]")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def remove(self, ctx, category: Optional[CategoryConverter]=None, amount:MoniConverter=None, user:Optional[discord.Member]=None, *, flag:flags=None):
        """
        Remove an amount from someone's donation balance.
        
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author
        
        if not amount:
            return await ctx.send_help()
        
        category: DonoBank = category or await self.cache.get_default_category(ctx.guild.id)

        u = category.get_user(user.id)
        donation = u.remove(amount)
        
        role = await category.removeroles(ctx, user)
        note = await self.add_note(user, ctx.message, flag if flag else {})
        
        await self.dono_log(ctx, "remove", user, amount, donation, category, role, note)

    @dono.command(name="reset", description="Parameters:\n\n<user> user to reset the donation balance of.",
    help="Resets a person's donation balance. Requires the manager role.")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def reset(self, ctx, category: Optional[CategoryConverter]=None, user:discord.Member=None):
        """
        Reset someone's donation balance
        
        This will set their donations to 0.
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author
        
        if not category:
            await ctx.send(f"You didn't provide a category to reset, are you sure you want to reset all donations of {ctx.author}?"
                           " Reply with `yes`/`no`.")
            pred = MessagePredicate.yes_or_no(ctx)
            try:
                await ctx.bot.wait_for("message", check=pred, timeout=30)
            except asyncio.TimeoutError:
                return await ctx.send("No response, aborting.")
            
            if pred.result:
                await self.cache.delete_all_user_data(user.id, ctx.guild.id)
                return await ctx.send(f"{user.mention}'s donations have been reset.")
            
            else:
                return await ctx.send("Alright!")
        
        category.remove_user(user.id)
        emoji = category.emoji

        embed = discord.Embed(
            title="***__Reset!__***", 
            description=f"Resetted {user.name}'s donation bal. Their current donation amount is {emoji} 0", 
            color=await ctx.embed_color())
        embed.add_field(name="Category: ", value=f"{category.name.title()}", inline=False)
        embed.add_field(name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})")
        embed.set_footer(text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url)

        chanid = await self.config.guild(ctx.guild).logchannel()
        
        role = await category.removeroles(ctx, user)

        if chanid and chanid != "none":
            channel = await self.bot.fetch_channel(chanid)
            await ctx.tick()
            await channel.send(role, embed=embed)
        else:
            await ctx.send(role, embed=embed)

    @dono.command(name="notes")
    @commands.guild_only()
    @is_dmgr()
    @setup_done()
    async def check_notes(self, ctx, member:Optional[discord.Member]=None, number=None):
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
    @setup_done()
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
    help="Shows a leaderboard containing the top donators in the guild.", aliases=["lb", "topdonators"])
    @commands.guild_only()
    @setup_done()
    async def leaderboard(self, category: CategoryConverter, ctx, topnumber=5):
        """
        See the top donators in the server.
        
        Use the <topnumber> parameter to see the top `x` donators. """
        data: List[DonoUser] = category.get_leaderboard()

        embed = discord.Embed(title=f"Top {topnumber} donators for **__{category.name.title()}__**", color=discord.Color.random())
        emoji = category.emoji
        
        for index, user in enumerate(data, 1):
            if user.donations != 0:
                user = user.user
                embed.add_field(name=f"{index}. **{user.name}**", value=f"{emoji} {humanize_number(user.donations)}", inline=False)
            
            if (index) == topnumber:
                break

        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.set_author(name=ctx.guild.name)
        embed.set_footer(text=f"For a higher top number, do `{ctx.prefix}dono lb {category.name} [amount]`")

        await ctx.send(embed=embed)
        
    @commands.group(name='donoset', invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def donoset(self, ctx):
        """
        Base command for changing donation settings for your server."""
        pass
    
    @donoset.group(name="autorole", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def autorole(self, ctx):
        """
        Change settings for Auto donation roles behaviour in your server."""
        await ctx.send_help("donoset autorole")
        
    @autorole.command(name="add")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
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
    @setup_done()
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
    @setup_done()
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
    @setup_done()
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
    @setup_done()
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
    @setup_done()
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
    @setup_done()
    async def set_channel(self, ctx, channel:discord.TextChannel=None):
        """Set the donation logging channel or reset it.

        This is an alternative to `[p]dono setup`. 
        You can use this to change or reset log channel post setup.
        """
        
        await self.config.guild(ctx.guild).logchannel.set(None if not channel else channel.id)
        return await ctx.send(f"Successfully set {channel.mention} as the donation logging channel." if channel else "Successfully reset the log channel.")
    
    @donoset.command(name="showsettings", aliases=["showset", "ss"])
    @setup_done()
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
