import discord
from .dono import DonationLogging

def setup(bot):
    bot.add_cog(DonationLogging(bot))