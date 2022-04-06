import contextlib
import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple, Union

import discord
from fuzzywuzzy import process
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list

from .exceptions import BankAlreadyExists, BankDoesNotExist, SimilarBankExists

log = logging.getLogger("red.craycogs.donationlogging.models")


@dataclass
class DonoItem:
    name: str
    amount: int
    bank: "DonoBank"


class DonoUser:
    def __init__(
        self, bot: Red, dono_bank: "DonoBank", guild_id: int, user_id: int, data: int = 0
    ):
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
    def __init__(
        self,
        bot: Red,
        manager: "DonationManager",
        name: str,
        emoji: str,
        guild_id: int,
        is_default: bool = False,
        hidden: bool = True,
        data: Dict[str, int] = {},
        items: List[DonoItem] = [],
    ):
        self.bot = bot
        self.manager = manager
        self.name = name
        self.emoji = emoji
        self.guild_id = guild_id
        self.is_default = is_default
        self.hidden = hidden
        self._data = data
        self.items = items

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash((self.name, self.guild_id))

    def get_user(self, user_id: int) -> DonoUser:
        return DonoUser(
            self.bot, self, self.guild_id, user_id, self._data.setdefault(str(user_id), 0)
        )

    def remove_user(self, user_id: int):
        with contextlib.suppress(KeyError):
            del self._data[str(user_id)]

    def get_leaderboard(self):
        lb = [
            DonoUser(self.bot, self, self.guild_id, user_id, amount)
            for user_id, amount in self._data.items()
        ]
        lb.sort(key=lambda x: x.donations, reverse=True)
        return lb

    async def get_item(self, item_name: str):
        items = {i.name: i for i in self.items}
        match = process.extractOne(item_name, items.keys())
        return items[match[0]] if match else None

    async def setroles(self, amountrolepairs: Dict[int, List[discord.Role]]):
        pairs = {}
        for k, v in amountrolepairs.items():
            pairs[k] = [role.id for role in v]
        async with self.manager.config.guild_from_id(self.guild_id).banks() as banks:
            banks.setdefault(
                self.name, {"emoji": self.emoji, "roles": {}}
            )  # edge case that the bank doesnt exist there.
            banks[self.name].setdefault("roles", {}).update(pairs)

    async def getroles(self, ctx) -> Dict[int, List[discord.Role]]:
        banks = await self.manager.config.guild_from_id(self.guild_id).banks()
        data = banks.get(self.name, {})
        roles = data.get("roles", {})
        return {
            amount: [_role for r in role if (_role := ctx.guild.get_role(int(r)))]
            for amount, role in roles.items()
            if isinstance(role, list)
        }

    async def addroles(self, ctx, user: discord.Member):
        # if not await self.config.guild(ctx.guild).autoadd():
        #     return f"Auto role adding is disabled for this server. Enable with `{ctx.prefix}donoset autorole add true`."
        try:
            data = await self.getroles(ctx)
            if not data:
                return
            amount = self.get_user(user.id).donations
            added_roles = set()
            for key, roles in data.items():
                if amount >= int(key):
                    added_roles.update({role for role in roles if not role in user.roles})
            added_roles = list(added_roles)
            await user.add_roles(
                *added_roles,
                reason=f"Automatic role adding based on donation logging, requested by {ctx.author}",
            )
            roleadded = (
                f"The following roles were added to `{user.name}`: {humanize_list([f'**{role.name}**' for role in added_roles])}"
                if added_roles
                else ""
            )
            return roleadded

        except Exception as e:
            log.exception("Error in addroles", exc_info=e)

    async def removeroles(self, ctx, user: discord.Member):
        try:
            data = await self.getroles(ctx)
            if not data:
                return
            amount = self.get_user(user.id).donations
            removed_roles: set = set()
            for key, roles in data.items():
                if key.isdigit() and amount < int(key):
                    removed_roles.update(roles)
            if removed_roles:
                await user.remove_roles(
                    *removed_roles,
                    reason=f"Automatic role removal based on donation logging, requested by {ctx.author}",
                )
            roleadded = (
                f"The following roles were removed from `{user.name}`: {humanize_list([f'**{role.name}**' for role in removed_roles])}"
                if removed_roles
                else ""
            )
            return roleadded

        except Exception as e:
            log.exception("An error occurred when removing roles: ", exc_info=e)


