import json
import pickle
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Body, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

router = APIRouter()


class HomeFeatures(BaseModel):
    # Any house field may be null or left out; the imputer fills it. zipcode can't.
    bedrooms: int | None = None
    bathrooms: float | None = None
    sqft_living: float | None = None
    sqft_lot: float | None = None
    floors: float | None = None
    sqft_above: float | None = None
    sqft_basement: float | None = None
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
    return prediction


def predict_rows(state, rows: list[HomeFeatures]) -> list[dict]:
    """Price validated rows with one model call. Their zipcodes must be known.

    Join the demographics, fill missing house fields with the imputer, then
    predict with the columns in the model's order. Complete rows skip the imputer.
    Each result is {"predicted_price": float, "imputed_fields": {field: value}}.
    """
    data = [{**row.dict(), **state.demographics_by_zip[row.zipcode]} for row in rows]
    frame = pd.DataFrame(data)

    missing = frame[HOUSE_FIELDS].isna()
    gaps = missing.any(axis=1)
    if gaps.any():
        house = frame[HOUSE_FIELDS].astype(float)
        house.loc[gaps] = state.imputer.transform(house.loc[gaps])
        frame[HOUSE_FIELDS] = house

    prices = state.model.predict(frame[state.model_features])
    return [
        {
            "predicted_price": float(price),
            "imputed_fields": {
                field: float(frame.at[i, field])
                for field in HOUSE_FIELDS
                if missing.at[i, field]
            },
        }
        for i, price in enumerate(prices)
    ]


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
        for i, result in zip(positions, predict_rows(state, valid), strict=True):
            results[i] = result

    return results
