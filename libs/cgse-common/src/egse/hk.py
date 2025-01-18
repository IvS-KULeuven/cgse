__all__ = [
    "get_housekeeping",
    "convert_hk_names",
    "read_conversion_dict",
    "TmDictionaryColumns",
]
import csv
import datetime
import logging
from enum import Enum
from pathlib import Path
from typing import Optional
from typing import Union

import dateutil.parser as date_parser
import numpy as np
from egse.config import find_files
from egse.env import get_data_storage_location
from egse.env import get_site_id
from egse.obsid import ObservationIdentifier
from egse.obsid import obsid_from_storage
from egse.setup import Setup
from egse.setup import SetupError
from egse.setup import load_setup
from egse.system import SECONDS_IN_A_DAY
from egse.system import read_last_line
from egse.system import read_last_lines
from egse.system import str_to_datetime
from egse.system import time_since_epoch_1958

_LOGGER = logging.getLogger(__name__)


class TmDictionaryColumns(str, Enum):
    """ Enumeration of the relevant columns in the TM dictionary spreadsheet.

    The relevant columns are:

        - STORAGE_MNEMONIC: Column with the storage mnemonic of the process that generated the HK;
        - CORRECT_HK_NAMES: Column with the correct HK names (that can be used in `get_housekeeping`);
        - ORIGINAL_EGSE_HK_NAMES: Column with the names that were originally used in `get_housekeeping` the device
                                  protocol;
        - SYNOPTICS_ORIGIN: Column with the origin of the synoptics at the current site;
        - TIMESTAMP_NAMES: Column with the name of the timestamps.
        - DASHBOARD: Column with the name of the dashboard that holds the HK metric
    """

    STORAGE_MNEMONIC = "Storage mnemonic"
    CORRECT_HK_NAMES = "CAM EGSE mnemonic"
    ORIGINAL_EGSE_HK_NAMES = "Original name in EGSE"
    SYNOPTICS_ORIGIN = f"Origin of synoptics at {get_site_id()}"
    TIMESTAMP_NAMES = "Name of corresponding timestamp"
    DESCRIPTION = "Description"
    DASHBOARD = "MON screen"


class HKError(Exception):
    """An HK-specific error."""
    pass


def get_housekeeping(hk_name: str, obsid: Union[ObservationIdentifier, str, int] = None, od: str = None,
                     time_window: int = None, data_dir=None, setup: Optional[Setup] = None):
    """
    Returns the timestamp(s) and housekeeping value(s) for the housekeeping parameter with the given name.

    It is possible to indicate for which obsid or which OD the housekeeping is to be returned.  If neither of them is
    specified, the latest daily files are used.

    When the time window has not been specified, the last timestamp and housekeeping value will be returned for the
    given OD. It is possible that a component stopped writing HK for some reason, and that the last housekeeping value
    is older than you would want.  It is therefore important to inspect the corresponding timestamp.

    When the time window has been specified, the relevant housekeeping will be read:

    * determine the sampling rate (compare the timestamps for the last 2 lines in the housekeeping file);
    * determine how many samples we need to read (starting at the back);
    * read the required number of line, starting at the back;
    * for each of the read lines, append the timestamp and HK value to the arrays that will be returned

    Args:
        hk_name: Name of the housekeeping parameter.
        obsid: Observation identifier.  This can be an ObservationIdentifier object, a string in format TEST_LAB or
            TEST_LAB_SETUP, or an integer representing the test ID; optional.
        od: Identifier for the OD (yyyymmdd); optional.
        time_window: Length of the time window over which to retrieve the housekeeping [s].  The time window ends at
            the moment this method is called.  If not given, the latest housekeeping value is returned.
        data_dir: Folder (with sub-folders /daily and /obs) in which the HK files are stored. If this argument is not
            provided, the data_dir will be determined from the environment variable PLATO_DATA_STORAGE_LOCATION.
        setup: Setup

    Raises:
        A HKError when one of the following problems occur
            * no obsid nor an od argument was provided
            * no HK measures were found for the given parameter and obsid/od

    Returns:
        - If the time window has not been specified: the most recent timestamp and housekeeping value.
        - If the time window has been specified: an array of timestamps and an array of housekeeping values, belonging
          to the specified time window.

    """

    setup = setup or load_setup()

    # Either specify the obsid or the OD (or neither of them) but not both

    if obsid is not None and od is not None:

        raise HKError(f"Both the obsid ({obsid}) and the OD ({od}) were specified.")

    # Specified obsid (as integer or as string)

    data_dir = data_dir or get_data_storage_location()

    if obsid:

        try:
            return _get_housekeeping_obsid(hk_name, data_dir, obsid=obsid, time_window=time_window, setup=setup)
        except (ValueError, StopIteration, FileNotFoundError) as exc:
            raise HKError(f"No HK found for {hk_name} for obsid {obsid} at {get_site_id()}") from exc

    # Specified OD

    if od:

        try:
            return _get_housekeeping_od(hk_name, data_dir, od=od, time_window=time_window, setup=setup)
        except (ValueError, StopIteration, FileNotFoundError) as exc:
            raise HKError(f"No HK found for {hk_name} for OD {od} at {get_site_id()}") from exc

    # Didn't specify neither the obsid nor the OD

    try:
        return _get_housekeeping_daily(hk_name, data_dir, time_window=time_window, setup=setup)
    except (ValueError, StopIteration, FileNotFoundError) as exc:
        raise HKError(f"No HK found for {hk_name} for today at {get_site_id()}") from exc


