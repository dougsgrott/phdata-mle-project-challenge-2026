import itertools
import json
import logging
import math
import pickle
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.endpoints import HOUSE_FIELDS


def test_health_endpoint(test_client):
    """Test the /health endpoint returns correct status."""
    response = test_client.get("/health")
    assert response.status_code == 200
    response_data = response.json()
    assert "status" in response_data
    assert response_data["status"] == "healthy"


def test_predict_endpoint_valid_input(test_client, sample_home_features):
    """Test the /predict endpoint with valid input."""
    response = test_client.post("/predict", json=sample_home_features)
    assert response.status_code == 200
    response_data = response.json()
    assert "predicted_price" in response_data
    assert isinstance(response_data["predicted_price"], float)


def test_artifacts_load_once(monkeypatch, sample_home_features):
    """N requests must not reload the model: it is read once, at startup."""
    from src.main import app

    calls = []
    real_load = pickle.load
    monkeypatch.setattr(
        pickle, "load", lambda f: calls.append(Path(f.name).name) or real_load(f)
    )

    with TestClient(app) as client:
        for _ in range(5):
            response = client.post("/predict", json=sample_home_features)
            assert response.status_code == 200

    assert sorted(calls) == ["imputer.pkl", "model.pkl"]


def test_batch_reports_bad_rows(test_client, sample_home_features):
    """One bad row gets an error; the other rows still get prices, in order."""
    bad_value = {**sample_home_features, "bedrooms": "three"}
    unknown_zip = {**sample_home_features, "zipcode": "00000"}
    body = [sample_home_features, bad_value, unknown_zip, 42]

    response = test_client.post("/predict/batch", json=body)

    assert response.status_code == 200
    good, bad, unknown, not_object = response.json()
    assert good["predicted_price"] > 0
    assert "bedrooms" in bad["error"]
    assert "zipcode" in unknown["error"]
    assert "error" in not_object


def test_batch_rejects_non_list(test_client, sample_home_features):
    response = test_client.post("/predict/batch", json=sample_home_features)
    assert response.status_code == 422


def test_predict_unknown_zipcode(test_client, sample_home_features):
    """A zipcode without demographics is a client error, not a server error."""
    body = {**sample_home_features, "zipcode": "00000"}

    response = test_client.post("/predict", json=body)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "zipcode"]
    assert "00000" in error["msg"]


def test_request_is_logged_as_json(test_client, sample_home_features, caplog):
    """Each request produces one JSON log line with path, status and zipcode."""
    caplog.set_level(logging.INFO, logger="housing_api")

    test_client.post("/predict", json=sample_home_features)

    lines = [r.getMessage() for r in caplog.records if r.name == "housing_api"]
    entry = json.loads(lines[-1])
    assert entry["path"] == "/predict"
    assert entry["status"] == 200
    assert entry["zipcode"] == sample_home_features["zipcode"]
    assert entry["latency_ms"] >= 0


def test_house_fields_match_model_features():
    """The schema's house fields are the model's first features, in the same order."""
    from src.api.endpoints import HOUSE_FIELDS

    features = json.loads(Path("model/model_features.json").read_text())
    assert features[: len(HOUSE_FIELDS)] == HOUSE_FIELDS


def test_every_null_combination_gets_a_price(test_client, sample_home_features):
    """All 128 null/present combinations of the house fields get a finite price."""
    for nulls in itertools.product([False, True], repeat=len(HOUSE_FIELDS)):
        gaps = {
            field: None for field, null in zip(HOUSE_FIELDS, nulls, strict=True) if null
        }
        body = {**sample_home_features, **gaps}

        response = test_client.post("/predict", json=body)

        assert response.status_code == 200, body
        price = response.json()["predicted_price"]
        assert math.isfinite(price) and price > 0, body


def test_omitted_field_is_treated_as_null(test_client, sample_home_features):
    """Leaving a field out gives the same price as sending it as null."""
    as_null = {**sample_home_features, "bathrooms": None}
    omitted = {k: v for k, v in sample_home_features.items() if k != "bathrooms"}

    null_price = test_client.post("/predict", json=as_null).json()["predicted_price"]
    omitted_price = test_client.post("/predict", json=omitted).json()["predicted_price"]

    assert omitted_price == null_price


def test_null_zipcode_rejected(test_client, sample_home_features):
    """zipcode stays required: null is a client error."""
    response = test_client.post(
        "/predict", json={**sample_home_features, "zipcode": None}
    )

    assert response.status_code == 422


def test_batch_price_does_not_depend_on_batchmates(test_client, sample_home_features):
    """A house with gaps gets the same price alone and in two different batches."""
    house = {**sample_home_features, "bathrooms": None, "sqft_lot": None}
    other = {**sample_home_features, "zipcode": "98125", "sqft_living": None}

    alone = test_client.post("/predict", json=house).json()["predicted_price"]
    first = test_client.post("/predict/batch", json=[house, sample_home_features])
    second = test_client.post("/predict/batch", json=[other, house, other])

    assert first.json()[0]["predicted_price"] == alone
    assert second.json()[1]["predicted_price"] == alone
