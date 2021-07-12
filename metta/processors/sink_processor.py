import asyncio
import logging

from typing import Optional
from aiokafka.consumer.consumer import AIOKafkaConsumer

from metta.common.config import SinkConfig
from metta.topics.topics import Message, NewMessage
from metta.processors.base_processor import BaseProcessor


class SinkProcessor(BaseProcessor):
    def __init__(
        self,
        *,
        config: SinkConfig,
        event_loop: Optional[asyncio.unix_events._UnixSelectorEventLoop] = None,
    ):
        self.source_filters = config.SOURCE_FILTERS
        super().__init__(
            config=config,
            event_loop=event_loop,
        )

    async def __aenter__(self):
        await self._init_consumer()
        return await super().__aenter__(self)

    async def process(self, input_msg: Message) -> None:
        raise NotImplementedError

    async def run(
        self,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        seek_to_latest: bool = False,
        profile: Optional[bool] = False,
    ) -> None:
        assert (
            self.consumer is not None
        ), "Cannot consume messages. Consumer not initialized"

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

        async for record in self.consumer():
            try:
                input_msg = await self._parse(record.value)
                if input_msg.msg.source in self.source_filters:
                    await self._process(input_msg)
                if end_ts is not None and input_msg.msg.timestamp >= end_ts:
                    break
            except Exception as e:
                logging.error(e)
                break
