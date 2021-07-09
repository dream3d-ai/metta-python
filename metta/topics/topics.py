from __future__ import annotations
from typing import (
    NamedTuple,
    Type,
    Union,
)
from nptyping import NDArray
from google.protobuf import message

from metta.types.topic_pb2 import TopicMessage


ProtobufMessage = Type[message.Message]
MessageData = Union[ProtobufMessage, NDArray]


class TopicNotRegistered(Exception):
    pass


class TopicAlreadyRegistered(Exception):
    pass


class Message(NamedTuple):
    msg: TopicMessage
    data: MessageData


class NewMessage(NamedTuple):
    timestamp: int
    data: MessageData
