"""delivery-lab: REST API for deliveries (FastAPI)."""
import threading
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="delivery-lab")

deliveries = {}          # id -> {"id", "recipient", "address", "status"}
next_id = 1
lock = threading.Lock()  # sync endpoints run in a thread pool: protect shared state

STATUSES = ["created", "in_transit", "delivered"]
NEXT_STATUS = {"created": "in_transit", "in_transit": "delivered"}


# --- every error is {"error": "..."} -------------------------------------
@app.exception_handler(StarletteHTTPException)
def http_error(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
def validation_error(request, exc):
    return JSONResponse({"error": "invalid request"}, status_code=400)


def non_empty_string(value):
    return isinstance(value, str) and value.strip() != ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/deliveries", status_code=201)
def create_delivery(data: dict = Body(...)):
    global next_id
    if not non_empty_string(data.get("recipient")):
        raise HTTPException(400, "'recipient' must be a non-empty string")
    if not non_empty_string(data.get("address")):
        raise HTTPException(400, "'address' must be a non-empty string")
    with lock:
        delivery = {"id": next_id, "recipient": data["recipient"],
                    "address": data["address"], "status": "created"}
        deliveries[next_id] = delivery
        next_id += 1
    return delivery


@app.get("/deliveries")
def list_deliveries(status: Optional[str] = None):
    if status is not None and status not in STATUSES:
        raise HTTPException(400, f"'status' must be one of {STATUSES}")
    with lock:
        return [d for d in deliveries.values() if status is None or d["status"] == status]


@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: int):
    with lock:
        delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise HTTPException(404, "delivery not found")
    return delivery


@app.patch("/deliveries/{delivery_id}/status")
def update_status(delivery_id: int, data: dict = Body(...)):
    if data.get("status") not in STATUSES:
        raise HTTPException(400, f"'status' must be one of {STATUSES}")
    with lock:
        delivery = deliveries.get(delivery_id)
        if delivery is None:
            raise HTTPException(404, "delivery not found")
        if NEXT_STATUS.get(delivery["status"]) != data["status"]:
            raise HTTPException(409, f"cannot move from {delivery['status']} to {data['status']}")
        delivery["status"] = data["status"]
        return delivery


@app.delete("/deliveries/{delivery_id}", status_code=204)
def delete_delivery(delivery_id: int):
    with lock:
        delivery = deliveries.get(delivery_id)
        if delivery is None:
            raise HTTPException(404, "delivery not found")
        if delivery["status"] != "created":
            raise HTTPException(409, "only deliveries in status 'created' can be deleted")
        del deliveries[delivery_id]
    return Response(status_code=204)