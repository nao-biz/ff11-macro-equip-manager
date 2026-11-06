"""Structured specification schema and pure validation/query helpers."""

import json
import re
import unicodedata

CATALOG = "specs/catalog.json"
KINDS = ("requirement", "design", "policy")
LEGACY_SOURCES = ("requirements.md", "docs/design-constraints.md", "docs/design-policy.md")
SOURCES = {CATALOG: "catalog", "tests/specs/example-tests.md": "verification",
           "tests/specs/property-tests.md": "verification",
           "docs/requirements-traceability.md": "traceability"}
ID = r"(?:[A-Z]{2,}-\d{3}|DP-\d{2}|D-\d{2})"
TOKEN = re.compile(rf"(?<![A-Za-z0-9_-])({ID})(?![A-Za-z0-9_-])"
                   rf"(?:[〜～–](?:([A-Z]+)-)?(\d{{2,3}})(?!\d))?")
LINK = re.compile(r"\[[^\]\n]*\]\(([^\s)]+)\)")
ROLES = ("condition", "outcome", "example", "detail", "markdown")
RELATIONS = {"basis": "対応", "related": "関連", "adopts": "採用設計", "replaced_by": "代替"}
RECORD_KEYS = {"id", "kind", "title", "status", "relations", "content"}


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


def visible_lines(text):
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            yield "\n" if line.endswith("\n") else ""
        elif fence:
            yield "\n" if line.endswith("\n") else ""
        else:
            yield line


def references(text):
    found = set()
    for match in TOKEN.finditer(text):
        first, end_prefix, end = match.groups()
        found.add(first)
        if end:
            prefix, number = first.rsplit("-", 1)
            if end_prefix and end_prefix != prefix:
                found.add(f"{end_prefix}-{end}")
            elif int(number) <= int(end):
                found.update(f"{prefix}-{value:0{len(number)}d}"
                             for value in range(int(number), int(end) + 1))
            else:
                found.add(f"{prefix}-{end}")
    return sorted(found)


