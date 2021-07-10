from typing import Any
import aiozmq
import zmq


class Record:
    value: Any


class AIOZMQConsumer:
    def __init__(self, input_host: str, topic: str) -> None:
        self.input_host = input_host
        self.topic = topic

    async def start(self):
        self.stream = await aiozmq.stream.create_zmq_stream(
            zmq_type=zmq.SUB,
            connect=self.input_host,
        )
        self.stream.transport.subscribe(self.topic)

    async def stop(self):
        self.stream.close()

    async def __aiter__(self):
        while True:
            yield Record(value=await self.stream.read())

    async def __anext__(self):
        raise StopAsyncIteration


class AIOZMQProducer:
    async def start(self):
        self.stream = await aiozmq.stream.create_zmq_stream(
            zmq_type=zmq.PUB,
            bind="tcp://127.0.0.1:*",
        )

    async def stop(self):
        self.stream.close()

    async def send(self, topic: str, value: bytes, key: str, timestamp_ms: int):
        self.stream.write(value)
