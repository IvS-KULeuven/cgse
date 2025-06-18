import logging

import numpy as np
import pytest
import transforms3d as t3
from pytest import approx

from egse.coordinates.referenceFrame import ReferenceFrame
from egse.coordinates.rotationMatrix import RotationMatrix
from egse.exceptions import InvalidOperationError

LOGGER = logging.getLogger(__name__)


def test_master_construction():
    # This frame "refers to", i.e. it "is defined in", itself

    master = ReferenceFrame.createMaster()

    assert np.array_equal(master.transformation, np.identity(4))
    assert master.name == "Master"
    assert master.ref is master
    assert master.ref == master
    assert master.rot_config == "sxyz"


def test_link_to_master():
    master = ReferenceFrame.createMaster()
    rot_config = "sxyz"

    glfix = ReferenceFrame(transformation=np.identity(4), ref=master, name="glfix", rot_config=rot_config)
    glfix.addLink(master, transformation=np.identity(4))

    assert not glfix.isMaster()
    assert glfix.linkedTo
    assert master.linkedTo


def test_invalid_constructions():
    # We used to create a master frame when ref is None, but that is no longer supported.

    with pytest.raises(ValueError) as ve:
        ReferenceFrame(transformation=None, ref=None)
    assert ve.value.args[1] == "REF_IS_NONE"

    # ref shall be a reference frame object

    with pytest.raises(ValueError) as ve:
        ReferenceFrame(transformation=None, ref="MyReference")
    assert ve.value.args[1] == "REF_IS_NOT_CLS"

    # Master is a reserved name for the MASTER reference frame

    with pytest.raises(ValueError) as ve:
        master = ReferenceFrame.createMaster()
        ReferenceFrame(transformation=None, ref=master, name="Master")
    assert ve.value.args[1] == "MASTER_NAME_USED"

    # Master is a reserved name for the MASTER reference frame

    with pytest.raises(ValueError) as ve:
        master = ReferenceFrame.createMaster()
        ReferenceFrame(transformation=[], ref=master)
    assert ve.value.args[1] == "TRANSFORMATION_IS_NOT_NDARRAY"


def test_str():
    master = ReferenceFrame.createMaster()

    assert str(master)


def test_repr():
    master = ReferenceFrame.createMaster()

    assert repr(master) != str(master)

    # We want repr() to always return just one line

    assert "\n" not in repr(master)


def test_hash():
    # Any hash function MUST satisfy the following properties:
    #
    # - If two object are equal, then their hashes should be equal, i.e.
    #   a == b implies hash(a) == hash(b)
    #
    #   note: hash(a) == hash(b) does NOT imply a == b (which is a hash collision)
    #
    # - In order for an object to be hashable, it must be 'immutable', i.e. the
    #   hash of an object does not change across the object's lifetime
    #
    # For good hash functions, the following properties should be implemented:
    #
    # - If two objects have the same hash, then they are likely to be the same object
    #
    # - The hash of an object should be cheap to compute
    #
    # Check out this great article:
    #
    # What happens when you mess with hashing in Python [https://www.asmeurer.com/blog/posts/what-happens-when-you-mess-with-hashing-in-python/]

    master = ReferenceFrame.createMaster()

    # In the current implementation of __eq__ all these reference frames will be
    # different because their name is different (and we cannot create two reference
    # frames with the same name).

    A1 = ReferenceFrame.fromTranslation(1, 1, 1, ref=master, name="A1")
    A2 = ReferenceFrame.fromTranslation(1, 1, 1, ref=master, name="A2")

    B1 = ReferenceFrame.fromTranslation(2, 0, 0, ref=A1, name="B1")
    B2 = ReferenceFrame.fromTranslation(2, 0, 0, ref=A2, name="B2")

    # Put the ReferenceFrames in a set (muttable), uses hashes
    frames = {master, A1, B1}  # __hash__ called three times
    assert master in frames  # __hash__ called once

    # Put the ReferenceFrames in a dict (muttable), uses hashes
    frames = {master: master, A1: A1, B1: B1}  # __hash__ called three times
    assert master in frames  # __hash__ called once

    assert master == master
    assert hash(master) == hash(master)


