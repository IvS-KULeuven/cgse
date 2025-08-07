import datetime
import os
import random
import time

import pandas as pd
from influxdb_client_3 import Point
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

    result = influxdb.query("SELECT * FROM cm ORDER BY TIME DESC LIMIT 20", mode="pandas")
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

                if duration > 0.1:  # Warn if > 100ms
                    print(f"⚠️  Slow write detected: {duration:.3f}s for {len(points)} points")

    token = os.environ.get("INFLUXDB3_AUTH_TOKEN")
    influxdb = DiagnosticInfluxDBRepository(host="http://localhost:8181", database="ARIEL", token=token)
    influxdb.connect()

    points = []
    for count in range(10):
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
