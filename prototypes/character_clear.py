"""Run the clear confirmation against synthetic data without game files."""
import tkinter as tk
from ff11reader.edit_application import Editor
from ff11reader.ui import ReaderWindow
from prototypes.book_copy import snapshot


def main():
    app = tk.Tk()
    source = snapshot()
    view = ReaderWindow(app, source, editor=Editor(source, 'work/clear-mock/draft.json'))
    app.after(200, view.clear_character_data)
    app.mainloop()


if __name__ == '__main__':main()
