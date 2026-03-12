import logging

import numpy as np
import pytest
import transforms3d as t3
from pytest import approx

from egse.coordinates.reference_frame import ReferenceFrame
from egse.coordinates.rotation_matrix import RotationMatrix
from egse.exceptions import InvalidOperationError

LOGGER = logging.getLogger(__name__)


def test_master_construction():
    # This frame "refers to", i.e. it "is defined in", itself

    master = ReferenceFrame.create_master()

    assert np.array_equal(master.transformation, np.identity(4))
    assert master.name == "Master"
    assert master.reference_frame is master
    assert master.reference_frame == master
    assert master.rotation_config == "sxyz"


def test_link_to_master():
    master = ReferenceFrame.create_master()
    rot_config = "sxyz"

    glfix = ReferenceFrame(
        transformation=np.identity(4), reference_frame=master, name="glfix", rotation_config=rot_config
    )
    glfix.add_link(master, transformation=np.identity(4))

    assert not glfix.is_master()
    assert glfix.linked_to
    assert master.linked_to


def test_invalid_constructions():
    # We used to create a master frame when ref is None, but that is no longer supported.

    with pytest.raises(ValueError) as ve:
        ReferenceFrame(transformation=None, reference_frame=None)
    assert ve.value.args[1] == "REF_IS_NONE"

    # ref shall be a reference frame object

    with pytest.raises(ValueError) as ve:
        ReferenceFrame(transformation=None, reference_frame="MyReference")
    assert ve.value.args[1] == "REF_IS_NOT_CLS"

    # Master is a reserved name for the MASTER reference frame

    with pytest.raises(ValueError) as ve:
        master = ReferenceFrame.create_master()
        ReferenceFrame(transformation=None, reference_frame=master, name="Master")
    assert ve.value.args[1] == "MASTER_NAME_USED"

    # Master is a reserved name for the MASTER reference frame

    with pytest.raises(ValueError) as ve:
        master = ReferenceFrame.create_master()
        ReferenceFrame(transformation=[], reference_frame=master)
    assert ve.value.args[1] == "TRANSFORMATION_IS_NOT_NDARRAY"


def test_str():
    master = ReferenceFrame.create_master()

    assert str(master)


def test_repr():
    master = ReferenceFrame.create_master()

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

    master = ReferenceFrame.create_master()

    # In the current implementation of __eq__ all these reference frames will be
    # different because their name is different (and we cannot create two reference
    # frames with the same name).

    a1 = ReferenceFrame.from_translation(1, 1, 1, reference_frame=master, name="A1")
    a2 = ReferenceFrame.from_translation(1, 1, 1, reference_frame=master, name="A2")

    b1 = ReferenceFrame.from_translation(2, 0, 0, reference_frame=a1, name="B1")
    b2 = ReferenceFrame.from_translation(2, 0, 0, reference_frame=a2, name="B2")

    # Put the ReferenceFrames in a set (muttable), uses hashes
    frames = {master, a1, b1}  # __hash__ called three times
    assert master in frames  # __hash__ called once

    # Put the ReferenceFrames in a dict (muttable), uses hashes
    frames = {master: master, a1: a1, b1: b1}  # __hash__ called three times
    assert master in frames  # __hash__ called once

    assert master == master
    assert hash(master) == hash(master)


def test_add_link():
    master = ReferenceFrame.create_master()
    A = ReferenceFrame.from_translation(1, 1, 1, reference_frame=master, name="A")
    B = ReferenceFrame.from_translation(2, 0, 0, reference_frame=A, name="B")

    B.add_link(A, transformation=B.transformation)

    assert A in B.linked_to
    assert B in A.linked_to
    assert master not in A.linked_to
    assert master not in B.linked_to


def test_random_name():
    # The Master should have "Master" as its name
    master = ReferenceFrame.create_master()
    assert not master.name.startswith("F")

    # Any other reference frame that is not given a name should start with 'F'
    ref = ReferenceFrame.from_translation(1.0, 2.0, 3.0, reference_frame=master)
    assert ref.name.startswith("F")


def test_set_name():
    master = ReferenceFrame.create_master()
    with pytest.raises(InvalidOperationError):
        master.set_name("MyMaster")

    ref = ReferenceFrame.from_translation(1.0, 2.0, 3.0, reference_frame=master)
    assert ref.name != "Basic Translation"
    ref.set_name("Basic Translation")
    assert ref.name == "Basic Translation"


def test_translation():
    master = ReferenceFrame.create_master()

    # define a reference frame that is translated by 2 in Y

    transx, transy, transz = 0, 2, 0
    adef = np.identity(4)
    adef[:3, 3] = [transx, transy, transz]
    a = ReferenceFrame(transformation=adef, reference_frame=master, name="A")
    assert a is not None

    b = ReferenceFrame.from_translation(transx, transy, transz, master, name="B")
    assert b is not None

    assert np.array_equal(a.get_translation_vector(), b.get_translation_vector())
    assert a.reference_frame is b.reference_frame
    assert a is not b
    assert a != b
    assert a.is_same(b)


