from dataclasses import dataclass
from typing import Dict, List, Optional

import discord
from redbot.core import Config

from ..constants import guild_default_config

config: Config = Config.get_conf(None, 234_6969_420, True, cog_name="Giveaways")
config.register_guild(**guild_default_config)


@dataclass(init=True, repr=True)
class GuildSettings:
    msg: str
    emoji: str
    winnerdm: bool
    hostdm: bool
    endmsg: str
    reactdm: bool
    unreactdm: bool
    tmsg: str
    manager: List[int]
    pingrole: Optional[int]
    autodelete: bool
    blacklist: List[int]
    bypass: List[int]
    top_managers: Dict[int, int]
    color: Optional[int]
    show_defaults: bool
    edit_timer: bool = False


async def get_guild_settings(guild_id: int, obj=True):
    if not obj:
        return config.guild_from_id(guild_id)

    return GuildSettings(**(await config.guild_from_id(guild_id).all()))


async def get_role(role_id: int):
    return config.role_from_id(role_id)


async def apply_multi(guild: discord.Guild, winners: list):
    _winners = winners.copy()
    roles = await config.all_roles()
    roles = {
        guild.get_role(_id): data["multi"] for _id, data in roles.items() if guild.get_role(_id)
    }
    for member in _winners:
        for key, value in roles.items():
            winners += [member for i in range(value) if member and key in member.roles]

    return winners
