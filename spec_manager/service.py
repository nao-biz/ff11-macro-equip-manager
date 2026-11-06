"""Transport-independent JSON operations, shared by the CLI and a future MCP adapter."""

from copy import deepcopy
import difflib
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .catalog import (CATALOG, KINDS, LEGACY_SOURCES, LINK, dumps, issues, mentioned_ids,
                      normalize, references, shape_issues, text_parts, visible_lines)
from .rendering import render
from .storage import JsonStore, SpecError, digest, revision


def find_record(data, identifier):
    matches = [(i, record) for i, record in enumerate(data["records"]) if record["id"] == identifier]
    if len(matches) != 1:
        raise SpecError("ambiguous_id" if matches else "unknown_id", "一意なIDを指定してください。", identifier)
    return matches[0]


def source(index):
    return {"path": CATALOG, "pointer": f"/records/{index}"}


def summary(record, index):
    return {key: deepcopy(record[key]) for key in ("id", "kind", "title", "status")} | {"source": source(index)}


def related_data(data, documents, identifier, limit):
    _, selected = find_record(data, identifier)
    outgoing = mentioned_ids(selected)
    linked, edges, occurrences = [], [], []
    for index, record in enumerate(data["records"]):
        if record["id"] != identifier and (record["id"] in outgoing or identifier in mentioned_ids(record)):
            linked.append(summary(record, index))
        for relation, targets in record["relations"].items():
            for target in targets:
                if identifier in (record["id"], target):
                    edges.append({"from": record["id"], "type": relation, "to": target})
        for pointer, text in text_parts(record):
            if identifier in references("".join(visible_lines(text))):
                occurrences.append({"path": CATALOG, "pointer": f"/records/{index}" + pointer, "text": text})
    for kind, collection in data["collections"].items():
        for key, text in collection.items():
            if identifier in references("".join(visible_lines(text))):
                occurrences.append({"path": CATALOG, "pointer": f"/collections/{kind}/{key}", "text": text})
    for path, text in documents.items():
        for line, content in enumerate(visible_lines(text), 1):
            if identifier in references(content):
                occurrences.append({"path": path, "line": line, "text": content.rstrip()})
    return {"id": identifier, "records": linked, "relations": edges, "occurrences": occurrences[:limit],
            "total_occurrences": len(occurrences), "truncated": len(occurrences) > limit}


