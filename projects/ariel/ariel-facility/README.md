# Extraction of HK from the MySQL Facility Database

During the Ariel TA test campaign at CSL, facility (and potentially other) housekeeping data will be stored in the MySQL 
facility database.  To store (housekeeping) data in a consistent way across devices/processes and to enable quick-look 
analysis (e.g. via Grafana dashboards), we want to extract the data from the MySQL facility database and ingest it 
into our TA-EGSE framework.

---

## Database Structure

The structure of the MySQL facility database is as follows:

- Each sensor has its own table with recorded values (one measure every minute).
- Each table has the following column names:
  - `measure_id`: Identifiers for the entries in the table (basically the row number),
  - `measure_timestamp`: Timestamp of the measurements [Unix time],
  - `measure_value`: Recorded values (already converted/calibrated).

---

## Local Settings

The following entries have to be included in the (local) settings file:

```yaml
Facility HK:
    TABLES:
        
Facility DB:
    USER:
    PASSWORD:
```

- In the "TABLES" block under "Facility HK", you have to link the table names (as in the facility database) to the 
storage mnemonic (as in the TA-EGSE framework, to pass to the Storage Manager) and the server identifier.  This can be 
done by adding entries to the "TABLES" block, in the following format:

    ```
    <table name (in facility database)>:  (storage mnemonic, server identifier)
    ```

- In the "Facility DB" block, the credentials to connect to the MySQL facility database have to be specified via "USER" 
and "PASSWORD".

---

## Functionality

The `FacilityHousekeepingExporter` process is responsible for:
- Extracting housekeeping data from the MySQL facility database,
- Storing the extracted housekeeping in dedicated, TA-EGSE-consistent CSV files (via the Storage Manager),
- Ingesting the extracted housekeeping in the InfluxDB metrics database.

For each of the selected tables in the facility database, a dedicated thread will check for new entries in that table. When
a new entry appears in such a table, the corresponding thread will receive the new data as a `dict` and take the following action:
- Convert the timestamp to the format that we use throughout the TA-EGSE framework (YYYY-mm-ddTHH:MM:SS.μs+0000).
- Re-name the key for the timestamp in the dictionary to "timestamp".
- Re-name the key for the recorded value to the table name.
- If required by the telemetry, further re-naming of the keys in the dictionary will be performed.
- Send the new housekeeping value and corresponding timestamp to the Storage Manager.  The latter will store it in a 
  dedicated CSV file.
- Send the new housekeeping value and corresponding timestamp to the InfluxDB metrics database.

---

## Enable Binary Logging

To make this all work, binary logging should be enabled on the MySQL server.  This can be done by adding the following 
information in the `my.cnf` file:

```
[mysqld]
log-bin=mysql-bin
server-id=<server identifier>
binlog_format=ROW
```

You would have to add an entry for each of the server identifiers listed in the (local) settings file (see section above).

To find this file, check the `MYSQL_HOME` environment variable.

When you have added all required server identifiers, the MySQL server should be re-started.  Also make sure that your 
user had `REPLICATION SLAVE` or `REPLICATION CLIENT` privileges.  This can be configured as follows:

```mysql
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'your_user'@'%';
FLUSH PRIVILEGES;
```