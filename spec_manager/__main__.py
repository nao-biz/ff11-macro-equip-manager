"""Thin JSON CLI adapter for SpecService; all operations live in the service."""

import argparse
import json
from pathlib import Path
import sys

from .service import SpecError, SpecService
from .catalog import LEGACY_SOURCES, loads


def main(argv=None):
    parser = argparse.ArgumentParser(description="構造化した要件・設計を検索・検証・更新します。出力はJSONです。")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="対象リポジトリ（既定: 現在のディレクトリ）")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="本文の検索、空文字で一覧")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--kind", choices=["requirement", "design", "policy"])
    search.add_argument("--limit", type=int, default=30)
    get = sub.add_parser("get", help="IDの本文と文書の版を取得")
    get.add_argument("id")
    related = sub.add_parser("related", help="IDを参照する正本・検証仕様・対応表の箇所を取得")
    related.add_argument("id")
    related.add_argument("--limit", type=int, default=50)
    sub.add_parser("overview", help="種類ごとの説明・未確定事項・件数を取得")
    sub.add_parser("validate", help="ID・必須項目・参照ファイルを検証")
    render = sub.add_parser("render", help="現在の正本から閲覧用Markdownを生成")
    render.add_argument("--out", type=Path, help="新規出力先（リポジトリ内はwork/か.spec-manager/）")
    plan = sub.add_parser("plan", help="変更要求JSONから差分付き変更案を作成（文書は未更新）")
    plan.add_argument("request", type=Path)
    plan.add_argument("--out", type=Path, required=True, help="変更案JSONの新規保存先")
    apply = sub.add_parser("apply", help="確認した変更案を再検証して適用")
    apply.add_argument("plan", type=Path)
    sub.add_parser("recover", help="未完了の更新を記録された原文へ復旧")
    args = parser.parse_args(argv)
    try:
        service = SpecService(args.root)
        if args.command == "search":
            result = service.search(args.query, args.kind, args.limit)
        elif args.command == "get":
            result = service.get(args.id)
        elif args.command == "related":
            result = service.related(args.id, args.limit)
        elif args.command == "validate":
            result = service.validate()
        elif args.command == "overview":
            result = service.overview()
        elif args.command == "render":
            result = service.render()
            if args.out:
                output = args.out.resolve()
                if output.is_relative_to(service.store.root):
                    relative = output.relative_to(service.store.root)
                    if relative.as_posix() in LEGACY_SOURCES or relative.parts[0] not in {"work", ".spec-manager"}:
                        raise SpecError("invalid_output", "閲覧用出力はwork/または.spec-manager/へ保存してください。")
                with args.out.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(result["markdown"])
                result = {"revision": result["revision"], "output": str(output)}
        elif args.command == "plan":
            request = loads(args.request.read_text(encoding="utf-8-sig"))
            if (not isinstance(request, dict) or not {"changes", "base_revision", "reason"} <= set(request)
                    or set(request) - {"changes", "base_revision", "reason", "collections"}):
                raise SpecError("invalid_input", "changes/base_revision/reasonと、必要ならcollectionsを指定してください。")
            result = service.plan(**request)
            with args.out.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        elif args.command == "apply":
            result = service.apply(loads(args.plan.read_text(encoding="utf-8-sig")))
        else:
            result = service.recover()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("valid", True) else 1
    except (SpecError, OSError, ValueError) as exc:
        error = exc.data() if isinstance(exc, SpecError) else {"code": "io_or_input_error", "message": str(exc)}
        print(json.dumps({"error": error}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
