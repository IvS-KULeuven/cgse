# The Service Registry

The service registry is a centralised database that keeps track of all active
services in our distributed CGSE system. It acts as a dynamic directory where
services can register themselves upon startup and de-register when shutting
down. Any other service, script or app can use the service registry to retrieve
information about a registered service.

The service registry currently provides the following:

- It enables service discovery, allowing applications to find and connect to
  services without hardcoded hostnames and port numbers.
- It provides health monitoring and improves system resilience by automatically
  routing requests away from failed services.
- It facilitates dynamic scaling, as new service instances can register
  themselves automatically.
- It simplifies configuration management by centralizing service information.

The service registry is a critical component in our distributed system that
helps manage complexity, improve reliability, and enable elasticity.
Functionality will be gradually improved over time, e.g. by implementing load
balancing for storage services, or by adding security features like service
authentication to protect services.

## The Registry Service Client

A service registry client is a component that is part of an application or
microservice (e.g. a device driver) and is used to communicate with the service
registry server and discover available services. Microservices like device
drivers and core services that need to be discovered shall register to the
service registry. Applications can use the registry client without registration.

The registry client:

- Registers and de-registers itself to the service registry.
- Queries the service registry to discover a required service.
- Check the health of the service registry server.
- Can act on certain types of events from the registry server.
- Sends a heartbeat to the registry server to keep the registration alive.

A microservice can register as follows:

```python
from egse.registry.client import AsyncRegistryClient

registry_client = AsyncRegistryClient()
registry_client.connect()

service_id = await registry_client.register(
    name=service_name,
    host=hostname,
    port=port_number,
    service_type=service_type,
    metadata={},
    ttl=30,
)
```

Notice that the client operates asynchronously and is designed to run within an
asynchronous microservice or application. If your application or microservice
follows a synchronous execution model and cannot be converted to an asynchronous
approach, we also provide a synchronous version of the client through
the `RegistryClient()` class. This synchronous alternative offers the same core
functionality but blocks execution until operations complete, making it
compatible with traditional synchronous codebases while still leveraging the
service registry infrastructure.

The `service_name` must be a unique identifier for your specific service
instance. The `host` and `port` arguments specify the network location (hostname
and port number) where your microservice can be reached. These values enable
other services and applications to locate and communicate with your
microservice. The `service_type` parameter is a category identifier that groups
services providing equivalent functionality and compatible communication
interfaces. Services sharing the same `service_type` are considered
interchangeable from a client perspective. While this categorization primarily
facilitates service discovery in the current implementation, it also forms the
foundation for future enhancements such as intelligent load-balancing, failover
mechanisms, and service redundancy. When registering your service, ensure these
parameters accurately reflect your service's identity, location, and
capabilities.

The `metadata` parameter accepts a dictionary containing service-specific
information that complements the core registration details. While optional and
potentially empty, this field provides valuable extensibility for conveying
additional service characteristics. Common metadata includes version numbers (
enabling version-aware client routing), supplementary endpoints (such as ports
for monitoring, health checks, or event notifications), current load metrics (
facilitating intelligent load distribution), and capability flags (indicating
supported features). The `ttl` (Time To Live) parameter defines the maximum
duration, in seconds, that a service can remain unresponsive before the registry
automatically deregisters it. This mechanism ensures the registry maintains an
accurate representation of available services by removing instances that have
crashed or become network-isolated without proper deregistration.

Service discovery can be done as follows:

```python
registry_client = AsyncRegistryClient()

try:
    service = await registry_client.discover_service(service_type)

    if not service:
        logger.warning(f"No service of type '{service_type}' found")
        return None

    ...

    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

    try:
        # Connect to the service
        socket.connect(f"tcp://{service['host']}:{service['port']}")

        ...

    finally:
        socket.close()
finally:
    await registry_client.close()
```

