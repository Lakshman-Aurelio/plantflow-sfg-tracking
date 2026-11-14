from __future__ import annotations
import csv, io, os
import psycopg
from psycopg.rows import dict_row
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required.")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
origins = [v.strip() for v in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if v.strip()]
app = FastAPI(title="PlantFlow SFG Transfer API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
@contextmanager
def db():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10) as connection:
        yield connection

def init():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
        if not c.execute("SELECT 1 FROM schema_migrations WHERE version='001_initial'").fetchone():
            schema = [
                "CREATE TABLE plants(id BIGSERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,code TEXT UNIQUE NOT NULL)",
                "CREATE TABLE products(id BIGSERIAL PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL DEFAULT 'pcs')",
                "CREATE TABLE inventory(plant_id BIGINT REFERENCES plants(id),product_id BIGINT REFERENCES products(id),on_hand INTEGER NOT NULL DEFAULT 0 CHECK(on_hand>=0),in_transit INTEGER NOT NULL DEFAULT 0 CHECK(in_transit>=0),PRIMARY KEY(plant_id,product_id))",
                "CREATE TABLE transfers(id BIGSERIAL PRIMARY KEY,number TEXT UNIQUE NOT NULL,source_id BIGINT REFERENCES plants(id),destination_id BIGINT REFERENCES plants(id),status TEXT NOT NULL,created_at TEXT NOT NULL,dispatched_at TEXT,received_at TEXT,notes TEXT DEFAULT '',carrier TEXT DEFAULT '',expected_at TEXT)",
                "CREATE TABLE transfer_items(id BIGSERIAL PRIMARY KEY,transfer_id BIGINT REFERENCES transfers(id),product_id BIGINT REFERENCES products(id),quantity INTEGER NOT NULL CHECK(quantity>0),received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty>=0 AND received_qty<=quantity),UNIQUE(transfer_id,product_id))",
                "CREATE TABLE events(id BIGSERIAL PRIMARY KEY,transfer_id BIGINT REFERENCES transfers(id),event_type TEXT NOT NULL,event_at TEXT NOT NULL,details TEXT DEFAULT '')",
                "CREATE TABLE stock_movements(id BIGSERIAL PRIMARY KEY,plant_id BIGINT REFERENCES plants(id),product_id BIGINT REFERENCES products(id),transfer_id BIGINT REFERENCES transfers(id),movement_type TEXT NOT NULL,quantity INTEGER NOT NULL,created_at TEXT NOT NULL,note TEXT DEFAULT '')",
                "CREATE INDEX idx_transfers_created_at ON transfers(created_at)",
                "CREATE INDEX idx_transfers_status ON transfers(status)",
                "CREATE INDEX idx_events_transfer_id ON events(transfer_id,id)",
                "CREATE INDEX idx_stock_movements_transfer_id ON stock_movements(transfer_id)"
            ]
            for statement in schema:
                c.execute(statement)
            c.execute("INSERT INTO schema_migrations(version) VALUES('001_initial')")
        if c.execute("SELECT COUNT(*) AS n FROM plants").fetchone()["n"]==0:
            for row in [("Demo Plant 1","PLT-01"),("Demo Plant 2","PLT-02"),("Demo Plant 3","PLT-03")]:
                c.execute("INSERT INTO plants(name,code) VALUES(%s,%s)",row)
            for row in [("HDR-001","Header Assembly","pcs"),("SMP-002","Sheet Metal Panel","pcs"),("MTB-003","Motor Base","pcs"),("BRK-004","Bracket Set","sets")]:
                c.execute("INSERT INTO products(sku,name,unit) VALUES(%s,%s,%s)",row)
            for plant in range(1,4):
                for product,qty in [(1,120*plant),(2,85*plant),(3,60*plant),(4,45*plant)]:
                    c.execute("INSERT INTO inventory(plant_id,product_id,on_hand) VALUES(%s,%s,%s)",(plant,product,qty))
