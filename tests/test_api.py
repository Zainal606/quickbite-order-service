from app import restaurant_client

ORDER = {
    "customer_name": "Asha",
    "delivery_address": "Flat 12, Marina Heights",
    "restaurant_id": 1,
    "items": [{"menu_item_id": 10, "quantity": 2}, {"menu_item_id": 11, "quantity": 3}],
}


def _place(client, **overrides):
    return client.post("/orders", json=ORDER | overrides)


def test_place_order_uses_restaurant_prices(client):
    response = _place(client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PLACED"
    assert body["restaurant_name"] == "Spice Route"
    assert body["total_amount"] == 2 * 28.5 + 3 * 6.0
    assert [i["name"] for i in body["items"]] == ["Paneer Tikka", "Butter Naan"]


def test_duplicate_lines_are_merged(client):
    body = _place(client, items=[{"menu_item_id": 11, "quantity": 1}, {"menu_item_id": 11, "quantity": 2}]).json()
    assert body["items"] == [{"menu_item_id": 11, "name": "Butter Naan", "unit_price": 6.0, "quantity": 3}]


def test_rejects_unknown_restaurant_and_item(client):
    assert _place(client, restaurant_id=99).status_code == 404
    assert _place(client, items=[{"menu_item_id": 999, "quantity": 1}]).status_code == 422


def test_rejects_unavailable_item_and_closed_restaurant(client, restaurant):
    assert _place(client, items=[{"menu_item_id": 12, "quantity": 1}]).status_code == 409
    restaurant["is_open"] = False
    assert _place(client).status_code == 409


def test_restaurant_service_down_gives_503(client, monkeypatch):
    def down(_):
        raise restaurant_client.RestaurantServiceUnavailable("connection refused")

    monkeypatch.setattr(restaurant_client, "fetch_restaurant", down)
    assert _place(client).status_code == 503
    assert client.get("/orders").json() == []


def test_status_flow_and_invalid_transition(client):
    order_id = _place(client).json()["id"]
    for step in ["CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED"]:
        response = client.patch(f"/orders/{order_id}/status", json={"status": step})
        assert response.status_code == 200
        assert response.json()["status"] == step
    assert client.post(f"/orders/{order_id}/cancel").status_code == 409


def test_cancel_and_filters(client):
    first = _place(client).json()["id"]
    _place(client, customer_name="Ravi")
    assert client.post(f"/orders/{first}/cancel").json()["status"] == "CANCELLED"

    assert len(client.get("/orders").json()) == 2
    assert len(client.get("/orders", params={"customer_name": "ravi"}).json()) == 1
    assert len(client.get("/orders", params={"status": "CANCELLED"}).json()) == 1
    assert client.get("/orders/999").status_code == 404
