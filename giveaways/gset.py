import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, humanize_list

from .events import main


class gsettings(main):
    def __init__(self, bot):
        super().__init__(bot)

    @commands.group(
        name="giveawaysettings", aliases=["gset", "giveawaysetting"], invoke_without_command=True
    )
    @commands.admin_or_permissions(administrator=True)
    async def gset(self, ctx):
        """
        Customize giveaways to how you want them.

        All subcommands represent a separate settings."""
        await ctx.send_help("gset")

    @gset.command(name="gmsg", usage="<message>")
    @commands.admin_or_permissions(administrator=True)
    async def gmsg(self, ctx, *, message):
        """
        Set a custom giveaway message.

        This message shows above the giveaway embed."""
        await self.config.set_guild_msg(ctx.guild, message)
        await ctx.reply(f"The new giveaway message has been set to \n```\n{message}\n```")

    @gset.command(name="tmsg")
    @commands.admin_or_permissions(administrator=True)
    async def tmsg(self, ctx, *, message):
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
        await self.config.set_guild_tmsg(ctx.guild, message)
        await ctx.reply(f"The new giveaway message has been set to \n```\n{message}\n```")

    @gset.command(name="emoji", usage="<emoji>")
    @commands.admin_or_permissions(administrator=True)
    async def emoji(self, ctx, emoji: discord.Emoji):
        """
        Set a custom giveaway emoji that the bot reacts with on giveaway embeds.

        The bot must have access to the emoji to be used."""
        await self.config.set_guild_emoji(ctx.guild, emoji)
        await ctx.reply(f"The new giveaway emoji has been set to {emoji}")

    @gset.command(name="winnerdm", usage="<status>")
    @commands.admin_or_permissions(administrator=True)
    async def winnerdm(self, ctx, status: bool):
        """
        Set whether the bot dms the winners when the giveaway ends.

        This won't be able to dm if the winners have their dms closed."""
        await self.config.set_guild_windm(ctx.guild, status)
        await ctx.reply(
            "The winner will be dm'ed when the giveaway ends now."
            if status == True
            else "The winner will not be dm'ed when the giveaway ends."
        )

    @gset.command(name="hostdm", usage="<status>")
    @commands.admin_or_permissions(administrator=True)
    async def hostdm(self, ctx, status: bool):
        """
        Set whether the bot dms the host when the giveaway ends.

        This won't be able to dm if the host has their dms closed."""
        await self.config.set_guild_hostdm(ctx.guild, status)
        await ctx.reply(
            "The host will be dm'ed when the giveaway ends now."
            if status == True
            else "The host will not be dm'ed when the giveaway ends."
        )

    @gset.command(name="endmsg", usage="<message>")
    @commands.admin_or_permissions(administrator=True)
    async def endmsg(self, ctx, *, message):
        """
        Set the message that gets sent when a giveaway ends.

        Usable variables:
                - prize : The prize of the giveaway

                - winner : The winner(s) of the giveaway

                - link : The jumplink to the giveaway.

        For example:
                `[p]gset endmsg Congratulations {winner}! You have won the givaway for **{prize}**.
                {link}`"""
        await self.config.set_guild_endmsg(ctx.guild, message)
        await ctx.reply(f"The ending message has been changed to\n```\n{message}\n```")

    @gset.command(name="manager", usage="<role>")
    @commands.admin_or_permissions(administrator=True)
    async def manager(self, ctx, *roles: discord.Role):
        """
        Set roles that can manage giveaways in your server.

        If you dont set this up, users will need either manage messages permission or the server's bot mod role."""
        if not roles:
            return await ctx.send(
                "You need to provide proper role ids or mentions to add them as managers"
            )
        await self.config.set_manager(ctx.guild, *list(roles))
        await ctx.reply(
            f"{humanize_list([role.mention for role in roles])} have been set as the giveaway managers!",
            allowed_mentions=discord.AllowedMentions(roles=False, replied_user=False),
        )

    @gset.command(name="pingrole", usage="<role>")
    @commands.admin_or_permissions(administrator=True)
    async def pingrole(self, ctx, role: discord.Role):
        """
        Set which role gets pinged in giveaways.

        This only takes effect when the `--ping` flag is used in giveaways."""
        await self.config.set_guild_pingrole(ctx.guild, role.id)
        await ctx.reply(
            f"{role.mention} has been set as the pingrole!",
            allowed_mentions=discord.AllowedMentions(roles=False, replied_user=False),
        )

    @gset.command(name="autodelete", aliases=["autodel"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def auto(self, ctx, toggle: bool):
        """
        Set whether giveaway command invocations get automatically deleted or not.

        Pass true to delete and false to not."""
        await self.config.set_guild_autodelete(ctx.guild, toggle)
        await ctx.reply(
            "Giveaway commands will automatically delete now."
            if toggle == True
            else "Giveaway commands will retain."
        )

    @gset.command(name="blacklist", aliases=["bl"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def bl_role(self, ctx, roles: commands.Greedy[discord.Role] = None):
        """
        Blacklist roles from giveaway permanently without having to pass them as requirements each time.

        You can send multiple role ids or mentions.

        Sending nothing will show a list of blacklisted roles."""
        if not roles:
            roles = await self.config.all_blacklisted_roles(ctx.guild, False)
            return await ctx.send(
                embed=discord.Embed(
                    title=f"Giveaway Blacklisted Roles in `{ctx.guild.name}`!",
                    description="\n\n".join([str(role.mention) for role in roles])
                    if roles
                    else "No roles have been blacklisted from giveaways permanently.",
                    color=discord.Color.green(),
                )
            )
        roles = await self.config.blacklist_role(ctx.guild, roles)
        await ctx.send(roles)

    @gset.command(name="unblacklist", aliases=["ubl"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def ubl_role(self, ctx, roles: commands.Greedy[discord.Role]):
        """
        Unblacklist previously blacklisted roles from giveaways."""
        roles = await self.config.unblacklist_role(ctx.guild, roles)
        return await ctx.send(roles)

    @gset.command(name="bypass", aliases=["by"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def by_role(self, ctx, add_or_remove=None, roles: commands.Greedy[discord.Role] = None):
        """
        Set roles to bypass all giveaways in your server.

        Passing no parameters will show a list of all roles set to bypass.

        1st argument should be either of add or remove
        2nd should be role ids or mentions separated by spaces."""
        if not add_or_remove and not roles:
            roles = await self.config.all_bypass_roles(ctx.guild, False)
            return await ctx.send(
                embed=discord.Embed(
                    title=f"Role Bypasses for `{ctx.guild.name}`!",
                    description="\n\n".join([str(role.mention) for role in roles])
                    if roles
                    else "No role bypasses set in this server.",
                    color=discord.Color.green(),
                )
            )
        if not add_or_remove.lower() in ["add", "remove"]:
            return await ctx.send_help("gset bypass")
        if add_or_remove.lower() == "add":
            roles = await self.config.bypass_role(ctx.guild, roles)
            return await ctx.send(roles)

        roles = await self.config.unbypass_role(ctx.guild, roles)
        return await ctx.send(roles)

    @gset.command(name="multi", aliases=["rolemulti", "rm"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def role_multi(
        self, ctx, add_or_remove=None, role: discord.Role = None, multi: int = None
    ):
        """
        Add role multipliers for giveaways.

        This multiplier gives extra entries to users with that role in giveaways.
        If a user has multiple roles each with its separate multiplier, all of them will apply to him.
        A role's multiplier can not be greater than 5.

        Passing no parameters will show you the current multipliers of the server.
        [add_or_remove] takes either of 'add' or 'remove'.
        [role] is the role name, id or mention and
        [multi] is the multiplier amount. **Must be under 5**. This is not required when you are removing."""
        if not add_or_remove and not role and not multi:
            roles = await self.config.get_all_roles_multi(ctx.guild)
            return await ctx.send(
                embed=discord.Embed(
                    title=f"Role Multipliers for `{ctx.guild.name}`'s giveaways!",
                    description=box(
                        "\n\n".join(
                            [
                                f"@{k.name:<10}  {'<'+'-'*15+'>':>5}  {v:>5}"
                                for k, v in roles.items()
                            ]
                        )
                        if roles
                        else "No role multipliers set in this server."
                    ),
                    color=discord.Color.green(),
                )
            )

        if not add_or_remove.lower() in ["add", "remove"]:
            return await ctx.send_help("gset multi")

        if add_or_remove.lower() == "add":
            if multi > 5:
                return await ctx.send("Multipliers must be under 5x.")
            role = await self.config.set_role_multi(role, multi)
            return await ctx.send(role)

        else:
            role = await self.config.reset_role_multi(role)
            return await ctx.send(role)

    @gset.command(name="et", aliases=["edit_timer"])
    @commands.admin_or_permissions(administrator=True)
    async def edit_timers(self, ctx, enable_or_disable: bool):
        """
        Configure whether you want to edit the timers for your server's giveaways.

        If disabled, the embed will use discord's native timestamps or else will use text
        to show the remaining time for the giveaway to end.

        **NOTE TO BOT OWNER:**
            > This has the potential of ratelimiting your bot and if you want to prevent that,
            > disable this command globally using `[p]command disable gset et`."""
        await self.config.set_guild_timer(ctx.guild, enable_or_disable)
        return await ctx.send(
            f"Editing timers for giveaways has been {'enabled' if enable_or_disable else 'disabled'}."
        )

    @gset.command(name="color", aliases=["colour"])
    @commands.admin_or_permissions(administrator=True)
    async def gset_colour(self, ctx, colour: discord.Colour = discord.Color(0x303036)):
        """
        Set the colour of giveaways embeds.

        if color is not passed, it will default to invisible embeds.
        Before this command is used, the global bot color will be used.
        Default is invisible (0x303036)."""
        await self.config.set_guild(ctx.guild, "color", colour.value)
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
        current = await self.config.get_guild(ctx.guild, "show_defaults")
        await self.config.set_guild(ctx.guild, "show_defaults", not current)
        return await ctx.send(
            f"Showing default requirements in giveaway embeds has been {'enabled' if not current else 'disabled'}."
        )

    @gset.command(name="showsettings", aliases=["ss", "show", "showset"])
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def show(self, ctx):
        """
        See giveaway settings configured for your server"""
        message = await self.config.get_guild_msg(ctx.guild)
        tmsg = await self.config.get_guild_tmsg(ctx.guild)
        emoji = await self.config.get_guild_emoji(ctx.guild)
        winnerdm = await self.config.dm_winner(ctx.guild)
        hostdm = await self.config.dm_host(ctx.guild)
        endmsg = await self.config.get_guild_endmsg(ctx.guild)
        managers = await self.config.get_managers(ctx.guild)
        autodelete = await self.config.config.guild(ctx.guild).autodelete()

        embed = discord.Embed(
            title=f"Giveaway Settings for **__{ctx.guild.name}__**",
            description=f"""
**Giveaway Managers:** {humanize_list([manager.mention for manager in managers if manager]) if managers else "No managers set. Requires manage message permission or bot's mod role."}
**Message:** {message}
**Reaction Emoji:** {emoji}
**Will the winner be dm'ed?:** {winnerdm}
**Will the host be dm'ed?:** {hostdm}
**Auto delete Giveaway Commands?:** {autodelete}
**Embed color: **{await self.get_embed_color(ctx)}
**Show defaults in giveaway embed?: **{await self.config.get_guild(ctx.guild, "show_defaults")}
**Giveaway Thank message:** {box(tmsg)}
**Giveaway Ending message:** {box(endmsg)}
			""",
            color=await self.get_embed_color(ctx),
        )

        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon_url)
        embed.set_thumbnail(url=ctx.guild.icon_url)

        await ctx.send(embed=embed)
