from typing import Union

from discord.ext.commands.errors import CommandError


class ItemAlreadyExists(CommandError):
    pass


class ItemDoesntExist(CommandError):
    pass


class ItemOnCooldown(CommandError):
    def __init__(self, message=None, retry_after=None, *args):
        super().__init__(message=message, *args)
        self.retry_after: Union[int, float] = retry_after
