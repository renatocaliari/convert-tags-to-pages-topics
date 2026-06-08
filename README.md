# convert-tags-to-pages-topics

Convert `#tags` to `[[Topics/tag]]` wiki-links in markdown vaults (Obsidian, Logseq, etc).

## Problem

You have a markdown vault with tags like `#LLM`, `#AI`, `#Health/Sleep` scattered across
hundreds of files. You're migrating to a wiki-link based organization where each tag
maps to a page under a `Topics/` directory. Doing this manually is error-prone.

This script automates the migration:

- Scans all `.md` files for `#tags`
- Replaces them with `[[Topics/tag]]` wiki-links
- Extracts tags from YAML frontmatter (`tags: [Tag1, Tag2]`) and injects as links
- Handles glued tags (`#Tag1#Tag2`), hierarchical tags (`#A/B/C`), Unicode
- Skips URL fragments, code blocks, and markdown headings

## Setup

```bash
pip install pyyaml  # optional — for YAML config support
```

## Usage

```bash
# 1. Generate whitelist (scans vault, outputs all #pattern found)
python3 migrate-tags.py --dir ~/my-vault --generate-whitelist

# 2. REVIEW the whitelist file
#    Edit tag-whitelist.txt — remove lines that aren't real tags.
#    Only tags in this list will be converted.

# 3. Preview changes (dry-run — no files are modified)
python3 migrate-tags.py --dir ~/my-vault --dry-run

# 4. Execute migration
python3 migrate-tags.py --dir ~/my-vault
```

## Special Rules

Some tags might need custom replacements — e.g. `#Company` should link to
both `[[Topics/Company]]` and `[[Organizations/MyCompany]]`.

Create a `migrate-tags.yaml`:

```yaml
special_rules:
  - tag: "Company"
    replacement: "[[Topics/Company]] · [[Organizations/MyCompany]]"
```

Then run with:

```bash
python3 migrate-tags.py --dir ~/my-vault --config migrate-tags.yaml
```

## Resume

Migration interrupted? No problem:

```bash
python3 migrate-tags.py --dir ~/my-vault --resume
```

The script saves a `checkpoint.json` after each file, so it picks up
exactly where it left off.

## Batch Mode (for git)

```bash
# Process 200 files, then pause for a git commit
python3 migrate-tags.py --dir ~/my-vault --batch 200
git add -A && git commit -m "batch 1: migrate tags"

# Resume for next batch
python3 migrate-tags.py --dir ~/my-vault --resume
```

## How It Works

1. **Whitelist generation:** scans all `#pattern` across `.md` files, filters
   noise (numeric-only tags, single chars), outputs a list for your review.
2. **Dry-run:** simulates replacements without writing anything.
3. **Execution:** processes each file, skipping:
   - YAML frontmatter (but extracts `tags:` field for injection)
   - Code fences (```` ``` ```` blocks)
   - URL fragments (`url#section`)
   - Markdown headings (`## Heading`)
4. **Checkpoint:** saves progress after every file for resume.

## Safety

- The script is **idempotent** — running it twice produces no extra changes.
- Use **git** before running: create a branch, review with `git diff`, merge if happy.
- Dry-run mode lets you preview before any writes.
