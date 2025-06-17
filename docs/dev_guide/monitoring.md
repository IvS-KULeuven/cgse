# Monitoring with InfluxDB and Grafana

The CGSE provides mechanisms to monitor metrics from different processes and devices.  These are 
collected by InfluxDB and are visualised by means of Grafana dashboards.

In this section, we explain how to install both InfluxDB and Grafana on the Server, how to set up and populate a database 
in InfluxDB, and how to visualise the metrics in Grafana dashboards.


---

## Installation

### InfluxDB3 Core

To install InfluxDB3 Core, execute this in a Terminal on the Server:

```
curl -s https://repos.influxdata.com/influxdata-archive_compat.key > influxdata-archive_compat.key

echo '393e8779c89ac8d958f81f942f9ad7fb82a25e133faddaf92e15b16e6ac9ce4c influxdata-archive_compat.key' | sha256sum -c && cat influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg > /dev/null
echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list

sudo apt-get update

sudo apt-get install influxdb3-core
```

For database management, you will need a token to interact with InfluxDB.  This can be generated as follows (in a 
Terminal on the Server):

```
influxdb3 create token --admin
```

This will print out a token, starting with `apiv3_`.  Export this value as environment variable `INFLUXDB3_AUTH_TOKEN`.


### Grafana

To install Grafana, execute this in a Terminal on the Server:

```
sudo apt-get install -y apt-transport-https software-properties-common wget

sudo mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null

echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list
sudo apt-get update

sudo apt-get install grafana

sudo /bin/systemctl daemon-reload
sudo /bin/systemctl enable grafana-server
```

---

## Database Structure

### Database Name

In the current implementation, the name of the database in which all CGSE metrics are stored, is taken 
from the `PROJECT` environment variable.  At a later stage, we could change this by means of a dedicated 
environment variable or by specifying it in the local settings file.

To inspect the names of the available databases, execute this in a Terminal on the Server:

```
influxdb3 show databases
```

The command to create a database manually (from a Terminal on the Server) is:

```
influxdb3 create database <database name>
```

### Table Names

For each of the processes, we have a dedicated table in the database, the name of which is the same as 
the storage mnemonic of the process.

To get an overview of the available tables, execute this in a Terminal on the Server:

```
influxdb3 query --database <database name> "SHOW TABLES"
```

### Content of the Tables

For each table, the column names are the names of the corresponding housekeeping/metrics parameters.  The name of the column with the timestamp is `TIME`. 

To get an overview of the columns for a given table in a given database, execute this in a Terminal on the Server:

```
influxdb3 query --database <database name> "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '<table name>'"
```

To get an overview of the data stored in a given table (sorted by ascending order of timestamp), execute this in a 
Terminal on the Server:

```
influxdb3 query --database <database name> "SELECT * FROM <table name> ORDER BY TIME"
```

---

## Propagating Metrics to InfluxDB via Python

To populate the metrics in InfluxDB, we use the Python package `influxdb3-python`. This has been added to the `pyproject.toml` 
file of the `cgse-common` module.

When implementing a new device, nothing has to be done specifically to propagate the metrics to InfluxDB.  This is 
automatically being taken care of in the `serve` method of the `ControlServer` class.  In the section where the 
housekeeping information is written to a dedicated CSV file, the `propagate_metrics` method of the `ControlServer` 
class is called and this takes care of everything.



