import json
import pickle


def load_model(model_path: str):
    with open(model_path, "rb") as model_file:
        model = pickle.load(model_file)
    return model


def load_features(features_path: str):
    with open(features_path) as features_file:
        features = json.load(features_file)
    return features


def get_demographics(zipcode: str, demographics_path: str):
    import pandas as pd

    demographics = pd.read_csv(demographics_path)
    demographic_data = demographics[demographics["zipcode"] == zipcode]
    if demographic_data.empty:
        return {}
    return demographic_data.to_dict(orient="records")[0]
