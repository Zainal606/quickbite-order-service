import os
import sys
import tempfile
from pathlib import Path

# Point the service at a throwaway SQLite file before the app is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import restaurant_client
from app.database import Base, engine
from app.main import app

RESTAURANT = {
    "id": 1,
    "name": "Spice Route",
    "cuisine": "Indian",
    "city": "Dubai",
    "is_open": True,
    "menu": [
        {"id": 10, "restaurant_id": 1, "name": "Paneer Tikka", "price": 28.5, "is_available": True},
        {"id": 11, "restaurant_id": 1, "name": "Butter Naan", "price": 6.0, "is_available": True},
        {"id": 12, "restaurant_id": 1, "name": "Mango Lassi", "price": 12.0, "is_available": False},
    ],
}


@pytest.fixture()
def restaurant(monkeypatch):
    """Stands in for the restaurant service so the order service is tested alone."""
    data = {**RESTAURANT, "menu": [dict(item) for item in RESTAURANT["menu"]]}

    def fake_fetch(restaurant_id: int) -> dict:
        if restaurant_id != data["id"]:
            raise restaurant_client.RestaurantNotFound(restaurant_id)
        return data

    monkeypatch.setattr(restaurant_client, "fetch_restaurant", fake_fetch)
    return data


@pytest.fixture()
def client(restaurant):
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
