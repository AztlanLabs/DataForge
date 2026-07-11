# UI/UX Review & Redesign Proposal

**Date:** 2026-07-10
**Reviewer role:** Product / UX designer with front-end engineering background
**Surface reviewed:** the PyQt5 desktop app (`filemanager/ui/`) — shell, navigation, views, settings, dialogs — plus the naming/labelling used across CLI and GUI.
**Goal:** make the app easier to understand and safer to use for a *non-expert end user*, without dumbing it down for power users.

> **One-line assessment:** the app is *feature-rich and visually competent* (clean light/dark theme, grouped sidebar, consistent preview→confirm pattern), but it is organised around **the developer's module boundaries, not the user's tasks**, and several core interactions (choosing a path, saving settings, "Experience Level" gating) fight the user's mental model. The biggest wins are in **information architecture, naming, and interaction consistency** — not visual polish.

---

## 1. What's already good (keep it)

- **Grouped, colour-coded left rail** with collapsible sections — a sound structure for this many features.
- **Consistent safety pattern:** dry-run preview → confirmation dialog → execute, with a persistent bottom status bar (spinner + progress + a red **STOP** button). This is genuinely good and should be the app's signature.
- **Cohesive theming:** the light/dark palettes and stylesheets in `ui/app.py` are carefully built (even the checkbox/spinbox glyphs are theme-aware SVGs). Applied at `QApplication` level so dialogs match.
- **Tooltips everywhere** via `attach_tooltips`, with genuinely helpful copy in Settings.
- **Titles are human**, mostly ("Duplicate Finder", "System Cleanup", "File Recovery").

The problems below are about *coherence and task-fit*, not competence.

---

## 2. Information Architecture — organise around tasks, not modules

### 2.1 The current sidebar mixes altitudes and audiences
Current groups (`ui/app.py:875`):

```
Overview            → Dashboard
File Utilities      → Search & Organize, Duplicate Finder, Media Tools, Action Builder, Tools & Workflows
System Maintenance  → System Cleanup, Performance, File Recovery
Advanced Analysis   → Metadata Studio, Hardware Diagnostics, Forensics Lab
Application         → Settings, About & Help
```

Issues:
- **"Tools & Workflows" vs "Action Builder"** — both sound like "the place where you build/run multi-step things." Users won't know which to open. (There are *three* renamer entry points across these — see the code review's "multiple orchestration patterns".)
- **"Media Tools" sits under File Utilities**, but "Metadata Studio" (also media-centric) sits under Advanced Analysis. Same user, same files, two different groups.
- **"Hardware Diagnostics" and "Performance"** are split across two groups though users think of them as one question: *"how is my machine doing?"*
- **`fm devices` has no GUI at all** — a capability that exists only in the CLI is invisible to GUI users.

### 2.2 Proposed grouping (task-oriented)

