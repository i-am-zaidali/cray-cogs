import functools
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Coroutine, List, Optional, Union

import discord
from discord.ui import Button, View
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .exceptions import TimerError

if TYPE_CHECKING:
    from .timers import Timer

log = logging.getLogger("red.craycogs.Timer.models")


@dataclass
class TimerSettings:
    notify_users: bool
    emoji: str


class TimerView(View):
    def __init__(self, cog: "Timer", emoji=":tada:", disabled=False):
        super().__init__(timeout=None)
        self.bot = cog.bot
        self.cog = cog
        self.JTB = JoinTimerButton(emoji, self._callback, disabled)
        self.add_item(self.JTB)

    async def _callback(self, button: "JoinTimerButton", interaction: discord.Interaction):
        log.debug("callback called")
        cog: "Timer" = self.cog

        timer = await cog.get_timer(interaction.guild.id, interaction.message.id)
        if not timer:
            return await interaction.response.send_message(
                "This timer does not exist in my database. It might've been erased due to a glitch.",
                ephemeral=True,
            )

        elif not timer.remaining_seconds:
            await interaction.response.defer()
            return await timer.end()

        log.debug("timer exists")

        result = await timer.add_entrant(interaction.user.id)
        kwargs = {}

        if result:
            kwargs.update(
                {"content": f"{interaction.user.mention} you will be notfied when the timer ends."}
            )

        else:
            await timer.remove_entrant(interaction.user.id)
            kwargs.update(
                {
                    "content": f"{interaction.user.mention} you will no longer be notified for the timer."
                }
            )

        await interaction.response.send_message(**kwargs, ephemeral=True)


class JoinTimerButton(Button[TimerView]):
    def __init__(
        self,
        emoji: Optional[str],
        callback,
        disabled=False,
        custom_id="JOIN_TIMER_BUTTON",
    ):
        super().__init__(
            emoji=emoji,
            style=discord.ButtonStyle.green,
            disabled=disabled,
            custom_id=custom_id,
        )
        self.callback = functools.partial(callback, self)


class TimerObj:
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
    def cog(self) -> Optional["Timer"]:
        return self.bot.get_cog("Timer")

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)

    @property
    def channel(self) -> Optional[Union[discord.abc.GuildChannel, discord.Thread]]:
        assert self.guild is not None
        return self.guild.get_channel_or_thread(self.channel_id)

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
    def remaining_seconds(self):
        return self.ends_at - datetime.now(timezone.utc)

    @property
    def remaining_time(self):
        return self.remaining_seconds.total_seconds()

    @property
    def ended(self):
        return datetime.now(timezone.utc) > self.ends_at

    @property
    def edit_wait_duration(self):
        return (
            15
            if (secs := self.remaining_time.total_seconds()) <= 120
            else 60 if secs < 300 else 300
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
            f"Remaining time: **<t:{int(time.time() + self.remaining_time)}:R>** (<t:{int(time.time() + self.remaining_time)}:F>)\n"
            if (await self.cog.get_guild_settings(self.guild_id)).notify_users
            else f"Remaining time: **<t:{int(time.time() + self.remaining_time)}:R>** (<t:{int(time.time() + self.remaining_time)}:F>)\n"
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
        if user_id == self._host or user_id in self._entrants:
            return False
        self._entrants.add(user_id)
        return True

    async def remove_entrant(self, user_id: int):
        if user_id == self._host or user_id not in self._entrants:
            return False
        self._entrants.remove(user_id)
        return True

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

        kwargs = {
            "embed": embed,
        }
        if (await self.cog.get_guild_settings(self.guild_id)).notify_users:
            kwargs.update({"view": TimerView(self.cog, self.emoji, False)})

        msg: discord.Message = await self.channel.send(**kwargs)

        self.message_id = msg.id
        kwargs["view"].stop()

        await self.cog.add_timer(self)

    async def end(self):
        msg = await self.message
        if not msg:
            await self.cog.remove_timer(self)
            raise TimerError(
                f"Couldn't find timer message with id {self.message_id}. Removing from cache."
            )

        embed: discord.Embed = msg.embeds[0]

        embed.description = "This timer has ended!"

        settings = await self.cog.get_guild_settings(self.guild_id)

        view = TimerView(self.cog, settings.emoji, True)

        await msg.edit(embed=embed, view=view)

        notify = settings.notify_users

        rep = await msg.reply(
            f"{getattr(self.host, 'mention', f'{self._host} (host user not found)')} your timer for **{self.name}** has ended!\n"
            + self.jump_url
        )

        pings = (
            " ".join((i.mention for i in self.entrants if i is not None))
            if self._entrants and notify
            else ""
        )

        if pings:
            for page in cf.pagify(pings, delims=[" "], page_length=2000):
                await msg.channel.send(page, reference=rep.to_reference(fail_if_not_exists=False))

        await self.cog.remove_timer(self)

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
