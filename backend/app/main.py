from __future__ import annotations
import csv, io, sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

DB = Path(__file__).resolve().parents[1] / "plantflow.db"
app = FastAPI(title="PlantFlow SFG Transfer API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
@contextmanager
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    try: yield c; c.commit()
    except Exception: c.rollback(); raise
    finally: c.close()
def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS plants(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,code TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,unit TEXT NOT NULL DEFAULT 'pcs');
        CREATE TABLE IF NOT EXISTS inventory(plant_id INTEGER REFERENCES plants(id),product_id INTEGER REFERENCES products(id),on_hand INTEGER NOT NULL DEFAULT 0 CHECK(on_hand>=0),in_transit INTEGER NOT NULL DEFAULT 0 CHECK(in_transit>=0),PRIMARY KEY(plant_id,product_id));
        CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY,number TEXT UNIQUE NOT NULL,source_id INTEGER REFERENCES plants(id),destination_id INTEGER REFERENCES plants(id),status TEXT NOT NULL,created_at TEXT NOT NULL,dispatched_at TEXT,received_at TEXT,notes TEXT DEFAULT '',carrier TEXT DEFAULT '',expected_at TEXT);
        CREATE TABLE IF NOT EXISTS transfer_items(id INTEGER PRIMARY KEY,transfer_id INTEGER REFERENCES transfers(id),product_id INTEGER REFERENCES products(id),quantity INTEGER NOT NULL CHECK(quantity>0),received_qty INTEGER NOT NULL DEFAULT 0 CHECK(received_qty>=0));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,transfer_id INTEGER REFERENCES transfers(id),event_type TEXT NOT NULL,event_at TEXT NOT NULL,details TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS stock_movements(id INTEGER PRIMARY KEY,plant_id INTEGER REFERENCES plants(id),product_id INTEGER REFERENCES products(id),transfer_id INTEGER REFERENCES transfers(id),movement_type TEXT NOT NULL,quantity INTEGER NOT NULL,created_at TEXT NOT NULL,note TEXT DEFAULT '');
        """)
        if c.execute("SELECT COUNT(*) FROM plants").fetchone()[0]==0:
            c.executemany("INSERT INTO plants(name,code) VALUES(?,?)",[("Demo Plant 1","PLT-01"),("Demo Plant 2","PLT-02"),("Demo Plant 3","PLT-03")])
            c.executemany("INSERT INTO products(sku,name,unit) VALUES(?,?,?)",[("HDR-001","Header Assembly","pcs"),("SMP-002","Sheet Metal Panel","pcs"),("MTB-003","Motor Base","pcs"),("BRK-004","Bracket Set","sets")])
            for plant in range(1,4):
                for product,qty in [(1,120*plant),(2,85*plant),(3,60*plant),(4,45*plant)]:
                    c.execute("INSERT INTO inventory(plant_id,product_id,on_hand) VALUES(?,?,?)",(plant,product,qty))
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
    items=c.execute("SELECT ti.product_id,p.sku,p.name,p.unit,ti.quantity,ti.received_qty FROM transfer_items ti JOIN products p ON p.id=ti.product_id WHERE ti.transfer_id=?",(t["id"],)).fetchall()
    events=c.execute("SELECT event_type,event_at,details FROM events WHERE transfer_id=? ORDER BY id",(t["id"],)).fetchall()
    src=c.execute("SELECT name,code FROM plants WHERE id=?",(t["source_id"],)).fetchone()
    dst=c.execute("SELECT name,code FROM plants WHERE id=?",(t["destination_id"],)).fetchone()
    return {**dict(t),"source":dict(src),"destination":dict(dst),"items":[dict(x) for x in items],"events":[dict(x) for x in events]}
@app.get("/api/health")
def health(): return {"status":"ok"}
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
        if plant_id: q+=" AND i.plant_id=?"; a.append(plant_id)
        if search: q+=" AND (p.sku LIKE ? OR p.name LIKE ?)"; a += [f"%{search}%",f"%{search}%"]
        return [dict(x) for x in c.execute(q+" ORDER BY pl.id,p.sku",a)]
@app.get("/api/transfers")
def transfers(search:str="",status:str="",date_from:str="",date_to:str=""):
    with db() as c:
        q="SELECT * FROM transfers WHERE 1=1"; a=[]
        if search:
            q+=" AND (number LIKE ? OR id IN (SELECT ti.transfer_id FROM transfer_items ti JOIN products p ON p.id=ti.product_id WHERE p.sku LIKE ? OR p.name LIKE ?))"; a += [f"%{search}%",f"%{search}%",f"%{search}%"]
        if status: q+=" AND status=?"; a.append(status)
        if date_from: q+=" AND substr(created_at,1,10)>=?"; a.append(date_from)
        if date_to: q+=" AND substr(created_at,1,10)<=?"; a.append(date_to)
        return [transfer_view(c,t) for t in c.execute(q+" ORDER BY id DESC",a).fetchall()]
@app.post("/api/transfers")
def create_transfer(x:TransferIn):
    if x.source_id==x.destination_id: raise HTTPException(400,"Source and destination must differ.")
    if not x.items: raise HTTPException(400,"Add at least one SKU line.")
    with db() as c:
        for line in x.items:
            if not c.execute("SELECT 1 FROM products WHERE id=?",(line.product_id,)).fetchone(): raise HTTPException(404,"Product not found.")
        stamp=now(); number="SFG-"+datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        tid=c.execute("INSERT INTO transfers(number,source_id,destination_id,status,created_at,notes,carrier,expected_at) VALUES(?,?,?,'DRAFT',?,?,?,?)",(number,x.source_id,x.destination_id,stamp,x.notes,x.carrier,x.expected_at)).lastrowid
        for line in x.items: c.execute("INSERT INTO transfer_items(transfer_id,product_id,quantity) VALUES(?,?,?)",(tid,line.product_id,line.quantity))
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(?,?,?,?)",(tid,"CREATED",stamp,"Transfer created"))
        return transfer_view(c,c.execute("SELECT * FROM transfers WHERE id=?",(tid,)).fetchone())
@app.post("/api/transfers/{tid}/dispatch")
def dispatch(tid:int):
    with db() as c:
        t=c.execute("SELECT * FROM transfers WHERE id=?",(tid,)).fetchone()
        if not t: raise HTTPException(404,"Transfer not found.")
        if t["status"]!="DRAFT": raise HTTPException(409,"Only draft transfers can be dispatched.")
        items=c.execute("SELECT * FROM transfer_items WHERE transfer_id=?",(tid,)).fetchall()
        for i in items:
            inv=c.execute("SELECT on_hand FROM inventory WHERE plant_id=? AND product_id=?",(t["source_id"],i["product_id"])).fetchone()
            if not inv or inv["on_hand"]<i["quantity"]: raise HTTPException(409,f"Insufficient stock for product ID {i['product_id']}.")
        stamp=now()
        for i in items:
            c.execute("UPDATE inventory SET on_hand=on_hand-?,in_transit=in_transit+? WHERE plant_id=? AND product_id=?",(i["quantity"],i["quantity"],t["source_id"],i["product_id"]))
            c.execute("INSERT INTO stock_movements(plant_id,product_id,transfer_id,movement_type,quantity,created_at) VALUES(?,?,?,?,?,?)",(t["source_id"],i["product_id"],tid,"DISPATCH",-i["quantity"],stamp))
        c.execute("UPDATE transfers SET status='IN_TRANSIT',dispatched_at=? WHERE id=?",(stamp,tid))
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(?,?,?,?)",(tid,"DISPATCHED",stamp,"Dispatched by plant manager"))
        return transfer_view(c,c.execute("SELECT * FROM transfers WHERE id=?",(tid,)).fetchone())
@app.post("/api/transfers/{tid}/receive")
def receive(tid:int,x:Receipt):
    if not x.items: raise HTTPException(400,"Enter received quantities.")
    with db() as c:
        t=c.execute("SELECT * FROM transfers WHERE id=?",(tid,)).fetchone()
        if not t: raise HTTPException(404,"Transfer not found.")
        if t["status"] not in ("IN_TRANSIT","PARTIALLY_RECEIVED","DISCREPANCY"): raise HTTPException(409,"Transfer is not awaiting receipt.")
        stamp=now()
        for rec in x.items:
            i=c.execute("SELECT * FROM transfer_items WHERE transfer_id=? AND product_id=?",(tid,rec.product_id)).fetchone()
            if not i: raise HTTPException(400,"SKU is not part of this transfer.")
            remaining=i["quantity"]-i["received_qty"]
            if rec.quantity>remaining: raise HTTPException(409,"Received quantity exceeds outstanding quantity.")
            c.execute("UPDATE transfer_items SET received_qty=received_qty+? WHERE id=?",(rec.quantity,i["id"]))
            c.execute("INSERT INTO inventory(plant_id,product_id,on_hand,in_transit) VALUES(?,?,?,0) ON CONFLICT(plant_id,product_id) DO UPDATE SET on_hand=on_hand+excluded.on_hand",(t["destination_id"],rec.product_id,rec.quantity))
            c.execute("UPDATE inventory SET in_transit=in_transit-? WHERE plant_id=? AND product_id=?",(rec.quantity,t["source_id"],rec.product_id))
            c.execute("INSERT INTO stock_movements(plant_id,product_id,transfer_id,movement_type,quantity,created_at,note) VALUES(?,?,?,?,?,?,?)",(t["destination_id"],rec.product_id,tid,"RECEIPT",rec.quantity,stamp,x.discrepancy_reason))
        sums=c.execute("SELECT SUM(quantity) q,SUM(received_qty) r FROM transfer_items WHERE transfer_id=?",(tid,)).fetchone()
        status="DISCREPANCY" if x.discrepancy_reason.strip() else ("RECEIVED" if sums["q"]==sums["r"] else "PARTIALLY_RECEIVED")
        c.execute("UPDATE transfers SET status=?,received_at=? WHERE id=?",(status,stamp if status=="RECEIVED" else t["received_at"],tid))
        detail=x.discrepancy_reason.strip() or f"Received quantities recorded ({sums['r']}/{sums['q']} units)"
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(?,?,?,?)",(tid,"RECEIVED",stamp,detail))
        return transfer_view(c,c.execute("SELECT * FROM transfers WHERE id=?",(tid,)).fetchone())
@app.post("/api/transfers/{tid}/location")
def location(tid:int,x:Location):
    with db() as c:
        if not c.execute("SELECT 1 FROM transfers WHERE id=?",(tid,)).fetchone(): raise HTTPException(404,"Transfer not found.")
        detail=f"{x.note} | {x.latitude:.6f}, {x.longitude:.6f}"
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(?,?,?,?)",(tid,"LOCATION",now(),detail))
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
        return {"counts":counts,"total":sum(counts.values()),"avg_transit_hours":round(sum(durations)/len(durations),1) if durations else None,"plants":c.execute("SELECT COUNT(*) FROM plants").fetchone()[0]}
@app.get("/api/transfers.csv")
def export_csv():
    with db() as c:
        rows=c.execute("SELECT t.number,s.name source,d.name destination,t.status,t.created_at,t.dispatched_at,t.received_at,p.sku,p.name product,ti.quantity,ti.received_qty FROM transfers t JOIN plants s ON s.id=t.source_id JOIN plants d ON d.id=t.destination_id JOIN transfer_items ti ON ti.transfer_id=t.id JOIN products p ON p.id=ti.product_id ORDER BY t.id DESC").fetchall()
    out=io.StringIO(); w=csv.writer(out); w.writerow(["Transfer","Source","Destination","Status","Created UTC","Dispatched UTC","Received UTC","SKU","Product","Qty Sent","Qty Received"])
    for r in rows: w.writerow(list(r))
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=plantflow-transfers.csv"})
