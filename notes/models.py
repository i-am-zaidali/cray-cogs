import datetime
import enum

import discord
from redbot.core.bot import Red

# import time
# from typing import List, Union


class NoteType(enum.Enum):
    DonationNote = 1
    RegularNote = 2


class UserNote:
    def __init__(self, bot, guild, user, author, content, date, type=None):
        self.bot: Red = bot
        self._guild: int = guild
        self._user: int = user
        self._author: int = author
        self.content: str = content
        self._date: float = int(date)
        self.type: NoteType = (
            NoteType[type]
            if isinstance(type, str)
            else type
            if isinstance(type, NoteType)
            else NoteType.RegularNote
        )

    def __str__(self):
        return f"""- Content: ***{self.content}***
- Taken by: ***{self.author}***
- Taken on: <t:{self._date}:F>
    """

    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self._guild)

    @property
    def user(self) -> discord.Member:
        return self.guild.get_member(self._user)

    @property
    def author(self) -> discord.Member:
        return self.guild.get_member(self._author)

    @property
    def date(self):
        return datetime.datetime.fromtimestamp(self._date)

    def to_dict(self):
        return {
            "user": self._user,
            "author": self._author,
            "content": self.content,
            "date": self._date,
            "type": self.type.name,
        }
