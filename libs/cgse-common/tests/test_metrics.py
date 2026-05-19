import datetime
import os
from types import SimpleNamespace

import pytest

from egse.metrics import DataPoint
from egse.metrics import MeasurementColumn
from egse.metrics import MeasurementSchema
from egse.metrics import clear_measurement_schemas
from egse.metrics import get_measurement_schema
from egse.metrics import get_metrics_repo
from egse.metrics import load_measurement_schemas_from_modules
from egse.metrics import register_measurement_schema


def test_datapoint_as_dict_serializes_datetime_timestamp():
    timestamp = datetime.datetime(2026, 3, 25, 15, 12, 52, tzinfo=datetime.timezone.utc)

    point = DataPoint.measurement("camera_tm").field("temperature", 23.4).time(timestamp)

    payload = point.as_dict()

    assert payload["measurement"] == "camera_tm"
    assert payload["fields"]["temperature"] == 23.4
    assert payload["time"] == timestamp.timestamp()


def test_get_metrics_repo():
    token = os.environ.get("INFLUXDB3_AUTH_TOKEN")

    influxdb = get_metrics_repo("influxdb", {"host": "http://localhost:8181", "database": "ARIEL", "token": token})
    influxdb.connect()

    # Don't use a too large time interval here, or you will get an error like:
    # 'External error: Query would exceed file limit of 432 parquet files'
    result = influxdb.query(
        "SELECT * FROM cm WHERE time >= now() - INTERVAL '2 days' ORDER BY TIME DESC LIMIT 20", mode="pandas"
    )
    print(result)

    # result = influxdb.query("SHOW TABLES;")
    # result = influxdb.query("SHOW COLUMNS IN cm;", mode="pandas")
    # print(f"Columns in cm: {result}")

    result = influxdb.get_table_names()
    print(f"Tables in ARIEL: {result}")

    result = influxdb.get_column_names("cm")
    print(f"Columns in cm: {result}")

    influxdb.close()


def test_measurement_schema_registry_round_trip():
    clear_measurement_schemas()
    schema = MeasurementSchema(
        name="synthetic_load",
        tags=(MeasurementColumn("device_id", "symbol"), MeasurementColumn("profile", "symbol")),
        fields=(MeasurementColumn("temperature", "double"), MeasurementColumn("sample_idx", "long")),
    )

    register_measurement_schema(schema)

    stored = get_measurement_schema("synthetic_load")
    assert stored == schema
    assert stored is not None
    assert stored.get_tag("device_id") == MeasurementColumn("device_id", "symbol")
    assert stored.get_field("temperature") == MeasurementColumn("temperature", "double")

    clear_measurement_schemas()
    assert get_measurement_schema("synthetic_load") is None


def test_load_measurement_schemas_from_modules(monkeypatch):
    clear_measurement_schemas()

    def register_fn():
        register_measurement_schema(
            MeasurementSchema(
                name="camera_tm",
                fields=(MeasurementColumn("temperature", "double"),),
            )
        )

    fake_module = SimpleNamespace(register_measurement_schemas=register_fn)

    monkeypatch.setattr("egse.metrics.importlib.import_module", lambda name: fake_module)

    loaded = load_measurement_schemas_from_modules(["my.schemas"])
    assert loaded == ["my.schemas"]
    assert get_measurement_schema("camera_tm") is not None


def test_load_measurement_schemas_from_modules_requires_callable(monkeypatch):
    fake_module = SimpleNamespace(not_register_measurement_schemas=lambda: None)
    monkeypatch.setattr("egse.metrics.importlib.import_module", lambda name: fake_module)

    with pytest.raises(AttributeError, match="does not expose callable"):
        load_measurement_schemas_from_modules(["my.schemas"])
