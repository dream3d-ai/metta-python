import asyncio
import click
import ffmpeg
import numpy as np

from typing import Optional, List
from nptyping import NDArray

from metta import SourceConfig, SourceProcessor, NewMessage, time_utils


class VideoConfig(SourceConfig):
    HEIGHT: int
    WIDTH: int
    SOURCE_PATH: str
    HWACCEL: bool


class VideoSource(SourceProcessor):
    def __init__(
        self,
        *,
        config: VideoConfig,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop]
    ):
        self.height = config.HEIGHT
        self.width = config.WIDTH
        self.source_path = config.SOURCE_PATH
        self.hwaccel = config.HWACCEL

        super().__init__(config=config, event_loop=event_loop)

    async def __aenter__(self):
        self.loop = asyncio.get_running_loop()

        input_args = {}
        if self.hwaccel:
            input_args["hwaccel"] = "cuda"

        self.frame_stream = (
            ffmpeg.input(self.source_path, **input_args)
            .output("pipe:", format="rawvideo", pix_fmt="rgb24")
            .run_async(pipe_stdout=True)
        )
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        self.frame_stream.stdout.close()
        self.frame_stream.wait()
        return await super().__aexit__(exc_type, exc, tb)

    def read_next(self) -> Optional[NDArray[np.uint8]]:
        in_bytes = self.frame_stream.stdout.read(self.height * self.width * 3)
        if in_bytes:
            return np.frombuffer(in_bytes, np.uint8).reshape(
                [self.height, self.width, 3]
            )
        return None

    async def process(self) -> List[NewMessage]:
        frame = await self.loop.run_in_executor(None, self.read_next)
        if frame is not None:
            return [NewMessage(data=frame, timestamp=time_utils.time_ms())]
        return []


@click.command()
def main():
    processor = VideoSource(config=VideoConfig())
    processor.mainloop()


if __name__ == "__main__":
    main()