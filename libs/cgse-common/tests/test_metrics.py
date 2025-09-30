import os

from egse.metrics import get_metrics_repo


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
