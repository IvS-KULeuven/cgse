"""Built-in measurement schema definitions for Metrics Hub.

This module ships typed ``MeasurementSchema`` declarations for measurements
that are produced by built-in CGSE tools (load-generator scripts, benchmarks,
etc.).  Project code should define its own schema modules following the same
pattern — see ``register_measurement_schemas()`` below as the template.

Usage
-----
Point ``CGSE_METRICS_SCHEMA_MODULES`` at this module when starting the Metrics
Hub so that the declared measurements are written to per-measurement typed
tables instead of the generic fallback table::

    export CGSE_METRICS_SCHEMA_MODULES=egse.metricshub.schemas
    mh_cs start

Multiple modules are separated by commas::

    export CGSE_METRICS_SCHEMA_MODULES=egse.metricshub.schemas,myproject.metrics

Each module must expose a callable named ``register_measurement_schemas``
(configurable via ``CGSE_METRICS_SCHEMA_REGISTER_FUNCTION``) that calls
``register_measurement_schema`` for every measurement it owns.

Measurements: ``synthetic_load`` and ``mh_load_schema``
--------------------------------------------------------
Produced by ``script_send_metricshub_load.py`` — the high-rate load generator
used for Metrics Hub stress-testing and backend throughput benchmarking.

Schema::

    tags:
        device_id  symbol    loadgen_000 … loadgen_NNN
        channel    symbol    ch_000 … ch_NNN
        profile    symbol    e.g. "warm-cool-warm"

    fields:
        temperature  double   simulated temperature in °C
        sample_idx   long     monotonic sample counter
        elapsed_s    double   seconds since script start
"""

from egse.metrics import MeasurementColumn
from egse.metrics import MeasurementSchema
from egse.metrics import register_measurement_schema

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

#: Typed schema for the synthetic load-generator measurement.
SYNTHETIC_LOAD_SCHEMA = MeasurementSchema(
    name="synthetic_load",
    tags=(
        MeasurementColumn(name="device_id", data_type="symbol"),
        MeasurementColumn(name="channel", data_type="symbol"),
        MeasurementColumn(name="profile", data_type="symbol"),
    ),
    fields=(
        MeasurementColumn(name="temperature", data_type="double"),
        MeasurementColumn(name="sample_idx", data_type="long"),
        MeasurementColumn(name="elapsed_s", data_type="double"),
    ),
)

#: Alias schema for load-test runs using the historical measurement name.
MH_LOAD_SCHEMA = MeasurementSchema(
    name="mh_load_schema",
    tags=SYNTHETIC_LOAD_SCHEMA.tags,
    fields=SYNTHETIC_LOAD_SCHEMA.fields,
)

#: Typed schema for the temperature-control-server measurement (async_temp.py).
TEMP_CONTROL_SERVER_SCHEMA = MeasurementSchema(
    name="temp_control_server",
    tags=(
        MeasurementColumn(name="site_id", data_type="symbol"),
        MeasurementColumn(name="origin", data_type="symbol"),
        MeasurementColumn(name="sensor", data_type="symbol"),
        MeasurementColumn(name="source", data_type="symbol"),
    ),
    fields=(MeasurementColumn(name="temperature_c", data_type="double"),),
)

#: Names supported by built-in load schemas.
LOAD_SCHEMA_NAMES = frozenset({SYNTHETIC_LOAD_SCHEMA.name, MH_LOAD_SCHEMA.name})


# ---------------------------------------------------------------------------
# Registration hook — called by load_measurement_schemas_from_modules()
# ---------------------------------------------------------------------------


def register_measurement_schemas() -> None:
    """Register all built-in measurement schemas with the global registry.

    This function is the standard hook called by the Metrics Hub startup loader
    (``_register_measurement_schemas_from_env``).  Add a
    ``register_measurement_schema(...)`` call here for every new built-in
    measurement schema this module owns.
    """
    register_measurement_schema(SYNTHETIC_LOAD_SCHEMA)
    register_measurement_schema(MH_LOAD_SCHEMA)
    register_measurement_schema(TEMP_CONTROL_SERVER_SCHEMA)
