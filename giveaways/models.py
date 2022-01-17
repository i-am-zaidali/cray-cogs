import random
import time
from collections import Counter
from datetime import datetime, timedelta
from enum import Enum
from functools import reduce
from typing import Dict, List, Optional, Union

import discord
from discord.ext.commands.converter import RoleConverter
from discord.ext.commands.errors import BadArgument, RoleNotFound
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta

from .util import Coordinate, is_valid_message


class EndReason(Enum):
    """
    The reason for ending a giveaway.
    """

    SUCCESS = "The giveaway ended on time successfully."
    ERRORED = "The giveaway ended due to the following error:\n```py\n{}\n```"
    CANCELLED = "The giveaway was cancelled by {}."


class Requirements(commands.Converter):
    """
    A wrapper for giveaway requirements."""

    __slots__ = ["required", "blacklist", "bypass", "amari_level", "amari_weekly", "messages"]

    def __init__(
        self,
        *,
        guild: discord.Guild = None,
        required: List[int] = [],
        blacklist: List[int] = [],
        bypass: List[int] = [],
        default_bl: List[int] = [],
        default_by: List[int] = [],
        amari_level: int = None,
        amari_weekly: int = None,
        messages: int = None,
    ):

        self.guild = guild  # guild object for role fetching
        self.required = required  # roles that are actually required
        self.blacklist = blacklist  # list of role blacklisted for this giveaway
        self.bypass = bypass  # list of roles bypassing this giveaway
        self.amari_level = amari_level  # amari level required for this giveaway
        self.amari_weekly = amari_weekly  # amari weekly required for this giveaway
        self.messages = (
            messages or 0
        )  # messages to be sent after the giveaway has started required for this giveaway

        self.default_bl = default_bl
        self.default_by = default_by

    async def get_str(self, ctx):
        final = ""
        show_defaults = await ctx.cog.config.get_guild(ctx.guild, "show_defaults")
        items = self.as_dict()
        if not show_defaults:
            default_by, default_bl = set(self.default_by), set(self.default_bl)
            bl = set(items["blacklist"])
            bl.difference_update(default_bl)
            by = set(items["bypass"])
            by.difference_update(default_by)
            items["blacklist"] = bl
            items["bypass"] = by
        for key, value in items.items():
            if value:
                if isinstance(value, int):
                    final += f"Required {key.replace('_', ' ').capitalize()}: {value:>4}"
                    continue
                final += (
                    f"*{key.capitalize()} Roles:*\t{humanize_list([f'<@&{i}>' for i in value])}\n"
                )
        return final

    def no_defaults(self, stat: bool = False):
        """
        Kinda a hacky take towards a class method but with access to self attributes
        Did this because this was supposed to be used as a typehint converter
        and we can't pass the --no-defaults flag through there so....

        The idea is to get a Requirements object and then use this method by passing the flag :thumbsup:"""
        if not stat:
            self.blacklist += self.default_bl
            self.bypass += self.default_by
            # del self.default_by
            # del self.default_bl lets not delete them now
            return self  # return self because nothing needs to be modified

        d = self.as_dict()
        d.update({"default_by": [], "default_bl": []})

        return self.__class__(**d)

    def no_amari_available(self):
        self.amari_level = None
        self.amari_weekly = None
        return True

    def verify_role(self, id) -> Optional[discord.Role]:
        role = self.guild.get_role(id)
        return role

    def as_dict(self):
        return {i: getattr(self, i) for i in self.__slots__}

    def as_role_dict(self) -> Dict[str, Union[List[discord.Role], discord.Role, int]]:
        org = self.as_dict()
        for k, v in (org.copy()).items():
            if isinstance(v, list):
                org[k] = [
                    self.verify_role(int(i)) for i in v if self.verify_role(int(i)) is not None
                ]

            else:
                r = self.verify_role(v)  # checking if its a role
                if not r:
                    org[k] = v  # replace with orginal value if its not a role
                else:
                    org[k] = r  # yay its a role

        return org  # return the dictionary with ids repalced with roles

    def items(self):
        return self.as_dict().items()

    @property
    def null(self):
        return all([not i for i in self.as_dict().values()])

    @classmethod
    async def convert(cls, ctx, arg: str):
        maybeid = arg
        try:
            if ";;" in arg:
                maybeid = arg.split(";;")
            elif "," in arg:
                arg = arg.strip()
                maybeid = arg.split(",")

        except:
            maybeid = arg

        data = {
            "blacklist": [],
            "bypass": [],
            "required": [],
            "default_by": [],
            "default_bl": [],
            "amari_level": None,
            "amari_weekly": None,
            "messages": 0,
        }
        new_bl = await ctx.command.cog.config.all_blacklisted_roles(ctx.guild)
        new_by = await ctx.command.cog.config.all_bypass_roles(ctx.guild)
        data["default_bl"] += new_bl
        data["default_by"] += new_by

        if isinstance(maybeid, str) and maybeid.lower() == "none":
            return cls(guild=ctx.guild, **data)

        if isinstance(maybeid, list):
            for i in maybeid:
                if not "[" in i:
                    try:
                        role = await RoleConverter().convert(ctx, i)
                    except RoleNotFound:
                        raise BadArgument("Role with id: {} not found.".format(i))
                    data["required"].append(role.id)

                else:
                    _list = i.split("[")
                    if "blacklist" in _list[1]:
                        try:
                            role = await RoleConverter().convert(ctx, _list[0])
                        except RoleNotFound:
                            raise BadArgument(f"Role with id: {_list[0]} was not found.")
                        data["blacklist"].append(role.id)
                    elif "bypass" in _list[1]:
                        try:
                            role = await RoleConverter().convert(ctx, _list[0])
                        except RoleNotFound:
                            raise BadArgument(f"Role with id: {_list[0]} was not found.")
                        data["bypass"].append(role.id)
                    elif "alevel" in _list[1] or "alvl" in _list[1]:
                        data["amari_level"] = int(_list[0])
                    elif "aweekly" in _list[1] or "aw" in _list[1]:
                        data["amari_weekly"] = int(_list[0])

        else:
            if not "[" in maybeid:
                role = await RoleConverter().convert(ctx, maybeid)
                if not role:
                    raise BadArgument("Role with id: {} not found.".format(maybeid))
                data["required"].append(role.id)

            else:
                _list = maybeid.split("[")
                if "blacklist" in _list[1]:
                    try:
                        role = await RoleConverter().convert(ctx, _list[0])
                    except RoleNotFound:
                        raise BadArgument(f"Role with id: {_list[0]} was not found.")
                    if role.id in data["default_bl"]:
                        raise BadArgument(
                            f"Role `@{role.name}` is already blacklisted by default."
                        )
                    data["blacklist"].append(role.id)
                elif "bypass" in _list[1]:
                    try:
                        role = await RoleConverter().convert(ctx, _list[0])
                    except RoleNotFound:
                        raise BadArgument(f"Role with id: {_list[0]} was not found.")
                    if role.id in data["default_by"]:
                        raise BadArgument(f"Role `@{role.name}` is already bypassing by default.")
                    data["bypass"].append(role.id)
                elif "alevel" in _list[1] or "alvl" in _list[1] or "amarilevel" in _list[1]:
                    data["amari_level"] = int(_list[0])
                elif "aweekly" in _list[1] or "aw" in _list[1] or "amariweekly" in _list[1]:
                    data["amari_weekly"] = int(_list[0])
                elif "messages" in _list[1] or "msgs" in _list[1]:
                    data["messages"] = int(_list[0])
        return cls(guild=ctx.guild, **data)


