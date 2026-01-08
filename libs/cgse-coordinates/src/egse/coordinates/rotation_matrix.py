"""This module contains convenience methods to define and apply rotations."""

import transforms3d as t3
import numpy as np


class RotationMatrix:
    ROTATION_CONFIG = "sxyz"

    def __init__(self, angle_1: float, angle_2: float, angle_3: float, rotation_config=ROTATION_CONFIG, active=True):
        """Initialisation of a rotation matrix.

        The `angle_1`, `angle_2` and `angle_3` parameters provide the amplitude of rotation around the axes, according
        to the order of rotations corresponding to the `rotation_config` parameter.  The latter consist of four
        characters:
            - The first character: "r" for rotating system (intrinsic rotations) or "s" for static system (extrinsic
            rotations).
            - The next characters denote the order of the rotations.

        Args:
            angle_1 (float): Rotation angle for the first axis [radians].  To which angle this corresponds (x/y/z) is
                             specified by the `rotation_config` parameter.
            angle_2 (float): Rotation angle for hte second axis [radians].  To which angle this corresponds (x/y/z) is
                             specified by the `rotation_config` parameter.
            angle_3 (float): Rotation angle for the third axis [radians].  To which angle this corresponds (x/y/z) is
                             specified by the `rotation_config` parameter.
            rotation_config (str): Order in which the rotation about the three axes are chained.
            active (bool): Indicates if the rotation is active (object rotates IN a fixed coordinate system) or passive
                           (coordinate system rotates AROUND a fixed object).  Even if two angles are zero, the match
                           between angle orders and rot_config is still critical.
        """

        rotation_matrix = t3.euler.euler2mat(angle_1, angle_2, angle_3, rotation_config)

        if active:
            # Active: The object rotates IN a fixed coordinate system
            self.rotation_matrix = rotation_matrix
        else:
            # Passive: The coordinate system rotation AROUND a fixed object
            self.rotation_matrix = rotation_matrix.T
        self.active = active

        rotation_config_array = np.array(list(rotation_config[1:]))
        angles_array = np.array([angle_1, angle_2, angle_3])

        self.angles_hash = {}
        for axis in ["x", "y", "z"]:
            self.angles_hash[axis] = angles_array[np.where(rotation_config_array == axis)[0][0]]

    def get_rotation_matrix(self) -> np.ndarray:
        """Returns the rotation matrix.

        Returns:
            Rotation matrix.
        """

        return self.rotation_matrix

    def trace(self) -> float:
        """Returns the trace of the rotation matrix.

        Returns:
            Trace of the rotation matrix.
        """

        return np.sum([self.rotation_matrix[i, i] for i in range(3)])

    def get_angle(self, axis: str) -> float:
        """Returns the angle for the given axis.

        Args:
            axis (str): Axis for which to return the angle ("x", "y", "z").

        Returns:
            Angle for the given axis.
        """

        return self.angles_hash[axis]

    def apply(self, vectors: np.ndarray) -> np.ndarray:
        """Applies the rotation matrix to the given vector.

        The result depends on the rotation system:
            - Active: The output consists of the coordinates of the input vectors after rotation.
            - Passive: The output consists of the coordinates of the input vectors after transformation to the rotated
                       coordinate system.

        Args:
            vectors (np.ndarray): Array of shape [3,N] gathering a set of vectors along its columns.

        Returns:
            Array of shape [3,N] gathering a set of vectors along its columns.
        """

        return np.dot(self.rotation_matrix, vectors)
