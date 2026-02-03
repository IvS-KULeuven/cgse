from egse.scpi import count_number_of_channels
from egse.scpi import create_channel_list
from egse.scpi import get_channel_names


def test_get_channel_names():
    assert get_channel_names("1") == []
    assert get_channel_names("(@101)") == ["101"]
    assert get_channel_names("(@101,102,103)") == ["101", "102", "103"]
    assert get_channel_names("(@101:105)") == ["101", "102", "103", "104", "105"]
    assert get_channel_names("(@101, 102, 103, 105)") == ["101", "102", "103", "105"]
    assert get_channel_names("(@201:204,205,206,207:209,211)") == [
        "201",
        "202",
        "203",
        "204",
        "205",
        "206",
        "207",
        "208",
        "209",
        "211",
    ]


def test_get_channel_names_invalid():
    assert get_channel_names("") == []
    assert get_channel_names("101") == []
    assert get_channel_names("(@)") == []
    assert get_channel_names("(@101,,103)") == []
    assert get_channel_names("(@101:abc)") == []
    assert get_channel_names("(@101:102:103)") == []
    assert get_channel_names("(@101-105)") == []
    assert get_channel_names("(@10a)") == []
    assert get_channel_names("(@101, 10b)") == []
    assert get_channel_names("(@101:10c)") == []


def test_count_number_of_channels():
    assert count_number_of_channels("(@101)") == 1
    assert count_number_of_channels("(@101,102,103)") == 3
    assert count_number_of_channels("(@101:105)") == 5
    assert count_number_of_channels("(@101, 102, 103, 105)") == 4
    assert count_number_of_channels("(@201:204,205,206,207:209,211)") == 10
    assert count_number_of_channels("") == 0
    assert count_number_of_channels("101") == 0
    assert count_number_of_channels("(@)") == 0
    assert count_number_of_channels("(@101,,103)") == 0
    assert count_number_of_channels("(@101:abc)") == 0
    assert count_number_of_channels("(@101:102:103)") == 0
    assert count_number_of_channels("(@101-105)") == 0
    assert count_number_of_channels("(@10a)") == 0
    assert count_number_of_channels("(@101, 10b)") == 0
    assert count_number_of_channels("(@101:10c)") == 0


def test_create_channel_list():
    assert create_channel_list() == ""
    assert create_channel_list("101") == "(@101)"
    assert create_channel_list(["101"]) == "(@101)"
    assert create_channel_list(["101", "104"]) == "(@101:104)"
    assert create_channel_list("101", "102", "103") == "(@101,102,103)"
    assert create_channel_list("101", "102", "103", "104", "105") == "(@101,102,103,104,105)"
    assert create_channel_list("101", "102", "103", "105") == "(@101,102,103,105)"
    assert create_channel_list(["201", "204"], "205", "206", ["207", "209"], "211") == "(@201:204,205,206,207:209,211)"
