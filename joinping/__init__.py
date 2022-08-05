import json
from pathlib import Path

from .main import JoinPing

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = JoinPing(bot)
    await cog._build_cache()
    await bot.add_cog(cog)
