import ctypes
import logging

import pytest

from egse.bits import beautify_binary
from egse.bits import bit_set
from egse.bits import bits_set
from egse.bits import clear_bit
from egse.bits import clear_bits
from egse.bits import crc_calc
from egse.bits import humanize_bytes
from egse.bits import s16
from egse.bits import s32
from egse.bits import set_bit
from egse.bits import set_bits
from egse.bits import toggle_bit

logger = logging.getLogger(__name__)


def test_clear_bit():
    bf = 0b11111111

    for bit in range(8):
        assert bit_set(bf, bit)

    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")

    bf = clear_bit(bf, 3)
    assert not bit_set(bf, 3)
    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")

    bf = clear_bit(bf, 0)
    assert not bit_set(bf, 0)
    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")

    bf = clear_bit(bf, 7)
    assert not bit_set(bf, 7)
    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")


def test_set_bit():
    bf = 0b00000000

    for bit in range(8):
        assert not bit_set(bf, bit)

    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")
    bf = set_bit(bf, 3)
    assert bit_set(bf, 3)
    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")
    bf = set_bit(bf, 0)
    assert bit_set(bf, 0)
    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")
    bf = set_bit(bf, 7)
    assert bit_set(bf, 7)
    logger.debug(f"bf = {bf:4}, 0b{bf:08b}")
    assert bits_set(bf, 0, 3, 7)
    assert bits_set(bf, [0, 3, 7])
    assert not bits_set(bf, [0, 1, 3, 7])

    assert bits_set(bf, 0)
    assert bits_set(bf, [0])


def test_toggle_bit():

    bf = 0b0000_0000

    assert toggle_bit(bf, 0) == 0b0001
    assert toggle_bit(bf, 7) == 0b1000_0000

    bf = toggle_bit(bf, 3)

    assert bf == 0b0000_1000

    bf = 0b0000_0000

    for i in range(8):
        bf = toggle_bit(bf, i)

    assert bf == 0b1111_1111


def test_beautify_binary():
    assert beautify_binary(0b0010, group=4) == '0000 0010'
    assert beautify_binary(0b1111_1111, group=4) == '1111 1111'
    assert beautify_binary(0b0000_0001_1111_1111) == '00000001 11111111'

    assert beautify_binary(2 ** 7) == '10000000'
    assert beautify_binary(2 ** 8) == '00000001 00000000'
    assert beautify_binary(2 ** 9 - 1, group=4, sep='_') == '0000_0001_1111_1111'
    assert beautify_binary(2 ** 14) == '01000000 00000000'
    assert beautify_binary(2 ** 24) == '00000001 00000000 00000000 00000000'
    assert beautify_binary(2 ** 27) == '00001000 00000000 00000000 00000000'
    assert beautify_binary(2 ** 33) == '00000010 00000000 00000000 00000000 00000000'

    assert beautify_binary(0b11111111000011110000111100000000, sep='_') == \
        '11111111_00001111_00001111_00000000'
    assert beautify_binary(0b11111111000011110000111100000000, sep='_', group=4) == \
        '1111_1111_0000_1111_0000_1111_0000_0000'

    assert beautify_binary(0b0101_0101_0101_0011, sep='_', group=4, prefix='0b') == \
        '0b0101_0101_0101_0011'


def test_set_bits():
    assert set_bits(0, (0, 1)) == 0b00000001
    assert set_bits(0, (7, 8)) == 0b10000000
    assert set_bits(0, (1, 3)) == 0b00000110
    assert set_bits(0, (0, 8)) == 0b11111111

    assert set_bits(0b0001_1000, (3, 5)) == 0b0001_1000
    assert set_bits(0b0001_1000, (2, 6)) == 0b0011_1100

    assert set_bits(0, (128, 129)) == 2 ** 128
    assert set_bits(0, (0, 129)) == 2 ** 129 - 1


def test_alternative_set_bits():

    for width in 1, 4, 8, 12, 15, 16, 32, 128, 129:
        assert set_bits(0, (0, width)) == int('1'*width, 2)


def test_clear_bits():
    assert clear_bits(0xFF, (0, 1)) == 0b11111110
    assert clear_bits(0xFF, (7, 8)) == 0b01111111
    assert clear_bits(0xFF, (1, 3)) == 0b11111001
    assert clear_bits(0xFF, (0, 8)) == 0b00000000

    assert clear_bits(0b0001_1000, (3, 5)) == 0b0000_0000
    assert clear_bits(0b0011_1100, (3, 5)) == 0b0010_0100


def test_crc_calc():
    b = b'abcdefghijklmnopqrstuvwxyz'

    assert crc_calc(b, 0,  0) == 0x00
    assert crc_calc(b, 0,  1) == 0xD9
    assert crc_calc(b, 0, 16) == 0x8A
    assert crc_calc(b, 0, 26) == 0x63

    assert crc_calc(b, 5,  0) == 0x00
    assert crc_calc(b, 5,  1) == 0xAC
    assert crc_calc(b, 5, 16) == 0x12

    with pytest.raises(IndexError):
        assert crc_calc(b, 5, 26) == 0x32

    with pytest.raises(IndexError):
        assert crc_calc(b, 0, 27) == 0x63

    b = ctypes.create_string_buffer(b'abcdefghijklmnopqrstuvwxyz')

    assert crc_calc(b, 0,  0) == 0x00
    assert crc_calc(b, 0,  1) == 0xD9
    assert crc_calc(b, 0, 16) == 0x8A
    assert crc_calc(b, 0, 26) == 0x63

    assert crc_calc(b, 5,  0) == 0x00
    assert crc_calc(b, 5,  1) == 0xAC
    assert crc_calc(b, 5, 16) == 0x12

    with pytest.raises(IndexError):
        assert crc_calc(b, 5, 26) == 0x32

    # Note that we have an additional \x0 (NUL) character here added by the
    # ctypes function because we passed in a bytes object. So, the IndexError
    # will only be generated when accessing 28 characters!

    with pytest.raises(IndexError):
        assert crc_calc(b, 0, 28) == 0x63

