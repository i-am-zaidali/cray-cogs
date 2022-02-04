import time

from .flags import GiveawayFlags
from .giveaway import EndedGiveaway, Giveaway
from .guildsettings import get_guild_settings, get_role, config
from .requirements import Requirements


def model_from_time(ends_at: int):
    if time.time() < ends_at:
        return Giveaway

    else:
        return EndedGiveaway
