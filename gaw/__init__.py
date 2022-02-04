from .main import Giveaways

async def setup(bot):
    cog = await Giveaways.initialize(bot)
    bot.add_cog(cog)