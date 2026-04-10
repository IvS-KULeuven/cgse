import asyncio
import contextlib
import logging
import random
import time
import uuid

import pytest
from egse.system import Timer
from egse.system import type_name

from egse.notifyhub import async_is_notify_hub_active
from egse.notifyhub import is_notify_hub_active
from egse.notifyhub.server import AsyncNotificationHub
from egse.notifyhub.services import ServiceMessaging

pytestmark = pytest.mark.skipif(
    is_notify_hub_active(), reason="The notification hub shall NOT be running for this test."
)


@contextlib.asynccontextmanager
async def async_notify_hub():
    """Asynchronous context manager that starts a notification hub as an asyncio Task."""

    if await async_is_notify_hub_active():
        pytest.xfail("The notification hub shall not be running for this test.")

    server = AsyncNotificationHub()
    server_task = asyncio.create_task(server.start())

    with Timer(name="Notify Hub startup timer"):
        await asyncio.wait_for(async_is_notify_hub_active(), timeout=5.0)

    try:
        yield
    except Exception as exc:
        logging.getLogger(__name__).error(f"Caught {type_name(exc)}: {exc}", exc_info=True)

    await server.stop()

    await asyncio.gather(server_task, return_exceptions=True)

    if not server_task.done():
        server_task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await server_task


class UserService:
    def __init__(self):
        self.messaging = ServiceMessaging("user-service")
        self.users = {}
        self.logger = logging.getLogger("egse.user-service")

    async def create_user(self, email: str, name: str) -> str:
        """Create a user and publish event"""
        user_id = str(uuid.uuid4())

        user_data = {"id": user_id, "email": email, "name": name, "created_at": time.time()}
        self.users[user_id] = user_data

        self.logger.info(f"Created user: {name} ({email})")

        await self.messaging.publish_event("user_created", {"user_id": user_id, "email": email, "name": name})

        return user_id

    async def update_user(self, user_id: str, updates: dict):
        """Update user and publish event"""
        if user_id not in self.users:
            raise ValueError("User not found")

        self.users[user_id].update(updates)

        await self.messaging.publish_event("user_updated", {"user_id": user_id, "updates": updates})

    async def close(self):
        self.messaging.disconnect()


class EmailService:
    def __init__(self):
        self.messaging = ServiceMessaging(
            "email-service", subscriptions=["user_created", "user_updated", "order_placed"]
        )

        self.messaging.register_handler("user_created", self.handle_user_created)
        self.messaging.register_handler("user_updated", self.handle_user_updated)
        self.messaging.register_handler("order_placed", self.handle_order_placed)

        self.logger = logging.getLogger("egse.email-service")

    async def handle_user_created(self, event_data: dict):
        """Handle new user creation"""
        user_data = event_data["data"]
        email = user_data["email"]
        name = user_data["name"]

        self.logger.info(f"Sending welcome email to {name}")

        await self._send_email(to=email, subject="Welcome!", template="welcome", data={"name": name})

    async def handle_user_updated(self, event_data: dict):
        """Handle user updates"""
        user_data = event_data["data"]
        user_id = user_data["user_id"]

        self.logger.info(f"User {user_id} was updated")

    async def handle_order_placed(self, event_data: dict):
        """Handle order placement"""
        order_data = event_data["data"]
        customer_email = order_data["customer_email"]
        order_id = order_data["order_id"]

        await self._send_email(
            to=customer_email, subject="Order Confirmation", template="order_confirmation", data={"order_id": order_id}
        )

    async def _send_email(self, to: str, subject: str, template: str, data: dict):
        """Simulate sending email"""
        await asyncio.sleep(0.1)
        self.logger.info(f"Sent '{subject}' to {to}")

    async def start(self):
        """Start listening for events"""
        await self.messaging.start_listening()

    async def close(self):
        self.messaging.disconnect()


