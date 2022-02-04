import discord

giveaway_embed: discord.Embed = discord.Embed(
            title="**`{prize}`**",
            description=(
                "React with {emoji} to enter\n"
                "Host: {host}\n"
                "Ends {timestamp}\n"
            ),
        ).set_footer(text="Winners: {winners} | ends : ")

guild_default_config = {
    "msg": ":tada:Giveaway:tada:",
    "emoji": "🎉",
    "winnerdm": True,
    "hostdm": True,
    "endmsg": "Congratulations :tada:{winner}:tada:. You have won the giveaway for ***{prize}***.\n{link}",
    "tmsg": "Prize: {prize}\nDonor: {donor.mention}\n\nThank the donor in general chat",
    "manager": [],
    "pingrole": None,
    "autodelete": False,
    "blacklist": [],
    "bypass": [],
    "top_managers": {},
    "color": None,
    "show_defaults": True,
}