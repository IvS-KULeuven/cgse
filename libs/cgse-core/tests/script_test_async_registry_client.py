"""
Example client for the service registry. This example app allows you to inspect
the service registry and connect to services.

Usage:
    $ uv run py tests/script_service_client.py

You will need the service registry server to be running and at least one of the
services in the `services.py` module, user, product, or order.

The server can be started with:
    $ uv run py -m egse.registry.server

The microservices can be run with:
    $ uv run tests/services.py user
    $ uv run tests/services.py product
    $ uv run tests/services.py order

"""

import asyncio
import json
import logging

import rich
import zmq
import zmq.asyncio

from egse.registry.client import AsyncRegistryClient


async def run_async_client():
    """
    Example client that communicates with the microservices.

    This demonstrates how to call the registry service, subscribe to events and communicate with the microservice.
    """

    context = zmq.asyncio.Context()

    async def call_service(service_type, command, data=None):
        """
        Sends a command to a microservice.
        """
        registry_client = AsyncRegistryClient()
        registry_client.connect()

        try:
            service = await registry_client.discover_service(service_type)

            if not service:
                print(f"No service of type '{service_type}' found")
                return None

            rich.print(f"Information about the discovered service: {service_type}")
            rich.print(service)

            socket = context.socket(zmq.REQ)
            socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

            try:
                # Connect to the service
                socket.connect(f"tcp://{service['host']}:{service['port']}")

                # Prepare the request
                request = {"command": command, **(data or {})}

                # Send the request
                await socket.send_string(json.dumps(request))

                # Wait for the response
                response_json = await socket.recv_string()
                return json.loads(response_json)
            finally:
                socket.close()
        finally:
            await registry_client.close()
            registry_client.disconnect()

    # Function to subscribe to service events
    async def subscribe_to_events(service_type, event_types):
        # Create a registry client
        registry_client = AsyncRegistryClient()

        try:
            # Discover the service
            service = await registry_client.discover_service(service_type)

            if not service:
                print(f"No service of type '{service_type}' found")
                return

            # Get PUB port from metadata
            pub_port = service.get("metadata", {}).get("pub_port")

            if not pub_port:
                print(f"Service {service_type} does not expose a PUB socket")
                return

            # Create a SUB socket
            socket = context.socket(zmq.SUB)

            # Subscribe to specified event types
            for event_type in event_types:
                socket.setsockopt_string(zmq.SUBSCRIBE, event_type)

            # Connect to the service
            socket.connect(f"tcp://{service['host']}:{pub_port}")

            print(f"Subscribed to {service_type} events: {', '.join(event_types)}")

            try:
                while True:
                    # Wait for an event
                    event_type_bytes, event_json_bytes = await socket.recv_multipart()
                    event_type = event_type_bytes.decode("utf-8")
                    event = json.loads(event_json_bytes.decode("utf-8"))

                    print(f"\nReceived event: {event_type}")
                    print(f"Data: {json.dumps(event, indent=2)}")
            finally:
                socket.close()
        finally:
            await registry_client.close()

    print("\nZeroMQ Microservices Client")
    print("===========================")

    while True:
        print("\nAvailable actions:")
        print("1. List users")
        print("2. Get user")
        print("3. Create user")
        print("4. List products")
        print("5. Search products")
        print("6. Create order")
        print("7. Subscribe to order events")
        print("0. Exit")

        choice = input("\nEnter your choice: ")

        if choice == "0":
            break

        elif choice == "1":
            response = await call_service("user-service", "list_users")
            if response and response.get("status") == "ok":
                users = response.get("users", [])
                print("\nUsers:")
                for user in users:
                    print(f"  {user['id']}: {user['name']} ({user['email']})")
            else:
                print(f"Error: {response.get('error') if response else 'No response'}")

        elif choice == "2":
            user_id = input("Enter user ID: ")
            response = await call_service("user-service", "get_user", {"user_id": user_id})
            if response and response.get("status") == "ok":
                user = response.get("user", {})
                print(f"\nUser: {user['name']}")
                print(f"Email: {user['email']}")
            else:
                print(f"Error: {response.get('error') if response else 'No response'}")

        elif choice == "3":
            name = input("Enter user name: ")
            email = input("Enter user email: ")
            response = await call_service("user-service", "create_user", {"user": {"name": name, "email": email}})
            if response and response.get("status") == "ok":
                user = response.get("user", {})
                print(f"\nCreated user: {user['id']} - {user['name']}")
            else:
                print(f"Error: {response.get('error') if response else 'No response'}")

        elif choice == "4":
            response = await call_service("product-service", "list_products")
            if response and response.get("status") == "ok":
                products = response.get("products", [])
                print("\nProducts:")
                for product in products:
                    print(f"  {product['id']}: {product['name']} - ${product['price']} ({product['category']})")
            else:
                print(f"Error: {response.get('error') if response else 'No response'}")

        elif choice == "5":
            query = input("Enter search query: ")
            response = await call_service("product-service", "search_products", {"query": query})
            if response and response.get("status") == "ok":
                results = response.get("results", [])
                print(f"\nSearch results for '{query}':")
                for product in results:
                    print(f"  {product['id']}: {product['name']} - ${product['price']} ({product['category']})")
            else:
                print(f"Error: {response.get('error') if response else 'No response'}")

        elif choice == "6":
            user_id = input("Enter user ID: ")
            product_ids_input = input("Enter product IDs (comma-separated): ")
            product_ids = [pid.strip() for pid in product_ids_input.split(",") if pid.strip()]

            response = await call_service(
                "order-service", "create_order", {"user_id": user_id, "product_ids": product_ids}
            )

            if response and response.get("status") == "ok":
                order = response.get("order", {})
                print(f"\nCreated order: {order['id']}")
                print(f"User: {order['user_name']}")
                print(f"Products: {len(order['products'])}")
                print(f"Total: ${order['total_price']:.2f}")
            else:
                print(f"Error: {response.get('error') if response else 'No response'}")

        elif choice == "7":
            print("Subscribing to order events. Press Ctrl+C to stop.")
            try:
                await subscribe_to_events("order-service", ["order_created"])
            except KeyboardInterrupt:
                print("\nSubscription stopped.")

    # Clean up
    context.term()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-12s %(lineno)5d:%(module)-20s %(message)s",
    )

    asyncio.run(run_async_client())
