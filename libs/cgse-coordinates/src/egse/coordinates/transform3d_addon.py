import numpy as np
import math
import transforms3d as t3

from egse.coordinates.rotation_matrix import RotationMatrix


def affine_is_euclidian(matrix: np.ndarray) -> bool:
    """Checks if the given matrix is a pure solid-body Euclidian rotation + translation (no shear or scaling).

    We only need to check that:
        - The rotation part is orthogonal : R @ R.T = I
        - The det(R) = 1  (to check that the matrix does not represent a reflection)

    Args:
        matrix (np.ndarray): Matrix to check.

    Returns:
        True if the matrix is a pure solid-body Euclidian rotation + translation, False otherwise.
    """

    rotation = matrix[:3, :3]

    return np.allclose((rotation @ rotation.T), np.identity(3)) & np.allclose(np.linalg.det(matrix), 1)


def affine_inverse(matrix):
    """Returns the inverse of the given affine matrix.

    We assume that the given matrix is an affine transformation matrix that only involves rotation and translation,
    no zoom, no shear!  That is why we can invert it by simply transposing the rotation part and negating the
    translation part.

    Args:
        matrix (np.ndarray): Augmented matrix to invert.

    Returns:
        Inverted affine matrix.
    """

    if affine_is_euclidian(matrix):
        # Separate the given augmented matrix into rotation and translation

        rotation = matrix[:3, :3]
        translation = matrix[:3, 3]

        # Invert the rotation and the translation

        inverse_rotation = rotation.T
        inverse_translation = -translation

        # The inverse affine matrix is composed of
        #   - Rotation: R^-1
        #   - Translation: -(R^-1 . t)

        result = np.identity(4)
        result[:3, :3] = inverse_rotation
        result[:3, 3] = np.dot(inverse_rotation, inverse_translation)

        return result

    else:
        print("WARNING: This is not a rigid-body transformation matrix")
        # print(f"R.T-based  (.6f) = \n {np.round(result,6)}")
        # print(f"np.inverse (.6f) = \n {np.round(np.linalg.inv(matrix),6)}")
        return np.linalg.inv(matrix)


