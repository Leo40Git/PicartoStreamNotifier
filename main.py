import logging
import logging.handlers
import os
import sys
from collections.abc import Sequence, Mapping
from datetime import datetime, timezone, timedelta
from time import sleep
from typing import Final, Optional, cast, Any

import requests

from structures import *

# name of environment variable that contains the URL to download the config from
CONFIG_URL_ENV: Final[str] = 'PICARTOSTREAMNOTIFIER_CONFIG_URL'

# interval between each config update
CONFIG_UPDATE_INTERVAL: Final[timedelta] = timedelta(hours=1)

# alternate value for CONFIG_UPDATE_INTERVAL, used if the last update encountered any errors
CONFIG_UPDATE_INTERVAL_ERROR: Final[timedelta] = timedelta(minutes=5)

# interval between each check (keep this above 3 minutes!)
CHECK_INTERVAL: Final[timedelta] = timedelta(minutes=3)

# alternate value for CHECK_INTERVAL, used if the last check encountered any errors
CHECK_INTERVAL_ERROR: Final[timedelta] = timedelta(minutes=1)

# interval between each notification being set (per creator, per webhook URL)
NOTIFY_INTERVAL: Final[timedelta] = timedelta(minutes=30)


def _create_logger() -> logging.Logger:
    fmt = logging.Formatter('[{asctime}] [{levelname:8}] {message}',
                            datefmt='%m/%d/%Y %H:%M',
                            style='{')
    h_err = logging.StreamHandler(sys.stderr)
    h_err.setFormatter(fmt)
    h_err.setLevel(logging.INFO)

    h_file = logging.handlers.RotatingFileHandler('picartonotif.log', maxBytes=2 ** 15,
                                                  backupCount=9)
    h_file.setFormatter(fmt)
    h_file.setLevel(logging.DEBUG)

    _l = logging.getLogger('picartonotif')
    _l.setLevel(logging.DEBUG)
    _l.addHandler(h_err)
    _l.addHandler(h_file)
    return _l


logger: Final[logging.Logger] = _create_logger()


