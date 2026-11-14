"""SAP S/4HANA connector placeholder.

No SAP requests are made by this module. Implement only after Indus confirms
its S/4HANA edition, released APIs, authentication and network connectivity.
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SAPS4HANAConfig:
    base_url: str
    client_id: str
    client_secret: str
    token_url: str


class SAPS4HANAAdapter:
    def __init__(self, config: SAPS4HANAConfig) -> None:
        self.config = config

    async def fetch_inventory(self, plant_code: str, material_code: str) -> dict[str, Any]:
        raise NotImplementedError("SAP S/4HANA API mapping and authentication are not configured.")

    async def submit_stock_transfer(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("SAP S/4HANA stock-transfer API is not implemented.")

    async def fetch_transfer_status(self, external_reference: str) -> dict[str, Any]:
        raise NotImplementedError("SAP S/4HANA transfer-status API is not implemented.")
