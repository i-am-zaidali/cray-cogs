from typing import Counter
from redbot.core.utils import mod
import discord
from redbot.core import commands
from discord.ext.commands.converter import RoleConverter
import discord.utils
from typed_flags import TypedFlags

import re

class flags(TypedFlags):
  def __init__(self):
      super().__init__(delim=" ", start="--")
      
def is_gwmanager():
  async def predicate(ctx):
    roles = await ctx.cog.config.get_managers(ctx.guild)
    if roles and any([role in ctx.author.roles for role in roles]):
      return True
    elif ctx.author.guild_permissions.manage_messages == True or await mod.is_mod_or_superior(ctx.bot, ctx.author) == True:
      return True
    
    return False

  return commands.check(predicate)
      
class prizeconverter(commands.Converter):
  async def convert(self, ctx, argument:str):
    if argument.startswith("--"):
          return ""

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
        winner = float(argument[:-1])

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