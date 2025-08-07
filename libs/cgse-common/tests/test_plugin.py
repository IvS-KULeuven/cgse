import logging

from egse.plugin import load_plugins_fn

logger = logging.getLogger("test")


def test_load_plugins_fn():
    # Load ALL plugins from the `egse.plugins` namespace
    plugins_1 = load_plugins_fn("plugins/**/*.py", "egse")
    print(plugins_1)

    # Load ALL plugins from the `egse.plugins` namespace
    plugins_2 = load_plugins_fn("**/*.py", "egse.plugins")
    print(plugins_2)

    assert plugins_1.keys() == plugins_2.keys()

    assert "influxdb" in plugins_1
    assert "fits" in plugins_1
    assert "hdf5" in plugins_1

    # No Exception should be raised when the module doesn't exist
    plugins = load_plugins_fn("not-a-module")
    assert plugins == {}

    # Load a normal regular module
    plugins = load_plugins_fn("bits.py", "egse")
    assert "bits" in plugins
