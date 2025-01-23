import datetime
import textwrap
from pathlib import Path

import rich

from egse.env import get_site_id
from egse.hk import get_housekeeping
from egse.setup import Setup
from egse.system import EPOCH_1958_1970
from egse.system import format_datetime

from fixtures.helpers import create_text_file

HERE = Path(__file__).parent


def test_get_housekeeping(default_env):

    data_dir = Path(default_env.data_root)

    # The get_housekeeping() function will by default search for HK telemetry in the daily CSV file that contains the
    # HK parameter that is passed into the function. Since we have no operational system running during the tess,
    # we will need to create sample data for that parameter in the correct file. The file will be located in the
    # data storage location folder (defined by the default_env fixture) at
    # `HERE/data/LAB23/daily/YYYYMMDD/YYYYMMDD_LAB23_DAQ-TM.csv`, where 'LAB23' is the SITE_ID and 'DAQ-TM' is the
    # storage mnemonic of the device (this is read from the TM dictionary file).

    today = format_datetime("today")
    today_with_dash = format_datetime("today", fmt="%Y-%m-%d")

    tm_dictionary_path = data_dir / "../common/telemetry/tm-dictionary.csv"

    create_text_file(tm_dictionary_path, textwrap.dedent(
        """\
        TM source;Storage mnemonic;CAM EGSE mnemonic;Original name in EGSE;Name of corresponding timestamp;\
        Origin of synoptics at CSL;Origin of synoptics at CSL1;Origin of synoptics at CSL2;\
        Origin of synoptics at SRON;Origin of synoptics at IAS;Origin of synoptics at INTA;\
        Description;MON screen;unit cal1;offset b cal1;slope a cal1;calibration function;\
        MAX nonops;MIN nonops;MAX ops;MIN ops;Comment

        Unit Test Manager;DAQ-TM;TEMP_ABC_001;ABC_001;timestamp;;;;;;;Temperature of ABC;;;;;;;;;;

        """
    ), create_folder=True)

    hk_path = data_dir / f"daily/{today}/{today}_{get_site_id()}_DAQ-TM.csv"

    create_text_file(hk_path, textwrap.dedent(
            f"""\
            timestamp,TEMPT_ABC_000,TEMP_ABC_001,TEMP_ABC_002
            {today_with_dash}T00:00:23.324+0000,21.333,23.3421,26.234
            {today_with_dash}T00:00:42.123+0000,22.145,23.4567,27.333
            """
        ), create_folder=True
    )

    # The TM dictionary will be loaded relative from the configuration data location as defined by
    # `get_conf_data_location()` (the latter being defined from the data storage location which is defined
    # in `default_env`).

    setup = Setup.from_yaml_string(
        textwrap.dedent(
            """
            telemetry:
                dictionary: pandas//../../common/telemetry/tm-dictionary.csv
                separator: ;
            """
        )
    )

    rich.print(f"{hk_path = }")
    rich.print(f"{tm_dictionary_path = }")

    try:
        timestamp, data = get_housekeeping("TEMP_ABC_001", setup=setup)
        timestamp -= EPOCH_1958_1970
        dt = datetime.datetime.utcfromtimestamp(timestamp)

        rich.print(f"{timestamp}, {dt}, {data}")

        assert data.strip() == '23.4567'
        assert format_datetime(dt, fmt="%Y-%m-%d").startswith(today_with_dash)

    finally:
        # Get rid of the CSV file
        hk_path.unlink()

        # Get rid of the tm dictionary file
        tm_dictionary_path.unlink()


def test_convert_hk_names():

    a = {
        'aaa': 1,
        'bbb': 2,
        'ccc': 3,
        'eee': 4,
    }

    c = {
        'aaa': 'AAA',
        'bbb': 'BBB',
        'ccc': 'CCC',
        'ddd': 'DDD',
    }

    from egse.hk import convert_hk_names

    b = convert_hk_names(a, c)

    # Result:
    #  * all keys in 'a' that have a conversion in 'c' shall be in 'b' with the converted key
    #  * all keys in 'a' that do not have a conversion in 'c', shall be in 'b' with their original key
    #  * all conversion keys that are in 'c' but not in 'a' shall just be ignored

    assert 'AAA' in b
    assert 'BBB' in b
    assert 'CCC' in b
    assert 'eee' in b

    assert 'aaa' not in b
    assert 'bbb' not in b
    assert 'ccc' not in b
    assert 'ddd' not in b
    assert 'DDD' not in b

    for k, v in a.items():
        if k == 'eee':
            assert b[k] == v
        else:
            assert b[k.upper()] == v
