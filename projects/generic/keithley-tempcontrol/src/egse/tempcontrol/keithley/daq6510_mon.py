"""
The synchronous monitoring service is a small application that performs measurements on
the DAQ6510.

The service reads the configuration for the Keithley DAQ6510 from the
Configuration Manager and then configures the device. When no Configuration Manager is
available, the service can also be started with a filename to read the configuration from. The file
should have the YAML format.

```
insert an excerpt of a sample YAML configuration file here...
```

The monitoring service can be started as follows:


"""

import datetime
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Any

import rich
import typer

from egse.env import bool_env
from egse.hk import read_conversion_dict
from egse.log import logger
from egse.logger import remote_logging
from egse.response import Failure
from egse.scpi import count_number_of_channels, get_channel_names
from egse.setup import Setup, load_setup
from egse.storage import StorageProxy, is_storage_manager_active
from egse.storage.persistence import CSV
from egse.system import SignalCatcher, flatten_dict, format_datetime, now
from egse.tempcontrol.keithley.daq6510 import DAQ6510Proxy, DEFAULT_BUFFER_1
from egse.tempcontrol.keithley.daq6510_cs import is_daq6510_cs_active

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")


def load_setup_from_input_file(input_file: str | Path) -> Setup | None:
    """Loads a Setup YAML file from disk."""
    input_file = Path(input_file).resolve()

    if not input_file.exists():
        logger.error(f"ERROR: Input file ({input_file}) doesn't exists.")
        return None

    return Setup.from_yaml_file(input_file)


