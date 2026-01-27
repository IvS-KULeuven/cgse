"""
The point module provides two classes, a `Point` class which simply represents a point in the 3D space, and a `Points`
class which is a collection of Point objects.

Point objects defined in the same reference frame can be combined with the natural `+`, `-` , `+=` and `-=` operations.

In order to work with 4x4 transformation matrices, the 3D [x, y, z] coordinates are automatically converted to a
[x, y, z, 1] coordinates array attribute.
"""

import logging
import random
import string
from typing import Any

import numpy
import numpy as np
from numpy import floating

import egse.coordinates.transform3d_addon as t3add

LOGGER = logging.getLogger(__name__)


class Point:
    from egse.coordinates.reference_frame import ReferenceFrame

    """Representation of a point in 3D space, defined w.r.t. a given reference frame."""

    def __init__(self, coordinates: np.ndarray | list, reference_frame: ReferenceFrame, name: str = None):
        """Initialisation of a point in 3D space, defined w.r.t. a given reference frame.

        In order to work with 4x4 transformation matrices, the 3D [x, y, z] coordinates are automatically converted to a
        [x, y, z, 1] coordinates array attribute.

        Args:
            coordinates (np.ndarray, list): 1x3 or 1x4 matrix defining this system in the given reference frame
                                            (1x3 being x, y, z + an additional 1 for the affine operations).
            reference_frame (ReferenceFrame): Reference system in which this point object will be defined.
            name (str): Name of the point. If not given, a random name will be generated. Note that there is no check
                        that the randomly generated name is unique, so two `Point` objects can be different but have
                        the same name.

        Raises:
            ValueError: If the reference frame is None.
        """

        # Coordinates

        self.x = None
        self.y = None
        self.z = None
        self.coordinates = np.ndarray([])

        self.set_coordinates(coordinates)  # Format (x, y, z, 1)

        # Reference frame

        if reference_frame is None:
            raise ValueError("The reference frame must not be None.")
        else:
            self.reference_frame = reference_frame

        # Name

        self.name = None
        self.set_name(name)

        # Definition

        self.definition = [self.coordinates[:-1], self.reference_frame, self.name]

    def __repr__(self) -> str:
        """Returns a representation the point.

        Returns:
            Representation of the point.
        """

        return f"{self.coordinates[:-1]} (ref {self.reference_frame.name})"

    def __str__(self) -> str:
        """Returns a printable string representation of the point.

        Returns:
            Printable string representation of the point.
        """

        return f"{self.coordinates[:-1]} (ref {self.reference_frame.name}), name {self.name}"

    def __eq__(self, other) -> bool:
        """Implements the == operator.

        Two points are equal when:
            - Their coordinates are equal,
            - The reference system in which they are defined is equal.

        The name does not have to be equal.

        Args:
            other (Point): Other point to compare with.

        Returns:
            True if the points are equal, False otherwise.
        """

        if self is other:
            return True

        if isinstance(other, Point):
            if not np.array_equal(self.coordinates, other.coordinates):
                return False
            if self.reference_frame != other.reference_frame:
                return False
            return True

        return False

    def __hash__(self) -> int:
        """Returns a unique integer hash value for the point.

        Returns:
            Unique integer hash value for the point.
        """

        return id(self.definition) // 16

    def is_same(self, other) -> bool:
        """Checks whether two points are the same, even if they are defined in different reference frames.

        Args:
            other (Point): Other point to compare with.

        Returns:
            True if the points are the same, False otherwise.
        """

        if isinstance(other, Point):
            if self == other:
                return True
            if np.array_equal(self.coordinates, other.express_in(self.reference_frame)):
                return True

        return False

    @staticmethod
    def __coords__(coordinates) -> np.ndarray:
        """Formats the input list into 1x4 np.array coordinates.

        Args:
              coordinates (Point | np.ndarray | list):

        Returns:
            Coordinates formatted as a 1x4 np.ndarray.

        Raises:
            ValueError: If the input is not a list, numpy.ndarray, or Point.
        """

        if isinstance(coordinates, Point):
            return coordinates.coordinates
        elif isinstance(coordinates, (np.ndarray, list)):
            coordinates = list(coordinates)
            if len(coordinates) == 3:
                coordinates.append(1)
            return np.ndarray(coordinates)
        else:
            raise ValueError("Input must be a list, numpy.ndarray or Point")

    def set_name(self, name: (str | None) = None) -> None:
        """Sets the name of the point.

        Args:
            name (str | None): Name to use for the point. If None, a random name will be generated.
        """

        if name is None:
            # TODO Should we care about the possibility the the generation of random names does not necessarily create
            #      a unique name for the point?
            self.name = "p" + "".join(random.choices(string.ascii_lowercase, k=3))
        else:
            self.name = name

    def set_coordinates(self, coordinates: np.ndarray | list) -> None:
        """Sets the coordinates of the point.

        Args:
            coordinates (np.ndarray | list): Coordinates to set.
        """

        coordinates = Point.__coords__(coordinates)
        self.coordinates = np.ndarray(coordinates)

        self.x = self.coordinates[0]
        self.y = self.coordinates[1]
        self.z = self.coordinates[2]

    def get_coordinates(self, reference_frame: ReferenceFrame | None = None) -> np.ndarray:
        """Returns the coordinates of the point.

        Args:
            reference_frame (ReferenceFrame | None): Reference frame in which the point coordinates are returned.

        Returns:
            Coordinates of the point in the given reference frame.
        """

        if reference_frame is None:
            return self.coordinates
        else:
            return self.express_in(reference_frame)

    def distance_to(self, target) -> floating[Any]:
        """Returns the distance from this point to the target.

        Args:
            target (Point | ReferenceFrame | np.ndarray | list): Target to compute the distance to.

        Returns:
            Distance from this point to the target.

        Raises:
            ValueError: If the target is not a Point, ReferenceFrame, numpy.ndarray, or list.
        """

        from egse.coordinates.reference_frame import ReferenceFrame

        if isinstance(target, Point):
            target_coordinates = target.express_in(self.reference_frame)[:3]
        elif isinstance(target, ReferenceFrame):
            return np.linalg.norm(self.express_in(target)[:3])
        elif isinstance(target, (np.ndarray, list)):
            if len(target) > 3:
                target = target[:3]
            target_coordinates = target
        else:
            raise ValueError("Target must be a list, numpy.ndarray, Point, or ReferenceFrame")

        LOGGER.info(f"self={self.coordinates[:-1]}, target={target_coordinates}")

        return np.linalg.norm(self.coordinates[:3] - target_coordinates)

    def in_plane_distance_to(self, target, plane: str = "xy") -> np.floating[Any]:
        """Returns the distance of this point object to the target, considering 2 coordinates only.

        Note that this is not a commutative operation, because the plane used to project the points coordinates
        before computing the distances is taken from the coordinate system of `self`.

        Args:
            target (Point | ReferenceFrame | np.ndarray | list): Target to compute the distance to.
            plane (str): Plane to consider. Must be in ['xy', 'xz', 'yz'].

        Returns:
            Distance from this point to the target.
        """

        from egse.coordinates.reference_frame import ReferenceFrame

        if isinstance(target, Point):
            target_coordinates = target.express_in(self.reference_frame)
        elif isinstance(target, ReferenceFrame):
            target_coordinates = target.get_origin().express_in(self)
        elif isinstance(target, (np.ndarray, list)):
            target_coordinates = target
        else:
            raise ValueError("input must be a list, numpy.ndarray, Point or ReferenceFrame")

        LOGGER.info(f"self={self.coordinates[:-1]}, target={target_coordinates}")

        plane_selection = {"xy": [0, 1], "xz": [0, 2], "yz": [1, 2]}

        LOGGER.info(f"self.coordinates[planeSelect[plane]]  {self.coordinates[plane_selection[plane]]}")
        LOGGER.info(f"targetCoords[planeSelect[plane]]      {target_coordinates[plane_selection[plane]]}")
        LOGGER.info(
            f"Difference                            {self.coordinates[plane_selection[plane]] - target_coordinates[plane_selection[plane]]}"
        )

        return np.linalg.norm(self.coordinates[plane_selection[plane]] - target_coordinates[plane_selection[plane]])

    def distance_to_plane(self, plane: str = "xy", reference_frame: ReferenceFrame | None = None) -> float:
        """Calculates the distance from the point to a plane in a given reference frame.

        Args:
            plane (str): Target plane, must be in ["xy", "xz", "yz"]
            reference_frame (ReferenceFrame | None, optional): Reference frame in which the distance is calculated.

        Returns:
            Distance from the point to the plane.
        """

        if (reference_frame is None) or (self.reference_frame == reference_frame):
            coordinates = self.coordinates[:-1]
        else:
            coordinates = self.express_in(reference_frame)

        out_of_plane_index = {"xy": 2, "xz": 1, "yz": 0}

        return coordinates[out_of_plane_index[plane]]

    def __sub__(self, point):
        """Implements the subtraction operator (-).

        Args:
            point (Point | np.ndarray | list): Point to subtract from `self`.

        Returns:
            Point: New point resulting from the subtraction.
        """

        if isinstance(point, Point):
            if point.reference_frame != self.reference_frame:
                raise NotImplementedError("The points have different reference frames")

            new_coordinates = self.coordinates - point.coordinates

        elif isinstance(point, (np.ndarray, list)):
            new_coordinates = self.coordinates - Point.__coords__(point)

        else:
            raise ValueError("The point must be a Point, numpy.ndarray, or list")

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)

        new_coordinates[-1] = 1

        return Point(coordinates=new_coordinates, reference_frame=self.reference_frame)

    def __isub__(self, point):
        """Implements the subtraction assignment operator (-=).

        Args:
            point (Point | np.ndarray | list): Point to add to `self`.

        Returns:
            Modified point.

        Raises:
            ValueError: If the point is not a Point, numpy.ndarray, or list.
        """

        if isinstance(point, Point):
            if point.reference_frame != self.reference_frame:
                raise NotImplementedError("The points have different reference frames")

            new_coordinates = self.coordinates - point.coordinates

        elif isinstance(point, (np.ndarray, list)):
            new_coordinates = self.coordinates - Point.__coords__(point)

        else:
            raise ValueError("The point must be a Point, numpy.ndarray, or list")

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)
        new_coordinates[-1] = 1

        self.coordinates = new_coordinates

        return self

    def __add__(self, point):
        """Implements the addition operator (+).

        Args:
            point (Point | np.ndarray | list): Point to add to `self`.

        Returns:
            Point: New point resulting from the addition.

        Raises:
            ValueError: If the point is not a Point, numpy.ndarray, or list.
        """

        if isinstance(point, Point):
            if point.reference_frame != self.reference_frame:
                raise NotImplementedError("The points have different reference frames")

            new_coordinates = self.coordinates + point.coordinates

        elif isinstance(point, (np.ndarray, list)):
            new_coordinates = self.coordinates + Point.__coords__(point)

        else:
            raise ValueError("The point must be a Point, numpy.ndarray, or list")

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)

        new_coordinates[-1] = 1

        return Point(coordinates=new_coordinates, reference_frame=self.reference_frame)

    def __iadd__(self, point):
        """Implements the addition assignment operator (+=).

        Args:
            point (Point | np.ndarray | list): Point to add to `self`.

        Returns:
            Modified point.

        Raises:
            ValueError: If the point is not a Point, numpy.ndarray, or list.
        """

        if isinstance(point, Point):
            if point.reference_frame != self.reference_frame:
                raise NotImplementedError("The points have different reference frames")

            new_coordinates = self.coordinates + point.coordinates

        elif isinstance(point, (np.ndarray, list)):
            new_coordinates = self.coordinates + Point.__coords__(point)

        else:
            raise ValueError("The point must be a Point, numpy.ndarray, or list")

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)

        new_coordinates[-1] = 1
        self.coordinates = new_coordinates

        return self

    def express_in(self, target_frame: ReferenceFrame) -> np.ndarray:
        """Expresses the coordinates in another reference frame.

        Args:
            target_frame (ReferenceFrame): Target reference frame.

        Returns:
            Coordinates in the target reference frame.
        """

        if target_frame == self.reference_frame:
            result = self.coordinates

        else:
            # Apply coordinate transformation of self.coordinates from self.reference_frame to target_frame
            transform = self.reference_frame.get_passive_transformation_to(target_frame)
            result = np.dot(transform, self.coordinates)

            LOGGER.debug(f"transform: \n{transform}")

        return result

    def change_reference_frame(self, target_frame: ReferenceFrame):
        """Re-defines `self` as attached to another reference frame.

        This is done by:
        - Calculating the coordinates of `self` in the target reference frame,
        - Updating the definition of `self` in the new reference frame (with the newly calculated coordinates and the
          target reference frame).

        Args:
            target_frame (ReferenceFrame): Target reference frame.
        """

        new_coordinates = self.express_in(target_frame)
        self.set_coordinates(new_coordinates)

        self.reference_frame = target_frame


