"""
Part of the housekeeping acquired during the Ariel TA test campaign at CSL will be stored directly into the MySQL
facility database.  This module enables watching specific tables in that database for new entries.  The goal is to
store those into the dedicated CSV files for the TA-EGSE framework.
"""

import threading
from egse.log import egse_logger
from egse.settings import Settings
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import WriteRowsEvent

from egse.storage import StorageProxy

LOGGER = egse_logger
FACILITY_DB_SETTINGS = Settings.load("Facility DB")


class DatabaseTableWatcher:
    def __init__(self, origin: str, table_name: str, server_id: int):
        """Initialisation of a watcher for a specific table in the facility database.

        The watcher is a daemon thread the watches the specified table in the facility database for new entries.  If
        a new entry is encountered, it will be sent to the Storage Manager, which will store it in the HK file for the
        given storage mnemonic.

        Args:
            table_name (str): Name of the table in the facility database.
            origin (str): Storage mnemonic for the data in the TA-EGSE framework.
            server_id (int): Unique identifier for the MySQL binlog stream reader.
        """

        self.origin = origin
        self.table_name = table_name
        self.server_id = server_id

        # Make a thread and let it start watching the specified table in the facility database

        self.watch_thread = threading.Thread(target=self.watch_db_table)
        self.watch_thread.daemon = True
        self.keep_watching = True

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
                    values = row["values"]
                    self.send_to_storage(values)

        stream.close()

    def send_to_storage(self, data: dict):
        """Sends the given data to the Storage Manager.

        The Storage Manager will store the given data in the HK file for the specified storage mnemonic.
        """

        try:
            with StorageProxy() as storage:
                # TODO Should we check how the timestamp is stored in the DB (name, format, etc.)?
                response = storage.save({"origin": self.origin, "data": data})
                if not response.successful:
                    LOGGER.warning(
                        f"Couldn't save facility data to the Storage manager for {self.origin}, cause: {response}"
                    )
        except ConnectionError as exc:
            LOGGER.warning(
                f"Couldn't connect to the Storage Manager to store facility housekeeping for {self.origin}: {exc}"
            )
            raise
