from metta.types.topic_pb2 import CPU_NDARRAY, DataLocation
from typing import Any, Dict, List, Optional

from pydantic import BaseSettings, AnyHttpUrl, validator


class Config(BaseSettings):
    METTA_ACCESS_TOKEN: str
    ENV: str
    BROKERS: List[str]
    ZOOKEEPER_HOSTS: List[str]

    INPUT_PROCESSOR: Optional[str] = None
    SOURCE_FILTERS: List[str] = []

    DATA_LOCATION: Optional[DataLocation] = None
    DATA_TARGETS: List[AnyHttpUrl] = []

    @validator("DATA_TARGET")
    def target_set(cls, targets, values, **kwargs):
        if (
            "DATA_LOCATION" in values
            and (values["DATA_LOCATION"] == DataLocation.CPU_NDARRAY)
            and not targets
        ):
            raise ValueError("Data targets not set")
        return targets

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = "utf-8"


class SourceConfig(Config):
    INPUT_PROCESSOR: None = None
    SOURCE_NAME: str
    DATA_LOCATION: DataLocation


class SinkConfig(Config):
    INPUT_PROCESSOR: str
