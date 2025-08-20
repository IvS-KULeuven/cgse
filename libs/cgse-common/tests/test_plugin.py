import logging

from egse.plugin import HierarchicalEntryPoints
from egse.plugin import load_plugins_fn

logger = logging.getLogger("test")


def test_load_plugins_fn():
    # Load ALL plugins from the `egse` namespace in the plugins folder
    plugins_1 = load_plugins_fn("plugins/**/*.py", "egse")
    print(plugins_1)

    # Load ALL plugins from the `egse.plugins` namespace
    plugins_2 = load_plugins_fn("**/*.py", "egse.plugins")
    print(plugins_2)

    assert plugins_1.keys() == plugins_2.keys()

    assert "influxdb" in plugins_1

    # No Exception should be raised when the module doesn't exist
    plugins = load_plugins_fn("not-a-module")
    assert plugins == {}

    # Load a normal regular module
    plugins = load_plugins_fn("bits.py", "egse")
    assert "bits" in plugins


def test_hierarchical_entry_points():
    # We have no extensions defined in the `cgse-common` package. A similar test should be run for
    # the `cgse-core` package.

    print()

    cgse_ext = HierarchicalEntryPoints("cgse.extension")

    assert cgse_ext.base_group == "cgse.extension"
    assert len(cgse_ext.get_by_subgroup("setup")) == 0
