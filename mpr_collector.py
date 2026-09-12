from __future__ import annotations

import json
import sys
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
)

from mpr_collector_themes import COLOR_SCHEMES, DEFAULT_COLOR_SCHEME

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
        self.minsize(1040, 700)

        cfg = app_config_dir()
        self.presets_path = cfg / "presets.json"
        self.settings_path = cfg / "settings.json"
        saved_settings = load_app_settings(self.settings_path)
        saved_scheme = saved_settings.get("color_scheme", "")
        if saved_scheme not in COLOR_SCHEMES:
            saved_scheme = DEFAULT_COLOR_SCHEME

        self.color_scheme = tk.StringVar(value=saved_scheme)
        self.palette = COLOR_SCHEMES[saved_scheme]
        self.configure(bg=self.palette["bg"])

        self.root_folder = tk.StringVar()
        self.destination_folder = tk.StringVar()
        self.overwrite_existing = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value="Choose folders, then click the experiment branches you want.")
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

        self._shadow_frames: list[tk.Frame] = []
        self._border_frames: list[tk.Frame] = []

        self._configure_styles()
        self._build_ui()
        self._refresh_presets()
        self._restore_last_folders()
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
            padding=(13, 8), font=("Segoe UI Semibold", 9), relief="raised", borderwidth=1,
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
            padding=(11, 7), font=("Segoe UI", 9), relief="raised", borderwidth=1,
        )
        style.map("Soft.TButton", background=[("active", p["soft_hover"]), ("pressed", p["select_bg"])])

        style.configure(
            "Folder.Treeview", background=p["entry_bg"], fieldbackground=p["entry_bg"],
            foreground=p["text"], rowheight=34, font=("Segoe UI", 10),
            bordercolor=p["border"], borderwidth=1,
        )
        style.map("Folder.Treeview", background=[("selected", p["select_bg"])], foreground=[("selected", p["text"])])
        style.configure("Folder.Treeview.Heading", background=p["soft"], foreground=p["text"], font=("Segoe UI Semibold", 9))

        style.configure(
            "Files.Treeview", background=p["entry_bg"], fieldbackground=p["entry_bg"],
            foreground=p["text"], rowheight=28, font=("Segoe UI", 9), bordercolor=p["border"],
        )
        style.configure("Files.Treeview.Heading", background=p["soft"], foreground=p["text"], font=("Segoe UI Semibold", 9), padding=(6, 7))
        style.map("Files.Treeview", background=[("selected", p["select_bg"])], foreground=[("selected", p["text"])])

        style.configure("Warm.TCheckbutton", background=p["card"], foreground=p["text"], font=("Segoe UI", 9))
        style.map("Warm.TCheckbutton", background=[("active", p["card"])])
        style.configure("TEntry", fieldbackground=p["entry_bg"], bordercolor=p["border"], padding=6)
        style.configure("TCombobox", fieldbackground=p["entry_bg"], bordercolor=p["border"], padding=5)

    def _card(self, parent: tk.Misc, *, padx: int = 1, pady: int = 1) -> tuple[tk.Frame, ttk.Frame]:
        """Return a subtle bordered/shadowed card and its inner ttk frame."""
        shadow = tk.Frame(parent, bg=self.palette["shadow"], bd=0)
        border = tk.Frame(shadow, bg=self.palette["border"], bd=0)
        self._shadow_frames.append(shadow)
        self._border_frames.append(border)
        border.pack(fill="both", expand=True, padx=(0, 2), pady=(0, 2))
        inner = ttk.Frame(border, style="Card.TFrame", padding=(12, 10))
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return shadow, inner

    def _build_ui(self) -> None:
        self.banner = tk.Canvas(self, height=78, bg=self.palette["bg"], highlightthickness=0)
        self.banner.pack(fill="x")
        self.banner.bind("<Configure>", self._draw_gradient_banner)

        main = ttk.Frame(self, style="App.TFrame", padding=(12, 8, 12, 8))
        main.pack(fill="both", expand=True)

        # Paths card
        path_card, paths = self._card(main)
        path_card.pack(fill="x", pady=(0, 10))
        paths.columnconfigure(1, weight=1)
        ttk.Label(paths, text="Folders", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        appearance = ttk.Frame(paths, style="Card.TFrame")
        appearance.grid(row=0, column=1, columnspan=2, sticky="e", pady=(0, 6))
        ttk.Label(appearance, text="Color scheme", style="Muted.TLabel").pack(side="left", padx=(0, 7))
        self.theme_combo = ttk.Combobox(
            appearance, textvariable=self.color_scheme, values=list(COLOR_SCHEMES.keys()),
            state="readonly", width=19,
        )
        self.theme_combo.pack(side="left")
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_color_scheme_changed)

        ttk.Label(paths, text="Mother folder", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=5)
        self.root_entry = ttk.Entry(paths, textvariable=self.root_folder)
        self.root_entry.grid(row=1, column=1, sticky="ew", pady=5)
        self.root_entry.bind("<Return>", lambda _e: self._apply_root_entry())
        self.root_entry.bind("<FocusOut>", lambda _e: self._save_last_folders())
        ttk.Button(paths, text="Browse…", command=self.choose_root, style="Soft.TButton").grid(row=1, column=2, padx=(10, 0), pady=5)

        ttk.Label(paths, text="Copy MPR files to", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        self.dest_entry = ttk.Entry(paths, textvariable=self.destination_folder)
        self.dest_entry.grid(row=2, column=1, sticky="ew", pady=5)
        self.dest_entry.bind("<Return>", lambda _e: self._save_last_folders())
        self.dest_entry.bind("<FocusOut>", lambda _e: self._save_last_folders())
        ttk.Button(paths, text="Browse…", command=self.choose_destination, style="Soft.TButton").grid(row=2, column=2, padx=(10, 0), pady=5)
        ttk.Label(paths, text="These two paths are remembered automatically for the next time you open the program.", style="Muted.TLabel").grid(row=3, column=1, sticky="w", pady=(2, 0))

        middle = ttk.Panedwindow(main, orient="horizontal", height=335)
        middle.pack(fill="x", expand=False, pady=(0, 10))

        # Browser card
        left_shadow, left = self._card(middle)
        right_shadow, right = self._card(middle)
        middle.add(left_shadow, weight=3)
        middle.add(right_shadow, weight=2)

        ttk.Label(left, text="Choose experiment folders", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="Single-click selects a folder and everything below it. Double-click deselects that branch. Expand and exclude only what you do not want.",
            style="Muted.TLabel",
            wraplength=670,
            justify="left",
        ).pack(fill="x", pady=(2, 8))

        tools = ttk.Frame(left, style="Card.TFrame")
        tools.pack(fill="x", pady=(0, 6))
        ttk.Button(tools, text="▾  Expand focused", command=self.expand_focused, style="Soft.TButton").pack(side="left")
        ttk.Button(tools, text="▴  Collapse focused", command=self.collapse_focused, style="Soft.TButton").pack(side="left", padx=6)
        ttk.Button(tools, text="Clear selection", command=self.clear_selection, style="Soft.TButton").pack(side="left")

        tree_frame = tk.Frame(left, bg=self.palette["border"], bd=0)
        self._border_frames.append(tree_frame)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", style="Folder.Treeview")
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        yscroll.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Right>", lambda _e: (self.expand_focused(), "break")[1])
        self.tree.bind("<Left>", lambda _e: (self.collapse_focused(), "break")[1])

        # Selection summary card content
        ttk.Label(right, text="Selection", style="Section.TLabel").pack(anchor="w")
        ttk.Label(right, textvariable=self.selection_summary, style="Muted.TLabel").pack(anchor="w", pady=(2, 7))
        self.rule_list = tk.Listbox(
            right,
            selectmode="browse",
            exportselection=False,
            font=("Segoe UI", 9),
            bg=self.palette["entry_bg"],
            fg=self.palette["text"],
            selectbackground=self.palette["select_bg"],
            selectforeground=self.palette["text"],
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.palette["border"],
            activestyle="none",
            height=6,
        )
        self.rule_list.pack(fill="both", expand=True, pady=(0, 8))

        preset = ttk.Frame(right, style="Card.TFrame")
        preset.pack(fill="x")
        ttk.Label(preset, text="Saved selection", style="Card.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.preset_combo = ttk.Combobox(preset, textvariable=self.preset_name, state="readonly")
        self.preset_combo.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        preset.columnconfigure(0, weight=1)
        preset.columnconfigure(1, weight=1)
        preset.columnconfigure(2, weight=1)
        ttk.Button(preset, text="Load", command=self.load_preset, style="Soft.TButton").grid(row=2, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(preset, text="Save current", command=self.save_preset, style="Soft.TButton").grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Button(preset, text="Delete", command=self.delete_preset, style="Soft.TButton").grid(row=2, column=2, sticky="ew", padx=(4, 0))

        # Results card
        result_shadow, result = self._card(main)
        result_shadow.pack(fill="both", expand=True)

        result_top = ttk.Frame(result, style="Card.TFrame")
        result_top.pack(fill="x", pady=(0, 7))
        self._accent_button(result_top, "Scan selected folders", self.scan_files).pack(side="left")
        self._accent_button(result_top, "Copy MPR files", self.copy_files).pack(side="left", padx=8)
        ttk.Checkbutton(
            result_top,
            text="Replace same-named files already in destination",
            variable=self.overwrite_existing,
            style="Warm.TCheckbutton",
        ).pack(side="left", padx=(8, 4))
        ttk.Label(result_top, textvariable=self.scan_summary, style="Muted.TLabel").pack(side="right")

        ttk.Label(
            result,
            text="Replace affects only individual destination files with the same planned filename. Other files already in the destination folder are never removed.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        table_frame = tk.Frame(result, bg=self.palette["border"], bd=0)
        self._border_frames.append(table_frame)
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "copy_as", "modified", "source")
        self.files_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", style="Files.Treeview")
        self.files_table.heading("name", text="Source filename")
        self.files_table.heading("copy_as", text="Copied as")
        self.files_table.heading("modified", text="Modified")
        self.files_table.heading("source", text="Source folder")
        self.files_table.column("name", width=255, anchor="w")
        self.files_table.column("copy_as", width=290, anchor="w")
        self.files_table.column("modified", width=140, anchor="center")
        self.files_table.column("source", width=470, anchor="w")
        self._apply_table_tag_colors()
        sy = ttk.Scrollbar(table_frame, orient="vertical", command=self.files_table.yview)
        self.files_table.configure(yscrollcommand=sy.set)
        self.files_table.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sy.pack(side="right", fill="y", padx=(0, 1), pady=1)

        ttk.Label(main, textvariable=self.status_text, style="Status.TLabel", anchor="w").pack(fill="x", pady=(8, 0))

    def _accent_button(self, parent: tk.Misc, text: str, command) -> ttk.Button:
        return ttk.Button(parent, text=text, command=command, style="Accent.TButton")

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    def _apply_table_tag_colors(self) -> None:
        if not hasattr(self, "files_table"):
            return
        p = self.palette
        self.files_table.tag_configure("even", background=p["entry_bg"])
        self.files_table.tag_configure("odd", background=p["table_alt"])
        self.files_table.tag_configure("renamed", background=p["rename_bg"])

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
        self._apply_table_tag_colors()
        self._save_last_folders()

    def _draw_gradient_banner(self, _event=None) -> None:
        c = self.banner
        c.delete("all")
        width = max(c.winfo_width(), 2)
        height = max(c.winfo_height(), 2)
        start = self._hex_to_rgb(self.palette["gradient_start"])
        middle = self._hex_to_rgb(self.palette["gradient_middle"])
        end = self._hex_to_rgb(self.palette["gradient_end"])
        steps = min(width, 240)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            if t < 0.62:
                u = t / 0.62
                rgb = tuple(round(start[j] + (middle[j] - start[j]) * u) for j in range(3))
            else:
                u = (t - 0.62) / 0.38
                rgb = tuple(round(middle[j] + (end[j] - middle[j]) * u) for j in range(3))
            color = "#%02x%02x%02x" % rgb
            x0 = i * width / steps
            x1 = (i + 1) * width / steps + 1
            c.create_rectangle(x0, 0, x1, height, outline=color, fill=color)
        c.create_text(22, 28, text="MPR Collector", anchor="w", fill=self.palette["gradient_text"], font=("Segoe UI Semibold", 18))
        c.create_text(23, 53, text="Choose experiment branches across BIO machines • recursive to any depth", anchor="w", fill=self.palette["gradient_subtext"], font=("Segoe UI", 9))
        c.create_line(0, height - 1, width, height - 1, fill=self.palette["border"])

    # ---------- persistent folders ----------
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
            )
        except Exception:
            pass

    def _on_close(self) -> None:
        self._save_last_folders()
        self.destroy()

    def _apply_root_entry(self) -> None:
        text = self.root_folder.get().strip()
        if not text:
            return
        p = Path(text).expanduser()
        if not p.is_dir():
            messagebox.showwarning(APP_NAME, "That mother folder does not exist or cannot be opened.")
            return
        self.selection_rules.clear()
        self._load_tree(p.resolve())
        self._refresh_selection_summary()
        self._clear_scan()
        self._save_last_folders()

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
        self.status_text.set("Mother folder loaded. Single-click a folder to include its entire subtree.")

    def choose_destination(self) -> None:
        initial = self.destination_folder.get().strip() or None
        folder = filedialog.askdirectory(title="Choose destination folder", initialdir=initial)
        if folder:
            self.destination_folder.set(folder)
            self._save_last_folders()

    # ---------- lazy folder tree ----------
    def _load_tree(self, root: Path) -> None:
        self.tree.delete(*self.tree.get_children())
        self.item_paths.clear()
        for child in list_immediate_subfolders(root):
            self._insert_folder_node("", child)

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
        icon = {"checked": "☑", "partial": "◩", "unchecked": "☐"}[state]
        self.tree.item(node, text=f"{icon}   {path.name}")

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
        node = self.tree.identify_row(event.y)
        if not node:
            return "break"
        path = self.item_paths.get(node)
        if not path or str(path) == "__placeholder__":
            return "break"
        element = self.tree.identify_element(event.x, event.y)
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

        # A normal click means "include this whole branch".  If it is already
        # included we leave it as-is; double-click is the deliberate deselect.
        if selection_state(path, self.selection_rules) != "checked":
            set_selection_rule(self.selection_rules, path, True)
            self._selection_changed()
        return "break"

    def _on_tree_double_click(self, event) -> str:
        node = self.tree.identify_row(event.y)
        if not node:
            return "break"
        path = self.item_paths.get(node)
        if not path or str(path) == "__placeholder__":
            return "break"
        # Double-click always means exclude/deselect this branch.
        set_selection_rule(self.selection_rules, path, False)
        self.tree.focus(node)
        self.tree.selection_set(node)
        self._selection_changed()
        return "break"

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
            self.rule_list.insert(tk.END, "Single-click a folder on the left to include it.")
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
        self._refresh_files_table()

    def scan_files(self) -> None:
        if not any(self.selection_rules.values()):
            messagebox.showwarning(APP_NAME, "Select at least one folder branch first.")
            return
        self.status_text.set("Scanning selected branches recursively to the deepest subfolders…")
        self.update_idletasks()
        self.scanned_files = collect_mpr_files_by_rules(self.selection_rules)
        self.copy_name_plan = plan_flat_copy_names(self.scanned_files)
        self._refresh_files_table()

        conflicts = analyze_flat_name_conflicts(self.scanned_files)
        renamed = sum(1 for p in self.scanned_files if self.copy_name_plan.get(p.resolve(), p.name).casefold() != p.name.casefold())
        self.scan_summary.set(f"{len(self.scanned_files)} MPR found • {renamed} unique copied name(s)")
        self.status_text.set(
            f"Scan complete — {len(self.scanned_files)} MPR file(s). "
            f"{len(conflicts)} repeated filename group(s) are preserved rather than discarded."
        )

    def _refresh_files_table(self) -> None:
        self.files_table.delete(*self.files_table.get_children())
        root_text = self.root_folder.get().strip()
        root = Path(root_text) if root_text else None
        for idx, path in enumerate(self.scanned_files):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d-%m-%Y %H:%M")
            except OSError:
                modified = ""
            copy_as = self.copy_name_plan.get(path.resolve(), path.name)
            source = relative_display_path(path.parent, root) if root else str(path.parent)
            tag = "renamed" if copy_as.casefold() != path.name.casefold() else ("even" if idx % 2 == 0 else "odd")
            self.files_table.insert("", "end", values=(path.name, copy_as, modified, source), tags=(tag,))

    def copy_files(self) -> None:
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

        result = copy_files_flat(
            self.scanned_files,
            destination,
            overwrite=replacing,
            name_plan=self.copy_name_plan,
        )
        replaced_text = f"Replaced same-named destination files: {existing_count}\n" if replacing else ""
        text = (
            f"Copied: {result.copied}\n"
            f"{replaced_text}"
            f"Skipped because already present: {result.skipped_existing}\n"
            f"Failed: {result.failed}\n\n"
            "No unrelated file in the destination folder was removed.\n"
            "Source files were not moved, renamed, or deleted."
        )
        if result.failures:
            text += "\n\nFirst errors:\n" + "\n".join(result.failures[:5])
        messagebox.showinfo(APP_NAME, text)
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
        self.presets_path.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")

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
