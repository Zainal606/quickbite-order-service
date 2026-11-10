"""QuickBite order service: places orders and tracks them to delivery."""
import logging
import socket
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import models, restaurant_client, schemas
from .database import get_db, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("order-service")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="QuickBite Order Service",
    description="Owns orders. Validates each order against the restaurant service before saving it.",
    version="1.0.0",
    lifespan=lifespan,
)


def _order_or_404(db: Session, order_id: int) -> models.Order:
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
    return order


def _change_status(db: Session, order: models.Order, new_status: schemas.OrderStatus) -> models.Order:
    current = schemas.OrderStatus(order.status)
    if new_status not in schemas.ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Order {order.id} cannot move from {current.value} to {new_status.value}",
        )
    order.status = new_status.value
    db.commit()
    log.info("order id=%s status %s -> %s", order.id, current.value, new_status.value)
    return order


@app.get("/health", tags=["ops"])
def health(db: Session = Depends(get_db)):
    """Liveness and readiness check. `served_by` shows which pod answered."""
    db.execute(text("SELECT 1"))
    return {"service": "order-service", "status": "UP", "served_by": socket.gethostname()}


@app.get("/health/dependencies", tags=["ops"])
def dependencies():
    """Reports whether the restaurant service can be reached from this pod."""
    return {
        "restaurant_service_url": restaurant_client.RESTAURANT_SERVICE_URL,
        "restaurant_service": "UP" if restaurant_client.is_reachable() else "DOWN",
    }


# ---------- commands ----------

@app.post("/orders", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED, tags=["orders"])
def place_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    """Place an order.

    The restaurant, its opening status, each item's availability and the
    prices all come from the restaurant service. The client never sends a price.
    """
    try:
        restaurant = restaurant_client.fetch_restaurant(payload.restaurant_id)
    except restaurant_client.RestaurantNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Restaurant {payload.restaurant_id} not found")
    except restaurant_client.RestaurantServiceUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Restaurant service is unavailable, please retry shortly",
        )

    if not restaurant["is_open"]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{restaurant['name']} is closed")

    menu = {item["id"]: item for item in restaurant["menu"]}
    quantities: dict[int, int] = {}
    for line in payload.items:
        quantities[line.menu_item_id] = quantities.get(line.menu_item_id, 0) + line.quantity

    order_items = []
    for menu_item_id, quantity in quantities.items():
        menu_item = menu.get(menu_item_id)
        if menu_item is None:
            raise HTTPException(
                422,
                f"Menu item {menu_item_id} is not on the menu of {restaurant['name']}",
            )
        if not menu_item["is_available"]:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{menu_item['name']} is currently unavailable")
        order_items.append(
            models.OrderItem(
                menu_item_id=menu_item_id,
                name=menu_item["name"],
                unit_price=menu_item["price"],
                quantity=quantity,
            )
        )

    order = models.Order(
        customer_name=payload.customer_name,
        delivery_address=payload.delivery_address,
        restaurant_id=restaurant["id"],
        restaurant_name=restaurant["name"],
        status=schemas.OrderStatus.PLACED.value,
        total_amount=round(sum(i.unit_price * i.quantity for i in order_items), 2),
        items=order_items,
    )
    db.add(order)
    db.commit()
    log.info("order placed id=%s restaurant=%s total=%.2f", order.id, order.restaurant_id, order.total_amount)
    return order


@app.patch("/orders/{order_id}/status", response_model=schemas.OrderOut, tags=["orders"])
def update_order_status(order_id: int, payload: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    return _change_status(db, _order_or_404(db, order_id), payload.status)


@app.post("/orders/{order_id}/cancel", response_model=schemas.OrderOut, tags=["orders"])
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    return _change_status(db, _order_or_404(db, order_id), schemas.OrderStatus.CANCELLED)


# ---------- queries ----------

@app.get("/orders", response_model=list[schemas.OrderOut], tags=["orders"])
def list_orders(
    customer_name: str | None = Query(default=None, description="Order history of one customer"),
    restaurant_id: int | None = Query(default=None, description="Orders received by one restaurant"),
    order_status: schemas.OrderStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    query = select(models.Order).order_by(models.Order.id.desc())
    if customer_name:
        query = query.where(models.Order.customer_name.ilike(customer_name))
    if restaurant_id is not None:
        query = query.where(models.Order.restaurant_id == restaurant_id)
    if order_status is not None:
        query = query.where(models.Order.status == order_status.value)
    return db.scalars(query).all()


@app.get("/orders/{order_id}", response_model=schemas.OrderOut, tags=["orders"])
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _order_or_404(db, order_id)
