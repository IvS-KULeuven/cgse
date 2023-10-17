"""
This module defines classes and functions to work with SpaceWire packets.
"""
import logging
import os
import struct
from enum import IntEnum
from typing import Tuple
from typing import Union

import numpy as np

from egse.bits import clear_bit
from egse.bits import crc_calc
from egse.bits import set_bit
from egse.exceptions import Error
from egse.setup import SetupError
from egse.state import GlobalState

MODULE_LOGGER = logging.getLogger(__name__)

try:
    _ = os.environ["PLATO_CAMERA_IS_EM"]
    TWOS_COMPLEMENT_OFFSET = 32768 if _.capitalize() in ("1", "True", "Yes") else 0
except KeyError:
    TWOS_COMPLEMENT_OFFSET = 0

# RMAP Error Codes and Constants -------------------------------------------------------------------

RMAP_PROTOCOL_ID = 0x01
RMAP_TARGET_LOGICAL_ADDRESS_DEFAULT = 0xFE
RMAP_TARGET_KEY = 0xD1

# Error and Status Codes

RMAP_SUCCESS = 0
RMAP_GENERAL_ERROR = 1
RMAP_UNUSED_PACKET_TYPE_COMMAND_CODE = 2
RMAP_INVALID_KEY = 3
RMAP_INVALID_DATA_CRC = 4
RMAP_EARLY_EOP = 5
RMAP_TOO_MUCH_DATA = 6
RMAP_EEP = 7
RMAP_RESERVED = 8
RMAP_VERIFY_BUFFER_OVERRUN = 9
RMAP_NOT_IMPLEMENTED_AUTHORISED = 10
RMAP_RMW_DATA_LENGTH_ERROR = 11
RMAP_INVALID_TARGET_LOGICAL_ADDRESS = 12

# Memory Map layout --------------------------------------------------------------------------------

# NOTE: These memory areas are currently equal for N-FEE and F-FEE. Don't know if this will
#       change in the future.

CRITICAL_AREA_START = 0x0000_0000
CRITICAL_AREA_END = 0x0000_00FC
GENERAL_AREA_START = 0x0000_0100
GENERAL_AREA_END = 0x0000_06FC
HK_AREA_START = 0x0000_0700
HK_AREA_END = 0x0000_07FC
WINDOWING_AREA_START = 0x0080_0000
WINDOWING_AREA_END = 0x00FF_FFFC


class RMAPError(Error):
    """An RMAP specific Error."""
    pass


class CheckError(RMAPError):
    """
    Raised when a check fails and you want to pass a status values along with the message.
    """

    def __init__(self, message, status):
        self.message = message
        self.status = status


def update_transaction_identifier(tid: int) -> int:
    """
    Updates the transaction identifier and returns the new value.

    FIXME: document more about this identifier, where is it used, when is it checked,
           when does it need to be incremented, who initializes the identifier and
           who updates it, ...

    Args:
        tid (int): The current transaction identifier

    Returns:
        the updated transaction identifier (int).
    """
    tid = (tid + 1) & 0xFFFF
    return tid


def create_rmap_read_request_packet(address: int, length: int, tid: int, strict: bool = True) -> bytes:
    """
    Creates an RMAP Read Request SpaceWire packet.

    The read request is an RMAP command that read a number of bytes from the FEE register memory.

    The function returns a ``ctypes`` character array (which is basically a bytes array) that
    can be passed into the EtherSpaceLink library function ``esl_write_packet()``.

    Address shall be within the 0x0000_0000 and 0x00FF_FFFC. The memory map (register) is divided
    in the following areas:

        0x0000_0000 - 0x0000_00FC   Critical Configuration Area (verified write)
        0x0000_0100 - 0x0000_06FC   General Configuration Area (unverified write)
        0x0000_0700 - 0x0000_07FC   Housekeeping area
        0x0000_0800 - 0x007F_FFFC   Not Supported
        0x0080_0000 - 0x00FF_FFFC   Windowing Area (unverified write)
        0x0010_0000 - 0xFFFF_FFFC   Not Supported

    All read requests to the critical area shall have a fixed data length of 4 bytes.
    All read requests to a general area shall have a maximum data length of 256 bytes.
    All read requests to the housekeeping area shall have a maximum data length of 256 bytes.
    All read requests to the windowing area shall have a maximum data length of 4096 bytes.

    The transaction identifier shall be incremented for each read request. This shall be done by
    the calling function!

    Args:
        address (int): the FEE register memory address
        length (int): the data length
        tid (int): transaction identifier
        strict (bool): perform strict checking of address and length

    Returns:
        a bytes object containing the full RMAP Read Request packet.
    """

    check_address_and_data_length(address, length, strict=strict)

    buf = bytearray(16)

    # NOTE: The first bytes would each carry the target SpW address or a destination port,
    #       but this is not used for point-to-point connections, so we're safe.

    buf[0] = 0x51  # Target N-FEE or F-FEE
    buf[1] = 0x01  # RMAP Protocol ID
    buf[2] = 0x4C  # Instruction: 0b1001100, RMAP Request, Read, Incrementing address, reply address
    buf[3] = 0xD1  # Destination Key
    buf[4] = 0x50  # Initiator is always the DPU
    buf[5] = (tid >> 8) & 0xFF  # MSB of the Transition ID
    buf[6] = tid & 0xFF  # LSB of the Transition ID
    buf[7] = 0x00  # Extended address is not used
    buf[8] = (address >> 24) & 0xFF  # address (MSB)
    buf[9] = (address >> 16) & 0xFF  # address
    buf[10] = (address >> 8) & 0xFF  # address
    buf[11] = address & 0xFF  # address (LSB)
    buf[12] = (length >> 16) & 0xFF  # data length (MSB)
    buf[13] = (length >> 8) & 0xFF  # data length
    buf[14] = length & 0xFF  # data length (LSB)
    buf[15] = rmap_crc_check(buf, 0, 15) & 0xFF
    return bytes(buf)


