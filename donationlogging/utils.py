import asyncio
import re
from typing import Any, Awaitable, Callable, Dict, List, Tuple

import discord
from discord.ext.commands.converter import EmojiConverter, RoleConverter, TextChannelConverter
from discord.ext.commands.errors import BadArgument, EmojiNotFound
from discord.ext.commands.view import StringView
from emoji import UNICODE_EMOJI_ENGLISH
from fuzzywuzzy import process
from redbot.core import commands
from redbot.core.utils import mod
from redbot.core.utils.chat_formatting import box
from redbot.core.utils.predicates import MessagePredicate

from .exceptions import CategoryAlreadyExists, CategoryDoesNotExist
from .models import DonoBank

time_regex = re.compile(r"(?:(\d{1,5})(h|s|m|d))+?")
time_dict = {"h": 3600, "s": 1, "m": 60, "d": 86400}


class CategoryConverter(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            dono_bank = await ctx.cog.cache.get_existing_dono_bank(argument, ctx.guild.id)
            ctx.dono_category = dono_bank

        except CategoryDoesNotExist:
            ctx.dono_category = await ctx.cog.cache.get_default_category(ctx.guild.id)
            raise BadArgument(
                f"You haven't registered a currency category with the name `{argument}`."
                f"Use `{ctx.prefix}help donoset category` to know how to add a currency category."
            )

        return dono_bank


class CategoryMaker(commands.Converter):
    async def convert(self, ctx, argument) -> DonoBank:
        try:
            name, emoji = argument.strip().split(",")
        except:
            raise BadArgument(
                f"You need to provide a name and emoji for the category separated by a comma (`name,emoji`). You only provided `{argument}`."
            )
        if not emoji == "⏣":
            if not emoji in UNICODE_EMOJI_ENGLISH.keys():
                try:
                    emoji = await EmojiConverter().convert(ctx, emoji)
                except EmojiNotFound:
                    raise BadArgument(
                        "You need to provide a unicode emoji or a valid custom emoji that the bot has access to."
                    )
        if len(name) > 32:
            raise BadArgument("The name of the category can't be longer than 32 characters.")

        emoji = str(emoji)
        exists, potential_name = await ctx.cog.cache._verify_guild_category(ctx.guild.id, name)
        if not exists:
            if not potential_name:
                return await ctx.cog.cache.get_dono_bank(name, ctx.guild.id, emoji=emoji)

            else:
                pred = MessagePredicate.yes_or_no(ctx)
                await ctx.send(
                    f"The category name you sent has a potential match already: `{potential_name}`."
                    " Send `yes` to use the match or `no` to force a new category."
                )
                try:
                    await ctx.bot.wait_for("message", check=pred, timeout=30)
                except asyncio.TimeoutError:
                    return await ctx.send("You took too long to respond.")

                if pred.result:
                    return await ctx.cog.cache.get_dono_bank(
                        potential_name, ctx.guild.id, emoji=emoji
                    )

                else:
                    return await ctx.cog.cache.get_dono_bank(
                        name, ctx.guild.id, emoji=emoji, force=True
                    )

        else:
            raise CategoryAlreadyExists(f"The category: `{name}` already exists.", name)


class flags(commands.Converter):
    """
    This is a custom flag parsing class made by skelmis (ethan) from menudocs."""

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


class MoniConverter(commands.Converter):
    async def convert(self, ctx, argument) -> int:
        try:
            total_stars = 0
            num_map = {"K": 1000, "M": 1000000, "B": 1000000000}
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
                if re.match(r"<@!?([0-9]+)>$", argument):
                    raise BadArgument(f"The mention comes after the amount.")
                raise BadArgument(f"Couldn't convert {argument} to a proper amount.")


class AmountOrItem(MoniConverter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            return await super().convert(ctx, argument)

        except Exception:
            category: DonoBank = ctx.dono_category
            if not category:
                raise BadArgument("No default category set.")

            items = category.items
            if not items:
                raise BadArgument(f"Couldn't convert {argument} to a proper item or amount.")

            match = await category.get_item(argument)
            if match:
                return match.amount
            else:
                raise BadArgument(f"Couldn't find an item with the name `{argument}`.")


class AmountRoleConverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        if argument.lower() == "none":
            return {}
        pairs = argument.split()
        rconv = RoleConverter().convert
        mconv = MoniConverter().convert
        final = {}
        for pair in pairs:
            amount, roles = pair.split(",")
            roles = roles.split(":")
            act_roles = []
            for role in roles:
                role = await rconv(ctx, role)
                if not await valid_role(ctx, role):
                    raise BadArgument(
                        "Roles to assign cannot be higher than the bot's or your top role nor can they be bot managed."
                    )
                act_roles.append(role)
            final.update({await mconv(ctx, amount): act_roles})

        return final


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
                result = await check(message.content)

            except Exception as e:
                await ctx.send(
                    f"The following error has occurred:\n{box(e, lang='py')}\nPlease try again. (The process has not stopped. Send your answer again)"
                )
                continue

            answer = result

        final[key] = answer

    return final


async def valid_role(ctx: commands.Context, role: discord.Role):
    my_position = role > ctx.me.top_role
    bot_managed = role.is_bot_managed()
    author_position = role > ctx.author.top_role
    integration = role.is_integration()
    default = role.is_default()

    if my_position or bot_managed or author_position or integration or default:
        return False

    return True


async def sortdict(argument, key_or_value="value"):
    if not isinstance(argument, dict):
        raise TypeError(f"`{argument}` is a `{type(argument)}`, not a dict.")

    else:
        _sorted = sorted(
            argument.items(),
            key=lambda x: x[1 if key_or_value.lower() == "value" else 0],
            reverse=True,
        )
        final = {}
        for i in _sorted:
            final[i[0]] = i[1]

        return final


# ______________ checks ______________


def setup_done():
    async def predicate(ctx):
        if not await ctx.cog.config.guild(ctx.guild).setup():
            return False
        return True

    return commands.check(predicate)


def is_dmgr():
    async def predicate(ctx):
        cog = ctx.cog
        data = await cog.config.guild(ctx.guild).managers()
        if data:
            for i in data:
                role = ctx.guild.get_role(int(i))
                if role and role in ctx.author.roles:
                    return True

        elif ctx.author.guild_permissions.administrator == True:
            return True

        elif await mod.is_mod_or_superior(ctx.bot, ctx.author) == True:
            return True

    return commands.check(predicate)


# ______________ AFA check funcs ______________


def manager_roles(ctx):
    async def predicate(answer: str):
        roleids = answer.split(",")
        rc = RoleConverter()

        roles = []

        for id in roleids:
            role = await rc.convert(ctx, id)

            roles.append(role)

        return roles

    return predicate


def channel_conv(ctx):
    async def predicate(answer: str):
        if answer.lower() == "none":
            return None
        return await TextChannelConverter().convert(ctx, answer)

    return predicate


def category_conv(ctx):
    async def predicate(answer: str):
        return await CategoryMaker().convert(ctx, answer)

    return predicate


def amountrole_conv(ctx):
    async def predicate(answer: str):
        return await AmountRoleConverter().convert(ctx, answer)

    return predicate
