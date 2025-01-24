import datetime
import logging
import pickle
import textwrap
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import rich
import yaml

from egse.device import DeviceInterface
from egse.env import env_var
from egse.env import get_conf_data_location
from egse.env import get_conf_data_location_env_name
from egse.env import get_conf_repo_location_env_name
from egse.env import print_env
from egse.env import set_conf_repo_location
from egse.settings import SettingsError
from egse.setup import NavigableDict
from egse.setup import Setup
from egse.setup import get_last_setup_id_file_path
from egse.setup import get_path_of_setup_file
from egse.setup import load_last_setup_id
from egse.setup import load_setup
from egse.setup import navdict
from egse.setup import save_last_setup_id
from egse.system import AttributeDict
from fixtures.helpers import create_text_file

_LOGGER = logging.getLogger(__name__)

TEST_LOCATION = Path(__file__).parent


@dataclass
class SetupFixture:
    setup_path: Path


@dataclass
class DataFixture:
    data_path: Path

    @property
    def data_filename(self):
        return self.data_path.name


@pytest.fixture()
def default_test_setup(default_csv_test_data):

    conf_root = get_conf_data_location()

    setup_path = Path(conf_root) / "default_test_setup.yaml"

    create_text_file(
        setup_path,
        textwrap.dedent(
            f"""\
            # Example Setup configuration for 1234

            Setup:
                site_id:   KUL

                data_types:
                    array: csv//data/{default_csv_test_data.data_filename!s}
                    calibration: yaml//data/calibration.yaml
                    non_existing_yaml: yaml//data/unknown.yaml
                    table: csv//data/calibration.csv
                    non_existing_csv: csv//data/unknown.csv
                    corrupt_yaml: yaml//data/corrupt.yaml
            """
        ),
        create_folder=True
    )

    yield SetupFixture(setup_path=setup_path)

    setup_path.unlink()


@pytest.fixture()
def default_device_setup():
    conf_root = get_conf_data_location()

    setup_path = Path(conf_root) / "default_device_setup.yaml"

    create_text_file(
        setup_path,
        textwrap.dedent(
            """\
            # Example Setup configuration

            Setup:
                site_id:   KUL

                x: 1
                y:
                    device: class//test_setup.TakeTwoOptionalArguments
                z:
                    device: class//test_setup.TakeTwoOptionalArguments
                    device_args: [42, 73]
            """
        ),
        create_folder=True
    )

    yield SetupFixture(setup_path=setup_path)

    setup_path.unlink()


@pytest.fixture()
def default_calibration_setup():
    conf_root = get_conf_data_location()

    setup_path = Path(conf_root) / "default_calibration_setup.yaml"

    create_text_file(
        setup_path,
        textwrap.dedent(
            """\
            site_id: CSL

            gse:
                calibration: yaml//data/calibration.yaml
                non_existing_yaml: yaml//unknown.yaml
                table: csv//data/calibration.csv
                non_existing_csv: csv//unknown.csv
                corrupt_yaml: yaml//data/corrupt.yaml
            """
        ),
        create_folder=True
    )

    yield SetupFixture(setup_path=setup_path)

    setup_path.unlink()


@pytest.fixture()
def default_csv_test_data():

    conf_root = get_conf_data_location()

    csv_data_filename = "default_csv_test_data.csv"
    csv_data_path = Path(conf_root) / f"data/{csv_data_filename}"

    create_text_file(
        csv_data_path,
        textwrap.dedent(
            """\
            tx, ty, tz, rx, ry, rz
            1, 2, 3, 4, 5, 6
            0, 0, 0, 0, 0, 0
            0, 0, 0, 10, 20, 30
            """
        ),
        create_folder=True
    )

    yield DataFixture(data_path=csv_data_path)

    csv_data_path.unlink()


@pytest.fixture()
def default_csv_calibration_data():

    conf_root = get_conf_data_location()

    csv_data_filename = "calibration.csv"
    csv_data_path = Path(conf_root) / f"data/{csv_data_filename}"

    create_text_file(
        csv_data_path,
        textwrap.dedent(
            """\
            par_1, par_2, par_3
            1, 2, 3
            4, 5, 6
            7, 8, 9
            """
        ),
        create_folder=True
    )

    yield DataFixture(data_path=csv_data_path)

    csv_data_path.unlink()


