import json
import pickle
import zlib
from enum import IntEnum

import zmq


def connect_address(transport: str, address: str, port: int) -> str:
    """Returns a properly formatted URL to connect to."""
    return f"{transport}://{address}:{port}"


def bind_address(transport: str, port: int) -> str:
    """Returns a properly formatted url to bind a socket to."""
    return f"{transport}://*:{port}"


def set_address_port(url: str, port: int) -> str:
    """Returns a url where the 'port' part is replaced with the given port."""
    transport, address, old_port = split_address(url)

    return f"{transport}://{address}:{port}"


def split_address(url: str) -> tuple[str, str, int]:
    transport, address, port = url.split(":")
    if address.startswith("//"):
        address = address[2:]
    return transport, address, int(port)


def send_zipped_pickle(socket, obj, flags=0, protocol=-1):
    """pickle an object, and zip the pickle before sending it"""
    p = pickle.dumps(obj, protocol)
    z = zlib.compress(p)
    return socket.send(z, flags=flags)


def recv_zipped_pickle(socket, flags=0, protocol=-1):
    """inverse of send_zipped_pickle"""
    z = socket.recv(flags)
    p = zlib.decompress(z)
    return pickle.loads(p)


def get_port_number(socket: zmq.Socket) -> int | None:
    """
    Returns the port number associated with this socket. Returns None for sockets
    that do not bind to a TCP or IPC transport.
    """
    endpoint = socket.getsockopt(zmq.LAST_ENDPOINT)
    if endpoint:
        port = endpoint.decode("utf-8").split(":")[-1]
        return int(port)
    else:
        return None


def zmq_string_request(request: str) -> list:
    return [
        b"MESSAGE_TYPE:STRING",
        request.encode("utf-8"),
    ]


def zmq_string_response(message: str) -> list:
    return [
        b"MESSAGE_TYPE:STRING",
        message.encode("utf-8"),
    ]


def zmq_json_request(request: dict) -> list:
    return [
        b"MESSAGE_TYPE:JSON",
        json.dumps(request).encode(),
    ]


def zmq_json_response(message: dict) -> list:
    return [
        b"MESSAGE_TYPE:JSON",
        json.dumps(message).encode(),
    ]


def zmq_error_response(message: dict) -> list:
    return [
        b"MESSAGE_TYPE:ERROR",
        pickle.dumps(message),
    ]


class MessageIdentifier(IntEnum):
    """
    The first item in a multipart message that can be used to subscribe, filter and identify
    messages.
    """

    # ALL shall not be used in the multipart message itself, but exists as an indicator for
    # subscribing to all messages. The ALL shall be converted into b'' when subscribing.

    ALL = 0x00

    # Synchronisation to DPU Processor at time of reception

    SYNC_TIMECODE = 0x80
    SYNC_HK_PACKET = 0x81
    SYNC_DATA_PACKET = 0x82
    SYNC_ERROR_FLAGS = 0x85
    SYNC_HK_DATA = 0x86

    N_FEE_REGISTER_MAP = 0x83
    NUM_CYCLES = 0x84

    # Sending out all kinds of information

    HDF5_FILENAMES = 0x90

    STATUS = 0x91
    CUSTOM = 0x92

    HEARTBEAT = 0x99