def create_rmap_read_request_reply_packet(
        instruction_field: int, tid: int, status: int, buffer: bytes, buffer_length: int) -> bytes:
    """
    Creates an RMAP Reply to a RMAP Read Request packet.

    The function returns a ``ctypes`` character array (which is basically a bytes array) that
    can be passed into the EtherSpaceLink library function ``esl_write_packet()``.

    Args:
        instruction_field (int): the instruction field of the RMAP read request packet
        tid (int): the transaction identifier of the read request packet
        status (int): the status field, 0 on success
        buffer (bytes): the data that was read as indicated by the read request
        buffer_length (int): the data length

    Returns:
        packet: a bytes object containing the full RMAP Reply packet.
    """

    buf = bytearray(12 + buffer_length + 1)

    buf[0] = 0x50  # Initiator address N-DPU or F-DPU
    buf[1] = 0x01  # RMAP Protocol ID
    buf[2] = instruction_field & 0x3F  # Clear the command bit as this is a reply
    buf[3] = status & 0xFF  # Status field: 0 on success
    buf[4] = 0x51  # Target address is always the N-FEE or F-FEE
    buf[5] = (tid >> 8) & 0xFF  # MSB of the Transition ID
    buf[6] = tid & 0xFF  # LSB of the Transition ID
    buf[7] = 0x00  # Reserved
    buf[8] = (buffer_length >> 16) & 0xFF  # data length (MSB)
    buf[9] = (buffer_length >> 8) & 0xFF  # data length
    buf[10] = buffer_length & 0xFF  # data length (LSB)
    buf[11] = rmap_crc_check(buf, 0, 11) & 0xFF  # Header CRC

    # Note that we assume here that len(buffer) == buffer_length.

    if len(buffer) != buffer_length:
        MODULE_LOGGER.warning(
            f"While creating an RMAP read reply packet, the length of the buffer ({len(buffer)}) "
            f"not equals the buffer_length ({buffer_length})"
        )

    for idx, value in enumerate(buffer):
        buf[12 + idx] = value

    buf[12 + buffer_length] = rmap_crc_check(buffer, 0, buffer_length) & 0xFF  # data CRC

    return bytes(buf)


def create_rmap_verified_write_packet(address: int, data: bytes, tid: int) -> bytes:
    """
    Create an RMAP packet for a verified write request on the FEE. The length of the data is
    by convention always 4 bytes and therefore not passed as an argument.

    Args:
        address: the start memory address on the FEE register map
        data: the data to be written in the register map at address [4 bytes]
        tid (int): transaction identifier

    Returns:
        packet: a bytes object containing the SpaceWire packet.
    """

    if len(data) < 4:
        raise ValueError(
            f"The data argument should be at least 4 bytes, but it is only {len(data)} bytes: {data=}.")

    if address > CRITICAL_AREA_END:
        raise ValueError("The address range for critical configuration is [0x00 - 0xFC].")

    tid = update_transaction_identifier(tid)

    # Buffer length is fixed at 24 bytes since the data length is fixed
    # at 4 bytes (32 bit addressing)

    buf = bytearray(21)

    # The values below are taken from the PLATO N-FEE to N-DPU
    # Interface Requirements Document [PLATO-DLR-PL-ICD-0010]

    buf[0] = 0x51  # Logical Address
    buf[1] = 0x01  # Protocol ID
    buf[2] = 0x7C  # Instruction
    buf[3] = 0xD1  # Key
    buf[4] = 0x50  # Initiator Address
    buf[5] = (tid >> 8) & 0xFF  # MSB of the Transition ID
    buf[6] = tid & 0xFF  # LSB of the Transition ID
    buf[7] = 0x00  # Extended address
    buf[8] = (address >> 24) & 0xFF  # address (MSB)
    buf[9] = (address >> 16) & 0xFF  # address
    buf[10] = (address >> 8) & 0xFF  # address
    buf[11] = address & 0xFF  # address (LSB)
    buf[12] = 0x00  # data length (MSB)
    buf[13] = 0x00  # data length
    buf[14] = 0x04  # data length (LSB)
    buf[15] = rmap_crc_check(buf, 0, 15) & 0xFF  # header CRC
    buf[16] = data[0]
    buf[17] = data[1]
    buf[18] = data[2]
    buf[19] = data[3]
    buf[20] = rmap_crc_check(buf, 16, 4) & 0xFF  # data CRC

    return bytes(buf)


def create_rmap_unverified_write_packet(address: int, data: bytes, length: int, tid: int) -> bytes:
    """
    Create an RMAP packet for a unverified write request on the FEE.

    Args:
        address: the start memory address on the FEE register map
        data: the data to be written in the register map at address
        length: the length of the data
        tid (int): transaction identifier

    Returns:
        packet: a bytes object containing the SpaceWire packet.
    """

    # We can only handle data for which the length >= the given length argument.

    if len(data) < length:
        raise ValueError(
            f"The length of the data argument ({len(data)}) is smaller than "
            f"the given length argument ({length})."
        )

    if len(data) > length:
        MODULE_LOGGER.warning(
            f"The length of the data argument ({len(data)}) is larger than "
            f"the given length argument ({length}). The data will be truncated "
            f"when copied into the packet."
        )

    if address <= CRITICAL_AREA_END:
        raise ValueError(
            f"The given address (0x{address:08X}) is in the range for critical configuration is "
            f"[0x00 - 0xFC]. Use the verified write function for this."
        )

    tid = update_transaction_identifier(tid)

    # Buffer length is fixed at 24 bytes since the data length
    # is fixed at 4 bytes (32 bit addressing)

    buf = bytearray(16 + length + 1)
    offset = 0

    buf[offset + 0] = 0x51  # Logical Address
    buf[offset + 1] = 0x01  # Protocol ID
    buf[offset + 2] = 0x6C  # Instruction
    buf[offset + 3] = 0xD1  # Key
    buf[offset + 4] = 0x50  # Initiator Address
    buf[offset + 5] = (tid >> 8) & 0xFF  # MSB of the Transition ID
    buf[offset + 6] = tid & 0xFF  # LSB of the Transition ID
    buf[offset + 7] = 0x00  # Extended address
    buf[offset + 8] = (address >> 24) & 0xFF  # address (MSB)
    buf[offset + 9] = (address >> 16) & 0xFF  # address
    buf[offset + 10] = (address >> 8) & 0xFF  # address
    buf[offset + 11] = address & 0xFF  # address (LSB)
    buf[offset + 12] = (length >> 16) & 0xFF  # data length (MSB)
    buf[offset + 13] = (length >> 8) & 0xFF  # data length
    buf[offset + 14] = length & 0xFF  # data length (LSB)
    buf[offset + 15] = rmap_crc_check(buf, 0, 15) & 0xFF  # header CRC

    offset += 16

    for idx, value in enumerate(data):
        buf[offset + idx] = value

    buf[offset + length] = rmap_crc_check(buf, offset, length) & 0xFF  # data CRC

    return bytes(buf)


