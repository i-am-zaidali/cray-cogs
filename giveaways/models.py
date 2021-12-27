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

from .util import Coordinate


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

    __slots__ = ["required", "blacklist", "bypass", "amari_level", "amari_weekly"]

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
    ):

        self.guild = guild  # guild object for role fetching
        self.required = required  # roles that are actually required
        self.blacklist = blacklist  # list of role blacklisted for this giveaway
        self.bypass = bypass  # list of roles bypassing this giveaway
        self.amari_level = amari_level  # amari level required for this giveaway
        self.amari_weekly = amari_weekly  # amari weekly required for this giveaway

        self.default_bl = default_bl
        self.default_by = default_by

    async def get_str(self, ctx):
        final = ""
        show_defaults = await ctx.cog.config.get_guild(ctx.guild, "show_defaults")
        items = self.as_dict()
        if not show_defaults:
            default_by, default_bl = set(self.default_by), set(self.default_bl)
            items["blacklist"] = set(items["blacklist"]).difference_update(default_bl)
            items["bypass"] = set(items["bypass"]).difference_update(default_by)

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

        roles = {
            "blacklist": [],
            "bypass": [],
            "required": [],
            "default_by": [],
            "default_bl": [],
            "amari_level": None,
            "amari_weekly": None,
        }
        new_bl = await ctx.command.cog.config.all_blacklisted_roles(ctx.guild)
        new_by = await ctx.command.cog.config.all_bypass_roles(ctx.guild)
        roles["default_bl"] += new_bl
        roles["default_by"] += new_by

        if isinstance(maybeid, str) and maybeid.lower() == "none":
            return cls(guild=ctx.guild, **roles)

        if isinstance(maybeid, list):
            for i in maybeid:
                if not "[" in i:
                    try:
                        role = await RoleConverter().convert(ctx, i)
                    except RoleNotFound:
                        raise BadArgument("Role with id: {} not found.".format(i))
                    roles["required"].append(role.id)

                else:
                    _list = i.split("[")
                    if "blacklist" in _list[1]:
                        try:
                            role = await RoleConverter().convert(ctx, _list[0])
                        except RoleNotFound:
                            raise BadArgument(f"Role with id: {_list[0]} was not found.")
                        roles["blacklist"].append(role.id)
                    elif "bypass" in _list[1]:
                        try:
                            role = await RoleConverter().convert(ctx, _list[0])
                        except RoleNotFound:
                            raise BadArgument(f"Role with id: {_list[0]} was not found.")
                        roles["bypass"].append(role.id)
                    elif "alevel" in _list[1] or "alvl" in _list[1]:
                        roles["amari_level"] = int(_list[0])
                    elif "aweekly" in _list[1] or "aw" in _list[1]:
                        roles["amari_weekly"] = int(_list[0])

        else:
            if not "[" in maybeid:
                role = await RoleConverter().convert(ctx, maybeid)
                if not role:
                    raise BadArgument("Role with id: {} not found.".format(maybeid))
                roles["required"].append(role.id)

            else:
                _list = maybeid.split("[")
                if "blacklist" in _list[1]:
                    try:
                        role = await RoleConverter().convert(ctx, _list[0])
                    except RoleNotFound:
                        raise BadArgument(f"Role with id: {_list[0]} was not found.")
                    if role.id in roles["default_bl"]:
                        raise BadArgument(
                            f"Role `@{role.name}` is already blacklisted by default."
                        )
                    roles["blacklist"].append(role.id)
                elif "bypass" in _list[1]:
                    try:
                        role = await RoleConverter().convert(ctx, _list[0])
                    except RoleNotFound:
                        raise BadArgument(f"Role with id: {_list[0]} was not found.")
                    if role.id in roles["default_by"]:
                        raise BadArgument(f"Role `@{role.name}` is already bypassing by default.")
                    roles["bypass"].append(role.id)
                elif "alevel" in _list[1] or "alvl" in _list[1]:
                    roles["amari_level"] = int(_list[0])
                elif "aweekly" in _list[1] or "aw" in _list[1]:
                    roles["amari_weekly"] = int(_list[0])
        return cls(guild=ctx.guild, **roles)


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
    ) -> None:
        self.bot: Red = bot
        self.cog = cog
        self.prize: str = prize
        self._time: int = time
        self._host: int = host
        self._channel: int = channel
        self.requirements: Requirements = requirements
        self.winners: int = winners

    def __getitem__(self, key):
        attr = getattr(self, key, None)
        if not attr:
            raise KeyError(f"{key} does not exist.")

        return attr

    @property
    def host(self) -> discord.User:
        return self.bot.get_user(self._host)

    @property
    def channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self._channel)

    @property
    def guild(self) -> discord.Guild:
        return self.channel.guild

    @property
    def remaining_time(self) -> int:
        if self._time > int(time.time()):
            return self._time - int(time.time())
        else:
            return 0

    def to_dict(self):
        raise NotImplementedError()  # this method must be implemented by the subclasses


