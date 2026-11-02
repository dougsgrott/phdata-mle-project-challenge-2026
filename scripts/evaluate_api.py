"""Evaluate a running API on the held-out rows (sends each row to /predict)."""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from send_examples import API_FIELDS, run

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "model"))
from evaluation import load_holdout, save_report, score  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--label", required=True, help="report name, e.g. baseline")
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--timeout", type=float, default=30.0, help="seconds per request")
    p.add_argument("--out", type=Path, help="write per-row predictions CSV here")
    args = p.parse_args()

    holdout = load_holdout()
    rows = holdout[API_FIELDS].to_dict(orient="records")
    results, wall = asyncio.run(run(args.url, rows, args.concurrency, args.timeout))

    pred = np.array(
        [np.nan if r["price"] is None else r["price"] for r in results], dtype=float
    )
    predictions = pd.DataFrame(results)[["row", "price", "error"]].rename(
        columns={"price": "predicted_price"}
    )
    errors = Counter(r["error"] for r in results if r["error"])
    report = {
        "url": args.url,
        "rows": len(holdout),
        "failed": sum(errors.values()),
        "errors": dict(errors),
        **score(holdout["price"], pred),
        "wall_seconds": wall,
    }
    save_report("api", args.label, report, predictions, args.out)
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())