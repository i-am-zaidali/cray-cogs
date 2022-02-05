import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Coroutine, Counter, List, Optional

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from ..constants import giveaway_embed
from ..exceptions import GiveawayAlreadyEnded, GiveawayError, GiveawayNotStarted
from ..utils import Coordinate, SafeMember
from .flags import GiveawayFlags
from .guildsettings import apply_multi, get_guild_settings
from .requirements import Requirements


class GiveawayMeta:

    _tasks = []

    def __init__(self, **kwargs):
        mid, gid, cid, e, bot = self.check_kwargs(kwargs)

        self.bot: Red = bot

        self.message_id: int = mid
        self.channel_id: int = cid
        self.guild_id: int = gid
        self.prize: str = kwargs.get("prize", "Giveaway prize")
        self.requirements: Optional[Requirements] = kwargs.get("requirements")
        self.flags: Optional[GiveawayFlags] = kwargs.get("flags")
        self.emoji: str = kwargs.get("emoji", ":tada:")
        self.amount_of_winners: int = kwargs.get("amount_of_winners", 1)
        self._entrants: List[int] = kwargs.get("entrants") or []
        self._winners: List[int] = kwargs.get("winners") or []
        self._host: int = kwargs.get("host")
        self.starts_at: datetime = kwargs.get("starts_at", datetime.now(tz=timezone.utc))
        self.ends_at: datetime = e

    @property
    def cog(self):
        return self.bot.get_cog("Giveaways")

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
    def winners(self) -> List[Optional[discord.Member]]:
        return [self.guild.get_member(x) for x in self._winners]

    @property
    def entrants(self) -> List[Optional[discord.Member]]:
        return [self.guild.get_member(x) for x in self._entrants]

    @property
    def started(self) -> bool:
        return datetime.now(tz=timezone.utc) > self.starts_at

    @property
    def ended(self) -> bool:
        return datetime.now(tz=timezone.utc) > self.ends_at

    @property
    def json(self):
        """
        Return json serializable giveaways metadata."""
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "prize": self.prize,
            "amount_of_winners": self.amount_of_winners,
            "requirements": self.requirements.json if self.requirements else {},
            "flags": self.flags.json if self.flags else {},
            "emoji": self.emoji,
            "entrants": self._entrants,
            "winners": self._winners,
            "host": self._host,
            "ends_at": self.ends_at.timestamp(),
            "starts_at": self.starts_at.timestamp(),
        }

    @staticmethod
    def check_kwargs(kwargs: dict):
        if not (mid := kwargs.get("message_id")):
            raise GiveawayError("No message ID provided.")

        if not (gid := kwargs.get("guild_id")):
            raise GiveawayError("No guild ID provided.")

        if not (cid := kwargs.get("channel_id")):
            raise GiveawayError("No channel ID provided.")

        if not (e := kwargs.get("ends_at")):
            raise GiveawayError("No ends_at provided for the giveaway.")

        if not (bot := kwargs.get("bot")):
            raise GiveawayError("No bot object provided.")

        return mid, gid, cid, e, bot

    def __str__(self):
        return (
            f"<{self.__class__.__name__} "
            f"message_id={self.message_id} prize={self.prize} "
            f"emoji={self.emoji} winners={self.amount_of_winners} "
            f"ended={self.ended}>"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def get_winners_str(self):
        wcounter = Counter(self.winners)
        w = ""
        for k, v in wcounter.items():
            w += f"<@{k.id}> x {v}, " if v > 1 else f"<@{k.id}> "

        if not wcounter:
            w += "There were no winners."

        return w

    async def get_embed_color(self):
        set_color = (await get_guild_settings(self.guild.id)).color
        bot_color = await self.bot.get_embed_color(self.channel)

        return discord.Color(set_color) if set_color else bot_color

    async def _get_message(self) -> Optional[discord.Message]:
        msg = list(filter(lambda x: x.id == self.message_id, self.bot.cached_messages))
        if msg:
            return msg[0]
        try:
            msg = await self.channel.fetch_message(self.message_id)
        except Exception:
            msg = None
        return msg

    @classmethod
    def from_json(cls, json: dict):
        mid, gid, cid, e, bot = cls.check_kwargs(json)
        return cls(
            **{
                "message_id": mid,
                "channel_id": cid,
                "guild_id": gid,
                "bot": bot,
                "prize": json.get("prize", "Giveaway prize"),
                "amount_of_winners": json.get("amount_of_winners", 1),
                "requirements": Requirements.from_json(json.get("requirements", {})),
                "flags": GiveawayFlags.from_json(json.get("flags", {}), bot.get_guild(gid)),
                "emoji": json.get("emoji", ":tada:"),
                "entrants": json.get("entrants", []),
                "winners": json.get("winners", []),
                "host": json.get("host"),
                "ends_at": datetime.fromtimestamp(e, tz=timezone.utc),
                "starts_at": datetime.fromtimestamp(json.get("starts_at"), tz=timezone.utc),
            }
        )


class Giveaway(GiveawayMeta):
    def __init__(
        self,
        *,
        bot: Red,
        message_id: int = None,
        channel_id: int = None,
        guild_id: int = None,
        requirements: Requirements = None,
        flags: GiveawayFlags = None,
        prize: str = None,
        host: str = None,
        amount_of_winners: int = None,
        emoji: str = None,
        starts_at: datetime = datetime.now(tz=timezone.utc),
        ends_at: datetime = None,
        entrants: list = None,
        winners: list = None,
    ) -> None:

        super().__init__(
            bot=bot,
            message_id=message_id,
            channel_id=channel_id,
            guild_id=guild_id,
            prize=prize,
            requirements=requirements,
            flags=flags,
            emoji=emoji,
            entrants=entrants,
            winners=winners,
            host=host,
            ends_at=ends_at,
            starts_at=starts_at,
            amount_of_winners=amount_of_winners,
        )

        if self.starts_at > datetime.now(timezone.utc):
            self._tasks.append(self.bot.loop.create_task(self._wait_until_start()))

        if self.flags.message_count or self.requirements.messages:
            self._message_cache = {}

    async def _wait_until_start(self):
        while True:
            if self.starts_at > datetime.now(timezone.utc):
                await asyncio.sleep(15)
                continue

            await self.start()
            break

    async def hdm(self, message):
        host = self.host
        jump_url = message.jump_url
        prize = self.prize
        winners = self.winners
        winners = (
            f"The winners are: {humanize_list([getattr(m, 'mention', '') for m in winners])}"
            if winners
            else "There were no winners."
        )
        if host:
            try:
                embed = discord.Embed(
                    title="Your giveaway has ended!",
                    description=f"Your giveaway for {prize} has ended.\n{winners}\n\nClick [here]({jump_url}) to jump to the giveaway.",
                    color=discord.Color.random(),
                )
                embed.set_thumbnail(url=self.guild.icon_url)
                await host.send(embed=embed)

            except discord.HTTPException:
                return False

    async def wdm(self, message):
        winners = self.winners
        jump_url = message.jump_url
        prize = self.prize
        winners = Counter(winners)
        for winner in winners.keys():
            if winner:
                try:
                    embed = discord.Embed(
                        title="Congratulations!",
                        description=f"You have won the giveaway for `{prize}` in **__{self.guild}__**.\nClick [here]({jump_url}) to jump to the giveaway.",
                        color=discord.Color.random(),
                    ).set_thumbnail(url=self.guild.icon_url)
                    await winner.send(embed=embed)

                except discord.HTTPException:
                    return False

    async def create_embed(self) -> discord.Embed:
        embed = giveaway_embed.copy()

        timestamp_str = (
            f"<t:{int(self.ends_at.timestamp())}:R> (<t:{int(self.ends_at.timestamp())}:f>)"
        )

        embed.title = embed.title.format(prize=self.prize)
        embed.description = embed.description.format(
            emoji=self.emoji, host=self.host.mention, timestamp=timestamp_str
        )
        embed.timestamp = self.flags.ends_in or self.ends_at
        embed.color = await self.get_embed_color()
        embed._footer["text"] = embed._footer["text"].format(winners=self.amount_of_winners)

        if self.flags.donor:
            embed.add_field(name="**Donor:**", value=f"{self.flags.donor.mention}", inline=False)

        if self.flags.no_defaults:
            requirements = self.requirements.no_defaults(True)  # ignore defaults.

        if not self.flags.no_defaults:
            requirements = self.requirements.no_defaults()  # defaults will be used!!!

        if self.flags.message_count != 0:
            requirements.messages = self.flags.message_count

        self.requirements = requirements

        req_str = await requirements.get_str(self.guild_id)
        if not requirements.null and not req_str == "":
            embed.add_field(name="Requirements:", value=req_str, inline=False)

        return embed

    async def verify_entry(self, member: discord.Member):
        message = await self.message
        if self.flags.no_donor and member.id == (self.flags.donor or self.host).id:
            return False, (
                f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                "You used the `--no-donor` flag which "
                "restricts you from joining your own giveaway."
            )

        if self.requirements.null:
            return True, ""

        else:
            requirements = self.requirements.as_role_dict(member.guild)

            if requirements["bypass"]:
                maybe_bypass = any([role in member.roles for role in requirements["bypass"]])
                if maybe_bypass:
                    return True, ""
                    # All the below requirements can be overlooked if user has bypass role.

            for key, value in requirements.items():
                if value:
                    if isinstance(value, list):
                        for i in value:
                            if key == "blacklist" and i in member.roles:
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    "You had a role that was blacklisted from this giveaway.\n"
                                    f"Blacklisted role: `{i.name}`"
                                )

                            elif key == "required" and i not in member.roles:
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    "You did not have the required role to join it.\n"
                                    f"Required role: `{i.name}`"
                                )

                    else:
                        user = {}
                        if key == "amari_level":
                            try:
                                user = await self.bot.amari.get_user(member.guild.id, member.id)
                            except:
                                raise
                            level = user.get("level", 0)
                            if int(level) < int(value):
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    f"You are amari level `{level}` which is `{value - level}` levels fewer than the required `{value}`."
                                )

                        elif key == "amari_weekly":
                            try:
                                user = await self.bot.amari.get_user(member.guild.id, member.id)
                            except:
                                pass
                            weeklyxp = user.get("weeklyExp", 0)
                            if int(weeklyxp) < int(value):
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    f"You have `{weeklyxp}` weekly amari xp which is `{value - weeklyxp}` "
                                    f"xp fewer than the required `{value}`."
                                )

                        elif key == "messages":
                            messages = self._message_cache.setdefault(member.id, 0)
                            if not messages >= value:
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    f"You have sent `{messages}` messages since the giveaway started "
                                    f"which is `{value - messages}` messages fewer than the required `{value}`."
                                )

            return True, ""

    async def add_entrant(self, member: discord.Member):
        result, statement = await self.verify_entry(member)
        if not result:
            embed = discord.Embed(
                title="Entry Invalidated!",
                description=statement,
                color=discord.Color.red(),
            ).set_thumbnail(url=member.guild.icon_url)
            try:
                await member.send(embed=embed)
            except discord.HTTPException:
                pass
            return False

        self._entrants.append(member.id)
        return True

    async def _handle_flags(self):
        flags = self.flags
        if flags.ends_in:
            self.ends_at = flags.ends_in

        if flags.channel:
            self.channel_id = flags.channel.id

        ping = flags.ping
        msg = flags.message
        thank = flags.thank

        settings = await get_guild_settings(self.guild_id)

        if ping:
            pingrole = settings.pingrole
            ping = (
                f"<@&{pingrole}>"
                if pingrole
                else f"No pingrole set. Use the `gset pingrole` command to add a pingrole."
            )

        kwargs = {"content": None, "embed": None}

        if ping:
            kwargs["content"] = ping

        if msg:
            kwargs["embed"] = discord.Embed(
                description=f"***Message***: {msg}", color=await self.get_embed_color()
            )

        if any((kwargs["content"], kwargs["embed"])):
            await self.channel.send(**kwargs)

        if thank:
            tmsg = settings.tmsg
            embed = discord.Embed(
                description=tmsg.format_map(
                    Coordinate(
                        donor=SafeMember(self.flags.donor or self.host),
                        prize=self.prize,
                    )
                ),
                color=await self.get_embed_color(),
            )
            await self.channel.send(embed=embed)

    async def start(self):
        if self.ended:
            raise GiveawayAlreadyEnded(
                "The Giveaway ({}) has already ended at {}".format(
                    self.message_id, self.time_to_end
                )
            )

        self.cog.remove_from_cache(self)  # remove the old giveaway id

        embed = await self.create_embed()

        settings = await get_guild_settings(self.guild_id)

        gmsg: discord.Message = await self.channel.send(settings.msg, embed=embed)
        await gmsg.add_reaction(self.emoji)

        self.message_id = gmsg.id
        self.cog.add_to_cache(self)

        await self._handle_flags()

    async def end(self, reason=None) -> "EndedGiveaway":
        if not self.started:
            raise GiveawayNotStarted(
                "The Giveaway ({}) has not started yet".format(self.message_id)
            )

        msg = await self.message
        if not msg:
            await self.channel.send(
                f"Can't find message with id: {self.message_id}. Removing id from active giveaways."
            )
            return EndedGiveaway.from_giveaway(
                self,
                "The giveaway message was either deleted or bot had no `read message/history` permissions.",
            )
        guild = self.guild
        settings = await get_guild_settings(guild.id)
        winners = self.amount_of_winners
        embed = msg.embeds[0]
        prize = self.prize
        host = self.host
        winnerdm = settings.winnerdm
        hostdm = settings.hostdm
        endmsg: str = settings.endmsg
        gmsg = msg
        entrants = self.entrants
        random.shuffle(entrants)
        if not self.flags.no_multi:
            entrants = await apply_multi(guild, entrants)
        link = gmsg.jump_url

        try:
            w_list = [random.choice(entrants) for _ in range(winners)]

        except IndexError:  # there were no entrants
            w_list = []

        if len(w_list) == 0 or winners == 0:
            embed = gmsg.embeds[0]
            embed.description = (
                f"This giveaway has ended.\nThere were 0 winners.\n**Host:** {host.mention}"
            )
            embed.set_footer(text=f"{guild.name} - Winners: {winners}", icon_url=guild.icon_url)
            await gmsg.edit(embed=embed)

            await gmsg.reply(
                f"The giveaway for ***{prize}*** has ended. There were 0 users who qualified for the prize."
                f"\nClick on my replied message to jump to the giveaway.\n"
                f"Or click on this link: {gmsg.jump_url}"
            )
            if hostdm == True:
                await self.hdm(gmsg)

            return EndedGiveaway.from_giveaway(self, reason)

        self._winners = [i.id for i in w_list]

        w = self.get_winners_str()

        formatdict = {"winner": w, "prize": prize, "link": link}

        embed: discord.Embed = gmsg.embeds[0]
        embed.color = discord.Color.red()
        embed.description = f"This giveaway has ended.\n**Winners:** {w}\n**Host:** {host.mention}"
        embed.set_footer(text=f"{guild.name} - Winners: {winners}", icon_url=guild.icon_url)
        await gmsg.edit(embed=embed)

        await gmsg.reply(endmsg.format_map(formatdict))

        if winnerdm == True:
            await self.wdm(gmsg)

        if hostdm == True:
            await self.hdm(gmsg)

        return EndedGiveaway.from_giveaway(self, reason)


