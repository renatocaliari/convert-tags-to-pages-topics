# convert-tags-to-pages-topics

Convert `#tags` to `[[Topics/tag]]` wiki-links in markdown vaults.

Works with **Obsidian, Capacities, Octarine, Tolaria, Logseq**, or any markdown-based notes app.

## Problem

Your vault has tags like `#LLM`, `#AI`, `#Health/Sleep` across hundreds of files.
You want to migrate to wiki-link organization where each tag maps to a page under
a `Topics/` directory. Doing this manually is error-prone.

This script automates the entire migration:

- Scans all `.md` files for `#tags`
- Replaces them with `[[Topics/tag]]` wiki-links
- Extracts tags from YAML frontmatter `tags: [Tag1, Tag2]` and injects as links
- Creates stub Topic pages (optional, with optional `type:` frontmatter)
- Handles glued tags (`#Tag1#Tag2`), hierarchical tags (`#A/B/C`), Unicode
- Skips URL fragments, code blocks, and markdown headings
- Resume, dry-run, batch mode — safe for large vaults

---

## Quickstart

```bash
# 1. Generate whitelist (scans vault, outputs all #patterns found)
python3 migrate-tags.py --dir ~/my-vault --generate-whitelist

# 2. EDIT the whitelist file
#    tag-whitelist.txt — remove lines that aren't real tags.
#    Only tags in this list will be converted.

# 3. Preview (dry-run — no files are modified)
python3 migrate-tags.py --dir ~/my-vault --dry-run

# 4. Execute migration
python3 migrate-tags.py --dir ~/my-vault
```

---

## All Options

### `--dir PATH`
Vault root directory. Default: `.` (current directory).

### `--dry-run`
Preview changes without writing anything. Shows how many files would change.
No files are created or modified. Safe to run anytime.

### `--generate-whitelist`
Scans all `.md` files in the vault, collects every `#tag` pattern, filters out
obvious noise (numeric-only, single chars, URL fragments, base64 blobs), and
writes the result to `tag-whitelist.txt`.

**You MUST review this file before running the migration.** Delete any line
that isn't a real tag.

Default whitelist filters applied:
| Filter | Example excluded | Reason |
|---|---|---|
| Numeric-only | `#1`, `#2966` | URL fragments, timestamps |
| Single char | `#x`, `#a` | Noise |
| Max length (120 chars) | `#H4sIAAAA...` (base64) | URL params, blobs |
| URL context | `url/#fragment` | `https?://` detected before `#` |

### `--resume`
Continue from where the script last stopped. Uses `checkpoint.json` to find
the last processed file. Useful after interrupt or power loss.

### `--batch N`
Process N files, then pause. Useful with git:

```bash
python3 migrate-tags.py --dir ~/my-vault --batch 200
git add -A && git commit -m "batch 1/5: migrate tags"
python3 migrate-tags.py --dir ~/my-vault --resume
```

### `--links-only`
Skip creating Topic stub pages. Only convert `#tag` references in existing files.
Useful when you already have the Topic pages or want to handle them separately.

### `--topic-type TYPE`
Add YAML frontmatter with `type:` to each created Topic page.

```bash
python3 migrate-tags.py --dir ~/my-vault --topic-type Topic
```

Creates `Topics/LLM.md` as:
```yaml
---
type: Topic
---

# LLM
```

Also **patches existing** Topic pages that lack the `type:` field — scans
`Topics/` and adds the frontmatter to any file missing it.

**Default:** None (no frontmatter added to Topic pages).

### `--config FILE`
Path to YAML config file. Any CLI flag can also be set in the config file.
CLI flags override YAML values.

