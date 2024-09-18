import datetime
from enum import StrEnum, auto
from typing import Final

from strictyaml import Map, Str, Email, Url, MapPattern, Optional, Enum, UniqueSeq, Seq, Bool

__all__ = (
    'FALLBACK_LOG_WEBHOOK_URL_ENV',
    'CONFIG_URL_ENV',
    'StreamPlatform',
    'DEFAULT_STREAM_PLATFORM',
    'CONFIG_SCHEMA',
    'CONFIG_UPDATE_INTERVAL',
    'CONFIG_UPDATE_INTERVAL_ERROR',
    'CHECK_INTERVAL',
    'CHECK_INTERVAL_ERROR',
    'NOTIFY_INTERVAL',
)

# name of environment variable that contains the fallback Discord webhook URL
#  to log errors to, in case initial config loading fails
FALLBACK_LOG_WEBHOOK_URL_ENV: Final[str] \
    = 'PSN_FALLBACK_LOG_WEBHOOK_URL'

# name of environment variable that contains the URL to download the config from
CONFIG_URL_ENV: Final[str] \
    = 'PSN_CONFIG_URL'

# supported streaming platforms
class StreamPlatform(StrEnum):
    PICARTO = auto()
    PICZEL = auto()

# default streaming platform
DEFAULT_STREAM_PLATFORM: Final[StreamPlatform] \
    = StreamPlatform.PICARTO

def _define_config_schema() -> Map:
    platform_enum = Enum([str(x) for x in StreamPlatform])

    return Map({
        'user_agent': Str(),
        'email': Email(),
        'log_webhook': Url(),
        Optional('default_platform', default=str(DEFAULT_STREAM_PLATFORM)): platform_enum,
        Optional('platforms'): Map({
            'piczel_api_key': Optional(Str()),
        }),
        'webhooks': Seq(Map({
            'name': Str(),
            'url': Url(),
            'creators': Seq(Map({
                'name': Str(),
                Optional('platform'): platform_enum,
                Optional('ping_users'): UniqueSeq(Str()),
                Optional('ping_roles'): UniqueSeq(Str()),
                Optional('ping_everyone', default=False): Bool(),
                Optional('ping_here', default=False): Bool(),
            })),
        })),
    })

# StrictYAML schema for the config
CONFIG_SCHEMA: Final[Map] = _define_config_schema()

# interval between each config update
CONFIG_UPDATE_INTERVAL: Final[datetime.timedelta] \
    = datetime.timedelta(hours=1)

# alternate value for CONFIG_UPDATE_INTERVAL, used if the last update encountered any errors
CONFIG_UPDATE_INTERVAL_ERROR: Final[datetime.timedelta] \
    = datetime.timedelta(minutes=5)

# interval between each check (keep this above 3 minutes!)
CHECK_INTERVAL: Final[datetime.timedelta] \
    = datetime.timedelta(minutes=3)

# alternate value for CHECK_INTERVAL, used if the last check encountered any errors
CHECK_INTERVAL_ERROR: Final[datetime.timedelta] \
    = datetime.timedelta(minutes=1)

# interval between each notification being set (per creator, per webhook URL)
NOTIFY_INTERVAL: Final[datetime.timedelta] \
    = datetime.timedelta(minutes=15)
