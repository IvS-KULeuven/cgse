import pytest

from egse.setup import Setup
from egse.setup import SetupError
from egse.setup import validate_setup_description


@pytest.mark.parametrize(
    "description",
    ["Initial setup", "it's fine", "Hexapod aligned (v2)", "see issue (#15)", "temperature 20.5 degC", "a - b", "a#b"],
)
def test_valid_descriptions(description):
    assert validate_setup_description(description) == description


@pytest.mark.parametrize(
    "description",
    [
        "test: foo",
        "trailing colon:",
        "comment # here",
        "(see issue #15)",  # The #15 is interpreted as a comment and will not be saved
        "- item",
        "[list]",
        "{map}",
        "&anchor",
        "*alias",
        "!tag",
        "",
        "a\nb",
    ],
)
def test_invalid_descriptions(description):
    with pytest.raises(SetupError):
        validate_setup_description(description)


def test_non_string_description():
    with pytest.raises(SetupError, match="must be a string"):
        validate_setup_description(42)


def test_validated_description_survives_yaml_roundtrip(tmp_path):
    description = "Hexapod aligned (v2)"
    setup = Setup({"history": {"1": validate_setup_description(description)}})
    filename = tmp_path / "setup.yaml"

    setup.to_yaml_file(filename)

    assert Setup.from_yaml_file(filename).history[1] == description
