from typing import List, Optional, Dict, Union
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list
from .guildsettings import get_guild_settings

import discord

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
        
    @property
    def json(self):
        return self.as_dict()
    
    @property
    def null(self):
        return all([not i for i in self.as_dict().values()])

    async def get_str(self):
        final = ""
        show_defaults = (await get_guild_settings(self.guild.id)).show_defaults
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

    @classmethod
    def from_json(cls, json: dict):
        return cls(**json)
    
    @classmethod
    async def empty(cls, ctx):
        return await cls.convert(ctx, "none")

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
        settings = await get_guild_settings(ctx.guild.id)
        new_bl = settings.blacklist
        new_by = settings.bypass
        data["default_bl"] += new_bl
        data["default_by"] += new_by

        if isinstance(maybeid, str) and maybeid.lower() == "none":
            return cls(guild=ctx.guild, **data)

        if isinstance(maybeid, list):
            for i in maybeid:
                if not "[" in i:
                    try:
                        role = await commands.RoleConverter().convert(ctx, i)
                    except commands.RoleNotFound:
                        raise commands.BadArgument("Role with id: {} not found.".format(i))
                    data["required"].append(role.id)

                else:
                    _list = i.split("[")
                    if "blacklist" in _list[1]:
                        try:
                            role = await commands.RoleConverter().convert(ctx, _list[0])
                        except commands.RoleNotFound:
                            raise commands.BadArgument(f"Role with id: {_list[0]} was not found.")
                        data["blacklist"].append(role.id)
                    elif "bypass" in _list[1]:
                        try:
                            role = await commands.RoleConverter().convert(ctx, _list[0])
                        except commands.RoleNotFound:
                            raise commands.BadArgument(f"Role with id: {_list[0]} was not found.")
                        data["bypass"].append(role.id)
                    elif "alevel" in _list[1] or "alvl" in _list[1]:
                        data["amari_level"] = int(_list[0])
                    elif "aweekly" in _list[1] or "aw" in _list[1]:
                        data["amari_weekly"] = int(_list[0])

        else:
            if not "[" in maybeid:
                role = await commands.RoleConverter().convert(ctx, maybeid)
                if not role:
                    raise commands.BadArgument("Role with id: {} not found.".format(maybeid))
                data["required"].append(role.id)

            else:
                _list = maybeid.split("[")
                if "blacklist" in _list[1]:
                    try:
                        role = await commands.RoleConverter().convert(ctx, _list[0])
                    except commands.RoleNotFound:
                        raise commands.BadArgument(f"Role with id: {_list[0]} was not found.")
                    if role.id in data["default_bl"]:
                        raise commands.BadArgument(
                            f"Role `@{role.name}` is already blacklisted by default."
                        )
                    data["blacklist"].append(role.id)
                elif "bypass" in _list[1]:
                    try:
                        role = await commands.RoleConverter().convert(ctx, _list[0])
                    except commands.RoleNotFound:
                        raise commands.BadArgument(f"Role with id: {_list[0]} was not found.")
                    if role.id in data["default_by"]:
                        raise commands.BadArgument(f"Role `@{role.name}` is already bypassing by default.")
                    data["bypass"].append(role.id)
                elif "alevel" in _list[1] or "alvl" in _list[1] or "amarilevel" in _list[1]:
                    data["amari_level"] = int(_list[0])
                elif "aweekly" in _list[1] or "aw" in _list[1] or "amariweekly" in _list[1]:
                    data["amari_weekly"] = int(_list[0])
                elif "messages" in _list[1] or "msgs" in _list[1]:
                    data["messages"] = int(_list[0])
        return cls(guild=ctx.guild, **data)
