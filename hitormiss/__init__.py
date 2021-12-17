from .main import HitOrMiss


async def setup(bot):
    cog = await HitOrMiss.initialize(bot)
    bot.add_cog(cog)