class BaseGiveaway:
    """
    Just a base wrapper for giveaways."""

    def __init__(
        self,
        bot,
        cog,
        prize=None,
        time=None,
        host=None,
        channel=None,
        requirements=None,
        winners=None,
        **kwargs,
    ) -> None:
        self.bot: Red = bot
        self.cog = cog
        self.prize: str = prize
        self._time: int = time
        self._host: int = host
        self._channel: int = channel
        self._guild: Optional[int] = kwargs.get("guild", None)
        self.requirements: Requirements = requirements
        if self.requirements.messages != 0:
            self._message_cache = kwargs.get("message_counter") or Counter()
            cd = kwargs.get("message_cooldown", 0)
            self._message_cooldown = commands.CooldownMapping.from_cooldown(
                1, cd, commands.BucketType.guild
            )
        self.winners: int = winners

    def __getitem__(self, key):
        attr = getattr(self, key, None)
        if not attr:
            raise KeyError(f"{key} does not exist.")

        return attr

    def __str__(self):
        return f"<{self.__class__.__name__} Prize={self.prize} Host={self.host} Message={getattr(self, 'message_id', None)} >"

    def __repr__(self):
        return str(self)

    @property
    def host(self) -> discord.User:
        return self.bot.get_user(self._host)

    @property
    def channel(self) -> discord.TextChannel:
        return (
            self.bot.get_channel(self._channel)
            if not self._guild
            else self.guild.get_channel(self._channel)
        )

    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self._guild) if self._guild else None

    @property
    def remaining_time(self) -> int:
        if self._time > int(time.time()):
            return self._time - int(time.time())
        else:
            return 0

    async def verify_entry(self, entry: discord.Member):
        message = await self.get_message()
        if not self.donor_can_join and entry.id == self._donor:
            return False, (
                f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                "You used the `--no-donor` flag which "
                "restricts you from joining your own giveaway."
            )

        if self.requirements.null:
            return True

        else:
            requirements = self.requirements.as_role_dict()

            if requirements["bypass"]:
                maybe_bypass = any([role in entry.roles for role in requirements["bypass"]])
                if maybe_bypass:
                    return True  # All the below requirements can be overlooked if user has bypass role.

            for key, value in requirements.items():
                if value:
                    if isinstance(value, list):
                        for i in value:
                            if key == "blacklist" and i in entry.roles:
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    "You had a role that was blacklisted from this giveaway.\n"
                                    f"Blacklisted role: `{i.name}`"
                                )

                            elif key == "required" and i not in entry.roles:
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    "You did not have the required role to join it.\n"
                                    f"Required role: `{i.name}`"
                                )

                    else:
                        user = None
                        if key == "amari_level":
                            try:
                                user = await self.cog.amari.getGuildUser(entry.id, entry.guild.id)
                            except:
                                pass
                            level = getattr(user, "level", 0)  # int(user.level) if user else 0
                            if int(level) < int(value):
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    f"You are amari level `{level}` which is `{value - level}` levels fewer than the required `{value}`."
                                )

                        elif key == "amari_weekly":
                            try:
                                user = await self.cog.amari.getGuildUser(entry.id, entry.guild.id)
                            except:
                                pass
                            weeklyxp = getattr(
                                user, "weeklyxp", 0
                            )  # int(user.weeklyxp) if user else 0
                            if int(weeklyxp) < int(value):
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    f"You have `{weeklyxp}` weekly amari xp which is `{value - weeklyxp}` "
                                    f"xp fewer than the required `{value}`."
                                )

                        elif key == "messages":
                            messages = self._message_cache.setdefault(entry.id, 0)
                            if not messages >= value:
                                return False, (
                                    f"Your entry for [this]({message.jump_url}) giveaway has been removed.\n"
                                    f"You have sent `{messages}` messages since the giveaway started "
                                    f"which is `{value - messages}` messages fewer than the required `{value}`."
                                )

            return True

    def to_dict(self):
        raise NotImplementedError()  # this method must be implemented by the subclasses


