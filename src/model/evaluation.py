"""Held-out evaluation rows and accuracy metrics.

Shared by evaluate_model.py (a model file, in-process) and
scripts/evaluate_api.py (a running API), so both score the same rows the same way.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from create_model import SALES_COLUMN_SELECTION
from sklearn.model_selection import train_test_split

MODEL_DIR = Path(__file__).resolve().parent
DATA = MODEL_DIR.parent / "data"
ROOT = MODEL_DIR.parent.parent
RANDOM_STATE = 42  # same as the split in create_model.py


def load_holdout() -> pd.DataFrame:
    """The 25% of kc_house_data.csv that create_model.py does not train on."""
    sales = pd.read_csv(
        DATA / "kc_house_data.csv",
        usecols=SALES_COLUMN_SELECTION,
        dtype={"zipcode": str},
    )
    demographics = pd.read_csv(
        DATA / "zipcode_demographics.csv", dtype={"zipcode": str}
    )
    # create_model.py splits after a left merge with demographics. The split depends
    # only on the row count, so it is reproduced exactly if the merge keeps it.
    merged_rows = len(sales.merge(demographics[["zipcode"]], how="left", on="zipcode"))
    if merged_rows != len(sales):
        sys.exit(f"merge changes the row count ({len(sales)} -> {merged_rows})")
    _, holdout = train_test_split(sales, random_state=RANDOM_STATE)
    return holdout.reset_index(drop=True)


def score(true, pred) -> dict:
    """Coverage over all rows; the other metrics over rows that have a prediction."""
    true = np.asarray(true, dtype=float)
    pred = np.asarray(pred, dtype=float)
    covered = ~np.isnan(pred)
    if not covered.any():
        return {"coverage": 0.0, "mae": None, "mape_pct": None, "within_10pct": None}
    abs_err = np.abs(pred[covered] - true[covered])
    pct_err = abs_err / true[covered]
    return {
        "coverage": float(covered.mean()),
        "mae": float(abs_err.mean()),
        "mape_pct": float(pct_err.mean() * 100),
        "within_10pct": float((pct_err <= 0.10).mean()),
    }


def save_report(
    kind: str, label: str, report: dict, predictions: pd.DataFrame, out: Path | None
) -> None:
    """Write reports/evaluation/<kind>/<label>.json and, optionally, per-row CSV."""
    report = {
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **report,
    }
    path = ROOT / "reports" / "evaluation" / kind / f"{label}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        predictions.to_csv(out, index=False)
    print(json.dumps(report, indent=2))
    print(f"Wrote {path}")