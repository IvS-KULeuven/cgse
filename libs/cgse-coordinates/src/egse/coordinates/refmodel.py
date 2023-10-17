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
from typing import Union

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import ScaledTranslation
from mpl_toolkits.mplot3d import Axes3D

import egse.coordinates.transform3d_addon as t3add
from egse.coordinates import dict_to_ref_model
from egse.coordinates import ref_model_to_dict
from egse.coordinates.referenceFrame import ReferenceFrame
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
        model: Union[Dict, List[ReferenceFrame]] = None,
        rot_config: str = _ROT_CONFIG_DEFAULT,
        use_degrees: bool = _DEGREES_DEFAULT,
        use_active_movements: bool = _ACTIVE_DEFAULT,
    ):
        """
        When the model_dict is empty or None, a new model is created with a master reference frame.

        Args:
            model: a list or a dictionary of reference frames that make up the model
            use_degrees: use degrees throughout this model unless explicitly specified in the
                function call.
        """
        self._use_degrees = use_degrees
        self._use_active_movements = use_active_movements
        self._rot_config = rot_config

        # Keep a dictionary with all reference frames that are part of the model. The keys shall
        # be the name of the reference frame. When the model passed is empty, create only a
        # master reference frame.

        if isinstance(model, (dict, list)):
            self._model = self.deserialize(model)
        else:
            self._model = NavigableDict({})

    def __str__(self):
        return self._model.pretty_str()

    def __len__(self):
        return len(self._model)

    def __contains__(self, item):
        return item in self._model

    def __iter__(self):
        return iter(self._model.values())

    def summary(self):
        result = f"Nb of frames: {len(self)}\n"

        for ref in self:
            result += (
                f"{ref.name:>10}[{ref.ref.name}]" f"  ---  {[link.name for link in ref.linkedTo]}\n"
            )
        return result

    @staticmethod
    def deserialize(model_dict: dict) -> NavigableDict:
        """
        Deserialize means you take a serialized representation of a reference frames model and
        turn it into a dictionary containing all the reference frames with their links and
        references.

        Args:
            model_dict: a dictionary of serialized reference frames

        Returns:
            A dictionary of ReferenceFrames that make up a model.

        """
        return dict_to_ref_model(model_dict)

    def serialize(self) -> NavigableDict:
        """
        Serialize the model by serializing each of the reference frames into an object that can
        easily be saved to a YAML or a JSON file. Return a dictionary with the serialized frames.

        Returns:
            A dictionary with all the reference framed serialized.
        """

        return ref_model_to_dict(self._model)

    def add_master_frame(self):

        # TODO: First check if there is not already a Master frame in the model

        self._model["Master"] = ReferenceFrame.createMaster()

    def add_frame(
        self,
        name: str,
        *,
        translation: List[float] = None,
        rotation: List[float] = None,
        transformation=None,
        ref: str,
    ):
        """
        Add a reference frame to the model.

        .. note::
            Only the `name` parameter can be positional, all the other arguments (translation,
            rotation, transformation, and ref) must be given as keyword arguments.

        Args:
            name: the name for the reference frame. This name is it's identifier within the model.
            translation: the translation vector
            rotation: the rotation vector
            transformation: the transformation vector, if `transformation` is given,
                both `translation` and `rotation` are ignored.
            ref: the reference frame that is a reference for 'name', i.e. 'name' is defined with
                respect to 'ref'.
        """

        if name in self._model:
            raise KeyError("A reference frame with the name '{name} already exists in the model.")

        ref = self._model[ref]

        if transformation is not None:
            self._model[name] = ReferenceFrame(
                transformation, ref=ref, name=name, rot_config=self._rot_config,
            )
        else:
            self._model[name] = ReferenceFrame.fromTranslationRotation(
                translation,
                rotation,
                name=name,
                ref=ref,
                rot_config=self._rot_config,
                degrees=self._use_degrees,
                active=self._use_active_movements,
            )

    def remove_frame(self, name: str):
        """
        Deletes the reference frame from the model. If the reference frame doesn't exist in the
        model, a warning message is logged.

        Args:
            name: the name of the reference frame to remove
        """

        if name in self._model:

            frame: ReferenceFrame = self._model[name]

            # We need to get the links out in a list because the frame.removeLink() method deletes
            # frames from the linkedTo dictionary and that is not allowed in a for loop.

            links = [linked_frame for linked_frame in frame.linkedTo]
            for link in links:
                frame.removeLink(link)

            del self._model[name]
        else:
            LOGGER.warning(
                f"You tried to remove a non-existing reference frame '{name}' from the model."
            )

    def get_frame(self, name: str) -> ReferenceFrame:
        """
        Returns a frame with the given name.

        .. note::
            Use this function with care since this breaks encapsulation and may lead to an
            inconsistent model when the frame is changed outside of the scope of the reference
            model.

        Args:
            name: the name of the requested reference frame

        Returns:
            The reference frame with the given name.
        """
        return self._model[name]

    def add_link(self, source: str, target: str):
        """
        Add a link between two reference frames. All links are bi-directional.

        Args:
            source: the source reference frame
            target: the target reference frame

        """
        if source not in self._model:
            raise KeyError(f"There is no reference frame with the name '{source} in the model.")
        if target not in self._model:
            raise KeyError(f"There is no reference frame with the name '{target} in the model.")

        source = self._model[source]
        target = self._model[target]

        source.addLink(target)

    def remove_link(self, source: str, target: str):
        """
        Remove a link between two reference frames. All links are bi-directional and this method
        removes both links.

        Args:
            source: the source reference frame
            target: the target reference frame

        """
        if source not in self._model:
            raise KeyError(f"There is no reference frame with the name '{source} in the model.")
        if target not in self._model:
            raise KeyError(f"There is no reference frame with the name '{target} in the model.")

        source = self._model[source]
        target = self._model[target]

        source.removeLink(target)

    def move_absolute_self(self, frame: str, translation, rotation, degrees=_DEGREES_DEFAULT):
        """
        Apply an absolute movement to the given ReferenceFrame such that it occupies a given
        absolute position wrt "frame_ref" after the movement.

        NO Hexapod equivalent.

        Args:
            frame (str): the name of the reference frame to move
        """

        frame = self._model[frame]
        frame.setTranslationRotation(
            translation,
            rotation,
            rot_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserveLinks=True,
        )

    def move_absolute_in_other(
        self, frame: str, other: str, translation, rotation, degrees=_DEGREES_DEFAULT
    ):
        """
        Apply an absolute movement to the ReferenceFrame "frame", such that it occupies
        a given absolute position with respect to "other" after the movement.

        EQUIVALENT PunaSimulator.move_absolute, setting hexobj wrt hexusr.

        Args:
            frame (str): the name (id) of the reference frame to move
            other (str): the name (id) of the reference frame
        """

        # TODO:
        #   There can not be a link between frame and other, not direct and not indirect.
        #   So, with A-link-B-link-C-link-D, we can not do move_absolute_in_other('A', 'D', ...)

        frame = self._model[frame]
        other = self._model[other]

        transformation = other.getActiveTransformationTo(frame)

        moving_in_other = ReferenceFrame(
            transformation, rot_config=self._rot_config, ref=other, name="moving_in_other"
        )

        moving_in_other.addLink(frame)

        moving_in_other.setTranslationRotation(
            translation,
            rotation,
            rot_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserveLinks=True,
        )

        moving_in_other.removeLink(frame)

        del moving_in_other

    def move_relative_self(self, frame: str, translation, rotation, degrees=_DEGREES_DEFAULT):
        """
        Apply a relative movement to the given ReferenceFrame assuming the movement is expressed
        in that same frame.

        EQUIVALENT PunaSimulator.move_relative_object

        Args:
            frame (str): the name of the reference frame to move
        """

        frame = self._model[frame]
        frame.applyTranslationRotation(
            translation,
            rotation,
            rot_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserveLinks=True,
        )

    def move_relative_other(
        self, frame: str, other: str, translation, rotation, degrees=_DEGREES_DEFAULT
    ):
        """
        Apply a relative movement to the ReferenceFrame "frame". The movement is expressed wrt
        the axes of another frame, "other".

        The center of rotation is the origin of the reference frame 'other'.

        NO Hexapod equivalent.

        Args:
            frame (str): the name (id) of the reference frame to move
            other (str): the name (id) of the reference frame
        """

        # TODO:
        #   There can not be a link between frame and other, not direct and not indirect.
        #   So, with A-link-B-link-C-link-D, we can not do move_absolute_in_other('A', 'D', ...)

        frame = self._model[frame]
        other = self._model[other]

        transformation = frame.getActiveTransformationTo(other)

        moving_in_other = ReferenceFrame(
            transformation, rot_config=self._rot_config, ref=other, name="moving_in_other"
        )

        moving_in_other.addLink(frame)

        moving_in_other.applyTranslationRotation(
            translation,
            rotation,
            rot_config=self._rot_config,
            active=self._use_active_movements,
            degrees=degrees,
            preserveLinks=True,
        )

        moving_in_other.removeLink(frame)

        del moving_in_other  # not need as local scope

    def move_relative_other_local(
        self, frame: str, other: str, translation, rotation, degrees=_DEGREES_DEFAULT
    ):
        """
        Apply a relative movement to the ReferenceFrame "frame".

        The movement is expressed wrt the axes of an external frame "other"

        The center of rotation is the origin of the reference frame 'frame'.

        EQUIVALENT PunaSimulator.move_relative_user

        """

        # TODO:
        #   There can not be a link between frame and other, not direct and not indirect.
        #   So, with A-link-B-link-C-link-D, we can not do move_absolute_in_other('A', 'D', ...)

        frame = self._model[frame]
        other = self._model[other]

        # Represent the requested movement

        # Derotation of MOVING --> REF  (align frame_moving axes on those of frame_ref)

        derotation = frame.getActiveTransformationTo(other)
        derotation[:3, 3] = [0, 0, 0]

        # Reverse rotation (record inverse rotation, to restore the frame in the end)

        rerotation = derotation.T

        # Requested translation matrix  (already expressed wrt frame_ref)

        translation_ = np.identity(4)
        translation_[:3, 3] = translation

        # Requested rotation matrix (already expressed wrt frame_ref)

        zeros = [0, 0, 0]
        rotation_ = t3add.translationRotationToTransformation(
            zeros, rotation, rot_config=self._rot_config
        )

        # All translations and rotations are applied to frame_moving
        # ==> a. need for "derotation" before applying the translation
        #     b. the center or rotation is always the origin of frame_moving
        # 1. rotate frame_moving to align it with frame_ref (i.e. render their axes parallel)
        # 2. apply the translation in this frame
        # 3. restore the original orientation of the moving frame
        # 4. apply the requested rotation

        transformation = derotation @ translation_ @ rerotation @ rotation_

        # Apply the requested movement

        frame.applyTransformation(transformation, preserveLinks=True)


