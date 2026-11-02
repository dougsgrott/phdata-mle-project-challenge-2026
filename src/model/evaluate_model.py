"""Evaluate a model file on the held-out rows, in-process (no server needed)."""

import argparse
import json
import pickle
from pathlib import Path

import pandas as pd
from evaluation import DATA, MODEL_DIR, load_holdout, save_report, score


def build_features(rows: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Same assembly as the API: join demographics by zipcode, keep the model order."""
    demographics = pd.read_csv(
        DATA / "zipcode_demographics.csv", dtype={"zipcode": str}
    )
    return rows.merge(demographics, how="left", on="zipcode")[features]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, default=MODEL_DIR / "model.pkl")
    p.add_argument(
        "--features", type=Path, default=MODEL_DIR / "model_features.json"
    )
    p.add_argument("--label", required=True, help="report name, e.g. baseline")
    p.add_argument("--out", type=Path, help="write per-row predictions CSV here")
    args = p.parse_args()

    with open(args.model, "rb") as f:
        model = pickle.load(f)
    features = json.loads(args.features.read_text())

    holdout = load_holdout()
    pred = model.predict(build_features(holdout, features))

    predictions = pd.DataFrame(
        {"row": holdout.index, "predicted_price": pred, "error": None}
    )
    report = {
        "model": str(args.model),
        "rows": len(holdout),
        **score(holdout["price"], pred),
    }
    save_report("model", args.label, report, predictions, args.out)


if __name__ == "__main__":
    main()