def test_rotation():
    master = ReferenceFrame.create_master()

    # Convention (rotating axes, in order xyz)

    rot_config = "rxyz"

    # Rotation amplitude

    rotx, roty, rotz = 0, 0, np.pi / 4.0

    rotation = RotationMatrix(rotx, roty, rotz, rot_config, active=True)

    # Defaults for zoom & shear

    zoom = np.array([1, 1, 1])
    shear = np.array([0, 0, 0])

    translation = [0, 0, 0]
    TT = t3.affines.compose(T=translation, R=rotation.rotation_matrix, Z=zoom, S=shear)

    # D is rotated wrt master

    D = ReferenceFrame(transformation=TT, reference_frame=master, name="D")

    E = ReferenceFrame.from_rotation(rotx, roty, rotz, master, rotation_config=rot_config, name="E", degrees=False)

    assert np.array_equal(D.get_rotation_matrix(), E.get_rotation_matrix())

    F = ReferenceFrame.from_rotation(rotx, roty, 45.0, reference_frame=master)

    assert np.array_equal(D.get_rotation_matrix(), F.get_rotation_matrix())
    assert F.is_same(D)


def test_equals():
    master = ReferenceFrame.create_master()

    assert master is master
    assert master == master

    m1 = ReferenceFrame.create_master()
    m2 = ReferenceFrame.create_master()

    assert m1 is not master
    assert m1 == master
    assert m1 is not m2
    assert m1 == m2

    t1 = ReferenceFrame.from_translation(1, 2, 3, reference_frame=master)
    t2 = ReferenceFrame.from_translation(1, 2, 3, reference_frame=master)
    t3 = ReferenceFrame.from_translation(1, 2, 3, reference_frame=master, name=t2.name)
    t4 = ReferenceFrame.from_translation(2, 3, 4, reference_frame=master)
    t5 = ReferenceFrame.from_translation(2, 3, 4, reference_frame=m1)
    t6 = ReferenceFrame.from_translation(2, 3, 4, reference_frame=t2)

    assert t1 != t2
    assert t1 is not t2
    assert t1.is_same(t2)
    assert t2.is_same(t1)
    assert t1 != t3
    # t3 will be given another random generated name as t2.name exists already,
    # i.e. no two reference frames can have the same name
    # !! This rule has been relaxed and we now allow two or even more ReferenceFrames with the
    # !! same name, therefore != changed into ==
    assert t2 == t3
    assert t2.name == t3.name
    assert t2.is_same(t3)
    assert not t3.is_same(t4)
    assert t5 != t4
    assert t4.is_same(t5)
    assert t6 != t4  # different ref
    assert not t5.is_same(t6)

    r1 = ReferenceFrame.from_rotation(1, 2, 3, reference_frame=master)
    r2 = ReferenceFrame.from_rotation(1, 2, 3, reference_frame=master)
    r3 = ReferenceFrame.from_rotation(1, 2, 3, reference_frame=master, name=r2.name)
    r4 = ReferenceFrame.from_rotation(2, 3, 4, reference_frame=master)
    r5 = ReferenceFrame.from_rotation(2, 3, 4, reference_frame=m2)
    r6 = ReferenceFrame.from_rotation(2, 3, 4, reference_frame=r2)

    assert r1 != r2
    assert r1 is not r2
    assert r1.is_same(r2)
    assert r2.is_same(r1)
    assert r1 != r3
    # t3 will be given another random generated name as t2.name exists already,
    # i.e. no two reference frames can have the same name
    # !! This rule has been relaxed and we now allow two or even more ReferenceFrames with the
    # !! same name, therefore != changed into ==
    assert r2 == r3
    assert r2.is_same(r3)
    assert r2.name == r3.name
    assert r4 != r5
    assert r4.is_same(r5)
    assert r5 != r6  # different ref
    assert not r5.is_same(r6)

    assert master != "any other object"


def test_copy():
    import copy

    master = ReferenceFrame.create_master()

    assert master is copy.copy(master)
    assert master == copy.copy(master)

    r = ReferenceFrame.from_translation(1, 2, 3, reference_frame=master)

    assert r is not copy.copy(r)

    # This next test changed from != into == since we have relaxed the rule on
    # unique naming of ReferenceFrames
    assert r == copy.copy(r)

    assert r.is_same(copy.copy(r))


