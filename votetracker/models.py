from enum import Enum
from typing import Dict, Union

from redbot.core.bot import Red


class Types(Enum):
    test = 0
    upvote = 1


class VoteInfo:
    """
    A class wrapper for the data recieved from top.gg
    after someone votes."""

    def __init__(self, bot: Red, data: Dict[str, Union[str, int, bool]]) -> None:
        self.bot = bot
        self.raw = data
        # self._bot : int = data.get("bot") since the bot will always be our own
        self.user: int = data.get("user")
        self.type = Types[data.get("type")]
        self.is_weekend: bool = data.get("isWeekend")
