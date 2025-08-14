__all__ = [
    "DataPoint",
    "TimeSeriesRepository",
    "define_metrics",
    "get_metrics_repo",
]

from typing import Any
from typing import Optional
from typing import Protocol
from typing import Self

import numpy as np
from prometheus_client import Gauge

from egse.hk import TmDictionaryColumns
from egse.log import logger
from egse.plugin import load_plugins_fn
from egse.settings import Settings
from egse.setup import Setup
from egse.setup import SetupError
from egse.setup import load_setup
from egse.system import format_datetime
from egse.system import str_to_datetime

SITE_ID = Settings.load("SITE").ID


def define_metrics(origin: str, dashboard: str = None, use_site: bool = False, setup: Optional[Setup] = None) -> dict:
    """Creates a metrics dictionary from the telemetry dictionary.

    Read the metric names and their descriptions from the telemetry dictionary, and create Prometheus gauges based on
    this information.

    If `dashboard` is not provided, all telemetry parameters for the given origin will be returned.

    Args:
        origin: Storage mnemonics for the requested metrics
        dashboard: Restrict the metrics selection to those that are defined for the given dashboard. You can select
                   all dashboards with `dashboard='*'`.
        use_site: Indicate whether the prefixes of the new HK names are TH-specific
        setup: Setup.

    Returns: Dictionary with all Prometheus gauges for the given origin and dashboard.
    """

    setup = setup or load_setup()

    try:
        hk_info_table = setup.telemetry.dictionary
    except AttributeError:
        raise SetupError("Version of the telemetry dictionary not specified in the current setup")

    hk_info_table = hk_info_table.replace(np.nan, "")

    storage_mnemonic = hk_info_table[TmDictionaryColumns.STORAGE_MNEMONIC].values
    hk_names = hk_info_table[TmDictionaryColumns.CORRECT_HK_NAMES].values
    descriptions = hk_info_table[TmDictionaryColumns.DESCRIPTION].values
    mon_screen = hk_info_table[TmDictionaryColumns.DASHBOARD].values

    condition = storage_mnemonic == origin.upper()
    if dashboard is not None:
        if dashboard == "*":
            extra_condition = mon_screen != ""
        else:
            extra_condition = mon_screen == dashboard.upper()
        condition = np.all((condition, extra_condition), axis=0)

    selection = np.where(condition)

    syn_names = hk_names[selection]
    descriptions = descriptions[selection]

    if not use_site:
        metrics = {}

        for syn_name, description in zip(syn_names, descriptions):
            try:
                metrics[syn_name] = Gauge(syn_name, description)
            except ValueError:
                logger.warning(f"ValueError for {syn_name}")

        return metrics

    th_prefix = f"G{SITE_ID}_"

    th_syn_names = []
    th_descriptions = []
    for syn_name, description in zip(syn_names, descriptions):
        if syn_name.startswith(th_prefix):
            th_syn_names.append(syn_name)
            th_descriptions.append(description)

    return {syn_name: Gauge(syn_name, description) for syn_name, description in zip(th_syn_names, th_descriptions)}


def update_metrics(metrics: dict, updates: dict):
    """Updates the metrics parameters with the values from the updates dictionary.

    Only the metrics parameters for which the names are keys in the given updates dict are actually updated. Other
    metrics remain untouched.

    The functions log a warning when the updates dict contains a name which is not known as a metrics parameter.

    Args:
        metrics: Metrics dictionary previously defined with the define_metrics function
        updates: Dictionary with key=metrics name and value is the to-be-updated value
    """

    for metric_name, value in updates.items():
        try:
            if value is None:
                metrics[metric_name].set(float("nan"))
            else:
                metrics[metric_name].set(float(value))
        except KeyError:
            logger.warning(f"Unknown metric name: {metric_name=}")


class PointLike(Protocol):
    @staticmethod
    def measurement(measurement_name: str) -> "PointLike": ...

    def tag(self, key, value) -> Self: ...

    def field(self, field, value) -> Self: ...

    def time(self, time) -> Self: ...

    def as_dict(self) -> dict: ...


class DataPoint(PointLike):
    def __init__(self, measurement_name: str):
        self.measurement: str = measurement_name
        self.tags: dict[str, str] = {}
        self.fields: dict[str, Any] = {}
        self.timestamp: int | str = format_datetime()

    def as_dict(self):
        if isinstance(self.timestamp, str):
            timestamp = str_to_datetime(self.timestamp).timestamp()
        else:
            timestamp = self.timestamp

        return {
            "measurement": self.measurement,
            "tags": self.tags,
            "fields": self.fields,
            "time": timestamp,
        }

    @staticmethod
    def measurement(measurement_name):
        p = DataPoint(measurement_name)
        return p

    def tag(self, key, value):
        self.tags[key] = value
        return self

    def field(self, field, value):
        self.fields[field] = value
        return self

    def time(self, time):
        self.timestamp = time
        return self


class TimeSeriesRepository(Protocol):
    def connect(self) -> None: ...

    def write(self, points: PointLike | dict | list[PointLike | dict]) -> None: ...

    def query(self, query_str: str, mode: str) -> Any: ...

    def get_table_names(self) -> list[str]: ...

    def get_column_names(self, table_name: str) -> list[str]: ...

    def get_values_last_hours(self, table_name: str, column_name: str, hours: int, mode: str) -> Any: ...

    def get_values_in_range(
        self, table_name: str, column_name: str, start_time: str, end_time: str, mode: str
    ) -> Any: ...

    def close(self) -> None: ...


def get_metrics_repo(plugin_name: str, config: dict[str, Any]) -> TimeSeriesRepository:
    """
    Create a TimeSeriesRepository instance from a plugin.

    Args:
        plugin_name: Name of the plugin (without .py extension)
        config: Configuration parameters for the repository

    Returns:
        Configured TimeSeriesRepository instance.

    Raises:
        ModuleNotFoundError: If plugin not found
        NotImplementedError: If plugin is missing get_repository_class()
    """

    package_name = "egse.plugins"
    plugins = load_plugins_fn(f"{plugin_name}.py", package_name)

    if plugin_name in plugins:
        plugin = plugins[plugin_name]
        if hasattr(plugin, "get_repository_class"):
            repo_class = plugin.get_repository_class()
        else:
            raise NotImplementedError(f"Missing 'get_repository_class()` function in metrics plugin {plugin_name}.")
        return repo_class(**config)
    else:
        raise ModuleNotFoundError(f"No plugin found for {plugin_name} in {package_name}.")