The `AsyncRegistryClient` locates available services based on service type. Only
one service will be returned, even if more than one service was registered to
the same `service_type`. Once the service is discovered, the application can use
the information in the response to connect to and query the microservice, e.g.
using the service's `host` and `port` a ZeroMQ endpoint can be created.

The above code implements proper resource management by ensuring both the ZeroMQ
socket and registry client are closed, even if exceptions occur during service
discovery or communication.

## The Registry Service server

The `AsyncRegistryServer` is an asynchronous service registry implementation for
microservices architectures that are using ZeroMQ for communication and
providing persistent storage through pluggable backends. It enables service
discovery, registration, and health monitoring in distributed systems.

The server exposes two ZeroMQ sockets:

- A REQ-REP socket for service registration, discovery, and management
- A PUB-SUB socket for broadcasting service events (registrations,
  de-registrations, expirations)

The server uses a pluggable backend for storing the service registrations.
An `AsyncInMemoryBackend` is provided for in-memory storage as long as the
server is running. For persistent storage of service registrations, use
the `AsyncSLQiteBackend`.

Although, the server is integrated in the CGSE core services, the basic usage is
as follows:

```python
import asyncio

from egse.registry.server import AsyncSQLiteBackend
from egse.registry.server import AsyncRegistryServer


async def run_server():
    # Create and initialize a backend
    backend = AsyncSQLiteBackend("service_registry.db")
    await backend.initialize()

    # Create the server
    server = AsyncRegistryServer(
        req_port=4242,
        pub_port=4243,
        backend=backend
    )

    # Start the server
    await server.start()


if __name__ == "__main__":
    asyncio.run(run_server())
```

The `req_port` and `pub_port` parameters specify the network ports for the two
communication channels provided by the registry: the REQ-REP socket (handling
service requests and responses) and the PUB-SUB socket (broadcasting event
notifications). Both parameters are optional; if omitted, the system will use
the default values defined as constants `egse.registry.DEFAULT_RS_REQ_PORT`
and `egse.registry.DEFAULT_RS_PUB_PORT` respectively. The `backend` parameter
determines which `RegistryBackend` implementation will store and manage the
service registration data. This allows flexibility in how service information is
persisted (e.g., in-memory, file-based, or database-backed storage). An
additional optional parameter, `cleanup_interval`, controls how frequently (in
seconds) the registry scans for and removes expired service registrations whose
TTL has elapsed. This automatic cleanup mechanism ensures the registry maintains
an accurate representation of available services.

### Storage Backends

The server works with any backend that implements the `AsyncRegistryBackend`
protocol. Two implementations are provided:

- `AsyncSQLiteBackend`: Persistent storage using SQLite
- `AsyncInMemoryBackend`: In-memory storage for testing or simple deployments


### Service Registration Protocol

The server accepts requests in JSON format through its REQ-REP socket. Each
request must have an `action` field specifying the operation.

#### Registration

```json
{
  "action": "register",
  "service_info": {
    "name": "example-service",
    "host": "192.168.1.10",
    "port": 8080,
    "type": "web",
    "tags": [
      "web",
      "api"
    ],
    "metadata": {
      "version": "1.0.0"
    }
  },
  "ttl": 30
}
```

Response:

```json
{
  "success": true,
  "service_id": "example-service-f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "message": "Service registered successfully"
}
```

#### De-registration

