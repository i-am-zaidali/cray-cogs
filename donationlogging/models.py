import discord
import logging
import contextlib

from fuzzywuzzy import process
from typing import Dict, List, Tuple, Union

from redbot.core.utils.chat_formatting import humanize_list
from redbot.core.bot import Red
from redbot.core import Config

from .exceptions import CategoryAlreadyExists, CategoryDoesNotExist, SimilarCategoryExists

log = logging.getLogger("red.craycogs.donationlogging.models")

class DonoUser:
    def __init__(self, bot: Red, dono_bank, guild_id: int, user_id: int, data: int = 0):
        self.bot = bot
        self.dono_bank = dono_bank
        self.guild_id = guild_id
        self.user_id = int(user_id)
        self.donations = data
        
    @property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.guild_id)
    
    @property
    def user(self) -> discord.Member:
        return self.guild.get_member(self.user_id)
    
    def add(self, amount: int):
        self.donations += amount
        self.dono_bank._data[str(self.user_id)] = self.donations
        return self.donations
    
    def remove(self, amount: int):
        self.donations -= amount if self.donations - amount >= 0 else self.donations
        self.dono_bank._data[str(self.user_id)] = self.donations
        return self.donations
    
    def clear(self):
        self.remove(self.donations)
        return self.donations

class DonoBank:
    def __init__(self, bot: Red, manager, name: str, emoji: str, guild_id: int,  data: Dict[int, int]={}):
        self.bot = bot
        self.manager = manager
        self.name = name
        self.emoji = emoji
        self.guild_id = guild_id
        self._data = data
        
    def __hash__(self):
        return hash((self.name, self.guild_id))
        
    def get_user(self, user_id: int) -> DonoUser:
        return DonoUser(self.bot, self, self.guild_id, user_id, self._data.setdefault(str(user_id), 0))
    
    def remove_user(self, user_id: int):
        with contextlib.suppress(KeyError):
            del self._data[str(user_id)]
    
    def get_leaderboard(self):
        lb = [
            DonoUser(self.bot, self, self.guild_id, user_id, amount) for user_id, amount in self._data.items()
        ]
        lb.sort(key=lambda x: x.donations, reverse=True)
        return lb
    
    async def setroles(self,  amountrolepairs:Dict[int, List[discord.Role]]):
        pairs = {}
        for k, v in amountrolepairs.items():
            pairs[k] = [role.id for role in v]
        async with self.manager.config.guild_from_id(self.guild_id).categories() as categories:
            categories.setdefault(self.name, {"emoji": self.emoji}) # edge case that the category doesnt exist there.
            categories[self.name].update(pairs)
            
    async def getroles(self, ctx):
        roles = await getattr(self.manager.config.guild_from_id(self.guild_id).categories, self.name)()
        roles.pop("emoji")
        return {amount: [ctx.guild.get_role(r) for r in role] for amount, role in roles.items()}
    
    async def addroles(self, ctx, user: discord.Member):
        # if not await self.config.guild(ctx.guild).autoadd():
        #     return f"Auto role adding is disabled for this server. Enable with `{ctx.prefix}donoset autorole add true`."
        try:
            data : dict = await (getattr(self.manager.config.guild(ctx.guild).categories, self.name))()
            data.pop("emoji")
            if not data:
                return
            amount = self.get_user(user.id).donations
            added_roles = set()
            for key, value in data.items():
                if amount >= int(key):
                    roles = [ctx.guild.get_role(int(val)) for val in value]
                    added_roles.update({role for role in roles if not role in user.roles})
            added_roles = list(added_roles)
            await user.add_roles(*added_roles, reason=f"Automatic role adding based on donation logging, requested by {ctx.author}")
            roleadded = f"The following roles were added to `{user.name}`: {humanize_list([f'**{role.name}**' for role in added_roles])}" if added_roles else ""
            return roleadded

        except Exception as e:
            raise e
        
    async def removeroles(self, ctx, user: discord.Member):
        try:
            data : dict = await getattr(self.manager.config.guild(ctx.guild).categories, self.name)()
            data.pop("emoji")
            if not data:
                return
            amount = self.get_user(user.id).donations
            removed_roles : set = {}
            for key, value in data.items():
                if amount < int(key):
                    roles = [ctx.guild.get_role(int(val)) for val in value]
                    removed_roles.update({role.name for role in roles if role in user.roles})
            await user.remove_roles(*removed_roles, reason=f"Automatic role removal based on donation logging, requested by {ctx.author}")
            roleadded = f"The following roles were added to `{user.name}`: {humanize_list(removed_roles)}" if removed_roles else ""
            return roleadded

        except:
            pass
    
