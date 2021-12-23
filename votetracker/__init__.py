import json
from pathlib import Path

from redbot.core.errors import CogLoadError

from .main import VoteTracker

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = await VoteTracker.initialize(bot)
    if cog:
        bot.add_cog(cog)
    else:
        raise CogLoadError(f"VoteTracker failed to load. Make sure api key and passwords are set.")
