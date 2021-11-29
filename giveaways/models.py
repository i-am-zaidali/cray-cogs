import random
import time
from collections import Counter
from functools import reduce
from typing import Any, Dict, List, Union

import discord
from discord.ext.commands.converter import RoleConverter
from discord.ext.commands.errors import BadArgument, RoleNotFound
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list


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

    def __str__(self):
        final = ""
        for key, value in self.items():
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
            self.blacklist += self.default_by
            self.bypass += self.default_by
            del self.default_by
            del self.default_bl
            return self  # return self because nothing needs to be modified

        return self.__class__(**self.as_dict().update({"default_by": [], "default_bl": []}))

    def no_amari_available(self):
        self.amari_level = None
        self.amari_weekly = None
        return True

    def verify_role(self, id) -> discord.Role:
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
        return cls(guild=ctx.guild, **roles)


class Giveaway:
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
        requirements: Union[Any, Dict[str, List[int]]] = None,
        winners: int = 1,
        emoji: str = None,
    ):
        self.bot = bot
        self.cog = cog
        self._time = time
        self._host = host
        self._channel = channel
        self.requirements = requirements
        self.message_id = message
        self.winners = winners
        self.prize = prize
        self.emoji = emoji or "🎉"

    def __getitem__(self, key):
        attr = getattr(self, key, None)
        if not attr:
            raise KeyError(f"{key} does not exist.")

        return attr

    def __hash__(self) -> int:
        return self.message_id

    @property
    def channel(self) -> discord.TextChannel:
        return self.bot.get_channel(self._channel)

    @property
    def guild(self) -> discord.Guild:
        return self.channel.guild

    @property
    def host(self) -> discord.User:
        return self.bot.get_user(self._host)

    async def get_message(self) -> discord.Message:
        return await self.channel.fetch_message(self.message_id)

    @property
    def remaining_time(self) -> int:
        if self._time > int(time.time()):
            return self._time - int(time.time())
        else:
            return 0

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
            member = await self.bot.get_or_fetch_user(winner)
            if member:
                try:
                    embed = discord.Embed(
                        title="Congratulations!",
                        description=f"You have won a giveaway for `{prize}` in **__{guild}__**.\nClick [here]({jump_url}) to jump to the giveaway.",
                        color=discord.Color.random(),
                    ).set_thumbnail(url=member.avatar_url)
                    await member.send(embed=embed)

                except discord.HTTPException:
                    return False

    async def end(self) -> None:
        try:
            msg = await self.get_message()
        except discord.NotFound as e:
            await self.channel.send(
                f"Can't find message with id: {self.message_id}. Removing id from active giveaways."
            )
            self.cog.giveaway_cache.remove(self)
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
            )
            if hostdm == True:
                await self.hdm(host, gmsg.jump_url, prize, "None")

            self.cog.giveaway_cache.remove(self)
            return True

        w = ""
        w_list = []

        for i in range(winners):
            winner = random.choice(entrants)
            w_list.append(winner.id)
            w += f"{winner.mention} "

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
        }
        return data


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
