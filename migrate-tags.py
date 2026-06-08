#!/usr/bin/env python3
"""migrate-tags.py — Convert #tags to [[Topics/tag]] wiki-links in markdown vaults.

Reusable across any Obsidian/Capacities/Octarine/Logseq markdown vault. Config via YAML or CLI flags.

Usage:
  # 1. Generate whitelist (scan vault for all #tag patterns)
  python3 migrate-tags.py --dir ~/vault --generate-whitelist

  # 2. Edit the whitelist file (remove non-tags, keep real ones)

  # 3. Preview changes
  python3 migrate-tags.py --dir ~/vault --dry-run

  # 4. Execute
  python3 migrate-tags.py --dir ~/vault

  # With custom config
  python3 migrate-tags.py --dir ~/vault --config ./migrate-tags.yaml

  # Resume after interrupt
  python3 migrate-tags.py --dir ~/vault --resume

  # Batch mode (for git commits between batches)
  python3 migrate-tags.py --dir ~/vault --batch 200
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


# Regex: #TagName not preceded by word char (avoids URL#fragments),
# not followed by / or word char (avoids partial matches).
# Uses \w (unicode-aware in Py3) for chars like ç, ã, é.
TAG_INLINE_RE = re.compile(r"(?<!\w)#([\w/-]+)(?!/[\w-])")

DEFAULT_CONFIG = {
    "link_prefix": "Topics/",
    "whitelist_file": "tag-whitelist.txt",
    "whitelist_min_count": 0,
    "special_rules": [],
    "batch_size": 0,
    "save_checkpoint": True,
}


# ── CLI ──────────────────────────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert #tags to [[Topics/tag]] wiki-links"
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Vault root directory (default: current dir)",
    )
    parser.add_argument(
        "--config",
        help="YAML config file (overrides defaults, CLI flags override both)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes only — no files written",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continue from last checkpoint",
    )
    parser.add_argument(
        "--generate-whitelist",
        action="store_true",
        help="Scan vault and generate whitelist file for review",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=0,
        help="Process N files then pause (for git-commit between batches)",
    )
    parser.add_argument(
        "--links-only",
        action="store_true",
        help="Skip creating Topic stub pages; only convert #tag references",
    )
    return parser.parse_args()


def load_config(args):
    """Merge: defaults ← YAML file ← CLI flags."""
    config = dict(DEFAULT_CONFIG)

    # Load YAML over defaults
    if args.config and yaml:
        cfg_path = Path(args.config)
        if cfg_path.exists():
            with open(cfg_path) as f:
                file_cfg = yaml.safe_load(f)
                if file_cfg:
                    config.update(file_cfg)
        else:
            print(f"[WARN] Config file not found: {args.config}", file=sys.stderr)
    elif args.config and not yaml:
        print("[WARN] PyYAML not installed. Install with: pip install pyyaml")
        print("[WARN] Using defaults + CLI flags only.")

    # CLI flags override
    config["dir"] = args.dir
    config["dry_run"] = args.dry_run
    config["resume"] = args.resume
    config["generate_whitelist"] = args.generate_whitelist
    config["links_only"] = args.links_only
    if args.batch:
        config["batch_size"] = args.batch

    return config


# ── WHITELIST ────────────────────────────────────────────────────────────────


def scan_tags(vault: Path):
    """Scan all .md files, collect #tag occurrences with frequency.

    Returns dict[str, int] — tag name → count.
    Also filters out tags that look like URL fragments (preceded by URL pattern).
    """
    counts: dict[str, int] = {}

    for md_file in sorted(vault.rglob("*.md")):
        rel = md_file.relative_to(vault)
        # Skip hidden dirs (.git, .templates, .obsidian, etc.)
        if any(p.startswith(".") for p in rel.parts):
            continue

        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue  # binary or permission issue

        for m in TAG_INLINE_RE.finditer(text):
            tag = m.group(1)
            # Skip if # is part of a URL fragment — check chars before it
            start = m.start()
            before = text[max(0, start - 60):start]
            if re.search(r"https?://\S*$", before, re.IGNORECASE):
                continue
            counts[tag] = counts.get(tag, 0) + 1

    return counts


def filter_tags(raw_counts: dict[str, int], min_count: int = 0) -> list[str]:
    """Remove noise: numeric-only, single-char, rare tags (if min_count > 0)."""
    tags = []
    for tag, count in raw_counts.items():
        # Numeric-only tags (URL fragment leftovers like #1, #2966)
        if tag.replace("/", "").strip().isdigit():
            continue
        # Single character tags (noise)
        if len(tag.strip("/")) <= 1:
            continue
        # Rare tags (optional filter, for auto-whitelist without review)
        if min_count > 0 and count < min_count:
            continue
        # Excessively long tags (URL fragments, base64 blobs, noise)
        if len(tag) > 120:
            continue
        tags.append(tag)

    # Sort alphabetically for consistent whitelist output
    tags.sort(key=str.lower)
    return tags


def do_generate_whitelist(vault: Path, config: dict):
    """Scan vault, write whitelist to file, show stats."""
    print(f"  Scanning {vault} \u2026")
    raw = scan_tags(vault)
    print(f"  Found {len(raw)} unique tag patterns")

    tags = filter_tags(raw, config.get("whitelist_min_count", 0))
    wl_path = _resolve_path(config["whitelist_file"], vault)

    with open(wl_path, "w") as f:
        for tag in tags:
            f.write(f"{tag}\n")

    print(f"  Whitelist written: {wl_path} ({len(tags)} tags)")
    print(f"\n  Next steps:")
    print(f"    1. Edit {wl_path.name} \u2014 remove lines that aren't real tags")
    print(f"    2. Create migrate-tags.yaml for special rules (optional)")
    print(f"    3. Run with --dry-run to preview")
    print(f"    4. Run without flags to execute")


def load_whitelist(vault: Path, config: dict) -> set[str]:
    """Read whitelist file, return set of tag names."""
    wl_path = _resolve_path(config["whitelist_file"], vault)
    if not wl_path.exists():
        print(f"[ERROR] Whitelist not found: {wl_path}", file=sys.stderr)
        print("  Run with --generate-whitelist first.", file=sys.stderr)
        sys.exit(1)

    tags = set()
    with open(wl_path) as f:
        for line in f:
            tag = line.strip().strip("#")
            if tag:
                tags.add(tag)

    if not tags:
        print(f"[ERROR] Whitelist is empty: {wl_path}", file=sys.stderr)
        sys.exit(1)

    return tags


# ── SPECIAL RULES ────────────────────────────────────────────────────────────


def build_special_map(config: dict) -> dict[str, str]:
    """Convert YAML special_rules list \u2192 {tag: replacement} dict."""
    special = {}
    for rule in config.get("special_rules", []):
        tag = rule.get("tag", "").strip()
        replacement = rule.get("replacement", "")
        if tag and replacement:
            special[tag] = replacement
    return special


# ── CHECKPOINT ───────────────────────────────────────────────────────────────


def _ckpt_path(vault: Path) -> Path:
    return vault / "checkpoint.json"


def load_checkpoint(vault: Path) -> dict:
    """Load checkpoint dict or return empty default."""
    ckpt = _ckpt_path(vault)
    if ckpt.exists():
        with open(ckpt) as f:
            return json.load(f)
    return {"last_processed": None, "stats": {"changed": 0, "unchanged": 0}}


def save_checkpoint(vault: Path, ckpt: dict):
    """Persist checkpoint atomically (write \u2192 rename)."""
    tmp = _ckpt_path(vault).with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(ckpt, f, indent=2, ensure_ascii=False)
    tmp.replace(_ckpt_path(vault))


# ── FILE PROCESSING ──────────────────────────────────────────────────────────


def _resolve_path(name: str, anchor: Path) -> Path:
    """If name is relative, resolve against anchor dir."""
    p = Path(name)
    if p.is_absolute():
        return p
    return anchor / p


# Compiled regex: find any #TagName (single-pass, no lookbehind to catch glued tags)
_TAG_FIND_RE = re.compile(r"#([\w/-]+)")


def process_line(line: str, tags_set: set[str], special: dict[str, str], prefix: str) -> str:
    """Single-pass: find all #tag, convert if in whitelist.

    Handles glued tags like #Tag1#Tag2 (168 files in this vault).
    Skips ## headings automatically (regex requires # + [a-zA-Z0-9_/-], so ## doesn't match).
    Skips non-whitelisted tags (URL fragments, noise) via tags_set check.
    """
    parts: list[str] = []
    pos = 0

    for m in _TAG_FIND_RE.finditer(line):
        tag = m.group(1)

        # Text before this match
        if m.start() > pos:
            parts.append(line[pos:m.start()])

        # Skip if part of markdown heading (## or more)
        if m.start() > 0 and line[m.start() - 1] == "#":
            parts.append(m.group())
            pos = m.end()
            continue

        # Convert if whitelisted, else leave as-is
        if tag in tags_set:
            parts.append(special.get(tag, f"[[{prefix}{tag}]]"))
        else:
            parts.append(m.group())
        pos = m.end()

    # Remainder of line after last match
    if pos < len(line):
        parts.append(line[pos:])

    return "".join(parts)


def _extract_tags_from_frontmatter(fm_lines: list[str]) -> list[str]:
    """Parse YAML frontmatter lines and extract the `tags` list.

    Handles both inline (`tags: [A, B]`) and multi-line (`tags:\n  - A\n  - B`) formats.
    Uses PyYAML if available, falls back to regex.
    Returns list of tag strings (without # prefix).
    """
    text = "".join(fm_lines)

    # Prefer PyYAML for robust parsing
    if yaml:
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                raw = data.get("tags", [])
                if isinstance(raw, list):
                    return [str(t).lstrip("#") for t in raw if t]
        except Exception:
            pass

    # Fallback: manual regex parser
    import re as _re
    tags: list[str] = []

    # Inline: tags: [Tag1, Tag2]
    m = _re.search(r"^tags\s*:\s*\[([^\]]*)", text, _re.MULTILINE)
    if m:
        for item in m.group(1).split(","):
            val = item.strip().strip("'\"").lstrip("#")
            if val:
                tags.append(val)
        return tags

    # Multi-line: tags:\n  - Tag1\n  - Tag2
    in_tags = False
    for line in fm_lines:
        if _re.match(r"^tags\s*:\s*\[[^\]]*\]", line):
            break  # already handled above
        if _re.match(r"^tags\s*:", line):
            in_tags = True
            rest = line.split(":", 1)[1].strip()
            if rest and not rest.startswith("["):
                val = rest.strip("'\"").lstrip("#")
                if val:
                    tags.append(val)
            continue
        if in_tags:
            m2 = _re.match(r"^\s+-\s+(.+)$", line)
            if m2:
                val = m2.group(1).strip().strip("'\"").lstrip("#")
                if val:
                    tags.append(val)
            else:
                in_tags = False

    return tags


def process_file(filepath: Path, tags_set: set[str], special: dict[str, str],
                 prefix: str, dry_run: bool) -> bool:
    """Process one file. Returns True if file changed (or would change in dry-run).

    Replaces #tags in content AND extracts frontmatter tags to insert
    as wiki-links at the top of the page body.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return False

    if "\0" in text:
        return False  # binary

    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    changed = False
    frontmatter_active = False
    frontmatter_seen = False
    frontmatter_lines: list[str] = []
    fence_active = False

    # Check if frontmatter tags were already injected in a prior run:
    # look for ---\n...\n---\n[[Topics/ pattern
    already_injected = bool(
        re.search(r"^---\n(?:.*\n)*?---\n\[\[Topics/", text, re.MULTILINE)
    )

    for line in lines:
        stripped = line.strip()

        # ── YAML frontmatter start ──
        if not frontmatter_seen and stripped == "---":
            frontmatter_active = True
            frontmatter_seen = True
            frontmatter_lines = []
            new_lines.append(line)
            continue

        # ── YAML frontmatter end ──
        if frontmatter_active and stripped == "---":
            frontmatter_active = False
            new_lines.append(line)

            # Extract tags from frontmatter and inject as wiki-links
            # (skip if already done in a prior run)
            if not already_injected:
                fm_tags = _extract_tags_from_frontmatter(frontmatter_lines)
                if fm_tags:
                    injected = []
                    for tag in fm_tags:
                        if tag in tags_set:
                            repl = special.get(tag, f"[[{prefix}{tag}]]")
                            injected.append(repl)
                    if injected:
                        new_lines.append(" ".join(injected) + "\n")
                        changed = True
            continue

        # ── Frontmatter body ──
        if frontmatter_active:
            frontmatter_lines.append(line)
            new_lines.append(line)
            continue

        # ── Code fences ──
        if stripped.startswith("```"):
            fence_active = not fence_active
            new_lines.append(line)
            continue
        if fence_active:
            new_lines.append(line)
            continue

        # ── Tag replacement in content ──
        processed = process_line(line, tags_set, special, prefix)
        if processed != line:
            changed = True
        new_lines.append(processed)

    if changed and not dry_run:
        filepath.write_text("".join(new_lines), encoding="utf-8")

    return changed


# ── TOPIC PAGE CREATION ────────────────────────────────────────────────────────


def create_topic_pages(vault: Path, whitelist: set[str], prefix: str, dry_run: bool, links_only: bool) -> int:
    """Create stub .md files for each whitelisted tag under Topics/.

    - ``#Tag`` -> ``Topics/Tag.md``
    - ``#A/B/C`` -> ``Topics/A/B/C.md`` (creates subdirectories)
    - Skips if file already exists (does not overwrite).
    - Does nothing if ``--links-only`` (returns 0).

    Returns number of files created.
    """
    if links_only:
        return 0

    topics_dir = vault / prefix.rstrip("/")
    created = 0
    skipped = 0

    for tag in sorted(whitelist, key=str.lower):
        # Compute path: "Health/Sleep" -> Topics/Health/Sleep.md
        filepath = (topics_dir / tag).with_suffix(".md")

        if dry_run:
            if filepath.exists():
                skipped += 1
            else:
                created += 1
            continue

        if filepath.exists():
            skipped += 1
            continue

        # Safety: skip if filename would be too long for the filesystem
        try:
            # Probe by creating parent and testing a stat
            filepath.parent.mkdir(parents=True, exist_ok=True)
            # Touch with empty content first to validate path length
            filepath.write_text(f"# {tag}\n", encoding="utf-8")
        except OSError as e:
            print(f"  [WARN] Skipping topic page for '{tag}': {e}")
            # Clean up empty parent if we created it
            continue
        created += 1

    total = created + skipped
    if total > 0:
        print(f"  Topic pages: {created} created, {skipped} already exist")
    return created


# ── MAIN ─────────────────────────────────────────────────────────────────────


def main():
    args = parse_args()
    config = load_config(args)
    vault = Path(config["dir"]).resolve()

    if not vault.exists():
        print(f"[ERROR] Directory not found: {vault}", file=sys.stderr)
        sys.exit(1)

    prefix = config.get("link_prefix", "Topics/").rstrip("/") + "/"

    # Whitelist generation mode
    if config.get("generate_whitelist"):
        do_generate_whitelist(vault, config)
        return

    # Load whitelist
    whitelist = load_whitelist(vault, config)
    special_map = build_special_map(config)
    tags_set = whitelist  # set for O(1) lookup in process_line

    print(f"  Tags: {len(whitelist)} whitelisted, {len(special_map)} special rules")
    print(f"  Prefix: [[{prefix}{{tag}}]]\n")

    dry_run = config.get("dry_run", False)
    links_only = config.get("links_only", False)

    # Create topic stub pages (unless --links-only)
    if not links_only:
        topic_dir = vault / prefix.rstrip("/")
        print(f"  Topic dir: {topic_dir}")
    pages_created = create_topic_pages(vault, whitelist, prefix, dry_run, links_only)
    print()

    # Collect files
    md_files = sorted(vault.rglob("*.md"))
    md_files = [
        f for f in md_files
        if not any(p.startswith(".") for p in f.relative_to(vault).parts)
    ]

    print(f"  Files: {len(md_files)} markdown files")

    # Checkpoint / Resume
    is_resume = config.get("resume", False)
    ckpt = load_checkpoint(vault) if is_resume else {
        "last_processed": None, "stats": {"changed": 0, "unchanged": 0}
    }
    start_idx = 0

    if is_resume and ckpt.get("last_processed"):
        for idx, f in enumerate(md_files):
            if str(f.relative_to(vault)) == ckpt["last_processed"]:
                start_idx = idx + 1
                break
        if start_idx > 0:
            print(f"  Resume: {start_idx}/{len(md_files)} done, continuing")
        else:
            print(f"  Resume: last_processed not found, starting fresh")

    remaining = md_files[start_idx:]
    if not remaining:
        print("  All files already processed.")
        return

    # Dry run / Execute
    dry_run = config.get("dry_run", False)
    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(f"  Mode: {mode}\n")

    if dry_run:
        print(f"{'='*60}")
        print(f"  DRY RUN \u2014 no files will be modified")
        print(f"{'='*60}\n")

    batch_size = config.get("batch_size", 0)
    changed = ckpt.get("stats", {}).get("changed", 0)
    errored = ckpt.get("stats", {}).get("unchanged", 0)
    processed_in_batch = 0

    for idx, filepath in enumerate(remaining):
        rel = str(filepath.relative_to(vault))
        result = process_file(filepath, tags_set, special_map, prefix, dry_run)

        processed_in_batch += 1
        if result:
            changed += 1
        else:
            errored += 1

        # Save checkpoint after each file
        ckpt["last_processed"] = rel
        ckpt["stats"] = {"changed": changed, "unchanged": errored}
        if config.get("save_checkpoint", True):
            save_checkpoint(vault, ckpt)

        # Progress
        absolute_idx = start_idx + idx + 1
        if absolute_idx % 100 == 0 or absolute_idx == len(md_files):
            pct = absolute_idx / len(md_files) * 100
            print(f"  {absolute_idx}/{len(md_files)} ({pct:.0f}%) \u2014 "
                  f"{ckpt['stats']['changed']} changed, "
                  f"{ckpt['stats']['unchanged']} unchanged")

        # Batch boundary
        if batch_size > 0 and processed_in_batch >= batch_size and absolute_idx < len(md_files):
            print(f"\n  \u2500\u2500 Batch of {batch_size} complete \u2500\u2500")
            print(f"  Commit now, then re-run with --resume to continue.")
            print(f"  checkpoint.json saved at: {_ckpt_path(vault)}\n")
            return

    # Summary
    final = ckpt["stats"]
    print(f"\n{'='*60}")
    print(f"  COMPLETE")
    print(f"{'='*60}")
    print(f"  Changed:   {final['changed']}")
    print(f"  Unchanged: {final['unchanged']}")
    print(f"  Total:     {len(md_files)}")
    print(f"  Mode:      {'dry-run (no writes)' if dry_run else 'live'}")

    if not dry_run:
        print(f"\n  Tip: run `git diff --stat` to review changes.")


if __name__ == "__main__":
    main()