def test_humanize_bytes():

    assert humanize_bytes(0) == "0 bytes"
    assert humanize_bytes(1) == "1 byte"
    assert humanize_bytes(60) == "60 bytes"
    assert humanize_bytes(1023) == "1023 bytes"
    assert humanize_bytes(1024) == "1.000 KiB"
    assert humanize_bytes(1025) == "1.001 KiB"
    assert humanize_bytes(1024*2 - 1) == "1.999 KiB"
    assert humanize_bytes(1024*2) == "2.000 KiB"
    assert humanize_bytes(1024*2 + 1) == "2.001 KiB"

    assert humanize_bytes(1024**2 - 1) == "1023.999 KiB"
    assert humanize_bytes(1024**2) == "1.000 MiB"
    assert humanize_bytes(1024**2 + 1) == "1.000 MiB"
    assert humanize_bytes(1024**2 + 100) == "1.000 MiB"
    assert humanize_bytes(1024**2 + 1000) == "1.001 MiB"

    assert humanize_bytes(1024**3 - 1000) == "1023.999 MiB"
    assert humanize_bytes(1024**3) == "1.000 GiB"
    assert humanize_bytes(1024**3 + 1) == "1.000 GiB"
    assert humanize_bytes(1024**3 + 100) == "1.000 GiB"
    assert humanize_bytes(1024**3 + 1000) == "1.000 GiB"
    assert humanize_bytes(1024**3 + 1000000) == "1.001 GiB"

    assert humanize_bytes(1024**8) == "1.000 YiB"
    assert humanize_bytes(1024**9) == "1237940039285380274899124224 bytes"

    assert humanize_bytes(0, base=10) == "0 bytes"
    assert humanize_bytes(1, base=10) == "1 byte"
    assert humanize_bytes(60, base=10) == "60 bytes"
    assert humanize_bytes(999, base=10) == "999 bytes"
    assert humanize_bytes(1000, base=10) == "1.000 kB"
    assert humanize_bytes(1024, base=10) == "1.024 kB"
    assert humanize_bytes(1000*2 - 1, base=10) == "1.999 kB"
    assert humanize_bytes(1000*2, base=10) == "2.000 kB"
    assert humanize_bytes(1000*2 + 1, base=10) == "2.001 kB"

    assert humanize_bytes(10**6 - 1, base=10) == "999.999 kB"
    assert humanize_bytes(10**6, base=10) == "1.000 MB"
    assert humanize_bytes(10**6 + 1, base=10) == "1.000 MB"
    assert humanize_bytes(10**6 + 100, base=10) == "1.000 MB"
    assert humanize_bytes(10**6 + 1000, base=10) == "1.001 MB"
    assert humanize_bytes(10**6 + 1, base=10, precision=6) == "1.000001 MB"
    assert humanize_bytes(10**6 + 100, base=10, precision=6) == "1.000100 MB"
    assert humanize_bytes(10**6 + 1000, base=10, precision=6) == "1.001000 MB"

    assert humanize_bytes(10**9 - 1000, base=10) == "999.999 MB"
    assert humanize_bytes(10**9, base=10) == "1.000 GB"
    assert humanize_bytes(10**9 + 1, base=10) == "1.000 GB"
    assert humanize_bytes(10**9 + 100, base=10) == "1.000 GB"
    assert humanize_bytes(10**9 + 1000, base=10) == "1.000 GB"
    assert humanize_bytes(10**9 + 1000000, base=10) == "1.001 GB"
    assert humanize_bytes(10**9 + 1000000, base=10, precision=1) == "1.0 GB"

    assert humanize_bytes(10**12, base=10) == "1.000 TB"
    assert humanize_bytes(10**15, base=10) == "1.000 PB"
    assert humanize_bytes(10**18, base=10) == "1.000 EB"
    assert humanize_bytes(10**21, base=10) == "1.000 ZB"
    assert humanize_bytes(10**24, base=10) == "1.000 YB"

    assert humanize_bytes(1024**9, base=10) == "1237940039285380274899124224 bytes"

    # other bases than 2 or 10 are not supported

    assert 1073741824 == 8**10 == 1024**3

    with pytest.raises(ValueError):
        assert humanize_bytes(8**10, base=8) == "1.000 GiB"

    assert humanize_bytes(1024**3, base=2) == "1.000 GiB"
    assert humanize_bytes(1073741824, base=10) == "1.074 GB"

    assert humanize_bytes(1024**3, base='binary') == "1.000 GiB"
    assert humanize_bytes(1073741824, base='decimal') == "1.074 GB"


def test_s16():

    assert s16(0b1000_0000_0001_0001) == -32751
    assert s16(0b1000_0000_0000_0001) == -32767
    assert s16(0b1111_1111_1111_1111) == -1
    assert s16(0b0111_1111_1111_1111) == 32767


def test_s32():

    assert s32(0b1000_0000_0000_0000_0000_0000_0001_0001) == -2147483631
    assert s32(0b1000_0000_0000_0000_0000_0000_0000_0001) == -2147483647
    assert s32(0b1111_1111_1111_1111_1111_1111_1111_1111) == -1
    assert s32(0b0111_1111_1111_1111_1111_1111_1111_1111) == 2147483647
