import logging
from typing import Optional

import numpy as np
from prometheus_client import Gauge

from egse.hk import TmDictionaryColumns
from egse.settings import Settings
from egse.setup import SetupError, load_setup, Setup

LOGGER = logging.getLogger(__name__)
SITE_ID = Settings.load("SITE").ID


def define_metrics(origin: str, dashboard: str = None, use_site: bool = False, setup: Optional[Setup] = None) -> dict:
    """ Creates a metrics dictionary from the telemetry dictionary.

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
                LOGGER.warning(f"ValueError for {syn_name}")

        return metrics

    th_prefix = f"G{SITE_ID}_"

    th_syn_names = []
    th_descriptions = []
    for syn_name, description in zip(syn_names, descriptions):
        if syn_name.startswith(th_prefix):
            th_syn_names.append(syn_name)
            th_descriptions.append(description)

    return {
        syn_name: Gauge(syn_name, description)
        for syn_name, description in zip(th_syn_names, th_descriptions)
    }


def update_metrics(metrics: dict, updates: dict):
    """ Updates the metrics parameters with the values from the updates dictionary.

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
                metrics[metric_name].set(float('nan'))
            else:
                metrics[metric_name].set(float(value))
        except KeyError:
            LOGGER.warning(f"Unknown metric name: {metric_name=}")
