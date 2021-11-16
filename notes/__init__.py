from .notes import Notes

async def setup(bot):
    cog = await Notes.initialize(bot)
    bot.add_cog(cog)
    