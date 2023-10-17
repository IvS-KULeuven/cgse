#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module defines some plotting functions for Reference Frames.

@author: Pierre Royer
"""

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # needed for 3d projection
import numpy as np
import egse
from egse.coordinates.referenceFrame import ReferenceFrame
from egse.coordinates.point import Point, Points


def plot_reference_frame(frame, master=None, figname=None, **kwargs):
    """Plot a Reference Frame.

    Args:
        frame  : egse.coordinates.referenceFrame.ReferenceFrame
        master : master ReferenceFrame (optional)
        figname: string. Name of matplotlib figure (can be pre-existing)
        kwargs : passed to matplotlib.axes._subplots.Axes3DSubplot.quiver

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot displaying the reference frame.

        The three unit vectors are shown with the following colors ('RGB'):
            x: Red
            y: Green
            z: Blue

    .. note::
        Use ax.set_xlim3d(min,max) to properly set the ranges of the display

    """
    if master is None:
        tmpmaster = ReferenceFrame.createMaster()
    else:
        tmpmaster = master.__copy__()

    f0 = frame.getOrigin()
    fx = frame.getAxis('x', name='fx')
    fy = frame.getAxis('y', name='fy')
    fz = frame.getAxis('z', name='fz')
    f0m = f0.expressIn(tmpmaster)[:3]
    fxm = fx.expressIn(tmpmaster)[:3]
    fym = fy.expressIn(tmpmaster)[:3]
    fzm = fz.expressIn(tmpmaster)[:3]
    del tmpmaster

    # Origin of the X,Y and Z vectors (x = the 'x' coordinates of the origin of all 3 vectors)
    # Every vector independently (--> plot in diff. colors)
    x, y, z = np.array([f0m[0]]), np.array([f0m[1]]), np.array([f0m[2]])

    # Orientation of the X,Y and Z vectors
    vecxx, vecyx, veczx = np.array([fxm[0] - f0m[0]]), np.array([fym[0] - f0m[0]]), np.array([fzm[0] - f0m[0]])
    vecxy, vecyy, veczy = np.array([fxm[1] - f0m[1]]), np.array([fym[1] - f0m[1]]), np.array([fzm[1] - f0m[1]])
    vecxz, vecyz, veczz = np.array([fxm[2] - f0m[2]]), np.array([fym[2] - f0m[2]]), np.array([fzm[2] - f0m[2]])

    kwargs.setdefault('length', 1)
    kwargs.setdefault('normalize', True)
    #kwargs.setdefault('figsize', (10,10))

    fig = plt.figure(figname, figsize=plt.figaspect(1.0))
    ax = fig.gca(projection='3d')
    ax.quiver(x, y, z, vecxx, vecxy, vecxz, color='r', **kwargs)
    ax.quiver(x, y, z, vecyx, vecyy, vecyz, color='g', **kwargs)
    ax.quiver(x, y, z, veczx, veczy, veczz, color='b', **kwargs)
    #ax.axis('equal')

    return ax


def plot_points(points, master=None, figname=None, **kwargs):
    """Plot the Points object.

    Args:
        points : either a (egse.coordinate.point.)Points object or a list of Point objects
        master : master ReferenceFrame (optional)
        figname: string. Name of matplotlib figure (can be pre-existing)
        kwargs : passed to matplotlib.axes._subplots.Axes3DSubplot.scatter

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot displaying the reference frame.

    .. note::
        Use ax.set_xlim3d(min,max) to properly set the ranges of the display.

    """
    if master is None:
        tmpmaster = ReferenceFrame.createMaster()
    else:
        tmpmaster = master.__copy__()
    #
    if isinstance(points, list):
        allpoints = Points(points, ref=tmpmaster)
    elif isinstance(points, Points) or isinstance(points, egse.coordinates.point.Points):
        allpoints = points
    else:
        raise ValueError("If the input is a list, all items in it must be Point objects")
    #
    del tmpmaster
    #
    coordinates = allpoints.coordinates
    xs = coordinates[0, :]
    ys = coordinates[1, :]
    zs = coordinates[2, :]
    #
    kwargs.setdefault('s', 50)
    kwargs.setdefault('marker', 'o')
    kwargs.setdefault('color', 'k')
    #
    fig = plt.figure(figname)
    ax = fig.gca(projection='3d')
    ax.scatter(xs, ys, zs, **kwargs)

    return ax


def plot_vectors(points, master=None, figname=None, fromorigin=True, **kwargs):
    """Plot the Points object.

    Args:
        points : either a (egse.coordinate.point.)Points object or a list of Point objects
        master : master ReferenceFrame (optional)
        figname: string. Name of matplotlib figure (can be pre-existing)
        fromorigin: bool
                    if True, all vectors are displayed starting from the origin
                    if False, all vectors go towards the origin
        kwargs : passed to matplotlib.axes._subplots.Axes3DSubplot.scatter

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot displaying the reference frame.

    .. note::
        Use ax.set_xlim3d(min,max) to properly set the ranges of the display.

    """
    #from egse.coordinates.point import Points

    if master is None:
        tmpmaster = ReferenceFrame.createMaster()
    else:
        tmpmaster = master.__copy__()
    #
    if isinstance(points, list):
        allpoints = Points(points, ref=tmpmaster)
    elif isinstance(points, Points) or isinstance(points, egse.coordinates.point.Points):
        allpoints = points
    else:
        raise ValueError("If the input is a list, all items in it must be Point objects")
    #
    del tmpmaster
    #

    # SET DEFAULTS
    kwargs.setdefault('color', 'k')
    #

    # PREPARE VECTOR COORDINATES
    coordinates = allpoints.coordinates
    xs = coordinates[0, :]
    ys = coordinates[1, :]
    zs = coordinates[2, :]

    # Origin of the X,Y and Z vectors
    # ==> x = the 'x' coordinates of the origin of all vectors)
    # ==> [x,y,z] = the origin of points.ref
    x, y, z = points.ref.getOrigin().coordinates[:3]
    x = np.ones_like(xs) * x
    y = np.ones_like(xs) * y
    z = np.ones_like(xs) * z

    ### PLOT

    fig = plt.figure(figname)
    ax = fig.gca(projection='3d')

    if fromorigin == True:

        ax.quiver(x, y, z, xs-x, ys-y, zs-z, **kwargs)

    elif fromorigin == False:

        ax.quiver(xs, ys, zs, x-xs, y-ys, z-zs, **kwargs)

    else:
        print("Parameter 'fromorigin' must be True or False")
        print("Setting it to True by default")
        ax.quiver(x, y, z, xs-x, ys-y, zs-z, **kwargs)

    return ax

