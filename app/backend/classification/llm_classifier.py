"""LLM-based classification for complex metadata tasks.

Uses the existing agent/llm_client.py (OpenAI SDK) to classify columns
that need deeper analysis: business term mapping, HL7/FHIR ontology,
regulatory tagging, and refinement of low-confidence sklearn results.
"""

import json

from classification.prompts import CLASSIFICATION_SYSTEM_PROMPT, build_classification_prompt
from classification.classifiers import ColumnClassification


def classify_with_llm(
    client,
    model: str,
    fields: list,
    existing_classifications: list[ColumnClassification] | None = None,
    batch_size: int = 20,
) -> list[dict]:
    """Classify columns using the LLM in batches.

    Args:
        client: OpenAI-compatible client (from agent/llm_client.py).
        model: Model name for the LLM.
        fields: List of FieldMeta objects.
        existing_classifications: Optional sklearn results to include as context.
        batch_size: Number of columns per LLM call.

    Returns:
        List of dicts with LLM classification results.
    """
    # Build column info dicts with optional classifier context
    clf_lookup = {}
    if existing_classifications:
        for c in existing_classifications:
            clf_lookup[c.field_name] = c

    columns = []
    for f in fields:
        col = {
            "field_name": f.field_name,
            "business_name": f.business_name,
            "max_length": f.max_length,
            "is_code": f.is_code_field,
            "is_date": f.is_date_field,
            "is_phone": f.is_phone_field,
            "is_blank": f.is_blank_field,
        }
        if f.field_name in clf_lookup:
            clf = clf_lookup[f.field_name]
            col["classifier_sensitivity"] = clf.sensitivity_label
            col["classifier_semantic_type"] = clf.semantic_type
        columns.append(col)

    # Process in batches
    all_results = []
    for i in range(0, len(columns), batch_size):
        batch = columns[i:i + batch_size]
        prompt = build_classification_prompt(batch)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            text = response.choices[0].message.content or ""
            # Extract JSON from response (handle markdown fences)
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.endswith("```"):
                    text = text[:-3].strip()

            batch_results = json.loads(text)
            if isinstance(batch_results, list):
                all_results.extend(batch_results)

        except (json.JSONDecodeError, KeyError, IndexError, Exception) as e:
            # If LLM fails for a batch, skip it — classifier results still stand
            for col in batch:
                all_results.append({
                    "field_name": col["field_name"],
                    "business_term": col.get("business_name", ""),
                    "sensitivity": "",
                    "semantic_type": "",
                    "hl7_fhir_mapping": "",
                    "regulatory_tags": [],
                    "error": str(e)[:100],
                })

    return all_results


def classify_with_llm_streaming(
    client,
    model: str,
    fields: list,
    existing_classifications: list[ColumnClassification] | None = None,
    batch_size: int = 20,
):
    """Generator that yields SSE events while classifying with LLM.

    Yields dicts with "event" and "data" keys for SSE streaming.
    """
    clf_lookup = {}
    if existing_classifications:
        for c in existing_classifications:
            clf_lookup[c.field_name] = c

    columns = []
    for f in fields:
        col = {
            "field_name": f.field_name,
            "business_name": f.business_name,
            "max_length": f.max_length,
            "is_code": f.is_code_field,
            "is_date": f.is_date_field,
            "is_phone": f.is_phone_field,
            "is_blank": f.is_blank_field,
        }
        if f.field_name in clf_lookup:
            clf = clf_lookup[f.field_name]
            col["classifier_sensitivity"] = clf.sensitivity_label
            col["classifier_semantic_type"] = clf.semantic_type
        columns.append(col)

    total_batches = (len(columns) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        batch = columns[start:start + batch_size]

        yield {
            "event": "llm_batch",
            "data": {
                "batch": batch_idx + 1,
                "total_batches": total_batches,
                "columns": [c["field_name"] for c in batch],
            },
        }

        prompt = build_classification_prompt(batch)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            text = response.choices[0].message.content or ""
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:])
                if text.endswith("```"):
                    text = text[:-3].strip()

            batch_results = json.loads(text)
            if isinstance(batch_results, list):
                yield {
                    "event": "llm_batch_result",
                    "data": {"batch": batch_idx + 1, "results": batch_results},
                }

        except (json.JSONDecodeError, KeyError, IndexError, Exception) as e:
            fallback = []
            for col in batch:
                fallback.append({
                    "field_name": col["field_name"],
                    "business_term": col.get("business_name", ""),
                    "sensitivity": "",
                    "semantic_type": "",
                    "hl7_fhir_mapping": "",
                    "regulatory_tags": [],
                    "error": str(e)[:100],
                })
            yield {
                "event": "llm_batch_result",
                "data": {"batch": batch_idx + 1, "results": fallback, "error": str(e)[:200]},
            }