See [Config File](#config-file) below for all supported keys.

### `--help`
Show help message and exit.

---

## Config File

Create `migrate-tags.yaml` in your vault root:

```yaml
# Prefix for wiki-links (default: "Topics/")
link_prefix: "Topics/"

# Whitelist file path (relative to vault or absolute)
whitelist_file: tag-whitelist.txt

# Minimum occurrences to auto-include a tag (0 = manual review required)
whitelist_min_count: 0

# Save checkpoint.json for resume (default: true)
save_checkpoint: true

# Topic pages batch size (0 = all at once, N = pause every N files)
batch_size: 0

# Add type frontmatter to Topic pages (null = skip, "Topic" = enable for Tolaria/Octarine)
# topic_type: "Topic"

# Special rules: override replacement for specific tags
# Format: {tag: "TagName", replacement: "custom [[Link]] string"}
special_rules:
  - tag: "Contabilidade-Empresa"
    replacement: "[[Topics/Contabilidade-Empresa]] · [[Organizations/Cali Consultoria]]"
```

Run with:
```bash
python3 migrate-tags.py --dir ~/my-vault --config migrate-tags.yaml
```

---

## Special Rules

Some tags need custom replacements. For example, `#Company` should link to
`[[Topics/Company]]` AND `[[Organizations/MyCompany]]`:

```yaml
special_rules:
  - tag: "Company"
    replacement: "[[Topics/Company]] · [[Organizations/MyCompany]]"
  - tag: "Project"
    replacement: "[[Topics/Project]] · [[Projects/MyProject]]"
```

The `replacement` field supports any string — multiple wiki-links, text, or both.

---

## Topic Page Creation

By default, the script creates a stub `.md` file for each whitelisted tag under
`Topics/`:

```
#LLM        → Topics/LLM.md
#Health/Sleep → Topics/Health/Sleep.md
```

If `--topic-type Topic` is set (or `topic_type: "Topic"` in YAML), each page
includes frontmatter:

```yaml
---
type: Topic
---

# LLM
```

For **Tolaria** and **Octarine** users, this makes the pages appear as a
dedicated type with its own icon and sidebar section.

Existing pages that lack the type frontmatter are automatically patched on
subsequent runs. The script is idempotent — it never duplicates frontmatter.

To skip page creation entirely, use `--links-only`.

---

## How It Works

### Whitelist → Review → Execute

1. **Scan:** `--generate-whitelist` finds every `#pattern` across all `.md` files.
   URL fragments, base64 blobs, and numeric noise are auto-filtered.
2. **Review:** You edit `tag-whitelist.txt`, removing anything that isn't a tag.
3. **Dry-run:** `--dry-run` simulates replacements — no writes.
4. **Execute:** Script processes each file:
   - Skips YAML frontmatter (but extracts `tags:` for injection)
   - Skips code fences (```` ``` ```` blocks)
   - Skips URL fragments (anything after `https?://`)
   - Skips markdown headings (`## Heading`)
   - Replaces whitelisted `#tag` with `[[Topics/tag]]`
   - Handles glued tags: `#Tag1#Tag2` → `[[Topics/Tag1]][[Topics/Tag2]]`
   - Handles hierarchies: `#A/B/C` → `[[Topics/A/B/C]]`
   - Handles Unicode: `#SãoLourenço`, `#Córdoba`
5. **Topic pages:** Creates `Topics/*.md` stubs (skip with `--links-only`).
6. **Checkpoint:** Saves progress after every file for resume.

### What is skipped

| Context | Reason |
|---|---|
| YAML frontmatter (`---...---`) | Metadata, not content |
| Code fences (` ``` `) | Code, not tags |
| URL fragments (`url#section`) | Not a tag |
| Markdown headings (`##`) | Not a tag |
| Non-whitelisted patterns | User explicitly removed them |

---

## Safety

- **Idempotent:** Running twice produces zero extra changes.
- **Dry-run:** Preview every change before writing.
- **Checkpoint:** Interrupt-safe — resume from where you stopped.
- **Git-friendly:** Use `--batch` to commit in groups.
- **URL-safe:** URL fragments like `url#section` are never touched.
- **Recoverable:** `git checkout .` undoes everything if you used a branch.

---

## Full CLI Reference

```
usage: migrate-tags.py [-h] [--dir DIR] [--config CONFIG] [--dry-run]
                       [--resume] [--generate-whitelist] [--batch BATCH]
                       [--links-only] [--topic-type TOPIC_TYPE]

Convert #tags to [[Topics/tag]] wiki-links

options:
  --dir DIR             Vault root directory (default: .)
  --config CONFIG       YAML config file
  --dry-run             Preview only — no files written
  --resume              Continue from last checkpoint
  --generate-whitelist  Scan vault and generate whitelist for review
  --batch BATCH         Process N files then pause
  --links-only          Skip creating Topic pages
  --topic-type TYPE     Add type frontmatter (e.g. "Topic")
  -h, --help            Show this message
```

## Dependencies

- **Python 3.10+** (built-in modules only for core functionality)
- **PyYAML** (optional, for `--config` support): `pip install pyyaml`
