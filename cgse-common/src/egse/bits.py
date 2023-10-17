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


def beautify_binary(value: int, sep: str = ' ', group: int = 8, prefix: str = '', size: int = 0):
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

    b_str = f'{value:0{size}b}'

    return prefix + sep.join([b_str[i:i + group] for i in range(0, len(b_str), group)])


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
    units = ['KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']

    if base == 10 or base == 'decimal':
        one_kilo = 1000
        units = ['kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']

    _n = n
    if _n < one_kilo:
        return f"{_n} byte{'' if n == 1 else 's'}"

    for dim in units:
        _n /= one_kilo
        if _n < one_kilo:
            return f"{_n:.{precision}f} {dim}"

    return f"{n} byte{'' if n == 1 else 's'}"


CRC_TABLE = [
    0x00, 0x91, 0xe3, 0x72, 0x07, 0x96, 0xe4, 0x75,
    0x0e, 0x9f, 0xed, 0x7c, 0x09, 0x98, 0xea, 0x7b,
    0x1c, 0x8d, 0xff, 0x6e, 0x1b, 0x8a, 0xf8, 0x69,
    0x12, 0x83, 0xf1, 0x60, 0x15, 0x84, 0xf6, 0x67,
    0x38, 0xa9, 0xdb, 0x4a, 0x3f, 0xae, 0xdc, 0x4d,
    0x36, 0xa7, 0xd5, 0x44, 0x31, 0xa0, 0xd2, 0x43,
    0x24, 0xb5, 0xc7, 0x56, 0x23, 0xb2, 0xc0, 0x51,
    0x2a, 0xbb, 0xc9, 0x58, 0x2d, 0xbc, 0xce, 0x5f,
    0x70, 0xe1, 0x93, 0x02, 0x77, 0xe6, 0x94, 0x05,
    0x7e, 0xef, 0x9d, 0x0c, 0x79, 0xe8, 0x9a, 0x0b,
    0x6c, 0xfd, 0x8f, 0x1e, 0x6b, 0xfa, 0x88, 0x19,
    0x62, 0xf3, 0x81, 0x10, 0x65, 0xf4, 0x86, 0x17,
    0x48, 0xd9, 0xab, 0x3a, 0x4f, 0xde, 0xac, 0x3d,
    0x46, 0xd7, 0xa5, 0x34, 0x41, 0xd0, 0xa2, 0x33,
    0x54, 0xc5, 0xb7, 0x26, 0x53, 0xc2, 0xb0, 0x21,
    0x5a, 0xcb, 0xb9, 0x28, 0x5d, 0xcc, 0xbe, 0x2f,
    0xe0, 0x71, 0x03, 0x92, 0xe7, 0x76, 0x04, 0x95,
    0xee, 0x7f, 0x0d, 0x9c, 0xe9, 0x78, 0x0a, 0x9b,
    0xfc, 0x6d, 0x1f, 0x8e, 0xfb, 0x6a, 0x18, 0x89,
    0xf2, 0x63, 0x11, 0x80, 0xf5, 0x64, 0x16, 0x87,
    0xd8, 0x49, 0x3b, 0xaa, 0xdf, 0x4e, 0x3c, 0xad,
    0xd6, 0x47, 0x35, 0xa4, 0xd1, 0x40, 0x32, 0xa3,
    0xc4, 0x55, 0x27, 0xb6, 0xc3, 0x52, 0x20, 0xb1,
    0xca, 0x5b, 0x29, 0xb8, 0xcd, 0x5c, 0x2e, 0xbf,
    0x90, 0x01, 0x73, 0xe2, 0x97, 0x06, 0x74, 0xe5,
    0x9e, 0x0f, 0x7d, 0xec, 0x99, 0x08, 0x7a, 0xeb,
    0x8c, 0x1d, 0x6f, 0xfe, 0x8b, 0x1a, 0x68, 0xf9,
    0x82, 0x13, 0x61, 0xf0, 0x85, 0x14, 0x66, 0xf7,
    0xa8, 0x39, 0x4b, 0xda, 0xaf, 0x3e, 0x4c, 0xdd,
    0xa6, 0x37, 0x45, 0xd4, 0xa1, 0x30, 0x42, 0xd3,
    0xb4, 0x25, 0x57, 0xc6, 0xb3, 0x22, 0x50, 0xc1,
    0xba, 0x2b, 0x59, 0xc8, 0xbd, 0x2c, 0x5e, 0xcf,
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
        for idx in range(start, start+len):
            crc = CRC_TABLE[crc ^ (int.from_bytes(data[idx], byteorder='big') & 0xFF)]
    elif isinstance(data[0], int):
        for idx in range(start, start+len):
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