```json
{
  "action": "deregister",
  "service_id": "example-service-f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

Response:

```json
{
  "success": true,
  "message": "Service deregistered successfully"
}
```

#### Service Renewal (Heartbeat)

```json
{
  "action": "renew",
  "service_id": "example-service-f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

Response:

```json
{
  "success": true,
  "message": "Service renewed successfully"
}
```

#### Get Service

```json
{
  "action": "get",
  "service_id": "example-service-f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

Response:

```json
{
  "success": true,
  "service": {
    "id": "example-service-f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "name": "example-service",
    "host": "192.168.1.10",
    "port": 8080,
    "type": "web",
    "tags": [
      "web",
      "api"
    ],
    "metadata": {
      "version": "1.0.0"
    },
    "ttl": 30,
    "last_heartbeat": 1617293054,
    "health": "passing"
  }
}
```

#### List Services

```json
{
  "action": "list",
  "service_type": "web"  // Optional, filter by type
}
```

Response:

```json
{
  "success": true,
  "services": [
    {
      "id": "service-1",
      "name": "example-service",
      "host": "192.168.1.10",
      "port": 8080,
      "type": "web",
      "tags": [
        "web",
        "api"
      ],
      "metadata": {
        "version": "1.0.0"
      },
      "ttl": 30,
      "last_heartbeat": 1617293054,
      "health": "passing"
    },
    ...  // ... more services
  ]
}
```

#### Discover Service

```json
{
  "action": "discover",
  "service_type": "web"
}
```

Response:

```json
{
  "success": true,
  "service": {
    "id": "service-1",
    "name": "example-service",
    "host": "192.168.1.10",
    "port": 8080,
    "type": "web",
    "tags": [
      "web",
      "api"
    ],
    "metadata": {
      "version": "1.0.0"
    },
    "ttl": 30,
    "last_heartbeat": 1617293054,
    "health": "passing"
  }
}
```

#### Health Check

```json
{
  "action": "health"
}
```

Response:

```json
{
  "success": true,
  "status": "ok",
  "timestamp": 1617293054
}
```

### Event Broadcasting

The server publishes events to its PUB socket whenever services are registered,
deregistered, or expire. Events have the following format:

```json
{
  "type": "register",  // or "deregister", "expire"
  "timestamp": 1617293054,
  "data": {
    "service_id": "service-1",
    "service_info": {
      ... // Service information
    }
  }
}
```

Clients can subscribe to these events to maintain a local cache of service
information.

## Service Discovery Patterns

### Load Balancing

The `discover_service` action implements a simple load balancing strategy by
default, returning a random healthy service of the requested type. For more
advanced load balancing strategies, we could:

1. Extend `AsyncRegistryBackend` with custom discovery logic
2. Implement client-side load balancing in your service clients
3. Use a dedicated load balancer in front of your services

### Circuit Breaking

When services become unhealthy (failing to send heartbeats), they will be
automatically marked as "critical" and excluded from discovery results. This
provides a basic circuit breaking mechanism.

## Troubleshooting

### "Resource temporarily unavailable" Error

This typically indicates a ZeroMQ socket is in an invalid state or connection
issues:

- Ensure ports are not in use by other applications
- Check network connectivity between services
- Use longer timeouts for high-latency environments

### Services Not Being Discovered

If services register successfully but can't be discovered:

- Verify services are sending heartbeats regularly
- Check that services include the proper type and tags
- Ensure TTL values are appropriate for your environment

## Performance Considerations

### Scaling

For high-scale deployments:

- Use a more robust backend like a dedicated database server
- Deploy multiple registry servers behind a load balancer

### Resource Usage

The server's resource consumption is primarily affected by:

- Number of registered services
- Frequency of service heartbeats
- Cleanup interval for expired services

For large deployments, monitor memory usage and adjust these parameters
accordingly.

### ZeroMQ Socket Configuration

For high-throughput environments, consider tuning ZeroMQ socket options:

```python
socket.setsockopt(zmq.RCVHWM, 10000)  # Receive high-water mark
socket.setsockopt(zmq.SNDHWM, 10000)  # Send high-water mark
```

## Security Considerations

The basic implementation does not include authentication or encryption. For
production use, consider:

- Using ZeroMQ's built-in security mechanisms (CurveZMQ)
- Placing the registry server in a secure network segment
- Implementing application-level authentication for service registration

Example with CurveZMQ (requires additional setup):

```python
public_key, secret_key = zmq.curve_keypair()
socket.setsockopt(zmq.CURVE_SECRETKEY, secret_key)
socket.setsockopt(zmq.CURVE_PUBLICKEY, public_key)
socket.setsockopt(zmq.CURVE_SERVER, True)
```
