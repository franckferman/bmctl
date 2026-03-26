<div align="center">

# bmctl

**Firefox bookmark toolkit** - audit duplicates, compare exports, merge collections, and generate an interactive self-hosted dashboard from the command line.

[![Demo](https://img.shields.io/badge/demo-live-brightgreen?style=flat-square)](https://franckferman.github.io/bmctl/demo/)
[![Python Version](https://img.shields.io/badge/Python-3-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue?style=flat-square)](LICENSE)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Getting Started](#getting-started)
- [Commands](#commands)
  - [audit](#audit)
  - [compare](#compare)
  - [merge](#merge)
  - [export](#export)
  - [dashboard](#dashboard)
- [URL Deduplication](#url-deduplication)
- [Firefox JSON Compatibility](#firefox-json-compatibility)
- [License](#license)

---

## Overview

bmctl is a single-file Python CLI for managing Firefox bookmark exports (`.json`). It parses the full folder hierarchy, preserves the original Firefox tree order, and provides five commands covering the full lifecycle of a bookmark collection.

No installation required beyond Python itself. No database, no daemon, no config file. One file, one command, one output.

---

## Features

| Command | What it does |
|---|---|
| `audit` | Duplicate detection, stats, folder tree visualization |
| `compare` | Diff two exports - added, removed, net delta |
| `merge` | Merge two collections into a Netscape HTML file with conflict resolution |
| `export` | Flat export to CSV, Excel, or Markdown |
| `dashboard` | Self-contained interactive HTML dashboard, no server required |

URL normalization across all commands: scheme, `www.`, trailing slash, and `utm_*` parameters are stripped before comparison. `http://www.github.com/` and `https://github.com` are treated as the same URL.

---

## Quick Start

```bash
# 1. Get the tool
git clone https://github.com/franckferman/bmctl.git
cd bmctl

# 2. Export your bookmarks from Firefox
#    Bookmarks > Show All Bookmarks > Import and Backup > Backup...
#    Save as bookmarks.json

# 3. Run your first audit
python3 bmctl.py audit -i bookmarks.json

# Generate an interactive dashboard
python3 bmctl.py dashboard -i bookmarks.json -o dashboard.html
# Open dashboard.html in your browser
```

**Comparing two exports:**

`compare` works on two separate Firefox exports taken at different points in time. Export once, wait (add/remove bookmarks), export again, then diff:

```bash
# First export saved as bookmarks-jan.json
# Second export saved as bookmarks-feb.json

python3 bmctl.py compare -o bookmarks-jan.json -n bookmarks-feb.json
```

**Merging two collections:**

Useful if you have bookmarks spread across two Firefox profiles or two machines. The merge takes the union of both collections. For each URL:

- If it appears in only one collection, it is kept as-is.
- If it appears in both collections in the **same folder**, the most recent version is kept and tags are merged.
- If it appears in both collections in **different folders** (conflict), you are prompted to choose which folder to keep - or use `--no-confirm` to automatically keep the most recent.

No entries are silently deleted. Every URL from both files ends up in the output.

```bash
python3 bmctl.py merge -b profile-a.json -n profile-b.json -o merged.html
# merged.html is a Netscape HTML file - import it in any browser via:
# Bookmarks > Show All Bookmarks > Import and Backup > Restore... (or Import HTML)
```

No install step required. `bmctl.py` is a single file - you can also just download it directly without cloning the full repo.

---

## Project Structure

```
bmctl.py
  BookmarkNode          Data model for a single bookmark
  UrlNormalizer         URL normalization / deduplication
  BookmarkDatabase      JSON parser + in-memory index
  BookmarkAuditor       Duplicate detection + reporting
  BookmarkComparator    Two-database diff
  BookmarkMerger        Merge + conflict resolution + HTML export
  BookmarkDashboardGen  Interactive HTML dashboard generator
  BookmarkExporter      CSV / Excel / Markdown export
```

`BookmarkDatabase` is the core - it walks the Firefox JSON tree recursively, assigns each bookmark its full folder path, and builds a URL index for deduplication. All five commands consume it.

---

## Installation

**Prerequisites:** Python 3

No pip install required for core functionality. `pandas` and `openpyxl` are only needed for `export --format xlsx`:

```bash
pip install -r requirements.txt
```

No other dependencies.

---

## Getting Started

Export your bookmarks from Firefox:

```
Bookmarks > Show All Bookmarks > Import and Backup > Backup...
```

Save as `.json`. This file is the input for all commands.

---

## Commands

### `audit`

Inspect a single export: duplicate detection, stats, and optional folder tree.

```bash
python bmctl.py audit -i bookmarks.json
```

```
======================================================================
                  GLOBAL AUDIT REPORT
======================================================================
 Total bookmarks found        : 3110
 Folders scanned              : 244
 Unique links                 : 3059
 Duplicates detected          : 51 (1.6%)
======================================================================

[!] Top 10 most duplicated links:
  - GitHub
    URL : https://github.com
    Found 3 times:
      * Folder: Dev
      * Folder: CTI, OSINT & SocMint > Code Search Engines
```

Use `--show-tree` to verify that your folder structure was parsed correctly before generating a dashboard:

```bash
python bmctl.py audit -i bookmarks.json --show-tree
```

```
  |   [   0]  Cybersecurity & CTI
    +-- [   5]  C2 Frameworks
    +-- [   7]  OSINT & Recon
    +-- [   5]  Exploitation
  |   [   0]  Development
    +-- [   4]  Python
    +-- [   4]  Go
  |   [   6]  Tools
  |   [   6]  Blogs & News
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-i / --input` | required | Firefox JSON export |
| `--top N` | `10` | Show top N most duplicated URLs |
| `--show-short` | off | Stats only, skip duplicate list |
| `--show-tree` | off | Print full folder hierarchy with bookmark counts |

---

### `compare`

Diff two exports. Shows what was added and removed between two snapshots of the same collection.

```bash
python bmctl.py compare -o bookmarks-old.json -n bookmarks-new.json
```

```
======================================================================
                  COMPARISON REPORT
======================================================================
 Unique bookmarks V1 (old)    : 2980
 Unique bookmarks V2 (new)    : 3059
 Net delta                    : +79
======================================================================
 [+] New bookmarks added      : 102
 [-] Old bookmarks removed    : 23
======================================================================

[+] PREVIEW OF NEW ENTRIES (Max 15):
  + HackTricks                     (Folder: Cybersecurity > Documentation & Articles)
    https://book.hacktricks.xyz
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-o / --old` | required | Old JSON export |
| `-n / --new` | required | New JSON export |
| `--show-full` | off | Show complete added/removed lists (no limit) |
| `--show-short` | off | Stats only, skip item lists |

---

### `merge`

Merge two bookmark collections into a single Netscape HTML file (importable by any browser). Detects URL conflicts (same URL in different folders) and resolves them.

```bash
python bmctl.py merge -b bookmarks-base.json -n bookmarks-new.json -o merged.html
```

Without `--no-confirm`, conflicts trigger an interactive prompt:

```
[?] FOLDER CONFLICT DETECTED FOR:
    - URL  : https://example.com
    - Title: Example Site
    In which folder(s) do you want to keep it?
      1) [Keep] -> Dev > Tools
      2) [Keep] -> Misc.
      3) Skip / Keep most recent version
    Your choice (1, 2...) :
```

Tags from all instances are merged onto the surviving node.

With automatic conflict resolution (keeps most recent):

```bash
python bmctl.py merge -b base.json -n new.json -o merged.html --no-confirm
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-b / --base` | required | Base JSON export |
| `-n / --new` | required | JSON to merge in |
| `-o / --output` | required | Output HTML file |
| `--no-confirm` | off | Auto-resolve conflicts silently (keeps most recent) |

---

### `export`

Export to a flat format. All formats include: Title, URL, Folder path, Tags, Date added.

```bash
# CSV
python bmctl.py export -i bookmarks.json --format csv -o bookmarks.csv

# Excel
python bmctl.py export -i bookmarks.json --format xlsx -o bookmarks.xlsx

# Markdown (organized by folder)
python bmctl.py export -i bookmarks.json --format md -o bookmarks.md
```

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-i / --input` | required | Firefox JSON export |
| `--format` | required | `csv`, `xlsx`, or `md` |
| `-o / --output` | required | Output file path |

---

### `dashboard`

Generate a fully self-contained single-file HTML dashboard. No server required - open directly in a browser.

```bash
python bmctl.py dashboard -i bookmarks.json -o dashboard.html
```

**Dashboard features:**
- Sidebar with full collapsible folder tree (Firefox order preserved)
- Three views: Dashboard (widget grid), Cards, Table
- Global search across title, URL and tags
- "Recent additions" quick view (last 50)
- Folder-aware widget titles (relative path in folder view, full path in global view)
- Pure black enterprise theme

**Flags:**

| Flag | Default | Description |
|---|---|---|
| `-i / --input` | required | Firefox JSON export |
| `-o / --output` | `dashboard.html` | Output HTML file |

> **WSL users:** use Linux paths to avoid backslash stripping.
> ```bash
> # Correct
> python bmctl.py dashboard -i /mnt/c/Users/you/Desktop/bookmarks.json \
>                           -o /mnt/c/Users/you/Desktop/dashboard.html
> # Wrong - bash strips backslashes without quotes
> python bmctl.py dashboard -i ... -o C:\Users\you\Desktop\dashboard.html
> ```

---

## URL Deduplication

bmctl normalizes URLs before comparing them to find true duplicates:

| Rule | Example |
|---|---|
| Scheme normalization | `http://` = `https://` |
| Strip `www.` prefix | `www.github.com` = `github.com` |
| Strip trailing slash | `github.com/` = `github.com` |
| Strip `utm_*` params | `?utm_source=...` removed |
| Query params preserved | `?q=foo` != `?q=bar` |

`http://www.github.com/` and `https://github.com` resolve to the same canonical URL.

---

## Firefox JSON Compatibility

bmctl handles both Firefox export formats:

| Format | Bookmark | Folder |
|---|---|---|
| Legacy | `typeCode: 1` | `typeCode: 2` |
| Modern | `type: "text/x-moz-place"` | `type: "text/x-moz-place-container"` |
| Fallback | presence of `uri` field | presence of `children` field |

---

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

Any use, modification, or distribution - including over a network - requires the full source code to remain open under the same license.