def test_add_link():
    master = ReferenceFrame.createMaster()
    A = ReferenceFrame.fromTranslation(1, 1, 1, ref=master, name="A")
    B = ReferenceFrame.fromTranslation(2, 0, 0, ref=A, name="B")

    B.addLink(A, transformation=B.transformation)

    assert A in B.linkedTo
    assert B in A.linkedTo
    assert master not in A.linkedTo
    assert master not in B.linkedTo


def test_random_name():
    # The Master should have "Master" as its name
    master = ReferenceFrame.createMaster()
    assert not master.name.startswith("F")

    # Any other reference frame that is not given a name should start with 'F'
    ref = ReferenceFrame.fromTranslation(1.0, 2.0, 3.0, ref=master)
    assert ref.name.startswith("F")


def test_set_name():
    master = ReferenceFrame.createMaster()
    with pytest.raises(InvalidOperationError):
        master.setName("MyMaster")

    ref = ReferenceFrame.fromTranslation(1.0, 2.0, 3.0, ref=master)
    assert ref.name != "Basic Translation"
    ref.setName("Basic Translation")
    assert ref.name == "Basic Translation"


def test_translation():
    master = ReferenceFrame.createMaster()

    # define a reference frame that is translated by 2 in Y

    transx, transy, transz = 0, 2, 0
    adef = np.identity(4)
    adef[:3, 3] = [transx, transy, transz]
    A = ReferenceFrame(transformation=adef, ref=master, name="A")
    assert A is not None

    B = ReferenceFrame.fromTranslation(transx, transy, transz, master, name="B")
    assert B is not None

    assert np.array_equal(A.getTranslationVector(), B.getTranslationVector())
    assert A.ref is B.ref
    assert A is not B
    assert A != B
    assert A.isSame(B)


def test_rotation():
    master = ReferenceFrame.createMaster()

    # Convention (rotating axes, in order xyz)

    rot_config = "rxyz"

    # Rotation amplitude

    rotx, roty, rotz = 0, 0, np.pi / 4.0

    rotation = RotationMatrix(rotx, roty, rotz, rot_config, active=True)

    # Defaults for zoom & shear

    zdef = np.array([1, 1, 1])
    sdef = np.array([0, 0, 0])

    translation = [0, 0, 0]
    TT = t3.affines.compose(T=translation, R=rotation.R, Z=zdef, S=sdef)

    # D is rotated wrt master

    D = ReferenceFrame(transformation=TT, ref=master, name="D")

    E = ReferenceFrame.fromRotation(rotx, roty, rotz, master, rot_config=rot_config, name="E", degrees=False)

    assert np.array_equal(D.getRotationMatrix(), E.getRotationMatrix())

    F = ReferenceFrame.fromRotation(rotx, roty, 45.0, ref=master)

    assert np.array_equal(D.getRotationMatrix(), F.getRotationMatrix())
    assert F.isSame(D)


