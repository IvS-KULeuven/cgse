# Test if object can be pickled.
import pickle

from egse.response import Failure
from egse.response import Message
from egse.response import Success


def test_failure():

    try:
        1/0
    except ZeroDivisionError as exc:
        failure = Failure("You cannot divide one by zero")

        assert f"{failure!r}" == "Failure('You cannot divide one by zero')"
        assert failure.message == str(failure) == f"{failure}" == "You cannot divide one by zero"
        assert failure.cause is None
        assert not failure.successful

        data = pickle.dumps(failure)

        assert isinstance(pickle.loads(data), Failure)

        failure = pickle.loads(data)

        assert f"{failure!r}" == "Failure('You cannot divide one by zero')"
        assert failure.message == str(failure) == f"{failure}" == "You cannot divide one by zero"
        assert failure.cause is None
        assert not failure.successful

        # ----- adding the cause

        failure = Failure("You cannot divide one by zero", cause=exc)

        assert f"{failure!r}" == ("Failure('You cannot divide one by zero: division by zero', "
                                  "cause=ZeroDivisionError('division by zero'))")
        assert failure.message == str(failure) == f"{failure}" == "You cannot divide one by zero: division by zero"
        assert isinstance(failure.cause, ZeroDivisionError)
        assert f"{failure.cause!r}" == "ZeroDivisionError('division by zero')"
        assert str(failure.cause) == f"{failure.cause!s}" == "division by zero"
        assert not failure.successful

        data = pickle.dumps(failure)

        assert isinstance(pickle.loads(data), Failure)

        failure = pickle.loads(data)

        assert f"{failure!r}" == ("Failure('You cannot divide one by zero: division by zero', "
                                  "cause=ZeroDivisionError('division by zero'))")
        assert failure.message == str(failure) == f"{failure}" == "You cannot divide one by zero: division by zero"
        assert isinstance(failure.cause, ZeroDivisionError)
        assert f"{failure.cause!r}" == "ZeroDivisionError('division by zero')"
        assert str(failure.cause) == f"{failure.cause!s}" == "division by zero"
        assert not failure.successful


def test_success():

    success = Success("This is a great success!")

    assert f"{success!r}" == "Success('This is a great success!')"
    assert success.message == str(success) == f"{success!s}" == "This is a great success!"
    assert success.response is None
    assert success.return_code is None
    assert success.successful

    data = pickle.dumps(success)

    assert isinstance(pickle.loads(data), Success)

    success = pickle.loads(data)

    assert f"{success!r}" == "Success('This is a great success!')"
    assert success.message == str(success) == f"{success!s}" == "This is a great success!"
    assert success.response is None
    assert success.return_code is None
    assert success.successful

    # ----- adding a return_code / response

    success = Success("This is a great success", return_code=3.1415)

    assert f"{success!r}" == "Success('This is a great success: 3.1415', return_code=3.1415)"
    assert success.message == str(success) == f"{success!s}" == "This is a great success: 3.1415"
    assert success.response == 3.1415
    assert success.return_code == 3.1415
    assert success.successful

    data = pickle.dumps(success)

    assert isinstance(pickle.loads(data), Success)

    success = pickle.loads(data)

    assert f"{success!r}" == "Success('This is a great success: 3.1415', return_code=3.1415)"
    assert success.message == str(success) == f"{success!s}" == "This is a great success: 3.1415"
    assert success.response == 3.1415
    assert success.return_code == 3.1415
    assert success.successful


def test_message():

    msg = Message("Hello, World!")

    assert f"{msg!r}" == "Message('Hello, World!')"
    assert str(msg) == f"{msg}" == "Hello, World!"