def _get_housekeeping(hk_name: str, timestamp_name: str, hk_dir: str, files, time_window: int = None):
    """ Return the timestamp(s) and HK value(s) for the HK parameter with the given name, for the given files.

    When the time window has not been specified, the last timestamp and HK value will be returned for the given OD.
    It is possible that a component stopped writing HK for some reason, and that the last HK value is older than you
    would want.  It is therefore important to inspect the corresponding timestamp.

    When the time window has been specified, the relevant HK will be read:
        - determine the sampling rate (compare the timestamps for the last 2 lines in the HK file);
        - determine how many samples we need to read (starting at the back);
        - read the required number of line, starting at the back;
        - for each of the read lines, append the timestamp and HK value to the arrays that will be returned

    Args:
        - hk_name: Name of the housekeeping parameter.
        - timestamp_name: Name of the corresponding timestamp.
        - hk_dir: Directory with the housekeeping files.
        - files: Relative filepath of the selected housekeeping files.
        - time_window: Length of the time window over which to retrieve the housekeeping [s].  The time window ends at
                       the moment this method is called.  If not given, the latest HK-value is returned.

    Returns:
        - If the time window has not been specified: the most recent timestamp and housekeeping value.
        - If the time window has been specified: an array of timestamps and an array of housekeeping values, belonging
          to the specified time window.
    """

    filename = files[-1]

    # Indices of the columns we need

    timestamp_index, hk_index = get_indices(hk_dir + filename, hk_name, timestamp_name)

    # No time window specified: return the last value

    if time_window is None:

        return get_last_non_empty(hk_dir + filename, timestamp_index, hk_index)

    # Time window specified

    else:

        # We will return an array of timestamps and an array of HK values

        timestamp_array = np.array([])
        hk_array = np.array([])

        with open(hk_dir + filename) as file:

            csv_reader = csv.reader(file)
            next(csv_reader)
            first_timepoint = next(csv_reader)[0].split(",")[timestamp_index]  # Skip the header

        last_timepoint = read_last_line(hk_dir + filename).split(",")[timestamp_index]
        elapsed = (str_to_datetime(last_timepoint) - str_to_datetime(first_timepoint)).total_seconds()

        # The time window is shorter than the timespan covered by the file

        if time_window < elapsed:

            sampling_rate = get_sampling_rate(hk_dir + filename, timestamp_name)  # Time between subsequent samples
            num_samples = int(round(time_window / sampling_rate))

            lines = read_last_lines(hk_dir + filename, num_samples)

            for line in lines:

                line = line.split(",")

                timestamp_array = np.append(timestamp_array, line[timestamp_index])
                hk_array = np.append(hk_array, line[hk_index])

        # The time window is longer than the timespan covered by the file: read all lines

        else:

            with open(hk_dir + filename) as file:

                csv_reader = csv.reader(file)
                next(csv_reader)  # Skip the header

                for row in csv_reader:

                    timestamp_array = np.append(timestamp_array, row[timestamp_index])
                    hk_array = np.append(hk_array, row[hk_index])

        for index in range(len(timestamp_array)):

            timestamp_array[index] = time_since_epoch_1958(timestamp_array[index])

        return timestamp_array, hk_array