def create_rmap_write_request_reply_packet(instruction_field: int, tid: int, status: int) -> bytes:
    buf = bytearray(8)

    buf[0] = 0x50  # Initiator address N-DPU or F-DPU
    buf[1] = 0x01  # RMAP Protocol ID
    buf[2] = instruction_field & 0x3F  # Clear the command bit as this is a reply
    buf[3] = status & 0xFF  # Status field: 0 on success
    buf[4] = 0x51  # Target address is always the N-FEE or F-FEE
    buf[5] = (tid >> 8) & 0xFF  # MSB of the Transition ID
    buf[6] = tid & 0xFF  # LSB of the Transition ID
    buf[7] = rmap_crc_check(buf, 0, 7) & 0xFF  # Header CRC

    return bytes(buf)


def check_address_and_data_length(address: int, length: int, strict: bool = True) -> None:
    """
    Checks the address and length in the range of memory areas used by the FEE.

    The ranges are taken from the PLATO-DLR-PL-ICD-0010 N-FEE to N-DPU IRD.

    Args:
        address (int): the memory address of the FEE Register
        length (int): the number of bytes requested
        strict (bool): strictly apply the rules

    Raises:
        RMAPError: when address + length fall outside any specified area.
    """

    if not strict:
        # All these restrictions have been relaxed on the N-FEE.
        # We are returning here immediately instead of removing or commenting out the code.
        # These reason is that we can then bring back restriction easier and gradually.

        MODULE_LOGGER.warning(
            "Address and data length checks have been disabled, because the N-FEE "
            "does not enforce restrictions in the critical memory area.")
        return

    if length % 4:
        raise RMAPError(
            "The requested data length shall be a multiple of 4 bytes.", address, length
        )

    if address % 4:
        raise RMAPError("The address shall be a multiple of 4 bytes.", address, length)

    # Note that when checking the given data length, at the defined area end,
    # we can still read 4 bytes.

    if CRITICAL_AREA_START <= address <= CRITICAL_AREA_END:
        if length != 4:
            raise RMAPError(
                "Read requests to the critical area have a fixed data length of 4 bytes.",
                address, length
            )
    elif GENERAL_AREA_START <= address <= GENERAL_AREA_END:
        if length > 256:
            raise RMAPError(
                "Read requests to the general area have a maximum data length of 256 bytes.",
                address, length
            )
        if address + length > GENERAL_AREA_END + 4:
            raise RMAPError(
                "The requested data length for the general area is too large. "
                "The address + length exceeds the general area boundaries.",
                address, length
            )

    elif HK_AREA_START <= address <= HK_AREA_END:
        if length > 256:
            raise RMAPError(
                "Read requests to the housekeeping area have a maximum data length of 256 bytes.",
                address, length
            )
        if address + length > HK_AREA_END + 4:
            raise RMAPError(
                "The requested data length for the housekeeping area is too large. "
                "The address + length exceeds the housekeeping area boundaries.",
                address, length
            )

    elif WINDOWING_AREA_START <= address <= WINDOWING_AREA_END:
        if length > 4096:
            raise RMAPError(
                "Read requests to the windowing area have a maximum data length of 4096 bytes.",
                address, length
            )
        if address + length > WINDOWING_AREA_END + 4:
            raise RMAPError(
                "The requested data length for the windowing area is too large. "
                "The address + length exceeds the windowing area boundaries.", address, length
            )

    else:
        raise RMAPError("Register address for RMAP read requests is invalid.", address, length)


class PacketType(IntEnum):
    """Enumeration type that defines the SpaceWire packet type."""

    DATA_PACKET = 0
    OVERSCAN_DATA = 1
    HOUSEKEEPING_DATA = 2  # N-FEE
    DEB_HOUSEKEEPING_DATA = 2  # F-FEE
    AEB_HOUSEKEEPING_DATA = 3  # F-FEE