@pytest.fixture()
def default_yaml_calibration_data():

    conf_root = get_conf_data_location()

    yaml_data_filename = "calibration.yaml"
    yaml_data_path = Path(conf_root) / f"data/{yaml_data_filename}"

    create_text_file(
        yaml_data_path,
        textwrap.dedent(
            """\
            # A YAML file that is used in a test Setup to test the automatic loading of the content when
            # the field is accessed.

            cal_1:
                function: polynomial
                coefficients: [1.5, 2.1, 3.4, 4.7]

            cal_2:
                function: linear
                coefficients: [100.3, 24.5]
            """
        ),
        create_folder=True
    )

    yield DataFixture(data_path=yaml_data_path)

    yaml_data_path.unlink()


def test_setup():

    setup = Setup()

    assert setup == {}


def test_setup_from_yaml():
    """Perform some basic tests on data from the setup.yaml test data file."""

    setup = Setup.from_yaml_file(
        filename=TEST_LOCATION / "data/conf/SETUP_20250114_1519.yaml", add_local_settings=False)

    assert setup.site_id == "HOME"
    assert setup.creation_date == datetime.date(2025, 1, 14)

    assert setup.camera.tou.ID == 0x100CAFE
    assert setup.camera.fee.ID == 0xA5FE62B

    # legs is a normal dict since not all its keys are of type `str`

    assert setup.gse.hexapod.calibration.legs[2] == 12.3


def test_from_yaml_exceptions():

    with pytest.raises(ValueError):
        Setup.from_yaml_file("")

    with pytest.raises(ValueError):
        Setup.from_yaml_file()

    with pytest.raises(ValueError):
        Setup.from_yaml_file(None)

    with pytest.raises(SettingsError):
        Setup.from_yaml_file(__file__)


def test_setup_from_dict():
    """Test if a Setup is properly created from a dictionary."""

    setup = Setup.from_dict({"a": 1, "b": 2})

    assert setup.a == setup["a"] == 1
    assert setup.b == setup["b"] == 2
    assert list(setup.keys()) == ["a", "b"]

    setup = Setup(navdict({"c": 3, "d": 4}))

    assert setup.c == setup["c"] == 3
    assert setup.d == setup["d"] == 4


def test_setup_set():
    """Test that new keys can be added to an existing Setup."""

    setup = Setup.from_yaml_file(filename=TEST_LOCATION / "data/conf/SETUP_20250114_1519.yaml",
                                 add_local_settings=False)

    setup.cal = navdict({"sma": {"h": None}})

    assert setup.cal.sma.h is None

    setup.cal.sma.h = 37

    assert setup.cal.sma.h == 37

    setup.cal.add("refmodel", {"s": 2})

    assert setup.cal.refmodel

    assert setup.cal.refmodel.s == 2


def test_attr_dict_get():
    """Test some basic NavigableDict functionality for getting keys and attributes."""

    n = NavigableDict(
        {"x": 1, "y": {"a": "a", "b": "class//egse.device.DeviceTransport"}}
    )

    assert n.x == 1
    assert n["x"] == n.x == 1

    assert isinstance(n.y, NavigableDict)
    assert isinstance(n["y"], navdict)

    assert n.y.a == "a"
    assert n["y"]["a"] == "a"

    assert n.y.b.__class__.__name__ == "DeviceTransport"
    assert n.y["b"].__class__.__name__ == "DeviceTransport"


class Simulator:
    def info(self):
        return "Simple simulator"


def test_attr_dict_set():
    """Test some basic NavigableDict functionality for setting keys and attributes."""

    nd = NavigableDict(
        {"x": 1, "y": {"a": "a", "b": "class//test_setup.Simulator"}}
    )

    # Both key and attribute should return the same value

    assert nd.x == nd["x"] == 1

    # Set/overwrite an existing attribute

    nd.x = 42

    assert nd.x == nd["x"] == 42

    # Accessing a non-existing attribute raises an AttributeError

    with pytest.raises(AttributeError):
        assert nd.z

    # Setting a non-existing attribute

    nd.z = 73

    assert nd.z == nd["z"] == 73

    # Setting a non-existing key, value

    nd["w"] = 117

    assert nd.w == nd["w"] == 117

    # Check if class has been instantiated

    sim = nd.y.b
    assert not isinstance(sim, str)
    assert isinstance(sim, Simulator)
    assert "simulator" in sim.info()


