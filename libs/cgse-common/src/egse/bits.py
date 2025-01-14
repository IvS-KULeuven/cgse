"""
This module contains a number of convenience functions to work with bits, bytes and integers.
"""

import ctypes
from typing import Union


def set_bit(value: int, bit) -> int:
    """
    Set bit to 1 for the given value.

    Args:
        value (int): the integer value that needs a bit set or unset
        bit (int): the index of the bit to set/unset, starting from 0 at the LSB

    Returns:
        the changed value.
    """
    return value | (1 << bit)


def set_bits(value: int, bits: tuple) -> int:
    """
    Set the given bits in value to 1.
    Args:
        value (int): the value where the given bits shall be changed
        bits (tuple): a tuple with start and stop bits
    Returns:
        the changed value
    """
    for i in range(bits[0], bits[1]):
        value |= 1 << i
    return value


def clear_bit(value: int, bit) -> int:
    """
    Set bit to 0 for the given value.

    Args:
        value (int): the integer value that needs a bit set or unset
        bit (int): the index of the bit to set/unset, starting from 0 at the LSB

    Returns:
        the changed value.
    """
    return value & ~(1 << bit)


def clear_bits(value: int, bits: tuple) -> int:
    """
    Set the given bits in value to 0.
    Args:
        value (int): the value where the given bits shall be changed
        bits (tuple): a tuple with start and stop bits
    Returns:
        the changed value
    """
    for i in range(bits[0], bits[1]):
        value &= ~(1 << i)
    return value


def toggle_bit(value: int, bit) -> int:
    """
    Toggle the bit in the given value.

    Args:
        value (int): the integer value that needs a bit toggled
        bit (int): the index of the bit to toggle, starting from 0 at the LSB

    Returns:
        the changed value.
    """
    return value ^ (1 << bit)


def bit_set(value: int, bit) -> bool:
    """
    Return True if the bit is set.

    Args:
        value (int): the value to check
        bit (int): the index of the bit to check, starting from 0 at the LSB

    Returns:
        True if the bit is set (1).
    """
    bit_value = 1 << bit
    return value & (bit_value) == bit_value


def bits_set(value: int, *args) -> bool:
    """
    Return True if all the bits are set.

    Args:
        value (int): the value to check
        args: a set of indices of the bits to check, starting from 0 at the LSB
    Returns:
        True if all the bits are set (1).

    For example:
        >>> assert bits_set(0b0101_0000_1011, [0, 1, 3, 8, 10])
        >>> assert bits_set(0b0101_0000_1011, [3, 8])
        >>> assert not bits_set(0b0101_0000_1011, [1, 2, 3])
    """

    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]
    return all([bit_set(value, bit) for bit in args])


def beautify_binary(value: int, sep: str = " ", group: int = 8, prefix: str = "", size: int = 0):
    """
    Returns a binary representation of the given value. The bits are presented
    in groups of 8 bits for clarity by default (can be changed with the `group` keyword).

    Args:
        value (int): the value to beautify
        sep (str): the separator character to be used, default is a space
        group (int): the number of bits to group together, default is 8
        prefix (str): a string to prefix the result, default is ''
        size (int): number of digits

    Returns:
        a binary string representation.

    For example:
        >>> status = 2**14 + 2**7
        >>> assert beautify_binary(status) == "01000000 10000000"
    """

    if size == 0:
        size = 8
        while value > 2**size - 1:
            size += 8

    b_str = f"{value:0{size}b}"

    return prefix + sep.join([b_str[i : i + group] for i in range(0, len(b_str), group)])