def plot_ref_model(model: ReferenceFrameModel):

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


def plot_ref_model_3d(model: ReferenceFrameModel):

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


# The aspect ration of the plots is not equal by default.
# This solution was given in SO: https://stackoverflow.com/a/63625222/4609203


def set_axes_equal(ax: plt.Axes):
    """Set 3D plot axes to equal scale.

    Make axes of 3D plot have equal scale so that spheres appear as
    spheres and cubes as cubes.  Required since `ax.axis('equal')`
    and `ax.set_aspect('equal')` don't work on 3D.
    """
    limits = np.array([ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()])
    origin = np.mean(limits, axis=1)
    radius = 0.5 * np.max(np.abs(limits[:, 1] - limits[:, 0]))
    x, y, z = origin
    ax.set_xlim3d([x - radius, x + radius])
    ax.set_ylim3d([y - radius, y + radius])
    ax.set_zlim3d([z - radius, z + radius])


def draw_frame_3d(ax: Axes3D, frame: ReferenceFrame, DEFAULT_AXIS_LENGTH=100, **kwargs):

    master = frame.find_master()

    f0 = frame.getOrigin()
    fx = frame.getAxis("x", name="fx")
    fy = frame.getAxis("y", name="fy")
    fz = frame.getAxis("z", name="fz")
    f0m = f0.expressIn(master)[:3]
    fxm = fx.expressIn(master)[:3]
    fym = fy.expressIn(master)[:3]
    fzm = fz.expressIn(master)[:3]

    # Origin of the X,Y and Z vectors (x = the 'x' coordinates of the origin of all 3 vectors)
    # Every vector independently (--> plot in diff. colors)
    x, y, z = np.array([f0m[0]]), np.array([f0m[1]]), np.array([f0m[2]])

    # Orientation of the X,Y and Z vectors
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