def timestamp_url(url: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
    return f'{url}?_t={timestamp}'


# used for dict.get(key, default) calls to represent missing keys
_MISSING_KEY: Final[object] = object()


def validate_creator_config(name: str, config: PicartoCreatorConfig,
                            *, indent: str = '') -> bool:
    logger.info('%sValidating configuration for creator "%s":', indent, name)
    success: bool = True

    pings = config.get('pings', _MISSING_KEY)
    if pings == _MISSING_KEY:
        logger.error("%sMissing required key 'pings'", indent)
        success = False
    elif not isinstance(pings, Sequence):
        logger.error("%sKey 'pings' has invalid value (expected 'Sequence', got '%s')",
                     indent, repr(pings))
        success = False
    else:
        p_indent = indent + '  '
        logger.info("%sValidating pings:", p_indent)

        for ping in pings:
            if isinstance(ping, dict):
                flake = ping.get('role', _MISSING_KEY)
                if flake != _MISSING_KEY:
                    if not isinstance(flake, str):
                        logger.error("%sRole ping has invalid snowflake value "
                                     "(expected 'istrnt', got '%s')", p_indent, repr(flake))
                        success = False
                    continue

                flake = ping.get('user', _MISSING_KEY)
                if flake != _MISSING_KEY:
                    if not not isinstance(flake, str):
                        logger.error("%sUser ping has invalid snowflake value "
                                     "(expected 'istrnt', got '%s')", p_indent, repr(flake))
                        success = False
                    continue

            elif isinstance(ping, str):
                if ping == '@everyone' or ping == 'everyone':
                    continue
                elif ping == '@here' or ping == 'here':
                    continue

            logger.warning("%sUnrecognized ping '%s', will be ignored",
                           p_indent, repr(ping))
            # not a failure!

    return success


def validate_webhook_config(name: str, config: DiscordWebhookConfig,
                            *, indent: str = '') -> bool:
    logger.info('%sValidating configuration for webhook "%s":', indent, name)
    success: bool = True

    url = config.get('url', _MISSING_KEY)
    if url == _MISSING_KEY:
        logger.error("%sMissing required key 'url'", indent)
        success = False
    elif not isinstance(url, str):
        logger.error("%sKey 'url' has invalid value (expected 'str', got '%s')",
                     indent, repr(url))
        success = False
    
    creators = config.get('creators', _MISSING_KEY)
    if creators == _MISSING_KEY:
        logger.error("%sMissing required key 'creators'", indent)
        success = False
    elif not isinstance(creators, Mapping):
        logger.error("%sKey 'creators' has invalid value (expected 'Mapping', got '%s')",
                     indent, repr(creators))
        success = False
    else:
        c_indent = indent + '  '
        for c_name, c_config in creators.items():
            if not validate_creator_config(c_name, c_config, indent=c_indent):
                success = False

    return success


def validate_config(config: NotifierConfig,
                    *, indent: str = '') -> bool:
    logger.info('%sValidating configuration:', indent)
    success: bool = True

    user_agent = config.get('user_agent', _MISSING_KEY)
    if user_agent == _MISSING_KEY:
        logger.error("%sMissing required key 'user_agent'", indent)
        success = False
    elif not isinstance(user_agent, str):
        logger.error("%sKey 'user_agent' has invalid value (expected 'str', got '%s')",
                     indent, repr(user_agent))
        success = False

    email = config.get('email', _MISSING_KEY)
    if email == _MISSING_KEY:
        logger.error("%sMissing required key 'email'", indent)
        success = False
    elif not isinstance(email, str):
        logger.error("%sKey 'email' has invalid value (expected 'str', got '%s')",
                     indent, repr(email))
        success = False

    webhooks = config.get('webhooks', _MISSING_KEY)
    if webhooks == _MISSING_KEY:
        logger.error("%sMissing required key 'webhooks'", indent)
        success = False
    elif not isinstance(webhooks, Mapping):
        logger.error("%sKey 'webhooks' has invalid value (expected 'Mapping', got '%s')",
                     indent, repr(webhooks))
        success = False
    else:
        w_indent = indent + '  '
        for w_name, w_config in webhooks.items():
            if not validate_webhook_config(w_name, w_config, indent=w_indent):
                success = False

    return success


class PicartoCreator:
    __name: str                   # as defined by configuration
    __actual_name: Optional[str]  # as defined by Picarto
    ping_everyone: bool
    ping_here: bool
    ping_roles: set[str]
    ping_users: set[str]

    def __init__(self, name: str, config: PicartoCreatorConfig,
                 *, indent: str = ''):
        self.__name = name
        self.__actual_name = None
        self.ping_everyone = False
        self.ping_here = False
        self.ping_roles = set()
        self.ping_users = set()
        self.update_config(name, config, indent=indent)

    @property
    def name(self) -> str:
        return self.__actual_name or self.__name

    @name.setter
    def name(self, name: str):
        if name.casefold() != self.__name.casefold():
            self.__name = name
            self.__actual_name = None

    def update_config(self, name: str, config: PicartoCreatorConfig,
                      *, indent: str = ''):
        self.name = name

        self.ping_everyone = False
        self.ping_here = False
        self.ping_roles.clear()
        self.ping_users.clear()

        for ping in config['pings']:
            if isinstance(ping, dict):
                if 'role' in ping:
                    self.ping_roles.add(cast(DiscordRolePing, ping)['role'])
                elif 'user' in ping:
                    self.ping_users.add(cast(DiscordUserPing, ping)['user'])
            elif isinstance(ping, str):
                if ping == '@everyone' or ping == 'everyone':
                    self.ping_everyone = True
                elif ping == '@here' or ping == 'here':
                    self.ping_here = True

        ping_list: list[str] = []
        if self.ping_everyone:
            ping_list.append('@everyone')
        if self.ping_here:
            ping_list.append('@here')
        ping_list.append(f'{len(self.ping_roles)} role(s)')
        ping_list.append(f'{len(self.ping_users)} user(s)')

        logger.debug('%sNow pings: %s', indent, ', '.join(ping_list))

    def create_webhook_post_json(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        if 'name' in data:
            # update proper casing of name from Picarto
            self.__actual_name = data['name']

        return {
            'content': self._create_message_content(),
            'embeds': [self._create_embed_dict(data)],
            'allowed_mentions': self._create_allowed_mentions_dict(),
        }

    def _create_message_content(self) -> str:
        pings: list[str] = []

        if self.ping_everyone:
            pings.append('@everyone')

        if self.ping_here:
            pings.append('@here')

        pings.extend([f'<@&{flake}>' for flake in self.ping_roles])
        pings.extend([f'<@{flake}>' for flake in self.ping_users])
        return f"{' '.join(pings)} **{self.name}** is now live!"

    def _create_allowed_mentions_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        parse: list[str] = []

        if self.ping_everyone or self.ping_here:
            parse.append('everyone')

        if len(self.ping_roles) > 100:
            # 'roles' array has a maximum length of 100 items
            # past that, we must allow all role mentions
            parse.append('roles')
        elif len(self.ping_roles) > 0:
            result['roles'] = [flake for flake in self.ping_roles]

        if len(self.ping_users) > 100:
            # 'users' array has a maximum length of 100 items
            # past that, we must allow all user mentions
            parse.append('user')
        elif len(self.ping_users) > 0:
            result['users'] = [flake for flake in self.ping_users]

        result['parse'] = parse
        return result

    def _create_embed_dict(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        image_url: Optional[str] = None
        thumbnails = data.get('thumbnails')
        if isinstance(thumbnails, dict):
            if 'web_large' in thumbnails:
                image_url = thumbnails['web_large']
            elif 'web' in thumbnails:
                image_url = thumbnails['web']

        embed: dict[str, Any] = {
            'title': data.get('title', '(unnamed stream)'),
            'description': f"Join {data.get('viewers', 0)} other viewers in **{self.name}**'s stream!",
            'url': f'https://picarto.tv/{self.name}',
            'color': 0x4C90F3,
        }

        if 'avatar' in data:
            embed['thumbnail'] = {'url': timestamp_url(data['avatar'])}

        if image_url is not None:
            embed['image'] = {'url': timestamp_url(image_url)}

        footer_parts: list[str] = []

        if data.get('adult', False):
            footer_parts.append('Mature Content (NSFW)')

        if data.get('gaming', False):
            footer_parts.append('Gaming')

        if 'category' in data:
            footer_parts.append(data['category'])

        if len(footer_parts) > 0:
            embed['footer'] = {'text': ' | '.join(footer_parts)}

        return embed


class DiscordWebhook:
    name: str
    url: str
    creators: dict[str, PicartoCreator]

    # last time we pushed a notification for a creator to the webhook
    last_notified: dict[str, datetime]

    def __init__(self, name: str, config: DiscordWebhookConfig,
                 *, indent: str = ''):
        self.name = name
        self.url = ''
        self.creators = {}
        self.last_notified = {}
        self.update_config(name, config, indent=indent)

    def update_config(self, name: str, config: DiscordWebhookConfig,
                      *, indent: str = ''):
        self.name = name
        self.url = config['url']

        removed_creators: set[str] = set(self.creators.keys())
        removed_creators.update(self.last_notified.keys())

        c_indent = indent + '  '
        for c_name, c_config in config['creators'].items():
            key = c_name.casefold()

            if key in self.creators:
                logger.debug('%sCreator "%s" updated:', indent, c_name)
                self.creators[key].update_config(c_name, c_config, indent=c_indent)
            else:
                logger.debug('%sNew creator "%s" added:', indent, c_name)
                self.creators[key] = PicartoCreator(c_name, c_config, indent=c_indent)

            removed_creators.discard(key)

        for key in removed_creators:
            creator = self.creators.pop(key, None)
            if creator is not None:
                logger.debug('%sCreator "%s" removed', indent, creator.name)
                pass

            self.last_notified.pop(key, None)

    def notify(self, online_creators: Mapping[str, Mapping[str, Any]]) -> bool:
        success: bool = True

        now = datetime.now(timezone.utc)

        for c_key, c_data in online_creators.items():
            if c_key not in self.creators:
                continue

            if c_key in self.last_notified \
                    and self.last_notified[c_key] - now < NOTIFY_INTERVAL:
                continue

            creator = self.creators[c_key]
            try:
                requests.post(self.url,
                              json=creator.create_webhook_post_json(c_data),
                              timeout=10).raise_for_status()
                self.last_notified[c_key] = now
                logger.debug('Webhook "%s" sent notification for creator "%s"',
                             self.name, creator.name)
            except requests.exceptions.RequestException as exc:
                logger.error('Webhook "%s" failed to send notification for creator "%s"',
                             self.name, creator.name,
                             exc_info=exc)
                success = False

        return success


class Notifier:
    config_url: Final[str]
    config: NotifierConfig
    last_config_update: datetime
    config_update_interval: timedelta

    user_agent: str
    email: str
    webhooks: dict[str, DiscordWebhook]
    tracked_creators: dict[str, str]

    def __init__(self, config_url: str):
        self.config_url = config_url
        self.config_update_interval = CONFIG_UPDATE_INTERVAL
        self.webhooks = {}
        self.tracked_creators = {}

    def run(self):
        if self.update_config():
            logger.info('Fetched initial configuration')
        else:
            logger.critical('Failed to fetch initial configuration, exiting')
            exit(-1)

        while True:
            try:
                logger.debug('Checking for online creators')

                success = True

                now = datetime.now(timezone.utc)
                if self.last_config_update - now >= self.config_update_interval:
                    self.update_config()

                response: list[dict[str, Any]] = []
                try:
                    response = requests.get(
                        'https://api.picarto.tv/api/v1/online?adult=true&gaming=true',
                        headers={
                            'User-Agent': self.user_agent,
                            'From': self.email
                        },
                        timeout=10).json()
                except requests.exceptions.RequestException as exc:
                    logger.error('Failed to fetch online creators from Picarto',
                                 exc_info=exc)
                    success = False

                if success:
                    if not isinstance(response, Sequence):
                        logger.error("Unexpected API response (expected 'Sequence', got '%s')",
                                     repr(response))
                        success = False

                if success:
                    online_creators = {}
                    for i, data in enumerate(response):
                        if not isinstance(data, Mapping):
                            logger.error("Unexpected API response (expected 'str' at [%s].name, got '%s')",
                                         i, repr(data))
                            success = False
                            continue

                        if 'name' not in data:
                            logger.error("Unexpected API response (Mapping at index %s missing key 'name')",
                                         i)
                            success = False
                            continue

                        creator_name = data.get('name')
                        if not isinstance(creator_name, str):
                            logger.error("Unexpected API response (expected 'str' at [%s].name, got '%s')",
                                         i, repr(creator_name))
                            success = False
                            continue

                        online_creators[creator_name.casefold()] = data

                    for webhook in self.webhooks.values():
                        if not webhook.notify(online_creators):
                            success = False

                if success:
                    sleep(CHECK_INTERVAL.total_seconds())
                else:
                    sleep(CHECK_INTERVAL_ERROR.total_seconds())
            except KeyboardInterrupt:
                break

    def update_config(self,
                      *, indent: str = '') -> bool:
        logger.info('%sFetching latest configuration from "%s"', indent, self.config_url)

        new_config: NotifierConfig
        try:
            new_config = requests.get(self.config_url, timeout=10).json()
        except requests.exceptions.RequestException as exc:
            logger.error('%sFailed to fetch latest configuration:', indent,
                         exc_info=exc)
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        if not validate_config(new_config):
            logger.error('%sLatest configuration is invalid, continuing with current configuration', indent)
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        self.config = new_config
        self.last_config_update = datetime.now(timezone.utc)

        logger.info('%sApplying latest configuration', indent)

        self.user_agent = self.config['user_agent']
        self.email = self.config['email']

        removed_webhooks: set[str] = set(self.webhooks.keys())

        w_indent = indent + '  '
        for w_name, w_config in self.config['webhooks'].items():
            key = w_name.casefold()

            if key in self.webhooks:
                logger.debug('%sWebhook "%s" updated:', indent, w_name)
                self.webhooks[key].update_config(w_name, w_config, indent=w_indent)
            else:
                logger.debug('%sNew webhook "%s" added:', indent, w_name)
                self.webhooks[key] = DiscordWebhook(w_name, w_config, indent=w_indent)

            removed_webhooks.discard(key)

        for key in removed_webhooks:
            webhook = self.webhooks.pop(key, None)
            if webhook is not None:
                logger.debug('%sWebhook "%s" removed', indent, webhook.name)

        self.tracked_creators.clear()

        for webhook in self.webhooks.values():
            for creator_key, creator in webhook.creators.items():
                self.tracked_creators[creator_key] = creator.name

        logger.info('%sLatest configuration applied', indent)

        self.config_update_interval = CONFIG_UPDATE_INTERVAL
        return True


if __name__ == '__main__':
    _config_url: str
    try:
        _config_url = os.environ[CONFIG_URL_ENV]
    except KeyError:
        print(f'Please set environment variable "{CONFIG_URL_ENV}" to the URL of the configuration file')
        exit(1)

    _notifier = Notifier(_config_url)
    _notifier.run()
