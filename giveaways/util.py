import asyncio
import datetime
import logging
import re
import time
from argparse import ArgumentParser
from typing import Any, Awaitable, Callable, Dict, List, Tuple, Union

import discord
from dateparser import parse
from discord.ext.commands.converter import MemberConverter, MessageConverter, TextChannelConverter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.utils import mod
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.craycogs.giveaways.util")


def group_embeds_by_fields(
    *fields: Dict[str, Union[str, bool]], per_embed: int = 3, **kwargs
) -> List[discord.Embed]:
    """
    This was the result of a big brain moment i had

    This method takes dicts of fields and groups them into separate embeds
    keeping `per_embed` number of fields per embed.

    Extra kwargs can be passed to create embeds off of.
    """
    groups = []
    for ind, i in enumerate(range(0, len(fields), per_embed)):
        groups.append(
            discord.Embed(**kwargs)
        )  # append embeds in the loop to prevent incorrect embed count
        fields_to_add = fields[i : i + per_embed]
        for field in fields_to_add:
            groups[ind].add_field(**field)
    return groups


def is_gwmanager():
    async def predicate(ctx):
        roles = await ctx.cog.config.get_managers(ctx.guild)
        if roles and any([role in ctx.author.roles for role in roles]):
            return True
        elif (
            ctx.author.guild_permissions.manage_messages == True
            or await mod.is_mod_or_superior(ctx.bot, ctx.author) == True
        ):
            return True

        return False

    return commands.check(predicate)


class Coordinate(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class prizeconverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        if argument.startswith("--"):
            raise BadArgument("You can't use flags in prize names.")

        return argument


time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d))+?")
time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400}


class TimeConverter(commands.Converter):
    async def convert(self, ctx, argument):
        args = argument.lower()
        matches = re.findall(time_regex, args)
        time = 0
        if not matches:
            raise commands.BadArgument("Invalid time format. h|m|s|d are valid arguments.")
        for key, value in matches:
            try:
                time += time_dict[value] * float(key)
            except KeyError:
                raise commands.BadArgument(
                    f"{value} is an invalid time key! h|m|s|d are valid arguments"
                )
            except ValueError:
                raise commands.BadArgument(f"{key} is not a number!")
        return round(time)


class WinnerConverter(commands.Converter):
    async def convert(self, ctx, argument):
        winner = 0
        try:
            match = re.findall(r"^\d+", argument)
            if not match:
                raise BadArgument(f"{argument} is not a valid number for winners.")
            winner = int(match[0])
            if winner > 20:
                raise BadArgument("You can't have more than 20 winners.")
            return winner

        except Exception as e:
            raise BadArgument(str(e))


class GiveawayMessageConverter(MessageConverter):
    async def convert(self, ctx, argument):
        message = await super().convert(ctx, argument)
        active_cache = ctx.cog.giveaway_cache.copy()
        msg = list(
            filter(
                lambda x: x.message_id == message.id and x.guild.id == message.guild.id,
                active_cache,
            )
        )
        if not msg:
            ended_cache = ctx.cog.ended_cache.copy()
            msg = list(
                filter(
                    lambda x: x.message_id == message.id and x.guild.id == message.guild.id,
                    ended_cache,
                )
            )

        try:
            msg = msg[0]

        except IndexError:
            raise BadArgument("That message is not a giveaway message.")

        return msg


# Thanks neuroassassin and flare for the inspiration :p


class NoExitParser(ArgumentParser):
    def error(self, message):
        raise BadArgument()


