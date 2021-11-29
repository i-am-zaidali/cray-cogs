from .giveaway import giveaways


async def setup(bot):
    bot.add_cog(await giveaways.inititalze(bot))
