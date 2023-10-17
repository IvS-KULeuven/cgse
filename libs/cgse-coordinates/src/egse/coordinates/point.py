"""
The point module provides two classes, a `Point` class which simply represents a point
in the 3D space, and a `Points` class which is a collection of Point objects.

A Point is defined with respect to a given reference frame and is given a name.

Point objects defined in the same reference frame can be combined with the
natural `+`, `-` , `+=` and `-=` operations.

In order to work with 4x4 transformation matrices, the 3D [x,y,z] coordinates are
automatically converted to a [x,y,z,1] coordinates array attribute.

@author: Pierre Royer
"""
import logging
import random
import string

import numpy as np

import egse.coordinates.transform3d_addon as t3add

LOGGER = logging.getLogger(__name__)


class Point:
    """
    A Point object represents a point in 3D space and is defined with respect to
    a given reference frame.

    .. note::
        There is no check that the randomly generated name is unique, so two Point
        objects can be different but have the same name.

    """
    debug = 0

    def __init__(self, coordinates, ref, name=None):
        """
        This initializes a Point object in a given reference frame.

        Args:
            coordinates (numpy.ndarray, list): 1x3 or 1x4 matrix defining this system in "ref" system
                (1x3 being x,y,z + an additional 1 for the affine operations)

            ref (ReferenceFrame): the reference system in which this Point object will be defined,
                if not given or None the master reference frame will be used

        """

        # Makes sure of format [x,y,z,1] and sets coordinates
        self.setCoordinates(coordinates)

        # set the reference frame of reference
        if ref is None:
            raise ValueError("A Point shall be defined with a reference frame, ref can not be None.")
        else:
            self.ref = ref

        self.setName(name)

        self.definition = [self.coordinates[:-1], self.ref, self.name]

    def __repr__(self):
        return f"{self.coordinates[:-1]} (ref {self.ref.name})"

    def __str__(self):
        return f"{self.coordinates[:-1]} (ref {self.ref.name}), name {self.name}"

    def __eq__(self, other):
        """
        Re-implements the == operator which by default checks if id(self) == id(other).

        Two Point objects are equal when:

        * their coordinates are equal
        * the reference system in which they are defined is equal
        * the name must not be equal
        """
        if self is other:
            return True

        if isinstance(other, Point):
            if not np.array_equal(self.coordinates, other.coordinates):
                return False
            if self.ref != other.ref:
                return False
            return True
        return NotImplemented

    def __hash__(self):
        return id(self.definition) // 16

    def isSame(self, other):
        """
        This checks if a Point is the same as another Point in a different reference frame.

        Two Point objects are the same when their position, i.e. coordinates, are equal
        after they have been expressed in the same reference frame.

        :param other: a Point object that you want to check
        :type other: Point

        :returns: True when the two Point objects are the same, False otherwise

        :raises TypeError: when other is not a compatible type, NotImplemented will returned
                           which will result in a ```TypeError: unsupported operand type(s) for +:```.
        """

        if isinstance(other, Point):
            if self == other:
                return True
            else:
                if np.array_equal(self.coordinates, other.expressIn(self.ref)):
                    return True
            return False
        return NotImplemented

    @staticmethod
    def __coords__(coordinates):
        """
        Formats 1x3 or 1x4 input lists or np.arrays into 1x4 np.array coordinates
        Static --> can be called 'from outside', without passing a Point object
        """
        if isinstance(coordinates, Point):
            return coordinates.coordinates
        elif isinstance(coordinates, (np.ndarray, list)):
            coordinates = list(coordinates)
            if len(coordinates) == 3:
                coordinates.append(1)
            return coordinates
        else:
            raise ValueError("input must be a list, numpy.ndarray or Point")

    def setName(self, name=None):
        """
        Set or change the name of a Point object.

        :param str name: the new name for the Point, if None, a random name will be generated.

        .. todo:: Should we care about the possibility the the generation of random names does not
                  necessarily create a unique name for the Point?
        """
        if name is None:
            self.name = 'p'+''.join(random.choices(string.ascii_lowercase, k=3))
        else:
            self.name = name

    def setCoordinates(self, coordinates):
        """
        Set the coordinates of this Point object.
        """
        coordinates = Point.__coords__(coordinates)
        self.coordinates = np.array(coordinates)

        self.x = self.coordinates[0]
        self.y = self.coordinates[1]
        self.z = self.coordinates[2]

    def getCoordinates(self, ref=None):
        """
        Returns the coordinates of this Points object.

        If no reference frame is given, the coordinates of the Point will just be returned,
        other wise this method behaves the same as the ``expressIn(ref)`` method.

        :param ref: the Reference Frame in which the Point shall be defined
        :type ref: ReferenceFrame
        """
        if ref is None:
            return self.coordinates
        else:
            return self.expressIn(ref)

    def distanceTo(self, target):
        """
        Returns the distance of this Point object to the target. Target can be another Point,
        a ReferenceFrame object or a Numpy dnarray or list with coordinates.
        """
        from egse.coordinates.referenceFrame import ReferenceFrame

        if isinstance(target, Point):
            targetCoords = target.expressIn(self.ref)[:3]
        elif isinstance(target, ReferenceFrame):
            return np.linalg.norm(self.expressIn(target)[:3])
        elif isinstance(target, (np.ndarray, list)):
            if len(target) > 3:
                target = target[:3]
            targetCoords = target
        else:
            raise ValueError("input must be a list, numpy.ndarray, Point or ReferenceFrame")

        LOGGER.info(f"self={self.coordinates[:-1]}, target={targetCoords}")

        return np.linalg.norm(self.coordinates[:3]-targetCoords)

    def inPlaneDistanceTo(self,target,plane='xy'):
        """
        Returns the distance of this Point object to the target, considering 2 coordinates only!

        target: can be another Point, a ReferenceFrame object or a Numpy dnarray or list with coordinates.

        plane : must be in ['xy', 'xz', 'yz']

        NB: The xy, yz or xz plane used to project the points coordinates before
            computing the distances is taken from the coordinate system of "self"
            ==> pointA.inPlaneDistanceTo(pointB) != pointB.inPlaneDistanceTo(pointA)
            The first projects on the xy plane of pointA.ref, the second on the xy plane of pointB.ref
        """
        from egse.coordinates.referenceFrame import ReferenceFrame

        if isinstance(target, Point):
            targetCoords = target.expressIn(self.ref)
        elif isinstance(target, ReferenceFrame):
            targetCoords = target.getOrigin().expressIn(self)
        elif isinstance(target, (np.ndarray, list)):
            targetCoords = target
        else:
            raise ValueError("input must be a list, numpy.ndarray, Point or ReferenceFrame")

        LOGGER.info(f"self={self.coordinates[:-1]}, target={targetCoords}")

        planeSelect = {'xy':[0,1], 'xz':[0,2], 'yz':[1,2]}

        LOGGER.info(f"self.coordinates[planeSelect[plane]]  {self.coordinates[planeSelect[plane]]}")
        LOGGER.info(f"targetCoords[planeSelect[plane]]      {targetCoords[planeSelect[plane]]}")
        LOGGER.info(f"Difference                            {self.coordinates[planeSelect[plane]]-targetCoords[planeSelect[plane]]}")

        return np.linalg.norm(self.coordinates[planeSelect[plane]]-targetCoords[planeSelect[plane]])

    def distanceToPlane(self,plane="xy",ref=None):
        """
        distanceToPlane(self,plane="xy",ref=None)

        The target plane is defined by one of it coordinate planes: ["xy", "yz", "xz"]

        :param ref: reference frame
        :type ref: ReferenceFrame

        :param plane: in ["xy", "xz", "yz"]
        :type plane: str

        :returns: the distance from self to plane
        """
        if (ref is None) or (self.ref == ref):
            coordinates = self.coordinates[:-1]
        elif self.ref != ref:
            coordinates = self.expressIn(ref)

        outOfPlaneIndex = {'xy':2,'xz':1,'yz':0}

        return coordinates[outOfPlaneIndex[plane]]

    def __sub__(self,apoint):
        """
        Takes care for
        newPoint = self + point
        """
        if isinstance(apoint, Point):

            try:
                if apoint.ref != self.ref:
                    raise ValueError
            except ValueError:
                print("WARNING: The points have different reference frames, returning NotImplemented")
                return NotImplemented
            newCoordinates = self.coordinates - apoint.coordinates

        elif isinstance(apoint, (np.ndarray, list)):

            newCoordinates = self.coordinates - Point.__coords__(apoint)

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)
        newCoordinates[-1] = 1

        return Point(coordinates=newCoordinates,ref=self.ref)

    def __isub__(self,apoint):
        """
        Takes care for
        self += coordinates (modifies self in place)
        """
        if isinstance(apoint, Point):

            try:
                if apoint.ref != self.ref:
                    raise ValueError
            except ValueError:
                print("WARNING: The points have different reference frames, returning NotImplemented")
                return NotImplemented
            newCoordinates = self.coordinates - apoint.coordinates

        elif isinstance(apoint, (np.ndarray, list)):

            newCoordinates = self.coordinates - Point.__coords__(apoint)

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)
        newCoordinates[-1] = 1

        self.coordinates = newCoordinates

        return self

    def __add__(self,apoint):
        """
        Takes care for
        newPoint = self + point
        """
        if isinstance(apoint, Point):

            try:
                if apoint.ref != self.ref:
                    print(f"DEBUG: {apoint} = {apoint.expressIn(self.ref)}")
                    raise ValueError
            except ValueError:
                print("WARNING: The points have different reference frames, returning NotImplemented")
                return NotImplemented
            newCoordinates = self.coordinates + apoint.coordinates

        elif isinstance(apoint, (np.ndarray, list)):

            newCoordinates = self.coordinates + Point.__coords__(apoint)

        else:
            return NotImplemented

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)
        newCoordinates[-1] = 1

        return Point(coordinates=newCoordinates,ref=self.ref)

    def __iadd__(self,apoint):
        """
        Takes care for
        self += coordinates (modifies self in place)
        """
        if isinstance(apoint, Point):

            try:
                if apoint.ref != self.ref:
                    raise ValueError
            except ValueError:
                print("WARNING: The points have different reference frames, returning NotImplemented")
                return NotImplemented
            newCoordinates = self.coordinates + apoint.coordinates

        elif isinstance(apoint, (np.ndarray, list)):

            newCoordinates = self.coordinates + Point.__coords__(apoint)

        # For the affine transforms, the 4th digit must be set to 1 (it has been modified above)
        newCoordinates[-1] = 1

        self.coordinates = newCoordinates

        return self

    def expressIn(self,targetFrame):
        """
        expressIn(self,targetFrame)
        """
        if targetFrame == self.ref:
            """
            targetFrame == self.ref
            We're after the definition of self
            """
            result = self.coordinates
        else:
            """
            We're after the coordinates of self, i.e. the definition of self in targetFrame

            We know the coordinates in self.ref
            #We need to apply the transformation from targetFrame to self.ref
            self.ref        --> self (self.transformation)
            """
            #transform = targetFrame.getTransformationFrom(self.ref)
            transform = self.ref.getPassiveTransformationTo(targetFrame)
            if self.debug: print("transform \n{0}".format(transform))
            result    = np.dot(transform,self.coordinates)
        return result

    def changeRef(self,targetFrame):
        """
        We redefine self as attached to another reference frame
        . calculate self's coordinates in the new reference frame
        . update the definition
        """
        newCoordinates = self.expressIn(targetFrame)
        self.setCoordinates(newCoordinates)
        self.ref = targetFrame
        return




