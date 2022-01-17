import discord


class Coordinate(dict):
    def __missing__(self, key):
        return f"{{{key}}}"


class SafeMember:
    def __init__(self, member: discord.Member):
        self._org = member
        self.id = member.id
        self.name = member.name
        self.mention = member.mention
        self.discriminator = member.discriminator

    def __str__(self) -> str:
        return self._org.__str__()
