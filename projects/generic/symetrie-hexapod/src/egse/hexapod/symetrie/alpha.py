from egse.decorators import dynamic_interface


class AlphaControllerInterface:
    @dynamic_interface
    def info(self):
        """Returns basic information about the hexapod and the controller.

        Returns:
            a multiline response message containing the device info.
        Raises:
            HexapodError: when information can not be retrieved.
        """
        raise NotImplementedError

    @dynamic_interface
    def reset(self, wait=True):
        """Completely resets the Hexapod hardware controller with the standard boot cycle.

        Args:
            wait (bool): after the reset command has been sent to the controller, wait
                for 30 seconds which should complete the cycle, i.e. this command will
                only return after 30 seconds.

        Note:
           This command is equivalent to power cycling the controller manually.

        """
        raise NotImplementedError

    @dynamic_interface
    def homing(self):
        """Start the homing cycle for the Hexapod PUNA.

        Homing is required before performing a control movement. Without absolute encoders,
        the homing is performed with a hexapod movement until detecting the reference sensor
        on each of the actuators. The Hexapod will go to a position were the sensors are
        reached that signal a known calibrated position and then returns to the zero position.

        Whenever a homing is performed, the method will return before the actual movement
        is finished.

        The homing cycle takes about two minutes to complete, but the ``homing()`` method
        returns almost immediately. Therefore, to check if the homing is finished, use
        the is_homing_done() method.

        Returns:
            0 on success.
        Raises:
            HexapodError: when there is a timeout or when there is a communication error with
            the hexapod.
        """
        raise NotImplementedError

    @dynamic_interface
    def set_virtual_homing(self, tx, ty, tz, rx, ry, rz):
        """Starts the virtual homing cycle on the hexapod.

        This command uses the position given in parameters to initialize the hexapod position.
        No movements of the hexapod are performed during this homing cycle. Please note that the
        position specified in parameters must match the absolute position of the Object coordinate
        system in the User coordinate system (see description in the manual chapter 2 on coordinates
        systems). This position correspond to the answer of the command `get_user_positions()`.
        During this operation, it is important to have the same hexapod position as those defined
        during the record of the position. Otherwise, the system initialization will be incorrect.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            return_code: 0 on success, -1 when ignored

        Raises:
            HexapodError: when the arguments do not match up, or when there is a timeout or when
            there is a
            socket communication error.

        """
        return NotImplementedError

    @dynamic_interface
    def stop(self):
        """Stop the current motion. This command can be sent during a motion of the Hexapod.

        Returns:
            0 on success.
        Raises:
            HexapodError: when there is a timeout or when there is a communication error with
            the hexapod.
        """
        raise NotImplementedError

    @dynamic_interface
    def clear_error(self):
        """Clear all errors in the controller software.

        Returns:
            0 on success.
        Raises:
            HexapodError: when there is Time-Out or when there is a communication error with the
            hexapod.
        """
        raise NotImplementedError

    @dynamic_interface
    def activate_control_loop(self):
        """Activates the control loop on motors.

        Returns:
            0 on success, -1 when ignored, -2 on error.
        Raises:
            HexapodError: when there is a timeout or when there is a communication error with
            the hexapod
                hardware controller.
        """
        raise NotImplementedError

    @dynamic_interface
    def deactivate_control_loop(self):
        """Disables the control loop on the servo motors.

        Returns:
            0 on success.
        Raises:
            HexapodError: when there is a timeout or when there is a communication error with
            the hexapod.
        """
        raise NotImplementedError

    @dynamic_interface
    def jog(self, axis: int, inc: float) -> int:
        """Perform a JOG-type movement on the specified actuator.

        Note:
            This is a maintenance feature.

        Args:
            axis (int): number of the actuator (1 to 6)
            inc (float): increment to achieve in mm
        Returns:
            0 on success, -1 if command was ignored due to non-compliance.
        Raises:
            HexapodError: when there is a timeout or when there is a communication error with
            the hexapod.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_debug_info(self):
        """
        Request debug information from the Hexapod Controller.

        The method returns four values that represent the following status:

        1. ``Homing``: state of the homing
        2. ``PosRef``: state of the Position Reference command
        3. ``KinError``: error in kinematic calculation
        4. ``Panel``: Panel state

        The Homing can take the following values:

            =====     ==================
            Value     Meaning
            =====     ==================
            0         Undefined
            1         Homing in progress
            2         Homing done
            3         Error
            =====     ==================

        The PosRef can take the following values:

            =======     =====================
             Value       Meaning
            =======     =====================
               0         Undefined
               1         Abort input error
               2         Movement in progress
               3         Position reached
               4         Error
            =======     =====================

        The KinError can take the following values:

            =======     ===============================================
             Value       Meaning
            =======     ===============================================
               0         none
               1         Homing not done
               2         Inverse kinematic model (MGI) – workspace
               3         Inverse kinematic model (MGI) – joint angle
               4         Forward kinematic model (MGD) – workspace
               5         Forward kinematic model (MGD) – max iteration
               6         Position calculation (PLCC) – workspace
               7         Position calculation (PLCC) – max iteration.
            =======     ===============================================

        The Panel status can take the following values:

            ======   ===============
            Index       Command
            ======   ===============
            -2       Command error
            -1       Ignored / Command not allowed
            **0**       **None**
            1        Homing
            2        Stop
            3        Control ON
            4        Control OFF
            10       Valid POS
            11       Move
            12       Sequence
            13       Specific POS
            15       Clear Error
              **Family “Set config”**
            ------------------------
            21       Config CS
            22       Config Limits_mTn
            23       Config Limits_uTo
            24       Config Limits_Enabled
            25       Config Speed
            26       Config Current
            27       Config Backlash
              **Family “Get config”**
            ------------------------
            31       Config CS
            32       Config Limits_mTn
            33       Config Limits_uTo
            34       Config Limits_Enabled
            35       Config Speed
            36       Config Current
            37       Config Backlash
              **Family “Maintenance”**
            ------------------------
            41       Jog
            50       Config Save
            51       Config Default
            52       Config Saved?
            55       Version
            ======   ===============

        """
        raise NotImplementedError

    @dynamic_interface
    def configure_coordinates_systems(
        self, tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o
    ):
        """
        Change the definition of the User Coordinate System and the Object Coordinate System.

        The parameters tx_u, ty_u, tz_u, rx_u, ry_u, rz_u are used to define the user coordinate
        system
        relative to the Machine Coordinate System and the parameters tx_o, ty_o, tz_o, rx_o,
        ry_o, rz_o
        are used to define the Object Coordinate System relative to the Platform Coordinate System.

        Args:
            tx_u (float): translation parameter that define the user coordinate system relative
            to the machine coordinate system [in mm]
            ty_u (float): translation parameter that define the user coordinate system relative
            to the machine coordinate system [in mm]
            tz_u (float): translation parameter that define the user coordinate system relative
            to the  machine coordinate system [in mm]
            rx_u (float): rotation parameter that define the user coordinate system relative to
            the machine coordinate system [in deg]
            ry_u (float): rotation parameter that define the user coordinate system relative to
            the machine coordinate system [in deg]
            rz_u (float): rotation parameter that define the user coordinate system relative to
            the machine coordinate system [in deg]
            tx_o (float): translation parameter that define the object coordinate system relative
            to the platform coordinate system [in mm]
            ty_o (float): translation parameter that define the object coordinate system relative
            to the platform coordinate system [in mm]
            tz_o (float): translation parameter that define the object coordinate system relative
            to the platform coordinate system [in mm]
            rx_o (float): rotation parameter that define the object coordinate system relative to the platform
            coordinate system [in deg]
            ry_o (float): rotation parameter that define the object coordinate system relative to the platform
            coordinate system [in deg]
            rz_o (float): rotation parameter that define the object coordinate system relative to the platform
            coordinate system [in deg]

        Returns:
            0 on success and -1 when the configuration is ignored, e.g. when password protection
            is enabled.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_coordinates_systems(self):
        """Retrieve the definition of the User Coordinate System and the Object Coordinate System.

        Returns:
            tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o where the
            translation \
            parameters are in [mm] and the rotation parameters are in [deg].
        Raises:
            HexapodError: when an error occurred while trying to retrieve the information.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_actuator_length(self):
        """Retrieve the current length of the hexapod actuators.

        Returns:
            array: an array of six float values for actuator length L1 to L6 in [mm], and \
            None: when an Exception was raised and logs the error message.
        """
        raise NotImplementedError

    @dynamic_interface
    def move_absolute(self, tx, ty, tz, rx, ry, rz):
        """Move/define the Object Coordinate System position and orientation expressed
        in the invariant user coordinate system.

        The rotation centre coincides with the Object Coordinates System origin and
        the movements are controlled with translation components at first (Tx, Ty, tZ)
        and then the rotation components (Rx, Ry, Rz).

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            return_code: 0 on success, -1 when ignored, -2 on error

        Raises:
            HexapodError: when the arguments do not match up, or when there is a time out or when
            there is a
            socket communication error.

        .. note::
           When the command was not successful, this method will query the
           POSVALID? using the checkAbsolutePosition() and print a summary
           of the error messages to the log file.

        .. todo::
           do we want to check if the movement is valid before actually performing
           the movement?

        """
        raise NotImplementedError

    @dynamic_interface
    def move_relative_object(self, tx, ty, tz, rx, ry, rz):
        """Move the object relative to its current object position and orientation.

        The relative movement is expressed in the object coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            0 on success, -1 when ignored, -2 on error.

        Raises:
            HexapodError: when the arguments do not match up, or when there is a time out or when
            there is a
            socket communication error.

        .. todo:: do we want to check if the movement is valid before actually performing
                  the movement?

        """
        raise NotImplementedError

    @dynamic_interface
    def move_relative_user(self, tx, ty, tz, rx, ry, rz):
        """Move the object relative to its current object position and orientation.

        The relative movement is expressed in the (invariant) user coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            0 on success, -1 when ignored, -2 on error.

        Raises:
            HexapodError: when the arguments do not match up, or when there is a time out or when
            there is a
            socket communication error.

        .. todo:: do we want to check if the movement is valid before actually performing
                  the movement?

        """
        raise NotImplementedError

    @dynamic_interface
    def check_absolute_movement(self, tx, ty, tz, rx, ry, rz):
        """Check if the requested object movement is valid.

        The absolute movement is expressed in the user coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            tuple: where the first element is an integer that represents the
                bitfield encoding the errors. The second element is a dictionary
                with the bit numbers that were (on) and the corresponding error
                description.

        .. todo:: either provide a more user friendly return value or a method/function
                  to process the information into a human readable form. Also update
                  the documentation of this method with more information about the
                  bitfields etc.
        """
        raise NotImplementedError

    @dynamic_interface
    def check_relative_object_movement(self, tx, ty, tz, rx, ry, rz):
        """Check if the requested object movement is valid.

        The relative motion is expressed in the object coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            tuple: where the first element is an integer that represents the
                bitfield encoding the errors. The second element is a dictionary
                with the bit numbers that were (on) and the corresponding error
                description.

        .. todo:: either provide a more user friendly return value or a method/function
                  to process the information into a human readable form. Also update
                  the documentation of this method with more information about the
                  bitfields etc.
        """
        raise NotImplementedError

    @dynamic_interface
    def check_relative_user_movement(self, tx, ty, tz, rx, ry, rz):
        """Check if the requested object movement is valid.

        The relative motion is expressed in the user coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            tuple: where the first element is an integer that represents the
                bitfield encoding the errors. The second element is a dictionary
                with the bit numbers that were (on) and the corresponding error
                description.

        .. todo:: either provide a more user friendly return value or a method/function
                  to process the information into a human readable form. Also update
                  the documentation of this method with more information about the
                  bitfields etc.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_user_positions(self):
        """Retrieve the current position of the hexapod.

        The returned position corresponds to the position of the Object Coordinate System
        in the User Coordinate System.

        Returns:
            array: an array of six float values for Tx, Ty, Tz, Rx, Ry, Rz.
            None: when an Exception was raised and logs the error message.

        Note: This is equivalent to the POSUSER? command.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_machine_positions(self):
        """Retrieve the current position of the hexapod.

        The returned position corresponds to the position of the Platform Coordinate System
        in the Machine Coordinate System.

        Returns:
            array: an array of six float values for Tx, Ty, Tz, Rx, Ry, Rz.
            None: when a PMACError was raised and logs the error message.

        Note: This is equivalent to the POSMACH? command.
        """
        raise NotImplementedError

    @dynamic_interface
    def set_speed(self, vt, vr):
        """Set the speed of the hexapod movements.

        Args:
            vt (float): The translation speed, expressed in mm per second [mm/s].
            vr (float): The angular speed, expressed in deg per second [deg/s].

        The arguments `vt` and `vr` are automatically limited by the controller
        between the minimum and maximum allowed speeds for the hexapod.
        See the `getSpeed()` method to know the limits.

        Returns:
            0 on success and -1 when the configuration is ignored, e.g. when password protection
            is enabled.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_speed(self):
        """Retrieve the configuration of the movement speed.

        Returns:
            vt, vr, vt_min, vr_min, vt_max, vr_max

        Where:
            * ``vt`` is the translation speed of the hexapod in mm per second [mm/s]
            * ``vr`` is the angular speed of the hexapod in deg per second [deg/s]
            * ``vt_min``, ``vt_max`` are the limits for the translation speed [mm/s]
            * ``vr_min``, ``vr_max`` are the limits for the angular speed [mm/s]

        """
        raise NotImplementedError

    @dynamic_interface
    def get_general_state(self):
        """Retrieve general state information of the hexapod.

        Returns:
            tuple: where the first element is an integer where the bits represent each state, and
                the second element is an array of True/False flags for each state described in
                Hexapod
                Controller API, section 4.5.6.

            None: when an Exception was raised and logs the error message.

        Note: This is equivalent to the STATE#HEXA? Command.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_actuator_state(self):
        """Retrieve general state information of the actuators.

        For each of the six actuators, an integer value is returned that should be interpreted as a
        bit field containing status bits for that actuator.

            ======   ========================
             Bit      Function
            ======   ========================
              0       In position
              1       Control loop on servo motors active
              2       Homing done
              3       Input "Home Switch"
              4       Input "Positive limit switch"
              5       Input "Negative limit switch"
              6       Brake control output
              7       Following error (warning)
              8       Following error (Fatal)
              9       Actuator out of bounds error
             10       Amplifier error
             11       Encoder error
             12       Phasing error (brushless engine only)
             13-23    Reserved
            ======   ========================

        Returns:
            array: an array of six (6) dictionaries with True/False flags for each actuator state
            as described in
                Hexapod Controller API, section 4.5.5.
            None: when an Exception was raised and logs the error message.

        Note: This is equivalent to the STATE#ACTUATOR? Command.
        """
        raise NotImplementedError

    @dynamic_interface
    def goto_specific_position(self, pos):
        """Ask to go to a specific position.

        * pos=0 Zero position (jog & maintenance only!)
        * pos=1 Zero position
        * pos=2 Retracted position

        Returns:
            0 on success, -1 when ignored.

        Raises:
            HexapodError: when there is Time-Out or when there is a communication error with the
            hexapod controller.
        """
        raise NotImplementedError

    @dynamic_interface
    def goto_retracted_position(self):
        """Ask the hexapod to go to the retracted position.

        Returns:
            0 on success, -1 when ignored.

        Raises:
            HexapodError: when there is Time-Out or when there is a socket communication error.
        """
        raise NotImplementedError

    @dynamic_interface
    def goto_zero_position(self):
        """Ask the hexapod to go to the zero position.

        Returns:
            0 on success, -1 when ignored.

        Raises:
            HexapodError: when there is Time-Out or when there is a socket communication error.
        """
        raise NotImplementedError

    @dynamic_interface
    def is_homing_done(self):
        """
        Check if Homing is done. This method checks the ``Q26`` variable.
        When this variable indicates 'Homing is done' it means the command has properly been
        executed,
        but it doesn't mean the Hexapod is in position. The hexapod might still be moving to its
        zero position.

        Returns:
            True when the homing is done, False otherwise.
        """
        raise NotImplementedError

    @dynamic_interface
    def is_in_position(self):
        """
        Checks if the actuators are in position.

        This method queries the Q36 variable and examines the third bit which is the 'Is
        Position' bit.
        This method does **not** query the actuator state variables Q30 till Q36.

        Returns:
            True when in position, False otherwise.
        """
        raise NotImplementedError

    @dynamic_interface
    def perform_maintenance(self, axis):
        """Perform a maintenance cycle which consists of travelling the full range
        on one axis corresponding to the Hexapod machine limits. The movement is
        also in machine coordinate system.

        The ``axis`` argument can take the following values:

        * 1: movement on the X-axis
        * 2: movement on the Y-axis
        * 3: movement on the Z-axis
        * 4: movement around the X-axis
        * 5: movement around the Y-axis
        * 6: movement around the Z-axis
        * 10: all previous cycles chained together

        Args:
            axis (int): on which axis the full range movement is executed
        Returns:
            0 on success, -1 when ignored for non-compliance.
        Raises:
            HexapodError: when there is Time-Out or when there is a socket communication error.
        """
        raise NotImplementedError

    def log_positions(self):
        """
        Log the current position of the hexapod (level=INFO). The positions correspond to

          * the position of the Object Coordinate System in the User Coordinate System, and
          * the position of the Platform Coordinate System in the Machine Coordinate System.

        """

        pos = self.get_user_positions()
        logger.info(
            f"Object [in User]     : "
            f"{pos[0]:2.5f}, {pos[1]:2.5f}, {pos[2]:2.5f}, {pos[3]:2.5f}, {pos[4]:2.5f}, "
            f"{pos[5]:2.5f}"
        )

        pos = self.get_machine_positions()
        logger.info(
            f"Platform [in Machine]: "
            f"{pos[0]:2.5f}, {pos[1]:2.5f}, {pos[2]:2.5f}, {pos[3]:2.5f}, {pos[4]:2.5f}, "
            f"{pos[5]:2.5f}"
        )


class AlphaPlusControllerInterface(AlphaControllerInterface):

    @dynamic_interface
    def get_limits_value(self, lim):
        """Three different and independent operational workspace limits are defined on the controller:
            * Factory limits: are expressed in machine coordinate system limits. Those parameters cannot be modified.
            * Machine coordinate system limits: they are expressed in the Machine coordinate system. It can be used to
            secure the hexapod (and/or object) from its environment.
            * User coordinate system limits: they are expressed in the User coordinate system. It can be used to limits
            the movements of the object mounted on hexapod.

        Remark: operational workspace limits must be understood as limits in terms of amplitude of movement. Those
        limits are defined for each operational axis with a negative and positive value and are used in the validation
        process. Position on each operational axis must be within those two values.

        Args:
            lim (int):
            0 = factory (GET only),
            1 = machine cs limit,
            2 = user cs limit

        """
        raise NotImplementedError

    @dynamic_interface
    def get_limits_state(self):
        """ Return workspace limits enable state

        """
        raise NotImplementedError

    @dynamic_interface
    def get_temperature(self):
        """ Return the 6xPT100 temperature sensor's value in C

        """
        raise NotImplementedError

    @dynamic_interface
    def machine_limit_enable(self, state):
        """Enable or disable the machine workspace limit of the hexapod.

        Remark: the factory machine coordinate system limit is always enabled to ensure the safety of the hexapod. It
        cannot be disabled.

            state(int):
            0 = disabled
            1 = enabled

        """

        raise NotImplementedError

    @dynamic_interface
    def machine_limit_set(self, *par):
        """Sets the machine workspace limits of the hexapod. Will raise error if not all the parameters are set (see
        Args definition)

        Remark: operational workspace limits must be understood as limits in terms of amplitude of movement. Those limits
        are defined for each operational axis with a negative and positive value and are used in the validation process.
        Position on each operational axis must be within those two values.

        Args:
            ntx(double): negative position limit in X in mm
            nty(double): negative position limit in Y in mm
            ntz(double): negative position limit in Z in mm
            nrx(double): negative position limit around the axis X in deg
            nry(double): negative position limit around the axis Y in deg
            nrz(double): negative position limit around the axis Y in deg

            ptx(double): positive position limit in X in mm
            pty(double): positive position limit in Y in mm
            ptz(double): positive position limit in Z in mm
            prx(double): positive position limit around the axis X in deg
            pry(double): positive position limit around the axis Y in deg
            prz(double): positive position limit around the axis Y in deg

        """

        raise NotImplementedError

    @dynamic_interface
    def user_limit_enable(self, state):
        """Enable or disable the user workspace limit of the hexapod.

        Remark: the factory machine coordinate system limit is always enabled to ensure the safety of the hexapod. It
        cannot be disabled.

            state(int):
            0 = disabled
            1 = enabled

        """

        raise NotImplementedError

    @dynamic_interface
    def user_limit_set(self, *par):
        """Sets the user workspace limits of the hexapod. Will raise error if not all the parameters are set (see
        Args definition)

        Remark: operational workspace limits must be understood as limits in terms of amplitude of movement. Those
        limits are defined for each operational axis with a negative and positive value and are used in the
        validation process.  Position on each operational axis must be within those two values.

        Args:
            ntx(double): negative position limit in X in mm
            nty(double): negative position limit in Y in mm
            ntz(double): negative position limit in Z in mm
            nrx(double): negative position limit around the axis X in deg
            nry(double): negative position limit around the axis Y in deg
            nrz(double): negative position limit around the axis Y in deg

            ptx(double): positive position limit in X in mm
            pty(double): positive position limit in Y in mm
            ptz(double): positive position limit in Z in mm
            prx(double): positive position limit around the axis X in deg
            pry(double): positive position limit around the axis Y in deg
            prz(double): positive position limit around the axis Y in deg

        """

        raise NotImplementedError

    @dynamic_interface
    def set_default(self):
        """
        Restores the default configuration parameters. The command can be used to restore factory default parameters.
        The restored configuration is not automatically saved. refer to the command CFG_SAVE to save the parameters in
        order to keep them after a controller power off. The calculation of the hexapod position is suspended during the
        command execution.
        """

        raise NotImplementedError
