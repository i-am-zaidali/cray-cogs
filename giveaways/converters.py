import re
from datetime import datetime, timedelta, timezone

from redbot.core import commands


class TimeConverter(commands.Converter):
    time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d))+?")
    time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400}

    async def convert(self, ctx, argument):
        args = argument.lower()
        matches = re.findall(self.time_regex, args)
        time = 0
        if not matches:
            raise commands.BadArgument("Invalid time format. h|m|s|d are valid arguments.")
        for key, value in matches:
            try:
                time += self.time_dict[value] * float(key)
            except KeyError:
                raise commands.BadArgument(
                    f"{value} is an invalid time key! h|m|s|d are valid arguments"
                )
            except ValueError:
                raise commands.BadArgument(f"{key} is not a number!")

        if not time >= 10:
            raise commands.BadArgument("Time must be greater than 10 seconds.")

        if time > (60 * 60 * 24 * 14):
            raise commands.BadArgument("Time for giveaways must be less than 2 weeks")

        time = timedelta(seconds=time)
        time = datetime.now(timezone.utc) + time
        return time


class WinnerConverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        try:
            match = re.findall(r"^\d+", argument)
            if not match:
                raise commands.BadArgument(f"{argument} is not a valid number for winners.")
            winner = int(match[0])
            return winner

        except Exception as e:
            raise commands.BadArgument(str(e))


class PrizeConverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        if argument.startswith("--"):
            raise commands.BadArgument("You can't use flags in prize names.")

        return argument
