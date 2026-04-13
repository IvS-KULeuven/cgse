import datetime
import os
import random
import time

import pandas as pd
from influxdb_client_3 import Point
from influxdb_client_3.write_client.domain.write_precision import WritePrecision
from rich import print

from egse.metrics import get_metrics_repo
from egse.plugins.metrics.influxdb import InfluxDBRepository
from egse.system import Timer
from egse.system import format_datetime
from egse.system import str_to_datetime


def test_influxdb_access():
    token = os.environ.get("INFLUXDB3_AUTH_TOKEN")

    influxdb = get_metrics_repo("influxdb", {"host": "http://localhost:8181", "database": "ARIEL", "token": token})
    influxdb.connect()

    result = influxdb.query(
        "SELECT * FROM cm WHERE time >= now() - INTERVAL '2 days' ORDER BY TIME DESC LIMIT 20", mode="pandas"
    )
    print(result)
    assert isinstance(result, pd.DataFrame)

    result = influxdb.get_values_last_hours("cm", "cm_setup_id", hours=24, mode="pandas")
    print(f"Values from 'cm_setup_id': \n{result}")

    result = influxdb.get_values_in_range("cm", "cm_site_id", "2025-06-26T08:10:00Z", "2025-06-26T08:15:00Z", mode="")
    print(f"Values from 'cm_site_id': \n{result}")

    result = influxdb.get_table_names()
    print(f"Tables in ARIEL: {result}")

    result = influxdb.get_column_names("cm")
    print(f"Columns in cm: {result}")

    result = influxdb.get_column_names("storagecontrolserver")
    print(f"Columns in storagecontrolserver: {result}")

    result = influxdb.get_column_names("unit_test")
    print(f"Columns in unit_test: {result}")

    influxdb.close()


def test_influxdb_write():
    token = os.environ.get("INFLUXDB3_AUTH_TOKEN")

    influxdb = get_metrics_repo("influxdb", {"host": "http://localhost:8181", "database": "ARIEL", "token": token})

    print()

    with influxdb:
        points = []
        measurements = ["unit_test", "ariel", "localhost", "random"]
        for count in range(500):
            points.append(
                Point.measurement(random.choice(measurements))
                .tag("site_id", "KUL")
                .tag("origin", "UNITTEST")
                .field("count", count)
                .field("random", random.randint(0, 100))
                .time(datetime.datetime.now(tz=datetime.timezone.utc))
            )
            # with Timer("influxdb.write", precision=3):
            #     influxdb.write(points[count])
            # print('.', end="", flush=True)

        print()
        with Timer("influxdb.writes", precision=3):
            influxdb.write(points)

        names = influxdb.get_table_names()
        print(f"{names = }")
        assert "unit_test" in names

        names = influxdb.get_column_names("unit_test")
        assert "count" in names

        result = influxdb.get_values_last_hours("unit_test", "count", hours=1, mode="pandas")
        print(f"Values from 'count': {result}")

        result = influxdb.query("SELECT * FROM unit_test ORDER BY TIME DESC LIMIT 20", mode="pandas")
        print(result)


def test_speed():
    import time

    class DiagnosticInfluxDBRepository(InfluxDBRepository):
        def write_points(self, points):
            start_time = time.time()

            try:
                super().write(points)

            except Exception as exc:
                print(f"Write error: {exc}")
                raise

            finally:
                duration = time.time() - start_time
                print(f"Wrote {len(points)} points in {duration:.3f}s")

                if duration > 1.0:  # Warn if > 1000ms
                    print(f"⚠️  Slow write detected: {duration:.3f}s for {len(points)} points")

    token = os.environ.get("INFLUXDB3_AUTH_TOKEN")
    assert token is not None, "Please set the INFLUXDB3_AUTH_TOKEN environment variable to run this test."
    influxdb = DiagnosticInfluxDBRepository(host="http://localhost:8181", database="ARIEL", token=token)
    influxdb.connect()

    points = []
    for count in range(10_000):
        points.append(
            {
                "measurement": "unit_test",
                "tags": {"site_id": "KUL", "origin": "UNITTEST"},
                "fields": {
                    "count": count,
                    "random": random.randint(0, 100),
                },
                "time": str_to_datetime(format_datetime()),
            }
        )

    influxdb.write_points(points)

    influxdb.close()


def test_connection_speed():
    import requests

    start = time.time()
    response = requests.get("http://localhost:8181/health")
    duration = time.time() - start

    print(f"Health check took {duration:.3f}s")
    if duration > 0.1:
        print("⚠️  Network latency detected")


# ============================================================================
# Unit Tests for write() and _to_line_protocol() methods with mocking
# ============================================================================


