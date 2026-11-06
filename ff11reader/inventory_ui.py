"""Compact inventory rows using the workspace's selection and scrolling."""
from .theme import ACCENT, BORDER, FG, MUTED, PANEL
import tkinter as tk


def item_row(view, ordinal, row, path):
    frame = tk.Canvas(view.cards, height=44, width=400, bg=PANEL,
                      highlightbackground=BORDER, highlightthickness=1, borderwidth=0)
    frame.normal_border = BORDER
    frame.grid(row=ordinal, column=0, sticky='ew', padx=5, pady=1)
    view.cards.columnconfigure(0, weight=1)
    photo = view.icon(row.item_id)
    if photo:
        frame.item_photo = photo.subsample(2, 2)
        frame.create_image(24, 22, image=frame.item_photo)
    else:
        frame.create_text(24, 22, text='—', fill=MUTED)
    frame.create_text(50, 22, text=f'{row.index:02}', anchor='w', fill=MUTED, font=('MS Gothic',9))
    title = frame.create_text(82, 22, text=view.item_name(row.item_id), anchor='w',
                             fill=FG, font=('MS Gothic',11))
    tag = frame.create_text(380, 22, text=path, anchor='e', fill=ACCENT, font=('MS Gothic',10,'bold'))
    def resize(event):
        frame.coords(tag, event.width-12, 22)
        frame.itemconfigure(title, width=max(40, event.width-180))
    frame.bind('<Configure>', resize)
    frame.bind('<Button-1>', lambda event:view.activate_card(frame,lambda:view.inspect_inventory(row)))
    frame.bind('<MouseWheel>', lambda event:view.canvas.yview_scroll(-int(event.delta/120),'units'))
    return frame
