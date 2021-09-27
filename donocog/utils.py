from redbot.core import commands
import re

time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d))+?")
time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400}

class MoniConverter(commands.Converter):
  async def convert(self, ctx, argument):
    try:
      total_stars = 0
      num_map = {'K':1000, 'M':1000000, 'B':1000000000}
      if argument.isdigit():
          total_stars = int(argument)
      else:
          if len(argument) > 1:
              total_stars = float(argument[:-1]) * num_map.get(argument[-1].upper(), 1)
      return int(total_stars)

    except:
      try:
        return int(float(argument))
      except:
        if re.match(r'<@!?([0-9]+)>$', argument):
          await ctx.send(f"The mention comes after the amount.")
          await ctx.send_help(ctx.command.qualified_name)
          return
        await ctx.send(f"Couldn't convert {argument} to a proper amount.")
        await ctx.send_help(ctx.command.qualified_name)

async def sortdict(argument, key_or_value="value"):
  if not isinstance(argument, dict):
    raise TypeError(f"`{argument}` is a `{type(argument)}`, not a dict.")

  else:
    _sorted = sorted(argument.items(), key=lambda x: x[1 if key_or_value.lower() == "value" else 0], reverse=True)
    final = {}
    for i in _sorted:
      final[i[0]] = i[1]

    return final