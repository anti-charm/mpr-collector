# Changelog

## Unreleased

- Saved presets use folder rules relative to the mother folder. An explicitly chosen current mother folder takes precedence over the saved root, even if that root exists; an automatically restored folder does not. The loader tries the exact relative path, then a unique trailing-folder match. Missing or ambiguous matches warn without changing the current selection.
- Older presets with a saved root can be rebased. The oldest list-only presets can also rebase under a current mother folder by unique trailing-folder matching when their old absolute paths are unavailable.
- Added a clickable Size column after Modified, with numeric sorting and readable decimal file-size units.
- Shortened Source folder entries to the final two folder names; full paths remain available in file details.
- Enabled Replace existing files by default while keeping its checkbox and copy confirmation.
- Removed the tagline beneath the app title.

## v1.0.0 — 2026-09-12

### Appearance and review update

- Eleven more distinct appearances, including dark red, blue, teal, and violet.
- Independent resizable Review & Copy window with search, sortable headings, and full file details.
- Double-click column dividers to fit content, with a width cap for long paths.
- Explicit Name change information replaces unexplained yellow highlighting.
- Checkbox-only folder toggles; single-click names to focus and double-click to expand.
- Clearer selection legend and compact layout with visible preset controls.
- Regression coverage for selection, review independence, themes, column fitting, and layout reset.


### Workspace and safety update

- Lab Slate appearance and numbered workflow sections.
- Draggable dividers, remembered window/column sizes, and reset layout.
- Scrollable paths and previewed copy/skip/replace actions.
- Include/Exclude buttons, keyboard toggling, selectable mother folder.
- Background scanning/copying and activity indicator.
- Optional remembered paths, separate from saved layout and presets.
- Globally unique destination names and consistent continuation suffixes.
- Staged copies, selected-source protection, and validated copy plans.
- Visible scan errors and stale-scan invalidation for invalid edited roots.
- Restored Git ignore rules, clearer launcher, regression tests, and privacy documentation.
