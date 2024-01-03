import os
import sys
import traceback
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


def log_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime('%m/%d/%Y %H:%M')


def log(message: str, timestamp: Optional[datetime] = None):
    if timestamp is None:
        timestamp = datetime.now()
    print(f"[{log_timestamp(timestamp)}] {message}")


def log_exception(message: str, exc: Exception, timestamp: Optional[datetime] = None):
    if timestamp is None:
        timestamp = datetime.now()
    timestamp_str = log_timestamp(timestamp)
    print(f"[{timestamp_str}] {message}")
    traceback.print_exception(exc, file=sys.stdout)


def validate_config(config: NotifierConfig) -> bool:
    # TODO
    return True


class PicartoCreator:
    name: str
    ping_everyone: bool
    ping_here: bool
    ping_roles: set[DiscordSnowflake]
    ping_users: set[DiscordSnowflake]

    def __init__(self, name: str, config: PicartoCreatorConfig):
        self.ping_roles = set()
        self.ping_users = set()
        self.update_config(name, config)

    def update_config(self, name: str, config: PicartoCreatorConfig):
        self.name = name

        self.ping_everyone = False
        self.ping_here = False
        self.ping_roles.clear()
        self.ping_users.clear()

        for ping in config['pings']:
            if isinstance(ping, dict):
                if 'role' in ping:
                    self.ping_roles.add(cast(DiscordRolePing, ping)['role'])
                    continue
                elif 'user' in ping:
                    self.ping_users.add(cast(DiscordUserPing, ping)['user'])
                    continue
            elif isinstance(ping, str):
                ping = ping.casefold()
                if ping == '@everyone' or ping == 'everyone':
                    self.ping_everyone = True
                    continue
                elif ping == '@here' or ping == 'here':
                    self.ping_here = True
                    continue

            # TODO report this error better (in validate_config, maybe?)
            log(f'PicartoCreatorConfig.pings contains invalid value "{ping}", ignoring')

    def create_webhook_post_json(self, data: dict[str, Any]) -> dict[str, Any]:
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
        return ' '.join(pings)

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
            result['roles'] = [str(flake) for flake in self.ping_roles]

        if len(self.ping_users) > 100:
            # 'users' array has a maximum length of 100 items
            # past that, we must allow all user mentions
            parse.append('user')
        elif len(self.ping_users) > 0:
            result['users'] = [str(flake) for flake in self.ping_users]

        result['parse'] = parse
        return result

    def _create_embed_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        footer_parts: list[str] = list()

        if data['adult']:
            footer_parts.append('**NSFW**')

        if data['gaming']:
            footer_parts.append('Gaming')

        footer_parts.append(data['category'])
        footer_parts.append(', '.join(data['tags']))

        return {
            'title': data['title'],
            'url': f'https://picarto.tv/{self.name}',
            'color': 0x4C90F3,
            'author': {'name': self.name},
            'image': {
                # TODO add timestamp to URL
                'url': data['thumbnails']['web']
            },
            'fields': [
                # TODO prettier number formatting
                {'name': 'Followers', 'value': str(data['followers'])},
                {'name': 'Total views', 'values': str(data['views_total'])}
            ],
            'thumbnail': {
                # TODO add timestamp to URL
                'url': data['avatar']
            },
            'footer': {
                'text': ' | '.join(footer_parts)
            }
        }


