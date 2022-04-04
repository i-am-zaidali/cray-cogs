import asyncio
import operator
from typing import List, Optional

import discord
from discord.ext import tasks
from discord.ext.commands.converter import Greedy
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate
from tabulate import tabulate

from .models import DonationManager, DonoItem, DonoUser
from .utils import *

DictConverter = commands.get_dict_converter(delims=[",", " "])


class DonationLogging(commands.Cog):
    """
    Donation logging commands.
    Helps you in counting and tracking user donations (**for discord bot currencies**) and automatically assigning them roles.
    """

    __version__ = "2.6.0"
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

        self._task = self._back_to_config.start()

        self.conv = MoniConverter().convert  # api for giveaway cog.

    @classmethod
    async def initialize(cls, bot):
        self = cls(bot)

        if (task := getattr(bot, "_backing_up_task", None)) is not None:
            await task

        self.cache = await DonationManager.initialize(bot)

        self.bot.add_dev_env_value("dono", lambda ctx: self)

        notes = await self.config.all_members()
        if notes:
            cog = self.notes_cog
            if not cog:
                return self
            for guild_id, data in notes.items():
                for member_id, d in data.items():
                    if d.get("notes"):
                        for note in d["notes"].values():
                            cog._create_note(
                                guild_id,
                                note["author"],
                                note["content"],
                                member_id,
                                "DonationNote",
                                note["at"],
                            )

                    await self.config.member_from_ids(guild_id, member_id).clear()

        return self

    @property
    def notes_cog(self):
        return self.bot.get_cog("Notes")

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
        self.bot.remove_dev_env_value("dono")

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

        This helps you setup basic stuff sich as the logging channel and manager roles.

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
                "What would you like your first donation logging currency bank to be named?",
                "Send its name and emoji (id only) separated by a comma."
                "You can use custom emojis as long as the bot has access to it.\nFor example: `dank,⏣`",
                "bank",
                bank_conv(ctx),
            ),
            (
                "Are there any roles that you would like to be assigned at certain milestones in this bank?",
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
        bank = answers["bank"]
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
            await self.bank_remove(ctx, bank)
            return await ctx.send("Aight, retry the command and do it correctly this time.")

        await self.config.guild(ctx.guild).logchannel.set(channel.id if channel else None)
        await self.config.guild(ctx.guild).managers.set([role.id for role in roles])
        await self.config.guild(ctx.guild).setup.set(True)
        if pairs:
            await bank.setroles(pairs)
        await self.cache.set_default_bank(ctx.guild.id, bank)

        if old_data := await self.get_old_data(ctx.guild):
            confirmation = await ctx.send(
                "Old donation logging data was found for this guild. "
                "\nWould you like to associate it with the bank you just registered? "
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
                    "Updated new bank with old data :D You can now continue logging donations normally."
                )

        return await ctx.send(
            f"Alright. I've noted that down. You can now start logging donations."
        )

    @dono.command(name="bal", aliases=["mydono"])
    @commands.guild_only()
    @setup_done()
    async def bal(self, ctx, bank: BankConverter = None):
        """
        Check the amount you have donated in the current server

        For admins, if you want to check other's donations, use `[p]dono check`"""
        if bank:
            donos = bank.get_user(ctx.author.id).donations
            emoji = bank.emoji

            embed = discord.Embed(
                title=f"Your donations in **__{ctx.guild.name}__** for **__{bank.name}__**",
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
                if bank.hidden: 
                    continue
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
        self, 
        ctx: commands.Context, 
        action: str, 
        user: discord.Member, 
        amount: int, 
        donos: int, 
        bank: DonoBank, 
        role: str = None, 
        note: str = None
    ):
        emoji = bank.emoji
        embed = discord.Embed(
            title="***__Added!__***" if action.lower() == "add" else "***__Removed!__***",
            description=f"{emoji} {humanize_number(amount)} was "
            f"{'added to' if action.lower() == 'add' else 'removed from'} {user.name}'s donations balance.\n",
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Bank: ", value=f"**{bank.name.title()}**", inline=True)
        embed.add_field(name="Note: ", value=str(note) if note else "No note taken.", inline=False)
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

    async def add_note(self, ctx: commands.Context, member, flag={}):
        if note := flag.get("note"):
            cog = self.notes_cog

            note = cog._create_note(ctx.guild.id, ctx.author.id, note, member.id, "DonationNote")

            return note.content

        return

    @dono.command(name="add", usage="[bank] <amount> [user] [--note]")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def add(
        self,
        ctx,
        bank: Optional[BankConverter] = None,
        amount: AmountOrItem = None,
        user: Optional[discord.Member] = None,
        *,
        flag: flags = None,
    ):
        """
        Add an amount to someone's donation balance.

        This requires either one of the donation manager roles or the bot mod role.
        The bank must be the name of a registered bank. These can be seen with `[p]donoset bank list`
        [--note] parameter is a flag used for setting notes for a donation
        For example:
            `[p]dono add dank 1000 @Twentysix --note hes cute`"""
        user = user or ctx.author

        if not amount:
            return await ctx.send_help()

        bank: DonoBank = ctx.dono_bank

        if not bank:
            return await ctx.send(
                "Default bank was not set for this server. Please pass a bank name when running the command."
            )

        u = bank.get_user(user.id)

        donos = u.add(amount)
        note = await self.add_note(ctx, user, flag if flag else {}, bank)

        if not await self.config.guild(ctx.guild).autoadd():
            role = f"Auto role adding is disabled for this server. Enable with `{ctx.prefix}donoset autorole add true`."
        else:
            role = await bank.addroles(ctx, user)
        await self.dono_log(ctx, "add", user, amount, donos, bank, role, note)

    @dono.command(name="remove", usage="[bank] <amount> [user] [--note]")
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def remove(
        self,
        ctx,
        bank: Optional[BankConverter] = None,
        amount: MoniConverter = None,
        user: Optional[discord.Member] = None,
        *,
        flag: flags = None,
    ):
        """
        Remove an amount from someone's donation balance.

        The bank must be the name of a registered bank. These can be seen with `[p]donoset bank list`
        This requires either one of the donation manager roles or the bot mod role."""
        user = user or ctx.author

        if not amount:
            return await ctx.send_help()

        bank: DonoBank = ctx.dono_bank

        if not bank:
            return await ctx.send(
                "Default bank was not set for this server. Please pass a bank name when running the command."
            )

        u = bank.get_user(user.id)
        donation = u.remove(amount)

        if not await self.config.guild(ctx.guild).autoremove():
            role = f"Auto role removing is disabled for this server. Enable with `{ctx.prefix}donoset autorole remove true`."
        else:
            role = await bank.removeroles(ctx, user)
        note = await self.add_note(ctx, user, flag if flag else {}, bank)

        await self.dono_log(ctx, "remove", user, amount, donation, bank, role, note)

    @dono.command(
        name="reset",
        description="Parameters:\n\n<user> user to reset the donation balance of.",
        help="Resets a person's donation balance. Requires the manager role.",
    )
    @is_dmgr()
    @commands.guild_only()
    @setup_done()
    async def reset(
        self, ctx, bank: Optional[BankConverter] = None, user: discord.Member = None
    ):
        """
        Reset a bank or a user's donation balance.

        The bank must be the name of a registered bank. These can be seen with `[p]donoset bank list`
        If a user isn't provided, this command will reset all the users in the bank.
        If a bank isn't provided, this command will reset the user's donation balance for all banks.
        This requires either one of the donation manager roles or the bot mod role."""

        user = user or ctx.author

        if not bank:
            await ctx.send(
                f"You didn't provide a bank to reset, are you sure you want to reset all donations of {user}?"
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

        bank.remove_user(user.id)
        emoji = bank.emoji

        embed = discord.Embed(
            title="***__Reset!__***",
            description=f"Resetted {user.name}'s donation bal. Their current donation amount is {emoji} 0",
            color=await ctx.embed_color(),
        )
        embed.add_field(name="Bank: ", value=f"{bank.name.title()}", inline=False)
        embed.add_field(
            name="Jump Link To The Command:", value=f"[click here]({ctx.message.jump_url})"
        )
        embed.set_footer(
            text=f"Command executed by: {ctx.author.display_name}", icon_url=ctx.guild.icon_url
        )

        chanid = await self.config.guild(ctx.guild).logchannel()

        role = await bank.removeroles(ctx, user)

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
    async def check_notes(self, ctx, member: Optional[discord.Member] = None):
        """
        See donation notes taken for users.

        Theses are set with the `--note` flag in either
        `[p]dono add` or `[p]dono remove` commands."""
        member = member or ctx.author
        if not (cog := self.notes_cog):
            return await ctx.send("Notes cog isn't loaded. Please make sure it's loaded.")

        notes = self.notes_cog._get_notes_of_type(ctx.guild, member, cog.note_type.DonationNote)

        if not notes:
            return await ctx.send(f"*{member}* has no notes!")

        embed = discord.Embed(
            title=f"{member.display_name.capitalize()}'s Notes!",
            color=member.color,
        )

        for i, note in enumerate(notes, 1):
            embed.add_field(name=f"Note:- {i} ", value=note, inline=False)

        embed.set_footer(text=f"Use `{ctx.prefix}delnote <id>` to remove a note.")

        return await ctx.send(embed=embed)

    @dono.command(name="check")
    @commands.guild_only()
    @is_dmgr()
    @setup_done()
    async def check(self, ctx, user: discord.Member = None, bank: BankConverter = None):
        """
        Check someone's donation balance.

        The bank must be the name of a registered bank. These can be seen with `[p]donoset bank list`
        This requires either one of the donation manager roles or the bot mod role."""
        if not user:
            await ctx.send("Please mention a user or provide their id to check their donations")
            return

        if not bank:
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

        donos = bank.get_user(user.id).donations
        emoji = bank.emoji
        notes = len(
            self.notes_cog._get_notes_of_type(
                ctx.guild, user, self.notes_cog.note_type.DonationNote
            )
        )

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
        bank: BankConverter,
        function: str,
        amount: MoniConverter,
    ):
        """
        See who has donated more/less than the given amount in the given bank.

        The fuction is one of `less` or `more`. Pretty much self explanatory but if u pass `less`,
        it will return users that have doanted less than that amount, and more does the opposite.
        This sends an embedded list of user mentions alonside their ids.
        The bank must be the name of a registered bank. These can be seen with `[p]donoset bank list`
        This requires either one of the donation manager roles or the bot mod role."""

        if not function.lower() in ["less", "more"]:
            return await ctx.send("Valid function arguments are: `less` or `more`")

        lb = bank.get_leaderboard()

        if not lb:
            return await ctx.send(
                "No donations have been made yet for the bank **`{}`**".format(bank.name)
            )

        op = operator.ge if function == "more" else operator.le

        lb = filter(lambda x: op(x.donations, amount), lb)

        final = [(x.user, f"{x.donations:,}") for x in lb]
        if not final:
            return await ctx.send(
                "No users have donated `{}` than **`{}`** in the bank **`{}`**".format(
                    function, amount, bank.name
                )
            )

        headers = ["UserName", "Donations"]

        msg = tabulate(final, tablefmt="rst", showindex=True, headers=headers)
        pages = []
        title = f"Donation Leaderboard for {bank.name}\n\t{function.capitalize()} than {amount:,}"

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
    async def leaderboard(self, ctx, bank: BankConverter, topnumber=5):
        """
        See the top donators in the server.

        The bank must be the name of a registered bank. These can be seen with `[p]donoset bank list`
        Use the <topnumber> parameter to see the top `x` donators."""
        data: List[DonoUser] = bank.get_leaderboard()

        embed = discord.Embed(
            title=f"Top {topnumber} donators for **__{bank.name.title()}__**",
            color=discord.Color.random(),
        )
        emoji = bank.emoji

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
            embed.description = f"No donations have been made yet for **{bank}**."

        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.set_author(name=ctx.guild.name)
        embed.set_footer(
            text=f"For a higher top number, do `{ctx.prefix}dono lb {bank.name} [amount]`"
        )

        await ctx.send(embed=embed)

    @commands.group(name="donoset", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def donoset(self, ctx):
        """
        Base command for changing donation settings for your server."""
        await ctx.send_help()

    @donoset.group(name="autorole", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def autorole(self, ctx):
        """
        Change settings for Auto donation roles behaviour in your server."""
        await ctx.send_help()

    @autorole.command(name="add")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def ar_add(self, ctx, true_or_false: bool):
        """
        Set whether donation roles(set with `[p]donoset bank roles`) automatically get added to users or not.

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
        Set whether donation roles (set with `[p]donoset bank roles`) automatically get removed from users or not.

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

    @donoset.group(name="bank", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank(self, ctx):
        """
        Manage currency banks in your guild.

        These allow you to log donations of multiple different currencies.
        """
        await ctx.send_help()

    @bank.command(name="add")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_add(self, ctx, *banks: BankMaker):
        """
        Add a new bank to your server.

        You can add multiple banks at once.
        The format for a bank definition is `name,emoji`.
        Multiple banks should be separated by a space. `name,emoji anothername,emoji2 thirdbank,emoji3`
        """
        if not banks:
            return await ctx.send("You need to specify at least one bank.")
        await ctx.send(
            (
                (
                    "The following new banks have been added: "
                    if len(banks) > 1
                    else "The following bank has been added: "
                )
                + "\n"
                + "\n".join(
                    f"{index}:  {bank.name} - {bank.emoji}"
                    for index, bank in enumerate(banks, 1)
                )
            )
        )

    @bank.command(name="remove")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_remove(self, ctx, *banks: BankConverter):
        """
        Remove a bank from your server.

        You can remove multiple banks at once.
        Send their names separated with a space.
        For example:
        `name anothername thirdbank`"""
        if not banks:
            return await ctx.send("You need to specify at least one bank.")

        all_banks = await self.cache.get_all_dono_banks(ctx.guild.id)

        for bank in banks:
            self.cache._CACHE.remove(bank)
            if bank.is_default:
                if len(all_banks) == 1 and all_banks[0] == bank:
                    return await ctx.send(
                        "You only have one bank and that is the default. Create a new bank before removing the default."
                    )

                await self.cache.config.guild(ctx.guild).default_bank.set(None)
            await self.cache.config.custom("guild_bank", ctx.guild.id, bank.name).clear()

        async with self.cache.config.guild(ctx.guild).banks() as cats:
            for bank in banks:
                del cats[bank.name]

        await ctx.send("Given banks have been deleted!")

    @bank.group(name="item", aliases=["items"], invoke_without_command=True)
    async def bank_item(self, ctx):
        """
        Manage item amounts to count towards a bank.

        You can use these item names in place of the amount argument in `dono add/remove` commands.
        """
        await ctx.send_help()

    @bank_item.command(name="add")
    async def bank_item_add(self, ctx, bank: BankConverter, *, items: DictConverter):
        """
        Add items to a bank.

        You can add multiple items at once.
        The format for an item definition is `name,amount`.
        Multiple items should be separated by a space. `name,amount anothername,amount2 thirditem,amount3`"""
        if not items:
            return await ctx.send("You need to specify at least one item.")
        async with self.cache.config.guild(ctx.guild).banks.get_attr(
            bank.name
        )() as cat_data:
            cat_items = cat_data.setdefault("items", {})
            for item, amount in items.items():

                if item in cat_items:
                    return await ctx.send(f"{item} is already in {bank.name}")

                try:
                    amt = await self.conv(ctx, amount)

                except:
                    return await ctx.send(
                        "Invalid amount for item `{}`: `{}`".format(item, amount)
                    )

                cat_items[item] = amt

                bank.items.append(DonoItem(item, int(amt), bank))

        await ctx.send(f"Given items have been added to {bank.name}")

    @bank_item.command(name="remove")
    async def bank_item_remove(self, ctx, bank: BankConverter, *items):
        """
        Remove items from a bank.

        You can remove multiple items at once.
        Just send their exact names separated by a space."""
        if not items:
            return await ctx.send("You need to specify at least one item.")
        async with self.cache.config.guild(ctx.guild).banks.get_attr(
            bank.name
        )() as cat_data:
            cat_items = cat_data.setdefault("items", {})
            if not cat_items:
                return await ctx.send("No items registered for this bank.")
            for item in items:

                if item not in cat_items:
                    return await ctx.send(f"{item} is not present in {bank.name}")

                del cat_items[item]
                item = await bank.get_item(item)
                bank.items.remove(item)

        await ctx.send(f"Given items have been removed from {bank.name}")

    @bank_item.command(name="list")
    async def bank_item_list(self, ctx, bank: BankConverter):
        """
        List all registered items of a bank.
        """
        cat_items = bank.items
        if not cat_items:
            return await ctx.send("No items registered for this bank.")
        tab = tabulate([(item.name, item.amount) for item in cat_items], ["Item Name", "Worth"])
        await ctx.send("Following items are registered for this bank:\n" + box(tab, lang="py"))

    @bank.command(name="list")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_list(self, ctx):
        """
        List all currency banks in your server."""
        banks = await self.cache.get_all_dono_banks(ctx.guild.id)
        if not banks:
            return await ctx.send("There are no banks in this server.")

        default = await self.cache.get_default_bank(ctx.guild.id)

        embed = discord.Embed(
            title=f"Registered currency banks in **__{ctx.guild.name}__**",
            description="\n".join(
                [
                    f"{index}: {bank.emoji} {bank.name} "
                    f"{'(default)' if bank == default else ''}"
                    for index, bank in enumerate(banks, 1)
                ]
            ),
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=embed)

    @bank.command(name="default")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_default(self, ctx, *, bank: BankConverter = None):
        """
        See or set the default bank for your server.

        if no bank is given, it will show the current default.

        This bank will be used for commands if no bank is specified
        in commands that require a bank being specified.
        """
        if not bank:
            return await ctx.send(
                f"The current default bank is: {await self.cache.get_default_bank(ctx.guild.id)}"
            )
        await self.cache.set_default_bank(ctx.guild.id, bank)
        await ctx.send(f"Default bank for this server has been set to {bank.name}")

    @bank.command(name="reset")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_reset(self, ctx: commands.Context, *banks: BankConverter):
        """
        Reset given banks in your server.

        This will remove all donations of that bank.
        """
        await ctx.send(
            f"Are you sure you want to reset all donations of the given banks `{humanize_list([bank.name for bank in banks])}`?"
            " Reply with `yes`/`no`."
        )
        pred = MessagePredicate.yes_or_no(ctx)
        try:
            await ctx.bot.wait_for("message", check=pred, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send("No response, aborting.")

        if pred.result:
            for bank in banks:
                bank._data = {}
            return await ctx.send(f"Given banks' donations have been reset.")

        else:
            return await ctx.send("Alright!")

    @bank.group(name="roles", invoke_without_command=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_role(self, ctx):
        """
        See or edit auto roles for a given bank"""
        await ctx.send_help()

    @bank_role.command(name="add")
    async def bank_role_add(
        self, ctx, bank: BankConverter, *, pairs: AmountRoleConverter
    ):
        """
        Add autoroles for a bank.

        The pairs argument should be in this format:
        `amount` `,` `multiple roles separated with a colon(:)`
        For example:
            `10000,someroleid:onemoreroleid 15k,@rolemention 20e4,arolename`"""
        cat_roles = await bank.getroles(ctx)

        for k, v in pairs.items():
            k = str(k)
            r = cat_roles.get(k)
            if not r:
                cat_roles.update({k: v})

            else:
                for role in v:
                    if role in r:
                        continue
                    r.append(role)

        await bank.setroles(cat_roles)

        embed = discord.Embed(
            title=f"Updated autoroles for {bank.name.title()}!", color=await ctx.embed_color()
        )
        rolelist = ""
        for key, value in cat_roles.items():
            rolelist += f"{humanize_list([role.name for role in value])} for {humanize_number(key)} donations\n"
        embed.description = f"`{rolelist}`"

        await ctx.send(embed=embed)

    @bank_role.command(name="remove")
    async def bank_role_remove(
        self, ctx, bank: BankConverter, *, pairs: AmountRoleConverter
    ):
        """
        Remove autoroles for a bank.

        The pairs argument should be in this format:
        `amount` `,` `multiple roles separated with a colon(:)`
        For example:
            `10000,someroleid:onemoreroleid 15k,@rolemention 20e4,arolename`"""
        cat_roles = await bank.getroles(ctx)

        for k, v in pairs.items():
            k = str(k)
            r = cat_roles.get(k)
            if not r:
                continue

            else:
                for role in v:
                    if role in r:
                        r.remove(role)

        await bank.setroles(cat_roles)

        embed = discord.Embed(
            title=f"Updated autoroles for {bank.name.title()}!", color=await ctx.embed_color()
        )
        rolelist = ""
        for key, value in cat_roles.items():
            rolelist += f"{humanize_list([role.name for role in value])} for {humanize_number(key)} donations\n"
        embed.description = f"`{rolelist}`"

        await ctx.send(embed=embed)

    @bank_role.command(name="list")
    async def bank_role_list(self, ctx: commands.Context, bank: BankConverter):
        """
        List autoroles for a bank."""
        cat_roles = await bank.getroles(ctx)
        if not cat_roles:
            return await ctx.send("No autoroles set for this bank.")

        tab = tabulate(
            [
                (humanize_number(key), humanize_list([role.name for role in value]))
                for key, value in cat_roles.items()
            ],
            ["Amount", "Roles"],
        )
        await ctx.send("Following autoroles are set for this bank:\n" + box(tab, lang="py"))
        
    @bank.command(name="hide")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_hide(self, ctx: commands.Context, *, bank: BankConverter):
        """
        Hide a bank from the `dono bal` command.
        """
        bank.hidden = True
        async with self.cache.config.guild(ctx.guild).banks() as cats:
            cats.get(bank.name).update({"hidden": True})
        await ctx.send(f"bank {bank.name} has been hidden.")
        
    @bank.command(name="unhide")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_unhide(self, ctx: commands.Context, *, bank: BankConverter):
        """
        Unhide a bank from the `dono bal` command."""
        bank.hidden = False
        async with self.cache.config.guild(ctx.guild).banks() as cats:
            cats.get(bank.name).update({"hidden": False})
            
        await ctx.send(f"bank {bank.name} has been unhidden.")
        
    @bank.command(name="emoji")
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def bank_emoji(self, ctx: commands.Context, bank: BankConverter, emoji: EmojiConverter):
        """
        Edit the emoji used for the bank.
        """
        bank.emoji = str(emoji)
        async with self.cache.config.guild(ctx.guild).banks() as cats:
            cats.get(bank.name).update({"emoji": str(emoji)})
        await ctx.send(f"bank {bank.name}'s emoji has been set to {emoji}.")

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

    @donoset.command(name="reset", hidden=True)
    @commands.mod_or_permissions(administrator=True)
    @setup_done()
    async def donoset_reset(self, ctx: commands.Context):
        """
        Completely reset you guild's settings.

        All your data will be removed and you will have to re-run the setup process.
        """
        await self.config.guild(ctx.guild).clear()
        await self.cache.clear_guild_settings(ctx.guild.id)
        return await ctx.send("Successfully reset your guild's settings.")

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
        banks = await self.cache.config.guild(ctx.guild).banks()
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
            name="banks: ",
            value=f"{len(banks)} banks: `{humanize_list(list(banks.keys()))}`",
            inline=False,
        )
        await ctx.send(embed=embed)
