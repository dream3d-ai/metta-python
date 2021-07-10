from metta.types.topic_pb2 import CPU_NDARRAY, DataLocation
from typing import Any, Dict, List, Optional

from pydantic import BaseSettings, AnyHttpUrl, validator


class Config(BaseSettings):
    METTA_ACCESS_TOKEN: str
    ENV: str
    BROKERS: List[str]
    ZOOKEEPER_HOSTS: List[str]

    INPUT_PROCESSOR: Optional[str] = None
    INPUT_HOST: Optional[str] = None
    INPUT_DATA_LOCATION: Optional[DataLocation] = None
    SOURCE_FILTERS: List[str] = []

    DATA_LOCATION: Optional[DataLocation] = None

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


class SourceConfig(Config):
    INPUT_PROCESSOR: None = None
    SOURCE_NAME: str
    DATA_LOCATION: DataLocation


class EdgeConfig(Config):
    DATA_LOCATION: DataLocation
    INPUT_PROCESSOR: str
    INPUT_DATA_LOCATION: DataLocation


class SinkConfig(Config):
    INPUT_PROCESSOR: str
    INPUT_DATA_LOCATION: DataLocation