def test_attr_dict_set_dict():
    """
    When an attribute is added as a plain dictionary, the attribute itself is accessible,
    but the keys of the dictionary will not be accessible as attributes [CHANGED, they will].
    """

    n = NavigableDict({"x": 1, "y": {"a": "a", "b": "b"}})

    n.ascii_table = {k: hex(ord(k)) for k in "abcdefghijklmnopqrstuvwxyz"}

    # When an attribute is set, it is also added to the dictionary

    assert n["ascii_table"]

    print(n.ascii_table)
    print(n.pretty_str())

    assert n.ascii_table["a"] == "0x61"

    # The keys of the dictionary however are not accessible as attributes (intended behaviour)
    # This has changed! the keys are now accessible as attributes

    #  with pytest.raises(AttributeError):
    #     assert n.ascii_table.a
    assert n.ascii_table.a == "0x61"


def test_adding_dict_with_non_str_keys():
    """
    When the dictionary to add contains just one non-string key, none of the keys will be
    available as an attribute.
    """

    n = NavigableDict()

    n.values = {"one": 1, 1: 1, "two": 2, 2: 2, "three": 3, 3: 3}

    with pytest.raises(AttributeError):
        assert n.values.one == 1

    n.other = {"one": 1, "two": 2, "three": 3}

    assert n.other.one == 1


def test_attr_dict_set_nav_dict():
    """
    When you want to have all keys of dictionary accessible as attributes, make sure you add
    the dictionary as a NavigableDict and not as a plain dictionary.
    """

    n = NavigableDict({"x": 1, "y": {"a": "a", "b": "b"}})

    n.ascii_table = NavigableDict({k: hex(ord(k)) for k in "abcdefghijklmnopqrstuvwxyz"})

    assert n.ascii_table.a == n.ascii_table["a"] == "0x61"


def test_pretty_print():
    """
    A simple test for the pretty_str() method.
    """

    d = {"x": 1, "y": 2, "a long key for this dict": "test case", "z": {1: 1, 2: 2, 3: 3}}

    n = NavigableDict(d)

    assert "NavigableDict" in repr(n)
    assert "NavigableDict" not in str(n)
    assert "NavigableDict" not in n.pretty_str()

    assert len(n.pretty_str().split("\n")) == 8

    print()
    print(n.pretty_str())


def test_deletion():
    """
    This test checks if a key is removed from the dictionary, that
    the attribute is also removed from the object. Vice versa, if the
    attribute is removed, the key should also be removed.
    """

    nd = NavigableDict({"a": 1, "b": 2, "c": 3, "d": 4})

    assert nd.b == nd["b"] == 2

    # Delete the key 'b' and assert that both the key and the attribute are deleted

    del nd["b"]

    with pytest.raises(KeyError):
        assert nd["b"] == 2

    with pytest.raises(AttributeError):
        assert nd.b == 2

    with pytest.raises(KeyError):
        del nd["b"]  # I can not remove a key twice!

    # Delete the 'c' attribute and assert that both the key and the attribute are deleted

    del nd.c

    with pytest.raises(KeyError):
        assert nd["c"] == 3

    with pytest.raises(AttributeError):
        assert nd.c == 3

    with pytest.raises(AttributeError):
        del nd.c  # I cannot delete an attribute twice!


def test_no_extra_keys():
    """
    This test makes sure there are no extra keys than those defined in the dictionary.
    """

    nd = NavigableDict({"a": 1, "b": 2, "c": 3, "d": 4})

    keys = nd.keys()

    assert list(keys) == ["a", "b", "c", "d"]


def test_clear():
    """
    When a NavigableDict is cleared, both the keys in the dictionary and the attributes of
    the object should be cleared.
    """

    nd = NavigableDict({"a": 1, "b": 2, "c": 3, "d": 4})

    keys = list(nd.keys())  # The list makes sure that the keys will be remembered.

    assert len(nd.keys()) == 4

    nd.clear()

    assert len(nd.keys()) == 0  # should now be an empty key view
    assert len(keys) == 4

    for key in keys:
        assert not hasattr(nd, key)
        assert key not in nd


