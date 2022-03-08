from dataclasses import dataclass
from typing import Dict, List, Optional

import discord
from redbot.core import Config

from ..constants import guild_default_config
from ..utils import has_repeats

config: Config = Config.get_conf(None, 234_6969_420, True, cog_name="Giveaways")
config.register_global(schema=0)
config.register_guild(**guild_default_config)


@dataclass(init=True, repr=True)
class GuildSettings:
    msg: str
    emoji: str
    winnerdm: bool
    winnerdm_message: str
    hostdm: bool
    hostdm_message: str
    endmsg: str
    reactdm: bool
    unreactdm: bool
    embed_title: str
    embed_description: str
    embed_footer_text: str
    embed_footer_icon: str
    embed_thumbnail: str
    color: Optional[int]
    tmsg: str
    manager: List[int]
    pingrole: Optional[int]
    autodelete: bool
    blacklist: List[int]
    bypass: List[int]
    top_managers: Dict[int, int]
    show_defaults: bool
    multi_roles: Dict[int, int]


async def get_guild_settings(guild_id: int, obj=True):
    if not obj:
        return config.guild_from_id(guild_id)

    settings = await config.guild_from_id(guild_id).all()

    if settings["manager"] and settings["blacklist"] and settings["bypass"]:
        if any(has_repeats(settings[i]) for i in ["manager", "blacklist", "bypass"]):
            settings["manager"] = list({role_id for role_id in settings["manager"]})
            settings["blacklist"] = list({role_id for role_id in settings["blacklist"]})
            settings["bypass"] = list({role_id for role_id in settings["bypass"]})

            await config.guild_from_id(guild_id).set(settings)

    return GuildSettings(**settings)


async def apply_multi(guild: discord.Guild, winners: list):
    _winners = winners.copy()
    roles = (await get_guild_settings(guild.id)).multi_roles
    roles = {guild.get_role(_id): multi for _id, multi in roles.items() if guild.get_role(_id)}
    for member in _winners:
        for key, value in roles.items():
            winners += [member for i in range(value) if member and key in member.roles]

    return winners


async def _config_schema_0_to_1(bot):
    guilds = await config.all_guilds()
    roles = await config.all_roles()
    for guild_id, guild_data in guilds.items():
        guild: discord.Guild = bot.get_guild(guild_id)
        if not guild:
            continue

        if guild_data.get("edit_timer") is not None:
            guild_data.pop("edit_timer")

        guild_data["multi_roles"] = {}

        guild_roles = [role.id for role in guild.roles if role.id in roles]

        for role in guild_roles:
            guild_data["multi_roles"].update({role: roles.get(role, {}).get("multi")})
            await config.role_from_id(role).clear()

        await config.guild_from_id(guild_id).set(guild_data)

    await config.schema.set(1)
