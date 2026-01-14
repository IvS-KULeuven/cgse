"""
Part of the housekeeping acquired during the Ariel TA test campaign at CSL will be stored directly into the MySQL
facility database.  This module enables watching specific tables in that database for new entries.  The goal is to
store those into the dedicated CSV files for the TA-EGSE framework.
"""

import threading
from datetime import datetime

from egse.confman.confman_cs import load_setup
from egse.hk import read_conversion_dict, convert_hk_names
from egse.log import egse_logger
from egse.system import str_to_datetime, format_datetime
from egse.metrics import get_metrics_repo
from egse.settings import Settings, get_site_id
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import WriteRowsEvent
from urllib3.exceptions import NewConnectionError
import os

from egse.storage import StorageProxy

LOGGER = egse_logger
SITE_ID = get_site_id()
FACILITY_DB_SETTINGS = Settings.load("Facility DB")

ID_COLUMN_NAME = "measure_id"
TIMESTAMP_COLUMN_NAME = "measure_timestamp"
VALUE_COLUMN_NAME = "measure_value"


class DatabaseTableWatcher:
    def __init__(self, table_name: str, origin: str, server_id: int):
        """Initialisation of a watcher for a specific table in the facility database.

        The watcher is a daemon thread the watches the specified table in the facility database for new entries.  If
        a new entry is encountered, it will be sent to the Storage Manager, which will store it in the HK file for the
        given storage mnemonic.

        Args:
            table_name (str): Name of the table in the facility database.
            origin (str): Storage mnemonic for the data in the TA-EGSE framework.
            server_id (int): Unique identifier for the MySQL binlog stream reader.
        """

        self.table_name = table_name
        self.origin = origin
        self.server_id = server_id

        # noinspection PyBroadException
        try:
            self.hk_conversion_dict = read_conversion_dict(self.origin, use_site=False, setup=load_setup())
        except:
            self.hk_conversion_dict = None

        # Make a thread and let it start watching the specified table in the facility database

        self.watch_thread = threading.Thread(target=self.watch_db_table)
        self.watch_thread.daemon = True
        self.keep_watching = True

        # Metrics client

        token = os.getenv("INFLUXDB3_AUTH_TOKEN")
        project = os.getenv("PROJECT")

        if project and token:
            self.metrics_client = get_metrics_repo(
                "influxdb", {"host": "http://localhost:8181", "database": project, "token": token}
            )
            self.metrics_client.connect()
        else:
            self.metrics_client = None
            LOGGER.warning(
                "INFLUXDB3_AUTH_TOKEN and/or PROJECT environment variable is not set.  Metrics will not be propagated "
                "to InfluxDB."
            )

    def start_watching_db_table(self):
        """Starts the thread that checks for new entries in the specified table in the facility database."""

        self.keep_watching = True
        self.watch_thread.start()

    def stop_watching_db_table(self):
        """Stops the thread that checks for new entries in the specified table in the facility database."""

        self.keep_watching = False
        self.watch_thread.join()

    def watch_db_table(self):
        """Lets the thread watch for new entries in the specified table in the facility database.

        If a new entry is encountered, it will be sent to the Storage Manager, which will store it in the HK file for
        the specified storage mnemonic.
        """

        # Connect to the (MySQL) facility database -> Start watching the specified table

        mysql_settings = {
            "host": FACILITY_DB_SETTINGS.HOST,
            "port": FACILITY_DB_SETTINGS.PORT,
            "user": FACILITY_DB_SETTINGS.USER,
            "passwd": FACILITY_DB_SETTINGS.PASSWORD,
        }

        stream: BinLogStreamReader = BinLogStreamReader(
            connection_settings=mysql_settings,
            server_id=self.server_id,  # Unique identifier per Python client watching the MySQL facility database
            blocking=True,
            only_events=[WriteRowsEvent],  # Watch for new row entries
            only_tables=[self.table_name],  # Watch for changes in the specified table
        )

        while self.keep_watching:
            for bin_log_event in stream:
                for row in bin_log_event.rows:
                    values = row["values"]  # Dictionary with the column names (from the facility database) as keys
                    hk = self.translate_parameter_names(values)  # Convert to TA-EGSE-consistent names
                    self.store_housekeeping_information(hk)
                    self.propagate_metrics(hk)

        stream.close()

    def translate_parameter_names(self, hk: dict):
        """Converts the parameter names from the facility database to TA-EGSE-consistent names.

        Args:
            hk (dict): Dictionary with the column names (from the facility database) as keys.

        Returns:
            Dictionary with the TA-EGSE-consistent names as keys.
        """

        # Timestamp

        # noinspection PyUnresolvedReferences
        hk["timestamp"] = format_datetime(
            datetime.datetime.fromtimestamp(hk[TIMESTAMP_COLUMN_NAME], datetime.UTC)
        )  # Unix time -> datetime [UTC]
        del hk[TIMESTAMP_COLUMN_NAME]

        # Delete identifier of the entry

        del hk[ID_COLUMN_NAME]

        # Parameter value

        hk[self.table_name] = hk[VALUE_COLUMN_NAME]
        del hk[VALUE_COLUMN_NAME]

        if self.hk_conversion_dict:
            return convert_hk_names(hk, self.hk_conversion_dict)
        else:
            return hk

    def store_housekeeping_information(self, hk: dict):
        """Sends the given housekeeping information to the Storage Manager.

        The housekeeping is passed as a dictionary, with the parameter names as keys.  There's also an entry for the
        timestamp, which represents the date/time at which the value was received.

        Args:
            hk (dict): Housekeeping that was extracted from the facility database, after converting the parameter names
                       to TA-EGSE-consistent names.
        """

        try:
            with StorageProxy() as storage:
                response = storage.save({"origin": self.origin, "data": hk})
                if not response.successful:
                    LOGGER.warning(
                        f"Couldn't save facility data to the Storage manager for {self.origin}, cause: {response}"
                    )
        except ConnectionError as exc:
            LOGGER.warning(
                f"Couldn't connect to the Storage Manager to store facility housekeeping for {self.origin}: {exc}"
            )
            raise

    def propagate_metrics(self, hk: dict):
        """Propagates the given housekeeping information to the metrics database.

        The housekeeping is passed as a dictionary, with the parameter names as keys.  There's also an entry for the
        timestamp, which represents the date/time at which the value was received.  In case only the timestamp is
        present in the dictionary, nothing will be written to the metrics database.

        Args:
            hk (dict): Housekeeping that was extracted from the facility database, after converting the parameter names
                       to TA-EGSE-consistent names.
        """

        if not [x for x in hk if x != "timestamp"]:
            LOGGER.debug(f"no metrics defined for {self.origin}")
            return

        try:
            if self.metrics_client:
                point = {
                    "measurement": self.origin.lower(),
                    "tags": {"site_id": SITE_ID, "origin": self.origin},
                    "fields": {hk_name.lower(): hk[hk_name] for hk_name in hk if hk_name != "timestamp"},
                    "time": str_to_datetime(hk["timestamp"]),
                }
                self.metrics_client.write(point)
            else:
                LOGGER.warning(
                    f"Could not write {self.origin} metrics to the time series database (self.metrics_client is None)."
                )
        except NewConnectionError:
            LOGGER.warning(
                f"No connection to the time series database could be established to propagate {self.origin} metrics.  "
                f"Check whether this service is (still) running."
            )
