import asyncio

import discord
from redbot.core import Config
from redbot.core.utils.chat_formatting import humanize_list

from .models import Giveaway, Requirements


class conf:
    cache = []
    ended_cache = []

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(None, 234_6969_420, True, cog_name="Giveaways")

        default_guild = {
            "msg": ":tada:Giveaway:tada:",
            "emoji": "🎉",
            "winnerdm": True,
            "hostdm": True,
            "endmsg": "Congratulations :tada:{winner}:tada:. You have won the giveaway for ***{prize}***.\n{link}",
            "tmsg": "Prize: {prize}\nDonor: {donor.mention}\n\nThank the donor in general chat",
            "manager": [],
            "pingrole": None,
            "autodelete": False,
            "edit_timer": False,
            "blacklist": [],
            "bypass": [],
            "top_managers": {},
        }

        default_role = {"multi": 0}

        default_global = {"activegaws": [], "endedgaws": [], "already_sent": False}

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_role(**default_role)

    async def _sent_message(self, b: bool = None):
        if not b:
            return await self.config.already_sent()
        await self.config.already_sent.set(True)

    async def get_guild_timer(self, guild: discord.Guild):
        return await self.config.guild(guild).edit_timer()

    async def get_guild_msg(self, guild: discord.Guild):
        return await self.config.guild(guild).msg()

    async def get_guild_tmsg(self, guild: discord.Guild):
        return await self.config.guild(guild).tmsg()

    async def get_guild_endmsg(self, guild: discord.Guild):
        return await self.config.guild(guild).endmsg()

    async def dm_winner(self, guild: discord.Guild):
        return await self.config.guild(guild).winnerdm()

    async def dm_host(self, guild: discord.Guild):
        return await self.config.guild(guild).hostdm()

    async def get_guild_autodel(self, guild):
        return await self.config.guild(guild).autodelete()

    async def get_pingrole(self, guild: discord.Guild):
        role = await self.config.guild(guild).pingrole()
        if not role:
            return None

        return guild.get_role(role)

    async def get_managers(self, guild: discord.Guild):
        roles = await self.config.guild(guild).manager()
        if not roles:
            return []

        return [guild.get_role(int(role)) for role in roles]

    async def get_guild_emoji(self, guild: discord.Guild):
        return await self.config.guild(guild).emoji()

    async def get_all_roles_multi(self, guild: discord.Guild):
        roles = await self.config.all_roles()
        final = {}
        for key, value in roles.items():
            role = guild.get_role(int(key))
            if not role:
                continue

            final[role] = value["multi"]

        final = {
            d[0]: d[1]
            for d in sorted(final.items(), key=lambda x: x[1], reverse=True)
            if not d[1] == 0
        }
        return final

    async def get_role_multi(self, role: discord.Role):
        return await self.config.role(role).multi()

    async def get_list_multi(self, guild: discord.Guild, member_list: list):
        final = member_list.copy()
        multi = await self.get_all_roles_multi(guild)
        for member in member_list:
            member = guild.get_member(member.id)
            for key, value in multi.items():
                final += [member for i in range(value) if member and key in member.roles]
                await asyncio.sleep(0)

        return final

    async def set_role_multi(self, role: discord.Role, multi: int):
        await self.config.role(role).multi.set(multi)
        return f"Set the role multi for role: `@{role.name}` to {multi}"

    async def set_guild_msg(self, guild: discord.Guild, message):
        return await self.config.guild(guild).msg.set(message)

    async def set_guild_emoji(self, guild: discord.Guild, emoji):
        return await self.config.guild(guild).emoji.set(str(emoji))

    async def set_guild_tmsg(self, guild: discord.Guild, message):
        return await self.config.guild(guild).tmsg.set(message)

    async def set_guild_endmsg(self, guild: discord.Guild, message):
        return await self.config.guild(guild).endmsg.set(message)

    async def set_guild_windm(self, guild: discord.Guild, status: bool):
        return await self.config.guild(guild).winnerdm.set(status)

    async def set_guild_hostdm(self, guild: discord.Guild, status: bool):
        return await self.config.guild(guild).hostdm.set(status)

    async def set_guild_pingrole(self, guild: discord.Guild, role):
        return await self.config.guild(guild).pingrole.set(role)

    async def set_guild_autodelete(self, guild: discord.Guild, status: bool):
        return await self.config.guild(guild).autodelete.set(status)

    async def set_manager(self, guild: discord.Guild, *roles):
        return await self.config.guild(guild).manager.set(roles)

    async def set_guild_timer(self, guild: discord.Guild, b: bool):
        return await self.config.guild(guild).edit_timer.set(b)

    async def reset_role_multi(self, role: discord.Role):
        await self.config.role(role).multi.set(0)
        return f"Reset the multi for role: `@{role.name}`"

    async def blacklist_role(self, guild: discord.Guild, roles: list):
        async with self.config.guild(guild).blacklist() as bl:
            failed = []
            for role in roles:
                if not role.id in bl:
                    bl.append(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return (
            f"Blacklisted `{humanize_list([f'`@{role.name}`' for role in roles])}`` permanently from giveaways."
            + (f"{humanize_list(failed)} were already blacklisted." if failed else "")
        )

    async def unblacklist_role(self, guild: discord.Guild, roles: list):
        async with self.config.guild(guild).blacklist() as bl:
            failed = []
            for role in roles:
                if role.id in bl:
                    bl.remove(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return (
            f"UnBlacklisted {humanize_list([f'`@{role.name}`' for role in roles])} permanently from giveaways."
            + (f"{humanize_list(failed)} were never blacklisted" if failed else "")
        )

    async def unbypass_role(self, guild: discord.Guild, roles: list):
        async with self.config.guild(guild).bypass() as by:
            failed = []
            for role in roles:
                if role.id in by:
                    by.remove(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return (
            f"Removed giveaway bypass from {humanize_list([f'`@{role.name}`' for role in roles])}."
            + (f"{humanize_list(failed)} were never allowed to bypass" if failed else "")
        )

    async def bypass_role(self, guild: discord.Guild, roles: list):
        async with self.config.guild(guild).bypass() as by:
            failed = []
            for role in roles:
                if role.id not in by:
                    by.append(role.id)
                else:
                    failed.append(f"`{role.name}`")

        return (
            f"Added giveaway bypass to {humanize_list([f'`@{role.name}`' for role in roles])}."
            + (f"{humanize_list(failed)} were never allowed to bypass" if failed else "")
        )

    async def all_blacklisted_roles(self, guild: discord.Guild, id_or_object=True):
        async with self.config.guild(guild).blacklist() as bl:
            if not bl:
                return bl

            return [
                guild.get_role(_id).id if id_or_object == True else guild.get_role(_id)
                for _id in bl
            ]

    async def all_bypass_roles(self, guild: discord.Guild, id_or_object=True):
        async with self.config.guild(guild).bypass() as by:
            if not by:
                return by

            return [
                guild.get_role(_id).id if id_or_object == True else guild.get_role(_id)
                for _id in by
            ]

    async def cache_to_config(self):
        await self.config.activegaws.set([i.to_dict() for i in self.cache.copy()])
        await self.config.endedgaws.set(self.ended_cache)
        self.cache.clear()

    async def config_to_cache(self, bot, cog):
        org = await self.config.activegaws()
        self.ended_cache = await self.config.endedgaws()
        if org:
            for i in org:
                i.update(
                    {
                        "requirements": Requirements(
                            guild=bot.get_guild(i["guild"]), **i["requirements"]
                        )
                    }
                )
                i.pop("guild")
            self.cache = [Giveaway(bot=bot, cog=cog, **i) for i in org]
