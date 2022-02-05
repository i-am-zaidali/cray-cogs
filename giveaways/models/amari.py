import typing

from aiohttp import ClientResponse, ClientSession
from cachetools import TTLCache
from redbot.core.bot import Red


class AmariException(Exception):
    """Base exception for Amari"""



class NotFoundError(AmariException):
    """
    An exception raised when the Amari API returns a 404 status code
    indicating the object requested was not found."""

    def __init__(
        self,
        response: ClientResponse.status,
        message: typing.Optional[str] = "Requested Guild/User was not found",
    ):
        super().__init__(response, message)


class RatelimitedError(AmariException):
    """
    An exception raised when the API returns a 429 status code
    indicating that the user is currently ratelimited."""

    def __init__(
        self,
        response: ClientResponse.status,
        message: typing.Optional[
            str
        ] = "You are being ratelimited by the API. Please try again later.",
    ):
        super().__init__(response, message)


class APIError(AmariException):
    """
    An exception raised when the Amari API returns a 500 status code
    indicating that theres an issue with the API due to which the request could not be completed."""

    def __init__(
        self,
        response: ClientResponse.status,
        message: typing.Optional[
            str
        ] = "The request couldn't be resolved due to an error with the Amari API. Try again later.",
    ):
        super().__init__(response, message)


class AmariClient:

    URL = "https://amaribot.com/api/v1/"

    status_codes = {404: NotFoundError, 429: RatelimitedError, 500: APIError}

    def __init__(self, bot: Red, auth_key: str) -> None:
        self.bot = bot
        self.session = ClientSession(headers={"Authorization": auth_key})
        self.cache = TTLCache(maxsize=100, ttl=5 * 60)  # a temp 5 miutes cache

    async def close(self):
        return await self.session.close()

    def _find_user(self, l: dict, user_id: int):
        user = list(filter(lambda member: member.get("id") == str(user_id), l))
        if user:
            return user[0]

    async def get_user(self, guild_id: int, user_id: int) -> dict:
        """
        Get a user from the guild.

        Parameters
        ----------
        guild_id: int
            The ID of the guild to get the user from.
        user_id: int
            The ID of the user to get.

        Returns
        -------
        dict
            The user's data.
        """
        endpoint = f"guild/{guild_id}/members"
        if data := self.cache.get(endpoint):
            members = data.get("members", {}) or {}
            user = self._find_user(members, user_id)
            if user:
                return user

        json = {"members": [str(i.id) for i in self.bot.get_guild(guild_id).members]}

        result = await self._request(self.URL + endpoint, method="POST", json=json)

        self.cache[endpoint] = result

        return self._find_user(result["members"], user_id)

    @staticmethod
    def _check_for_error(response):
        """Internal private method to check the status code to see the result is proper."""
        if response.status in AmariClient.status_codes:
            raise AmariClient.status_codes[response.status](response.status)

    async def _request(self, endpoint, *, method="GET", json=None, headers={}):
        resp = await self.session.request(method, endpoint, json=json, headers=headers)
        self._check_for_error(resp)
        return await resp.json()