def test_equals():
    master = ReferenceFrame.createMaster()

    assert master is master
    assert master == master

    m1 = ReferenceFrame.createMaster()
    m2 = ReferenceFrame.createMaster()

    assert m1 is not master
    assert m1 == master
    assert m1 is not m2
    assert m1 == m2

    t1 = ReferenceFrame.fromTranslation(1, 2, 3, ref=master)
    t2 = ReferenceFrame.fromTranslation(1, 2, 3, ref=master)
    t3 = ReferenceFrame.fromTranslation(1, 2, 3, ref=master, name=t2.name)
    t4 = ReferenceFrame.fromTranslation(2, 3, 4, ref=master)
    t5 = ReferenceFrame.fromTranslation(2, 3, 4, ref=m1)
    t6 = ReferenceFrame.fromTranslation(2, 3, 4, ref=t2)

    assert t1 != t2
    assert t1 is not t2
    assert t1.isSame(t2)
    assert t2.isSame(t1)
    assert t1 != t3
    # t3 will be given another random generated name as t2.name exists already,
    # i.e. no two reference frames can have the same name
    # !! This rule has been relaxed and we now allow two or even more ReferenceFrames with the
    # !! same name, therefore != changed into ==
    assert t2 == t3
    assert t2.name == t3.name
    assert t2.isSame(t3)
    assert not t3.isSame(t4)
    assert t5 != t4
    assert t4.isSame(t5)
    assert t6 != t4  # different ref
    assert not t5.isSame(t6)

    r1 = ReferenceFrame.fromRotation(1, 2, 3, ref=master)
    r2 = ReferenceFrame.fromRotation(1, 2, 3, ref=master)
    r3 = ReferenceFrame.fromRotation(1, 2, 3, ref=master, name=r2.name)
    r4 = ReferenceFrame.fromRotation(2, 3, 4, ref=master)
    r5 = ReferenceFrame.fromRotation(2, 3, 4, ref=m2)
    r6 = ReferenceFrame.fromRotation(2, 3, 4, ref=r2)

    assert r1 != r2
    assert r1 is not r2
    assert r1.isSame(r2)
    assert r2.isSame(r1)
    assert r1 != r3
    # t3 will be given another random generated name as t2.name exists already,
    # i.e. no two reference frames can have the same name
    # !! This rule has been relaxed and we now allow two or even more ReferenceFrames with the
    # !! same name, therefore != changed into ==
    assert r2 == r3
    assert r2.isSame(r3)
    assert r2.name == r3.name
    assert r4 != r5
    assert r4.isSame(r5)
    assert r5 != r6  # different ref
    assert not r5.isSame(r6)

    assert master != "any other object"


def test_copy():
    import copy

    master = ReferenceFrame.createMaster()

    assert master is copy.copy(master)
    assert master == copy.copy(master)

    r = ReferenceFrame.fromTranslation(1, 2, 3, ref=master)

    assert r is not copy.copy(r)

    # This next test changed from != into == since we have relaxed the rule on
    # unique naming of ReferenceFrames
    assert r == copy.copy(r)

    assert r.isSame(copy.copy(r))


