"""Normalize a bounded supported subset without expanding reference graphs."""

import hashlib

from auditor.spec_input import (
    MAX_DEPTH, MAX_OPERATIONS, MAX_SCHEMAS, MAX_WARNINGS,
    SpecError, pointer, resolve_pointer,
)

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
SCHEMA_SUPPORTED = {"type", "properties", "required", "enum", "items", "$ref"}
ANNOTATIONS = {"title", "description", "example", "examples", "deprecated", "externalDocs", "$comment"}


class Normalizer:
    def __init__(self, document, digest):
        self.document = document
        self.digest = digest
        self.schemas = {}
        self.warnings = {}

    def warn(self, code, path, message, keywords=()):
        identity = code + "\0" + path + "\0" + ",".join(keywords)
        warning_id = "coverage-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        self.warnings[warning_id] = {
            "id": warning_id, "code": code, "pointer": path,
            "message": message, "keywords": list(keywords),
        }
        if len(self.warnings) > MAX_WARNINGS:
            raise SpecError("resource_limit", "Coverage warnings exceed the supported limit of 200.")

    def dereference(self, value, path):
        seen = set()
        while isinstance(value, dict) and "$ref" in value:
            if path in seen or len(seen) >= MAX_DEPTH:
                raise SpecError("unsupported_reference_cycle", "Recursive non-schema references cannot be normalized.", path)
            seen.add(path)
            if set(value) - {"$ref", "description", "summary"}:
                self.warn("reference_siblings", path, "Reference sibling semantics require manual review.")
            value, path = resolve_pointer(self.document, value["$ref"])
        return value, path, seen | {path}

    def schema(self, value, path, active=()):
        if path in self.schemas:
            if path in active:
                self.warn("recursive_schema", path, "Recursive schema compatibility is not analyzed.")
            return path
        if len(active) >= MAX_DEPTH or len(self.schemas) >= MAX_SCHEMAS:
            raise SpecError("resource_limit", "Schema normalization exceeds its depth or 2000-node limit.")
        node = {"pointer": path, "ref": None, "type": None, "required": [], "enum": None, "properties": {}, "items": None}
        self.schemas[path] = node
        if isinstance(value, bool):
            self.warn("boolean_schema", path, "Boolean schema compatibility requires manual review.")
            return path
        if not isinstance(value, dict):
            raise SpecError("invalid_openapi", "Expected a schema object or a supported boolean schema.", path)
        if "$ref" in value:
            target, target_path = resolve_pointer(self.document, value["$ref"])
            node["ref"] = self.schema(target, target_path, (*active, path))
            if set(value) - {"$ref", *ANNOTATIONS}:
                self.warn("reference_siblings", path, "Reference sibling constraints require manual review.")
            # Never accidentally merge 3.0 ignored siblings or 3.1 active constraints.
            return path
        unknown = sorted(key for key in value if key not in SCHEMA_SUPPORTED | ANNOTATIONS and not key.startswith("x-"))
        if unknown:
            self.warn("schema_keywords_not_analyzed", path, "These schema constraints are outside the comparison subset.", unknown)
        node["type"] = value.get("type")
        if "type" not in value:
            self.warn("untyped_schema", path, "Schemas without an explicit type require manual compatibility review.")
        if isinstance(node["type"], list):
            self.warn("union_type", path, "Union type compatibility requires manual review.")
        node["required"] = sorted(value.get("required", []))
        enum = value.get("enum")
        if enum is not None and any(isinstance(item, (dict, list)) for item in enum):
            self.warn("complex_enum", path, "Object and array enum compatibility is not analyzed.")
        else:
            node["enum"] = enum
        for name, child in value.get("properties", {}).items():
            child_path = pointer(pointer(path, "properties"), name)
            node["properties"][name] = self.schema(child, child_path, (*active, path))
        if "items" in value:
            node["items"] = self.schema(value["items"], pointer(path, "items"), (*active, path))
        return path

    def media(self, value, path):
        result = {}
        for media_type, media in value.items():
            media_path = pointer(path, media_type)
            if "encoding" in media:
                self.warn("media_encoding", media_path, "Media encoding semantics are not analyzed.")
            result[media_type] = self.schema(media["schema"], pointer(media_path, "schema")) if "schema" in media else None
        return result

    def operation(self, route, method, value, path, item, item_path, item_origins):
        origins = {path, item_path} | item_origins
        merged = {}
        for container, container_path in ((item, item_path), (value, path)):
            for index, raw in enumerate(container.get("parameters", [])):
                parameter, parameter_path, parameter_origins = self.dereference(raw, pointer(pointer(container_path, "parameters"), index))
                origins.update(parameter_origins)
                if any(key in parameter for key in ("style", "explode", "allowReserved", "allowEmptyValue", "content")):
                    self.warn("parameter_serialization", parameter_path, "Explicit serialization/content constraints require manual review.")
                schema = self.schema(parameter["schema"], pointer(parameter_path, "schema")) if "schema" in parameter else None
                merged[(parameter["in"], parameter["name"])] = {
                    "name": parameter["name"], "in": parameter["in"],
                    "required": parameter.get("required", False), "pointer": parameter_path, "schema": schema,
                }
        body = None
        if "requestBody" in value:
            body_value, body_path, body_origins = self.dereference(value["requestBody"], pointer(path, "requestBody"))
            origins.update(body_origins)
            body = {"pointer": body_path, "required": body_value.get("required", False), "content": self.media(body_value.get("content", {}), pointer(body_path, "content"))}
        responses = {}
        for status, raw in value.get("responses", {}).items():
            if status.startswith("x-"):
                continue
            response, response_path, response_origins = self.dereference(raw, pointer(pointer(path, "responses"), status))
            origins.update(response_origins)
            if response.get("headers") or response.get("links"):
                self.warn("response_metadata", response_path, "Response headers and links require manual review.")
            responses[status] = {"pointer": response_path, "content": self.media(response.get("content", {}), pointer(response_path, "content"))}
        for key in ("security", "servers", "callbacks"):
            if key in value:
                self.warn("operation_feature_not_analyzed", pointer(path, key), "This operation feature requires manual review.")
        return {
            "path": route, "method": method.upper(), "pointer": path,
            "parameters": sorted(merged.values(), key=lambda p: (p["in"], p["name"])),
            "request_body": body, "responses": responses, "coverage_warning_ids": [],
            "_origins": origins,
        }

    def run(self):
        for key in ("security", "servers", "webhooks", "jsonSchemaDialect"):
            if key in self.document:
                self.warn("document_feature_not_analyzed", pointer("#", key), "This document feature requires manual review.")
        if self.document.get("components", {}).get("securitySchemes"):
            self.warn("authentication_not_analyzed", "#/components/securitySchemes", "Authentication compatibility is not analyzed.")
        for name, value in self.document.get("components", {}).get("schemas", {}).items():
            self.schema(value, pointer("#/components/schemas", name))
        operations = []
        for route, raw in self.document.get("paths", {}).items():
            if route.startswith("x-"):
                continue
            item, item_path, item_origins = self.dereference(raw, pointer("#/paths", route))
            if "servers" in item:
                self.warn("path_servers", pointer(item_path, "servers"), "Path-specific server changes are not analyzed.")
            for method in sorted(METHODS & item.keys()):
                if len(operations) >= MAX_OPERATIONS:
                    raise SpecError("resource_limit", "Specification exceeds the 300-operation limit.")
                operations.append(self.operation(route, method, item[method], pointer(item_path, method), item, item_path, item_origins))
        if not operations:
            self.warn("no_operations", "#/paths", "No HTTP operations were available to normalize.")
        for operation in operations:
            origins = operation.pop("_origins")
            schema_roots = [p["schema"] for p in operation["parameters"]]
            if operation["request_body"]:
                schema_roots.extend(operation["request_body"]["content"].values())
            for response in operation["responses"].values():
                schema_roots.extend(response["content"].values())
            seen, stack = set(), [p for p in schema_roots if p]
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                origins.add(current)
                schema = self.schemas[current]
                stack.extend(p for p in [schema["ref"], schema["items"], *schema["properties"].values()] if p)
            for warning_id, warning in self.warnings.items():
                wp = warning["pointer"]
                global_warning = warning["code"] in {"document_feature_not_analyzed", "authentication_not_analyzed"}
                if global_warning or any(wp == origin or wp.startswith(origin + "/") for origin in origins):
                    operation["coverage_warning_ids"].append(warning_id)
            operation["coverage_warning_ids"].sort()
        return {
            "normalizer_version": "1", "input_sha256": self.digest,
            "openapi_version": self.document["openapi"],
            "title": self.document["info"]["title"], "api_version": self.document["info"]["version"],
            "operations": sorted(operations, key=lambda op: (op["path"], op["method"])),
            "schemas": self.schemas,
            "warnings": sorted(self.warnings.values(), key=lambda w: (w["pointer"], w["code"])),
            "coverage": {"status": "partial" if self.warnings else "supported_subset", "warning_count": len(self.warnings), "operation_count": len(operations), "full_compatibility_analysis": False},
        }
