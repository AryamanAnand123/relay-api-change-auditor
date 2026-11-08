"""Strict JSON and offline OpenAPI validation with explicit resource limits."""

import copy
import hashlib
import json
import math
import re
from decimal import Decimal
from urllib.parse import quote, unquote

FILE_LIMIT = 2 * 1024 * 1024
BODY_LIMIT = 2 * FILE_LIMIT + 64 * 1024
MAX_DEPTH = 64
MAX_NODES = 20_000
MAX_REFS = 1_000
MAX_SCHEMAS = 2_000
MAX_OPERATIONS = 300
MAX_WARNINGS = 200
WORKER_TIMEOUT = 10
OUTPUT_LIMIT = 8 * 1024 * 1024


class SpecError(Exception):
    def __init__(self, code, message, pointer=None, side=None):
        super().__init__(message)
        self.detail = {"code": code, "message": message}
        if pointer is not None:
            self.detail["pointer"] = pointer[:512]
        if side is not None:
            self.detail["side"] = side


def pointer(parent, token):
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return parent + "/" + quote(escaped, safe="~")


def resolve_pointer(document, ref):
    if not isinstance(ref, str) or not ref.startswith("#"):
        raise SpecError("unsupported_reference", "Only same-document JSON Pointer references are supported.")
    if re.search(r"%(?![0-9a-fA-F]{2})", ref):
        raise SpecError("invalid_reference", "Reference contains an invalid percent escape.")
    try:
        fragment = unquote(ref[1:], encoding="utf-8", errors="strict")
    except UnicodeError:
        raise SpecError("invalid_reference", "Reference is not valid UTF-8.") from None
    current, canonical = document, "#"
    if not fragment:
        return current, canonical
    if not fragment.startswith("/"):
        raise SpecError("unsupported_reference", "Named anchors are outside the supported JSON Pointer reference policy.")
    for part in fragment[1:].split("/"):
        if re.search(r"~(?![01])", part):
            raise SpecError("invalid_reference", "Reference contains an invalid JSON Pointer escape.")
        token = part.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(current, dict):
                current = current[token]
            elif isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
                current = current[int(token)]
            else:
                raise KeyError(token)
        except (KeyError, IndexError, ValueError):
            raise SpecError("unresolved_reference", "Reference target does not exist.") from None
        canonical = pointer(canonical, token)
    return current, canonical


def _pairs(items):
    result = {}
    for key, value in items:
        try:
            key.encode("utf-8")
        except UnicodeError:
            raise SpecError("invalid_encoding", "JSON strings must contain valid Unicode scalar values.") from None
        if key in result:
            raise SpecError("duplicate_key", "Duplicate JSON object keys are not allowed.")
        result[key] = value
    return result


def _constant(_):
    raise SpecError("invalid_number", "JSON numbers must be finite.")


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        _constant(value)
    if Decimal(value) != Decimal(str(number)):
        raise SpecError("unsupported_numeric_precision", "A JSON decimal cannot be represented without losing significant digits in this analyzer.")
    return number


