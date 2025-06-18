import pytest

from egse.coordinates.point import Point
from egse.coordinates.referenceFrame import ReferenceFrame


def test_construction():
    master = ReferenceFrame.createMaster()

    p1 = Point([1, 2, 3], ref=master, name="P1")
    p2 = Point([1, 2, 3], ref=master, name="P2")
    assert p1 is not p2
    assert p1 == p2

    p3 = Point([1, 2, 3], ref=master, name="P1")
    assert p3 is not p1
    assert p3 == p1 == p2


def test_equal():
    master = ReferenceFrame.createMaster()

    p1 = Point([1, 2, 3], ref=master)
    p2 = Point([1, 2, 3], ref=master)

    assert p1 == p1
    assert p1 != [1, 2, 3]

    assert p1.name != p2.name
    assert p1 is not p2
    assert p1 == p2

    p3 = Point([1, 3, 5], ref=master)

    assert p3 is not p2
    assert p3 != p2

    r1 = ReferenceFrame.fromTranslation(0.0, 1.0, 2.0, ref=master)
    p4 = Point([1, 3, 5], ref=r1)

    assert p4 is not p3
    assert p4 != p3


def test_isSame():
    master = ReferenceFrame.createMaster()

    p1 = Point([1, 2, 3], ref=master)
    p2 = Point([1, 2, 3], ref=master)

    assert p1.isSame(p2)

    r1 = ReferenceFrame.fromTranslation(1.0, 2.0, 3.0, ref=master)
    p3 = Point([1, 3, 5], ref=master)
    p4 = Point([0, 0, 0], ref=r1)

    assert p4.isSame(p2)
    assert p2.isSame(p4)
    assert not p4.isSame(p3)
    assert not p3.isSame(p4)


def test_addition():
    master = ReferenceFrame.createMaster()

    p1 = Point([1, 2, 3], ref=master, name="P1")
    p2 = Point([1, 2, 3], ref=master, name="P2")

    assert p1 + p2 == Point([2, 4, 6], ref=master)

    r1 = ReferenceFrame.fromTranslation(0, 0, 3, ref=master)
    p3 = Point([1, 2, 0], ref=r1)

    with pytest.raises(TypeError):
        assert p1 + p3 == Point([2, 4, 6], ref=master)


def test_subtraction():
    master = ReferenceFrame.createMaster()

    p1 = Point([1, 2, 3], ref=master, name="P1")
    p2 = Point([1, 2, 3], ref=master, name="P2")

    assert p1 - p2 == Point([0, 0, 0], ref=master)

    r1 = ReferenceFrame.fromTranslation(0, 0, 3, ref=master)
    p3 = Point([1, 2, 0], ref=r1)

    with pytest.raises(TypeError):
        assert p1 - p3 == Point([0, 0, 0], ref=master)