def loads(text):
    """Reject duplicate JSON keys rather than silently accepting the last value."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"JSONキーが重複しています: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def issue(code, message, pointer="", **location):
    return {"severity": "error", "code": code, "path": CATALOG,
            "pointer": pointer, "message": message, **location}


def shape_issues(data):
    if not isinstance(data, dict) or set(data) != {"schema_version", "collections", "records"}:
        return [issue("schema", "schema_version/collections/recordsが必要です。")]
    if type(data["schema_version"]) is not int or data["schema_version"] != 2:
        return [issue("schema_version", "対応するschema_versionは2です。")]
    if not isinstance(data["collections"], dict) or set(data["collections"]) != set(KINDS):
        return [issue("schema", "requirement/design/policyの文書情報が必要です。", "/collections")]
    result = []
    for kind, collection in data["collections"].items():
        if (not isinstance(collection, dict) or set(collection) != {"title", "introduction", "afterword"}
                or not all(isinstance(x, str) for x in collection.values()) or not collection["title"].strip()):
            result.append(issue("schema", "文書情報にはtitle/introduction/afterwordの文字列を指定します。", f"/collections/{kind}"))
    if not isinstance(data["records"], list) or not data["records"]:
        return result + [issue("schema", "recordsは空でない配列です。", "/records")]
    for index, record in enumerate(data["records"]):
        pointer = f"/records/{index}"
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            result.append(issue("schema", "recordの項目はid/kind/title/status/relations/contentです。", pointer))
            continue
        if not all(isinstance(record[key], str) and record[key].strip() for key in ("id", "kind", "title")):
            result.append(issue("schema", "id/kind/titleには空でない文字列を指定します。", pointer))
        if not isinstance(record["kind"], str) or record["kind"] not in KINDS:
            result.append(issue("schema", "kindはrequirement/design/policyです。", pointer + "/kind"))
        state = record["status"]
        if state is not None and (not isinstance(state, dict) or set(state) != {"summary", "note"}
                                  or not all(isinstance(x, str) for x in state.values()) or not state["summary"].strip()):
            result.append(issue("schema", "statusはnull、またはsummary/noteです。", pointer + "/status"))
        relations = record["relations"]
        if (not isinstance(relations, dict) or set(relations) - set(RELATIONS)
                or not all(isinstance(ids, list) and all(isinstance(x, str) for x in ids)
                           for ids in relations.values())):
            result.append(issue("schema", "relationsにはbasis/related/adopts/replaced_byごとのID配列を指定します。", pointer + "/relations"))
        content = record["content"]
        if not isinstance(content, list) or not content:
            result.append(issue("schema", "contentは空でない配列です。", pointer + "/content"))
            continue
        for number, block in enumerate(content):
            if (not isinstance(block, dict) or block.get("type") not in ROLES
                    or set(block) != ({"type", "text"} if block.get("type") == "markdown" else {"type", "label", "text"})
                    or not all(isinstance(x, str) and x.strip() for x in block.values())):
                result.append(issue("schema", "本文ブロックのtype/label/textを確認してください。", f"{pointer}/content/{number}"))
    return result


def text_parts(record):
    yield "/title", record["title"]
    if record["status"]:
        yield "/status/summary", record["status"]["summary"]
        yield "/status/note", record["status"]["note"]
    for index, block in enumerate(record["content"]):
        if "label" in block:
            yield f"/content/{index}/label", block["label"]
        yield f"/content/{index}/text", block["text"]


def mentioned_ids(record):
    result = {target for targets in record["relations"].values() for target in targets}
    for _, text in text_parts(record):
        result.update(references("".join(visible_lines(text))))
    return result - {record["id"]}


def issues(data, documents):
    result = shape_issues(data)
    if result:
        return result
    ids = {record["id"] for record in data["records"]}
    kinds = {record["id"]: record["kind"] for record in data["records"]}
    seen = set()
    for index, record in enumerate(data["records"]):
        pointer = f"/records/{index}"
        identifier = record["id"]
        if not re.fullmatch(ID, identifier):
            result.append(issue("invalid_id", "IDの形式を確認してください。", pointer, id=identifier))
        if identifier in seen:
            result.append(issue("duplicate_id", "IDが重複しています。", pointer, id=identifier))
        seen.add(identifier)
        expected = "policy" if identifier.startswith("DP-") else "design" if identifier.startswith("D-") else "requirement"
        if record["kind"] != expected:
            result.append(issue("wrong_kind", "IDと種類が一致しません。", pointer, id=identifier))
        if record["kind"] == "requirement":
            for role in ("condition", "outcome"):
                if not any(block["type"] == role for block in record["content"]):
                    result.append(issue("missing_field", f"{role}がありません。", pointer, id=identifier))
        for relation, targets in record["relations"].items():
            if len(targets) != len(set(targets)):
                result.append(issue("duplicate_relation", "関係の対象IDが重複しています。", pointer + "/relations/" + relation))
            if identifier in targets:
                result.append(issue("self_relation", "自分自身への関係を確認してください。", pointer))
            for target in targets:
                if target not in kinds:
                    continue
                valid_kind = (
                    (record["kind"] == "requirement" and kinds[target] == "design") if relation == "adopts" else
                    (record["kind"] == "design" and kinds[target] in {"requirement", "design"}) if relation == "basis" else
                    record["kind"] == kinds[target] if relation == "replaced_by" else True)
                if not valid_kind:
                    result.append(issue("relation_kind", "関係の種類と参照元・参照先の種類が一致しません。", pointer, id=target))
        for target in mentioned_ids(record) - ids:
            result.append(issue("unknown_id", "参照先のIDがありません。", pointer, id=target))
    for kind, collection in data["collections"].items():
        for field, text in collection.items():
            for target in set(references("".join(visible_lines(text)))) - ids:
                result.append(issue("unknown_id", "参照先のIDがありません。", f"/collections/{kind}/{field}", id=target))
    for path, text in documents.items():
        for line, content in enumerate(visible_lines(text), 1):
            for target in set(references(content)) - ids:
                result.append(issue("unknown_id", "参照先のIDがありません。", path=path, line=line, id=target))
    return result
