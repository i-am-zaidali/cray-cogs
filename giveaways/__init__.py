from .gset import Gset


async def setup(bot):
    cog = await Gset.initialize(bot)
    bot.add_cog(cog)
