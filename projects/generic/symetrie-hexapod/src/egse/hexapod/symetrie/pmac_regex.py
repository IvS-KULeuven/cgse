import logging
import re

logger = logging.getLogger(__name__)

regex_response = {
    # Error message as ERRXXX
    "ERROR": re.compile(r"\a(ERR\d{3})\r"),
    # a floating point number [-]x[.[xxx]], possibly followed by spaces
    "FLOAT": re.compile(r"(-?(\d*\.)?\d+)\s*\r\x06"),
    # an integer number possible [-]iiiii, possibly followed by spaces
    "INT": re.compile(r"(-?\d+)\s*\r\x06"),
    # Anything else, stripping off '\x06'
    "ANY": re.compile(r"(.*)\x06"),
    # Just the null character
    "NUL": re.compile(r"(\x00)"),
}


def match_regex_response(regex_prog, res):
    """
    This 'matches' from the start of the string 'res'. If you want to match anywhere in the
    string, you will need to make another function search_regex_response() with 'search' instead
    of 'match'.

    Return None if no match and the match object otherwise.
    """
    logger.flash_flood(f"res = {res} with type {type(res)}")
    if isinstance(res, bytes):
        res = res.decode()
    match_obj = regex_prog.match(res)
    return match_obj


def patter_n_int(nr):
    return re.compile(fr"(-?\d+)\r((-?\d+)\r){{{nr}}}\x06")


def patter_n_float(nr):
    return re.compile(fr"(-?\d+)\r((-?(\d*\.)?\d+)\r){{{nr}}}\x06")


def match_int_response(res):
    match_obj = match_regex_response(regex_response["INT"], res)
    if match_obj is None:
        logger.error(f"Could not parse INT response for {res}")
        return None
    return int(match_obj[1])


def match_float_response(res):
    match_obj = match_regex_response(regex_response["FLOAT"], res)
    if match_obj is None:
        logger.error(f"Could not parse FLOAT response for {res}")
        return None
    return float(match_obj[1])


def match_error_response(res):
    match_obj = match_regex_response(regex_response["ERROR"], res)
    if match_obj is None:
        logger.error(f"Could not parse ERROR response for {res}")
        return None
    return match_obj[1]


def match_nul_response(res):
    match_obj = match_regex_response(regex_response["NUL"], res)
    if match_obj is None:
        logger.error(f"Could not parse NUL response for {res}")
        return None
    return match_obj[1]


def match_string_response(res):
    match_obj = match_regex_response(regex_response["ANY"], res)
    if match_obj is None:
        logger.error(f"Could not parse STRING response for {res}")
        return None
    if len(match_obj[1]) > 0 and match_obj[1][-1] == "\r":
        return match_obj[1][:-1]
    else:
        return match_obj[1]
