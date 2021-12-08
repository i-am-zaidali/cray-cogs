import asyncio
import contextlib
import datetime
import logging
import random
import time as _time
import typing

import discord
from discord.ext.commands.converter import MemberConverter
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .gset import gsettings
from .models import Giveaway, Requirements, SafeMember
from .util import (
    TimeConverter,
    WinnerConverter,
    flags,
    is_gwmanager,
    prizeconverter,
    readabletimer,
)

log = logging.getLogger("red.ashcogs.giveaways")


class Coordinate(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class giveaways(gsettings, name="Giveaways"):
    """
    Host embed and reactions based giveaways in your server
    with advanced requirements, customizable embeds
    and much more."""

    __version__ = "1.3.1"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot):
        super().__init__(bot)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        if not self.giveaway_cache:
            return
        for i in self.giveaway_cache.copy():
            if i.host.id == user_id:
                self.giveaway_cache.remove(i)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if ctx.command.qualified_name.lower() == "giveaway start":
            async with self.config.config.guild(ctx.guild).top_managers() as top:
                top[str(ctx.author.id)] = (
                    1 if not str(ctx.author.id) in top else top[str(ctx.author.id)] + 1
                )

    @commands.group(name="giveaway", aliases=["g"], invoke_without_command=True)
    @commands.guild_only()
    async def giveaway(self, ctx):
        """
        Base command for giveaway controls.

        Use given subcommands to start new giveaways,
        end all (or one) giveaway and reroll ended giveaways.
        """
        await ctx.send_help("giveaway")

    @giveaway.command(name="start", usage="<time> <winners> [requirements] <prize> [flags]")
    @commands.max_concurrency(5, per=commands.BucketType.guild, wait=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    @is_gwmanager()
    async def _start(
        self,
        ctx: commands.Context,
        time: TimeConverter = None,
        winners: WinnerConverter = None,
        requirements: typing.Optional[Requirements] = None,
        prize: commands.Greedy[prizeconverter] = None,
        *,
        flags: flags = None,
    ):
        """Start a giveaway in the current channel with a prize

        Requires a manager role set with `[p]gset manager` or
        The bot mod role set with `[p]set addmodrole`
        or manage messages permissions.

        Example:
            `[p]g start 30s 1 my soul`
            `[p]g start 5m 1 someroleid;;another_role[bypass];;onemore[blacklist] Yayyyy new giveaway`
        """
        if not time or winners is None or not prize:
            return await ctx.send_help("giveaway start")

        if not requirements:
            requirements = await Requirements.convert(
                ctx, "none"
            )  # requirements weren't provided, they are now null

        prize = " ".join(prize)

        if not getattr(self, "amari", None):  # amari token wasn't available.
            requirements.no_amari_available()  # cancel out amari reqs if they were given.

        if time < 15:
            return await ctx.reply("Giveaways have to be longer than 15 seconds.")

        if await self.config.get_guild_autodel(ctx.guild):
            with contextlib.suppress(Exception):
                await ctx.message.delete()

        emoji = await self.config.get_guild_emoji(ctx.guild)
        endtime = ctx.message.created_at + datetime.timedelta(seconds=time)

        embed = discord.Embed(
            title=prize.center(len(prize) + 4, "*"),
            description=(
                f"React with {emoji} to enter\n"
                f"Host: {ctx.author.mention}\n"
                f"Ends {f'<t:{int(_time.time())+time}:R>' if not await self.config.get_guild_timer(ctx.guild) else f'in {humanize_timedelta(seconds=time)}'}\n"
            ),
            timestamp=endtime,
        ).set_footer(text=f"Winners: {winners} | ends : ", icon_url=ctx.guild.icon_url)

        message = await self.config.get_guild_msg(ctx.guild)
        p = None
        if flags:
            donor = flags.get("donor")
            _list = flags.get(None)
            no_defaults = flags.get("no-defaults")
            if donor:
                donor = await MemberConverter().convert(ctx, donor)
                embed.add_field(name="**Donor:**", value=f"{donor.mention}", inline=False)
            if no_defaults or (_list and "no-defaults" in _list):
                requirements = requirements.no_defaults(True)

            else:
                requirements = requirements.no_defaults()

        if not requirements.null:
            embed.add_field(name="Requirements:", value=str(requirements), inline=False)

        gembed = await ctx.send(message, embed=embed)
        await gembed.add_reaction(emoji)
        if flags:
            msg = flags.get("msg")
            _list = flags.get(None)
            amt = flags.get("amt")
            bank = flags.get("bank") or flags.get("category")
            # await ctx.send(f"{flags}")

            if amt:
                cog: commands.Cog = self.bot.get_cog("DonationLogging")
                if cog:
                    command = ctx.bot.get_command("dono add")
                    if await command.can_run(ctx):
                        amt = await cog.conv(ctx, amt)
                        if bank:
                            try:
                                bank = await cog.cache.get_dono_bank(ctx.guild.id, bank)
                            except Exception as e:
                                bank = await cog.cache.get_default_category(ctx.guild.id)
                        mem = await MemberConverter().convert(ctx, donor) if donor else ctx.author
                        await ctx.invoke(command, category=bank, amount=amt, user=mem)

            if (_list and "ping" in _list) or "ping" in flags:
                pingrole = await self.config.get_pingrole(ctx.guild)
                p = (
                    pingrole.mention
                    if pingrole
                    else f"No pingrole set. Use `{ctx.prefix}gset pingrole` to add a pingrole"
                )

            if msg and p:
                membed = discord.Embed(
                    description=f"***Message***: {msg}", color=discord.Color.random()
                )
                await ctx.send(
                    p, embed=membed, allowed_mentions=discord.AllowedMentions(roles=True)
                )
            elif p and not msg:
                await ctx.send(p)
            elif msg and not p:
                membed = discord.Embed(
                    description=f"***Message***: {msg}", color=discord.Color.random()
                )
                await ctx.send(embed=membed)
            if "thank" in flags or (_list and "thank" in _list):
                tmsg: str = await self.config.get_guild_tmsg(ctx.guild)
                embed = discord.Embed(
                    description=tmsg.format_map(
                        Coordinate(
                            donor=SafeMember(donor) if donor else SafeMember(ctx.author),
                            prize=prize,
                        )
                    ),
                    color=0x303036,
                )
                await ctx.send(embed=embed)

        data = {
            "message": gembed.id,
            "emoji": emoji,
            "channel": ctx.channel.id,
            "cog": self,
            "time": _time.time() + time,
            "winners": winners,
            "requirements": requirements,
            "prize": prize,
            "host": ctx.author.id,
            "bot": self.bot,
        }
        giveaway = Giveaway(**data)
        self.giveaway_cache.append(giveaway)

    async def message_reply(self, message: discord.Message) -> discord.Message:
        if not message.reference:
            return

        try:
            return await message.channel.fetch_message(message.reference.message_id)

        except:
            return message.reference.resolved

    async def giveaway_from_message_reply(self, message: discord.Message):
        msg = await self.message_reply(message)

        e = list(
            filter(
                lambda x: x.message_id == msg.id and x.guild == message.guild,
                self.giveaway_cache.copy(),
            )
        )
        if not e:
            return
        return msg

    @giveaway.command(name="end")
    @is_gwmanager()
    @commands.guild_only()
    async def end(
        self, ctx: commands.Context, giveaway_id: typing.Union[discord.Message, str] = None
    ):
        """End an ongoing giveaway prematurely.

        This will end the giveaway before its original time.
        You can also reply to the giveaway message instead of passing its id"""
        gmsg = giveaway_id or await self.giveaway_from_message_reply(ctx.message)
        if not gmsg:
            return await ctx.send_help("giveaway end")
        activegaw = self.giveaway_cache.copy()
        if not activegaw:
            return await ctx.send("There are no active giveaways.")

        if await self.config.get_guild_autodel(ctx.guild):
            await ctx.message.delete()

        if isinstance(gmsg, str) and gmsg.lower() == "all":
            msg = await ctx.send(
                "Are you sure you want to end all giveaways in your server? This action is irreversible."
            )
            start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(msg, ctx.author)
            try:
                await self.bot.wait_for("reaction_add", check=pred, timeout=30)
            except asyncio.TimeoutError:
                return await ctx.send("No thank you for wasting my time :/")

            if pred.result:
                for i in activegaw.copy():
                    if i.guild == ctx.guild:
                        await i.end()
                return await ctx.send("All giveaways have been ended.")

            else:
                return await ctx.send("Thanks for saving me from all that hard work lmao :weary:")

        e = list(filter(lambda x: x.message_id == gmsg.id and x.guild == ctx.guild, activegaw))
        if len(e) == 0:
            return await ctx.send("There is no active giveaway with that ID.")

        else:
            await e[0].end()

    @giveaway.command(name="reroll")
    @is_gwmanager()
    @commands.guild_only()
    async def reroll(self, ctx, giveaway_id: discord.Message = None, winners: WinnerConverter = 1):
        """Reroll the winners of a giveaway

        This requires for the giveaway to already have ended.
        This will select new winners for the giveaway.

        You can also reply to the giveaway message instead of passing its id.

        [winners] is the amount of winners to pick. Defaults to 1"""
        gmsg = giveaway_id or await self.message_reply(ctx.message)
        if not gmsg:
            return await ctx.send_help("giveaway reroll")

        if e := list(
            filter(
                lambda x: x.message_id == gmsg.id and x.guild == ctx.guild,
                self.giveaway_cache.copy(),
            )
        ):
            return await ctx.send(
                "That giveaway is currently active. Can't reroll an already active giveaway."
            )

        if await self.config.get_guild_autodel(ctx.guild):
            await ctx.message.delete()

        entrants = await gmsg.reactions[0].users().flatten()
        try:
            entrants.pop(entrants.index(ctx.guild.me))
        except:
            pass
        entrants = await self.config.get_list_multi(ctx.guild, entrants)
        link = gmsg.jump_url

        if winners == 0:
            return await ctx.reply("You cant have 0 winners for a giveaway 🤦‍♂️")

        if len(entrants) == 0:
            await gmsg.reply(
                f"There weren't enough entrants to determine a winner.\nClick on my replied message to jump to the giveaway."
            )
            return

        winner = [random.choice(entrants).mention for i in range(winners)]

        await gmsg.reply(
            f"Congratulations :tada:{humanize_list(winner)}:tada:. You are the new winners for the giveaway below.\n{link}"
        )

    @giveaway.command(name="clear", hidden=True)
    @commands.is_owner()
    async def clear(self, ctx):
        """
        Clear the giveaway cache in the bot.

        This will abandon all ongoing giveaways and leave them as is"""
        self.giveaway_cache.clear()

        await ctx.send("Cleared all giveaway data.")

    async def active_giveaways(self, ctx, per_guild: bool = False):
        data = self.giveaway_cache.copy()
        failed = []
        final = ""
        for index, i in enumerate(data, 1):
            channel = i.channel
            if per_guild and i.guild != ctx.guild:
                continue

            try:
                final += f"""
    {index}. **[{i.prize}]({(await i.get_message()).jump_url})**
    Hosted by <@{i.host.id}> with {i.winners} winners(s)
    in {f'guild {i.guild} ({i.guild.id})' if not per_guild else f'{channel.mention}'}
    Ends <t:{int(i._time)}:R> ({humanize_timedelta(seconds=i.remaining_time)})
    """
            except:
                failed.append(i)
                self.giveaway_cache.remove(i)
                continue

        return final, failed

    @giveaway.command(name="list")
    @commands.cooldown(1, 30, commands.BucketType.guild)
    @commands.max_concurrency(3, commands.BucketType.default, wait=True)
    @commands.bot_has_permissions(embed_links=True)
    async def glist(self, ctx: commands.Context):
        """
        See a list of active giveaway in your server.

        This is a pretty laggy command and can take a while to show the results so please have patience."""
        data = self.giveaway_cache.copy()
        if not data:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("No active giveaways currently")

        embeds = []
        final, failed = await self.active_giveaways(ctx, per_guild=True)

        for page in pagify(final, page_length=2048):
            embed = discord.Embed(
                title="Currently Active Giveaways!", color=discord.Color.blurple()
            )
            embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
            embed.description = page
            embeds.append(embed)

        if embeds:
            embeds = [
                embed.set_footer(text=f"Page {embeds.index(embed)+1}/{len(embeds)}")
                for embed in embeds
            ]

            if len(embeds) == 1:
                return await ctx.send(embed=embeds[0])
            else:
                await menu(ctx, embeds, DEFAULT_CONTROLS)

        else:
            await ctx.send("No active giveaways in this server.")

        if failed:
            log.warning(
                f"Following giveaway messages weren't found, removing them from database\n{failed}"
            )

    @giveaway.command(name="show")
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def gshow(self, ctx, giveaway: discord.Message = None):
        """
        Shows all active giveaways in all servers.
        You can also check details for a single giveaway by passing a message id.

        This commands is for owners only."""
        data = self.giveaway_cache.copy()
        if not data:
            return await ctx.send("No active giveaways currently")
        if not giveaway and not self.giveaway_from_message_reply(ctx.message):

            embeds = []
            final, failed = await self.active_giveaways(ctx)
            for page in pagify(final, page_length=2048):
                embed = discord.Embed(
                    title="Currently Active Giveaways!", color=discord.Color.blurple()
                )
                embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
                embed.description = page
                embeds.append(embed)

            if failed:
                failed = "\n".join(failed)
                log.warning(
                    f"Following giveaway messages weren't found, removing them from database\n{failed}"
                )

            if embeds:
                embeds = [
                    embed.set_footer(text=f"Page {embeds.index(embed)+1}/{len(embeds)}")
                    for embed in embeds
                ]

                if len(embeds) == 1:
                    return await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)

        else:
            gaw = list(filter(lambda x: x.message_id == giveaway.id, data))
            if not gaw:
                return await ctx.send("not a valid giveaway.")

            else:
                gaw = gaw[0]
                channel = gaw["channel"]
                host = gaw["host"]
                requirements = gaw["requirements"]
                prize = gaw["prize"]
                winners = gaw["winners"]
                endsat = gaw.remaining_time
                endsat = humanize_timedelta(seconds=endsat)
                embed = discord.Embed(title="Giveaway Details: ")
                embed.description = f"""
Giveaway Channel: {channel.mention} (`{channel.name}`)
Host: {host} (<@!{host}>)
Requirements: {requirements}
prize: {prize}
Amount of winners: {winners}
Ends at: {endsat}
				"""
                embed.set_thumbnail(url=channel.guild.icon_url)

                await ctx.send(embed=embed)

    @giveaway.command(name="top")
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.bot_has_permissions(embed_links=True)
    async def top_mgrs(self, ctx):
        """
        See the users who have performed the most giveaways in your server.
        """
        async with self.config.config.guild(ctx.guild).top_managers() as top:
            if not top:
                return await ctx.send("No giveaways performed here in this server yet.")

            _sorted = {k: v for k, v in sorted(top.items(), key=lambda i: i[1], reverse=True)}

            embed = discord.Embed(
                title=f"Top giveaway managers in **{ctx.guild.name}**",
                description="\n".join(
                    [f"<@{k}> : {v} giveaway(s) performed." for k, v in _sorted.items()]
                ),
            )
            embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
            return await ctx.send(embed=embed)

    @giveaway.command(name="explain")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @commands.bot_has_permissions(embed_links=True)
    async def gexplain(self, ctx):
        """Start a paginated embeds session explaining how
        to use the commands of this cog and how it works."""
        embeds = []
        something = f"""
***__Basics:__ ***
    > You can host giveaways with the bot. What this is,
    > is that the bot sends an embed containing information such as the prize,
    > the amount of winners, the requirements and the time it ends.

    > People have to react to an emoji set by you through the `{ctx.prefix}gset emoji` command
    > and after the time to end has come for the giveaway to end, the bot will choose winners from the list of
    > people who reacted and send their mentions in the channel and edit the original embedded message.

    > You can also set multipliers for roles which increase the chances of people with that role to win in a giveaway. `{ctx.prefix}gset multi`
    > These multipliers stack and a user's entries in a giveaway add up for each role multiplier they have.
    > The format to add multis is:
        `{ctx.prefix}gset multi add <role id or mention> <multi>`
    > And to remove is the same:
        `{ctx.prefix}gset multi remove <role id or mention>`

    > To see all active role multipliers:
        `{ctx.prefix}gset multi`

***__Requirements:__ ***
    > You can set requirements for the people who wish to join the giveaways.
    > These requirements can be either of role requirements or AmariBot level requirements.
    > Requirements are provided after the time and no. of winners like so:
        *{ctx.prefix}g start <time> <no. of winners> <requirements> <prize> [flags]*

    > The type of requirements is specified within square brackets `[]`.
    > For role requirements, you just use the role id, mention, or exact name.
    > But if you wanna set a role to be a bypass for the giveaway, you put the role and follow it with a `[bypass]` or `[blacklist]`

    > There are also ash level requirements based on ASH's levelling system. `{ctx.prefix}help Levelling`
    > These can be used with `[level]` or `[lvl]` brackets.

    > For Amari level requirements you do the same but `[level]` gets replaced with `[alevel]` or `[alvl]`
    > You can also have Amari weekly xp requirements, just use the level amount and use the `[aweekly]` brackets.

    For example:
        **{ctx.prefix}g start 1h30m 1 somerolemention[bypass];;123456789[blacklist];;12[alvl] [alevel]**

***__Flags:__ ***
    > Flags are extra arguments passed to the giveaway command to modify it.
    > Flags should be prefixed with `--` (two minus signs?)

    **Types of flags**
    > *--donor*
        This sets a donor for the giveaway. This donor name shows up in the giveaway embed and also is used when using the `--amt` flag

    > *--amt*
        This adds the given amount to the donor's (or the command author if donor is not provided) donation balance.
        **You need my DonationLogging cog for this to work.**

    > *--msg*
        This sends a separate embed after the main giveaway one stating a message give by you.

    > *--ping*
        This flag pings the set role. ({ctx.prefix}gset pingrole)

    > *--thank*
        This flag also sends a separate embed with a message thanking the donor. The message can be changed with `{ctx.prefix}gset tmsg`

    > *--no-defaults*
        This disables the default bypass and blacklist roles set by you with the `{ctx.prefix}gset blacklist` and `{ctx.prefix}gset bypass`

***__Customization:__ ***
    > Giveaways can be customized to your liking but under a certain limit.
    > There are a bunch of giveaway settings that you can change.

    > **Auto deletion of giveaway commands**
        You can set whether giveaway command invocations get deleted themselves or not. `{ctx.prefix}gset autodelete true`

    > **Giveaway headers**
        The message above the giveaway can also be changed. `{ctx.prefix}gset msg`

    > **Giveaway emoji**
        The emoji to which people must react to enter a giveaway. This defaults to :tada: but can be changed to anything. `{ctx.prefix}gset emoji`

    > **Giveaway pingrole**
        The role that gets pinged when you use the `--ping` flag. `{ctx.prefix}gset pingrole`

    > **Thank message**
        The message sent when you use the `--thank` flag. `{ctx.prefix}gset tmsg`

    > **Ending message**
        The message sent when the giveaway ends containing the winner mentions. `{ctx.prefix}gset endmsg`

    > **Default blacklist**
        The roles that are by default blacklisted from giveaways. `{ctx.prefix}gset blacklist`

    > **Default bypass**
        The roles that are by default able to bypass requirements in giveaways. `{ctx.prefix}gset bypass`
        """
        pages = list(pagify(something, delims=["\n***"], page_length=1200))
        for page in pages:
            embed = discord.Embed(title="Giveaway Explanation!", description=page, color=0x303036)
            embed.set_footer(text=f"Page {pages.index(page) + 1} out of {len(pages)}")
            embeds.append(embed)

        await menu(ctx, embeds, DEFAULT_CONTROLS)
