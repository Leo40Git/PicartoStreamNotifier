import sys
import traceback
from collections.abc import Sequence, Mapping
from datetime import datetime, timezone, timedelta
from time import sleep
from typing import Final, Optional, cast, Any

import requests

from structures import *

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


def timestamp_url(url: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
    return f'{url}?_t={timestamp}'


# used for dict.get(key, default) calls to represent missing keys
_MISSING_KEY: Final[object] = object()


def validate_creator_config(name: str, config: PicartoCreatorConfig,
                            *, indent: str = '') -> bool:
    log(f'{indent}Validating configuration for creator "{name}":')
    success: bool = True

    pings = config.get('pings', _MISSING_KEY)
    if pings == _MISSING_KEY:
        log(f"{indent}Missing required key 'pings'")
        success = False
    elif not isinstance(pings, Sequence):
        log(f"{indent}Key 'pings' has invalid value (expected 'Sequence', got '{pings!r}')")
        success = False
    else:
        p_indent = indent + '  '
        log(f'{p_indent}Validating pings:')

        for ping in pings:
            if isinstance(ping, dict):
                flake = ping.get('role', _MISSING_KEY)
                if flake != _MISSING_KEY:
                    if not isinstance(flake, str):
                        log(f"{p_indent}Role ping has invalid snowflake value "
                            f"(expected 'istrnt', got '{flake!r}')")
                        success = False
                    continue

                flake = ping.get('user', _MISSING_KEY)
                if flake != _MISSING_KEY:
                    if not not isinstance(flake, str):
                        log(f"{p_indent}User ping has invalid snowflake value "
                            f"(expected 'str', got '{flake!r}')")
                        success = False
                    continue

            elif isinstance(ping, str):
                if ping == '@everyone' or ping == 'everyone':
                    continue
                elif ping == '@here' or ping == 'here':
                    continue

            log(f"{p_indent}Unrecognized ping '{ping!r}', will be ignored")
            # not a failure!

    return success


def validate_webhook_config(name: str, config: DiscordWebhookConfig,
                            *, indent: str = '') -> bool:
    log(f'{indent}Validating configuration for webhook "{name}":')
    success: bool = True

    url = config.get('url', _MISSING_KEY)
    if url == _MISSING_KEY:
        log(f"{indent}Missing required key 'url'")
        success = False
    elif not isinstance(url, str):
        log(f"{indent}Key 'url' has invalid value (expected 'str', got '{url!r}')")
        success = False
    
    creators = config.get('creators', _MISSING_KEY)
    if creators == _MISSING_KEY:
        log(f"{indent}Missing required key 'creators'")
        success = False
    elif not isinstance(creators, Mapping):
        log(f"{indent}Key 'creators' has invalid value (expected 'Mapping', got '{creators!r}')")
        success = False
    else:
        c_indent = indent + '  '
        for c_name, c_config in creators.items():
            if not validate_creator_config(c_name, c_config, indent=c_indent):
                success = False

    return success


def validate_config(config: NotifierConfig,
                    *, indent: str = '') -> bool:
    log(f'{indent}Validating configuration:')
    success: bool = True

    user_agent = config.get('user_agent', _MISSING_KEY)
    if user_agent == _MISSING_KEY:
        log(f"{indent}Missing required key 'user_agent'")
        success = False
    elif not isinstance(user_agent, str):
        log(f"{indent}Key 'user_agent' has invalid value (expected 'str', got '{user_agent!r}')")
        success = False

    email = config.get('email', _MISSING_KEY)
    if email == _MISSING_KEY:
        log(f"{indent}Missing required key 'email'")
        success = False
    elif not isinstance(email, str):
        log(f"{indent}Key 'email' has invalid value (expected 'str', got '{email!r}')")
        success = False

    webhooks = config.get('webhooks', _MISSING_KEY)
    if webhooks == _MISSING_KEY:
        log(f"{indent}Missing required key 'webhooks'")
        success = False
    elif not isinstance(webhooks, Mapping):
        log(f"{indent}Key 'webhooks' has invalid value (expected 'Mapping', got '{webhooks!r}')")
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
        log(f'{indent}Now pings: {", ".join(ping_list)}')

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
        embed: dict[str, Any] = {
            'title': data.get('title', f"{self.name}'s Picarto Stream"),
            'url': f'https://picarto.tv/{self.name}',
            'color': 0x4C90F3,
            'author': {'name': self.name},
        }

        fields: list[dict[str, Any]] = []

        if 'followers' in data:
            fields.append({'name': 'Followers', 'value': str(data['followers'])})

        if 'views_total' in data:
            fields.append({'name': 'Total views', 'value': str(data['views_total'])})

        if len(fields) > 0:
            embed['fields'] = fields

        if 'avatar' in data:
            embed['thumbnail'] = {'url': timestamp_url(data['avatar'])}

        tn_data = data.get('thumbnails')
        if isinstance(tn_data, dict) and 'web' in tn_data:
            embed['image'] = {'url': timestamp_url(tn_data['web'])}

        footer_parts: list[str] = []

        if data.get('adult', False):
            footer_parts.append('**NSFW**')

        if data.get('adult', False):
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
                log(f'{indent}Creator "{c_name}" updated:')
                self.creators[key].update_config(c_name, c_config, indent=c_indent)
            else:
                log(f'{indent}New creator "{c_name}" added:')
                self.creators[key] = PicartoCreator(c_name, c_config, indent=c_indent)

            removed_creators.discard(key)

        for key in removed_creators:
            creator = self.creators.pop(key, None)
            if creator is not None:
                log(f'{indent}Creator "{creator.name}" removed')

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
                log(f'Webhook "{self.name}" sent notification for creator "{creator.name}"')
            except requests.exceptions.RequestException as exc:
                log_exception(
                    f'Webhook "{self.name}" failed to send notification for creator "{creator.name}":',
                    exc)
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
        if not self.update_config():
            log('Failed to fetch initial configuration')
            exit(1)

        while True:
            try:
                log('Performing check...')

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
                    if not isinstance(response, Sequence):
                        log(f"Unexpected API response (expected 'Sequence', got '{response!r}')")
                        success = False

                if success:
                    online_creators = {}
                    for i, data in enumerate(response):
                        if not isinstance(data, Mapping):
                            log(f"Unexpected API response (expected 'Mapping' at [{i}], got '{data!r}')")
                            success = False
                            continue

                        if 'name' not in data:
                            log(f"Unexpected API response (Mapping at index {i} missing key 'name')")
                            success = False
                            continue

                        creator_name = data.get('name')
                        if not isinstance(creator_name, str):
                            log(f"Unexpected API response (expected 'str' at [{i}].name, got '{creator_name!r}')")
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
        log(f'{indent}Fetching latest configuration from "{self.config_url}"')
        new_config: NotifierConfig
        try:
            new_config = requests.get(self.config_url, timeout=10).json()
        except requests.exceptions.RequestException as exc:
            log_exception(f'{indent}Failed to fetch latest configuration from "{self.config_url}":', exc)
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        if not validate_config(new_config):
            log(f'{indent}Latest configuration is invalid, continuing with current configuration')
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        self.config = new_config
        self.last_config_update = datetime.now(timezone.utc)

        log(f'{indent}Applying latest configuration')

        self.user_agent = self.config['user_agent']
        self.email = self.config['email']

        removed_webhooks: set[str] = set(self.webhooks.keys())

        w_indent = indent + '  '
        for w_name, w_config in self.config['webhooks'].items():
            key = w_name.casefold()

            if key in self.webhooks:
                log(f'{indent}Webhook "{w_name}" updated:')
                self.webhooks[key].update_config(w_name, w_config, indent=w_indent)
            else:
                log(f'{indent}New webhook "{w_name}" added:')
                self.webhooks[key] = DiscordWebhook(w_name, w_config, indent=w_indent)

            removed_webhooks.discard(key)

        for key in removed_webhooks:
            webhook = self.webhooks.pop(key, None)
            if webhook is not None:
                log(f'{indent}Webhook "{webhook.name}" removed')

        self.tracked_creators.clear()

        for webhook in self.webhooks.values():
            for creator_key, creator in webhook.creators.items():
                self.tracked_creators[creator_key] = creator.name

        log('Latest configuration applied')

        self.config_update_interval = CONFIG_UPDATE_INTERVAL
        return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'usage: main.py <configuration URL>')
        exit(1)

    _notifier = Notifier(sys.argv[1])
    _notifier.run()