def _get_housekeeping_od(hk_name: str, data_dir, od: str, time_window: int = None, setup: Optional[Setup] = None):
    """ Return the timestamp(s) and HK value(s) for the HK parameter with the given name, for the given OD.

    When the time window has not been specified, the last timestamp and HK value will be returned for the given OD.
    It is possible that a component stopped writing HK for some reason, and that the last HK value is older than you
    would want.  It is therefore important to inspect the corresponding timestamp.

    When the time window has been specified, the relevant HK will be read:
        - determine the sampling rate (compare the timestamps for the last 2 lines in the HK file);
        - determine how many samples we need to read (starting at the back);
        - read the required number of line, starting at the back;
        - for each of the read lines, append the timestamp and HK value to the arrays that will be returned

    Args:
        - hk_name: Name of the housekeeping parameter.
        - data_dir: Folder (with sub-folders /daily and /obs) in which the HK files are stored.
        - od: Identifier for the OD (yyyymmdd).
        - time_window: Length of the time window over which to retrieve the housekeeping [s].  The time window ends at
                       the moment this method is called.  If not given, the latest HK-value is returned.
        - setup: Setup.

        Returns:
            - If the time window has not been specified: the most recent timestamp and HK value.
            - If the time window has been specified: an array of timestamps and an array of HK values, belonging to the
              specified time window.
    """

    setup = setup or load_setup()
    hk_dir = f"{data_dir}/daily/"  # Where the HK is stored

    try:

        origin, timestamp_name = get_hk_info(hk_name, setup=setup)

    except KeyError:

        raise HKError(f"Cannot determine which EGSE component generated HK parameter {hk_name}")

    hk_dir += f"{od}/"
    hk_files = [f"{od}_{get_site_id()}_{origin}.csv"]

    return _get_housekeeping(hk_name, timestamp_name, hk_dir, hk_files, time_window=time_window)


def _get_housekeeping_obsid(hk_name: str, data_dir, obsid: Union[ObservationIdentifier, str, int],
                            time_window: int = None, setup: Optional[Setup] = None):
    """ Return the timestamp(s) and HK value(s) for the HK parameter with the given name, for the given obsid.

    When the time window has not been specified, the last timestamp and HK value will be returned for the given obsid.
    It is possible that a component stopped writing HK for some reason, and that the last HK value is older than you
    would want.  It is therefore important to inspect the corresponding timestamp.

    When the time window has been specified, the relevant HK will be read:
        - determine the sampling rate (compare the timestamps for the last 2 lines in the HK file);
        - determine how many samples we need to read (starting at the back);
        - read the required number of line, starting at the back;
        - for each of the read lines, append the timestamp and HK value to the arrays that will be returned

    Args:
        - hk_name: Name of the housekeeping parameter.
        - data_dir: Folder (with sub-folders /daily and /obs) in which the HK files are stored.
        - obsid: Observation identifier.  This can be an ObservationIdentifier object, a string in format TEST_LAB or
                 TEST_LAB_SETUP, or an integer representing the test ID.
        - time_window: Length of the time window over which to retrieve the housekeeping [s].  The time window ends at
                       the moment this method is called.  If not given, the latest HK-value is returned.
        - setup: Setup.

    Returns:
        - If the time window has not been specified: the most recent timestamp and HK value.
        - If the time window has been specified: an array of timestamps and an array of HK values, belonging to the
          specified time window.
    """

    setup = setup or load_setup()

    hk_dir = f"{data_dir}/obs/"  # Where the HK is stored

    try:

        origin, timestamp_name = get_hk_info(hk_name, setup=setup)

    except KeyError:

        raise HKError(f"Cannot determine which EGSE component generated HK parameter {hk_name}")

    obsid = obsid_from_storage(obsid, data_dir=data_dir)     # Convert the obsid to the correct format

    hk_dir += f"{obsid}/"
    pattern = f"{obsid}_{origin}_*.csv"
    hk_files = sorted(find_files(pattern=pattern, root=hk_dir))

    if len(hk_files) == 0:

        raise HKError(f"No HK found for the {origin} at {get_site_id()} for obsid {obsid}")

    hk_files = [hk_files[-1].name]

    return _get_housekeeping(hk_name, timestamp_name, hk_dir, hk_files, time_window=time_window)


