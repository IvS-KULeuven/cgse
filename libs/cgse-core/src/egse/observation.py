import functools
import hashlib
from collections import deque
from inspect import signature
from typing import Callable

from egse.confman import ConfigurationManagerProxy
from egse.decorators import borg
from egse.env import bool_env
from egse.log import logger
from egse.response import Failure
from egse.response import Success

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG", default=False)


@borg
class ObservationContext:
    """Keep record of the observation context.

    Note: This class implements the Borg pattern and shares state between its instances.
          This allows us to keep track of the observation context across multiple building blocks and observations,
          without having to pass around an instance of this class.
    """

    def __init__(self) -> None:
        self.level = -1
        self.bbid_count = 0
        self.bbids = deque()

    def set_bbid(self, bbid: str):
        """Set the current building block id."""
        if bbid in self.bbids:
            raise ValueError(
                f"This building block ({bbid}) is already in execution, check dependencies between building blocks."
            )
        if self.level == -1:
            raise RuntimeError(f"This building block ({bbid}) is called outside the scope of an observation context.")

        self.bbids.append(bbid)
        self.bbid_count += 1
        self.level += 1

    def unset_bbid(self):
        """Unset the current building block id and go back to the previous level and bbid."""
        self.bbids.pop()
        self.level -= 1

    def get_current_bbid(self):
        return self.bbids[-1]

    def get_level(self):
        return self.level

    def start_observation(self, function_info: dict):
        if self.level == -1:
            self.level = 0
        else:
            raise Failure(
                "An observation can only be started when no observation is already running. "
                "Only one Observation can be active at a time."
            )

        try:
            with ConfigurationManagerProxy() as cm:
                rc = cm.start_observation(function_info)
                if not rc.successful:
                    self.level = -1
                    raise rc
                else:
                    return rc.return_code
        except ConnectionError as exc:
            self.level = -1
            raise Failure("Couldn't connect to the Configuration Manager Control Server", exc)

    def end_observation(self):
        if self.level > 0 or self.bbids:
            logger.warning(f"Observation contexts not empty at time of reset! (Level={self.level}, bbids={self.bbids})")
        self.level = -1
        self.bbid_count = 0
        self.bbids.clear()

        with ConfigurationManagerProxy() as cm:
            rc = cm.end_observation()
            if not rc.successful:
                raise rc


def request_obsid():
    """Requests an `obsid` from the configuration manager.

    Returns:
        the current observation identifier.

    Raises:
        Failure with message and cause.
    """
    with ConfigurationManagerProxy() as cm:
        rc = cm.get_obsid()
        if isinstance(rc, Success):
            return rc.return_code

    raise rc


def stringify_args(args):
    s_args = []
    for arg in args:
        try:
            s_args.append(f"{arg.__module__}.{arg.__class__.__qualname__}")
        except AttributeError:
            s_args.append(repr(arg))

    return s_args


def stringify_kwargs(kwargs):
    s_kwargs = {}
    for k, v in kwargs.items():
        try:
            s_kwargs[k] = f"{v.__module__}.{v.__class__.__qualname__}"
        except AttributeError:
            s_kwargs[k] = repr(v)

    return s_kwargs


def execute(func: Callable, description=None, *args, **kwargs):
    """Execute a building block or observation."""

    try:
        ObservationContext().start_observation(
            {
                "func_name": func.__name__,
                "description": description,
                "args": stringify_args(args),
                "kwargs": stringify_kwargs(kwargs),
            }
        )

        obsid = request_obsid()
        logger.info(f"OBSID = {obsid}")

    except (Failure, TypeError) as exc:
        logger.error(f"Failed to start observation or test: {exc}")
        raise exc

    # can I check here if func is indeed a building_block?

    if not hasattr(func, "__building_block_func"):
        logger.warning("Executing a function that is not a building block.")

    try:
        response = func(*args, **kwargs)
    finally:
        ObservationContext().end_observation()

    return response


def start_observation(description: str):
    try:
        ObservationContext().start_observation({"description": description})

        obsid = request_obsid()
        logger.info(f"Observation started with obsid={obsid}")

    except Failure as exc:
        logger.error(f"Failed to start observation or test: {exc}")
        raise exc

    return obsid


def end_observation():
    ObservationContext().end_observation()


def building_block(func: Callable) -> Callable:
    """Mark a function as a building block and wrap it with lifecycle handling.

    The wrapper enforces keyword-only invocation, validates required keyword
    arguments against the function signature, sets the BBID on entry, and
    unsets it on exit (even if the function raises).

    Args:
        func: Function to decorate as a building block.

    Returns:
        A wrapped callable that preserves the original signature metadata.

    Raises:
        ValueError: If positional arguments are provided or required kwargs are missing.
    """

    setattr(func, "__building_block_func", True)

    def check_kwargs(**kwargs):
        sig = signature(func)
        missing = [par.name for par in sig.parameters.values() if par.name not in kwargs]

        if VERBOSE_DEBUG:
            logger.debug(f"missing keyword arguments: {missing}")

        if missing:
            raise ValueError(
                f"Expected {len(sig.parameters)} keyword parameters for "
                f"building block {func.__name__}, missing arguments are {missing}."
            )

    def rewrite_kwargs(**kwargs):
        if VERBOSE_DEBUG:
            logger.debug(f"{func.__name__}({kwargs})")
        return kwargs

    @functools.wraps(func)
    def wrapper_func(*args, **kwargs):
        # Take steps to make the function `func` into a building block.
        #
        # * set its building block id based on the name of the function
        # * check if this building block is executed within the scope of an observation
        # * execute the function `func`

        # TODO: We should also check for args, there can be no args!!

        if args:
            raise ValueError(
                f"Building block {func.__name__} can not have positional arguments. "
                f"The following arguments {args} should be given as keyword arguments."
            )

        kwargs = rewrite_kwargs(**kwargs)
        check_kwargs(**kwargs)

        start_building_block(func, *args, **kwargs)

        try:
            result = func(*args, **kwargs)
        finally:
            # Take steps to end the building block
            end_building_block()

        return result

    return wrapper_func


def start_building_block(func: Callable, *args, **kwargs) -> str:
    """Start a building block by assigning its BBID in the observation context.

    Args:
        func: Building block function used to derive the BBID.
        *args: Unused positional arguments (kept for compatibility).
        **kwargs: Unused keyword arguments (kept for compatibility).

    Returns:
        The generated BBID string.
    """

    # * define a unique building block identifier
    # * return the building block identifier

    bbid = get_bbid_uuid(func)
    ObservationContext().set_bbid(bbid)
    return bbid


def end_building_block():
    """End a building block by clearing the BBID from the observation context."""
    ObservationContext().unset_bbid()


def get_bbid_uuid(func: Callable) -> str:
    """Return a deterministic BBID for the given building block function.

    The BBID is derived from the function's fully-qualified name and is stable
    across runs. Only functions decorated with :func:`building_block` are
    accepted.

    Args:
        func: Building block function.

    Returns:
        A BBID string in the form ``BBID-<FUNCNAME>-<HASH>``.

    Raises:
        ValueError: If ``func`` is not callable or is not a building block.
    """
    if not isinstance(func, Callable):
        raise ValueError("The given argument should be a function or method.")

    if not hasattr(func, "__building_block_func"):
        raise ValueError("The given function is not defined as a building block.")

    func_identifier = f"{func.__module__}.{func.__qualname__}"
    unique_uuid = hashlib.sha256(func_identifier.encode()).hexdigest()
    bbid = f"BBID-{func.__name__.upper()}-{unique_uuid.upper()}"
    return bbid
