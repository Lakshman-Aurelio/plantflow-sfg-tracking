from typing import Any, Protocol


class ERPAdapter(Protocol):
    """Vendor-neutral contract; implementations must not bypass PlantFlow services."""

    async def fetch_inventory(self, plant_code: str, material_code: str) -> dict[str, Any]:
        ...

    async def submit_stock_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def fetch_transfer_status(self, external_reference: str) -> dict[str, Any]:
        ...
