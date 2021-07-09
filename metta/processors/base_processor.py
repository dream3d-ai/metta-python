from abc import abstractmethod
import asyncio
import random
import logging
import re
import sys
import signal
import proto_profiler
import uvloop

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiozmq import rpc
from enum import Enum
from typing import (
    Callable,
    List,
    Optional,
    Tuple,
    Union,
)
from contextlib import AsyncExitStack
from functools import partial

from metta.common import shared_memory
from metta.common.config import Config
from metta.topics.topics import Message, NewMessage
from metta.topics.topic_registry import TopicRegistry
from metta.types.topic_pb2 import DataLocation, TopicMessage


class TransportType(Enum):
    KAFKA = 0
    ZMQ = 1


class BaseHandler(rpc.AttrHandler):
    def __init__(
        self,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        profile: bool = False,
    ):
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.profiler = proto_profiler.ProtoTimer(disable=not profile)

    @abstractmethod
    async def consume_msg(self, input_value):
        pass


class BaseProcessor(AsyncExitStack):
    def __init__(
        self,
        *,
        config: Config,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop] = None,
    ):
        self.identifer = random.randint(0, 100)
        self.env = config.ENV
        self.source_topic = config.INPUT_PROCESSOR
        self.data_location = config.DATA_LOCATION

        self.kafka_brokers = config.BROKERS
        self.zk_hosts = config.ZOOKEEPER_HOSTS
        self.event_loop = event_loop

        self.transport: TransportType
        self.handler: BaseHandler
        self.consumer: Union[AIOKafkaConsumer, rpc.PubSubClient]
        self.producer: Union[AIOKafkaProducer, rpc.PubSubService]

    @property
    def publish_topic(self):
        return (
            f"{re.sub(r'(?<!^)(?=[A-Z])', '_', self.__class__.name).lower()}-{self.env}"
        )

    @property
    def client_id(self) -> str:
        return f"{self.source_topic}->{self.publish_topic}-{self.identifer}"

    async def _init_shared_memory(self) -> None:
        self.shm_client = shared_memory.SharedMemoryClient()
        logging.info(f"Initialized shared memory client")

    async def _init_topic_registry(self):
        self.topic_registry = TopicRegistry(
            kafka_brokers=self.kafka_brokers, zookeeper_hosts=self.zk_hosts
        )
        async with self.topic_registry as registry:
            await registry.sync()
        logging.info(f"Initialized & synchronized topic registry")

    async def _init_consumer(self) -> None:
        # TODO: lookup data location
        self.consumer = AIOKafkaConsumer(
            self.source_topic,
            loop=self.event_loop,
            bootstrap_servers=self.kafka_brokers,
            client_id=self.client_id,
        )
        await self.consumer.start()
        logging.info(f"Initialized consumer for topic {self.source_topic}")

    async def _init_kafka_producer(self) -> None:
        self.producer = AIOKafkaProducer(
            loop=self.event_loop,
            bootstrap_servers=self.kafka_brokers,
            client_id=self.client_id,
        )
        await self.producer.start()
        logging.info(f"Initialized producer for topic {self.publish_topic}")

    def _handle_interrupt(self, *args):
        logging.info(f"Interrupted. Exiting.")
        sys.exit()

    async def __aenter__(self):
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

        if self.event_loop is None:
            self.event_loop = asyncio.get_event_loop()
        await self._init_shared_memory()
        await self._init_topic_registry()
        return self

    async def __aexit__(self, __exc_type, __exc_value, __traceback):
        if isinstance(self.consumer, AIOKafkaConsumer):
            await self.consumer.stop()
        else:
            await self.consumer.close()

        if isinstance(self.producer, AIOKafkaProducer):
            await self.producer.stop()
        else:
            await self.producer.close()

    async def _parse(self, msg: str) -> Message:
        topic_msg = TopicMessage.FromString(msg)
        topic = self.topic_registry[topic_msg.topic]

        data = None
        if topic.data_location == DataLocation.MESSAGE:
            data = topic.type.FromString(topic.data)
        elif topic.data_location == DataLocation.CPU_NDARRAY:
            plasma_object_id = shared_memory.object_id_from_bytes(topic_msg.data)
            data = self.shm_client.read(plasma_object_id)
        else:
            raise NotImplementedError

        return Message(msg=topic_msg, data=data)

    async def process(
        self,
        input_msg: Message,
    ) -> Optional[List[NewMessage]]:
        raise NotImplementedError

    async def _process(
        self,
        input_msg: Message,
    ) -> Optional[List[Tuple[NewMessage, proto_profiler.Trace]]]:
        output_msgs = await self.process(input_msg)
        if not output_msgs:
            return None

        output_traces = []
        for _ in output_msgs:
            trace = input_msg.msg.trace
            if trace is None:
                trace = proto_profiler.init_trace()
            proto_profiler.touch_trace(trace, self.publish_topic)
            output_traces.append(trace)

        return list(zip(output_msgs, output_traces))

    async def _publish(self, msg: NewMessage, source: str, trace: proto_profiler.Trace):
        topic_msg = TopicMessage(
            topic_name=self.publish_topic.name,
            source=source,
            timestamp=msg.timestamp,
        )
        if self.publish_topic.data_location == DataLocation.MESSAGE:
            topic_msg.data = msg.data.SerializeToString()
        elif self.publish_topic.data_location == DataLocation.CPU_NDARRAY:
            plasma_obj_id = self.shm_client.write(msg.data, compress=True)
            topic_msg.data = shared_memory.object_id_to_bytes(plasma_obj_id)
        else:
            raise NotImplementedError

        await self.producer.send(
            self.publish_topic.name,
            value=topic_msg.SerializeToString(),
            key=source,
            timestamp_ms=msg.timestamp,
        )

    async def run(
        self,
    ) -> None:
        if isinstance(self.consumer, AIOKafkaConsumer):
            async for record in self.consumer():
                try:
                    self.handler.consume_msg(record.value)
                except Exception as e:
                    logging.error(e)
                    break

    def register(self, forward_fn: Callable[[List[Message]], Optional[NewMessage]]):
        def _fn(self, fn, inputs):
            return fn(inputs)

        self.process = partial(_fn, self, forward_fn)  # type: ignore

    def mainloop(
        self,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        seek_to_latest: bool = False,
        profile: Optional[bool] = False,
    ):
        async def _run():
            async with self as node:
                await node.run(start_ts, end_ts, seek_to_latest, profile)

        uvloop.install()
        asyncio.run(_run())


