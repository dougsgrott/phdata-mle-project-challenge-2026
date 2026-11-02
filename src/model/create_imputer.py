"""Fit the KNN imputer for missing house fields and save it as imputer.pkl.

Run from src/model:  uv run python create_imputer.py
The model is not retrained; model.pkl is left as it is (D16).
"""

import pickle

from evaluation import MODEL_DIR, load_split
from sklearn.impute import KNNImputer

from create_model import HOUSE_FIELDS


def main() -> None:
    # Training rows only, so holdout rows are never neighbours (D15)
    train, _ = load_split()
    # The notebook's settings, on the 7 house fields, unscaled (D14)
    imputer = KNNImputer(n_neighbors=5, weights="distance").fit(train[HOUSE_FIELDS])

    path = MODEL_DIR / "imputer.pkl"
    with open(path, "wb") as f:
        pickle.dump(imputer, f)
    print(f"Wrote {path}: {len(train)} rows, columns {list(imputer.feature_names_in_)}")


if __name__ == "__main__":
    main()