class DonationManager:
    _CACHE: List[DonoBank] = []

    def __init__(self, bot) -> None:
        self.bot = bot
        self.config = Config.get_conf(self, identifier=111)
        # config structure would be something like:
        # {
        #  guild_id: {
        #      "banks": {
        #          "bank name": {
        #               "emoji": emoji,
        #                "roles": {amount: roleid} # roles to assign
        #                "items": {},
        #                "hidden": bool
        #               }
        #          },
        #      "default_bank": "default bank name"
        #      "bank name": {
        #          user_id: amount
        #          }
        #      }
        #  }

        self.config.register_global(schema=0)
        self.config.register_guild(bank={}, default_bank=None)
        self.config.init_custom("guild_category", 2) #backwards compatibility for new schema
        self.config.init_custom("guild_bank", 2)
        self.config.register_custom("guild_bank", donations={})

    async def _verify_guild_bank(
        self, guild_id: int, bank: str
    ) -> Tuple[bool, Union[Tuple[str, int], None]]:
        banks = await self.config.guild_from_id(guild_id).banks()
        org = bank.lower() in banks.keys()
        match = process.extractOne(
            bank, banks.keys(), score_cutoff=80
        )  # Just to keep up with typos

        return (org and match), match[0] if match else None
        # if first value is true, the second one will almost always be the actual name
        # if first value is false, the second one will be a comparable match or None if not found at all.

    async def _create_bank(
        self,
        guild_id: int,
        bank: str,
        emoji: str = None,
        hidden: bool = False,
        force: bool = False,
    ):
        if (tup := await self._verify_guild_bank(guild_id, bank))[0]:
            raise BankAlreadyExists(f"Bank with that name already exists.", tup[1])

        elif not tup[0]:
            if tup[1] and not force:
                raise SimilarBankExists(
                    f"Bank with a similar name already exists. Pass True to the force Kwarg to bypass this error",
                    tup[1],
                )

        async with self.config.guild_from_id(guild_id).banks() as banks:
            banks.setdefault(bank.lower(), {"emoji": emoji, "roles": {}, "hidden": False})

        return bank.lower()

    async def _schema_0_to_1(self):
        for guild, data in (await self.config.all_guilds()).items():
            if not data.get("categories"):
                continue
            for bank_name, d in data["categories"].items():
                copy = d.copy()
                d.clear()
                d["emoji"] = copy.pop("emoji")
                d["roles"] = copy

            await self.config.guild_from_id(guild).categories.set(data["categories"])

        await self.config.schema.set(1)

    async def _schema_1_to_2(self):
        guilds = await self.config.all_guilds()
        for guild, data in guilds.items():
            if cat_data := data.get("categories"):
                data["banks"] = cat_data
                cat_data = self.config.custom("guild_category", guild)
                await self.config.custom("guild_bank", guild).set(await cat_data.all())
                await cat_data.clear()
                del data["categories"]

            if default_bank := data.get("default_category"):
                data["default_bank"] = default_bank
                del data["default_category"]

            await self.config.guild_from_id(guild).set(data)

        await self.config.schema.set(2)

    async def _populate_cache(self):
        if (schema := await self.config.schema()) == 0:
            await self._schema_0_to_1()
            schema += 1  # to keep up with its update within config itself

        elif schema == 1:
            await self._schema_1_to_2()

        for guild, data in (await self.config.all_guilds()).items():
            default = await self.get_default_bank(guild, False)
            if not data["banks"]:
                continue
            donations: dict = await self.config.custom("guild_bank", guild).all()
            for bank_name, d in data["banks"].items():
                try:
                    donos = donations.get(bank_name, {}).get("donations", {}).copy()
                    is_default = default == bank_name
                    hidden = d.get("hidden", False)
                    bank = DonoBank(
                        self.bot, self, bank_name, d["emoji"], guild, is_default, hidden, donos
                    )
                    items = d.get("items", {})
                    for name, amount in items.items():
                        bank.items.append(DonoItem(name, amount, bank))
                    self._CACHE.append(bank)

                except Exception as e:
                    log.exception("Error: ", exc_info=e)

        log.debug(f"DonationLogging cache populated with {len(self._CACHE)} entries.")

    async def _back_to_config(self):
        copy = self._CACHE.copy()
        if not copy:
            log.debug("DonationLogging cache is empty, not backing to config.")
            return

        for bank in copy:
            await self.config.custom("guild_bank", bank.guild_id, bank.name).donations.set(
                bank._data
            )
        log.debug("Cache backed up to config.")

    async def get_dono_bank(
        self, name: str, guild_id: int, *, emoji=None, hidden=False, force=False
    ) -> DonoBank:
        try:
            name = await self._create_bank(guild_id, name, emoji=emoji, force=force)

        except BankAlreadyExists as e:
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
            await self.get_default_bank(guild_id, False) == name,
            hidden,
            await self.config.custom("guild_bank", guild_id, name).donations(),
        )
        self._CACHE.append(bank)
        return bank

    async def get_existing_dono_bank(self, name: str, guild_id: int) -> DonoBank:
        for i in self._CACHE:
            if i.name == name and i.guild_id == guild_id:
                return i

        raise BankDoesNotExist(f"Bank with that name does not exist.", name)

    async def delete_all_user_data(self, user_id: int, guild_id: int = None):
        if not guild_id:
            for bank in self._CACHE:
                bank.remove_user(user_id)
                async with self.config.custom(
                    "guild_bank", bank.guild_id, bank.name
                ).donations() as data:
                    with contextlib.suppress(KeyError):
                        del data[user_id]

        else:
            banks = await self.get_all_dono_banks(guild_id)
            for bank in banks:
                bank.remove_user(user_id)

    async def clear_guild_settings(self, guild_id: int):
        await self.config.guild_from_id(guild_id).clear()
        await self.config.custom("guild_bank", guild_id).clear()
        for i in await self.get_all_dono_banks(guild_id):
            self._CACHE.remove(i)

    async def get_all_dono_banks(self, guild_id: int = None) -> List[DonoBank]:
        if not self._CACHE:
            await self._populate_cache()
        if not guild_id:
            return self._CACHE

        else:
            return list(filter(lambda x: x.guild_id == guild_id, self._CACHE))

    async def get_default_bank(self, guild_id: int, obj: bool = True) -> DonoBank:
        bank = await self.config.guild_from_id(guild_id).default_bank()
        if not bank:
            return None

        if obj:
            return await self.get_dono_bank(bank, guild_id)

        return bank

    async def set_default_bank(self, guild_id: int, bank: DonoBank):
        await self.config.guild_from_id(guild_id).default_bank.set(bank.name)

    @classmethod
    async def initialize(cls, bot):
        s = cls(bot)
        await s._populate_cache()
        return s
