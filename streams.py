import datetime
from abc import ABC, abstractmethod
from collections.abc import Mapping
from enum import StrEnum, auto
from typing import Final, Any, NamedTuple, ClassVar

import httpx

__all__ = (
    'StreamPlatform',
    'StreamQueryContext',
    'StreamQueryResult',
    'StreamQueryError',
    'PlatformAPIError',
    'InvalidPlatformCredentials',
    'StreamNotFound',
    'Stream',
    'PicartoStream',
    'PiczelStream',
)


class StreamPlatform(StrEnum):
    PICARTO = auto()
    PICZEL = auto()


class StreamQueryContext(ABC):
    _client: Final[httpx.AsyncClient]

    def __init__(self,
                 client: httpx.AsyncClient):
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    @abstractmethod
    def get_authentication_headers(self,
                                   platform: StreamPlatform) \
            -> Mapping[str, str] | None:
        pass


class StreamQueryResult(NamedTuple):
    is_online: bool
    live_since: datetime.datetime | None
    data: Any


class StreamQueryError(Exception):
    pass


class PlatformAPIError(StreamQueryError):
    status_code: int
    data: Any
    
    def __init__(self,
                 status_code: int,
                 data: Any = None):
        self.status_code = status_code
        self.data = data
        super().__init__(f'{status_code=} {data=}')

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self!s})'


class InvalidPlatformCredentials(StreamQueryError):
    pass


class StreamNotFound(StreamQueryError):
    pass


class Stream(ABC):
    platform: Final[StreamPlatform]
    handle: Final[str]

    def __init__(self,
                 platform: StreamPlatform,
                 handle: str):
        self.platform = platform
        self.handle = handle

    @property
    def display_name(self) -> str:
        return self.handle

    @abstractmethod
    async def query(self, context: StreamQueryContext) \
            -> StreamQueryResult:
        pass

    @abstractmethod
    def create_embed(self, data: Any) -> dict[str, Any]:
        pass


class PicartoStream(Stream):
    BASE_URL: Final[ClassVar[str]] \
        = 'https://api.picarto.tv/api/v1'

    __id: str | None
    __display_name: str | None

    def __init__(self,
                 handle: str):
        super().__init__(StreamPlatform.PICARTO, handle)

    @property
    def display_name(self) -> str:
        return self.__display_name or self.handle

    async def query(self, context: StreamQueryContext) -> StreamQueryResult:
        url: str
        if self.__id is not None:
            url = f'{PicartoStream.BASE_URL}/channel/id/{self.__id}'
        else:
            url = f'{PicartoStream.BASE_URL}/channel/name/{self.handle}'

        res = await context.client.get(url, headers={'Accept': 'application/json'})
        if res.status_code == 404:
            raise StreamNotFound()
        elif res.status_code != 200:
            raise PlatformAPIError(res.status_code)

        data = res.json()
        self.__id = str(data['user_id'])
        self.__display_name = str(data['name'])
        # TODO parse last_live into datetime.datetime
        return StreamQueryResult(is_online=bool(data['online']),
                                 live_since=None,
                                 data=data)


    def create_embed(self, data: Any) -> dict[str, Any]:
        raise NotImplementedError()

class PiczelStream(Stream):
    def __init__(self,
                 handle: str):
        super().__init__(StreamPlatform.PICZEL, handle)

    async def query(self, context: StreamQueryContext) -> StreamQueryResult:
        raise NotImplementedError()

    def create_embed(self, data: Any) -> dict[str, Any]:
        raise NotImplementedError()

