"""
An ObservationIdentifier or OBSID is a unique identifier for an observation or test.

Each observation or test needs a unique identification that can be used as a key in a
database or in a filename for test data etc.

"""
from pathlib import Path
from typing import Union

from egse.config import find_dir
from egse.settings import Settings

LAB_SETUP_TEST = 0
TEST_LAB_SETUP = 1
TEST_LAB = 3

SITE = Settings.load("SITE")


class ObservationIdentifier:
    """A unique identifier for each observation or test."""

    def __init__(self, lab_id: str = None, setup_id: int = None, test_id: int = None):
        """
        Args:
            lab_id: the identifier for the site or lab that performs the test
            setup_id: the identifier for the setup that is used for the test
            test_id: the test identifier or test number
        """
        if lab_id is None or setup_id is None or test_id is None:
            raise ValueError("arguments can not be None or an empty string")

        self._lab_id = lab_id
        self._setup_id = setup_id
        self._test_id = test_id

        # Construct the OBSID as it will be used in serialisation etc.

        self._obsid = f"{lab_id}_{setup_id:05d}_{test_id:05d}"

    @staticmethod
    def create_from_string(obsid: str, order: int = LAB_SETUP_TEST):
        if order == LAB_SETUP_TEST:
            lab_id, setup_id, test_id = obsid.split("_")
        elif order == TEST_LAB_SETUP:
            test_id, lab_id, setup_id = obsid.split("_")
        else:
            raise ValueError(
                f"The order argument can only be {LAB_SETUP_TEST=} or {TEST_LAB_SETUP=}")

        return ObservationIdentifier(lab_id, int(setup_id), int(test_id))

    @property
    def lab_id(self):
        return self._lab_id

    @property
    def setup_id(self):
        return self._setup_id

    @property
    def test_id(self):
        return self._test_id

    def __eq__(self, other):
        if not isinstance(other, ObservationIdentifier):
            return NotImplemented
        return self._obsid == other._obsid

    def __hash__(self):
        return hash(self._obsid)

    def __str__(self):
        return self._obsid

    def create_id(self, *, order: int = LAB_SETUP_TEST, camera_name: str = None) -> str:
        """
        Creates a string representation of the observation identifier.

        Args:
            order: the order in which the parts are concatenated
            camera_name: if a camera name is given, it will be appended in lower case

        Returns:
            A string representation of the obsid with or without camera name attached.
        """
        camera = f"{f'_{camera_name.lower()}' if camera_name else ''}"

        if order == TEST_LAB_SETUP:
            return f"{self._test_id:05d}_{self._lab_id}_{self._setup_id:05d}{camera}"
        if order == TEST_LAB:
            return f"{self._test_id:05d}_{self._lab_id}{camera}"
        if order == LAB_SETUP_TEST:
            return f"{self._lab_id}_{self._setup_id:05d}_{self._test_id:05d}{camera}"


def obsid_from_storage(obsid: Union[ObservationIdentifier, str, int], data_dir: str,
                       site_id: str = None, camera_name: str = None) -> str:
    """
    Return the name of the folder for the given obsid in the 'obs' sub-folder of data_dir.

    For the oldest observations, the obsid used in the directory structure and filenames was of the format
    TEST_LAB_SETUP.  All files in this folder also have the obsid in that format in their name.  At some point, we
    decided to change this to TEST_LAB, but we still need to be able to re-process the old data (with the setup ID in
    the names of the directories and files).

    For newer observations (>= 2023.6.0+CGSE), the camera name is appended to the folder name and also included
    in the filenames in that folder.

    Args:
        obsid: Observation identifier.  This can be an ObservationIdentifier object, a string in format TEST_LAB or
            TEST_LAB_SETUP, or an integer representing the test ID. In this last case, the site id is taken from the
            Settings.
        data_dir: root folder in which the observations are stored. This folder shall have a sub-folder 'obs'.
        site_id: a site id like 'CSL1' or 'IAS', when `None`, the `SITE.ID` from the Settings will be used
        camera_name: if not None, append the camera name to the result

    Returns:
        The name of the folder for the given obsid in the 'obs' sub-folder of data_dir.
    """

    obs_dir = f"{data_dir}/obs/"
    site_id = site_id or SITE.ID
    camera = f"_{camera_name.lower()}" if camera_name else ""

    if isinstance(obsid, ObservationIdentifier):
        test, site = obsid.test_id, obsid.lab_id
    elif isinstance(obsid, str):    # TEST_LAB or TEST_LAB_SETUP
        test, site = obsid.split("_")[:2]
    else:
        test, site = obsid, site_id

    test = int(test)

    # Remember the camera name can be an empty string, so this will match both
    # '00313_CSL' and '00313_CSL_achel'.

    result_without_setup = Path(f"{obs_dir}/{test:05d}_{site}{camera}")

    if result_without_setup.exists():
        return result_without_setup.stem

    # If a camera name was provided, but we try to find an old observation where the
    # camera name was not appended to the folder name yet, the following will match
    # that folder name.

    result_without_camera = Path(f"{obs_dir}/{test:05d}_{site}")

    if result_without_camera.exists():
        return result_without_camera.stem

    # When we come here, we can still match old observations that included the setup id in their
    # folder name.

    pattern = f"{test:05d}_{site}_*{camera}"

    if (match := find_dir(pattern=pattern, root=obs_dir)) is None:
        raise ValueError(f"Could not find a folder matching '{pattern}' in '{obs_dir}'")

    return match.stem
