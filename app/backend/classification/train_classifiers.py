"""Training script for classification models.

Run: python -m classification.train_classifiers
(from app/backend/ directory)

Loads training data from multiple JSON files (original AGT labels,
augmented healthcare labels, and enterprise/telecom labels), trains
three sklearn pipelines, and saves to classification/models/*.pkl.
"""

import json
import re
from pathlib import Path

import joblib

from classification.classifiers import create_pipeline, _build_feature_text, _MODELS_DIR

_TRAINING_DIR = Path(__file__).resolve().parent / "training_data"


def _load_labels(filename: str) -> dict[str, str]:
    path = _TRAINING_DIR / filename
    with open(path, "r") as f:
        return json.load(f)


def _merge_label_files(filenames: list[str]) -> dict[str, str]:
    """Load and merge multiple label files. Later files override earlier ones."""
    merged = {}
    for fn in filenames:
        path = _TRAINING_DIR / fn
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
            merged.update(data)
            print(f"  Loaded {len(data)} labels from {fn}")
    return merged


def _load_metadata() -> list[dict]:
    """Load AGT_metadata.json to get field info for feature engineering."""
    meta_path = Path(__file__).resolve().parent.parent / "AGT_metadata.json"
    with open(meta_path, "r") as f:
        raw = f.read()
    raw = re.sub(r"^```\s*json?\s*\n", "", raw.strip())
    raw = re.sub(r"\n```\s*$", "", raw.strip())
    return json.loads(raw)


def _build_training_data(labels: dict[str, str], metadata: list[dict]) -> tuple[list[str], list[str]]:
    """Build feature text and label lists aligned by field name."""
    meta_lookup = {}
    for rec in metadata:
        meta_lookup[rec["Field Name"]] = rec

    X, y = [], []
    for field_name, label in labels.items():
        rec = meta_lookup.get(field_name, {})
        business_name = rec.get("FullName (Business Friendly Names)", "")
        max_length = rec.get("Max Length", 0)

        is_code = field_name.endswith("CD") or field_name.endswith("CDVAL")
        is_date = field_name.endswith("DT") or field_name.endswith("_DATE") or field_name.endswith("TSTMP")
        is_phone = "PHONE" in field_name.upper() or "MOBILE" in field_name.upper() or "CELL" in field_name.upper() or field_name in ("MDN", "CTN", "MSISDN", "TEL")
        is_blank = field_name.lower().startswith("blank") or field_name.upper() in ("FILLER", "FILLER1", "FILLER2", "FILLER3", "FILLER4", "RESERVED", "RESERVED1", "RESERVED2", "RESERVED3", "UNUSED", "UNUSED1", "UNUSED2", "SPARE", "PADDING", "PADDING1", "SPACER", "SPACER1", "SPACER2")

        text = _build_feature_text(
            field_name=field_name,
            business_name=business_name,
            is_code=is_code,
            is_date=is_date,
            is_phone=is_phone,
            is_blank=is_blank,
            max_length=max_length,
        )
        X.append(text)
        y.append(label)

    return X, y


def train_and_save():
    """Train all three classifiers and save to models/."""
    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    metadata = _load_metadata()
    print(f"Loaded {len(metadata)} field definitions from AGT_metadata.json")

    # Each model uses multiple label files merged together
    # Sources: original AGT, augmented healthcare, enterprise/retail,
    # vertical-specific: automotive (Ford), telecom (Verizon/T-Mobile)
    models = [
        ("sensitivity", [
            "sensitivity_labels.json",
            "augmented_sensitivity_labels.json",
            "enterprise_sensitivity_labels.json",
            "vertical_automotive_sensitivity.json",
            "vertical_telecom_sensitivity.json",
        ]),
        ("semantic_type", [
            "augmented_semantic_type_labels.json",
            "enterprise_semantic_type_labels.json",
            "vertical_automotive_semantic.json",
            "vertical_telecom_semantic.json",
        ]),
        ("format", [
            "augmented_format_labels.json",
            "enterprise_format_labels.json",
            "vertical_automotive_format.json",
            "vertical_telecom_format.json",
        ]),
    ]

    for model_name, label_files in models:
        print(f"\nTraining {model_name} classifier...")
        labels = _merge_label_files(label_files)
        X, y = _build_training_data(labels, metadata)
        print(f"  Total training samples: {len(X)}")

        label_counts = {}
        for label in y:
            label_counts[label] = label_counts.get(label, 0) + 1
        print(f"  Unique labels: {len(set(y))}")
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            print(f"    {label:30s}: {count:4d}")

        pipeline = create_pipeline()
        pipeline.fit(X, y)

        # Quick self-check
        train_score = pipeline.score(X, y)
        print(f"  Training accuracy: {train_score:.2%}")

        output_path = _MODELS_DIR / f"{model_name}.pkl"
        joblib.dump(pipeline, output_path)
        print(f"  Saved to {output_path}")

    print("\nAll models trained and saved successfully!")


if __name__ == "__main__":
    train_and_save()