@app.on_event("startup")
def startup(): init()
class Line(BaseModel):
    product_id:int
    quantity:int=Field(gt=0)
class TransferIn(BaseModel):
    source_id:int
    destination_id:int
    items:list[Line]
    notes:str=""
    carrier:str=""
    expected_at:Optional[str]=None
class Receipt(BaseModel):
    items:list[Line]
    discrepancy_reason:str=""
class Location(BaseModel):
    latitude:float
    longitude:float
    note:str="Manual checkpoint"
def transfer_view(c,t):
    items=c.execute("SELECT ti.product_id,p.sku,p.name,p.unit,ti.quantity,ti.received_qty FROM transfer_items ti JOIN products p ON p.id=ti.product_id WHERE ti.transfer_id=%s",(t["id"],)).fetchall()
    events=c.execute("SELECT event_type,event_at,details FROM events WHERE transfer_id=%s ORDER BY id",(t["id"],)).fetchall()
    src=c.execute("SELECT name,code FROM plants WHERE id=%s",(t["source_id"],)).fetchone()
    dst=c.execute("SELECT name,code FROM plants WHERE id=%s",(t["destination_id"],)).fetchone()
    return {**dict(t),"source":dict(src),"destination":dict(dst),"items":[dict(x) for x in items],"events":[dict(x) for x in events]}
@app.get("/api/health")
def health():
    with db() as c:
        c.execute("SELECT 1")
    return {"status":"ok","database":"postgresql"}
@app.get("/api/plants")
def plants():
    with db() as c: return [dict(x) for x in c.execute("SELECT * FROM plants ORDER BY id")]
@app.get("/api/products")
def products():
    with db() as c: return [dict(x) for x in c.execute("SELECT * FROM products ORDER BY sku")]
@app.get("/api/inventory")
def inventory(plant_id:Optional[int]=None,search:str=""):
    with db() as c:
        q="SELECT i.plant_id,pl.name plant,p.id product_id,p.sku,p.name product,p.unit,i.on_hand,i.in_transit FROM inventory i JOIN plants pl ON pl.id=i.plant_id JOIN products p ON p.id=i.product_id WHERE 1=1"; a=[]
        if plant_id: q+=" AND i.plant_id=%s"; a.append(plant_id)
        if search: q+=" AND (p.sku LIKE %s OR p.name LIKE %s)"; a += [f"%{search}%",f"%{search}%"]
        return [dict(x) for x in c.execute(q+" ORDER BY pl.id,p.sku",a)]
@app.get("/api/transfers")
def transfers(search:str="",status:str="",date_from:str="",date_to:str=""):
    with db() as c:
        q="SELECT * FROM transfers WHERE 1=1"; a=[]
        if search:
            q+=" AND (number LIKE %s OR id IN (SELECT ti.transfer_id FROM transfer_items ti JOIN products p ON p.id=ti.product_id WHERE p.sku LIKE %s OR p.name LIKE %s))"; a += [f"%{search}%",f"%{search}%",f"%{search}%"]
        if status: q+=" AND status=%s"; a.append(status)
        if date_from: q+=" AND substr(created_at,1,10)>=%s"; a.append(date_from)
        if date_to: q+=" AND substr(created_at,1,10)<=%s"; a.append(date_to)
        return [transfer_view(c,t) for t in c.execute(q+" ORDER BY id DESC",a).fetchall()]
