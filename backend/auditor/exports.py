"""Deterministic exports; untrusted specification text remains encoded data."""

import json

MAX_EXPORT_BYTES = 16 * 1024 * 1024
EXPORT_VERSION = "1"


class ExportTooLarge(Exception):
    pass


def json_export(record):
    result = {"export_schema_version": EXPORT_VERSION, **record}
    output = json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(output) > MAX_EXPORT_BYTES:
        raise ExportTooLarge("Export exceeds its 16 MiB limit.")
    return output


def markdown_export(record):
    parts, size = [], 0

    def append(text):
        nonlocal size
        size += len(text.encode("utf-8"))
        if size > MAX_EXPORT_BYTES:
            raise ExportTooLarge("Export exceeds its 16 MiB limit; use JSON for this report.")
        parts.append(text)

    def block(value):
        append("```json\n")
        for chunk in json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).iterencode(value):
            # Decode as JSON to recover original values; these escapes prevent
            # HTML/fence injection while keeping the exported evidence lossless.
            append(chunk.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("`", "\\u0060"))
        append("\n```\n\n")

    report = record["result"]["comparison"]
    append("# API Change Impact Auditor report\n\n")
    append("Deterministic declared-contract findings. This is not a full compatibility certification.\n\n")
    append("## Saved comparison\n\n")
    block({"export_schema_version": EXPORT_VERSION, **{key: value for key, value in record.items() if key != "result"}})
    append("## Policy assumptions\n\n")
    block(report["policy_assumptions"])
    append("## Summary\n\n")
    block({"verdict": report["verdict"], "counts": report["summary"]})
    append("## Coverage\n\n")
    block(report["coverage"])
    append("## Findings\n\n")
    if not report["findings"]:
        append("No findings in the implemented subset; review the coverage limitations above.\n\n")
    for index, finding in enumerate(report["findings"], 1):
        append("### Finding " + str(index) + "\n\n")
        block(finding)
    return "".join(parts).encode("utf-8")
