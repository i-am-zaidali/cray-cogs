import logging
import typing

import discord
import TagScriptEngine as tse
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list

log = logging.getLogger("red.craycogs.joinping")

guild_defaults = {
    "ping_channels": [],
    "delete_after": 2,
    "ping_message": "{member(mention)}",
}


class JoinPing(commands.Cog):
    """
    Ghost ping users when they join.
    """

    __version__ = "1.1.2"
    __author__ = ["crayyy_zee"]

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

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        return True

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_data: dict = self.cache.get(member.guild.id)
        if not guild_data:
            return

        if not guild_data.get("ping_channels"):
            return

        message = guild_data.get("ping_message", "")
        engine = tse.AsyncInterpreter(
            [
                tse.EmbedBlock(),
                tse.LooseVariableGetterBlock(),
                tse.StrictVariableGetterBlock(),
            ]
        )
        resp = await engine.process(
            message,
            seed_variables={
                "member": tse.MemberAdapter(member),
                "server": tse.GuildAdapter(member.guild),
            },
        )
        if not resp.body and not resp.actions.get("embed"):
            return

        for i in guild_data.get("ping_channels"):
            channel = self.bot.get_channel(i)
            if not channel:
                continue

            if channel.permissions_for(member.guild.me).send_messages is False:
                continue

            if channel.permissions_for(member.guild.me).embed_links is False and isinstance(
                emb := resp.actions.get("embed"), discord.Embed
            ):
                await channel.send(f"{member.mention} {emb.description or ''}")
                continue

            try:
                await channel.send(
                    content=resp.body or None,
                    embed=resp.actions.get("embed"),
                    delete_after=guild_data.get("delete_after"),
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except discord.HTTPException:
                pass

        log.debug(
            f"{member} joined the guild {member.guild.name} and was pinged in {humanize_list([str(i) for i in guild_data.get('ping_channels')])}"
        )

    @commands.group(name="jpset", aliases=["joinpingset"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def jpset(self, ctx):
        """
        Adjust the settings for the cog."""
        return await ctx.send_help()

    @jpset.command(name="test", aliases=["testping"], hidden=True)
    @commands.bot_has_permissions(embed_links=True)
    async def jpset_test(self, ctx):
        """
        Test whether the pings and message you set up work correctly.

        This is hidden as to not abuse the pings.
        """
        if not self.cache.get(ctx.guild.id):
            return await ctx.send("You haven't set up the join ping yet ._.")

        await self.on_member_join(ctx.author)

    @jpset.command(name="deleteafter", aliases=["da"])
    @commands.bot_has_permissions(embed_links=True)
    async def jpset_da(self, ctx, seconds: int):
        """Set the time in seconds after which the ping message will be deleted."""
        if seconds < 0:
            return await ctx.send("The time must be a positive integer.")
        await self.config.guild(ctx.guild).delete_after.set(seconds)
        await self._build_cache()
        await ctx.send(f"The ping message will be deleted after {seconds} seconds.")

    @jpset.command(name="message", aliases=["m"])
    @commands.bot_has_permissions(embed_links=True)
    async def jpset_msg(self, ctx, *, message: str):
        """Set the message that will be sent when a user joins.

        Usable placeholders include:
        - {member} (the member that joined)
            - {member(mention)} (the mention)
            - {member(id)} (the id)
            - {member(name)} (the name)
            - {member(discriminator)} (the discriminator)

        - {server} (the server the member joined)

        This messsage uses tagscript and allows embed
        """
        await self.config.guild(ctx.guild).ping_message.set(message)
        await self._build_cache()
        await ctx.send(f"The ping message has been set to:\n{message}")

    @jpset.group(name="channel", aliases=["c", "channels"], invoke_without_command=True)
    @commands.bot_has_permissions(embed_links=True)
    async def jpset_channels(self, ctx):
        """
        Set the channels where the pings will be sent on member join."""
        return await ctx.send_help()

    @jpset_channels.command(name="remove", aliases=["r"])
    @commands.bot_has_permissions(embed_links=True)
    async def jpsetchan_remove(self, ctx, *channels: typing.Union[discord.TextChannel, int]):
        """
        Add the channels to the list of channels where the pings will be sent on member join."""
        cached_chans = self.cache.setdefault(ctx.guild.id, guild_defaults).get("ping_channels")
        channels = {getattr(x, "id", x) for x in channels}
        not_present = []
        for i in channels:
            try:
                cached_chans.remove(i)

            except ValueError:
                not_present.append(i)

        await self.config.guild(ctx.guild).ping_channels.set(cached_chans)
        await self._build_cache()
        await ctx.send(
            f"The channel to ping in have been removed. There are currently {len(cached_chans)} channels."
            + (
                f"Following channels were not present in the list: {humanize_list([f'<#{chan}>' for chan in not_present])}"
                if not_present
                else ""
            )
        )

    @jpset_channels.command(name="add", aliases=["a"])
    @commands.bot_has_permissions(embed_links=True)
    async def jpsetchan_add(self, ctx, *channels: discord.TextChannel):
        """
        Remove the channels from the list of channels where the pings will be sent on member join.
        """
        cached_chans = self.cache.setdefault(ctx.guild.id, guild_defaults).get("ping_channels")
        al_present = (channels := {a.id for a in channels}) & set(cached_chans)
        channels -= al_present
        cached_chans += channels
        await self.config.guild(ctx.guild).ping_channels.set(cached_chans)
        await self._build_cache()
        await ctx.send(
            f"The channel to ping in have been added. There are currently {len(cached_chans)} channels.\n"
            + (
                f"The following channels were already present: {humanize_list([f'<#{chan}>' for chan in al_present])}"
                if al_present
                else ""
            )
        )

    @jpset.command(name="show", aliases=["showsettings", "settings", "setting"])
    @commands.bot_has_permissions(embed_links=True)
    async def jpset_show(self, ctx):
        """
        Show the current joinping settings.
        """
        data = self.cache.setdefault(ctx.guild.id, guild_defaults)
        channels = data.get("ping_channels", [])
        message = data.get("ping_message", "{member.mention}")
        delete_after = data.get("delete_after", 2)
        if not channels:
            return await ctx.send(
                f"JoinPing is not enabled for your guild. Please enable first by running the `{ctx.prefix}jpset channels` command."
            )

        embed = (
            discord.Embed(
                title=f"JoinPing Settings for **__{ctx.guild.name}__**",
                color=await ctx.embed_colour(),
            )
            .add_field(
                name="Channels", value=" ".join([f"<#{i}>" for i in channels]), inline=False
            )
            .add_field(name="Message", value=box(message, "py"), inline=False)
            .add_field(
                name="Delete After (seconds)", value=box(f"{delete_after} seconds"), inline=False
            )
        )

        await ctx.send(embed=embed)
