import numpy as np

from egse.coordinates import dict_to_ref_model
from egse.coordinates import deserialize_array
from egse.coordinates import serialize_array
from egse.coordinates import ref_model_to_dict
from egse.coordinates.reference_frame import ReferenceFrame


def test_serialization_of_numpy_arrays():
    assert serialize_array([1, 2, 3]) == "[1, 2, 3]"
    assert serialize_array(np.array([1, 2, 3])) == "[1, 2, 3]"
    assert serialize_array([[1], [2], [3]]) == "[[1], [2], [3]]"
    assert serialize_array([[1, 2.3, 4], [5, 6.2, 7]]) == "[[1.0000, 2.3000, 4.0000], [5.0000, 6.2000, 7.0000]]"


def test_deserialization_of_numpy_array():
    assert (deserialize_array("[1, 2, 3]") == np.array([1, 2, 3])).all()
    assert (deserialize_array("[[1], [2], [3]]") == np.array([[1], [2], [3]])).all()


def test_serialization_of_reference_model():
    rot_config = "sxyz"

    master = ReferenceFrame.create_master()

    a_ref = ReferenceFrame(
        transformation=np.identity(4), reference_frame=master, name="a_ref", rotation_config=rot_config
    )
    a_ref.add_link(master)

    b_ref = ReferenceFrame(
        transformation=np.identity(4), reference_frame=a_ref, name="b_ref", rotation_config=rot_config
    )

    c_ref = ReferenceFrame.from_translation_rotation(
        [-2, -2, -2], [-3, -4, -5], rotation_config=rot_config, reference_frame=b_ref, name="c_ref"
    )
    c_ref.add_link(b_ref)

    model_list = [a_ref, b_ref, c_ref, master]

    model_def = ref_model_to_dict(model_list)

    print()
    print(model_def.pretty_str())

    ref_model = dict_to_ref_model(model_def)

    assert "a_ref" in ref_model.keys()
    assert ref_model.a_ref.name == "a_ref"

    assert "b_ref" in ref_model.keys()
    assert "c_ref" in ref_model.keys()
    assert "Master" in ref_model.keys()

    print()
    print(ref_model.pretty_str())
