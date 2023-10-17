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
from egse.coordinates.point import Point
from egse.coordinates.rotationMatrix import RotationMatrix
from egse.decorators import deprecate
from egse.exceptions import InvalidOperationError

LOGGER = logging.getLogger(__name__)


def transformationToString(transformation):
    """Helper function: prints out a transformation (numpy ndarray) in a condensed form on one line."""

    if isinstance(transformation, np.ndarray):
        if np.allclose(transformation, ReferenceFrame._I):
            return "Identity"
        msg = np.array2string(
            transformation,
            separator=",",
            suppress_small=True,
            formatter={"float_kind": lambda x: "%.2f" % x},
        ).replace("\n", "")
        return msg

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

    :param ref: reference system in which this new reference frame is defined
    :type ref: ReferenceFrame

    :param name: name the reference frame so it can be referenced, set to 'master' when None
    :type name: str

    :param rot_config:
            * Is set when using creator ReferenceFrame.fromTranslationRotation()
            * In other cases, is set to a default "szyx"
              (rotations around static axes z, y and x in this order)
              In these other cases, it has no real direct influence,
              except for methods returning the rotation vector (e.g. getRotationVector)
              It is therefore always recommended to pass it to the constructor, even when
              constructing the ReferenceFrame directly from a transformation matrix
    :type rot_config: str

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

    def __new__(cls, transformation, ref, name=None, rot_config=_ROT_CONFIG_DEFAULT):
        """Create a new ReferenceFrame class."""

        LOGGER.debug(
            f"transformation={transformationToString(transformation)}, ref={ref!r}, name={name}, rot_config={rot_config}"
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

    def __init__(self, transformation, ref, name=None, rot_config=_ROT_CONFIG_DEFAULT):
        """Initialize the ReferenceFrame object """

        self.debug = False

        LOGGER.debug(
            f"transformation={transformationToString(transformation)}, ref={ref!r}, name={name}, rot_config={rot_config}"
        )

        # All argument testing is done in the __new__() method and we should be save here.

        self.ref = ref
        self.name = self.__createName(name)
        self.transformation = transformation
        self.rot_config = rot_config

        self.definition = [self.transformation, self.ref, self.name]

        self.x = self.getAxis("x")
        self.y = self.getAxis("y")
        self.z = self.getAxis("z")

        self.linkedTo = {}
        self.referenceFor = []

        ref.referenceFor.append(self)

        return

    def find_master(self):
        return self.findMaster()

    def findMaster(self):
        """
        Returns the Master frame for this reference frame. The Master frame is always at the end
        of the path following the references.

        Returns:
            The master frame.
        """

        frame = self
        while not frame.isMaster():
            frame = frame.ref
        return frame

    @classmethod
    def createMaster(cls):
        """
        Create a master reference frame.

        A master reference frame is defined with respect to itself and is initialised with the
        identity matrix.

        The master frame is automatically given the name "Master".
        """
        ref_master = super(ReferenceFrame, cls).__new__(cls)
        ref_master.name = "Master"
        ref_master.ref = ref_master
        ref_master.transformation = cls._I
        ref_master.rot_config = cls._ROT_CONFIG_DEFAULT
        ref_master.initialized = True
        ref_master.debug = False
        ref_master.linkedTo = {}
        ref_master.referenceFor = []

        LOGGER.debug(
            f"NEW MASTER CREATED: {id(ref_master)}, ref = {id(ref_master.ref)}, "
            f"name = {ref_master.name}"
        )

        return ref_master

    @classmethod
    def __createName(cls, name: str = None):

        if name is None:
            while name in cls._names_used:
                name = "F" + "".join(random.choices(string.ascii_uppercase, k=3))
            return name

        if cls._strict_naming:

            # generate a unique name

            old_name = name

            while name in cls._names_used:
                name = "F" + "".join(random.choices(string.ascii_uppercase, k=3))

            LOGGER.warning(
                f"name ('{old_name}') is already defined, since strict naming is applied, "
                f"a new unique name was created: {name}"
            )

        else:

            if name in cls._names_used:
                LOGGER.log(
                    0,
                    f"name ('{name}') is already defined, now you have more than one "
                    f"ReferenceFrame with the same name.",
                )

        cls._names_used.append(name)
        return name

    @classmethod
    def fromTranslation(cls, transx, transy, transz, ref, name=None):
        """
        Create a ReferenceFrame from a translation with respect to the given reference frame.

        :param transx: translation along the x-axis
        :type transx: float

        :param transy: translation along the y-axis
        :type transy: float

        :param transz: translation along the z-axis
        :type transz: float

        :param ref: reference frame with respect to which the translation is performed. If no ref is given
            the rotation is with respect to the master reference frame
        :type ref: ReferenceFrame

        :param name: a simple convenient name to identify the reference frame. If no name is provided
                     a random name of four characters starting with 'F' will be generated.
        :type name: str

        :return: a reference frame
        """
        adef = np.identity(4)
        adef[:3, 3] = [transx, transy, transz]

        if ref is None:
            raise ValueError(
                "The ref argument can not be None, provide a master or another reference frame."
            )

        return cls(transformation=adef, ref=ref, name=name)

    @classmethod
    def fromRotation(
        cls,
        rotx,
        roty,
        rotz,
        ref,
        name=None,
        rot_config=_ROT_CONFIG_DEFAULT,
        active=_ACTIVE_DEFAULT,
        degrees=True,
    ):
        """
        Create a ReferenceFrame from a rotation with respect to the given reference frame.

        :param rotx: rotation around the x-axis
        :type rotx: float

        :param roty: rotation around the y-axis
        :type roty: float

        :param rotz: rotation around the z-axis
        :type rotz: float

        :param ref: reference frame with respect to which the rotation is performed. If no ref is given
            the rotation is with respect to the master reference frame
        :type ref: ReferenceFrame

        :param name: a simple convenient name to identify the reference frame. If no name is provided
                     a random name of four characters starting with 'F' will be generated.
        :type name: str

        :return: a reference frame
        """
        # Convention (rotating axes, in order xyz)

        # rot_config = cls._ROT_CONFIG_DEFAULT

        # Rotation amplitude

        # Rotation
        if degrees:
            rotx = np.deg2rad(rotx)
            roty = np.deg2rad(roty)
            rotz = np.deg2rad(rotz)

        rotation = RotationMatrix(rotx, roty, rotz, rot_config, active=active)

        # Defaults for zoom & shear

        zdef = np.array([1, 1, 1])
        sdef = np.array([0, 0, 0])

        translation = [0, 0, 0]

        TT = t3.affines.compose(T=translation, R=rotation.R, Z=zdef, S=sdef)

        if ref is None:
            raise ValueError(
                "The ref argument can not be None, provide a master or another reference frame."
            )

        return cls(transformation=TT, ref=ref, name=name, rot_config=rot_config)

    @staticmethod
    def fromPoints(points, plane="xy", name=None, usesvd=True, verbose=True):
        """
        fromPoints(points, plane="xy", name=None, usesvd=True,verbose=True)

        Finds the best fitting "plane" plane to all points in "points" and builds a ReferenceFrame
        considering the fitted plane as the 'xy' plane of the new system

        fitPlane must be in ['xy','yz','zx']
        """
        return points.bestFittingPlane(fitPlane=plane, usesvd=usesvd, verbose=verbose)

    @classmethod
    def fromTranslationRotation(
        cls,
        translation,
        rotation,
        ref,
        name=None,
        rot_config=_ROT_CONFIG_DEFAULT,
        active=_ACTIVE_DEFAULT,
        degrees=True,
    ):
        """fromTranslationRotation(cls,translation,rotation, ref=None,name=None, rot_config=_ROT_CONFIG_DEFAULT,active=_ACTIVE_DEFAULT, degrees=True)

        Construct a ReferenceFrame from a translation and a rotation (vectors!)

        translation : translation vector : 3 x 1 = tx, ty, tz
        rotation    : rotation vector    : 3 x 1 = rx, ry, rz

        rot_config : convention for the rotation, see rotationMatrix.__doc__

        degrees : if True, input values are assumed in degrees, otherwise radians
        """
        # Translation
        translation = np.array(translation)
        # Zoom - unit
        zdef = np.array([1, 1, 1])
        # Shear
        sdef = np.array([0, 0, 0])
        # Rotation
        if degrees:
            rotation = np.array([np.deg2rad(item) for item in rotation])
        rotx, roty, rotz = rotation
        #
        rmat = RotationMatrix(rotx, roty, rotz, rot_config=rot_config, active=active)
        #
        # transformation = t3.affines.compose(translation,rmat.R,Z=zdef,S=sdef)

        if ref is None:
            raise ValueError(
                "The ref argument can not be None, provide a master or another reference frame."
            )

        return cls(
            transformation=t3.affines.compose(translation, rmat.R, Z=zdef, S=sdef),
            ref=ref,
            name=name,
            rot_config=rot_config,
        )

    def getTranslationVector(self):
        """
        getTranslationVector()

        Returns the translation defining this reference frame (from self.ref to self)
        """
        return self.transformation[:3, 3]

    def getRotationVector(self, degrees=True, active=_ACTIVE_DEFAULT):
        """
        getRotationVector()

        Returns the rotation (vector) defining this reference frame (from self.ref to self)
        degrees : if true, rotation angles are expressed in degrees
        """
        rotation = t3.euler.mat2euler(self.transformation, axes=self.rot_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        return rotation

    def getTranslationRotationVectors(self, degrees=True, active=_ACTIVE_DEFAULT):
        """getTranslationRotationVectors()
        Returns the translation and rotation (vectors) defining this reference frame (from self.ref to self)
        degrees : if true, rotation angles are expressed in degrees
        """
        translation = self.getTranslationVector()
        rotation = self.getRotationVector(degrees=degrees, active=active)
        return translation, rotation

    def getRotationMatrix(self):
        """
        getRotationMatrix()

        Returns the rotation (matrix) defining this reference frame (from self.ref to self)
        """
        result = self.transformation.copy()
        result[:3, 3] = [0.0, 0.0, 0.0]
        return result

    def __repr__(self):
        return f"ReferenceFrame(transformation={transformationToString(self.transformation)}, ref={self.ref.name}, name={self.name}, rot_config={self.rot_config})"

    def __str__(self):
        msg = textwrap.dedent(
            f"""\
                ReferenceFrame
                name          : {self.name}
                reference     : {self.ref.name}
                rot_config    : {self.rot_config}
                links         : {[key.name for key in self.linkedTo.keys()]}
                transformation:
                  [{np.round(self.transformation[0], 3)}
                   {np.round(self.transformation[1], 3)}
                   {np.round(self.transformation[2], 3)}
                   {np.round(self.transformation[3], 3)}]
                translation   : {np.round(self.getTranslationVector(),3)}
                rotation      : {np.round(self.getRotationVector(),3)}"""
        )
        return msg

    @deprecate(
        reason=(
            "I do not see the added value of changing the name and "
            "the current method has the side effect to change the name "
            "to a random string when the name argument is already used."
        ),
        alternative="the constructor argument to set the name already of the object.",
    )
    def setName(self, name=None):
        """
        Set or change the name of a reference frame.

        ..note: this method is deprecated

        :param str name: the new name for the reference frame, if None, a random name will be generated.

        :raises InvalidOperationError: when you try to change the name of the Master reference frame
        """
        if self.isMaster():
            raise InvalidOperationError(
                "You try to change the name of the Master reference frame, which is not allowed."
            )
        self.name = self.__createName(name)

    def addLink(self, ref, transformation=None, _stop=False):
        """
        adds a link between self and ref in self.linkedTo and ref.linkedTo
        """

        # DONE: set the inverse transformation in the ref to this
        #   ref.linkedTo[self] = t3add.affine_inverse(transformation)
        # TODO:
        #   remove the _stop keyword

        # TODO: deprecate transformation as an input variable
        #       linkedTo can become a list of reference frames, with no transformation
        #       associated to the link. The tfo associated to a link is already
        #       checked in real time whenever the link is addressed
        if transformation is None:
            transformation = self.getActiveTransformationTo(ref)
        else:
            LOGGER.info("Deprecation warning: transformation will be automatically set to "
                        "the current relation between {self.name} and {ref.name}")
            LOGGER.debug("Requested:")
            LOGGER.debug(np.round(transformation, decimals=3))
            LOGGER.debug("Auto (enforced):")

            transformation = self.getActiveTransformationTo(ref)

            LOGGER.debug(np.round(transformation, decimals=3))

        self.linkedTo[ref] = transformation

        # TODO simplify this when transformation is deprecated
        #      it becomes ref.linkedTo[self] = ref.getActiveTransformationTo(self)
        ref.linkedTo[self] = t3add.affine_inverse(transformation)

    def removeLink(self, ref):
        """
        Remove the link between self and ref, both ways.
        """

        # First remove the entry in ref to this

        if self in ref.linkedTo:
            del ref.linkedTo[self]

        # Then remove the entry in this to ref

        if ref in self.linkedTo:
            del self.linkedTo[ref]

    def getPassiveTransformationTo(self, targetFrame):
        """
        getPassiveTransformationTo(self,targetFrame)
        == getPointTransformationTo(self,targetFrame)

        returns the transformation to apply to a Point (defined in self) to express it in targetFrame

        Passive transformation : the point is static, we change the reference frame around it
        """
        LOGGER.debug("PASSIVE TO self {self.name} target {targetFrame.name}")
        if targetFrame is self:
            """
            Nothing to do here, we already have the right coordinates
            """
            LOGGER.debug("case 1")
            result = np.identity(4)

        elif targetFrame.ref is self:
            """
            The target frame is defined in self => the requested transformation is the targetFrame definition
            """
            LOGGER.debug("=== 2 start ===")
            result = t3add.affine_inverse(targetFrame.transformation)
            LOGGER.debug("=== 2 end   ===")
        elif targetFrame.ref is self.ref:
            """
            targetFrame and self are defined wrt the same reference frame
            We want
            self --> targetFrame
            We know
            targetFrame.ref --> targetFrame (= targetFrame.transformation)
            self.ref   --> self   (= self.transformation)
            That is
            self --> self.ref is targetFrame.ref --> targetFrame
            inverse(definition)    targetFrame definition

            """
            LOGGER.debug("=== 3 start ===")
            LOGGER.debug(" ref   \n{0}".format(self.ref))
            LOGGER.debug("===")
            LOGGER.debug("self   \n{0}".format(self))
            LOGGER.debug("===")
            LOGGER.debug("targetFrame \n{0}".format(targetFrame))
            LOGGER.debug("===")

            selfToRef = self.transformation
            LOGGER.debug("selfToRef \n{0}".format(selfToRef))

            # refToRef = I

            refToTarget = t3add.affine_inverse(targetFrame.transformation)
            LOGGER.debug("refToTarget \n{0}".format(refToTarget))

            result = np.dot(refToTarget, selfToRef)
            LOGGER.debug("result \n{0}".format(result))
            LOGGER.debug("=== 3 end   ===")
        else:
            """
            We are after the transformation from
            self --> targetFrame
            ==
            self --> self.ref --> targetFrame.ref --> targetFrame

            We know
            targetFrame.ref --> targetFrame (targetFrame.transformation)
            self.ref        --> self (self.transformation)
            but
            targetFrame.ref != self.ref
            so we need
            self.ref --> targetFrame.ref
            then we can compose
            self --> self.ref --> targetFrame.ref --> targetFrame

            Note: the transformation self.ref --> targetFrame.ref is acquired recursively
                  This relies on the underlying assumption that there exists
                  one unique reference frame that source and self can be linked to
                  (without constraints on the number of links necessary), i.e.
                  that, from a frame to its reference or the opposite, there exists
                  a path between self and targetFrame. That is equivalent to
                  the assumption that the entire set of reference frames is connex,
                  i.e. defined upon a unique master reference frame.
            """
            LOGGER.debug("=== 4 start ===")
            selfToRef = self.transformation
            selfRefToTargetRef = self.ref.getPassiveTransformationTo(targetFrame.ref)
            refToTarget = t3add.affine_inverse(targetFrame.transformation)
            result = np.dot(refToTarget, np.dot(selfRefToTargetRef, selfToRef))
            LOGGER.debug("=== 4 end   ===")

        return result

    def getPassiveTranslationRotationVectorsTo(
        self, targetFrame, degrees=True
    ):  # , active=_ACTIVE_DEFAULT):
        """
        getPassiveTranslationRotationVectorsTo(self,ref,degrees=True)

        extracts rotation vector from the result of getPassiveTransformationTo(target)
        """
        transformation = self.getPassiveTransformationTo(targetFrame)
        rotation = t3.euler.mat2euler(transformation, axes=self.rot_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]
        return translation, rotation

    def getPassiveTranslationVectorTo(self, targetFrame, degrees=True):
        """
        getPassiveTranslationRotationVectorsTo(self,ref,degrees=True)

        extracts translation vector from the result of getPassiveTransformationTo(target)
        """
        return self.getPassiveTranslationRotationVectorsTo(targetFrame, degrees=degrees)[0]

    def getPassiveRotationVectorTo(self, targetFrame, degrees=True):
        """
        getPassiveTranslationRotationVectorsTo(self,targetFrame,degrees=True)

        extracts rotation vector from the result of getPassiveTransformationTo(targetFrame)
        """
        return self.getPassiveTranslationRotationVectorsTo(targetFrame, degrees=degrees)[1]

    def getPassiveTransformationFrom(self, source):
        """
        getPassiveTransformationFrom(self,source)
        ==  getPointTransformationTo(self,source)

        INPUT
        source : is a ReferenceFrame object

        OUTPUT
        returns the transformation matrix  that, applied to a point defined
        in source returns its coordinates in self
        """
        LOGGER.debug("PASSIVE FROM self {self.name} source {source.name}")
        return source.getPassiveTransformationTo(self)

    def getPassiveTranslationRotationVectorsFrom(
        self, source, degrees=True
    ):  # , active=_ACTIVE_DEFAULT):
        """
        getPassiveTranslationRotationVectorsFrom(self,source, degrees=True)

        extracts rotation vector from the result of getPassiveTransformationTo(target)
        """
        transformation = self.getPassiveTransformationFrom(source)
        rotation = t3.euler.mat2euler(transformation, axes=self.rot_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]
        return translation, rotation

    def getPassiveTranslationVectorFrom(self, source, degrees=True):
        """
        getPassiveTranslationVectorFrom(self,source, degrees=True)

        extracts translation vector from the result of getPassiveTransformationFrom(source)
        """
        return self.getPassiveTranslationRotationVectorsFrom(source, degrees=degrees)[0]

    def getPassiveRotationVectorFrom(self, source, degrees=True):
        """
        getPassiveTranslationRotationVectorsFrom(self,source,degrees=True)

        extracts rotation vector from the result of getPassiveTransformationFrom(source)
        """
        return self.getPassiveTranslationRotationVectorsFrom(source, degrees=degrees)[1]

    def getActiveTransformationTo(self, target):
        """
        Return the transformation matrix from this reference frame (``self``) to
        the target reference frame.

        Applying this transformation to the ``self`` ReferenceFrame would render it
        identical to target.

        Applying this transformation to a point defined in ``self`` would move it to
        the same coordinates in target.

        :param target: is a ReferenceFrame object

        :return: the transformation matrix that defines the reference frame ``target``
            in ``self``, the current reference frame. The transformation from self
            to target

        """
        LOGGER.debug("ACTIVE TO self {self.name} target {target.name}")
        return target.getPassiveTransformationTo(self)

    def getActiveTranslationRotationVectorsTo(
        self, targetFrame, degrees=True
    ):  # ,active=_ACTIVE_DEFAULT):
        """
        getActiveTranslationRotationVectorsTo(self,ref,degrees=True)

        extracts rotation vector from the result of getActiveTransformationTo(target)
        """
        transformation = self.getActiveTransformationTo(targetFrame)
        rotation = t3.euler.mat2euler(transformation, axes=self.rot_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]
        return translation, rotation

    def getActiveTranslationVectorTo(self, targetFrame, degrees=True):
        """
        getActiveTranslationRotationVectorsTo(self,ref,degrees=True)

        extracts translation vector from the result of getActiveTransformationTo(target)
        """
        return self.getActiveTranslationRotationVectorsTo(targetFrame, degrees=degrees)[0]

    def getActiveRotationVectorTo(self, targetFrame, degrees=True):
        """
        getActiveTranslationRotationVectorsTo(self,targetFrame,degrees=True)

        extracts rotation vector from the result of getActiveTransformationTo(targetFrame)
        """
        return self.getActiveTranslationRotationVectorsTo(targetFrame, degrees=degrees)[1]

    def getActiveTransformationFrom(self, source):
        """
        Applying this transformation to the ``source`` ReferenceFrame
        would render it identical to self.

        Applying this transformation to a point defined in source
        would move it to the same coordinates in self.

        :param source: is a ReferenceFrame object

        :return: the transformation matrix that defines this reference frame in ``source``,
            i.e. the transformation from ``source`` to ``self``

        """
        LOGGER.debug("ACTIVE FROM self {self.name} source {source.name}")
        return self.getPassiveTransformationTo(source)

    def getActiveTranslationRotationVectorsFrom(
        self, source, degrees=True
    ):  # ,active=_ACTIVE_DEFAULT):
        """
        getActiveTranslationRotationVectorsFrom(self,source, degrees=True)

        extracts rotation vector from the result of getActiveTransformationTo(target)
        """
        transformation = self.getActiveTransformationFrom(source)
        rotation = t3.euler.mat2euler(transformation, axes=self.rot_config)
        if degrees:
            rotation = np.array([np.rad2deg(item) for item in rotation])
        translation = transformation[:3, 3]
        return translation, rotation

    def getActiveTranslationVectorFrom(self, source, degrees=True):
        """
        getActiveTranslationVectorFrom(self,source, degrees=True)

        extracts translation vector from the result of getActiveTransformationFrom(source)
        """
        return self.getActiveTranslationRotationVectorsFrom(source, degrees=degrees)[0]

    def getActiveRotationVectorFrom(self, source, degrees=True):
        """
        getActiveTranslationRotationVectorsFrom(self,source,degrees=True)

        extracts rotation vector from the result of getActiveTransformationFrom(source)
        """
        return self.getActiveTranslationRotationVectorsFrom(source, degrees=degrees)[1]

    def _findEnds(self, frame, visited=[], ends=[], verbose=True, level=1):
        """
        PURPOSE
        Identify the 'linked_frames':
            frames that are linked, either directly or indirectly (via mult. links) to "frame"
            --> returned as visited
        Identify subset of 'linked_frames of which the reference does not belong to linked_frames
            --> returned as 'finalEnds'
        """
        LOGGER.debug(
            f"{level:-2d}{2*level*' '} Current: {frame.name} --  ends: {[f.name for f in ends]} -- visited {[f.name for f in visited]}"
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
            if frame.ref not in frame.linkedTo:
                ends.append(frame)
                LOGGER.debug(f"{(10+2*level)*' '}{frame.name}: new end")
                # if verbose: LOGGER.info(f"{(10+2*level)*' '}{frame.name}: new end")
            for linkedFrame in frame.linkedTo:
                ends, visited = self._findEnds(
                    linkedFrame, visited=visited, ends=ends, verbose=verbose, level=level
                )

        # If frame.ref was linked to frame via an indirect route, reject it
        finalEnds = []
        for aframe in ends:
            if aframe.ref not in ends:
                finalEnds.append(aframe)
        return finalEnds, visited

    def setTransformation(
        self, transformation, updated=None, preserveLinks=True, _relative=False, verbose=True
    ):
        """
        setTransformation(self,transformation, updated=None, preserveLinks=True,_relative=False, verbose=True)

        Alter the definition of this coordinate system

        If other systems are linked to this one, their definition must be updated accordingly
          The link set between two ref. Frames A & B is the active transformation matrix from A to B
          A.addLink(B, matrix)
          A.getActiveTransformationTo(B) --> matrix

        The way to update the definition of the present system, and of those linked to it
        depends on the structure of those links.

        We define
        - the target frame as the one we want to move / redefine
        - 'linkedFrames' as those directly, or indirectly (i.e. via multiple links)
           linked to the target frame
        - endFrames as the subset of linkedFrames which are not linked to their reference (directly or indirectly)
        - sideFrames as the set of frames whose reference is a linkedFrame, but not themselves belonging to the linkedFrames

        We can demonstrate that updating the endFrames (Block A below) is sufficient to represent
        the movement of the target frame and all frames directly or indirectly linked to it.

        This may nevertheless have perverse effects for sideFrames. Indeed,
        their reference will (directly or implicitely) be redefined, but they shouldn't:
        they are not linked to their reference --> their location in space (e.g. wrt the master frame)
        should not be affected by the movement of the target frame. This is the aim of block B.

        For a completely robust solution, 2 steps must be taken
        BLOCK A. apply the rigt transformation to all "endFrames"
        BLOCK B. Check for frames
                       using any of the "visited" frames as a reference
                       not linked to its reference
            Correct its so that it doesn't move (it shouldn't be affected by the requested movement)
            This demands a "referenceFor" array property

        """
        # Ruthless, enforced redefinition of one system. Know what you do, or stay away.
        # Semi-unpredictible side effets if the impacted frame has links!
        if preserveLinks == False:
            self.transformation = transformation
            return

        if updated is None:
            updated = []

        # visitedFrames = all frames which can be reached from self via invariant links
        # endFrames = subset of visitedFrames that are at the end of a chain, and must be updated
        #             in order to properly represent the requested movement
        endFrames, visitedFrames = self._findEnds(frame=self, visited=[], ends=[], verbose=verbose)
        if verbose:
            LOGGER.info(
                f"Visited sub-system                      {[f.name for f in visitedFrames]}"
            )
            LOGGER.info(f"End-frames (movement necessary)         {[f.name for f in endFrames]}")

        # All updates are done by relative movements
        # so we must first compute the relative movement corresponding to the requested absolute movement
        if _relative == False:
            ## virtual = what self should become after the (absolute) movement
            ## it allows to compute the relative transformation to be applied and work in relative further down
            virtual = ReferenceFrame(
                transformation, ref=self.ref, name="virtual", rot_config=self.rot_config
            )
            request = self.getActiveTransformationTo(virtual)
            del virtual
        else:
            # If this method is called by applyTransformation,
            # we are facing a request for a relative movement
            # In that case the input is directly what we want
            request = transformation

        # BLOCK B. Check for frames that were impacted but shouldn't have been and correct them
        # B1. List of frames demanding a correction
        #     'impacted' are frames having their reference inside the rigid structure moving, but not linked to it
        #     If nothing is done, the movement will implicitely displace them, which is not intended

        ### Impacted shall not contain frames that are linked to self (== to any frame in visitedFrames) via any route...
        ### We check if the impacted frames are in visitedFrames:
        ### it is enough to know it's connected to the entire 'solid body' in which self belongs
        impacted = []
        for frame in visitedFrames:
            for child in frame.referenceFor:
                # Version 1 : too simple (restores too many frames)
                #if child not in frame.linkedTo:

                # Version 2 : overkill
                #child_ends, child_visited = child._findEnds(frame=child,visited=[],ends=[],verbose=verbose)
                #if frame not in child_visited:

                # Version 3 : just check if the child belongs to the rigid structure...
                if child not in visitedFrames:
                    impacted.append(child)

        LOGGER.debug(f"Impacted (not moving, defined in moving) {[f.name for f in impacted]}")

        # B2. save the location of all impacted frames
        # tempReference has the only purpose of avoiding that every frame must know the master
        # It could be any frame without links and defined wrt the master, but the master isn't known here...
        # TODO : confirm that the master isn't known (e.g. via cls._MASTER)
        tempMaster = self.findMaster()
        toRestore = {}
        for frame in impacted:
            toRestore[frame] = ReferenceFrame(
                frame.getActiveTransformationFrom(tempMaster),
                ref=tempMaster,
                name=frame.name + "toRestore",
                rot_config=frame.rot_config,
            )

        # BLOCK A. apply the rigt transformation to all "endFrames"
        """
        ### Ensure that "Untouched" remains unaffected regardless of the update order of the endFrames
        selfUntouched = ReferenceFrame(
            transformation = self.getActiveTransformationFrom(tempMaster),
            ref=tempMaster,
            name=self.name + "_fixed",
            rot_config=self.rot_config,
        )
        """

        selfUntouched = ReferenceFrame(
            transformation=self.transformation,
            ref=self.ref,
            name=self.name + "_fixed",
            rot_config=self.rot_config,
        )

        for bottom in endFrames:

            up = bottom.getActiveTransformationTo(selfUntouched)
            down = selfUntouched.getActiveTransformationTo(bottom)

            relativeTransformation = up @ request @ down

            LOGGER.debug(
                f"\nAdjusting {bottom.name} to {self.name}\nUpdated {[i.name for i in updated]}"
            )
            LOGGER.debug(f"\ninput transformation \n{np.round(transformation,3)}")
            LOGGER.debug(
                f"\nup \n{np.round(up,3)}\ntransformation\n{np.round(request,3)}\ndown\n{np.round(down,3)}"
            )
            LOGGER.debug(f"\nrelativeTransformation \n{np.round(relativeTransformation,3)}")

            bottom.transformation = bottom.transformation @ relativeTransformation

            updated.append(bottom)

        for frame in visitedFrames:
            if frame not in updated:
                updated.append(frame)

        # Block B
        # B3. Correction
        # we must set preserveLinks to False to prevent cascading impact from this update
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

        for frame in toRestore:
            frame.transformation = frame.ref.getActiveTransformationTo(toRestore[frame])

        del toRestore

        return

    def setTranslationRotation(
        self,
        translation,
        rotation,
        rot_config=_ROT_CONFIG_DEFAULT,
        active=_ACTIVE_DEFAULT,
        degrees=True,
        preserveLinks=True,
    ):
        """
        setTranslationRotation(self,translation,rotation,rot_config=_ROT_CONFIG_DEFAULT, active=_ACTIVE_DEFAULT, degrees=True, preserveLinks=True)

        Same as setTransformation, but input = translation and rotation vectors rather than affine transformation matrix
        """
        # Translation
        translation = np.array(translation)
        # Zoom - unit
        zdef = np.array([1, 1, 1])
        # Shear
        sdef = np.array([0, 0, 0])
        # Rotation
        if degrees:
            rotation = np.array([np.deg2rad(item) for item in rotation])

        rotx, roty, rotz = rotation

        rmat = RotationMatrix(rotx, roty, rotz, rot_config=rot_config, active=active)

        LOGGER.debug(t3.affines.compose(translation, rmat.R, Z=zdef, S=sdef))

        transformation = t3.affines.compose(translation, rmat.R, Z=zdef, S=sdef)

        self.setTransformation(transformation, preserveLinks=preserveLinks, _relative=False)
        return

    def applyTransformation(self, transformation, updated=None, preserveLinks=True):
        """
        applyTransformation(self,transformation)

        Applies the transformation to the current reference frame's definition

        self.transformation := transformation @ self.transformation
        """
        if updated is None:
            updated = []

        self.setTransformation(
            transformation=transformation,
            updated=updated,
            preserveLinks=preserveLinks,
            _relative=True,
        )

    def applyTranslationRotation(
        self,
        translation,
        rotation,
        rot_config=None,
        active=_ACTIVE_DEFAULT,
        degrees=True,
        preserveLinks=True,
    ):
        """
        applyTranslationRotation(self,translation,rotation,rot_config=None,active=_ACTIVE_DEFAULT,degrees=True, preserveLinks=True)

        Builds transformation from input translation and rotation, then applies this transformation
        """
        if rot_config is None:
            rot_config = self.rot_config

        # Translation
        translation = np.array(translation)
        # Zoom - unit
        zdef = np.array([1, 1, 1])
        # Shear
        sdef = np.array([0, 0, 0])
        # Rotation
        if degrees:
            rotation = np.array([np.deg2rad(item) for item in rotation])
        rotx, roty, rotz = rotation
        #
        rmat = RotationMatrix(rotx, roty, rotz, rot_config=rot_config, active=active)
        #
        transformation = t3.affines.compose(translation, rmat.R, Z=zdef, S=sdef)
        #
        self.applyTransformation(transformation, preserveLinks=preserveLinks)
        return

    def getAxis(self, axis, name=None):
        """
        INPUT
        axis : in ['x','y','z']

        OUTPUT
        Returns an object of class Point, corresponding to the vector defining
        the axis of choice in self.
        The output can be used with the Point methods to express that axis in any reference frame
        """
        haxis = {}
        haxis["x"] = [1, 0, 0]
        haxis["y"] = [0, 1, 0]
        haxis["z"] = [0, 0, 1]
        if name is None:
            name = self.name + axis
        return Point(haxis[axis], ref=self, name=name)

    def getNormal(self, name=None):
        """
        getNormal(self,name=None)

        Returns a unit vector normal to the X-Y plane (= [0,0,1] = getAxis('z'))
        """
        return Point([0, 0, 1], ref=self, name=name)

    def getOrigin(self, name=None):
        """
        OUTPUT
        Returns an object of class Point, corresponding to the vector defining the origin in 'self', i.e. [0,0,0]
        The output can be used with the Point methods to express that axis in any reference frame
        """
        return Point([0, 0, 0], ref=self, name=name)

    def is_master(self):
        return self.isMaster()

    def isMaster(self):
        """
        A Master reference frame is a reference frame that refers to itself, and the
        transformation is the Identity matrix.
        """
        tr = self.transformation

        if (
            (self.name == self.ref.name)
            and (tr.shape[0] == tr.shape[1])
            and np.allclose(tr, np.eye(tr.shape[0]))
        ):
            return True
        return False

    def isSame(self, other):
        """
        Returns True if the two reference frames are the same except for their name.

        Two Reference Frames are considered the same when:

        * their transformation matrices are equal
        * the reference frame is equal
        * the rot_config is equal
        * the name may be different

        .. todo:: This needs further work and testing!
        """

        if other is self:
            LOGGER.debug(
                "self and other are the same object (beware: this message might occur with recursion from self.ref != self.other)"
            )
            return True

        if isinstance(other, ReferenceFrame):
            LOGGER.debug(f"comparing {self.name} and {other.name}")
            if not np.array_equal(self.transformation, other.transformation):
                LOGGER.debug("self.transformation not equals other.transformation")
                return False
            if self.rot_config != other.rot_config:
                LOGGER.debug("self.rot_config not equals other.rot_config")
                return False
            # The following tests are here to prevent recursion to go infinite when self and other
            # point to itself
            if self.ref is self and other.ref is other:
                LOGGER.debug("both self.ref and other.ref point to themselves")
                pass
            else:
                LOGGER.debug("one of self.ref or other.ref doesn't points to itself")
                if self.ref != other.ref:
                    LOGGER.debug("self.ref not equals other.ref")
                    return False
            if self.name is not other.name:
                LOGGER.debug(
                    f"When checking two reference frames for equality, only their names differ: '{self.name}' not equals '{other.name}'"
                )
                pass
            return True
        return NotImplemented

    def __eq__(self, other):
        """
        Overrides the default implementation, which basically checks for id(self) == id(other).

        Two Reference Frames are considered equal when:

        * their transformation matrices are equal
        * the reference frame is equal
        * the rot_config is equal
        * do we want to insist on the name being equal?
          YES - for strict testing
          NO  - this might need a new method like isSame(self, other) where the criteria are relaxed


        .. todo:: This needs further work and testing!
        """

        if other is self:
            LOGGER.debug(
                "self and other are the same object (beware: this message might occur with recursion from self.ref != self.other)"
            )
            return True

        if isinstance(other, ReferenceFrame):
            LOGGER.debug(f"comparing {self.name} and {other.name}")
            if not np.array_equal(self.transformation, other.transformation):
                LOGGER.debug("self.transformation not equals other.transformation")
                return False
            if self.rot_config != other.rot_config:
                LOGGER.debug("self.rot_config not equals other.rot_config")
                return False
            # The following tests are here to prevent recursion to go infinite when self and other
            # point to itself
            if self.ref is self and other.ref is other:
                LOGGER.debug("both self.ref and other.ref point to themselves")
                pass
            else:
                LOGGER.debug("one of self.ref or other.ref doesn't points to itself")
                if self.ref != other.ref:
                    LOGGER.debug("self.ref not equals other.ref")
                    return False
            if self.name is not other.name:
                LOGGER.debug(
                    f"When checking two reference frames for equality, only their names differ: '{self.name}' not equals '{other.name}'"
                )
                return False
            return True
        return NotImplemented

    def __hash__(self):
        """Overrides the default implementation"""
        hash_number = (id(self.rot_config) + id(self.ref) + id(self.name)) // 16
        return hash_number

    def __copy__(self):

        LOGGER.debug(
            f'Copying {self!r} unless {self.name} is "Master" in which case the Master itself is returned.'
        )

        if self.isMaster():
            LOGGER.debug(f"Returning Master itself instead of a copy.")
            return self

        return ReferenceFrame(self.transformation, self.ref, self.name, self.rot_config)