class Giveaway(BaseGiveaway):
    """
    A class wrapper for a giveaway which handles the ending of a giveaway and stores all its necessary attributes."""

    def __init__(
        self,
        bot: Red,
        cog,
        time: int = int(time.time()),
        host: int = None,
        prize: str = None,
        channel: int = None,
        message: int = None,
        requirements: Union[Requirements, Dict[str, List[int]]] = None,
        winners: int = 1,
        emoji: str = None,
        use_multi: bool = True,
        donor: Optional[int] = None,
        donor_can_join: bool = True,
        **kwargs,
    ):
        super().__init__(bot, cog, prize, time, host, channel, requirements, winners, **kwargs)
        self.message_id = message
        self.emoji = emoji or "🎉"
        self.use_multi = use_multi
        self._donor = donor or self._host
        self.donor_can_join = donor_can_join

        self.next_edit = self.get_next_edit_time()

    def __hash__(self) -> int:
        return self.message_id

    @property
    def donor(self) -> discord.Member:
        return self.guild.get_member(self._donor)

    async def get_message(self) -> discord.Message:
        msg = list(
            filter(lambda x: x.id == self.message_id, self.bot.cached_messages)
        )  # i mean, if its cached, why waste an api request right?
        if msg:
            return msg[0]
        try:
            msg = await self.channel.fetch_message(self.message_id)
        except Exception:
            msg = None
        return msg

    def get_next_edit_time(self):
        if not (t := self.remaining_time) == 0:
            if t < 60:
                return None  # no edit if its within a minute of ending
            elif t >= 1200:
                return (
                    time.time() + 600
                )  # edit every half an hour if its longer than half an hour.
            elif t >= 300:
                return (
                    time.time() + 60
                )  # its longer than 5 minutes but less than half an hour, edit it every minute.

            return (
                time.time() + 60
            )  # middle case, its not greater than 5 minutes but greater than a minute.

    async def hdm(self, host, jump_url, prize, winners):
        member = await self.bot.fetch_user(host)
        if member:
            try:
                embed = discord.Embed(
                    title="Your giveaway has ended!",
                    description=f"Your giveaway for {prize} has ended.\n{f'The winners are: {winners}' if winners != 'None' else 'There are no winners'}\n\nClick [here]({jump_url}) to jump to the giveaway.",
                    color=discord.Color.random(),
                )
                embed.set_thumbnail(url=self.guild.icon_url)
                await member.send(embed=embed)

            except discord.HTTPException:
                return False

    async def wdm(self, winners, jump_url, prize):
        winners = Counter(winners)
        # winners = [k for k, v in winners.items()]
        for winner in winners.keys():
            if winner:
                try:
                    embed = discord.Embed(
                        title="Congratulations!",
                        description=f"You have won a giveaway for `{prize}` in **__{self.guild}__**.\nClick [here]({jump_url}) to jump to the giveaway.",
                        color=discord.Color.random(),
                    ).set_thumbnail(url=self.guild.icon_url)
                    await winner.send(embed=embed)

                except discord.HTTPException:
                    return False

    async def edit_timer(self):
        if not (t := self.next_edit) or not await self.cog.config.get_guild_timer(self.guild):
            return

        if t > time.time():
            return

        message = await self.get_message()
        embed: discord.Embed = message.embeds[0]
        timer_pos = embed.description.find("in") + 3
        embed.description = embed.description[:timer_pos] + humanize_timedelta(
            seconds=self.remaining_time
        )
        await message.edit(embed=embed)
        self.next_edit = self.get_next_edit_time()

    async def end(self, canceller=None) -> "EndedGiveaway":
        end_data = {
            "bot": self.bot,
            "cog": self.cog,
            "message": self.message_id,
            "channel": self._channel,
            "host": self._host,
            "prize": self.prize,
            "requirements": self.requirements,
            "winnersno": self.winners,
        }
        msg = await self.get_message()
        if not msg:
            await self.channel.send(
                f"Can't find message with id: {self.message_id}. Removing id from active giveaways."
            )
            self.cog.giveaway_cache.remove(self)
            end_data.update(
                {
                    "winnerslist": [],
                    "reason": EndReason.ERRORED.value.format(
                        f"Message with id {self.message_id} not found."
                    ),
                }
            )
            ended = EndedGiveaway(**end_data)
            self.cog.ended_cache.append(ended)
            return ended
        guild = self.guild
        winners = self.winners
        embed = msg.embeds[0]
        prize = self.prize
        host = self._host
        winnerdm = await self.cog.config.dm_winner(guild)
        hostdm = await self.cog.config.dm_host(guild)
        endmsg: str = await self.cog.config.get_guild_endmsg(guild)
        channel = msg.channel
        gmsg = msg
        entrants = (
            await gmsg.reactions[
                gmsg.reactions.index(
                    reduce(
                        lambda x, y: x
                        if str(x.emoji) == self.emoji
                        else y
                        if str(y.emoji) == self.emoji
                        else None,
                        gmsg.reactions,
                    )
                )
            ]
            .users()
            .flatten()
        )
        random.shuffle(entrants)
        try:
            entrants.pop(entrants.index(guild.me))
        except:
            pass
        if self.use_multi:
            entrants = await self.cog.config.get_list_multi(guild, entrants)
        link = gmsg.jump_url

        w_list = []
        for i in entrants:
            i = guild.get_member(i.id)
            if not len(w_list) == winners and not isinstance(await self.verify_entry(i), tuple):
                w_list.append(i)

        if len(w_list) == 0 or winners == 0:
            embed = gmsg.embeds[0]
            embed.description = (
                f"This giveaway has ended.\nThere were 0 winners.\n**Host:** <@{host}>"
            )
            embed.set_footer(text=f"{guild.name} - Winners: {winners}", icon_url=guild.icon_url)
            await gmsg.edit(embed=embed)

            await gmsg.reply(
                f"The giveaway for ***{prize}*** has ended. There were 0 users who qualified for the prize."
                f"\nClick on my replied message to jump to the giveaway.\n"
                f"Or click on this link: {gmsg.jump_url}"
            )
            if hostdm == True:
                await self.hdm(host, gmsg.jump_url, prize, "None")

            end_data.update({"winnerslist": [], "ended_at": datetime.now()})
            if not canceller:
                end_data.update({"reason": EndReason.SUCCESS.value})
            else:
                end_data.update({"reason": EndReason.CANCELLED.value.format(canceller)})

            self.cog.giveaway_cache.remove(self)
            ended = EndedGiveaway(**end_data)
            self.cog.ended_cache.append(ended)
            return ended

        w = ""

        wcounter = Counter(w_list)
        for k, v in wcounter.items():
            w += f"<@{k.id}> x {v}, " if v > 1 else f"<@{k.id}> "

        formatdict = {"winner": w, "prize": prize, "link": link}

        embed: discord.Embed = gmsg.embeds[0]
        embed.color = discord.Color.red()
        embed.description = f"This giveaway has ended.\n**Winners:** {w}\n**Host:** <@{host}>"
        embed.set_footer(text=f"{guild.name} - Winners: {winners}", icon_url=guild.icon_url)
        await gmsg.edit(embed=embed)

        await gmsg.reply(endmsg.format_map(formatdict))

        if winnerdm == True:
            await self.wdm(w_list, gmsg.jump_url, prize)

        if hostdm == True:
            await self.hdm(host, gmsg.jump_url, prize, w)

        self.cog.giveaway_cache.remove(self)
        end_data.update({"winnerslist": [i.id for i in w_list], "ended_at": datetime.now()})
        if not canceller:
            end_data.update({"reason": EndReason.SUCCESS.value})
        else:
            end_data.update({"reason": EndReason.CANCELLED.value.format(canceller)})
        ended = EndedGiveaway(**end_data)
        self.cog.ended_cache.append(ended)
        return ended

    def to_dict(self) -> dict:
        data = {
            "time": self._time,
            "guild": self.guild.id,
            "host": self._host,
            "channel": self._channel,
            "message": self.message_id,
            "emoji": self.emoji,
            "winners": self.winners,
            "prize": self.prize,
            "requirements": self.requirements.as_dict(),
            "use_multi": self.use_multi,
            "donor": self._donor,
            "donor_can_join": self.donor_can_join,
        }
        if getattr(self, "_message_cache", None):
            data["message_counter"] = self._message_cache
        return data


