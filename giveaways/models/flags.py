from argparse import ArgumentParser
from datetime import datetime, timezone
from typing import Optional

import discord
from dateparser import parse
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list

from ..converters import TimeConverter


class NoExitParser(ArgumentParser):
    def error(self, message):
        raise commands.BadArgument(message)


class GiveawayFlags(commands.Converter):
    def __init__(self, data: dict = {}) -> None:
        self.message: str = data.get("msg")
        self.ping: bool = data.get("ping", False)
        self.donor: Optional[discord.Member] = data.get("donor")
        self.thank: bool = data.get("thank", False)
        self.channel: Optional[discord.TextChannel] = data.get("channel")
        self.ends_in: Optional[datetime] = data.get("ends_at")
        self.starts_in: Optional[datetime] = data.get("starts_in")
        self.no_defaults: bool = data.get("no_defaults")
        self.no_multi: bool = data.get("no_multi")
        self.no_multiple_winners: bool = data.get("no_multiple_winners", False)
        self.no_donor: bool = data.get("no_donor")
        self.message_count: int = data.get("message_count")
        self.cooldown = data.get("message_cooldown", 1)
        self.message_cooldown: Optional[
            commands.CooldownMapping
        ] = commands.CooldownMapping.from_cooldown(1, self.cooldown, commands.BucketType.member)

    @property
    def json(self):
        return {
            "message": self.message,
            "ping": self.ping,
            "donor": getattr(self.donor, "id", None),
            "thank": self.thank,
            "channel": getattr(self.channel, "id", None),
            "ends_at": self.ends_in.timestamp() if self.ends_in else None,
            "starts_in": self.starts_in.timestamp() if self.starts_in else None,
            "no_defaults": self.no_defaults,
            "no_multi": self.no_multi,
            "no_donor": self.no_donor,
            "message_count": self.message_count,
            "message_cooldown": self.cooldown,
        }

    def __str__(self):
        return (
            f"<{self.__class__.__name__} message={self.message} ping={self.ping} "
            f"donor={self.donor} thank={self.thank} channel={getattr(self.channel, 'id', None)} "
            f"ends_in={self.ends_in} starts_in={self.starts_in} no_defaults={self.no_defaults} "
            f"no_multiple_winners={self.no_multiple_winners} no_multi={self.no_multi} "
            f"no_donor={self.no_donor} message_count={self.message_count}>"
        )

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def from_json(cls, json: dict, guild: discord.Guild):
        json.update(
            {
                "donor": guild.get_member(json.get("donor")) if json.get("donor") else None,
                "channel": guild.get_channel(json.get("channel")) if json.get("channel") else None,
                "ends_at": datetime.fromtimestamp(json.get("ends_at"), timezone.utc)
                if json.get("ends_at")
                else None,
                "starts_in": datetime.fromtimestamp(json.get("starts_in"), timezone.utc)
                if json.get("starts_in")
                else None,
            }
        )
        return cls(data=json)

    @classmethod
    def none(cls):
        return cls()

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
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
        parser.add_argument(
            "--no-multiple-winners", action="store_true", dest="no_multiple_winners"
        )
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
            raise commands.BadArgument(str(e))

        if msg := flags.get("msg"):
            flags["msg"] = " ".join(msg)

        end_t = None
        start_t = None

        if start_at := flags.get("starts_in"):
            # hahaha ctrl-C + ctrl-V go brrrrrrr
            start_at = " ".join(start_at)

            try:
                t = await TimeConverter().convert(ctx, start_at)

            except Exception:
                try:
                    t = parse(start_at)

                except Exception as e:
                    raise commands.BadArgument(f"{start_at} is not a valid date/time!") from e

                if not t.tzinfo:
                    _ = datetime.now()
                    if t < _:
                        print("here?", t, _)
                        raise commands.BadArgument(
                            f"Given date/time for `--starts-in` is in the past!"
                        )
                    _ = t - _
                    t = start_t = datetime.now(tz=timezone.utc) + _

                current = datetime.now(tz=timezone.utc)
                if t < current:
                    print("or here?")
                    raise commands.BadArgument("Given date/time for `--starts-in` is in the past.")

            flags["starts_in"] = t

        if end_at := flags.get("ends_at"):
            end_at = " ".join(end_at)

            try:
                t = await TimeConverter().convert(ctx, end_at)

            except Exception:
                try:
                    t = parse(end_at)

                except Exception as e:
                    raise commands.BadArgument(f"{end_at} is not a valid date/time!") from e

                if not t.tzinfo:
                    # honestly idk how this works but it does and tbf idk how to work with times so bare with me pls-
                    _ = datetime.now()
                    if t < _:
                        raise commands.BadArgument(
                            f"Given date/time for `--ends-at` is in the past!"
                        )
                    _ = t - _
                    if _.total_seconds() > (60 * 60 * 24 * 14):
                        raise commands.BadArgument("Time for giveaways must be less than 2 weeks")
                    t = end_t = datetime.now(tz=timezone.utc) + _
                    # t = t.replace(tzinfo=timezone.utc)

                    # i couldve just done this but it gets messed up with the system time
                    # when the user passes a *duration* and not a date/time
                    # so for example user says "30 minutes" and the system time is 1:00pm in a UTC-5 timezone
                    # dateparser will give us 1:30pm (no timezone) and converting it to utc gives us 1:30pm UTC
                    # which is 5 hours ahead of current time and not 30 minutes.

                current = datetime.now(tz=timezone.utc)
                if t < current:
                    raise commands.BadArgument("Given date/time for `--ends-at` is in the past.")

                if (t - current).total_seconds() < 10:
                    raise commands.BadArgument("Time to end at must be greater than 10 seconds.")

                if start_t and t < start_t:
                    raise commands.BadArgument(
                        "Given date/time for `--ends-at` must be after `--starts-in`."
                    )

            flags["ends_at"] = t

        if donor := flags.get("donor"):
            try:
                flags["donor"] = await commands.MemberConverter().convert(ctx, donor)
            except Exception as e:
                raise commands.BadArgument()

        if channel := flags.get("channel"):
            try:
                flags["channel"] = await commands.TextChannelConverter().convert(ctx, channel)
            except Exception as e:
                raise commands.BadArgument()

        if amount := flags.get("amount"):
            cog = ctx.bot.get_cog("DonationLogging")
            if not cog:
                raise commands.BadArgument(
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
                raise commands.BadArgument(
                    "You do not have the required permissions to add to a user's donations."
                )

        if message_count := flags.get("message_count"):
            flags["message_count"] = abs(message_count)

        if msg_cd := flags.get("message_cooldown"):
            if msg_cd > 60:
                raise commands.BadArgument("The cooldown can not be greater than 60 seconds.")

            flags["message_cooldown"] = abs(msg_cd)

        return cls(data=flags)
