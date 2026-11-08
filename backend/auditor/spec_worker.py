"""Disposable offline subprocess: validate and normalize a pair, then exit."""

import json
import socket
import sys

from auditor.normalization import Normalizer
from auditor.comparison import Comparator
from auditor.spec_input import OUTPUT_LIMIT, SpecError, check_references, parse_document, validate_structure


def deny_network(*args, **kwargs):
    raise OSError("Network access is disabled in the specification worker.")


def analyze_pair(payload, compare=False):
    result = {}
    documents = {}
    for side in ("old", "new"):
        try:
            document, digest = parse_document(payload[side].encode("utf-8"))
            documents[side] = document
            check_references(document)
            validate_structure(document)
            result[side] = Normalizer(document, digest).run()
        except SpecError as error:
            error.detail["side"] = side
            raise
    if compare:
        report = Comparator(result["old"], result["new"], documents).run()
        return {"status": "compared", "comparison_performed": True, "comparison": report, **result}
    return {"status": "validated", "comparison_performed": False, **result}


def main():
    # Defense in depth within this disposable process, in addition to empty
    # reference handlers and the same-document pointer policy. No global API patch.
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    try:
        payload = json.loads(sys.stdin.buffer.read())
        result = {"ok": True, "result": analyze_pair(payload, compare=payload.get("_compare", False))}
    except SpecError as error:
        result = {"ok": False, "error": error.detail}
    except RecursionError:
        result = {"ok": False, "error": {"code": "resource_limit", "message": "Specification recursion exceeds the supported workload."}}
    except Exception:
        # No tracebacks or validator messages containing uploaded values.
        result = {"ok": False, "error": {"code": "validation_failed", "message": "Specification validation could not complete; simplify the document or review unsupported references."}}
    output = json.dumps(result, ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(output) > OUTPUT_LIMIT:
        output = json.dumps({"ok": False, "error": {"code": "resource_limit", "message": "Normalized output exceeds the supported size."}}).encode()
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    main()
