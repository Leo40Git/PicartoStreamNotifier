from collections.abc import Mapping, Sequence
from typing import TypedDict, Literal, NewType

DiscordSnowflake = NewType('DiscordSnowflake', int)

DiscordEveryonePing = Literal['@everyone']
DiscordHerePing = Literal['@here']


class DiscordUserPing(TypedDict):
    user: DiscordSnowflake


class DiscordRolePing(TypedDict):
    role: DiscordSnowflake


DiscordPing = DiscordEveryonePing | DiscordHerePing | DiscordUserPing | DiscordRolePing


class PicartoCreatorConfig(TypedDict):
    pings: Sequence[DiscordPing]


class DiscordWebhookConfig(TypedDict):
    url: str
    creators: Mapping[str, PicartoCreatorConfig]


class NotifierConfig(TypedDict):
    user_agent: str
    email: str
    webhooks: Mapping[str, DiscordWebhookConfig]