def _get_housekeeping_daily(hk_name: str, data_dir, time_window: int = None, setup: Optional[Setup] = None):
    """ Return the timestamp(s) and HK value(s) for the HK parameter with the given name.

    When the time window has not been specified, the last timestamp and HK value will be returned.  It is possible that
    a component stopped writing HK for some reason, and that the last HK value is older than you would want.  It is
    therefore important to inspect the corresponding timestamp.

    When the time window has been specified, it is possible that we have to fetch the HK from multiple files,
    depending on the length of the time window:

        * Oldest file (i.e. the HK file in which the first timestamp in the specified time window is held): only part
          of it will have to be read (start reading at the back):
            - determine the filename;
            - determine the sampling rate (compare the timestamps for the last 2 lines in the HK file);
            - determine how many samples we need to read (starting at the back);
            - read the required number of line, starting at the back;
            - for each of the read lines, append the timestamp and HK value to the arrays that will be returned.
        * Any other files: entire file will have to be read:
            - determine the filename;
            - read all lines;
            - for each line: append the timestamp and HK value to the arrays that will be returned.

    Args:
        - hk_name: Name of the housekeeping parameter.
        - data_dir: Folder (with sub-folders /daily and /obs) in which the HK files are stored.
        - time_window: Length of the time window over which to retrieve the housekeeping [s].  The time window ends at
          the moment this method is called.  If not given, the latest HK-value is returned.
        - setup: Setup.

    Returns:
        - If the time window has not been specified: the most recent timestamp and HK value.
        - If the time window has been specified: an array of timestamps and an array of HK values, belonging to the
          specified time window.
    """

    setup = setup or load_setup()
    hk_dir = f"{data_dir}/daily/"  # Where the HK is stored

    try:

        origin, timestamp_name = get_hk_info(hk_name, setup=setup)

    except KeyError:

        raise HKError(f"Cannot determine which EGSE component generated HK parameter {hk_name}")

    # No time window specified: return the last value

    if time_window is None:

        # Look for the last file of this component

        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d")
        hk_dir += f"{timestamp}/"
        filename = f"{timestamp}_{get_site_id()}_{origin}.csv"

        timestamp_index, hk_index = get_indices(hk_dir + filename, hk_name, timestamp_name)
        return get_last_non_empty(hk_dir + filename, timestamp_index, hk_index)

    # Time window specified

    else:

        # We will return an array of timestamps and an array of HK values

        timestamp_array = np.array([])
        hk_array = np.array([])

        # Go back in time from this very moment and determine:
        #   - which timespan the most recent HK file covers (i.e. how much time has elapsed since midnight)
        #   - what the time is at the start of the time window

        now = datetime.datetime.utcnow()
        elapsed_since_midnight = now.microsecond * 1e-6 + now.second + 60 * (now.minute + 60 * now.hour)
        start_time = now - datetime.timedelta(seconds=time_window)
        start_od = f"{start_time.year}{start_time.month:02d}{start_time.day:02d}"

        # Determine which columns will be needed from which file

        filename = f"{start_od}/{start_od}_{get_site_id()}_{origin}.csv"

        if Path(hk_dir + filename).exists():

            timestamp_index, hk_index = get_indices(hk_dir + filename, hk_name, timestamp_name)

            # Determine how many time samples you need to read in the first relevant HK file (starting from the back)

            sampling_rate = get_sampling_rate(hk_dir + filename, timestamp_name)  # Time between subsequent samples

            if time_window <= elapsed_since_midnight:

                num_samples_first_day = int(round(time_window / sampling_rate))

            else:

                time_window_first_day = (time_window - elapsed_since_midnight) % SECONDS_IN_A_DAY
                num_samples_first_day = int(round(time_window_first_day / sampling_rate))  # TODO Round or floor?

            # Read the required number of lines in the relevant HK file (starting from the back of the file)

            lines_first_day = read_last_lines(hk_dir + filename, num_samples_first_day)

            for line in lines_first_day:

                line = line.split(",")

                timestamp_array = np.append(timestamp_array, line[timestamp_index])
                hk_array = np.append(hk_array, line[hk_index])

        # In case we also need to read more recent files
        # (those will have to be read entirely)

        else:

            _LOGGER.warning(f"No HK available for {origin} on "
                           f"{start_time.day}/{start_time.month}/{start_time.year}")

        day = (start_time + datetime.timedelta(days=1)).date()  # The day after the first day
        last_day = datetime.date(now.year, now.month, now.day)  # Today

        while day <= last_day:

            od = f"{day.year}{day.month:02d}{day.day:02d}"
            filename = f"{od}/{od}_{get_site_id()}_{origin}.csv"

            if Path(hk_dir + filename).exists():

                with open(hk_dir + filename) as file:

                    csv_reader = csv.reader(file)

                    header = next(csv_reader)  # Skip the header
                    timestamp_index = header.index("timestamp")
                    try:
                        hk_index = header.index(hk_name)
                    except ValueError:
                        raise HKError(f"Cannot find column {hk_name} in {filename}")

                    for row in csv_reader:

                        timestamp_array = np.append(timestamp_array, row[timestamp_index])
                        hk_array = np.append(hk_array, row[hk_index])

            else:

                _LOGGER.warning(f"No HK available for {origin} on {day.day}/{day.month}/{day.year}")

            day += datetime.timedelta(days=1)

        for index in range(len(timestamp_array)):

            timestamp_array[index] = time_since_epoch_1958(timestamp_array[index])

        return timestamp_array, hk_array