@app.post("/api/transfers")
def create_transfer(x:TransferIn):
    if x.source_id==x.destination_id: raise HTTPException(400,"Source and destination must differ.")
    if not x.items: raise HTTPException(400,"Add at least one SKU line.")
    if len({line.product_id for line in x.items}) != len(x.items): raise HTTPException(400,"Each SKU can appear only once per transfer.")
    with db() as c:
        for plant_id in (x.source_id, x.destination_id):
            if not c.execute("SELECT 1 FROM plants WHERE id=%s",(plant_id,)).fetchone(): raise HTTPException(404,"Plant not found.")
        for line in x.items:
            if not c.execute("SELECT 1 FROM products WHERE id=%s",(line.product_id,)).fetchone(): raise HTTPException(404,"Product not found.")
        stamp=now(); number="SFG-"+datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        tid=c.execute("INSERT INTO transfers(number,source_id,destination_id,status,created_at,notes,carrier,expected_at) VALUES(%s,%s,%s,'DRAFT',%s,%s,%s,%s) RETURNING id",(number,x.source_id,x.destination_id,stamp,x.notes,x.carrier,x.expected_at)).fetchone()["id"]
        for line in x.items: c.execute("INSERT INTO transfer_items(transfer_id,product_id,quantity) VALUES(%s,%s,%s)",(tid,line.product_id,line.quantity))
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",(tid,"CREATED",stamp,"Transfer created"))
        return transfer_view(c,c.execute("SELECT * FROM transfers WHERE id=%s FOR UPDATE",(tid,)).fetchone())
@app.post("/api/transfers/{tid}/dispatch")
def dispatch(tid:int):
    with db() as c:
        t=c.execute("SELECT * FROM transfers WHERE id=%s FOR UPDATE",(tid,)).fetchone()
        if not t: raise HTTPException(404,"Transfer not found.")
        if t["status"]!="DRAFT": raise HTTPException(409,"Only draft transfers can be dispatched.")
        items=c.execute("SELECT * FROM transfer_items WHERE transfer_id=%s ORDER BY product_id",(tid,)).fetchall()
        for i in items:
            inv=c.execute("SELECT on_hand FROM inventory WHERE plant_id=%s AND product_id=%s FOR UPDATE",(t["source_id"],i["product_id"])).fetchone()
            if not inv or inv["on_hand"]<i["quantity"]: raise HTTPException(409,f"Insufficient stock for product ID {i['product_id']}.")
        stamp=now()
        for i in items:
            c.execute("UPDATE inventory SET on_hand=on_hand-%s,in_transit=in_transit+%s WHERE plant_id=%s AND product_id=%s",(i["quantity"],i["quantity"],t["source_id"],i["product_id"]))
            c.execute("INSERT INTO stock_movements(plant_id,product_id,transfer_id,movement_type,quantity,created_at) VALUES(%s,%s,%s,%s,%s,%s)",(t["source_id"],i["product_id"],tid,"DISPATCH",-i["quantity"],stamp))
        c.execute("UPDATE transfers SET status='IN_TRANSIT',dispatched_at=%s WHERE id=%s",(stamp,tid))
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",(tid,"DISPATCHED",stamp,"Dispatched by plant manager"))
        return transfer_view(c,c.execute("SELECT * FROM transfers WHERE id=%s",(tid,)).fetchone())
