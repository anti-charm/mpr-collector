from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CopyResult:
    copied: int
    skipped_existing: int
    failed: int
    failures: tuple[str, ...] = ()


def _norm_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _is_descendant_or_same(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def set_selection_rule(rules: dict[Path, bool], path: Path | str, selected: bool) -> None:
    """Set a subtree rule and discard stale descendant overrides.

    The nearest rule to a path controls it. Selecting/deselecting a folder
    therefore applies to all descendants until a deeper rule overrides it.
    Redundant rules matching the inherited ancestor state are removed.
    """
    target = _norm_path(path)
    inherited = False
    best_depth = -1
    for existing, value in list(rules.items()):
        existing = _norm_path(existing)
        if existing != target and _is_descendant_or_same(target, existing) and len(existing.parts) > best_depth:
            best_depth = len(existing.parts)
            inherited = bool(value)
    for existing in list(rules):
        existing_resolved = _norm_path(existing)
        if _is_descendant_or_same(existing_resolved, target):
            del rules[existing]
    if bool(selected) != inherited:
        rules[target] = bool(selected)


def effective_selection(path: Path | str, rules: Mapping[Path, bool]) -> bool:
    target = _norm_path(path)
    best_depth = -1
    value = False
    for raw_rule, selected in rules.items():
        rule = _norm_path(raw_rule)
        if _is_descendant_or_same(target, rule) and len(rule.parts) > best_depth:
            best_depth = len(rule.parts)
            value = bool(selected)
    return value


def selection_state(path: Path | str, rules: Mapping[Path, bool]) -> str:
    """Return checked/unchecked/partial for a folder under hierarchical rules."""
    target = _norm_path(path)
    current = effective_selection(target, rules)
    descendant_values = []
    for raw_rule, selected in rules.items():
        rule = _norm_path(raw_rule)
        if rule != target and _is_descendant_or_same(rule, target):
            descendant_values.append(bool(selected))
    if descendant_values and any(v != current for v in descendant_values):
        return 'partial'
    return 'checked' if current else 'unchecked'


def collect_mpr_files_by_rules(rules: Mapping[Path, bool]) -> list[Path]:
    """Collect MPR files from selected rules while honoring excluded subtrees."""
    found: dict[str, Path] = {}
    true_roots = sorted(
        (_norm_path(p) for p, selected in rules.items() if selected),
        key=lambda p: (len(p.parts), str(p).lower()),
    )
    def scan_error(error):
        raise error

    for root in true_roots:
        if not root.is_dir():
            raise FileNotFoundError(f'Selected folder is missing or inaccessible: {root}')
        for current, dirs, files in os.walk(root, onerror=scan_error):
            current_path = Path(current).resolve()
            if not effective_selection(current_path, rules):
                dirs[:] = []
                continue
            dirs[:] = [
                d for d in dirs
                if effective_selection(current_path / d, rules)
                or any(
                    selected and _is_descendant_or_same(_norm_path(rule), (current_path / d).resolve())
                    for rule, selected in rules.items()
                )
            ]
            for name in files:
                if Path(name).suffix.lower() != '.mpr':
                    continue
                path = (current_path / name).resolve()
                key = os.path.normcase(str(path))
                found[key] = path
    return sorted(found.values(), key=lambda p: (p.name.lower(), str(p).lower()))


def save_folder_settings(settings_path: Path | str, root_folder: Path | str, destination_folder: Path | str) -> None:
    path = Path(settings_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'root_folder': str(root_folder),
        'destination_folder': str(destination_folder),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def load_folder_settings(settings_path: Path | str) -> tuple[str, str]:
    path = Path(settings_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return str(data.get('root_folder', '')), str(data.get('destination_folder', ''))
    except Exception:
        return '', ''


def list_immediate_subfolders(folder: Path | str) -> list[Path]:
    """Return readable immediate child folders, sorted by name."""
    folder = Path(folder).expanduser()
    try:
        return sorted(
            (p.resolve() for p in folder.iterdir() if p.is_dir()),
            key=lambda p: p.name.lower(),
        )
    except (PermissionError, OSError):
        return []


def collect_mpr_files(selected_folders: Iterable[Path | str]) -> list[Path]:
    """Recursively collect .mpr files from every selected folder at any depth.

    The same physical path is returned only once, even when selections overlap.
    Matching is case-insensitive on the extension.
    """
    found: dict[str, Path] = {}
    for raw_folder in selected_folders:
        folder = Path(raw_folder).expanduser()
        if not folder.is_dir():
            continue
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if Path(name).suffix.lower() != ".mpr":
                    continue
                path = (Path(root) / name).resolve()
                key = os.path.normcase(str(path))
                found[key] = path
    return sorted(found.values(), key=lambda p: (p.name.lower(), str(p).lower()))


def relative_display_path(path: Path | str, root: Path | str) -> str:
    """Return a compact Windows-style display path beginning at root name."""
    path = Path(path).expanduser().resolve()
    root = Path(root).expanduser().resolve()
    try:
        rel = path.relative_to(root)
        parts = [root.name, *rel.parts]
    except ValueError:
        parts = list(path.parts)
    return "\\".join(parts)


def analyze_flat_name_conflicts(files: Iterable[Path | str]) -> dict[str, list[Path]]:
    """Return case-insensitive filename collisions in a flat destination."""
    by_name: dict[str, list[Path]] = {}
    for raw in files:
        path = Path(raw).resolve()
        by_name.setdefault(path.name.lower(), []).append(path)
    return {name: paths for name, paths in by_name.items() if len(paths) > 1}


def _safe_suffix_component(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip().rstrip(".")
    return text or "folder"


def _shortest_unique_folder_suffix(path: Path, group: list[Path]) -> str:
    """Return the shortest parent-path suffix that distinguishes path in group."""
    parent_parts = [_safe_suffix_component(part) for part in path.parent.parts]
    other_parts = [
        [_safe_suffix_component(part) for part in other.parent.parts]
        for other in group
        if other != path
    ]
    for count in range(1, len(parent_parts) + 1):
        candidate = tuple(part.casefold() for part in parent_parts[-count:])
        if all(tuple(part.casefold() for part in parts[-count:]) != candidate for parts in other_parts):
            return "__".join(parent_parts[-count:])
    return "__".join(parent_parts)


def plan_flat_copy_names(files: Iterable[Path | str]) -> dict[Path, str]:
    """Plan unique flat destination names while preserving every source file.

    Unique filenames stay unchanged. If several source files share a filename,
    a shallower unique original keeps the plain filename (typical original +
    cont + cont2 layout), while continuation/collision files get the shortest
    unique parent-folder suffix, e.g. ``name__cont.mpr``.
    """
    resolved = sorted({Path(raw).resolve() for raw in files}, key=lambda p: str(p).casefold())
    by_name: dict[str, list[Path]] = {}
    for path in resolved:
        by_name.setdefault(path.name.casefold(), []).append(path)

    plan: dict[Path, str] = {}
    used: set[str] = set()

    # Reserve real filenames first: a generated suffix must never steal one.
    reserved = {p.name.casefold() for p in resolved}
    for group in by_name.values():
        group = sorted(group, key=lambda p: (len(p.parts), str(p).casefold()))
        depths = [len(p.parts) for p in group]
        minimum = min(depths)
        minimum_paths = [p for p in group if len(p.parts) == minimum]
        plain_path = minimum_paths[0] if len(minimum_paths) == 1 else None

        for path in group:
            continuation = bool(re.fullmatch(r"cont(?:\s*\d+)?", path.parent.name, flags=re.I))
            if not continuation and (len(group) == 1 or path == plain_path):
                candidate = path.name
            else:
                suffix = _shortest_unique_folder_suffix(path, group)
                candidate = f"{path.stem}__{suffix}{path.suffix}"

            base_candidate = candidate
            serial = 2
            while candidate.casefold() in used or (
                candidate.casefold() in reserved and candidate.casefold() != path.name.casefold()
            ):
                candidate = f"{Path(base_candidate).stem}__{serial}{Path(base_candidate).suffix}"
                serial += 1
            plan[path] = candidate
            used.add(candidate.casefold())

    return plan


def copy_files_flat(
    files: Iterable[Path | str],
    destination: Path | str,
    *,
    overwrite: bool = False,
    name_plan: Mapping[Path, str] | None = None,
) -> CopyResult:
    """Copy files into one flat destination; source files are never moved or deleted."""
    destination = Path(destination).expanduser().resolve()
    sources = list(dict.fromkeys(Path(raw).resolve() for raw in files))
    if name_plan is None:
        name_plan = plan_flat_copy_names(sources)

    copied = 0
    skipped = 0
    failures: list[str] = []

    # Validate the complete plan before writing anything.
    names = [name_plan.get(src, src.name) for src in sources]
    invalid = any(
        not isinstance(name, str) or not name or name in ('.', '..')
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name.endswith((' ', '.')) or Path(name).suffix.lower() != '.mpr'
        for name in names
    )
    if invalid or len({n.casefold() for n in names}) != len(names):
        return CopyResult(0, 0, len(sources), ('Invalid or duplicate destination filenames; nothing copied.',))
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CopyResult(0, 0, len(sources), (f'Cannot create destination: {exc}',))

    source_set = set(sources)

    for src in sources:
        dst = destination / name_plan.get(src, src.name)
        temporary = None
        try:
            if dst.is_symlink() or dst.resolve() in source_set:
                raise ValueError('Destination would overwrite a source file or symbolic link')
            if dst.exists() and not overwrite:
                skipped += 1
                continue
            # Stage the full file beside its destination before publishing it.
            # An interrupted copy leaves an existing destination untouched.
            fd, temporary_name = tempfile.mkstemp(prefix='.mpr-copy-', suffix='.tmp', dir=destination)
            os.close(fd)
            temporary = Path(temporary_name)
            shutil.copy2(src, temporary)
            if overwrite:
                os.replace(temporary, dst)
            else:
                # Atomic, exclusive publication: never overwrite a file that
                # appeared since the existence check. Windows rename refuses
                # existing targets; POSIX link provides the same guarantee.
                try:
                    if os.name == 'nt':
                        os.rename(temporary, dst)
                    else:
                        os.link(temporary, dst)
                except FileExistsError:
                    skipped += 1
                    continue
            copied += 1
        except Exception as exc:
            failures.append(f"{src}: {exc}")
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    return CopyResult(copied=copied, skipped_existing=skipped, failed=len(failures), failures=tuple(failures))


def local_program_data_dir(program_dir: Path | str) -> Path:
    """Create and return the collector's portable data folder next to the app."""
    base = Path(program_dir).expanduser().resolve()
    path = base / "MPR_Collector_Data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_app_settings(
    settings_path: Path | str,
    root_folder: Path | str,
    destination_folder: Path | str,
    color_scheme: str,
    *,
    remember_paths: bool = True,
    layout: dict | None = None,
) -> None:
    """Persist folder paths and appearance settings to one local JSON file."""
    path = Path(settings_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "root_folder": str(root_folder) if remember_paths else "",
        "destination_folder": str(destination_folder) if remember_paths else "",
        "color_scheme": str(color_scheme),
        "remember_paths": remember_paths,
        "layout": layout or {},
    }
    write_json_atomic(path, data)


def load_app_settings(settings_path: Path | str) -> dict:
    """Load app settings, returning empty strings when unavailable/corrupt."""
    path = Path(settings_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings must be a JSON object")
        return {
            "root_folder": str(data.get("root_folder", "")),
            "destination_folder": str(data.get("destination_folder", "")),
            "color_scheme": str(data.get("color_scheme", "")),
            "remember_paths": data.get("remember_paths", True) is not False,
            "layout": data.get("layout", {}) if isinstance(data.get("layout"), dict) else {},
        }
    except Exception:
        return {"root_folder": "", "destination_folder": "", "color_scheme": ""}


def write_json_atomic(path: Path, data: object) -> None:
    """Preserve the previous settings if writing the new version fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
