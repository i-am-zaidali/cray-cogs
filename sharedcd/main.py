import asyncio
import datetime
import functools
import itertools
import logging
import random
import string
import typing

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext.menus import ListPageSource

from .paginator import Paginator
from .utils import SCDFlags, SCDFlagsAllOPT, SharedCooldown

log = logging.getLogger("red.cray.SharedCooldowns")

# class SharedCooldownError(commands.CommandError):
#     def __init__(self, shared_cooldown: SharedCooldown, retry_after: float):
#         self.shared_cooldown = shared_cooldown
#         self.retry_after = retry_after

#         super().__init__(
#             f"Commands {cf.humanize_list(list(map(lambda x: f'`{x}`', self.shared_cooldown.command_names)))} are on a shared cooldown for {shared_cooldown.cooldown} seconds. Try again in {retry_after:.2f} seconds."
#         )


def generate_random_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=8))


# async def _before_hook(ctx: commands.Context):
#     assert isinstance(ctx.bot, Red)
#     cog = ctx.bot.get_cog("SharedCooldowns")
#     if not cog or not isinstance(cog, SharedCooldowns):
#         return
#     shared_cooldowns: list[SharedCooldownsDict] = await cog.config.cooldowns()
#     for scd in shared_cooldowns:
#         scd = SharedCooldown.from_dict(scd)
#         if ctx.command.qualified_name in scd.command_names:
#             if scd.cooldown_mapping is None:
#                 scd.cooldown_mapping = commands.CooldownMapping.from_cooldown(
#                     1, scd.cooldown, scd.bucket_type
#                 )
#             if scd.cooldown_mapping.valid:
#                 bucket = scd.cooldown_mapping.get_bucket(ctx)
#                 if bucket is None:
#                     return 0.0
#                 dt = ctx.message.edited_at or ctx.message.created_at
#                 current = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
#                 retry_after = bucket.get_retry_after(current)
#                 if retry_after:
#                     raise SharedCooldownError(scd, retry_after)


# async def scd_error(ctx: commands.Context, error: commands.CommandError):
#     if not isinstance(error, SharedCooldownError):
#         await ctx.bot.on_command_error(ctx, error)
#         ctx.command.invoke
#         return

#     await ctx.send(str(error))


def custom_cooldown(
    ctx: commands.Context,
    *,
    new_cooldown: commands.CooldownMapping,
    org_cooldown: typing.Optional[commands.CooldownMapping],
    scd: SharedCooldown,
):
    # we need both cooldowns to work simulataneously
    if scd.bypass and ctx.author.id in scd.bypass:
        log.debug(scd.bypass), log.debug(ctx.author.id), log.debug(ctx.author.id in scd.bypass)
        return None
    cd = None
    if org_cooldown and org_cooldown.valid and not scd.replace:
        cd = org_cooldown

    dt = ctx.message.edited_at or ctx.message.created_at
    current = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    if cd:
        bucket = new_cooldown.get_bucket(ctx, current)
        if bucket is not None:
            bucket.update_rate_limit(current)

    return (cd or new_cooldown).get_bucket(ctx, current)


