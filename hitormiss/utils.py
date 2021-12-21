import re

import discord
from redbot.core.utils.predicates import MessagePredicate


def no_special_characters(ctx):
    """
    I SAID NO F*CKING SPECIAL CHARACTERS."""

    def pred(s, message: discord.Message):
        if not ctx.author == message.author and ctx.channel == message.channel:
            return False
        regex = re.compile(r"[@_!#$%^&*()<>?/\|}{~:]")
        if not regex.search(message.content):
            s.result = message.content
            return True

        else:
            s.result = None
            return False

    return MessagePredicate(pred)


def is_lt(lt: int, ctx):
    def pred(s, message: discord.Message):
        if not ctx.author == message.author and ctx.channel == message.channel:
            return False
        if message.content.isdigit() and int(message.content) <= lt:
            s.result = int(message.content)
            return True
        else:
            s.result = None
            return False

    return MessagePredicate(pred)
