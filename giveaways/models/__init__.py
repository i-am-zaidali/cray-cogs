import time

from .amari import AmariClient
from .flags import GiveawayFlags
from .giveaway import EndedGiveaway, Giveaway
from .guildsettings import get_guild_settings
from .requirements import Requirements
from .views import GiveawayView, PaginationView, YesOrNoView


def model_from_time(ends_at: int):
    if time.time() < ends_at:
        return Giveaway

    else:
        return EndedGiveaway
