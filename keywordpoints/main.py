import asyncio
import logging
from collections import deque
from typing import Dict, List, Literal, TypedDict, Union

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from redbot.core.utils.predicates import MessagePredicate
from tabulate import tabulate

KEYWORDPOINTS = "keywordpoints"

log = logging.getLogger("red.craycogs.kwp")


class KeyWordDetails(TypedDict):
    points: int
    channels: List[int]
    blacklisted_members: List[int]


class KeyWordPoints(commands.Cog):
    """
    A cog to reward users points based on keywords that their message contains.

    This cog does not respect word boundaries and thus if the keyword is "test" then "test" will be found in "testify" and "testing",
    and points will be rewarded accordingly.
    However, multiple usage of a single keyword in a message, does not reward points multiple times.
    But multiple different keywords in a message will reward points multiple times.
    """

    __version__ = "1.0.8"
    __author__ = ["crayyy_zee"]

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        self.config.init_custom(KEYWORDPOINTS, 2)  # guild_id and the keyword
        self.config.register_member(points=0)

        # config structure would be like:
        # {
        #     guild_id: {
        #         keyword: {
        #             points: x,
        #             channels: [chan_id, ...],
        #             blacklisted_members: [member_id, ...]
        #         },
        #         member_id: {
        #             points: x
        #         }
        #         ...
        #     },
        #     ...
        # }

        self.settings_cache: Dict[str, Dict[str, KeyWordDetails]] = {}
        # this cache would just mirror the config structure
        self.member_cache: Dict[int, Dict[int, Dict[Literal["points"], int]]] = {}
        # {guild_id: {member_id: {points: x}, ...}, ...}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {cf.humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    @staticmethod
    async def group_embeds_by_fields(
        *fields: Dict[str, Union[str, bool]],
        per_embed: int = 3,
        page_in_footer: Union[str, bool] = True,
        **kwargs,
    ) -> List[discord.Embed]:
        """
        This was the result of a big brain moment i had

        This method takes dicts of fields and groups them into separate embeds
        keeping `per_embed` number of fields per embed.

        page_in_footer can be passed either as a boolen value ( True to enable, False to disable. in which case the footer will look like `Page {index of page}/{total pages}` )
        Or it can be passed as a string template to format. The allowed variables are: `page` and `total_pages`

        Extra kwargs can be passed to create embeds off of.
        """

        def fix_kwargs(kwargs):
            return {
                next(x): (fix_kwargs({next(x): v}) if "__" in k else v)
                for k, v in kwargs.copy().items()
                if (x := iter(k.split("__", 1)))
            }

        kwargs = fix_kwargs(kwargs)
        # yea idk man.

        groups: list[discord.Embed] = []
        page_format = ""
        if page_in_footer:
            kwargs.get("footer", {}).pop("text", None)  # to prevent being overridden
            page_format = (
                page_in_footer if isinstance(page_in_footer, str) else "Page {page}/{total_pages}"
            )

        ran = list(range(0, len(fields), per_embed))

        for ind, i in enumerate(ran):
            groups.append(
                discord.Embed.from_dict(kwargs)
            )  # append embeds in the loop to prevent incorrect embed count
            fields_to_add = fields[i : i + per_embed]
            for field in fields_to_add:
                groups[ind].add_field(**field)

            if page_format:
                groups[ind].set_footer(text=page_format.format(page=ind + 1, total_pages=len(ran)))
        return groups

    async def initialize(self):
        self.settings_cache.update(await self.config.custom(KEYWORDPOINTS).all())
        self.member_cache.update(await self.config.all_members())
        self._task = self._update_config.start()

    def cog_unload(self) -> None:
        self._task.cancel()
        asyncio.create_task(self._update_config())

    @tasks.loop(minutes=2)
    async def _update_config(self):
        await self.config.custom(KEYWORDPOINTS).set(self.settings_cache)
        for guild_id, member_data in self.member_cache.items():
            for member_id, member_details in member_data.items():
                await self.config.member_from_ids(guild_id, member_id).points.set(
                    member_details["points"]
                )

    @_update_config.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        if guild_id not in self.settings_cache:
            return

        cache = self.settings_cache[guild_id]

        valid_keywords = filter(
            lambda x: message.channel.id in cache[x]["channels"]
            and x in message.content
            and message.author.id not in cache[x]["blacklisted_members"],
            cache,
        )

        def add_points(word: str):
            self.member_cache.setdefault(message.guild.id, {}).setdefault(
                message.author.id, {"points": 0}
            )["points"] += cache[word]["points"]

        deque(map(add_points, valid_keywords), maxlen=0)  # cursed?

    @commands.group(name="keywordpoints", aliases=["kwp", "keywordpoint", "kwpoints", "kwpoint"])
    async def kwp(self, ctx: commands.Context):
        """Manage keyword points"""

    @kwp.command(name="add")
    @commands.mod_or_permissions(manage_guild=True)
    async def kwp_add(
        self,
        ctx: commands.Context,
        keyword: str,
        points: int,
        channels: commands.Greedy[discord.TextChannel],
        blacklist_members: commands.Greedy[discord.Member] = [],
    ):
        """
        Add a keyword for your server.

        If a user says this keyword in a channel where it is enabled, they will be awarded the specified amount of points.

        channels is a required argument, blacklist_members is optional.
        """
        if not channels:
            return await ctx.send_help()

        guild_id = str(ctx.guild.id)
        if guild_id not in self.settings_cache:
            self.settings_cache[guild_id] = {}

        if keyword in self.settings_cache[guild_id]:
            await ctx.send(
                cf.error(
                    f"Keyword `{keyword}` already exists. Do you want to edit it with the given details? (reply with yes/no)"
                )
            )
            pred = MessagePredicate.yes_or_no(ctx)
            try:
                await self.bot.wait_for("message", check=pred, timeout=30)

            except asyncio.TimeoutError:
                return await ctx.send("Aborting...!")

            else:
                if not pred.result:
                    return await ctx.send("Aborting...!")

        self.settings_cache[guild_id][keyword] = {
            "points": points,
            "channels": [channel.id for channel in channels],
            "blacklisted_members": [member.id for member in blacklist_members],
        }

        await ctx.send(
            cf.success(
                f"Keyword `{keyword}` added with {points} points, enabled in {cf.humanize_list([channel.mention for channel in channels])} and blacklisted members: {cf.humanize_list([member.mention for member in blacklist_members]) or None}"
            )
        )

    @kwp.command(name="remove")
    @commands.mod_or_permissions(manage_guild=True)
    async def kwp_remove(self, ctx: commands.Context, keyword: str):
        """
        Remove a registered keyword in this server.

        `keyword` must be a vald keyword that is registered in this server"""

        guild_id = str(ctx.guild.id)
        if guild_id not in self.settings_cache or keyword not in self.settings_cache[guild_id]:
            return await ctx.send(cf.error(f"Keyword `{keyword}` does not exist."))

        del self.settings_cache[guild_id][keyword]
        await ctx.send(cf.success(f"Keyword `{keyword}` removed."))

    @kwp.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    @commands.mod_or_permissions(manage_guild=True)
    async def kwp_list(self, ctx: commands.Context):
        """List all keywords in this server."""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.settings_cache:
            return await ctx.send(cf.error("No keywords registered in this server."))

        keywords = self.settings_cache[guild_id]
        fields: List[Dict[str, Union[str, bool]]] = []

        def handle_keyword(keyword: str):
            details = keywords[keyword]
            fields.append(
                {
                    "name": f"**{keyword}**",
                    "value": (
                        f"Points Awarded: **{details['points']}**\n"
                        f"Channels: {cf.humanize_list([f'<#{channel}>' for channel in details['channels']])}\n"
                        f"Blacklisted Members: {cf.humanize_list([f'<@{member}>' for member in details['blacklisted_members']]) or 'No one is blacklisted.'}"
                    ),
                }
            )

        deque(map(handle_keyword, keywords), maxlen=0)

        embeds = await self.group_embeds_by_fields(
            *fields,
            per_embed=5,
            color=ctx.author.color.value,
            title=f"Keywords in {ctx.guild.name}",
        )

        if len(embeds) == 1:
            return await ctx.send(embed=embeds[0])

        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @kwp.command(name="leaderboard", aliases=["lb"])
    @commands.bot_has_permissions(embed_links=True)
    async def kwp_lb(self, ctx: commands.Context):
        """
        See a leaderboard of points of each member in the server."""
        if not self.member_cache or ctx.guild.id not in self.member_cache:
            return await ctx.send(cf.error("No points have been awarded yet."))

        members = dict(
            sorted(
                filter(
                    lambda x: ctx.guild.get_member(x[0]) is not None and x[1]["points"] > 0,
                    self.member_cache[ctx.guild.id].items(),
                ),
                key=lambda x: x[1]["points"],
                reverse=True,
            )
        )

        tab_data = map(
            lambda x: (str(ctx.guild.get_member(x[0])), str(x[1]["points"])), members.items()
        )
        headers = ("Member", "Points")

        tabbed = tabulate(tab_data, headers=headers, tablefmt="fancy_grid")

        return await ctx.send(
            embed=discord.Embed(
                title=f"Leaderboard for {ctx.guild.name}", description=cf.box(tabbed, lang="yaml")
            )
        )
