import logging

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from .utils import Coordinate

log = logging.getLogger("red.craycogs.joinping")

guild_defaults = {
    "ping_channels": [],
    "delete_after": 2,
    "ping_message": "{member.mention}",
}


class JoinPing(commands.Cog):
    """
    Ghost ping users when they join."""

    __version__ = "1.0.0"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=56789, force_registration=True)
        self.config.register_guild(**guild_defaults)
        self.cache = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def _build_cache(self):
        self.cache = await self.config.all_guilds()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild_data: dict = self.cache.get(member.guild.id)
        if not guild_data:
            return

        if not guild_data.get("ping_channels"):
            return

        for i in guild_data.get("ping_channels"):
            channel = self.bot.get_channel(i)
            if not channel:
                continue

            message = f"{(guild_data.get('ping_message', '')).format_map(Coordinate(member=member, server=member.guild.name, guild=member.guild.name))}"
            try:
                await channel.send(message, delete_after=guild_data.get("delete_after"))
            except discord.HTTPException:
                pass

        log.debug(
            f"{member} joined the guild {member.guild.name} and was pinged in {' '.join(guild_data.get('ping_channels'))}"
        )

    @commands.group(name="jpset", aliases=["joinpingset"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def jpset(self, ctx):
        """
        Adjust the settings for the cog."""
        return await ctx.send_help()

    @jpset.command(name="deleteafter", aliases=["da"])
    async def jpset_da(self, ctx, seconds: int):
        """Set the time in seconds after which the ping message will be deleted."""
        if seconds < 0:
            return await ctx.send("The time must be a positive integer.")
        await self.config.guild(ctx.guild).delete_after.set(seconds)
        await self._build_cache()
        await ctx.send(f"The ping message will be deleted after {seconds} seconds.")

    @jpset.command(name="message", aliases=["m"])
    async def jpset_msg(self, ctx, *, message: str):
        """Set the message that will be sent when a user joins.

        Usable placeholders include:
        - member (the member that joined)
            - member.mention (the mention)
            - member.id (the id)
            - member.name (the name)
            - member.discriminator (the discriminator)

        - server (the name of the server the member joined)

        These placeholders must be places within `{}` (curly brackets) to be replaced with actual values."""
        await self.config.guild(ctx.guild).ping_message.set(message)
        await self._build_cache()
        await ctx.send(f"The ping message has been set to:\n{message}")

    @jpset.group(name="channel", aliases=["c", "channels"], invoke_without_command=True)
    async def jpset_channels(self, ctx):
        """
        Set the channels where the pings will be sent on member join."""

    @jpset_channels.command(name="remove", aliases=["r"])
    async def jpsetchan_remove(self, ctx, *channels: discord.TextChannel):
        """
        Add the channels to the list of channels where the pings will be sent on member join."""
        cached_chans = self.cache.setdefault(ctx.guild.id, guild_defaults).get("ping_channels")
        al_present = []
        channels = list(channels)
        for i in channels.copy():
            if i.id not in cached_chans:
                al_present.append(i.id)

                channels.remove(i)

        final = set(cached_chans) - set(channels)

        await self.config.guild(ctx.guild).ping_channels.set(list(final))
        await self._build_cache()
        await ctx.send(
            f"The channel to ping in have been removed. There are currently {len(cached_chans)} channels."
        )

    @jpset_channels.command(name="add", aliases=["a"])
    async def jpsetchan_add(self, ctx, *channels: discord.TextChannel):
        """
        Remove the channels from the list of channels where the pings will be sent on member join."""
        cached_chans = self.cache.setdefault(ctx.guild.id, guild_defaults).get("ping_channels")
        al_present = []
        chans = []
        for i in channels:
            if i.id in cached_chans:
                al_present.append(i.id)
                continue

            chans.append(i.id)

        cached_chans += chans

        await self.config.guild(ctx.guild).ping_channels.set(cached_chans)
        await self._build_cache()
        await ctx.send(
            f"The channel to ping in have been added. There are currently {len(cached_chans)} channels.\n"
            + (
                f"The following channels were already present: {', '.join([f'<#{chan}>' for chan in al_present])}"
                if al_present
                else ""
            )
        )
