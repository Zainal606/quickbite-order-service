"""HTTP client for the restaurant service.

The order service never reads the restaurant database. It asks the restaurant
service over REST, with a short timeout and a small number of retries so a
slow or restarting pod does not hang the order request.
"""
import logging
import os

import httpx

log = logging.getLogger("order-service")

RESTAURANT_SERVICE_URL = os.getenv("RESTAURANT_SERVICE_URL", "http://localhost:8001").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("RESTAURANT_TIMEOUT_SECONDS", "3"))
RETRIES = int(os.getenv("RESTAURANT_RETRIES", "2"))


class RestaurantNotFound(Exception):
    pass


class RestaurantServiceUnavailable(Exception):
    pass


def fetch_restaurant(restaurant_id: int) -> dict:
    """Return the restaurant with its menu, as served by GET /restaurants/{id}."""
    url = f"{RESTAURANT_SERVICE_URL}/restaurants/{restaurant_id}"
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 2):
        try:
            response = httpx.get(url, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last_error = exc
            log.warning("restaurant service call failed (attempt %s): %s", attempt, exc.__class__.__name__)
            continue
        if response.status_code == 404:
            raise RestaurantNotFound(restaurant_id)
        if response.status_code >= 500:
            last_error = RuntimeError(f"HTTP {response.status_code}")
            log.warning("restaurant service returned %s (attempt %s)", response.status_code, attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RestaurantServiceUnavailable(str(last_error))


def is_reachable() -> bool:
    try:
        return httpx.get(f"{RESTAURANT_SERVICE_URL}/health", timeout=TIMEOUT_SECONDS).status_code == 200
    except httpx.HTTPError:
        return False
