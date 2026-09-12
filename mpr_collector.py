from __future__ import annotations

import json
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from mpr_collector_core import (
    analyze_flat_name_conflicts,
    collect_mpr_files_by_rules,
    copy_files_flat,
    list_immediate_subfolders,
    load_app_settings,
    local_program_data_dir,
    plan_flat_copy_names,
    relative_display_path,
    save_app_settings,
    selection_state,
    set_selection_rule,
    write_json_atomic,
)

from mpr_collector_themes import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME
from mpr_collector_review import COLUMNS, ReviewTable

APP_NAME = "MPR Collector"


def app_program_dir() -> Path:
    """Directory containing the collector script/executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_config_dir() -> Path:
    """Portable data folder stored next to the MPR Collector itself."""
    return local_program_data_dir(app_program_dir())


class MPRCollectorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1240x820")
        self.minsize(900, 680)

        cfg = app_config_dir()
        self.presets_path = cfg / "presets.json"
        self.settings_path = cfg / "settings.json"
        saved_settings = load_app_settings(self.settings_path)
        self.remember_paths = tk.BooleanVar(value=saved_settings.get('remember_paths', True))
        self._saved_layout = saved_settings.get('layout', {})
        self._loaded_root = None
        self._busy = False
        self._job_queue = queue.Queue()
        self._poll_id = None
        saved_scheme = saved_settings.get("color_scheme", "")
        if saved_scheme not in COLOR_SCHEMES:
            saved_scheme = DEFAULT_COLOR_SCHEME

        self.color_scheme = tk.StringVar(value=saved_scheme)
        self.palette = COLOR_SCHEMES[saved_scheme]
        self.configure(bg=self.palette["bg"])

        self.root_folder = tk.StringVar()
        self.destination_folder = tk.StringVar()
        self.overwrite_existing = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value="Choose folders, then check the experiment branches you want.")
        self.scan_summary = tk.StringVar(value="No scan yet")
        self.preset_name = tk.StringVar()
        self.selection_summary = tk.StringVar(value="Nothing selected")

        # Selection is hierarchical.  A True rule selects a whole subtree;
        # a deeper False rule excludes one branch; an even deeper True rule
        # can include part of that excluded branch again.
        self.selection_rules: dict[Path, bool] = {}
        self.scanned_files: list[Path] = []
        self.copy_name_plan: dict[Path, str] = {}
        self.item_paths: dict[str, Path] = {}
        self.review_window = None
        self.review_popup_view = None
        self._review_rows = []
        self._details_windows = []

        self._shadow_frames: list[tk.Frame] = []
        self._border_frames: list[tk.Frame] = []

        self._configure_styles()
        self._build_selection_images()
        self._build_ui()
        self._refresh_presets()
        self._restore_last_folders()
        self.after_idle(self._restore_layout)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- visual design ----------
    def _configure_styles(self) -> None:
        p = self.palette
        style = ttk.Style(self)
        try:
            if "clam" in style.theme_names():
                style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=p["bg"])
        style.configure("Card.TFrame", background=p["card"])
        style.configure("Card.TLabel", background=p["card"], foreground=p["text"], font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=p["card"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=p["card"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("Status.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))

        style.configure(
            "Accent.TButton",
            background=p["accent"], foreground="#ffffff", bordercolor=p["accent_pressed"],
            lightcolor=p["accent_hover"], darkcolor=p["accent_pressed"],
            padding=(13, 7), font=("Segoe UI Semibold", 9), relief="flat", borderwidth=1,
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", p["accent_pressed"]), ("active", p["accent_hover"])],
            lightcolor=[("active", p["accent_hover"])],
        )
        style.configure(
            "Soft.TButton",
            background=p["soft"], foreground=p["text"], bordercolor=p["border"],
            lightcolor=p["entry_bg"], darkcolor=p["border"],
            padding=(9, 5), font=("Segoe UI", 9), relief="flat", borderwidth=1,
        )
        style.map("Soft.TButton", background=[("active", p["soft_hover"]), ("pressed", p["select_bg"])])

        style.configure(
            "Folder.Treeview", background=p["entry_bg"], fieldbackground=p["entry_bg"],
            foreground=p["text"], rowheight=29, font=("Segoe UI", 10),
            bordercolor=p["border"], borderwidth=1,
        )
        style.map("Folder.Treeview", background=[("selected", p["select_bg"])], foreground=[("selected", p["text"])])
        style.configure("Folder.Treeview.Heading", background=p["soft"], foreground=p["text"], font=("Segoe UI Semibold", 9))

        style.configure(
            "Files.Treeview", background=p["entry_bg"], fieldbackground=p["entry_bg"],
            foreground=p["text"], rowheight=28, font=("Segoe UI", 9), bordercolor=p["border"],
        )
        style.configure("Files.Treeview.Heading", background=p["soft"], foreground=p["text"], font=("Segoe UI Semibold", 9), padding=(6, 4))
        style.map("Files.Treeview", background=[("selected", p["select_bg"])], foreground=[("selected", p["text"])])

        style.configure("Warm.TCheckbutton", background=p["card"], foreground=p["text"], font=("Segoe UI", 9))
        style.map("Warm.TCheckbutton", background=[("active", p["card"])])
        style.configure("TEntry", fieldbackground=p["entry_bg"], bordercolor=p["border"], padding=6)
        style.configure("TCombobox", fieldbackground=p["entry_bg"], bordercolor=p["border"], padding=5)
        style.map('TCombobox', fieldbackground=[('readonly', p['entry_bg'])], foreground=[('readonly', p['text'])])
        style.configure('Horizontal.TProgressbar', background=p['accent'], troughcolor=p['bg'], borderwidth=0)
        style.configure('TEntry', foreground=p['text'], insertcolor=p['text'])
        style.map('TEntry', fieldbackground=[('disabled', p['soft'])], foreground=[('disabled', p['muted'])])
        style.configure('TCombobox', foreground=p['text'], arrowcolor=p['text'], background=p['soft'])
        style.map('TCombobox', fieldbackground=[('disabled', p['soft']), ('readonly', p['entry_bg'])],
                  foreground=[('disabled', p['muted']), ('readonly', p['text'])],
                  selectbackground=[('readonly', p['select_bg'])], selectforeground=[('readonly', p['text'])])
        self.option_add('*TCombobox*Listbox.background', p['entry_bg'])
        self.option_add('*TCombobox*Listbox.foreground', p['text'])
        self.option_add('*TCombobox*Listbox.selectBackground', p['select_bg'])
        self.option_add('*TCombobox*Listbox.selectForeground', p['text'])
        for kind in ('Vertical.TScrollbar', 'Horizontal.TScrollbar'):
            style.configure(kind, background=p['soft'], troughcolor=p['bg'], arrowcolor=p['text'],
                            bordercolor=p['border'], lightcolor=p['soft'], darkcolor=p['soft'])
            style.map(kind, background=[('active', p['soft_hover'])])
        for kind in ('Accent.TButton', 'Soft.TButton'):
            style.map(kind, foreground=[('disabled', p['muted'])])
        style.configure('Warm.TCheckbutton', indicatorbackground=p['entry_bg'], indicatorforeground=p['text'])
        style.map('Warm.TCheckbutton', indicatorbackground=[('selected', p['accent']), ('!selected', p['entry_bg'])],
                  indicatorforeground=[('selected', '#ffffff')], foreground=[('disabled', p['muted'])])
        for kind in ('TEntry', 'TCombobox', 'Folder.Treeview', 'Files.Treeview', 'Files.Treeview.Heading'):
            style.configure(kind, lightcolor=p['border'], darkcolor=p['border'], bordercolor=p['border'])

    def _build_selection_images(self):
        self._selection_images = {}
        for state in ('checked', 'unchecked', 'partial'):
            icon = tk.PhotoImage(master=self, width=20, height=20)
            icon.put(self.palette['muted'], to=(2, 2, 18, 18))
            icon.put(self.palette['entry_bg'], to=(3, 3, 17, 17))
            if state != 'unchecked':
                icon.put(self.palette['accent'], to=(2, 2, 18, 18))
                if state == 'partial':
                    icon.put('#ffffff', to=(5, 9, 15, 12))
                else:
                    for x, y in ((5, 9), (6, 10), (7, 11), (8, 12), (9, 11), (10, 10), (11, 9), (12, 8), (13, 7)):
                        icon.put('#ffffff', to=(x, y, x+2, y+2))
            self._selection_images[state] = icon

    def _card(self, parent: tk.Misc, *, padx: int = 1, pady: int = 1) -> tuple[tk.Frame, ttk.Frame]:
        """Return a subtle bordered/shadowed card and its inner ttk frame."""
        shadow = tk.Frame(parent, bg=self.palette["shadow"], bd=0)
        border = tk.Frame(shadow, bg=self.palette["border"], bd=0)
        self._shadow_frames.append(shadow)
        self._border_frames.append(border)
        border.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
        inner = ttk.Frame(border, style="Card.TFrame", padding=(12, 8))
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return shadow, inner

    def _build_ui(self) -> None:
        self.banner = tk.Canvas(self, height=56, bg=self.palette['card'], highlightthickness=0)
        self.banner.pack(fill='x')
        self.banner.bind('<Configure>', self._draw_gradient_banner)
        main = ttk.Frame(self, style='App.TFrame', padding=(16, 10, 16, 10))
        main.pack(fill='both', expand=True)

        card, paths = self._card(main)
        card.pack(fill='x', pady=(0, 8))
        paths.columnconfigure(1, weight=1)
        ttk.Label(paths, text='01  /  LOCATIONS', style='Section.TLabel').grid(row=0, column=0, sticky='w')
        appearance = ttk.Frame(paths, style='Card.TFrame')
        appearance.grid(row=0, column=1, columnspan=2, sticky='e')
        ttk.Label(appearance, text='Appearance', style='Muted.TLabel').pack(side='left', padx=8)
        self.theme_combo = ttk.Combobox(appearance, textvariable=self.color_scheme,
                                      values=list(COLOR_SCHEMES), state='readonly', width=18)
        self.theme_combo.pack(side='left')
        self.theme_combo.bind('<<ComboboxSelected>>', self._on_color_scheme_changed)
        ttk.Button(appearance, text='Reset layout', command=self.reset_layout,
                   style='Soft.TButton').pack(side='left', padx=(8, 0))
        ttk.Label(paths, text='Mother folder', style='Card.TLabel').grid(row=1, column=0, sticky='w', padx=(0, 12), pady=(8, 4))
        self.root_entry = ttk.Entry(paths, textvariable=self.root_folder)
        self.root_entry.grid(row=1, column=1, sticky='ew', pady=(8, 4))
        self.root_entry.bind('<Return>', lambda e: self._apply_root_entry())
        self.root_entry.bind('<FocusOut>', lambda e: self._apply_root_entry())
        ttk.Button(paths, text='Browse…', command=self.choose_root, style='Soft.TButton').grid(row=1, column=2, padx=(8, 0), pady=(8, 4))
        ttk.Label(paths, text='Destination', style='Card.TLabel').grid(row=2, column=0, sticky='w', padx=(0, 12))
        self.dest_entry = ttk.Entry(paths, textvariable=self.destination_folder)
        self.dest_entry.grid(row=2, column=1, sticky='ew')
        self.dest_entry.bind('<Return>', lambda e: self._destination_changed())
        self.dest_entry.bind('<FocusOut>', lambda e: self._destination_changed())
        ttk.Button(paths, text='Browse…', command=self.choose_destination, style='Soft.TButton').grid(row=2, column=2, padx=(8, 0))
        ttk.Checkbutton(paths, text='Remember folder paths on this computer', variable=self.remember_paths,
                        command=self._save_last_folders, style='Warm.TCheckbutton').grid(row=3, column=1, sticky='w', pady=(7, 0))

        self.workspace_panes = tk.PanedWindow(main, orient='vertical', bd=0, sashwidth=9,
                                              bg=self.palette['bg'], opaqueresize=True)
        self.workspace_panes.pack(fill='both', expand=True)
        self.folder_panes = tk.PanedWindow(self.workspace_panes, orient='horizontal', bd=0,
                                          sashwidth=9, bg=self.palette['bg'], opaqueresize=True)
        self.workspace_panes.add(self.folder_panes, minsize=200, stretch='always')
        left_card, left = self._card(self.folder_panes)
        right_card, right = self._card(self.folder_panes)
        self.folder_panes.add(left_card, minsize=390, stretch='always')
        self.folder_panes.add(right_card, minsize=240, stretch='always')
        ttk.Label(left, text='02  /  SELECT BRANCHES', style='Section.TLabel').pack(anchor='w')
        ttk.Label(left, text='Checkbox: include/exclude · Folder name: focus · Double-click name: expand', style='Muted.TLabel', wraplength=510).pack(anchor='w', pady=(4, 6))
        toolbar = ttk.Frame(left, style='Card.TFrame')
        toolbar.pack(fill='x', pady=(0, 6))
        for label, command in [('Expand', self.expand_focused), ('Collapse', self.collapse_focused),
                               ('Include', lambda: self.set_focused_selection(True)),
                               ('Exclude', lambda: self.set_focused_selection(False)), ('Clear', self.clear_selection)]:
            ttk.Button(toolbar, text=label, command=command, style='Soft.TButton').pack(side='left', padx=(0, 4))
        ttk.Label(left, text='✓ Included   − Mixed selection   □ Excluded', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        tree_frame = ttk.Frame(left, style='Card.TFrame')
        tree_frame.pack(fill='both', expand=True)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_frame, show='tree', selectmode='browse', style='Folder.Treeview', height=4)
        self.tree.column('#0', width=600, minwidth=200, stretch=True)
        self._scrollable(self.tree, tree_frame)
        self.tree.bind('<<TreeviewOpen>>', self._on_tree_open)
        self.tree.bind('<Button-1>', self._on_tree_click)
        self.tree.bind('<Double-1>', self._on_tree_double_click)
        self.tree.bind('<Right>', lambda e: (self.expand_focused(), 'break')[1])
        self.tree.bind('<Left>', lambda e: (self.collapse_focused(), 'break')[1])
        self.tree.bind('<space>', self._toggle_focused)

        ttk.Label(right, text='SELECTION & PRESETS', style='Section.TLabel').pack(anchor='w')
        ttk.Label(right, textvariable=self.selection_summary, style='Muted.TLabel').pack(anchor='w', pady=(4, 6))
        rule_frame = ttk.Frame(right, style='Card.TFrame')
        rule_frame.pack(fill='both', expand=True)
        rule_frame.rowconfigure(0, weight=1)
        rule_frame.columnconfigure(0, weight=1)
        self.rule_list = tk.Listbox(rule_frame, height=3, font=('Segoe UI', 10),
                                   bg=self.palette['entry_bg'], fg=self.palette['text'],
                                   relief='flat', highlightthickness=0, exportselection=False,
                                   selectbackground=self.palette['select_bg'], selectforeground=self.palette['text'])
        self._scrollable(self.rule_list, rule_frame)
        preset = ttk.Frame(right, style='Card.TFrame')
        preset.pack(side='bottom', fill='x', pady=(6, 0), before=rule_frame)
        preset.columnconfigure(0, weight=1)
        self.preset_combo = ttk.Combobox(preset, textvariable=self.preset_name, state='readonly', width=12)
        self.preset_combo.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        ttk.Button(preset, text='Load', command=self.load_preset, style='Soft.TButton').grid(row=0, column=1)
        presets_bar = ttk.Frame(right, style='Card.TFrame')
        presets_bar.pack(side='bottom', fill='x', pady=(5, 0), before=preset)
        ttk.Button(presets_bar, text='Save selection', command=self.save_preset, style='Soft.TButton').pack(side='left')
        ttk.Button(presets_bar, text='Delete preset', command=self.delete_preset, style='Soft.TButton').pack(side='left', padx=5)

        result_card, result = self._card(self.workspace_panes)
        self.workspace_panes.add(result_card, minsize=190, stretch='always')
        top = ttk.Frame(result, style='Card.TFrame')
        top.pack(fill='x', pady=(0, 7))
        ttk.Label(top, text='03  /  REVIEW & COPY', style='Section.TLabel').pack(side='left')
        ttk.Label(top, textvariable=self.scan_summary, style='Muted.TLabel').pack(side='right')
        actions = ttk.Frame(result, style='Card.TFrame')
        actions.pack(fill='x', pady=(0, 7))
        self.scan_button = ttk.Button(actions, text='Scan selected folders', command=self.scan_files, style='Soft.TButton')
        self.scan_button.pack(side='left')
        self.copy_button = self._accent_button(actions, 'Copy MPR files', self.copy_files)
        self.copy_button.pack(side='left', padx=8)
        self.copy_button.state(['disabled'])
        ttk.Checkbutton(actions, text='Replace existing files', variable=self.overwrite_existing,
                        command=self._refresh_files_table, style='Warm.TCheckbutton').pack(side='left', padx=6)
        ttk.Button(actions, text='Open review window ↗', command=self.open_review_window, style='Soft.TButton').pack(side='right')
        ttk.Label(result, text='Name adjusted = a unique destination name, not an error. Double-click a row for full paths.',
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
        self.review_view = ReviewTable(result, self.palette, details=self.show_file_details)
        self.review_view.pack(fill='both', expand=True)
        self.files_table = self.review_view.table
        footer = ttk.Frame(main, style='App.TFrame')
        footer.pack(side='bottom', fill='x', pady=(8, 0), before=self.workspace_panes)
        ttk.Label(footer, textvariable=self.status_text, style='Status.TLabel', anchor='w').pack(side='left', fill='x', expand=True)
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=110)

    def _scrollable(self, widget, parent):
        vertical = ttk.Scrollbar(parent, orient='vertical', command=widget.yview)
        horizontal = ttk.Scrollbar(parent, orient='horizontal', command=widget.xview)
        widget.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        widget.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')

    def _capture_layout(self):
        layout = {'columns': {key: self.files_table.column(key, 'width') for key in self.files_table['columns']}}
        if self.state() != 'withdrawn':
            layout['width'] = self.winfo_width()
            layout['height'] = self.winfo_height()
            layout['maximized'] = self.state() == 'zoomed'
        for key, pane, axis in [('vertical', self.workspace_panes, 1), ('horizontal', self.folder_panes, 0)]:
            extent = pane.winfo_height() if axis else pane.winfo_width()
            if extent > 1:
                layout[key] = pane.sash_coord(0)[axis] / extent
        return layout

    def _restore_layout(self):
        saved = self._saved_layout
        try:
            width = max(900, min(int(saved.get('width', 1240)), self.winfo_screenwidth()))
            height = max(680, min(int(saved.get('height', 820)), self.winfo_screenheight() - 70))
            self.geometry(f'{width}x{height}')
            if saved.get('maximized') is True:
                self.state('zoomed')
            self.update_idletasks()
            for key, pane, axis, default in [('vertical', self.workspace_panes, 1, .45), ('horizontal', self.folder_panes, 0, .62)]:
                fraction = max(.2, min(.8, float(saved.get(key, default))))
                extent = pane.winfo_height() if axis else pane.winfo_width()
                pane.sash_place(0, 0 if axis else int(extent*fraction), int(extent*fraction) if axis else 0)
            columns = saved.get('columns', {})
            if isinstance(columns, dict):
                for key in self.files_table['columns']:
                    if key in columns:
                        self.files_table.column(key, width=max(70, min(1500, int(columns[key]))))
        except (ValueError, TypeError, tk.TclError, OverflowError):
            pass

    def reset_layout(self):
        self._saved_layout = {}
        self.state('normal')
        for key, _label, width in COLUMNS:
            self.files_table.column(key, width=width)
        self._restore_layout()

    def set_focused_selection(self, selected):
        path = self._focused_path()
        if path and not self._busy:
            set_selection_rule(self.selection_rules, path, selected)
            self._selection_changed()

    def _toggle_focused(self, event=None):
        path = self._focused_path()
        if path:
            self.set_focused_selection(selection_state(path, self.selection_rules) != 'checked')
        return 'break'

    def _destination_changed(self):
        self._save_last_folders()
        self._refresh_files_table()

    def _start_job(self, work, completed, label):
        if self._busy:
            return
        self._busy = True
        self.status_text.set(label)
        self._disabled_widgets = []
        def disable(parent):
            for widget in parent.winfo_children():
                if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton)):
                    self._disabled_widgets.append((widget, widget.state()))
                    widget.state(['disabled'])
                disable(widget)
        disable(self)
        self.progress.pack(side='right', padx=(8, 0))
        self.progress.start(15)
        def run():
            try:
                self._job_queue.put((True, work()))
            except Exception as exc:
                self._job_queue.put((False, exc))
        threading.Thread(target=run, daemon=True).start()
        self._job_completed = completed
        self._poll_id = self.after(40, self._poll_job)

    def _poll_job(self):
        self._poll_id = None
        try:
            success, value = self._job_queue.get_nowait()
        except queue.Empty:
            self._poll_id = self.after(40, self._poll_job)
            return
        self._busy = False
        self.progress.stop()
        self.progress.pack_forget()
        for widget, previous in self._disabled_widgets:
            if widget.winfo_exists():
                widget.state(['!disabled'])
                widget.state(previous)
        if success:
            self._job_completed(value)
        else:
            self.status_text.set('Operation failed. See the error for details.')
            messagebox.showerror(APP_NAME, str(value))
        self._sync_popup_copy_button()

    def _accent_button(self, parent: tk.Misc, text: str, command) -> ttk.Button:
        return ttk.Button(parent, text=text, command=command, style="Accent.TButton")

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    def _apply_table_tag_colors(self) -> None:
        if hasattr(self, 'review_view'):
            self.review_view.apply_palette(self.palette)
        if self._review_is_open():
            self.review_popup_view.apply_palette(self.palette)
            self.review_window.configure(bg=self.palette['bg'])

    def _review_is_open(self):
        return self.review_window is not None and self.review_window.winfo_exists()

    def open_review_window(self):
        if self._review_is_open():
            self.review_window.deiconify()
            self.review_window.lift()
            return
        window = tk.Toplevel(self)
        self.review_window = window
        window.title('Review & Copy — MPR Collector')
        window.configure(bg=self.palette['bg'])
        window.geometry('1180x680')
        window.minsize(760, 440)
        window.protocol('WM_DELETE_WINDOW', window.destroy)
        content = ttk.Frame(window, style='Card.TFrame', padding=16)
        content.pack(fill='both', expand=True, padx=10, pady=10)
        heading = ttk.Frame(content, style='Card.TFrame')
        heading.pack(fill='x', pady=(0, 8))
        ttk.Label(heading, text='REVIEW & COPY', style='Section.TLabel').pack(side='left')
        ttk.Label(heading, textvariable=self.scan_summary, style='Muted.TLabel').pack(side='right')
        ttk.Label(content, text='Independent view · Search and sorting do not change the main table or the files to copy.',
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        actions = ttk.Frame(content, style='Card.TFrame')
        actions.pack(fill='x', pady=(0, 8))
        self.popup_copy_button = self._accent_button(actions, 'Copy all scanned files', self.copy_files)
        self.popup_copy_button.pack(side='left')
        ttk.Button(actions, text='Fit columns', command=lambda: self.review_popup_view.fit_columns(),
                   style='Soft.TButton').pack(side='left', padx=8)
        ttk.Button(actions, text='Full file details', command=lambda: self.review_popup_view.show_selected_details(),
                   style='Soft.TButton').pack(side='left')
        ttk.Button(actions, text='Close window', command=window.destroy, style='Soft.TButton').pack(side='right')
        ttk.Label(content, text='Name adjusted = copied under a unique name. Auto-fit is capped; full paths are in file details.',
                  style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
        self.review_popup_view = ReviewTable(content, self.palette, details=self.show_file_details, searchable=True)
        self.review_popup_view.pack(fill='both', expand=True)
        ttk.Label(content, textvariable=self.status_text, style='Muted.TLabel', wraplength=1050).pack(fill='x', pady=(8, 0))
        self.review_popup_view.set_rows(self._review_rows)
        self._sync_popup_copy_button()

    def _sync_popup_copy_button(self):
        if self._review_is_open():
            self.popup_copy_button.state(['disabled' if self._busy or not self.scanned_files else '!disabled'])

    def show_file_details(self, row):
        window = tk.Toplevel(self)
        window.title('File details — MPR Collector')
        window.geometry('820x420')
        window.minsize(480, 250)
        window.configure(bg=self.palette['bg'])
        panel = ttk.Frame(window, style='Card.TFrame', padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='FILE DETAILS · snapshot when opened', style='Section.TLabel').pack(anchor='w', pady=(0, 8))
        body = ttk.Frame(panel, style='Card.TFrame')
        body.pack(fill='both', expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        text = tk.Text(body, wrap='word', font=('Segoe UI', 11), bg=self.palette['entry_bg'],
                       fg=self.palette['text'], insertbackground=self.palette['text'], relief='flat', padx=10, pady=10)
        text.grid(row=0, column=0, sticky='nsew')
        bar = ttk.Scrollbar(body, orient='vertical', command=text.yview)
        bar.grid(row=0, column=1, sticky='ns')
        text.configure(yscrollcommand=bar.set)
        source = row.get('_path', row.get('source', ''))
        destination = self.destination_folder.get().strip()
        target = str(Path(destination).expanduser() / row['copy_as']) if destination else 'Choose a destination first'
        text.insert('1.0', f"Source file\n{source}\n\nDestination file\n{target}\n\nPlanned action: {row['action']}\nFilename: {row['naming']}\n\nSource files are copied without renaming or deleting them.")
        text.configure(state='disabled')
        self._details_windows.append((window, text))
        ttk.Button(panel, text='Close', command=window.destroy, style='Soft.TButton').pack(anchor='e', pady=(8, 0))

    def _on_color_scheme_changed(self, _event=None) -> None:
        name = self.color_scheme.get()
        if name not in COLOR_SCHEMES:
            return
        self.palette = COLOR_SCHEMES[name]
        self.configure(bg=self.palette["bg"])
        self._configure_styles()
        for frame in self._shadow_frames:
            try:
                frame.configure(bg=self.palette["shadow"])
            except tk.TclError:
                pass
        for frame in self._border_frames:
            try:
                frame.configure(bg=self.palette["border"])
            except tk.TclError:
                pass
        if hasattr(self, "rule_list"):
            self.rule_list.configure(
                bg=self.palette["entry_bg"], fg=self.palette["text"],
                selectbackground=self.palette["select_bg"], selectforeground=self.palette["text"],
                highlightbackground=self.palette["border"],
            )
        if hasattr(self, "banner"):
            self.banner.configure(bg=self.palette["bg"])
            self._draw_gradient_banner()
        self.workspace_panes.configure(bg=self.palette['bg'])
        self.folder_panes.configure(bg=self.palette['bg'])
        self._build_selection_images()
        self._refresh_loaded_tree_states()
        self._apply_table_tag_colors()
        self._details_windows = [(w, text) for w, text in self._details_windows if w.winfo_exists()]
        for window, text in self._details_windows:
            window.configure(bg=self.palette['bg'])
            text.configure(bg=self.palette['entry_bg'], fg=self.palette['text'], insertbackground=self.palette['text'])
        self._save_last_folders()

    def _draw_gradient_banner(self, _event=None) -> None:
        c = self.banner
        p = self.palette
        c.delete('all')
        c.configure(bg=p['accent_pressed'])
        c.create_rectangle(18, 10, 52, 44, fill='#ffffff', outline='')
        c.create_text(35, 27, text='M', fill=p['accent_pressed'], font=('Segoe UI Semibold', 17))
        c.create_text(66, 19, anchor='w', text='MPR Collector', fill='#ffffff', font=('Segoe UI Semibold', 19))
        c.create_text(67, 42, anchor='w', text='Select experiments. Review filenames. Collect with confidence.', fill='#e5ecf5', font=('Segoe UI', 10))
        c.create_text(max(650, c.winfo_width()-22), 27, anchor='e', text='LOCAL FILE UTILITY', fill='#e5ecf5', font=('Segoe UI Semibold', 9))
        c.create_line(0, 55, c.winfo_width(), 55, fill=p['border'])

    def _restore_last_folders(self) -> None:
        settings = load_app_settings(self.settings_path)
        root = settings.get("root_folder", "")
        dest = settings.get("destination_folder", "")
        if root:
            self.root_folder.set(root)
            p = Path(root).expanduser()
            if p.is_dir():
                self._load_tree(p.resolve())
                self.status_text.set("Previous mother folder restored. Select the experiment branches you want.")
        if dest:
            self.destination_folder.set(dest)

    def _save_last_folders(self) -> None:
        try:
            save_app_settings(
                self.settings_path,
                self.root_folder.get().strip(),
                self.destination_folder.get().strip(),
                self.color_scheme.get(),
                remember_paths=self.remember_paths.get(),
                layout=self._capture_layout(),
            )
        except Exception:
            pass

    def _on_close(self) -> None:
        if self._busy:
            messagebox.showinfo(APP_NAME, 'Please wait for the current scan or copy to finish before closing.')
            return
        self._save_last_folders()
        self.destroy()

    def _apply_root_entry(self) -> bool:
        if self._busy:
            return False
        text = self.root_folder.get().strip()
        if not text:
            if self._loaded_root is None and self.selection_rules:
                return True  # Legacy presets can contain paths without a mother folder.
            self._clear_scan()
            return False
        p = Path(text).expanduser()
        if not p.is_dir():
            self._clear_scan()
            messagebox.showwarning(APP_NAME, "That mother folder does not exist or cannot be opened.")
            return False
        if p.resolve() == self._loaded_root:
            return True
        self.selection_rules.clear()
        self._load_tree(p.resolve())
        self._refresh_selection_summary()
        self._clear_scan()
        self._save_last_folders()
        return True

    def choose_root(self) -> None:
        initial = self.root_folder.get().strip() or None
        folder = filedialog.askdirectory(title="Choose mother folder", initialdir=initial)
        if not folder:
            return
        self.root_folder.set(folder)
        self.selection_rules.clear()
        self._load_tree(Path(folder).resolve())
        self._refresh_selection_summary()
        self._clear_scan()
        self._save_last_folders()
        self.status_text.set("Mother folder loaded. Click a checkbox to include its entire subtree.")

    def choose_destination(self) -> None:
        initial = self.destination_folder.get().strip() or None
        folder = filedialog.askdirectory(title="Choose destination folder", initialdir=initial)
        if folder:
            self.destination_folder.set(folder)
            self._destination_changed()

    # ---------- lazy folder tree ----------
    def _load_tree(self, root: Path) -> None:
        self._loaded_root = root.resolve()
        self.tree.delete(*self.tree.get_children())
        self.item_paths.clear()
        node = self._insert_folder_node('', root)
        self._ensure_node_loaded(node)
        self.tree.item(node, open=True)

    def _insert_folder_node(self, parent_id: str, folder: Path) -> str:
        node = self.tree.insert(parent_id, "end", text="")
        self.item_paths[node] = folder.resolve()
        self._refresh_item_label(node)
        if list_immediate_subfolders(folder):
            placeholder = self.tree.insert(node, "end", text="…")
            self.item_paths[placeholder] = Path("__placeholder__")
        return node

    def _refresh_item_label(self, node: str) -> None:
        path = self.item_paths.get(node)
        if not path or str(path) == "__placeholder__":
            return
        state = selection_state(path, self.selection_rules)
        self.tree.item(node, text='  ' + path.name, image=self._selection_images[state])

    def _refresh_loaded_tree_states(self) -> None:
        for node, path in list(self.item_paths.items()):
            if str(path) != "__placeholder__" and self.tree.exists(node):
                self._refresh_item_label(node)

    def _populate_one_level(self, parent_id: str, folder: Path) -> None:
        for child in self.tree.get_children(parent_id):
            self.item_paths.pop(child, None)
        self.tree.delete(*self.tree.get_children(parent_id))
        for child in list_immediate_subfolders(folder):
            self._insert_folder_node(parent_id, child)

    def _ensure_node_loaded(self, node: str) -> None:
        path = self.item_paths.get(node)
        if not path or str(path) == "__placeholder__":
            return
        children = self.tree.get_children(node)
        if len(children) == 1 and str(self.item_paths.get(children[0], "")) == "__placeholder__":
            self._populate_one_level(node, path)

    def _on_tree_open(self, _event=None) -> None:
        node = self.tree.focus()
        if node:
            self._ensure_node_loaded(node)

    def _focused_path(self) -> Path | None:
        node = self.tree.focus()
        path = self.item_paths.get(node)
        if not path or str(path) == "__placeholder__":
            return None
        return path

    def _on_tree_click(self, event) -> str:
        if self._busy:
            return 'break'
        node = self.tree.identify_row(event.y)
        if not node:
            return "break"
        path = self.item_paths.get(node)
        if not path or str(path) == "__placeholder__":
            return "break"
        element = self.tree.identify_element(event.x, event.y)
        self.tree.focus_set()
        self.tree.focus(node)
        self.tree.selection_set(node)

        # The native disclosure triangle still works; the large toolbar buttons
        # above are provided for easier expansion.
        if "indicator" in element:
            if self.tree.item(node, "open"):
                self.tree.item(node, open=False)
            else:
                self._ensure_node_loaded(node)
                self.tree.item(node, open=True)
            return "break"

        if element == 'image' or element.endswith('.image'):
            self.set_focused_selection(selection_state(path, self.selection_rules) != 'checked')
        return 'break'

    def _on_tree_double_click(self, event) -> str:
        if self._busy:
            return 'break'
        element = self.tree.identify_element(event.x, event.y)
        # The first click already handles checkbox/disclosure actions.
        # Never undo that action on the second click of the same gesture.
        if 'indicator' in element or 'image' in element:
            return 'break'
        node = self.tree.identify_row(event.y)
        if node and self.item_paths.get(node) and str(self.item_paths[node]) != '__placeholder__':
            self.tree.focus_set()
            self.tree.focus(node)
            self.tree.selection_set(node)
            if self.tree.item(node, 'open'):
                self.tree.item(node, open=False)
            else:
                self._ensure_node_loaded(node)
                self.tree.item(node, open=True)
        return 'break'

    def expand_focused(self) -> None:
        node = self.tree.focus()
        if node:
            self._ensure_node_loaded(node)
            self.tree.item(node, open=True)

    def collapse_focused(self) -> None:
        node = self.tree.focus()
        if node:
            self.tree.item(node, open=False)

    def clear_selection(self) -> None:
        if self._busy:
            return
        self.selection_rules.clear()
        self._selection_changed()

    def _selection_changed(self) -> None:
        self._refresh_loaded_tree_states()
        self._refresh_selection_summary()
        self._clear_scan()

    def _refresh_selection_summary(self) -> None:
        self.rule_list.delete(0, tk.END)
        root_text = self.root_folder.get().strip()
        root = Path(root_text) if root_text else None
        ordered = sorted(self.selection_rules.items(), key=lambda kv: (len(kv[0].parts), str(kv[0]).lower()))
        includes = sum(1 for _p, selected in ordered if selected)
        excludes = sum(1 for _p, selected in ordered if not selected)
        if not ordered:
            self.selection_summary.set("Nothing selected")
            self.rule_list.insert(tk.END, "Click a checkbox on the left to include a branch.")
            return
        self.selection_summary.set(f"{includes} included branch(es) • {excludes} excluded branch(es)")
        for path, selected in ordered:
            shown = relative_display_path(path, root) if root else str(path)
            prefix = "✓  " if selected else "–  exclude  "
            self.rule_list.insert(tk.END, prefix + shown)

    # ---------- scan / copy ----------
    def _clear_scan(self) -> None:
        self.scanned_files = []
        self.copy_name_plan = {}
        self.scan_summary.set("No scan yet")
        self.copy_button.state(["disabled"])
        self._refresh_files_table()

    def scan_files(self) -> None:
        if self._busy:
            return
        if not self._apply_root_entry():
            return
        if not any(self.selection_rules.values()):
            messagebox.showwarning(APP_NAME, 'Select at least one folder branch first.')
            return
        rules = dict(self.selection_rules)
        self._clear_scan()
        self._start_job(lambda: collect_mpr_files_by_rules(rules), self._finish_scan, 'Scanning selected branches…')

    def _finish_scan(self, files):
        self.scanned_files = files
        self.copy_name_plan = plan_flat_copy_names(files)
        self._refresh_files_table()
        if files:
            self.copy_button.state(['!disabled'])
        conflicts = analyze_flat_name_conflicts(self.scanned_files)
        renamed = sum(1 for p in self.scanned_files if self.copy_name_plan.get(p.resolve(), p.name).casefold() != p.name.casefold())
        self.scan_summary.set(f"{len(self.scanned_files)} MPR found • {renamed} adjusted filename(s)")
        self.status_text.set(
            f"Scan complete — {len(self.scanned_files)} MPR file(s). "
            f"{len(conflicts)} repeated filename group(s) are preserved rather than discarded."
        )

    def _refresh_files_table(self) -> None:
        root_text = self.root_folder.get().strip()
        root = Path(root_text) if root_text else None
        destination = self.destination_folder.get().strip()
        rows = []
        for path in self.scanned_files:
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            except OSError:
                modified = ''
            copy_as = self.copy_name_plan.get(path.resolve(), path.name)
            source = relative_display_path(path.parent, root) if root else str(path.parent)
            exists = bool(destination) and (Path(destination).expanduser() / copy_as).exists()
            action = ('Replace' if self.overwrite_existing.get() else 'Skip existing') if exists else 'Copy'
            if not destination:
                action = 'Set destination'
            naming = 'Name adjusted' if copy_as.casefold() != path.name.casefold() else 'Unchanged'
            rows.append(dict(name=path.name, copy_as=copy_as, action=action, naming=naming,
                             modified=modified, source=source, _path=path))
        self._review_rows = rows
        self.review_view.set_rows(rows)
        if self._review_is_open():
            self.review_popup_view.set_rows(rows)
        self._sync_popup_copy_button()

    def copy_files(self) -> None:
        if self._busy:
            return
        if not self._apply_root_entry():
            return
        if not self.scanned_files:
            messagebox.showwarning(APP_NAME, "Scan the selected folders first.")
            return
        destination_text = self.destination_folder.get().strip()
        if not destination_text:
            messagebox.showwarning(APP_NAME, "Choose a destination folder first.")
            return
        destination = Path(destination_text).expanduser().resolve()

        selected_true = [p.resolve() for p, selected in self.selection_rules.items() if selected]
        if any(destination == p or destination.is_relative_to(p) for p in selected_true):
            if not messagebox.askyesno(
                APP_NAME,
                "The destination is inside one of the included source branches. Later scans could see copied files there.\n\nContinue anyway?",
            ):
                return

        if not self.copy_name_plan:
            self.copy_name_plan = plan_flat_copy_names(self.scanned_files)

        existing_count = sum(1 for p in self.scanned_files if (destination / self.copy_name_plan[p.resolve()]).exists())
        renamed = sum(1 for p in self.scanned_files if self.copy_name_plan[p.resolve()].casefold() != p.name.casefold())
        replacing = self.overwrite_existing.get()
        behavior = (
            f"{existing_count} same-named destination file(s) will be replaced."
            if replacing
            else f"{existing_count} same-named destination file(s) will be kept and skipped."
        )
        if not messagebox.askyesno(
            APP_NAME,
            f"Copy {len(self.scanned_files)} MPR file(s) into:\n{destination}\n\n"
            f"Continuation/name collisions preserved with unique copied names: {renamed}\n"
            f"{behavior}\n\n"
            "Other files already in the destination folder will stay exactly where they are.\n"
            "Source files are never moved or deleted. Continue?",
        ):
            return

        files = list(self.scanned_files)
        plan = dict(self.copy_name_plan)
        self._start_job(lambda: copy_files_flat(files, destination, overwrite=replacing, name_plan=plan),
                        self._finish_copy, f'Copying {len(files)} MPR files…')

    def _finish_copy(self, result):
        text = (
            f"Copied: {result.copied}\n"
            f"Skipped because already present: {result.skipped_existing}\n"
            f"Failed: {result.failed}\n\n"
            "No unrelated file in the destination folder was removed.\n"
            "Source files were not moved, renamed, or deleted."
        )
        if result.failures:
            text += "\n\nFirst errors:\n" + "\n".join(result.failures[:5])
        self._refresh_files_table()
        (messagebox.showwarning if result.failed else messagebox.showinfo)(APP_NAME, text)
        self.status_text.set(f"Finished — copied {result.copied}, skipped {result.skipped_existing}, failed {result.failed}.")

    # ---------- presets ----------
    def _read_presets(self) -> dict[str, object]:
        try:
            if self.presets_path.exists():
                data = json.loads(self.presets_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _write_presets(self, presets: dict[str, object]) -> None:
        write_json_atomic(self.presets_path, presets)

    def _refresh_presets(self) -> None:
        names = sorted(self._read_presets().keys(), key=str.lower)
        self.preset_combo["values"] = names
        if self.preset_name.get() not in names:
            self.preset_name.set(names[0] if names else "")

    def save_preset(self) -> None:
        if not any(self.selection_rules.values()):
            messagebox.showwarning(APP_NAME, "There is no included folder selection to save.")
            return
        name = simpledialog.askstring(APP_NAME, "Preset name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        presets = self._read_presets()
        presets[name] = {
            "root": self.root_folder.get().strip(),
            "rules": [
                {"path": str(path), "selected": bool(selected)}
                for path, selected in sorted(self.selection_rules.items(), key=lambda kv: str(kv[0]).lower())
            ],
        }
        self._write_presets(presets)
        self._refresh_presets()
        self.preset_name.set(name)

    def load_preset(self) -> None:
        name = self.preset_name.get().strip()
        presets = self._read_presets()
        if not name or name not in presets:
            return
        raw = presets[name]
        new_rules: dict[Path, bool] = {}
        missing: list[str] = []

        # New format.
        if isinstance(raw, dict) and isinstance(raw.get("rules"), list):
            preset_root = str(raw.get("root", "")).strip()
            if preset_root and Path(preset_root).is_dir():
                self.root_folder.set(preset_root)
                self._load_tree(Path(preset_root).resolve())
            for item in raw["rules"]:
                if not isinstance(item, dict):
                    continue
                path_text = str(item.get("path", ""))
                p = Path(path_text)
                if p.is_dir():
                    set_selection_rule(new_rules, p.resolve(), bool(item.get("selected", True)))
                else:
                    missing.append(path_text)
        # Backward compatibility with old presets that were just lists of included folders.
        elif isinstance(raw, list):
            for path_text in raw:
                p = Path(str(path_text))
                if p.is_dir():
                    set_selection_rule(new_rules, p.resolve(), True)
                else:
                    missing.append(str(path_text))

        self.selection_rules = new_rules
        self._refresh_loaded_tree_states()
        self._refresh_selection_summary()
        self._clear_scan()
        self._save_last_folders()
        if missing:
            messagebox.showwarning(APP_NAME, "Some preset folders no longer exist:\n\n" + "\n".join(missing[:10]))

    def delete_preset(self) -> None:
        name = self.preset_name.get().strip()
        presets = self._read_presets()
        if not name or name not in presets:
            return
        if not messagebox.askyesno(APP_NAME, f"Delete preset '{name}'?"):
            return
        del presets[name]
        self._write_presets(presets)
        self._refresh_presets()


def main() -> int:
    try:
        app = MPRCollectorApp()
        app.mainloop()
        return 0
    except Exception as exc:
        try:
            messagebox.showerror(APP_NAME, f"Unexpected error:\n{exc}")
        except Exception:
            print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
