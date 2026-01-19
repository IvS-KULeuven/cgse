import ast
import logging
import re
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import numpy as np
from egse.setup import navdict

logger = logging.getLogger(__name__)


def dict_to_ref_model(model_def: Union[Dict, List]) -> navdict:
    """Creates a reference frames model from a dictionary or list of reference frame definitions.

    When a list is provided, the items in the list must be ReferenceFrames.

    The reference frame definitions are usually read from a YAML file or returned by a Setup, but can also be just
    ReferenceFrame objects.

    ReferenceFrame definitions have the following format:

    ```
    ReferenceFrame://(<definition>)
    ```
    where `<definition>` has the following elements, separated by '` | `':
    * a translation matrix
    * a rotation matrix
    * the name of the reference frame
    * the name of the reference for this reference frame
    * a dictionary of links

    Args:
        model_def (dict or list): Definition of the reference model.

    Returns:
        Dictionary representing the reference frames model.
    """

    ref_model = navdict()
    ref_links = {}

    from egse.coordinates.reference_frame import ReferenceFrame

    def create_ref_frame(name, data) -> Union[ReferenceFrame, str]:
        # This is a recursive function that creates a reference frame based on the given data.
        # * When the data is already a ReferenceFrame, it just returns data
        # * When data starts with the special string `ReferenceFrame//`, the data string is parsed
        #   and a corresponding ReferenceFrame is returned
        # * When there is no match, the data is returned unaltered.
        #
        # SIDE EFFECT:
        # * In the process, the outer ref-model and ref_links are updated.

        if isinstance(data, ReferenceFrame):
            return data

        match = re.match(r"ReferenceFrame//\((.*)\)$", data)
        if not match:
            return data

        translation, rotation, name, ref_name, links = match[1].split(" | ")

        # All links are processed later

        ref_links[name] = ast.literal_eval(links)

        if ref_name == name == "Master":
            ref_model.add(ref_name, ReferenceFrame.create_master())
            return ref_model["Master"]

        if ref_name not in ref_model:
            ref_model.add(ref_name, create_ref_frame(ref_name, model_def[ref_name]))

        ref_frame = ReferenceFrame.from_translation_rotation(
            deserialize_array(translation),
            deserialize_array(rotation),
            name=name,
            reference_frame=ref_model[ref_name],
        )

        return ref_frame

    # if the given model_def is a list, turn it into a dict

    if isinstance(model_def, list):
        model_def = {frame.name: frame for frame in model_def}

    for key, value in model_def.items():
        if key not in ref_model:
            ref_model.add(key, create_ref_frame(key, value))

    # Process all the links

    for ref_name, link_names in ref_links.items():
        ref = ref_model[ref_name]
        for link_name in link_names:
            if link_name not in ref.linked_to:
                ref.add_link(ref_model[link_name])

    return ref_model


def ref_model_to_dict(ref_model) -> navdict:
    """Creates a dictionary with reference frames definitions that define a reference model.

    Args:
        ref_model: A dictionary representing the reference frames model or a list of reference frames.

    Returns:
        Dictionary of reference frame definitions.
    """

    if isinstance(ref_model, dict):
        ref_model = ref_model.values()

    # take each key (which is a reference frame) and serialize it

    model_def = {}

    for ref in ref_model:
        translation, rotation = ref.get_translation_rotation_vectors()
        links = [ref.name for ref in ref.linked_to]
        model_def[ref.name] = (
            f"ReferenceFrame//("
            f"{serialize_array(translation, precision=6)} | "
            f"{serialize_array(rotation, precision=6)} | "
            f"{ref.name} | "
            f"{ref.reference_frame.name} | "
            f"{links})"
        )

    return navdict(model_def)


def serialize_array(arr: Union[np.ndarray, list], precision: int = 4) -> str:
    """Returns a string representation of a numpy array.

    >>> serialize_array([1,2,3])
    '[1, 2, 3]'
    >>> serialize_array([[1,2,3], [4,5,6]])
    '[[1, 2, 3], [4, 5, 6]]'
    >>> serialize_array([[1,2.2,3], [4.3,5,6]])
    '[[1.0000, 2.2000, 3.0000], [4.3000, 5.0000, 6.0000]]'
    >>> serialize_array([[1,2.2,3], [4.3,5,6]], precision=2)
    '[[1.00, 2.20, 3.00], [4.30, 5.00, 6.00]]'

    Args:
        arr: One- or-two dimensional numpy array or list.
        precision (int): number of digits of precision
    Returns:
        A string representing the input array.
    """
    if isinstance(arr, list):
        arr = np.array(arr)
    msg = np.array2string(
        arr,
        separator=", ",
        suppress_small=True,
        formatter={"float_kind": lambda x: f"{x:.{precision}f}"},
    ).replace("\n", "")
    return msg


def deserialize_array(arr_str: str) -> Optional[np.ndarray]:
    """Returns a numpy array from the given string.

    The input string is interpreted as a one or two-dimensional array, with commas or spaces separating the columns,
    and semicolons separating the rows.

    >>> deserialize_array('1,2,3')
    array([1, 2, 3])
    >>> deserialize_array('1 2 3')
    array([1, 2, 3])
    >>> deserialize_array('1,2,3;4,5,6')
    array([[1, 2, 3],
           [4, 5, 6]])
    >>> deserialize_array("[[1,2,3], [4,5,6]]")
    array([[1, 2, 3],
           [4, 5, 6]])

    Args:
        arr_str: String representation of a numpy array.

    Returns:
        One- or two-dimensional numpy array or `None` when input string cannot be parsed into a numpy array.
    """

    import re

    arr_str = re.sub(r"\],\s*\[", "];[", arr_str)
    try:
        arr = np.array(_convert_from_string(arr_str))
        return arr if ";" in arr_str else arr.flatten()
    except ValueError as exc:
        logger.error(f"Input string could not be parsed into a numpy array: {exc}")
    return None


def _convert_from_string(data: str) -> list[list]:
    # This function was copied from:
    #   https://github.com/numpy/numpy/blob/v1.19.0/numpy/matrixlib/defmatrix.py#L14
    # We include the function here because the np.matrix class is deprecated and will be removed.
    # This function is what we actually needed from np.matrix.

    # This function can be replaced with np.fromstring()

    for char in "[]":
        data = data.replace(char, "")

    rows = data.split(";")
    new_data = []
    count = 0
    for row in rows:
        trow = row.split(",")
        new_row = []
        for col in trow:
            temp = col.split()
            new_row.extend(map(ast.literal_eval, temp))
        if count == 0:
            n_cols = len(new_row)
        elif len(new_row) != n_cols:
            raise ValueError("Rows not the same size.")
        count += 1
        new_data.append(new_row)

    return new_data
