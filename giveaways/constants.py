import discord

giveaway_embed: discord.Embed = discord.Embed(
    title="**`{prize}`**",
    description=("React with {emoji} to enter\n" "Host: {host}\n" "Ends {timestamp}\n"),
).set_footer(text="Winners: {winners} | ends : ")

winnerdm_message: str = (
    "You have won the giveaway for `{prize}` in **__{server}__**.\n"
    "Click [here]({jump_url}) to jump to the giveaway."
)

hostdm_message: str = (
    "Your giveaway for {prize} has ended.\n"
    "The winner(s) are: {winners}\n\n"
    "Click [here]({jump_url}) to jump to the giveaway."
)

embed_title: str = "**`{prize}`**"
embed_description: str = (
    "React with {emoji} to enter\n" "Host: {host.mention}\n" "Ends {timestamp}\n"
)
embed_footer_text: str = "Winners: {winners} | ends : "
embed_footer_icon: str = "{host_avatar_url}"
embed_thumbnail: str = "{server_icon_url}"

guild_default_config = {
    "msg": ":tada:Giveaway:tada:",
    "emoji": "🎉",
    "winnerdm": True,
    "winnerdm_message": winnerdm_message,
    "hostdm": True,
    "hostdm_message": hostdm_message,
    "reactdm": True,
    "unreactdm": True,
    "endmsg": "Congratulations :tada:{winner}:tada:. You have won the giveaway for ***{prize}***.\n{link}",
    "tmsg": "Prize: {prize}\nDonor: {donor.mention}\n\nThank the donor in general chat",
    "manager": [],
    "pingrole": None,
    "autodelete": False,
    "blacklist": [],
    "bypass": [],
    "top_managers": {},
    "show_defaults": True,
    "embed_title": embed_title,
    "embed_description": embed_description,
    "embed_footer_text": embed_footer_text,
    "embed_footer_icon": embed_footer_icon,
    "embed_thumbnail": embed_thumbnail,
    "color": None,
}

commands_to_delete = ["giveaway start", "giveaway flash", "giveaway end", "giveaway reroll"]
