import logging
from pathlib import Path
from typing import Optional

import h5py
import natsort
import numpy as np
from egse.spw import DataDataPacket
from egse.spw import HousekeepingPacket
from egse.spw import OverscanDataPacket
from egse.spw import TimecodePacket
from egse.persistence import PersistenceLayer  # -> circular dependency because this import loads this module as a plugin

LOGGER = logging.getLogger(__name__)


class HDF5(PersistenceLayer):
    extension = "hdf5"

    def __init__(self, filename, prep: dict = None):
        """
        The `prep` argument needs at least the following mandatory key:value pairs:

          * mode: the mode used for opening the file [default is 'r']

        """
        # LOGGER.debug(f"{h5py.version.hdf5_version=}")
        self._filepath = Path(filename)
        self._mode = prep.get("mode") or "r"
        self._h5file: Optional[h5py.File] = None

    def __enter__(self):
        self.open(mode=self._mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self, mode=None):
        self._mode = mode or self._mode
        LOGGER.debug(f"Opening file {self._filepath} in mode '{self._mode}'")
        self._h5file = h5py.File(self._filepath, mode=self._mode)

        # File "h5py/h5f.pyx", line 554, in h5py.h5f.FileID.start_swmr_write
        # RuntimeError: Unable to start swmr writing (file superblock version - should be at least 3)
        # self._h5file.swmr_mode = True

    def close(self):
        self._h5file.close()

    def exists(self):
        return self._filepath.exists()

    def create(self, data):
        """
        Store the given data in the HDF5 file. The data argument shall be a dictionary where the
        keys represent the group where the data shall be saved, and the value is the data to be
        saved. When the key ends with ":ATTRS", then the value is a list of attributes to that
        group. Values can be of different type and are processed if needed.

        An example data argument:

            {
                "/10/timecode": tc_packet,
                "/10/timecode:ATTRS": [("timestamp", timestamp)],
                "/10/command/": f"{command.__name__}, {args=}",
                "/10/register/": self.register_map.get_memory_map_as_ndarray()
            }

        The example saves a Timecode packet in the group "/10/timecode" and attaches a timestamp
        as an attribute called "timestamp" to the same group. It then adds a command string in
        the "/10/command" group and finally adds a register memory map (an np.ndarray) in the group
        "/10/register".

        Args:
            data (dict): a dictionary containing the data that needs to be saved.

        Returns:
            None.
        """
        for key, value in data.items():
            if key.endswith(":ATTRS"):
                a_key = key.split(":")[0]
                for k, v in value:
                    self._h5file[a_key].attrs[k] = v
            if isinstance(value, TimecodePacket):
                self._h5file[key] = value.timecode
            if isinstance(value, HousekeepingPacket):
                self._h5file[key] = value.packet_as_ndarray
            if isinstance(value, HousekeepingData):
                self._h5file[key] = value.data_as_ndarray
            if isinstance(value, DataDataPacket):
                self._h5file[key] = value.packet_as_ndarray
            if isinstance(value, OverscanDataPacket):
                self._h5file[key] = value.packet_as_ndarray
            if isinstance(value, (str, bytearray, np.ndarray)):

                # if we save a command, put it into a 'commands' group.
                # This is a special case that is the result of issue #1461

                if 'command' in key:
                    idx = key.split('/')[1]
                    if idx in self._h5file and 'commands' in self._h5file[idx]:
                        last_idx = int(sorted(self._h5file[f"/{idx}/commands"].keys())[-1])
                        key = f"/{idx}/commands/{last_idx + 1}"
                    else:
                        key = f"/{idx}/commands/0"

                self._h5file[key] = value

    def read(self, select=None):
        """
        Read information or data from the HDF5 file.

        The `select` argument can contain the following information:

        * the string 'number_of_groups': request to determine the number of top groups in
          the HDF5 file.
        * the string 'last_top_group': request the name/key of the last item in the top group.
                The last item is the last element of the list of keys, sorted with natural order.

        Args:
            select (str or dict): specify which information should be read

        Returns:
            When 'number_of_groups', return an integer, when 'last_top_group' return a string.
        """
        if select == "number_of_groups":
            return len(self._h5file.keys())
        if select == "last_top_group":
            keys = self._h5file.keys()

            LOGGER.debug(f"{self._h5file.filename}: {keys=}")

            return 0 if len(keys) == 0 else natsort.natsorted(keys)[-1]

            # This following lines is a longer version of the previous two lines, keep them for
            # debugging because I had problems and not yet sure what is the cause...

            # sorted_keys = natsort.natsorted(keys)
            # LOGGER.debug(f"{self._h5file.filename}: {sorted_keys=}")
            # key = sorted_keys[-1]
            # LOGGER.debug(f"{key=}")
            # return key

    def update(self, idx, data):

        pass

    def delete(self, idx):
        pass

    def get_filepath(self):
        return self._filepath
