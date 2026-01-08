"""
A CSL reference frame model which has knowledge about the CSL Setup, and the PUNA Hexapod model.

The CSL Reference Frame Model incorporates a Hexapod PUNA model which is represented by the
Reference Frames HEXUSR, HEXOBJ, HEXMEC, and HEXPLT. A number of methods are defined here that
assume these four reference frames exist in the model and behave like a proper hexapod simulator.
Those methods start with the name `hexapod_`, e.g. `hexapod_goto_zero_position()`.

"""

from typing import List

import numpy as np
from egse.coordinates.refmodel import ReferenceFrameModel

HEXUSR = "hexusr"
HEXMEC = "hexmec"
HEXOBJ = "hexobj"
HEXPLT = "hexplt"
HEXOBUSR = "hexobusr"


class CSLReferenceFrameModel(ReferenceFrameModel):
    """
    The CSL reference Frame Model is a specific reference model that adds convenience methods for manipulating the
    Hexapod PUNA which is part of the overall CSL Setup.
    """

    _DEGREES_DEFAULT = ReferenceFrameModel._DEGREES_DEFAULT

    def _create_obusr(self) -> None:
        """Creates the Object User Reference Frame if it does not exist yet."""

        if HEXOBUSR in self:
            return

        hexusr = self.get_frame(HEXUSR)
        hexobj = self.get_frame(HEXOBJ)

        transformation = hexusr.get_active_transformation_to(hexobj)

        self.add_frame(HEXOBUSR, transformation=transformation, reference=HEXUSR)
        self.add_link(HEXOBUSR, HEXOBJ)

    def hexapod_move_absolute(self, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT):
        """Moves/defines the Object Coordinate System expressed in the invariant User Coordinate System.

        The rotation centre coincides with the Object Coordinates System origin and the movements are controlled with
        translation components first (Tx, Ty, tZ) and then the rotation components (Rx, Ry, Rz).

        Args:
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        self.move_absolute_self(HEXOBUSR, translation, rotation, degrees=degrees)

    def hexapod_move_relative_object(
        self, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ):
        """Moves the object relative to its current position and orientation

        The relative movement is expressed in the object coordinate system.

        Args:
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        self.move_relative_self(HEXOBJ, translation, rotation, degrees=degrees)

    def hexapod_move_relative_user(
        self, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ) -> None:
        """Moves the object relative to its current object position and orientation.

        The relative movement is expressed in the (invariant) user coordinate system.

        Args:
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        self.move_relative_other_local(HEXOBJ, HEXUSR, translation, rotation, degrees=degrees)

    def hexapod_configure_coordinates(
        self,
        usr_trans: np.ndarray,
        usr_rot: np.ndarray,
        obj_trans: np.ndarray,
        obj_rot: np.ndarray,
    ) -> None:
        """Changes the definition of the User Coordinate System and the Object Coordinate System in the hexapod.

        Args:
            usr_trans (np.ndarray): Translation vector used to define the User Coordinate System relative to the Machine Coordinate System.
            usr_rot (np.ndarray): Rotation vector used to define the User Coordinate System relative to the Machine Coordinate System.
            obj_trans (np.ndarray): Translation vector used to define the Object Coordinate System relative to the Platform Coordinate System.
            obj_rot (np.ndarray): Rotation vector used to define the Object Coordinate System relative to the Platoform Coordinate System.
        """

        self.remove_link(HEXUSR, HEXMEC)
        self.remove_link(HEXOBJ, HEXPLT)
        self.get_frame(HEXUSR).set_translation_rotation(usr_trans, usr_rot)
        self.get_frame(HEXOBJ).set_translation_rotation(obj_trans, obj_rot)
        self.add_link(HEXUSR, HEXMEC)
        self.add_link(HEXOBJ, HEXPLT)

    def hexapod_goto_zero_position(self) -> None:
        """Instructs the hexapod to go to its zero position"""

        self.move_absolute_self(HEXPLT, translation=np.array([0, 0, 0]), rotation=np.array([0, 0, 0]))

    def hexapod_goto_retracted_position(self) -> None:
        """Instructs the hexapod to go to its retracted position."""

        self.move_absolute_self(HEXPLT, translation=np.array([0, 0, -20]), rotation=np.array([0, 0, 0]))