class EndedGiveaway(GiveawayMeta):
    def __init__(
        self,
        *,
        bot: Red,
        message_id: int = None,
        channel_id: int = None,
        guild_id: int = None,
        requirements: Requirements = None,
        flags: GiveawayFlags = None,
        prize: str = None,
        host: str = None,
        amount_of_winners: int = None,
        emoji: str = None,
        starts_at: datetime = datetime.now(tz=timezone.utc),
        ends_at: datetime = None,
        entrants: list = None,
        winners: list = None,
        reason: str = None,
    ) -> None:

        super().__init__(
            bot=bot,
            message_id=message_id,
            channel_id=channel_id,
            guild_id=guild_id,
            prize=prize,
            requirements=requirements,
            flags=flags,
            emoji=emoji,
            entrants=entrants,
            winners=winners,
            host=host,
            ends_at=ends_at,
            starts_at=starts_at,
            amount_of_winners=amount_of_winners,
        )

        self.reason = reason

    @property
    def ended_at(self):
        return self.ends_at

    @property
    def json(self):
        json = super().json
        json.update(reason=self.reason)
        return json

    async def reroll(self, ctx: commands.Context, winners: int = None):
        gmsg = await self.message
        if not gmsg:
            await ctx.send("I couldn't find the giveaway message.")
            return
        winners = winners or 1
        entrants = self.entrants
        entrants = await apply_multi(self.guild, entrants)
        link = gmsg.jump_url

        if len(entrants) == 0:
            await gmsg.reply(
                f"There weren't enough entrants to determine a winner.\nClick on my replied message to jump to the giveaway."
            )
            return

        winner = [random.choice(entrants).mention for i in range(winners)]
        self._winners = winner

        w = self.get_winners_str()

        await gmsg.reply(
            f"Congratulations :tada:{w}:tada:. You are the new winner(s) for the giveaway below.\n{link}"
        )
        
    @classmethod
    def from_json(cls, json: dict):
        self = super().from_json(json)
        self.reason = json.get("reason")

    @classmethod
    def from_giveaway(cls, giveaway: Giveaway, reason=None):
        reason = reason or "Giveaway ended successfully."
        kwargs = giveaway.json
        kwargs.update(reason=reason, bot=giveaway.bot)
        return cls.from_json(kwargs)
