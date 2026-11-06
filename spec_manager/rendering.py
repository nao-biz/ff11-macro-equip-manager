"""Generate a disposable Markdown view of the current structured catalog."""

from .catalog import KINDS, LINK, RELATIONS


def render(data, revision, root):
    def links(text):
        def replace(match):
            href = match.group(1)
            if href.startswith("spec:"):
                target = "#" + href[5:].lower()
            elif href.startswith("spec-kind:"):
                target = "#kind-" + href[10:]
            elif href.startswith("repo:"):
                path, separator, fragment = href[5:].partition("#")
                target = "<" + (root / path).as_posix() + (separator + fragment if separator else "") + ">"
            else:
                return match.group(0)
            return match.group(0).replace("(" + href + ")", "(" + target + ")")
        return LINK.sub(replace, text)

    parts = ["# 要件・設計の閲覧用出力", f"生成元の版: `{revision}`",
             "このファイルは生成物です。最新の参照・更新はspec_managerを使います。"]
    for kind in KINDS:
        collection = data["collections"][kind]
        parts += [f'<a id="kind-{kind}"></a>', "# " + collection["title"], links(collection["introduction"])]
        for record in data["records"]:
            if record["kind"] != kind:
                continue
            parts += [f'<a id="{record["id"].lower()}"></a>', f'## {record["id"]} — {record["title"]}']
            if record["status"]:
                state = record["status"]
                parts.append(f'状態: **{state["summary"]}**{links(state["note"])}')
            for relation, targets in record["relations"].items():
                parts.append(RELATIONS[relation] + ": " + "、".join(f"[{x}](#{x.lower()})" for x in targets) + "。")
            for block in record["content"]:
                text = links(block["text"])
                parts.append(text if block["type"] == "markdown" else f'- {block["label"]}: {text}')
        parts.append(links(collection["afterword"]))
    return "\n\n".join(x for x in parts if x) + "\n"
