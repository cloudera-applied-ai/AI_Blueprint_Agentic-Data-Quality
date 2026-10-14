"""Parse AGT_metadata.json into structured field metadata."""

import json
import re
from dataclasses import dataclass


@dataclass
class FieldMeta:
    position: int
    field_name: str
    max_length: int
    business_name: str

    @property
    def is_code_field(self) -> bool:
        return self.field_name.endswith("CD") or self.field_name.endswith("CDVAL")

    @property
    def is_date_field(self) -> bool:
        return self.field_name.endswith("DT")

    @property
    def is_phone_field(self) -> bool:
        return "PHONE" in self.field_name

    @property
    def is_blank_field(self) -> bool:
        return self.field_name.lower().startswith("blank")


def parse_metadata(path: str) -> list[FieldMeta]:
    """Load AGT_metadata.json, stripping markdown fences if present."""
    with open(path, "r") as f:
        raw = f.read()

    # Strip ``` json ... ``` fences
    raw = re.sub(r"^```\s*json?\s*\n", "", raw.strip())
    raw = re.sub(r"\n```\s*$", "", raw.strip())

    records = json.loads(raw)
    fields = []
    for rec in records:
        fields.append(FieldMeta(
            position=rec["Position"],
            field_name=rec["Field Name"],
            max_length=rec["Max Length"],
            business_name=rec.get("FullName (Business Friendly Names)", ""),
        ))
    fields.sort(key=lambda f: f.position)
    return fields


def get_column_names(fields: list[FieldMeta]) -> list[str]:
    """Return ordered list of column names for DuckDB loading."""
    return [f.field_name for f in fields]
