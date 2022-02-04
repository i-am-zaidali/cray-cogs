import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Union

import discord
import asyncio
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

from .converters import PrizeConverter, TimeConverter, WinnerConverter
from .models import (
    EndedGiveaway,
    Giveaway,
    GiveawayFlags,
    Requirements,
    get_guild_settings,
    model_from_time,
)
from .utils import dict_keys_to, ask_for_answers, is_lt, datetime_conv, requirement_conv, flags_conv, channel_conv

log = logging.getLogger("red.craycogs.giveaways")


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, 1, True, "Giveaways")
        self.config.init_custom("giveaway", 2)

        self._CACHE: Dict[int, Dict[int, Union[Giveaway, EndedGiveaway]]] = {}

        self.end_giveaways_task = self.end_giveaway.start()

    @classmethod
    async def initialize(cls, bot: Red):
        self = cls(bot)
        all = await self.config.custom("giveaway").all()
        all = await dict_keys_to(all)
        for guild_id, data in all.items():
            guild = self._CACHE.setdefault(guild_id, {})
            for message_id, more_data in data.items():
                g = model_from_time(more_data.get("ends_at"))
                more_data.update(bot=bot)
                guild.setdefault(message_id, g.from_json(more_data))

        return self

    def add_to_cache(self, giveaway: Union[Giveaway, EndedGiveaway]):
        e = self._CACHE.setdefault(giveaway.guild_id, {})
        e[giveaway.message_id] = giveaway

    def remove_from_cache(self, giveaway: Union[Giveaway, EndedGiveaway]):
        guild = self._CACHE.get(giveaway.guild_id)
        try:
            return guild.pop(giveaway.message_id)

        except:
            return

    async def to_config(self):
        try:
            copy = self._CACHE.copy()
            for guild_id, data in copy.items():
                for message_id, giveaway in data.items():
                    json = giveaway.json
                    print(json)
                    await self.config.custom("giveaway", guild_id, message_id).set(json)

            log.debug("Saved cache to config!")

        except Exception as e:
            log.exception("Exception occurred when backing up cache: ", exc_info=e)

    async def message_from_reply(self, message: discord.Message):
        if not message.reference:
            return

        reply = message.reference.resolved
        return reply

    def cog_unload(self):
        self.bot.loop.create_task(self.to_config())
        self.end_giveaways_task.cancel()
        for i in Giveaway._tasks:
            i.cancel()  # cancel all running tasks

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

                        except Exception as e:
                            log.exception(
                                f"Error occurred while ending a giveaway with message id: {giveaway.message_id}",
                                exc_info=e,
                            )

        except Exception as e:
            log.exception(
                f"Error occurred while ending a giveaway with message id: {giveaway.message_id}",
                exc_info=e,
            )

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

        result = await giveaway.add_entrant(payload.member)
        if not result:
            channel: discord.TextChannel = self.bot.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)
            try:
                await message.remove_reaction(payload.emoji, payload.member)

            except discord.HTTPException:
                return

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

    @commands.group(
        name="giveaway", aliases=["g"], invoke_without_command=True, cooldown_after_parsing=True
    )
    @commands.mod_or_permissions(administrator=True)
    @commands.guild_only()
    async def g(self, ctx: commands.Context):
        """
        Perform giveaway related actions.

        Including `start`, `end` and `reroll`
        """
        await ctx.send_help(ctx.command)

    @g.command(
        name="start", aliases=["s"], usage="[time] <winners> [requirements] <prize> [flags]"
    )
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
            return await ctx.send("You must specify a time or use the `--ends-at` flag.")

        settings = await get_guild_settings(ctx.guild.id)

        starts_in = (
            flags.starts_in
            if flags.starts_in and flags.starts_in > datetime.now(timezone.utc)
            else datetime.now(timezone.utc)
        )

        giveaway = Giveaway(
            bot=ctx.bot,
            message_id=ctx.message.id,  # istg theres a reason behind this. I will only explain if anyone wants it.
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            requirements=requirements or await Requirements.empty(ctx),
            flags=flags,
            prize=" ".join(prize),
            host=ctx.author.id,
            amount_of_winners=winners,
            emoji=settings.emoji,
            starts_at=starts_in,
            ends_at=time,
        )

        if datetime.now(timezone.utc) >= starts_in:
            await giveaway.start()

        self.add_to_cache(giveaway)

    @g.command(name="end")
    async def g_end(
        self, ctx: commands.Context, message: discord.Message = None, reason: str = ""
    ):
        """
        End a giveaway prematurely.

        This can also act as a second option for giveaways that are stuck because of some internal error.
        `Reason` is an optional argument to pass to why the giveaway was ended."""

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
    async def g_reroll(
        self, ctx: commands.Context, message: discord.Message = None, winners: WinnerConverter = 1
    ):

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
    async def g_create(self, ctx: commands.Context):
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

        await self.g_start(ctx=ctx, time=time, prize=prize, winners=winners, requirements=requirements, flags=flags)
        
    