def test_hasattr():

    setup = Setup({"a": 1, "b": 2, "c": {"d": 4, "e": 5}})

    assert hasattr(setup, "a")
    assert not hasattr(setup, "d")


def test_private_keys():

    nd = NavigableDict({"a": 1, "b": 2, "c": 3, "d": 4})

    nd.set_private_attribute("_a", 11)

    assert "_a" not in nd
    assert nd.get_private_attribute("_a") == 11
    assert nd.has_private_attribute("_a")

    assert not nd.has_private_attribute("_b")

    with pytest.raises(ValueError):
        assert nd.get_private_attribute("a") == 1

    with pytest.raises(ValueError):
        nd.set_private_attribute("a", 11)

    with pytest.raises(ValueError):
        nd.set_private_attribute("e", 5)

    with pytest.raises(ValueError) as exc_info:
        nd.has_private_attribute("a")

    assert "Invalid argument" in exc_info.value.args[0]


def test_save_to_yaml():
    """
    This test loads the standard Setup and saves it without change to a new file.
    Loading back the saved Setup should show no differences.
    """

    orig_setup_name = TEST_LOCATION / "data/conf/SETUP_20250114_1519.yaml"
    orig_setup = Setup.from_yaml_file(orig_setup_name)

    saved_setup_name = TEST_LOCATION / "saved_setup.yaml"
    Setup.to_yaml_file(orig_setup, filename=saved_setup_name)

    # Reload the saved Setup

    saved_setup = Setup.from_yaml_file(filename=saved_setup_name, add_local_settings=False)

    deep_diff = Setup.compare(orig_setup, saved_setup)

    # If there were changes, the deep_diff dict would contain keys like: values_changed,
    # type_changes, dictionary_item_added, dictionary_item_removed, ...

    assert not deep_diff

    if deep_diff:
        import rich
        rich.print(AttributeDict(deep_diff))

    Path(saved_setup_name).unlink()


def test_save_to_yaml_exception():

    setup = Setup({"a": 1, "b": 2, "c": {"d": 4, "e": 5}})

    with pytest.raises(ValueError):
        setup.to_yaml_file()


def test_lazy_load_value_from_yaml(default_test_setup):
    """This test load a value from the Setup from a YAML file.

    * The loading should be lazy
    * The returned value should be the file content, but the actual value should still be the
      file identifier.
    """

    print_env()

    Setup.from_yaml_file.cache_clear()  # needed because the same file is used elsewhere

    setup_path = default_test_setup.setup_path

    orig_setup = Setup.from_yaml_file(setup_path, add_local_settings=False)

    # Save a file as a CVS file and add the file identifier to a key in the Setup

    arr = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]])

    new_csv_file_name = Path(get_conf_data_location()) / "data/test_arr.csv"
    np.savetxt(new_csv_file_name, arr, delimiter=",", header="Test data used in test_setup.py")

    # Test the values from the original array

    assert orig_setup.data_types.array[0, 2] == 3.0  # load csv file with __getattribute__
    assert orig_setup.data_types.array[2, 3] == 10.0  # load csv file with __getattribute__

    orig_arr = orig_setup.data_types.array  # load csv file with __getattribute__

    assert orig_arr[0, 2] == 3.0
    assert orig_arr[2, 3] == 10.0

    orig_setup.data_types.array = "csv//data/test_arr.csv"

    assert orig_setup.data_types.array[1, 2] == 7.0  # load csv file with __getattribute__
    assert orig_setup.data_types.array[2, 3] == 12.0  # load csv file with __getattribute__
    assert isinstance(orig_setup.data_types["array"], np.ndarray)  # load csv file with __getitem__

    Path(new_csv_file_name).unlink()

    print_env()


