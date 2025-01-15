import rich


def test_get_housekeeping():
    from egse.hk import get_housekeeping

    data = get_housekeeping("TEMP_ABC_001")

    rich.print(data)

    assert data


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
