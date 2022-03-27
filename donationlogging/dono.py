import asyncio
import operator
import time
from collections import namedtuple
from typing import List, Optional

import discord
from discord.ext import tasks
from discord.ext.commands.converter import Greedy
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.commands import RedHelpFormatter
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from tabulate import tabulate

from donationlogging.models import DonationManager, DonoItem, DonoUser

from .utils import *

DictConverter = commands.get_dict_converter(delims=[",", " "])


class DonationLogging(commands.Cog):
    """
    Donation logging commands.
    Helps you in counting and tracking user donations (**for discord bot currencies**) and automatically assigning them roles.
    """

    __version__ = "2.3.2"
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

        self._task = self._back_to_config.start()

        self.conv = MoniConverter().convert  # api for giveaway cog.

    @classmethod
    async def initialize(cls, bot):
        self = cls(bot)

        if (task := getattr(bot, "_backing_up_task", None)) is not None:
            await task

        self.cache = await DonationManager.initialize(bot)

        return self

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
        self._task.cancel()
        self.bot._backing_up_task = asyncio.create_task(self.cache._back_to_config())

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

    @tasks.loop(minutes=5)
    async def _back_to_config(self):
        if not self.cache:
            return
        await self.cache._back_to_config()

    @_back_to_config.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_red_ready()

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
            (
                "Which roles do you want to be able to manage donations?",
                "You can provide multiple roles. Send their ids/mentions/names all in one message separated by a comma.",
                "roles",
                manager_roles(ctx),
            ),
            (
                "Which channel do you want the donations to be logged to?",
                "Type 'None' if you dont want that",
                "channel",
                channel_conv(ctx),
            ),
            (
                "What would you like your first donation logging currency category to be named?",
                "Send its name and emoji (id only) separated by a comma."
                "You can use custom emojis as long as the bot has access to it.\nFor example: `dank,⏣`",
                "category",
                category_conv(ctx),
            ),
            (
                "Are there any roles that you would like to be assigned at certain milestones in this category?",
                (
                    "Send amount and roles separate by a comma. "
                    "Multiple roles should also be separated by a colon (:) or just send `none`"
                    "\nFor example: `10000,someroleid:onemoreroleid 15k,@rolemention 20e4,arolename`"
                ),
                "milestones",
                amountrole_conv(ctx),
            ),
        ]

        answers = await ask_for_answers(ctx, questions, 60)

        if not answers:
            return

        roles = answers["roles"]
        channel = answers["channel"]
        bank = answers["category"]
        pairs = answers["milestones"]

        emb = discord.Embed(title="Is all this information valid?", color=await ctx.embed_color())
        emb.add_field(
            name=f"Question: `{questions[0][0]}`",
            value=f"Answer: `{' '.join([role.name for role in roles])}`",
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
            value=f"Answer: \n`{ans4}`" if pairs else f"Answer: `None given`.",
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
            await self.category_remove(ctx, bank)
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
            log = ctx.guild.get_channel(int(chanid))
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
        amount: AmountOrItem = None,
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

        category: DonoBank = ctx.dono_category

        if not category:
            return await ctx.send(
                "Default category was not set for this server. Please pass a category name when running the command."
            )

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

        if not category:
            return await ctx.send(
                "Default category was not set for this server. Please pass a category name when running the command."
            )

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
        Reset a category or a user's donation balance.

        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        If a user isn't provided, this command will reset all the users in the category.
        If a category isn't provided, this command will reset the user's donation balance for all categories.
        This requires either one of the donation manager roles or the bot mod role."""
        if user:
            if not category:
                await ctx.send(
                    f"You didn't provide a category to reset, are you sure you want to reset all donations of {user}?"
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

        else:
            if not category:
                return await ctx.send(
                    "You need to provide either a category or a user to reset or both."
                )
            await ctx.send(
                f"You didn't provide a user to reset, are you sure you want to reset all donations of the category `{category.name}`?"
                " Reply with `yes`/`no`."
            )
            pred = MessagePredicate.yes_or_no(ctx)
            try:
                await ctx.bot.wait_for("message", check=pred, timeout=30)
            except asyncio.TimeoutError:
                return await ctx.send("No response, aborting.")

            if pred.result:
                category._data = {}
                return await ctx.send(
                    f"Category **`{category.name}`**'s donations have been reset."
                )

            else:
                return await ctx.send("Alright!")

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
                description=f"Total amount donated overall: {humanize_number(sum([bank.get_user(user.id).donations for bank in banks]))}",
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

        donos = category.get_user(user.id).donations
        emoji = category.emoji
        notes = len(await self.get_member_notes(user))

        embed = discord.Embed(
            title=f"{user}'s donations in **__{ctx.guild.name}__**",
            description=f"Total amount donated: {emoji}{humanize_number(donos)}\n\nThey have **{notes}** notes",
            color=discord.Color.random(),
        )
        embed.set_author(name=user, icon_url=user.avatar_url)
        embed.set_footer(text=f"{ctx.guild.name}", icon_url=ctx.guild.icon_url)

        await ctx.send(embed=embed)

    @dono.command(name="amountcheck", aliases=["ac"])
    @commands.guild_only()
    @is_dmgr()
    @setup_done()
    async def dono_amountcheck(
        self,
        ctx: commands.Context,
        category: CategoryConverter,
        function: str,
        amount: MoniConverter,
    ):
        """
        See who has donated more/less than the given amount in the given category.

        The fuction is one of `less` or `more`. Pretty much self explanatory but if u pass `less`,
        it will return users that have doanted less than that amount, and more does the opposite.
        This sends an embedded list of user mentions alonside their ids.
        The category must be the name of a registered category. These can be seen with `[p]donoset category list`
        This requires either one of the donation manager roles or the bot mod role."""

        if not function.lower() in ["less", "more"]:
            return await ctx.send("Valid function arguments are: `less` or `more`")

        cat: DonoBank = category
        lb = cat.get_leaderboard()

        if not lb:
            return await ctx.send(
                "No donations have been made yet for the category **`{}`**".format(cat.name)
            )

        op = operator.ge if function == "more" else operator.le

        lb = filter(lambda x: op(x.donations, amount), lb)

        final = [(x.user, f"{x.donations:,}") for x in lb]
        if not final:
            return await ctx.send(
                "No users have donated `{}` than **`{}`** in the category **`{}`**".format(
                    function, amount, cat.name
                )
            )

        headers = ["UserName", "Donations"]

        msg = tabulate(final, tablefmt="rst", showindex=True, headers=headers)
        pages = []
        title = f"Donation Leaderboard for {cat.name}\n\t{function.capitalize()} than {amount:,}"

        for page in pagify(msg, delims=["\n"], page_length=700):
            page = title + "\n\n" + page + "\n\n"
            pages.append(box(page, lang="html"))

        if len(pages) == 1:
            return await ctx.send(pages[0])
        return await menu(ctx, pages, DEFAULT_CONTROLS)

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
        return await ctx.send_help()

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
        await ctx.send(
            (
                (
                    "The following new categories have been added: "
                    if len(categories) > 1
                    else "The following category has been added: "
                )
                + "\n"
                + "\n".join(
                    f"{index}:  {category.name} - {category.emoji}"
                    for index, category in enumerate(categories, 1)
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

        all_banks = await self.cache.get_all_dono_banks(ctx.guild.id)

        for category in categories:
            self.cache._CACHE.remove(category)
            if category.is_default:
                if len(all_banks) == 1 and all_banks[0] == category:
                    return await ctx.send(
                        "You only have one category and that is the default. Create a new category before removing the default."
                    )

                await self.cache.config.guild(ctx.guild).default_category.set(None)
            await self.cache.config.custom("guild_category", ctx.guild.id, category.name).clear()

        async with self.cache.config.guild(ctx.guild).categories() as cats:
            for category in categories:
                del cats[category.name]

        await ctx.send("Given categories have been deleted!")

    @category.group(name="item", aliases=["items"])
    async def category_item(self, ctx):
        """
        Manage item amounts to count towards a category.

        You can use these item names in place of the amount argument in `dono add/remove` commands.
        """

    @category_item.command(name="add")
    async def category_item_add(
        self, ctx, category: CategoryConverter, *, items: DictConverter
    ):
        """
        Add items to a category.

        You can add multiple items at once.
        The format for an item definition is `name,amount`.
        Multiple items should be separated by a space. `name,amount anothername,amount2 thirditem,amount3`"""
        if not items:
            return await ctx.send("You need to specify at least one item.")
        async with self.cache.config.guild(ctx.guild).categories.get_attr(
            category.name
        )() as cat_data:
            cat_items = cat_data.setdefault("items", {})
            for item, amount in items.items():

                if item in cat_items:
                    return await ctx.send(f"{item} is already in {category.name}")

                try:
                    amt = await self.conv(ctx, amount)

                except:
                    return await ctx.send(
                        "Invalid amount for item `{}`: `{}`".format(item, amount)
                    )

                cat_items[item] = amt

                category.items.append(DonoItem(item, int(amt), category))

        await ctx.send(f"Given items have been added to {category.name}")

    @category_item.command(name="remove")
    async def category_item_remove(self, ctx, category: CategoryConverter, *items):
        """
        Remove items from a category.

        You can remove multiple items at once.
        Just send their exact names separated by a space."""
        if not items:
            return await ctx.send("You need to specify at least one item.")
        async with self.cache.config.guild(ctx.guild).categories.get_attr(
            category.name
        )() as cat_data:
            cat_items = cat_data.setdefault("items", {})
            if not cat_items:
                return await ctx.send("No items registered for this category.")
            for item in items:

                if item not in cat_items:
                    return await ctx.send(f"{item} is not present in {category.name}")

                del cat_items[item]
                item = await category.get_item(item)
                category.items.remove(item)

        await ctx.send(f"Given items have been removed from {category.name}")

    @category_item.command(name="list")
    async def category_item_list(self, ctx, category: CategoryConverter):
        """
        List all registered items of a category.
        """
        cat_items = category.items
        if not cat_items:
            return await ctx.send("No items registered for this category.")
        tab = tabulate([(item.name, item.amount) for item in cat_items], ["Item Name", "Worth"])
        await ctx.send("Following items are registered for this category:\n" + box(tab, lang="py"))

    @category.command(name="list")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def category_list(self, ctx):
        """
        List all currency categories in your server."""
        categories = await self.cache.get_all_dono_banks(ctx.guild.id)
        if not categories:
            return await ctx.send("There are no categories in this server.")

        default = await self.cache.get_default_category(ctx.guild.id)

        embed = discord.Embed(
            title=f"Registered currency categories in **__{ctx.guild.name}__**",
            description="\n".join(
                [
                    f"{index}: {category.emoji} {category.name} "
                    f"{'(default)' if category == default else ''}"
                    for index, category in enumerate(categories, 1)
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
        await self.cache.set_default_category(ctx.guild.id, category)
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
        cat_roles = cop.get(category.name).get("roles")

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

        await category.setroles(_pairs)

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