def affine_matrix_from_points(
    v0: np.ndarray, v1: np.ndarray, shear: bool = False, scale: bool = False, use_svd: bool = True
) -> np.ndarray:
    """Computes the homogeneous affine transform matrix that best maps one set of points to another.

    Returns affine transform matrix to register two point sets.

    v0 and v1 are shape (ndims, \*) arrays of at least ndims non-homogeneous
    coordinates, where ndims is the dimensionality of the coordinate space.

    If shear is False, a similarity transformation matrix is returned.
    If also scale is False, a rigid/Euclidean transformation matrix
    is returned.

    By default, the algorithm by Hartley and Zissermann [15] is used.
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
    >>> T = translation_matrix(np.random.random(3)-0.5)
    >>> R = random_rotation_matrix(np.random.random(3))
    >>> S = scale_matrix(random.random())
    >>> M = concatenate_matrices(T, R, S)
    >>> v0 = (np.random.rand(4, 100) - 0.5) * 20
    >>> v0[3] = 1
    >>> v1 = np.dot(M, v0)
    >>> v0[:3] += np.random.normal(0, 1e-8, 300).reshape(3, -1)
    >>> M = affine_matrix_from_points(v0[:3], v1[:3])
    >>> np.allclose(v1, np.dot(M, v0))
    True

    More examples in superimposition_matrix()

    References: This function was extracted from the original transformations.py written by Christoph Golke:
                https://www.lfd.uci.edu/~gohlke/code/transformations.py.html

    Args:
        v0 (np.ndarray): Set of points to transform.
        v1 (np.ndarray): Set of points to transform to.
        shear (bool): Indicates whether a full affine transform is allowed (i.e. incl. shear).
        scale (bool): Indicates whether a full affine transform is allowed (i.e. incl. zoom).
        use_svd (bool): Indicates whether to use SVD-base solution (Singular Value Decomposition) for
                        rigid/similarity transformations.  If False and ndims = 3, the quaternion-based solution is used.

    Returns:
        Best affine transformation matrix to map `v0` to `v1`.
    """

    v0 = np.array(v0, dtype=np.float64, copy=True)
    v1 = np.array(v1, dtype=np.float64, copy=True)

    num_dimensions = v0.shape[0]
    if num_dimensions < 2 or v0.shape[1] < num_dimensions or v0.shape != v1.shape:
        print(
            f"num_dimensions {num_dimensions} v0/1.shape {v0.shape} {v1.shape} v0/1 class {v0.__class__} {v1.__class__}"
        )
        raise ValueError("input arrays are of wrong shape or type")

    # First set of coordinates

    t0 = -np.mean(v0, axis=1)  # Move centroids to origin
    v0 += t0.reshape(num_dimensions, 1)
    matrix_0 = np.identity(num_dimensions + 1)
    matrix_0[:num_dimensions, num_dimensions] = t0  # (I | t0)

    # Second set of coordinates

    t1 = -np.mean(v1, axis=1)  # Move centroids to origin
    v1 += t1.reshape(num_dimensions, 1)
    matrix_1 = np.identity(num_dimensions + 1)
    matrix_1[:num_dimensions, num_dimensions] = t1  # (I | t1)

    if shear:
        # Affine transformation
        A = np.concatenate((v0, v1), axis=0)
        svd_u, svd_s, svd_vh = np.linalg.svd(A.T)  # Singular Value Decomposition -> U, S, Vh
        svd_vh = svd_vh[:num_dimensions].T
        B = svd_vh[:num_dimensions]
        C = svd_vh[num_dimensions : 2 * num_dimensions]
        t = np.dot(C, np.linalg.pinv(B))
        t = np.concatenate((t, np.zeros((num_dimensions, 1))), axis=1)
        M = np.vstack((t, ((0.0,) * num_dimensions) + (1.0,)))

    elif use_svd or num_dimensions != 3:
        # Rigid transformation via SVD of covariance matrix
        svd_u, svd_s, svd_vh = np.linalg.svd(np.dot(v1, v0.T))
        # rotation matrix from SVD orthonormal bases
        R = np.dot(svd_u, svd_vh)
        if np.linalg.det(R) < 0.0:
            # R does not constitute right-handed system
            R -= np.outer(svd_u[:, num_dimensions - 1], svd_vh[num_dimensions - 1, :] * 2.0)
            svd_s[-1] *= -1.0
        # homogeneous transformation matrix
        M = np.identity(num_dimensions + 1)
        M[:num_dimensions, :num_dimensions] = R

    else:
        # Rigid transformation matrix via quaternion
        # compute symmetric matrix N
        xx, yy, zz = np.sum(v0 * v1, axis=1)
        xy, yz, zx = np.sum(v0 * np.roll(v1, -1, axis=0), axis=1)
        xz, yx, zy = np.sum(v0 * np.roll(v1, -2, axis=0), axis=1)
        N = [
            [xx + yy + zz, 0.0, 0.0, 0.0],
            [yz - zy, xx - yy - zz, 0.0, 0.0],
            [zx - xz, xy + yx, yy - xx - zz, 0.0],
            [xy - yx, zx + xz, yz + zy, zz - xx - yy],
        ]
        # quaternion: eigenvector corresponding to most positive eigenvalue
        eigenvalues, eigenvectors = np.linalg.eigh(N)
        quaternion = eigenvectors[:, np.argmax(eigenvalues)]
        quaternion /= _vector_norm(quaternion)  # Normalised quaternion
        # Quaternion -> Homogeneous rotation matrix
        M = quaternion_matrix(quaternion)

    if scale and not shear:
        # Affine transformation; scale is ratio of RMS deviations from centroid
        v0 *= v0
        v1 *= v1
        M[:num_dimensions, :num_dimensions] *= math.sqrt(np.sum(v1) / np.sum(v0))

    # Move centroids back
    M = np.dot(np.linalg.inv(matrix_1), np.dot(M, matrix_0))
    M /= M[num_dimensions, num_dimensions]

    return M


def _vector_norm(data: np.ndarray, axis: str | None = None, out=None):
    """Returns the length, i.e. Euclidean norm, of the given array along the given axis.

    >>> v = np.random.random(3)
    >>> n = vector_norm(v)
    >>> np.allclose(n, np.linalg.norm(v))
    True
    >>> v = np.random.rand(6, 5, 3)
    >>> n = vector_norm(v, axis=-1)
    >>> np.allclose(n, np.sqrt(np.sum(v*v, axis=2)))
    True
    >>> n = vector_norm(v, axis=1)
    >>> np.allclose(n, np.sqrt(np.sum(v*v, axis=1)))
    True
    >>> v = np.random.rand(5, 4, 3)
    >>> n = np.empty((5, 3))
    >>> vector_norm(v, axis=1, out=n)
    >>> np.allclose(n, np.sqrt(np.sum(v*v, axis=1)))
    True
    >>> vector_norm([])
    0.0
    >>> vector_norm([1])
    1.0

    This function is called by affine_matrix_from_points when usesvd=False

    References: This function was extracted from the original transformations.py written by Christoph Golke:
                https://www.lfd.uci.edu/~gohlke/code/transformations.py.html

    """

    data = np.array(data, dtype=np.float64, copy=True)

    if out is None:
        if data.ndim == 1:
            return math.sqrt(np.dot(data, data))
        data *= data
        out = np.atleast_1d(np.sum(data, axis=axis))
        np.sqrt(out, out)

        return out
    else:
        data *= data
        np.sum(data, axis=axis, out=out)
        return np.sqrt(out, out)