def daq6510(count, interval, delay, channel_list, input_file: str):
    """
    Run the monitoring service for the DAQ6510.

    Args:
        count: Number of measurements to perform per acquisition [optional]
        interval: Time interval between measurements in seconds [optional]
        delay: Delay between acquisitions in seconds [optional]
        channel_list: Comma-separated list of channels to acquire data from [optional]
        input_file: YAML file containing the Setup for the DAQ6510 [optional]

    """

    multiprocessing.current_process().name = "egse.daq6510.monitor"

    if input_file:
        setup = load_setup_from_input_file(input_file)
    else:
        setup = load_setup()

    if setup is None:
        logger.error("ERROR: Could not load setup.")
        sys.exit(1)

    if not hasattr(setup, "gse"):
        logger.error("ERROR: No GSE section in the loaded Setup.")
        sys.exit(1)

    try:
        hk_conversion_table = read_conversion_dict("DAQ6510-MON", use_site=True, setup=setup)
        column_names = list(hk_conversion_table.values())
    except Exception as exc:
        logger.warning(f"WARNING: Failed to read telemetry dictionary: {exc}")
        hk_conversion_table = {}
        column_names = []

    if not is_daq6510_cs_active():
        logger.error(
            "The DAQ6510 Control Server is not running, start the 'daq6510_cs' command "
            "before running the data acquisition."
        )
        return

    if not is_storage_manager_active():
        logger.error("The storage manager is not running, start the core services before running the data acquisition.")
        return

    if "DAQ6510" not in setup.gse:  # type: ignore
        logger.error("ERROR: no DAQ6510 entry in the loaded Setup.")
        sys.exit(1)

    if not channel_list:
        channel_list = setup.gse.DAQ6510.channels  # type: ignore

    if not count:
        count = setup.gse.DAQ6510.route.scan.count.scan  # type: ignore

    if not interval:
        interval = setup.gse.DAQ6510.route.scan.interval  # type: ignore

    if not delay:
        delay = setup.gse.DAQ6510.route.delay  # type: ignore

    count, interval, delay = int(count), int(interval), int(delay)

    channel_count = count_number_of_channels(channel_list)
    channel_names = get_channel_names(channel_list)

    # FIXME:
    #     Metrics shall be ingested in InfluxDB

    # DAQ_METRICS = {}
    # for channel in channel_names:
    #     metrics_name = hk_conversion_table[channel]
    #     DAQ_METRICS[metrics_name] = Gauge(
    #         f"{metrics_name}",
    #         f"The current measure for the sensor connected to channel {channel} ({metrics_name}) on the DAQ6510",
    #     )

    # start_http_server(DAS.METRICS_PORT_DAQ6510)

    # Initialize some variables that will be used for registration to the Storage Manager

    origin = "DAQ6510-MON"
    persistence_class = CSV
    prep = {
        "mode": "a",
        "ending": "\n",
        "column_names": ["timestamp", *column_names],
    }

    killer = SignalCatcher()

    with DAQ6510Proxy() as daq, StorageProxy() as storage:
        daq.reset()

        dt = now()
        daq.set_time(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        logger.info(f"DAQ6510 date and time set: {daq.get_time()}")

        storage.register({"origin": origin, "persistence_class": persistence_class, "prep": prep})

        # This will write a comment line to the CSV file with the column names. This might be useful when
        # the sensors are reconfigured and the number or names of columns changes.
        storage.save({"origin": origin, "data": f"# columns: {column_names}"})

        for sensor in setup.gse.DAQ6510.sensors:  # type: ignore
            for function in setup.gse.DAQ6510.sensors[sensor]:  # type: ignore
                sense = {
                    function.upper(): [
                        (key, value)
                        for key, value in flatten_dict(setup.gse.DAQ6510.sensors[sensor][function]).items()  # type: ignore
                        if key != "channels"
                    ]
                }
                function_channel_list = setup.gse.DAQ6510.sensors[sensor][function].channels  # type: ignore
                if VERBOSE_DEBUG:
                    logger.debug(f"{sense=}")
                    logger.debug(f"{function_channel_list=}")
                daq.configure_sensors(channel_list=function_channel_list, sense=sense)

        logger.info(f"global: {channel_list=}, {channel_count=}")

        daq.setup_measurements(buffer_name=DEFAULT_BUFFER_1, channel_list=channel_list)

        while True:
            try:
                response = daq.perform_measurement(
                    buffer_name=DEFAULT_BUFFER_1, channel_list=channel_list, count=count, interval=interval
                )

                if killer.term_signal_received:
                    break

                if not response:
                    logger.warning("Received an empty response from the DAQ6510, check the connection with the device.")
                    logger.warning(f"Response: {response=}")
                    time.sleep(1.0)
                    continue

                if isinstance(response, Failure):
                    logger.warning("Received a Failure from the DAQ6510 Control Server:")
                    logger.warning(f"Response: {response}")
                    time.sleep(1.0)
                    continue

                # Process and save the response

                if VERBOSE_DEBUG:
                    logger.debug(f"{response=}")

                dts = response[0][1].strip()
                dt = datetime.datetime.strptime(dts[:-3], "%m/%d/%Y %H:%M:%S.%f")
                datetime_string = format_datetime(dt.replace(tzinfo=datetime.timezone.utc))

                data: dict[str, Any] = {hk_conversion_table[measure[0]]: float(measure[2]) for measure in response}
                data.update({"timestamp": datetime_string})

                # FIXME: we probably need to do something with the units...

                units = [measure[3] for measure in response]

                if VERBOSE_DEBUG:
                    logger.debug(f"{data=}")

                storage.save({"origin": origin, "data": data})

                # Now extract channels from the response to update the metrics

                for channel in [measure[0] for measure in response]:
                    if channel in hk_conversion_table:
                        metrics_name = hk_conversion_table[channel]
                        # DAQ_METRICS[metrics_name].set(data[metrics_name])

                # wait for the next measurement to be done (delay)

                time.sleep(delay)

            except KeyboardInterrupt:
                logger.debug("Interrupt received, terminating...")
                break
            except Exception as exc:
                logger.warning(f"DAS Exception: {exc}", exc_info=True)
                logger.warning("Got a corrupt response from the DAQ6510. Check log messages for 'DAS Exception'.")
                time.sleep(1.0)
                continue

        storage.unregister({"origin": origin})

    logger.info("DAQ6510 Data Acquisition System terminated.")


app = typer.Typer(
    name="daq6510_mon", help="DAQ6510 Data Acquisition Unit, Keithley, temperature monitoring (monitoring)"
)


@app.command()
def start(input_file: str = typer.Option("", help="YAML file containing the Setup for the DAQ6510")):
    """Starts the Keithley DAQ6510 Monitoring Service."""

    multiprocessing.current_process().name = "daq6510_mon (start)"

    with remote_logging():
        from egse.env import setup_env

        setup_env()

        try:
            daq6510(count=None, interval=None, delay=None, channel_list=None, input_file=input_file)
        except KeyboardInterrupt:
            logger.debug("Shutdown requested...exiting")
        except SystemExit as exit_code:
            logger.debug("System Exit with code {}.".format(exit_code))
            sys.exit(exit_code.code)
        except Exception:
            msg = "Cannot start the DAQ6510 Monitoring Service"
            logger.exception(msg)
            rich.print(f"[red]{msg}.")