class TestToLineProtocol:
    """Unit tests for InfluxDBRepository._to_line_protocol() static method."""

    def test_basic_measurement_with_fields(self):
        """Test basic line protocol generation with measurement and fields."""
        payload = {
            "measurement": "cpu",
            "fields": {"value": 50.5, "usage": 75},
            "time": 1609459200.0,  # 2021-01-01 00:00:00 UTC
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        # Fields are not sorted, so check they're both present in the output
        assert result.startswith("cpu ")
        assert "value=50.5" in result
        assert "usage=75i" in result
        assert "1609459200000000000" in result

    def test_with_tags_and_fields(self):
        """Test line protocol with both tags and fields."""
        payload = {
            "measurement": "temperature",
            "tags": {"location": "room1", "sensor_id": "tmp001"},
            "fields": {"celsius": 22.5},
            "time": 1609459200.0,
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result == "temperature,location=room1,sensor_id=tmp001 celsius=22.5 1609459200000000000"

    def test_escaping_special_characters_in_tags(self):
        """Test that special characters are properly escaped in tags."""
        payload = {
            "measurement": "event space",  # space in measurement
            "tags": {
                "label": "tag=value",  # equals sign in tag value
                "path": "a,b,c",  # comma in tag value
            },
            "fields": {"count": 1},
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        # Should escape spaces and special chars in measurement and tag values
        assert "event\\ space" in result
        assert "tag\\=value" in result
        assert "a\\,b\\,c" in result

    def test_escaping_special_characters_in_fields(self):
        """Test that special characters are properly handled in field values."""
        payload = {
            "measurement": "message",
            "fields": {
                "text": 'hello "world"',
                "path": "C:\\Users\\test",
            },
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        # Strings should have escaped quotes and backslashes
        assert 'text="hello \\"world\\""' in result
        assert 'path="C:\\\\Users\\\\test"' in result

    def test_various_field_types(self):
        """Test different field value types (bool, int, float, string)."""
        payload = {
            "measurement": "metrics",
            "fields": {
                "is_active": True,
                "is_disabled": False,
                "count": 42,
                "temperature": 37.5,
                "message": "test message",
            },
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        assert "is_active=true" in result
        assert "is_disabled=false" in result
        assert "count=42i" in result
        assert "temperature=37.5" in result
        assert 'message="test message"' in result

    def test_none_values_filtered(self):
        """Test that None values in fields are skipped."""
        payload = {
            "measurement": "test",
            "fields": {
                "value1": 10,
                "value2": None,
                "value3": 20,
            },
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        assert "value1=10i" in result
        assert "value3=20i" in result
        assert "value2" not in result

    def test_none_tag_values_filtered(self):
        """Test that None values in tags are skipped."""
        payload = {
            "measurement": "test",
            "tags": {
                "tag1": "val1",
                "tag2": None,
                "tag3": "val3",
            },
            "fields": {"value": 1},
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        assert "tag1=val1" in result
        assert "tag3=val3" in result
        assert "tag2" not in result

    def test_nan_and_inf_values_filtered(self):
        """Test that NaN and inf values are filtered out."""
        payload = {
            "measurement": "test",
            "fields": {
                "normal": 3.14,
                "nan_value": float("nan"),
                "inf_value": float("inf"),
                "neg_inf": float("-inf"),
            },
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        assert "normal=3.14" in result
        assert "nan_value" not in result
        assert "inf_value" not in result
        assert "neg_inf" not in result

    def test_missing_measurement_returns_none(self):
        """Test that payload without measurement returns None."""
        payload = {"fields": {"value": 1}}
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is None

    def test_empty_measurement_returns_none(self):
        """Test that empty measurement string returns None."""
        payload = {"measurement": "", "fields": {"value": 1}}
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is None

    def test_no_fields_returns_none(self):
        """Test that payload without fields returns None."""
        payload = {"measurement": "test", "fields": {}}
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is None

    def test_no_valid_fields_returns_none(self):
        """Test that payload with only None/invalid fields returns None."""
        payload = {
            "measurement": "test",
            "fields": {"nan": float("nan"), "inf": float("inf")},
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is None

    def test_timestamp_as_unix_float(self):
        """Test timestamp conversion from Unix float (seconds) to nanoseconds."""
        payload = {
            "measurement": "test",
            "fields": {"value": 1},
            "time": 1609459200.123456,
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        # Should convert to nanoseconds
        assert result is not None
        assert "1609459200123456000" in result

    def test_timestamp_as_iso_string(self):
        """Test timestamp conversion from ISO string."""
        payload = {
            "measurement": "test",
            "fields": {"value": 1},
            "time": "2021-01-01T00:00:00+00:00",
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        assert "1609459200000000000" in result

    def test_timestamp_as_iso_string_with_z(self):
        """Test timestamp conversion from ISO string with Z notation."""
        payload = {
            "measurement": "test",
            "fields": {"value": 1},
            "time": "2021-01-01T00:00:00Z",
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        assert result is not None
        assert "1609459200000000000" in result

    def test_timestamp_invalid_raises_no_error(self):
        """Test that invalid timestamp strings are silently ignored."""
        payload = {
            "measurement": "test",
            "fields": {"value": 1},
            "time": "invalid-timestamp",
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        # Should return line protocol without timestamp
        assert result is not None
        assert "test value=1i" in result

    def test_tags_sorted_in_output(self):
        """Test that tags are sorted alphabetically in the output."""
        payload = {
            "measurement": "test",
            "tags": {"zebra": "z", "apple": "a", "mango": "m"},
            "fields": {"value": 1},
        }
        result = InfluxDBRepository._to_line_protocol(payload)
        # Tags should be in alphabetical order
        assert result is not None
        assert "apple=a,mango=m,zebra=z" in result


class TestWrite:
    """Unit tests for InfluxDBRepository.write() method with mocked client."""

    def test_write_single_point_object(self):
        """Test writing a single Point object."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        point = Point("measurement").field("value", 42)
        repo.write(point)

        repo.client.write.assert_called_once()
        call_args = repo.client.write.call_args
        assert len(call_args.kwargs["record"]) == 1
        assert call_args.kwargs["write_precision"] == repo.metrics_time_precision

    def test_write_single_dict_converts_to_line_protocol(self):
        """Test writing a single dict that is converted to line protocol."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        payload = {
            "measurement": "cpu",
            "fields": {"value": 50},
        }
        repo.write(payload)

        repo.client.write.assert_called_once()
        call_args = repo.client.write.call_args
        records = call_args.kwargs["record"]
        assert len(records) == 1
        assert "cpu" in records[0]
        assert "value=50i" in records[0]

    def test_write_invalid_dict_not_written(self):
        """Test that invalid dicts (no measurement/fields) are not written."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        payload = {"fields": {}}  # No measurement, invalid
        repo.write(payload)

        repo.client.write.assert_not_called()

    def test_write_list_of_dicts(self):
        """Test writing a list of dicts."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        dicts = [
            {"measurement": "cpu", "fields": {"value": 50}},
            {"measurement": "mem", "fields": {"value": 75}},
        ]
        repo.write(dicts)

        repo.client.write.assert_called_once()
        call_args = repo.client.write.call_args
        records = call_args.kwargs["record"]
        assert len(records) == 2
        assert all(isinstance(r, str) for r in records)

    def test_write_mixed_list_points_and_dicts(self):
        """Test writing a list with both Point objects and dicts."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        items = [
            {"measurement": "cpu", "fields": {"value": 50}},
            Point("mem").field("value", 75),
        ]
        repo.write(items)

        repo.client.write.assert_called_once()
        call_args = repo.client.write.call_args
        records = call_args.kwargs["record"]
        assert len(records) == 2
        # First should be line protocol string, second should be Point
        assert isinstance(records[0], str)
        assert isinstance(records[1], Point)

    def test_write_filters_invalid_dicts_from_list(self):
        """Test that invalid dicts are filtered out from a list."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        items = [
            {"measurement": "valid", "fields": {"value": 50}},
            {"fields": {}},  # Invalid (no measurement)
            {"measurement": "valid2", "fields": {"data": 100}},
        ]
        repo.write(items)

        repo.client.write.assert_called_once()
        call_args = repo.client.write.call_args
        records = call_args.kwargs["record"]
        # Should only write 2 valid records
        assert len(records) == 2

    def test_write_preserves_write_precision(self):
        """Test that write precision is passed to client.write()."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.metrics_time_precision = WritePrecision.NS
        repo.client = MagicMock()

        payload = {"measurement": "test", "fields": {"value": 1}}
        repo.write(payload)

        call_args = repo.client.write.call_args
        assert call_args.kwargs["write_precision"] == WritePrecision.NS

    def test_write_empty_list_no_client_call(self):
        """Test that writing an empty list doesn't call client.write()."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        repo.write([])

        repo.client.write.assert_not_called()

    def test_write_list_all_invalid_no_client_call(self):
        """Test that a list of all invalid items doesn't call client.write()."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        items = [
            {"fields": {}},  # Invalid
            {"measurement": ""},  # Invalid
        ]
        repo.write(items)

        repo.client.write.assert_not_called()

    def test_write_dict_with_tags_and_timestamp(self):
        """Test writing dict with tags and timestamp is converted correctly."""
        from unittest.mock import MagicMock

        repo = InfluxDBRepository(host="http://localhost", database="test", token="token")
        repo.client = MagicMock()

        payload = {
            "measurement": "sensor",
            "tags": {"location": "room1"},
            "fields": {"temp": 22.5},
            "time": 1609459200.0,
        }
        repo.write(payload)

        call_args = repo.client.write.call_args
        records = call_args.kwargs["record"]
        assert len(records) == 1
        lp = records[0]
        assert "sensor,location=room1" in lp
        assert "temp=22.5" in lp
        assert "1609459200000000000" in lp
