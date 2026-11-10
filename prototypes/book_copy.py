"""Synthetic book-copy UI; all edits stay in memory."""
from dataclasses import replace
import tkinter as tk
from ff11reader.codecs import book_titles, macros, equipsets
from ff11reader.domain import Character, Snapshot
from ff11reader.edit_application import Editor
from ff11reader.ui import ReaderWindow
from ff11reader.book_copy_ui import open_book_copy
from ff11reader.references import assess_equipment
import hashlib


def raw_file(size):
    raw = bytearray(size)
    raw[8:24] = hashlib.md5(raw[24:]).digest()
    return bytes(raw)


def snapshot():
    chars = []
    for folder, name in (('abc', 'コピー元'), ('def', 'コピー先')):
        character = Character(folder, name, books=book_titles(raw_file(344)),
                              macros=[m for page in range(10) for m in macros(raw_file(7624), page)],
                              equipsets=equipsets(raw_file(1624), 0))
        if folder == 'abc':
            title = bytearray(raw_file(344));title[24:28] = b'Test'
            title[8:24] = hashlib.md5(title[24:]).digest()
            character.books = book_titles(bytes(title))
            first = character.macros[0]
            line = replace(first.lines[0], display='/equipset 1', tokens=())
            character.macros[0] = replace(first, lines=(line, *first.lines[1:]))
        character.equipsets = assess_equipment(character)
        chars.append(character)
    return Snapshot('book-copy-mock', '', chars, {}, [], [], 'book-copy-mock')


def main():
    app = tk.Tk()
    source = snapshot()
    view = ReaderWindow(app, source, editor=Editor(source, 'work/book-copy-mock/draft.json'))
    app.after(200, lambda:open_book_copy(view))
    app.mainloop()


if __name__ == '__main__':main()