class DonationManager:
    _CACHE : List[DonoBank] = []
    def __init__(self, bot) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=111)
        # config structure would be something like:
        # {
        #  guild_id: {
        #      "categories": {
        #          "category name": {
        #               "emoji": emoji,
        #                amount: roleid
        #               } # roles to assign
        #          },
        #      "default_category": "default category name"
        #      "category name": {
        #          user_id: amount
        #          }
        #      }
        #  }
        
        self.config.register_guild(categories={}, default_category=None)
        self.config.init_custom("guild_category", 2)
        self.config.register_custom("guild_category", donations={})
        
    async def _verify_guild_category(self, guild_id: int, category: str) -> Tuple[bool, Union[Tuple[str, int], None]]:
        categories = await self.config.guild_from_id(guild_id).categories()
        org = category.lower() in categories.keys()
        match = process.extractOne(category, categories.keys(), score_cutoff=80) # Just to keep up with typos
        
        return (org and match), match[0] if match else None 
        # if first value is true, the second one will almost always be the actual name
        # if first value is false, the second one will be a comparable match or None if not found at all.
    
    async def _create_category(self, guild_id: int, category: str, emoji: str = None, force:bool=False):
        if (tup:=await self._verify_guild_category(guild_id, category))[0]:
            raise CategoryAlreadyExists(f"Category with that name already exists.", tup[1])

        elif not tup[0]:
            if tup[1] and not force:
                raise SimilarCategoryExists(f"Category with a similar name already exists. Pass True to the force Kwarg to bypass this error", tup[1])
            
        
        async with self.config.guild_from_id(guild_id).categories() as categories:
            categories.setdefault(category.lower(), {"emoji": emoji})
            
        return category.lower()
    
    async def _populate_cache(self):
        for guild, data in (await self.config.all_guilds()).items():
            if not data["categories"]:
                continue
            for category_name, d in data["categories"].items():
                donos = await self.config.custom("guild_category", guild, category_name).donations()
                self._CACHE.append(
                    DonoBank(
                        self.bot,
                        self,
                        category_name,
                        d["emoji"],
                        guild,
                        donos
                        )
                    )
                
        log.debug(f"DonationLogging cache populated with {len(self._CACHE)} entries.")
        
    async def _back_to_config(self):
        copy = self._CACHE.copy()
        if not copy:
            log.debug("DonationLogging cache is empty, not backing to config.")
            return

        for i in copy:
            await self.config.custom("guild_category", i.guild_id, i.name).donations.set(i._data)
            log.debug("Cache backed up to config.")
            
    async def get_dono_bank(self, name: str, guild_id: int, *, emoji=None, force=False) -> DonoBank:
        try:
            name = await self._create_category(guild_id, name, emoji=emoji, force=force)
            
        except CategoryAlreadyExists as e:
            name = e.name
            
        for i in self._CACHE:
            if i.name == name and i.guild_id == guild_id:
                return i
        
        bank = DonoBank(
            self.bot,
            self,
            name,
            emoji,
            guild_id,
            await self.config.custom("guild_category", guild_id, name).donations()
        )
        self._CACHE.append(bank)
        return bank
    
    async def get_existing_dono_bank(self, name: str, guild_id: int) -> DonoBank:
        for i in self._CACHE:
            if i.name == name and i.guild_id == guild_id:
                return i
        
        raise CategoryDoesNotExist(f"Category with that name does not exist.", name)
    
    async def delete_all_user_data(self, user_id: int, guild_id:int=None):
        if not guild_id:
            for bank in self._CACHE:
                bank.remove_user(user_id)
                async with self.config.custom("guild_category", bank.guild_id, bank.name).donations() as data:
                    with contextlib.suppress(KeyError):
                        del data[user_id]
        
        else:
            banks = await self.get_all_dono_banks(guild_id)
            for bank in banks:
                bank.remove_user(user_id)
                    
    async def get_all_dono_banks(self, guild_id=None) -> List[DonoBank]:
        if not self._CACHE:
            await self._populate_cache()
        if not guild_id:
            return self._CACHE

        else:
            return list(filter(lambda x: x.guild_id == guild_id, self._CACHE))
    
    async def get_default_category(self, guild_id: int) -> DonoBank:
        cat = await self.config.guild_from_id(guild_id).default_category()
        return await self.get_dono_bank(cat, guild_id)
    
    async def set_default_category(self, guild_id: int, category: str):
        if not (await self._verify_guild_category(guild_id, category))[0]:
            raise CategoryDoesNotExist(f"The category {category} does not exist.", category)
        await self.config.guild_from_id(guild_id).default_category.set(category)
    
    @classmethod
    async def initialize(cls, bot):
        s = cls(bot)
        await s._populate_cache()
        return s