class DataPacketType:
    """
    Defines the Data Packet Field: Type, which is a bit-field of 16 bits.

    Properties:
      * value: returns the data type as an integer
      * packet_type: the type of data packet, defined in PacketType enum.
      * mode: the FEE mode, defined in n_fee_mode and f_fee_mode enum
      * last_packet: flag which defines the last packet of a type in the current readout cycle
      * ccd_side: 0 for E-side (left), 1 for F-side (right), see egse.fee.fee_side
      * ccd_number: CCD number [0, 3]
      * frame_number: the frame number after sync
    """

    def __init__(self, data_type: int = 0):
        self._data_type: int = data_type
        # self.n_fee_side = GlobalState.setup.camera.fee.ccd_sides.enum

    @property
    def value(self) -> int:
        """Returns the data packet type as an int."""
        return self._data_type

    @property
    def packet_type(self):
        """Returns the packet type: 0 = data packet, 1 = overscan data, 2 = housekeeping packet."""
        return self._data_type & 0b0011

    @packet_type.setter
    def packet_type(self, value):
        if not 0 <= value < 3:
            raise ValueError(f"Packet Type can only have the value 0, 1, or 2, {value=} given.")
        x = self._data_type
        for idx, bit in enumerate([0, 1]):
            x = set_bit(x, bit) if value & (1 << idx) else clear_bit(x, bit)
        self._data_type = x

    @property
    def mode(self) -> int:
        return (self._data_type & 0b1111_0000_0000) >> 8

    @mode.setter
    def mode(self, value: int):
        x = self._data_type
        for idx, bit in enumerate([8, 9, 10, 11]):
            x = set_bit(x, bit) if value & (1 << idx) else clear_bit(x, bit)
        self._data_type = x

    @property
    def last_packet(self) -> bool:
        return bool(self._data_type & 0b1000_0000)

    @last_packet.setter
    def last_packet(self, flag: bool):
        self._data_type = set_bit(self._data_type, 7) if flag else clear_bit(self._data_type, 7)

    @property
    def ccd_side(self) -> int:
        return (self._data_type & 0b0100_0000) >> 6

    @ccd_side.setter
    def ccd_side(self, value: int):
        self._data_type = set_bit(self._data_type, 6) if value & 0b0001 else clear_bit(self._data_type, 6)

    @property
    def ccd_number(self) -> int:
        return (self._data_type & 0b0011_0000) >> 4

    @ccd_number.setter
    def ccd_number(self, value):
        x = self._data_type
        for idx, bit in enumerate([4, 5]):
            x = set_bit(x, bit) if value & (1 << idx) else clear_bit(x, bit)
        self._data_type = x

    @property
    def frame_number(self) -> int:
        return (self._data_type & 0b1100) >> 2

    @frame_number.setter
    def frame_number(self, value):
        x = self._data_type
        for idx, bit in enumerate([2, 3]):
            x = set_bit(x, bit) if value & (1 << idx) else clear_bit(x, bit)
        self._data_type = x

    def __str__(self) -> str:
        from egse.fee import n_fee_mode
        n_fee_side = GlobalState.setup.camera.fee.ccd_sides.enum

        return (
            f"mode:{n_fee_mode(self.mode).name}, last_packet:{self.last_packet}, "
            f"CCD side:{n_fee_side(self.ccd_side).name}, CCD number:{self.ccd_number}, "
            f"Frame number:{self.frame_number}, Packet Type:{PacketType(self.packet_type).name}"
        )


def to_string(data: Union[DataPacketType]) -> str:
    """Returns a 'user-oriented' string representation of the SpW DataPacketType.

    The purpose of this function is to represent the N-FEE information in a user-oriented way.
    That means for certain values that they will be converted into the form the a user understands
    and that may be different or reverse from the original N-FEE definition. An example is the
    CCD number which is different from the user perspective with respect to the N-FEE.

    If any other object type is passed, the data.__str__() method will be returned without
    processing or conversion.

    Args:
        data: a DataPacketType
    """
    from egse.fee import n_fee_mode
    n_fee_side = GlobalState.setup.camera.fee.ccd_sides.enum

    if isinstance(data, DataPacketType):
        try:
            ccd_bin_to_id = GlobalState.setup.camera.fee.ccd_numbering.CCD_BIN_TO_ID
        except AttributeError:
            raise SetupError("No entry in the setup for camera.fee.ccd_numbering.CCD_BIN_TO_ID")
        return (
            f"mode:{n_fee_mode(data.mode).name}, last_packet:{data.last_packet}, "
            f"CCD side:{n_fee_side(data.ccd_side).name}, CCD number:"
            f"{ccd_bin_to_id[data.ccd_number]}, "
            f"Frame number:{data.frame_number}, Packet Type:{PacketType(data.packet_type).name}"
        )
    else:
        return data.__str__()