@app.post("/api/transfers/{tid}/receive")
def receive(tid:int,x:Receipt):
    if not x.items: raise HTTPException(400,"Enter received quantities.")
    with db() as c:
        t=c.execute("SELECT * FROM transfers WHERE id=%s",(tid,)).fetchone()
        if not t: raise HTTPException(404,"Transfer not found.")
        if t["status"] not in ("IN_TRANSIT","PARTIALLY_RECEIVED","DISCREPANCY"): raise HTTPException(409,"Transfer is not awaiting receipt.")
        stamp=now()
        for rec in x.items:
            i=c.execute("SELECT * FROM transfer_items WHERE transfer_id=%s AND product_id=%s FOR UPDATE",(tid,rec.product_id)).fetchone()
            if not i: raise HTTPException(400,"SKU is not part of this transfer.")
            remaining=i["quantity"]-i["received_qty"]
            if rec.quantity>remaining: raise HTTPException(409,"Received quantity exceeds outstanding quantity.")
            c.execute("UPDATE transfer_items SET received_qty=received_qty+%s WHERE id=%s",(rec.quantity,i["id"]))
            c.execute("INSERT INTO inventory(plant_id,product_id,on_hand,in_transit) VALUES(%s,%s,%s,0) ON CONFLICT(plant_id,product_id) DO UPDATE SET on_hand=on_hand+excluded.on_hand",(t["destination_id"],rec.product_id,rec.quantity))
            updated=c.execute("UPDATE inventory SET in_transit=in_transit-%s WHERE plant_id=%s AND product_id=%s AND in_transit >= %s",(rec.quantity,t["source_id"],rec.product_id,rec.quantity))
            if updated.rowcount != 1: raise HTTPException(409,"Source in-transit balance is inconsistent; receipt was not applied.")
            c.execute("INSERT INTO stock_movements(plant_id,product_id,transfer_id,movement_type,quantity,created_at,note) VALUES(%s,%s,%s,%s,%s,%s,%s)",(t["destination_id"],rec.product_id,tid,"RECEIPT",rec.quantity,stamp,x.discrepancy_reason))
        sums=c.execute("SELECT SUM(quantity) q,SUM(received_qty) r FROM transfer_items WHERE transfer_id=%s",(tid,)).fetchone()
        status="DISCREPANCY" if x.discrepancy_reason.strip() else ("RECEIVED" if sums["q"]==sums["r"] else "PARTIALLY_RECEIVED")
        c.execute("UPDATE transfers SET status=%s,received_at=%s WHERE id=%s",(status,stamp if status=="RECEIVED" else t["received_at"],tid))
        detail=x.discrepancy_reason.strip() or f"Received quantities recorded ({sums['r']}/{sums['q']} units)"
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",(tid,"RECEIVED",stamp,detail))
        return transfer_view(c,c.execute("SELECT * FROM transfers WHERE id=%s",(tid,)).fetchone())
@app.post("/api/transfers/{tid}/location")
def location(tid:int,x:Location):
    with db() as c:
        if not c.execute("SELECT 1 FROM transfers WHERE id=%s",(tid,)).fetchone(): raise HTTPException(404,"Transfer not found.")
        detail=f"{x.note} | {x.latitude:.6f}, {x.longitude:.6f}"
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",(tid,"LOCATION",now(),detail))
        return {"recorded":True,"detail":detail}
@app.get("/api/dashboard")
def dashboard():
    with db() as c:
        counts={r["status"]:r["n"] for r in c.execute("SELECT status,COUNT(*) n FROM transfers GROUP BY status")}
        rows=c.execute("SELECT dispatched_at,received_at FROM transfers WHERE status='RECEIVED' AND dispatched_at IS NOT NULL AND received_at IS NOT NULL").fetchall()
        durations=[]
        for r in rows:
            try: durations.append((datetime.fromisoformat(r["received_at"])-datetime.fromisoformat(r["dispatched_at"])).total_seconds()/3600)
            except ValueError: pass
        return {"counts":counts,"total":sum(counts.values()),"avg_transit_hours":round(sum(durations)/len(durations),1) if durations else None,"plants":c.execute("SELECT COUNT(*) AS n FROM plants").fetchone()["n"]}
@app.get("/api/transfers.csv")
def export_csv():
    with db() as c:
        rows=c.execute("SELECT t.number,s.name source,d.name destination,t.status,t.created_at,t.dispatched_at,t.received_at,p.sku,p.name product,ti.quantity,ti.received_qty FROM transfers t JOIN plants s ON s.id=t.source_id JOIN plants d ON d.id=t.destination_id JOIN transfer_items ti ON ti.transfer_id=t.id JOIN products p ON p.id=ti.product_id ORDER BY t.id DESC").fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(["Transfer","Source","Destination","Status","Created UTC","Dispatched UTC","Received UTC","SKU","Product","Qty Sent","Qty Received"])
    for r in rows: w.writerow(list(r))
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=plantflow-transfers.csv"})
