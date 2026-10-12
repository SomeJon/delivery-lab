from typing import Optional

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

deliveries = {}
next_id = 1
VALID_STATUSES = {"created", "in_transit", "delivered"}

STATUS_ORDER = {
    "created": 0,
    "in_transit": 1,
    "delivered": 2,
}

def validate_delivery_payload(payload: dict):
    if "recipient" not in payload or "address" not in payload:
        raise HTTPException(400, "recipient and address are required")

    recipient = payload["recipient"]
    address = payload["address"]

    if not isinstance(recipient, str) or not recipient.strip():
        raise HTTPException(400, "recipient must be a non-empty string")

    if not isinstance(address, str) or not address.strip():
        raise HTTPException(400, "address must be a non-empty string")

    return {
        "recipient": recipient.strip(),
        "address": address.strip(),
    }

def validate_status_transition(current_status: str, next_status: str):
    if next_status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of: {sorted(VALID_STATUSES)}")

    current_index = STATUS_ORDER.get(current_status)
    next_index = STATUS_ORDER.get(next_status)

    if current_index is None or next_index is None:
        raise HTTPException(400, "invalid current or next status")

    if next_index <= current_index:
        if current_status == next_status:
            raise HTTPException(409, "delivery already has this status")
        raise HTTPException(409, "status can only move forward through the allowed lifecycle")

    return True

@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "invalid request body"},
    )

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/deliveries", status_code=201)
def create_delivery(payload: dict = Body(...)):
    clean = validate_delivery_payload(payload)

    global next_id

    delivery = {
        "id": next_id,
        "recipient": clean["recipient"],
        "address": clean["address"],
        "status": "created",
    }

    deliveries[next_id] = delivery
    next_id += 1
    return delivery

@app.get("/deliveries")
def list_deliveries(status: Optional[str] = None):
    items = list(deliveries.values())

    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(400, f"status must be one of: {sorted(VALID_STATUSES)}")
        items = [d for d in items if d["status"] == status]

    return items

@app.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: int):
    delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise HTTPException(404, "delivery not found")
    return delivery

@app.patch("/deliveries/{delivery_id}/status")
def update_delivery_status(delivery_id: int, payload: dict = Body(...)):
    delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise HTTPException(404, "delivery not found")

    if "status" not in payload:
        raise HTTPException(400, "status is required")

    new_status = payload["status"]
    current_status = delivery["status"]

    validate_status_transition(current_status, new_status)

    delivery["status"] = new_status
    return delivery

@app.delete("/deliveries/{delivery_id}", status_code=204)
def delete_delivery(delivery_id: int):
    delivery = deliveries.get(delivery_id)
    if delivery is None:
        raise HTTPException(404, "delivery not found")

    if delivery["status"] != "created":
        raise HTTPException(409, "only deliveries with status 'created' can be deleted")

    del deliveries[delivery_id]
    return None