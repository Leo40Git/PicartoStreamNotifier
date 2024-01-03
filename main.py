import json
import os
import traceback
from datetime import datetime
from typing import Final, Optional

import requests

from structures import *

CONFIG_URL_ENV: Final[str] = 'PICARTOSTREAMNOTIFIER_CONFIG_URL'


class PicartoCreator:
    name: Final[str]
    ping_everyone: bool
    ping_here: bool
    ping_roles: set[DiscordSnowflake]
    ping_users: set[DiscordSnowflake]

    def __init__(self, name: str, config: PicartoCreatorConfig):
        self.name = name

        self.ping_everyone = False
        self.ping_here = False
        self.ping_roles = set()
        self.ping_users = set()

        for ping in config['pings']:
            if ping == '@everyone':
                self.ping_everyone = True
            elif ping == '@here':
                self.ping_here = True
            elif isinstance(ping, dict):
                if 'role' in ping:
                    self.ping_roles.add(ping['role'])
                elif 'user' in ping:
                    self.ping_users.add(ping['user'])
                else:
                    log(f'Unknown ping specification {str(ping)}, ignoring')
            else:
                log(f'Unknown ping specification {str(ping)}, ignoring')

    def create_webhook_payload(self):
        ret = dict()

        ping_strs: list[str] = list()
        if self.ping_everyone:
            ping_strs.append('@everyone')
        if self.ping_here:
            ping_strs.append('@here')
        for sf in self.ping_roles:
            ping_strs.append(f'<@&{sf}>')
        for sf in self.ping_users:
            ping_strs.append(f'<@{sf}>')

        ret['message'] = ' '.join(ping_strs)

        ret['embeds'] = [self._create_embed()]
        ret['allowed_mentions'] = self._create_allowed_mentions()

        return ret

    def _create_embed(self):
        # TODO
        return dict()

    def _create_allowed_mentions(self):
        ret = dict()
        parse: list[str] = list()

        if self.ping_everyone or self.ping_here:
            parse.append('everyone')

        if len(self.ping_roles) > 100:
            parse.append('roles')
        elif len(self.ping_roles) > 0:
            ret['roles'] = (str(sf) for sf in self.ping_roles)

        if len(self.ping_users) > 100:
            parse.append('users')
        elif len(self.ping_users) > 0:
            ret['users'] = (str(sf) for sf in self.ping_users)

        if len(parse) > 0:
            ret['parse'] = parse

        return ret

    def __str__(self):
        return self.name


class DiscordServer:
    name: Final[str]
    webhook_url: Final[str]
    creators: dict[str, PicartoCreator]

    # key is creator name
    last_notify_timestamps: dict[str, datetime]

    def __init__(self, name: str, config: DiscordServerConfig):
        self.name = name
        self.webhook_url = config['webhook_url']
        self.creators = dict()
        self.last_notify_timestamps = dict()

        self.update_config(config)

    def update_config(self, config: DiscordServerConfig):
        new_creators: dict[str, PicartoCreator] = dict()
        for (c_name, c_config) in config['creators'].items():
            new_creators[c_name.casefold()] = PicartoCreator(c_name, c_config)

        removed_creators = set(self.creators.keys()) - set(new_creators.keys())

        self.creators.clear()
        self.creators.update(new_creators)

        for creator in removed_creators:
            self.last_notify_timestamps.pop(creator, None)

    def __str__(self):
        return self.name


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
    print(f"[{timestamp_str}] ", end=None)
    traceback.print_exception(exc)


class Notifier:
    config_url: Final[str]
    config: NotifierConfig
    last_config_update: datetime

    user_agent: str
    email: str
    servers: dict[str, DiscordServer]
    tracked_creators: set[str]

    def __init__(self, config_url: str):
        self.config_url = config_url

        self.servers = dict()
        self.tracked_creators = set()

    def run(self):
        self.update_config()

        # TODO main loop
        print(str(self.tracked_creators))

        for server in self.servers.values():
            print(server.name)
            for creator in server.creators.values():
                print(f'{creator.name} - {json.dumps(str(creator.create_webhook_payload()))}')

    def update_config(self):
        try:
            self.config = requests.get(self.config_url).json()
        except requests.exceptions.RequestException as e:
            log_exception(f'Failed to fetch latest configuration from "{self.config_url}":', e)
            exit(-1)

        self.last_config_update = datetime.now()

        self.user_agent = self.config['user_agent']
        self.email = self.config['email']

        new_servers: dict[str, tuple[str, DiscordServerConfig]] = dict()
        for (s_name, s_config) in self.config['servers'].items():
            new_servers[s_name.casefold()] = (s_name, s_config)

        removed_servers = set(self.servers.keys()) - set(new_servers.keys())

        self.tracked_creators.clear()

        for (s_name, s_config) in new_servers.items():
            if s_name in self.servers:
                self.servers[s_name].update_config(s_config[1])
            else:
                self.servers[s_name] = DiscordServer(s_config[0], s_config[1])

            for creator in self.servers[s_name].creators:
                self.tracked_creators.add(creator)

        for server in removed_servers:
            del self.servers[server]


if __name__ == '__main__':
    _config_url: str
    try:
        _config_url = os.environ[CONFIG_URL_ENV]
    except KeyError:
        print(f'Please set environment variable "{CONFIG_URL_ENV}" to the URL of the configuration file')
        exit(1)

    _notifier = Notifier(_config_url)
    _notifier.run()
