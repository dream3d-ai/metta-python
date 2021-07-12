import asyncio
import logging

from typing import (
    List,
    Optional,
)
from aiokafka.consumer.consumer import AIOKafkaConsumer
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

    async def __aenter__(self):
        await self._init_consumer()
        await self._init_producer()
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

        if start_ts is not None and not isinstance(self.consumer, AIOKafkaConsumer):
            raise RuntimeError(
                "Cannot start processor. start_ts cannot be used with shared memory processor"
            )
        elif start_ts is not None and isinstance(self.consumer, AIOKafkaConsumer):
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
                    profiler.register(output_msg)
                if end_ts is not None and input_msg.msg.timestamp >= end_ts:
                    break
            except Exception as e:
                logging.error(e)
                break