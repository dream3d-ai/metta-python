import pickle

from types import TracebackType
from typing import (
    Dict,
    Optional,
    Type,
    List,
)

from aiozk import ZKClient
from contextlib import AsyncExitStack
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from google.protobuf import message

from metta.topics.topics import (
    ProtobufMessage,
    TopicAlreadyRegistered,
)


class TopicRegistry(AsyncExitStack):
    def __init__(self, *, kafka_brokers: List[str], zookeeper_hosts: List[str]):
        self.kafka_client = KafkaAdminClient(bootstrap_servers=kafka_brokers)
        self.zk_client = ZKClient(",".join(zookeeper_hosts))

        self.topics: Dict[str, ProtobufMessage] = dict()

    async def __aenter__(self):
        await self.zk_client.start()
        await self.zk_client.ensure_path("/metta/topics")
        return self

    async def __aexit__(
        self,
        __exc_type: Optional[Type[BaseException]],
        __exc_value: Optional[BaseException],
        __traceback: Optional[TracebackType],
    ) -> bool:
        await self.zk_client.close()
        return await super().__aexit__(__exc_type, __exc_value, __traceback)

    def __getattribute__(self, name: str) -> ProtobufMessage:
        return self.topics[name]

    async def _create(self, topic: str, type: ProtobufMessage) -> None:
        await self.zk_client.create(
            f"/metta/topics/{topic}", type.DESCRIPTOR.file.serialized_pb
        )
        await self.zk_client.ensure_path(f"/metta/topics/{topic}")
        await self.zk_client.create(f"/metta/topics/{topic}/python", pickle.dumps(type))
        self.topics[topic] = type

    async def _update(
        self, topic: str, type: ProtobufMessage, overwrite: bool = False
    ) -> None:
        curr_topic_type = (
            await self.zk_client.get_data(f"/metta/topics/{topic}")
        ).decode()

        if type.DESCRIPTOR.file.serialized_pb != curr_topic_type and not overwrite:
            raise TopicAlreadyRegistered(
                f"Conflicting types. Topic already registered with type {curr_topic_type}"
            )

        await self.zk_client.set_data(
            f"/metta/topics/{topic.name}", type.DESCRIPTOR.file.serialized_pb
        )
        await self.zk_client.set_data(
            f"/metta/topics/{topic.name}/python", pickle.dumps(topic)
        )
        self.topics[topic] = type

    async def register(
        self,
        topic: str,
        type: ProtobufMessage,
        overwrite: bool = False,
    ):
        zk_node = f"/metta/topics/{topic.name}"

        if await self.zk_client.exists(zk_node):
            await self._update(topic, type, overwrite)
        else:
            await self._create(topic, type)
            try:
                topic = NewTopic(name=topic, num_partitions=1, replication_factor=1)
                self.kafka_client.create_topics(new_topics=[topic])
            except TopicAlreadyExistsError:
                pass

    async def sync(self):
        topics = await self.zk_client.get_children("/metta/topics")
        for topic_name in topics:
            topic = pickle.loads(
                await self.zk_client.get_data(f"/metta/topics/{topic_name}/python")
            )
            self.topics[topic_name] = topic