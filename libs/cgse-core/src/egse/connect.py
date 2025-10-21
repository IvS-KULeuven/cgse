from egse.env import bool_env
from egse.log import logging
from egse.zmq_ser import connect_address

logger = logging.getLogger("egse.connect")

# random.seed(time.monotonic())  # uncomment for testing only, main application should set a seed.

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")


def get_endpoint(
    service_type: str,
    protocol: str = "tcp",
    hostname: str = "localhost",
    port: int = 0,
):
    """
    Returns the endpoint for a service, either from the registry or by constructing
    it from protocol, hostname and port.

    If port is 0 (the default), attempt to retrieve the endpoint from the service registry.

    Args:
        service_type: The service type to look up in the registry.
        protocol: Protocol to use if constructing the endpoint, defaults to tcp.
        hostname: Hostname to use if constructing the endpoint, defaults to localhost.
        port: Port to use if constructing the endpoint, defaults to 0.

    Returns:
        The endpoint string.

    Raises:
        RuntimeError: If no endpoint can be determined.
    """
    endpoint = None
    from egse.registry.client import RegistryClient

    if port == 0:
        with RegistryClient() as reg:
            endpoint = reg.get_endpoint(service_type)
        if endpoint:
            if VERBOSE_DEBUG:
                logger.debug(f"Endpoint for {service_type} found in registry: {endpoint}")
        else:
            logger.warning(f"No endpoint for {service_type} found in registry.")

    if not endpoint:
        if port == 0:
            raise RuntimeError(f"No service registered as {service_type} and no port provided.")
        endpoint = connect_address(protocol, hostname, port)
        if VERBOSE_DEBUG:
            logger.debug(f"Endpoint constructed from protocol/hostname/port: {endpoint}")

    return endpoint