class DiscordServer:
    name: str
    webhook_url: str
    creators: dict[str, PicartoCreator]

    # last time the creator went live, as reported by Picarto
    last_live: dict[str, datetime]

    # last time we pushed a notification to the webhook
    last_notified: dict[str, datetime]

    def __init__(self, name: str, config: DiscordServerConfig):
        self.creators = {}
        self.last_live = {}
        self.last_notified = {}

        self.update_config(name, config)

    def update_config(self, name: str, config: DiscordServerConfig):
        self.name = name
        self.webhook_url = config['webhook_url']

        removed_creators: set[str] = set(self.creators.keys())
        removed_creators.update(self.last_notified.keys())

        for c_name, c_config in config['creators'].items():
            key = c_name.casefold()

            if key in self.creators:
                self.creators[key].update_config(c_name, c_config)
            else:
                self.creators[key] = PicartoCreator(c_name, c_config)

            removed_creators.discard(key)

        for creator in removed_creators:
            self.creators.pop(creator, None)
            self.last_notified.pop(creator, None)

    def notify(self, online_creators: dict[str, dict[str, Any]]) -> bool:
        any_errors: bool = False

        now = datetime.now(timezone.utc)

        for c_key, c_data in online_creators.items():
            if c_key not in self.creators:
                continue

            if c_key in self.last_notified \
                    and self.last_notified[c_key] - now < NOTIFY_INTERVAL:
                continue

            creator = self.creators[c_key]
            try:
                requests.post(self.webhook_url,
                              json=creator.create_webhook_post_json(c_data),
                              timeout=10).raise_for_status()
                self.last_notified[c_key] = now
                log(f'Server "{self.name}" sent notification for creator "{creator.name}"')
            except requests.exceptions.RequestException as exc:
                log_exception(
                    f'Server "{self.name}" failed to send notification for creator "{creator.name}":',
                    exc)
                any_errors = True

        return any_errors


class Notifier:
    config_url: Final[str]
    config: NotifierConfig
    last_config_update: datetime
    config_update_interval: timedelta

    user_agent: str
    email: str
    servers: dict[str, DiscordServer]
    tracked_creators: dict[str, str]

    def __init__(self, config_url: str):
        self.config_url = config_url
        self.config_update_interval = CONFIG_UPDATE_INTERVAL

        self.servers = {}
        self.tracked_creators = {}

    def run(self):
        self.update_config()

        while True:
            try:
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
                    log_exception('Failed to fetch online creators from Picarto', exc)
                    success = False

                if success:
                    if not isinstance(response, list):
                        log(f"Unexpected API response (expected 'list', got '{repr(response)}')")
                        success = False

                if success:
                    online_creators = {}
                    for i, data in enumerate(response):
                        if not isinstance(data, dict):
                            log(f"Unexpected API response (expected 'dict' at [{i}], got '{repr(data)}')")
                            continue

                        if 'name' not in data:
                            log(f"Unexpected API response (dict at index {i} missing key 'name')")
                            continue

                        creator_name = data.pop('name')
                        if not isinstance(creator_name, str):
                            log(f"Unexpected API response (expected 'str' at [{i}].name, got '{repr(creator_name)}')")

                        online_creators[creator_name.casefold()] = data

                    for server in self.servers.values():
                        if not server.notify(online_creators):
                            success = False

                if success:
                    sleep(CHECK_INTERVAL.total_seconds())
                else:
                    sleep(CHECK_INTERVAL_ERROR.total_seconds())
            except KeyboardInterrupt:
                break

    def update_config(self) -> bool:
        new_config: NotifierConfig
        try:
            new_config = requests.get(self.config_url).json()
        except requests.exceptions.RequestException as exc:
            log_exception(f'Failed to fetch latest configuration from "{self.config_url}":', exc)
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        if not validate_config(new_config):
            log('Configuration failed validation, continuing with old configuration')
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        self.config = new_config
        self.last_config_update = datetime.now(timezone.utc)

        self.user_agent = self.config['user_agent']
        self.email = self.config['email']

        removed_servers: set[str] = set(self.servers.keys())

        for s_name, s_config in self.config['servers'].items():
            key = s_name.casefold()

            if key in self.servers:
                self.servers[key].update_config(s_name, s_config)
            else:
                self.servers[key] = DiscordServer(s_name, s_config)

            removed_servers.discard(key)

        for server in removed_servers:
            self.servers.pop(server, None)

        self.tracked_creators.clear()

        for server in self.servers.values():
            for creator_key, creator in server.creators.items():
                self.tracked_creators[creator_key] = creator.name

        log('Updated configuration!')
        log(f'Now tracking the following creators: {" ".join(self.tracked_creators.values())}')
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
