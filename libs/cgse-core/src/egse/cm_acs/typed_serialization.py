"""Typed payload serializer configuration for async configuration manager."""

from __future__ import annotations

from functools import lru_cache

from egse.setup import Setup

from egse.serialization import CodecRegistry
from egse.serialization import JsonCodec
from egse.serialization import SetupCodec
from egse.serialization import TypedPayloadSerializer


@lru_cache(maxsize=1)
def get_typed_payload_serializer() -> TypedPayloadSerializer:
    registry = CodecRegistry()
    registry.register_codec(JsonCodec.name, JsonCodec())
    registry.register_codec("setup_codec", SetupCodec())
    registry.register_type("setup", "setup_codec", Setup)

    return TypedPayloadSerializer(registry=registry, schema_version=1)
