"""
The RotationMatrix provides a number of convenience methods to define and apply rotations.

@author: pierre
"""

import transforms3d as t3
import numpy as np

class RotationMatrix():
    """
    RotationMatrix(angle1, angle2, angle3, rot_config="sxyz", active=True)
    
    The ``angle`` parameters provide the amplitude of rotation around an axis 
    according to the order of rotations corresponding to the ``rot_config`` parameter.

    The ``rot_config`` parameter is a string that consists of four letter
    indicating the rotation system and the order of applying the rotations. The default 
    for this parameter is ``"rxyz"`` where the first character can be 'r' or 's' and 
    the next three characters define the axes of rotation in the order specified, here 'xyz'.

    * 'r' stands for rotating system (intrinsic rotations)
    * 's' stands for static system (extrinsic rotations)
    * "rxyz" imposes angle1 describes the rotation around X
    * even if two angles = 0, the match between angle orders and rot_config is still critical
    
    :param str rot_config: otation system to be used, 4 characters. Default = "sxyz"

    :param float angle1: amplitude of rotations around the first axis

    :param float angle2: amplitude of rotations around the second axis
    
    :param float angle3: amplitude of rotations around the third axis
    
    :param bool active: when True the object rotates **in** a fixed coord system,
        when False the coord system rotates **around** a fixed object
        The default for the transform3d.euleur package is to represent movements
        of the coordinate system itself --> **around** the object <==> passive
    """
    _ROT_CONFIG_DEFAULT = 'sxyz'

    def __init__(self,angle1,angle2,angle3,rot_config=_ROT_CONFIG_DEFAULT,active=True):
        R = t3.euler.euler2mat(angle1,angle2,angle3,rot_config)
        if active:
            self.R = R
        else:
            self.R = R.T
        rot_config_array = np.array(list(rot_config[1:]))
        angles_array = np.array([angle1,angle2,angle3])
        self.angles_hash = {}
        for axis in ['x','y','z']:
            self.angles_hash[axis] = angles_array[np.where(rot_config_array==axis)[0][0]]
        self.active=active


    def getRotationMatrix(self):
        '''Return the Rotation Matrix'''
        return self.R


    def trace(self):
        return np.sum([self.R[i,i] for i in range(3)])


    def getAngle(self, axis):
        """
        Returns the angle 

        :param str axis: 'x', 'y', 'z'

        :return: the angle 
        """
        return self.angles_hash[axis]


    def apply(self, vectors):
        """
        if self = active, the output = the coords of these vectors after rotation

        if self = passive, the ouput = the coords of these vectors after transformation to the rotated coordinate system

        :param vectors: an array of shape [3,N] gathering a set of vectors along its columns
        """
        return np.dot(self.R, vectors)

