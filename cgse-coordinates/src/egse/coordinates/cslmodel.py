"""
A CSL reference frame model which has knowledge about the CSL Setup, and the PUNA Hexapod model.

The CSL Reference Frame Model incorporates a Hexapod PUNA model which is represented by the
Reference Frames HEXUSR, HEXOBJ, HEXMEC, and HEXPLT. A number of methods are defined here that
assume these four reference frames exist in the model and behave like a proper hexapod simulator.
Those methods start with the name `hexapod_`, e.g. `hexapod_goto_zero_position()`.

"""
from typing import List

from egse.coordinates.refmodel import ReferenceFrameModel

HEXUSR = "hexusr"
HEXMEC = "hexmec"
HEXOBJ = "hexobj"
HEXPLT = "hexplt"
HEXOBUSR = "hexobusr"


class CSLReferenceFrameModel(ReferenceFrameModel):
    """
    The CSL Reference Frame Model is a specific reference model that adds convenience methods
    for manipulating the Hexapod PUNA which is part of the overall CSH Setup.
    """

    _DEGREES_DEFAULT = ReferenceFrameModel._DEGREES_DEFAULT

    def _create_obusr(self):

        if HEXOBUSR in self:
            return

        hexusr = self.get_frame(HEXUSR)
        hexobj = self.get_frame(HEXOBJ)

        transformation = hexusr.getActiveTransformationTo(hexobj)

        self.add_frame(HEXOBUSR, transformation=transformation, ref=HEXUSR)
        self.add_link(HEXOBUSR, HEXOBJ)

    def hexapod_move_absolute(self, translation, rotation, degrees=_DEGREES_DEFAULT):
        """
        Move/define the Object Coordinate System position and orientation expressed
        in the invariant user coordinate system.

        The rotation centre coincides with the Object Coordinates System origin and
        the movements are controlled with translation components at first (Tx, Ty, tZ)
        and then the rotation components (Rx, Ry, Rz).

        Args:
            translation: the translation vector
            rotation: the rotation vector
            degrees: use degrees [default: True]
        """

        self.move_absolute_self(HEXOBUSR, translation, rotation, degrees=degrees)

    def hexapod_move_relative_object(self, translation, rotation, degrees=_DEGREES_DEFAULT):
        """
        Hexapod Command:
            Move the object relative to its current object position and orientation.

        The relative movement is expressed in the object coordinate system.

        Args:
            translation: the translation vector
            rotation: the rotation vector
            degrees: use degrees [default: True]
        """

        self.move_relative_self(HEXOBJ, translation, rotation, degrees=degrees)

    def hexapod_move_relative_user(self, translation, rotation, degrees=_DEGREES_DEFAULT):
        """
        Hexapod Command:
            Move the object relative to its current object position and orientation.

        The relative movement is expressed in the (invariant) user coordinate system.

        Args:
            translation: the translation vector
            rotation: the rotation vector
            degrees: use degrees [default: True]
        """

        self.move_relative_other_local(HEXOBJ, HEXUSR, translation, rotation, degrees=degrees)

    def hexapod_configure_coordinates(
        self,
        usr_trans: List[float],
        usr_rot: List[float],
        obj_trans: List[float],
        obj_rot: List[float],
    ):
        """
        Change the definition of the User Coordinate System and the Object Coordinate System in
        the Hexapod.

        The parameters tx_u, ty_u, tz_u, rx_u, ry_u, rz_u are used to define the user coordinate
        system
        relative to the Machine Coordinate System and the parameters tx_o, ty_o, tz_o, rx_o,
        ry_o, rz_o
        are used to define the Object Coordinate System relative to the Platform Coordinate System.

        """

        self.remove_link(HEXUSR, HEXMEC)
        self.remove_link(HEXOBJ, HEXPLT)
        self.get_frame(HEXUSR).setTranslationRotation(usr_trans, usr_rot)
        self.get_frame(HEXOBJ).setTranslationRotation(obj_trans, obj_rot)
        self.add_link(HEXUSR, HEXMEC)
        self.add_link(HEXOBJ, HEXPLT)

    def hexapod_goto_zero_position(self):
        """
        Ask the hexapod to go to the zero position.
        """

        self.move_absolute_self(HEXPLT, translation=[0, 0, 0], rotation=[0, 0, 0])

    def hexapod_goto_retracted_position(self):
        """
        Ask the hexapod to go to its retracted position.
        """

        self.move_absolute_self(HEXPLT, translation=[0, 0, -20], rotation=[0, 0, 0])