def test_pickling(default_test_setup, default_csv_test_data):

    Setup.from_yaml_file.cache_clear()  # needed because the same file is used elsewhere

    setup_path = default_test_setup.setup_path

    orig_setup = Setup.from_yaml_file(setup_path, add_local_settings=False)

    xx = pickle.dumps(orig_setup)
    yy = pickle.loads(xx)

    # Note: location of the resource is always relative to the {PROJECT}_CONF_DATA_LOCATION

    assert yy.data_types.get_raw_value("array") == f"csv//data/{default_csv_test_data.data_filename}"
    assert yy.data_types.array[0, 2] == 3.0


def test_raw_value(default_test_setup, default_csv_test_data):

    Setup.from_yaml_file.cache_clear()  # needed because the same file is used elsewhere

    setup_path = default_test_setup.setup_path
    orig_setup = Setup.from_yaml_file(setup_path, add_local_settings=False)

    assert orig_setup.get_raw_value("site_id") == "KUL"
    assert isinstance(orig_setup.get_raw_value("data_types"), NavigableDict)
    assert orig_setup.data_types.get_raw_value("array") == f"csv//data/{default_csv_test_data.data_filename}"

    with pytest.raises(KeyError):
        orig_setup.get_raw_value("unknown")


class TakeTwoOptionalArguments(DeviceInterface):
    """Test class for device with device_args."""
    def __init__(self, a=23, b=24):
        super().__init__()
        self._a = a
        self._b = b

    def __str__(self):
        return f"a={self._a}, b={self._b}"


SETUP_YAML = """
x: 1
y:
    device: class//test_setup.TakeTwoOptionalArguments
z:
    device: class//test_setup.TakeTwoOptionalArguments
    device_args: [42, 73]
"""


def test_device_args():

    d = yaml.safe_load(SETUP_YAML)
    nd = NavigableDict(d)

    d_y = nd.y.device

    assert isinstance(d_y, TakeTwoOptionalArguments)
    assert str(d_y) == "a=23, b=24"

    d_z = nd.z.device

    assert isinstance(d_z, TakeTwoOptionalArguments)
    assert str(d_z) == "a=42, b=73"

    d_z = nd.z["device"]

    assert isinstance(d_z, TakeTwoOptionalArguments)
    assert str(d_z) == "a=42, b=73"

    setup = Setup(d)
    setup.to_yaml_file("xxx.yaml")


SETUP_YAML_FOR_FIELD = """

Setup:
    site_id: CSL

    gse:
        calibration: yaml//data/calibration.yaml
        non_existing_yaml: yaml//unknown.yaml
        table: csv//data/calibration.csv
        non_existing_csv: csv//unknown.csv
        corrupt_yaml: yaml//data/corrupt.yaml
"""


def test_load_yaml_for_a_field(default_yaml_calibration_data):

    setup = Setup.from_yaml_string(SETUP_YAML_FOR_FIELD)

    assert setup.gse.get_raw_value('calibration').startswith("yaml//")
    assert setup.gse.get_memoized_keys() == []
    assert setup.gse.calibration.cal_2.coefficients[1] == 24.5
    assert setup.gse.get_memoized_keys() == ['calibration']


def test_load_csv_for_a_field(default_csv_calibration_data):

    print()

    setup = Setup.from_yaml_string(SETUP_YAML_FOR_FIELD)

    assert setup.gse.get_raw_value('table').startswith("csv//")

    rich.print(setup.gse.table)

    assert setup.gse.table[0, 2] == 3
    assert setup.gse.table[2, 1] == 8


def test_csv_file_for_field_not_found():

    print()

    setup = Setup.from_yaml_string(SETUP_YAML_FOR_FIELD)

    assert setup.gse.get_raw_value('non_existing_csv').startswith("csv//")

    with pytest.raises(ValueError) as ve:
        _ = setup.gse.non_existing_csv

    rich.print(ve.value)


def test_yaml_file_for_field_not_found():

    print()

    setup = Setup.from_yaml_string(SETUP_YAML_FOR_FIELD)

    assert setup.gse.get_raw_value('non_existing_yaml').startswith("yaml//")

    with pytest.raises(ValueError) as ve:
        _ = setup.gse.non_existing_yaml

    rich.print(ve.value)


