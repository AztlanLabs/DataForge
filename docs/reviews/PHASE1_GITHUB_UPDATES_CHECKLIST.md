# Phase 1: GitHub Branding Updates — Quick Checklist

**Status:** Ready to implement immediately  
**Estimated time:** 30 minutes  
**Impact:** Professional, distinctive brand presence  

---

## 🎯 What to Do Right Now

### 1. Update GitHub Repository Settings (10 min)

**Go to:** Settings → General

- [ ] **Repository name:** Keep as "FileManager" (or change if you control the repo)
  - *Note: repo name stays; we're updating the presentation*

**Go to:** Settings → General → Repository details

- [ ] **Description:** Change from:
  ```
  A Python file-management toolkit
  ```
  To:
  ```
  Professional file and system intelligence platform with unified CLI + desktop interface. Discover, organize, recover, and analyze files with power-user tools for cleanup, forensics, and automation.
  ```

### 2. Update Repository Topics (5 min)

**Go to:** About → Topics (or Settings → General → Topics)

**Remove:** (if present)
- `filemanager`
- `file-management` (if too generic)

**Add these topics:**
- `file-management`
- `forensics`
- `data-discovery`
- `cli`
- `gui`
- `automation`
- `pyqt5`
- `python`
- `duplicate-finder`
- `system-tools`

**Result:** People searching for "forensics python" or "file carving" will find this.

### 3. Update README.md (5 min)

- [ ] Verify README.md is updated (already done ✅)
- [ ] Check that the title shows **DataForge** (not FileManager)
- [ ] Verify "Why DataForge?" table is visible
- [ ] Check that feature sections are organized (🧹 Cleanup, 🔍 Discovery, etc.)
- [ ] Confirm "Common Use Cases" table is present

### 4. Update GUI Application (5 min)

**File:** `filemanager/ui/app.py` (or relevant About view file)

Find the About dialog and change:

**From:**
```python
title = "FileManager"
version_text = "Version 3.0.0-production"  # or similar
```

**To:**
```python
title = "DataForge"
version_text = "Development build (pre-release, v0.1.0)"
```

Also update any Help text that refers to "FileManager" → "DataForge"

### 5. Update setup.py (5 min)

**File:** `setup.py`

Find the `setup()` call and update:

**From:**
```python
name='filemanager-utils',
description='A Python file-management toolkit',
```

**To:**
```python
name='dataforge',  # or 'dataforge-tools'
description='Professional file and system intelligence platform with unified CLI + desktop interface',
```

### 6. Pin Updated README (5 min)

**Go to:** Repository home → README section

- [ ] Verify the updated README displays correctly
- [ ] Check that all links work (esp. to docs/reviews/)
- [ ] Confirm emoji render correctly in your browser
- [ ] Optionally: add a 1-line note at the very top if this is the first update visibility

---

## ✅ Verification Checklist

After making changes, verify:

- [ ] GitHub repo description shows professional messaging
- [ ] Topics include "forensics", "data-discovery", "automation"
- [ ] README displays with DataForge title and new layout
- [ ] "Why DataForge?" table is visible and formatted
- [ ] "Common Use Cases" section appears with 9 personas
- [ ] Links to docs/reviews/ work
- [ ] GUI About dialog shows "DataForge" (if you updated it)

---

## 🚀 Next: Phase 2 & 3 (Preview)

Once Phase 1 is complete:

**Phase 2 (optional, can defer):** Rename package `filemanager/` → `dataforge/`  
**Phase 3 (recommended next):** Initialize git + CI/CD + release to PyPI

See `05_PRODUCT_NAMING_AND_NEXT_STEPS.md` for full roadmap.

---

## 📋 Copy-Paste Snippets

### GitHub Description (ready to paste)

```
🔨 DataForge — File System Management with Steroids and Superpowers

Professional file and system intelligence platform with unified CLI + desktop interface. Enterprise-grade duplicate detection, forensic carving, integrity verification, automated cleanup, media batch processing, hardware diagnostics, artifact parsing, and workflow automation — all battle-tested in production.

Includes: 224+ passing tests, parallel hashing, batch operations at scale, drag-reorder pipeline builder, forensic file recovery, metadata stripping, system performance monitoring, and extensible plugin architecture.
```

### Repository Topics (ready to copy)

```
file-management, forensics, data-discovery, cli, gui, automation, pyqt5, python, duplicate-finder, system-tools, file-carving, integrity-verification, batch-operations
```

### setup.py description

```python
description='File system management with steroids and superpowers — enterprise-grade duplicate detection, forensics, recovery, and automation'
```

### About Dialog (GUI)

```python
title = "DataForge"
tagline = "File System Management with Steroids and Superpowers"
version = "v0.1.0 (Development build)"
```

---

## Questions?

- **Should I keep the repo named "FileManager"?** Yes, for now. The product name is DataForge, but keeping the repo name avoids breaking existing links. Consider renaming after wider adoption.
- **Do I need to update the Python package name now?** No, that's Phase 2 (optional, can defer 1-2 weeks). Focus on GitHub visibility first.
- **What if I don't control the GitHub repo?** Ask the repo owner to make these changes, or create a fork with your own branding.

---

**Time to complete:** ~30 minutes  
**Effort level:** Low (copy-paste)  
**Impact:** High (professional brand presence, better discoverability)  

✅ **Ready? Start with GitHub Settings → General → Description**
