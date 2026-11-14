from __future__ import annotations
import csv, io, os
import psycopg
import jwt
from pwdlib import PasswordHash
from psycopg.rows import dict_row
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, EmailStr

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
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET","POST","OPTIONS"], allow_headers=["Authorization","Content-Type"])
def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
@contextmanager
def db():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10) as connection:
        yield connection

def init():
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    with db() as c:
        if c.execute("SELECT COUNT(*) AS n FROM plants").fetchone()["n"] == 0:
            for row in [("Demo Plant 1","PLT-01"),("Demo Plant 2","PLT-02"),("Demo Plant 3","PLT-03")]:
                c.execute("INSERT INTO plants(name,code) VALUES(%s,%s)",row)
            for row in [("HDR-001","Header Assembly","pcs"),("SMP-002","Sheet Metal Panel","pcs"),("MTB-003","Motor Base","pcs"),("BRK-004","Bracket Set","sets")]:
                c.execute("INSERT INTO products(sku,name,unit) VALUES(%s,%s,%s)",row)
            for plant in range(1,4):
                for product,qty in [(1,120*plant),(2,85*plant),(3,60*plant),(4,45*plant)]:
                    c.execute("INSERT INTO inventory(plant_id,product_id,on_hand) VALUES(%s,%s,%s)",(plant,product,qty))
        if email and password:
            if len(password) < 12:
                raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.")
            c.execute("INSERT INTO users(email,password_hash,role) VALUES(%s,%s,'admin') ON CONFLICT(email) DO NOTHING",(email,password_hash.hash(password)))
        elif c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0:
            raise RuntimeError("No users exist. Configure BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD to create the first administrator.")

@app.on_event("startup")
def startup(): init()

def issue_token(user):
    payload={"sub":str(user["id"]),"role":user["role"],"plant_id":user["plant_id"],"exp":datetime.now(timezone.utc)+timedelta(minutes=TOKEN_MINUTES)}
    return jwt.encode(payload,JWT_SECRET,algorithm=JWT_ALGORITHM)

@app.middleware("http")
async def authentication(request: Request, call_next):
    if request.url.path in ("/api/health","/api/auth/login") or request.method == "OPTIONS":
        return await call_next(request)
    auth=request.headers.get("authorization","")
    if not auth.lower().startswith("bearer "):
        return JSONResponse(status_code=401,content={"detail":"Authentication required."},headers={"WWW-Authenticate":"Bearer"})
    try:
        claims=jwt.decode(auth.split(" ",1)[1],JWT_SECRET,algorithms=[JWT_ALGORITHM])
        with db() as c:
            user=c.execute("SELECT id,email,role,plant_id,is_active FROM users WHERE id=%s",(int(claims["sub"]),)).fetchone()
        if not user or not user["is_active"]:
            raise ValueError("Inactive user")
        request.state.user=dict(user)
    except Exception:
        return JSONResponse(status_code=401,content={"detail":"Invalid or expired access token."},headers={"WWW-Authenticate":"Bearer"})
    return await call_next(request)

def require_roles(request: Request, *roles):
    user=request.state.user
    if user["role"] not in roles:
        raise HTTPException(403,"Your account does not have permission for this action.")
    return user

def ensure_plant_access(user, plant_id):
    if user["role"] != "admin" and user["plant_id"] is not None and int(user["plant_id"]) != int(plant_id):
        raise HTTPException(403,"This account is not assigned to the requested plant.")

class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
class UserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(pattern="^(admin|manager|viewer)$")
    plant_id: Optional[int] = None

@app.post("/api/auth/login")
def login(x: LoginIn):
    with db() as c:
        user=c.execute("SELECT * FROM users WHERE email=%s AND is_active=TRUE",(x.email.lower(),)).fetchone()
    if not user or not password_hash.verify(x.password,user["password_hash"]):
        raise HTTPException(401,"Incorrect email or password.")
    return {"access_token":issue_token(user),"token_type":"bearer","user":{"id":user["id"],"email":user["email"],"role":user["role"],"plant_id":user["plant_id"]}}

@app.get("/api/auth/me")
def me(request: Request):
    u=request.state.user
    return {"id":u["id"],"email":u["email"],"role":u["role"],"plant_id":u["plant_id"]}

@app.post("/api/users")
def create_user(x: UserIn, request: Request):
    require_roles(request,"admin")
    if x.role != "admin" and x.plant_id is None:
        raise HTTPException(400,"Manager and viewer accounts must be assigned to a plant.")
    with db() as c:
        if x.plant_id is not None and not c.execute("SELECT 1 FROM plants WHERE id=%s",(x.plant_id,)).fetchone():
            raise HTTPException(404,"Plant not found.")
        try:
            row=c.execute("INSERT INTO users(email,password_hash,role,plant_id) VALUES(%s,%s,%s,%s) RETURNING id,email,role,plant_id",(x.email.lower(),password_hash.hash(x.password),x.role,x.plant_id)).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409,"An account with this email already exists.")
        return dict(row)

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
def inventory(request: Request, plant_id:Optional[int]=None,search:str=""):
    with db() as c:
        q="SELECT i.plant_id,pl.name plant,p.id product_id,p.sku,p.name product,p.unit,i.on_hand,i.in_transit FROM inventory i JOIN plants pl ON pl.id=i.plant_id JOIN products p ON p.id=i.product_id WHERE 1=1"; a=[]
        if plant_id: q+=" AND i.plant_id=%s"; a.append(plant_id)\n        if u["role"]!="admin" and u["plant_id"] is not None: q+=" AND i.plant_id=%s"; a.append(u["plant_id"])
        if search: q+=" AND (p.sku LIKE %s OR p.name LIKE %s)"; a += [f"%{search}%",f"%{search}%"]
        return [dict(x) for x in c.execute(q+" ORDER BY pl.id,p.sku",a)]
@app.get("/api/transfers")
def transfers(request: Request,search:str="",status:str="",date_from:str="",date_to:str=""):
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
            c.execute("INSERT INTO inventory(plant_id,product_id,on_hand,in_transit) VALUES(%s,%s,%s,0) ON CONFLICT(plant_id,product_id) DO UPDATE SET on_hand=inventory.on_hand+EXCLUDED.on_hand",(t["destination_id"],rec.product_id,rec.quantity))
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
        t=c.execute("SELECT * FROM transfers WHERE id=%s",(tid,)).fetchone()\n        if not t: raise HTTPException(404,"Transfer not found.")\n        ensure_plant_access(u,t["source_id"])
        detail=f"{x.note} | {x.latitude:.6f}, {x.longitude:.6f}"
        c.execute("INSERT INTO events(transfer_id,event_type,event_at,details) VALUES(%s,%s,%s,%s)",(tid,"LOCATION",now(),detail))
        return {"recorded":True,"detail":detail}
@app.get("/api/dashboard")
def dashboard():
    with db() as c:
        query="SELECT status,COUNT(*) n FROM transfers GROUP BY status"; args=[]\n        if u["role"]!="admin" and u["plant_id"] is not None: query="SELECT status,COUNT(*) n FROM transfers WHERE source_id=%s OR destination_id=%s GROUP BY status"; args=[u["plant_id"],u["plant_id"]]\n        counts={r["status"]:r["n"] for r in c.execute(query,args)}
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