| Group | Views | Rationale |
| --- | --- | --- |
| **Home** | Dashboard | Single landing/overview. |
| **Find & Organize** | Search, Duplicates, Organize/Rename, Media, Metadata | Everything about *your files*: find them, de-dupe, tidy, convert, inspect. Fold "Action Builder" + "Tools & Workflows" into one **"Automations"** entry here. |
| **Clean & Optimize** | System Cleanup, Storage & Devices *(new: surfaces `fm devices`)*, Performance | Reclaim space + machine health, together. |
| **Recover & Investigate** | File Recovery, Forensics, Integrity/Hashing | The "something went wrong / prove what happened" tasks. Give Integrity its own visible entry (today it's CLI + buried). |
| **System** | Hardware, Settings, About & Help | Read-only machine info + app config. |

This reduces the "which of these two similar-sounding tools?" ambiguity and puts related jobs next to each other.

---

## 3. Naming & labelling — say what it does, drop the theatre

"Studio", "Lab", "V3" are *marketing textures* that reduce clarity. The project already removed "Action Builder V3" and the fake "Version 3.0.0" — continue that discipline.

| Current label | Problem | Suggested label |
| --- | --- | --- |
| **Metadata Studio** | "Studio" adds nothing; users search for "metadata" / "EXIF" / "remove location". | **Metadata & EXIF** |
| **Forensics Lab** | "Lab" is theatre; scares non-experts, over-promises to experts. | **Forensics** (or **Investigate**) |
| **Tools & Workflows** + **Action Builder** | Two names for "do multi-step operations". | Merge → **Automations** (with sub-tabs "Quick tools" / "Pipeline builder"). |
| **Search & Organize** | Bundles two distinct jobs in one label. | **Search** (with an "Organize matches" action inside it) |
| **Hardware Diagnostics** | "Diagnostics" implies it fixes things; it reports. | **Hardware Info** |
| **System Cleanup** | Fine, but clarify scope. | **Clean Up Space** |
| **Experience Level: Basic/Advanced/Expert** | Sounds like a skill judgement; hides features (see §5). | **Detail level: Simple / Standard / Everything** |
| Sidebar title **"File Manager"** / window **"File Manager Utils"** / package **"filemanager-utils"** | Three different product names. | Pick one product name and use it consistently. |

**Microcopy:** prefer verbs and outcomes. "Strip GPS" → "Remove location data". "Carve files from image" → "Recover files from a disk image (advanced)". "Hash-calc" → "Verify file fingerprint (hash)".

---

## 4. Interaction problems (highest user-friction, ranked)

### 4.1 🔴 The file-vs-folder picker is an anti-pattern
`BaseView.choose_file_or_directory` (`views/base.py:244-262`) pops a **Yes/No/Cancel** `QMessageBox` reading *"Select a file? Choose Yes for a file, No for a folder, or Cancel…"*, then opens the real dialog. Users must answer a riddle before they can browse.
- **Fix:** use a native dialog that allows both, or place two explicit buttons in the view ("Choose File…", "Choose Folder…"). Never overload Yes/No to mean file/folder.

### 4.2 🔴 Settings persistence is inconsistent (some autosave, some need a button)
In `views/settings.py`, **Theme, Path Display, and Duplicate keep-strategy autosave on change**, but **Performance, Exclusions, and Dashboard require an explicit "Save" button** — and each tab has its *own* differently-coloured save button (`#5cb85c` green, `#5bc0de` blue, `#d9534f` red). Users can't predict whether a change stuck, and unsaved edits are silently lost on tab switch.
- **Fix:** pick **one** model. Recommended: autosave everything with a small, consistent "Saved ✓" affordance, or a single global "Save changes" bar that appears only when there are unsaved edits. Remove the per-button ad-hoc colours.

### 4.3 🟠 "Experience Level" *hides* features → discoverability cliff
The tier system (`ui/app.py:673`, `views/settings.py:289`) removes whole sidebar groups (System Maintenance, Advanced Analysis) and settings widgets at lower tiers. A "Basic" user literally **cannot see** Cleanup, Recovery, Performance, Forensics, or Hardware, and there is no hint they exist or how to unlock them.
- **Fix:** default to showing everything but **progressively disclose complexity *within* a view** (advanced options behind a "More options" expander), rather than deleting navigation. If you keep tiers, add a persistent "Showing simplified view — [Show all features]" banner so the cliff is discoverable.

### 4.4 🟠 Two controls for one setting (dark mode)
Dark mode is a **checkbox in the sidebar** *and* a **Theme dropdown in Settings** — both write `config["theme"]`. Redundant controls invite "I changed it and it didn't change" confusion.
- **Fix:** one control. Keep the quick sidebar toggle; in Settings show the *same* toggle state (or a link "Theme is set in the sidebar"). Consider a third "Follow system" option.

### 4.5 🟠 Help is a wall of plain text
`BaseView.show_help` dumps `get_help_text()` into a read-only `QTextEdit` as **plain text** (`setPlainText`), so any markdown in the help renders as literal `#`/`*`. Help is also disconnected from context (no per-field help, no "what will this do?").
- **Fix:** render help as rich text/markdown; add first-run coach marks or an inline "What's this?" on destructive actions.

### 4.6 🟠 Destructive actions rely on a text summary, not a reviewable list
`build_preview_message` truncates to 8 lines ("… and N more") inside a `QMessageBox`. For "delete 4,000 junk files" or "move 900 duplicates", a one-paragraph message box is not enough to build trust.
- **Fix:** show a **scrollable, checkable table** of exactly what will change (with per-row opt-out), a clear space-reclaimed/affected count, and make **Cancel the default button** on destructive dialogs (it currently is `No`, good — keep that). Colour the confirm button as destructive (red) only on delete.

### 4.7 🟠 One global "busy" lock with a vague message
`run_background` sets `is_busy` and rejects new work with *"Busy: please wait for the current operation to finish."* — but the user can't see *what* is running or how long it'll take beyond the spinner.
- **Fix:** name the running task in the status bar ("Hashing 1,203 files… STOP"), and either queue or clearly disable the controls that would start conflicting work.

---

## 5. Visual & consistency issues

- **Two colour systems coexist.** `ui/app.py` uses a modern Tailwind-ish palette (`#ef4444`, `#3b82f6`, `#6366f1`); `views/settings.py` hardcodes old Bootstrap colours inline (`#d9534f`, `#5cb85c`, `#5bc0de`). Consolidate into named semantic tokens (`--danger`, `--success`, `--info`) applied via the stylesheet, not per-widget `setStyleSheet`.
- **No iconography in the sidebar.** Icons were deliberately removed. For 14+ destinations, a small leading icon per item dramatically improves scan-ability and recognition. Re-introduce a minimal, monochrome icon set (they can tint with the theme).
- **Group-header colour coding** is nice but currently the *only* affordance distinguishing groups; pair it with spacing/weight so it survives for colour-blind users.
- **Status/percentage text** (`"{step}: {current}/{total} ({pct}%)"`) is functional but dense; consider a cleaner "Hashing files — 42%" with the counts as secondary text.

---

## 6. Accessibility (currently unaddressed)

| Area | Gap | Fix |
| --- | --- | --- |
| **Contrast** | Muted greys (`#4b5563` on `#ffffff`, `#94a3b8` on dark) are borderline for small text vs WCAG AA. | Verify all text meets ≥4.5:1; bump muted tones. |
| **Keyboard** | No visible focus ring styling; nav is mouse-first; no documented shortcuts. | Add `:focus` outlines, tab order, and accelerators (Alt+key) for primary actions. |
| **Screen readers** | Icon-only future buttons and the spinner need accessible names; status changes aren't announced. | Set `setAccessibleName`/`setAccessibleDescription`; use an ARIA-live-equivalent status update. |
| **Colour-only meaning** | Group identity and success/danger conveyed by colour alone. | Add text/iconography as a second channel. |
| **Motion** | Continuous spinner + theme animation. | Respect a "reduce motion" preference. |

---

## 7. Content & empty/error states

- **Empty states are generic.** "No matching items were available for this action." Give each view a purposeful empty state: what it does, an example, and a primary action (e.g. Recovery: "No trashed files found. [Scan a removable drive]").
- **Errors surface as raw exception text** in a `QMessageBox` (`show_workflow_error` → `str(error)`). Translate common failures ("Permission denied", "Not enough disk space" — the disk-space check already produces a friendly message; route more errors through that style).
- **Windows features that silently no-op** (Recycle Bin scan returns empty) should say "Not supported on this platform yet," not present an empty success.

---

## 8. Concrete, low-effort quick wins (do these first)

1. Replace the **Yes/No/Cancel file-vs-folder** riddle with two explicit buttons (§4.1).
2. Make **settings persistence uniform** and drop the three ad-hoc save-button colours (§4.2).
3. **Merge "Tools & Workflows" + "Action Builder"** into one "Automations" destination (§2, §3).
4. **Surface `fm devices`** as a "Storage & Devices" view so GUI users see it (§2).
5. **De-duplicate the dark-mode control** (§4.4).
6. **Render help as rich text** and add "What's this?" on delete/cleanup (§4.5).
7. Rename **Studio/Lab/Diagnostics** to plain descriptors; settle on **one product name** (§3).
8. Turn the **destructive preview** into a scrollable checklist with a space-reclaimed total (§4.6).

## 9. Suggested longer-term direction

- **A task-first launcher on the Dashboard:** big buttons for the top 5 jobs ("Free up space", "Find duplicates", "Recover a file", "Remove photo location data", "Check a download's hash") that deep-link into the right view pre-configured. Most users arrive with a *task*, not a *tool*, in mind.
- **Progressive disclosure instead of tiers:** one UI, with "Advanced" expanders, so nothing is hidden from navigation but nothing overwhelms by default.
- **A unified "review changes" component** reused by every destructive/batch operation, so trust is built the same way everywhere.
- **Iconography + a single design-token layer** so future views inherit consistency for free.

---

### Appendix — mapping of proposed renames (for implementers)

| File / symbol | Current user-facing string | Proposed |
| --- | --- | --- |
| `views/metadata_view.py` `get_title()` | "Metadata Studio" | "Metadata & EXIF" |
| `views/forensics_view.py` `get_title()` | "Forensics Lab" | "Forensics" |
| `views/hardware_view.py` `get_title()` | "Hardware Diagnostics" | "Hardware Info" |
| `views/tools.py` + `views/action_builder.py` | "Tools & Workflows" / "Action Builder" | "Automations" (tabs inside) |
| `views/search.py` | "Search & Organize" | "Search" |
| `ui/app.py` window/title, `setup.py` name | "File Manager Utils" / "filemanager-utils" | one chosen product name |

None of these require behavioural change — they're label/IA edits, so they're safe to ship incrementally while the deeper interaction fixes (§4) are scheduled.
