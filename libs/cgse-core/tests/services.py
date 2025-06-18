import asyncio
import logging
import signal
import sys
import time
from typing import Any

from egse.registry.service import ZMQMicroservice

module_logger_name = "example-services"
logger = logging.getLogger(module_logger_name)


class UserService(ZMQMicroservice):
    """
    User management microservice.

    This service provides user-related functionality:
    - User lookup
    - User registration
    - User authentication
    """

    def __init__(self, rep_port: int = 0, pub_port: int = 0):
        super().__init__(
            service_name="user-service",
            service_type="user-service",
            rep_port=rep_port,
            pub_port=pub_port,
            metadata={"version": "1.0.0"},
        )

        self.logger = logging.getLogger(f"{module_logger_name}.user")

        # Mock user database
        self.users = {
            "user1": {"id": "user1", "name": "John Doe", "email": "john@example.com"},
            "user2": {"id": "user2", "name": "Jane Smith", "email": "jane@example.com"},
            "user3": {"id": "user3", "name": "Bob Johnson", "email": "bob@example.com"},
        }

        self.register_handler("get_user", self._handle_get_user)
        self.register_handler("list_users", self._handle_list_users)
        self.register_handler("create_user", self._handle_create_user)

    async def _handle_get_user(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle get_user command."""
        user_id = data.get("user_id")

        if not user_id:
            return {"status": "error", "error": "Missing user_id"}

        user = self.users.get(user_id)

        if not user:
            return {"status": "error", "error": "User not found"}

        return {"status": "ok", "user": user}

    async def _handle_list_users(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle list_users command."""
        return {"status": "ok", "users": list(self.users.values())}

    async def _handle_create_user(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle create_user command."""
        user_data = data.get("user")

        if not user_data or not isinstance(user_data, dict):
            return {"status": "error", "error": "Invalid user data"}

        required_fields = ["name", "email"]
        for field in required_fields:
            if field not in user_data:
                return {"status": "error", "error": f"Missing required field: {field}"}

        # Generate ID
        user_id = f"user{len(self.users) + 1}"

        # Create user
        user = {"id": user_id, "name": user_data["name"], "email": user_data["email"]}

        # Add to database
        self.users[user_id] = user

        # Publish event
        await self.publish_event("user_created", {"user": user})

        return {"status": "ok", "user": user}


class ProductService(ZMQMicroservice):
    """
    Product catalog microservice.

    This service provides product-related functionality:
    - Product lookup
    - Product listing
    - Product search
    """

    def __init__(self, rep_port: int = 0, pub_port: int = 0):
        super().__init__(
            service_name="product-service",
            service_type="product-service",
            rep_port=rep_port,
            pub_port=pub_port,
            metadata={"version": "1.0.0"},
        )

        self.logger = logging.getLogger(f"{module_logger_name}.product")

        # Mock product database
        self.products = {
            "prod1": {"id": "prod1", "name": "Laptop", "price": 999.99, "category": "electronics"},
            "prod2": {"id": "prod2", "name": "Smartphone", "price": 699.99, "category": "electronics"},
            "prod3": {"id": "prod3", "name": "Headphones", "price": 199.99, "category": "accessories"},
        }

        # Register handlers
        self.register_handler("get_product", self._handle_get_product)
        self.register_handler("list_products", self._handle_list_products)
        self.register_handler("search_products", self._handle_search_products)

    async def _handle_get_product(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle get_product command."""
        product_id = data.get("product_id")

        if not product_id:
            return {"status": "error", "error": "Missing product_id"}

        product = self.products.get(product_id)

        if not product:
            return {"status": "error", "error": "Product not found"}

        return {"status": "ok", "product": product}

    async def _handle_list_products(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle list_products command."""
        category = data.get("category")

        if category:
            # Filter by category
            products = [p for p in self.products.values() if p.get("category") == category]
        else:
            # Return all products
            products = list(self.products.values())

        return {"status": "ok", "products": products}

    async def _handle_search_products(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle search_products command."""
        query = data.get("query", "").lower()

        if not query:
            return {"status": "error", "error": "Missing query parameter"}

        # Simple search implementation
        results = [
            p for p in self.products.values() if query in p["name"].lower() or query in p.get("category", "").lower()
        ]

        return {"status": "ok", "results": results}


class OrderService(ZMQMicroservice):
    """
    Order processing microservice.

    This service provides order-related functionality:
    - Create orders
    - Get order status
    - List user orders

    It demonstrates communication with other services.
    """

    def __init__(self, rep_port: int = 0, pub_port: int = 0):
        super().__init__(
            service_name="order-service",
            service_type="order-service",
            rep_port=rep_port,
            pub_port=pub_port,
            metadata={"version": "1.0.0"},
        )

        self.logger = logging.getLogger(f"{module_logger_name}.order")

        # Mock order database
        self.orders = {}
        self.next_order_id = 1

        # Register handlers
        self.register_handler("create_order", self._handle_create_order)
        self.register_handler("get_order", self._handle_get_order)
        self.register_handler("list_user_orders", self._handle_list_user_orders)

    async def _handle_create_order(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle create_order command."""
        user_id = data.get("user_id")
        product_ids = data.get("product_ids", [])

        if not user_id:
            return {"status": "error", "error": "Missing user_id"}

        if not product_ids or not isinstance(product_ids, list):
            return {"status": "error", "error": "Invalid product_ids"}

        try:
            # Verify user exists
            try:
                user_response = await self.call_service("user-service", "get_user", {"user_id": user_id})

                if user_response.get("status") != "ok":
                    return {"status": "error", "error": f"Invalid user: {user_response.get('error')}"}

                user = user_response.get("user")
            except Exception as exc:
                self.logger.error(f"Error calling user service: {exc}")
                return {"status": "error", "error": "User service unavailable"}

            # Verify products exist and get details
            products = []
            total_price = 0.0

            for product_id in product_ids:
                try:
                    product_response = await self.call_service(
                        "product-service", "get_product", {"product_id": product_id}
                    )

                    if product_response.get("status") != "ok":
                        return {
                            "status": "error",
                            "error": f"Invalid product {product_id}: {product_response.get('error')}",
                        }

                    product = product_response.get("product")
                    products.append(product)
                    total_price += product.get("price", 0.0)
                except Exception as exc:
                    self.logger.error(f"Error calling product service: {exc}")
                    return {"status": "error", "error": "Product service unavailable"}

            # Create the order
            order_id = f"order{self.next_order_id}"
            self.next_order_id += 1

            order = {
                "id": order_id,
                "user_id": user_id,
                "user_name": user.get("name"),
                "products": products,
                "total_price": total_price,
                "status": "created",
                "created_at": time.time(),
            }

            # Save the order
            self.orders[order_id] = order

            # Publish event
            await self.publish_event("order_created", {"order": order})

            return {"status": "ok", "order": order}
        except Exception as exc:
            self.logger.error(f"Error creating order: {exc}")
            return {"status": "error", "error": str(exc)}

    async def _handle_get_order(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle get_order command."""
        order_id = data.get("order_id")

        if not order_id:
            return {"status": "error", "error": "Missing order_id"}

        order = self.orders.get(order_id)

        if not order:
            return {"status": "error", "error": "Order not found"}

        return {"status": "ok", "order": order}

    async def _handle_list_user_orders(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle list_user_orders command."""
        user_id = data.get("user_id")

        if not user_id:
            return {"status": "error", "error": "Missing user_id"}

        # Find all orders for the user
        user_orders = [order for order in self.orders.values() if order.get("user_id") == user_id]

        return {"status": "ok", "orders": user_orders}


async def run_service(service_class, **kwargs):
    """
    Run a service with proper signal handling.

    Args:
        service_class: Service class to instantiate
        **kwargs: Arguments for the service constructor
    """
    # Create the service
    service = service_class(**kwargs)

    # Set up signal handlers
    loop = asyncio.get_running_loop()

    def signal_handler():
        asyncio.create_task(service.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # Start the service
    await service.start()


def main():
    import argparse

    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-21s %(lineno)5d:%(module)-20s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run a ZeroMQ-based microservice")
    parser.add_argument("service", choices=["user", "product", "order"], help="Service to run")
    parser.add_argument("--rep-port", type=int, help="REP socket port")
    parser.add_argument("--pub-port", type=int, help="PUB socket port")

    args = parser.parse_args()

    service_kwargs = {}
    if args.rep_port:
        service_kwargs["rep_port"] = args.rep_port
    if args.pub_port:
        service_kwargs["pub_port"] = args.pub_port

    if args.service == "user":
        asyncio.run(run_service(UserService, **service_kwargs))
    elif args.service == "product":
        asyncio.run(run_service(ProductService, **service_kwargs))
    elif args.service == "order":
        asyncio.run(run_service(OrderService, **service_kwargs))


if __name__ == "__main__":
    sys.exit(main())
