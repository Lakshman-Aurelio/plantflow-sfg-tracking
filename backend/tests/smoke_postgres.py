"""Small integration smoke test against a disposable PostgreSQL database."""
import os
os.environ.setdefault("JWT_SECRET", "ci-only-not-a-production-secret-" + "x" * 24)
from starlette.requests import Request
from fastapi.testclient import TestClient
from app.main import Line, Receipt, TransferIn, app, create_transfer, db, dispatch, init, password_hash, receive


def main() -> None:
    # A pre-existing account row lets init() verify that bootstrap credentials
    # are not required for an already-provisioned database.
    with db() as connection:
        connection.execute(
            "INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s) ON CONFLICT(email) DO NOTHING",
            ("ci-admin@plantflow.test", password_hash.hash("CITest-Password-1234"), "admin"),
        )
    with db() as connection:
        connection.execute("INSERT INTO users(email,password_hash,role,plant_id) VALUES(%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING", ("ci-viewer@plantflow.test", password_hash.hash("ViewerTest-Password-1234"), "viewer", 1))
    init()
    with TestClient(app) as client:
        assert client.get("/api/plants").status_code == 401
        login = client.post("/api/auth/login", json={"email":"ci-admin@plantflow.test","password":"CITest-Password-1234"})
        assert login.status_code == 200, login.text
        admin_headers = {"Authorization":"Bearer "+login.json()["access_token"]}
        assert client.get("/api/plants", headers=admin_headers).status_code == 200
        viewer_login = client.post("/api/auth/login", json={"email":"ci-viewer@plantflow.test","password":"ViewerTest-Password-1234"})
        assert viewer_login.status_code == 200, viewer_login.text
        viewer_headers = {"Authorization":"Bearer "+viewer_login.json()["access_token"]}
        assert client.get("/api/inventory?plant_id=2", headers=viewer_headers).status_code == 403
        assert client.post("/api/transfers", headers=viewer_headers, json={"source_id":1,"destination_id":2,"items":[{"product_id":1,"quantity":1}]}).status_code == 403
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    request.state.user = {"id": 1, "email": "ci-admin@plantflow.test", "role": "admin", "plant_id": None}
    transfer = create_transfer(
        TransferIn(source_id=1, destination_id=2, items=[Line(product_id=1, quantity=3)]), request
    )
    transfer_id = transfer["id"]

    dispatched = dispatch(transfer_id, request)
    assert dispatched["status"] == "IN_TRANSIT"

    partial = receive(transfer_id, Receipt(items=[Line(product_id=1, quantity=1)]), request)
    assert partial["status"] == "PARTIALLY_RECEIVED"
    completed = receive(transfer_id, Receipt(items=[Line(product_id=1, quantity=2)]), request)
    assert completed["status"] == "RECEIVED"

    with db() as connection:
        source = connection.execute(
            "SELECT on_hand, in_transit FROM inventory WHERE plant_id=%s AND product_id=%s",
            (1, 1),
        ).fetchone()
        destination = connection.execute(
            "SELECT on_hand, in_transit FROM inventory WHERE plant_id=%s AND product_id=%s",
            (2, 1),
        ).fetchone()

    assert source["on_hand"] == 117 and source["in_transit"] == 0, source
    assert destination["on_hand"] == 243 and destination["in_transit"] == 0, destination
    print("PostgreSQL smoke test passed: migration, login, role/plant authorization, create, dispatch, partial receipt and completion.")


if __name__ == "__main__":
    main()
