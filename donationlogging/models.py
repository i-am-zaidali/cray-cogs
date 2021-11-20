

import discord
from fuzzywuzzy import process
from typing import Dict, Tuple, Union

from redbot.core.bot import Red
from redbot.core import Config

class DonoUser:
    def __init__(self, bot: Red, dono_bank: str, guild_id: int, user_id: int, data: int = 0):
        self.bot = bot
        self.dono_bank = dono_bank
        self.guild_id = guild_id
        self.user_id = user_id
        self.donations = data
        
    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.guild_id)
    
    @property
    def user(self) -> discord.Member:
        return self.guild.get_member(self.user_id)

class DonoBank:
    def __init__(self, bot: Red, name: str, guild_id: int,  data: Dict[int, int]={}):
        self.bot = bot
        self.name = name
        self.guild_id = guild_id
        self._data = data
        
    def get_user(self, user_id: int) -> DonoUser:
        return DonoUser(self, self.guild_id, user_id, self._data.setdefault(user_id, 0))
    
class Donations:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=123_6969_420)
        # config structure would be something like:
        # {guild_id: {"categories": [list of category names], "category name": {user_id: amount}}}
        
        self.config.register_guild(categories=[])
        
    async def _verify_guild_category(self, guild_id: int, category: str) -> Tuple[bool, Union[Tuple[str, int], None]]:
        categories = await self.config.guild_from_id(guild_id).categories()
        org = category.lower() in categories
        match = process.extractOne(org, categories, score_cutoff=80) # Just to keep up with typos
        
        return (org and match), match
    
    async def _create_category(self, guild_id: int, category: str):
        if (tup:=await self._verify_guild_category(guild_id, category))[0]:
            raise ValueError(f"Category `{category}` already exists with the name {tup[1][0]}")
        
        async with self.config.guild_from_id(guild_id).categories() as categories:
            categories.append(category.lower())
            
        return tup[1][0] if tup[0] else category
            
    async def get_dono_bank(self, name: str, guild_id: int) -> DonoBank:
        try:
            name = await self._create_category(guild_id, name)
            
        except ValueError as e:
            pass
        
        return DonoBank(
            self.bot,
            name,
            guild_id,
            await getattr(self.config.guild_from_id(guild_id), name)()
        )