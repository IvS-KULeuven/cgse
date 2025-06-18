import time

from egse.coordinates.point import Point
from egse.coordinates.pyplot import plot_points
from egse.coordinates.pyplot import plot_reference_frame
from egse.coordinates.referenceFrame import ReferenceFrame


def test_master_plot_reference_frame():
    try:
        _ = plot_reference_frame(ReferenceFrame.createMaster())
        time.sleep(5)
    except NotImplementedError:
        pass


def test_master_plot_points():
    master = ReferenceFrame.createMaster()

    p1 = Point([1, 2, 3], ref=master, name="P1")
    p2 = Point([1, 2, 3], ref=master, name="P2")

    try:
        _ = plot_points([p1, p2], master)
        time.sleep(5)
    except NotImplementedError:
        pass
