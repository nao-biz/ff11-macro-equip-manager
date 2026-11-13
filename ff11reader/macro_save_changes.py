"""Pure selection and encoding of macro changes before file-plan assembly."""
from .codecs import text as decode_text
from .edit_values import key as macro_key, text_value, validate_structure
from .macro_save_encoding import patch_line
from .macro_text import patch_text
from .save_plan import DeferredChange, LineChange
from .text_editing import remap_text


def semantic_changed(before, after):
    return any(text_value(a) != text_value(b) for a, b in zip(
        (before.title, *before.lines), (after.title, *after.lines)))


def needs_dictionary(original, edited, scope):
    if scope == 'storage-fix':
        return True
    old = {macro_key(m): m for m in original.macros}
    for macro in edited.macros:
        before = old[macro_key(macro)]
        if not semantic_changed(before, macro):
            continue
        relocated = bool(macro.raw_hex) and macro.raw_hex != before.raw_hex
        for a, b in zip(before.lines, macro.lines):
            if text_value(a) != text_value(b) or relocated:
                if a.tokens or b.tokens or b'\xfd' in bytes.fromhex(a.raw_hex) or b'\xfd' in bytes.fromhex(b.raw_hex):
                    return True
    return False


def field_bytes(base, line):
    return base[370:380] if line == 0 else base[4+(line-1)*61:4+line*61]


def field_changed(before, after, base, line, resolver):
    if text_value(before) != text_value(after):
        return True
    if not base:
        return False
    decoded = decode_text(field_bytes(base, line), None if line == 0 else resolver)
    return decoded.display != after.display or tuple(decoded.tokens or ()) != tuple(after.tokens or ())


def encode_change(key, line, before, after, base, scope, resolver):
    raw = field_bytes(base, line) if base else bytes.fromhex(before.raw_hex)
    displayed = decode_text(raw, None if line == 0 else resolver).display if base else before.display
    provenance = bytes.fromhex(after.raw_hex) if scope == 'all' and line else b''
    if scope == 'storage-fix':
        replacement = patch_line(raw, before.display, after.display, resolver)
    else:
        replacement = patch_text(raw, displayed, after.display, resolver,
                                 title=line == 0, provenance=provenance, tokens=after.tokens)
    return LineChange(key, line, before.display, after.display, raw, replacement,
                      provenance, after.tokens, tuple(before.tokens or ()))


def macro_changes(before, macro, scope, resolver, refs):
    key = macro_key(macro)
    address = f'ブック {macro.book:02} / パレット {macro.palette} / {macro.bank.upper()} {macro.key}'
    validate_structure(macro, 'macros')
    relocated = scope == 'all' and bool(macro.raw_hex) and macro.raw_hex != before.raw_hex
    base = bytes.fromhex(macro.raw_hex) if relocated else b''
    if relocated and len(base) != 380:
        raise ValueError('マクロ原本は380バイト必要です。')
    if not semantic_changed(before, macro):
        return (), (), b''
    deferred = []
    if scope == 'storage-fix' and before.title.display != macro.title.display:
        deferred.append(DeferredChange(address+' / 名前', '名前の変更は「ゲームへ書き戻す…」から保存できます。'))
    fields = list(enumerate(zip(before.lines, macro.lines), 1))
    if scope == 'all':
        fields.insert(0, (0, (before.title, macro.title)))
    changes = []
    for line, (a, b) in fields:
        if not field_changed(a, b, base, line, resolver):
            continue
        if scope == 'storage-fix':
            ref = refs.get((key, line))
            if ref is None or ref.replacement is None or text_value(remap_text(a, ref.replacement)) != text_value(b):
                deferred.append(DeferredChange(address+f' / {line}行目', '手編集した行は「ゲームへ書き戻す…」から保存できます。'))
                continue
        try:
            changes.append(encode_change(key, line, a, b, base, scope, resolver))
        except ValueError as exc:
            label = '名前' if line == 0 else f'{line}行目'
            raise ValueError(f'{address} / {label}: {exc}') from exc
    return tuple(changes), tuple(deferred), base


def collect_changes(original, edited, scope, resolver, refs):
    old = {macro_key(m): m for m in original.macros}
    grouped, deferred, record_bases = {}, [], {}
    for macro in edited.macros:
        key = macro_key(macro)
        changes, held, base = macro_changes(old[key], macro, scope, resolver, refs)
        deferred.extend(held)
        if base:
            record_bases[key] = base
        if changes:
            page = (macro.book-1)*10+macro.palette-1
            grouped.setdefault(page, []).extend(changes)
    return grouped, deferred, record_bases
