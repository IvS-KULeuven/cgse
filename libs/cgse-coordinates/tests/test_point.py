import pytest

from egse.coordinates.point import Point
from egse.coordinates.reference_frame import ReferenceFrame


def test_construction():
    master = ReferenceFrame.create_master()

    p1 = Point([1, 2, 3], reference_frame=master, name="P1")
    p2 = Point([1, 2, 3], reference_frame=master, name="P2")
    assert p1 is not p2
    assert p1 == p2

    p3 = Point([1, 2, 3], reference_frame=master, name="P1")
    assert p3 is not p1
    assert p3 == p1 == p2


def test_equal():
    master = ReferenceFrame.create_master()

    p1 = Point([1, 2, 3], reference_frame=master)
    p2 = Point([1, 2, 3], reference_frame=master)

    assert p1 == p1
    assert p1 != [1, 2, 3]

    assert p1.name != p2.name
    assert p1 is not p2
    assert p1 == p2

    p3 = Point([1, 3, 5], reference_frame=master)

    assert p3 is not p2
    assert p3 != p2

    r1 = ReferenceFrame.from_translation(0.0, 1.0, 2.0, reference_frame=master)
    p4 = Point([1, 3, 5], reference_frame=r1)

    assert p4 is not p3
    assert p4 != p3


def test_is_same():
    master = ReferenceFrame.create_master()

    p1 = Point([1, 2, 3], reference_frame=master)
    p2 = Point([1, 2, 3], reference_frame=master)

    assert p1.is_same(p2)

    r1 = ReferenceFrame.from_translation(1.0, 2.0, 3.0, reference_frame=master)
    p3 = Point([1, 3, 5], reference_frame=master)
    p4 = Point([0, 0, 0], reference_frame=r1)

    assert p4.is_same(p2)
    assert p2.is_same(p4)
    assert not p4.is_same(p3)
    assert not p3.is_same(p4)


def test_addition():
    master = ReferenceFrame.create_master()

    p1 = Point([1, 2, 3], reference_frame=master, name="P1")
    p2 = Point([1, 2, 3], reference_frame=master, name="P2")

    assert p1 + p2 == Point([2, 4, 6], reference_frame=master)

    r1 = ReferenceFrame.from_translation(0, 0, 3, reference_frame=master)
    p3 = Point([1, 2, 0], reference_frame=r1)

    with pytest.raises(TypeError):
        assert p1 + p3 == Point([2, 4, 6], reference_frame=master)


def test_subtraction():
    master = ReferenceFrame.create_master()

    p1 = Point([1, 2, 3], reference_frame=master, name="P1")
    p2 = Point([1, 2, 3], reference_frame=master, name="P2")

    assert p1 - p2 == Point([0, 0, 0], reference_frame=master)

    r1 = ReferenceFrame.from_translation(0, 0, 3, reference_frame=master)
    p3 = Point([1, 2, 0], reference_frame=r1)

    with pytest.raises(TypeError):
        assert p1 - p3 == Point([0, 0, 0], reference_frame=master)
