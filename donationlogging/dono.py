import asyncio
import time
from collections import namedtuple
from typing import List, Optional

import discord
from discord.ext.commands.converter import Greedy, RoleConverter, TextChannelConverter
from discord.ext.commands.errors import ChannelNotFound
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.commands import RedHelpFormatter
from redbot.core.utils.chat_formatting import humanize_list, humanize_number
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

from donationlogging.models import DonationManager, DonoUser

from .utils import *


class DonationLogging(commands.Cog):
    """
    Donation logging commands.
    Helps you in counting and tracking user donations (**for discord bot currencies**) and automatically assigning them roles.
    """

    __version__ = "2.1.0"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.cache: DonationManager = None
        self.config = Config.get_conf(None, 123_6969_420, True, "DonationLogging")

        default_guild = {
            "managers": [],
            "logchannel": None,
            "autoadd": False,
            "autoremove": False,
            "setup": False,
        }

        self.config.register_global(migrated=False)
        self.config.register_guild(**default_guild)
        self.config.register_member(notes={})

        self.conv = MoniConverter().convert  # api for giveaway cog.

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

    async def get_old_data(self, guild: discord.Guild):
        all_members = await self.config.all_members(guild)
        if all_members:
            return {
                str(k): v["donations"] for k, v in all_members.items()
            }  # return strid, donations pair.
        return None

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        if requester not in ("discord_deleted_user", "user"):
            return
        self.cache.delete_all_user_data(user_id)

    async def GetMessage(self, ctx: commands.Context, contentOne, contentTwo, timeout=100):
        embed = discord.Embed(
            title=f"{contentOne}", description=f"{contentTwo}", color=await ctx.embed_color()
        )
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

    @commands.group(name="dono", invoke_without_command=True)
    async def dono(self, ctx):
        """
        Donation Logging for your server.

        (For currency based bots on discord)"""
        await ctx.send_help("dono")

    @dono.command(name="setup")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: commands.Context):
        """
        A step by step interactive setup command.

        This helps you setup the logging channel and the manager roles.

        This is a one time command per guild.

        Alternatively you can use the `[p]donoset managers` and `[p]donoset logchannel` commands."""
        if await self.config.guild(ctx.guild).setup():
            return await ctx.send("This setup is a one time process only.")
        await ctx.send(
            "Ok so you want to setup donation logging for your server. Type `yes` to start the process and `no` to cancel."
        )
        pred = MessagePredicate.yes_or_no(ctx, ctx.channel, ctx.author)
        try:
            await self.bot.wait_for("message", timeout=30, check=pred)
        except asyncio.TimeoutError:
            return await ctx.send("You didn't answer in time. Please try again and answer faster.")

        if pred.result:
            await ctx.send(
                "ok lets do this. Please provide answers to the following questions properly."
            )

        else:
            return await ctx.send("Some other time i guess.")

        questions = [
            [
                "Which roles do you want to be able to manage donations?",
                "You can provide multiple roles. Send their ids/mentions/names all in one message separated by a comma.",
            ],
            [
                "Which channel do you want the donations to be logged to?",
                "Type 'None' if you dont want that",
            ],
            [
                "What would you like your first donation logging currency category to be named?",
                "Send its name and emoji (id only) separated by a comma."
                "You can use custom emojis as long as the bot has access to it.\nFor example: `dank,⏣`",
            ],
            [
                "Are there any roles that you would like to be assigned at certain milestones in this category?",
                (
                    "Send amount and roles separate by a comma. "
                    "Multiple roles should also be separated by a colon (:) or just send `none`"
                    "\nFor example: `10000,someroleid:onemoreroleid 15k,@rolemention 20e4,arolename`"
                ),
            ],
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

        if (
            chan := answers[1]
        ).lower() != "none":  # apparently .lower() messes up the mention so that should be called after assignment
            try:
                channel = await cc.convert(ctx, str(chan))
            except ChannelNotFound:
                await ctx.send("You didn't provide a proper channel.")
                return

        else:
            channel = None

        if answers[3] == "none":
            pairs = {}
        else:
            try:
                pairs = await AmountRoleConverter().convert(ctx, answers[3])
            except Exception as e:
                return await ctx.send(e)

        try:
            bank = await CategoryMaker().convert(ctx, answers[2])
        except Exception as e:
            return await ctx.send(e)

        emb = discord.Embed(title="Is all this information valid?", color=await ctx.embed_color())
        emb.add_field(
            name=f"Question: `{questions[0][0]}`",
            value=f"Answer: `{' '.join([role.name for role in roles])}"
            f"{'Couldnt find roles with following ids'+' '.join([i for i in failed]) if failed else ''}`",
            inline=False,
        )
        emb.add_field(
            name=f"Question: `{questions[1][0]}`",
            value=f"Answer: `{f'#{channel.name}' if channel else 'None'}`",
            inline=False,
        )
        emb.add_field(
            name=f"Question: `{questions[2][0]}`",
            value=f"Answer: {bank.emoji} `{bank.name}`",
            inline=False,
        )
        ans4 = "\n".join(
            [
                f"{humanize_list([role.name for role in roles])} for {humanize_number(amount)} donations"
                for amount, roles in pairs.items()
            ]
        )
        emb.add_field(
            name=f"Question: `{questions[3][0]}`",
            value=f"Answer: \n`{ans4}`" if pairs else f"Answer: None given.",
            inline=False,
        )

        confirmation = await ctx.send(embed=emb)
        start_adding_reactions(confirmation, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(confirmation, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
        except:
            return await ctx.send("Request timed out.")

        if not pred.result:
            await self.category_remove(ctx, bank.name)
            return await ctx.send("Aight, retry the command and do it correctly this time.")

        await self.config.guild(ctx.guild).logchannel.set(channel.id if channel else None)
        await self.config.guild(ctx.guild).managers.set([role.id for role in roles])
        await self.config.guild(ctx.guild).setup.set(True)
        if pairs:
            await bank.setroles(pairs)
        await self.cache.set_default_category(ctx.guild.id, bank.name)

        if old_data := await self.get_old_data(ctx.guild):
            confirmation = await ctx.send(
                "Old donation logging data was found for this guild. "
                "\nWould you like to associate it with the category you just registered? "
                "\nIf not, this data will be cleared and will not be able to be recovered."
            )
            start_adding_reactions(confirmation, ReactionPredicate.YES_OR_NO_EMOJIS)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except:
                return await ctx.send("Request timed out.")

            if not pred.result:
                return await ctx.send(
                    "Alright removing this redundant data. You can now start logging donations."
                )  # nah we wont actually do it :P

            else:
                bank._data.update(old_data)
                await ctx.send(
                    "Updated new category with old data :D You can now continue logging donations normally."
                )

        return await ctx.send(
            f"Alright. I've noted that down. You can now start logging donations."
        )

    @dono.command(name="roles")
    @commands.guild_only()
    @setup_done()
    @commands.has_guild_permissions(administrator=True)
    async def roles(self, ctx, category: CategoryConverter = None):
        """
        Shows the donation autoroles for the category provided.
        If the category isn't provided, shows all the category autoroles.

        These are set initially in the `[p]dono setup` command
        but can also be set with `[p]donoset addroles`"""
        if not category:
            categories = await self.cache.config.guild(ctx.guild).categories()
            cat_roles = {}
            for name, data in categories.items():
                data.pop("emoji")
                if not data:
                    continue
                bank = await self.cache.get_dono_bank(name, ctx.guild.id)
                cat_roles.update({bank: await bank.getroles(ctx)})
            embed = discord.Embed(title=f"All donations autoroles in {ctx.guild}!", color=0x303036)
            if not cat_roles:
                embed.description = "No roles setup for any category."
            for key, value in cat_roles.items():
                roles = "\n".join(
                    [
                        f"{humanize_list([role.name for role in roles])} for {humanize_number(amount)} donations"
                        for amount, roles in value.items()
                    ]
                )
                embed.add_field(
                    name=f"Category: {key.name.title()}",
                    value=f"`{roles}`" if value else "No roles setup for this category.",
                    inline=False,
                )

        else:
            data = await category.getroles(ctx)
            embed = discord.Embed(
                title=f"{category.name.title()}'s autoroles", color=await ctx.embed_color()
            )
            embed.set_footer(text=f"{ctx.guild.name}", icon_url=ctx.author.avatar_url)
            if data:
                rolelist = ""
                for key, value in data.items():
                    rolelist += f"{humanize_list([role.name for role in value])} for {humanize_number(key)} donations\n"
                embed.description = f"{rolelist}"

            elif not data:
                embed.description = f"There are no autoroles setup for this guild.\nRun `{ctx.prefix}dono setroles` to set them up."

        if not await self.config.guild(ctx.guild).autoadd():
            embed.set_footer(
                text="These roles are dull and wont be automatically added/removed since auto adding of roles is disabled for this server."
            )

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
                color=await ctx.embed_color(),
            )

        else:
            banks = await self.cache.get_all_dono_banks(ctx.guild.id)
            embed = discord.Embed(
                title=f"All your donations in **__{ctx.guild.name}__**",
                description=f"Total amount donated overall: {humanize_number(sum([bank.get_user(ctx.author.id).donations for bank in banks]))}",
                color=await ctx.embed_color(),
            )
            for bank in banks:
                donations = bank.get_user(ctx.author.id).donations
                embed.add_field(
                    name=f"*{bank.name.title()}*",
                    value=f"Donated: {bank.emoji} {humanize_number(donations)}",
                    inline=True,
                )

        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Thanks for donating <3", icon_url=ctx.guild.icon_url)

        await ctx.send(embed=embed)

    async def dono_log(
        self, ctx, action, user, amount, donos, bank, role=None, note=None
    ):  # API for giveaways.
        emoji = bank.emoji
        embed = discord.Embed(
            title="***__Added!__***" if action.lower() == "add" else "***__Removed!__***",
            description=f"{emoji} {humanize_number(amount)} was "
            f"{'added to' if action.lower() == 'add' else 'removed from'} {user.name}'s donations balance.\n",
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Category: ", value=f"**{bank.name.title()}**", inline=True)
        embed.add_field(name="Note: ", value=note if note else "No note taken.", inline=False)
        embed.add_field(
            name="Their total donations are: ", value=f"{emoji} {humanize_number(donos)}"
        )
        embed.add_field(
            name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})"
        )
        embed.set_footer(
            text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url
        )

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

    async def add_note(self, member, message, flag={}, category: DonoBank = None):
        if note := flag.get("note"):
            data = {
                "content": note,
                "message_id": message.id,
                "channel_id": message.channel.id,
                "author": message.author.id,
                "at": int(time.time()),
                "category": category.name,
            }
            async with self.config.member(member).notes() as notes:
                if not notes:
                    notes[1] = data

                else:
                    notes[len(notes) + 1] = data

            return data["content"]

        return

    async def get_member_notes(self, member: discord.Member):
        async with self.config.member(member).notes() as notes:
            return notes

    @dono.command(name="add", usage="[category] <amount> [user] [--note]")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def add(
        self,
        ctx,
        category: Optional[CategoryConverter] = None,
        amount: MoniConverter = None,
        user: Optional[discord.Member] = None,
        *,
        flag: flags = None,
    ):
        """
        Add an amount to someone's donation balance.

        This requires either one of the donation manager roles or the bot mod role.
        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        [--note] parameter is a flag used for setting notes for a donation
        For example:
            `[p]dono add dank 1000 @Twentysix --note hes cute`"""
        user = user or ctx.author

        if not amount:
            return await ctx.send_help()

        category: DonoBank = category or await self.cache.get_default_category(ctx.guild.id)

        u = category.get_user(user.id)

        donos = u.add(amount)
        note = await self.add_note(user, ctx.message, flag if flag else {}, category)

        if not await self.config.guild(ctx.guild).autoadd():
            role = f"Auto role adding is disabled for this server. Enable with `{ctx.prefix}donoset autorole add true`."
        else:
            role = await category.addroles(ctx, user)
        await self.dono_log(ctx, "add", user, amount, donos, category, role, note)

    @dono.command(name="remove", usage="[category] <amount> [user] [--note]")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def remove(
        self,
        ctx,
        category: Optional[CategoryConverter] = None,
        amount: MoniConverter = None,
        user: Optional[discord.Member] = None,
        *,
        flag: flags = None,
    ):
        """
        Remove an amount from someone's donation balance.

        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author

        if not amount:
            return await ctx.send_help()

        category: DonoBank = category or await self.cache.get_default_category(ctx.guild.id)

        u = category.get_user(user.id)
        donation = u.remove(amount)

        if not await self.config.guild(ctx.guild).autoremove():
            role = f"Auto role removing is disabled for this server. Enable with `{ctx.prefix}donoset autorole remove true`."
        else:
            role = await category.removeroles(ctx, user)
        note = await self.add_note(user, ctx.message, flag if flag else {}, category)

        await self.dono_log(ctx, "remove", user, amount, donation, category, role, note)

    @dono.command(
        name="reset",
        description="Parameters:\n\n<user> user to reset the donation balance of.",
        help="Resets a person's donation balance. Requires the manager role.",
    )
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def reset(
        self, ctx, category: Optional[CategoryConverter] = None, user: discord.Member = None
    ):
        """
        Reset someone's donation balance

        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        This will set their donations to 0.
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author

        if not category:
            await ctx.send(
                f"You didn't provide a category to reset, are you sure you want to reset all donations of {ctx.author}?"
                " Reply with `yes`/`no`."
            )
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
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Category: ", value=f"{category.name.title()}", inline=False)
        embed.add_field(
            name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})"
        )
        embed.set_footer(
            text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url
        )

        chanid = await self.config.guild(ctx.guild).logchannel()

        role = await category.removeroles(ctx, user)

        if chanid and chanid != "none":
            channel = await self.bot.fetch_channel(chanid)
            await ctx.tick()
            await channel.send(role, embed=embed)
        else:
            await ctx.send(role, embed=embed)

    @dono.command(name="notes", aliases=["note"])
    @commands.guild_only()
    @is_dmgr()
    @setup_done()
    async def check_notes(self, ctx, member: Optional[discord.Member] = None, number=None):
        """
        See donation notes taken for users.

        Theses are set with the `--note` flag in either
        `[p]dono add` or `[p]dono remove` commands."""
        EmbedField = namedtuple("EmbedField", "name value inline")
        member = member or ctx.author
        notes = await self.get_member_notes(member)
        if not notes:
            return await ctx.send(f"*{member}* has no notes!")
        if number != None:
            note = notes.get(str(number))
            print(number)
            if not note:
                return await ctx.send(
                    f"That doesn't seem to a valid note! **{member}** only has *{len(notes)}* notes."
                )

            embed = discord.Embed(
                title=f"{member.display_name.capitalize()}'s Notes!",
                description=f"Note taken on <t:{int(note['at'])}:D>",
                color=discord.Color.green(),
            )
            embed.add_field(
                name=f"**Note Number {number}**",
                value=f"*[{note['content']}]({(await (self.bot.get_channel(note['channel_id'])).fetch_message(int(note['message_id']))).jump_url})*",
                inline=False,
            )
            if cat := note.get("category"):
                embed.add_field(name="Category: ", value=f"**{cat.title()}**", inline=False)
            embed.set_footer(
                text=f"Note taken by {await self.bot.get_or_fetch_member(ctx.guild, note['author'])}"
            )
            return await ctx.send(embed=embed)

        # Thanks to epic guy for this suggestion :D

        fields = []
        embeds = []
        emb = {
            "embed": {"title": f"{member.name.capitalize()}'s Notes!", "description": ""},
            "footer": {"text": "", "icon_url": ctx.author.avatar_url},
            "fields": [],
        }
        for key, value in notes.items():
            field = EmbedField(
                f"**Note Number {key}.**",
                f"*[{value['content'][:20] if len(value['content']) > 20 else value['content']}]({(await(self.bot.get_channel(value['channel_id'])).fetch_message(int(value['message_id']))).jump_url})*",
                False,
            )
            fields.append(field)

        fieldgroups = RedHelpFormatter.group_embed_fields(fields, 200)
        page_len = len(fieldgroups)

        for i, group in enumerate(fieldgroups, 1):
            embed = discord.Embed(color=0x303036, **emb["embed"])
            emb["footer"][
                "text"
            ] = f"Use `{ctx.prefix}notes {member} [number]` to look at a specific note.\nPage {i}/{page_len}."
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
    async def check(self, ctx, user: discord.Member = None, category: CategoryConverter = None):
        """
        Check someone's donation balance.

        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        This requires either one of the donation manager roles or the bot mod role."""
        if not user:
            await ctx.send("Please mention a user or provide their id to check their donations")
            return

        if not category:
            banks = await self.cache.get_all_dono_banks(ctx.guild.id)
            embed = discord.Embed(
                title=f"All of {user}'s donations in **__{ctx.guild.name}__**",
                description=f"Total amount donated overall: {humanize_number(sum([bank.get_user(ctx.author.id).donations for bank in banks]))}",
                color=await ctx.embed_color(),
            )
            for bank in banks:
                donations = bank.get_user(user.id).donations
                embed.add_field(
                    name=f"*{bank.name.title()}*",
                    value=f"Donated: {bank.emoji} {humanize_number(donations)}",
                    inline=True,
                )

            return await ctx.send(embed=embed)

        donos = category.get_user(ctx.author.id).donations
        emoji = category.emoji
        notes = len(await self.get_member_notes(user))

        embed = discord.Embed(
            title=f"{user}'s donations in **__{ctx.guild.name}__**",
            description=f"Total amount donated: {emoji}{humanize_number(donos)}\n\nThey have **{notes}** notes",
            color=discord.Color.random(),
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        embed.set_footer(text=f"{ctx.guild.name}", icon_url=ctx.guild.icon_url)

        await ctx.send(embed=embed)

    @dono.command(
        name="leaderboard",
        aliases=["lb", "topdonators"],
    )
    @commands.guild_only()
    @setup_done()
    async def leaderboard(self, ctx, category: CategoryConverter, topnumber=5):
        """
        See the top donators in the server.

        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        Use the <topnumber> parameter to see the top `x` donators."""
        data: List[DonoUser] = category.get_leaderboard()

        embed = discord.Embed(
            title=f"Top {topnumber} donators for **__{category.name.title()}__**",
            color=discord.Color.random(),
        )
        emoji = category.emoji

        if data:
            for index, user in enumerate(data, 1):
                if user.donations != 0:
                    embed.add_field(
                        name=(
                            f"{index}. **{u.display_name}**"
                            if (u := user.user)
                            else f"{index}. **{user.user_id} (User not found in server)**"
                        ),
                        value=f"{emoji} {humanize_number(user.donations)}",
                        inline=False,
                    )

                if (index) == topnumber:
                    break

        else:
            embed.description = f"No donations have been made yet for **{category}**."

        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.set_author(name=ctx.guild.name)
        embed.set_footer(
            text=f"For a higher top number, do `{ctx.prefix}dono lb {category.name} [amount]`"
        )

        await ctx.send(embed=embed)

    @commands.group(name="donoset", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def donoset(self, ctx):
        """
        Base command for changing donation settings for your server."""

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
    async def ar_add(self, ctx, true_or_false: bool):
        """
        Set whether donation roles(set with `[p]donoset addroles`) automatically get added to users or not.

        \n<true_or_false> is supposed to be either of True or False.
        True to enable and False to disable."""
        toggle = await self.config.guild(ctx.guild).autoadd()
        if toggle and true_or_false:
            return await ctx.send("Auto-role adding is already enabled for this server.")
        elif not toggle and not true_or_false:
            return await ctx.send("Auto-role adding is already disabled for this server.")

        await self.config.guild(ctx.guild).autoadd.set(true_or_false)
        return await ctx.send(
            f"{'Disabled' if true_or_false == False else 'Enabled'} auto role adding for this server"
        )

    @autorole.command(name="remove")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def ar_remove(self, ctx, true_or_false: bool):
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
        return await ctx.send(
            f"{'Disabled' if true_or_false == False else 'Enabled'} auto role removing for this server"
        )

    @donoset.group(name="category", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def category(self, ctx):
        """
        Manage currency categories in your guild.

        These allow you to log donations of multiple different currencies.
        """
        return await ctx.send_help()

    @category.command(name="add")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def category_add(self, ctx, *categories: CategoryMaker):
        """
        Add a new category to your server.

        You can add multiple categories at once.
        The format for a category definition is `name,emoji`.
        Multiple categories should be separated by a space. `name,emoji anothername,emoji2 thirdcategory,emoji3`
        """
        if not categories:
            return await ctx.send("You need to specify at least one category.")
        guild = ctx.guild
        await ctx.send(
            (
                (
                    "The following new categories have been added: "
                    if len(categories) > 1
                    else "The following category has been added: "
                )
                + "\n"
                + "\n".join(
                    f"{categories.index(category) + 1}:  {category.name} - {category.emoji}"
                    for category in categories
                )
            )
        )

    @category.command(name="remove")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def category_remove(self, ctx, *categories: CategoryConverter):
        """
        Remove a category from your server.

        You can remove multiple categories at once.
        Send their names separated with a space.
        For example:
        `name anothername thirdcategory`"""
        if not categories:
            return await ctx.send("You need to specify at least one category.")
        for category in categories:
            self.cache._CACHE.remove(category)
            await self.cache.config.custom("guild_category", ctx.guild.id, category.name).clear()

        async with self.cache.config.guild(ctx.guild).categories() as cats:
            for category in categories:
                del cats[category.name]

        await ctx.send("Given categories have been deleted!")

    @category.command(name="list")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def category_list(self, ctx):
        """
        List all currency categories in your server."""
        guild = ctx.guild
        categories = await self.cache.config.guild(guild).categories()
        categories = {category: data["emoji"] for category, data in categories.items()}
        embed = discord.Embed(
            title=f"Registered currency categories in **__{ctx.guild.name}__**",
            description="\n".join(
                [
                    f"{index}: {emoji} {category} "
                    f"{'(default)' if category == await self.cache.get_default_category(ctx.guild.id) else ''}"
                    for index, (category, emoji) in enumerate(categories.items(), 1)
                ]
            ),
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=embed)

    @category.command(name="default")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def category_default(self, ctx, *, category: CategoryConverter = None):
        """
        See or set the default category for your server.

        if not category is given, it will show the currenct default.

        This category will be used for commands if no category is specified
        in commands that require a category being specified.
        """
        if not category:
            return await ctx.send(
                f"The current default category is: {await self.cache.get_default_category(ctx.guild.id)}"
            )
        await self.cache.set_default_category(ctx.guild.id, category.name)
        await ctx.send(f"Default category for this server has been set to {category.name}")

    @donoset.command(name="addroles")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def addroles(self, ctx, category: CategoryConverter, *, pairs: AmountRoleConverter):
        """
        Add autoroles for a category.

        The pairs argument should be in this format:
        `amount` `,` `multiple roles separated with a colon(:)`
        For example:
            `10000,someroleid:onemoreroleid 15k,@rolemention 20e4,arolename`"""
        data = await self.cache.config.guild(ctx.guild).categories()
        cop = data.copy()
        cat_roles = cop.get(category.name)
        cat_roles.pop("emoji")

        _pairs = {amount: [role.id for role in roles] for amount, roles in pairs.items()}
        for k, v in _pairs.items():
            k = str(k)
            r = cat_roles.get(k)
            if not r:
                cat_roles.update({k: v})

            else:
                for rid in v:
                    if rid in r:
                        continue
                    r.append(rid)

        async with self.cache.config.guild(ctx.guild).categories() as cats:
            cats[category.name].update(cat_roles)

        embed = discord.Embed(
            title=f"Updated autoroles for {category.name.title()}!", color=await ctx.embed_color()
        )
        rolelist = ""
        for key, value in cat_roles.items():
            rolelist += f"{humanize_list([ctx.guild.get_role(role).name for role in value])} for {humanize_number(key)} donations\n"
        embed.description = f"`{rolelist}`"

        await ctx.send(embed=embed)

    @donoset.command(name="managers")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def set_managers(self, ctx, add_or_remove, roles: Greedy[discord.Role] = None):
        """Adds or removes managers for your guild.

        This is an alternative to `[p]dono setup`.
        You can use this to add or remove manager roles post setup.

        <add_or_remove> should be either `add` to add roles or `remove` to remove roles.
        """
        if roles is None:
            return await ctx.send("`Roles` is a required argument.")

        async with self.config.guild(ctx.guild).managers() as l:
            for role in roles:
                if add_or_remove.lower() == "add":
                    if not role.id in l:
                        l.append(role.id)

                elif add_or_remove.lower() == "remove":
                    if role.id in l:
                        l.remove(role.id)

        return await ctx.send(
            f"Successfully {'added' if add_or_remove.lower() == 'add' else 'removed'} {len([role for role in roles])} roles."
        )

    @donoset.command(name="logchannel")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def set_channel(self, ctx, channel: discord.TextChannel = None):
        """Set the donation logging channel or reset it.

        This is an alternative to `[p]dono setup`.
        You can use this to change or reset log channel post setup.
        """

        await self.config.guild(ctx.guild).logchannel.set(None if not channel else channel.id)
        return await ctx.send(
            f"Successfully set {channel.mention} as the donation logging channel."
            if channel
            else "Successfully reset the log channel."
        )

    @donoset.command(name="showsettings", aliases=["showset", "ss"])
    @setup_done()
    async def showsettings(self, ctx):
        """
        See all the configured donation logging settings for your guild.
        """
        data = await self.config.guild(ctx.guild).all()

        embed = discord.Embed(
            title=f"Donation Logging settings for {ctx.guild}",
            color=0x303036,
            timestamp=ctx.message.created_at,
        )
        managers = (
            humanize_list([(ctx.guild.get_role(i)).mention for i in data["managers"]])
            if data["managers"]
            else data["managers"]
        )
        categories = await self.cache.config.guild(ctx.guild).categories()
        embed.add_field(
            name="Donation Managers: ",
            value=(managers) if data["managers"] else "None",
            inline=False,
        )
        embed.add_field(
            name="Log Channel: ",
            value=f"<#{data['logchannel']}>" if data["logchannel"] else "None",
            inline=False,
        )
        embed.add_field(name="Auto Add Roles: ", value=data["autoadd"], inline=False)
        embed.add_field(name="Auto Remove Roles: ", value=data["autoremove"])
        embed.add_field(
            name="Categories: ",
            value=f"{len(categories)} categories: `{humanize_list(list(categories.keys()))}`",
            inline=False,
        )
        await ctx.send(embed=embed)
