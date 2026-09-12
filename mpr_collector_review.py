"""Independent table views over one shared scan; no file operations live here."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont, ttk


COLUMNS = (
    ('name', 'Source filename', 215), ('copy_as', 'Copied as', 235),
    ('action', 'Planned action', 130), ('naming', 'Name change', 140),
    ('modified', 'Modified', 145), ('source', 'Source folder', 390),
)


class ReviewTable(ttk.Frame):
    """Sort, search, selection and column sizes belong to this view only."""

    def __init__(self, parent, palette, *, details, searchable=False):
        super().__init__(parent, style='Card.TFrame')
        self.rows = []
        self._visible = {}
        self.palette = palette
        self.details = details
        self.sort_column = None
        self.descending = False
        self.search = tk.StringVar(self, '')
        self.count = tk.StringVar(self, '')
        self._filter_job = None
        if searchable:
            tools = ttk.Frame(self, style='Card.TFrame')
            tools.pack(fill='x', pady=(0, 8))
            ttk.Label(tools, text='Search this view', style='Card.TLabel').pack(side='left', padx=(0, 8))
            self.search_entry = ttk.Entry(tools, textvariable=self.search)
            self.search_entry.pack(side='left', fill='x', expand=True)
            ttk.Button(tools, text='Clear', command=lambda: self.search.set(''), style='Soft.TButton').pack(side='left', padx=6)
            ttk.Label(tools, textvariable=self.count, style='Muted.TLabel').pack(side='left')
            self.search.trace_add('write', self._schedule_filter)
        body = ttk.Frame(self, style='Card.TFrame')
        body.pack(fill='both', expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(body, columns=[c[0] for c in COLUMNS], show='headings',
                                  style='Files.Treeview', selectmode='browse', height=3)
        for key, label, width in COLUMNS:
            self.table.heading(key, text=label, command=lambda k=key: self.sort_by(k))
            self.table.column(key, width=width, minwidth=70, stretch=False, anchor='w')
        sy = ttk.Scrollbar(body, orient='vertical', command=self.table.yview)
        sx = ttk.Scrollbar(body, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.table.grid(row=0, column=0, sticky='nsew')
        sy.grid(row=0, column=1, sticky='ns')
        sx.grid(row=1, column=0, sticky='ew')
        self.table.bind('<Double-1>', self._double_click)
        self.table.bind('<Return>', lambda e: self.show_selected_details())
        self.apply_palette(palette)

    def _schedule_filter(self, *args):
        if self._filter_job is not None:
            self.after_cancel(self._filter_job)
        self._filter_job = self.after_idle(self._filter)

    def _filter(self):
        self._filter_job = None
        self.render()

    def destroy(self):
        if self._filter_job is not None:
            self.after_cancel(self._filter_job)
        super().destroy()

    def apply_palette(self, palette):
        self.palette = palette
        # Stripe for readability only. Filename changes are spelled out.
        self.table.tag_configure('even', background=palette['entry_bg'], foreground=palette['text'])
        self.table.tag_configure('odd', background=palette['table_alt'], foreground=palette['text'])

    def set_rows(self, rows):
        self.rows = list(rows)
        self.render()

    def render(self):
        old_selection = self.table.selection()
        selected_path = self._visible.get(old_selection[0], {}).get('_path') if old_selection else None
        scroll_x, scroll_y = self.table.xview()[0], self.table.yview()[0]
        query = self.search.get().strip().casefold()
        rows = [row for row in self.rows if not query or any(query in str(row.get(c[0], '')).casefold() for c in COLUMNS)]
        if self.sort_column:
            rows.sort(key=lambda row: str(row.get(self.sort_column, '')).casefold(), reverse=self.descending)
        self.table.delete(*self.table.get_children())
        self._visible = {}
        for index, row in enumerate(rows):
            iid = self.table.insert('', 'end', values=[row.get(key, '') for key, _, _ in COLUMNS],
                                    tags=('even' if index % 2 == 0 else 'odd',))
            self._visible[iid] = row
            if selected_path is not None and row.get('_path') == selected_path:
                self.table.selection_set(iid)
        self.table.xview_moveto(scroll_x)
        self.table.yview_moveto(scroll_y)
        self.count.set(f'{len(rows)} of {len(self.rows)} files')

    def sort_by(self, column):
        self.descending = not self.descending if self.sort_column == column else False
        self.sort_column = column
        for key, label, _ in COLUMNS:
            suffix = (' ▼' if self.descending else ' ▲') if key == column else ''
            self.table.heading(key, text=label + suffix)
        self.render()

    def autofit(self, column):
        style = ttk.Style(self)
        body_font = tkfont.Font(self, font=style.lookup('Files.Treeview', 'font'))
        header_font = tkfont.Font(self, font=style.lookup('Files.Treeview.Heading', 'font'))
        width = header_font.measure(self.table.heading(column, 'text')) + 28
        for row in self._visible.values():
            width = max(width, body_font.measure(str(row.get(column, ''))) + 24)
        # A single unusual path must not monopolize the viewport.
        cap = min(520, max(100, self.table.winfo_width() // 2))
        self.table.column(column, width=max(70, min(width, cap)))

    def fit_columns(self):
        for key, _, _ in COLUMNS:
            self.autofit(key)

    def _double_click(self, event):
        if self.table.identify_region(event.x, event.y) == 'separator':
            column = self.table.identify_column(event.x)
            if column and column != '#0':
                self.autofit(COLUMNS[int(column[1:]) - 1][0])
            return 'break'
        iid = self.table.identify_row(event.y)
        if iid:
            self.table.selection_set(iid)
            self.show_selected_details()
        return 'break'

    def show_selected_details(self):
        selected = self.table.selection()
        if selected:
            self.details(self._visible[selected[0]])
