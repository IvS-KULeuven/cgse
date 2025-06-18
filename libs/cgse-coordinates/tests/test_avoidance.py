import textwrap

import pytest

from egse.coordinates import ReferenceFrame
from egse.coordinates.avoidance import is_avoidance_ok
from egse.setup import Setup


def test_is_avoidance_with_faulty_arguments():
    with pytest.raises(TypeError):
        is_avoidance_ok()

    with pytest.raises(AttributeError):
        is_avoidance_ok("hexusr", "hexobj", verbose=True)


def test_is_avoidance_with_master_ref_frames():
    print()  # Print a blank line to start fresh with printed output

    master_ref_frame = ReferenceFrame.createMaster()

    setup = Setup.from_yaml_string(
        textwrap.dedent(
            """
        camera:
            fpa:
                avoidance:
                    clearance_xy: 2.000000E+00
                    clearance_z: 2.000000E+00
                    vertices_nb: 60
                    vertices_radius: 1.000000E+02
        """
        )
    )

    # So, why would the avoidance check fail here?
    #
    # * We provide a scaled-down setup with only those values used by the tested function
    # * Horizontal avoidance should be OK since both reference frames are the same which is within
    #   clearance_xy obviously.
    # * Vertical avoidance should NOT be OK since again both reference frames are identical and therefore
    #   we enter the avoidance in clearance_z

    assert not is_avoidance_ok(master_ref_frame, master_ref_frame, setup=setup, verbose=2)
