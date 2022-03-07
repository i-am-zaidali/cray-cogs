from .timers import Timer


async def setup(bot):
    bot.add_cog(await Timer.initialize(bot))
