from inspect import iscoroutinefunction
from typing import List, Union

import discord
from discord.ui import Button, Select, View, button
from redbot.core import commands
from redbot.core.bot import Red

from .guildsettings import get_guild_settings


class JoinGiveawayButton(Button):
    def __init__(self, bot: Red, emoji, disabled: bool = False, callback=None):
        self.bot = bot
        super().__init__(
            label="Join Giveaway",
            emoji=emoji,
            style=discord.ButtonStyle.green,
            disabled=disabled,
            custom_id="JOIN_GIVEAWAY_BUTTON",
        )
        
        if not iscoroutinefunction(callback):
            raise TypeError("Callback must be a coroutine.")
        
        self._callback = callback

    @property
    def cog(self):
        return self.bot.get_cog("Giveaways")

    async def callback(self, interaction: discord.Interaction):
        await self._callback(self, interaction)


class GiveawayView(View):
    def __init__(self, bot, emoji, disabled=False):
        super().__init__(timeout=None)
        self.add_item(JoinGiveawayButton(bot, emoji, disabled, self.callback))
        
    @staticmethod
    async def callback(self: JoinGiveawayButton, interaction: discord.Interaction):

        if not self.cog:
            return await interaction.response.send_message(
                "Giveaways cog is not loaded so i cannot add your entry.", ephemeral=True
            )

        cache: dict = self.cog._CACHE

        guild: dict = cache.get(interaction.guild_id)

        if not guild:
            return await interaction.response.send_message(
                "This giveaway doesn't exist within my cache for some reason.", ephemeral=True
            )

        giveaway = guild.get(interaction.message.id)

        if not giveaway:
            return await interaction.response.send_message(
                "This giveaway doesn't exist within my cache for some reason.", ephemeral=True
            )

        if (
            giveaway.__class__.__name__ == "EndedGiveaway"
        ):  # doing it this way since importing the class will probably create a circular import
            # we will disable the button if the giveaway is ended but handling this just incase something goes wrong.
            return await interaction.response.send_message(
                "This giveaway has already ended. No more entries are being accepted.",
                ephemeral=True,
            )

        message = await giveaway.message

        result = await giveaway.add_entrant(interaction.user)
        if isinstance(result, str):  # entry wasn't valid. User didnt meet requirements
            embed = discord.Embed(
                title="Entry Invalidated!",
                description=result,
                color=discord.Color.red(),
            ).set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif result is False:  # User was already in entrants but reacted again.
            await giveaway.remove_entrant(interaction.user)
            embed = discord.Embed(
                title="Entry Removed!",
                description="Your entry for this giveaway has been removed.\n"
                "Reacting multiple times after your entry has been added, removes it.\n"
                "If this wasn't intentional, Click on the `Join Giveaway` button again to re-add your entry!",
                color=discord.Color.red(),
            ).set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif result is True:  # User has been added to the entrants
            embed = discord.Embed(
                title="Entry Verified!",
                description=f"You have been added as an entrant to [this]({giveaway.jump_url}) giveaway.\n"
                f"The winners for this giveaway will be announced **<t:{int(giveaway.ends_at.timestamp())}:R>**.\n"
                "Please have patience till then. Clicking on the button multiple times won't increase your chances of winning.",
                color=await giveaway.get_embed_colour(),
            ).set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        entrants = len(giveaway._entrants)
        self.label = "Join Giveaway ({} Entrants)".format(entrants)

        await message.edit(view=self.view)


# < ------------------------- Confirmation Stuff ------------------------- >


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


async def interaction_check(ctx: commands.Context, interaction: discord.Interaction):
    if not ctx.author.id == interaction.user.id:
        await interaction.response.send_message(
            "You aren't allowed to interact with this bruh. Back Off!", ephemeral=True
        )
        return False

    return True


class CloseButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.red, label="Close", emoji="❌")

    async def callback(self, interaction: discord.Interaction):
        await self.view.message.delete()
        self.view.stop()


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(self, **kwargs):
        self.message: discord.Message = None
        self.ctx: commands.Context = kwargs.pop("ctx")
        self.timeout_message: str = kwargs.pop("timeout_message")
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)
            if self.timeout_message:
                await self.ctx.send(self.timeout_message)


class YesOrNoView(ViewDisableOnTimeout):
    def __init__(
        self,
        ctx: commands.Context,
        yes_response: str = "you have chosen yes.",
        no_response: str = "you have chosen no.",
        *,
        timeout=180,
    ):
        self.yes_response = yes_response
        self.no_response = no_response
        self.value = None
        self.message = None
        super().__init__(timeout=timeout, ctx=ctx, timeout_message="You took too long to respond. Cancelling...")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    @button(label="Yes", custom_id="_yes", style=discord.ButtonStyle.green)
    async def yes_button(self, button: Button, interaction: discord.Interaction):
        disable_items(self)
        await interaction.response.edit_message(view=self)
        if self.yes_response:
            await self.ctx.send(self.yes_response)
        self.value = True
        self.stop()

    @button(label="No", custom_id="_no", style=discord.ButtonStyle.red)
    async def no_button(self, button: Button, interaction: discord.Interaction):
        disable_items(self)
        await interaction.response.edit_message(view=self)
        if self.no_response:
            await self.ctx.send(self.no_response)
        self.value = False
        self.stop()


