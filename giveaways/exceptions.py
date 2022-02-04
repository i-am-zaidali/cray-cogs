class GiveawayError(Exception):
    pass


class GiveawayAlreadyEnded(GiveawayError):
    pass


class GiveawayAlreadyStarted(GiveawayError):
    pass


class GiveawayNotStarted(GiveawayError):
    pass


class EntryInvalidated(GiveawayError):
    pass
