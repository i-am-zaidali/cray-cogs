import time

from .amari import AmariClient
from .flags import GiveawayFlags
from .giveaway import EndedGiveaway, Giveaway
from .guildsettings import config, get_guild_settings, get_role
from .requirements import Requirements
from .views import GiveawayView, YesOrNoView, PaginationView


def model_from_time(ends_at: int):
    if time.time() < ends_at:
        return Giveaway

    else:
        return EndedGiveaway
