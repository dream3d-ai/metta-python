import asyncio
import click
import urllib
import wave
import numpy as np

from typing import Optional, List
from nptyping import NDArray
from pydantic import BaseSettings

from metta import SourceConfig, SourceProcessor, NewMessage, time_utils


class Authorization(BaseSettings):
    TYPE: str = "Bearer"
    VALUE: str


class UrlAudioConfig(SourceConfig):
    FRAME_SIZE: int
    SOURCE_PATH: str
    AUTH: Optional[Authorization] = None


class UrlAudioSource(SourceProcessor):
    def __init__(
        self,
        *,
        config: UrlAudioConfig,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop],
    ):
        self.source_path = config.SOURCE_PATH
        self.frame_size = config.FRAME_SIZE
        self.auth = config.AUTH

        super().__init__(config=config, event_loop=event_loop)

    async def __aenter__(self):
        self.loop = asyncio.get_running_loop()

        request = urllib.request.Request(self.source_path)
        if self.auth:
            request.add_header(
                "Authorization", f"{self.auth.TYPE} {self.auth.value}".bytes()
            )
        in_file = urllib.request.urlopen(request)

        self.in_wave = wave.open(in_file, "rb")
        self.in_params = self.in_wave.getparams()
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        self.in_wave.close()
        return await super().__aexit__(exc_type, exc, tb)

    def read_next(self) -> Optional[NDArray[np.int16]]:
        in_bytes = self.in_wave.readframes(self.frame_size)
        if in_bytes:
            return np.fromstring(in_bytes, "Int16")
        return None

    async def process(self) -> List[NewMessage]:
        frame = await self.loop.run_in_executor(None, self.read_next)
        if frame is not None:
            return [NewMessage(data=frame, timestamp=time_utils.time_ms())]
        return []


@click.command()
def main():
    processor = UrlAudioSource(config=UrlAudioConfig())
    processor.mainloop()


if __name__ == "__main__":
    main()