class Points:
    """Representation of a collection of points in 3D space."""

    from egse.coordinates.reference_frame import ReferenceFrame

    debug = 0

    def __init__(self, coordinates: numpy.ndarray | list, reference_frame: ReferenceFrame, name: str = None):
        """Initialisation of a new set of points.

        Args:
            coordinates (numpy.ndarray | list): Either a 4xn matrix (3 being x, y, z + an additional 1 for the affine
                                                operations), defining n coordinates in the given reference frame, or a
                                                list of Point(s) objects.
            reference_frame (ReferenceFrame): Reference frame in which the coordinates are defined.
            name (str | None): Name of the Points object.  When None, a name will be generated automatically, consisting
                               of a capital "P" followed by three lower case letters.
        """

        # Coordinates

        self.x = None
        self.y = None
        self.z = None
        self.coordinates = np.ndarray([])

        if isinstance(coordinates, list):
            coordinate_list = []

            for item in coordinates:
                if isinstance(item, Point):
                    coordinate_list.append(item.express_in(reference_frame))
                elif isinstance(item, Points):
                    coordinate_list.extend(item.express_in(reference_frame))
                else:
                    raise ValueError("If the input is a list, all items in it must be Point(s) objects")
            self.set_coordinates(np.array(coordinate_list).T)
        elif isinstance(coordinates, np.ndarray):
            self.set_coordinates(coordinates)
        else:
            raise ValueError("The input must be either a numpy.ndarray or a list of Point/Points objects")

        # Reference frame

        if reference_frame is None:
            raise ValueError("The reference frame must not be None.")
        else:
            self.reference_frame = reference_frame

        # Name

        self.name = None
        self.set_name(name)

    def __repr__(self) -> str:
        """Returns a representation the points.

        Returns:
            Representation of the points.
        """

        return "{0} (ref {1})".format(self.coordinates[:-1], self.reference_frame.name)

    def __str__(self) -> str:
        """Returns a printable string representation of the point.

        Returns:
            Printable string representation of the point.
        """

        return "{1} (ref {2}), name {0}".format(self.name, self.coordinates[:-1], self.reference_frame.name)

    @staticmethod
    def __coords__(coordinates):
        """Formats the input list into 4xn np.array coordinates.

        Args:
              coordinates (Point | np.ndarray | list):

        Returns:
            Coordinates formatted as a 1x4 np.ndarray.

        Raises:
            ValueError: If the input is not a list, numpy.ndarray, or Point.
        """

        if isinstance(coordinates, Point):
            return coordinates.coordinates
        elif isinstance(coordinates, np.ndarray):
            if coordinates.shape[0] not in [3, 4]:
                raise ValueError("Input coordinates array must be 3 x n or 4 x n")
            if coordinates.shape[0] == 3:
                new_coordinates = np.ones([4, coordinates.shape[1]])
                new_coordinates[:3, :] = coordinates
                coordinates = new_coordinates
            return coordinates
        else:
            raise ValueError("input must be a list, numpy.ndarray or Point")

    def set_name(self, name: str | None = None):
        """Sets the name of the point.

        Args:
            name (str | None): Name to use for the point. If None, a random name will be generated.
        """

        if name is None:
            self.name = (
                "P"
                + "".join(random.choices(string.ascii_lowercase, k=2))
                + "".join(random.choices(string.ascii_uppercase, k=1))
            )
        else:
            self.name = name

    def set_coordinates(self, coordinates: numpy.ndarray | list) -> None:
        """Sets the coordinates of the point.

        Args:
            coordinates (np.ndarray | list): Coordinates to set.
        """

        coordinates = Points.__coords__(coordinates)
        self.coordinates = coordinates

        self.x = self.coordinates[0, :]
        self.y = self.coordinates[1, :]
        self.z = self.coordinates[2, :]

    def get_coordinates(self, reference_frame: ReferenceFrame | None = None) -> numpy.ndarray:
        """Returns the coordinates of the point.

        Args:
            reference_frame (ReferenceFrame | None): Reference frame in which the point coordinates are returned.

        Returns:
            Coordinates of the point in the given reference frame.
        """

        if reference_frame is None:
            return self.coordinates
        else:
            return self.express_in(reference_frame)

    def express_in(self, target_frame: ReferenceFrame) -> np.ndarray:
        """Expresses the coordinates in another reference frame.

        Args:
            target_frame (ReferenceFrame): Target reference frame.

        Returns:
            Coordinates in the target reference frame.
        """

        if target_frame == self.reference_frame:
            result = self.coordinates
        else:
            # Apply coordinate transformation of self.coordinates from self.reference_frame to target_frame
            transform = self.reference_frame.get_passive_transformation_to(target_frame)
            if self.debug:
                print("transform \n{0}".format(transform))
            result = np.dot(transform, self.coordinates)
        return result

    def change_reference_frame(self, target_frame: ReferenceFrame):
        """Re-defines `self` as attached to another reference frame.

        This is done by:
        - Calculating the coordinates of `self` in the target reference frame,
        - Updating the definition of `self` in the new reference frame (with the newly calculated coordinates and the
          target reference frame).

        Args:
            target_frame (ReferenceFrame): Target reference frame.
        """

        new_coordinates = self.express_in(target_frame)
        self.set_coordinates(new_coordinates)

        self.reference_frame = target_frame

    def get_num_points(self) -> int:
        """Returns the number of points in the set of points.

        Returns:
            Number of points in the set of points.
        """

        return self.coordinates.shape[1]

    def get_point(self, index: int, name: str | None = None) -> Point:
        """Returns the point with the given index and assigns the given name to it.

        Args:
            index (int): Index of the point to return.
            name (str): Name of the point.

        Returns:
            Point with the given index.
        """

        return Point(self.coordinates[:, index], reference_frame=self.reference_frame, name=name)

    get = get_point

    def best_fitting_plane(self, plane: str = "xy", use_svd: bool = False, verbose: bool = True):
        """Returns the reference frame with the given plane as best fitting to all points in this collection of points.

        Args:
            plane (str): Plane to fit. Must be in ["xy", "yz", "zx"].
            use_svd (bool): Indicates whether to use SVD-base solution (Singular Value Decomposition) for
                            rigid/similarity transformations.  If False and ndims = 3, the quaternion-based solution is
                            used.
            verbose (bool): Indicates whether to print verbose output.

        Returns:
            Reference frame with the given plane as best fitting to all points in this collection of points.
        """

        # Import necessary due to a circular dependency between Point and ReferenceFrame
        from egse.coordinates.reference_frame import ReferenceFrame

        debug = True

        a, b, c = self.fit_plane(plane=plane, verbose=verbose)

        unit_axes = Points.from_plane_parameters(a, b, c, reference_frame=self.reference_frame, plane=plane)
        # print(f"Unit axes coordinates \n{np.round(unit_axes.coordinates,3)}")

        # unit_axes contain 3 unit axes and an origin
        # => the unit vectors do NOT belong to the target plane
        # => they must be translated before
        unit_coordinates = unit_axes.coordinates
        for ax in range(3):
            unit_coordinates[:3, ax] += unit_coordinates[:3, 3]

        new_axes = Points(unit_coordinates, reference_frame=self.reference_frame)

        # print(f"new_axes {np.round(new_axes.coordinates,3)}")

        self_axes = Points(np.identity(4), reference_frame=self.reference_frame)

        transform = t3add.affine_matrix_from_points(
            self_axes.coordinates[:3, :], new_axes.coordinates[:3, :], shear=False, scale=False, use_svd=use_svd
        )

        if debug:
            transform2 = t3add.rigid_transform_3d(self_axes.coordinates[:3, :], new_axes.coordinates[:3, :])

        if verbose:
            print(f"Transform  \n{np.round(transform, 3)}")
            if debug:
                print(f"Transform2 \n{np.round(transform2, 3)}")
                print(f"Both methods consistent ? {np.allclose(transform, transform2)}")

        return ReferenceFrame(transformation=transform, reference_frame=self.reference_frame)

    def fit_plane(self, plane: str = "xy", verbose: bool = True) -> tuple[float, float, float]:
        """Fits the plane best fitting the points.

        Depending on the `plane` parameter, the plane is fitted in the xy, yz, or zx plane:
            - "xy": z = ax + by + c
            - "yz": x = ay + bz + c
            - "zx": y = az + bx + c

        Args:
            plane (str): Plane to fit. Must be in ["xy", "yz", "zx"].
            verbose (bool): If True, print the results on screen.

        Returns:
            Best fitting parameters (a, b, c), corresponding to the fitted plane.
        """

        xyz = [self.x, self.y, self.z]

        num_points = len(xyz[0])

        starting_index = {"xy": 0, "yz": 1, "zx": 2}[plane]

        # Coefficients matrix
        coefficients_matrix = np.vstack([xyz[starting_index], xyz[(starting_index + 1) % 3], np.ones(num_points)]).T

        # Solve linear equations
        a, b, c = np.linalg.lstsq(coefficients_matrix, xyz[(starting_index + 2) % 3], rcond=None)[0]

        # Print results on screen
        if verbose:
            hprint = {"xy": "z = ax + by + c", "yz": "x = ay + bz + c", "zx": "y = az + bx + c"}
            print(f"{hprint[plane]} : \n    a = {a:7.3e}  \n    b = {b:7.3e} \n    c = {c:7.3e}")

        return a, b, c

    @classmethod
    def from_plane_parameters(
        cls, a: float, b: float, c: float, reference_frame: ReferenceFrame, plane: str = "xy", verbose: bool = False
    ):
        """Returns the unit axes and the origin of the given reference frame.

        Args:
            a (float): Coefficient `a` in the equation of the target plane (z = ax + by + c)
            b (float): Coefficient `b` in the equation of the target plane (z = ax = by + c)
            c (float): Coefficient `c` in the equation of the target plane (z = ax + by + c)
            reference_frame (ReferenceFrame): Reference frame.
            plane (str): Plane to fit. Must be in ["xy", "yz", "zx"].
            verbose (bool): If True, print the results on screen.

        Returns:
            Points object describing the unit axes and the origin of the reference frame defined by the input parameters.
        """

        if plane != "xy":
            print(f"WARNING: plane = {plane} NOT IMPLEMENTED")

        origin_coords = np.array([0, 0, c])  # Origin coordinates (x = y = 0, z = c)

        # Intersection between
        #   - Target plane (z = ax + by + c)
        #   - Plane // to xy passing through z=c

        if np.abs(b) > 1.0e-5:
            pxy = np.array([1, -a / float(b), c])  # z = c, x = 1
        else:
            pxy = np.array([-b / float(a), 1, c])  # z = c, y = 1

        # Intersection between:
        #   - Target plane (z = ax + by + c)
        #   - yz-plane (x = 0)

        pyz = np.array([0, 1, b + c])  # x = 0, y = 1

        # # pzx : intersection of target plane and Z-X plane
        # if np.abs(a)>1.e-3:
        #     # y = 0, z = 1
        #     pzx = np.array([(1-c)/float(a),0,1])
        # else:
        #     # y = 0, x = 1
        #     pzx = np.array([1,0,a+c])

        # Unit vector from [0, 0, 0] along the intersection between the target plane and the plane // to xy passing
        # through z=c

        x_unit_coords = (pxy - origin_coords) / np.linalg.norm(pxy - origin_coords)  # Normalise

        # Unit vector from [0, 0, 0] along the intersection between the target plane and the yz-plane
        # In the target plane but not perpendicular to x_unit_coords (its norm doesn't matter)

        y_temp = pyz - origin_coords  # /np.linalg.norm(pyz-p0)

        # x_unit_coords and y_temp are both in the plane
        # -> z_unit_coords is perpendicular to both

        z_unit_coords = np.cross(x_unit_coords, y_temp)
        z_unit_coords /= np.linalg.norm(z_unit_coords)  # Normalise

        # y_unit_coords completes the right-handed reference frame

        y_unit_coords = np.cross(z_unit_coords, x_unit_coords)
        y_unit_coords /= np.linalg.norm(y_unit_coords)  # Normalise

        x_unit_point = Point(x_unit_coords, reference_frame=reference_frame)
        y_unit_point = Point(y_unit_coords, reference_frame=reference_frame)
        z_unit_point = Point(z_unit_coords, reference_frame=reference_frame)
        origin = Point(origin_coords, reference_frame=reference_frame)

        if verbose:
            print(f"x_unit_coords  {x_unit_coords}")
            print(f"y_unit_coords  {y_unit_coords}")
            print(f"z_unit_coords  {z_unit_coords}")
            print(f"origin_coords {origin_coords}")

        return cls([x_unit_point, y_unit_point, z_unit_point, origin], reference_frame=reference_frame)
