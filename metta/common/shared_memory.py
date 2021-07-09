import blosc
import base64

import numpy as np
import pyarrow as pa
import pyarrow.plasma as plasma

from typing import List
from threading import local

from metta.types.plasma_pb2 import PlasmaObjectID


class PlasmaReadError(Exception):
    pass


class BloscReadError(Exception):
    pass


def make_plasma_conn(socket: str = "/tmp/plasma"):
    context = local()
    context.plasma_conn = plasma.connect(socket)
    return context


def write_to_plasma(context, data: np.ndarray, **kwargs) -> PlasmaObjectID:
    object_id = write(context.plasma_conn, data, **kwargs)
    return PlasmaObjectID(data=object_id.binary())


def read_from_plasma(context, frame_id: PlasmaObjectID, **kwargs) -> np.ndarray:
    _id = object_id_from_bytes(frame_id.data)
    frame = read(context.plasma_conn, _id, **kwargs)
    return frame


def delete_from_plasma(context, *frame_ids: List[PlasmaObjectID]) -> None:
    _ids = []
    for frame_id in frame_ids:
        _ids.append(object_id_from_bytes(frame_id.data))
    context.plasma_conn.delete(_ids)


def write(client: plasma.PlasmaClient, x: np.ndarray, compress=True) -> plasma.ObjectID:
    if compress:
        return write_blosc(client, x)
    object_id = plasma.ObjectID(np.random.bytes(20))
    tensor = pa.Tensor.from_numpy(x)
    data_size = pa.get_tensor_size(tensor)
    buf = client.create(object_id, data_size)
    stream = pa.FixedSizeBufferWriter(buf)
    stream.set_memcopy_threads(5)
    pa.write_tensor(tensor, stream)
    client.seal(object_id)
    return object_id


def read(
    client: plasma.PlasmaClient, object_id: plasma.ObjectID, compress=True
) -> np.ndarray:
    if compress:
        return read_blosc(client, object_id)
    [buf] = client.get_buffers([object_id], timeout_ms=100)
    if buf is None:
        raise PlasmaReadError
    reader = pa.BufferReader(buf)
    return pa.read_tensor(reader).to_numpy()


def write_blosc(client: plasma.PlasmaClient, x: np.ndarray):
    object_id = plasma.ObjectID(np.random.bytes(20))
    buf = blosc.pack_array(x)
    client.create_and_seal(object_id, buf)
    return object_id


def read_blosc(client: plasma.PlasmaClient, object_id: plasma.ObjectID):
    [buf] = client.get_buffers([object_id], timeout_ms=100)
    if buf is None:
        raise PlasmaReadError
    try:
        res = blosc.unpack_array(buf.to_pybytes())
    except blosc.blosc_extension.error:
        raise BloscReadError
    return res


def object_id_from_bytes(x: bytes) -> plasma.ObjectID:
    return plasma.ObjectID(x)


def object_id_to_pbuf(object_id: plasma.ObjectID) -> PlasmaObjectID:
    return PlasmaObjectID(data=object_id_to_bytes(object_id))


def object_id_from_pbuf(msg: PlasmaObjectID) -> plasma.ObjectID:
    return object_id_from_bytes(msg.data)


def object_id_to_bytes(object_id: plasma.ObjectID) -> bytes:
    return object_id.binary()


def serialize_object_id(object_id: plasma.ObjectID) -> str:
    object_id_serial = base64.b64encode(object_id_to_bytes(object_id))
    return object_id_serial.decode("utf-8")


def deserialize_object_id(object_id_serial: str):
    object_id_binary = base64.b64decode(object_id_serial.encode())
    return object_id_from_bytes(object_id_binary)


class SharedMemoryClient:
    def __init__(self, socket: str = "/tmp/plasma"):
        self.context = make_plasma_conn(socket=socket)
        np.random.seed()

    def write(self, x: np.ndarray, compress=True) -> plasma.ObjectID:
        return write(self.context.plasma_conn, x, compress)

    def read(self, object_id: plasma.ObjectID, compress=True) -> np.ndarray:
        return read(self.context.plasma_conn, object_id, compress)
