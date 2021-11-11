from redbot.core.errors import CogLoadError

from .main import VoteTracker


async def setup(bot):
    cog = await VoteTracker.initialize(bot)
    if cog:
        bot.add_cog(cog)
    else:
        raise CogLoadError(f"VoteTracker failed to load. Make sure api key and passwords are set.")
