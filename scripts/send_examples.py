"""Send the rows of a CSV to /predict; record latency, throughput and errors."""

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "src" / "data" / "future_unseen_examples.csv"

# Must match HomeFeatures in src/api/endpoints.py
API_FIELDS = [
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "sqft_lot",
    "floors",
    "sqft_above",
    "sqft_basement",
    "zipcode",
]


def load_rows(path: Path) -> list[dict]:
    df = pd.read_csv(path, dtype={"zipcode": str})
    missing = [c for c in API_FIELDS if c not in df.columns]
    if missing:
        sys.exit(f"{path} is missing columns: {missing}")
    return df[API_FIELDS].to_dict(orient="records")


async def send_one(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, row: int, payload: dict
) -> dict:
    async with sem:
        # Timer starts after the semaphore, so client-side queueing isn't counted.
        start = time.perf_counter()
        try:
            response = await client.post("/predict", json=payload)
            latency = time.perf_counter() - start
            if response.status_code != 200:
                error = f"HTTP {response.status_code}"
                return {"row": row, "latency": latency, "price": None, "error": error}
            price = response.json()["predicted_price"]
            return {"row": row, "latency": latency, "price": price, "error": None}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            latency = time.perf_counter() - start
            error = type(exc).__name__
            return {"row": row, "latency": latency, "price": None, "error": error}


async def run(url: str, rows: list[dict], concurrency: int, timeout: float):
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    async with httpx.AsyncClient(base_url=url, timeout=timeout, limits=limits) as c:
        start = time.perf_counter()
        results = await asyncio.gather(
            *(send_one(c, sem, i, payload) for i, payload in enumerate(rows))
        )
        wall = time.perf_counter() - start
    return list(results), wall


def latency_stats(results: list[dict]) -> dict | None:
    ms = np.array([r["latency"] for r in results if r["error"] is None]) * 1000
    if ms.size == 0:
        return None
    return {
        "min": float(ms.min()),
        "mean": float(ms.mean()),
        "p50": float(np.percentile(ms, 50)),
        "p90": float(np.percentile(ms, 90)),
        "p95": float(np.percentile(ms, 95)),
        "p99": float(np.percentile(ms, 99)),
        "max": float(ms.max()),
    }

def summarize(results: list[dict], wall: float, args: argparse.Namespace) -> dict:
    ok = [r for r in results if r["error"] is None]
    errors = Counter(r["error"] for r in results if r["error"] is not None)

    latency = None
    if ok:
        ms = np.array([r["latency"] for r in ok]) * 1000
        latency = {
            "min": float(ms.min()),
            "mean": float(ms.mean()),
            "p50": float(np.percentile(ms, 50)),
            "p90": float(np.percentile(ms, 90)),
            "p95": float(np.percentile(ms, 95)),
            "p99": float(np.percentile(ms, 99)),
            "max": float(ms.max()),
        }

    first = results[0]  # row 0 is always the first request issued
    return {
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": args.url,
        "input": str(args.input),
        "concurrency": args.concurrency,
        "requests": len(results),
        "succeeded": len(ok),
        "failed": len(results) - len(ok),
        "errors": dict(errors),
        "wall_seconds": wall,
        "throughput_rps": len(ok) / wall if wall > 0 else None,
        "latency_ms": latency,  # successful requests only
        "latency_ms_excl_first": latency_stats(results[1:]),  # row 0 removed
        "first_request_ms": first["latency"] * 1000 if first["error"] is None else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--timeout", type=float, default=30.0, help="seconds per request")
    p.add_argument("--report", type=Path, help="write the JSON report here")
    p.add_argument("--out", type=Path, help="write predictions CSV here")
    p.add_argument("--label", default="", help="free-text label stored in the report")
    args = p.parse_args()
    if args.concurrency < 1:
        p.error("--concurrency must be >= 1")

    rows = load_rows(args.input)
    results, wall = asyncio.run(run(args.url, rows, args.concurrency, args.timeout))
    report = summarize(results, wall, args)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results)[["row", "price", "error"]].rename(
            columns={"price": "predicted_price"}
        ).to_csv(args.out, index=False)

    print(json.dumps(report, indent=2))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())