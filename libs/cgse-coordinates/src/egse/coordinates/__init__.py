import ast
import logging
import re
from math import atan
from math import atan2
from math import cos
from math import degrees
from math import pow
from math import radians
from math import sin
from math import sqrt
from math import tan
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

import numpy as np
from numpy.polynomial import Polynomial

from egse.coordinates.referenceFrame import ReferenceFrame
from egse.settings import Settings
from egse.state import GlobalState
from egse.setup import NavigableDict

logger = logging.getLogger(__name__)

FOV_SETTINGS = Settings.load("Field-Of-View")
CCD_SETTINGS = Settings.load("CCD")


def undistorted_to_distorted_focal_plane_coordinates(
    x_undistorted, y_undistorted, distortion_coefficients, focal_length
):
    """
    Conversion from undistorted to distorted focal-plane coordinates.  The distortion is a
    radial effect and is defined as the difference in radial distance to the optical axis
    between the distorted and undistorted coordinates, and can be expressed in terms of the
    undistorted radial distance r as follows:

        Δr = r * [(k1 * r**2) + (k2 * r**4) + (k3 * r**6)],

    where the distortion and r are expressed in normalised focal-plane coordinates (i.e. divided
    by the focal length, expressed in the same unit), and (k1, k2, k3) are the distortion
    coefficients.

    Args:
        x_undistorted: Undistorted x-coordinate on the focal plane [mm].
        y_undistorted: Undistorted y-coordinate on the focal plane [mm].
        distortion_coefficients: List of polynomial coefficients for the field distortion.
        focal_length: Focal length [mm].
    Returns:
        x_distorted: Distorted x-coordinate on the focal plane [mm].
        y_distorted: Distorted y-coordinate on the focal plane [mm].
    """

    # Distortion coefficients -> (0, 0, 0, k1, 0, k2, 0, k3)

    coefficients = [
        0,
        0,
        0,
        distortion_coefficients[0],
        0,
        distortion_coefficients[1],
        0,
        distortion_coefficients[2],
    ]
    distortion_polynomial = Polynomial(coefficients)

    # Position on the focal plane:
    #   - field angle [radians]
    #   - radial distance from the optical axis [normalised pixels]

    angle = atan2(y_undistorted, x_undistorted)
    distance_undistorted = sqrt(pow(x_undistorted, 2) + pow(y_undistorted, 2)) / focal_length

    # Distortion [mm]
    # Source moves away from the optical axis (radially)

    distortion = distortion_polynomial(distance_undistorted) * focal_length

    # The field angle remains the same

    x_distorted = x_undistorted + cos(angle) * distortion
    y_distorted = y_undistorted + sin(angle) * distortion

    return x_distorted, y_distorted


def distorted_to_undistorted_focal_plane_coordinates(
    x_distorted, y_distorted, inverse_distortion_coefficients, focal_length
):
    """
    Conversion from distorted to undistorted focal-plane coordinates.  The inverse distortion is a
    radial effect and is defined as the difference in radial distance to the optical axis
    between the distorted and undistorted coordinates, and can be expressed in terms of the
    undistorted radial distance r as follows:

        Δr = r * [(k1 * r**2) + (k2 * r**4) + (k3 * r**6)],

    where the inverse distortion and r are expressed in normalised focal-plane coordinates (i.e. divided
    by the focal length, expressed in the same unit), and (k1, k2, k3) are the inverse distortion
    coefficients.

    Args:
        x_distorted: Distorted x-coordinate on the focal plane [mm].
        y_distorted: Distorted y-coordinate on the focal plane [mm].
        inverse_distortion_coefficients: List of polynomial coefficients for the inverse field distortion.
        focal_length: Focal length [mm].
    Returns:
        x_undistorted: Undistorted x-coordinate on the focal plane [mm].
        y_undistorted: Undistorted y-coordinate on the focal plane [mm].
    """

    # Inverse distortion coefficients -> (0, 0, 0, k1, 0, k2, 0, k3)

    coefficients = [
        0,
        0,
        0,
        inverse_distortion_coefficients[0],
        0,
        inverse_distortion_coefficients[1],
        0,
        inverse_distortion_coefficients[2],
    ]
    inverse_distortion_polynomial = Polynomial(coefficients)

    # Position on the focal plane:
    #   - field angle [radians]
    #   - radial distance from the optical axis [normalised pixels]

    angle = atan2(y_distorted, x_distorted)
    distance_distorted = sqrt(pow(x_distorted, 2) + pow(y_distorted, 2)) / focal_length

    # Inverse distortion [mm]
    # Source moves towards the optical axis (radially) -> negative!

    inverse_distortion = inverse_distortion_polynomial(distance_distorted) * focal_length

    # The field angle remains the same

    x_undistorted = x_distorted + cos(angle) * inverse_distortion
    y_undistorted = y_distorted + sin(angle) * inverse_distortion

    return x_undistorted, y_undistorted


