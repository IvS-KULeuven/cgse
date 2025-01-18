import datetime
import textwrap
from pathlib import Path

import rich

from egse.env import get_site_id
from egse.setup import Setup
from egse.system import EPOCH_1958_1970
from egse.system import format_datetime


HERE = Path(__file__).parent


def test_get_housekeeping(default_env):
    from egse.hk import get_housekeeping

    # The get_housekeeping() function will by default search for HK telemetry in the daily CSV file that contains the
    # HK parameter that is passed into the function. Since we have no operational system running during the tess,
    # we will need to create sample data for that parameter in the correct file. The file will be located in the
    # data storage location folder (defined by the default_env fixture) at
    # `HERE/data/LAB23/daily/YYYYMMDD/YYYYMMDD_LAB23_DAQ-TM.csv`, where 'LAB23' is the SITE_ID and 'DAQ-TM' is the
    # storage mnemonic of the device (this is read from the TM dictionary file).

    today = format_datetime("today")
    today_with_dash = format_datetime("today", fmt="%Y-%m-%d")

    hk_path = HERE / f"data/{get_site_id()}/daily/{today}/"
    hk_filename = f"{today}_{get_site_id()}_DAQ-TM.csv"

    hk_path.mkdir(mode=0o777, parents=True, exist_ok=True)

    with (hk_path / hk_filename).open(mode='w') as fd:
        fd.writelines(textwrap.dedent(
            f"""\
            timestamp,TEMPT_ABC_000,TEMP_ABC_001,TEMP_ABC_002
            {today_with_dash}T00:00:23.324+0000,21.333,23.3421,26.234
            {today_with_dash}T00:00:42.123+0000,22.145,23.4567,27.333
            """
        ))

    setup = Setup.from_yaml_string(
        textwrap.dedent(
            """
            telemetry:
                dictionary: pandas//../../common/telemetry/tm-dictionary-default.csv
                separator: ;
            """
        )
    )

    rich.print("telemetry", setup.telemetry.dictionary)

    try:
        timestamp, data = get_housekeeping("TEMP_ABC_001", setup=setup)
        timestamp -= EPOCH_1958_1970
        dt = datetime.datetime.utcfromtimestamp(timestamp)

        rich.print(f"{timestamp}, {dt}, {data}")

        assert data.strip() == '23.4567'
        assert format_datetime(dt, fmt="%Y-%m-%d").startswith(today_with_dash)

    finally:
        # Get rid of the CSV file
        (hk_path / hk_filename).unlink()

        # Get rid of today's folder
        hk_path.rmdir()


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
