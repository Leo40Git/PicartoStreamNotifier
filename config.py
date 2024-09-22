from datetime import timedelta
from typing import Final

from strictyaml import Map, Str, Url, Optional, Enum, UniqueSeq, Seq, Bool

from streams import StreamPlatform

__all__ = (
    'USER_AGENT_ENV',
    'EMAIL_ENV',
    'LOG_WEBHOOK_URL_ENV',
    'CONFIG_URL_ENV',
    'DEFAULT_STREAM_PLATFORM',
    'CONFIG_SCHEMA',
    'CONFIG_UPDATE_INTERVAL',
    'CONFIG_UPDATE_INTERVAL_ERROR',
    'CHECK_INTERVAL',
    'CHECK_INTERVAL_ERROR',
    'NOTIFY_INTERVAL',
)

# prefix for environment variable names
ENV_PREFIX: Final[str] = 'STREAMNOTIF_'

# name of environment variable that contains the user agent to specify
#  in the 'User-Agent' header of HTTP requests made by the script
USER_AGENT_ENV: Final[str] = ENV_PREFIX + 'USER_AGENT'

# name of environment variable that contains the E-mail to specify
#  in the 'From' header of HTTP request made by the script
EMAIL_ENV: Final[str] = ENV_PREFIX + 'EMAIL'

# name of environment variable that contains a Discord webhook URL to log errors to
LOG_WEBHOOK_URL_ENV: Final[str] = ENV_PREFIX + 'LOG_WEBHOOK_URL'

# name of environment variable that contains the URL to download the config from
CONFIG_URL_ENV: Final[str] = ENV_PREFIX + 'CONFIG_URL'

# default streaming platform
DEFAULT_STREAM_PLATFORM: Final[StreamPlatform] \
    = StreamPlatform.PICARTO

def _define_config_schema() -> Map:
    platform_enum = Enum([str(x) for x in StreamPlatform])

    return Map({
        Optional('default_platform', default=str(DEFAULT_STREAM_PLATFORM)): platform_enum,
        Optional('platforms'): Map({
            Optional('piczel_api_key'): Str(),
        }),
        'webhooks': Seq(Map({
            'name': Str(),
            'url': Url(),
            'streams': Seq(Map({
                Optional('platform'): platform_enum,
                'handle': Str(),
                Optional('ping_users'): UniqueSeq(Str()),
                Optional('ping_roles'): UniqueSeq(Str()),
                Optional('ping_everyone', default=False): Bool(),
                Optional('ping_here', default=False): Bool()
            }))
        }))
    })

# StrictYAML schema for the config
CONFIG_SCHEMA: Final[Map] = _define_config_schema()

# interval between each config update
CONFIG_UPDATE_INTERVAL: Final[timedelta] = timedelta(hours=1)

# alternate value for CONFIG_UPDATE_INTERVAL, used if the last update encountered any errors
CONFIG_UPDATE_INTERVAL_ERROR: Final[timedelta] = timedelta(minutes=5)

# interval between each check (keep this above 3 minutes!)
CHECK_INTERVAL: Final[timedelta] = timedelta(minutes=3)

# alternate value for CHECK_INTERVAL, used if the last check encountered any errors
CHECK_INTERVAL_ERROR: Final[timedelta] = timedelta(minutes=1)

# interval between each notification being set (per creator, per webhook URL)
NOTIFY_INTERVAL: Final[timedelta] = timedelta(minutes=15)
