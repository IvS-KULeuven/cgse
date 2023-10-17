#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jun 25 16:25:33 2018

@author: pierre
"""
import numpy
import numpy as np
import math
import transforms3d as t3

from egse.coordinates.rotationMatrix import RotationMatrix

def affine_isEuclidian(matrix):
    """
    Tests if a matrix is a pure solid-body euclidian rotation + translation (no shear or scaling)
    
    We only need to check that 
    . the rotation part is orthogonal : R @ R.T = I
    . the det(R) = 1  (=> this is not a reflexion) 
    """
    rotation = matrix[:3,:3]
    return np.allclose((rotation @ rotation.T),np.identity(3)) & np.allclose(np.linalg.det(matrix),1)

def affine_inverse(matrix):
    """
    affine_inverse(matrix)
    
    WARNING: 
    This is NOT a generic inversion of an affine transformation matrix
    
    This returns the affine transformation inverting that produced by the input matrix, 
    
    ASSSUMING that only rotation and translation were involved 
    in the affine transformation, no zoom, no shear!
    
    That preserves the fact that the orthogonal property of the part of the input matrix
    corresponding to rotation => the inverse is simply the transpose.
    
    Pierre Royer
    """
    #import numpy as np

    # Extract Rotation matrix and translation vector from input affine transformation
    R = matrix[:3,:3]
    t = matrix[:3,3]
    #
    # Invert the rotation and the translation
    Rinv = R.T
    tinv = -t
    #
    # The inverse affine is composed from R^-1 for the rotation and -(R^-1 . t) for the translation
    result = np.identity(4)
    result[:3,:3] = Rinv
    result[:3,3]  = np.dot(Rinv,tinv)
    
    if affine_isEuclidian(result):
        return result
    else:
        print("WARNING: This is not a rigid-body transformation matrix")
        #print(f"R.T-based  (.6f) = \n {np.round(result,6)}")
        #print(f"np.inverse (.6f) = \n {np.round(np.linalg.inv(matrix),6)}")
        return np.linalg.inv(matrix)

def affine_matrix_from_points(v0, v1, shear=False, scale=False, usesvd=True):
    """affine_matrix_from_points(v0, v1, shear=False, scale=False, usesvd=True)
    Return affine transform matrix to register two point sets.

    v0 and v1 are shape (ndims, \*) arrays of at least ndims non-homogeneous
    coordinates, where ndims is the dimensionality of the coordinate space.

    If shear is False, a similarity transformation matrix is returned.
    If also scale is False, a rigid/Euclidean transformation matrix
    is returned.

    By default the algorithm by Hartley and Zissermann [15] is used.
    If usesvd is True, similarity and Euclidean transformation matrices
    are calculated by minimizing the weighted sum of squared deviations
    (RMSD) according to the algorithm by Kabsch [8].
    Otherwise, and if ndims is 3, the quaternion based algorithm by Horn [9]
    is used, which is slower when using this Python implementation.

    The returned matrix performs rotation, translation and uniform scaling
    (if specified).

    >>> v0 = [[0, 1031, 1031, 0], [0, 0, 1600, 1600]]
    >>> v1 = [[675, 826, 826, 677], [55, 52, 281, 277]]
    >>> affine_matrix_from_points(v0, v1)
    array([[   0.14549,    0.00062,  675.50008],
           [   0.00048,    0.14094,   53.24971],
           [   0.     ,    0.     ,    1.     ]])
    >>> T = translation_matrix(numpy.random.random(3)-0.5)
    >>> R = random_rotation_matrix(numpy.random.random(3))
    >>> S = scale_matrix(random.random())
    >>> M = concatenate_matrices(T, R, S)
    >>> v0 = (numpy.random.rand(4, 100) - 0.5) * 20
    >>> v0[3] = 1
    >>> v1 = numpy.dot(M, v0)
    >>> v0[:3] += numpy.random.normal(0, 1e-8, 300).reshape(3, -1)
    >>> M = affine_matrix_from_points(v0[:3], v1[:3])
    >>> numpy.allclose(v1, numpy.dot(M, v0))
    True

    More examples in superimposition_matrix()

    Author: this function was extracted from the original transformations.py 
            written by Christoph Golke:
            https://www.lfd.uci.edu/~gohlke/code/transformations.py.html
            
    usesvd controls the use of a method based on Singular Value Decomposition (SVD)
    --> when True, it is equivalent to rigid_transform_3D (see below)

    """
    import numpy
    v0 = numpy.array(v0, dtype=numpy.float64, copy=True)
    v1 = numpy.array(v1, dtype=numpy.float64, copy=True)

    ndims = v0.shape[0]
    if ndims < 2 or v0.shape[1] < ndims or v0.shape != v1.shape:
        print(f"ndims {ndims} v0/1.shape {v0.shape} {v1.shape} v0/1 class {v0.__class__} {v1.__class__}")
        raise ValueError('input arrays are of wrong shape or type')

    # move centroids to origin
    t0 = -numpy.mean(v0, axis=1)
    M0 = numpy.identity(ndims+1)
    M0[:ndims, ndims] = t0
    v0 += t0.reshape(ndims, 1)
    t1 = -numpy.mean(v1, axis=1)
    M1 = numpy.identity(ndims+1)
    M1[:ndims, ndims] = t1
    v1 += t1.reshape(ndims, 1)

    if shear:
        # Affine transformation
        A = numpy.concatenate((v0, v1), axis=0)
        u, s, vh = numpy.linalg.svd(A.T)
        vh = vh[:ndims].T
        B = vh[:ndims]
        C = vh[ndims:2*ndims]
        t = numpy.dot(C, numpy.linalg.pinv(B))
        t = numpy.concatenate((t, numpy.zeros((ndims, 1))), axis=1)
        M = numpy.vstack((t, ((0.0,)*ndims) + (1.0,)))
    elif usesvd or ndims != 3:
        # Rigid transformation via SVD of covariance matrix
        u, s, vh = numpy.linalg.svd(numpy.dot(v1, v0.T))
        # rotation matrix from SVD orthonormal bases
        R = numpy.dot(u, vh)
        if numpy.linalg.det(R) < 0.0:
            # R does not constitute right handed system
            R -= numpy.outer(u[:, ndims-1], vh[ndims-1, :]*2.0)
            s[-1] *= -1.0
        # homogeneous transformation matrix
        M = numpy.identity(ndims+1)
        M[:ndims, :ndims] = R
    else:
        # Rigid transformation matrix via quaternion
        # compute symmetric matrix N
        xx, yy, zz = numpy.sum(v0 * v1, axis=1)
        xy, yz, zx = numpy.sum(v0 * numpy.roll(v1, -1, axis=0), axis=1)
        xz, yx, zy = numpy.sum(v0 * numpy.roll(v1, -2, axis=0), axis=1)
        N = [[xx+yy+zz, 0.0,      0.0,      0.0],
             [yz-zy,    xx-yy-zz, 0.0,      0.0],
             [zx-xz,    xy+yx,    yy-xx-zz, 0.0],
             [xy-yx,    zx+xz,    yz+zy,    zz-xx-yy]]
        # quaternion: eigenvector corresponding to most positive eigenvalue
        w, V = numpy.linalg.eigh(N)
        q = V[:, numpy.argmax(w)]
        q /= _vector_norm(q)  # unit quaternion
        # homogeneous transformation matrix
        M = _quaternion_matrix(q)

    if scale and not shear:
        # Affine transformation; scale is ratio of RMS deviations from centroid
        v0 *= v0
        v1 *= v1
        M[:ndims, :ndims] *= math.sqrt(numpy.sum(v1) / numpy.sum(v0))

    # move centroids back
    M = numpy.dot(numpy.linalg.inv(M1), numpy.dot(M, M0))
    M /= M[ndims, ndims]
    return M


def _vector_norm(data, axis=None, out=None):
    """Return length, i.e. Euclidean norm, of ndarray along axis.

    >>> v = numpy.random.random(3)
    >>> n = vector_norm(v)
    >>> numpy.allclose(n, numpy.linalg.norm(v))
    True
    >>> v = numpy.random.rand(6, 5, 3)
    >>> n = vector_norm(v, axis=-1)
    >>> numpy.allclose(n, numpy.sqrt(numpy.sum(v*v, axis=2)))
    True
    >>> n = vector_norm(v, axis=1)
    >>> numpy.allclose(n, numpy.sqrt(numpy.sum(v*v, axis=1)))
    True
    >>> v = numpy.random.rand(5, 4, 3)
    >>> n = numpy.empty((5, 3))
    >>> vector_norm(v, axis=1, out=n)
    >>> numpy.allclose(n, numpy.sqrt(numpy.sum(v*v, axis=1)))
    True
    >>> vector_norm([])
    0.0
    >>> vector_norm([1])
    1.0
    
    This function is called by affine_matrix_from_points when usesvd=False

    Author: this function was extracted from the original transformations.py 
            written by Christoph Golke:
            https://www.lfd.uci.edu/~gohlke/code/transformations.py.html

    """
    data = numpy.array(data, dtype=numpy.float64, copy=True)
    if out is None:
        if data.ndim == 1:
            return math.sqrt(numpy.dot(data, data))
        data *= data
        out = numpy.atleast_1d(numpy.sum(data, axis=axis))
        numpy.sqrt(out, out)
        return out
    else:
        data *= data
        numpy.sum(data, axis=axis, out=out)
        numpy.sqrt(out, out)


def _quaternion_matrix(quaternion):
    """Return homogeneous rotation matrix from quaternion.

    >>> M = quaternion_matrix([0.99810947, 0.06146124, 0, 0])
    >>> numpy.allclose(M, rotation_matrix(0.123, [1, 0, 0]))
    True
    >>> M = quaternion_matrix([1, 0, 0, 0])
    >>> numpy.allclose(M, numpy.identity(4))
    True
    >>> M = quaternion_matrix([0, 1, 0, 0])
    >>> numpy.allclose(M, numpy.diag([1, -1, -1, 1]))
    True

    This function is called by affine_matrix_from_points when usesvd=False

    Author: this function was extracted from the original transformations.py 
            written by Christoph Golke:
            https://www.lfd.uci.edu/~gohlke/code/transformations.py.html
    """
    _EPS = np.finfo(float).eps * 5
    
    q = numpy.array(quaternion, dtype=numpy.float64, copy=True)
    n = numpy.dot(q, q)
    if n < _EPS:
        return numpy.identity(4)
    q *= math.sqrt(2.0 / n)
    q = numpy.outer(q, q)
    return numpy.array([
        [1.0-q[2, 2]-q[3, 3],     q[1, 2]-q[3, 0],     q[1, 3]+q[2, 0], 0.0],
        [    q[1, 2]+q[3, 0], 1.0-q[1, 1]-q[3, 3],     q[2, 3]-q[1, 0], 0.0],
        [    q[1, 3]-q[2, 0],     q[2, 3]+q[1, 0], 1.0-q[1, 1]-q[2, 2], 0.0],
        [                0.0,                 0.0,                 0.0, 1.0]])


def rigid_transform_3D(fromA, toB, verbose=True):
    """rigid_transform_3D(fromA, toB, verbose=True)
    
    INPUT
    Afrom, Bto 3xn arrays = xyz coords of n points to be registered
    
    OUTPUT
    Rotation + translation transformation matrix registering fromA into toB
    
    Author : Nghia Ho - 2013 - http://nghiaho.com/?page_id=671
            "Finding optimal rotation and translation between corresponding 3D points"
             Based on "A Method for Registration of 3-D Shapes", by Besl and McKay, 1992.
             
    This is based on Singular Value Decomposition (SVD) 
    --> it is equivalent to affine_matrix_from_points with parameter usesvd=True
    """
    A = fromA.T
    B = toB.T
    
    assert len(A) == len(B)
    
    N = A.shape[0]; # total points

    centroid_A = np.mean(A, axis=0)
    centroid_B = np.mean(B, axis=0)
    
    # centre the points
    AA = A - np.tile(centroid_A, (N, 1))
    BB = B - np.tile(centroid_B, (N, 1))
    
    # @ is matrix multiplication for array
    H = np.transpose(AA) @ BB
    
    U, S, Vt = np.linalg.svd(H)
    
    R = Vt.T @ U.T
    
    # special reflection case
    if np.linalg.det(R) < 0:
       print ("Reflection detected")
       Vt[2,:] *= -1
       R = Vt.T @ U.T
       
    t = -R @ centroid_A.T + centroid_B.T
    
    result = np.identity(4)
    result[:3,:3] = R
    result[:3,3]  = t
    
    return result


def translationRotationToTransformation(translation,rotation,rot_config="sxyz",active=True,degrees=True,translationFirst=False):
    """
    translationRotationToTransformation(translation,rotation,rot_config="sxyz",active=True,degrees=True,translationFirst=False)
    
    translationFirst : translation first
             False first 3 rows of transformation matrix = (R   t) [usual convention and default here]
             True  first 3 rows of transformation matrix = (R  Rt) [used in the hexapod]
    """
    import transforms3d as t3
    import numpy as np
    # Zoom - unit
    zdef = np.array([1,1,1])
    # Shear
    sdef = np.array([0,0,0])
    translation = np.array(translation)
    #if degrees: rotation = np.deg2rad(np.array(rotation))
    if degrees: rotation = np.array([np.deg2rad(item) for item in rotation])
    rotx,roty,rotz = rotation
    rmat = RotationMatrix(rotx,roty,rotz,rot_config=rot_config,active=active)
    #
    if translationFirst:
        result = np.identity(4)
        result[:3,:3] = rmat.R
        result[:3,3]  = rmat.R @ translation
    else:
        result = t3.affines.compose(translation,rmat.R,Z=zdef,S=sdef)
    return result

def translationRotationFromTransformation(transformation,rot_config="sxyz",active=True,degrees=True,translationFirst=False):
    """
    translationRotationFromTransformation(transformation,rot_config="sxyz",active=True,degrees=True,translationFirst=False)
    
    translationFirst : translation first
             False first 3 rows of transformation matrix = (R   t) [usual convention and default here]
             True  first 3 rows of transformation matrix = (R  Rt) [used in the hexapod]
    """
    translation = transformation[:3,3]
    rotation = t3.euler.mat2euler(transformation,axes=rot_config)
    if degrees: rotation = np.array([np.rad2deg(item) for item in rotation])
    if translationFirst:
        translation = transformation[:3,:3].T @ translation
    return translation,rotation

tr2T = translationRotationToTransformation
T2tr = translationRotationFromTransformation


def vectorPlaneIntersection(pt, frame, epsilon=1.e-6):
    """
    return the coordinates of the intersection of a vector with a plane.

    pt = input vector. Point object, expressing the vector
         vector origin = pt.ref.getOrigin().coordinates[:3]
         vector direction = pt.coordinates[:3]
    frame = input plane. ReferenceFrame object whose x-y plane is the target plane for intersection

    If the vector's own reference frame is 'frame', the problem is trivial

    In all cases, the coordinates of the interesection point are provided as a Point object, in "frame" coordinates

    Ref:
    https://stackoverflow.com/questions/5666222/3d-line-plane-intersection
    """

    from egse.coordinates.point import Point

    if pt.ref == frame:
        # The point is defined in frame => the origin of the vector is the origin of the target plane.
        return np.array([0,0,0])
    else:
        # Express all inputs in 'frame'

        # Vector Origin (p0)
        vec_orig = Point(pt.ref.getOrigin().coordinates[:3],ref=pt.ref, name='ptorig').expressIn(frame)[:3]
        # Vector End (p1)
        vec_end  = pt.expressIn(frame)[:3]
        # Vector (u)
        vec = vec_end - vec_orig

        # A point in Plane (pco)
        #plane_orig = np.array([0,0,0],dtype=float)
        plane_orig = frame.getOrigin().coordinates[:3]
        # Normal to the plane (pno)
        plane_normal = frame.getAxis('z').coordinates[:3]

        # Vector to normal 'angle'
        vec_x_normal = np.dot(vec, plane_normal)

        # Test if there is an intersection (and if it's unique)
        # --> input vector and normal mustn't be perpendicular, else the vector is // to the plane or inside it
        #
        if (np.allclose(vec_x_normal, 0., atol=epsilon)):
            print('The input vector is // to the plane normal (or inside the plane)')
            print('--> there exists no intersection (or an infinity of them)')
            return None
        else:
            # Vector from the point in the plane to the origin of the vector (w)
            plane_to_vec = vec_orig - plane_orig

            # Solution  ("how many 'vectors' away is the interesection ?")
            vec_multiplicator = - np.dot(plane_normal, plane_to_vec) / vec_x_normal

            return Point(vec_orig + (vec * vec_multiplicator), ref=frame)

