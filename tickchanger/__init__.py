from .main import TickChanger


async def setup(bot):
    cog = await TickChanger.initialize(bot)
    bot.add_cog(cog)
