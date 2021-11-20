from redbot.core import commands
from discord.ext.commands.view import StringView
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
  
class flags(commands.Converter):
    """
    This is a custom flag parsing class made by me with help from skelmis (ethan) from menudocs."""
    def __init__(self, *, delim=None, start=None):
        self.delim = delim or " "
        self.start = start or "--"

    async def convert(self, ctx, argument):
        x = True
        argless = []
        data = {None: []}
        argument = argument.split(self.start)

        if (length := len(argument)) == 1:
            # No flags
            argless.append(argument[0])
            x = False  # Don't loop

        i = 0
        while x:
            if i >= length:
                # Have consumed all
                break

            if self.delim in argument[i]:
                # Get the arg name minus start state
                arg = argument[i].split(self.delim, 1)

                if len(arg) == 1:
                    # Arg has no value, so its argless
                    # This still removes the start and delim however
                    argless.append(arg)
                    i += 1
                    continue

                arg_name = arg[0]
                arg_value = arg[1].strip()

                data[arg_name] = arg_value

            else:
                argless.append(argument[i])

            i += 1

        # Time to manipulate argless
        # into the same expected string pattern
        # as dpy's argparsing
        for arg in argless:
            view = StringView(arg)
            while not view.eof:
                word = view.get_quoted_word()
                data[None].append(word)
                view.skip_ws()

        if not bool(data[None]):
            data.pop(None)

        return data