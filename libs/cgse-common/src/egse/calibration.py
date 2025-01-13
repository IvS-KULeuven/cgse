import numpy as np

from egse.setup import NavigableDict, Setup, SetupError


def apply_gain_offset(counts: float, gain: float, offset: float) -> float:
    """ Applies the given gain and offset to the given counts.

    Args:
        counts: Uncalibrated, raw data [ADU]
        gain: Gain to apply
        offset: Offset to apply

    Returns: Counts after applying the given gain and offset.
    """

    return counts * gain + offset

#########################
# Temperature calibration
#########################


def counts_to_temperature(sensor_name: str, counts: float, sensor_info: NavigableDict, setup: Setup):
    """ Converts the given counts for the given sensor to temperature.

    This conversion can be done as follows:

        - (1) Directly from counts to temperature, by applying the gain and offset;
        - (2) Directly from counts to temperature, by applying a function;
        - (3) From counts, via resistance, to temperature.

    Args:
        sensor_name: Sensor name
        counts: Uncalibrated, raw data [ADU]
        sensor_info: Calibration information for the given sensor (type)
        setup: Setup

    Returns: Calibrated temperature [°C] for the given sensor
    """

    # (1) Conversion: temperature = counts * gain + offset

    if "counts_to_temperature_gain" in sensor_info and "counts_to_temperature_offset" in sensor_info:

        return apply_gain_offset(counts,
                                 gain=eval(str(sensor_info.counts_to_temperature_gain)),
                                 offset=sensor_info.counts_to_temperature_offset)

    # (2) Conversion: temperature = func(counts)

    if "counts_to_temperature" in sensor_info:

        # (2a) Polynomial

        if sensor_info.counts_to_temperature.method == "polynomial":
            return np.polyval(sensor_info.counts_to_temperature.counts_to_temperature_coefficients, counts)

    # (3) Conversion: counts -> resistance -> temperature

    else:
        resistance = counts_to_resistance(sensor_name, counts, sensor_info)
        return resistance_to_temperature(sensor_name, resistance, sensor_info, setup)


def counts_to_resistance(sensor_name: str, counts: float, sensor_info: NavigableDict):
    """ Converts the given counts for the given sensor to resistance.

    Args:
        sensor_name: Sensor name
        counts: Uncalibrated, raw data [ADU]
        sensor_info: Calibration information for the given sensor (type)

    Returns: Resistance [Ohm] for the given sensor.
    """

    # Offset (if any)

    counts_to_resistance_offset = sensor_info.counts_to_resistance_offset \
        if "counts_to_resistance_offset" in sensor_info \
        else 0

    # Conversion: counts -> voltage -> resistance

    if "counts_to_voltage_gain" in sensor_info and "voltage_to_resistance_gain" in sensor_info:

        return apply_gain_offset(counts,
                                 gain=sensor_info.counts_to_voltage_gain * sensor_info.voltage_to_resistance_gain,
                                 offset=counts_to_resistance_offset)

    # Conversion: counts -> resistance

    elif "counts_to_resistance_gain" in sensor_info:

        return apply_gain_offset(counts,
                                 gain=sensor_info.counts_to_resistance_gain,
                                 offset=counts_to_resistance_offset)

    raise SetupError(f"Setup does not contain info for conversion from counts to resistance for {sensor_name}")


