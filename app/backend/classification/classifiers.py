"""Sklearn-based classifiers for column metadata classification.

Three classifiers using TfidfVectorizer + LogisticRegression:
  - SensitivityClassifier: PII / PHI / internal / public
  - SemanticTypeClassifier: ~20 semantic type labels
  - FormatClassifier: ~15 format labels

Models are lazy-loaded from classification/models/*.pkl.
"""

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

_MODELS_DIR = Path(__file__).resolve().parent / "models"
_lock = threading.Lock()


@dataclass
class ColumnClassification:
    """Classification result for a single column."""
    field_name: str
    sensitivity_label: str = ""
    sensitivity_confidence: float = 0.0
    semantic_type: str = ""
    semantic_confidence: float = 0.0
    format_label: str = ""
    format_confidence: float = 0.0
    business_term: str = ""
    business_term_confidence: float = 0.0
    hl7_fhir_mapping: str = ""
    regulatory_tags: list[str] = field(default_factory=list)
    classified_by: str = "classifier"

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "sensitivity_label": self.sensitivity_label,
            "sensitivity_confidence": round(self.sensitivity_confidence, 4),
            "semantic_type": self.semantic_type,
            "semantic_confidence": round(self.semantic_confidence, 4),
            "format_label": self.format_label,
            "format_confidence": round(self.format_confidence, 4),
            "business_term": self.business_term,
            "business_term_confidence": round(self.business_term_confidence, 4),
            "hl7_fhir_mapping": self.hl7_fhir_mapping,
            "regulatory_tags": self.regulatory_tags,
            "classified_by": self.classified_by,
        }


def _build_feature_text(field_name: str, business_name: str = "",
                        is_code: bool = False, is_date: bool = False,
                        is_phone: bool = False, is_blank: bool = False,
                        max_length: int = 0) -> str:
    """Build a feature string for the TF-IDF vectorizer.

    Combines field name character n-grams (via TF-IDF analyzer),
    business name tokens, and metadata flags into a single text string.
    """
    parts = [field_name]
    if business_name:
        parts.append(business_name)
    if is_code:
        parts.append("FLAG_CODE")
    if is_date:
        parts.append("FLAG_DATE")
    if is_phone:
        parts.append("FLAG_PHONE")
    if is_blank:
        parts.append("FLAG_BLANK")
    if max_length <= 3:
        parts.append("LEN_SHORT")
    elif max_length <= 10:
        parts.append("LEN_MEDIUM")
    elif max_length <= 50:
        parts.append("LEN_LONG")
    else:
        parts.append("LEN_VERY_LONG")
    return " ".join(parts)


def create_pipeline() -> Pipeline:
    """Create an untrained sklearn pipeline."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=500,
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            solver="lbfgs",
            class_weight="balanced",
        )),
    ])


# Lazy-loaded model singletons
_sensitivity_model: Pipeline | None = None
_semantic_model: Pipeline | None = None
_format_model: Pipeline | None = None


def _load_model(name: str) -> Pipeline | None:
    """Load a model from disk, returning None if not found."""
    path = _MODELS_DIR / f"{name}.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


def get_sensitivity_model() -> Pipeline | None:
    global _sensitivity_model
    with _lock:
        if _sensitivity_model is None:
            _sensitivity_model = _load_model("sensitivity")
        return _sensitivity_model


def get_semantic_model() -> Pipeline | None:
    global _semantic_model
    with _lock:
        if _semantic_model is None:
            _semantic_model = _load_model("semantic_type")
        return _semantic_model


def get_format_model() -> Pipeline | None:
    global _format_model
    with _lock:
        if _format_model is None:
            _format_model = _load_model("format")
        return _format_model


def classify_columns(fields: list) -> list[ColumnClassification]:
    """Run all three classifiers on a list of FieldMeta objects.

    Returns a ColumnClassification for each field with confidence scores.
    If models aren't trained yet, returns empty labels with 0.0 confidence.
    """
    sensitivity_model = get_sensitivity_model()
    semantic_model = get_semantic_model()
    format_model = get_format_model()

    # Build feature texts
    feature_texts = []
    for f in fields:
        feature_texts.append(_build_feature_text(
            field_name=f.field_name,
            business_name=f.business_name,
            is_code=f.is_code_field,
            is_date=f.is_date_field,
            is_phone=f.is_phone_field,
            is_blank=f.is_blank_field,
            max_length=f.max_length,
        ))

    results = []
    for i, f in enumerate(fields):
        clf_result = ColumnClassification(field_name=f.field_name)

        text = [feature_texts[i]]

        if sensitivity_model is not None:
            pred = sensitivity_model.predict(text)[0]
            proba = sensitivity_model.predict_proba(text)[0]
            clf_result.sensitivity_label = pred
            clf_result.sensitivity_confidence = float(max(proba))

        if semantic_model is not None:
            pred = semantic_model.predict(text)[0]
            proba = semantic_model.predict_proba(text)[0]
            clf_result.semantic_type = pred
            clf_result.semantic_confidence = float(max(proba))

        if format_model is not None:
            pred = format_model.predict(text)[0]
            proba = format_model.predict_proba(text)[0]
            clf_result.format_label = pred
            clf_result.format_confidence = float(max(proba))

        results.append(clf_result)

    return results
