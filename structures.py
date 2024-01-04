from typing import TypedDict, NewType, Literal, Mapping, Sequence

__all__ = (
    'DiscordSnowflake',
    'DiscordEveryonePing',
    'DiscordHerePing',
    'DiscordUserPing',
    'DiscordRolePing',
    'DiscordPing',
    'PicartoCreatorConfig',
    'DiscordWebhookConfig',
    'NotifierConfig',
)

DiscordSnowflake = NewType('DiscordSnowflake', int)

DiscordEveryonePing = Literal['@everyone', 'everyone']
DiscordHerePing = Literal['@here', 'here']


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
