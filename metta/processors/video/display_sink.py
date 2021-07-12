import asyncio
import cv2
import click

from typing import List, Optional

from metta import SinkProcessor, Message, SinkConfig


class DisplayConfig(SinkConfig):
    FPS: Optional[int] = None


class DisplaySink(SinkProcessor):
    def __init__(
        self,
        *,
        config: DisplayConfig,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop] = None,
    ):
        super().__init__(
            config=config,
            event_loop=event_loop,
        )
        self.display_ns = int(1000 / config.FPS) if config.FPS is not None else 1
        self.windows: List[str] = []
    
    def create_window(self, name: str):
        cv2.namedWindow(name)
        self.windows.append(name)

    async def __aenter__(self):
        for source in self.source_filters:
          self.create_window(source)
            
        return await super().__aenter__()

    async def __aexit__(self, exc_type, exc, tb):
        cv2.destroyAllWindows()
        return await super().__aexit__(exc_type, exc, tb)

    async def process(self, input_msg: Message):
        if input_msg.msg.source not in self.windows:
            self.create_window(input_msg.msg.source)
        cv2.imshow(input_msg.msg.source, input_msg.data)
        cv2.waitKey(self.display_ns)

@click.command()
def main():
  display = DisplaySink(config=DisplayConfig())
  display.mainloop()

if __name__ == "__main__":
    main()