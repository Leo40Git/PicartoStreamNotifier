from typing import TypedDict, Literal, Mapping, Sequence

__all__ = (
    'DiscordEveryonePing',
    'DiscordHerePing',
    'DiscordUserPing',
    'DiscordRolePing',
    'DiscordPing',
    'PicartoCreatorConfig',
    'DiscordWebhookConfig',
    'NotifierConfig',
)

DiscordEveryonePing = Literal['@everyone', 'everyone']
DiscordHerePing = Literal['@here', 'here']


class DiscordUserPing(TypedDict):
    user: str


class DiscordRolePing(TypedDict):
    role: str


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