def test_yaml_file_for_field_not_loaded():

    print()

    setup = Setup.from_yaml_string(SETUP_YAML_FOR_FIELD)

    assert setup.gse.get_raw_value('corrupt_yaml').startswith("yaml//")

    with pytest.raises(ValueError) as ve:
        _ = setup.gse.corrupt_yaml

    rich.print(ve.value)

    assert "Couldn't load resource" in ve.value.args[0]


def test_saving_setup_with_yaml_and_csv_resources(default_csv_calibration_data):

    setup = Setup.from_yaml_string(SETUP_YAML_FOR_FIELD)

    # make sure you have accessed the fields before saving

    assert setup.gse.calibration.cal_2.coefficients[1] == 24.5
    assert setup.gse.table[0, 2] == 3

    filepath = Path("xxx.yaml")
    setup.to_yaml_file(filepath)
    filepath.unlink(missing_ok=True)


def test_get_path_of_last_setup_file():

    env_name = get_conf_data_location_env_name()
    env_repo_name = get_conf_repo_location_env_name()

    with env_var(PROJECT="CGSE"), env_var(**{env_name: None}), env_var(**{env_repo_name: None}):

        with pytest.raises(FileNotFoundError):
            get_path_of_setup_file(43, "SRON")

        with pytest.warns(UserWarning, match="CGSE_CONF_REPO_LOCATION doesn't exist: YYYY"):
            set_conf_repo_location('YYYY')

        with (pytest.raises(LookupError),
              pytest.warns(UserWarning, match="configuration data repository doesn't exist: YYYY")):
            get_path_of_setup_file(setup_id=43, site_id='XXXX')

        with env_var(**{env_repo_name: "/tmp/no-such-folder"}):
            with pytest.raises(LookupError):
                get_path_of_setup_file(setup_id=43, site_id='XXXX')

            with pytest.raises(LookupError):
                get_path_of_setup_file(setup_id=43, site_id='SRON')

            # FIXME: these tests became invalid after a change in the strategy of checking in get_path_of_setup_file()
            # assert "SETUP_SRON_00031" in str(get_path_of_setup_file(setup_id=None, site_id="SRON"))
            # assert "SETUP_SRON_00029" in str(get_path_of_setup_file(setup_id=29, site_id="SRON"))


@pytest.mark.skip(reason="load_setup prefers the repo location over the conf data location.")
def test_load_setup_from_disk():

    with pytest.raises(ValueError):
        _ = load_setup(from_disk=True)

    env_repo_name = get_conf_repo_location_env_name()
    with env_var(**{env_repo_name: "/tmp/no-such-folder-either"}):

        # This will always fail since the load_setup() -> get_path_of_setup_file() prefers the repo location
        # over the conf data location. Since we set the repo location to a non-existing folder, this will fail.
        # FIXME: provide a proper mocked repo location or se the conf data location.

        setup = load_setup(site_id='SRON', from_disk=True)

        assert setup.site_id == 'SRON'
        assert setup.camera.fee.ID == 174057003
        assert 31 in setup.history

        setup = load_setup(setup_id=28, site_id='SRON', from_disk=True)

        assert setup.site_id == 'SRON'
        assert 29 not in setup.history
        assert "SETUP_SRON_00028" in str(setup.get_private_attribute("_filename"))

        setup = load_setup(setup_id=28, site_id='CSL', from_disk=True)

        assert setup.site_id == 'CSL'
        assert 29 not in setup.history
        assert "SETUP_CSL_00028" in str(setup.get_private_attribute("_filename"))


def test_last_setup_id():

    with (env_var(PROJECT="CGSE"),
          env_var(SITE_ID="CSL"),
          env_var(CGSE_DATA_STORAGE_LOCATION=str(TEST_LOCATION / 'data'))):

        get_last_setup_id_file_path().unlink(missing_ok=True)

        assert load_last_setup_id() == 0

        # File was previously deleted, so, the load_last_setup_id() will create the file and return 0

        assert get_last_setup_id_file_path().is_file()
        assert get_last_setup_id_file_path().exists()
        assert get_last_setup_id_file_path().is_absolute()

        save_last_setup_id(23)
        assert load_last_setup_id() == 23
        save_last_setup_id("42")
        assert load_last_setup_id() == 42

        get_last_setup_id_file_path().unlink(missing_ok=True)


