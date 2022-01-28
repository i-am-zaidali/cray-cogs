import datetime
import discord
from redbot.core.bot import Red


class UserNote:
    def __init__(self, bot, guild, user, author, content, date):
        self.bot: Red = bot
        self._guild: int = guild
        self._user: int = user
        self._author: int = author
        self.content: str = content
        self._date: float = int(date)

    def __str__(self):
        return f"""Content: ***{self.content}***
    Taken by: ***{self.author}***
    Taken on: <t:{self._date}:F>
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
        }