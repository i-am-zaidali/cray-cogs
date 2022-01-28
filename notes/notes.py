import logging
import time
from typing import Dict, List, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from donationlogging.views import PaginationView

from .models import UserNote

global log
log = logging.getLogger("red.craycogs.notes")
log.setLevel(logging.DEBUG)


class Notes(commands.Cog):
    """
    Store moderator notes on users"""

    __version__ = "1.0.0"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot):
        self.bot: Red = bot
        self.config = Config.get_conf(None, 1, True, "Notes")
        self.config.register_member(notes=[])
        self.cache: Dict[int, Dict[int, List[UserNote]]] = {}

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
        members = await self.config.all_members()
        if not members:
            return
        final = {}
        for key, value in members.items():
            guild = self.bot.get_guild(key)
            final.update(
                {
                    guild.id: {
                        member: [
                            UserNote(bot=self.bot, guild=guild.id, **note)
                            for note in data["notes"]
                            if data["notes"]
                        ]
                        for member, data in value.items()
                    }
                }
            )

        log.debug(f"Cached all user notes.")

        self.cache = final

    async def to_config(self):
        if not self.cache:
            return
        for key, value in self.cache.copy().items():
            for member, notes in value.items():
                notes = [note.to_dict() for note in notes]
                await self.config.member_from_ids(key, member).notes.set(notes)

        log.debug(f"Saved all user notes")

    @classmethod
    async def initialize(cls, bot):
        self = cls(bot)
        await self.to_cache()
        return self

    def cog_unload(self):
        self.bot.loop.create_task(self.to_config())

    def _get_notes(self, guild: discord.guild, member: discord.Member = None):
        if not member:
            return self.cache.setdefault(guild.id, {})

        return self.cache.setdefault(guild.id, {}).setdefault(member.id, [])

    def _add_note(self, ctx: commands.Context, member: discord.Member, note: UserNote):
        user = self.cache.setdefault(ctx.guild.id, {}).setdefault(member.id, [])
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
        self, ctx: commands.Context, member: Optional[discord.Member] = None, *, note
    ):
        """
        Add a note to a user.

        The member argument is optional and defaults to the command invoker"""
        member = member or ctx.author
        note = UserNote(self.bot, ctx.guild.id, member.id, ctx.author.id, note, time.time())
        self._add_note(ctx, member, note)
        await ctx.send(f"Note added to **{member}**\nNote:- {note}")

    @commands.command(name="allnotes", aliases=["guildnotes"])
    @commands.mod_or_permissions(manage_messages=True)
    async def allnotes(self, ctx: commands.Context):
        """
        See all the notes ever taken in your server.

        This is a button based pagination session and each page contains a single user's notes"""
        notes = self._get_notes(ctx.guild)
        if not notes:
            return await ctx.send("No notes found for this server.")

        if len(notes) == 1:
            final = ""
            for user, n in notes.items():
                if not n:
                    return await ctx.send("No notes found for this server.")
                for i, note in enumerate(n, 1):
                    final += f"**{i}**. {note}/n"
            return await ctx.send(
                embed=discord.Embed(
                    title=f"Notes for {ctx.guild}", color=discord.Color.green()
                ).add_field(
                    name=f"**{ctx.guild.get_member(list(notes.keys())[0])}: **",
                    value=final,
                    inline=False,
                )
            )

        embeds = []
        for user, n in notes.items():
            final = ""
            if not n:
                continue
            for i, note in enumerate(n, 1):
                final += f"**{i}**. {note}\n"
            user = ctx.guild.get_member(user)
            embeds.append(
                discord.Embed(
                    title=f"Notes for {ctx.guild}", color=discord.Color.green()
                ).add_field(
                    name=f"**{user}: **",
                    value=final
                )
            )

        embeds = [
            embed.set_footer(text=f"Page {embeds.index(embed)+1}/{len(embeds)}")
            for embed in embeds
        ]

        if not embeds:
            return await ctx.send("No notes found for this server.")

        view = PaginationView(ctx, embeds, 60, True)
        await view.start()

    @commands.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def notes(self, ctx: commands.Context, member: discord.User = None):
        """
        See all the notes of a user.

        The member argument is optional and defaults to the command invoker"""
        member = member or ctx.author
        notes = self._get_notes(ctx.guild, member)
        embed = discord.Embed(color=await ctx.embed_color())
        embed.set_author(name=f"{member}", icon_url=member.display_avatar.url)
        if notes:
            embed.color = member.color

            for i, note in enumerate(notes, 1):
                embed.add_field(name=f"Note:- {i}", value=note, inline=False)
        else:
            embed.description = "No notes found"
        await ctx.send(embed=embed)

    @commands.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def delnote(self, ctx, member: Optional[discord.Member] = None, id: int = 0):
        """
        Delete a note of a user.

        The member argument is optional and defaults to the command invoker
        The id argument is the index of the note which can be checked with the `[p]notes` command"""
        member = member or ctx.author
        try:
            removed = self._remove_note(ctx, member, id)

        except Exception:
            return await ctx.send(
                f"That wasn't a valid id. use `{ctx.prefix}notes` to see which note number you wanna remove."
            )

        if not removed:
            return await ctx.send(f"There are no notes for that user.")
        return await ctx.send(f"Removed note: {id}. {removed}")

    @commands.command()
    @commands.mod_or_permissions(manage_messages=True)
    async def removenotes(self, ctx, user: discord.User = None):
        """
        Delete all notes of a user.

        The user argument is optional and defaults to the command invoker"""
        user = user or ctx.author
        notes = self._get_notes(ctx.guild, user)
        if not notes:
            return await ctx.send("No notes found.")

        self._remove_all_notes(ctx, user)
        return await ctx.send(f"Removed all notes for {user}")