def test_last_setup_site_dependence():

    # Test that successive calls for different site ids do not overwrite previously save setup ids for a site.

    site_setup_ids = {"SRON": 2, "INTA": 23, "IAS": 47, "CSL1": 17, "CSL2": 18}

    with env_var(PROJECT="CGSE"), env_var(CGSE_DATA_STORAGE_LOCATION=str(TEST_LOCATION / 'data')):

        for site_id, setup_id in site_setup_ids.items():
            assert site_id in str(get_last_setup_id_file_path(site_id=site_id))
            save_last_setup_id(setup_id=setup_id, site_id=site_id)

        for site_id, setup_id in site_setup_ids.items():
            assert setup_id == load_last_setup_id(site_id=site_id)

        for site_id in site_setup_ids:
            get_last_setup_id_file_path(site_id=site_id).unlink(missing_ok=True)


class Device:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        print(f"{args = }, {kwargs = }")

    def get_args(self):
        return self.args

    def get_kwargs(self):
        return self.kwargs


class DeviceFactory:
    def create(self, *, device_name: str, **_ignored):
        print(f"{device_name = }, {_ignored = }")
        return Device(device_name, **_ignored)


AAAADeviceFactory = BBBBDeviceFactory = CCCCDeviceFactory = DDDDDeviceFactory = DeviceFactory


def test_device_factory():

    setup = Setup.from_yaml_string(
        textwrap.dedent(
            """
            gse:
                AAAA:
                    device: factory//test_setup.AAAADeviceFactory
                BBBB:
                    device: factory//test_setup.BBBBDeviceFactory
                    device_args:
                        device_name: XXX
                CCCC:
                    device: factory//test_setup.CCCCDeviceFactory
                    device_args:
                        device_name: YYY
                        device_id: YYY_ID
                DDDD:
                    device: factory//test_setup.DDDDDeviceFactory
                    device_args:
                        device_name: ZZZ
                    ID: ZZZ_ID
            """
        )
    )

    print()

    # This should raise a TypeError on the missing 'device_name' argument

    with pytest.raises(TypeError):
        assert isinstance(setup.gse.AAAA.device, Device)

    assert isinstance(setup.gse.BBBB.device, Device)

    dev = setup.gse.BBBB.device
    assert len(dev.get_args()) == 1
    assert dev.get_args()[0] == "XXX"
    assert len(dev.get_kwargs()) == 0

    dev = setup.gse.CCCC.device
    assert len(dev.get_args()) == 1
    assert dev.get_args()[0] == "YYY"
    assert len(dev.get_kwargs()) == 1
    assert "device_id" in dev.get_kwargs()
    assert dev.get_kwargs()["device_id"] == "YYY_ID"

    dev = setup.gse.DDDD.device
    assert len(dev.get_args()) == 1
    assert dev.get_args()[0] == "ZZZ"
    assert len(dev.get_kwargs()) == 0


# Now in the following tests let's prove the factory implementation is device independent

class Beer:
    def __init__(self, name: str, alcohol: float):
        self._name = name
        self._alcohol = alcohol

    @property
    def name(self):
        return self._name

    @property
    def alcohol(self):
        return self._alcohol


class BeerFactory:
    def create(self, *, beer_name, percent_alcohol, **_ignored):
        print(f"{beer_name = }, {percent_alcohol = }, {_ignored = }")
        return Beer(beer_name, percent_alcohol)


def test_beer_factory():

    setup = Setup.from_yaml_string(
        textwrap.dedent(
            """
            AchelBlond:
                beer: factory//test_setup.BeerFactory
                beer_args:
                    beer_name: Achel Blond
                    percent_alcohol: 8.0

            AchelExtra:                    
                beer: factory//test_setup.BeerFactory
                beer_args:
                    beer_name: Achel Blond Extra
                    percent_alcohol: 9.5
                    volume: 75cl
            """
        )
    )

    print()

    beer = setup.AchelBlond.beer

    assert isinstance(beer, Beer)
    assert beer.name == "Achel Blond"
    assert beer.alcohol == 8.0

    beer = setup.AchelExtra.beer

    assert isinstance(beer, Beer)
    assert beer.name == "Achel Blond Extra"
    assert beer.alcohol == 9.5