def quaternion_matrix(quaternion: np.ndarray):
    """Returns the homogeneous rotation matrix from the given quaternion.

    >>> M = quaternion_matrix([0.99810947, 0.06146124, 0, 0])
    >>> np.allclose(M, rotation_matrix(0.123, [1, 0, 0]))
    True
    >>> M = quaternion_matrix([1, 0, 0, 0])
    >>> np.allclose(M, np.identity(4))
    True
    >>> M = quaternion_matrix([0, 1, 0, 0])
    >>> np.allclose(M, np.diag([1, -1, -1, 1]))
    True

    This function is called by affine_matrix_from_points when usesvd=False

    References: This function was extracted from the original transformations.py written by Christoph Golke:
                https://www.lfd.uci.edu/~gohlke/code/transformations.py.html

    Args:
        quaternion (np.ndarray): Quaternion to convert to a rotation matrix.

    Returns:
        Homogeneous rotation matrix corresponding to the given quaternion.
    """

    _EPS = np.finfo(float).eps * 5

    q = np.array(quaternion, dtype=np.float64, copy=True)
    n = np.dot(q, q)

    if n < _EPS:
        return np.identity(4)

    q *= math.sqrt(2.0 / n)
    q = np.outer(q, q)
    return np.array(
        [
            [1.0 - q[2, 2] - q[3, 3], q[1, 2] - q[3, 0], q[1, 3] + q[2, 0], 0.0],
            [q[1, 2] + q[3, 0], 1.0 - q[1, 1] - q[3, 3], q[2, 3] - q[1, 0], 0.0],
            [q[1, 3] - q[2, 0], q[2, 3] + q[1, 0], 1.0 - q[1, 1] - q[2, 2], 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )


def rigid_transform_3d(dataset_a: np.ndarray, dataset_b: np.ndarray):
    """Returns best translation and rotation to align points in dataset A to points in dataset B.

    Args:
        dataset_a (np.ndarray): First 3xn dataset of points (dataset A).
        dataset_b (np.ndarray): Second 3xn dataset of points (dataset B).

    References: Nghia Ho - 2013 - http://nghiaho.com/?page_id=671
                "Finding optimal rotation and translation between corresponding 3D points"
                Based on "A Method for Registration of 3-D Shapes", by Besl and McKay, 1992.

    This is based on Singular Value Decomposition (SVD)
    -> It is equivalent to affine_matrix_from_points with parameter use_svd=True

    Returns:
        Transformation matrix to align points in dataset A to points in dataset B.
    """

    dataset_a_transposed = dataset_a.T
    dataset_b_transposed = dataset_b.T

    assert len(dataset_a_transposed) == len(dataset_b_transposed)

    num_points = dataset_a_transposed.shape[0]  # Total points

    centroid_a = np.mean(dataset_a_transposed, axis=0)
    centroid_b = np.mean(dataset_b_transposed, axis=0)

    # Centre the points
    a_centered = dataset_a_transposed - np.tile(centroid_a, (num_points, 1))
    b_centered = dataset_b_transposed - np.tile(centroid_b, (num_points, 1))

    # @ is matrix multiplication for array
    covariance_matrix = np.transpose(a_centered) @ b_centered  # Covariance matrix H

    svd_u, svd_s, svd_vh = np.linalg.svd(covariance_matrix)  # SVD(H) = [U, S, V]

    rotation = svd_vh.T @ svd_u.T  # Rotation matrix R

    # Special reflection case
    # There’s a special case when finding the rotation matrix that you have to take care of. Sometimes the SVD will
    # return a "reflection" matrix, which is numerically correct but is actually nonsense in real life. This is
    # addressed by checking the determinant of R (from SVD above) and seeing if it’s negative (-1). If it is then the
    # 3rd column of V is multiplied by -1.

    if np.linalg.det(rotation) < 0:
        print("Reflection detected")
        svd_vh[2, :] *= -1
        rotation = svd_vh.T @ svd_u.T

    translation = -rotation @ centroid_a.T + centroid_b.T

    result = np.identity(4)
    result[:3, :3] = rotation
    result[:3, 3] = translation

    return result


def translation_rotation_to_transformation(
    translation: np.ndarray,
    rotation: np.ndarray,
    rotation_config: str = "sxyz",
    active: bool = True,
    degrees: bool = True,
    translation_first: bool = False,
):
    """Returns the transformation matrix from the given translation and rotation.

    Args:
        translation (np.ndarray): Translation vector.
        rotation (np.ndarray): Rotation vector.
        rotation_config (str): Order in which the rotation about the three axes are chained.
        active (bool): Indicates if the rotation is active (object rotates IN a fixed coordinate system) or passive
                           (coordinate system rotates AROUND a fixed object).  Even if two angles are zero, the match
                           between angle orders and rot_config is still critical
        degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        translation_first (bool): Indicates the order of the translation and rotation in the transformation matrix.
                                  False if the first three rows of the transformation matrix are (R t). This is the
                                  usual convention.
                                  True if the first three rows of the transformation matrix are (R Rt).  This is used
                                  in the hexapod.

    Returns:
        Transformation matrix corresponding to the given translation and rotation.
    """

    zoom = np.array([1, 1, 1])
    shear = np.array([0, 0, 0])
    translation = np.array(translation)
    if degrees:
        rotation = np.array([np.deg2rad(item) for item in rotation])
    rotation_x, rotation_y, rotation_z = rotation
    rotation_matrix = RotationMatrix(rotation_x, rotation_y, rotation_z, rotation_config=rotation_config, active=active)

    if translation_first:
        result = np.identity(4)
        result[:3, :3] = rotation_matrix.rotation_matrix
        result[:3, 3] = rotation_matrix.rotation_matrix @ translation
    else:
        result = t3.affines.compose(translation, rotation_matrix.rotation_matrix, Z=zoom, S=shear)

    return result


def translation_rotation_from_transformation(
    transformation: np.ndarray,
    rotation_config: str = "sxyz",
    active: bool = True,
    degrees: bool = True,
    translation_first: bool = False,
):
    """Extracts the translation and rotation vector from the given transformation matrix.

    Args:
    transformation (np.ndarray): Transformation matrix.
    rotation_config (str): Order in which the rotation about the three axes are chained.
    active (bool): Indicates if the rotation is active (object rotates IN a fixed coordinate system) or passive
                       (coordinate system rotates AROUND a fixed object).  Even if two angles are zero, the match
                       between angle orders and rot_config is still critical
    degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
    translation_first (bool): Indicates the order of the translation and rotation in the transformation matrix.
                              False if the first three rows of the transformation matrix are (R t). This is the
                              usual convention.
                              True if the first three rows of the transformation matrix are (R Rt).  This is used
                              in the hexapod.

    Returns:
        Translation and rotation vector for the given transformation matrix.
    """

    translation = transformation[:3, 3]
    rotation = t3.euler.mat2euler(transformation, axes=rotation_config)
    if degrees:
        rotation = np.array([np.rad2deg(item) for item in rotation])
    if translation_first:
        translation = transformation[:3, :3].T @ translation

    return translation, rotation


tr2t = translation_rotation_to_transformation
t2tr = translation_rotation_from_transformation


def vector_plane_intersection(vector, frame, epsilon=1.0e-6):
    """Returns the coordinates of the insection of a vector with a plane.

    The origin of the input vector is:
        vector.reference_frame.get_origin().coordinates[:3]

    The direction of the input vector is:
        vector.coordinates[:3]

    In all cases, the coordinates of the intersection point are provided as a Point object, in "frame" coordinates

    Args:
        vector (Vector): Input vector.
        frame (ReferenceFrame): Reference frame for which the xy-plane is the target plane for intersection.
        epsilon (float):


    References:
        https://stackoverflow.com/questions/5666222/3d-line-plane-intersection
    """

    from egse.coordinates.point import Point

    if vector.reference_frame == frame:
        # The point is defined in frame => the origin of the vector is the origin of the target plane.
        return np.array([0, 0, 0])
    else:
        # Express all inputs in the given reference frame

        vector_origin = Point(
            vector.reference_frame.get_origin().coordinates[:3], reference_frame=vector.reference_frame, name="ptorig"
        ).express_in(frame)[:3]  # Vector Origin (p0)
        vector_end = vector.express_in(frame)[:3]  # Vector end (p1)

        vector_u = vector_end - vector_origin  # Vector (u)

        plane_origin = frame.get_origin().coordinates[:3]  # Origin of the reference frame (p_co)
        plane_normal = frame.get_axis("z").coordinates[:3]  # Normal to the plane (p_no)

        # Vector to normal 'angle'
        dot = np.dot(vector_u, plane_normal)  # dot = p_no * u

        # Test if there is an intersection (and if it's unique)
        # -> input vector and normal mustn't be perpendicular, else the vector is // to the plane or inside it

        if np.allclose(dot, 0.0, atol=epsilon):
            print("The input vector is // to the plane normal (or inside the plane)")
            print("-> There exists no intersection (or an infinity of them)")
            return None
        else:
            # Vector from the point in the plane to the origin of the vector (w)
            plane_to_vector = vector_origin - plane_origin  # w = p0 - p_co

            # Solution  ("how many 'vectors' away is the intersection ?")
            factor = -np.dot(plane_normal, plane_to_vector) / dot  # fac = -(plane * w) / fac

            return Point(vector_origin + (vector_u * factor), reference_frame=frame)
