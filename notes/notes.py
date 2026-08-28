import asyncio
import logging
import math
import time as _time
from operator import attrgetter
from typing import Dict, List, Optional, TypeVar, Union, overload

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from .models import NoteType, UserNote
from .views import PaginationView

log = logging.getLogger("red.craycogs.notes")
log.setLevel(logging.DEBUG)

T = TypeVar("T")


def chunkify(iterable: list[T], chunk_size: int):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i : i + chunk_size]


class Notes(commands.Cog):
    """
    Store moderator notes on users
    """

    __version__ = "1.2.1"
    __author__ = ["crayyy_zee"]

    def __init__(self, bot):
        self.bot: Red = bot
        self.config = Config.get_conf(None, 1, True, "Notes")
        self.config.register_member(notes=[])
        self.cache: Dict[int, Dict[int, List[UserNote]]] = {}
        self.note_type = NoteType

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def to_cache(self):
        await self.bot.wait_until_red_ready()
        members = await self.config.all_members()
        if not members:
            return
        final = {}
        for key, value in members.items():
            guild = self.bot.get_guild(key)
            if guild:
                final.update(
                    {
                        guild.id: {
                            member: [
                                UserNote(bot=self.bot, guild=guild.id, **note)
                                for note in data["notes"]
                            ]
                            for member, data in value.items()
                        }
                    }
                )

        log.debug("Cached all user notes.")

        self.cache = final

    async def to_config(self):
        if not self.cache:
            return
        for key, value in self.cache.copy().items():
            for member, notes in value.items():
                notes = [note.to_dict() for note in notes]
                await self.config.member_from_ids(key, member).notes.set(notes)

        log.debug("Saved all user notes")

    @classmethod
    async def initialize(cls, bot):
        self = cls(bot)
        asyncio.create_task(self.to_cache())
        return self

    async def cog_unload(self):
        await self.to_config()

    def _create_note(
        self,
        guild: int,
        author: int,
        content: str,
        user: int = None,
        note_type: NoteType = None,
        time: int = None,
    ):
        note = UserNote(
            bot=self.bot,
            guild=guild,
            user=user,
            author=author,
            content=content,
            type=note_type,
            date=time or _time.time(),
        )
        self._add_note(note)
        return note

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

    @overload
    def _get_notes(self, guild: discord.Guild) -> Dict[int, List[UserNote]]: ...

    @overload
    def _get_notes(self, guild: discord.Guild, member: discord.Member) -> List[UserNote]: ...

    def _get_notes(self, guild: discord.Guild, member: discord.Member = None):
        if member is None:
            return self.cache.setdefault(guild.id, {})

        return self.cache.setdefault(guild.id, {}).setdefault(member.id, [])

    def _get_notes_of_type(self, guild: discord.Guild, member: discord.Member, type: NoteType):
        user = self._get_notes(guild, member)
        if not user:
            return []

        return [note for note in user if note.type == type]

    def _add_note(self, note: UserNote):
        user = self.cache.setdefault(note._guild, {}).setdefault(note._user, [])
        user.append(note)
        return user

    def _remove_note(self, ctx: commands.Context, member: discord.Member, index: int):
        user = self._get_notes(ctx.guild, member)
        if not user:
            return False

        return user.pop(index - 1)

    def _remove_all_notes(self, ctx: commands.Context, member: discord.Member):
        user = self._get_notes(ctx.guild, member)
        if not user:
            return False

        user.clear()
        return True

    @commands.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def setnote(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
        *,
        note,
    ):
        """
        Add a note to a user.

        The member argument is optional and defaults to the command invoker"""
        member = member or ctx.author
        note = self._create_note(
            ctx.guild.id, ctx.author.id, note, member.id, NoteType.RegularNote
        )
        await ctx.send(f"Note added to **{member}**\nNote:- {note}")

    @commands.command(name="allnotes", aliases=["guildnotes"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def allnotes(self, ctx: commands.Context):
        """
        See all the notes ever taken in your server.

        This is a button based pagination session and each page contains a single user's notes"""
        notes = self._get_notes(ctx.guild)
        if not notes:
            return await ctx.send("No notes found for this server.")

        if not any(notes.values()):
            return await ctx.send("No notes found for this server.")

        embeds = []
        total_pages = math.ceil(sum(1 for note_list in notes.values() for i in note_list) / 5)
        for user_id, n in notes.items():
            if not n:
                continue
            user = ctx.guild.get_member(user_id) or self.bot.get_user(user_id)
            if not user:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.HTTPException:
                    user = f"Unknown User ({user_id})"

            for page, chunk in enumerate(chunkify(n, 5)):
                final = f"**{user}**\n\n"
                for j, note in enumerate(chunk, 1):
                    final += f"""**{page * 5 + j}**. {"(Donation note)" if note.type is NoteType.DonationNote else ""} \n{note}\n\n"""
                embeds.append(
                    discord.Embed(
                        title=f"Notes for {ctx.guild}",
                        description=final,
                        color=discord.Color.green(),
                    ).set_footer(text=f"Page {page + 1}/{total_pages}")
                )

        if not embeds:
            return await ctx.send("No notes found for this server.")

        view = PaginationView(ctx, embeds, 60, True)
        await view.start()

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def notes(self, ctx: commands.Context, member: discord.User = commands.Author):
        """
        See all the notes of a user.

        The member argument is optional and defaults to the command invoker"""
        notes = self._get_notes(ctx.guild, member)
        if not notes:
            embed = discord.Embed(color=await ctx.embed_color())
            embed.set_author(name=f"{member}", icon_url=member.display_avatar.url)
            embed.description = "No notes found"
            return await ctx.send(embed=embed)

        fields = []
        for i, note in enumerate(notes, 1):
            fields.append({"name": f"Note #{i}", "value": note, "inline": False})

        embeds = await self.group_embeds_by_fields(
            *fields,
            page_in_footer=True,
            author__name=str(member),
            per_embed=5,
            color=member.color.value,
        )

        await PaginationView(ctx, embeds, 60, True).start()

    @commands.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def delnote(
        self,
        ctx,
        member: discord.Member = commands.parameter(
            default=attrgetter("author"), displayed_default="<you>"
        ),
        id: int = commands.parameter(converter=int, default=0),
    ):
        """
        Delete a note of a user.

        The member argument is optional and defaults to the command invoker
        The id argument is the index of the note which can be checked with the `[p]notes` command
        """
        try:
            removed = self._remove_note(ctx, member, id)

        except Exception:
            return await ctx.send(
                f"That wasn't a valid id. use `{ctx.prefix}notes` to see which note number you wanna remove."
            )

        if not removed:
            return await ctx.send("There are no notes for that user.")
        return await ctx.send(f"Removed note: {id}. {removed}")

    @commands.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def removenotes(self, ctx, user: discord.User = commands.Author):
        """
        Delete all notes of a user.

        The user argument is optional and defaults to the command invoker"""

        notes = self._get_notes(ctx.guild, user)
        if not notes:
            return await ctx.send("No notes found.")

        self._remove_all_notes(ctx, user)
        return await ctx.send(f"Removed all notes for {user}")
