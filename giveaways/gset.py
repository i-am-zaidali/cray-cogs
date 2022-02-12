from typing import Union

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list

from .main import Giveaways
from .models import config, get_guild_settings, get_role


class Gset(Giveaways, name="Giveaways"):
    """
    Host embedded giveaways in your server with the help of reactions.
    This cog is a very complex cog and could be resource intensive on your bot.
    Use `giveaway explain` command for an indepth explanation on how to use the commands."""

    def __init__(self, bot: Red):
        super().__init__(bot)

    @commands.group(name="giveawaysettings", aliases=["gset", "giveawaysetting"])
    @commands.admin_or_permissions(administrator=True)
    async def gset(self, ctx):
        """
        Customize giveaways to how you want them.

        All subcommands represent a separate settings."""

    @gset.command(name="gmsg", usage="<message>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_gmsg(self, ctx, *, message):
        """
        Set a custom giveaway message.

        This message shows above the giveaway embed."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.msg.set(message)
        await ctx.reply(f"The new giveaway message has been set to \n```\n{message}\n```")

    @gset.command(name="tmsg")
    @commands.admin_or_permissions(administrator=True)
    async def gset_tmsg(self, ctx, *, message):
        """
        Set a custom message for giveaways.

        This message gets sent in an embed when you use the `--thank` flag while starting a giveaway.

        Usable variables:
                - donor :
                        donor.mention
                        donor.display_name
                        donor.name
                        donor.id

                - prize

        Use these variables within curly brackets.
        For Example:
                `[p]gset tmsg Donated by: {donor.mention}
                Prize: **{prize}**
                Please thank **{donor.name}** in #general`"""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.tmsg.set(message)
        await ctx.reply(f"The new giveaway message has been set to \n```\n{message}\n```")

    @gset.command(name="emoji", usage="<emoji>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_emoji(self, ctx, emoji: Union[discord.Emoji, discord.PartialEmoji]):
        """
        Set a custom giveaway emoji that the bot reacts with on giveaway embeds.

        The bot must have access to the emoji to be used."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.emoji.set(str(emoji))
        await ctx.reply(f"The new giveaway emoji has been set to {emoji}")

    @gset.command(name="winnerdm", usage="<status>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_winnerdm(self, ctx, status: bool):
        """
        Set whether the bot dms the winners when the giveaway ends.

        This won't be able to dm if the winners have their dms closed."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.winnerdm.set(status)
        await ctx.reply(
            "The winner will be dm'ed when the giveaway ends now."
            if status == True
            else "The winner will not be dm'ed when the giveaway ends."
        )

    @gset.command(name="hostdm", usage="<status>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_hostdm(self, ctx, status: bool):
        """
        Set whether the bot dms the host when the giveaway ends.

        This won't be able to dm if the host has their dms closed."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.hostdm.set(status)
        await ctx.reply(
            "The host will be dm'ed when the giveaway ends now."
            if status == True
            else "The host will not be dm'ed when the giveaway ends."
        )

    @gset.command(name="endmsg", usage="<message>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_endmsg(self, ctx, *, message):
        """
        Set the message that gets sent when a giveaway ends.

        Usable variables:
                - prize : The prize of the giveaway

                - winner : The winner(s) of the giveaway

                - link : The jumplink to the giveaway.

        For example:
                `[p]gset endmsg Congratulations {winner}! You have won the givaway for **{prize}**.
                {link}`"""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.endmsg.set(message)
        await ctx.reply(f"The ending message has been changed to\n```\n{message}\n```")

    @gset.command(name="manager", aliases=["managers"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_manager(self, ctx, *roles: discord.Role):
        """
        Set roles that can manage giveaways in your server.

        If you dont set this up, users will need either manage messages permission or the server's bot mod role."""
        if not roles:
            return await ctx.send(
                "You need to provide proper role ids or mentions to add them as managers"
            )

        settings = await get_guild_settings(ctx.guild.id, False)
        async with settings.manager() as managers:
            roles = set(roles)
            managers += [role.id for role in roles  if role.id not in managers]
        await ctx.reply(
            f"{humanize_list([role.mention for role in roles])} have been set as the giveaway managers!",
            allowed_mentions=discord.AllowedMentions(roles=False, replied_user=False),
        )

    @gset.command(name="pingrole", usage="<role>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_pingrole(self, ctx, role: discord.Role):
        """
        Set which role gets pinged in giveaways.

        This only takes effect when the `--ping` flag is used in giveaways."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.pingrole.set(role.id)
        await ctx.reply(
            f"{role.mention} has been set as the pingrole!",
            allowed_mentions=discord.AllowedMentions(roles=False, replied_user=False),
        )

    @gset.command(name="autodelete", aliases=["autodel"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def gset_autodelete(self, ctx, toggle: bool):
        """
        Set whether giveaway command invocations get automatically deleted or not.

        Pass true to delete and false to not."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.autodelete.set(toggle)
        await ctx.reply(
            "Giveaway commands will automatically delete now."
            if toggle == True
            else "Giveaway commands will retain."
        )

    @gset.command(name="blacklist", aliases=["bl"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_blacklist(self, ctx, roles: commands.Greedy[discord.Role] = None):
        """
        Blacklist roles from giveaway permanently without having to pass them as requirements each time.

        You can send multiple role ids or mentions.

        Sending nothing will show a list of blacklisted roles."""
        if not roles:
            settings = await get_guild_settings(ctx.guild.id)
            roles = settings.blacklist
            return await ctx.send(
                embed=discord.Embed(
                    title=f"Giveaway Blacklisted Roles in `{ctx.guild.name}`!",
                    description="\n\n".join(
                        [
                            ctx.guild.get_role(role).mention
                            for role in roles
                            if ctx.guild.get_role(role)
                        ]
                    )
                    if roles
                    else "No roles have been blacklisted from giveaways permanently.",
                    color=discord.Color.green(),
                )
            )

        settings = await get_guild_settings(ctx.guild.id, False)
        async with settings.blacklist() as bl:
            failed = []
            for role in roles:
                if not role.id in bl:
                    bl.append(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return await ctx.send(
            f"Blacklisted {humanize_list([f'`@{role.name}`' for role in roles])} permanently from giveaways."
            + (f"{humanize_list(failed)} were already blacklisted." if failed else "")
        )

    @gset.command(name="unblacklist", aliases=["ubl"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_unblacklist(self, ctx, roles: commands.Greedy[discord.Role]):
        """
        Unblacklist previously blacklisted roles from giveaways."""
        settings = await get_guild_settings(ctx.guild.id, False)
        async with settings.blacklist() as bl:
            failed = []
            for role in roles:
                if role.id in bl:
                    bl.remove(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return await ctx.send(
            f"UnBlacklisted {humanize_list([f'`@{role.name}`' for role in roles])} permanently from giveaways."
            + (f"{humanize_list(failed)} were never blacklisted" if failed else "")
        )

    @gset.group(name="bypass", aliases=["by"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_bypass(self, ctx):
        """
        See a list of roles that can bypass requirements in giveaways.

        Use subcommands for more specific actions."""
        settings = await get_guild_settings(ctx.guild.id)
        roles = settings.bypass
        return await ctx.send(
            embed=discord.Embed(
                title=f"Role Bypasses for `{ctx.guild.name}`!",
                description="\n\n".join(
                    [
                        ctx.guild.get_role(role).mention
                        for role in roles
                        if ctx.guild.get_role(role)
                    ]
                )
                if roles
                else "No role bypasses set in this server.",
                color=discord.Color.green(),
            )
        )

    @gset_bypass.command(name="add", aliases=["a"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_bypass_add(self, ctx, *roles: discord.Role):
        """
        Add one or more roles to the server's bypass list."""
        settings = await get_guild_settings(ctx.guild.id, False)
        async with settings.bypass() as by:
            failed = []
            for role in roles:
                if role.id not in by:
                    by.append(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return await ctx.send(
            f"Added giveaway bypass to {humanize_list([f'`@{role.name}`' for role in roles])}."
            + (f"{humanize_list(failed)} were never allowed to bypass" if failed else "")
        )

    @gset_bypass.command(name="remove", aliases=["r"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_bypass_remove(self, ctx, *roles: discord.Role):
        """
        Remove one or more roles from the server's bypass list."""
        settings = await get_guild_settings(ctx.guild.id, False)
        async with settings.bypass() as by:
            failed = []
            for role in roles:
                if role.id in by:
                    by.remove(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return await ctx.send(
            f"Removed giveaway bypass from {humanize_list([f'`@{role.name}`' for role in roles])}."
            + (f"{humanize_list(failed)} were never allowed to bypass" if failed else "")
        )

    @gset.group(name="multi", aliases=["rolemulti", "rm"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_multi(self, ctx):
        """
        See a list for all roles that have multipliers in giveaways in this server."""
        roles = await config.all_roles()
        roles = [
            ctx.guild.get_role(role)
            for role in filter(lambda x: ctx.guild.get_role(x) is not None, roles)
        ]
        return await ctx.send(
            embed=discord.Embed(
                title=f"Role Multipliers for `{ctx.guild.name}`'s giveaways!",
                description=box(
                    "\n\n".join(
                        [f"@{k.name:<10}  {'<'+'-'*15+'>':>5}  {v:>5}" for k, v in roles.items()]
                    )
                    if roles
                    else "No role multipliers set in this server."
                ),
                color=discord.Color.green(),
            )
        )

    @gset_multi.command(name="add", aliases=["a"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def role_multi_add(self, ctx, role: discord.Role, multi: int):
        """
        Add a multipier to a given role.

        This will increase the chances of the members of that role to win in giveaways."""
        if multi > 5:
            return await ctx.send("Multiplier can not be greater than 5.")
        settings = await get_role(role.id)
        await settings.multi.set(multi)
        return await ctx.send(
            f"Added `{role.name}` with multiplier `{multi}` to the server's role multipliers."
        )

    @gset_multi.command(name="remove", aliases=["r"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def role_multi_remove(self, ctx, role: discord.Role):
        """
        Remove multiplier from a given role."""
        settings = await get_role(role.id)
        await settings.multi.set(None)
        return await ctx.send(f"Removed `{role.name}` from the server's role multipliers.")

    @gset.command(name="color", aliases=["colour"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_colour(self, ctx, colour: discord.Colour = discord.Color(0x303036)):
        """
        Set the colour of giveaways embeds.

        if color is not passed, it will default to invisible embeds.
        Before this command is used, the global bot color will be used.
        Default is invisible (0x303036)."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.color.set(colour.value)
        embed = discord.Embed(
            title="Color successfully set!",
            description=f"Embed colors for giveaways will now be set to `{colour.value}`",
            color=colour,
        ).set_image(
            url=f"https://singlecolorimage.com/get/{str(colour)[1:]}/400x100.png"
        )  # i love this api *chef kiss*
        return await ctx.send(embed=embed)

    @gset.command(name="sdr", aliases=["show_default_requirements", "showdefault", "showdefaults"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_sdr(self, ctx):
        """
        Set whether the default requirements set through `[p]gset bypass/blacklist` should be shown in the giveaway embed.

        If set to False, the requirements would still be applied but not shown in the embed itself."""
        settings = await get_guild_settings(ctx.guild.id, False)
        current = await settings.show_defaults()
        await settings.show_defaults.set(not current)
        return await ctx.send(
            f"Showing default requirements in giveaway embeds has been {'enabled' if not current else 'disabled'}."
        )

    @gset.command(name="unreactdm", aliases=["urdm"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_urdm(self, ctx: commands.Context, status: bool):
        """
        Set whether the user is informed when their reaction is removed from a giveaway message.
        """
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.unreactdm.set(status)
        await ctx.reply(
            "The user will be dmed if their reaction is removed from the giveaway."
            if status == True
            else "The user will not be dm'ed when their reaction is removed."
        )

    @gset.command(name="showsettings", aliases=["ss", "show", "showset"])
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def gset_show(self, ctx):
        """
        See giveaway settings configured for your server"""
        settings = await get_guild_settings(ctx.guild.id)
        message = settings.msg
        tmsg = settings.tmsg
        emoji = settings.emoji
        winnerdm = settings.winnerdm
        hostdm = settings.hostdm
        endmsg = settings.endmsg
        managers = settings.manager
        autodelete = settings.autodelete
        color = discord.Color(settings.color) if settings.color else await ctx.embed_color()
        show_defaults = settings.show_defaults

        message = (
            f"**Message:** {message}\n"
            f"**Reaction Emoji:** {emoji}\n"
            f"**Will the winner be dm'ed?:** {winnerdm}\n"
            f"**Will the host be dm'ed?:** {hostdm}\n"
            f"**Will users be dmed if their reaction is removed?:** {settings.unreactdm}\n"
            f"**Auto delete Giveaway Commands?:** {autodelete}\n"
            f"**Embed color: **{color}\n"
            f"**Show defaults in giveaway embed?: **{show_defaults}\n"
            f"**Giveaway Thank message:** {box(tmsg)}\n"
            f"**Giveaway Ending message:** {box(endmsg)}\n"
            f"**Giveaway Managers:** {humanize_list([ctx.guild.get_role(manager).mention for manager in managers if ctx.guild.get_role(manager)]) if managers else 'No Managers set. Requires manage message permission or bots mod role.'}"
        )
        embed = discord.Embed(
            title=f"Giveaway Settings for **__{ctx.guild.name}__**",
            description=message,
            color=color,
        )

        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        embed.set_thumbnail(url=ctx.guild.icon_url)

        await ctx.send(embed=embed)