def focal_plane_to_ccd_coordinates(x_fp, y_fp):
    """
    Conversion from focal-plane to pixel coordinates on the appropriate CCD.

    Args:
        x_fp: Focal-plane x-coordinate [mm].
        y_fp: Focal-plane y-coordinate [mm].
    Returns:
        Pixel coordinates (row, column) and the corresponding CCD.  If the given
        focal-plane coordinates do not fall on any CCD, (None, None, None) is
        returned.
    """
    setup = GlobalState.setup

    if setup is not None:
        num_rows = setup.camera.ccd.num_rows
        num_cols = setup.camera.ccd.num_column
    else:
        num_rows = CCD_SETTINGS.NUM_ROWS
        num_cols = CCD_SETTINGS.NUM_COLUMNS

    for ccd_code in range(1, 5):

        (row, column) = __focal_plane_to_ccd_coordinates__(x_fp, y_fp, ccd_code)

        if (row < 0) or (column < 0):
            continue

        if (row >= num_rows) or (column >= num_cols):
                continue

        return row, column, ccd_code

    return None, None, None


def __focal_plane_to_ccd_coordinates__(x_fp, y_fp, ccd_code):
    """
    Conversion from focal-plane coordinates to pixel coordinates on the given CCD.

    Args:
        x_fp: Focal-plane x-coordinate [mm].
        y_fp: Focal-plane y-coordinate [mm].
        ccd_code: Code of the CCD for which to calculate the pixel coordinates [1, 2, 3, 4].
    Returns:
        Pixel coordinates (row, column) on the given CCD.
    """

    setup = GlobalState.setup

    if setup is not None:
        ccd_orientation = setup.camera.ccd.orientation[int(ccd_code) - 1]
        pixel_size      = setup.camera.ccd.pixel_size / 1000.0  # [mm]
        ccd_origin_x    = GlobalState.setup.camera.ccd.origin_offset_x[int(ccd_code) - 1]
        ccd_origin_y    = GlobalState.setup.camera.ccd.origin_offset_y[int(ccd_code) - 1]
    else:
        ccd_orientation = CCD_SETTINGS.ORIENTATION[int(ccd_code) - 1]
        pixel_size      = CCD_SETTINGS.PIXEL_SIZE / 1000  # Pixel size [mm]
        ccd_origin_x    = CCD_SETTINGS.ZEROPOINT[0]
        ccd_origin_y    = CCD_SETTINGS.ZEROPOINT[1]

    ccd_angle = radians(ccd_orientation)

    # CCD coordinates [mm]

    row    = ccd_origin_y - x_fp * sin(ccd_angle) + y_fp * cos(ccd_angle)
    column = ccd_origin_x + x_fp * cos(ccd_angle) + y_fp * sin(ccd_angle)

    row /= pixel_size
    column /= pixel_size

    return row, column


def focal_plane_coordinates_to_angles(x_fp, y_fp):
    """
    Conversion from focal-plane coordinates to the gnomonic distance from the optical axis and
    the in-field angle.

    Args:
        x_fp: Focal-plane x-coordinate [mm].
        y_fp: Focal-plane y-coordinate [mm].
    Returns:
        Gnomonic distance from the optical axis and in-field angle [degrees].
    """

    setup = GlobalState.setup

    if setup is not None:
        focal_length_mm = GlobalState.setup.camera.fov.focal_length_mm
    else:
        focal_length_mm = FOV_SETTINGS.FOCAL_LENGTH

    theta = degrees(atan(sqrt(pow(x_fp, 2) + pow(y_fp, 2)) / focal_length_mm))
    phi = degrees(atan2(y_fp, x_fp))

    return theta, phi


def ccd_to_focal_plane_coordinates(row, column, ccd_code):
    """
    Conversion from pixel-coordinates on the given CCD to focal-plane coordinates.

    Args:
        row: Row coordinate [pixels].
        column: Column coordinate [pixels].
        ccd_code: Code of the CCD for which the pixel coordinates are given.
    Returns:
        Focal-plane coordinates (x, y) [mm].
    """

    setup = GlobalState.setup

    if setup is not None:
        ccd_orientation = setup.camera.ccd.orientation[int(ccd_code) - 1]
        pixel_size_mm   = setup.camera.ccd.pixel_size / 1000.0  # [mm]
        ccd_origin_x    = GlobalState.setup.camera.ccd.origin_offset_x[int(ccd_code) - 1]
        ccd_origin_y    = GlobalState.setup.camera.ccd.origin_offset_y[int(ccd_code) - 1]
    else:
        ccd_orientation = CCD_SETTINGS.ORIENTATION[int(ccd_code) - 1]
        pixel_size_mm   = CCD_SETTINGS.PIXEL_SIZE / 1000  # Pixel size [mm]
        ccd_origin_x    = CCD_SETTINGS.ZEROPOINT[0]
        ccd_origin_y    = CCD_SETTINGS.ZEROPOINT[1]

    # Convert the pixel coordinates into [mm] coordinates

    row_mm = row * pixel_size_mm
    column_mm = column * pixel_size_mm

    # Convert the CCD coordinates into FP coordinates [mm]

    ccd_angle = radians(ccd_orientation)

    x_fp = (column_mm - ccd_origin_x) * cos(ccd_angle) - (row_mm - ccd_origin_y) * sin(ccd_angle)
    y_fp = (column_mm - ccd_origin_x) * sin(ccd_angle) + (row_mm - ccd_origin_y) * cos(ccd_angle)

    # That's it

    return x_fp, y_fp

