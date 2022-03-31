import asyncio
import enum
import datetime
import time
from typing import List, Union

import discord
from discord_components import Button, ButtonStyle, DiscordComponents, Interaction
from redbot.core import commands
from redbot.core.bot import Red


class NoteType(enum.Enum):
    DonationNote = 1
    RegularNote = 2


class UserNote:
    def __init__(self, bot, guild, user, author, content, date, type = None):
        self.bot: Red = bot
        self._guild: int = guild
        self._user: int = user
        self._author: int = author
        self.content: str = content
        self._date: float = int(date)
        self.type: NoteType = NoteType[type] if type else NoteType.RegularNote

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
            "type": self.type.name
        }


class ButtonPaginator:
    """
    A custom paginator class that uses buttons :D"""

    def __init__(
        self,
        client: DiscordComponents,
        context: commands.Context,
        contents: Union[List[str], List[discord.Embed]],
        timeout: int = 30,
    ):
        self.client = client
        self.bot = self.client.bot
        self.timeout = timeout
        self.user = context.author
        self.channel = context
        self.contents = contents
        self.index = 0
        if not isinstance(contents[0], (str, discord.Embed)):
            raise RuntimeError("Content must be of type str or discord.Embed.")
        if not all(isinstance(x, discord.Embed) for x in contents) and not all(
            isinstance(x, str) for x in contents
        ):
            raise RuntimeError("All pages must be of the same type")

        if self.timeout:
            self.clicks = [time.time()]

            self.loop = self.bot.loop
            if len(self.contents) > 1:
                self.loop.create_task(self.deactivate_components_on_timeout())

    async def deactivate_components_on_timeout(self):
        if self.timeout:
            while True:
                if self.clicks:
                    l = len(self.clicks) - 1
                    if (time.time() - self.clicks[l]) >= self.timeout:
                        await self.cancel_pag()
                        return
                await asyncio.sleep(5)
                continue
        else:
            return

    def get_components(self):
        if len(self.contents) == 1:
            return []
        elif len(self.contents) < 3:
            return [
                [
                    self.client.add_callback(
                        Button(style=ButtonStyle.blue, emoji="◀️"),
                        self.button_left_callback,
                    ),
                    Button(
                        label=f"Page {self.index + 1}/{len(self.contents)}",
                        disabled=True,
                    ),
                    self.client.add_callback(
                        Button(style=ButtonStyle.blue, emoji="▶️"),
                        self.button_right_callback,
                    ),
                    self.client.add_callback(
                        Button(style=ButtonStyle.red, emoji="❎"), self.cross_callback
                    ),
                ]
            ]
        return [
            [
                self.client.add_callback(
                    Button(style=ButtonStyle.red, emoji="◀️"), self.ff_left_callback
                ),
                self.client.add_callback(
                    Button(style=ButtonStyle.blue, emoji="⬅"),
                    self.button_left_callback,
                ),
                Button(
                    label=f"Page {self.index + 1}/{len(self.contents)}",
                    disabled=True,
                ),
                self.client.add_callback(
                    Button(style=ButtonStyle.blue, emoji="➡️"),
                    self.button_right_callback,
                ),
                self.client.add_callback(
                    Button(style=ButtonStyle.red, emoji="▶️"), self.ff_right_callback
                ),
            ],
            [
                self.client.add_callback(
                    Button(style=ButtonStyle.red, emoji="❎"), self.cross_callback
                )
            ],
        ]

    async def start(self):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]
        self.msg = await self.channel.send(
            content=content, embed=embed, components=self.get_components()
        )

    async def select_callback(self, inter: Interaction):
        self.index = int(inter.values[0])
        await inter.edit_origin(
            content=self.contents[self.index], components=self.get_components()
        )

    def valid_inter(self, inter: Interaction):
        return inter.author == self.user

    async def button_left_callback(self, inter: Interaction):
        if not self.valid_inter(inter):
            return
        if self.index == 0:
            self.index = len(self.contents) - 1
        else:
            self.index -= 1

        await self.button_callback(inter)

    async def button_right_callback(self, inter: Interaction):
        if not self.valid_inter(inter):
            return
        if self.index == len(self.contents) - 1:
            self.index = 0
        else:
            self.index += 1

        await self.button_callback(inter)

    async def ff_right_callback(self, inter: Interaction):
        if not self.valid_inter(inter):
            return
        self.index = len(self.contents) - 1

        await self.button_callback(inter)

    async def ff_left_callback(self, inter: Interaction):
        if not self.valid_inter(inter):
            return
        self.index = 0

        await self.button_callback(inter)

    async def cross_callback(self, inter: Interaction):
        if not self.valid_inter(inter):
            return
        await self.cancel_pag()

    async def button_callback(self, inter: Interaction):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]
        self.msg = await inter.edit_origin(
            content=content, embed=embed, components=self.get_components()
        )
        self.clicks.append(time.time())

    async def cancel_pag(self):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]
        await self.msg.edit(content=content, embed=embed, components=[])
