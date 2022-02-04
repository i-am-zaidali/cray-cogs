from .guildsettings import get_guild_settings
from .requirements import Requirements
from .flags import GiveawayFlags
from .giveaway import Giveaway, EndedGiveaway

import time

def model_from_time(ends_at: int):
    if time.time() < ends_at:
        return Giveaway
    
    else:
        return EndedGiveaway