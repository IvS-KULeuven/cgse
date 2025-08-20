from egse.plugin import HierarchicalEntryPoints


def test_hierarchical_entry_points():
    print()

    cgse_ext = HierarchicalEntryPoints("cgse.extension")

    assert cgse_ext.base_group == "cgse.extension"
    assert len(cgse_ext.get_by_subgroup("setup_provider")) == 1
