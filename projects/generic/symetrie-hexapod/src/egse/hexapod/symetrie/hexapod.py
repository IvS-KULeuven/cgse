import math

import numpy as np

from egse.bits import set_bit
from egse.coordinates import ReferenceFrame
from egse.hexapod.symetrie import logger
from egse.hexapod.symetrie.pmac import decode_Q36


class HexapodSimulator:
    """
    HexapodSimulator simulates the Symétrie Hexapod. The class is heavily based on the
    ReferenceFrames in the `egse.coordinates` package.

    The simulator implements the same methods as the HexapodController class which acts on the
    real hardware controller in either simulation mode or with a real Hexapod PUNA connected.

    Therefore, the HexapodSimulator can be used instead of the Hexapod class in test harnesses
    and when the hardware is not available.

    This class simulates all the movements and status of the Hexapod.
    """

    def __init__(self):
        identity = np.identity(4)

        # Rotation around static axis, and around x, y and z in that order
        self.rot_config = "sxyz"

        # Configure the Master Reference Frame
        self.cs_master = ReferenceFrame.createMaster()

        # Configure the Machine Coordinate System, i.e. cs_mec [ref:cs_master]
        self.cs_machine = ReferenceFrame(
            transformation=identity,
            ref=self.cs_master,
            name="Machine[Master]",
            rot_config=self.rot_config,
        )

        # Configure the Platform Coordinate System, i.e. cs_platform [ref:cs_machine]
        # default after homing: PLATFORM = MACHINE

        self.cs_platform = ReferenceFrame(
            transformation=identity,
            ref=self.cs_machine,
            name="Platform[Machine]",
            rot_config=self.rot_config,
        )

        # Configure the User Coordinate System, i.e. cs_user [ref:cs_machine]
        self.cs_user = ReferenceFrame(
            transformation=identity,
            ref=self.cs_machine,
            name="User[Machine]",
            rot_config=self.rot_config,
        )

        # Configure the Object Coordinate System, i.e. cs_object [ref:cs_platform]
        self.cs_object = ReferenceFrame(
            transformation=identity,
            ref=self.cs_platform,
            name="Object[Platform]",
            rot_config=self.rot_config,
        )

        # We use a CS called cs_object_in_user, i.e. Object as defined in the User CS,
        # and we define this
        # from the transformation user -> object.

        tf_user_to_object = self.cs_user.getActiveTransformationTo(self.cs_object)
        self.cs_object_in_user = ReferenceFrame(
            tf_user_to_object, rot_config=self.rot_config, ref=self.cs_user, name="Object[User]"
        )

        # Define the invariant links within the system, i.e. some systems are bound with an
        # invariant transformation
        # matrix and those links shall be preserved throughout the movement within the system.

        # We link this cs_object_in_user to cs_object with the identity transformation,
        # which connects them together

        self.cs_object_in_user.addLink(self.cs_object, transformation=identity)

        # The User Coordinate System is linked to the Machine Coordinate System

        self.cs_machine.addLink(self.cs_user, transformation=self.cs_user.transformation)

        # The Object Coordinate System is linked to the Platform Coordinate System

        self.cs_platform.addLink(self.cs_object, transformation=self.cs_object.transformation)

        # Keep a record if the homing() command has been executed.

        self.homing_done = False
        self.control_loop = False
        self._virtual_homing = False
        self._virtual_homing_position = None

        # Just keep the speed settings, no used in movement currently

        self._speed = [1.0, 1.0, 0.01, 0.001, 4.0, 2.0]

        # Print out some debugging information

        logger.debug(f"Linked to cs_object_in_user  {[i.name for i in self.cs_object_in_user.linkedTo]}")
        logger.debug(f"Linked to cs_object          {[i.name for i in self.cs_object.linkedTo]}")
        logger.debug(f"Linked to cs_platform        {[i.name for i in self.cs_platform.linkedTo]}")
        logger.debug(f"Linked to cs_machine         {[i.name for i in self.cs_machine.linkedTo or {}]}")

    def is_simulator(self):
        return True

    def connect(self):
        pass

    def reconnect(self):
        pass

    def disconnect(self):
        # TODO:
        #   Should I keep state in this class to check if it has been disconnected?
        #
        # TODO:
        #   What happens when I re-connect to this Simulator? Shall it be in Homing position or
        #   do I have to keep state via a persistency mechanism?
        pass

    def is_connected(self):
        return True

    def reset(self, wait=True, verbose=False):
        # TODO:
        #   Find out what exactly a reset() should be doing. Does it bring back the Hexapod
        #   in it's original state, loosing all definitions of coordinate systems? Or does it
        #   do a clearError() and a homing()?
        pass

    def homing(self):
        self.goto_zero_position()
        self.homing_done = True
        self._virtual_homing = False
        self._virtual_homing_position = None
        return 0

    def is_homing_done(self):
        return self.homing_done

    def set_virtual_homing(self, tx, ty, tz, rx, ry, rz):
        self._virtual_homing_position = [tx, ty, tz, rx, ry, rz]
        self._virtual_homing = True
        return 0

    def stop(self):
        pass

    def clear_error(self):
        return 0

    def activate_control_loop(self):
        self.control_loop = True
        return self.control_loop

    def deactivate_control_loop(self):
        self.control_loop = False
        return self.control_loop

    def configure_coordinates_systems(self, tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o):
        identity = np.identity(4)

        # Redefine the User Coordinate System

        translation = np.array([tx_u, ty_u, tz_u])
        rotation = np.array([rx_u, ry_u, rz_u])
        degrees = True

        # Remove the old links between user and machine CS, and between Object in User and Object CS

        self.cs_machine.removeLink(self.cs_user)
        self.cs_object_in_user.removeLink(self.cs_object)

        # Redefine the User Coordinate System

        self.cs_user = ReferenceFrame.fromTranslationRotation(
            translation,
            rotation,
            rot_config=self.rot_config,
            ref=self.cs_machine,
            name="User[Machine]",
            degrees=degrees,
        )

        # Redefine the Object in User Coordinate System

        tf_user_to_object = self.cs_user.getActiveTransformationTo(self.cs_object)
        self.cs_object_in_user = ReferenceFrame(
            tf_user_to_object, rot_config=self.rot_config, ref=self.cs_user, name="Object[User]"
        )

        # Define the invariant links within the system, i.e. some systems are bound with an
        # invariant transformation
        # matrix and those links shall be preserved throughout the movement within the system.

        # User and Machine CS are invariant, reset the transformation. User in Object is
        # identical to Object

        self.cs_machine.addLink(self.cs_user, transformation=self.cs_user.transformation)
        self.cs_object_in_user.addLink(self.cs_object, transformation=identity)

        # Redefine the Object Coordinates System

        translation = np.array([tx_o, ty_o, tz_o])
        rotation = np.array([rx_o, ry_o, rz_o])
        degrees = True

        # Remove the old links between user and machine CS, and between Object in User and Object CS

        self.cs_platform.removeLink(self.cs_object)
        self.cs_object_in_user.removeLink(self.cs_object)

        self.cs_object = ReferenceFrame.fromTranslationRotation(
            translation,
            rotation,
            rot_config=self.rot_config,
            ref=self.cs_platform,
            name="Object[Platform]",
            degrees=degrees,
        )

        # Redefine the Object in User Coordinate System

        tf_user_to_object = self.cs_user.getActiveTransformationTo(self.cs_object)
        self.cs_object_in_user = ReferenceFrame(
            tf_user_to_object, rot_config=self.rot_config, ref=self.cs_user, name="Object[User]"
        )

        # Object CS and Platform CS are invariant, reset the transformation. User in Object is
        # identical to Object

        self.cs_platform.addLink(self.cs_object, transformation=self.cs_object.transformation)
        self.cs_object_in_user.addLink(self.cs_object, transformation=identity)

        return 0

    def get_coordinates_systems(self):
        degrees = True

        t_user, r_user = self.cs_user.getTranslationRotationVectors(degrees=degrees)
        t_object, r_object = self.cs_object.getTranslationRotationVectors(degrees=degrees)

        return list(np.concatenate((t_user, r_user, t_object, r_object)))

    def move_absolute(self, tx, ty, tz, rx, ry, rz):
        # FIXME:
        #  to really simulate the behavior of the Hexapod, this method should implement limit
        #  checking and other condition or error checking, e.g. argument matching, etc.

        logger.debug(f"moveAbsolute with {tx}, {ty}, {tz}, {rx}, {ry}, {rz}")

        translation = np.array([tx, ty, tz])
        rotation = np.array([rx, ry, rz])

        # We set a new transformation for cs_object_in_user which will update our model,
        # because cs_object and cs_object_in_user are linked.

        self.cs_object_in_user.setTranslationRotation(
            translation,
            rotation,
            rot_config=self.rot_config,
            active=True,
            degrees=True,
            preserveLinks=True,
        )

        return 0

    def move_relative_object(self, tx, ty, tz, rx, ry, rz):
        tr_rel = np.array([tx, ty, tz])
        rot_rel = np.array([rx, ry, rz])

        self.cs_object.applyTranslationRotation(
            tr_rel,
            rot_rel,
            rot_config=self.rot_config,
            active=True,
            degrees=True,
            preserveLinks=True,
        )

    def move_relative_user(self, tx, ty, tz, rx, ry, rz):
        # The Symétrie Hexapod definition of moveRelativeUser
        #
        # - Translation and rotations are expressed in USER reference frame
        #
        # - Actually,
        #     - the translations happen parallel to the USER reference frame
        #     - the rotations are applied after the translations, on the OBJ ReferenceFrame
        #
        # To achieve this,
        #
        #     * OBUSR is "de-rotated", to become parallel to USR
        #     * the requested translation is applied
        #     * OBUSR is "re-rotated" to its original orientation
        #     * the requested rotation is applied

        # Derotation of cs_object --> cs_user

        derotation = self.cs_object.getActiveTransformationTo(self.cs_user)
        derotation[:3, 3] = [0, 0, 0]

        # Reverse rotation

        rerotation = derotation.T

        # Requested translation matrix

        translation = np.identity(4)
        translation[:3, 3] = [tx, ty, tz]

        # Requested rotation matrix

        import egse.coordinates.transform3d_addon as t3add

        rotation = t3add.translationRotationToTransformation([0, 0, 0], [rx, ry, rz], rot_config=self.rot_config)

        transformation = derotation @ translation @ rerotation @ rotation

        # Adapt our model

        self.cs_object.applyTransformation(transformation)

    def check_absolute_movement(self, tx, ty, tz, rx, ry, rz):
        rc = 0
        rc_dict = {}
        if not -30.0 <= tx <= 30.0:
            rc += 1
            rc_dict.update({1: "Tx should be in range ±30.0 mm"})
        if not -30.0 <= ty <= 30.0:
            rc += 1
            rc_dict.update({2: "Ty should be in range ±30.0 mm"})
        if not -20.0 <= tz <= 20.0:
            rc += 1
            rc_dict.update({3: "Tz should be in range ±20.0 mm"})
        if not -11.0 <= rx <= 11.0:
            rc += 1
            rc_dict.update({4: "Rx should be in range ±11.0 mm"})
        if not -11.0 <= ry <= 11.0:
            rc += 1
            rc_dict.update({5: "Ry should be in range ±11.0 mm"})
        if not -20.0 <= rz <= 20.0:
            rc += 1
            rc_dict.update({6: "Rz should be in range ±20.0 mm"})
        return rc, rc_dict

    def check_relative_object_movement(self, tx, ty, tz, rx, ry, rz):
        return 0, {}

    def check_relative_user_movement(self, tx, ty, tz, rx, ry, rz):
        return 0, {}

    def get_user_positions(self):
        t, r = self.cs_user.getActiveTranslationRotationVectorsTo(self.cs_object_in_user)

        pos = list(np.concatenate((t, r)))

        return pos

    def get_machine_positions(self):
        t, r = self.cs_platform.getTranslationRotationVectors()
        t, r = self.cs_machine.getActiveTranslationRotationVectorsTo(self.cs_platform)

        pos = list(np.concatenate((t, r)))

        return pos

    def get_actuator_length(self):
        alen = [math.nan for _ in range(6)]

        return alen

    def get_general_state(self):
        state = 0
        state = set_bit(state, 1)  # System Initialized
        state = set_bit(state, 2)  # In Position
        if self.homing_done:
            state = set_bit(state, 4)
        if self.control_loop:
            state = set_bit(state, 3)
        if self._virtual_homing:
            state = set_bit(state, 18)
        return state, decode_Q36(state)

    def goto_specific_position(self, pos):
        return 0

    def goto_retracted_position(self):
        translation = np.array([0, 0, -20])
        rotation = np.array([0, 0, 0])

        self.cs_platform.setTranslationRotation(
            translation,
            rotation,
            rot_config=self.rot_config,
            active=True,
            degrees=True,
            preserveLinks=True,
        )

        return 0

    def goto_zero_position(self):
        # We set a new transformation for cs_platform which will update our model.
        # See issue #58: updating the cs_platform is currently not a good idea because that will
        # not properly update the chain/path upwards, i.e. the chain/path is followed in the
        # direction of the references that are defined, not in the other direction.
        #
        translation = np.array([0, 0, 0])
        rotation = np.array([0, 0, 0])

        self.cs_platform.setTranslationRotation(
            translation,
            rotation,
            rot_config=self.rot_config,
            active=True,
            degrees=True,
            preserveLinks=True,
        )

        # As a work around for the bug in issue #58, we determine the transformation from
        # cs_object as it is
        # invariantly linked with cs_platform. Updating cs_object_in_user with that
        # transformation will
        # properly update all the reference frames.

        # tr_abs, rot_abs = self.cs_object.getTranslationRotationVectors()
        #
        # self.cs_object_in_user.setTranslationRotation(
        #     tr_abs,
        #     rot_abs,
        #     rot_config=self.rot_config,
        #     active=True,
        #     degrees=True,
        #     preserveLinks=True,
        # )

        return 0

    def is_in_position(self):
        return True

    def jog(self, axis: int, inc: float) -> int:
        pass

    def get_debug_info(self):
        pass

    def set_speed(self, vt, vr):
        self._speed[0] = vt
        self._speed[1] = vr

    def get_speed(self):
        return tuple(self._speed)

    def get_actuator_state(self):
        return [
            (
                {
                    0: "In position",
                    1: "Control loop on servo motors active",
                    2: "Homing done",
                    4: 'Input "Positive limit switch"',
                    5: 'Input "Negative limit switch"',
                    6: "Brake control output",
                },
                [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ),
            (
                {
                    0: "In position",
                    1: "Control loop on servo motors active",
                    2: "Homing done",
                    4: 'Input "Positive limit switch"',
                    5: 'Input "Negative limit switch"',
                    6: "Brake control output",
                },
                [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ),
            (
                {
                    0: "In position",
                    1: "Control loop on servo motors active",
                    2: "Homing done",
                    4: 'Input "Positive limit switch"',
                    5: 'Input "Negative limit switch"',
                    6: "Brake control output",
                },
                [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ),
            (
                {
                    0: "In position",
                    1: "Control loop on servo motors active",
                    2: "Homing done",
                    4: 'Input "Positive limit switch"',
                    5: 'Input "Negative limit switch"',
                    6: "Brake control output",
                },
                [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ),
            (
                {
                    0: "In position",
                    1: "Control loop on servo motors active",
                    2: "Homing done",
                    4: 'Input "Positive limit switch"',
                    5: 'Input "Negative limit switch"',
                    6: "Brake control output",
                },
                [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ),
            (
                {
                    0: "In position",
                    1: "Control loop on servo motors active",
                    2: "Homing done",
                    4: 'Input "Positive limit switch"',
                    5: 'Input "Negative limit switch"',
                    6: "Brake control output",
                },
                [1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            ),
        ]

    def perform_maintenance(self, axis):
        pass

    def info(self):
        msg = "Info about the PunaSimulator:\n"
        msg += "\n"
        msg += "This Hexapod PUNA Simulator works with several reference frames:\n"
        msg += "  * The machine reference frame\n"
        msg += "  * The platform reference frame\n"
        msg += "  * The object reference frame\n"
        msg += "  * The user reference frame\n\n"
        msg += "Any movement commands result in a transformation of the appropriate coordinate systems."

        logger.info(msg)

        return msg
