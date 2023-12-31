import os
import traceback
from datetime import datetime

import requests

from config_types import *

last_config_update: datetime = datetime.now()
config: NotifierConfig
config_url: str


all_creators: set[str] = set()
online_creators: set[str] = set()
notified_webhooks: dict[str, set[str]] = dict()  # webhook_url -> set[creator.name]


def update_config() -> None:
    # why do you force me to do this, Python?
    global config
    global last_config_update
    global all_creators
    global online_creators
    global notified_webhooks

    try:
        config = requests.get(config_url).json()
    except requests.exceptions.RequestException as e:
        print(f'Failed to fetch latest configuration from "{config_url}":')
        traceback.print_exception(e)
        exit(-1)

    last_config_update = datetime.now()

    new_all_creators: set[str] = set()
    for server in config['servers']:
        for creator in server['creators']:
            new_all_creators.add(creator['name'])

    removed_creators = all_creators.difference(new_all_creators)
    all_creators.intersection_update(new_all_creators)

    for creator in removed_creators:
        online_creators.remove(creator)

        for notified_set in notified_webhooks.values():
            notified_set.remove(creator)


if __name__ == '__main__':
    try:
        config_url = os.environ[CONFIG_URL_ENV]
    except KeyError:
        print(f'Please set environment variable "{CONFIG_URL_ENV}" to the URL of the configuration file')
        exit(1)

    update_config()

    # TODO main loop