class Flags(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        argument = argument.replace("—", "--")
        parser = NoExitParser(description="Giveaways flag parser", add_help=False)

        parser.add_argument("--message", "--msg", nargs="+", default=[], dest="msg")
        parser.add_argument("--ping", dest="ping", action="store_true")
        parser.add_argument("--donor", dest="donor", nargs="?", default=None)
        parser.add_argument("--thank", action="store_true", dest="thank")
        parser.add_argument("--channel", "--chan", dest="channel", nargs="?", default=None)
        parser.add_argument(
            "--ends-at",
            "--end-in",
            "--ends-in",
            "--end-at",
            dest="ends_at",
            nargs="+",
            default=None,
        )
        parser.add_argument(
            "--starts-in",
            "--start-in",
            "--starts-at",
            "--start-at",
            dest="starts_in",
            nargs="+",
            default=None,
        )
        parser.add_argument("--no-defaults", action="store_true", dest="no_defaults")
        parser.add_argument("--no-multi", action="store_true", dest="no_multi")
        parser.add_argument("--no-donor", action="store_true", dest="no_donor")
        donolog = parser.add_argument_group()
        donolog.add_argument("--amount", "--amt", nargs="?", dest="amount", default=None)
        donolog.add_argument("--bank", "--category", nargs="?", dest="bank", default=None)

        msg_req = parser.add_argument_group()
        msg_req.add_argument(
            "--messages",
            "--msgs",
            "--msg-req",
            "--msg-count",
            nargs="?",
            default=0,
            type=int,
            dest="message_count",
        )
        msg_req.add_argument(
            "--cooldown", "--cd", nargs="?", default=0, dest="message_cooldown", type=int
        )

        try:
            flags = vars(parser.parse_args(argument.split(" ")))
        except Exception as e:
            raise BadArgument(str(e))

        if msg := flags.get("msg"):
            flags["msg"] = " ".join(msg)

        end_t = None
        start_t = None

        if end_at := flags.get("ends_at"):
            end_at = " ".join(end_at)

            try:
                t = await TimeConverter().convert(ctx, end_at)

            except Exception:
                try:
                    t = parse(end_at)

                except Exception as e:
                    raise BadArgument(f"{end_at} is not a valid date/time!") from e

                if not t.tzinfo:
                    # honestly idk how this works but it does and tbf idk how to work with times so bare with me pls-
                    _ = datetime.datetime.now()
                    if t < _:
                        raise BadArgument(f"1 Given date/time for `--ends-at` is in the past!")
                    _ = t - _
                    t = end_t = datetime.datetime.now(tz=datetime.timezone.utc) + _
                    # t = t.replace(tzinfo=datetime.timezone.utc)

                    # i couldve just done this but it gets messed up with the system time
                    # when the user passes a *duration* and not a date/time
                    # so for example user says "30 minutes" and the system time is 1:00pm in a UTC-5 timezone
                    # dateparser will give us 1:30pm (no timezone) and converting it to utc gives us 1:30pm UTC
                    # which is 5 hours ahead of current time and not 30 minutes.

                current = datetime.datetime.now(tz=datetime.timezone.utc)
                if t < current:
                    raise BadArgument("Given date/time for `--ends-at` is in the past.")

                t = int(t.timestamp() - current.timestamp())

            flags["ends_at"] = t

        if start_at := flags.get("starts_in"):
            # hahaha ctrl-C + ctrl-V go brrrrrrr
            start_at = " ".join(start_at)

            try:
                t = await TimeConverter().convert(ctx, start_at)
                t += int(time.time())

            except Exception:
                try:
                    t = parse(start_at)

                except Exception as e:
                    raise BadArgument(f"{start_at} is not a valid date/time!") from e

                if not t.tzinfo:
                    _ = datetime.datetime.now()
                    if t < _:
                        raise BadArgument(f"Given date/time for `--starts-in` is in the past!")
                    _ = t - _
                    t = start_t = datetime.datetime.now(tz=datetime.timezone.utc) + _

                current = datetime.datetime.now(tz=datetime.timezone.utc)
                if t < current:
                    raise BadArgument("Given date/time for `--starts-in` is in the past.")

                if end_t and end_t < start_t:
                    raise BadArgument("`--ends-at` can not be a time before `--starts-in`.")

                t = int(t.timestamp())

            flags["starts_in"] = t

        if donor := flags.get("donor"):
            try:
                flags["donor"] = await MemberConverter().convert(ctx, donor)
            except Exception as e:
                raise BadArgument()

        if channel := flags.get("channel"):
            try:
                flags["channel"] = await TextChannelConverter().convert(ctx, channel)
            except Exception as e:
                raise BadArgument()

        if amount := flags.get("amount"):
            cog = ctx.bot.get_cog("DonationLogging")
            if not cog:
                raise BadArgument(
                    "The `--amount` and `--bank` flag require the DonationLogging cog to be loaded."
                )

            command = ctx.bot.get_command("dono add")
            if await command.can_run(ctx):
                amt = await cog.conv(ctx, amount)
                if bank := flags.get("bank"):
                    try:
                        bank = await cog.cache.get_dono_bank(ctx.guild.id, bank)
                    except Exception as e:
                        bank = await cog.cache.get_default_category(ctx.guild.id)
                mem = flags.get("donor") or ctx.author
                await ctx.invoke(command, category=bank, amount=amt, user=mem)

            else:
                raise BadArgument(
                    "You do not have the required permissions to add to a user's donations."
                )

        if message_count := flags.get("message_count"):
            flags["message_count"] = abs(message_count)

        if msg_cd := flags.get("message_cooldown"):
            if msg_cd > 60:
                raise BadArgument("The cooldown can not be greater than 60 seconds.")

            flags["message_cooldown"] = abs(msg_cd)

        return flags


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
        raise BadArgument()

    return pred


def datetime_conv(ctx):
    async def pred(message: discord.Message):
        try:
            t = await TimeConverter().convert(ctx, message.content)
        except Exception:
            try:
                t = parse(message.content)
            except Exception:
                raise BadArgument(f"`{message.content}` is not a valid date/time.")

            if not t.tzinfo:
                # honestly idk how this works but it does and tbf idk how to work with times so bare with me pls-
                _ = datetime.datetime.now()
                if t < _:
                    raise BadArgument(f"1 Given date/time for `--ends-at` is in the past!")
                _ = t - _
                t = end_t = datetime.datetime.now(tz=datetime.timezone.utc) + _
                # t = t.replace(tzinfo=datetime.timezone.utc)

                # i couldve just done this but it gets messed up with the system time
                # when the user passes a *duration* and not a date/time
                # so for example user says "30 minutes" and the system time is 1:00pm in a UTC-5 timezone
                # dateparser will give us 1:30pm (no timezone) and converting it to utc gives us 1:30pm UTC
                # which is 5 hours ahead of current time and not 30 minutes.

            current = datetime.datetime.now(tz=datetime.timezone.utc)
            if t < current:
                raise BadArgument("Given date/time is in the past.")

            t = int(t.timestamp() - current.timestamp())

        return t

    return pred


def requirement_conv(ctx):
    from .models import Requirements

    async def pred(message: discord.Message):
        return await Requirements.convert(ctx, message.content)

    return pred


def channel_conv(ctx):
    async def pred(message: discord.Message):
        return await TextChannelConverter().convert(ctx, message.content)

    return pred


def flags_conv(ctx):
    async def pred(message: discord.Message):
        if message.content.lower() == "none":
            return {}
        return await Flags().convert(ctx, message.content)

    return pred