# <-------------------Paginaion Stuff Below------------------->


class PaginatorButton(Button):
    def __init__(self, *, emoji=None, label=None):
        super().__init__(style=discord.ButtonStyle.green, label=label, emoji=emoji)


class ForwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}")

    async def callback(self, interaction: discord.Interaction):
        if self.view.index == len(self.view.contents) - 1:
            self.view.index = 0
        else:
            self.view.index += 1

        await self.view.edit_message(interaction)


class BackwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}")

    async def callback(self, interaction: discord.Interaction):
        if self.view.index == 0:
            self.view.index = len(self.view.contents) - 1
        else:
            self.view.index -= 1

        await self.view.edit_message(interaction)


class LastItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.index = len(self.view.contents) - 1

        await self.view.edit_message(interaction)


class FirstItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.index = 0

        await self.view.edit_message(interaction)


class PageButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, disabled=True)

    def _change_label(self):
        self.label = f"Page {self.view.index + 1}/{len(self.view.contents)}"


class PaginatorSelect(Select):
    def __init__(self, *, placeholder: str = "Select an item:", length: int):
        options = [
            discord.SelectOption(label=f"{i+1}", value=i, description=f"Go to page {i+1}")
            for i in range(length)
        ]
        super().__init__(options=options, placeholder=placeholder)

    async def callback(self, interaction: discord.Interaction):
        self.view.index = int(self.values[0])

        await self.view.edit_message(interaction)


class PaginationView(ViewDisableOnTimeout):
    def __init__(
        self,
        context: commands.Context,
        contents: Union[List[str], List[discord.Embed]],
        timeout: int = 30,
        use_select: bool = False,
    ):
        super().__init__(timeout=timeout, ctx=context, timeout_message=None)

        self.ctx = context
        self.contents = contents
        self.use_select = use_select
        self.index = 0
        if not all(isinstance(x, discord.Embed) for x in contents) and not all(
            isinstance(x, str) for x in contents
        ):
            raise TypeError("All pages must be of the same type. Either a string or an embed.")

        if self.use_select and len(self.contents) > 1:
            self.add_item(PaginatorSelect(placeholder="Select a page:", length=len(contents)))

        buttons_to_add = (
            [FirstItemButton, BackwardButton, PageButton, ForwardButton, LastItemButton]
            if len(self.contents) > 2
            else [BackwardButton, PageButton, ForwardButton]
            if not len(self.contents) == 1
            else []
        )
        for i in buttons_to_add:
            self.add_item(i())

        self.add_item(CloseButton())
        self.update_items()

    def update_items(self):
        for i in self.children:
            if isinstance(i, PageButton):
                i._change_label()
                continue

            elif self.index == 0 and isinstance(i, FirstItemButton):
                i.disabled = True
                continue

            elif self.index == len(self.contents) - 1 and isinstance(i, LastItemButton):
                i.disabled = True
                continue

            i.disabled = False

    async def start(self):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]
        self.message = await self.ctx.send(content=content, embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    async def edit_message(self, inter: discord.Interaction):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]

        self.update_items()
        await inter.response.edit_message(content=content, embed=embed, view=self)


# <---------------- First To React Stuff Below ---------------->

class FTRView(ViewDisableOnTimeout):
    def __init__(self, ctx: commands.Context, timeout, giveaway):
        self.giveaway = giveaway
        super().__init__(timeout=timeout, ctx=ctx, timeout_message="Nobody reacted in time. This giveaway has ended.")
        
        self.add_item(
            JoinGiveawayButton(ctx.bot, self.giveaway.emoji, False, self.clicked)
        )
        
    @staticmethod
    async def clicked(self:JoinGiveawayButton, interaction: discord.Interaction):
        giveaway = self.view.giveaway
        giveaway._entrants = [interaction.user.id]
        embed = interaction.message.embeds[0]
        embed.description = f"This giveaway has ended.\n**Winners:** {interaction.user.mention}\n**Host:** {giveaway.host.mention}"
        embed.color = discord.Color.red()
        embed.set_footer(
            text=f"{giveaway.guild.name} - Winners: 1", icon_url=getattr(giveaway.guild.icon, "url", None)
        )
        
        disable_items(self.view)
        
        await interaction.response.edit_message(
            content="GIVEAWAY ENDED!",
            embed=embed,
            view=self.view
        )
        
        settings = await get_guild_settings(giveaway.guild_id)
        
        await interaction.followup.send(
            content=settings.endmsg.format_map({"winner": interaction.user.mention, "prize": giveaway.prize, "link": giveaway.jump_url})
        )