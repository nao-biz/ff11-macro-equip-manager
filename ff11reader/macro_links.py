"""Read-only domain queries for literal macro -> equipment-set references."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SetReference:
    book: int
    palette: int
    bank: str
    key: int
    macro_title: str
    line: int
    command: str
    number: int
    target_state: str

    @property
    def address(self):
        return self.book, self.palette, self.bank, self.key


@dataclass(frozen=True)
class MacroSetLinks:
    references: tuple[SetReference, ...]
    unreferenced: tuple[int, ...]

    @property
    def empty_references(self):
        return tuple(r for r in self.references if r.target_state == 'empty')

    def for_macro(self, macro):
        address = macro.book, macro.palette, macro.bank, macro.key
        return tuple(r for r in self.references if r.address == address)

    def for_set(self, number):
        return tuple(r for r in self.references if r.number == number)


def is_empty(equipset):
    # Remove-only sets have an effect. Unknown/truncated data is not empty.
    return len(equipset.slots) == 16 and all(s.action == 'keep' for s in equipset.slots)


def reference_match(line):
    # Keep spans in the original display text, including an auto-translate command.
    match=re.match(r'\s*(?:/(equipset|lockstyleset)|【/(equipset|lockstyleset)】)\s+([0-9]{1,3})(?=\s|<|$)',line,re.I)
    return match if match and 1<=int(match[3])<=200 else None


def parse_reference(line):
    match=reference_match(line)
    return ((match[1] or match[2]).lower(),int(match[3])) if match else None


def retarget_reference(line,source,target):
    from .text_editing import remap_text
    match=reference_match(line.display)
    if not match or int(match[3])!=source:return line
    start,end=match.span(3)
    number=str(target).zfill(end-start)
    return remap_text(line,line.display[:start]+number+line.display[end:])


def analyze_macro_sets(character):
    sets = {e.number: e for e in character.equipsets}
    refs = []
    for macro in character.macros:
        for line_number, line in enumerate(macro.lines, 1):
            parsed = parse_reference(line.display)
            if parsed is None:
                continue
            command, number = parsed
            target = sets.get(number)
            state = 'unavailable' if target is None else ('empty' if is_empty(target) else 'present')
            refs.append(SetReference(macro.book, macro.palette, macro.bank, macro.key,
                                    macro.title.display, line_number, command, number, state))
    used = {r.number for r in refs}
    return MacroSetLinks(tuple(refs), tuple(sorted(n for n, e in sets.items() if n not in used and not is_empty(e))))
