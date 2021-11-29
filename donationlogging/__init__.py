import discord

from .dono import DonationLogging


async def setup(bot):
    bot.add_cog(await DonationLogging.initialize(bot))
