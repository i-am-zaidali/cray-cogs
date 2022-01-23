import datetime
import logging
import time
from collections import Counter
from functools import reduce
from typing import Dict, Optional

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_list
from topgg import DBLClient, WebhookManager

from .models import VoteInfo

global log
log = logging.getLogger("red.craycogs.VoteTracker")


class VoteTracker(commands.Cog):
    """Track votes for your bot on [Top.gg](https://top.gg)"""

    __version__ = "1.5.0"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red, token: str, password: str):
        self.bot: Red = bot

        self.config: Config = Config.get_conf(None, 1, True, "VoteTracker")
        self.config.register_user(votes=0, vote_cd=None)
        self.config.register_global(role_id=None, chan=None, guild_id=None)

        self.topgg_client: DBLClient = DBLClient(
            bot,
            token,
            True,
        )
        bot.topgg_client = self.topgg_client
        self.topgg_webhook = WebhookManager(bot).dbl_webhook("/dbl", password)

        self.cache: Dict[int, Dict[str, int]] = {}

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def get_guild(self) -> Optional[discord.Guild]:
        gid = await self.config.guild_id()
        if gid:
            return self.bot.get_guild(gid)
        else:
            return None

    async def red_delete_data_for_user(self, *, requester, user_id):

        user = [x for x in self.cache if (x == user_id)][0]
        if user:
            await self.config.user_from_id(user).clear()
            log.debug("Deleted user from cache.")
            return True
        else:
            return False

    async def _populate_cache(self):
        users = await self.config.all_users()
        if users:
            self.cache = {uid: v for uid, v in users.items()}
            log.debug("Transferred config to cache.")
        else:
            self.cache = {
                k: {"votes": v, "vote_cd": None}
                for k, v in (await self.get_monthly_votes()).items()
            }
            log.debug("Populated cache.")

    async def get_monthly_votes(self):
        """
        Credits to Predä for this
        """
        data = await self.topgg_client.get_bot_votes()
        votes_count = Counter()
        for user_data in data:
            votes_count[user_data["id"]] += 1
        final = {}
        for user_id, value in votes_count.most_common():
            final[user_id] = value

        return final

    @property
    def total_votes(self):
        return reduce(
            lambda x, y: x["votes"] + y["votes"] if isinstance(x, dict) else x + y["votes"],
            self.cache.values(),
        )

    @classmethod
    async def initialize(cls, bot: Red):
        tokens = await bot.get_shared_api_tokens("topgg")
        key = tokens.get("api_key")
        password = tokens.get("pass")
        if not key or not password:
            await bot.send_to_owners(
                f"The cog `VoteTracker` requires an api token and webhook password from top.gg to function. "
                "To get these, you must visit the top.gg website, go to your profile, click on your bot's edit buttons "
                "Go to the webhooks section and click the `reveal` button to get your token. "
                "Scroll down to find the `Webhook url` field and replace it with `https://<Your-vps-ip-here>:5400/dbl`. "
                "Below that will be the password field and set that to whatever you want."
                "Then use the following command on your bot: `[p]set api topgg api_key,<api_token> pass,<password>` "
                "to add the token to the bot's shared tokens and then try reloading the cog "
                "again. If it still doesnt work, contact crayyy_zee#2900. "
                "\nHere's a little gif showing where everything is present: "
                "\nhttps://media.giphy.com/media/XB4JIFSPvC7WurI62B/giphy.gif"
            )
            return

        else:
            s = cls(bot, key, password)
            await s.topgg_webhook.run(5400)
            await s._populate_cache()
            return s

    async def _unload(self):
        await self.topgg_webhook.close()
        if self.cache:
            for k, v in self.cache.items():
                await self.config.user_from_id(k).set(v)
            log.debug("Transferred cache to config.")

    def cog_unload(self):
        self.bot.loop.create_task(self._unload())

    @staticmethod
    def sort_dict(d: dict):
        d = sorted(d.items(), key=lambda x: x[1], reverse=True)
        d = {i[0]: i[1] for i in d}
        return d

    @commands.command(name="listvotes", aliases=["lv"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lvotes(self, ctx: commands.Context):
        """
        List all votes **[botname]** has recieved in a leaderboard."""
        if not self.cache:
            return await ctx.send("No votes have been recieved so far.")
        lb = self.sort_dict({k: v["votes"] for k, v in self.cache.items()})

        embed = discord.Embed(
            title=f"All votes for {self.bot.user.name.title()}", color=await ctx.embed_colour()
        )
        for i, (k, v) in enumerate(lb.items(), 1):
            k = await self.bot.get_or_fetch_user(k)
            embed.add_field(
                name=f"{i}. {k.name}",
                value=f"Amount of votes: \n**{box(f'{v}')}**",
                inline=False,
            )

        embed.set_footer(
            text=f"Total Votes: {self.total_votes}",
            icon_url=ctx.author.avatar_url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="listmonthlyvotes", aliases=["lmv"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def lmvotes(self, ctx: commands.Context):
        """
        List this month's votes for **[botname]**"""
        lb = await self.get_monthly_votes()
        lb = self.sort_dict(lb)
        embed = discord.Embed(
            title=f"This month's top votes for {self.bot.user.name.title()}",
            color=await ctx.embed_colour(),
        )
        for i, (k, v) in enumerate(lb.items(), 1):
            k = await self.bot.get_or_fetch_user(k)
            embed.add_field(
                name=f"{i}. {k.name}",
                value=f"Amount of votes: \n**{box(f'{v}')}**",
                inline=False,
            )

        embed.set_footer(
            text=f"Total Monthly Votes: {reduce(lambda x, y: x + y, lb.values())}",
            icon_url=ctx.author.avatar_url,
        )
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command(name="setvoterole", aliases=["svr", "voterole"])
    async def svr(self, ctx: commands.Context, role: discord.Role):
        """
        Set the role to be assigned to the user upon recieving a vote from them.

        This command can only be run by bot owners."""
        await self.config.role_id.set(role.id)
        await self.config.guild_id.set(ctx.guild.id)

        await ctx.send(f"Set the role for voting to {role.name}")

    @commands.is_owner()
    @commands.command(name="setvotechannel", aliases=["svc", "votechannel"])
    async def svc(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the channel where vote logs will be sent.

        This command can only be run by bot owners."""
        await self.config.chan.set(channel.id)
        return await ctx.send(f"Set the channel for vote logging to {channel.name}")

    @commands.command(name="getuservotes", aliases=["uservotes"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def guv(self, ctx: commands.Context, user: discord.User):
        """
        Check how many times a certain user has voted for **[botname]**."""
        user_votes = self.cache.setdefault(user.id, {"votes": 0, "vote_cd": None}).get("votes")
        if user_votes == 0:
            return await ctx.send(f"{user.name} has not voted yet.")

        return await ctx.send(
            f"{user.name} has voted for **{self.bot.user.name}** *{user_votes}* time{'s' if user_votes > 1 else ''}."
        )

    @commands.Cog.listener()
    async def on_dbl_vote(self, data: dict):
        vote = VoteInfo(self.bot, data)

        user = vote.user
        user_mention = user.mention
        user_id = user.id

        g = await self.get_guild()

        if vote.type.name == "test":
            log.info(f"Test vote recieved from: {user_mention} (`{user_id}`)")
            return

        u_data = self.cache.setdefault(user_id, {"votes": 0, "vote_cd": None})
        u_data.update({"votes": u_data["votes"] + 1})
        if (r := await self.config.role_id()) and g:
            if mem := g.get_member(user_id):
                role = g.get_role(r)
                if role:
                    await mem.add_roles(g.get_role(role))

        role_recieved = (
            f"\n{user_mention} has recieved the role: <@&{r}>"
            if (r := await self.config.role_id())
            else ""
        )
        embed = discord.Embed(
            title="Vote recieved on Top.gg!",
            description=f"{user_mention} (`{user_id}`) has voted for **{self.bot.user}**"
            f"\nTheir total votes are: {self.cache.get(user_id)}" + role_recieved,
            color=0x303036,
        )
        embed.set_footer(text=f"Total Votes: {self.total_votes}")
        embed.timestamp = datetime.datetime.now()

        u_data["vote_cd"] = int(time.time() + (3600 * 12))

        self.cache[user_id] = u_data  # just to make sure data is actually updated in cache

        if chanid := await self.config.chan():
            await self.bot.get_channel(chanid).send(embed=embed)

        log.info(f"Vote recieved from: {user_mention} (`{user_id}`)")

    @tasks.loop(minutes=10)
    async def remove_role_from_members(self):
        if not (g := await self.get_guild()):
            return

        await g.chunk()

        if not (r := await self.config.role_id()):
            return

        if not self.cache:
            return

        if not (role := g.get_role(r)):
            return

        for k, v in self.cache.items():
            if not (mem := g.get_member(k)):
                continue
            if not role in mem.roles:
                continue
            if not v["vote_cd"]:
                continue
            if v["vote_cd"] > time.time():
                continue
            if not g.me.guild_permissions.manage_roles:
                continue
            if not g.me.top_role.position > mem.top_role.position:
                continue
            mem: discord.Member
            await mem.remove_roles(role, reason="Automatic voter role removal after timeout.")
            self.cache[k]["vote_cd"] = None
