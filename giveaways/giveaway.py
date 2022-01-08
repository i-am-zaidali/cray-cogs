import asyncio
import contextlib
import datetime
import time as _time
import typing

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta, pagify, warning
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

from .gset import gsettings, log
from .models import EndedGiveaway, Giveaway, PendingGiveaway, Requirements, SafeMember
from .util import (
    Coordinate,
    Flags,
    GiveawayMessageConverter,
    TimeConverter,
    WinnerConverter,
    ask_for_answers,
    channel_conv,
    datetime_conv,
    flags_conv,
    group_embeds_by_fields,
    is_gwmanager,
    is_lt,
    prizeconverter,
    requirement_conv,
)


class giveaways(gsettings, name="Giveaways"):
    """
    Host embed and reactions based giveaways in your server
    with advanced requirements, customizable embeds
    and much more."""

    __version__ = "1.7.5"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot):
        self.converter = GiveawayMessageConverter()
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

    async def get_embed_color(self, ctx: commands.Context) -> discord.Color:
        if not (color := await self.config.get_guild(ctx.guild, "color")):
            return await ctx.embed_color()
        return discord.Color(color)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        if ctx.command.qualified_name.lower() in ["giveaway start", "giveaway create"]:
            async with self.config.config.guild(ctx.guild).top_managers() as top:
                top.setdefault(str(ctx.author.id), 0)
                top[str(ctx.author.id)] += 1

    @commands.group(name="giveaway", aliases=["g"], invoke_without_command=True)
    @commands.guild_only()
    async def giveaway(self, ctx):
        """
        Base command for giveaway controls.

        Use given subcommands to start new giveaways,
        end all (or one) giveaway and reroll ended giveaways.
        """
        await ctx.send_help("giveaway")

    @giveaway.command(name="create")
    @commands.max_concurrency(5, per=commands.BucketType.guild, wait=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    @is_gwmanager()
    async def giveaway_create(self, ctx: commands.Context):
        """
        Start an interaction step by step questionnaire to create a new giveaway.
        """

        async def _prize(m):
            return m.content

        await ctx.send(
            "The giveaway creation process will start now. If you ever wanna quit just send a `cancel` to end the process."
        )
        await asyncio.sleep(3)  # delay the questionnaire so people can read the above message
        questions = [
            (
                "What is the prize for this giveaway?",
                "The prize can be multi worded and can have emojis.\nThis prize will be the embed title.",
                "prize",
                _prize,
            ),
            (
                "How many winners will there be?",
                "The number of winners must be a number less than 20.",
                "winners",
                is_lt(20),
            ),
            (
                "How long/Until when will the giveaway last?",
                "Either send a duration like `1m 45s` (1 minute 45 seconds)\nor a date/time with your timezone like `30 december 2021 1 pm UTC`.",
                "time",
                datetime_conv(ctx),
            ),
            (
                "Are there any requirements to join this giveaways?",
                "These requirements will be in the format explained in `[p]giveaway explain`.\nIf there are none, just send `None`.",
                "requirements",
                requirement_conv(ctx),
            ),
            (
                "What channel will this giveaway be hosted in?",
                "This can be a channel mention or channel ID.",
                "channel",
                channel_conv(ctx),
            ),
            (
                "Do you want to pass flags to this giveaways?",
                "Send the flags you want to associate to this giveaway. Send `None` if you don't want to use any.",
                "flags",
                flags_conv(ctx),
            ),
        ]

        final = await ask_for_answers(ctx, questions, 45)

        if not final:
            return

        time = final.get("time", 30)
        winners = final.get("winners", 1)
        requirements = final.get("requirements")
        prize = final.get("prize", "A new giveaway").split()
        flags = final.get("flags", {})
        channel = final.get("channel", None)
        if channel:
            flags.update({"channel": channel})
            await ctx.send("Successfully created giveaway in channel `{}`.".format(channel))

        start = ctx.bot.get_command("giveaway start")
        await ctx.invoke(
            start, prize=prize, winners=winners, time=time, requirements=requirements, flags=flags
        )  # Lmao no more handling :p

    @giveaway.command(name="start", usage="[time] <winners> [requirements] <prize> [flags]")
    @commands.max_concurrency(5, per=commands.BucketType.guild, wait=True)
    @commands.bot_has_permissions(embed_links=True)
    @commands.guild_only()
    @is_gwmanager()
    async def _start(
        self,
        ctx: commands.Context,
        time: typing.Optional[TimeConverter] = None,
        winners: WinnerConverter = None,
        requirements: typing.Optional[Requirements] = None,
        prize: commands.Greedy[prizeconverter] = None,
        *,
        flags: Flags = {},
    ):
        """Start a giveaway with a prize

        The time argument is optional, you can instead use the `--ends-at` flag to
        specify a more accurate time span.

        Requires a manager role set with `[p]gset manager` or
        The bot mod role set with `[p]set addmodrole`
        or manage messages permissions.

        Use `[p]g create` instead if you want a step by step process.

        Example:
            `[p]g start 30s 1 my soul`
            `[p]g start 5m 1 someroleid;;another_role[bypass];;onemore[blacklist] Yayyyy new giveaway`
            `[p]giveaway start 1 this giveaway has no time argument --ends-at 30 december 2021 1 pm UTC --msg but has the `--ends-at` flag`
        """
        if winners is None or not prize:
            return await ctx.send_help("giveaway start")

        if not time and not flags.get("ends_at"):
            return await ctx.send(
                "If you dont pass `<time>` in the command invocation, you must pass the `--ends-at` flag.\nSee `[p]giveaway explain` for more info."
            )

        elif flags.get("ends_at"):
            time = flags.get("ends_at")

        if not requirements:
            requirements = await Requirements.convert(
                ctx, "none"
            )  # requirements weren't provided, they are now null

        if not ctx.channel.permissions_for(ctx.me).manage_messages and not requirements.null:
            await ctx.send(
                warning(
                    "I will not be able to enforce the requirements "
                    "on the giveaway since I am missing the `Manage Messages` permission. "
                    "But the giveaway will start as intended."
                )
            )

        prize = " ".join(prize)

        if not getattr(self, "amari", None):  # amari token wasn't available.
            requirements.no_amari_available()  # cancel out amari reqs if they were given.

        if time < 15:
            return await ctx.reply("Giveaways have to be longer than 15 seconds.")

        if await self.config.get_guild_autodel(ctx.guild):
            with contextlib.suppress(Exception):
                await ctx.message.delete()

        messagable: discord.TextChannel = ctx.channel
        if channel := flags.get("channel"):
            messagable = channel

        if start_in := flags.get("starts_in"):
            flags.update({"channel": messagable.id})
            pg = PendingGiveaway(
                ctx.bot,
                self,
                ctx.author.id,
                int(start_in + time),
                winners,
                requirements,
                prize,
                flags,
            )
            self.pending_cache.append(pg)
            return await ctx.send(f"Giveaway for `{pg.prize}` will start in <t:{pg.start}:R>")

        emoji = await self.config.get_guild_emoji(ctx.guild)
        endtime = ctx.message.created_at + datetime.timedelta(seconds=time)

        embed = discord.Embed(
            title=prize.center(len(prize) + 4, "*"),
            description=(
                f"React with {emoji} to enter\n"
                f"Host: {ctx.author.mention}\n"
                f"Ends {f'<t:{int(_time.time()+time)}:R>' if not await self.config.get_guild_timer(ctx.guild) else f'in {humanize_timedelta(seconds=time)}'}\n"
            ),
            timestamp=endtime,
            color=await self.get_embed_color(ctx),
        ).set_footer(text=f"Winners: {winners} | ends : ", icon_url=ctx.guild.icon_url)

        message = await self.config.get_guild_msg(ctx.guild)

        # flag handling below!!

        if donor := flags.get("donor"):
            embed.add_field(name="**Donor:**", value=f"{donor.mention}", inline=False)
        ping = flags.get("ping")
        no_multi = flags.get("no_multi")
        no_defaults = flags.get("no_defaults")
        donor_join = not flags.get("no_donor")
        msg = flags.get("msg")
        thank = flags.get("thank")
        message_count = flags.get("message_count", 0)
        message_cooldown = flags.get("message_cooldown", 0)
        if no_defaults:
            requirements = requirements.no_defaults(True)  # ignore defaults.

        if not no_defaults:
            requirements = requirements.no_defaults()  # defaults will be used!!!

        if message_count != 0:
            requirements.messages = message_count

        req_str = await requirements.get_str(ctx)
        if not requirements.null and not req_str == "":
            embed.add_field(name="Requirements:", value=req_str, inline=False)

        gembed = await messagable.send(message, embed=embed)
        await gembed.add_reaction(emoji)

        if ping:
            pingrole = await self.config.get_pingrole(ctx.guild)
            ping = (
                pingrole.mention
                if pingrole
                else f"No pingrole set. Use `{ctx.prefix}gset pingrole` to add a pingrole"
            )

        if msg and ping:
            membed = discord.Embed(
                description=f"***Message***: {msg}", color=await self.get_embed_color(ctx)
            )
            await messagable.send(
                ping, embed=membed, allowed_mentions=discord.AllowedMentions(roles=True)
            )
        elif ping and not msg:
            await messagable.send(ping, allowed_mentions=discord.AllowedMentions(roles=True))
        elif msg and not ping:
            membed = discord.Embed(
                description=f"***Message***: {msg}", color=await self.get_embed_color(ctx)
            )
            await messagable.send(embed=membed)
        if thank:
            tmsg: str = await self.config.get_guild_tmsg(ctx.guild)
            embed = discord.Embed(
                description=tmsg.format_map(
                    Coordinate(
                        donor=SafeMember(donor or ctx.author),
                        prize=prize,
                    )
                ),
                color=await self.get_embed_color(ctx),
            )
            await messagable.send(embed=embed)

        data = {
            "donor": donor.id if donor else None,
            "donor_can_join": donor_join,
            "use_multi": not no_multi,
            "message": gembed.id,
            "emoji": emoji,
            "channel": messagable.id,
            "cog": self,
            "time": _time.time() + time,
            "winners": winners,
            "requirements": requirements,
            "prize": prize,
            "host": ctx.author.id,
            "bot": self.bot,
            "message_cooldown": message_cooldown,
        }
        giveaway = Giveaway(**data)
        self.giveaway_cache.append(giveaway)
        log.info(
            f"{ctx.author} created a giveaway for {prize} with {winners} winners in channel: {messagable.name} (guild: {messagable.guild})."
        )

    async def message_reply(self, message: discord.Message) -> discord.Message:
        if not message.reference:
            return

        try:
            return await message.channel.fetch_message(message.reference.message_id)

        except:
            return message.reference.resolved

    async def giveaway_from_message_reply(self, ctx):
        msg = await self.message_reply(ctx.message)

        if msg:
            try:
                msg = await self.converter.convert(ctx, str(msg.id))
            except Exception as e:
                print(e)
                msg = None

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

        activegaw = self.giveaway_cache.copy()
        if not activegaw:
            return await ctx.send("There are no active giveaways.")
        gmsg = giveaway_id
        if await self.config.get_guild_autodel(ctx.guild):
            await ctx.message.delete()
        if gmsg:
            if not isinstance(gmsg, str):
                try:
                    gmsg = await self.converter.convert(ctx, str(gmsg.id))
                except Exception as e:
                    return await ctx.send(f"{e}")

                await ctx.tick()
                if isinstance(gmsg, Giveaway):
                    await gmsg.end(ctx.author)
                else:
                    await ctx.send("That giveaway has already ended tho.")
                return

            else:
                msg = await ctx.send(
                    "Are you sure you want to end all giveaways in your server? This action is irreversible."
                )
                await start_adding_reactions(msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(msg, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=30)
                except asyncio.TimeoutError:
                    return await ctx.send("No thank you for wasting my time :/")

                if pred.result:
                    active, failed = await self.get_active_giveaways(ctx.guild)
                    for i in active:
                        await i.end(canceller=ctx.author)
                    return await ctx.send("All giveaways have been ended.")

                else:
                    return await ctx.send(
                        "Thanks for saving me from all that hard work lmao :weary:"
                    )

        else:
            message = await self.giveaway_from_message_reply(ctx)
            if not message:
                return await ctx.send(
                    "You either didn't reply to a message or the replied message isn't a giveaway."
                )

            if isinstance(message, Giveaway):
                await ctx.tick()
                await message.end(ctx.author)
            else:
                await ctx.send("That giveaway seems to have ended already.")

    @giveaway.command(name="reroll")
    @is_gwmanager()
    @commands.guild_only()
    async def reroll(
        self,
        ctx: commands.Context,
        giveaway_id: typing.Optional[discord.Message] = None,
        winners: WinnerConverter = 1,
    ):
        """Reroll the winners of a giveaway

        This requires for the giveaway to already have ended.
        This will select new winners for the giveaway.

        You can also reply to the giveaway message instead of passing its id.

        [winners] is the amount of winners to pick. Defaults to 1"""
        gmsg = giveaway_id
        if await self.config.get_guild_autodel(ctx.guild):
            await ctx.message.delete()

        if not self.ended_cache:
            return await ctx.send(
                "The ended giveaways cache seems to be empty. Wait for a giveaway to end before rerolling it LOL."
            )
        if gmsg:
            try:
                gmsg = await self.converter.convert(ctx, str(gmsg.id))

            except Exception as e:
                return await ctx.send(e)

        else:
            gmsg = await self.giveaway_from_message_reply(ctx)
            if not gmsg:
                return await ctx.send_help()

        if not isinstance(gmsg, EndedGiveaway):
            return await ctx.send(
                "That giveaway hasn't ended yet. Wait for it to end before rerolling it."
            )

        await gmsg.reroll(ctx, winners)

    @giveaway.command(name="clear", hidden=True)
    @commands.is_owner()
    async def clear(self, ctx):
        """
        Clear the giveaway cache in the bot.

        This will abandon all ongoing giveaways and leave them as is"""
        self.giveaway_cache.clear()

        await ctx.send("Cleared all giveaway data.")

    @giveaway.command(name="list", usage="")
    @commands.cooldown(1, 30, commands.BucketType.member)
    @commands.max_concurrency(3, commands.BucketType.default, wait=True)
    @commands.bot_has_permissions(embed_links=True)
    async def glist(self, ctx: commands.Context, globally: bool = False):
        """
        See a list of active giveaway in your server.

        This can be a pretty laggy command and can take a while to show the results so please have patience."""
        if globally and not ctx.author.id in ctx.bot.owner_ids:
            return await ctx.send("That option is for bot owners only.")

        if not self.giveaway_cache:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("No active giveaways currently")

        active, failed = await self.get_active_giveaways(ctx.guild if not globally else None)
        if not active:
            return await ctx.send("There are no active giveaways in this server.")

        fields = []
        for i in active:
            value = (
                f"***[{i.prize}]({(await i.get_message()).jump_url})***\n"
                f"> Guild: **{i.guild}**\n"
                f"> Host: **{i.host}**\n"
                f"> Message id: **{i.message_id}**\n"
                f"> Amount of winners: **{i.winners}**\n"
                f"> Ends in: **{humanize_timedelta(seconds=i.remaining_time)}**\n"
            )
            fields.append({"name": "\u200b", "value": value, "inline": False})

        if failed:
            for i in failed:
                value = (
                    f"***{i.prize}***\n"
                    f"> Guild: **{i.guild}**\n"
                    f"> Host: **{i.host}**\n"
                    f"> Message id: **{i.message_id}**\n"
                    f"> Amount of winners: **{i.winners}**\n"
                    f"> Reason for failure: {i.reason}"
                )

                fields.append({"name": "\u200b", "value": value, "inline": False})

        embeds = group_embeds_by_fields(
            *fields,
            per_embed=5,
            title=f"Active giveaways in **{ctx.guild.name}**"
            if not globally
            else "Active giveaways **globally**",
            color=await self.get_embed_color(ctx),
        )

        embeds = [
            embed.set_footer(text=f"Page {embeds.index(embed)+1}/{len(embeds)}").set_thumbnail(
                url=ctx.guild.icon_url if not globally else ctx.bot.user.avatar_url
            )
            for embed in embeds
        ]

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @giveaway.command(name="show")
    @commands.bot_has_permissions(embed_links=True)
    async def gshow(self, ctx: commands.Context, giveaway: discord.Message = None):
        """
        See the details of a giveaway.

        The giveaway can be an ended giveaway or a curretly active one.
        You can also reply to a giveaway message to see its details instead of passing a message id."""
        if giveaway:
            try:
                gmsg = await self.converter.convert(ctx, str(giveaway.id))
            except Exception as e:
                return await ctx.send(e)

        else:
            gmsg = await self.giveaway_from_message_reply(ctx)
            if not gmsg:
                return await ctx.send_help()

        gmsg: typing.Union[Giveaway, EndedGiveaway]
        title = (
            f"***[{gmsg.prize}]({(await gmsg.get_message()).jump_url})***\n"
            if await gmsg.get_message()
            else f"***{gmsg.prize}***\n"
        )
        if isinstance(gmsg, EndedGiveaway):
            winners = typing.Counter(gmsg.winnerslist)  # too lazy for a separate import?
            if winners:
                winners = "".join([f"{k} x{v}\n" for k, v in winners.items()])
            else:
                winners = None
        details = (
            f"> Guild: **{gmsg.guild}**\n"
            + f"> Host: **{gmsg.host}**\n"
            + f"> Message id: **{gmsg.message_id}**\n"
            + f"> Amount of winners: **{gmsg.winners}**\n"
            + (
                f"> Donor: **{gmsg.donor}**\n"
                if isinstance(gmsg, Giveaway)
                else f"> Reasion for ending:\n> **{gmsg.reason}**\n"
            )
            + (
                f"> Ends in: **{humanize_timedelta(seconds=gmsg.remaining_time)}**\n"
                if isinstance(gmsg, Giveaway)
                else f"> Winners: {winners}"
            )
        )

        embed = discord.Embed(
            title="Giveaway details!", color=await self.get_embed_color(ctx)
        ).add_field(name="\u200b", value=title + details, inline=False)

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
        something = (
            f"""
***__Basics:__ ***
    > You can host giveaways with the bot. What this is,
    > is that the bot sends an embed containing information such as the prize,
    > the amount of winners, the requirements and the time it ends.

    > People have to react to an emoji set by you through the `{ctx.prefix}gset emoji` command (defaults to :tada: )
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

    > The format to specify a requirements is as follows:

    > `argument[requirements_type]`

    > The requirements_type are below with their argument types specified in () brackets:
        • required (role)
        `The role required for the giveaway`

        • blacklist (role)
        `The role blacklisted from the giveaway`

        • bypass (role)
        `The role that bypasses the requirements`

        • amari level (number)
        `The minimum AmariBot level required for the giveaway`

        • amari weekly (number)
        `The minimum weekly AmariBot XP required for the giveaway`

        • messages (number)
        `The minimum amount of messages sent by the user after the giveaway started`

    > For the required roles, you dont need to use brackets. You can just type a role and it will work.

    > For example, we want a role `rolename` to be required and a role `anotherrole` to be blacklisted.
    > This is how the requirements string will be constructed:
    > `rolename;;anotherrole[blacklist]`

    > Same way if we want amari level and weekly xp requirements, here is what we would do:
    > `10[alevel];;200[aweekly]` Now the giveaway will require 10 amari elvel **AND** 200 amari weekly xp.

    > Here's another more complicated example:

    >    **{ctx.prefix}g start 1h30m 1 somerolemention[bypass];;123456789[blacklist];;12[alvl]**

    ***NOTE***:
        Bypass overrides blacklist, so users with even one bypass role specified
        will be able to join the giveaway regardless of the blacklist.

***__Flags:__ ***
    > Flags are extra arguments passed to the giveaway command to modify it.
    > Flags should be prefixed with `--` (two minus signs?)
    > Flags require you to provide an argument after them unless they are marked as `[argless]`.
    > Then tou som't have to provide anything ans you can just type the flag and get on with it.

    **Types of flags**
    > *--no-multi* [argless]
        This flag will disallow role multipliers to determine the giveaway winner.

    > *--donor*
        This sets a donor for the giveaway. This donor name shows up in the giveaway embed and also is used when using the `--amt` flag

    > *--no-donor* [argless]
        This flag will disallow the donor (if given, else the host) to win the giveaway.

    > *--msg*
        This sends a separate embed after the main giveaway one stating a message give by you.

    > *--ping* [argless]
        This flag pings the set role. ({ctx.prefix}gset pingrole)

    > *--thank* [argless]
        This flag also sends a separate embed with a message thanking the donor. The message can be changed with `{ctx.prefix}gset tmsg`

    > *--no-defaults* [argless]
        This disables the default bypass and blacklist roles set by you with the `{ctx.prefix}gset blacklist` and `{ctx.prefix}gset bypass`

    > *--ends-at*/*--end-in*
        This flag allows you to pass a date/time to end the giveaway at or just a duration. This will override the duration you give in the command invocation.
        You can provide your time zone here for more accurate end times but if you don't, it will default to UTC.

    > *--starts-at*/*--start-in*
        This flag delays the giveaway from starting until your given date/time.
        This is useful if you want to start a giveaway at a specific time but you aren't available.

    > *--channel*/*--chan*
        This redirects the giveaway to the provided channel after the flag.

    > *--messages*/*--msgs*
        This sets the minimum amount of messages a user must send after the giveaway to join. This will override the requirement if passed.

    > *--cooldown*
        This adds a cooldown to the message tracking for the requirement.
        This is useful if people will spam messages to fulfil the requirements.
"""
            + (
                """
    > *--amt*
        This adds the given amount to the donor's (or the command author if donor is not provided) donation balance.

    > *--bank* or *--category*
        This flag followed with a category name, uses the given category to to add the amount to.
        If not given, the default category, if set, will be used.
        This flag can not be used without using the *--amt* flag.
"""
                if self.bot.get_cog("DonationLogging")
                else ""
            )
            + """

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

    > **Show defaults in giveaway embed**
        It gets kinda janky when you ahve multiple defaults set and the giveaway embed becomes too long.
        Easy way out, is to simply disable showing the defaults in the embed ;) `{ctx.prefix}gset showdefaults`

    > **Embed Color**
        The default embed color doesn't look good to you? now worries, you can now customize the color for your server.
        `{ctx.prefix}gset color`
        """
        )
        pages = list(pagify(something, delims=["\n***"], page_length=2800))
        for page in pages:
            embed = discord.Embed(title="Giveaway Explanation!", description=page, color=0x303036)
            embed.set_footer(text=f"Page {pages.index(page) + 1} out of {len(pages)}")
            embeds.append(embed)

        await menu(ctx, embeds, DEFAULT_CONTROLS)
