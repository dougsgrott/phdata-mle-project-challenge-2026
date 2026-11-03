import pytest


@pytest.mark.integration
def test_predict_endpoint_integration(http_client, sample_home_features):
    """Test the /predict endpoint via HTTP using httpx client."""
    response = http_client.post("/predict", json=sample_home_features)
    assert response.status_code == 200
    response_data = response.json()
    assert "predicted_price" in response_data
    assert isinstance(response_data["predicted_price"], float)
    assert response_data["predicted_price"] > 0


@pytest.mark.integration
def test_health_endpoint_integration(http_client):
    """Test the /health endpoint via HTTP using httpx client."""
    response = http_client.get("/health")
    assert response.status_code == 200
    response_data = response.json()
    assert "status" in response_data
    assert response_data["status"] == "healthy"


@pytest.mark.integration
def test_predict_with_nulls_integration(http_client):
    """The brief's example with missing values, against the built image."""
    body = {
        "bedrooms": 3,
        "bathrooms": None,
        "sqft_living": 2000,
        "sqft_lot": None,
        "floors": 2,
        "sqft_above": 1500,
        "sqft_basement": 500,
        "zipcode": "98125",
    }

    response = http_client.post("/predict", json=body)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["predicted_price"] > 0
    assert set(response_data["imputed_fields"]) == {"bathrooms", "sqft_lot"}