class Giveaway(BaseGiveaway):
    """
    A class wrapper for a giveaway which handles the ending of a giveaway and stores all its necessary attributes."""

    def __init__(
        self,
        *,
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
    ):
        super().__init__(bot, cog, prize, time, host, channel, requirements, winners)
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
        msg = self.bot._connection._get_message(
            self.message_id
        )  # i mean, if its cached, why waste an api request right?
        if not msg:
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
                embed.set_thumbnail(url=member.avatar_url)
                await member.send(embed=embed)

            except discord.HTTPException:
                return False

    async def wdm(self, winners, jump_url, prize, guild):
        winners = Counter(winners)
        # winners = [k for k, v in winners.items()]
        for winner in winners.keys():
            if winner:
                try:
                    embed = discord.Embed(
                        title="Congratulations!",
                        description=f"You have won a giveaway for `{prize}` in **__{guild}__**.\nClick [here]({jump_url}) to jump to the giveaway.",
                        color=discord.Color.random(),
                    ).set_thumbnail(url=winner.avatar_url)
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

    async def end(self, canceller=None) -> None:
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
            self.cog.ended_cache.append(EndedGiveaway(**end_data))
            return
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
        try:
            entrants.pop(entrants.index(msg.guild.me))
        except:
            pass
        if self.use_multi:
            entrants = await self.cog.config.get_list_multi(channel.guild, entrants)
        link = gmsg.jump_url

        if len(entrants) == 0 or winners == 0:
            embed = gmsg.embeds[0]
            embed.description = (
                f"This giveaway has ended.\nThere were 0 winners.\n**Host:** <@{host}>"
            )
            embed.set_footer(
                text=f"{msg.guild.name} - Winners: {winners}", icon_url=msg.guild.icon_url
            )
            await gmsg.edit(embed=embed)

            await gmsg.reply(
                f"The giveaway for ***{prize}*** has ended. There were 0 winners.\nClick on my replied message to jump to the giveaway."
                f"Or click on this link: {gmsg.jump_url}"
            )
            if hostdm == True:
                await self.hdm(host, gmsg.jump_url, prize, "None")

            end_data.update({"winnerslist": []})
            if not canceller:
                end_data.update({"reason": EndReason.SUCCESS.value})
            else:
                end_data.update({"reason": EndReason.CANCELLED.value.format(canceller)})

            self.cog.giveaway_cache.remove(self)
            self.cog.ended_cache.append(EndedGiveaway(**end_data))
            return True

        w = ""
        w_list = [random.choice(entrants) for i in range(winners)]

        wcounter = Counter(w_list)
        for k, v in wcounter.items():
            w += f"<@{k.id}> x {v}, " if v > 1 else f"<@{k.id}> "

        formatdict = {"winner": w, "prize": prize, "link": link}

        embed = gmsg.embeds[0]
        embed.description = f"This giveaway has ended.\n**Winners:** {w}\n**Host:** <@{host}>"
        embed.set_footer(
            text=f"{msg.guild.name} - Winners: {winners}", icon_url=msg.guild.icon_url
        )
        await gmsg.edit(embed=embed)

        await gmsg.reply(endmsg.format_map(formatdict))

        if winnerdm == True:
            await self.wdm(w_list, gmsg.jump_url, prize, channel.guild)

        if hostdm == True:
            await self.hdm(host, gmsg.jump_url, prize, w)

        self.cog.giveaway_cache.remove(self)
        end_data.update({"winnerslist": [i.id for i in w_list]})
        if not canceller:
            end_data.update({"reason": EndReason.SUCCESS.value})
        else:
            end_data.update({"reason": EndReason.CANCELLED.value.format(canceller)})
        self.cog.ended_cache.append(EndedGiveaway(**end_data))
        return True

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
        return data


class EndedGiveaway(BaseGiveaway):
    def __init__(
        self, bot, cog, host, channel, message, winnersno, winnerslist, prize, requirements, reason
    ) -> None:
        super().__init__(
            bot, cog, prize, None, host, channel, requirements, winnersno
        )  # winners no is number of winners and list is a list of winners.
        self.message_id = message
        self._winnerlist = winnerslist
        self.reason: str = reason

    def __hash__(self) -> int:
        return hash(self.message_id)

    async def get_message(self):
        msg = self.bot._connection._get_message(
            self.message_id
        )  # i mean, if its cached, why waste an api request right?
        if not msg:
            try:
                msg = await self.channel.fetch_message(self.message_id)
            except Exception:
                msg = None
        return msg

    @property
    def winnerslist(self):
        return [self.guild.get_member(i) for i in self._winnerlist]

    def to_dict(self):
        return {
            "message": self.message_id,
            "channel": self._channel,
            "guild": self.guild.id,
            "host": self._host,
            "prize": self.prize,
            "requirements": self.requirements.as_dict(),
            "winnersno": self.winners,
            "winnerslist": self.winnerslist,
            "reason": self.reason,
        }


class PendingGiveaway(BaseGiveaway):
    def __init__(self, bot, cog, host, _time, winners, requirements, prize, flags):
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
            await messagable.send(ping)
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
