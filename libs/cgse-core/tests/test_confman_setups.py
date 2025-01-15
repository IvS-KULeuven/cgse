def test_private_caching_functions():

    set_conf_repo_location(str(Path(__file__).parent))

    assert _get_cached_setup_info(0) is None

    _populate_cached_setup_info()

    assert _get_cached_setup_info(0) is not None
    assert _get_cached_setup_info(0).site_id == "CSL"

    _print_cached_setup_info()

    setup = load_setup(setup_id=28, site_id="CSL", from_disk=True)

    assert setup.get_id() == '00028'
    assert 'SETUP_CSL_00028' in str(setup.get_filename())

    _add_setup_info_to_cache(setup)

    assert _get_cached_setup_info(28) is not None
    assert _get_cached_setup_info(28).site_id == 'CSL'
    assert _get_cached_setup_info(28).path.name.endswith('SETUP_CSL_00028_201028_155259.yaml')

    _print_cached_setup_info()