def parse_document(raw):
    if len(raw) > FILE_LIMIT:
        raise SpecError("file_too_large", "Each specification must be at most 2 MiB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise SpecError("invalid_encoding", "Specifications must be UTF-8 JSON without a byte-order mark.") from None
    # Bound nesting before invoking the recursive standard-library decoder.
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise SpecError("resource_limit", "JSON nesting exceeds the supported limit of 64.")
        elif char in "]}":
            depth -= 1
    try:
        document = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except (ValueError, RecursionError):
        raise SpecError("invalid_json", "File is not valid JSON within the supported numeric limits.") from None
    if not isinstance(document, dict):
        raise SpecError("invalid_root", "The OpenAPI document root must be an object.")
    count, stack = 0, [document]
    while stack:
        item = stack.pop()
        count += 1
        if count > MAX_NODES:
            raise SpecError("resource_limit", "Specification exceeds the 20000-node input limit.")
        if isinstance(item, dict):
            count += len(item)  # Keys consume the budget as well as values.
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeError:
                raise SpecError("invalid_encoding", "JSON strings must contain valid Unicode scalar values.") from None
    version = document.get("openapi")
    if not isinstance(version, str) or not re.fullmatch(r"3\.(?:0|1)\.[0-9]+", version):
        raise SpecError("unsupported_version", "Only OpenAPI 3.0.x and 3.1.x JSON specifications are accepted.", "#/openapi")
    return document, hashlib.sha256(raw).hexdigest()


SCHEMA_MAPS = {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
SCHEMA_ARRAYS = {"allOf", "anyOf", "oneOf", "prefixItems"}
SCHEMA_CHILDREN = {"items", "additionalProperties", "unevaluatedProperties", "unevaluatedItems", "contains", "not", "if", "then", "else", "propertyNames", "contentSchema"}
OBJECT_MAPS = {"paths", "webhooks", "responses", "content", "examples", "parameters", "requestBodies", "headers", "callbacks", "links", "securitySchemes"}
KNOWN_DIALECTS = {"https://spec.openapis.org/oas/3.1/dialect/base", "https://json-schema.org/draft/2020-12/schema"}


def structural_nodes(document):
    """Visit specification/schema objects, excluding literal examples and extensions.

    Map entries are names, not keywords: a property called `example` still has a
    real schema, while `$ref` inside an example value is just user data.
    """
    stack = [(document, "#", "object")]
    while stack:
        value, path, mode = stack.pop()
        if isinstance(value, list):
            stack.extend((item, pointer(path, index), mode) for index, item in enumerate(value))
            continue
        if not isinstance(value, dict):
            continue
        if mode in {"map", "schema_map"}:
            child_mode = "schema" if mode == "schema_map" else "object"
            stack.extend((item, pointer(path, key), child_mode) for key, item in value.items())
            continue
        yield value, path, mode
        for key, item in value.items():
            if key.startswith("x-"):
                continue
            if mode == "schema":
                if key in SCHEMA_MAPS:
                    child_mode = "schema_map"
                elif key in SCHEMA_ARRAYS or key in SCHEMA_CHILDREN:
                    child_mode = "schema"
                else:
                    continue
            elif key in {"example", "value", "default", "enum"}:
                continue
            elif key == "schema":
                child_mode = "schema"
            elif key == "schemas" and path == "#/components":
                child_mode = "schema_map"
            elif key in OBJECT_MAPS and isinstance(item, dict):
                child_mode = "map"
            else:
                child_mode = "object"
            stack.append((item, pointer(path, key), child_mode))


def check_references(document):
    count = 0
    for node, path, mode in structural_nodes(document):
        if "$ref" in node:
            count += 1
            if count > MAX_REFS:
                raise SpecError("resource_limit", "Specification exceeds the 1000-reference limit.")
            try:
                target, _ = resolve_pointer(document, node["$ref"])
                if not isinstance(target, dict) and not (mode == "schema" and isinstance(target, bool)):
                    raise SpecError("invalid_reference_target", "Reference target must be an OpenAPI object or schema.")
            except SpecError as error:
                error.detail["pointer"] = pointer(path, "$ref")[:512]
                raise
        if mode == "schema":
            if any(key in node for key in ("$id", "$anchor", "$dynamicAnchor", "$dynamicRef", "$recursiveRef")):
                raise SpecError("unsupported_reference_scope", "Schema IDs, anchors, and dynamic references are outside the supported reference policy.", path)
            if "$schema" in node:
                if not isinstance(node["$schema"], str):
                    raise SpecError("invalid_openapi", "Schema dialect must be a string.", path)
                if node["$schema"] not in KNOWN_DIALECTS:
                    raise SpecError("unsupported_dialect", "Custom schema dialects are not supported.", path)
    dialect = document.get("jsonSchemaDialect")
    if dialect is not None:
        if not isinstance(dialect, str):
            raise SpecError("invalid_openapi", "OpenAPI schema dialect must be a string.", "#/jsonSchemaDialect")
        if dialect not in KNOWN_DIALECTS:
            raise SpecError("unsupported_dialect", "Custom OpenAPI schema dialects are not supported.", "#/jsonSchemaDialect")


def validate_structure(document):
    from jsonschema_path import SchemaPath
    from openapi_spec_validator import OpenAPIV30SpecValidator, OpenAPIV31SpecValidator

    # The OAS Components key pattern is normative in both supported families.
    # The 3.0 validator currently accepts some keys that the 3.1 validator rejects.
    components = document.get("components")
    if isinstance(components, dict):
        for field in ("schemas", "responses", "parameters", "examples", "requestBodies", "headers", "securitySchemes", "links", "callbacks", "pathItems"):
            entries = components.get(field)
            if isinstance(entries, dict) and any(not re.fullmatch(r"[a-zA-Z0-9._-]+", name) for name in entries):
                raise SpecError("invalid_openapi", "Component names must use only letters, digits, dot, underscore, or hyphen.", pointer("#/components", field))

    # The reference library treats an encoded leading slash as an anchor. Supply
    # equivalent canonical pointers on a bounded copy, never mutate source data.
    validation_document = copy.deepcopy(document)
    for node, _, _ in structural_nodes(validation_document):
        if "$ref" in node:
            _, node["$ref"] = resolve_pointer(validation_document, node["$ref"])
    # Passing an empty dict is important: None would enable default URL/file handlers.
    schema_path = SchemaPath.from_dict(validation_document, handlers={}, resolved_cache_maxsize=256)
    validator_type = OpenAPIV30SpecValidator if document["openapi"].startswith("3.0.") else OpenAPIV31SpecValidator
    try:
        error = next(validator_type(schema_path).iter_errors(), None)
    except RecursionError:
        raise SpecError("resource_limit", "Validator recursion exceeded the supported workload.") from None
    if error is not None:
        path = "#"
        for part in error.path:
            path = pointer(path, part)
        # Do not echo validator messages, which may embed large/private input values.
        raise SpecError("invalid_openapi", "Document does not satisfy the OpenAPI structure or schema rules.", path)
