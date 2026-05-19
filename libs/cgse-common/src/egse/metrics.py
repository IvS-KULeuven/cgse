__all__ = [
    "DataPoint",
    "MeasurementColumn",
    "MeasurementSchema",
    "TimeSeriesRepository",
    "clear_measurement_schemas",
    "define_metrics",
    "get_measurement_schema",
    "get_measurement_schemas",
    "get_metrics_repo",
    "load_measurement_schemas_from_modules",
    "register_measurement_schema",
]

import datetime
import importlib
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Optional
from typing import Protocol

import numpy as np
from prometheus_client import Gauge
from typing_extensions import Self

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

TimestampLike = str | int | float | datetime.datetime

MetricScalarType = str


@dataclass(frozen=True)
class MeasurementColumn:
    name: str
    data_type: MetricScalarType


@dataclass(frozen=True)
class MeasurementSchema:
    name: str
    tags: tuple[MeasurementColumn, ...] = field(default_factory=tuple)
    fields: tuple[MeasurementColumn, ...] = field(default_factory=tuple)

    def get_tag(self, name: str) -> MeasurementColumn | None:
        for column in self.tags:
            if column.name == name:
                return column
        return None

    def get_field(self, name: str) -> MeasurementColumn | None:
        for column in self.fields:
            if column.name == name:
                return column
        return None


_MEASUREMENT_SCHEMAS: dict[str, MeasurementSchema] = {}


def register_measurement_schema(schema: MeasurementSchema) -> None:
    _MEASUREMENT_SCHEMAS[schema.name] = schema


def get_measurement_schema(measurement_name: str) -> MeasurementSchema | None:
    return _MEASUREMENT_SCHEMAS.get(measurement_name)


def get_measurement_schemas() -> dict[str, MeasurementSchema]:
    return dict(_MEASUREMENT_SCHEMAS)


def clear_measurement_schemas() -> None:
    _MEASUREMENT_SCHEMAS.clear()


def load_measurement_schemas_from_modules(
    module_names: list[str],
    function_name: str = "register_measurement_schemas",
) -> list[str]:
    loaded_modules: list[str] = []
    for module_name in module_names:
        normalized = module_name.strip()
        if not normalized:
            continue

        module = importlib.import_module(normalized)
        callback = getattr(module, function_name, None)
        if callback is None or not callable(callback):
            raise AttributeError(f"Module {normalized!r} does not expose callable {function_name!r}")

        callback()
        loaded_modules.append(normalized)

    return loaded_modules


def define_metrics(
    origin: str, dashboard: str | None = None, use_site: bool = False, setup: Optional[Setup] = None
) -> dict:
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
        raise SetupError(
            "Version of the telemetry dictionary not specified in the current setup, "
            "expected to find it in setup.telemetry.dictionary. Cannot define metrics without telemetry dictionary."
        )

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

    def time(self, time: TimestampLike) -> Self: ...

    def as_dict(self) -> dict[str, Any]: ...


class DataPoint(PointLike):
    def __init__(self, measurement_name: str):
        self.measurement_name: str = measurement_name
        self.tags: dict[str, str] = {}
        self.fields: dict[str, Any] = {}
        self.timestamp: TimestampLike = format_datetime()

    def as_dict(self) -> dict[str, Any]:
        if isinstance(self.timestamp, str):
            timestamp = str_to_datetime(self.timestamp).timestamp()
        elif isinstance(self.timestamp, datetime.datetime):
            timestamp = self.timestamp.timestamp()
        else:
            timestamp = self.timestamp

        return {
            "measurement": self.measurement_name,
            "tags": self.tags,
            "fields": self.fields,
            "time": timestamp,
        }

    @staticmethod
    def measurement(measurement_name: str) -> "DataPoint":
        data_point = DataPoint(measurement_name)
        return data_point

    def tag(self, key, value):
        self.tags[key] = value
        return self

    def field(self, field, value):
        self.fields[field] = value
        return self

    def time(self, time: TimestampLike) -> Self:
        self.timestamp = time
        return self


class TimeSeriesRepository(Protocol):
    def __enter__(self):
        self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self) -> None: ...

    def ping(self) -> bool: ...

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
