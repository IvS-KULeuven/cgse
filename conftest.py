from glob import glob

import rich

# Quick hack to load plugins from different places.
# This doesn't work, I get an import error.

# def refactor(string: str) -> str:
#     entry = string.replace("/", ".").replace("\\", ".").replace(".py", "")
#     rich.print(f"[green]{entry = }[/]")
#     return entry
#
# pytest_plugins = [
#     refactor(conftest)
#     for conftest in glob("**/tests/fixtures/*.py", recursive=True)
#     if "__" not in conftest
# ]

# Doesn't work, with the following error:
#
# File "/Users/rik/github/cgse/libs/cgse-common/tests/fixtures/default_env.py", line 7, in <module>
#     from fixtures.helpers import setup_data_storage_layout, teardown_data_storage_layout
# ImportError: Error importing plugin "libs.cgse-common.tests.fixtures.default_env": No module named 'fixtures'
#

# pytest_plugins = [
#     "libs.cgse-common.tests.fixtures.helpers",
#     "libs.cgse-common.tests.fixtures.default_env",
#     "libs.cgse-core.tests.fixtures.services",
# ]
