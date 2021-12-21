import re
from argparse import ArgumentParser

from discord.ext.commands.converter import MemberConverter, TextChannelConverter
from discord.ext.commands.errors import BadArgument
from redbot.core import commands
from redbot.core.utils import mod


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
        if argument.isdigit():
            winner = int(argument)

        else:
            if len(argument) > 1:
                winner = int(
                    float(argument[:-1])
                )  # case where user writes `1w` instead of just an integer.

        return winner


def readabletimer(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if int(d) == 0 and int(h) == 0 and int(m) == 0:
        sentence = f"**{int(s)}** seconds "
    elif int(d) == 0 and int(h) == 0 and int(m) != 0:
        sentence = f"**{int(m)}** minutes and **{int(s)}** seconds"
    elif int(d) != 0:
        sentence = f"**{int(d)}** days, **{int(h)}** hours and **{int(m)}** minutes"
    else:
        sentence = f"**{int(h)}** hours, **{int(m)}** minutes and **{int(s)}** seconds"

    return sentence


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
        parser.add_argument("--no-defaults", action="store_true", dest="no_defaults")
        parser.add_argument("--no-multi", action="store_true", dest="no_multi")
        parser.add_argument("--no-donor", action="store_true", dest="no_donor")
        donolog = parser.add_argument_group()
        donolog.add_argument("--amount", "--amt", nargs="?", dest="amount", default=None)
        donolog.add_argument("--bank", "--category", nargs="?", dest="bank", default=None)

        try:
            flags = vars(parser.parse_args(argument.split(" ")))
        except Exception as e:
            raise BadArgument() from e

        if msg := flags.get("msg"):
            flags["msg"] = " ".join(msg)

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

        return flags