class SpecService:
    def __init__(self, root: str | Path):
        self.store = JsonStore(root)

    def _read(self):
        raw, data, documents = self.store.read()
        errors = shape_issues(data)
        if errors:
            raise SpecError("invalid_catalog", "正本の構造を確認してください。", errors)
        return raw, data, documents

    def overview(self) -> dict[str, Any]:
        with self.store.locked():
            raw, data, _ = self._read()
            return {"revision": revision(raw), "schema_version": data["schema_version"],
                    "collections": deepcopy(data["collections"]),
                    "counts": {kind: sum(r["kind"] == kind for r in data["records"]) for kind in KINDS}}

    def search(self, query: str = "", kind: str | None = None, limit: int = 30) -> dict[str, Any]:
        if kind is not None and kind not in KINDS:
            raise SpecError("invalid_input", "kindはrequirement/design/policyです。")
        self._limit(limit)
        if not isinstance(query, str):
            raise SpecError("invalid_input", "queryは文字列です。")
        with self.store.locked():
            raw, data, _ = self._read()
            terms = normalize(query).split()
            found = [(i, r) for i, r in enumerate(data["records"])
                     if (kind is None or r["kind"] == kind) and all(
                         term in normalize(r["id"] + " " + " ".join(text for _, text in text_parts(r))
                                           + " " + " ".join(mentioned_ids(r))) for term in terms)]
            found.sort(key=lambda item: (normalize(item[1]["id"]) != normalize(query), item[0]))
            return {"revision": revision(raw), "records": [summary(r, i) for i, r in found[:limit]],
                    "total": len(found), "truncated": len(found) > limit}

    def get(self, identifier: str) -> dict[str, Any]:
        with self.store.locked():
            raw, data, _ = self._read()
            index, record = find_record(data, identifier)
            return {"revision": revision(raw), "record": deepcopy(record), "source": source(index),
                    "mentions": sorted(mentioned_ids(record))}

    def related(self, identifier: str, limit: int = 50) -> dict[str, Any]:
        self._limit(limit)
        with self.store.locked():
            raw, data, documents = self._read()
            return {"revision": revision(raw), **related_data(data, documents, identifier, limit)}

    def validate(self) -> dict[str, Any]:
        with self.store.locked():
            raw, data, documents = self.store.read()
            found = self._issues(data, documents)
            return {"revision": revision(raw), "valid": not found,
                    "record_count": len(data["records"]) if not shape_issues(data) else None, "issues": found}

    def render(self) -> dict[str, Any]:
        """Generate a view; no Markdown is used as an input or written by this method."""
        with self.store.locked():
            raw, data, documents = self._read()
            found = self._issues(data, documents)
            if found:
                raise SpecError("validation_failed", "検査エラーを解消してから出力してください。", found)
            current = revision(raw)
            return {"revision": current, "markdown": render(data, current, self.store.root)}

    def plan(self, changes: list[dict[str, Any]], base_revision: str, reason: str,
             collections: dict[str, Any] | None = None) -> dict[str, Any]:
        """Preview complete record replacements/additions and optional collection notes."""
        with self.store.locked():
            raw, data, documents = self._read()
            return self._plan(raw, data, documents, changes, base_revision, reason, collections)[0]

    def apply(self, plan: dict[str, Any]) -> dict[str, Any]:
        if (not isinstance(plan, dict) or plan.get("version") != 2
                or not {"changes", "base_revision", "reason", "collections"} <= plan.keys()):
            raise SpecError("invalid_plan", "現行のplanで作成した変更案を指定してください。")
        with self.store.locked():
            raw, data, documents = self._read()
            expected, updated = self._plan(raw, data, documents, plan["changes"],
                                          plan["base_revision"], plan["reason"], plan["collections"])
            if expected != plan:
                raise SpecError("invalid_plan", "変更案が変わっています。planを作り直してください。")
            if not expected["valid"]:
                raise SpecError("validation_failed", "検査エラーを解消してください。", expected["issues"])
            after = dict(raw)
            if updated != data:
                after[CATALOG] = dumps(updated).encode("utf-8")
            self.store.write(raw, after)
            return {"applied": True, "revision": revision(after), "plan_id": plan["plan_id"],
                    "reason": plan["reason"], "changed_ids": [r["id"] for r in plan["changes"]],
                    "files": [name for name in raw if raw[name] != after[name]]}

    def recover(self) -> dict[str, Any]:
        with self.store.locked():
            return self.store.recover()

    def _plan(self, raw, data, documents, changes, base_revision, reason, collections):
        if not isinstance(base_revision, str) or base_revision != revision(raw):
            raise SpecError("conflict", "正本・関連文書の版が変わっています。再取得して案を作り直してください。")
        if not isinstance(reason, str) or not reason.strip():
            raise SpecError("invalid_input", "変更理由を指定してください。")
        if not isinstance(changes, list) or (not changes and not collections):
            raise SpecError("invalid_input", "changesまたはcollectionsに変更を指定してください。")
        if collections is None:
            collections = {}
        if not isinstance(collections, dict) or set(collections) - set(KINDS):
            raise SpecError("invalid_input", "collectionsの種類を確認してください。")
        existing = {r["id"]: i for i, r in enumerate(data["records"])}
        if len(existing) != len(data["records"]):
            raise SpecError("ambiguous_id", "重複IDを解消してください。")
        updated, seen, review = deepcopy(data), set(), []
        for record in changes:
            # Validate shape before indexing or performing any mutation.
            candidate = {**data, "records": [record]}
            errors = shape_issues(candidate)
            if errors:
                raise SpecError("invalid_input", "getで取得したrecord全体を指定してください。", errors)
            identifier = record["id"]
            if identifier in seen:
                raise SpecError("duplicate_change", "同じIDへの変更が重複しています。", identifier)
            seen.add(identifier)
            if identifier in existing:
                index = existing[identifier]
                if record["kind"] != data["records"][index]["kind"]:
                    raise SpecError("invalid_input", "既存IDの種類を維持してください。")
                updated["records"][index] = deepcopy(record)
            else:
                updated["records"].append(deepcopy(record))
        updated["collections"].update(deepcopy(collections))
        found = self._issues(updated, documents)
        if not shape_issues(updated):
            review = [{"id": r["id"],
                       "before": related_data(data, documents, r["id"], 30) if r["id"] in existing else None,
                       "after": related_data(updated, documents, r["id"], 30)} for r in changes]
        diff = "".join(difflib.unified_diff(dumps(data).splitlines(True), dumps(updated).splitlines(True),
                                           fromfile=CATALOG, tofile=CATALOG))
        result = {"version": 2, "base_revision": base_revision, "reason": reason,
                  "changes": deepcopy(changes), "collections": deepcopy(collections),
                  "diff": diff, "issues": found, "review": review, "valid": not found}
        result["plan_id"] = digest(result)
        return result, updated

    def _issues(self, data, documents):
        found = issues(data, documents)
        if shape_issues(data):
            return found
        for name in LEGACY_SOURCES:
            if self.store.path(name).exists():
                found.append({"severity": "error", "code": "legacy_source", "path": name,
                              "message": "旧Markdownが残っています。正本は構造化データです。"})
        fragments = []
        for index, record in enumerate(data["records"]):
            fragments.extend(({"path": CATALOG, "pointer": f"/records/{index}" + pointer}, text)
                             for pointer, text in text_parts(record))
        for kind, collection in data["collections"].items():
            fragments.extend(({"path": CATALOG, "pointer": f"/collections/{kind}/{key}"}, text)
                             for key, text in collection.items())
        for path, text in documents.items():
            fragments.extend(({"path": path, "line": number}, line)
                             for number, line in enumerate(visible_lines(text), 1))
        ids = {r["id"] for r in data["records"]}
        for location, text in fragments:
            for match in LINK.finditer("".join(visible_lines(text))):
                href = match.group(1)
                link = urlsplit(href)
                if link.scheme == "spec":
                    valid = link.path in ids
                elif link.scheme == "spec-kind":
                    valid = link.path in KINDS
                elif link.scheme == "repo":
                    target = (self.store.root / unquote(link.path)).resolve()
                    valid = target.is_relative_to(self.store.root) and target.is_file()
                elif link.scheme in {"http", "https", "mailto"}:
                    continue
                elif location["path"] == CATALOG:
                    valid = False
                else:
                    target = (self.store.root / location["path"]).parent / unquote(link.path)
                    if not link.path:
                        target = self.store.root / location["path"]
                    target = target.resolve()
                    valid = target.is_relative_to(self.store.root) and target.is_file()
                if not valid:
                    found.append({"severity": "error", "code": "broken_link", **location,
                                  "message": f"参照先を確認してください: {href}"})
        return found

    @staticmethod
    def _limit(limit):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise SpecError("invalid_input", "limitは1〜1000の整数です。")
