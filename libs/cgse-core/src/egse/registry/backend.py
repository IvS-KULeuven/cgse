"""
Asynchronous Registry Backend Protocol and Implementations.

This file defines:
1. A Protocol for async registry backends
2. The AsyncSQLiteBackend implementation
3. The AsyncInMemoryBackend for testing
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from typing import Protocol
from typing import runtime_checkable

import aiosqlite

from egse.decorators import implements_protocol
from egse.registry import logger


@runtime_checkable
class AsyncRegistryBackend(Protocol):
    """Protocol defining the interface for asynchronous registry backends."""

    async def initialize(self) -> None:
        """Initialize the backend."""
        ...

    async def close(self) -> None:
        """Close the backend and release resources."""
        ...

    async def clean_expired_services(self) -> list[str]:
        """
        Remove services that haven't sent a heartbeat within their TTL.

        Returns:
            List of service IDs that were removed.
        """
        ...

    async def register(self, service_id: str, service_info: dict[str, Any], ttl: int = 30) -> bool:
        """
        Register a service with the registry.

        FIXME: describe what is mandatory in the service_info dictionary.

        Args:
            service_id: Unique identifier for the service
            service_info: Service information (host, port, metadata, etc.)
            ttl: Time to live in seconds

        Returns:
            True if registration was successful, False otherwise
        """
        ...

    async def deregister(self, service_id: str) -> bool:
        """
        Remove a service from the registry.

        Args:
            service_id: Unique identifier for the service

        Returns:
            True if de-registration was successful, False otherwise
        """
        ...

    async def renew(self, service_id: str) -> bool:
        """
        Renew a service's TTL in the registry.

        Args:
            service_id: Unique identifier for the service

        Returns:
            True if renewal was successful, False otherwise
        """
        ...

    async def get_service(self, service_id: str) -> dict[str, Any] | None:
        """
        Get information about a specific service.

        Args:
            service_id: Unique identifier for the service

        Returns:
            Service information or None if not found
        """
        ...

    async def list_services(self, service_type: str | None = None) -> list[dict[str, Any]]:
        """
        List all registered services, optionally filtered by type.

        Args:
            service_type: Optional service type to filter by

        Returns:
            List of service information dictionaries
        """
        ...

    async def discover_service(self, service_type: str) -> dict[str, Any] | None:
        """
        Find a healthy service of the specified type using load balancing.

        Args:
            service_type: Type of service to discover

        Returns:
            Service information or None if no healthy service is found
        """
        ...


@implements_protocol(AsyncRegistryBackend)
class AsyncSQLiteBackend:
    """Asynchronous persistent storage backend using SQLite."""

    def __init__(self, db_path: str = "service_registry.db"):
        """
        Initialize the SQLite backend.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.logger = logger
        self._lock = asyncio.Lock()
        self._db = None

    async def initialize(self) -> None:
        """Initialize the database connection and schema."""
        self._db = await aiosqlite.connect(self.db_path)

        # Enable WAL mode for better concurrency
        await self._db.execute("PRAGMA journal_mode=WAL")

        # Initialize schema
        await self._init_db()

        self.logger.info(f"SQLite backend initialized with database: {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            self.logger.info("SQLite backend closed")

    @asynccontextmanager
    async def _db_cursor(self):
        """Async context manager for database operations with automatic commit/rollback."""
        async with self._lock:  # Ensure thread safety
            try:
                cursor = await self._db.cursor()
                yield cursor
                await self._db.commit()
            except Exception as exc:
                await self._db.rollback()
                self.logger.error(f"Database error: {exc}")
                raise

    async def _init_db(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        async with self._db_cursor() as cursor:
            # Create services table
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS services (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    metadata TEXT,
                    ttl INTEGER NOT NULL,
                    last_heartbeat INTEGER NOT NULL,
                    tags TEXT
                )
                """
            )

    async def clean_expired_services(self) -> list[str]:
        """Remove services that haven't sent a heartbeat within their TTL."""
        current_time = int(time.time())

        async with self._db_cursor() as cursor:
            # Find expired services first (for return value)
            await cursor.execute(
                """
                SELECT id FROM services 
                WHERE last_heartbeat + ttl < ?
                """,
                (current_time,),
            )

            expired_ids = [row[0] async for row in cursor]

            # Then delete them
            if expired_ids:
                await cursor.execute(
                    """
                    DELETE FROM services 
                    WHERE last_heartbeat + ttl < ?
                    """,
                    (current_time,),
                )

                self.logger.info(f"Cleaned up {len(expired_ids)} expired services")

            return expired_ids

    async def register(self, service_id: str, service_info: dict[str, Any], ttl: int = 30) -> bool:
        """Register a service with the registry."""
        try:
            current_time = int(time.time())

            # Prepare data for insertion
            name = service_info.get("name", service_id)
            host = service_info.get("host", "127.0.0.1")
            port = service_info.get("port", 8000)

            metadata = service_info.get("metadata", {}).copy()
            tags = service_info.get("tags", []).copy()
            service_type = service_info.get("type")

            if service_type:
                if service_type not in tags:
                    tags.append(service_type)
                if "type" in metadata:
                    self.logger.warning(
                        f"The 'type' key is found in both 'service_info' ({service_type}) and 'metadata' "
                        f"({metadata['type']}), overwriting in 'metadata."
                    )
                metadata["type"] = service_info["type"]

            # Convert metadata and tags to JSON strings
            metadata_json = json.dumps(metadata)
            tags_json = json.dumps(tags)

            async with self._db_cursor() as cursor:
                # Check if service already exists
                await cursor.execute("SELECT id FROM services WHERE id = ?", (service_id,))
                exists = await cursor.fetchone() is not None

                if exists:
                    # Update existing service
                    await cursor.execute(
                        """
                        UPDATE services
                        SET name = ?, host = ?, port = ?, metadata = ?, 
                            ttl = ?, last_heartbeat = ?, tags = ?
                        WHERE id = ?
                        """,
                        (name, host, port, metadata_json, ttl, current_time, tags_json, service_id),
                    )
                else:
                    # Insert new service
                    await cursor.execute(
                        """
                        INSERT INTO services 
                        (id, name, host, port, metadata, ttl, last_heartbeat, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (service_id, name, host, port, metadata_json, ttl, current_time, tags_json),
                    )

            return True
        except Exception as exc:
            self.logger.error(f"Failed to register service {service_id}: {exc}")
            return False

    async def deregister(self, service_id: str) -> bool:
        """Remove a service from the registry."""
        try:
            async with self._db_cursor() as cursor:
                await cursor.execute("DELETE FROM services WHERE id = ?", (service_id,))
                return cursor.rowcount > 0
        except Exception as exc:
            self.logger.error(f"Failed to deregister service {service_id}: {exc}")
            return False

    async def renew(self, service_id: str) -> bool:
        """Renew a service's TTL in the registry."""
        try:
            current_time = int(time.time())

            async with self._db_cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE services
                    SET last_heartbeat = ?
                    WHERE id = ?
                    """,
                    (current_time, service_id),
                )

                return cursor.rowcount > 0
        except Exception as exc:
            self.logger.error(f"Failed to renew service {service_id}: {exc}")
            return False

    async def get_service(self, service_id: str) -> dict[str, Any] | None:
        """Get information about a specific service."""
        try:
            async with self._db_cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, name, host, port, metadata, ttl, last_heartbeat, tags
                    FROM services
                    WHERE id = ?
                    """,
                    (service_id,),
                )

                row = await cursor.fetchone()

                if row:
                    current_time = int(time.time())
                    return {
                        "id": row[0],
                        "name": row[1],
                        "host": row[2],
                        "port": row[3],
                        "metadata": json.loads(row[4]) if row[4] else {},
                        "ttl": row[5],
                        "last_heartbeat": row[6],
                        "tags": json.loads(row[7]) if row[7] else [],
                        "health": "passing" if current_time - row[6] <= row[5] else "critical",
                    }

                return None
        except Exception as exc:
            self.logger.error(f"Failed to get service {service_id}: {exc}")
            return None

    async def list_services(self, service_type: str | None = None) -> list[dict[str, Any]]:
        """List all registered services, optionally filtered by type."""
        try:
            async with self._db_cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT id, name, host, port, metadata, ttl, last_heartbeat, tags
                    FROM services
                    """
                )

                services = []
                current_time = int(time.time())

                async for row in cursor:
                    tags = json.loads(row[7]) if row[7] else []
                    metadata = json.loads(row[4]) if row[4] else {}

                    # Check if we need to filter by service type
                    if service_type and service_type not in tags and metadata.get("type") != service_type:
                        continue

                    services.append(
                        {
                            "id": row[0],
                            "name": row[1],
                            "host": row[2],
                            "port": row[3],
                            "metadata": metadata,
                            "ttl": row[5],
                            "last_heartbeat": row[6],
                            "tags": tags,
                            "health": "passing" if current_time - row[6] <= row[5] else "critical",
                        }
                    )

                return services
        except Exception as exc:
            self.logger.error(f"Failed to list services: {exc}")
            return []

    async def discover_service(self, service_type: str) -> dict[str, Any] | None:
        """Find a healthy service of the specified type using load balancing."""
        services = await self.list_services(service_type)

        # Filter only healthy services
        healthy_services = [s for s in services if s.get("health") == "passing"]

        if healthy_services:
            # Simple load balancing - random selection
            import random

            return random.choice(healthy_services)

        return None


@implements_protocol(AsyncRegistryBackend)
class AsyncInMemoryBackend:
    """
    In-memory backend implementation for testing or simple deployments.

    This backend keeps all service information in memory and is not persistent
    between restarts.
    """

    def __init__(self):
        """Initialize the in-memory backend."""
        self.logger = logger
        self._services = {}  # Dictionary to store services
        self._lock = asyncio.Lock()  # Async lock for thread safety

    async def initialize(self) -> None:
        """Initialize the backend (no-op for in-memory)."""
        self.logger.info("In-memory backend initialized")

    async def close(self) -> None:
        """Close the backend (no-op for in-memory)."""
        self.logger.info("In-memory backend closed")

    async def clean_expired_services(self) -> list[str]:
        """Remove services that haven't sent a heartbeat within their TTL.

        Returns:
            A list of the expired and removed id's.
        """
        current_time = int(time.time())
        expired_ids = []

        async with self._lock:
            for service_id, service_data in list(self._services.items()):
                last_heartbeat = service_data.get("last_heartbeat", 0)
                ttl = service_data.get("ttl", 30)

                if current_time - last_heartbeat > ttl:
                    expired_ids.append(service_id)
                    del self._services[service_id]

        if expired_ids:
            self.logger.info(f"Cleaned up {len(expired_ids)} expired services")

        return expired_ids

    async def register(self, service_id: str, service_info: dict[str, Any], ttl: int = 30) -> bool:
        """Register a service with the registry.

        Returns:
            True when the service was properly registered, False is an error occurred.
        """
        try:
            current_time = int(time.time())

            self.logger.info(f"{service_id}: {service_info = }")

            # Make a deepcopy of the service_info
            service_data = json.loads(json.dumps(service_info.copy()))

            # Add TTL and heartbeat information
            service_data["ttl"] = ttl
            service_data["last_heartbeat"] = current_time

            if "metadata" not in service_data:
                service_data["metadata"] = {}
            if "tags" not in service_data:
                service_data["tags"] = []

            # Always add service_type to tags (used for discovery) and to metadata
            service_type = service_data.get("type")
            if service_type:
                if service_type not in service_data["tags"]:
                    service_data["tags"].append(service_type)
                if "type" in service_data["metadata"]:
                    self.logger.warning(
                        f"The 'type' key is found in both 'service_info' ({service_type}) and 'metadata' "
                        f"({service_data['metadata']['type']}), overwriting in 'metadata."
                    )

                service_data["metadata"]["type"] = service_type

            async with self._lock:
                self._services[service_id] = service_data
                self.logger.info(f"{service_id}: {service_data = }")

            return True
        except Exception as exc:
            self.logger.error(f"Failed to register service {service_id}: {exc}")
            return False

    async def deregister(self, service_id: str) -> bool:
        """Remove a service from the registry.

        Returns:
            True when the service was properly de-registered, False when an error
                occurred or when the `service_id` was not found.
        """
        try:
            async with self._lock:
                if service_id in self._services:
                    del self._services[service_id]
                    return True
                return False
        except Exception as exc:
            self.logger.error(f"Failed to deregister service {service_id}: {exc}")
            return False

    async def renew(self, service_id: str) -> bool:
        """Renew a service's TTL in the registry.

        Returns:
            True when the new TTL could be set, False if an error occurred or when
                the `service_id` was not found.
        """
        try:
            current_time = int(time.time())

            async with self._lock:
                if service_id in self._services:
                    self._services[service_id]["last_heartbeat"] = current_time
                    return True
                return False
        except Exception as exc:
            self.logger.error(f"Failed to renew service {service_id}: {exc}")
            return False

    async def get_service(self, service_id: str) -> dict[str, Any] | None:
        """Get information about a specific service.

        Returns:
            A dictionary with information about the service, or None when an
                error occurred or the `service_id` could not be found.
        """
        try:
            async with self._lock:
                if service_id in self._services:
                    service_data = self._services[service_id].copy()

                    # Add the ID to the service data (this was missing!)
                    service_data["id"] = service_id

                    # Add health status
                    current_time = int(time.time())
                    last_heartbeat = service_data.get("last_heartbeat", 0)
                    ttl = service_data.get("ttl", 30)
                    service_data["health"] = "passing" if current_time - last_heartbeat <= ttl else "critical"

                    return service_data
                return None
        except Exception as exc:
            self.logger.error(f"Failed to get service {service_id}: {exc}")
            return None

    async def list_services(self, service_type: str | None = None) -> list[dict[str, Any]]:
        """List all registered services, optionally filtered by type.

        Returns:
            A list of dictionaries containing information about the services that
                are registered. An empty list is returned whn no services are registered
                or when an error occurred.
        """
        try:
            services = []
            current_time = int(time.time())

            async with self._lock:
                for service_id, service_data in self._services.items():
                    # Make a copy to avoid modifying the original
                    service = service_data.copy()

                    # Add health status
                    last_heartbeat = service.get("last_heartbeat", 0)
                    ttl = service.get("ttl", 30)
                    service["health"] = "passing" if current_time - last_heartbeat <= ttl else "critical"

                    # Check if we need to filter by service type
                    if service_type:
                        tags = service.get("tags", [])
                        metadata = service.get("metadata", {})

                        if service_type not in tags and metadata.get("type") != service_type:
                            continue

                    services.append(service)

            return services
        except Exception as exc:
            self.logger.error(f"Failed to list services: {exc}")
            return []

    async def discover_service(self, service_type: str) -> dict[str, Any] | None:
        """
        Find a healthy service of the specified type using load balancing.

        Only healthy services will be returned, and if more than one healthy service exists
        for the given service_type, ony of them will be returned by random choice.

        Returns:
            A dictionary with the information for the service. If no healthy service is
                available for the given service type, None will be returned.
        """
        services = await self.list_services(service_type)

        # Filter only healthy services
        healthy_services = [s for s in services if s.get("health") == "passing"]

        if healthy_services:
            # Simple load balancing - pick one of the services by random selection
            # In practice, there will be only one service of a given type, but if you
            # need to get your hands on all services of that type, use `list_services()`.
            import random

            return random.choice(healthy_services)

        return None
