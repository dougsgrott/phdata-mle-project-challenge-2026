import json
import pickle

import pandas as pd
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HomeFeatures(BaseModel):
    bedrooms: int
    bathrooms: float
    sqft_living: float
    sqft_lot: float
    floors: float
    sqft_above: float
    sqft_basement: float
    zipcode: str


def load_artifacts():
    """Read the model, its feature order and the demographics table (once)."""
    with open("model/model.pkl", "rb") as model_file:
        model = pickle.load(model_file)
    with open("model/model_features.json") as features_file:
        model_features = json.load(features_file)
    demographics = pd.read_csv("data/zipcode_demographics.csv", dtype={"zipcode": str})
    demographics_by_zip = demographics.set_index("zipcode").to_dict(orient="index")
    return model, model_features, demographics_by_zip


@router.get("/health")
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns 200 if API is ready to accept requests.
    """
    return {"status": "healthy"}


@router.post("/predict")
async def predict(home_features: HomeFeatures, request: Request):
    state = request.app.state

    # One row: house fields + the zipcode's demographics, in the model's order
    row = {**home_features.dict(), **state.demographics_by_zip[home_features.zipcode]}
    input_data = pd.DataFrame([row], columns=state.model_features)

    # Make prediction
    prediction = state.model.predict(input_data)

    return {"predicted_price": prediction[0]}