def get_last_non_empty(filename: str, timestamp_index: int, hk_index: int):
    """  Return the timestamp and HK value for last real value.

    Args:
         - filename: HK file in which to look for the given HK parameter.
         - timestamp_index: Index of the column with the timestamps.
         - hk_index: Index of the column with the HK parameter with the given name.

    Returns:  The timestamp and HK value with the last real value.
    """

    timestamp = None
    hk_value = " "

    filename = Path(filename)

    if not filename.exists():
        return None

    # Declaring variable to implement exponential search

    try:

        num_lines = 1

        while hk_value == " " or hk_value == "":

            pos = num_lines + 1

            # List to store last N lines

            lines = []

            with open(filename) as f:

                while len(lines) <= num_lines:

                    try:

                        f.seek(-pos, 2)

                    except IOError:

                        f.seek(0)
                        break

                    finally:

                        lines = list(f)

                    # Increasing value of variable exponentially

                    pos *= 2

            last_line = lines[-num_lines].rstrip("\r").split(",")
            timestamp, hk_value = last_line[timestamp_index], last_line[hk_index]

            num_lines += 1

        return time_since_epoch_1958(timestamp), hk_value

    except IndexError:
        return None, None


def get_indices(filename: str, hk_name: str, timestamp_name: str):
    """ Return the column number of the timestamp and given HK parameter in the given HK file.

    Args:
        - filename: HK file in which to look for the given HK parameter.
        - hk_name: Name of the HK parameter.
        - timestamp_name: Name of the corresponding timestamp.

    Returns:
        - Index of the column with the timestamps.
        - Index of the column with the HK parameter with the given name.
    """

    with open(filename, "r") as f:

        reader = csv.reader(f)
        header = next(reader)  # Skip the header

    timestamp_index = header.index(timestamp_name)
    # timestamp_index = 0

    try:

        hk_index = header.index(hk_name)

    except ValueError:

        raise HKError(f"Cannot find column {hk_name} in {filename}")

    return timestamp_index, hk_index


