"""The committed imputer.pkl, tested directly (no API)."""

import pickle

import numpy as np
import pandas as pd
import pytest

from src.api.endpoints import HOUSE_FIELDS

TRAINING_ROWS = 16209  # the 75% training split of kc_house_data.csv


@pytest.fixture(scope="module")
def imputer():
    with open("model/imputer.pkl", "rb") as f:
        return pickle.load(f)


@pytest.fixture
def house(sample_home_features):
    """The sample house with bathrooms and sqft_lot missing, as in the brief."""
    values = {field: sample_home_features[field] for field in HOUSE_FIELDS}
    return {**values, "bathrooms": None, "sqft_lot": None}


def as_frame(house: dict) -> pd.DataFrame:
    return pd.DataFrame([house], columns=HOUSE_FIELDS, dtype=float)


def test_imputer_fit_on_house_fields_of_training_split(imputer):
    """Same columns, in the same order, as the API sends; holdout rows not in pool."""
    assert list(imputer.feature_names_in_) == HOUSE_FIELDS
    assert len(imputer._fit_X) == TRAINING_ROWS


def test_known_values_unchanged(imputer, house):
    filled = imputer.transform(as_frame(house))[0]

    for i, field in enumerate(HOUSE_FIELDS):
        if house[field] is not None:
            assert filled[i] == house[field]


def test_gaps_filled_with_finite_values(imputer, house):
    filled = imputer.transform(as_frame(house))[0]

    assert np.isfinite(filled).all()


def test_all_null_row_uses_training_mean(imputer):
    """With no known value there are no neighbours, so each field gets its mean."""
    empty = dict.fromkeys(HOUSE_FIELDS)

    filled = imputer.transform(as_frame(empty))[0]

    np.testing.assert_allclose(filled, imputer._fit_X.mean(axis=0))