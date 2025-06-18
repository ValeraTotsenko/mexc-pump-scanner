import aiohttp
import logging
from typing import List

logger = logging.getLogger(__name__)


async def fetch_all_pairs(rest_url: str) -> List[str]:
    """Fetch list of all trading pairs from MEXC REST API."""
    url_base = rest_url.rstrip('/')
    paths = ["/api/v3/defaultSymbols", "/api/v3/exchangeInfo"]
    async with aiohttp.ClientSession() as session:
        for path in paths:
            try:
                async with session.get(f"{url_base}{path}") as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    if isinstance(data, list):
                        return [str(s) for s in data]
                    if isinstance(data, dict):
                        if "data" in data and isinstance(data["data"], list):
                            return [d if isinstance(d, str) else d.get("symbol") for d in data["data"]]
                        if "symbols" in data and isinstance(data["symbols"], list):
                            return [s.get("symbol") for s in data["symbols"]]
            except Exception as exc:  # pragma: no cover - network
                logger.error("Failed fetching %s: %s", path, exc)
                continue
    raise RuntimeError("Unable to fetch symbol list from MEXC")
