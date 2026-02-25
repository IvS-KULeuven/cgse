""" " This module contains plotting utility functions for reference frames."""

import matplotlib
import matplotlib.pyplot as plt
from egse.coordinates.reference_frame import ReferenceFrame
import numpy as np
import egse
from egse.coordinates.point import Point, Points


def plot_reference_frame(
    frame: ReferenceFrame, master: ReferenceFrame | None = None, fig_name: str | None = None, **kwargs
):
    """Plots a reference frame.

    Use ax.set_xlim3d(min, max) to properly set the ranges of the display.

    Args:
        frame (ReferenceFrame): Reference frame
        master (ReferenceFrame | None): Optional master reference frame.
        fig_name (str): Name of the plot figure.
        kwargs : Keyword arguments passed to matplotlib.axes._subplots.Axes3DSubplot.quiver.

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot displaying the reference frame.  The three unit vectors are shown in
        the following colours (RGB):
            x: Red
            y: Green
            z: Blue
    """

    if master is None:
        temp_master = ReferenceFrame.create_master()
    else:
        temp_master = master.__copy__()

    # Origin and unit axes of the reference frame

    origin = frame.get_origin()
    unit_axis_x = frame.get_axis("x", name="fx")
    unit_axis_y = frame.get_axis("y", name="fy")
    unit_axis_z = frame.get_axis("z", name="fz")

    # Now expressed in the master reference frame

    origin_master = origin.express_in(temp_master)[:3]
    unit_axis_x_master = unit_axis_x.express_in(temp_master)[:3]
    unit_axis_y_master = unit_axis_y.express_in(temp_master)[:3]
    z_axis_master = unit_axis_z.express_in(temp_master)[:3]

    del temp_master

    # Coordinates of the origin, expressed in the master reference frame
    origin_x_master, origin_y_master, origin_z_master = (
        np.array([origin_master[0]]),
        np.array([origin_master[1]]),
        np.array([origin_master[2]]),
    )

    # Orientation of the unit vectors of the reference frame, expressed in the master reference frame

    vecxx, vecyx, veczx = (
        np.array([unit_axis_x_master[0] - origin_master[0]]),
        np.array([unit_axis_y_master[0] - origin_master[0]]),
        np.array([z_axis_master[0] - origin_master[0]]),
    )
    vecxy, vecyy, veczy = (
        np.array([unit_axis_x_master[1] - origin_master[1]]),
        np.array([unit_axis_y_master[1] - origin_master[1]]),
        np.array([z_axis_master[1] - origin_master[1]]),
    )
    vecxz, vecyz, veczz = (
        np.array([unit_axis_x_master[2] - origin_master[2]]),
        np.array([unit_axis_y_master[2] - origin_master[2]]),
        np.array([z_axis_master[2] - origin_master[2]]),
    )

    kwargs.setdefault("length", 1)
    kwargs.setdefault("normalize", True)
    # kwargs.setdefault('figsize', (10,10))

    fig = plt.figure(fig_name, figsize=plt.figaspect(1.0))
    ax = fig.add_subplot(projection="3d")
    ax.quiver(origin_x_master, origin_y_master, origin_z_master, vecxx, vecxy, vecxz, color="r", **kwargs)
    ax.quiver(origin_x_master, origin_y_master, origin_z_master, vecyx, vecyy, vecyz, color="g", **kwargs)
    ax.quiver(origin_x_master, origin_y_master, origin_z_master, veczx, veczy, veczz, color="b", **kwargs)
    # ax.axis('equal')

    return ax


def plot_points(
    points: Points | list[Point], master=None, fig_name: str | None = None, **kwargs
):
    """Plots the given collection of points.

    Use ax.set_xlim3d(min, max) to properly set the ranges of the display.

    Args:
        points (Points | list[Point]): Collection of points to plot.
        master (ReferenceFrame | None): Optional master reference frame.
        fig_name (str): Name of the plot figure.
        kwargs : Keyword arguments passed to matplotlib.axes._subplots.Axes3DSubplot.scatter.

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot displaying the given collection of points
    """

    if master is None:
        temp_master = ReferenceFrame.create_master()
    else:
        temp_master = master.__copy__()

    if isinstance(points, list):
        all_points = Points(points, reference_frame=temp_master)
    elif isinstance(points, Points) or isinstance(points, egse.coordinates.point.Points):
        all_points = points
    else:
        raise ValueError("If the input is a list, all items in it must be Point objects")

    del temp_master

    coordinates = all_points.coordinates
    xs = coordinates[0, :]
    ys = coordinates[1, :]
    zs = coordinates[2, :]

    kwargs.setdefault("s", 50)
    kwargs.setdefault("marker", "o")
    kwargs.setdefault("color", "k")

    fig = plt.figure(fig_name)
    ax = fig.add_subplot(projection="3d")
    ax.scatter(xs, ys, zs, **kwargs)

    return ax


def plot_vectors(
    points: Points | list[Point], master=None, fig_name: str | None = None, from_origin: bool = True, **kwargs
):
    """Plots the given collection of vectors.

    Use ax.set_xlim3d(min, max) to properly set the ranges of the display.

    Args:
        points (Points | list[Point]): Collection of vectors to plot.
        master (ReferenceFrame | None): Optional master reference frame.
        fig_name (str): Name of the plot figure.
        kwargs : Keyword arguments passed to matplotlib.axes._subplots.Axes3DSubplot.scatter.

    Returns:
        matplotlib.axes._subplots.Axes3DSubplot displaying the given collection of points
    """

    if master is None:
        temp_master = ReferenceFrame.create_master()
    else:
        temp_master = master.__copy__()

    if isinstance(points, list):
        all_points = Points(points, reference_frame=temp_master)
    elif isinstance(points, Points) or isinstance(points, egse.coordinates.point.Points):
        all_points = points
    else:
        raise ValueError("If the input is a list, all items in it must be Point objects")

    del temp_master

    kwargs.setdefault("color", "k")

    # Prepare vector coordinates

    coordinates = all_points.coordinates
    xs = coordinates[0, :]
    ys = coordinates[1, :]
    zs = coordinates[2, :]

    # Origin of the x, y, and z vectors
    # -> x = The x coordinates of the origin of all vectors
    # -> [x,y,z] = Origin of points.reference_frame
    x, y, z = points.reference_frame.get_origin().coordinates[:3]
    x = np.ones_like(xs) * x
    y = np.ones_like(xs) * y
    z = np.ones_like(xs) * z

    # Plot

    fig = plt.figure(fig_name)
    ax = fig.gca(projection="3d")

    if from_origin:
        ax.quiver(x, y, z, xs - x, ys - y, zs - z, **kwargs)

    elif not from_origin:
        ax.quiver(xs, ys, zs, x - xs, y - ys, z - zs, **kwargs)

    else:
        print("Parameter 'from_origin' must be True or False")
        print("Setting it to True by default")
        ax.quiver(x, y, z, xs - x, ys - y, zs - z, **kwargs)

    return ax
