from __future__ import annotations

import csv
import io
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pwdlib import PasswordHash

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required.")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

JWT_SECRET = os.environ.get("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be configured with at least 32 characters.")
JWT_ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.environ.get("TOKEN_MINUTES", "480"))
password_hash = PasswordHash.recommended()
origins = [v.strip() for v in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if v.strip()]

app = FastAPI(title="PlantFlow SFG Transfer API", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10) as connection:
        yield connection


def init() -> None:
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    with db() as connection:
        if connection.execute("SELECT COUNT(*) AS n FROM plants").fetchone()["n"] == 0:
            for row in [("Demo Plant 1", "PLT-01"), ("Demo Plant 2", "PLT-02"), ("Demo Plant 3", "PLT-03")]:
                connection.execute("INSERT INTO plants(name,code) VALUES(%s,%s)", row)
            for row in [
                ("HDR-001", "Header Assembly", "pcs"),
                ("SMP-002", "Sheet Metal Panel", "pcs"),
                ("MTB-003", "Motor Base", "pcs"),
                ("BRK-004", "Bracket Set", "sets"),
            ]:
                connection.execute("INSERT INTO products(sku,name,unit) VALUES(%s,%s,%s)", row)
            for plant in range(1, 4):
                for product, quantity in [(1, 120 * plant), (2, 85 * plant), (3, 60 * plant), (4, 45 * plant)]:
                    connection.execute(
                        "INSERT INTO inventory(plant_id,product_id,on_hand) VALUES(%s,%s,%s)",
                        (plant, product, quantity),
                    )
        if email and password:
            if len(password) < 12:
                raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.")
            connection.execute(
                "INSERT INTO users(email,password_hash,role) VALUES(%s,%s,'admin') ON CONFLICT(email) DO NOTHING",
                (email, password_hash.hash(password)),
            )
        elif connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
            raise RuntimeError(
                "No users exist. Configure BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD to create the first administrator."
            )


@app.on_event("startup")
def startup() -> None:
    init()


