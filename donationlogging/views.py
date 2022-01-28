from typing import Dict, List, Union

import discord
from discord.ui import Button, Select, View, button
from redbot.core import commands

from donationlogging.models import DonoBank


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
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)


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
        super().__init__(timeout=timeout, ctx=ctx)

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


# <--------------------- Category View --------------------->


class CategoriesSelect(Select):
    def __init__(
        self,
        ctx,
        categories: List[DonoBank],
        embeds: Dict[str, discord.Embed],
        add_all: bool,
        placeholder: str,
    ):
        placeholder = placeholder or "Select a category:"
        options = [
            discord.SelectOption(
                label=bank.name,
                value=bank.name,
                description=f"{ctx.guild.name}'s donation bank.",
                emoji="💰",
            )
            for bank in categories
        ]
        if add_all:
            options.insert(
                0,
                discord.SelectOption(
                    label="All", value="all", description="All donation banks.", emoji="💰"
                ),
            )
        self.embeds = embeds
        super().__init__(options=options, placeholder=placeholder)

    async def callback(self, interaction: discord.Interaction):

        await interaction.response.edit_message(embed=self.embeds[self.values[0]])


class CategorySelectView(ViewDisableOnTimeout):
    def __init__(
        self,
        ctx,
        categories: List[DonoBank],
        embeds: Dict[str, discord.Embed],
        add_all_select: bool,
        *,
        placeholder: str = None,
        timeout=180,
    ):
        super().__init__(timeout=timeout, ctx=ctx)

        self.embeds = embeds

        self.add_item(
            CategoriesSelect(ctx, categories, embeds, add_all_select, placeholder=placeholder)
        )
        self.add_item(CloseButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)


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
        super().__init__(timeout=timeout, ctx=context)

        self.ctx = context
        self.contents = contents
        self.use_select = use_select
        self.index = 0
        if not all(isinstance(x, discord.Embed) for x in contents) and not all(
            isinstance(x, str) for x in contents
        ):
            raise TypeError("All pages must be of the same type. Either a string or an embed.")

        if self.use_select:
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
        self.message = await inter.response.edit_message(content=content, embed=embed, view=self)