class EndedGiveaway(BaseGiveaway):
    def __init__(
        self,
        bot,
        cog,
        host,
        channel,
        message,
        winnersno,
        winnerslist,
        prize,
        requirements,
        reason,
        **kwargs,
    ) -> None:
        super().__init__(
            bot, cog, prize, None, host, channel, requirements, winnersno, **kwargs
        )  # winners no is number of winners and list is a list of winners.
        self.message_id = message
        self._winnerlist = winnerslist
        self._ended_at = kwargs.get(
            "ended_at"
        )  # i mean come on we need to replace this with something
        self.reason: str = reason

    def __hash__(self) -> int:
        return hash(self.message_id)

    async def get_message(self) -> Optional[discord.Message]:
        msg = self.bot._connection._get_message(
            self.message_id
        )  # i mean, if its cached, why waste an api request right?
        if not msg or not is_valid_message(msg):  # check if message is valid lol.
            try:
                msg = await self.channel.fetch_message(self.message_id)
            except Exception:
                msg = None
        return msg

    async def reroll(self, ctx: commands.Context, winners: int = 1):
        emoji = await self.cog.config.get_guild_emoji(ctx.guild)
        gmsg = await self.get_message()
        if not gmsg:
            return await ctx.send("I couldn't find the giveaway message.")
        entrants = (
            await gmsg.reactions[
                gmsg.reactions.index(
                    reduce(
                        lambda x, y: x
                        if str(x.emoji) == emoji
                        else y
                        if str(y.emoji) == emoji
                        else None,
                        gmsg.reactions,
                    )
                )
            ]
            .users()
            .flatten()
        )
        try:
            entrants.pop(entrants.index(ctx.guild.me))
        except:
            pass
        entrants = await self.cog.config.get_list_multi(ctx.guild, entrants)
        link = gmsg.jump_url

        if len(entrants) == 0:
            await gmsg.reply(
                f"There weren't enough entrants to determine a winner.\nClick on my replied message to jump to the giveaway."
            )
            return

        winner = {random.choice(entrants).mention for i in range(winners)}

        await gmsg.reply(
            f"Congratulations :tada:{humanize_list(list(winner))}:tada:. You are the new winners for the giveaway below.\n{link}"
        )

    async def ended_at(self):
        if not self._ended_at:
            if not (msg := await self.get_message()):
                self._ended_at = "Not available."

            else:
                timestamp: datetime = msg.embeds[0].timestamp
                secs = int(timestamp.timestamp)
                self._ended_at = f"<t:{secs}:R>"

        return self._ended_at

    @property
    def winnerslist(self):
        return [self.guild.get_member(i) for i in self._winnerlist]

    def to_dict(self):
        return {
            "message": self.message_id,
            "channel": self._channel,
            "guild": getattr(self.guild, "id", None),
            "host": self._host,
            "prize": self.prize,
            "requirements": self.requirements.as_dict(),
            "winnersno": self.winners,
            "winnerslist": self._winnerlist,
            "reason": self.reason,
            "ended_at": self._ended_at,
        }


