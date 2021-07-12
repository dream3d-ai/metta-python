from typing import Any, AsyncIterable
import aiozmq
import zmq


class Record:
    def __init__(self, value: str):
        self.value = value


class ConsumerStoppedError(Exception):
    pass


class AIOZMQConsumer:
    def __init__(self, input_host: str, topic: str) -> None:
        self.input_host = input_host
        self.topic = topic
        self._closed = True

    __call__ = lambda x: x.__aiter__()

    async def start(self):
        self._closed = False
        self.stream = await aiozmq.stream.create_zmq_stream(
            zmq_type=zmq.SUB,
            connect=self.input_host,
        )
        self.stream.transport.subscribe(self.topic)

    async def stop(self):
        self.stream.close()
        self._closed = True

    async def __aiter__(self):
        if self._closed:
            raise ConsumerStoppedError
        return self

    async def __anext__(self) -> Record:
        while True:
            try:
                return Record(value=await self.stream.read())
            except ConsumerStoppedError:
                raise StopAsyncIteration  # noqa: F821

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.stop()


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