def draw_frame(ax, frame: ReferenceFrame, plane="xz", DEFAULT_AXIS_LENGTH=100):

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

    origin = frame.getOrigin()
    origin_in_master = origin.expressIn(frame.find_master())

    ax.scatter([origin_in_master[x_idx]], [origin_in_master[y_idx]], color="k")

    # Draw the axis

    origin_dc = np.array([[origin_in_master[x_idx], origin_in_master[y_idx]]])

    point = dc2fc(origin_dc[0])
    point[0] += DEFAULT_AXIS_LENGTH
    target_dc = np.append(origin_dc, [fc2dc(point)], axis=0)

    ax.plot(target_dc[:, 0], target_dc[:, 1], color="k")

    point = dc2fc(origin_dc[0])
    point[1] += DEFAULT_AXIS_LENGTH
    target_dc = np.append(origin_dc, [fc2dc(point)], axis=0)

    ax.plot(target_dc[:, 0], target_dc[:, 1], color="k")

    # Draw the axes label

    dx, dy = 10 / fig.dpi, 10 / fig.dpi
    offset = ScaledTranslation(dx, dy, fig.dpi_scale_trans)
    point = dc2ndc(origin_dc[0])
    plt.text(point[0], point[1], frame.name, transform=ax.transAxes + offset)


