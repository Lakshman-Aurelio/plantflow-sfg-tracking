"""Small integration smoke test against a disposable PostgreSQL database."""
import os
os.environ.setdefault("JWT_SECRET", "ci-only-not-a-production-secret-" + "x" * 24)
from app.main import Line, Receipt, TransferIn, create_transfer, db, dispatch, init, receive


def main() -> None:
    # A pre-existing account row lets init() verify that bootstrap credentials
    # are not required for an already-provisioned database.
    with db() as connection:
        connection.execute(
            "INSERT INTO users(email,password_hash,role) VALUES(%s,%s,%s) ON CONFLICT(email) DO NOTHING",
            ("ci-admin@plantflow.test", "test-hash-not-used", "admin"),
        )
    init()
    transfer = create_transfer(
        TransferIn(source_id=1, destination_id=2, items=[Line(product_id=1, quantity=3)])
    )
    transfer_id = transfer["id"]

    dispatched = dispatch(transfer_id)
    assert dispatched["status"] == "IN_TRANSIT"

    partial = receive(transfer_id, Receipt(items=[Line(product_id=1, quantity=1)]))
    assert partial["status"] == "PARTIALLY_RECEIVED"
    completed = receive(transfer_id, Receipt(items=[Line(product_id=1, quantity=2)]))
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
    print("PostgreSQL smoke test passed: migration, create, dispatch, partial receipt and completion.")


if __name__ == "__main__":
    main()