def humanize_bytes(n: int, base: Union[int, str] = 2, precision: int = 3) -> str:
    """
    Represents the size `n` in human readable form, i.e. as byte, KiB, MiB, GiB, ...

    Please note that, by default, I use the IEC standard (International Engineering Consortium)
    which is in `base=2` (binary), i.e. 1024 bytes = 1.0 KiB. If you need SI units (International
    System of Units), you need to specify `base=10` (decimal), i.e. 1000 bytes = 1.0 kB.

    Args:
        n (int): number of byte
        base (int, str): binary (2) or decimal (10)
        precision (int): the number of decimal places [default=3]
    Returns:
        a human readable size, like 512 byte or 2.300 TiB
    Raises:
        ValueError when base is different from 2 (binary) or 10 (decimal).

    Examples:
        >>> assert humanize_bytes(55) == "55 bytes"
        >>> assert humanize_bytes(1024) == "1.000 KiB"
        >>> assert humanize_bytes(1000, base=10) == "1.000 kB"
        >>> assert humanize_bytes(1000000000) == '953.674 MiB'
        >>> assert humanize_bytes(1000000000, base=10) == '1.000 GB'
        >>> assert humanize_bytes(1073741824) == '1.000 GiB'
        >>> assert humanize_bytes(1024**5 - 1, precision=0) == '1024 TiB'
    """

    if base not in [2, 10, "binary", "decimal"]:
        raise ValueError(f"Only base 2 (binary) and 10 (decimal) are supported, got {base}.")

    # By default we assume base == 2 or base == "binary"

    one_kilo = 1024
    units = ["KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"]

    if base == 10 or base == "decimal":
        one_kilo = 1000
        units = ["kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]

    _n = n
    if _n < one_kilo:
        return f"{_n} byte{'' if n == 1 else 's'}"

    for dim in units:
        _n /= one_kilo
        if _n < one_kilo:
            return f"{_n:.{precision}f} {dim}"

    return f"{n} byte{'' if n == 1 else 's'}"


CRC_TABLE = [
    0x00,
    0x91,
    0xE3,
    0x72,
    0x07,
    0x96,
    0xE4,
    0x75,
    0x0E,
    0x9F,
    0xED,
    0x7C,
    0x09,
    0x98,
    0xEA,
    0x7B,
    0x1C,
    0x8D,
    0xFF,
    0x6E,
    0x1B,
    0x8A,
    0xF8,
    0x69,
    0x12,
    0x83,
    0xF1,
    0x60,
    0x15,
    0x84,
    0xF6,
    0x67,
    0x38,
    0xA9,
    0xDB,
    0x4A,
    0x3F,
    0xAE,
    0xDC,
    0x4D,
    0x36,
    0xA7,
    0xD5,
    0x44,
    0x31,
    0xA0,
    0xD2,
    0x43,
    0x24,
    0xB5,
    0xC7,
    0x56,
    0x23,
    0xB2,
    0xC0,
    0x51,
    0x2A,
    0xBB,
    0xC9,
    0x58,
    0x2D,
    0xBC,
    0xCE,
    0x5F,
    0x70,
    0xE1,
    0x93,
    0x02,
    0x77,
    0xE6,
    0x94,
    0x05,
    0x7E,
    0xEF,
    0x9D,
    0x0C,
    0x79,
    0xE8,
    0x9A,
    0x0B,
    0x6C,
    0xFD,
    0x8F,
    0x1E,
    0x6B,
    0xFA,
    0x88,
    0x19,
    0x62,
    0xF3,
    0x81,
    0x10,
    0x65,
    0xF4,
    0x86,
    0x17,
    0x48,
    0xD9,
    0xAB,
    0x3A,
    0x4F,
    0xDE,
    0xAC,
    0x3D,
    0x46,
    0xD7,
    0xA5,
    0x34,
    0x41,
    0xD0,
    0xA2,
    0x33,
    0x54,
    0xC5,
    0xB7,
    0x26,
    0x53,
    0xC2,
    0xB0,
    0x21,
    0x5A,
    0xCB,
    0xB9,
    0x28,
    0x5D,
    0xCC,
    0xBE,
    0x2F,
    0xE0,
    0x71,
    0x03,
    0x92,
    0xE7,
    0x76,
    0x04,
    0x95,
    0xEE,
    0x7F,
    0x0D,
    0x9C,
    0xE9,
    0x78,
    0x0A,
    0x9B,
    0xFC,
    0x6D,
    0x1F,
    0x8E,
    0xFB,
    0x6A,
    0x18,
    0x89,
    0xF2,
    0x63,
    0x11,
    0x80,
    0xF5,
    0x64,
    0x16,
    0x87,
    0xD8,
    0x49,
    0x3B,
    0xAA,
    0xDF,
    0x4E,
    0x3C,
    0xAD,
    0xD6,
    0x47,
    0x35,
    0xA4,
    0xD1,
    0x40,
    0x32,
    0xA3,
    0xC4,
    0x55,
    0x27,
    0xB6,
    0xC3,
    0x52,
    0x20,
    0xB1,
    0xCA,
    0x5B,
    0x29,
    0xB8,
    0xCD,
    0x5C,
    0x2E,
    0xBF,
    0x90,
    0x01,
    0x73,
    0xE2,
    0x97,
    0x06,
    0x74,
    0xE5,
    0x9E,
    0x0F,
    0x7D,
    0xEC,
    0x99,
    0x08,
    0x7A,
    0xEB,
    0x8C,
    0x1D,
    0x6F,
    0xFE,
    0x8B,
    0x1A,
    0x68,
    0xF9,
    0x82,
    0x13,
    0x61,
    0xF0,
    0x85,
    0x14,
    0x66,
    0xF7,
    0xA8,
    0x39,
    0x4B,
    0xDA,
    0xAF,
    0x3E,
    0x4C,
    0xDD,
    0xA6,
    0x37,
    0x45,
    0xD4,
    0xA1,
    0x30,
    0x42,
    0xD3,
    0xB4,
    0x25,
    0x57,
    0xC6,
    0xB3,
    0x22,
    0x50,
    0xC1,
    0xBA,
    0x2B,
    0x59,
    0xC8,
    0xBD,
    0x2C,
    0x5E,
    0xCF,
]


def crc_calc(data, start: int, len: int) -> int:
    """
    Calculate the checksum for (part of) the data.

    Reference:
        The description of the CRC calculation for RMAP is given in the ECSS document
        _Space Engineering: SpaceWire - Remote Memory Access Protocol_, section A.3
        on page 80 [ECSS‐E‐ST‐50‐52C].

    Args:
        data: the data for which the checksum needs to be calculated
        start: offset into the data array [byte]
        len: number of bytes to incorporate into the calculation

    Returns:
        the calculated checksum.
    """
    crc: int = 0

    # The check below is needed because we can pass data that is of type ctypes.c_char_Array
    # and the individual elements have then type 'bytes'.

    if isinstance(data[0], bytes):
        for idx in range(start, start + len):
            crc = CRC_TABLE[crc ^ (int.from_bytes(data[idx], byteorder="big") & 0xFF)]
    elif isinstance(data[0], int):
        for idx in range(start, start + len):
            crc = CRC_TABLE[crc ^ (data[idx] & 0xFF)]

    return crc


def s16(value: int):
    """
    Return the signed equivalent of a hex or binary number.

    Since integers in Python are objects and stored in a variable number of bits, Python doesn't
    know the concept of twos-complement for negative integers. For example, this 16-bit number

        >>> 0b1000_0000_0001_0001
        32785

    which in twos-complement is actually a negative value:

        >>> s16(0b1000_0000_0001_0001)
        -32751

    The 'bin()' fuction will return a strange representation of this number:

        >>> bin(-32751)
        '-0b111111111101111'

    when we however mask the value we get:

        >>> bin(-32751 & 0b1111_1111_1111_1111)
        '0b1000000000010001'

    See:
        https://stackoverflow.com/questions/1604464/twos-complement-in-python and
        https://stackoverflow.com/questions/46993519/python-representation-of-negative-integers and
        https://stackoverflow.com/questions/25096755/signed-equivalent-of-a-2s-complement-hex-value
        and https://stackoverflow.com/a/32262478/4609203

    Returns:
        The negative equivalent of a twos-complement binary number.
    """
    return ctypes.c_int16(value).value


def s32(value: int):
    """
    Return the signed equivalent of a hex or binary number.

    Since integers in Python are objects and stored in a variable number of bits, Python doesn't
    know the concept of twos-complement for negative integers. For example, this 32-bit number

        >>> 0b1000_0000_0000_0000_0000_0000_0001_0001
        2147483665

    which in twos-complement is actually a negative value:

        >>> s32(0b1000_0000_0000_0000_0000_0000_0001_0001)
        -2147483631

    Returns:
        The negative equivalent of a twos-complement binary number.
    """
    return ctypes.c_int32(value).value
