import pickle

from egse.zmq_ser import zmq_error_response
from egse.zmq_ser import zmq_json_request
from egse.zmq_ser import zmq_json_response
from egse.zmq_ser import zmq_string_request
from egse.zmq_ser import zmq_string_response


def test_zmq_requests():
    assert zmq_string_request("") == [b"MESSAGE_TYPE:STRING", b""]
    assert zmq_string_request("hello") == [b"MESSAGE_TYPE:STRING", b"hello"]

    assert zmq_json_request({}) == [b"MESSAGE_TYPE:JSON", b"{}"]
    assert zmq_json_request({"command": "do_something"}) == [b"MESSAGE_TYPE:JSON", b'{"command": "do_something"}']


def test_zmq_responses():
    assert zmq_string_response("") == [b"MESSAGE_TYPE:STRING", b""]
    assert zmq_string_response("Good Job!") == [b"MESSAGE_TYPE:STRING", b"Good Job!"]

    assert zmq_json_response({}) == [b"MESSAGE_TYPE:JSON", b"{}"]
    assert zmq_json_response({"success": True, "message": "all good", "metadata": {"version": "0.1.0"}}) == [
        b"MESSAGE_TYPE:JSON",
        b'{"success": true, "message": "all good", "metadata": {"version": "0.1.0"}}',
    ]
    assert zmq_json_response(
        {
            "success": True,
            "message": {"name": "cgse", "description": "Great software"},
            "metadata": {"version": "0.1.0"},
        }
    ) == [
        b"MESSAGE_TYPE:JSON",
        b"{"
        b'"success": true, '
        b'"message": {"name": "cgse", "description": "Great software"}, "metadata": {"version": "0.1.0"}'
        b"}",
    ]


def test_zmq_error_responses():
    assert zmq_error_response({}) == [b"MESSAGE_TYPE:ERROR", b"\x80\x04}\x94."]
    response = zmq_error_response(
        {
            "success": False,
            "message": "Incorrect message type: MESSAGE_TYPE:PICKLE",
            "metadata": {
                "data": {
                    "file": "/Users/rik/github/cgse/libs/cgse-common/src/egse/async_control.py",
                    "lineno": 322,
                    "function": "_process_device_command",
                },
            },
        }
    )
    assert isinstance(response, list)
    assert len(response) == 2
    assert response[0] == b"MESSAGE_TYPE:ERROR"
    assert isinstance(response[1], bytes)
    assert pickle.loads(response[1]) == {
        "success": False,
        "message": "Incorrect message type: MESSAGE_TYPE:PICKLE",
        "metadata": {
            "data": {
                "file": "/Users/rik/github/cgse/libs/cgse-common/src/egse/async_control.py",
                "lineno": 322,
                "function": "_process_device_command",
            },
        },
    }
