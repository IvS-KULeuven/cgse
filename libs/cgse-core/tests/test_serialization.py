from pathlib import Path

from egse.serialization import to_json_safe


class _AsDictObject:
    def as_dict(self):
        return {"answer": 42, "path": Path("/tmp/value")}


class _ToDictObject:
    def to_dict(self):
        return {"value": "from_to_dict"}


class _BrokenAsDictWithToDict:
    def as_dict(self):
        raise RuntimeError("boom")

    def to_dict(self):
        return {"fallback": True}


class _BrokenToDict:
    def to_dict(self):
        raise RuntimeError("boom in to_dict")


class _FallbackToStr:
    def __str__(self):
        return "fallback-string"


class _UsingReprIfNoStr:
    def __repr__(self):
        return "repr-value"


class _NoneOfTheAbove:
    pass


def test_to_json_safe_primitives_and_path():
    assert to_json_safe(None) is None
    assert to_json_safe(True) is True
    assert to_json_safe(7) == 7
    assert to_json_safe(3.14) == 3.14
    assert to_json_safe("text") == "text"
    assert to_json_safe(Path("/tmp/demo")) == "/tmp/demo"


def test_to_json_safe_nested_containers_and_stringified_keys():
    payload = {
        5: Path("/tmp/a"),
        "items": [1, (2, Path("/tmp/b")), {"inner": Path("/tmp/c")}],
    }

    converted = to_json_safe(payload)

    assert converted == {
        "5": "/tmp/a",
        "items": [1, [2, "/tmp/b"], {"inner": "/tmp/c"}],
    }


def test_to_json_safe_prefers_as_dict_then_to_dict_and_final_fallback():
    assert to_json_safe(_AsDictObject()) == {"answer": 42, "path": "/tmp/value"}
    assert to_json_safe(_ToDictObject()) == {"value": "from_to_dict"}
    assert to_json_safe(_BrokenAsDictWithToDict()) == {"fallback": True}
    assert to_json_safe(_BrokenToDict()).startswith("<test_serialization._BrokenToDict object at ")
    assert to_json_safe(_FallbackToStr()) == "fallback-string"
    assert to_json_safe(_NoneOfTheAbove()).startswith("<test_serialization._NoneOfTheAbove object at ")
    assert to_json_safe(_UsingReprIfNoStr()) == "repr-value"
