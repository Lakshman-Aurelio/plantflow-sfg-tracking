"""Small integration smoke test against a disposable PostgreSQL database."""
from app.main import Line, Receipt, TransferIn, create_transfer, db, dispatch, init, receive


def main() -> None:
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
    print("PostgreSQL smoke test passed: create, dispatch, partial receipt and completion.")


if __name__ == "__main__":
    main()
