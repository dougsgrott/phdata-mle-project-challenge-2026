import pickle

from fastapi.testclient import TestClient


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
    monkeypatch.setattr(pickle, "load", lambda f: calls.append(1) or real_load(f))

    with TestClient(app) as client:
        for _ in range(5):
            response = client.post("/predict", json=sample_home_features)
            assert response.status_code == 200

    assert len(calls) == 1


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
