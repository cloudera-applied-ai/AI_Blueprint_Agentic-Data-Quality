"""LLM prompt templates for metadata classification."""

CLASSIFICATION_SYSTEM_PROMPT = """You are a healthcare data governance specialist with deep expertise in:
- HIPAA privacy rules (PHI/PII identification)
- HL7 FHIR resource mapping
- Healthcare data standards (X12, NCPDP, ICD-10, CPT)
- Data sensitivity classification for regulatory compliance

You analyze healthcare data field definitions and classify them across multiple dimensions.
You always respond with valid JSON and nothing else."""


def build_classification_prompt(columns: list[dict]) -> str:
    """Build a prompt for LLM-based column classification.

    Args:
        columns: List of dicts with field_name, business_name, max_length,
                 is_code, is_date, is_phone, is_blank, and optionally
                 classifier_sensitivity, classifier_semantic_type, classifier_format.
    """
    col_lines = []
    for c in columns:
        parts = [
            f"  {c['field_name']}",
            f"biz_name={c.get('business_name', '')}",
            f"max_len={c.get('max_length', 0)}",
        ]
        flags = []
        if c.get("is_code"):
            flags.append("code")
        if c.get("is_date"):
            flags.append("date")
        if c.get("is_phone"):
            flags.append("phone")
        if c.get("is_blank"):
            flags.append("blank")
        if flags:
            parts.append(f"flags=[{','.join(flags)}]")

        # Include classifier predictions for context
        if c.get("classifier_sensitivity"):
            parts.append(f"clf_sens={c['classifier_sensitivity']}")
        if c.get("classifier_semantic_type"):
            parts.append(f"clf_type={c['classifier_semantic_type']}")

        col_lines.append(" | ".join(parts))

    columns_text = "\n".join(col_lines)

    return f"""Classify the following healthcare data fields. For each field, provide:

1. **business_term**: A clear, human-readable business term (e.g., "Social Security Number", "Member Birth Date")
2. **sensitivity**: One of: PII, PHI, internal, public
   - PII: Directly identifies a person (SSN, name, email, phone, address)
   - PHI: Health-related personal info (diagnosis, coverage, birth date, gender, ethnicity)
   - internal: Business operational data (codes, dates, IDs not directly identifying)
   - public: No sensitivity (blank/reserved fields)
3. **semantic_type**: Specific data type (e.g., "Social Security Number", "US State Code", "Date", "Phone Number")
4. **hl7_fhir_mapping**: The HL7 FHIR resource and element this maps to (e.g., "Patient.identifier", "Patient.name.given", "Coverage.period.start"). Use empty string if no mapping.
5. **regulatory_tags**: List of applicable regulations (e.g., ["HIPAA", "42CFR"], ["HIPAA", "ACA"]). Use empty list if none.

Fields to classify:
{columns_text}

Respond with a JSON array. Each element must have exactly these keys:
field_name, business_term, sensitivity, semantic_type, hl7_fhir_mapping, regulatory_tags

JSON response:"""
