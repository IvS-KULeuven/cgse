import asyncio
import pickle
import random

import pytest
import zmq
import zmq.asyncio

from egse.zmq_ser import wait_for_message
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


@pytest.mark.asyncio
async def test_wait_for_message_does_not_take_the_message():
    context = zmq.asyncio.Context.instance()
    pull = context.socket(zmq.PULL)
    port = pull.bind_to_random_port("tcp://127.0.0.1")
    push = context.socket(zmq.PUSH)
    push.connect(f"tcp://127.0.0.1:{port}")
    try:
        assert await wait_for_message(pull, timeout=0.05) is False

        await push.send(b"hello")
        assert await wait_for_message(pull, timeout=1.0) is True
        assert await wait_for_message(pull, timeout=0.0) is True  # still there, poll() didn't take it
        assert await pull.recv() == b"hello"
    finally:
        push.close(linger=0)
        pull.close(linger=0)


@pytest.mark.asyncio
async def test_receive_loop_with_wait_for_message_loses_no_requests():
    """A server loop with a short timeout, like the request loops of the registry and the hubs.

    With `asyncio.wait_for(socket.recv_multipart(), timeout)` instead, a request that arrives just when the receive
    is cancelled is lost: with a 1 ms timeout, about 3% of the requests in this test.
    """
    context = zmq.asyncio.Context.instance()
    router = context.socket(zmq.ROUTER)
    port = router.bind_to_random_port("tcp://127.0.0.1")
    stop = asyncio.Event()

    async def server():
        while not stop.is_set():
            if not await wait_for_message(router, timeout=0.001):
                continue
            client_id, *_ = await router.recv_multipart()
            await router.send_multipart([client_id, b"reply"])

    task = asyncio.create_task(server())
    lost = 0
    try:
        for _ in range(300):
            dealer = context.socket(zmq.DEALER)
            dealer.connect(f"tcp://127.0.0.1:{port}")
            await asyncio.sleep(random.uniform(0, 0.002))
            await dealer.send_multipart([b"request"])
            if not await dealer.poll(timeout=1000):
                lost += 1
            dealer.close(linger=0)
    finally:
        stop.set()
        await asyncio.gather(task, return_exceptions=True)
        router.close(linger=0)

    assert lost == 0
