MPR Collector local data
========================

Created on this computer when needed:
- settings.json: appearance, layout, and optionally remembered folder paths
- presets.json: saved mother folder and folder selections relative to it;
  older presets may contain absolute folder paths

These files are plain text. To transfer presets to another computer, copy
presets.json to this folder in the other installation. If the saved mother
folder is unavailable there, choose a mother folder before loading. An
explicitly chosen folder takes precedence even if the preset's saved root
exists; a folder restored automatically at startup does not override an
available saved root. The loader tries relative paths, then a unique
trailing-folder match beneath the selected root. Older list-only presets can
also match trailing folders under the current mother folder when their old
absolute paths are unavailable. Missing or ambiguous matches leave the
current selection unchanged and show a warning.
Do not include these files when sharing a clean program distribution.
Unchecking Remember folder paths clears those paths from settings; it does not
remove paths deliberately saved in presets. A sync service such as OneDrive
may sync this folder independently of MPR Collector.
