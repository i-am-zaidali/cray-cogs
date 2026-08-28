import datetime
import itertools
import typing
from dataclasses import asdict, dataclass

import discord
from redbot.core import commands
from redbot.core.utils import chat_formatting as cf

__all__ = ["SharedCooldown", "SCDFlags", "SCDFlagsAllOPT"]

# bucket type name to value
bt_ntv = {
    "global": 0,
    "default": 0,
    "user": 1,
    "guild": 2,
    "channel": 3,
    "member": 4,
    "category": 5,
    "role": 6,
}


class SharedCooldownsDict(typing.TypedDict):
    command_names: list[str]
    # the name of all the commands that are a part of this shared cooldown
    cooldown: float
    # the duration of the cooldown
    uses: int
    # the number of uses before the cooldown applies
    last_used: int
    # the timestamp of when the last command was used.
    replace: bool
    # whether to replace the developer defined cooldown of the commands or stack it with the shared cooldown
    bucket_type: typing.Literal[0, 1, 2, 3, 4, 5, 6]
    # the type of cooldown bucket to use
    bypass: list[int]
    # list of user ids that are unaffected by this cooldown


class SCDFlags(commands.FlagConverter):
    _commands: list[tuple[commands.Command, ...]] = commands.flag(
        name="command",
        aliases=["c", "commands"],
        converter=typing.List[typing.Tuple[commands.CommandConverter, ...]],
    )
    cooldown: datetime.timedelta = commands.flag(
        name="cooldown",
        aliases=["cd"],
        converter=commands.get_timedelta_converter(
            default_unit="s",
            minimum=datetime.timedelta(seconds=3),
            maximum=datetime.timedelta(seconds=60 * 60 * 6),
            allowed_units=["seconds", "minutes", "hours"],
        ),
    )
    uses: int = 1
    replace: bool = False
    bucket: commands.BucketType = commands.flag(
        name="bucket",
        converter=lambda x: (
            commands.BucketType(int(x) if x.isdecimal() else bt_ntv.get(x))
            if bt_ntv.get(x) is not None or "0" <= x <= "6"
            else (_ for _ in ()).throw(
                commands.BadArgument(
                    f"`{x}` is invalid. `bucket` flag accepts a number between 0-6 or one of {cf.humanize_list([*bt_ntv])}, where `default` is equal to `global`"
                )
            )
        ),
    )
    bypass: typing.List[typing.Tuple[discord.User, ...]] = commands.flag(
        name="bypass",
        default=lambda ctx: [],
    )


class SCDFlagsAllOPT(commands.FlagConverter):
    _commands: typing.Optional[list[commands.Command]] = commands.flag(
        name="command",
        aliases=["c", "commands"],
        default=None,
        converter=typing.Optional[typing.List[typing.Tuple[commands.CommandConverter, ...]]],
    )
    cooldown: typing.Optional[datetime.timedelta] = commands.flag(
        name="cooldown",
        aliases=["cd"],
        converter=commands.get_timedelta_converter(
            default_unit="s",
            minimum=datetime.timedelta(seconds=3),
            maximum=datetime.timedelta(seconds=60 * 60 * 6),
            allowed_units=["seconds", "minutes", "hours"],
        ),
        default=None,
    )
    uses: typing.Optional[int] = None
    replace: typing.Optional[bool] = None
    bucket: typing.Optional[commands.BucketType] = commands.flag(
        name="bucket",
        default=None,
        converter=lambda x: (
            commands.BucketType(int(x) if x.isdecimal() else bt_ntv.get(x))
            if bt_ntv.get(x) is not None or "0" <= x <= "6"
            else (_ for _ in ()).throw(
                commands.BadArgument(
                    f"`{x}` is invalid. `bucket` flag accepts a number between 0-6 or one of {cf.humanize_list([*bt_ntv])}, where `default` is equal to `global`"
                )
            )
        ),
    )
    bypass: typing.Optional[list[int]] = commands.flag(
        name="bypass",
        default=None,
        converter=typing.Optional[typing.List[typing.Tuple[discord.User, ...]]],
    )


@dataclass
class SharedCooldown:
    id: str
    # the id of the cooldown
    bypass: list[int]
    # list of user ids that are unaffected by this cooldown
    command_names: list[str]
    # the name of all the commands that are a part of this shared cooldown
    cooldown: float  # the duration of the cooldown
    uses: int  # the number of uses the commands can be used before the cooldown applies

    cooldown_mapping: commands.CooldownMapping

    replace: bool = False
    # whether to replace the developer defined cooldown of the commands or stack it with the shared cooldown
    bucket_type: commands.BucketType = commands.BucketType.user
    # the type of cooldown bucket to use

    def update(
        self,
        *,
        bypass: typing.Optional[list[int]] = None,
        command_names: typing.Optional[list[str]] = None,
        cooldown: typing.Optional[int] = None,
        uses: typing.Optional[int] = None,
        replace: typing.Optional[bool] = None,
        bucket_type: typing.Optional[commands.BucketType] = None,
    ):
        if bypass is not None:
            self.bypass = bypass

        if command_names is not None:
            if len(command_names) < 1:
                raise commands.BadArgument("SharedCooldowns must have atleast 1 command.")
            self.command_names = command_names

        if cooldown is not None:
            if 3 > cooldown > 60 * 60 * 6:
                raise commands.BadArgument(
                    "SharedCooldowns must have a cooldown greater than 3 seconds and less than 6 hours"
                )
            self.cooldown = cooldown

        if uses is not None:
            if uses < 1:
                raise commands.BadArgument(
                    "SharedCooldowns' commands must be usable atleast one time."
                )

            self.uses = uses

        if replace is not None:
            self.replace = replace

        if bucket_type is not None:
            self.bucket_type = bucket_type

        if cooldown is not None or bucket_type is not None or uses is not None:
            self.cooldown_mapping = commands.CooldownMapping.from_cooldown(
                self.uses, self.cooldown, self.bucket_type
            )
        return self

    def to_dict(self):
        return asdict(self, dict_factory=self.dict_factory)

    @classmethod
    def from_dict(
        cls,
        id: str,
        data: SharedCooldownsDict,
        *,
        cooldown_mapping: typing.Optional[commands.CooldownMapping] = None,
    ):
        bucket_type = commands.BucketType(data.pop("bucket_type"))
        return cls(
            id=id,
            bucket_type=bucket_type,
            cooldown_mapping=cooldown_mapping
            or commands.CooldownMapping.from_cooldown(
                data.get("uses", 1),
                data.get("cooldown"),
                bucket_type,
            ),
            **data,
        )

    @classmethod
    def from_scd_flags(cls, id: str, flags: SCDFlags):
        return cls(
            id=id,
            bypass=list(map(lambda x: x.id, itertools.chain.from_iterable(flags.bypass))),
            command_names=list(
                map(lambda x: x.qualified_name, itertools.chain.from_iterable(flags._commands))
            ),
            cooldown=flags.cooldown.total_seconds(),
            cooldown_mapping=commands.CooldownMapping.from_cooldown(
                flags.uses,
                flags.cooldown.total_seconds(),
                flags.bucket,
            ),
            replace=flags.replace,
            bucket_type=flags.bucket,
            uses=flags.uses,
        )

    @staticmethod
    def dict_factory(x: list[tuple]) -> SharedCooldownsDict:
        x = dict(x)
        x["bucket_type"] = x["bucket_type"].value
        x.pop("id")
        x.pop("cooldown_mapping")
        return x
