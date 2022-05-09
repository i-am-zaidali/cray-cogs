from typing import Union

from discord.ext.commands.errors import BadArgument, CommandError


class ItemAlreadyExists(BadArgument):
    pass


class ItemDoesntExist(BadArgument):
    pass


class ItemOnCooldown(CommandError):
    def __init__(self, message=None, retry_after=None, *args):
        super().__init__(message=message, *args)
        self.retry_after: Union[int, float] = retry_after
