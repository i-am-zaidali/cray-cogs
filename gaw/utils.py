from typing import Callable, Awaitable, List, Tuple, Dict, Any
from .converters import TimeConverter
from dateparser import parse
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.predicates import MessagePredicate
import asyncio
from datetime import datetime, timezone
import discord
from redbot.core import commands


async def dict_keys_to(d: dict, conv: Callable = int):
    """Convert a dict's keys to the given conv. This will convert keys upto one nested dict."""
    final = {}
    for key, value in d.items():
        if isinstance(value, dict):
            final[conv(key)] = {conv(k): v for k, v in value.items()}
            continue

        final[conv(key)] = value

    return final


class Coordinate(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class SafeMember:
    def __init__(self, member: discord.Member):
        self._org = member
        self.id = member.id
        self.name = member.name
        self.mention = member.mention
        self.avatar_url = member.avatar_url

    def __str__(self) -> str:
        return self._org.__str__()

    def __getattr__(
        self, value
    ):  # if anyone tries to be sneaky and tried to access things they cant
        return f"donor.{value}"  # since its only used in one place where the var name is donor.
    

async def ask_for_answers(
    ctx: commands.Context,
    questions: List[Tuple[str, str, str, Callable[[discord.Message], Awaitable[Any]]]],
    timeout: int = 30,
) -> Dict[str, Any]:
    main_check = MessagePredicate.same_context(ctx)
    final = {}
    for question in questions:
        title, description, key, check = question
        answer = None
        sent = False
        while answer is None:
            if not sent:
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=await ctx.embed_color(),
                    timestamp=ctx.message.created_at,
                ).set_footer(
                    text=f"You have {timeout} seconds to answer.\nSend `cancel` to cancel."
                )
                sent = await ctx.send(embed=embed)
            try:
                message = await ctx.bot.wait_for("message", check=main_check, timeout=timeout)
            except asyncio.TimeoutError:
                await ctx.send("You took too long to answer. Cancelling.")
                return False

            if message.content.lower() == "cancel":
                await ctx.send("Cancelling.")
                return False

            try:
                result = await check(message)

            except Exception as e:
                await ctx.send(
                    f"The following error has occurred:\n{box(e, lang='py')}\nPlease try again. (The process has not stopped. Send your answer again)"
                )
                # log.exception(
                #     "An exception occurred during hte step by step process:\n", exc_info=e
                # )
                continue

            answer = result

        final[key] = answer

    return final


# helper methods for ask_for_answer ugh


def is_lt(lt: int):
    async def pred(message: discord.Message):
        if message.content.isdigit() and int(message.content) <= lt:
            return int(message.content)
        raise commands.BadArgument("Given argument must be less than or equal to {} and a numeric digit".format(lt))

    return pred


def datetime_conv(ctx):
    async def pred(message: discord.Message):
        try:
            t = await TimeConverter().convert(ctx, message.content)
        except Exception:
            try:
                t: datetime = parse(message.content)
            except Exception:
                raise commands.BadArgument(f"`{message.content}` is not a valid date/time.")

            if not t.tzinfo:
                # honestly idk how this works but it does and tbf idk how to work with times so bare with me pls-
                _ = datetime.now()
                if t < _:
                    raise commands.BadArgument(f"1 Given date/time for `--ends-at` is in the past!")
                _ = t - _
                t = datetime.now(tz=timezone.utc) + _
                # t = t.replace(tzinfo=datetime.timezone.utc)

                # i couldve just done this but it gets messed up with the system time
                # when the user passes a *duration* and not a date/time
                # so for example user says "30 minutes" and the system time is 1:00pm in a UTC-5 timezone
                # dateparser will give us 1:30pm (no timezone) and converting it to utc gives us 1:30pm UTC
                # which is 5 hours ahead of current time and not 30 minutes.

            current = datetime.now(tz=timezone.utc)
            if t < current:
                raise commands.BadArgument("Given date/time is in the past.")

        return t

    return pred


def requirement_conv(ctx):
    from .models import Requirements

    async def pred(message: discord.Message):
        return await Requirements.convert(ctx, message.content)

    return pred


def channel_conv(ctx):
    async def pred(message: discord.Message):
        return await commands.TextChannelConverter().convert(ctx, message.content)

    return pred


def flags_conv(ctx):
    from .models import GiveawayFlags
    async def pred(message: discord.Message):
        if message.content.lower() == "none":
            return GiveawayFlags.none()
        return await GiveawayFlags().convert(ctx, message.content)

    return pred