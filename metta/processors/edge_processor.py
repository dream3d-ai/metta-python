import asyncio
import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from typing import (
    List,
    Optional,
)

from proto_profiler import ProtoTimer

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

    async def _init_kafka_connections(self) -> None:
        # Init Conumser
        client_id = self._make_client_id()
        self.consumer = AIOKafkaConsumer(
            self.source_topic,
            loop=self.event_loop,
            bootstrap_servers=self.kafka_brokers,
            client_id=client_id,
        )
        await self.consumer.start()
        logging.info(f"Initialized consumer for topic {self.source_topic}")

        # Init Producer
        self.producer = AIOKafkaProducer(
            loop=self.event_loop,
            bootstrap_servers=self.kafka_brokers,
            client_id=client_id,
        )
        await self.producer.start()
        logging.info(f"Initialized producer for topic {self.publish_topic}")

    async def __aenter__(self):
        await self._init_kafka_connections()
        return await super().__aenter__(self)

    async def process(
        self,
        input_msg: Message,
    ) -> List[NewMessage]:
        raise NotImplementedError

    async def run(
        self,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        seek_to_latest: bool = False,
        profile: bool = False,
    ) -> None:
        if start_ts is not None and seek_to_latest:
            raise RuntimeError(
                "Cannot start processor. start_ts and seek_to_latest cannot be used together"
            )

        if start_ts is not None:
            partitions = self.consumer.partitions_for_topic(self.source_topic)
            offsets = self.consumer.offsets_for_times(
                {partition: start_ts for partition in partitions}
            )
            for parition, offset_and_ts in offsets.items():
                self.consumer.seek(parition, offset_and_ts.offset)

        profiler = ProtoTimer(disable=not profile)

        async for record in self.consumer():
            try:
                input_msg = await self._parse(record.value)
                output_msgs = await self._process(input_msg)
                for (output_msg, output_trace) in output_msgs:  # type: ignore
                    await self._publish(
                        output_msg, source=input_msg.msg.source, trace=output_trace
                    )
                    if profile:
                        profiler.register(output_msg)
                if end_ts is not None and input_msg.msg.timestamp >= end_ts:
                    break
            except Exception as e:
                logging.error(e)
                break