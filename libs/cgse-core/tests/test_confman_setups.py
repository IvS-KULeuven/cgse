from egse.setup import load_setup


def test_private_caching_functions(default_env):

    from egse.confman import _get_cached_setup_info
    from egse.confman import _populate_cached_setup_info
    from egse.confman import _print_cached_setup_info
    from egse.confman import _add_setup_info_to_cache

    assert _get_cached_setup_info(0) is None

    _populate_cached_setup_info()

    assert _get_cached_setup_info(0) is not None
    assert _get_cached_setup_info(0).site_id == "LAB23"

    _print_cached_setup_info()

    from egse.env import print_env
    print_env()

    # The Setup shall be loaded from the configuration data location, not from the repo location (which is None)
    setup = load_setup(setup_id=28, site_id="LAB23", from_disk=True)

    assert setup.get_id() == '00028'
    assert 'SETUP_LAB23_00028' in str(setup.get_filename())

    _add_setup_info_to_cache(setup)

    assert _get_cached_setup_info(28) is not None
    assert _get_cached_setup_info(28).site_id == 'LAB23'
    assert _get_cached_setup_info(28).path.name.endswith('SETUP_LAB23_00028_240123_120028.yaml')

    _print_cached_setup_info()