def get_sampling_rate(filename: str, timestamp_name: str):
    """ Return the sampling rate for the HK file with the given name [s].

    The sampling rate is determine as the difference between the timestamps of the last two lines of the HK file.

    Args:
        - filename: Name of the HK file.  We do not check explicitly whether this file exists.

    Returns: Sampling rate for the HK file with the given name [s].
    """

    # Determine which column comprises the timestamp

    with open(filename, "r") as f:

        reader = csv.reader(f)
        header = next(reader)  # Skip the header

    timestamp_index = header.index(timestamp_name)

    # Read the last 2 lines and extract the timestamps for these lines

    eof = read_last_lines(filename, 2)

    penultimate_timestamp = date_parser.parse(eof[0].split(",")[timestamp_index])
    last_timestamp = date_parser.parse(eof[1].split(",")[timestamp_index])

    # Calculate the sampling rate [s]

    return (last_timestamp - penultimate_timestamp).total_seconds()


def convert_hk_names(original_hk: dict, conversion_dict: dict) -> dict:
    """
    Converts the names of the HK parameters in the given dictionary.

    The names/keys in the given dictionary of HK parameters (original_hk) are replaced by the names
    from the given conversion dictionary. The original dictionary is left unchanged, a new dictionary is
    returned.

    Args:
        - original_hk: Original dictionary of HK parameters.
        - conversion_dict: Dictionary with the original HK names as keys and the new HK names as values.

    Returns:
        A new dictionary of HK parameters with the corrected HK names.
    """

    converted_hk = {}

    for orig_key in original_hk:

        try:
            new_key = conversion_dict[orig_key]
        except KeyError:
            new_key = orig_key   # no conversion, just copy the key:value pair

        converted_hk[new_key] = original_hk[orig_key]

    return converted_hk


def read_conversion_dict(storage_mnemonic: str, use_site: bool = False, setup: Optional[Setup] = None):
    """ Read the HK spreadsheet and compose conversion dictionary for HK names.

    The spreadsheet contains the following information:

        - storage mnemonic of the component that generates the HK
        - original HK name (as is comes from the device itself)
        - HK name with the correct prefix
        - name of the column (in the HK file) with the corresponding timestamp

    Args:
        - storage_mnemonic: Storage mnemonic of the component for which to compose the conversion dictionary
        - use_site: Indicate whether the prefixes of the new HK names are TH-specific
        - setup: Setup.

    Returns: Dictionary with the original HK names as keys and the converted HK names as values.
    """

    setup = setup or load_setup()

    try:
        hk_info_table = setup.telemetry.dictionary
    except AttributeError:
        raise SetupError("Version of the telemetry dictionary not specified in the current setup")

    storage_mnemonic_col = hk_info_table[TmDictionaryColumns.STORAGE_MNEMONIC].values
    correct_name_col = hk_info_table[TmDictionaryColumns.CORRECT_HK_NAMES].values
    original_name_col = hk_info_table[TmDictionaryColumns.ORIGINAL_EGSE_HK_NAMES].values

    selection = np.where(storage_mnemonic_col == storage_mnemonic)

    correct_name_col = correct_name_col[selection]
    original_name_col = original_name_col[selection]

    if use_site:

        th_prefix = f"G{get_site_id()}_"

        th_conversion_dict = {}

        for (original_name, correct_name) in zip(original_name_col, correct_name_col):
            if str.startswith(str(correct_name), th_prefix):
                th_conversion_dict[original_name] = correct_name

        return th_conversion_dict

    else:

        if len(original_name_col) != len(correct_name_col):
            _LOGGER.error(f"Name columns in TM dictionary have different length: "
                          f"{len(original_name_col)} != {len(correct_name_col)}")

        return dict(zip(original_name_col, correct_name_col))


