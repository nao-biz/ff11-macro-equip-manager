"""Book-title copies, validated and executed within the combined transaction."""
from pathlib import Path
import hashlib
import re

from .codecs import book_titles, text
from .save_plan import BookFile, BookNameChange, BookSavePlan
from .edit_values import integer, text_value


def patch_titles(raw, page, changes):
    if not integer(page, 0, 1):raise ValueError('ブック名ファイルの番号が不正です。')
    titles = book_titles(raw, bool(page))
    out = bytearray(raw)
    seen = set()
    for change in changes:
        if type(change) is not BookNameChange or change.number not in titles or change.number in seen:
            raise ValueError('ブック名の変更対象が不正です。')
        seen.add(change.number)
        if titles[change.number].display != change.before or len(change.replacement) != 16:
            raise ValueError('ブック名の原本またはコピーする長さが不正です。')
        if text(change.replacement).display != change.after:
            raise ValueError('ブック名の表示とバイト列が一致しません。')
        offset = 24 + (change.number - 1) % 20 * 16
        out[offset:offset+16] = change.replacement
    out[8:24] = hashlib.md5(out[24:]).digest()
    return bytes(out)


def prepare_book_save(saved, working, folder, *, source_index):
    before = next(c for c in saved.characters if c.folder_id == folder).books
    after = next(c for c in working.characters if c.folder_id == folder).books
    if before.keys() != after.keys():raise ValueError('ブック名の保存対象が変わりました。')
    sources = source_index
    records = sources.records()
    parents = {p.parent for p in records if p.parent.name == folder and p.parent.parent.name.upper() == 'USER'}
    if len(parents) != 1 or not re.fullmatch('[0-9a-fA-F]+', folder):raise ValueError('ブック名の保存先を特定できません。')
    parent = parents.pop()
    grouped = {}
    for number, title in after.items():
        if text_value(before[number]) == text_value(title):continue
        raw = bytes.fromhex(title.raw_hex)
        if text_value(text(raw)) != text_value(title):raise ValueError('コピー元のブック名の原本が一致しません。')
        grouped.setdefault((number-1)//20, []).append(BookNameChange(number, before[number].display, title.display, raw))
    files = []
    dependencies = []
    for page, changes in sorted(grouped.items()):
        path = parent / ('mcr_2.ttl' if page else 'mcr.ttl')
        if path not in records:raise ValueError('ブック名ファイルを読み取れていません。')
        expected = sources.verify(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:raise ValueError('ブック名が変更されました。再読み込みしてください。')
        files.append(BookFile(str(path), page, raw, patch_titles(raw, page, changes), tuple(changes)))
        dependencies.append((str(path), expected))
    return BookSavePlan(folder, tuple(files), tuple(dependencies))


def validate_book_plan(plan):
    if type(plan) is not BookSavePlan or not plan.files or not re.fullmatch('[0-9a-fA-F]+', plan.character):
        raise ValueError('ブック名の保存計画が不正です。')
    parent = Path(plan.files[0].target).resolve().parent
    if parent.name != plan.character or parent.parent.name.upper() != 'USER':
        raise ValueError('ブック名の保存先が不正です。')
    expected = []
    for file in plan.files:
        path = parent / ('mcr_2.ttl' if file.page else 'mcr.ttl')
        if type(file) is not BookFile or Path(file.target).resolve() != path or not file.changes:
            raise ValueError('ブック名の保存ファイルが不正です。')
        if patch_titles(file.original, file.page, file.changes) != file.replacement:
            raise ValueError('ブック名の保存内容が変更案と一致しません。')
        expected.append((str(path), hashlib.sha256(file.original).hexdigest()))
    if tuple(expected) != plan.dependencies or len(set(expected)) != len(expected):
        raise ValueError('ブック名の依存資料が不正です。')
    return parent.parent.parent