def test_positionAfterHoming():
    # Rotation around static axis, and around x, y and z in that order

    rot_config = "sxyz"

    # Use degrees in all arguments

    degrees = True

    # Configure representations of the coordinate systems of the hexapod
    # Configure the following reference frames: master, mec, usr, plt, obj, obusr
    # Configure invariant links between those reference frames

    master = ReferenceFrame.createMaster()

    # MEC = MASTER
    mec = ReferenceFrame(transformation=np.identity(4), ref=master, name="mec", rot_config=rot_config)

    # USR, defined in MEC
    tr_u = np.array([0, 0, 0])
    rot_u = np.array([0, 0, 0])

    usr = ReferenceFrame.fromTranslationRotation(
        tr_u, rot_u, rot_config=rot_config, ref=mec, name="usr", degrees=degrees
    )

    # PLATFORM (default after homing: PLT = MEC)
    plt = ReferenceFrame(transformation=np.identity(4), ref=mec, name="plt", rot_config=rot_config)

    # OBJECT, defined wrt PLATFORM
    tr_o = np.array([0, 0, 0])
    rot_o = np.array([0, 0, 0])
    obj = ReferenceFrame.fromTranslationRotation(
        tr_o, rot_o, rot_config=rot_config, ref=plt, name="obj", degrees=degrees
    )

    # OBUSR == OBJ, but defined wrt USR  (OBJ is defined in PLT) --> used in moveAbsolute
    transfo = usr.getActiveTransformationTo(obj)
    obusr = ReferenceFrame(transfo, rot_config=rot_config, ref=usr, name="obusr")

    # Configure the invariant links within the system

    # Link OBUSR to OBJ
    # OBUSR = OBJ ==> the link is the identity matrix
    obusr.addLink(obj, transformation=np.identity(4))

    # Link PLT to OBJ
    # The link is the definition of OBJ given above

    transformation = obj.transformation
    plt.addLink(obj, transformation=transformation)

    # Link USR to MEC
    # The link is the definition of USR given above

    transformation = usr.transformation
    mec.addLink(usr, transformation=transformation)

    # Now perfom the actual tests.

    # Check system status before any movement, i.e. the default initialization state

    out = plt.getTranslationRotationVectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = obusr.getTranslationRotationVectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = usr.getActiveTranslationRotationVectorsTo(obusr)
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])

    # Configure movement

    tx, ty, tz = [5, 2, 0]
    rx, ry, rz = [0, 0, 0]

    tr_abs = np.array([tx, ty, tz])
    rot_abs = np.array([rx, ry, rz])

    obusr.setTranslationRotation(tr_abs, rot_abs, rot_config=rot_config, active=True, degrees=True, preserveLinks=True)

    out = plt.getTranslationRotationVectors()
    check_positions(np.reshape(out, 6), [5, 2, 0, 0, 0, 0])
    out = obusr.getTranslationRotationVectors()
    check_positions(np.reshape(out, 6), [5, 2, 0, 0, 0, 0])
    out = usr.getActiveTranslationRotationVectorsTo(obusr)
    check_positions(np.reshape(out, 6), [5, 2, 0, 0, 0, 0])

    # Perform a Homing, i.e. goto position zero

    tx, ty, tz = [0, 0, 0]
    rx, ry, rz = [0, 0, 0]

    tr_abs = np.array([tx, ty, tz])
    rot_abs = np.array([rx, ry, rz])

    # See issue #58
    # plt.setTranslationRotation(tr_abs,rot_abs,rot_config=rot_config, active=True, degrees=True,preserveLinks=True)

    tr_abs, rot_abs = obj.getTranslationRotationVectors()
    obusr.setTranslationRotation(tr_abs, rot_abs, rot_config=rot_config, active=True, degrees=True, preserveLinks=True)

    out = plt.getTranslationRotationVectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = obusr.getTranslationRotationVectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = usr.getActiveTranslationRotationVectorsTo(obusr)
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])


def test_linked_to_reference():
    master = ReferenceFrame.createMaster()

    translation = [0, 2, 0]
    Adef = np.identity(4)
    Adef[:3, 3] = translation
    A1 = ReferenceFrame(transformation=Adef, ref=master, name="A1")
    A2 = ReferenceFrame(transformation=Adef, ref=master, name="A2")

    # C
    translation = [2, 0, 0]
    Cdef = np.identity(4)
    Cdef[:3, 3] = translation
    C = ReferenceFrame(transformation=Cdef, ref=master, name="C")

    # B
    translation = [2, 0, 0]
    Bdef = np.identity(4)
    Bdef[:3, 3] = translation
    B1 = ReferenceFrame(transformation=Bdef, ref=A1, name="B1")
    B2 = ReferenceFrame(transformation=Bdef, ref=A2, name="B2")

    # Frame D is defined in C
    translation = [2, 0, 0]
    rotation = [0, 0, 45]
    degrees = True
    D = ReferenceFrame.fromTranslationRotation(
        translation=translation, rotation=rotation, ref=C, name="D", degrees=degrees
    )

    B1.addLink(A1, transformation=B1.transformation)

    translation = [0, 0, 0]
    rotation = [0, 0, 45]
    A1.applyTranslationRotation(translation, rotation, active=True, degrees=True)
    A2.applyTranslationRotation(translation, rotation, active=True, degrees=True)

    assert A1.isSame(A2)
    assert not B1.isSame(B2)


def check_positions(out, expected, precision=0.00001):
    assert len(out) == len(expected)

    for idx, element in enumerate(out):
        assert element == approx(expected[idx], precision)