class DataPacketHeader:
    """
    Defines the header of a data packet.

    The full header can be retrieved as a bytes object with the `data_as_bytes()` method.

    Properties:
      * logical_address: fixed value of  0x50
      * protocol_id: fixed value of 0xF0
      * length: length of the data part of the packet, i.e. the packet length - size of the header
      * type: data packet type as defined by DataPacketType
      * frame_counter:
      * sequence_counter: a packet sequence counter per CCD
    """
    def __init__(self, header_data: bytes = None):
        self.header_data = bytearray(
            header_data or bytes([0x50, 0xF0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))

        if len(self.header_data) != 10:
            raise ValueError(f"The length of the header for a data packet shall be 10 bytes, "
                             f"got {len(self.header_data)}.")

        self.n_fee_side = GlobalState.setup.camera.fee.ccd_sides.enum

    def data_as_bytes(self) -> bytes:
        """Returns the full header as a bytes object."""
        return bytes(self.header_data)

    @property
    def logical_address(self) -> int:
        return self.header_data[0]

    @logical_address.setter
    def logical_address(self, value: int):
        self.header_data[0] = value

    @property
    def protocol_id(self) -> int:
        return self.header_data[1]

    @protocol_id.setter
    def protocol_id(self, value: int):
        self.header_data[1] = value

    @property
    def length(self) -> int:
        return int.from_bytes(self.header_data[2:4], byteorder='big')

    @length.setter
    def length(self, value: int):
        self.header_data[2:4] = value.to_bytes(2, 'big')

    @property
    def type(self):
        return int.from_bytes(self.header_data[4:6], byteorder='big')

    @type.setter
    def type(self, value: Union[int, bytes, DataPacketType]):
        if isinstance(value, bytes):
            self.header_data[4:6] = value
        elif isinstance(value, DataPacketType):
            self.header_data[4:6] = value.value.to_bytes(2, 'big')
        else:
            self.header_data[4:6] = value.to_bytes(2, 'big')

    @property
    def type_as_object(self):
        return DataPacketType(self.type)

    @property
    def packet_type(self):
        return self.type_as_object.packet_type

    @packet_type.setter
    def packet_type(self, value: int):
        type_obj = self.type_as_object
        type_obj.packet_type = value
        self.type = type_obj

    @property
    def last_packet(self):
        return self.type_as_object.last_packet

    @last_packet.setter
    def last_packet(self, flag: bool):
        type_obj = self.type_as_object
        type_obj.last_packet = flag
        self.type = type_obj

    @property
    def frame_counter(self):
        return int.from_bytes(self.header_data[6:8], byteorder='big')

    @frame_counter.setter
    def frame_counter(self, value):
        self.header_data[6:8] = value.to_bytes(2, 'big')

    @property
    def sequence_counter(self):
        return int.from_bytes(self.header_data[8:10], byteorder='big')

    @sequence_counter.setter
    def sequence_counter(self, value):
        self.header_data[8:10] = value.to_bytes(2, 'big')

    def as_dict(self):
        from egse.fee import n_fee_mode

        data_packet_type = DataPacketType(self.type)
        return dict(
            logical_address=f"0x{self.logical_address:02X}",
            protocol_id=f"0x{self.protocol_id:02X}",
            length=self.length,
            type=f"0x{self.type:04X}",
            frame_counter=self.frame_counter,
            sequence_counter=self.sequence_counter,
            packet_type=data_packet_type.packet_type,
            frame_number=data_packet_type.frame_number,
            ccd_number=data_packet_type.ccd_number,
            ccd_side=self.n_fee_side(data_packet_type.ccd_side).name,
            last_packet=data_packet_type.last_packet,
            mode=n_fee_mode(data_packet_type.mode).name,
        )


class SpaceWirePacket:
    """Base class for any packet transmitted over a SpaceWire cable."""

    # these settings are used by this class and its sub-classes to configure the print options
    # for the numpy arrays.

    _threshold = 300  # sys.maxsize
    _edgeitems = 10
    _linewidth = 120

    def __init__(self, data: Union[bytes, np.ndarray]):
        """
        Args:
            data: a bytes object or a numpy array of type np.uint8 (not enforced)
        """
        self._bytes = bytes(data)

    def __repr__(self):
        options = np.get_printoptions()
        np.set_printoptions(
            formatter={"int": lambda x: f"0x{x:02x}"},
            threshold=self._threshold,
            edgeitems=self._edgeitems,
            linewidth=self._linewidth,
        )
        msg = f"{self.__class__.__name__}({self._bytes})"
        np.set_printoptions(**options)
        return msg

    @property
    def packet_as_bytes(self):
        return self._bytes

    @property
    def packet_as_ndarray(self):
        return np.frombuffer(self._bytes, dtype=np.uint8)

    @property
    def logical_address(self):
        # TODO: what about a timecode, that has no logical address?
        return self._bytes[0]

    @property
    def protocol_id(self):
        # TODO: what about a timecode, that has no protocol id?
        return self._bytes[1]

    def header_as_bytes(self) -> bytes:
        # TODO: what about timecode, this has no header, except maybe the first byte: 0x91
        raise NotImplementedError

    @staticmethod
    def create_packet(data: Union[bytes, np.ndarray]):
        """
        Factory method that returns a SpaceWire packet of the correct type based on the information
        in the header.
        """
        if TimecodePacket.is_timecode_packet(data):
            return TimecodePacket(data)
        if HousekeepingPacket.is_housekeeping_packet(data):
            return HousekeepingPacket(data)
        if DataDataPacket.is_data_data_packet(data):
            return DataDataPacket(data)
        if OverscanDataPacket.is_overscan_data_packet(data):
            return OverscanDataPacket(data)
        if WriteRequest.is_write_request(data):
            return WriteRequest(data)
        if WriteRequestReply.is_write_reply(data):
            return WriteRequestReply(data)
        if ReadRequest.is_read_request(data):
            return ReadRequest(data)
        if ReadRequestReply.is_read_reply(data):
            return ReadRequestReply(data)
        return SpaceWirePacket(data)


class DataPacket(SpaceWirePacket):
    """
    Base class for proprietary SpaceWire data packets that are exchanged between FEE and DPU.

    .. note::
        This class should not be instantiated directly. Use the SpaceWirePacket.create_packet()
        factory method or the constructors of one of the sub-classes of this DataPacket class.
    """

    DATA_HEADER_LENGTH = 10

    def __init__(self, data: Union[bytes, np.ndarray]):
        """
        Args:
            data: a bytes object or a numpy array
        """
        if not self.is_data_packet(data):
            raise ValueError(
                f"Can not create a DataPacket from the given data {[f'0x{x:02x}' for x in data]}"
            )

        super().__init__(data)

        if (data[2] == 0x00 and data[3] == 0x00) or len(data) == self.DATA_HEADER_LENGTH:
            MODULE_LOGGER.warning(
                f"SpaceWire data packet without data found, packet={[f'0x{x:02x}' for x in data]}"
            )

        self._length = (data[2] << 8) + data[3]

        if len(data) != self._length + self.DATA_HEADER_LENGTH:
            MODULE_LOGGER.warning(
                f"The length of the data argument ({len(data)}) given to "
                f"the constructor of {self.__class__.__name__} (or sub-classes) is inconsistent "
                f"with the length data field ({self._length} + 10) in the packet header."
            )
            raise ValueError(
                f"{self.__class__.__name__} header: data-length field ({self._length}) not "
                f"consistent with packet length ({len(data)}). Difference should be "
                f"{self.DATA_HEADER_LENGTH}."
            )

        self._type = DataPacketType((data[4] << 8) + data[5])
        self._data = None  # lazy loading of data from self._bytes

    @property
    def length(self) -> int:
        """Returns the data length in bytes.

        .. note:: length == len(data_nd_array) * 2
            This length property returns the length of the data area in bytes. This value is
            taken  from the header of the data packet. If you want to compare this with the size
            of the data_as_ndarray property, multiply the length by 2 because the data is 16-bit
            integers, not bytes.

        Returns:
            the size of the data area of the packet in bytes.
        """
        return self._length

    @property
    def data_as_ndarray(self):
        """
        Returns the data from this data packet as a 16-bit integer Numpy array.

        .. note::
            The data has been converted from the 8-bit packet data into 16-bit integers. That
            means the length of this data array will be half the length of the data field the
            packet, i.e. ``len(data) == length // 2``.
            The reason for this is that pixel data has a size of 16-bit.

        .. todo::
            check if the data-length of HK packets should also be a multiple of 16.

        Returns:
            data: Numpy array with the data from this packet (type is np.uint16)

        """

        # We decided to lazy load/construct the data array. The reason is that the packet may be
        # created / transferred without the need to unpack the data field into a 16-bit numpy array.

        if self._data is None:
            # The data is in two's-complement. The most significant bit (msb) shall be inverted
            # according to Sampie Smit. That is done in the following line where the msb in each
            # byte on an even index is inverted.

            # data = [toggle_bit(b, 7) if not idx % 2 else b for idx, b in enumerate(self._bytes)]
            # data = bytearray(data)
            # data_1 = np.frombuffer(data, offset=10, dtype='>u2')

            # Needs further confirmation, but the following line should have the same effect as
            # the previous three lines.
            data_2 = np.frombuffer(self._bytes, offset=10, dtype='>i2') + TWOS_COMPLEMENT_OFFSET

            # Test if the results are identical, left the code in until we are fully confident
            # if diff := np.sum(np.cumsum(data_1 - data_2)):
            #     MODULE_LOGGER.info(f"cumsum={diff}")

            self._data = data_2.astype('uint16')
        return self._data

    @property
    def data(self) -> bytes:
        return self._bytes[10: 10 + self._length]

    @property
    def type(self) -> DataPacketType:
        return self._type

    @property
    def frame_counter(self):
        return (self._bytes[6] << 8) + self._bytes[7]

    @property
    def sequence_counter(self):
        return (self._bytes[8] << 8) + self._bytes[9]

    @property
    def header(self) -> DataPacketHeader:
        return DataPacketHeader(self.header_as_bytes())

    def header_as_bytes(self):
        return self._bytes[:10]

    @classmethod
    def is_data_packet(cls, data: np.ndarray) -> bool:
        if len(data) < 10 or data[0] != 0x50 or data[1] != 0xF0:
            return False
        return True

    def __str__(self):
        options = np.get_printoptions()
        np.set_printoptions(
            formatter={"int": lambda x: f"0x{x:04x}"},
            threshold=super()._threshold,
            edgeitems=super()._edgeitems,
            linewidth=super()._linewidth,
        )
        msg = (
            f"{self.__class__.__name__}:\n"
            f"  Logical Address = 0x{self.logical_address:02X}\n"
            f"  Protocol ID = 0x{self.protocol_id:02X}\n"
            f"  Length = {self.length}\n"
            f"  Type = {self._type}\n"
            f"  Frame Counter = {self.frame_counter}\n"
            f"  Sequence Counter = {self.sequence_counter}\n"
            f"  Data = \n{self.data}"
        )
        np.set_printoptions(**options)
        return msg


class DataDataPacket(DataPacket):
    """Proprietary Data Packet for N-FEE and F-FEE CCD image data."""

    @classmethod
    def is_data_data_packet(cls, data: Union[bytes, np.ndarray]) -> bool:
        if len(data) <= 10:
            return False
        if data[0] != 0x50:
            return False
        if data[1] != 0xF0:
            return False
        type_ = DataPacketType((data[4] << 8) + data[5])
        if type_.packet_type == PacketType.DATA_PACKET:
            return True
        return False


class OverscanDataPacket(DataPacket):
    """Proprietary Overscan Data Packet for N-FEE and F-FEE CCD image data."""

    @classmethod
    def is_overscan_data_packet(cls, data: Union[bytes, np.ndarray]) -> bool:
        if len(data) <= 10:
            return False
        if data[0] != 0x50:
            return False
        if data[1] != 0xF0:
            return False
        type_ = DataPacketType((data[4] << 8) + data[5])
        if type_.packet_type == PacketType.OVERSCAN_DATA:
            return True
        return False


class HousekeepingPacket(DataPacket):
    """Proprietary Housekeeping data packet for the N-FEE and F-FEE."""

    def __init__(self, data: Union[bytes, np.ndarray]):
        """
        Args:
            data: a numpy array of type np.uint8 (not enforced)
        """
        if not self.is_housekeeping_packet(data):
            raise ValueError(f"Can not create a HousekeepingPacket from the given data {data}")

        # The __init__ method of DataPacket already checks e.g. data-length against packet length,
        # so there is no need for these tests here.

        super().__init__(data)

    @classmethod
    def is_housekeeping_packet(cls, data: Union[bytes, np.ndarray]) -> bool:
        if len(data) <= 10:
            return False
        if data[0] != 0x50:
            return False
        if data[1] != 0xF0:
            return False
        type_ = DataPacketType((data[4] << 8) + data[5])
        if type_.packet_type == PacketType.HOUSEKEEPING_DATA:
            return True
        return False


class TimecodePacket(SpaceWirePacket):
    """A Timecode Packet.

    This packet really is an extended packet which is generated by the Diagnostic SpaceWire
    Interface (DSI) to forward a SpaceWire timecode over the Ethernet connection.
    """

    def __init__(self, data: Union[bytes, np.ndarray]):
        super().__init__(data)

    @property
    def timecode(self) -> int:
        return self._bytes[1] & 0x3F

    def header_as_bytes(self) -> bytes:
        return self._bytes[0:1]

    @classmethod
    def is_timecode_packet(cls, data: Union[bytes, np.ndarray]) -> bool:
        return data[0] == 0x91

    def __str__(self):
        return f"Timecode Packet: timecode = 0x{self.timecode:x}"


class RMAPPacket(SpaceWirePacket):
    """Base class for RMAP SpaceWire packets."""

    def __init__(self, data: Union[bytes, np.ndarray]):
        if not self.is_rmap_packet(data):
            raise ValueError(f"Can not create a RMAPPacket from the given data {data}")
        super().__init__(data)

    def __str__(self):
        return (
            f"{self.__class__.__name__}:\n"
            f"  Logical Address = 0x{self.logical_address:02X}\n"
            f"  Data = {self.data}\n"
        )

    @property
    def instruction(self):
        return get_instruction_field(self._bytes)

    @property
    def transaction_id(self):
        return get_transaction_identifier(self._bytes)

    @classmethod
    def is_rmap_packet(cls, data: Union[bytes, np.ndarray]):
        if data[1] == 0x01:  # Protocol ID
            return True
        return False


class WriteRequest(RMAPPacket):
    """A Write Request SpaceWire RMAP Packet."""

    def __init__(self, data: Union[bytes, np.ndarray]):
        super().__init__(data)

    def is_verified(self):
        return self._bytes[2] == 0x7C

    def is_unverified(self):
        return self._bytes[2] == 0x6C

    @property
    def address(self):
        return get_address(self._bytes)

    @property
    def data_length(self):
        return get_data_length(self._bytes)

    @property
    def data(self) -> bytes:
        return get_data(self._bytes)

    @classmethod
    def is_write_request(cls, data: Union[bytes, np.ndarray]):
        if not RMAPPacket.is_rmap_packet(data):
            return False
        if data[0] != 0x51:
            return False
        if (data[2] == 0x7C or data[2] == 0x6C) and data[3] == 0xD1:
            return True
        return False

    def __str__(self):
        prefix = "Verified" if self.is_verified() else "Unverified"
        return f"{prefix} Write Request: {self.transaction_id=}, data=0x{self.data.hex()}"


class WriteRequestReply(RMAPPacket):
    """An RMAP Reply packet to a Write Request."""

    def __init__(self, data: Union[bytes, np.ndarray]):
        super().__init__(data)
        self._status = data[3]

    @classmethod
    def is_write_reply(cls, data: Union[bytes, np.ndarray]):
        if not RMAPPacket.is_rmap_packet(data):
            return False
        if data[0] != 0x50:
            return False
        if (data[2] == 0x3C or data[2] == 0x2C) and data[4] == 0x51:
            return True

    @property
    def status(self):
        return self._status

    def __str__(self):
        return f"Write Request Reply: status={self.status}"


class ReadRequest(RMAPPacket):
    """A Read Request SpaceWire RMAP Packet."""

    def __init__(self, data: Union[bytes, np.ndarray]):
        super().__init__(data)

    @classmethod
    def is_read_request(cls, data: Union[bytes, np.ndarray]):
        if not RMAPPacket.is_rmap_packet(data):
            return False
        if data[0] != 0x51:
            return False
        if data[2] == 0x4C and data[3] == 0xD1:
            return True
        return False

    @property
    def address(self):
        return get_address(self._bytes)

    @property
    def data_length(self):
        return get_data_length(self._bytes)

    def __str__(self):
        return (
            f"Read Request: tid={self.transaction_id}, address=0x{self.address:04x}, "
            f"data length={self.data_length}"
        )


class ReadRequestReply(RMAPPacket):
    """An RMAP Reply packet to a Read Request."""

    def __init__(self, data: Union[bytes, np.ndarray]):
        super().__init__(data)

    @classmethod
    def is_read_reply(cls, data: Union[bytes, np.ndarray]):
        if not RMAPPacket.is_rmap_packet(data):
            return False
        if data[0] != 0x50:
            return False
        if data[2] == 0x0C and data[4] == 0x51:
            return True

    @property
    def data(self) -> bytes:
        return get_data(self._bytes)

    @property
    def data_length(self):
        return get_data_length(self._bytes)

    def __str__(self):
        data_length = self.data_length
        return f"Read Request Reply: data length={data_length}, data={self.data[:20]} " \
               f"{'(data is cut to max 20 bytes)' if data_length > 20 else ''}\n"


class SpaceWireInterface:
    """
    This interface defines methods that are used by the DPU to communicate with the FEE over
    SpaceWire.
    """

    def __enter__(self):
        self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def configure(self):
        raise NotImplementedError

    def flush(self):
        raise NotImplementedError

    def send_timecode(self, timecode: int):
        raise NotImplementedError

    def read_packet(self, timeout: int = None) -> Tuple[int, bytes]:
        """
        Read a full packet from the SpaceWire transport layer.

        Args:
            timeout (int): timeout in milliseconds [default=None]
        Returns:
            A tuple with the terminator value and a bytes object containing the packet.
        """
        raise NotImplementedError

    def write_packet(self, packet: bytes):
        """
        Write a full packet to the SpaceWire transport layer.

        Args:
            packet (bytes): a bytes object containing the SpaceWire packet

        Returns:
            None.
        """
        raise NotImplementedError

    def read_register(self, address: int, length: int = 4, strict: bool = True) -> bytes:
        """
        Reads the data for the given register from the FEE memory map.

        This function sends an RMAP read request for the register to the FEE.

        Args:
            address: the start address (32-bit aligned) in the remote memory
            length: the number of bytes to read from the remote memory [default = 4]
            strict: perform strict checking of address and length

        Returns:
            data: the 32-bit data that was read from the FEE.
        """
        raise NotImplementedError

    def write_register(self, address: int, data: bytes):
        """
        Writes the data from the given register to the N-FEE memory map.

        The function reads the data for the registry from the local register map
        and then sends an RMAP write request for the register to the N-FEE.

        .. note:: it is assumed that the local register map is up-to-date.

        Args:
            address: the start address (32-bit aligned) in the remote memory
            data: the data that will be written into the remote memory

        Raises:
            RMAPError: when data can not be written on the target, i.e. the N-FEE.
        """

        raise NotImplementedError

    def read_memory_map(self, address: int, size: int):
        """
        Read (part of) the memory map from the N-FEE.

        Args:
            address: start address
            size: number of bytes to read

        Returns:
            a bytes object containing the requested memory map.
        """

        raise NotImplementedError


# General RMAP helper functions ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

def rmap_crc_check(data, start, length) -> int:
    """Calculate the checksum for the given data."""
    return crc_calc(data, start, length)


def get_protocol_id(data: bytes) -> int:
    """
    Returns the protocol identifier field. The protocol ID is 1 (0x01) for the RMAP protocol.
    """
    return data[1]


def get_reply_address_field_length(rx_buffer) -> int:
    """Returns the size of reply address field.

    This function returns the actual size of the reply address field. It doesn't return
    the content of the reply address length field. If you need that information, use the
    reply_address_length() function that work on the instruction field.

    Returns:
         length: the size of the reply address field.
    """
    instruction = get_instruction_field(rx_buffer)
    return reply_address_length(instruction) * 4


def get_data(rxbuf) -> bytes:
    """
    Return the data from the RMAP packet.

    Raises:
        ValueError: if there is no data section in the packet (TODO: not yet implemented)
    """
    instruction_field = get_instruction_field(rxbuf)
    address_length = get_reply_address_field_length(rxbuf)
    data_length = get_data_length(rxbuf)

    offset = 12 if is_read(instruction_field) else 16

    return rxbuf[offset + address_length:offset + address_length + data_length]


def check_data_crc(rxbuf):
    instruction_field = get_instruction_field(rxbuf)
    address_length = get_reply_address_field_length(rxbuf)
    data_length = get_data_length(rxbuf)

    offset = 12 if is_read(instruction_field) else 16
    idx = offset + address_length

    d_crc = rxbuf[idx + data_length]
    c_crc = rmap_crc_check(rxbuf, idx, data_length) & 0xFF
    if d_crc != c_crc:
        raise CheckError(
            f"Data CRC doesn't match calculated CRC, d_crc=0x{d_crc:02X} & c_crc=0x{c_crc:02X}",
            RMAP_GENERAL_ERROR
        )


def check_header_crc(rxbuf):
    instruction_field = get_instruction_field(rxbuf)
    if is_command(instruction_field):
        offset = 15
    elif is_write(instruction_field):
        offset = 7
    else:
        offset = 11

    idx = offset + get_reply_address_field_length(rxbuf)
    h_crc = rxbuf[idx]
    c_crc = rmap_crc_check(rxbuf, 0, idx)
    if h_crc != c_crc:
        raise CheckError(
            f"Header CRC doesn't match calculated CRC, h_crc=0x{h_crc:02X} & c_crc=0x{c_crc:02X}",
            RMAP_GENERAL_ERROR
        )


def get_data_length(rxbuf) -> int:
    """
    Returns the length of the data in bytes.

    Raises:
        TypeError: when this method is used on a Write Request Reply packet (which has no
            data length).
    """
    instruction_field = get_instruction_field(rxbuf)

    if not is_command(instruction_field) and is_write(instruction_field):
        raise TypeError("There is no data length field for Write Request Reply packets, "
                        "asking for the data length is an invalid operation.")

    offset = 12 if is_command(instruction_field) else 8
    idx = offset + get_reply_address_field_length(rxbuf)

    # We could use two alternative decoding methods here:
    #   int.from_bytes(rxbuf[idx:idx+3], byteorder='big')    (timeit=1.166s)
    #   struct.unpack('>L', b'\x00' + rxbuf[idx:idx+3])[0]   (timeit=0.670s)
    data_length = struct.unpack('>L', b'\x00' + rxbuf[idx:idx + 3])[0]
    return data_length


def get_address(rxbuf) -> int:
    """
    Returns the address field (including the extended address field if the address is 40-bits).

    Raises:
        TypeError: when this method is used on a Reply packet (which has no address field).
    """
    instruction_field = get_instruction_field(rxbuf)

    if not is_command(instruction_field):
        raise TypeError("There is no address field for Reply packets, asking for the address is "
                        "an invalid operation.")

    idx = 7 + get_reply_address_field_length(rxbuf)
    extended_address = rxbuf[idx]
    idx += 1
    address = struct.unpack('>L', rxbuf[idx:idx + 4])[0]
    if extended_address:
        address = address + (extended_address << 32)
    return address


def get_instruction_field(rxbuf):
    idx = 2
    return rxbuf[idx]


def get_transaction_identifier(rxbuf):
    idx = 5 + get_reply_address_field_length(rxbuf)
    tid = struct.unpack('>h', rxbuf[idx:idx + 2])[0]
    return tid


# Functions to interpret the Instrument Field

def is_reserved(instruction):
    """The reserved bit of the 2-bit packet type field from the instruction field.

    For PLATO this bit shall be zero as the 0b10 and 0b11 packet field values are reserved.

    Returns:
        bit value: 1 or 0.
    """
    return (instruction & 0b10000000) >> 7


def is_command(instruction):
    """Returns True if the RMAP packet is a command packet."""
    return (instruction & 0b01000000) >> 6


def is_reply(instruction):
    """Returns True if the RMAP packet is a reply to a previous command packet."""
    return not is_command(instruction)


def is_write(instruction):
    """Returns True if the RMAP packet is a write request command packet."""
    return (instruction & 0b00100000) >> 5


def is_read(instruction):
    """Returns True if the RMAP packet is a read request command packet."""
    return not is_write(instruction)


def is_verify(instruction):
    """Returns True if the RMAP packet needs to do a verify before write."""
    return (instruction & 0b00010000) >> 4


def is_reply_required(instruction):
    """Returns True if the reply bit is set in the instruction field.

    Args:
        instruction (int): the instruction field of an RMAP packet

    .. note:: the name of this function might be confusing.

        This function does **not** test if the packet is a reply packet, but it checks
        if the command requests a reply from the target. If you need to test if the
        packet is a command or a reply, use the is_command() or is_reply() function.

    """
    return (instruction & 0b00001000) >> 3


def is_increment(instruction):
    """Returns True if the data is written to sequential memory addresses."""
    return (instruction & 0b00000100) >> 2


def reply_address_length(instruction):
    """Returns the content of the reply address length field.

    The size of the reply address field is then decoded from the following table:

        Address Field Length  |  Size of Address Field
        ----------------------+-----------------------
             0b00             |      0 bytes
             0b01             |      4 bytes
             0b10             |      8 bytes
             0b11             |     12 bytes

    """
    return (instruction & 0b00000011) << 2
