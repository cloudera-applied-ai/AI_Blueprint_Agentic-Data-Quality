"""Orchestrator: routes classification between sklearn classifiers and LLM.

Core routing logic:
1. Run all 3 sklearn classifiers on all columns -> results with confidence scores
2. Identify columns where any confidence < threshold (default 0.7)
3. If LLM available: classify low-confidence columns + ALL columns for business terms
4. Merge: LLM overrides classifier where invoked
5. Return unified ClassificationResult
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from classification.classifiers import classify_columns, ColumnClassification
from classification.llm_classifier import classify_with_llm, classify_with_llm_streaming


@dataclass
class ClassificationResult:
    """Complete classification result for all columns."""
    name: str
    columns: list[ColumnClassification]
    confidence_threshold: float
    llm_used: bool
    total_columns: int
    classifier_only_count: int
    llm_enhanced_count: int
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        sensitivity_counts = {}
        for c in self.columns:
            label = c.sensitivity_label or "unclassified"
            sensitivity_counts[label] = sensitivity_counts.get(label, 0) + 1

        return {
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns],
            "confidence_threshold": self.confidence_threshold,
            "llm_used": self.llm_used,
            "total_columns": self.total_columns,
            "classifier_only_count": self.classifier_only_count,
            "llm_enhanced_count": self.llm_enhanced_count,
            "created_at": self.created_at,
            "summary": {
                "sensitivity_counts": sensitivity_counts,
                "avg_sensitivity_confidence": _avg_conf(self.columns, "sensitivity_confidence"),
                "avg_semantic_confidence": _avg_conf(self.columns, "semantic_confidence"),
                "avg_format_confidence": _avg_conf(self.columns, "format_confidence"),
            },
        }


def _avg_conf(columns: list[ColumnClassification], attr: str) -> float:
    vals = [getattr(c, attr, 0.0) for c in columns]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def _merge_llm_results(
    classifications: list[ColumnClassification],
    llm_results: list[dict],
    llm_field_names: set[str] | None = None,
) -> None:
    """Merge LLM results into existing classifier results in-place."""
    llm_lookup = {r["field_name"]: r for r in llm_results if "field_name" in r}

    for clf in classifications:
        llm = llm_lookup.get(clf.field_name)
        if not llm:
            continue

        # Always take business term from LLM
        if llm.get("business_term"):
            clf.business_term = llm["business_term"]
            clf.business_term_confidence = 0.85

        # Always take HL7/FHIR and regulatory from LLM
        if llm.get("hl7_fhir_mapping"):
            clf.hl7_fhir_mapping = llm["hl7_fhir_mapping"]
        if llm.get("regulatory_tags"):
            clf.regulatory_tags = llm["regulatory_tags"]

        # Override sensitivity/semantic only for low-confidence columns
        if llm_field_names and clf.field_name in llm_field_names:
            if llm.get("sensitivity") and llm["sensitivity"] in ("PII", "PHI", "internal", "public"):
                clf.sensitivity_label = llm["sensitivity"]
                clf.sensitivity_confidence = 0.80
            if llm.get("semantic_type"):
                clf.semantic_type = llm["semantic_type"]
                clf.semantic_confidence = 0.80
            clf.classified_by = "classifier+llm"
        elif clf.classified_by == "classifier":
            clf.classified_by = "classifier+llm"


def classify_metadata(
    fields: list,
    name: str = "AGT Classification",
    confidence_threshold: float = 0.7,
    use_llm: bool = True,
    llm_client=None,
    llm_model: str = "",
) -> ClassificationResult:
    """Synchronous classification: run classifiers, optionally enhance with LLM.

    Args:
        fields: List of FieldMeta objects.
        name: Name for this classification run.
        confidence_threshold: Below this, columns are sent to LLM.
        use_llm: Whether to use LLM for enhancement.
        llm_client: OpenAI-compatible client (required if use_llm=True).
        llm_model: Model name for LLM.
    """
    # Step 1: Run sklearn classifiers
    classifications = classify_columns(fields)

    # Step 2: Identify low-confidence columns
    low_conf_fields = set()
    for clf in classifications:
        if (clf.sensitivity_confidence < confidence_threshold or
            clf.semantic_confidence < confidence_threshold or
            clf.format_confidence < confidence_threshold):
            low_conf_fields.add(clf.field_name)

    llm_used = False
    llm_enhanced_count = 0

    # Step 3: LLM classification
    if use_llm and llm_client and llm_model:
        try:
            llm_results = classify_with_llm(
                client=llm_client,
                model=llm_model,
                fields=fields,
                existing_classifications=classifications,
            )
            _merge_llm_results(classifications, llm_results, low_conf_fields)
            llm_used = True
            llm_enhanced_count = len(fields)
        except Exception:
            pass  # LLM failure is non-fatal; classifier results stand

    return ClassificationResult(
        name=name,
        columns=classifications,
        confidence_threshold=confidence_threshold,
        llm_used=llm_used,
        total_columns=len(fields),
        classifier_only_count=len(fields) - llm_enhanced_count,
        llm_enhanced_count=llm_enhanced_count,
    )


def classify_metadata_stream(
    fields: list,
    name: str = "AGT Classification",
    confidence_threshold: float = 0.7,
    use_llm: bool = True,
    llm_client=None,
    llm_model: str = "",
):
    """Streaming classification: yields SSE events for progress tracking.

    Events: classifier_start, classifier_done, llm_start, llm_batch,
    llm_batch_result, llm_done, classification_result, done.
    """
    # Step 1: Classifier phase
    yield {"event": "classifier_start", "data": {"total_columns": len(fields)}}

    classifications = classify_columns(fields)

    yield {"event": "classifier_done", "data": {
        "total_columns": len(fields),
        "columns_classified": len(classifications),
    }}

    # Step 2: Identify low-confidence columns
    low_conf_fields = set()
    for clf in classifications:
        if (clf.sensitivity_confidence < confidence_threshold or
            clf.semantic_confidence < confidence_threshold or
            clf.format_confidence < confidence_threshold):
            low_conf_fields.add(clf.field_name)

    yield {"event": "classifier_confidence", "data": {
        "low_confidence_count": len(low_conf_fields),
        "low_confidence_fields": sorted(low_conf_fields)[:20],
    }}

    llm_used = False
    llm_enhanced_count = 0

    # Step 3: LLM enhancement
    if use_llm and llm_client and llm_model:
        yield {"event": "llm_start", "data": {"total_columns": len(fields)}}

        try:
            all_llm_results = []
            for event in classify_with_llm_streaming(
                client=llm_client,
                model=llm_model,
                fields=fields,
                existing_classifications=classifications,
            ):
                yield event
                if event["event"] == "llm_batch_result":
                    results = event["data"].get("results", [])
                    all_llm_results.extend(results)

            _merge_llm_results(classifications, all_llm_results, low_conf_fields)
            llm_used = True
            llm_enhanced_count = len(fields)

        except Exception as e:
            yield {"event": "llm_error", "data": {"error": str(e)[:200]}}

        yield {"event": "llm_done", "data": {"enhanced_count": llm_enhanced_count}}

    # Step 4: Build and yield final result
    result = ClassificationResult(
        name=name,
        columns=classifications,
        confidence_threshold=confidence_threshold,
        llm_used=llm_used,
        total_columns=len(fields),
        classifier_only_count=len(fields) - llm_enhanced_count,
        llm_enhanced_count=llm_enhanced_count,
    )

    yield {"event": "classification_result", "data": result.to_dict()}
    yield {"event": "done", "data": {}}
