import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Union

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_timedelta, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .constants import commands_to_delete
from .converters import PrizeConverter, TimeConverter, WinnerConverter
from .models import (
    AmariClient,
    EndedGiveaway,
    Giveaway,
    GiveawayFlags,
    PaginationView,
    Requirements,
    YesOrNoView,
    get_guild_settings,
    model_from_time,
)
from .models.guildsettings import config as guildconf
from .utils import (
    ask_for_answers,
    channel_conv,
    datetime_conv,
    dict_keys_to,
    flags_conv,
    group_embeds_by_fields,
    is_lt,
    is_manager,
    requirement_conv,
)

log = logging.getLogger("red.craycogs.giveaways")


class Giveaways(commands.Cog):

    """
    Host embedded giveaways in your server with the help of reactions.

    This cog is a very complex cog and could be resource intensive on your bot.
    Use `giveaway explain` command for an indepth explanation on how to use the commands."""

    __version__ = "2.2.0"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(None, 1, True, "Giveaways")
        self.config.register_global(sent_message=False)
        self.config.init_custom("giveaway", 2)

        self._CACHE: Dict[int, Dict[int, Union[Giveaway, EndedGiveaway]]] = {}

        self.gs = get_guild_settings

    # < ----------------- Internal Private Methods ----------------- > #

    async def initialize(self):
        if not getattr(self.bot, "amari", None):
            keys = await self.bot.get_shared_api_tokens("amari")
            auth = keys.get("auth")
            if auth:
                amari = AmariClient(self.bot, auth)
                setattr(self.bot, "amari", amari)

            else:
                if not await self.config.sent_message():
                    await self.bot.send_to_owners(
                        "Thanks for installing and using my Giveaways cog. "
                        "This cog has a requirements system for the giveaways and one of "
                        "these requirements type is amari levels. "
                        "If you don't know what amari is, ignore this message. "
                        "But if u do, you need an Amari auth key for these to work, "
                        "go to this website: <https://forms.gle/TEZ3YbbMPMEWYuuMA> "
                        "and apply to get the key. You should probably get a response within "
                        "24 hours but if you don't, visit this server for information: https://discord.gg/6FJhupDHS6 "
                        "You can then set the amari api key with the `[p]set api amari auth,<api key>` command"
                    )
                    await self.config.sent_message.set(True)

        all = await self.config.custom("giveaway").all()
        all = await dict_keys_to(all)
        await self.bot.wait_until_red_ready()
        for guild_id, data in all.items():
            self._CACHE.setdefault(guild_id, {})
            for more_data in data.values():
                g = model_from_time(more_data.get("ends_at"))
                more_data.update(bot=self.bot)
                g = g.from_json(more_data)
                if (
                    isinstance(g, EndedGiveaway)
                    and (datetime.now(timezone.utc) - g.ended_at).days > 2
                    and g.duration < (5 * 60)
                ):
                    # if giveaway is over 2 days old and the duration is under 5 minutes, remove it from config
                    # no need for it to occupy space anyways.
                    await self.config.custom("giveaway").clear_raw(guild_id, g.message_id)
                    continue
                self.add_to_cache(g)

        self.end_giveaways_task = self.end_giveaway.start()

        self.bot.add_dev_env_value("giveaways", lambda x: self)

        return self

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        if not self._CACHE:
            return
        for guild_id, data in self._CACHE.copy().items():
            for msg_id, giveaway in data.items():
                if giveaway.host.id == user_id:
                    if isinstance(giveaway, Giveaway):
                        await giveaway.end(
                            reason=f"Host ({giveaway.host}) requested to delete their data so the giveaway was ended."
                        )

                    self._CACHE[guild_id].pop(msg_id)
                    self.config.custom("giveaway").clear_raw(guild_id, msg_id)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    def add_to_cache(self, giveaway: Union[Giveaway, EndedGiveaway]):
        e = self._CACHE.setdefault(giveaway.guild_id, {})
        e[giveaway.message_id] = giveaway

    def remove_from_cache(self, giveaway: Union[Giveaway, EndedGiveaway]):
        guild = self._CACHE.get(giveaway.guild_id)
        try:
            return guild.pop(giveaway.message_id)

        except:
            return

    async def to_config(self, unload=False):
        try:
            copy = self._CACHE.copy()
            for guild_id, data in copy.items():
                for message_id, giveaway in data.items():
                    json = giveaway.json

                    await self.config.custom("giveaway", guild_id, message_id).set(json)

            log.debug("Saved cache to config!")
            if unload:
                self._CACHE.clear()

        except Exception as e:
            log.exception("Exception occurred when backing up cache: ", exc_info=e)

    async def message_from_reply(self, message: discord.Message):
        if not message.reference:
            return

        reply = message.reference.resolved
        return reply

    def _handle_starts_in(self, time: datetime, start_in: datetime):
        _t = time - datetime.now(timezone.utc)
        time_to_end = start_in + _t
        return time_to_end

    def cog_unload(self):
        self.bot.loop.create_task(self.to_config(True))
        self.end_giveaways_task.cancel()
        self.bot.remove_dev_env_value("giveaways")
        if getattr(self.bot, "amari", None):
            self.bot.loop.create_task(self.bot.amari.close())
            delattr(self.bot, "amari")
        for i in Giveaway._tasks:
            i.cancel()  # cancel all running tasks

        self.giveaway_view.stop()

    # < ----------------- Giveaway Ending Task ----------------- > #

    @tasks.loop(seconds=5)
    async def end_giveaway(self):
        try:
            c = self._CACHE.copy()
            for guild_id, data in c.items():
                for message_id, giveaway in data.items():
                    if isinstance(giveaway, EndedGiveaway):
                        continue

                    if giveaway.ended:
                        try:
                            g = await giveaway.end()
                            self.add_to_cache(g)
                            await self.to_config()

                        except Exception as e:
                            log.exception(
                                f"Error occurred while ending a giveaway with message id: {giveaway.message_id}",
                                exc_info=e,
                            )

        except Exception as e:
            log.exception(
                f"Error occurred while ending a giveaway with message id: {getattr(giveaway, 'message_id', None)}",
                exc_info=e,
            )

    # < ----------------- Event Listeners ----------------- > #

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member.bot:
            return

        guild = self._CACHE.get(payload.guild_id)

        if not guild:
            return

        giveaway: Optional[Union[Giveaway, EndedGiveaway]] = guild.get(payload.message_id)

        if not giveaway or isinstance(giveaway, EndedGiveaway):
            return

        if not str(payload.emoji) == giveaway.emoji:
            return

        try:
            result = await giveaway.add_entrant(payload.member)
            if isinstance(result, str):
                embed = discord.Embed(
                    title="Entry Invalidated!",
                    description=result,
                    color=discord.Color.red(),
                ).set_thumbnail(url=getattr(payload.member.guild.icon, "url", None))

                message = await giveaway.message
                try:
                    await message.remove_reaction(payload.emoji, payload.member)

                except discord.HTTPException:
                    return

                try:
                    await payload.member.send(embed=embed)
                except discord.HTTPException:
                    pass

            elif result is False:
                return

            else:
                reactdm = (await get_guild_settings(payload.guild_id)).reactdm
                if reactdm:
                    embed = discord.Embed(
                        title="Entry Accepted!",
                        description=f"Your entry has been accepted into [this]({giveaway.jump_url}) giveaway.\n"
                        f"Currently, {len(giveaway._entrants)} people have entered.\n"
                        f"This giveaway ends in {humanize_timedelta(timedelta=giveaway.ends_at - datetime.now(timezone.utc))}.",
                        color=discord.Color.green(),
                    ).set_thumbnail(url=getattr(payload.member.guild.icon, "url", None))
                    try:
                        await payload.member.send(embed=embed)
                    except discord.HTTPException as e:
                        pass

        except Exception as e:
            log.exception(f"Error occurred in on_reaction_add: ", exc_info=e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        try:
            member = payload.member or await self.bot.get_or_fetch_user(payload.user_id)

            if member.bot:
                return

            guild = self._CACHE.get(payload.guild_id)

            if not guild:
                return

            giveaway: Optional[Union[Giveaway, EndedGiveaway]] = guild.get(payload.message_id)

            if not giveaway or isinstance(giveaway, EndedGiveaway):
                return

            if not (str_emoji := str(payload.emoji)) == giveaway.emoji:
                # epic, i know you said to just match name and id
                # but that wouldve been too much work to extract that from the giveaway.emoji
                # since thats just a pure string. :p
                # so i just do this.
                if not str_emoji.replace("<:", "<a:") == giveaway.emoji:
                    return

            member = giveaway.guild.get_member(
                member.id
            )  # needs to be a proper member object for the below check

            if (await giveaway.verify_entry(member))[0] is False:
                # to check that the bot didnt remove the reaction.
                return

            await giveaway.remove_entrant(member)

            unreactdm = (await get_guild_settings(giveaway.guild_id)).unreactdm
            if unreactdm:
                embed = discord.Embed(
                    title="Entry removed!",
                    description=f"I detected your reaction was removed on [this]({giveaway.jump_url}) giveaway.\n"
                    f"As such, your entry for this giveaway has been removed.\n"
                    f"If you think this was a mistake, please go and react again to the giveaway :)",
                    color=await giveaway.get_embed_color(),
                ).set_thumbnail(url=getattr(giveaway.guild.icon, "url", None))

                try:
                    await member.send(embed=embed)

                except discord.HTTPException:
                    pass

        except Exception as e:
            log.exception(f"Error occurred in on_reaction_remove: ", exc_info=e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if message.author.bot:
            return

        giveaways = filter(
            lambda x: isinstance(x, Giveaway) and x.requirements.messages != 0,
            self._CACHE.get(message.guild.id, {}).values(),
        )

        for i in giveaways:
            bucket = i.flags.message_cooldown.get_bucket(message)
            retry_after = bucket.update_rate_limit()
            if not retry_after and getattr(i, "_message_cache", None):
                i._message_cache.setdefault(message.author.id, 0)
                i._message_cache[message.author.id] += 1

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):

        settings = await get_guild_settings(ctx.guild.id)

        if settings.autodelete and ctx.command.qualified_name in commands_to_delete:
            try:
                await ctx.message.delete()  # just handle it here :p

            except Exception:
                pass

        if ctx.command != (self.bot.get_command("giveaway start")):
            return

        async with guildconf.guild(ctx.guild).top_managers() as top_managers:
            top_managers.setdefault(str(ctx.author.id), 0)
            top_managers[str(ctx.author.id)] += 1

    # < ----------------- The Actual Commands ----------------- > #

    @commands.group(name="giveaway", aliases=["g"], cooldown_after_parsing=True)
    @commands.guild_only()
    @is_manager()
    async def g(self, ctx: commands.Context):
        """
        Perform giveaway related actions.

        Including `start`, `end` and `reroll`
        """

    @g.command(
        name="start", aliases=["s"], usage="[time] <winners> [requirements] <prize> [flags]"
    )
    @commands.cooldown(2, 1, commands.BucketType.guild)
    @commands.guild_only()
    @is_manager()
    async def g_start(
        self,
        ctx: commands.Context,
        time: Optional[TimeConverter] = None,
        winners: WinnerConverter = None,
        requirements: Optional[Requirements] = None,
        prize: commands.Greedy[PrizeConverter] = None,
        *,
        flags: GiveawayFlags = GiveawayFlags.none(),
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
            `[p]giveaway start 1 this giveaway has no time argument --ends-at 30 december 2021 1 pm UTC --msg but has the '--ends-at' flag`
        """

        if not winners or not prize:
            return await ctx.send_help()

        if not time and not flags.ends_in:
            return await ctx.send(
                "You must specify a time greater than 10 seconds and less than 2 weeks or use the `--ends-at` flag for a more accurate duration."
            )

        if winners > 20:
            return await ctx.send("You can not have more than 20 winners in a giveaway.")

        settings = await get_guild_settings(ctx.guild.id)

        prize = " ".join(prize)

        if flags.starts_in:
            starts_in = flags.starts_in
            time = self._handle_starts_in(time, starts_in)
            await ctx.send(
                f"The giveaway for {prize} will start in <t:{int(starts_in.timestamp())}:R>"
            )

        else:
            starts_in = datetime.now(timezone.utc)

        if flags.ends_in:
            time = flags.ends_in

        giveaway = Giveaway(
            bot=ctx.bot,
            message_id=ctx.message.id,  # istg theres a reason behind this. I will only explain if anyone wants it.
            guild_id=ctx.guild.id,
            channel_id=getattr(flags.channel, "id", ctx.channel.id),
            requirements=requirements or await Requirements.empty(ctx),
            flags=flags,
            prize=prize,
            host=ctx.author.id,
            amount_of_winners=winners,
            emoji=settings.emoji,
            starts_at=starts_in,
            ends_at=time,
        )

        if datetime.now(timezone.utc) >= starts_in:
            await giveaway.start()

        self.add_to_cache(giveaway)

    @g.command(name="flash", aliases=["f", "flashes"])
    @commands.cooldown(2, 15, commands.BucketType.guild)
    @commands.guild_only()
    @is_manager()
    async def g_flash(self, ctx: commands.Context, amount: int, *, prize: str):
        """
        Start multiple flash giveaways with a given prize.

        <amount> is the number of giveaways to flash.
        These giveaway will have 1 winner and will last for 10 seconds each."""
        if amount < 3:
            return await ctx.send("You must flash atleast 3 giveaways.")

        if amount > 10:
            return await ctx.send("You cant flash more than 10 giveaways.")

        for _ in range(amount):
            await self.g_start(
                ctx=ctx,
                time=datetime.now(timezone.utc) + timedelta(seconds=10),
                winners=1,
                prize=prize.split(""),
            )

    @g.command(name="end")
    @commands.guild_only()
    @is_manager()
    async def g_end(
        self, ctx: commands.Context, message: Union[discord.Message, str] = None, reason: str = ""
    ):
        """
        End a giveaway prematurely.

        This can also act as a second option for giveaways that are stuck because of some internal error.
        `Reason` is an optional argument to pass to why the giveaway was ended.

        You can also reply to a giveaway message instead of passing its id.
        Pass `all` to the message parameter to end all active giveaways in your server."""

        if isinstance(message, str):
            if message.lower() == "all":
                view = YesOrNoView(ctx, None, "Aight. Cancelling...", timeout=60)
                view.message = await ctx.send(
                    "Are you sure you want to end all giveaways? (yes/no)", view=view
                )
                if view.value:
                    guild = self._CACHE.get(ctx.guild.id)
                    if not guild:
                        return await ctx.send(
                            "It seems like this server has no giveaways, active or otherwise."
                        )

                    else:
                        ended = []
                        for giveaway in guild.values():
                            if isinstance(giveaway, Giveaway):
                                try:
                                    g = await giveaway.end(
                                        reason=reason + f" Ended prematurely by {ctx.author}"
                                    )
                                    self.add_to_cache(g)
                                    ended.append(g.message_id)

                                except Exception:
                                    await ctx.send(
                                        "An error occured while ending the giveaway with id {}.".format(
                                            giveaway.message_id
                                        )
                                    )

                        if not ended:
                            return await ctx.send(
                                "It appears there aren't any active giveaways to end."
                            )

                        await ctx.send(
                            f"Ended {len(ended)} giveaways with message ids: {humanize_list(ended)}"
                        )
                        await ctx.tick()
                        return

            else:
                return await ctx.send_help()

        message = message or await self.message_from_reply(ctx.message)

        if not message:
            return await ctx.send_help()

        guild = self._CACHE.get(ctx.guild.id)
        if not guild:
            return await ctx.send(
                "It seems like this server has no giveaways, active or otherwise."
            )

        giveaway = guild.get(message.id)
        if not giveaway:
            return await ctx.send(
                "That message doesnt seem to be a valid giveaway. (or it was but is no longer present in cache)"
            )

        if isinstance(giveaway, EndedGiveaway):
            return await ctx.send(
                "That giveaway has already ended. You cannot end an ended giveaway but you can reroll it!"
            )

        reason += f" Ended prematurely by {ctx.author}"

        try:
            g = await giveaway.end(reason)
            self.add_to_cache(g)

        except Exception as e:
            log.exception(
                f"Error occurred while ending a giveaway with message id: {giveaway.message_id}",
                exc_info=e,
            )
            return await ctx.send(
                f"There was an error while ending this giveaway: \n {box(e, 'py')}"
            )

        await ctx.tick(message="Giveaway was ended successfully!")

    @g.command(name="reroll")
    @commands.guild_only()
    @is_manager()
    async def g_reroll(
        self, ctx: commands.Context, message: discord.Message = None, winners: WinnerConverter = 1
    ):
        """
        Reroll the winners for an ended giveaway.

        You can pass the winners argument to specify how many winners you want to reroll.

        You can also reply to a giveaway message instead of passing its id."""
        message = message or await self.message_from_reply(ctx.message)

        if not message:
            return await ctx.send_help()

        guild = self._CACHE.get(ctx.guild.id)
        if not guild:
            return await ctx.send(
                "It seems like this server has no giveaways, active or otherwise."
            )

        giveaway = guild.get(message.id)
        if not giveaway:
            return await ctx.send(
                "That message doesnt seem to be a valid giveaway. (or it was but is no longer present in cache)"
            )

        if isinstance(giveaway, Giveaway):
            return await ctx.send(
                "That giveaway is still running. It needs to end in order to be rerolled!"
            )

        try:
            await giveaway.reroll(ctx, winners)

        except Exception as e:
            log.exception(
                f"Error occurred while rerolling a giveaway with message id: {giveaway.message_id}",
                exc_info=e,
            )
            return await ctx.send(
                f"There was an error while rerolling this giveaway: \n {box(e, 'py')}"
            )

        await ctx.tick(message="Successfuly rerolled the giveaway!")

    @g.command(name="create")
    @commands.guild_only()
    @is_manager()
    async def g_create(self, ctx: commands.Context):
        """
        Start a questionaire to start a giveaway.

        This asks you different question one by one to start a giveaway."""

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

        time = final.get("time", datetime.now(timezone.utc) + timedelta(seconds=30))
        winners = final.get("winners", 1)
        requirements = final.get("requirements")
        prize = final.get("prize", "A new giveaway").split()
        flags = final.get("flags", GiveawayFlags.none())
        channel = final.get("channel", None)
        if channel:
            flags.channel = channel
            await ctx.send("Successfully created giveaway in channel `{}`.".format(channel))

        await self.g_start(
            ctx=ctx,
            time=time,
            prize=prize,
            winners=winners,
            requirements=requirements,
            flags=flags,
        )

    @g.command(name="list", usage="")
    @commands.guild_only()
    @is_manager()
    async def g_list(self, ctx: commands.Context, _global: bool = False):
        """
        List all the active giveaways in a server.

        For bot owners, you can add `true` to the command invocation to list all the active giveaways globally."""
        if _global and not ctx.author.id in ctx.bot.owner_ids:
            return await ctx.send("Tryna be sneaky eh? :smirk:")

        if not _global:
            guild = self._CACHE.get(ctx.guild.id)

            if not guild:
                return await ctx.send("This server has no giveaways, active or otherwise.")

            giveaways = list(filter(lambda x: isinstance(x, Giveaway), guild.values()))

        else:
            if not self._CACHE:
                return await ctx.send("No guilds have started a giveaway yet!")

            giveaways: list[Giveaway] = []

            for guild, data in self._CACHE.items():
                for giveaway in data.values():
                    if not isinstance(giveaway, Giveaway):
                        continue

                    giveaways.append(giveaway)

        if not giveaways:
            return await ctx.send("It seems there are no active giveaways right now.")

        fields = []
        failed: list[EndedGiveaway] = []
        for i in giveaways:
            message = await i.message
            if not message and not i.starts_at > datetime.now(timezone.utc):
                failed.append(await i.end())
                continue
            value = (
                f"***[`{i.prize.center(len(i.prize) + 10, ' ')}`]({message.jump_url})***\n\n"
                f"> Guild: **{i.guild}**\n"
                f"> Channel: {i.channel.mention} ({i.channel})\n"
                f"> Host: **{i.host}**\n"
                f"> Message id: **{i.message_id}**\n"
                f"> Amount of winners: **{i.amount_of_winners}**\n"
                f"> Emoji: **{i.emoji}**\n"
                + (
                    f"> Starts in: **{humanize_timedelta(timedelta=i.starts_at - datetime.now(timezone.utc))}**\n"
                    if i.starts_at > datetime.now(timezone.utc)
                    else ""
                )
                + f"> Ends in: **{humanize_timedelta(timedelta=i.ends_at - datetime.now(timezone.utc))}**\n"
            )
            fields.append({"name": "\u200b", "value": value, "inline": False})

        if failed:
            fields.append(
                {
                    "name": "Failed Giveaways",
                    "value": "----------------------------------------\n",
                    "inline": False,
                }
            )
            for i in failed:
                self.add_to_cache(i)
                value = (
                    f"***__{i.prize}__***\n\n"
                    f"> Guild: **{i.guild}**\n"
                    f"> Channel: {i.channel.mention} ({i.channel})\n"
                    f"> Host: **{i.host}**\n"
                    f"> Message id: **{i.message_id}**\n"
                    f"> Amount of winners: **{i.amount_of_winners}**\n"
                    f"> Reason for failure: {i.reason}"
                )

                fields.append({"name": "\u200b", "value": value, "inline": False})

        embeds = await group_embeds_by_fields(
            *fields,
            per_embed=4,
            title=f"Active giveaways in **{ctx.guild.name}**"
            if not _global
            else "Active giveaways **globally**",
            color=await giveaways[0].get_embed_color(),
        )

        embeds = [
            embed.set_footer(text=f"Page {ind}/{len(embeds)}").set_thumbnail(
                url=getattr(ctx.guild.icon, "url", None)
                if not _global
                else ctx.bot.user.display_avatar.url
            )
            for ind, embed in enumerate(embeds, 1)
        ]

        await PaginationView(ctx, embeds, 60, True).start()

    @g.command(name="show")
    @commands.guild_only()
    @is_manager()
    async def g_show(self, ctx: commands.Context, message: discord.Message = None):
        """
        Show the giveaway that has the given message id.

        You can also reply to a giveaway message instead of passing its id."""
        guild = self._CACHE.get(ctx.guild.id)
        if not guild:
            return await ctx.send("This server has no giveaways, active or otherwise.")

        message = message or await self.message_from_reply(ctx.message)

        if not message:
            return await ctx.send_help()

        giveaway = guild.get(message.id)
        if giveaway is None:
            return await ctx.send("This server has no giveaway with that message id.")

        embed = discord.Embed(
            title=f"Giveaway for {giveaway.prize}",
            color=await giveaway.get_embed_color(),
        )
        embed.description = (
            f"***__[JUMP TO MESSAGE]({message.jump_url})__***\n\n"
            + f"> Guild: **{giveaway.guild}**\n"
            + f"> Channel: {giveaway.channel.mention} ({giveaway.channel})\n"
            + f"> Host: **{giveaway.host}**\n"
            + f"> Message id: **{giveaway.message_id}**\n"
            + f"> Amount of winners: **{giveaway.amount_of_winners}**\n"
            + f"> Emoji: **{giveaway.emoji}**\n"
            + (
                f"> Ends in: **{humanize_timedelta(timedelta=giveaway.ends_at - datetime.now(timezone.utc))}**\n"
                if isinstance(giveaway, Giveaway)
                else f"> Ended at: **<t:{int(giveaway.ends_at.timestamp())}:f>**\n"
                f"> Winner(s): {giveaway.get_winners_str()}"
                f"> Reason: {giveaway.reason}"
            )
            + f"> Requirements: {await giveaway.requirements.get_str(giveaway.guild_id)}"
        )
        embed.set_thumbnail(url=getattr(ctx.guild.icon, "url", None))
        await ctx.send(embed=embed)

    @g.command(name="entrants", aliasers=["entries"])
    @commands.guild_only()
    async def g_entrants(self, ctx: commands.Context, message: discord.Message = None):
        """
        Check who has entered the giveaway until now.

        You can also reply to a giveaway message instead of passing its id."""
        guild = self._CACHE.get(ctx.guild.id)
        if not guild:
            return await ctx.send("This server has no giveaways, active or otherwise.")

        message = message or await self.message_from_reply(ctx.message)

        if not message:
            return await ctx.send_help()

        giveaway = guild.get(message.id)
        if giveaway is None:
            return await ctx.send("This server has no giveaway with that message id.")

        embed = discord.Embed(
            title="Current Entrants for {}".format(giveaway.prize),
            description="\n\n".join(
                [f"{i.mention} - {i} ({i.id})" for i in giveaway.entrants]
                if giveaway._entrants
                else ["This giveaway has no entrants!"]
            ),
            color=await giveaway.get_embed_color(),
        ).set_thumbnail(url=getattr(ctx.guild.icon, "url", None))

        await ctx.send(embed=embed)

    @g.command(name="top", aliases=["topmanagers"])
    @commands.guild_only()
    @is_manager()
    async def g_top(self, ctx: commands.Context):
        """
        See the giveaway managers who have performed the most giveaways."""
        top = (await get_guild_settings(ctx.guild.id)).top_managers
        if not top:
            return await ctx.send("No giveaways performed here in this server yet.")

        _sorted = {k: v for k, v in sorted(top.items(), key=lambda i: i[1], reverse=True)}

        embed = discord.Embed(
            title=f"Top giveaway managers in **{ctx.guild.name}**",
            description="\n".join(
                [f"<@{k}> : {v} giveaway(s) performed." for k, v in _sorted.items()]
            ),
        )
        embed.set_footer(text=ctx.guild.name, icon_url=getattr(ctx.guild.icon, "url", None))
        return await ctx.send(embed=embed)

    @g.command(name="explain")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @commands.bot_has_permissions(embed_links=True)
    async def g_explain(self, ctx, query: str = None):
        """Start a paginated embeds session explaining how
        to use the commands of this cog and how it works.

        You can pass the query parameter to see a specific explanation page.
        Valid arguments are:
            - basics - requirements - flags - customization -"""
        page_names = ["basic", "requirements", "flags", "customization"]

        if query is not None and not query.lower() in page_names:
            return await ctx.send(
                "Valid arguments for the query parameter are: " + humanize_list(page_names)
            )

        something = (
            f"""
***__Basics:__ ***
    > You can host giveaways with the bot. What this is,
    > is that the bot sends an embed containing information such as the prize,
    > the amount of winners, the requirements and the time it ends.

    > People have to react to an emoji set by you through the `{ctx.clean_prefix}gset emoji` command (defaults to :tada: )
    > and after the time to end has come for the giveaway to end, the bot will choose winners from the list of
    > people who reacted and send their mentions in the channel and edit the original embedded message.

    > You can also set multipliers for roles which increase the chances of people with that role to win in a giveaway. `{ctx.clean_prefix}gset multi`
    > These multipliers stack and a user's entries in a giveaway add up for each role multiplier they have.

    > The format to add multis is:
        `{ctx.clean_prefix}gset multi add <role id or mention> <multi>`

    > And to remove is the same:
        `{ctx.clean_prefix}gset multi remove <role id or mention>`

    > To see all active role multipliers:
        `{ctx.clean_prefix}gset multi`

***__Requirements:__ ***
    > You can set requirements for the people who wish to join the giveaways.
    > These requirements can be either of role requirements or AmariBot level requirements.
    > Requirements are provided after the time and no. of winners like so:
        *{ctx.clean_prefix}g start <time> <no. of winners> <requirements> <prize> [flags]*

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

    >    **{ctx.clean_prefix}g start 1h30m 1 somerolemention[bypass];;123456789[blacklist];;12[alvl]**

    ***NOTE***:
        Bypass overrides blacklist, so users with even one bypass role specified
        will be able to join the giveaway regardless of the blacklist.

***__Flags:__ ***
    > Flags are extra arguments passed to the giveaway command to modify it.
    > Flags should be prefixed with `--` (two minus signs?)
    > Flags require you to provide an argument after them unless they are marked as `[argless]`.
    > Then you don't have to provide anything and you can just type the flag and get on with it.

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
        This flag pings the set role. ({ctx.clean_prefix}gset pingrole)

    > *--thank* [argless]
        This flag also sends a separate embed with a message thanking the donor. The message can be changed with `{ctx.clean_prefix}gset tmsg`

    > *--no-defaults* [argless]
        This disables the default bypass and blacklist roles set by you with the `{ctx.clean_prefix}gset blacklist` and `{ctx.clean_prefix}gset bypass`

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
            + f"""

***__Customization:__ ***
    > Giveaways can be customized to your liking but under a certain limit.
    > There are a bunch of giveaway settings that you can change.

    > **Auto deletion of giveaway commands**
        You can set whether giveaway command invocations get deleted themselves or not. `{ctx.clean_prefix}gset autodelete true`

    > **Giveaway headers**
        The message above the giveaway can also be changed. `{ctx.clean_prefix}gset gmsg`

    > **Giveaway emoji**
        The emoji to which people must react to enter a giveaway. This defaults to :tada: but can be changed to anything. `{ctx.clean_prefix}gset emoji`

    > **Giveaway pingrole**
        The role that gets pinged when you use the `--ping` flag. `{ctx.clean_prefix}gset pingrole`

    > **Thank message**
        The message sent when you use the `--thank` flag. `{ctx.clean_prefix}gset tmsg`

    > **Ending message**
        The message sent when the giveaway ends containing the winner mentions. `{ctx.clean_prefix}gset endmsg`

    > **Default blacklist**
        The roles that are by default blacklisted from giveaways. `{ctx.clean_prefix}gset blacklist`

    > **Default bypass**
        The roles that are by default able to bypass requirements in giveaways. `{ctx.clean_prefix}gset bypass`

    > **Show defaults in giveaway embed**
        It gets kinda janky when you have multiple defaults set and the giveaway embed becomes too long.
        Easy way out, is to simply disable showing the defaults in the embed ;) `{ctx.clean_prefix}gset showdefaults`

    > **Embed Color**
        The default embed color doesn't look good to you? now worries, you can now customize the color for your server.
        `{ctx.prefix}gset color`
        """
        )

        pages = list(pagify(something, delims=["\n***"], page_length=2800))

        final = {}

        for ind, page in enumerate(pages, 1):
            embed = discord.Embed(title="Giveaway Explanation!", description=page, color=0x303036)
            embed.set_footer(text=f"Page {ind} out of {len(pages)}")
            final[page_names[ind - 1]] = embed

        if not query:
            await PaginationView(ctx, final, 60, True).start()

        else:
            await PaginationView(ctx, [final[query]], 60, True).start()
