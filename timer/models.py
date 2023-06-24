import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Coroutine, Dict, List, Optional

import discord
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .exceptions import TimerError

log = logging.getLogger("red.craycogs.Timer.models")


@dataclass
class TimerSettings:
    notify_users: bool
    emoji: str


class TimerObj:
    _tasks: Dict[int, asyncio.Task] = {}

    # haha ctrl C + Ctrl V from giveaways go brrrrrrrrr

    def __init__(self, **kwargs):
        gid, cid, e, bot = self.check_kwargs(kwargs)

        self.bot: Red = bot

        self.message_id: int = kwargs.get("message_id")
        self.channel_id: int = cid
        self.guild_id: int = gid
        self.name: str = kwargs.get("name", "A New Timer!")
        self.emoji: str = kwargs.get("emoji", ":tada:")
        self._entrants: set[int] = set(kwargs.get("entrants", {}) or {})
        self._host: int = kwargs.get("host")
        self.ends_at: datetime = e

    @property
    def cog(self):
        return self.bot.get_cog("Timer")

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self) -> Optional[discord.TextChannel]:
        return self.guild.get_channel(self.channel_id)

    @property
    def message(self) -> Coroutine[Any, Any, Optional[discord.Message]]:
        return self._get_message()

    @property
    def host(self) -> Optional[discord.Member]:
        return self.guild.get_member(self._host)

    @property
    def entrants(self) -> List[Optional[discord.Member]]:
        return [self.guild.get_member(x) for x in self._entrants]

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"

    @property
    def remaining_time(self):
        return self.ends_at - datetime.now(timezone.utc)

    @property
    def ended(self):
        return datetime.now(timezone.utc) > self.ends_at

    @property
    def edit_wait_duration(self):
        return (
            15
            if (secs := self.remaining_time.total_seconds()) <= 120
            else 60
            if secs < 300
            else 300
        )

    @property
    def json(self):
        """
        Return json serializable giveaways metadata."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "name": self.name,
            "emoji": self.emoji,
            "entrants": list(self._entrants),
            "host": self._host,
            "ends_at": self.ends_at.timestamp(),
        }

    @staticmethod
    def check_kwargs(kwargs: dict):
        if not (gid := kwargs.get("guild_id")):
            raise TimerError("No guild ID provided.")

        if not (cid := kwargs.get("channel_id")):
            raise TimerError("No channel ID provided.")

        if not (e := kwargs.get("ends_at")):
            raise TimerError("No ends_at provided for the giveaway.")

        if not (bot := kwargs.get("bot")):
            raise TimerError("No bot object provided.")

        return gid, cid, e, bot

    def __str__(self):
        return (
            f"<{self.__class__.__name__} "
            f"message_id={self.message_id} name={self.name} "
            f"emoji={self.emoji} time_remainin={cf.humanize_timedelta(timedelta=self.remaining_time)}>"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __hash__(self) -> int:
        return hash((self.message_id, self.channel_id))

    async def get_embed_description(self):
        return (
            f"React with {self.emoji} to be notified when the timer ends.\n"
            f"Remaining time: **{cf.humanize_timedelta(timedelta=self.remaining_time)}**"
            if (await self.cog.get_guild_settings(self.guild_id)).notify_users
            else f"Remaining time: **{cf.humanize_timedelta(timedelta=self.remaining_time)}**"
        )

    async def get_embed_color(self):
        return await self.bot.get_embed_color(self.channel)

    async def _get_message(self, message_id: int = None) -> Optional[discord.Message]:
        message_id = message_id or self.message_id
        msg = list(filter(lambda x: x.id == message_id, self.bot.cached_messages))
        if msg:
            return msg[0]
        try:
            msg = await self.channel.fetch_message(message_id)
        except Exception:
            msg = None
        return msg

    async def add_entrant(self, user_id: int):
        if user_id == self._host:
            return
        self._entrants.add(user_id)

    async def start(self):
        embed = (
            discord.Embed(
                title=f"Timer for **{self.name}**",
                description=await self.get_embed_description(),
                color=await self.get_embed_color(),
            )
            .set_thumbnail(url=getattr(self.guild.icon, "url", ""))
            .set_footer(text=f"Hosted by: {self.host}", icon_url=self.host.display_avatar.url)
        )

        msg: discord.Message = await self.channel.send(embed=embed)
        if (await self.cog.get_guild_settings(self.guild_id)).notify_users:
            await msg.add_reaction(self.emoji)
        self.message_id = msg.id

        self._tasks[self.message_id] = asyncio.create_task(self._start_edit_task())
        await self.cog.add_timer(self)

    async def _start_edit_task(self):
        try:
            while True:
                await asyncio.sleep(self.edit_wait_duration)

                if self.ended:
                    await self.end()
                    break

                msg = await self.message
                if not msg:
                    raise TimerError(
                        f"Couldn't find timer message with id {self.message_id}. Removing from cache."
                    )

                embed: discord.Embed = msg.embeds[0]

                embed.description = await self.get_embed_description()

                await msg.edit(embed=embed)

            return True

        except Exception as e:
            log.exception("Error when editing timer: ", exc_info=e)

    async def end(self):
        msg = await self.message
        if not msg:
            await self.cog.remove_timer(self)
            self._tasks[self.message_id].cancel()
            del self._tasks[self.message_id]
            raise TimerError(
                f"Couldn't find timer message with id {self.message_id}. Removing from cache."
            )

        embed: discord.Embed = msg.embeds[0]

        embed.description = "This timer has ended!"

        await msg.edit(embed=embed)

        notify = (await self.cog.get_guild_settings(self.guild_id)).notify_users

        await msg.reply(
            f"{self.host.mention} your timer for **{self.name}** has ended!\n" + self.jump_url
        )

        pings = (
            "\n".join((i.mention for i in self.entrants if i is not None))
            if self._entrants and notify
            else ""
        )

        if pings:
            for page in cf.pagify(pings, delims=[" "], page_length=2000):
                await msg.channel.send(page,delete_after=1)

        await self.cog.remove_timer(self)
        self._tasks[self.message_id].cancel()
        del self._tasks[self.message_id]

    @classmethod
    def from_json(cls, json: dict):
        gid, cid, e, bot = cls.check_kwargs(json)
        return cls(
            **{
                "message_id": json.get("message_id"),
                "channel_id": cid,
                "guild_id": gid,
                "bot": bot,
                "name": json.get("name"),
                "emoji": json.get("emoji", ":tada:"),
                "entrants": json.get("entrants", []),
                "host": json.get("host"),
                "ends_at": datetime.fromtimestamp(e, tz=timezone.utc),
            }
        )