class PendingGiveaway(BaseGiveaway):
    def __init__(
        self,
        bot,
        cog,
        host,
        _time,
        winners,
        requirements,
        prize,
        flags,
        **kwargs,
    ):
        super().__init__(bot, cog, prize, _time, host, flags.get("channel"), requirements, winners)
        self.flags: dict = flags
        self.start: int = flags.get("starts_in")

    @property
    def remaining_time_to_start(self):
        if self.start < time.time():
            return 0
        return self.start - time.time()

    def __hash__(self) -> int:
        return hash((self.prize, self._time, self._host, self._channel, self.winners))

    async def start_giveaway(self):
        emoji = await self.cog.config.get_guild_emoji(self.guild)
        endtime = datetime.now() + timedelta(seconds=self.remaining_time)
        embed = discord.Embed(
            title=self.prize.center(len(self.prize) + 4, "*"),
            description=(
                f"React with {emoji} to enter\n"
                f"Host: {self.host.mention}\n"
                f"Ends {f'<t:{int(time.time()+self.remaining_time)}:R>' if not await self.cog.config.get_guild_timer(self.guild) else f'in {humanize_timedelta(seconds=self.remaining_time)}'}\n"
            ),
            timestamp=endtime,
        ).set_footer(text=f"Winners: {self.winners} | ends : ", icon_url=self.guild.icon_url)

        message = await self.cog.config.get_guild_msg(self.guild)

        # flag handling below!!

        if donor := self.flags.get("donor"):
            embed.add_field(name="**Donor:**", value=f"{donor.mention}", inline=False)
        messagable = self.channel
        ping = self.flags.get("ping")
        no_multi = self.flags.get("no_multi")
        no_defaults = self.flags.get("no_defaults")
        donor_join = not self.flags.get("no_donor")
        msg = self.flags.get("msg")
        thank = self.flags.get("thank")
        requirements = self.requirements
        if no_defaults:
            requirements = self.requirements.no_defaults(True)  # ignore defaults.

        if not no_defaults:
            requirements = self.requirements.no_defaults()  # defaults will be used!!!

        if not requirements.null:
            embed.add_field(name="Requirements:", value=str(requirements), inline=False)

        gembed = await messagable.send(message, embed=embed)
        await gembed.add_reaction(emoji)

        if ping:
            pingrole = await self.cog.config.get_pingrole(self.guild)
            ping = (
                pingrole.mention
                if pingrole
                else f"No pingrole set. Use `{(await self.bot.get_valid_prefixes(self.guild))[0]}gset pingrole` to add a pingrole"
            )

        if msg and ping:
            membed = discord.Embed(
                description=f"***Message***: {msg}", color=discord.Color.random()
            )
            await messagable.send(
                ping, embed=membed, allowed_mentions=discord.AllowedMentions(roles=True)
            )
        elif ping and not msg:
            await messagable.send(ping, allowed_mentions=discord.AllowedMentions(roles=True))
        elif msg and not ping:
            membed = discord.Embed(
                description=f"***Message***: {msg}", color=discord.Color.random()
            )
            await messagable.send(embed=membed)
        if thank:
            tmsg: str = await self.cog.config.get_guild_tmsg(self.guild)
            embed = discord.Embed(
                description=tmsg.format_map(
                    Coordinate(
                        donor=SafeMember(donor) if donor else SafeMember(self.host),
                        prize=self.prize,
                    )
                ),
                color=0x303036,
            )
            await messagable.send(embed=embed)

        data = {
            "donor": donor.id if donor else None,
            "donor_can_join": donor_join,
            "use_multi": not no_multi,
            "message": gembed.id,
            "emoji": emoji,
            "channel": self._channel,
            "cog": self.cog,
            "time": self._time,
            "winners": self.winners,
            "requirements": requirements,
            "prize": self.prize,
            "host": self._host,
            "bot": self.bot,
        }
        giveaway = Giveaway(**data)
        self.cog.giveaway_cache.append(giveaway)

    def to_dict(self):
        return {
            "host": self._host,
            "prize": self.prize,
            "guild": self.guild.id,
            "requirements": self.requirements.as_dict(),
            "winners": self.winners,
            "_time": self._time,
            "flags": self.flags,
        }


class SafeMember:
    def __init__(self, member: discord.Member):
        self._org = member
        self.id = member.id
        self.name = member.name
        self.mention = member.mention
        self.avatar_url = member.avatar_url

    def __str__(self) -> str:
        return self._org.__str__()

    def __getattr__(
        self, value
    ):  # if anyone tries to be sneaky and tried to access things they cant
        return f"donor.{value}"  # since its only used in one place where the var name is donor.
