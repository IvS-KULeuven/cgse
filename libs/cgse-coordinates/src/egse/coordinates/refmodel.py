"""
The Reference Frame Model is a self-consistent graph of reference frames that are connected by
reference and/or by explicit links.

The ReferenceFrameModel class will keep the model consistent and self-contained.

Functionality:

* Initialization from a list of ReferenceFrames.
* Serialization into a dictionary that can be saved into a YAML file.
* Manipulation of the model
    * Move a reference frame (translation, rotation) with respect to another reference frame
        * Absolute movement, center of rotation either local or other
        * Relative Movement, center of rotation either local or other
    * Move a reference frame (translation, rotation) with respect to itself
        * Absolute movement
        * Relative Movement
    * Change the definition of a reference frame in the model
* Inspection of the model
    * Get the definition of a reference frame (what should this be? only translation & rotation?)
    * Get position of a reference frame
    * Get the position of a point in a 'target' reference frame, but defined in a 'source'
      reference frame
    * Get a string representation of the model.
    * Find inconsistencies in the model
    * What other information do we need?
        * find the path from one reference frame to another reference frame?
        * find all reference frames that are affected by a movement or redefinition of a
          reference frame?
        * ...

"""

import logging
from typing import Dict
from typing import List

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import ScaledTranslation
from mpl_toolkits.mplot3d import Axes3D

import egse.coordinates.transform3d_addon as t3add
from egse.coordinates import dict_to_ref_model
from egse.coordinates import ref_model_to_dict
from egse.setup import NavigableDict

LOGGER = logging.getLogger(__name__)

# TODO : HANDLING "moving_in_ref" (obusr)  in move_absolute_ext and move_relative_ext
#        should it be added to the model temporarily ??
#        after the move : remove the link and delete that frame
#
# Priority 1
#   * access methods to allow for things like is_avoidance_ok(hexsim.cs_user, hexsim.cs_object,
#     setup=setup, verbose=True)
#
#  Priority 2
#   * Move name handling from ReferenceFrame to here (if necessary)