def test_position_after_homing():
    # Rotation around static axis, and around x, y and z in that order

    rot_config = "sxyz"

    # Use degrees in all arguments

    degrees = True

    # Configure representations of the coordinate systems of the hexapod
    # Configure the following reference frames: master, mec, usr, plt, obj, obusr
    # Configure invariant links between those reference frames

    master = ReferenceFrame.create_master()

    # MEC = MASTER
    mec = ReferenceFrame(transformation=np.identity(4), reference_frame=master, name="mec", rotation_config=rot_config)

    # USR, defined in MEC
    tr_u = np.array([0, 0, 0])
    rot_u = np.array([0, 0, 0])

    usr = ReferenceFrame.from_translation_rotation(
        tr_u, rot_u, rotation_config=rot_config, reference_frame=mec, name="usr", degrees=degrees
    )

    # PLATFORM (default after homing: PLT = MEC)
    plt = ReferenceFrame(transformation=np.identity(4), reference_frame=mec, name="plt", rotation_config=rot_config)

    # OBJECT, defined wrt PLATFORM
    tr_o = np.array([0, 0, 0])
    rot_o = np.array([0, 0, 0])
    obj = ReferenceFrame.from_translation_rotation(
        tr_o, rot_o, rotation_config=rot_config, reference_frame=plt, name="obj", degrees=degrees
    )

    # OBUSR == OBJ, but defined wrt USR  (OBJ is defined in PLT) --> used in moveAbsolute
    transfo = usr.get_active_transformation_to(obj)
    obusr = ReferenceFrame(transfo, rotation_config=rot_config, reference_frame=usr, name="obusr")

    # Configure the invariant links within the system

    # Link OBUSR to OBJ
    # OBUSR = OBJ ==> the link is the identity matrix
    obusr.add_link(obj, transformation=np.identity(4))

    # Link PLT to OBJ
    # The link is the definition of OBJ given above

    transformation = obj.transformation
    plt.add_link(obj, transformation=transformation)

    # Link USR to MEC
    # The link is the definition of USR given above

    transformation = usr.transformation
    mec.add_link(usr, transformation=transformation)

    # Now perfom the actual tests.

    # Check system status before any movement, i.e. the default initialization state

    out = plt.get_translation_rotation_vectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = obusr.get_translation_rotation_vectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = usr.get_active_translation_rotation_vectors_to(obusr)
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])

    # Configure movement

    tx, ty, tz = [5, 2, 0]
    rx, ry, rz = [0, 0, 0]

    tr_abs = np.array([tx, ty, tz])
    rot_abs = np.array([rx, ry, rz])

    obusr.set_translation_rotation(
        tr_abs, rot_abs, rotation_config=rot_config, active=True, degrees=True, preserve_links=True
    )

    out = plt.get_translation_rotation_vectors()
    check_positions(np.reshape(out, 6), [5, 2, 0, 0, 0, 0])
    out = obusr.get_translation_rotation_vectors()
    check_positions(np.reshape(out, 6), [5, 2, 0, 0, 0, 0])
    out = usr.get_active_translation_rotation_vectors_to(obusr)
    check_positions(np.reshape(out, 6), [5, 2, 0, 0, 0, 0])

    # Perform a Homing, i.e. goto position zero

    tx, ty, tz = [0, 0, 0]
    rx, ry, rz = [0, 0, 0]

    tr_abs = np.array([tx, ty, tz])
    rot_abs = np.array([rx, ry, rz])

    # See issue #58
    # plt.setTranslationRotation(tr_abs,rot_abs,rot_config=rot_config, active=True, degrees=True,preserveLinks=True)

    tr_abs, rot_abs = obj.get_translation_rotation_vectors()
    obusr.set_translation_rotation(
        tr_abs, rot_abs, rotation_config=rot_config, active=True, degrees=True, preserve_links=True
    )

    out = plt.get_translation_rotation_vectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = obusr.get_translation_rotation_vectors()
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])
    out = usr.get_active_translation_rotation_vectors_to(obusr)
    check_positions(np.reshape(out, 6), [0, 0, 0, 0, 0, 0])


def test_linked_to_reference():
    master = ReferenceFrame.create_master()

    translation = [0, 2, 0]
    Adef = np.identity(4)
    Adef[:3, 3] = translation
    A1 = ReferenceFrame(transformation=Adef, reference_frame=master, name="A1")
    A2 = ReferenceFrame(transformation=Adef, reference_frame=master, name="A2")

    # C
    translation = [2, 0, 0]
    Cdef = np.identity(4)
    Cdef[:3, 3] = translation
    C = ReferenceFrame(transformation=Cdef, reference_frame=master, name="C")

    # B
    translation = [2, 0, 0]
    Bdef = np.identity(4)
    Bdef[:3, 3] = translation
    B1 = ReferenceFrame(transformation=Bdef, reference_frame=A1, name="B1")
    B2 = ReferenceFrame(transformation=Bdef, reference_frame=A2, name="B2")

    # Frame D is defined in C
    translation = [2, 0, 0]
    rotation = [0, 0, 45]
    degrees = True
    D = ReferenceFrame.from_translation_rotation(
        translation=translation, rotation=rotation, reference_frame=C, name="D", degrees=degrees
    )

    B1.add_link(A1, transformation=B1.transformation)

    translation = [0, 0, 0]
    rotation = [0, 0, 45]
    A1.apply_translation_rotation(translation, rotation, active=True, degrees=True)
    A2.apply_translation_rotation(translation, rotation, active=True, degrees=True)

    assert A1.is_same(A2)
    assert not B1.is_same(B2)


def check_positions(out, expected, precision=0.00001):
    assert len(out) == len(expected)

    for idx, element in enumerate(out):
        assert element == approx(expected[idx], precision)