def get_hk_info(hk_name: str, setup: Optional[Setup] = None):
    """ Read the HK spreadsheet and extract information for the given HK parameter.

    The spreadsheet contains the following information:

        - storage mnemonic of the component that generates the HK
        - original HK name
        - HK name with the correct prefix
        - name of the column (in the HK file) with the corresponding timestamp

    Args:
        - hk_name: Name of the HK parameter.
        - setup: Setup.

    Returns:
        - storage mnemonic of the component that generates the given HK parameter
        - name of the column in the HK file with the corresponding timestamp
    """

    setup = setup or load_setup()
    hk_info_table = setup.telemetry.dictionary

    storage_mnemonic = hk_info_table[TmDictionaryColumns.STORAGE_MNEMONIC].values
    hk_names = hk_info_table[TmDictionaryColumns.CORRECT_HK_NAMES].values
    timestamp_col = hk_info_table[TmDictionaryColumns.TIMESTAMP_NAMES].values

    selection = np.where(hk_names == hk_name)

    try:
        return storage_mnemonic[selection][0], timestamp_col[selection][0]
    except IndexError:
        raise HKError(f"HK parameter {hk_name} unknown")


def get_storage_mnemonics(setup: Setup = None):
    """ Return the list of the storage mnemonics from the TM dictionary.

    Args:
          - setup: Setup.

    Returns: List of the storage mnemonics from the TM dictionary.
    """

    setup = setup or load_setup()

    hk_info_table = setup.telemetry.dictionary
    storage_mnemonics = hk_info_table[TmDictionaryColumns.STORAGE_MNEMONIC].values

    return np.unique(storage_mnemonics)


def get_housekeeping_names(name_filter=None, device_filter=None, setup: Setup = None):
    """ Return HK names, storage mnemonic, and description.

    The TM dictionary is read into a Pandas DataFrame.  If a device filter is given, only the rows pertaining to the
    given storage mnemonic are kept.  If a name filter is given, only the rows for which the HK parameter name contains
    the given name filter are kept.

    The result is returned as a Pandas DataFrame with the following columns:
        - "CAM EGSE mnemonic": Name of the HK parameter;
        - "Storage mnemonic": Storage mnemonic of the device producing the HK;
        - "Description": Description of the HK parameter.

    Synopsis:
        - get_housekeeping_names(name_filter="RAW", device_filter="N-FEE-HK")
        - get_housekeeping_names(name_filter="RAW", device_filter="N-FEE-HK", setup=setup)

    Args:
        - name_filter: Filter the HK dataframe, based on (a part of) the name of the HK parameter(s)
        - device: Filter the HK dataframe, based on the given storage mnemonic
        - setup: Setup.

    Returns: Pandas DataFrame with the HK name, storage mnemonic, and description of the HK parameters that pass the
             given filter.
    """

    setup = setup or load_setup()

    hk_info_table = setup.telemetry.dictionary
    hk_info_table.dropna(subset=[TmDictionaryColumns.CORRECT_HK_NAMES], inplace=True)

    if device_filter:
        hk_info_table = hk_info_table.loc[hk_info_table[TmDictionaryColumns.STORAGE_MNEMONIC] == device_filter]

    if name_filter:
        hk_info_table = hk_info_table.query(f'`{TmDictionaryColumns.CORRECT_HK_NAMES}`.str.contains("{name_filter}")')

    return hk_info_table[[TmDictionaryColumns.CORRECT_HK_NAMES, TmDictionaryColumns.STORAGE_MNEMONIC,
                          TmDictionaryColumns.DESCRIPTION]]