class ReferenceFrameModel:
    """
    A ReferenceFrameModel is a collection of reference frames that are linked to each other to
    form a Graph.
    """

    _ROT_CONFIG_DEFAULT = "sxyz"
    _ACTIVE_DEFAULT = True
    _DEGREES_DEFAULT = True

    def __init__(
        self,
        model: Dict | List = None,
        rotation_config: str = _ROT_CONFIG_DEFAULT,
        use_degrees: bool = _DEGREES_DEFAULT,
        use_active_movements: bool = _ACTIVE_DEFAULT,
    ):
        """Initialisation of a reference frame model.

        Args:
            model (Dict | List[ReferenceFrame]): List or a dictionary of reference frames that make up the model.
            rotation_config (str): Order in which the rotation about the three axes are chained.
            use_degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
            use_active_movements (bool): Indicates if the rotation is active (object rotates IN a fixed coordinate
                                         system) or passive (coordinate system rotates AROUND a fixed object).  Even if
                                         two angles are zero, the match between angle orders and rot_config is still
                                         critical.
        """

        self._use_degrees = use_degrees
        self._use_active_movements = use_active_movements
        self._rot_config = rotation_config

        # Keep a dictionary with all reference frames that are part of the model. The keys shall
        # be the name of the reference frame. When the model passed is empty, create only a
        # master reference frame.

        if isinstance(model, (dict, list)):
            self._model = self.deserialize(model)
        else:
            self._model = NavigableDict({})

    def __str__(self) -> str:
        """Returns a printable string representation of the reference frame.

        Returns:
            Printable string representation of the reference frame.
        """

        return self._model.pretty_str()

    def __len__(self) -> int:
        """Returns the number of reference frames in the model."""

        return len(self._model)

    def __contains__(self, item) -> bool:
        """Checks whether the given item is present in the model.

        Args:
            item: Item for which to check whether it's present in the model.

        Returns:
            True if the given item is present in the model; False otherwise.
        """

        return item in self._model

    def __iter__(self):
        """Returns an iterator over the reference frames in the model."""

        return iter(self._model.values())

    def summary(self) -> str:
        """Returns a summary of the model.

        Returns:
            String summary of the model.
        """

        result = f"Number of frames: {len(self)}\n"

        for reference_frame in self:
            result += f"{reference_frame.name:>10}[{reference_frame.reference_frame.name}]  ---  {[link.name for link in reference_frame.linked_to]}\n"

        return result

    @staticmethod
    def deserialize(model_dict: dict) -> NavigableDict:
        """De-serialisation of the model.

        De-serialisation means you take a serialised representation of a reference frames model and turn it into a
        dictionary containing all the reference frames with their links and references.

        Args:
            model_dict (dict): Dictionary of serialised reference frames.

        Returns:
            Dictionary of reference frames that make up a model.

        """
        return dict_to_ref_model(model_dict)

    def serialize(self) -> NavigableDict:
        """Serialisation of the model.


        Serialisation of the model by serialising each of the reference frames into an object that can easily be saved
        to a YAML or a JSON file.

        Returns:
            Dictionary with all the serialised reference framed.
        """

        return ref_model_to_dict(self._model)

    def add_master_frame(self) -> None:
        """Adds the master reference frame to the model."""

        # TODO: First check if there is not already a Master frame in the model

        from egse.coordinates.reference_frame import ReferenceFrame

        self._model["Master"] = ReferenceFrame.create_master()

    def add_frame(
        self,
        name: str,
        *,
        translation: np.ndarray = None,
        rotation: np.ndarray = None,
        transformation: np.ndarray = None,
        reference: str,
    ) -> None:
        """Adds a reference frame to the model.

        Args:
            name (str): Name of the reference frame to add to the model.  Only this parameter can be positional.  This
                        will serve as the identifier for the reference frame in the model.
            translation (np.ndarray): Translation vector. Ignored when `transformation` is given.
            rotation (np.ndarray: Rotation vector. Ignored when `transformation` is given.
            transformation (np.ndarray): Transformation matrix.
            reference (str): Name of the reference frame that is a reference for the new reference frame, i.e. the new
                             reference frame is defined w.r.t. this one.
        """

        from egse.coordinates.reference_frame import ReferenceFrame

        if name in self._model:
            raise KeyError("A reference frame with the name '{name} already exists in the model.")

        reference = self._model[reference]

        if transformation:
            self._model[name] = ReferenceFrame(
                transformation,
                reference_frame=reference,
                name=name,
                rotation_config=self._rot_config,
            )
        else:
            self._model[name] = ReferenceFrame.from_translation_rotation(
                translation,
                rotation,
                name=name,
                reference_frame=reference,
                rotation_config=self._rot_config,
                degrees=self._use_degrees,
                active=self._use_active_movements,
            )

    def remove_frame(self, name: str):
        """Deletes the given reference frame from the model.

        If the reference frame doesn't exist in the model, a warning message is logged.

        Args:
            name (str): Name of the reference frame to remove.
        """

        if name in self._model:
            from egse.coordinates.reference_frame import ReferenceFrame

            frame: ReferenceFrame = self._model[name]

            # We need to get the links out in a list because the frame.remove_link() method deletes
            # frames from the linked_to dictionary and that is not allowed in a for loop.

            links = [linked_frame for linked_frame in frame.linked_to]
            for link in links:
                frame.remove_link(link)

            del self._model[name]
        else:
            LOGGER.warning(f"You tried to remove a non-existing reference frame '{name}' from the model.")

    def get_frame(self, name: str):
        """Returns the reference frame with the given name.

        Use this function with care since this breaks encapsulation and may lead to an inconsistent model when the frame
        is changed outside the scope of the reference model.

         Args:
             name (str): Name of the requested reference frame.

         Returns:
             Reference frame with the given name.
        """

        return self._model[name]

    def add_link(self, source: str, target: str):
        """Adds a link between the two given reference frames of the model.

        All links are bi-directional.

        Args:
            source (args): Name of the source reference frame.
            target (args): Name of the target reference frame.
        """

        if source not in self._model:
            raise KeyError(f"There is no reference frame with the name '{source} in the model.")
        if target not in self._model:
            raise KeyError(f"There is no reference frame with the name '{target} in the model.")

        source = self._model[source]
        target = self._model[target]

        source.add_link(target)

    def remove_link(self, source: str, target: str):
        """Removes a link between two reference frames.

        All links are bi-directional and this method removes both links.

        Args:
            source (args): Name of the source reference frame.
            target (args): Name of the target reference frame.
        """

        if source not in self._model:
            raise KeyError(f"There is no reference frame with the name '{source} in the model.")
        if target not in self._model:
            raise KeyError(f"There is no reference frame with the name '{target} in the model.")

        source = self._model[source]
        target = self._model[target]

        source.remove_link(target)

    def move_absolute_self(
        self, name: str, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ) -> None:
        """Applies an absolute movement to the given reference frame.

        Applies an absolute movement to the given reference frame such that it occupies a given absolute position w.r.t.
        "frame_ref" after the movement.

        There is no hexapod equivalent.

        Args:
            name (str): Name of the reference frame to move.
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.

        Args:
            name (str): the name of the reference frame to move
        """

        name = self._model[name]
        name.set_translation_rotation(
            translation,
            rotation,
            rotation_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserve_links=True,
        )

    def move_absolute_in_other(
        self, frame: str, other: str, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ):
        """Applies an absolute movement to the given reference frame in another reference frame.

        Apply an absolute movement to the ReferenceFrame "frame", such that it occupies a given absolute position
        w.r.t. "other" after the movement.

        Hexapod equivalent: PunaSimulator.move_absolute, setting `hexobj` w.r.t. `hexusr`.

        Args:
            frame (str): Name of the reference frame to move.
            other (str): Name of the other reference frame.
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        # TODO:
        #   There can not be a link between frame and other, not direct and not indirect.
        #   So, with A-link-B-link-C-link-D, we can not do move_absolute_in_other('A', 'D', ...)

        frame = self._model[frame]
        other = self._model[other]

        transformation = other.get_active_transformation_to(frame)

        from egse.coordinates.reference_frame import ReferenceFrame

        moving_in_other = ReferenceFrame(
            transformation, rotation_config=self._rot_config, reference_frame=other, name="moving_in_other"
        )

        moving_in_other.add_link(frame)

        moving_in_other.set_translation_rotation(
            translation,
            rotation,
            rotation_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserve_links=True,
        )

        moving_in_other.remove_link(frame)

        del moving_in_other

    def move_relative_self(
        self, frame: str, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ):
        """Applies a relative movement to the given reference frame.

        It is assumed that the movement is expressed in that same reference frame.

        Hexapod equivalent: PunaSimulator.move_relative_object

        Args:
            frame (str): Name of the reference frame to move.
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        frame = self._model[frame]
        frame.apply_translation_rotation(
            translation,
            rotation,
            rotation_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserve_links=True,
        )

    def move_relative_other(
        self, frame: str, other: str, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ):
        """Applies a relative movement to the given reference frame.

        The movement is expressed w.r.t. the axes of another frame.  The centre of rotation is the origin of the
        that other reference frame.

        There is no hexapod equivalent.

        Args:
            frame (str): Name of the reference frame to move.
            other (str): Name of the reference frame in which the movements have been defined.
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        # TODO:
        #   There can not be a link between frame and other, not direct and not indirect.
        #   So, with A-link-B-link-C-link-D, we can not do move_absolute_in_other('A', 'D', ...)

        frame = self._model[frame]
        other = self._model[other]

        transformation = frame.get_active_transformation_to(other)

        from egse.coordinates.reference_frame import ReferenceFrame

        moving_in_other = ReferenceFrame(
            transformation, rotation_config=self._rot_config, reference_frame=other, name="moving_in_other"
        )

        moving_in_other.add_link(frame)

        moving_in_other.apply_translation_rotation(
            translation,
            rotation,
            rotation_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserve_links=True,
        )

        moving_in_other.remove_link(frame)

        del moving_in_other  # not need as local scope

    def move_relative_other_local(
        self, frame: str, other: str, translation: np.ndarray, rotation: np.ndarray, degrees: bool = _DEGREES_DEFAULT
    ):
        """Applies a relative movement to the given reference frame.

        The movement is expressed w.r.t. the axes of another reference frame.  The centre of rotation is the origin of
        that other reference frame.

        Hexapod equivalent: PunaSimulator.move_relative_user

        Args:
            frame (str): Name of the reference frame to move.
            other (str): Name of the reference frame in which the movements have been defined.
            translation (np.ndarray): Translation vector.
            rotation (np.ndarray): Rotation vector.
            degrees (bool): Indicates whether the rotation angles are specified in degrees, rather than radians.
        """

        # TODO:
        #   There can not be a link between frame and other, not direct and not indirect.
        #   So, with A-link-B-link-C-link-D, we can not do move_absolute_in_other('A', 'D', ...)

        frame = self._model[frame]
        other = self._model[other]

        # Represent the requested movement
        # De-rotation of MOVING -> REF  (align frame_moving axes on those of frame_ref)

        derotation = frame.get_active_transformation_to(other)
        derotation[:3, 3] = [0, 0, 0]

        # Reverse rotation (record inverse rotation, to restore the frame in the end)

        rerotation = derotation.T

        # Requested translation matrix  (already expressed wrt frame_ref)

        translation_ = np.identity(4)
        translation_[:3, 3] = translation

        # Requested rotation matrix (already expressed wrt frame_ref)

        zeros = [0, 0, 0]
        rotation_ = t3add.translation_rotation_to_transformation(
            zeros, rotation, rotation_config=self._rot_config, degrees=degrees
        )

        # All translations and rotations are applied to frame_moving
        # -> a. Need for "de-rotation" before applying the translation
        #    b. The centre of rotation is always the origin of frame_moving
        # 1. Rotate frame_moving to align it with frame_ref (i.e. render their axes parallel)
        # 2. Apply the translation in this frame
        # 3. Restore the original orientation of the moving frame
        # 4. Apply the requested rotation

        transformation = derotation @ translation_ @ rerotation @ rotation_

        # Apply the requested movement

        frame.apply_transformation(transformation, preserve_links=True)


def plot_ref_model(model: ReferenceFrameModel) -> None:
    """Plots the xz-plane of the given reference frame model."""

    # figsize is in inch, 6 inch = 15.24 cm, 5 inch = 12.7 cm

    fig = plt.figure(figsize=(6, 5), dpi=100)

    ax = fig.add_subplot(1, 1, 1)

    # Set axes limits in data coordinates

    ax.set_xlim(-10, 10)
    ax.set_ylim(-10, 10)
    ax.set_xticks(range(-10, 11, 2))
    ax.set_yticks(range(-10, 11, 2))
    ax.grid(True)

    for frame in model:
        draw_frame(ax, frame, plane="xz")

    plt.show()


def plot_ref_model_3d(model: ReferenceFrameModel) -> None:
    """Plots the given reference frame model in 3D."""

    fig = plt.figure(figsize=(8, 8), dpi=100)
    ax = Axes3D(fig)
    # ax.set_box_aspect([1, 1, 1])

    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("z")

    def get_fix_mins_maxs(mins, maxs):
        deltas = (maxs - mins) / 12.0
        mins = mins + deltas / 4.0
        maxs = maxs - deltas / 4.0

        return [mins, maxs]

    min_ = -8
    max_ = 8
    minmax = get_fix_mins_maxs(min_, max_)

    # ax.set_xticks(range(min_, max_, 2))
    # ax.set_yticks(range(min_, max_, 2))
    # ax.set_zticks(range(min_, max_, 2))

    ax.set_xlim(minmax)
    ax.set_ylim(minmax)
    ax.set_zlim(minmax)

    delta = 0.1
    ax.scatter(
        [min_ + delta, max_ - delta],
        [min_ + delta, max_ - delta],
        [min_ + delta, max_ - delta],
        color="k",
        marker=".",
    )

    for frame in model:
        draw_frame_3d(ax, frame)

    # ax.set_proj_type('ortho')
    ax.set_proj_type("persp")

    set_axes_equal(ax)
    plt.show()


def set_axes_equal(ax: plt.Axes) -> None:
    """Sets 3D plot axes to equal scale.

    Make axes of 3D plot have equal scale so that spheres appear as spheres and cubes as cubes.  Required since
    `ax.axis('equal')` and `ax.set_aspect('equal')` don't work on 3D.

    The aspect rati0 of the plots is not equal by default.  This solution was given in Stack Overflow:
    https://stackoverflow.com/a/63625222/4609203
    """

    limits = np.array([ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()])
    origin = np.mean(limits, axis=1)
    radius = 0.5 * np.max(np.abs(limits[:, 1] - limits[:, 0]))
    x, y, z = origin
    ax.set_xlim3d([x - radius, x + radius])
    ax.set_ylim3d([y - radius, y + radius])
    ax.set_zlim3d([z - radius, z + radius])


def draw_frame_3d(ax: Axes3D, frame, **kwargs) -> None:
    """Draws the given frame in 3D.

    Args:
        ax (Axes3D): Axis to draw the frame in.
        frame (ReferenceFrame): Reference frame to draw.
        **kwargs: Keyword arguments to pass to the quiver function.
    """

    master = frame.find_master()

    f0 = frame.get_origin()
    fx = frame.get_axis("x", name="fx")
    fy = frame.get_axis("y", name="fy")
    fz = frame.get_axis("z", name="fz")
    f0m = f0.express_in(master)[:3]
    fxm = fx.express_in(master)[:3]
    fym = fy.express_in(master)[:3]
    fzm = fz.express_in(master)[:3]

    # Origin of the x, y. and z vectors (x = the 'x' coordinates of the origin of all 3 vectors)
    # Every vector independently (-> plot in different colours)

    x, y, z = np.array([f0m[0]]), np.array([f0m[1]]), np.array([f0m[2]])

    # Orientation of the x, y, and z vectors

    vecxx, vecyx, veczx = (
        np.array([fxm[0] - f0m[0]]),
        np.array([fym[0] - f0m[0]]),
        np.array([fzm[0] - f0m[0]]),
    )
    vecxy, vecyy, veczy = (
        np.array([fxm[1] - f0m[1]]),
        np.array([fym[1] - f0m[1]]),
        np.array([fzm[1] - f0m[1]]),
    )
    vecxz, vecyz, veczz = (
        np.array([fxm[2] - f0m[2]]),
        np.array([fym[2] - f0m[2]]),
        np.array([fzm[2] - f0m[2]]),
    )

    kwargs.setdefault("length", 2)
    kwargs.setdefault("normalize", True)

    ax.quiver(x, y, z, vecxx, vecxy, vecxz, color="r", **kwargs)
    ax.quiver(x, y, z, vecyx, vecyy, vecyz, color="g", **kwargs)
    ax.quiver(x, y, z, veczx, veczy, veczz, color="b", **kwargs)

    offset = 0.1
    ax.text(f0m[0] + offset, f0m[1] + offset, f0m[2] + offset, frame.name)


def draw_frame(ax: plt.Axes, reference_frame, plane="xz", default_axis_length: int = 100) -> None:
    """Draws the given plane from the given reference frame in the given axis.

    Args:
        ax (plt.Axes): Axis to draw the plane in.
        reference_frame (ReferenceFrame): Reference frame to draw.
        plane (str, optional): Kind of plane to draw.  Must be in ["xy", "yz", "zx"].
        default_axis_length (int): Axis length.
    """

    fig = ax.get_figure()

    # FC : Figure coordinates (pixels)
    # NFC : Normalized figure coordinates (0 → 1)
    # DC : Data coordinates (data units)
    # NDC : Normalized data coordinates (0 → 1)

    dc2fc = ax.transData.transform
    fc2dc = ax.transData.inverted().transform
    fc2ndc = ax.transAxes.inverted().transform

    def dc2ndc(x):  # better than defining and assigning a lambda function
        return fc2ndc(dc2fc(x))

    x_idx, y_idx = {"xz": (0, 2), "xy": (0, 1), "yz": (1, 2)}[plane]

    # Draw the origin

    origin = reference_frame.get_origin()
    origin_in_master = origin.express_in(reference_frame.find_master())

    ax.scatter([origin_in_master[x_idx]], [origin_in_master[y_idx]], color="k")

    # Draw the axis

    origin_dc = np.array([[origin_in_master[x_idx], origin_in_master[y_idx]]])

    point = dc2fc(origin_dc[0])
    point[0] += default_axis_length
    target_dc = np.append(origin_dc, [fc2dc(point)], axis=0)

    ax.plot(target_dc[:, 0], target_dc[:, 1], color="k")

    point = dc2fc(origin_dc[0])
    point[1] += default_axis_length
    target_dc = np.append(origin_dc, [fc2dc(point)], axis=0)

    ax.plot(target_dc[:, 0], target_dc[:, 1], color="k")

    # Draw the axes label

    dx, dy = 10 / fig.dpi, 10 / fig.dpi
    offset = ScaledTranslation(dx, dy, fig.dpi_scale_trans)
    point = dc2ndc(origin_dc[0])
    plt.text(point[0], point[1], reference_frame.name, transform=ax.transAxes + offset)


def define_the_initial_setup() -> ReferenceFrameModel:
    """Defines the initial setup of the reference frame model.

    Returns:
        Reference frame model with the initial setup.
    """

    model = ReferenceFrameModel()

    model.add_master_frame()
    model.add_frame("A", translation=[2, 2, 2], rotation=[0, 0, 0], reference="Master")
    model.add_frame("B", translation=[-2, 2, 2], rotation=[0, 0, 0], reference="Master")
    model.add_frame("C", translation=[2, 2, 5], rotation=[0, 0, 0], reference="A")
    model.add_frame("D", translation=[2, 2, 2], rotation=[0, 0, 0], reference="B")

    model.add_link("A", "B")
    model.add_link("B", "C")

    print(model.serialize())
    plot_ref_model_3d(model)

    return model


def get_vectors(reference_frame_1, reference_frame_2, model: ReferenceFrameModel) -> tuple[np.ndarray, np.ndarray]:
    """Returns the translation and rotation vectors for the active transformation for the 1st reference frame to the 2nd.

    Args:
        reference_frame_1 (str): Name of the reference frame to get the active transformation from.
        reference_frame_2 (str): Name of the reference frame to get the active transformation to.
        model (ReferenceFrameModel): Model containing the reference frames with the given names.

    Returns:
        Translation and rotation vectors from the active transformation from the 1st reference frame to the 2nd.
    """

    return model.get_frame(reference_frame_1).get_active_translation_rotation_vectors_to(
        model.get_frame(reference_frame_2)
    )


def print_vectors(reference_frame_1: str, reference_frame_2: str, model: ReferenceFrameModel) -> None:
    """Prints the translation and rotation vectors for the active transformation for the 1st reference frame to the 2nd.

    Args:
        reference_frame_1 (str): Name of the reference frame to get the active transformation from.
        reference_frame_2 (str): Name of the reference frame to get the active transformation to.
        model (ReferenceFrameModel): Model containing the reference frames with the given names.
    """

    trans, rot = model.get_frame(reference_frame_1).get_active_translation_rotation_vectors_to(
        model.get_frame(reference_frame_2)
    )
    print(
        f"{reference_frame_1:8s} -> {reference_frame_2:8s} : Trans [{trans[0]:11.4e}, {trans[1]:11.4e}, {trans[2]:11.4e}]    Rot [{rot[0]:11.4e}, {rot[1]:11.4e}, {rot[2]:11.4e}]"
    )
    return


if __name__ == "__main__":
    logging.basicConfig(level=20)

    model = define_the_initial_setup()

    print(model.summary())

    print("\nMove frame 'A', frames 'B' and 'C' move with it.\n")
    model.move_absolute_self("A", [1, 1, 3], [0, 0, 45])
    print(model.serialize())
    plot_ref_model_3d(model)

    model = define_the_initial_setup()

    print("\nMove frame 'B' with respect to 'Master, frames 'A' and 'C' move with it.\n")
    model.move_absolute_in_other("B", "Master", [1, 1, -1], [0, 0, 0])
    print(model.serialize())
    plot_ref_model_3d(model)

    model = define_the_initial_setup()

    print("\nMove frame 'D' relative to itself, turn 45º\n")
    model.move_relative_self("D", [0, 0, 0], [45, 0, 0])
    print(model.serialize())
    plot_ref_model_3d(model)

    model = define_the_initial_setup()

    print("\nMove frame 'D' relative to 'A', turn 45º around origin of 'A'\n")
    model.move_relative_other("D", "A", [0, 0, 0], [0, 45, 0])
    print(model.serialize())
    plot_ref_model_3d(model)

    model = define_the_initial_setup()

    print("\nMove frame 'D' relative to 'A', turn 45º around origin of 'D'\n")
    model.move_relative_other_local("D", "A", [0, 0, 0], [0, 45, 0])
    print(model.serialize())
    plot_ref_model_3d(model)

    model = define_the_initial_setup()
