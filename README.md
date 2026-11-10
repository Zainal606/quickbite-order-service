# QuickBite Order Service

Owns orders. Before saving an order it calls the restaurant service over REST to check the restaurant is open, the items exist and are available, and to take the prices. Set `RESTAURANT_SERVICE_URL` to point it at the restaurant service (default `http://localhost:8001`).

Python 3.12, FastAPI, SQLAlchemy, PostgreSQL (SQLite for local development).

## API

| Type | Method | Path | Purpose |
|---|---|---|---|
| Command | POST | /orders | Place an order |
| Command | PATCH | /orders/{id}/status | Move an order to the next status |
| Command | POST | /orders/{id}/cancel | Cancel an order |
| Query | GET | /orders?customer_name=&restaurant_id=&status= | Order history and filters |
| Query | GET | /orders/{id} | Track one order |
| Ops | GET | /health | Health check, shows the pod that answered |
| Ops | GET | /health/dependencies | Can this pod reach the restaurant service |

Status flow: PLACED → CONFIRMED → PREPARING → OUT_FOR_DELIVERY → DELIVERED. An order can be cancelled while PLACED or CONFIRMED.

Interactive docs: `http://localhost:8002/docs`

## Project structure

```
order-service/
├── app/
│   ├── main.py          # routes (commands and queries)
│   ├── models.py        # database tables
│   ├── schemas.py       # request and response models
│   ├── restaurant_client.py  # REST client with timeout and retry
│   └── database.py      # engine, session, startup retry
├── tests/               # pytest suite
├── k8s/
│   ├── namespace.yaml
│   ├── postgres.yaml    # this service's own database
│   └── deployment.yaml  # Deployment (2 replicas) + NodePort Service
├── Dockerfile
└── requirements.txt
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
uvicorn app.main:app --port 8002
```

## Build the image

```bash
docker build -t quickbite/order-service:1.0 .
```

## Deploy to minikube

```bash
minikube image load quickbite/order-service:1.0
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/deployment.yaml
kubectl -n quickbite rollout status deployment/order-service
minikube service order-service -n quickbite --url
```

The service is exposed on NodePort 30082.