class OrderService:
    def __init__(self):
        self.messaging = ServiceMessaging(
            "order-service",
            subscriptions=["user_created"],
        )

        self.messaging.register_handler("user_created", self.handle_new_user)

        self.orders = {}
        self.user_orders = {}
        self.logger = logging.getLogger("egse.order-service")

    async def handle_new_user(self, event_data: dict):
        """Handle new user - track them"""
        user_data = event_data["data"]
        user_id = user_data["user_id"]

        self.user_orders[user_id] = []
        self.logger.info(f"Tracking new user: {user_id}")

    async def place_order(self, user_id: str, items: list[dict], customer_email: str):
        """Place an order and publish event"""
        order_id = str(uuid.uuid4())

        order_data = {
            "id": order_id,
            "user_id": user_id,
            "items": items,
            "customer_email": customer_email,
            "total": sum(item["price"] * item["quantity"] for item in items),
            "created_at": time.time(),
        }

        self.orders[order_id] = order_data

        if user_id in self.user_orders:
            self.user_orders[user_id].append(order_id)

        self.logger.info(f"Order placed: {order_id} for user {user_id}")

        await self.messaging.publish_event(
            "order_placed",
            {"order_id": order_id, "user_id": user_id, "customer_email": customer_email, "total": order_data["total"]},
        )

        return order_id

    async def start(self):
        """Start listening for events"""
        await self.messaging.start_listening()

    async def close(self):
        self.messaging.disconnect()


class AnalyticsService:
    def __init__(self):
        self.messaging = ServiceMessaging(
            "analytics-service", subscriptions=["user_created", "order_placed", "user_updated"]
        )

        self.messaging.register_handler("user_created", self.track_user_signup)
        self.messaging.register_handler("order_placed", self.track_order)
        self.messaging.register_handler("user_updated", self.track_user_update)

        self.metrics = {"users_created": 0, "orders_placed": 0, "total_revenue": 0.0}
        self.logger = logging.getLogger("egse.analytics-service")

    async def track_user_signup(self, event_data: dict):
        """Track user signup"""
        self.metrics["users_created"] += 1
        self.logger.info(f"Users created: {self.metrics['users_created']}")

    async def track_order(self, event_data: dict):
        """Track order placement"""
        order_data = event_data["data"]
        total = order_data["total"]

        self.metrics["orders_placed"] += 1
        self.metrics["total_revenue"] += total

        self.logger.info(f"Orders: {self.metrics['orders_placed']}, Revenue: ${self.metrics['total_revenue']:.2f}")

    async def track_user_update(self, event_data: dict):
        """Track user updates"""
        self.logger.info("User update tracked")

    async def start(self):
        await self.messaging.start_listening()

    async def close(self):
        self.messaging.disconnect()


async def run_microservices_demo():
    """Run the complete microservices system"""

    user_service = UserService()
    email_service = EmailService()
    order_service = OrderService()
    analytics_service = AnalyticsService()

    tasks = [
        asyncio.create_task(email_service.start()),
        asyncio.create_task(order_service.start()),
        asyncio.create_task(analytics_service.start()),
    ]

    async def demo_workflow():
        await asyncio.sleep(1)  # Let services connect

        user1_id = await user_service.create_user("alice@example.com", "Alice Smith")
        user2_id = await user_service.create_user("bob@example.com", "Bob Jones")

        await asyncio.sleep(0.5)

        await order_service.place_order(
            user1_id, [{"name": "Widget", "price": 29.99, "quantity": 2}], "alice@example.com"
        )

        await order_service.place_order(
            user2_id, [{"name": "Gadget", "price": 19.99, "quantity": 1}], "bob@example.com"
        )

        await asyncio.sleep(0.5)

        await user_service.update_user(user1_id, {"name": "Alice Johnson"})

        await asyncio.sleep(2)

        for x in range(100):
            await order_service.place_order(
                user1_id,
                [{"name": "Widget", "price": 29.99 + x * 3.14, "quantity": random.choice([1, 2, 3, 4])}],
                "alice@example.com",
            )

            await order_service.place_order(
                user2_id,
                [{"name": "Gadget", "price": 19.99 + x * 1.23, "quantity": random.choice([1, 2, 3, 4])}],
                "bob@example.com",
            )

        await user_service.close()
        await email_service.close()
        await order_service.close()
        await analytics_service.close()

    async def _cleanup_running_tasks():
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)

    tasks.append(asyncio.create_task(demo_workflow()))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("Shutting down...")

    await _cleanup_running_tasks()


@pytest.mark.asyncio
@pytest.mark.starts_services
async def test_service_messaging():
    async with async_notify_hub():
        await run_microservices_demo()


if __name__ == "__main__":
    asyncio.run(run_microservices_demo())
