"""On-disk data schema: file names, field names and conversion between schema versions.

Schema 1 (versions up to the "alan-adlari" change): Turkish file and field names, every file is a
bare JSON list.
Schema 2 (current): English file and field names, every file is an object with a version:
    items.json               {"schema_version": 2, "items": [...]}
    categories.json          {"schema_version": 2, "categories": [...]}
    completion_history.json  {"schema_version": 2, "completions": [...]}

The app works with schema-2 field names in memory. Reading accepts both schemas (a bare list or
records with schema-1 keys are converted on the fly), so a file from an older version still loads.
Only key names (and the history "type" values) change; every value is kept as it is. Unknown keys
are kept unchanged.
"""
SCHEMA_VERSION = 2
KINDS = ("items", "categories", "history")

FILE_NAMES = {
    1: {"items": "gorevler.json", "categories": "kategoriler.json", "history": "tamamlama_gecmisi.json"},
    2: {"items": "items.json", "categories": "categories.json", "history": "completion_history.json"},
}
# Key holding the list inside a schema-2 file.
LIST_KEYS = {"items": "items", "categories": "categories", "history": "completions"}

# Task/routine fields (items file).
ITEM_FIELDS_V1_TO_V2 = {
    "id": "id",
    "görev": "title",
    "tamamlandı": "done",
    "yıl": "year",
    "ay": "month",
    "gün": "day",
    "saat": "hour",
    "dakika": "minute",
    "rutin": "routine",
    "kategori": "category",
    "sıklık": "frequency",
    "streak": "streak",
    "hafta_gunleri": "weekdays",
}
# Completion history record fields and the values of its "type" field.
HISTORY_FIELDS_V1_TO_V2 = {"tarih": "date", "tip": "type"}
HISTORY_TYPES_V1_TO_V2 = {"rutin": "routine", "görev": "task"}

# Legacy stored category value meaning "no category" (normalised to "" by logic.fill_missing_fields,
# exactly as before; the conversion itself does not change values).
LEGACY_NO_CATEGORY = "Kategorisiz"

ITEM_FIELDS_V2_TO_V1 = {v: k for k, v in ITEM_FIELDS_V1_TO_V2.items()}
HISTORY_FIELDS_V2_TO_V1 = {v: k for k, v in HISTORY_FIELDS_V1_TO_V2.items()}
HISTORY_TYPES_V2_TO_V1 = {v: k for k, v in HISTORY_TYPES_V1_TO_V2.items()}


def _rename(record, mapping, reverse):
    """Renames keys; a key already in the target schema wins over its other-schema twin."""
    if not isinstance(record, dict):
        return record
    out = {}
    for key, value in record.items():
        if key in mapping:
            out.setdefault(mapping[key], value)
    for key, value in record.items():
        if key not in mapping:
            if key in reverse or key not in out:
                out[key] = value
    # keep the original key order as far as possible
    order = [mapping.get(k, k) for k in record]
    return {k: out[k] for k in dict.fromkeys(order) if k in out}


def item_to_v2(item):
    return _rename(item, ITEM_FIELDS_V1_TO_V2, ITEM_FIELDS_V2_TO_V1)


def item_to_v1(item):
    return _rename(item, ITEM_FIELDS_V2_TO_V1, ITEM_FIELDS_V1_TO_V2)


def history_to_v2(record):
    out = _rename(record, HISTORY_FIELDS_V1_TO_V2, HISTORY_FIELDS_V2_TO_V1)
    if isinstance(out, dict) and out.get("type") in HISTORY_TYPES_V1_TO_V2:
        out["type"] = HISTORY_TYPES_V1_TO_V2[out["type"]]
    return out


def history_to_v1(record):
    out = _rename(record, HISTORY_FIELDS_V2_TO_V1, HISTORY_FIELDS_V1_TO_V2)
    if isinstance(out, dict) and out.get("tip") in HISTORY_TYPES_V2_TO_V1:
        out["tip"] = HISTORY_TYPES_V2_TO_V1[out["tip"]]
    return out


_TO_V2 = {"items": item_to_v2, "categories": lambda c: c, "history": history_to_v2}
_TO_V1 = {"items": item_to_v1, "categories": lambda c: c, "history": history_to_v1}


def records_to_v2(kind, records):
    return [_TO_V2[kind](r) for r in records]


def records_to_v1(kind, records):
    return [_TO_V1[kind](r) for r in records]


def detect_version(content):
    """Schema version of a parsed file: 1 for a bare list, the stored number for a versioned object."""
    if isinstance(content, list):
        return 1
    if isinstance(content, dict) and isinstance(content.get("schema_version"), int):
        return content["schema_version"]
    raise ValueError("unrecognised data file content")


def parse(kind, content):
    """Parsed file content (either schema) -> list of schema-2 records."""
    version = detect_version(content)
    records = content if version == 1 else content.get(LIST_KEYS[kind], [])
    if not isinstance(records, list):
        raise ValueError(f"'{LIST_KEYS[kind]}' is not a list")
    return records_to_v2(kind, records)


def serialize(kind, records, version=SCHEMA_VERSION):
    """Schema-2 records -> file content in the given schema."""
    if version == 1:
        return records_to_v1(kind, records)
    return {"schema_version": SCHEMA_VERSION, LIST_KEYS[kind]: list(records)}


def verify_conversion(kind, old_records, new_content):
    """Checks a schema-1 list against the schema-2 file written from it, field by field.

    Written independently of the conversion functions above so that a bug there is caught here.
    Raises ValueError on the first mismatch.
    """
    if not isinstance(new_content, dict) or new_content.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("schema_version missing in the new file")
    new_records = new_content.get(LIST_KEYS[kind])
    if not isinstance(new_records, list) or len(new_records) != len(old_records):
        got = len(new_records) if isinstance(new_records, list) else "?"
        raise ValueError(f"record count differs ({len(old_records)} -> {got})")
    fields = {"items": ITEM_FIELDS_V1_TO_V2, "history": HISTORY_FIELDS_V1_TO_V2}.get(kind)
    for index, (old, new) in enumerate(zip(old_records, new_records)):
        if fields is None or not isinstance(old, dict):
            if old != new:
                raise ValueError(f"record {index} differs")
            continue
        if not isinstance(new, dict):
            raise ValueError(f"record {index} is not an object")
        expected = {}
        for key, value in old.items():
            target = fields.get(key, key)
            if kind == "history" and key == "tip":
                value = HISTORY_TYPES_V1_TO_V2.get(value, value)
            expected[target] = value
        if set(new) != set(expected):
            raise ValueError(f"record {index}: fields differ")
        for key, value in expected.items():
            if new[key] != value or type(new[key]) is not type(value):
                raise ValueError(f"record {index}: field '{key}' differs")
