from abc import ABC, abstractmethod
from enum import StrEnum, auto
from typing import Final, Any


class StreamPlatform(StrEnum):
    PICARTO = auto()
    PICZEL = auto()


class Stream(ABC):
    platform: Final[StreamPlatform]
    handle: Final[str]

    def __init__(self,
                 platform: StreamPlatform,
                 handle: str):
        self.platform = platform
        self.handle = handle

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @abstractmethod
    async def check_live(self) -> (bool, Any):
        pass

    @abstractmethod
    def create_embed(self, data: Any) -> dict[str, Any]:
        pass