def issue_token(user: dict) -> str:
    payload = {
        "sub": str(user["id"]),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


@app.middleware("http")
async def authentication(request: Request, call_next):
    if request.url.path in ("/api/health", "/api/auth/login") or request.method == "OPTIONS":
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = jwt.decode(auth.split(" ", 1)[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
        with db() as connection:
            user = connection.execute(
                "SELECT id,email,role,plant_id,is_active FROM users WHERE id=%s",
                (int(claims["sub"]),),
            ).fetchone()
        if not user or not user["is_active"]:
            raise ValueError("Inactive user")
        request.state.user = dict(user)
    except Exception:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired access token."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


def require_roles(request: Request, *roles: str) -> dict:
    user = request.state.user
    if user["role"] not in roles:
        raise HTTPException(403, "Your account does not have permission for this action.")
    return user


def ensure_plant_access(user: dict, plant_id: int) -> None:
    if user["role"] != "admin" and user["plant_id"] is not None and int(user["plant_id"]) != int(plant_id):
        raise HTTPException(403, "This account is not assigned to the requested plant.")


def ensure_transfer_access(user: dict, transfer: dict) -> None:
    if user["role"] != "admin" and user["plant_id"] is not None:
        if int(user["plant_id"]) not in (int(transfer["source_id"]), int(transfer["destination_id"])):
            raise HTTPException(403, "This transfer is outside your assigned plant.")


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(pattern="^(admin|manager|viewer)$")
    plant_id: Optional[int] = None


class Line(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class JobOrderLine(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0)


class JobOrderIn(BaseModel):
    job_order_id: str = Field(min_length=1, max_length=80)
    parent_build: str = Field(min_length=1, max_length=120)
    product: str = Field(min_length=1, max_length=160)
    quantity: int = Field(gt=0)
    unit: str = Field(default="pcs", max_length=16)
    required_sfg: list[JobOrderLine] = Field(min_length=1)


class TransferIn(BaseModel):
    job_order_id: Optional[str] = None
    source_id: int
    destination_id: int
    items: list[Line]
    notes: str = ""
    carrier: str = ""
    expected_at: Optional[str] = None


class Receipt(BaseModel):
    items: list[Line]
    discrepancy_reason: str = ""


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    note: str = "Manual checkpoint"


def transfer_view(connection, transfer: dict) -> dict:
    items = connection.execute(
        "SELECT ti.product_id,p.sku,p.name,p.unit,ti.quantity,ti.received_qty "
        "FROM transfer_items ti JOIN products p ON p.id=ti.product_id WHERE ti.transfer_id=%s",
        (transfer["id"],),
    ).fetchall()
    events = connection.execute(
        "SELECT event_type,event_at,details FROM events WHERE transfer_id=%s ORDER BY id",
        (transfer["id"],),
    ).fetchall()
    source = connection.execute("SELECT name,code FROM plants WHERE id=%s", (transfer["source_id"],)).fetchone()
    destination = connection.execute(
        "SELECT name,code FROM plants WHERE id=%s", (transfer["destination_id"],)
    ).fetchone()
    return {
        **dict(transfer),
        "source": dict(source),
        "destination": dict(destination),
        "items": [dict(item) for item in items],
        "events": [dict(event) for event in events],
    }


@app.post("/api/auth/login")
def login(data: LoginIn):
    with db() as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE email=%s AND is_active=TRUE", (data.email.lower(),)
        ).fetchone()
    if not user or not password_hash.verify(data.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "plant_id": user["plant_id"],
        },
    }


@app.get("/api/auth/me")
def me(request: Request):
    user = request.state.user
    return {key: user[key] for key in ("id", "email", "role", "plant_id")}


@app.post("/api/users")
def create_user(data: UserIn, request: Request):
    require_roles(request, "admin")
    if data.role != "admin" and data.plant_id is None:
        raise HTTPException(400, "Manager and viewer accounts must be assigned to a plant.")
    with db() as connection:
        if data.plant_id is not None and not connection.execute(
            "SELECT 1 FROM plants WHERE id=%s", (data.plant_id,)
        ).fetchone():
            raise HTTPException(404, "Plant not found.")
        try:
            row = connection.execute(
                "INSERT INTO users(email,password_hash,role,plant_id) VALUES(%s,%s,%s,%s) "
                "RETURNING id,email,role,plant_id",
                (data.email.lower(), password_hash.hash(data.password), data.role, data.plant_id),
            ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "An account with this email already exists.")
        return dict(row)


@app.get("/api/health")
def health():
    with db() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok", "database": "postgresql"}


@app.get("/api/plants")
def plants():
    with db() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM plants ORDER BY id")]


@app.get("/api/products")
def products():
    with db() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM products ORDER BY sku")]


@app.get("/api/inventory")
def inventory(request: Request, plant_id: Optional[int] = None, search: str = ""):
    user = request.state.user
    if plant_id is not None:
        ensure_plant_access(user, plant_id)
    query = (
        "SELECT i.plant_id,pl.name plant,p.id product_id,p.sku,p.name product,p.unit,i.on_hand,i.in_transit "
        "FROM inventory i JOIN plants pl ON pl.id=i.plant_id JOIN products p ON p.id=i.product_id WHERE 1=1"
    )
    args = []
    if plant_id is not None:
        query += " AND i.plant_id=%s"
        args.append(plant_id)
    if user["role"] != "admin" and user["plant_id"] is not None:
        query += " AND i.plant_id=%s"
        args.append(user["plant_id"])
    if search:
        query += " AND (p.sku ILIKE %s OR p.name ILIKE %s)"
        args.extend([f"%{search}%", f"%{search}%"])
    with db() as connection:
        return [dict(row) for row in connection.execute(query + " ORDER BY pl.id,p.sku", args)]


@app.get("/api/transfers")
def transfers(request: Request, search: str = "", status: str = "", date_from: str = "", date_to: str = ""):
    user = request.state.user
    query = "SELECT * FROM transfers WHERE 1=1"
    args = []
    if user["role"] != "admin" and user["plant_id"] is not None:
        query += " AND (source_id=%s OR destination_id=%s)"
        args.extend([user["plant_id"], user["plant_id"]])
    if search:
        query += (
            " AND (number ILIKE %s OR id IN (SELECT ti.transfer_id FROM transfer_items ti "
            "JOIN products p ON p.id=ti.product_id WHERE p.sku ILIKE %s OR p.name ILIKE %s))"
        )
        args.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    if status:
        query += " AND status=%s"
        args.append(status)
    if date_from:
        query += " AND substr(created_at,1,10)>=%s"
        args.append(date_from)
    if date_to:
        query += " AND substr(created_at,1,10)<=%s"
        args.append(date_to)
    with db() as connection:
        return [
            transfer_view(connection, transfer)
            for transfer in connection.execute(query + " ORDER BY id DESC", args).fetchall()
        ]


@app.post("/api/transfers")
def create_transfer(data: TransferIn, request: Request):
    user = require_roles(request, "admin", "manager")
    ensure_plant_access(user, data.source_id)
    if data.source_id == data.destination_id:
        raise HTTPException(400, "Source and destination must differ.")
    if not data.items:
        raise HTTPException(400, "Add at least one SKU line.")
    if len({line.product_id for line in data.items}) != len(data.items):
        raise HTTPException(400, "Each SKU can appear only once per transfer.")
    with db() as connection:
        for plant_id in (data.source_id, data.destination_id):
            if not connection.execute("SELECT 1 FROM plants WHERE id=%s", (plant_id,)).fetchone():
                raise HTTPException(404, "Plant not found.")
        for line in data.items:
            if not connection.execute("SELECT 1 FROM products WHERE id=%s", (line.product_id,)).fetchone():
                raise HTTPException(404, "Product not found.")
        stamp = now()
        number = "SFG-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        transfer_id = connection.execute(
            "INSERT INTO transfers(number,source_id,destination_id,status,created_at,notes,carrier,expected_at) "
            "VALUES(%s,%s,%s,'DRAFT',%s,%s,%s,%s) RETURNING id",
            (number, data.source_id, data.destination_id, stamp, data.notes, data.carrier, data.expected_at),
        ).fetchone()["id"]
        for line in data.items:
            connection.execute(
                "INSERT INTO transfer_items(transfer_id,product_id,quantity) VALUES(%s,%s,%s)",
                (transfer_id, line.product_id, line.quantity),
            )
        connection.execute(
            "INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",
            (transfer_id, "CREATED", stamp, "Transfer created"),
        )
        transfer = connection.execute("SELECT * FROM transfers WHERE id=%s", (transfer_id,)).fetchone()
        return transfer_view(connection, transfer)


@app.post("/api/transfers/{transfer_id}/dispatch")
def dispatch(transfer_id: int, request: Request):
    user = require_roles(request, "admin", "manager")
    with db() as connection:
        transfer = connection.execute(
            "SELECT * FROM transfers WHERE id=%s FOR UPDATE", (transfer_id,)
        ).fetchone()
        if not transfer:
            raise HTTPException(404, "Transfer not found.")
        ensure_plant_access(user, transfer["source_id"])
        if transfer["status"] != "DRAFT":
            raise HTTPException(409, "Only draft transfers can be dispatched.")
        items = connection.execute(
            "SELECT * FROM transfer_items WHERE transfer_id=%s ORDER BY product_id", (transfer_id,)
        ).fetchall()
        for item in items:
            stock = connection.execute(
                "SELECT on_hand FROM inventory WHERE plant_id=%s AND product_id=%s FOR UPDATE",
                (transfer["source_id"], item["product_id"]),
            ).fetchone()
            if not stock or stock["on_hand"] < item["quantity"]:
                raise HTTPException(409, f"Insufficient stock for product ID {item['product_id']}.")
        stamp = now()
        for item in items:
            connection.execute(
                "UPDATE inventory SET on_hand=on_hand-%s,in_transit=in_transit+%s "
                "WHERE plant_id=%s AND product_id=%s",
                (item["quantity"], item["quantity"], transfer["source_id"], item["product_id"]),
            )
            connection.execute(
                "INSERT INTO stock_movements(plant_id,product_id,transfer_id,movement_type,quantity,created_at) "
                "VALUES(%s,%s,%s,%s,%s,%s)",
                (transfer["source_id"], item["product_id"], transfer_id, "DISPATCH", -item["quantity"], stamp),
            )
        connection.execute(
            "UPDATE transfers SET status='IN_TRANSIT',dispatched_at=%s WHERE id=%s", (stamp, transfer_id)
        )
        connection.execute(
            "INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",
            (transfer_id, "DISPATCHED", stamp, "Dispatched by plant manager"),
        )
        updated = connection.execute("SELECT * FROM transfers WHERE id=%s", (transfer_id,)).fetchone()
        return transfer_view(connection, updated)


@app.post("/api/transfers/{transfer_id}/receive")
def receive(transfer_id: int, data: Receipt, request: Request):
    user = require_roles(request, "admin", "manager")
    if not data.items:
        raise HTTPException(400, "Enter received quantities.")
    if len({line.product_id for line in data.items}) != len(data.items):
        raise HTTPException(400, "Each SKU can appear only once per receipt.")
    with db() as connection:
        transfer = connection.execute(
            "SELECT * FROM transfers WHERE id=%s FOR UPDATE", (transfer_id,)
        ).fetchone()
        if not transfer:
            raise HTTPException(404, "Transfer not found.")
        ensure_plant_access(user, transfer["destination_id"])
        if transfer["status"] not in ("IN_TRANSIT", "PARTIALLY_RECEIVED", "DISCREPANCY"):
            raise HTTPException(409, "Transfer is not awaiting receipt.")
        stamp = now()
        for received in data.items:
            item = connection.execute(
                "SELECT * FROM transfer_items WHERE transfer_id=%s AND product_id=%s FOR UPDATE",
                (transfer_id, received.product_id),
            ).fetchone()
            if not item:
                raise HTTPException(400, "SKU is not part of this transfer.")
            remaining = item["quantity"] - item["received_qty"]
            if received.quantity > remaining:
                raise HTTPException(409, "Received quantity exceeds outstanding quantity.")
            connection.execute(
                "UPDATE transfer_items SET received_qty=received_qty+%s WHERE id=%s",
                (received.quantity, item["id"]),
            )
            connection.execute(
                "INSERT INTO inventory(plant_id,product_id,on_hand,in_transit) VALUES(%s,%s,%s,0) "
                "ON CONFLICT(plant_id,product_id) DO UPDATE SET on_hand=inventory.on_hand+EXCLUDED.on_hand",
                (transfer["destination_id"], received.product_id, received.quantity),
            )
            updated = connection.execute(
                "UPDATE inventory SET in_transit=in_transit-%s WHERE plant_id=%s AND product_id=%s AND in_transit >= %s",
                (received.quantity, transfer["source_id"], received.product_id, received.quantity),
            )
            if updated.rowcount != 1:
                raise HTTPException(409, "Source in-transit balance is inconsistent; receipt was not applied.")
            connection.execute(
                "INSERT INTO stock_movements(plant_id,product_id,transfer_id,movement_type,quantity,created_at,note) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (transfer["destination_id"], received.product_id, transfer_id, "RECEIPT", received.quantity, stamp, data.discrepancy_reason),
            )
        totals = connection.execute(
            "SELECT SUM(quantity) q,SUM(received_qty) r FROM transfer_items WHERE transfer_id=%s",
            (transfer_id,),
        ).fetchone()
        status = "DISCREPANCY" if data.discrepancy_reason.strip() else (
            "RECEIVED" if totals["q"] == totals["r"] else "PARTIALLY_RECEIVED"
        )
        connection.execute(
            "UPDATE transfers SET status=%s,received_at=%s WHERE id=%s",
            (status, stamp if status == "RECEIVED" else transfer["received_at"], transfer_id),
        )
        detail = data.discrepancy_reason.strip() or f"Received quantities recorded ({totals['r']}/{totals['q']} units)"
        connection.execute(
            "INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",
            (transfer_id, "RECEIVED", stamp, detail),
        )
        updated = connection.execute("SELECT * FROM transfers WHERE id=%s", (transfer_id,)).fetchone()
        return transfer_view(connection, updated)


@app.post("/api/transfers/{transfer_id}/location")
def location(transfer_id: int, data: Location, request: Request):
    user = require_roles(request, "admin", "manager")
    with db() as connection:
        transfer = connection.execute("SELECT * FROM transfers WHERE id=%s", (transfer_id,)).fetchone()
        if not transfer:
            raise HTTPException(404, "Transfer not found.")
        ensure_transfer_access(user, transfer)
        detail = f"{data.note} | {data.latitude:.6f}, {data.longitude:.6f}"
        connection.execute(
            "INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",
            (transfer_id, "LOCATION", now(), detail),
        )
        return {"recorded": True, "detail": detail}


@app.get("/api/dashboard")
def dashboard(request: Request):
    user = request.state.user
    scope = ""
    args = []
    if user["role"] != "admin" and user["plant_id"] is not None:
        scope = " WHERE source_id=%s OR destination_id=%s"
        args = [user["plant_id"], user["plant_id"]]
    with db() as connection:
        counts_query = "SELECT status,COUNT(*) n FROM transfers" + scope + " GROUP BY status"
        counts = {row["status"]: row["n"] for row in connection.execute(counts_query, args)}
        completed_query = (
            "SELECT dispatched_at,received_at FROM transfers WHERE status='RECEIVED' "
            "AND dispatched_at IS NOT NULL AND received_at IS NOT NULL"
        )
        completed_args = []
        if scope:
            completed_query += " AND (source_id=%s OR destination_id=%s)"
            completed_args = args
        rows = connection.execute(completed_query, completed_args).fetchall()
        durations = []
        for row in rows:
            try:
                durations.append(
                    (datetime.fromisoformat(row["received_at"]) - datetime.fromisoformat(row["dispatched_at"])).total_seconds() / 3600
                )
            except ValueError:
                continue
        return {
            "counts": counts,
            "total": sum(counts.values()),
            "avg_transit_hours": round(sum(durations) / len(durations), 1) if durations else None,
            "plants": connection.execute("SELECT COUNT(*) AS n FROM plants").fetchone()["n"],
        }


@app.get("/api/transfers.csv")
def export_csv(request: Request):
    user = request.state.user
    query = (
        "SELECT t.number,s.name source,d.name destination,t.status,t.created_at,t.dispatched_at,t.received_at,"
        "p.sku,p.name product,ti.quantity,ti.received_qty FROM transfers t "
        "JOIN plants s ON s.id=t.source_id JOIN plants d ON d.id=t.destination_id "
        "JOIN transfer_items ti ON ti.transfer_id=t.id JOIN products p ON p.id=ti.product_id"
    )
    args = []
    if user["role"] != "admin" and user["plant_id"] is not None:
        query += " WHERE t.source_id=%s OR t.destination_id=%s"
        args = [user["plant_id"], user["plant_id"]]
    query += " ORDER BY t.id DESC"
    with db() as connection:
        rows = connection.execute(query, args).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Transfer", "Source", "Destination", "Status", "Created UTC", "Dispatched UTC", "Received UTC", "SKU", "Product", "Qty Sent", "Qty Received"])
    for row in rows:
        writer.writerow(list(row))
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantflow-transfers.csv"},
    )