[//]: # (### Establishing a Connection)

[//]: # ()
[//]: # (In the initialisation a the `CommandProtocol`, an `influxdb_client_3.InfluxDBClient3` is created &#40;and stored in )

[//]: # (`self.client`&#41;, which establishes a connection to InfluxDB.  This is also where the write precision for the )

[//]: # (timestamp is specified.  Note that - to establish this connection - both the `PROJECT` and `INFLUXDB3_AUTH_TOKEN` )

[//]: # (environment variables have to be set.  If this is not the case, `self.client` will be `None`. )

[//]: # ()
[//]: # (Note that when the InfluxDB process is &#40;re-&#41;started, the individual processes pick up on this automatically &#40;so you )

[//]: # (don't have to do anything extra for the metrics to start appearing in the database again&#41;.)

[//]: # ()
[//]: # (### Device Protocols)

[//]: # ()
[//]: # (In the implementing protocols, in the `get_housekeeping` method, we have to propagate the metrics to InfluxDB.  Usually )

[//]: # (we have an `hk` dictionary &#40;or something alike&#41; with the housekeeping information that will be stored in a dedicated CSV file.  This dictionary )

[//]: # (also contains the timestamp for all parameters.  This is the return value of the `get_housekeeping` method.)

[//]: # ()
[//]: # (To propagate these housekeeping parameters as metrics to InfluxDB, you have to construct a dictionary &#40;see further for the required content&#41;, )

[//]: # (say `metrics_dictionary`, which we will write to InfluxDB, as follows &#40;in the `get_housekeeping` method&#41;:)

[//]: # ()
[//]: # (``` python )

[//]: # (try:)

[//]: # (    if self.client:)

[//]: # (        metrics_dictionary = {...})

[//]: # (        point = Point.from_dict&#40;metrics_dictionary, write_precision=self.metrics_time_precision&#41;)

[//]: # (        self.client.write&#40;point&#41;)

[//]: # ( except NewConnectionError:)

[//]: # (    pass)

[//]: # (```)

[//]: # ()
[//]: # (This requires the following imports:)

[//]: # ()
[//]: # (``` python)

[//]: # (from influxdb_client_3 import Point)

[//]: # (from urllib3.exceptions import NewConnectionError)

[//]: # (```)

[//]: # ()
[//]: # (#### Metrics Dictionary )

[//]: # ()
[//]: # (The `metrics_dictionary` has the following structure:)

[//]: # ()
[//]: # (- `measurement`: Storage mnemonic of the process, which will be used as table name in the database;)

[//]: # (- `tags`: Dictionary with tags for the table in the database.  At this point, its function is not entirely clear yet. We are using the following tags:)

[//]: # (  - `site_id`: Site identifier, as taken from the settings/setup &#40;e.g. "KUL", "CSL",...&#41;;)

[//]: # (  - `origin`: Storage mnemonic of the process;)

[//]: # (- `fields`: Dictionary with metrics.  This is the same as the `hk` dictionary but without the timestamp;)

[//]: # (- `time`: Timestamp as taken from the `hk` dictionary.)

[//]: # ()
[//]: # (### Closing the Connection)

[//]: # ()
[//]: # (In the `quit` method of the device protocol, do not forget to close the connection to InfluxDB, by adding this line:)

[//]: # ()
[//]: # (``` python)

[//]: # (if self.client:)

[//]: # (    self.client.close&#40;&#41;)

[//]: # (```)

---

## Visualisation of the Metrics

The Metrics are visualised in Grafana dashboards, but before we can start building those, we have to instruct Grafana to 
interpret InfluxDB as its data source.

### Adding InfluxDB as Data Source

After the InfluxDB and Grafana processes have been started, you can access Grafana in your browser via http://localhost:3000. 

On the left-hand side, select (under "Connections") "Add new connection" and search for "Influx DB".  After clicking on 
the search result, a Settings tab will open, in which you have to enter the following information:

- `Name`: Arbitrary name for the data source (it's a good idea to make this reflect the database you are settings up, e.g. `influxdb3-ariel`);
- `Query language`: Select "SQL";
- `HTTP` > `URL`: `http://127.0.0.1:8181`;
- `Auth`: Only enable "Basic auth";
- `InfluxDB Details` > `Database`: Name of the database for which you want to create Grafana dashboards;
- `InfluxDB Details` > `Token`: InfluxDB token you have created earlier (see above; starting with `apiv3_`);
- `InfluxDB Details`: Enable "Insecure Connection".

After having configured all of this, press "Save & test".

### Creating Grafana Dashboards

Creating a Grafana dashboard can be done by clicking "Dashboards" on the left-hand side.  In the "Queries" tab of such a 
dashboard panel, you have to specify the following information:

- `Data source`: Name of the data source you have just created (selectable via a drop-down menu);
- `Table`: Name of the table for which you want to visualise metrics.  Remember that this is the same as the storage
           mnemonic of the process generating the metrics (selectable via a drop-down menu);
- `Data operations`: Besides the name of the metric (selectable via a drop-down menu), you also have to add `time` under 
                     `Data Operations`, to make sure Grafana recognises and is able to show the timestamp in its panels.
                     Have a look at the screenshot below for an example.
  ![grafana-queries.png](../images/grafana-queries.png)
---

## Open Questions

- How can we specify the data retention period?
- Is it ok to use the `PROJECT` environment variable as name of the database or should this be configurable (e.g. via 
  the local settings, an extra environment variable)?
- Is ms the desired write precision of the timestamp?  Should this be configurable (via the local settings)?
