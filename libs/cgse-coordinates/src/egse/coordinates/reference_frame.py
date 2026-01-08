"""
The referenceFrames module provides the class :code:`ReferenceFrames` which defines the affine transformation
for bringing one reference frame to another.

.. todo:: The tests in methods like getPassiveTransformationTo using '==' should be looked at again and maybe
          changed into using the 'is' operator. This because we now have __eq__ implemented.

@author: Pierre Royer
"""

import logging
import random
import string
import textwrap

import numpy as np
import transforms3d as t3

import egse.coordinates.transform3d_addon as t3add
from egse.coordinates.rotation_matrix import RotationMatrix
from egse.decorators import deprecate
from egse.exceptions import InvalidOperationError

LOGGER = logging.getLogger(__name__)
DEBUG = False


def transformation_to_string(transformation: np.ndarray) -> str:
    """Represents the given transformation in a condensed form on one line.

    Args:
        transformation (np.ndarray): Transformation matrix to be printed.

    Returns:
        Given transformation in a condensed form on one line.
    """

    if isinstance(transformation, np.ndarray):
        if np.allclose(transformation, ReferenceFrame._I):
            return "Identity"

        message = np.array2string(
            transformation,
            separator=",",
            suppress_small=True,
            formatter={"float_kind": lambda x: "%.2f" % x},
        ).replace("\n", "")
        return message

    # We do not want to raise an Exception here since this is mainly used in logging messages
    # and doesn't really harm the execution of the program.

    return f"ERROR: expected transformation to be an ndarray, type={type(transformation)}"


