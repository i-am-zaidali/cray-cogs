import asyncio
import functools
import logging
import random
from dataclasses import make_dataclass
from typing import Dict, List, Literal, Optional, Tuple, Type, Union

import discord
from discord.ext.commands.converter import EmojiConverter
from emoji.unicode_codes import UNICODE_EMOJI_ENGLISH
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.errors import CogLoadError
from redbot.core.utils.chat_formatting import box, humanize_list, pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from redbot.core.utils.predicates import MessagePredicate
from tabulate import tabulate

from .CONSTANTS import dc_fields, global_defaults, lb_types, user_defaults
from .converters import ItemConverter, PlayerConverter
from .models import BaseItem, Player
from .utils import is_lt, no_special_characters
from .exceptions import ItemOnCooldown

log = logging.getLogger("red.craycogs.HitOrMiss")


class HitOrMiss(commands.Cog):
    """
    A snowball bot based (but hugely different) cog.

    And no it doesn't use slash commands.
    *Yet*."""

    __author__ = ["crayyy_zee#2900"]
    __version__ = "1.3.4"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=56789, force_registration=True)

        self.items: Dict[str, Type[BaseItem]] = {}
        self.cache: List[Player] = []

        self.config.register_global(**global_defaults)
        self.config.register_user(**user_defaults)

        self.converter = PlayerConverter()

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        if requester not in ("discord_deleted_user", "user"):
            return

        await self.config.user_from_id(user_id).clear()
        u = functools.reduce(lambda x: x.id == user_id, self.cache)
        if u:
            self.cache.remove(u)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    @staticmethod
    def group_embeds_by_fields(*fields: Dict[str, Union[str, bool]], per_embed: int = 3):
        """
        This was the result of a big brain moment i had

        This method takes dicts of fields and groups them into separate embeds
        keeping `per_embed` number of fields per embed.
        """
        groups: list[discord.Embed] = []
        for ind, i in enumerate(range(0, len(fields), per_embed)):
            groups.append(discord.Embed())
            fields_to_add = fields[i : i + per_embed]
            for field in fields_to_add:
                groups[ind].add_field(**field)
        return groups

    async def ask_for_answers(
        self,
        ctx: commands.Context,
        questions: List[Tuple[str, str, str, MessagePredicate]],
        timeout: int = 30,
    ) -> Dict[str, str]:
        """
        Ask the user a series of questions, and return the answers.
        """
        answers = {}
        message = None
        for question in questions:
            title, description, _type, check = question
            embed = discord.Embed(
                title=title, description=description, color=await ctx.embed_color()
            )
            embed.set_footer(text="You have {} seconds to answer.".format(timeout))
            if not message:
                message = await ctx.send(ctx.author.mention, embed=embed)
            else:
                await message.edit(embed=embed)
            m = await ctx.bot.wait_for("message", check=check, timeout=timeout)
            if _type == "emoji":
                if m.content.lower() == "none":
                    emoji = None

                elif m.content not in UNICODE_EMOJI_ENGLISH.keys():
                    try:
                        emoji = await EmojiConverter().convert(ctx, m.content)
                    except Exception as e:
                        return await ctx.send(e)

                else:
                    emoji = m.content

                check.result = str(emoji)

            try:
                await m.delete()
            except Exception:
                pass

            answers[_type] = check.result
        await message.delete()
        return answers

    async def _dict_to_class(self, name: str = None, d: dict = None):
        if not d and not name:
            items: dict = await self.config.items()
            for i, v in items.items():
                cls = make_dataclass(
                    i, dc_fields, bases=(BaseItem,), eq=True, unsafe_hash=True, init=False
                )(**v)
                self.items[i] = cls
        else:
            return make_dataclass(
                name, dc_fields, bases=(BaseItem,), eq=True, unsafe_hash=True, init=False
            )(**d)

    def filter_user_items(self, items):
        final = {}
        for key, value in items.items():
            item = functools.reduce(lambda x, y: x if x.name == key else y, self.items.values())
            final[item] = value

        return final

    async def _populate_cache(self):
        await self._dict_to_class()
        users = await self.config.all_users()
        for uid, data in users.items():
            data["items"] = self.filter_user_items(data["items"])

            self.cache.append(Player(self.bot, uid, data))

    @classmethod
    async def initialize(cls, bot):
        if not await bank.is_global():
            raise CogLoadError(
                "This cog requires the bank to be global. Please use `[p]bankset toggleglobal True` to do so before loading this cog."
            )
        s = cls(bot)
        await s._populate_cache()
        return s

    async def _unload(self):
        for player in self.cache.copy():
            await self.config.user_from_id(player.id).set(player.to_dict())

    def cog_unload(self):
        asyncio.create_task(self._unload())

    @commands.command(name="throw")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def throw(self, ctx, item: str = None, target: PlayerConverter = None):
        """Throw an item you own at a user"""
        if not item or not target:
            return await ctx.send_help()

        try:
            item: BaseItem = await ItemConverter().convert(ctx, item)
        except Exception as e:
            return await ctx.send(str(e))

        if not item.throwable:
            return await ctx.send(f"No, a {item} can not be thrown at others.")
        if target.id == ctx.author.id:
            return await ctx.send("Why do you wanna hurt yourself? sadistic much?")
        if target.user.bot:
            return await ctx.send("MY KIND. BACK OFF!")  # xD

        player = await self.converter.convert(ctx, f"{ctx.author.id}")
        try:
            result, string = player.throw(ctx.message, target, item)
            return await ctx.send(string)
        except (ValueError, ItemOnCooldown) as e:
            return await ctx.send(str(e))
        except Exception as e:
            log.exception("Error occurred in command `throw`: ", exc_info=e)
            return await ctx.send(f"An error occurred trying to throw `{item.name}` at `{target.name}`. Check logs for more information.")

    @commands.command(name="heal")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def heal(self, ctx: commands.Context):
        """
        Heal yourself.

        Use a medkit if you own one, to increase your hp from anywhere near 1 to 40."""
        medkit = self.items.get("MedKit")
        user = await self.converter.convert(ctx, str(ctx.author.id))
        old_hp = user.hp
        if not user.inv.get(medkit.name):
            return await ctx.send(
                "You dont own a MedKit. You need a medkit inorder to heal yourself."
            )

        if old_hp >= 75:
            return await ctx.send("Your hp needs to be less than 75 in order to use a medkit.")

        user.increase_hp(random.randrange(1, medkit.damage))
        user.inv.remove(medkit)
        return await ctx.send(
            f"You used a medkit you had and increased your hp by **{user.hp - old_hp}** and it is not **{user.hp}**"
        )

    @commands.group(name="hitormiss", aliases=["hom"], invoke_without_command=True)
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def hom(self, ctx):
        """Hit or Miss"""
        await ctx.send_help(ctx.command)

    @hom.command(name="shop", aliases=["items"])
    async def hom_shop(self, ctx: commands.Context):
        """
        See items available to buy for Hit Or Miss.

        User `[p]buy <item>` to buy an item."""

        fields = []

        for k, v in self.items.items():
            fields.append(
                {
                    "name": k.center(len(k) + 4, "*") + f" {v.emoji if v.emoji else ''}",
                    "value": f"> **Damage**: {v.damage}\n"
                    f"> **Throwable**: {v.throwable}\n"
                    f"> **Uses**: {v.uses}\n"
                    f"> **Cooldown**: {v.cooldown}\n"
                    f"> **Accuracy**: {v.accuracy}\n\n"
                    f"> ***Price***: {v.price} {await bank.get_currency_name()}",
                    "inline": False,
                }
            )

        embeds = self.group_embeds_by_fields(*fields)

        for embed in embeds:
            embed.title = "Hit or Miss Items"
            embed.description = "All the items available in H.O.M"
            embed.color = await ctx.embed_color()
            embed.set_thumbnail(url=ctx.guild.icon_url)
            embed.set_footer(text=f"Page {embeds.index(embed) + 1}/{len(embeds)}")

        return await menu(ctx, embeds, DEFAULT_CONTROLS)

    @hom.command(name="inventory", aliases=["inv"])
    async def hom_inv(self, ctx: commands.Context):
        """
        See all the items that you currently own in Hit Or Miss."""
        me = await self.converter.convert(ctx, f"{ctx.author.id}")
        if not me.inv.items:
            return await ctx.send(
                "You have no items in your inventory. Try buying some from the shop `[p]hitormiss shop`."
            )

        embed = discord.Embed(title=f"{me}'s Hit or Miss Inventory", color=await ctx.embed_color())

        for item, amount in me.inv.items.items():
            item_cooldown = (
                f"Can be used <t:{item.on_cooldown(me)}:R>."
                if (cd := item.on_cooldown(ctx.message))
                else "Not on cooldown."
            )
            embed.add_field(
                name=f"{item.__class__.__name__} {item.emoji if item.emoji else ''}",
                value=f"> **Amount Owned: ** {amount}\n"
                f"> **Uses remaining: ** {item.get_remaining_uses(me)}\n"
                f"> **On cooldown?: ** {item_cooldown}",
                inline=False,
            )

        return await ctx.send(embed=embed)

    @hom.command(name="buy", aliases=["purchase"], usage="[amount] <item>")
    async def hom_buy(
        self, ctx: commands.Context, amount: Optional[int] = None, item: ItemConverter = None
    ):
        """
        Buy a Hit Or Miss item for your inventory."""
        if not item:
            return await ctx.send_help()
        amount = amount or 1
        needed_to_buy = int(item.price) * amount
        if await bank.can_spend(ctx.author, needed_to_buy):
            me = await self.converter.convert(ctx, f"{ctx.author.id}")
            me.inv.add(item, amount)
            await bank.withdraw_credits(ctx.author, needed_to_buy)
            await self.config.user(ctx.author).set(me.to_dict())
            return await ctx.send(
                f"You have successfully bought {amount} {item.name}(s) for {needed_to_buy} {await bank.get_currency_name()}."
            )

        return await ctx.send(
            f"You do not have enough {await bank.get_bank_name()} to buy {amount} {item.name}(s)."
        )

    @hom.command(name="stats", aliases=["profile"])
    async def hom_stats(self, ctx: commands.Context, user: PlayerConverter = None):
        """
        See yours or others Hit Or Miss stats."""
        user: Player = user or await self.converter.convert(ctx, str(ctx.author.id))
        embed = discord.Embed(
            title=f"HitOrMiss stats for {user}",
            description=user.stats,
            color=await ctx.embed_color(),
        ).set_thumbnail(url=ctx.bot.user.avatar_url)

        await ctx.send(embed=embed)

    @hom.command(name="createitem", aliases=["make", "create", "newitem", "ci"])
    @commands.is_owner()
    async def hom_create(self, ctx: commands.Context):
        """
        Create a new Hit Or Miss item.

        Owner only command.
        This is an interactive questionaire asking you details about the item You want to create."""
        creating_questions = [
            (
                "What will be the name of this item?",
                "The name can have spaces in it but no special characters.\nAnd make sure the name is in PascalCase. For example: `SnowBall` and not `snowball`",
                "name",
                no_special_characters(ctx),
            ),
            (
                "What will be the price of this item?",
                "The price must be a number under 1,000,000.",
                "price",
                is_lt(1000000, ctx),
            ),
            (
                "What will be the damage of this item?",
                "The damage must be a number under 100.",
                "damage",
                is_lt(100, ctx),
            ),
            (
                "What will be the cooldown of this item?",
                "The cooldown must be a number under 1,000 seconds.",
                "cooldown",
                is_lt(1000, ctx),
            ),
            (
                "What will be the accuracy of this item?",
                "The accuracy must be a number under 100.",
                "accuracy",
                is_lt(100, ctx),
            ),
            (
                "How many uses does this item have before expiring?",
                "An item can only have a max of 5 usages.",
                "uses",
                is_lt(5, ctx),
            ),
            (
                "Does this item have an emoji?",
                "This emoji can be a custom one as long as the bot has access to it. Use `None` to skip ",
                "emoji",
                MessagePredicate.same_context(ctx),
            ),
        ]
        try:
            answers = await self.ask_for_answers(ctx, creating_questions, 45)
        except asyncio.TimeoutError:
            return await ctx.send(
                "You took too long to answer the questions correctly. Cancelling."
            )

        name = answers.pop("name")

        if functools.reduce(lambda x: x.lower() == name.lower(), self.items.keys()):
            return await ctx.send(f"An item with the name `{name}` already exists.")

        answers["throwable"] = True

        i = await self._dict_to_class(name, answers)
        self.items[name] = i
        async with self.config.items() as items:
            items[name] = answers

        return await ctx.send(
            f"New item `{name}`has been created: "
            + "\n".join([f"`{k}`: **{v}**" for k, v in answers.items()])
        )

    @hom.command(name="deleteitem", aliases=["remove", "delete", "di"])
    @commands.is_owner()
    async def hom_delete(self, ctx: commands.Context, item: ItemConverter):
        """
        Delete an item from the Hit Or Miss shop that you created.

        Owner only command."""
        name = item.__class__.__name__
        if name in global_defaults["items"]:
            return await ctx.send("Nope sorry, you cannot delete a default item.")

        del self.items[name]
        async with self.config.items() as items:
            del items[name]
        return await ctx.send(f"Item `{item.name}` has been deleted.")

    @hom.command(
        name="leaderboard",
        aliases=["lb", "top"],
        cooldown_after_parsing=True,
        usage="[type=kills] [global_or_local=False]",
    )
    async def hom_lb(
        self, ctx: commands.Context, _type: str = "kills", global_or_local: bool = False
    ):
        """
        Show the top players in the Hit Or Miss leaderboard.

        There are 6 ways learderboards can be sorted:
        - **Throws**: The leaderboard shows the top players who threw the most items.
        - **Kills**: The amount of kills users have. (default)
        - **Deaths**: The amount of times users have died.
        - **Hits**: The amount of times users have hit others.
        - **Misses**: The amount of times users have missed a throw.
        - **KDR**: The K/D ratio of user's kills to their deaths.
        - **All**: TO see all of the above at once. (This type won't be sorted and randomly placed.)

        Pass any of the above exactly to the `type` parameter.

        The leaderboard is `local` by default (only for the current server).
        To show the global leaderboard, pass `true` to the `global_or_local` argument.
        """
        if _type.lower() not in lb_types and _type.lower() != "all":
            return await ctx.send(
                "Invalid type. Valid types are `throws`, `kills`, `deaths`, `hits`, `misses`, `kdr` or `all`."
            )

        final = []

        users = self.cache.copy()
        if not users:
            return await ctx.send(
                "It seems like no one has played yet so I can't show you the leaderboard :("
            )
        if not _type.lower() == "all":
            users = sorted(users, key=lambda x: getattr(x, _type), reverse=True)
        for user in users:
            if not global_or_local and not ctx.guild.get_member(user.id) or user.is_new:
                continue
            f = [str(user)]
            if _type == "all":
                f += [f"{getattr(user, t):,}" for t in lb_types]
            else:
                f.append(f"{getattr(user, _type):,}")
            final.append(f)

        index = [i for i in range(1, len(final) + 1)]
        headers = ["UserName"] + (
            [t.capitalize() for t in lb_types] if _type == "all" else [_type.capitalize()]
        )

        msg = tabulate(final, tablefmt="rst", showindex=index, headers=headers)
        pages = []
        title = f"Hit Or Miss Leaderboard {'in ' + ctx.guild.name.capitalize() if not global_or_local else 'globally'}".center(
            20
        )
        for page in pagify(msg, delims=["\n"], page_length=700):
            page = title + "\n\n" + page + "\n\n"
            pages.append(box(page, lang="html"))

        if len(pages) == 1:
            return await ctx.send(pages[0])
        return await menu(ctx, pages, DEFAULT_CONTROLS)