class SharedCooldowns(commands.Cog):
    """
    Create custom cooldowns that apply to multiple commands at once.

    These custom cooldowns can be set to replace the original cooldown of the commands or stack with them.
    """

    __author__ = ["crayyy_zee"]
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self._cache: dict[str, SharedCooldown] = {}
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(cooldowns={})

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {cf.humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def red_delete_data_for_user(
        self,
        *,
        requester: typing.Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        return

    async def cog_load(self):
        self._load_task = asyncio.create_task(self._load_shared_cooldowns())
        self._load_task.add_done_callback(
            lambda x: (
                log.debug("Loaded all SharedCooldowns")
                if not (exc := x.exception())
                else log.exception("There was an error when loading SharedCooldowns", exc_info=exc)
            )
        )
        # temp task to prevent it from getting garbage collected

    async def _load_shared_cooldowns(self):
        await self.bot.wait_until_red_ready()
        scd = await self.config.cooldowns()
        for _id, data in scd.items():
            scd = SharedCooldown.from_dict(_id, data)
            self._load_cooldown(scd)

    def _load_cooldown(self, scd: SharedCooldown):
        for command_name in scd.command_names:
            command = self.bot.get_command(command_name)
            if command is None:
                continue
            command.__commands_cooldown__ = org_cooldown = getattr(
                command, "__commands_cooldown__", command._buckets
            )
            command._buckets = dcm = commands.DynamicCooldownMapping(
                functools.partial(
                    custom_cooldown,
                    new_cooldown=scd.cooldown_mapping,
                    org_cooldown=org_cooldown if not scd.replace else None,
                    scd=scd,
                ),
                lambda x: dcm._cache.clear(),  # this cache aint needed.
            )

        self._cache[scd.id] = scd

    async def cog_unload(self):
        await self._unload_shared_cooldowns()
        # unlike loading, this has to be awaited to ensure this is finished within the cog's lifetime
        # otherwise we end up with a stale state of our cog object

    async def _unload_shared_cooldowns(self, save_config: bool = True):
        cop = self._cache.copy()
        if not cop and self._load_task.exception():
            log.debug(
                "Skipping unloading SharedCooldowns since there was an error while loading them"
            )
            return
        for scd in self._cache.values():
            self._unload_cooldown(scd)
            cop[scd.id] = scd.to_dict()
        if save_config:
            await self.config.cooldowns.set(cop)
        self._cache.clear()
        log.debug("Unloaded all SharedCooldowns.")

    def _unload_cooldown(self, scd: SharedCooldown):
        for command_name in scd.command_names:
            command = self.bot.get_command(command_name)
            if command is None:
                continue
            command._buckets = command.__commands_cooldown__

    # async def cog_command_error(self, ctx: Context, error: Exception) -> None:
    #     log.exception("Error: ", exc_info=error)
    #     await super().cog_command_error(ctx, error)
    #     await self.bot.on_command_error(ctx, error)

    def check_command_exists_as_scd(self, command: commands.Command):
        return discord.utils.find(lambda x: command in x.command_names, self._cache.values())

    @commands.group(name="sharedcooldown", aliases=["sharedcd", "sharecd", "scd"])
    @commands.is_owner()
    async def scd(self, ctx: commands.Context):
        """
        Manage SharedCooldowns settings
        """

    @scd.group(name="group", aliases=["g", "groups"], invoke_without_command=True)
    async def scd_g(self, ctx: commands.Context):
        """
        Manage SharedCooldown groups
        """

    @scd_g.command(name="create", aliases=["c", "createg"])
    async def scd_c(self, ctx: commands.Context, *, flags: SCDFlags):
        """
        Create a new SharedCooldown group using flags.

        The flag format is `FlagName: FlagValue`
        Valid flags are:
        - `commands`, `commands`, or `c`: A space-separated list of command names (can be used multiple uses)
        - `cooldown` or `cd`: The cooldown delay.
        - `uses`: The number of uses before the cooldown is applied **[OPTIONAL]**
        - `replace`: Whether to override the original cooldown of the command or replace it entirely. **[OPTIONAl]**
        - `bucket`: The bucket of the cooldown. Can be a number between 0-6 or one of one of `global`, `default`, `user`, `guild`, `channel`, `member`, `category`, and `role` where `default` is equal to `global` **[OPTIONAl]**
        - `bypass`: A space-separated list of users who can bypass this cooldown **[OPTIONAl]**

        Examples:
        - `commands: sharedcooldown paginator whois replace:true bypass:581187816461959413 coolaidman cooldown:30s`
        - `c: help bypass:crayyy_zee c:"sharedcooldown cg" cd:5minutes uses:5`
        - `command:"set api" help cooldown: 40`

        """
        existing = list(
            filter(
                lambda y: y[1] is not None,
                map(
                    lambda x: (x, self.check_command_exists_as_scd(x)),
                    itertools.chain.from_iterable(flags._commands),
                ),
            )
        )
        if existing:
            return await ctx.send(
                f"The following commands are already part of other SharedCooldown groups. Commands can not be part of more than one group.\n"
                f"{cf.humanize_list(list(map(lambda x: f'`{x[0].qualified_name} (ID: {x[1].id})`', existing)))}"
            )

        if next(filter(lambda x: x.bot, itertools.chain.from_iterable(flags.bypass)), None):
            return await ctx.send(
                "Bots can not bypass SharedCooldowns since they can't run any commands in the first place."
            )
        scd = SharedCooldown.from_scd_flags(generate_random_id(), flags)
        await self.config.cooldowns.set_raw(scd.id, value=scd.to_dict())
        self._load_cooldown(scd)
        bnbtds = "\n  - "
        await ctx.send(
            f"SharedCooldown added with ID `{scd.id}`:\n"
            f"- **Commands**:\n  - {bnbtds.join(scd.command_names)}\n"
            f"- **Bypass** (following users bypass this cooldown): \n\t- {bnbtds.join(list(map(lambda x: f'<@{x}>', scd.bypass)) or ['No users bypass this cooldown'])}\n"
            f"- **Cooldown**: {cf.humanize_timedelta(seconds=scd.cooldown)}\n"
            f"- **Uses before cooldown applies**: {scd.uses}\n"
            f"- **Replace Original Cooldown**: {scd.replace}\n"
            f"- **Who does the cooldown apply to?**: {scd.bucket_type.name.replace('default', 'everyone')}"
        )

    @scd_g.command(name="edit", aliases=["e", "editg"])
    async def scd_e(self, ctx: commands.Context, id: str, *, flags: SCDFlagsAllOPT):
        """
        Edit a SharedCooldown gorup using flags

        The flag format is `FlagName: FlagValue`
        All flags are optional but atleast one had to be used.
        Use of any flag overwrites the complete value set during creation.
        Valid flags are:
        - `commands`, `commands`, or `c`: A space-separated list of command names (can be used multiple uses)
        - `cooldown` or `cd`: The cooldown delay.
        - `uses`: The number of uses before the cooldown is applied **[OPTIONAL]**
        - `replace`: Whether to override the original cooldown of the command or replace it entirely.
        - `bucket`: The bucket of the cooldown. Can be a number between 0-6 or one of one of `global`, `default`, `user`, `guild`, `channel`, `member`, `category`, and `role` where `default` is equal to `global`
        - `bypass`: A space-separated list of users who can bypass this cooldown

        Examples:
        - `commands: sharedcooldown paginator whois replace:true bypass:581187816461959413 coolaidman cooldown:30s`
        - `c: help bypass:crayyy_zee c:"sharedcooldown cg" cd:5minutes`
        - `command:"set api" help cooldown: 40`
        """
        if not (scd := self._cache.pop(id, None)):
            # popping from cache so it doesn't get detected as a duplicate in our check right below.
            return await ctx.send(
                f"SharedCooldown with the ID `{id}` does not exist. See existing shared cooldowns and their details with "
            )

        existing = list(
            filter(
                lambda y: y[1] is not None,
                map(
                    lambda x: (x, self.check_command_exists_as_scd(x)),
                    itertools.chain.from_iterable(flags._commands or []),
                ),
            )
        )
        if existing:
            self._cache[id] = scd  # reinserting since we are not updating it yet.
            return await ctx.send(
                f"The following commands are already part of other SharedCooldown groups. Commands can not be part of more than one group.\n"
                f"{cf.humanize_list(list(map(lambda x: f'`{x[0].qualified_name} (ID: {x[1].id})`', existing)))}"
            )

        if next(filter(lambda x: x.bot, itertools.chain.from_iterable(flags.bypass or [])), None):
            return await ctx.send(
                "Bots can not bypass SharedCooldowns since they can't run any commands in the first place."
            )

        if all([getattr(flags, flag.attribute) is None for flag in flags.get_flags().values()]):
            return await ctx.send("Atelast one of the flag values must be used.")

        scd.update(
            bypass=flags.bypass,
            command_names=list(map(lambda x: x.qualified_name, flags._commands or [])) or None,
            cooldown=flags.cooldown,
            replace=flags.replace,
            bucket_type=flags.bucket,
            uses=flags.uses,
        )

        await self.config.cooldowns.get_attr(scd.id).set(scd.to_dict())
        self._load_cooldown(scd)
        bnbtds = "\n  - "
        await ctx.send(
            f"SharedCooldown has been updated with new values.\n"
            f"- **Commands**:\n  - {bnbtds.join(scd.command_names)}\n"
            f"- **Bypass** (following users bypass this cooldown): \n  - {bnbtds.join(list(map(lambda x: f'<@{x}>', scd.bypass)) or ['No users bypass this cooldown'])}\n"
            f"- **Cooldown**: {cf.humanize_timedelta(seconds=scd.cooldown)}\n"
            f"- **Uses before cooldown applies**: {scd.uses}\n"
            f"- **Replace Original Cooldown**: {scd.replace}\n"
            f"- **Who does the cooldown apply to?**: {scd.bucket_type.name.replace('default', 'everyone')}"
        )

    @scd_g.command(name="delete", aliases=["d", "deleteg"], usage="<id>")
    async def scd_dg(self, ctx: commands.Context, id: str, confirm: bool = False):
        """Delete an existing SharedCooldown group using it's ID.

        You can use `[p]sharedcooldown listgroups` command to see each group and it's ID"""
        if not (scd := self._cache.get(id)):
            return await ctx.send(
                f"SharedCooldown with the ID `{id}` does not exist. See existing shared cooldowns and their details with "
            )

        if not confirm:
            return await ctx.send(
                f"If you are sure about deleting this group, Use `{ctx.clean_prefix}{ctx.command.qualified_name} {id} True`"
            )

        self._unload_cooldown(scd)
        self._cache.pop(id)
        await ctx.send(f"SharedCooldown group with ID: `{id}` has been deleted.")

    @scd_g.command(name="clear", aliases=["cg", "clearg"], usage="")
    async def scd_cg(self, ctx: commands.Context, confirm: bool = False):
        if not confirm:
            return await ctx.send(
                f"If you are sure about deleting all groups, Use `{ctx.clean_prefix}{ctx.command.qualified_name} True`"
            )

        await self._unload_shared_cooldowns(False)
        await self.config.cooldowns.clear()
        await ctx.send("All SharedCooldown groups have been deleted.")

    @scd_g.command(name="list", aliases=["l", "listgroups", "lg", "listg"])
    async def scd_lg(self, ctx: commands.Context):
        """List all of the SharedCooldown groups in pagianted embeds."""
        if not self._cache:
            return await ctx.send("No SharedCooldown groups created yet.")
        source = ListPageSource(list(self._cache.values()), per_page=1)

        def format_cooldown_cache(cache: dict[typing.Any, commands.Cooldown]):
            def mention(x):
                return getattr(
                    self.bot.get_user(x)
                    or ctx.guild.get_channel_or_thread(x)
                    or ctx.guild.get_role(x),
                    "mention",
                    getattr(self.bot.get_guild(x), "name", "Anyone"),
                )

            return "\n".join(
                f"{mention(k)} can run the command after {cf.humanize_timedelta(seconds=v.get_retry_after())}"
                for k, v in filter(lambda x: x[1].get_retry_after(), cache.items())
            )

        async def format_page(self: ListPageSource, menu: Paginator, scd: SharedCooldown):
            bnbtds = "\n  - "
            embed = discord.Embed(
                description=(
                    f"## Shared Cooldowns ID: *{scd.id}*\n"
                    f"- **Commands**:\n  - {bnbtds.join(map(lambda x: f'`{x}`', scd.command_names))}\n"
                    f"- **Bypass** (following users bypass this cooldown): \n  - {bnbtds.join(list(map(lambda x: f'<@{x}>', scd.bypass)) or ['No users bypass this cooldown'])}\n"
                    f"- **Cooldown**: {cf.humanize_timedelta(seconds=scd.cooldown)}\n"
                    f"- **Uses before cooldown applies**: {scd.uses}\n"
                    f"- **Replace Original Cooldown**: {scd.replace}\n"
                    f"- **Who does the cooldown apply to?**: {scd.bucket_type.name.replace('default', 'everyone')}\n"
                    f"- **Current cooldown cache**:\n{format_cooldown_cache(scd.cooldown_mapping._cache) or 'No one is on cooldown'}"
                ),
                color=discord.Color.random(),
            )
            return embed

        setattr(source, "format_page", functools.partial(format_page, source))

        await Paginator(
            source,
            use_select=True,
            select_indices=[
                (f"ID: {id} (Page {page + 1})", page) for page, id in enumerate(self._cache)
            ],
        ).start(ctx)
