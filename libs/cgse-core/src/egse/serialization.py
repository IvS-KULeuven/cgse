"""Shared serialization helpers for JSON-safe payload conversion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Protocol

from egse.log import logger
from egse.setup import Setup
from navdict import NavigableDict


def to_json_safe(value: Any) -> Any:
    """Recursively convert values into JSON-serializable structures.

    This helper normalizes controller and service payloads that can contain rich
    Python objects (for example `Path`, nested containers, or custom objects that
    expose `as_dict` / `to_dict`) into plain JSON-safe values.

    Conversion rules:
    - primitives are returned unchanged;
    - `Path` becomes `str(path)`;
    - mappings and iterables are converted recursively;
    - objects with `as_dict()` or `to_dict()` are converted via those methods;
    - remaining values fall back to `str(value)`.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]

    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        try:
            return to_json_safe(as_dict())
        except Exception:
            logger.warning(
                f"as_dict() method of {type(value).__name__} raised an exception during JSON conversion.",
                exc_info=True,
            )

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_json_safe(to_dict())
        except Exception:
            logger.warning(
                f"to_dict() method of {type(value).__name__} raised an exception during JSON conversion.",
                exc_info=True,
            )

    return str(value)


class Codec(Protocol):
    def encode(self, value: Any) -> Any:
        """Return a JSON-safe payload for the given object."""

    def decode(self, payload: Any) -> Any:
        """Rebuild the original object from a JSON-safe payload."""


class JsonCodec:
    """Pass-through codec for values that are already JSON-safe."""

    name = "json"

    def encode(self, value: Any) -> Any:
        return value

    def decode(self, payload: Any) -> Any:
        return payload


class SetupCodec:
    """Typed codec for Setup preserving private metadata fields."""

    def encode(self, value: Setup) -> dict[str, Any]:
        return {
            "setup_data": dict(value),
            "setup_meta": {
                "_setup_id": value.get_private_attribute("_setup_id"),
                "_filename": value.get_private_attribute("_filename"),
            },
        }

    def decode(self, payload: dict[str, Any]) -> Setup:
        setup = Setup(NavigableDict.from_dict(payload["setup_data"]))
        setup_meta = payload.get("setup_meta", {})
        setup_id = setup_meta.get("_setup_id")
        filename = setup_meta.get("_filename")

        if setup_id is not None:
            setup.set_private_attribute("_setup_id", setup_id)
        if filename is not None:
            setup.set_private_attribute("_filename", filename)

        return setup


@dataclass(frozen=True)
class CodecBinding:
    payload_type: str
    codec_name: str
    python_type: type[Any]


class CodecRegistry:
    def __init__(self):
        self._bindings_by_python_type: dict[type[Any], CodecBinding] = {}
        self._bindings_by_wire_type: dict[tuple[str, str], CodecBinding] = {}
        self._codecs: dict[str, Codec] = {}

    def register_codec(self, name: str, codec: Codec) -> None:
        self._codecs[name] = codec

    def register_type(self, payload_type: str, codec_name: str, python_type: type[Any]) -> None:
        binding = CodecBinding(payload_type=payload_type, codec_name=codec_name, python_type=python_type)
        self._bindings_by_python_type[python_type] = binding
        self._bindings_by_wire_type[(payload_type, codec_name)] = binding

    def encode_payload(self, value: Any) -> tuple[str, str, Any]:
        candidates = [python_type for python_type in self._bindings_by_python_type if isinstance(value, python_type)]

        if candidates:
            best = max(candidates, key=lambda t: sum(issubclass(t, other) for other in candidates))
            binding = self._bindings_by_python_type[best]
            codec = self._codecs[binding.codec_name]
            return binding.payload_type, binding.codec_name, codec.encode(value)

        codec_name = JsonCodec.name
        if codec_name not in self._codecs:
            self.register_codec(codec_name, JsonCodec())
        return "json", codec_name, self._codecs[codec_name].encode(value)

    def decode_payload(self, payload_type: str, codec_name: str, payload: Any) -> Any:
        codec = self._codecs[codec_name]
        return codec.decode(payload)


class TypedPayloadSerializer:
    """Recursively encode/decode typed values inside JSON-safe structures."""

    def __init__(self, registry: CodecRegistry, schema_version: int = 1):
        self.registry = registry
        self.schema_version = schema_version

    def encode_value(self, value: Any) -> Any:
        payload_type, payload_codec, encoded_payload = self.registry.encode_payload(value)

        if payload_type != "json" or payload_codec != JsonCodec.name:
            return {
                "__typed_payload__": True,
                "schema_version": self.schema_version,
                "payload_type": payload_type,
                "payload_codec": payload_codec,
                "payload": self._encode_container(encoded_payload),
            }

        return self._encode_container(encoded_payload)

    def decode_value(self, value: Any) -> Any:
        if isinstance(value, dict) and value.get("__typed_payload__") is True:
            payload = self._decode_container(value.get("payload"))
            return self.registry.decode_payload(
                value["payload_type"],
                value["payload_codec"],
                payload,
            )

        return self._decode_container(value)

    def _encode_container(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self.encode_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.encode_value(item) for item in value]
        if isinstance(value, tuple):
            return [self.encode_value(item) for item in value]
        return value

    def _decode_container(self, value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("__typed_payload__") is True:
                return self.decode_value(value)
            return {k: self.decode_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.decode_value(item) for item in value]
        return value
