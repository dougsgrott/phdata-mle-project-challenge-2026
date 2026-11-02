"""Profile a single /predict request (baseline measurement, no app changes)."""

import asyncio
import os
import sys
from pathlib import Path

import httpx
from pyinstrument import Profiler

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT = ROOT / "reports" / "profile" / "baseline.txt"

# The endpoint uses relative paths ("model/...", "data/..."), so run from src/
sys.path.insert(0, str(SRC))
os.chdir(SRC)

from main import app  # noqa: E402

PAYLOAD = {
    "bedrooms": 3,
    "bathrooms": 2.0,
    "sqft_living": 1500.0,
    "sqft_lot": 5000.0,
    "floors": 1.0,
    "sqft_above": 1200.0,
    "sqft_basement": 300.0,
    "zipcode": "98042",
}


async def call(client: httpx.AsyncClient) -> dict:
    response = await client.post("/predict", json=PAYLOAD)
    response.raise_for_status()
    return response.json()


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        await call(c)  # warm-up: lazy imports, OS file cache (not profiled)

        profiler = Profiler(interval=0.0001)
        profiler.start()
        result = await call(c)
        profiler.stop()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = f"# /predict profile (1 warm request)\n# result: {result}\n\n"
    OUT.write_text(header + profiler.output_text(unicode=False, color=False))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
