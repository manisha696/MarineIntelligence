"""
PFZ XGBoost Training
---------------------

Purpose:
Train an XGBoost model for Fishing Potential scoring.

Current training target:
The existing rule-based PFZ score generated from:
    - Chlorophyll
    - SST

Important:
This is a baseline ML model. Since the target is generated from
the existing rule-based PFZ system, the XGBoost model learns
that baseline behavior.

Later, real historical fish-catch / PFZ-labelled data can replace
this synthetic target to create a scientifically independent model.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split

from xgboost import XGBRegressor


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"

DATA_DIR.mkdir(exist_ok=True)
MODEL_DIR.mkdir(exist_ok=True)

DATASET_PATH = DATA_DIR / "pfz_training_dataset.csv"
MODEL_PATH = MODEL_DIR / "pfz_xgboost_model.joblib"


# ============================================================
# SETTINGS
# ============================================================

RANDOM_STATE = 42

FEATURES = [
    "chlorophyll",
    "sst",
]

TARGET = "fishing_score"


# ============================================================
# RULE-BASED BASELINE
# ============================================================

def calculate_chlorophyll_score(chlorophyll):
    """
    Convert chlorophyll into a 0-100 score.

    This follows the current PFZ baseline concept:
    higher chlorophyll -> higher potential.
    """

    if chlorophyll <= 0:
        return 0.0

    if chlorophyll >= 3.0:
        return 100.0

    return (chlorophyll / 3.0) * 100.0


def calculate_sst_score(sst):
    """
    Convert SST into a 0-100 score.

    Optimal SST is currently assumed to be 27 C.

    The score decreases as SST moves away from 27 C.
    """

    optimal_sst = 27.0

    distance = abs(sst - optimal_sst)

    score = 100.0 - (distance * 12.0)

    return max(0.0, min(100.0, score))


def calculate_fishing_score(chlorophyll, sst):
    """
    Current PFZ baseline:

        Chlorophyll = 60%
        SST         = 40%
    """

    chlorophyll_score = calculate_chlorophyll_score(
        chlorophyll
    )

    sst_score = calculate_sst_score(
        sst
    )

    score = (
        chlorophyll_score * 0.60
        + sst_score * 0.40
    )

    return max(0.0, min(100.0, score))


# ============================================================
# GENERATE TRAINING DATA
# ============================================================

def generate_dataset(
    number_of_samples=5000,
):
    """
    Generate synthetic PFZ training data.

    This creates combinations of chlorophyll and SST
    covering realistic ranges for the current baseline.
    """

    rng = np.random.default_rng(RANDOM_STATE)

    chlorophyll = rng.uniform(
        0.1,
        6.0,
        number_of_samples,
    )

    sst = rng.uniform(
        22.0,
        34.0,
        number_of_samples,
    )

    scores = [
        calculate_fishing_score(
            chl,
            temperature,
        )
        for chl, temperature in zip(
            chlorophyll,
            sst,
        )
    ]

    dataset = pd.DataFrame(
        {
            "chlorophyll": chlorophyll,
            "sst": sst,
            "fishing_score": scores,
        }
    )

    return dataset


# ============================================================
# LOAD OR CREATE DATASET
# ============================================================

def prepare_dataset():
    """
    Load existing dataset if available.

    Otherwise generate a new dataset.
    """

    if DATASET_PATH.exists():

        print()
        print("Existing dataset found:")
        print(DATASET_PATH)

        dataset = pd.read_csv(
            DATASET_PATH
        )

    else:

        print()
        print("No dataset found.")
        print("Generating PFZ training dataset...")

        dataset = generate_dataset(
            number_of_samples=5000
        )

        dataset.to_csv(
            DATASET_PATH,
            index=False,
        )

        print()
        print("Dataset created:")
        print(DATASET_PATH)

    return dataset


# ============================================================
# VALIDATE DATASET
# ============================================================

def validate_dataset(dataset):

    required_columns = FEATURES + [TARGET]

    missing_columns = [
        column
        for column in required_columns
        if column not in dataset.columns
    ]

    if missing_columns:

        raise ValueError(
            "Dataset is missing required columns: "
            + ", ".join(missing_columns)
        )

    dataset = dataset[
        required_columns
    ].copy()

    dataset = dataset.dropna()

    dataset = dataset[
        np.isfinite(
            dataset[FEATURES + [TARGET]]
        ).all(axis=1)
    ]

    if len(dataset) < 100:

        raise ValueError(
            "Not enough valid training samples."
        )

    return dataset


# ============================================================
# TRAIN MODEL
# ============================================================

def train_model(dataset):

    X = dataset[FEATURES]

    y = dataset[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
    )

    print()
    print("=" * 60)
    print("TRAINING XGBOOST MODEL")
    print("=" * 60)

    print()
    print(f"Total samples : {len(dataset)}")
    print(f"Training      : {len(X_train)}")
    print(f"Testing       : {len(X_test)}")

    model = XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.90,
        objective="reg:squarederror",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    model.fit(
        X_train,
        y_train,
        verbose=False,
    )

    predictions = model.predict(
        X_test
    )

    predictions = np.clip(
        predictions,
        0,
        100,
    )

    # ========================================================
    # METRICS
    # ========================================================

    mae = mean_absolute_error(
        y_test,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions,
        )
    )

    r2 = r2_score(
        y_test,
        predictions,
    )

    print()
    print("=" * 60)
    print("MODEL PERFORMANCE")
    print("=" * 60)

    print()
    print(
        f"MAE  : {mae:.4f}"
    )

    print(
        f"RMSE : {rmse:.4f}"
    )

    print(
        f"R²   : {r2:.4f}"
    )

    # ========================================================
    # FEATURE IMPORTANCE
    # ========================================================

    print()
    print("=" * 60)
    print("FEATURE IMPORTANCE")
    print("=" * 60)

    importance = model.feature_importances_

    feature_importance = sorted(
        zip(
            FEATURES,
            importance,
        ),
        key=lambda x: x[1],
        reverse=True,
    )

    for feature, value in feature_importance:

        print(
            f"{feature:<20} "
            f"{value:.4f}"
        )

    return model


# ============================================================
# SAVE MODEL
# ============================================================

def save_model(model):

    joblib.dump(
        model,
        MODEL_PATH,
    )

    print()
    print("=" * 60)
    print("MODEL SAVED")
    print("=" * 60)

    print()
    print(MODEL_PATH)


# ============================================================
# TEST SAMPLE PREDICTIONS
# ============================================================

def test_predictions(model):

    test_samples = pd.DataFrame(
        [
            {
                "chlorophyll": 3.0,
                "sst": 27.0,
            },
            {
                "chlorophyll": 2.5,
                "sst": 29.0,
            },
            {
                "chlorophyll": 1.0,
                "sst": 31.0,
            },
        ]
    )

    predictions = model.predict(
        test_samples[FEATURES]
    )

    predictions = np.clip(
        predictions,
        0,
        100,
    )

    print()
    print("=" * 60)
    print("SAMPLE PREDICTIONS")
    print("=" * 60)

    for index, prediction in enumerate(
        predictions
    ):

        chlorophyll = test_samples.iloc[
            index
        ]["chlorophyll"]

        sst = test_samples.iloc[
            index
        ]["sst"]

        level = get_pfz_level(
            prediction
        )

        print()
        print(
            f"Chlorophyll : {chlorophyll:.2f}"
        )

        print(
            f"SST         : {sst:.2f} °C"
        )

        print(
            f"Score       : {prediction:.2f}"
        )

        print(
            f"Potential   : {level}"
        )


# ============================================================
# PFZ LEVEL
# ============================================================

def get_pfz_level(score):

    if score >= 70:
        return "HIGH"

    if score >= 40:
        return "MODERATE"

    return "LOW"


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("MARINE INTELLIGENCE")
    print("PFZ XGBOOST TRAINING")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Dataset
    # --------------------------------------------------------

    dataset = prepare_dataset()

    # --------------------------------------------------------
    # 2. Validation
    # --------------------------------------------------------

    dataset = validate_dataset(
        dataset
    )

    print()
    print(
        f"Valid samples: {len(dataset)}"
    )

    print()
    print("Dataset preview:")
    print(
        dataset.head()
    )

    # --------------------------------------------------------
    # 3. Train
    # --------------------------------------------------------

    model = train_model(
        dataset
    )

    # --------------------------------------------------------
    # 4. Save
    # --------------------------------------------------------

    save_model(
        model
    )

    # --------------------------------------------------------
    # 5. Test
    # --------------------------------------------------------

    test_predictions(
        model
    )

    print()
    print("=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)

    print()
    print("Next step:")
    print(
        "Integrate the saved XGBoost model "
        "into the FastAPI PFZ endpoint."
    )


if __name__ == "__main__":
    main()