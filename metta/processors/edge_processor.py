import asyncio
import logging
from metta.types.topic_pb2 import DataLocation

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiozmq import rpc
from typing import (
    List,
    Optional,
)

from proto_profiler import ProtoTimer
import proto_profiler

from metta.common.config import Config
from metta.topics.topics import Message, NewMessage
from metta.processors.base_processor import BaseProcessor




class EdgeProcessor(BaseProcessor):
    def __init__(
        self,
        *,
        config: Config,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop] = None,
    ):
        super().__init__(
            config=config,
            event_loop=event_loop,
        )

    async def __aenter__(self):
        await super().__aenter__(self)
        await self._init_kafka_consumer()
        await self._init_kafka_producer()
        return self

    async def process(
        self,
        input_msg: Message,
    ) -> List[NewMessage]:
        raise NotImplementedError