class Points():
    """
    A Points object is a collection of Point objects.

    Points can be constructed from either a numpy.ndarray of shape 3 x n or 4 x n, or
    a list of Point objects. The coordinates of the Point objects are transferred to
    the desired ReferenceFrame and concatenated in the list order.

    When automatically generated a Points object name consists in a capital 'P' followed by
    three lower case letters. A Point can be extracted from a Points object by its
    position in the coordinates array (see below).

    """
    debug=0
    def __init__(self, coordinates, ref,name=None):
        """
        Points.__init__(self, coordinates, ref, name=None)

        Constructor

        coordinates : must be of one of the following type:
            * numpy.ndarray:
              4xn matrix defining this system in "ref" system
              (3 being x,y,z + an additional 1 for the affine operations)
            * list of Point objects:
              the coordinates of the Point objects are extracted in the order of the list
              and concatenated in a numpy.ndarray

        ref         : reference system in which self is defined

        Both parameters are mandatory.
        """

        # TODO: accept a list made of Point and Points rather than strictly Point

        if isinstance(coordinates, list):
            coordinateList = []
            for apoint in coordinates:
                if not isinstance(apoint, Point):
                    raise ValueError("If the input is a list, all items in it must be Point(s) objects")
                coordinateList.append(apoint.expressIn(ref))
            self.setCoordinates(np.array(coordinateList).T)
        elif isinstance(coordinates, np.ndarray):
            self.setCoordinates(coordinates)
        else:
            raise ValueError("The input must be either a numpy.ndarray or a list of Point objects")

        self.ref = ref

        self.setName(name)

        return

    def __repr__(self):
        return "{0} (ref {1})".format(self.coordinates[:-1], self.ref.name)

    def __str__(self):
        return "{1} (ref {2}), name {0}".format(self.name, self.coordinates[:-1], self.ref.name)

    @staticmethod
    def __coords__(coordinates):
        """
        Formats 3xn or 4xn input lists or np.arrays into 4xn np.array coordinates
        Static --> can be called 'from outside', without passing a Points object
        """
        if isinstance(coordinates, Point):
            return coordinates.coordinates
        elif isinstance(coordinates, np.ndarray):

            if coordinates.shape[0] not in [3,4]:
                raise ValueError("Input coordinates array must be 3 x n or 4 x n")

            if coordinates.shape[0]==3:
                newCoords = np.ones([4,coordinates.shape[1]])
                newCoords[:3,:] = coordinates
                coordinates = newCoords
            return coordinates
        else:
            raise ValueError("input must be a list, numpy.ndarray or Point")

    def setName(self,name=None):
        if name is None:
            self.name = 'P'+ ''.join(random.choices(string.ascii_lowercase, k=2))+\
                             ''.join(random.choices(string.ascii_uppercase, k=1))
        else:
            self.name = name

    def setCoordinates(self,coordinates):
        #coordinates = list(coordinates)
        #if len(coordinates)==3: coordinates.append(1)
        coordinates = Points.__coords__(coordinates)
        self.coordinates = coordinates

        self.x = self.coordinates[0,:]
        self.y = self.coordinates[1,:]
        self.z = self.coordinates[2,:]

        return

    def getCoordinates(self,ref=None):
        if ref is None:
            return self.coordinates
        else:
            return self.expressIn(ref)

    def expressIn(self,targetFrame):
        """
        expressIn(self,targetFrame)
        """
        if targetFrame == self.ref:
            """
            targetFrame == self.ref
            We're after the definition of self
            """
            result = self.coordinates
        else:
            """
            We're after the coordinates of self, i.e. the definition of self in targetFrame

            We know the coordinates in self.ref
            #We need to apply the transformation from targetFrame to self.ref
            self.ref        --> self (self.transformation)
            """
            #transform = targetFrame.getTransformationFrom(self.ref)
            transform = self.ref.getPassiveTransformationTo(targetFrame)
            if self.debug: print("transform \n{0}".format(transform))
            result    = np.dot(transform,self.coordinates)
        return result

    def changeRef(self,targetFrame):
        """
        We redefine self as attached to another reference frame
        . calculate self's coordinates in the new reference frame
        . update the definition
        """
        newCoordinates = self.expressIn(targetFrame)
        self.setCoordinates(newCoordinates)
        self.ref = targetFrame
        return

    def getPoint(self,index,name=None):
        """
        Returns the point with coordinates self.coordinates[:,index], in reference frame pts.ref
        """
        return Point(self.coordinates[:,index],ref=self.ref,name=name)

    get = getPoint

    def bestFittingPlane(self,fitPlane="xy", usesvd=False,verbose=True):
        """
        bestFittingPlane(self,fitPlane="xy", usesvd=False,verbose=True)

        fitPlane in ['xy,'yz','zx']
        usesvd   see transform3d_addon.affine_matrix_from_points.__doc__

        OUTPUT
        returns the reference Frame having as X-Y plane the plane best fitting all points in self
        """
        # Import necessary due to a circular dependency between Point and ReferenceFrame
        from egse.coordinates.referenceFrame import ReferenceFrame

        debug=True

        a,b,c = self.fitPlane(fitPlane=fitPlane,verbose=verbose)
        #print (f"a {a}, b {b}, c {c}")
        #print()

        unitaxes = Points.fromPlaneParameters(a,b,c,ref=self.ref,plane=fitPlane)
        #print(f"Unitaxes coordinates \n{np.round(unitaxes.coordinates,3)}")
        #print()


        # unitaxes contain 3 unit axes and an origin
        # => the unit vectors do NOT belong to the target plane
        # => they must be translated before
        unitcoords = unitaxes.coordinates
        for ax in range(3):
            unitcoords[:3,ax] += unitcoords[:3,3]

        newaxes = Points(unitcoords, ref=self.ref)

        #print(f"newaxes {np.round(newaxes.coordinates,3)}")

        selfaxes = Points(np.identity(4),ref=self.ref)

        transform  = t3add.affine_matrix_from_points(selfaxes.coordinates[:3,:], newaxes.coordinates[:3,:], shear=False, scale=False, usesvd=usesvd)


        if debug:
            transform2 =        t3add.rigid_transform_3D(selfaxes.coordinates[:3,:], newaxes.coordinates[:3,:], verbose=verbose)

        if verbose:
            print()
            print(f"Transform  \n{np.round(transform,3)}")
            if debug:
                print()
                print(f"Transform2 \n{np.round(transform2,3)}")
                print()
                print(f"Both methods consistent ? {np.allclose(transform, transform2)}")

        return ReferenceFrame(transformation=transform, ref=self.ref)



    def fitPlane(self,fitPlane="xy",verbose=True):
        """
        fitPlane(self,fitPlane="xy",verbose=True)

        :returns: the best fitting parameters a, b, c corresponding to the fitted plane

        :param fitPlane: defines the expression of the fitted plane in ['xy','yz','zx']:
                         'xy' : z = ax + by + c
                         'yz' : x = ay + bz + c
                         'zx' : y = az + bx + c

        :param verbose: default = True
        """
        xyz = [self.x,self.y,self.z]

        ndata = len(xyz[0])

        # Account for cases
        startingIndex={'xy':0,'yz':1,'zx':2}[fitPlane]

        # System matrix
        A = np.vstack([xyz[startingIndex],xyz[(startingIndex+1)%3], np.ones(ndata)]).T

        # Solve linear equations
        a, b, c = np.linalg.lstsq(A, xyz[(startingIndex+2)%3],rcond=None)[0]

        # Print results on screen
        if verbose:
            hprint = {'xy':'z = ax + by + c','yz':'x = ay + bz + c','zx':'y = az + bx + c'}
            print(f'{hprint[fitPlane]} : \n    a = {a:7.3e}  \n    b = {b:7.3e} \n    c = {c:7.3e}')

        return a,b,c

    @classmethod
    def fromPlaneParameters(cls,a,b,c,ref,plane='xy',verbose=False):
        """fromPlaneParameters(cls,a,b,c,ref,plane='xy',verbose=False)

        Returns a Points object describing the unit axes and the origin of the reference frame defined by
        the input parameters.

        :param plane: The plane definition depends on the "plane" parameter plane must be in ["xy","yz","zx"]
                      'xy' : z = ax + by + c (origin defined at x = y = 0)
                      'yz' : x = ay + bz + c  --> NOT IMPLEMENTED
                      'zx' : y = az + bx + c  --> NOT IMPLEMENTED

        :returns:  A Points with 4 Point objects corresponding to
                   - the 3 unit axes defining a coordinate system with this plane as "plane" plane
                   - the origin
                   in this order (origin last)
        """
        if plane != 'xy':
            print(f"WARNING: plane = {plane} NOT IMPLEMENTED")
        # p0 : on the Z-axis
        # x = y = 0
        p0 = np.array([0,0,c])

        # pxy : on the intersection between target plane and plane // to xy passing through z=c
        if np.abs(b)>1.e-5:
            # z = c, x = 1
            pxy = np.array([1,-a/float(b),c])
        else:
            # z = c, y = 1
            pxy = np.array([-b/float(a),1,c])

        # pyz : intersection of target plane and Y-Z plane
        # x = 0, y = 1
        pyz = np.array([0,1,b+c])

        """
        # pzx : intersection of target plane and Z-X plane
        if np.abs(a)>1.e-3:
            # y = 0, z = 1
            pzx = np.array([(1-c)/float(a),0,1])
        else:
            # y = 0, x = 1
            pzx = np.array([1,0,a+c])
        """
        #
        # xunit = unit vector from [0,0,0] along the intersection between target plane and plane // to xy passing through z=c
        xunit = (pxy - p0)/np.linalg.norm(pxy-p0)
        # ytemp = unit vector from [0,0,0] along the intersection between target plane and Y-Z plane
        # ytemp is in the target plane, but not perpendicular to xunit
        # its norm doesn't matter
        ytemp = (pyz - p0)#/np.linalg.norm(pyz-p0)

        # xunit and ytemp are both in the plane
        # => zunit is perpendicular to both
        zunit = np.cross(xunit,ytemp)
        zunit /= np.linalg.norm(zunit)

        # yunit completes the right handed reference frame
        # The renormalisation shouldn't be necessary...
        yunit = np.cross(zunit,xunit)
        yunit /= np.linalg.norm(yunit)

        xu = Point(xunit,ref=ref)
        yu = Point(yunit,ref=ref)
        zu = Point(zunit,ref=ref)
        origin = Point(p0,ref=ref)

        if verbose:
            print(f'xunit  {xunit}')
            print(f'yunit  {yunit}')
            print(f'zunit  {zunit}')
            print(f'origin {p0}')
            print()

        return cls([xu,yu,zu,origin],ref=ref)
