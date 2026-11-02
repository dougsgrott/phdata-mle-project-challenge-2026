import json
import pickle
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Body, Request
from pydantic import BaseModel, ValidationError

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


def predict_rows(state, rows: list[HomeFeatures]) -> list[float]:
    """Price validated rows with one model call. Their zipcodes must be known."""
    data = [{**row.dict(), **state.demographics_by_zip[row.zipcode]} for row in rows]
    input_data = pd.DataFrame(data, columns=state.model_features)
    return [float(price) for price in state.model.predict(input_data)]


def describe(exc: ValidationError) -> str:
    """One readable line per validation problem, e.g. 'bedrooms: Input should be...'."""
    return "; ".join(
        f"{'.'.join(map(str, err['loc']))}: {err['msg']}" if err["loc"] else err["msg"]
        for err in exc.errors()
    )


@router.post("/predict/batch")
async def predict_batch(request: Request, rows: Annotated[list[Any], Body()]):
    """Price a list of houses. Bad rows get an error; the others still get a price."""
    state = request.app.state
    results: list[dict] = [{} for _ in rows]
    valid, positions = [], []

    for i, raw in enumerate(rows):
        try:
            row = HomeFeatures.model_validate(raw)
        except ValidationError as exc:
            results[i] = {"error": describe(exc)}
            continue
        if row.zipcode not in state.demographics_by_zip:
            results[i] = {"error": f"zipcode: unknown zipcode {row.zipcode}"}
            continue
        valid.append(row)
        positions.append(i)

    if valid:
        for i, price in zip(positions, predict_rows(state, valid), strict=True):
            results[i] = {"predicted_price": price}

    return results
