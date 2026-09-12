MPR Collector
=============

Purpose
-------
Collect raw BioLogic .mpr files from selected experiment branches into one flat destination folder.
Source files are COPIED only. They are never moved, renamed, or deleted.

Windows use
-----------
1. Keep all files from this ZIP together in one folder.
2. Install Python 3 if needed.
3. Double-click Run_MPR_Collector.bat.
4. Choose the mother folder (for example, Experiments containing Instrument-A, Instrument-B, ...).
5. Choose the destination folder.
6. Single-click any folder in the tree to include that folder and EVERY nested subfolder below it.
7. Expand the branch and double-click a specific child branch to exclude it if you do not want it.
8. You can reselect a deeper branch inside an excluded branch with a normal single-click.
9. Click "Scan selected folders".
10. Review the Source filename / Copied as columns.
11. Click "Copy MPR files".

The previous mother and destination folder paths are remembered automatically and restored next time.
The last selected color scheme is remembered too.

Hierarchical selection
----------------------
The folder tree uses three visual states:
  [checked]   included branch
  [partial]   included branch with one or more excluded descendants
  [unchecked] not included

A parent selection applies to all descendants, no matter how deeply nested they are.
You do NOT need to select every subfolder individually.

Large "Expand focused" and "Collapse focused" buttons are provided so you do not have to rely on the small
native Windows disclosure arrow.

Recursive scanning
------------------
Scanning follows the selection rules to arbitrary depth.  Deeply buried experiment/cell/continuation folders
are included automatically unless their branch was explicitly excluded.

Continuation files and repeated filenames
-----------------------------------------
The collector preserves ALL source files, including continuation folders such as cont and cont2.
If different source files have the same filename, copied destination names are made unique.
Typical example:

  cell 12\same.mpr        -> same.mpr
  cell 12\cont\same.mpr  -> same__cont.mpr
  cell 12\cont2\same.mpr -> same__cont2.mpr

Continuation folders keep their suffix even if scanned separately later, so updating the destination remains stable.
If a short folder suffix is still not unique, additional parent-folder names are included automatically.
The original source filenames are never changed.

Destination files already present
---------------------------------
By default, a destination file with the same planned filename is skipped.

If "Replace same-named files already in destination" is enabled, ONLY those individual same-named files are
replaced.  The destination folder itself is never replaced or cleared, and unrelated files already there remain
untouched.

Portable saved data
-------------------
Presets and settings are stored beside the program in:

  MPR_Collector_Data\presets.json
  MPR_Collector_Data\settings.json

Nothing is read from or migrated from %APPDATA%.  Keep the MPR_Collector_Data folder with the collector if you
move the program and want to keep your presets, remembered paths, and selected color scheme.

Privacy
-------
This repository contains no experiment files, saved presets, or saved folder paths. The program creates
settings.json and presets.json only on the user's own computer. Both files, along with all .mpr files, are
excluded from Git by .gitignore.

Color schemes
-------------
Use the "Color scheme" drop-down at the top of the window.  Six restrained schemes are included:
  - Warm Clay
  - Sage & Linen
  - Slate & Sky
  - Sand & Teal
  - Rosewood & Cream
  - Graphite & Amber

Each scheme keeps the same interface and uses layered surfaces plus a subtle three-stop header gradient rather
than changing the program into a single flat color.

Selection summary and presets
-----------------------------
The right panel shows compact paths beginning at the mother-folder name, for example:
  Experiments\Instrument-A\Project-A\Condition-1
It also shows explicit exclusions.

Selections can be saved as presets, including parent selections and excluded branches.
Old presets from earlier versions are still accepted as simple included-folder lists.

Notes
-----
- Only .mpr files are collected (case-insensitive: .mpr / .MPR).
- Overlapping selected branches are deduplicated by exact source path.
- The destination remains flat; the source folder hierarchy is not recreated.
- The interface uses restrained professional palettes, subtle gradients, and larger controls while remaining a
  lightweight Windows Python utility.