class ReferenceFrame(object):
    """
    A Reference Frame defined in reference frame "ref", i.e.
    defined by the affine transformation bringing the reference frame "ref" onto "self".

    By default, "ref" is the master refence frame, defined as the identity matrix.

    :param transformation: 4x4 affine transformation matrix defining this system in "ref" system
    :type transformation: numpy array

    :param reference_frame: reference system in which this new reference frame is defined
    :type reference_frame: ReferenceFrame

    :param name: name the reference frame so it can be referenced, set to 'master' when None
    :type name: str

    :param rotation_config:
            * Is set when using creator ReferenceFrame.fromTranslationRotation()
            * In other cases, is set to a default "szyx"
              (rotations around static axes z, y and x in this order)
              In these other cases, it has no real direct influence,
              except for methods returning the rotation vector (e.g. getRotationVector)
              It is therefore always recommended to pass it to the constructor, even when
              constructing the ReferenceFrame directly from a transformation matrix
    :type rotation_config: str

    Both the ``transformation`` and the ``ref`` parameters are mandatory.

    If the reference frame is None, the master reference frame is created.

    The master reference frame:

        * is defined by the identity transformation matrix
        * has itself as a reference

    For convenience we provide the following factory methods:

    createMaster()
        Create a Master Reference Frame

    createRotation(..)
        Create a new Reference Frame that is rotated with respect to the given reference frame

    createTranslation(..)
        Create a new Reference Frame that is a translation with respect to the given reference frame
    """

    _I = np.identity(4)
    _MASTER = None
    _ROT_CONFIG_DEFAULT = "sxyz"
    _names_used = [None, "Master"]
    _strict_naming = False
    _ACTIVE_DEFAULT = True

    def __init__(
        self, transformation: np.ndarray | None, reference_frame, name=None, rotation_config=_ROT_CONFIG_DEFAULT
    ):
        """Initialization of a new reference frame.

        Args:
            transformation (np.ndarray | None): 4x4 affine transformation matrix defining this system in the given
                                                reference frame.
            reference_frame:
            name (str | None): Name of the reference frame.
            rotation_config (str): Order in which the rotation about the three axes are chained.
        """

        self.debug = False

        DEBUG and LOGGER.debug(
            f"transformation={transformation_to_string(transformation)}, reference_frame={reference_frame!r}, name={name}, rot_config={rotation_config}"
        )

        # All argument testing is done in the __new__() method and we should be save here.

        self.reference_frame = reference_frame
        self.name = self.__create_name(name)
        self.transformation = transformation
        self.rotation_config = rotation_config

        self.definition = [self.transformation, self.reference_frame, self.name]

        self.x = self.get_axis("x")
        self.y = self.get_axis("y")
        self.z = self.get_axis("z")

        self.linked_to = {}
        self.reference_for = []

        reference_frame.reference_for.append(self)

        return

    def __new__(cls, transformation, ref, name=None, rot_config=_ROT_CONFIG_DEFAULT):
        """Create a new ReferenceFrame class."""

        DEBUG and LOGGER.debug(
            f"transformation={transformation_to_string(transformation)}, ref={ref!r}, name={name}, rot_config={rot_config}"
        )

        if ref is None:
            msg = (
                "No reference frame was given, if you planned to create a Master Reference Frame, "
                "use ReferenceFrame.createMaster(). "
            )
            LOGGER.error(msg)
            raise ValueError(msg, "REF_IS_NONE")

        if not isinstance(ref, cls):
            msg = f"The 'ref' keyword argument is not a ReferenceFrame object, but {type(ref)}"
            LOGGER.error(msg)
            raise ValueError(msg, "REF_IS_NOT_CLS")

        if name == "Master":
            msg = (
                "The 'name' argument cannot be 'Master' unless a Master instance should be created, "
                "in that case, use ReferenceFrame.createMaster()"
            )
            LOGGER.error(msg)
            raise ValueError(msg, "MASTER_NAME_USED")

        if transformation is None:
            msg = "The 'transformation' argument can not be None, please provide a proper transformation for this reference frame."
            LOGGER.error(msg)
            raise ValueError(msg, "TRANSFORMATION_IS_NONE")

        if not isinstance(transformation, np.ndarray):
            msg = f"The 'transformation' argument shall be a Numpy ndarray [not a {type(transformation)}], please provide a proper transformation for this reference frame."
            LOGGER.error(msg)
            raise ValueError(msg, "TRANSFORMATION_IS_NOT_NDARRAY")

        if rot_config is None:
            msg = "The 'rot_config' keyword argument can not be None, do not specify it when you want to use the default value."
            LOGGER.error(msg)
            raise ValueError(msg)

        _instance = super(ReferenceFrame, cls).__new__(cls)

        return _instance

    def find_master(self):
        """Returns the master frame.

        The master frame is always at the end of the path, when following the references.

        Returns: Master frame.
        """

        frame = self

        while not frame.is_master():
            frame = frame.reference_frame

        return frame

    @classmethod
    def create_master(cls):
        """Creates a master reference frame.

        A master reference frame is defined w.r.t. itself and is initialised with the identity matrix.

        The master frame is automatically given the name "Master".
        """

        master_frame = super(ReferenceFrame, cls).__new__(cls)
        master_frame.name = "Master"
        master_frame.reference_frame = master_frame
        master_frame.transformation = cls._I
        master_frame.rotation_config = cls._ROT_CONFIG_DEFAULT
        master_frame.initialized = True
        master_frame.debug = False
        master_frame.linked_to = {}
        master_frame.reference_for = []

        DEBUG and LOGGER.debug(
            f"NEW MASTER CREATED: {id(master_frame)}, reference_frame = {id(master_frame.reference_frame)}, name = {master_frame.name}"
        )

        return master_frame

    @classmethod
    def __create_name(cls, name: str = None) -> str:
        """Creates a unique name for a reference frame.

        Args:
            name (str): Name for a reference frame.

        Returns:
            Unique name for a reference frame.
        """

        if name is None:
            while name in cls._names_used:
                name = "F" + "".join(random.choices(string.ascii_uppercase, k=3))
            return name

        if cls._strict_naming:
            # Generate a unique name

            old_name = name

            while name in cls._names_used:
                name = "F" + "".join(random.choices(string.ascii_uppercase, k=3))

            LOGGER.warning(
                f"Name ('{old_name}') is already defined, since strict naming is applied, a new unique name was "
                f"created: {name}"
            )

        else:
            if name in cls._names_used:
                DEBUG and LOGGER.warning(
                    f"Name ('{name}') is already defined, now you have more than one ReferenceFrame with the same name."
                )

        cls._names_used.append(name)

        return name

    @classmethod
    def from_translation(
        cls, translation_x: float, translation_y: float, translation_z: float, reference_frame, name: str = None
    ):
        """Creates a reference frame from a translation w.r.t. the given reference frame.

         Args:
             translation_x (float): Translation along the x-axis.
             translation_y (float): Translation along the y-axis.
             translation_z (float): Translation along the z-axis.
             reference_frame (ReferenceFrame): Reference frame w.r.t. which the translation is performed.
             name (str): Simple, convenient name to identify the reference frame. If no name is provided, a random name
                         of  four characters starting with 'F' will be generated.

        Returns:
            Reference frame, based on the given translation along the axes w.r.t. the given reference frame.
        """

        affine_matrix = np.identity(4)
        affine_matrix[:3, 3] = [translation_x, translation_y, translation_z]

        if reference_frame is None:
            raise ValueError(
                "The reference_frame argument can not be None, provide a master or another reference frame."
            )

        return cls(transformation=affine_matrix, reference_frame=reference_frame, name=name)

    @classmethod
    def from_rotation(
        cls,
        rotation_x: float,
        rotation_y: float,
        rotation_z: float,
        reference_frame,
        name: str = None,
        rotation_config: str = _ROT_CONFIG_DEFAULT,
        active: bool = _ACTIVE_DEFAULT,
        degrees: bool = True,
    ):
        """Creates a reference frame from a rotation w.r.t. the given reference frame.

        Args:
            rotation_x (float): Rotation angle about the x-axis.
            rotation_y (float): Rotation angle about the y-axis.
            rotation_z (float): Rotation angle about the z-axis.
            reference_frame (ReferenceFrame): Reference frame w.r.t. which the rotation is performed.
            name (str): Simple, convenient name to identify the reference frame. If no name is provided, a random name
                        of  four characters starting with 'F' will be generated.
            rotation_config (str): Order in which the rotation about the three axes are chained.
            active (bool): Indicates whether the rotation is active.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.

        Returns:
            Reference frame, based on the given rotations about the axes w.r.t. the given reference frame.
        """

        if degrees:
            rotation_x = np.deg2rad(rotation_x)
            rotation_y = np.deg2rad(rotation_y)
            rotation_z = np.deg2rad(rotation_z)
        rotation_matrix = RotationMatrix(rotation_x, rotation_y, rotation_z, rotation_config, active=active)

        zoom = np.array([1, 1, 1])
        shear = np.array([0, 0, 0])
        translation = [0, 0, 0]

        transformation = t3.affines.compose(T=translation, R=rotation_matrix.rotation_matrix, Z=zoom, S=shear)

        if reference_frame is None:
            raise ValueError(
                "The reference_frame argument can not be None, provide a master or another reference frame."
            )

        return cls(
            transformation=transformation, reference_frame=reference_frame, name=name, rotation_config=rotation_config
        )

    @staticmethod
    def from_points(points, plane: str = "xy", use_svd: bool = True, verbose: bool = True):
        """Finds the best-fitting plane to the given points.

        Args:
            points (Points): Collection of point to which to fit the plane.
            plane (str): Kind of plane to fit.  Must be in ["xy", "yz", "zx"].
            use_svd (bool): Indicates whether to use Single Value Decomposition (SVD).
            verbose (bool): Indicates whether to print verbose output.

        Returns:
            Reference frame, based on the given points.
        """

        return points.best_fitting_plane(plane=plane, use_svd=use_svd, verbose=verbose)

    @classmethod
    def from_translation_rotation(
        cls,
        translation: np.ndarray,
        rotation: np.ndarray,
        reference_frame,
        name: str = None,
        rotation_config: str = _ROT_CONFIG_DEFAULT,
        active: bool = _ACTIVE_DEFAULT,
        degrees: bool = True,
    ):
        """Creates a reference frame from the given translation and rotation vectors.

        Args:
            translation (np.ndarray): Translation vector: 3x1 = tx, ty, tz.
            rotation (np.ndarray): Rotation vector: 3x1: rx, ry, rz.


            reference_frame (ReferenceFrame): Reference frame w.r.t. which the rotation is performed.
            name (str): Simple, convenient name to identify the reference frame. If no name is provided, a random name
                        of  four characters starting with 'F' will be generated.
            rotation_config (str): Order in which the rotation about the three axes are chained.
            active (bool): Indicates whether the rotation is active.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.

        """

        translation = np.array(translation)
        zoom = np.array([1, 1, 1])
        shear = np.array([0, 0, 0])
        if degrees:
            rotation = np.array([np.deg2rad(item) for item in rotation])
        rotation_x, rotation_y, rotation_z = rotation

        rotation_matrix = RotationMatrix(
            rotation_x, rotation_y, rotation_z, rotation_config=rotation_config, active=active
        )

        if reference_frame is None:
            raise ValueError(
                "The reference_frame argument can not be None, provide a master or another reference frame."
            )

        return cls(
            transformation=t3.affines.compose(translation, rotation_matrix.rotation_matrix, Z=zoom, S=shear),
            reference_frame=reference_frame,
            name=name,
            rotation_config=rotation_config,
        )

    def get_translation_vector(self) -> np.ndarray:
        """Returns the translation vector defining the reference frame.

        Returns:
            Translation vector: 3x1 = tx, ty, tz.
        """

        return self.transformation[:3, 3]

    def get_rotation_vector(self, degrees: bool = True) -> np.ndarray:
        """Returns the rotation vector defining the reference frame.

        Args:
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.

        Returns:
            Rotation vector: 3x1 = rx, ry, rz.
        """

        rotation = t3.euler.mat2euler(self.transformation, axes=self.rotation_config)

        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])

        return rotation

    def get_translation_rotation_vectors(self, degrees: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Returns the translation and rotation (vectors) defining the reference frame.

        Args:
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.

        Returns:
            Translation vector: 3x1 = tx, ty, tz.
            Rotation vector: 3x1 = rx, ry, rz.
        """

        translation = self.get_translation_vector()
        rotation = self.get_rotation_vector(degrees=degrees)

        return translation, rotation

    def get_rotation_matrix(self) -> np.ndarray:
        """Returns the rotation matrix defining the reference frame.

        Args:
            Rotation matrix defining the reference frame.
        """

        result = self.transformation.copy()
        result[:3, 3] = [0.0, 0.0, 0.0]

        return result

    def __repr__(self) -> str:
        """Returns a representation the reference frame.

        Returns:
            Representation of the reference frame.
        """

        return (
            f"ReferenceFrame(transformation={transformation_to_string(self.transformation)}, "
            f"reference_frame={self.reference_frame.name}, name={self.name}, rotation_config={self.rotation_config})"
        )

    def __str__(self) -> str:
        """Returns a printable string representation of the reference frame.

        Returns:
            Printable string representation of the reference frame.
        """

        message = textwrap.dedent(
            f"""\
                ReferenceFrame
                name          : {self.name}
                reference     : {self.reference_frame.name}
                rotation_config    : {self.rotation_config}
                links         : {[key.name for key in self.linked_to.keys()]}
                transformation:
                  [{np.round(self.transformation[0], 3)}
                   {np.round(self.transformation[1], 3)}
                   {np.round(self.transformation[2], 3)}
                   {np.round(self.transformation[3], 3)}]
                translation   : {np.round(self.get_translation_vector(), 3)}
                rotation      : {np.round(self.get_rotation_vector(), 3)}"""
        )
        return message

    @deprecate(
        reason=(
            "I do not see the added value of changing the name and "
            "the current method has the side effect to change the name "
            "to a random string when the name argument is already used."
        ),
        alternative="the constructor argument to set the name already of the object.",
    )
    def set_name(self, name: str = None) -> None:
        """Sets or changes the name of the reference frame.

        Args:
            name (str): New name for the reference frame; if None, a random name will be generated.

        Raises:
             InvalidOperationError: When you try to change the name of the Master reference frame.
        """

        if self.is_master():
            raise InvalidOperationError(
                "You try to change the name of the Master reference frame, which is not allowed."
            )

        self.name = self.__create_name(name)

    def add_link(self, reference_frame, transformation=None, _stop: bool = False) -> None:
        """Adds a link with the given reference frame."""

        # DONE: set the inverse transformation in the ref to this
        #   ref.linkedTo[self] = t3add.affine_inverse(transformation)
        # TODO:
        #   remove the _stop keyword

        # TODO: deprecate transformation as an input variable
        #       linkedTo can become a list of reference frames, with no transformation
        #       associated to the link. The tfo associated to a link is already
        #       checked in real time whenever the link is addressed
        if transformation is None:
            transformation = self.get_active_transformation_to(reference_frame)
        else:
            if DEBUG:
                LOGGER.info(
                    "Deprecation warning: transformation will be automatically set to "
                    "the current relation between {self.name} and {ref.name}"
                )
                LOGGER.debug("Requested:")
                LOGGER.debug(np.round(transformation, decimals=3))
                LOGGER.debug("Auto (enforced):")

            transformation = self.get_active_transformation_to(reference_frame)

            DEBUG and LOGGER.debug(np.round(transformation, decimals=3))

        self.linked_to[reference_frame] = transformation

        # TODO simplify this when transformation is deprecated
        #      it becomes ref.linked_to[self] = ref.get_active_transformation_to(self)
        reference_frame.linked_to[self] = t3add.affine_inverse(transformation)

    def remove_link(self, reference_frame) -> None:
        """Removes the links with the given reference frame (both ways).

        Args:
            reference_frame (ReferenceFrame): Reference frame to remove the link with.
        """

        # First remove the entry in ref to this

        if self in reference_frame.linked_to:
            del reference_frame.linked_to[self]

        # Then remove the entry in this to ref

        if reference_frame in self.linked_to:
            del self.linked_to[reference_frame]

    def get_passive_transformation_to(self, target_frame) -> np.ndarray:
        """Returns the transformation to apply to a point (defined in self) to express it in the target frame.

        A passive transformation means that the point is static and that we change the reference frame around it.

        get_passive_transformation_to(self, target_frame) == get_point_transformation_to(self, target_frame)

        Args:
            target_frame (ReferenceFrame): Reference frame to get the passive transformation to.

        Returns:
            Passive transformation to apply to a point (defined in self) to express it in the target frame.
        """

        DEBUG and LOGGER.debug("PASSIVE TO self {self.name} target {targetFrame.name}")
        if target_frame is self:
            # Nothing to do here, we already have the right coordinates

            DEBUG and LOGGER.debug("case 1")
            result = np.identity(4)

        elif target_frame.reference_frame is self:
            # The target frame is defined in self -> The requested transformation is the target frame definition
            DEBUG and LOGGER.debug("=== 2 start ===")
            result = t3add.affine_inverse(target_frame.transformation)
            DEBUG and LOGGER.debug("=== 2 end   ===")
        elif target_frame.reference_frame is self.reference_frame:
            # target_frame and self are defined wrt the same reference frame
            # We want
            #   self --> target_frame
            # We know
            #   target_frame.reference_frame --> target_frame (= target_frame.transformation)
            #   self.reference_frame   --> self   (= self.transformation)
            # That is
            #   self --> self.reference_frame is target_frame.reference_frame --> target_frame
            #   inverse(definition)    target_frame definition

            # Both reference frames are defined w.r.t. the same reference frame

            if DEBUG:
                LOGGER.debug("=== 3 start ===")
                LOGGER.debug(" ref   \n{0}".format(self.reference_frame))
                LOGGER.debug("===")
                LOGGER.debug("self   \n{0}".format(self))
                LOGGER.debug("===")
                LOGGER.debug("target_frame \n{0}".format(target_frame))
                LOGGER.debug("===")

            self_to_ref = self.transformation
            DEBUG and LOGGER.debug("self_to_ref \n{0}".format(self_to_ref))

            ref_to_target = t3add.affine_inverse(target_frame.transformation)
            DEBUG and LOGGER.debug("ref_to_target \n{0}".format(ref_to_target))

            result = np.dot(ref_to_target, self_to_ref)
            DEBUG and LOGGER.debug("result \n{0}".format(result))
            DEBUG and LOGGER.debug("=== 3 end   ===")
        else:
            # We are after the transformation from
            #   self --> target_frame
            #   self --> self.reference_frame --> target_frame.reference_frame --> target_frame
            #
            # We know
            #   target_frame.reference_frame --> target_frame (target_frame.transformation)
            #   self.reference_frame        --> self (self.transformation)
            # but
            #   target_frame.reference_frame != self.reference_frame
            # so we need
            #   self.reference_frame --> target_frame.reference_frame
            # then we can compose
            # self --> self.reference_frame --> target_frame.reference_frame --> target_frame
            #
            # Note: the transformation self.reference_frame --> target_frame.reference_frame is acquired recursively
            #       This relies on the underlying assumption that there exists
            #       one unique reference frame that source and self can be linked to
            #       (without constraints on the number of links necessary), i.e.
            #       that, from a frame to its reference or the opposite, there exists
            #       a path between self and target_frame. That is equivalent to
            #       the assumption that the entire set of reference frames is connex,
            #       i.e. defined upon a unique master reference frame.

            DEBUG and LOGGER.debug("=== 4 start ===")
            self_to_ref = self.transformation
            self_ref_to_target_ref = self.reference_frame.get_passive_transformation_to(target_frame.reference_frame)
            ref_to_target = t3add.affine_inverse(target_frame.transformation)
            result = np.dot(ref_to_target, np.dot(self_ref_to_target_ref, self_to_ref))
            DEBUG and LOGGER.debug("=== 4 end   ===")

        return result

    def get_passive_translation_rotation_vectors_to(self, target_frame, degrees: bool = True):
        """Extracts the translation and rotation vectors from the passive transformation to the target frame.

        Args:
            target_frame (ReferenceFrame): Reference frame to get the passive transformation to.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Translation and rotation vectors from the passive transformation to the target frame.
        """

        transformation = self.get_passive_transformation_to(target_frame)

        rotation = t3.euler.mat2euler(transformation, axes=self.rotation_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]

        return translation, rotation

    def get_passive_translation_vector_to(self, target_frame) -> np.ndarray:
        """Extract the translation vector from the passive transformation to the target frame.

        Args:
            target_frame (ReferenceFrame): Reference frame to get the passive transformation to.

        Returns:
            Translation vector from the passive transformation to the target frame.
        """
        return self.get_passive_translation_rotation_vectors_to(target_frame)[0]

    def get_passive_rotation_vector_to(self, target_frame, degrees=True):
        """Extracts the rotation vector from the passive transformation to the target frame.

        Args:
            target_frame (ReferenceFrame): Reference frame to get the passive transformation to.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Rotation vector from the passive transformation to the target frame.
        """

        return self.get_passive_translation_rotation_vectors_to(target_frame, degrees=degrees)[1]

    def get_passive_transformation_from(self, source_frame) -> np.ndarray:
        """Returns the transformation to apply to a point (defined in the source frame) to express it in self.

        A passive transformation means that the point is static and that we change the reference frame around it.

        get_passive_transformation_from(self, source_frame) == get_point_transformation_from(self, source_frame)

        Args:
            source_frame (ReferenceFrame): Reference frame to get the passive transformation from.

        Returns:
            Passive transformation to apply to a point (defined in the source frame) to express it in self.
        """

        DEBUG and LOGGER.debug("PASSIVE FROM self {self.name} source {source.name}")
        return source_frame.get_passive_transformation_to(self)

    def get_passive_translation_rotation_vectors_from(self, source_frame, degrees: bool = True):
        """Extracts the translation and rotation vectors from the passive transformation from the source frame.

        Args:
            source_frame (ReferenceFrame): Reference frame to get the passive transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Translation and rotation vectors from the passive transformation from the source frame.
        """

        transformation = self.get_passive_transformation_from(source_frame)
        rotation = t3.euler.mat2euler(transformation, axes=self.rotation_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]

        return translation, rotation

    def get_passive_translation_vector_from(self, source_frame):
        """Extracts the translation vector from the passive transformation from the source frame.

        Args:
            source_frame (ReferenceFrame): Reference frame to get the passive transformation from.

        Returns:
            Translation vector from the passive transformation from the source frame.
        """
        return self.get_passive_translation_rotation_vectors_from(source_frame)[0]

    def get_passive_rotation_vector_from(self, source_frame, degrees=True):
        """Extracts the rotation vector from the passive transformation from the source frame.

        Args:
            source_frame (ReferenceFrame): Reference frame to get the passive transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Rotation vector from the passive transformation from the source frame.
        """
        return self.get_passive_translation_rotation_vectors_from(source_frame, degrees=degrees)[1]

    def get_active_transformation_to(self, target_frame) -> np.ndarray:
        """Returns the active transformation to the target frame.

        Returns:
            Transformation matrix that defines the target frame in the current frame.
        """

        DEBUG and LOGGER.debug("ACTIVE TO self {self.name} target {target.name}")
        return target_frame.get_passive_transformation_to(self)

    def get_active_translation_rotation_vectors_to(
        self, target_frame, degrees: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """Extracts the translation and rotation vectors from the active transformation to the target frame.

        Args:
            target_frame (ReferenceFrame): Reference frame to get the active transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Translation and rotation vectors from the active transformation to the target frame.
        """

        transformation = self.get_active_transformation_to(target_frame)
        rotation = t3.euler.mat2euler(transformation, axes=self.rotation_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]

        return translation, rotation

    def get_active_translation_vector_to(self, target_frame, degrees: bool = True) -> np.ndarray:
        """Extracts the translation vector from the active transformation to the target frame.

        Args:
            target_frame (ReferenceFrame): Reference frame to get the active transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Translation vector from the active transformation to the target frame.
        """

        return self.get_active_translation_rotation_vectors_to(target_frame, degrees=degrees)[0]

    def get_active_rotation_vector_to(self, target_frame, degrees: bool = True):
        """Extracts the rotation vector from the active transformation to the target frame.

        Args:
            target_frame (ReferenceFrame): Reference frame to get the active transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Rotation vector from the active transformation to the target frame.
        """

        return self.get_active_translation_rotation_vectors_to(target_frame, degrees=degrees)[1]

    def get_active_transformation_from(self, source_frame):
        """Returns the active transformation from the source frame.

        Returns:
            Transformation matrix that defines the current frame in the source frame.
        """

        DEBUG and LOGGER.debug("ACTIVE FROM self {self.name} source {source.name}")
        return self.get_passive_transformation_to(source_frame)

    def get_active_translation_rotation_vectors_from(self, source_frame, degrees: bool = True):
        """Extracts the translation and rotation vectors from the active transformation from the source frame.

        Args:
            source_frame (ReferenceFrame): Reference frame to get the active transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Translation and rotation vectors from the active transformation from the source frame.
        """

        transformation = self.get_active_transformation_from(source_frame)
        rotation = t3.euler.mat2euler(transformation, axes=self.rotation_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]

        return translation, rotation

    def get_active_translation_vector_from(self, source_frame):
        """Extracts the translation vector from the active transformation from the source frame.

        Args:
            source_frame (ReferenceFrame): Reference frame to get the active transformation from.

        Returns:
            Translation vector from the active transformation from the source frame.
        """

        return self.get_active_translation_rotation_vectors_from(source_frame)[0]

    def get_active_rotation_vector_from(self, source_frame, degrees: bool = True):
        """Extracts the rotation vector from the active transformation from the source frame.

        Args:
            source_frame (ReferenceFrame): Reference frame to get the active transformation from.
            degrees (bool): Indicates if the rotation vector should be in degrees rather than radians.

        Returns:
            Rotation vector from the active transformation from the source frame.
        """

        return self.get_active_translation_rotation_vectors_from(source_frame, degrees=degrees)[1]

    def _find_ends(
        self, frame, visited: list = [], ends: list = [], verbose: bool = True, level: int = 1
    ) -> tuple[list, list]:
        """Identifies the linked frames.

        We discern between two types of frames:
            1. Frames that are linked, either directly or indirectly (via multiple links) to the given frame.  These are
               returned as `visited`.
            2. Frames of which the reference frame does not belong to the set of linked frames.  These are returned as
               `final_ends`.

        Args:
            frame (ReferenceFrame): Reference frame to find the linked frames from.
            visited (list): List of frames that have already been visited.
            ends (list): List of frames that have not been visited.
            verbose (bool): Whether to print the progress.
            level (int): Recursion level.

        Returns:
            Frames of which the reference frame does not belong to the set of linked frames.  These are returned as
               `final_ends`.
            Frames of which the reference frame does not belong to the set of linked frames.  These are returned as
               `final_ends`.
        """

        DEBUG and LOGGER.debug(
            f"{level:-2d}{2 * level * ' '} Current: {frame.name} --  ends: {[f.name for f in ends]} -- visited {[f.name for f in visited]}"
        )
        # if verbose: print (f"{level:-2d}{2*level*' '} Current: {frame.name} --  ends: {[f.name for f in ends]} -- visited {[f.name for f in visited]}")

        # Establish the set of 'linked_frames' (variable 'visited')
        # The recursive process below keeps unwanted (non-endFrames), namely the
        # frames that are not directly, but well indirectly linked to their reference
        # This case is solved further down

        if frame not in visited:
            visited.append(frame)

            if verbose and level:
                level += 1

            if frame.reference_frame not in frame.linked_to:
                ends.append(frame)
                DEBUG and LOGGER.debug(f"{(10 + 2 * level) * ' '}{frame.name}: new end")
                # if verbose: LOGGER.info(f"{(10+2*level)*' '}{frame.name}: new end")

            for linked_frame in frame.linked_to:
                ends, visited = self._find_ends(linked_frame, visited=visited, ends=ends, verbose=verbose, level=level)

        # If frame.reference_frame was linked to frame via an indirect route, reject it

        final_ends = []
        for aframe in ends:
            if aframe.reference_frame not in ends:
                final_ends.append(aframe)

        return final_ends, visited

    def set_transformation(
        self, transformation, updated=None, preserve_links: bool = True, relative: bool = False, verbose: bool = True
    ) -> None:
        """Alters the definition of this coordinate system.

        If other systems are linked to this one, their definition must be updated accordingly

        The link set between two reference frames A & B is the active transformation matrix from A to B

          A.addLink(B, matrix)
          A.getActiveTransformationTo(B) --> matrix

        The way to update the definition of the present system, and of those linked to it
        depends on the structure of those links.

        We define:
        - the target frame as the one we want to move / re-define
        - 'linkedFrames' as those directly, or indirectly (i.e. via multiple links)
           linked to the target frame
        - end_frames as the subset of linked_frames which are not linked to their reference (directly or indirectly)
        - side_Frames as the set of frames whose reference is a linked_frame, but not themselves belonging to the linked_frames

        We can demonstrate that updating the end_frames (Block A below) is sufficient to represent
        the movement of the target frame and all frames directly or indirectly linked to it.

        This may nevertheless have perverse effects for side_frames. Indeed,
        their reference will (directly or implicitly) be redefined, but they shouldn't:
        they are not linked to their reference --> their location in space (e.g. wrt the master frame)
        should not be affected by the movement of the target frame. This is the aim of block B.

        For a completely robust solution, 2 steps must be taken
        BLOCK A. apply the right transformation to all "end_frames"
        BLOCK B. Check for frames
                       using any of the "visited" frames as a reference
                       not linked to its reference
            Correct its so that it doesn't move (it shouldn't be affected by the requested movement)
            This demands a "reference_for" array property

        Args:
            transformation (np.ndarray): Affine transformation matrix to apply to the frame.
            updated (list): List of frames that have been updated.
            preserve_links (bool): Indicates whether the links of the frame should be preserved.
            relative (bool): Indicates whether the transformation is relative to the current frame.
            verbose (bool): Indicates whether to print verbose output.
        """

        # Ruthless, enforced re-definition of one system. Know what you do, or stay away.
        # Semi-unpredictable side effects if the impacted frame has links!

        if not preserve_links:
            self.transformation = transformation
            return

        if updated is None:
            updated = []

        # visitedFrames = all frames which can be reached from self via invariant links
        # endFrames = subset of visitedFrames that are at the end of a chain, and must be updated
        #             in order to properly represent the requested movement
        end_frames, visited_frames = self._find_ends(frame=self, visited=[], ends=[], verbose=verbose)
        if verbose:
            LOGGER.info(f"Visited sub-system                      {[f.name for f in visited_frames]}")
            LOGGER.info(f"End-frames (movement necessary)         {[f.name for f in end_frames]}")

        # All updates are done by relative movements
        # so we must first compute the relative movement corresponding to the requested absolute movement
        if not relative:
            # virtual = what self should become after the (absolute) movement
            # it allows to compute the relative transformation to be applied and work in relative further down
            virtual = ReferenceFrame(
                transformation,
                reference_frame=self.reference_frame,
                name="virtual",
                rotation_config=self.rotation_config,
            )
            request = self.get_active_transformation_to(virtual)
            del virtual
        else:
            # If this method is called by applyTransformation,
            # we are facing a request for a relative movement
            # In that case the input is directly what we want
            request = transformation

        # BLOCK B. Check for frames that were impacted but shouldn't have been and correct them
        # B1. List of frames demanding a correction
        #     'impacted' are frames having their reference inside the rigid structure moving, but not linked to it
        #     If nothing is done, the movement will implicitly displace them, which is not intended

        # Impacted shall not contain frames that are linked to self (== to any frame in visitedFrames) via any route...
        # We check if the impacted frames are in visitedFrames:
        # it is enough to know it's connected to the entire 'solid body' in which self belongs
        impacted = []
        for frame in visited_frames:
            for child in frame.reference_for:
                # Version 1 : too simple (restores too many frames)
                # if child not in frame.linkedTo:

                # Version 2 : overkill
                # child_ends, child_visited = child._findEnds(frame=child,visited=[],ends=[],verbose=verbose)
                # if frame not in child_visited:

                # Version 3 : just check if the child belongs to the rigid structure...
                if child not in visited_frames:
                    impacted.append(child)

        DEBUG and LOGGER.debug(f"Impacted (not moving, defined in moving) {[f.name for f in impacted]}")

        # B2. save the location of all impacted frames
        # tempReference has the only purpose of avoiding that every frame must know the master
        # It could be any frame without links and defined wrt the master, but the master isn't known here...
        # TODO : confirm that the master isn't known (e.g. via cls._MASTER)

        temp_master = self.find_master()
        to_restore = {}

        for frame in impacted:
            to_restore[frame] = ReferenceFrame(
                frame.get_active_transformation_from(temp_master),
                reference_frame=temp_master,
                name=frame.name + "to_restore",
                rotation_config=frame.rotation_config,
            )

        # BLOCK A. apply the right transformation to all "endFrames"

        # Ensure that `untouched` remains unaffected regardless of the update order of the end_frames
        # self_untouched = ReferenceFrame(
        #     transformation = self.get_active_transformation_from(temp_master),
        #     reference_frame=temp_master,
        #     name=self.name + "_fixed",
        #     rotation_config=self.rotation_config,
        # )

        self_untouched = ReferenceFrame(
            transformation=self.transformation,
            reference_frame=self.reference_frame,
            name=self.name + "_fixed",
            rotation_config=self.rotation_config,
        )

        for bottom in end_frames:
            up = bottom.get_active_transformation_to(self_untouched)
            down = self_untouched.get_active_transformation_to(bottom)

            relative_transformation = up @ request @ down

            if DEBUG:
                LOGGER.debug(f"\nAdjusting {bottom.name} to {self.name}\nUpdated {[i.name for i in updated]}")
                LOGGER.debug(f"\ninput transformation \n{np.round(transformation, 3)}")
                LOGGER.debug(
                    f"\nup \n{np.round(up, 3)}\ntransformation\n{np.round(request, 3)}\ndown\n{np.round(down, 3)}"
                )
                LOGGER.debug(f"\nrelative_transformation \n{np.round(relative_transformation, 3)}")

            bottom.transformation = bottom.transformation @ relative_transformation

            updated.append(bottom)

        for frame in visited_frames:
            if frame not in updated:
                updated.append(frame)

        # Block B
        # B3. Correction
        # we must set preserve_inks to False in order to prevent cascading impact from this update
        # if X1 is impacted with
        #    X1.ref = E1     X1 --> X2 (simple link)    E2.ref = X2
        # where X1 and X2 are "external frames" and E1 and E2 are "endFrames" that will hence move
        # X1 was impacted by the move of E1, but X2 wasn't
        # ==> wrt master, neither X1 nor X2 should have moved, but X1 did (via its ref)
        # and hence its link with X2 is now corrupt
        # We need to move X1 back to its original location wrt master
        # if we preserved the links while doing that,
        # we will move X2, which shouldn't move
        # (it didn't have to, it didn't and the goal is to restore the validity of the links)
        #
        # Direct restoration or the impacted frames at their original location

        for frame in to_restore:
            frame.transformation = frame.reference_frame.get_active_transformation_to(to_restore[frame])

        del to_restore

    def set_translation_rotation(
        self,
        translation: np.ndarray,
        rotation: np.ndarray,
        rotation_config: str = _ROT_CONFIG_DEFAULT,
        active: bool = _ACTIVE_DEFAULT,
        degrees: bool = True,
        preserve_links: bool = True,
    ) -> None:
        """Alters the definition of this coordinate system.

        Same as `set_transformation`, but here the input is translation and rotation vectors rather than an affine transformation matrix.

        Args:
            translation (np.ndarray): Translation vector: 3x1 = tx, ty, tz.
            rotation (np.ndarray): Rotation vector: 3x1: rx, ry, rz.
            rotation_config (str): Order in which the rotation about the three axes are chained.
            active (bool): Indicates whether the rotation is active.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
            preserve_links (bool): Indicates whether the links of the frame should be preserved.
        """

        translation = np.array(translation)
        zoom = np.array([1, 1, 1])
        shear = np.array([0, 0, 0])
        if degrees:
            rotation = np.array([np.deg2rad(item) for item in rotation])
        rotation_x, rotation_y, rotation_z = rotation

        rotation_matrix = RotationMatrix(
            rotation_x, rotation_y, rotation_z, rotation_config=rotation_config, active=active
        )

        DEBUG and LOGGER.debug(t3.affines.compose(translation, rotation_matrix.rotation_matrix, Z=zoom, S=shear))

        transformation = t3.affines.compose(translation, rotation_matrix.rotation_matrix, Z=zoom, S=shear)

        self.set_transformation(transformation, preserve_links=preserve_links, relative=False)

    def apply_transformation(self, transformation: np.ndarray, updated=None, preserve_links: bool = True) -> None:
        """Applies the given transformation to the current reference frame's definition.

        self.transformation := transformation @ self.transformation

        Args:
            transformation (np.ndarray): Affine transformation matrix.
            updated (list, optional): List of frames that have been updated.
            preserve_links (bool): Indicates whether the links of the frame should be preserved.
        """

        if updated is None:
            updated = []

        self.set_transformation(
            transformation=transformation,
            updated=updated,
            preserve_links=preserve_links,
            relative=True,
        )

    def apply_translation_rotation(
        self,
        translation: np.ndarray,
        rotation: np.ndarray,
        rotation_config=None,
        active: bool = _ACTIVE_DEFAULT,
        degrees: bool = True,
        preserve_links: bool = True,
    ) -> None:
        """Applies the given translation and rotation vectors to the current reference frame's definition.

        self.transformation := transformation @ self.transformation

        Args:
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            rotation_config (str): Order in which the rotation about the three axes are chained.
            active (bool): Indicates whether the rotation is active.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
            preserve_links (bool): Indicates whether the links of the frame should be preserved.
        """

        if rotation_config is None:
            rotation_config = self.rotation_config

        translation = np.array(translation)
        zoom = np.array([1, 1, 1])
        shear = np.array([0, 0, 0])

        if degrees:
            rotation = np.array([np.deg2rad(item) for item in rotation])
        rotation_x, rotation_y, rotation_z = rotation

        rotation_matrix = RotationMatrix(
            rotation_x, rotation_y, rotation_z, rotation_config=rotation_config, active=active
        )

        transformation = t3.affines.compose(translation, rotation_matrix.rotation_matrix, Z=zoom, S=shear)

        self.apply_transformation(transformation, preserve_links=preserve_links)

    def get_axis(self, axis: str, name: str | None = None):
        """Returns a unit vector corresponding to the axis of choice in the current reference frame.

        Args:
            axis(str) : Axis, in ["x","y","z"].
            name(str) : Name of the point.

        Returns:
            Point, corresponding to the vectors defining the axis of choice in `self`.
        """

        unit_vectors = dict()

        unit_vectors["x"] = [1, 0, 0]
        unit_vectors["y"] = [0, 1, 0]
        unit_vectors["z"] = [0, 0, 1]

        if name is None:
            name = self.name + axis
        from egse.coordinates.point import Point

        return Point(unit_vectors[axis], reference_frame=self, name=name)

    def get_normal(self, name: str | None = None):
        """Returns a unit vector, normal to the xy-plane.

        This corresponds to [0,0,1] = get_axis("z").

        The output can be used with the Point methods to express that axis in any reference frame.

        Args:
            name(str | None) : Name of the point.

        Returns:
            Point, corresponding to the vector defining the normal to the xy-plane in `self`.
        """
        from egse.coordinates.point import Point

        return Point([0, 0, 1], reference_frame=self, name=name)

    def get_origin(self, name: str | None = None):
        """Returns the origin in `self`.

        The output can be used with the Point methods to express that axis in any reference frame.

        Args:
            name (str | None) : Name of the point.

        Returns:
            Point, corresponding to the vector defining the origin in 'self', i.e. [0,0,0]
        """

        from egse.coordinates.point import Point

        return Point([0, 0, 0], reference_frame=self, name=name)

    def is_master(self) -> bool:
        """Checks whether this reference frame is a master reference frame.

        Returns:
            True if this reference frame is a master reference frame; False otherwise.
        """
        transformation = self.transformation

        return (
            (self.name == self.reference_frame.name)
            and (transformation.shape[0] == transformation.shape[1])
            and np.allclose(transformation, np.eye(transformation.shape[0]))
        )

    def is_same(self, other) -> bool:
        """Checks whether this reference frame is the same as another one (except for their name).

        For two reference frames to be considered the same, they must have
            - The same transformation matrix,
            - The same reference frame,
            - The same rotation configuration.

        The name of the reference frames may be different.

        Returns:
            True if the two reference frames are the same (except for their name); False otherwise.

        TODO This needs further work and testing!
        """

        if other is self:
            DEBUG and LOGGER.debug(
                "self and other are the same object (beware: this message might occur with recursion from self.ref != self.other)"
            )
            return True

        if isinstance(other, ReferenceFrame):
            DEBUG and LOGGER.debug(f"comparing {self.name} and {other.name}")
            if not np.array_equal(self.transformation, other.transformation):
                DEBUG and LOGGER.debug("self.transformation not equals other.transformation")
                return False
            if self.rotation_config != other.rotation_config:
                DEBUG and LOGGER.debug("self.rotation_config not equals other.rot_config")
                return False
            # The following tests are here to prevent recursion to go infinite when self and other
            # point to itself
            if self.reference_frame is self and other.reference_frame is other:
                DEBUG and LOGGER.debug("both self.reference_frame and other.reference_frame point to themselves")
                pass
            else:
                DEBUG and LOGGER.debug("one of self.reference_frame or other.ref doesn't points to itself")
                if self.reference_frame != other.reference_frame:
                    DEBUG and LOGGER.debug("self.reference_frame not equals other.reference_frame")
                    return False
            if self.name is not other.name:
                DEBUG and LOGGER.debug(
                    f"When checking two reference frames for equality, only their names differ: '{self.name}' not equals '{other.name}'"
                )
                pass
            return True

        return NotImplemented

    def __eq__(self, other):
        """Overrides the default implementation, which basically checks for id(self) == id(other).

        Two Reference Frames are considered equal when:
            - Their transformation matrices are equal,
            - Their reference frame is equal,
            - Their rotation configuration is the same

        TODO: Do we want to insist on the name being equal?
          YES - for strict testing
          NO  - this might need a new method like is_same(self, other) where the criteria are relaxed


        TODO This needs further work and testing!
        """

        if other is self:
            DEBUG and LOGGER.debug(
                "self and other are the same object (beware: this message might occur with recursion from self.ref != self.other)"
            )
            return True

        if isinstance(other, ReferenceFrame):
            DEBUG and LOGGER.debug(f"comparing {self.name} and {other.name}")
            if not np.array_equal(self.transformation, other.transformation):
                DEBUG and LOGGER.debug("self.transformation not equals other.transformation")
                return False
            if self.rotation_config != other.rotation_config:
                DEBUG and LOGGER.debug("self.rot_config not equals other.rot_config")
                return False
            # The following tests are here to prevent recursion to go infinite when self and other
            # point to itself
            if self.reference_frame is self and other.reference_frame is other:
                DEBUG and LOGGER.debug("both self.reference_frame and other.reference_frame point to themselves")
                pass
            else:
                DEBUG and LOGGER.debug("one of self.reference_frame or other.ref doesn't points to itself")
                if self.reference_frame != other.reference_frame:
                    DEBUG and LOGGER.debug("self.ref not equals other.reference_frame")
                    return False
            if self.name is not other.name:
                DEBUG and LOGGER.debug(
                    f"When checking two reference frames for equality, only their names differ: '{self.name}' not equals '{other.name}'"
                )
                return False

            return True

        return NotImplemented

    def __hash__(self):
        """Overrides the default implementation."""

        hash_number = (id(self.rotation_config) + id(self.reference_frame) + id(self.name)) // 16
        return hash_number

    def __copy__(self):
        """Overrides the default implementation."""

        DEBUG and LOGGER.debug(
            f'Copying {self!r} unless {self.name} is "Master" in which case the Master itself is returned.'
        )

        if self.is_master():
            DEBUG and LOGGER.debug(f"Returning Master itself instead of a copy.")
            return self

        return ReferenceFrame(self.transformation, self.reference_frame, self.name, self.rotation_config)
