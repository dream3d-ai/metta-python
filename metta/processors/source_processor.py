import asyncio
import proto_profiler
import logging

from aiokafka import AIOKafkaProducer
from typing import List, Optional, Tuple

from metta.common.config import SourceConfig
from metta.topics.topics import NewMessage
from metta.processors.base_processor import BaseProcessor


class SourceProcessor(BaseProcessor):
    def __init__(
        self,
        *,
        config: SourceConfig,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop] = None,
    ):
        self.source_name = config.SOURCE_NAME
        super().__init__(
            config=config,
            event_loop=event_loop,
        )

    async def _init_kafka_connections(self) -> None:
        client_id = self._make_client_id()
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
    ) -> List[NewMessage]:
        raise NotImplementedError

    async def _process(
        self,
    ) -> List[Tuple[NewMessage, proto_profiler.Trace]]:
        output_msgs = await self.process()
        output_traces = []

        for _ in output_msgs:
            trace = proto_profiler.init_trace()
            proto_profiler.touch_trace(trace, self.publish_topic)
            output_traces.append(trace)

        return list(zip(output_msgs, output_traces))

    async def run(
        self,
        profile: Optional[bool] = False,
    ) -> None:

        profiler = proto_profiler.ProtoTimer(disable=not profile)

        while True:
            output_msgs = await self._process()
            if output_msgs:
                for (output_msg, output_trace) in output_msgs:
                    await self._publish(
                        output_msg, source=self.source_name, trace=output_trace
                    )
                    if profile:
                        profiler.register(output_msg)