def angles_to_focal_plane_coordinates(theta, phi):
    """
    Conversion from the gnomonic distance from the optical axis and
    the in-field angle to focal-plane coordinates.

    Args:
        theta: Gnomonic distance from the optical axis [degrees].
        phi: In-field angle [degrees].
    Returns:
        Focal-plane coordinates (x, y) [mm].
    """

    setup = GlobalState.setup

    if setup is not None:
        focal_length_mm = GlobalState.setup.camera.fov.focal_length_mm
    else:
        focal_length_mm = FOV_SETTINGS.FOCAL_LENGTH

    distance = focal_length_mm * tan(radians(theta))  # [mm]

    phi_radians = radians(phi)

    x_fp = distance * cos(phi_radians)
    y_fp = distance * sin(phi_radians)

    return x_fp, y_fp


def dict_to_ref_model(model_def: Union[Dict, List]) -> NavigableDict:
    """
    Creates a reference frames model from a dictionary or list of reference frame definitions.

    When a list is provided, the items in the list must be ReferenceFrames.

    The reference frame definitions are usually read from a YAML file or returned by a Setup,
    but can also be just ReferenceFrame objects.

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
        model_def (dict or list): the definition of the reference model

    Returns:
        A dictionary representing the reference frames model.
    """

    ref_model = NavigableDict({})
    ref_links = {}

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

        # all links are processed later..

        ref_links[name] = ast.literal_eval(links)

        if ref_name == name == "Master":
            ref_model.add(ref_name, ReferenceFrame.createMaster())
            return ref_model["Master"]

        if ref_name not in ref_model:
            ref_model.add(ref_name, create_ref_frame(ref_name, model_def[ref_name]))

        ref_frame = ReferenceFrame.fromTranslationRotation(
            deserialize_array(translation),
            deserialize_array(rotation),
            name=name,
            ref=ref_model[ref_name],
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
            if link_name not in ref.linkedTo:
                ref.addLink(ref_model[link_name])

    return ref_model


def ref_model_to_dict(ref_model) -> NavigableDict:
    """Creates a dictionary with reference frames definitions that define a reference model.

    Args:
        ref_model: A dictionary representing the reference frames model or a list of reference
            frames.
    Returns:
        A dictionary of reference frame definitions.
    """

    if isinstance(ref_model, dict):
        ref_model = ref_model.values()

    # take each key (which is a reference frame) and serialize it

    model_def = {}

    for ref in ref_model:
        translation, rotation = ref.getTranslationRotationVectors()
        links = [ref.name for ref in ref.linkedTo]
        model_def[ref.name] = (
            f"ReferenceFrame//("
            f"{serialize_array(translation, precision=6)} | "
            f"{serialize_array(rotation, precision=6)} | "
            f"{ref.name} | "
            f"{ref.ref.name} | "
            f"{links})"
        )

    return NavigableDict(model_def)


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
        arr: a one or two dimensional numpy array or list.
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

    The input string is interpreted as a one or two-dimensional array, with commas or spaces
    separating the columns, and semi-colons separating the rows.

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
        arr_str: string representation of a numpy array
    Returns:
        A one or two-dimensional numpy array or `None` when input string cannot be parsed into a
        numpy array.
    """

    import re

    arr_str = re.sub(r"\],\s*\[", "];[", arr_str)
    try:
        arr = np.array(_convert_from_string(arr_str))
        return arr if ";" in arr_str else arr.flatten()
    except ValueError as exc:
        logger.error(f"Input string could not be parsed into a numpy array: {exc}")
    return None


def _convert_from_string(data):

    # This function was copied from:
    #   https://github.com/numpy/numpy/blob/v1.19.0/numpy/matrixlib/defmatrix.py#L14
    # We include the function here because the np.matrix class is deprecated and will be removed.
    # This function is what we actually needed from np.matrix.

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
