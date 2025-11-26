"""
Tests for the egse.version module.
"""

import subprocess
import textwrap
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from egse.version import get_version_from_git
from egse.version import get_version_from_settings
from egse.version import get_version_from_settings_file_raw
from egse.version import get_version_installed


@patch("egse.plugin.entry_points")
@patch("egse.version.get_version_installed")
@patch("egse.version.get_version_from_git")
def test_main_execution(mock_git, mock_installed, mock_entry_points, capsys):
    """Test the main script execution."""
    mock_git.return_value = "2024.2.0-5-g1234567"
    mock_installed.return_value = "2024.1.0"
    mock_entry_point = MagicMock()
    mock_entry_point.name = "test-package"
    mock_entry_points.return_value = [mock_entry_point]

    # Import, execute the main function, and capture the output

    import egse.version
    from egse.version import main

    main()

    captured = capsys.readouterr()

    assert "CGSE version in Settings:" in captured.out
    assert egse.version.VERSION in captured.out

    assert "git version (current project) =" in captured.out
    assert "2024.2.0-5-g1234567" in captured.out

    assert "Installed version for test-package=" in captured.out
    assert "2024.1.0" in captured.out

    assert hasattr(egse.version, "VERSION")
    assert hasattr(egse.version, "__PYPI_VERSION__")

    captured = capsys.readouterr()

    with patch("egse.version.VERSION", None):
        main()
        assert "CGSE version in Settings:" not in captured.out


def test_get_version_from_settings():
    """Test reading version from settings.yaml file or a YAML string."""

    settings_content = textwrap.dedent(
        """
        CGSE:
            VERSION: 2025.11.25
            # This is a comment
            SITE_ID: TEST_LAB
        """
    )

    # Test with yaml_string input, this will take precedence over file input.

    version = get_version_from_settings("CGSE", yaml_string=settings_content)
    assert version == "2025.11.25"

    # Test mocking Settings.load to return specific values. We need to patch.object here since
    # Settings is imported inside the function `get_version_from_settings()`.

    import egse.settings
    from egse.settings import SettingsError
    from egse.system import attrdict

    with patch.object(egse.settings, "Settings") as inner_settings:
        inner_settings.load.return_value = attrdict({"VERSION": "2025.11.26", "SITE_ID": "TEST_LAB_2"})
        version = get_version_from_settings("CGSE")
        assert version == "2025.11.26"

    # Test with incorrect group name, this will result in eventually calling get_version_from_settings_file_raw()
    # which is tested below. With the WRONG_GROUP name, Settings.load() will raise a SettingsError
    # and the get_version_from_settings_file_raw() will raise a RuntimeError.

    with patch.object(egse.settings, "Settings") as inner_settings:
        inner_settings.load.side_effect = SettingsError()
        with pytest.raises(RuntimeError):
            get_version_from_settings("WRONG_GROUP")


def test_valid_settings_file(tmp_path):
    """Test reading version from a valid settings.yaml file."""
    settings_file = tmp_path / "settings.yaml"
    settings_content = textwrap.dedent(
        """\
        CGSE:
            VERSION: 2024.1.23
            # This is a comment
            OTHER_SETTING: value
        """
    )
    settings_file.write_text(settings_content)

    version = get_version_from_settings_file_raw("CGSE", location=tmp_path)
    assert version == "2024.1.23"


def test_version_with_inline_comment(tmp_path):
    """Test reading version with inline comment."""
    settings_file = tmp_path / "settings.yaml"
    settings_content = textwrap.dedent(
        """\
        CGSE:
            VERSION: 2024.1.24  # inline comment
        """
    )
    settings_file.write_text(settings_content)

    version = get_version_from_settings_file_raw("CGSE", location=tmp_path)
    assert version == "2024.1.24"


def test_invalid_group_name(tmp_path):
    """Test error when group name doesn't match."""
    settings_file = tmp_path / "settings.yaml"
    settings_content = textwrap.dedent(
        """\
        CGSE:
            VERSION: 2024.1.0
        """
    )
    settings_file.write_text(settings_content)

    with pytest.raises(RuntimeError, match="Incompatible format.*should start with 'WRONG_GROUP'"):
        get_version_from_settings_file_raw("WRONG_GROUP", location=tmp_path)


def test_missing_version_field(tmp_path):
    """Test error when VERSION field is missing."""
    settings_file = tmp_path / "settings.yaml"
    settings_content = textwrap.dedent(
        """\
        CGSE:
            OTHER_FIELD: random value
        """
    )
    settings_file.write_text(settings_content)

    with pytest.raises(RuntimeError, match="no VERSION found"):
        get_version_from_settings_file_raw("CGSE", location=tmp_path)


@patch("egse.system.chdir")
@patch("subprocess.run")
def test_successful_git_describe(mock_run, mock_chdir):
    """Test successful git describe command."""
    mock_proc = MagicMock()
    mock_proc.stdout = b"2024.1.0-5-g1234567\n"
    mock_proc.stderr = b""
    mock_run.return_value = mock_proc

    version = get_version_from_git()
    assert version == "2024.1.0-5-g1234567"
    mock_run.assert_called_once_with(
        ["git", "describe", "--tags", "--long", "--always"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )


@patch("egse.system.chdir")
@patch("subprocess.run")
def test_empty_stdout(mock_run, mock_chdir):
    """Test when git command returns empty stdout."""
    mock_proc = MagicMock()
    mock_proc.stdout = b""
    mock_proc.stderr = b"some error"
    mock_run.return_value = mock_proc

    version = get_version_from_git()

    assert version == "0.0.0"


@patch("egse.system.chdir")
@patch("subprocess.run")
def test_git_command_failure(mock_run, mock_chdir):
    """Test when git command raises CalledProcessError."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "git")

    version = get_version_from_git()

    assert version == "0.0.0"


@patch("egse.system.chdir")
@patch("subprocess.run")
def test_with_specific_location(mock_run, mock_chdir, tmp_path):
    """Test git describe with specific location."""
    mock_proc = MagicMock()
    mock_proc.stdout = b"2024.2.0-0-gabcdefg\n"
    mock_proc.stderr = b""
    mock_run.return_value = mock_proc

    version = get_version_from_git(location=tmp_path)
    assert version == "2024.2.0-0-gabcdefg"


# Tests for get_version_installed function.


@patch("importlib.metadata.version")
def test_package_found(mock_get_version):
    """Test when package is found in metadata."""
    mock_get_version.return_value = "2024.1.0+local.123"

    version = get_version_installed("cgse-common")
    assert version == "2024.1.0+local.123"


@patch("importlib.metadata.version")
def test_package_not_found(mock_get_version):
    """Test when package is not found in metadata."""
    from importlib.metadata import PackageNotFoundError

    mock_get_version.side_effect = PackageNotFoundError("cgse-unknown")

    version = get_version_installed("cgse-unknown")

    assert version == "0.0.0"


# Integration tests for version module variables.


def test_version_is_set():
    """Test that VERSION variable is set."""
    from egse.version import VERSION

    assert VERSION is not None
    # VERSION should either be a valid version string or "0.0.0"
    assert isinstance(VERSION, str)
    assert len(VERSION) > 0


def test_pypi_version_format():
    """Test that __PYPI_VERSION__ is properly formatted."""
    from egse.version import __PYPI_VERSION__

    assert __PYPI_VERSION__ is not None
    assert isinstance(__PYPI_VERSION__, str)
    # Should not contain '+' as it's split on that character
    assert "+" not in __PYPI_VERSION__


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
