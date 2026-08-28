from typing import List, Union

import discord
from discord.ui import Button, Select, View
from redbot.core import commands


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
            discord.SelectOption(label=f"{i + 1}", value=i, description=f"Go to page {i + 1}")
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

        if self.use_select and len(contents) > 3:
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
        self.message = inter.message
        await inter.response.edit_message(content=content, embed=embed, view=self)
