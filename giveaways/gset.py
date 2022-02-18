import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list

from .converters import EmojiConverter
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

    @gset.group(name="embed")
    @commands.admin_or_permissions(administrator=True)
    async def gset_embed(self, ctx: commands.Context):
        """
        Customize the giveaway embed.

        Each sub command changes a different attribute of the embed and supplies different variables to be replaced."""

    @gset_embed.command(name="title")
    async def gset_embed_title(self, ctx, *, title: str):
        """
        Set the title of the embed of the giveaway message.

        Available variables are:
            - {prize} - The prize of the giveaway"""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.embed_title.set(title)
        await ctx.send(f"The new embed title has been set to \n```\n{title}\n```")

    @gset_embed.command(name="description")
    async def gset_embed_description(self, ctx: commands.Context, *, description: str):
        """
        Set the description of the embed of the giveaway message.

        Available variables are:
            - {prize}: The prize of the giveaway.
            - {emoji}: The emoji to react to.
            - {timestamp}: A proper timestamp `<t:1644937496:R> (<t:1644937496:F>)`
            - {raw_timestamp}: The timestamp in seconds so you can construct your own timestamp `<t:{raw_timestamp}:R>`
            - {server}: The name of the server.
            - {host}: The host of the giveaway. Includes the `.mention .id .name` attributes.
            - {donor}: The donor of the giveaway. Same as host.
            - {winners}: The amount of winners the giveaway has."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.embed_description.set(description)
        await ctx.send(f"The new embed description has been set to \n{box(description, 'py')}")

    @gset_embed.group(name="footer")
    async def gset_embed_footer(self, ctx: commands.Context):
        """
        Custom the giveaway embed footer.

        Use subcommands to customize the text and icon."""

    @gset_embed_footer.command(name="text")
    async def gset_embed_footer_text(self, ctx: commands.Context, *, text: str = ""):
        """
        Change the giveaway embed footer text.

        Available variables are:
            - {winners}: the number of winners of the giveaway.
            - {server}: the name of the server."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.embed_footer_text.set(text)
        await ctx.send(
            f"The new embed footer text has been set to \n{box(text, 'py')}"
            if text
            else "The embed footer text has been removed."
        )

    @gset_embed_footer.command(name="icon")
    async def gset_embed_footer_icon(self, ctx: commands.Context, *, icon: str = ""):
        """
        Change the giveaway embed footer icon.

        Provide a link to an image or video to set as the footer icon.
        Usable variables are:
            - {server_icon_url}: The server icon url.
            - {host_avatar_url}: The host's avatar url.

        If you use these variables, please don't add anything else."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.embed_footer_icon.set(icon)
        await ctx.send(
            f"The new embed footer icon has been set to \n{icon}"
            if icon
            else "The embed footer icon has been removed."
        )

    @gset_embed.command(name="thumbnail")
    async def gset_embed_thumbnail(self, ctx: commands.Context, *, thumbnail: str = ""):
        """
        Change the giveaway embed thumbnail.

        Provide a link to an image or video to set as the thumbnail.
        Usable variables are:
            - {server_icon_url}: The server icon url.
            - {host_avatar_url}: The host's avatar url.

        If you use these variables, please don't add anything else."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.embed_thumbnail.set(thumbnail)
        await ctx.send(
            f"The new embed thumbnail has been set to \n{thumbnail}"
            if thumbnail
            else "The embed thumbnail has been removed."
        )

    @gset_embed.command(name="color", aliases=["colour"])
    async def gset_embed_colour(self, ctx, colour: discord.Colour = discord.Color(0x303036)):
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
    async def gset_emoji(self, ctx, emoji: EmojiConverter):
        """
        Set a custom giveaway emoji that the bot reacts with on giveaway embeds.

        The bot must have access to the emoji to be used."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.emoji.set(str(emoji))
        await ctx.reply(f"The new giveaway emoji has been set to {emoji}")

    @gset.group(name="winnerdm", usage="<status>")
    @commands.admin_or_permissions(administrator=True)
    async def gset_winnerdm(self, ctx: commands.Context):
        """
        Customize the winner dm settings."""

    @gset_winnerdm.command(name="toggle")
    async def gset_winnerdm_toggle(self, ctx: commands.Context, toggle: bool):
        """
        Set whether the bot dms the winners when the giveaway ends.

        This won't be able to dm if the winners have their dms closed."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.winnerdm.set(toggle)
        await ctx.reply(
            "The winner will be dm'ed when the giveaway ends now."
            if toggle == True
            else "The winner will not be dm'ed when the giveaway ends."
        )

    @gset_winnerdm.command(name="message")
    async def gset_winnerdm_message(self, ctx: commands.Context, *, message: str):
        """
        Change the message that is sent to the winners when the giveaway ends.

        Available variables are:
            - {prize}: the prize of the giveaway.
            - {winners}: a formatted list of winners if somebody won else "There were no winners."
            - {winners_amount}: the number of winners of the giveaway.
            - {server}: the name of the server.
            - {jump_url}: the url to the giveaway."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.winnerdm_message.set(message)
        await ctx.reply(f"The new winner dm message has been set to \n{box(message, 'py')}")

    @gset.group(name="hostdm")
    @commands.admin_or_permissions(administrator=True)
    async def gset_hostdm(self, ctx: commands.Context):
        """
        Customize the host dm settings."""

    @gset_hostdm.command(name="toggle")
    async def gset_hostdm_toggle(self, ctx: commands.Context, toggle: bool):
        """
        Set whether the bot dms the host when the giveaway ends.

        This won't be able to dm if the host has their dms closed."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.hostdm.set(toggle)
        await ctx.reply(
            "The host will be dm'ed when the giveaway ends now."
            if toggle == True
            else "The host will not be dm'ed when the giveaway ends."
        )

    @gset_hostdm.command(name="message")
    async def gset_hostdm_message(self, ctx: commands.Context, *, message: str):
        """
        Change the message that is sent to the host when the giveaway ends.

        Available variables are:
            - {prize}: the prize of the giveaway.
            - {winners}: a formatted list of winners if somebody won else "There were no winners."
            - {winners_amount}: the number of winners of the giveaway.
            - {server}: the name of the server.
            - {jump_url}: the url to the giveaway."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.hostdm_message.set(message)
        await ctx.reply(f"The new host dm message has been set to \n{box(message, 'py')}")

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
            managers += [role.id for role in roles if role.id not in managers]
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

    @gset.command(name="reactdm", aliases=["rdm"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_rdm(self, ctx: commands.Context, status: bool):
        """
        Set whether the user is informed in dms if their entry is added to the giveaway."""
        settings = await get_guild_settings(ctx.guild.id, False)
        await settings.reactdm.set(status)
        await ctx.reply(
            "The user will be dmed when their entry is added to the giveaway."
            if status == True
            else "The user will not be dm'ed when their entry is added."
        )

    @gset.command(name="unreactdm", aliases=["urdm"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_urdm(self, ctx: commands.Context, status: bool):
        """
        Set whether the user is informed in dms when their reaction is removed from a giveaway message.
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
            f"**Message:** {message}\n\n"
            f"**Reaction Emoji:** {emoji}\n\n"
            f"**Will the winner be dm'ed?:** {winnerdm}\n\n"
            f"**Will the host be dm'ed?:** {hostdm}\n\n"
            f"**Will users be dmed if their reaction is removed?:** {settings.unreactdm}\n\n"
            f"**Auto delete Giveaway Commands?:** {autodelete}\n\n"
            f"**Embed color: **{color}\n\n"
            f"**Show defaults in giveaway embed?: **{show_defaults}\n\n"
            f"**Giveaway Thank message:** {box(tmsg)}\n\n"
            f"**Giveaway Ending message:** {box(endmsg)}\n\n"
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
