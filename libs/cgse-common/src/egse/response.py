"""
This module provides functionality to handle responses from the control servers.
"""
__all__ = [
    "Failure",
    "Message",
    "Response",
    "Success",
]

from typing import Any

import rich.repr


class Response:
    """
    Base class for any reply or response between client-server communication.

    The idea is that the response is encapsulated in one of the subclasses depending
    on the type of response.
    """

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        return self.message

    @property
    def successful(self):
        """Returns True if the Response is not an Exception."""
        return not isinstance(self, Exception)


@rich.repr.auto
class Failure(Response, Exception):
    """
    A failure response indicating something went wrong at the other side.

    This class is used to encapsulate an Exception that was caught and needs to be
    passed to the client. So, the intended use is like this:

        try:
            # perform some useful action that might raise an Exception
        except SomeException as exc:
            return Failure("Our action failed", exc)

    The client can inspect the Exception that was originally raised, in this case `SomeException`
    with the `cause` variable.

    Since a Failure is also an Exception, the property `successful` will return False.
    So, the calling method can test for this easily.

        rc: Response = function_that_returns_a_response()

        if not rc.successful:
            # handle the failure
        else:
            # handle success

    """

    def __init__(self, message: str, cause: Exception = None):
        msg = f"{message}: {cause}" if cause is not None else message
        super().__init__(msg)
        self.cause = cause


@rich.repr.auto
class Success(Response):
    """
    A success response for the client.

    The return code from any action or function that needs to be returned to the
    client shall be added.

    Since `Success` doesn't inherit from `Exception`, the property `successful` will return True.
    """

    def __init__(self, message: str, return_code: Any = None):
        msg = f"{message}: {return_code}" if return_code is not None else message
        super().__init__(msg)
        self.return_code = return_code

    @property
    def response(self):
        return self.return_code


@rich.repr.auto
class Message(Response):
    """
    A message response from the client.

    Send a Message when there is no Failure, but also no return code. This is the alternative of
    returning a None.

    Message returns True for the property successful since it doesn't inherit from Exception.
    """

    pass