def define_the_initial_setup():
    model = ReferenceFrameModel()

    model.add_master_frame()
    model.add_frame("A", translation=[2, 2, 2], rotation=[0, 0, 0], ref="Master")
    model.add_frame("B", translation=[-2, 2, 2], rotation=[0, 0, 0], ref="Master")
    model.add_frame("C", translation=[2, 2, 5], rotation=[0, 0, 0], ref="A")
    model.add_frame("D", translation=[2, 2, 2], rotation=[0, 0, 0], ref="B")

    model.add_link("A", "B")
    model.add_link("B", "C")

    print(model.serialize())
    plot_ref_model_3d(model)

    return model


def get_vectors(rf1, rf2, model):
    """
    get_vectors(rf1,rf2, model)
    :param rf1: string : name of ref. frame "from"
    :param rf2: string : name of ref. frame "to"
    :param model: CSLReferenceFrameModel containing rf1 and rf2
    :return: translation and rotation vectors from rf1 to rf2
    """
    return model.get_frame(rf1).getActiveTranslationRotationVectorsTo(model.get_frame(rf2))


def print_vectors(rf1, rf2, model):
    """
    :param rf1: string : name of ref. frame "from"
    :param rf2: string : name of ref. frame "to"
    :param model: CSLReferenceFrameModel containing rf1 and rf2
    :return: N.A.
    Prints the translation and rotation vectors from rf1 to rf2
    """
    trans, rot = model.get_frame(rf1).getActiveTranslationRotationVectorsTo(model.get_frame(rf2))
    print(f"{rf1:8s} -> {rf2:8s} : Trans [{trans[0]:11.4e}, {trans[1]:11.4e}, {trans[2]:11.4e}]    Rot [{rot[0]:11.4e}, {rot[1]:11.4e}, {rot[2]:11.4e}]")
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