def resistance_to_temperature(sensor_name: str, resistance: float, sensor_info: NavigableDict, setup: Setup):
    """ Converts the given resistance for the given sensor to temperature.

    Args:
        sensor_name: Sensor name
        resistance: Resistance [Ohm]
        sensor_info: Calibration information for the given sensor (type)
        setup: Setup

    Returns: Temperature [°C] for the given sensor.
    """

    resistance_to_temperature_info = sensor_info.resistance_to_temperature

    # Series resistance (if any)

    if "series_resistance" in resistance_to_temperature_info:

        series_resistance = resistance_to_temperature_info.series_resistance
        if sensor_name in resistance_to_temperature_info:
            series_resistance = series_resistance[sensor_name]
        resistance -= series_resistance

    method: str = resistance_to_temperature_info.method

    if "divide_resistance_by" in resistance_to_temperature_info:
        resistance /= resistance_to_temperature_info.divide_resistance_by

    # Polynomial

    if method == "polynomial":

        # Coefficients given for conversion temperature -> resistance

        if "temperature_to_resistance_coefficients" in resistance_to_temperature_info:
            return solve_temperature(resistance_to_temperature_info.temperature_to_resistance_coefficients, resistance)

        # Coefficients given for conversion resistance -> temperature

        if "resistance_to_temperature_coefficients" in resistance_to_temperature_info:
            return np.polyval(resistance_to_temperature_info.resistance_to_temperature_coefficients, resistance)

    elif method == "callendar_van_dusen":

        standard = resistance_to_temperature_info.standard
        ref_resistance = resistance_to_temperature_info.ref_resistance

        return callendar_van_dusen(resistance, ref_resistance, standard, setup)

    else:
        raise SetupError(f"Setup does not contain info for conversion from resistance to temperature for {sensor_name}")


def solve_temperature(temperature_to_resistance_coefficients, resistance: float):
    """ Solves the temperature from the temperature -> resistance polynomial.

    For the given temperature -> resistance polynomial and the given resistance, we determine what the corresponding
    temperature is by:

        - Finding the roots of polynomial(temperature) = resistance;
        - Discarding the roots with an imaginary component;
        - Selecting the remaining root in the relevant temperature regime (here: [-200°C, 200°C]).
    """

    temperature_to_resistance_poly = np.poly1d(temperature_to_resistance_coefficients)
    temperatures = (temperature_to_resistance_poly - resistance).roots

    for temperature in temperatures:
        if temperature.imag == 0 and -200 <= temperature <= 200:
            return temperature.real


def callendar_van_dusen(resistance: float, ref_resistance: float, standard: str, setup: Setup):
    """ Solves the Callendar - van Dusen equation for temperature.

    Args:
        resistance: Resistance [Ohm] for which to calculate the temperature
        ref_resistance: Resistance [Ohm] for a temperature of 0°C
        standard: Sensor standard
        setup: Setup

    Returns: Temperature [°C] corresponding to the given resistance.
    """

    # Resistances higher than the reference resistance correspond to

    coefficients = setup.sensor_calibration.callendar_van_dusen[standard]

    # Positive temperatures

    if resistance >= ref_resistance:
        resistance_to_temperature_coefficients = [ref_resistance * coefficients.C,
                                                  -ref_resistance * 100 * coefficients.C,
                                                  ref_resistance * coefficients.B,
                                                  ref_resistance * coefficients.A, ref_resistance * 1]

    # Negative temperatures

    else:
        resistance_to_temperature_coefficients = [ref_resistance * coefficients.B,
                                                  ref_resistance * coefficients.A,
                                                  ref_resistance * 1]

    return solve_temperature(resistance_to_temperature_coefficients, resistance)


def chebychev(resistance: float, sensor_info: NavigableDict):
    """ Solves the Chebychev equation for temperature.

    Implemented as specified in the calibration certificate of the LakeShore Cernox sensors.

    Args:
        resistance:Resistance [Ohm] for which to calculate the temperature
        sensor_info: Calibration information

    Returns: Temperature [°C] corresponding to the given resistance.
    """

    num_fit_ranges = sensor_info.num_fit_ranges

    for fit_range_index in range(1, num_fit_ranges + 1):

        range_info = sensor_info[f"range{fit_range_index}"]

        resistance_lower_limit, resistance_upper_limit = range_info.resistance_range

        if resistance_lower_limit <= resistance <= resistance_upper_limit:

            if range_info.fit_type == "LOG":
                z = np.log10(resistance)

            zl, zu = range_info.z_range
            order = range_info.order
            coefficients = range_info.coefficients

            temperature = 0

            for index in range(0, order + 1):

                k = ((z-zl)-(zu-z))/(zu-zl)
                temperature += coefficients[index] * np.cos(index * np.arccos(k))

            return temperature

############################
# Supply voltage calibration
############################

# TODO
