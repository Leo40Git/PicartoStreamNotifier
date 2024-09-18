import asyncio
import datetime
import logging
import logging.handlers
import os
import sys
from collections.abc import Callable
from logging import LogRecord
from typing import Final

import hishel
import httpx
import strictyaml

from config import *


def _logger_sysout_filter(record: logging.LogRecord) -> bool:
    return logging.INFO <= record.levelno < logging.ERROR


def _create_logger() -> logging.Logger:
    fmt = logging.Formatter('[{asctime}] [{levelname:8}] {message}',
                            datefmt='%m/%d/%Y %H:%M',
                            style='{')
    h_err = logging.StreamHandler(sys.stderr)
    h_err.setFormatter(fmt)
    h_err.setLevel(logging.ERROR)

    h_out = logging.StreamHandler(sys.stdout)
    h_out.setFormatter(fmt)
    h_out.addFilter(_logger_sysout_filter)

    h_file = logging.handlers.RotatingFileHandler('psn.log', maxBytes=2 ** 15,
                                                  backupCount=9)
    h_file.setFormatter(fmt)
    h_file.setLevel(logging.DEBUG)

    _l = logging.getLogger('psn')
    _l.setLevel(logging.DEBUG)
    _l.addHandler(h_err)
    _l.addHandler(h_file)
    return _l


logger: Final[logging.Logger] = _create_logger()

def timestamp_url(url: str) -> str:
    """
    Appends the current UTC date and time as a parameter to the URL.
    Used to avoid Discord's thumbnail image caching.
    """

    timestamp = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d%H%M')
    return f'{url}?_t={timestamp}'


# sentinel value, used for dict.get(key, default) calls to represent missing keys
_MISSING_KEY: Final[object] = object()


class Notifier:
    config_url: Final[str]
    fallback_log_webhook_url: Final[str | None]

    client: httpx.AsyncClient
    last_config_update: datetime.datetime
    config_update_interval: datetime.timedelta
    config: strictyaml.YAML

    def __init__(self, config_url: str, fallback_log_webhook_url: str | None):
        self.config_url = config_url
        self.fallback_log_webhook_url = fallback_log_webhook_url

    async def run(self):
        # initialize our client
        transport = hishel.AsyncCacheTransport(transport=httpx.AsyncHTTPTransport())
        self.client = httpx.AsyncClient(transport=transport,
                                        follow_redirects=True)

        # fetch initial configuration
        if await self._update_config(initial=True):
            logger.info('Fetched initial configuration')
        else:
            logger.critical('Failed to fetch initial configuration')
            exit(1)

        # TODO
        print(self.config.as_yaml())

        # closing up shop!
        await self.client.aclose()

    async def _update_config(self,
                       *, initial: bool = False) -> bool:
        logger.info('Fetching %s configuration from "%s"...',
                    'initial' if initial else 'latest', self.config_url)

        res: httpx.Response
        try:
            res = await self.client.get(self.config_url)
            res.raise_for_status()
        except httpx.HTTPError as exc:
            self._log_error('Failed to get configuration', exc)
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        try:
            self.config = strictyaml.load(res.text, CONFIG_SCHEMA)
        except strictyaml.YAMLError as exc:
            self._log_error('Failed to parse configuration', exc)
            self.config_update_interval = CONFIG_UPDATE_INTERVAL_ERROR
            return False

        self.config_update_interval = CONFIG_UPDATE_INTERVAL
        return True

    def _log_error(self, msg: object, exc_info: BaseException):
        logger.error(msg, exc_info=exc_info)
        # TODO log to webhook


if __name__ == '__main__':
    _config_url: str
    try:
        _config_url = os.environ[CONFIG_URL_ENV]
    except KeyError:
        logger.critical('Environment variable "%s" not set', CONFIG_URL_ENV)
        exit(1)

    _fallback_log_webhook_url: str | None
    try:
        _fallback_log_webhook_url = os.environ[FALLBACK_LOG_WEBHOOK_URL_ENV]
    except KeyError:
        logger.warning('Environment variable "%s" not set', FALLBACK_LOG_WEBHOOK_URL_ENV)
        _fallback_log_webhook_url = None

    _notifier = Notifier(_config_url, _fallback_log_webhook_url)
    asyncio.run(_notifier.run())
