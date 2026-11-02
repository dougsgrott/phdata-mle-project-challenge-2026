import json
import pickle
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Body, Request
from fastapi.exceptions import RequestValidationError
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


# The house fields, in the model's order (a unit test checks model_features.json)
HOUSE_FIELDS = [name for name in HomeFeatures.model_fields if name != "zipcode"]


def load_artifacts():
    """Read the model, its feature order and the demographics table (once)."""
    with open("model/model.pkl", "rb") as model_file:
        model = pickle.load(model_file)
    with open("model/model_features.json") as features_file:
        model_features = json.load(features_file)
    with open("model/imputer.pkl", "rb") as imputer_file:
        imputer = pickle.load(imputer_file)
    demographics = pd.read_csv("data/zipcode_demographics.csv", dtype={"zipcode": str})
    demographics_by_zip = demographics.set_index("zipcode").to_dict(orient="index")
    return model, model_features, demographics_by_zip, imputer


@router.get("/health")
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns 200 if API is ready to accept requests.
    """
    return {"status": "healthy"}


def unknown_zipcode(zipcode: str) -> str:
    """Same wording for /predict and /predict/batch."""
    return f"zipcode {zipcode} is not in the demographics data"


@router.post("/predict")
async def predict(home_features: HomeFeatures, request: Request):
    state = request.app.state
    zipcode = home_features.zipcode
    request.state.zipcode = zipcode

    # Only zipcodes with demographics can be priced (D9: 422, not 500)
    if zipcode not in state.demographics_by_zip:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "zipcode"),
                    "msg": unknown_zipcode(zipcode),
                    "input": zipcode,
                }
            ]
        )

    # One row: house fields + the zipcode's demographics, in the model's order
    prediction = predict_rows(state, [home_features])[0]
    return {"predicted_price": prediction}


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
    request.state.rows = len(rows)
    results: list[dict] = [{} for _ in rows]
    valid, positions = [], []

    for i, raw in enumerate(rows):
        try:
            row = HomeFeatures.model_validate(raw)
        except ValidationError as exc:
            results[i] = {"error": describe(exc)}
            continue
        if row.zipcode not in state.demographics_by_zip:
            results[i] = {"error": f"zipcode: {unknown_zipcode(row.zipcode)}"}
            continue
        valid.append(row)
        positions.append(i)

    if valid:
        for i, price in zip(positions, predict_rows(state, valid), strict=True):
            results[i] = {"predicted_price": price}

    return results
