from collections.abc import Sequence
from typing import TypeAlias, TypedDict, Required, Literal, Final


CONFIG_URL_ENV: Final[str] = 'PICARTOSTREAMNOTIFIER_CONFIG_URL'


class DiscordUserPing(TypedDict):
    user: Required[int]


class DiscordRolePing(TypedDict):
    role: Required[int]


DiscordPing: TypeAlias = Literal['@everyone', '@here'] | DiscordUserPing | DiscordRolePing


class PicartoCreator(TypedDict):
    name: Required[str]
    pings: Sequence[DiscordPing]


class DiscordServer(TypedDict):
    name: Required[str]
    webhook_url: Required[str]
    creators: Sequence[PicartoCreator]


class NotifierConfig(TypedDict):
    user_agent: Required[str]
    from_email: Required[str]
    servers: Sequence[DiscordServer]