class SourceHandler(rpc.AttrHandler):
    def __init__(
        self,
        processor: BaseProcessor,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        profile: bool = False,
    ):
        self.processor = processor
        self.start_ts = start_ts
        self.end_ts = end_ts

    @rpc.method
    async def consume_msg(self, input_value):
        output_msgs = await self._process()
        if output_msgs:
            for (output_msg, output_trace) in output_msgs:
                await self._publish(
                    output_msg, source=self.source_name, trace=output_trace
                )
                self.profiler.register(output_msg)


class EdgeHandler(BaseHandler):
    def __init__(
        self,
        processor: BaseProcessor,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        profile: bool = False,
    ):
        self.processor = processor
        super().__init__(start_ts, end_ts, profile)

    @rpc.method
    async def consume_msg(self, input_value):
        input_msg = await self.processor._parse(input_value)
        output_msgs = await self.processor._process(input_msg)
        for (output_msg, output_trace) in output_msgs:  # type: ignore
            if self.processor.data_location == DataLocation.MESSAGE:
                await self.processor._publish(
                    output_msg, source=input_msg.msg.source, trace=output_trace
                )
            else:
                # put it into the output topic
                pass
            self.profiler.register(output_msg)


class SinkHandler(BaseHandler):
    def __init__(
        self,
        processor: BaseProcessor,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        profile: bool = False,
    ):
        self.processor = processor
        super().__init__(start_ts, end_ts, profile)

    @rpc.method
    async def consume_msg(self, input_value):
        try:
            input_msg = await self.processor._parse(input_value)
            output_msgs = await self.processor._process(input_msg)
            for (output_msg, output_trace) in output_msgs:  # type: ignore
                if self.processor.data_location == DataLocation.MESSAGE:
                    await self.processor._publish(
                        output_msg, source=input_msg.msg.source, trace=output_trace
                    )
                else:
                    pass
                if self.profile:
                    proto_profiler.register(output_msg)
            if self.end_ts is not None and input_msg.msg.timestamp >= self.end_ts:
                exit(0)
        except Exception as e:
            logging.error(e)