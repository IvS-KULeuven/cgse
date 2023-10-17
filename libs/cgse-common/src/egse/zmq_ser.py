import pickle
import zlib
from enum import IntEnum


def connect_address(transport, address, port):
    """Returns a properly formatted URL to connect to."""
    return f"{transport}://{address}:{port}"


def bind_address(transport, port):
    """Returns a properly formatted url to bind a socket to."""
    return f"{transport}://*:{port}"


def set_address_port(url: str, port: int):
    """Returns a url where the 'port' part is replaced with the given port."""
    transport, address, old_port = split_address(url)

    return f"{transport}://{address}:{port}"


def split_address(url: str):

    transport, address, port = url.split(":")
    if address.startswith("//"):
        address = address[2:]
    return transport, address, port


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
