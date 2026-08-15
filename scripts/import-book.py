#!/usr/bin/env python3
"""Import a worksheet book into content/books/<book>/.

Each book is a sibling repo with chapters/ch01.md..chNN.md + appendices.md.
The script reads those, adds Hugo front matter, converts ```mermaid fences to
the Congo {{< mermaid >}} shortcode, rewrites the source's relative chapter
links (chNN.md#anchor) to absolute Hugo relrefs, and regenerates the whole
section from scratch. The generated pages are stamped with the source commit.

Everything under content/books/<book>/ is generated — never hand-edit;
re-run this script after a book release instead:

    python3 scripts/import-book.py --book k8s-worksheet [--source ../k8s-worksheet]
    python3 scripts/import-book.py --book agentic-engineering [--source ../agentic-engineering]

To add a book, add an entry to BOOKS below and a branded card under static/og/.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

BLOG_ROOT = Path(__file__).resolve().parent.parent

# Per-book configuration. `parts` mirrors each source README; the appendices
# ride at the end as chapter `chapters + 1`.
BOOKS = {
    "k8s-worksheet": {
        "title": "Kubernetes Internals Worksheet",
        "weight": 1,
        "chapters": 12,
        "parts": [
            ("Part A — Foundations & control plane internals", [1, 2, 3, 4]),
            ("Part B — Controllers", [5, 6]),
            ("Part C — Standards & extension interfaces", [7, 8, 9]),
            ("Part D — Operating at scale", [10]),
            ("Part E — Judgment at principal scale", [11, 12]),
            ("Reference", [13]),
        ],
        "summary": (
            "A flow-first Kubernetes internals book for senior, staff, and principal "
            "engineers — 30 end-to-end flows, sequence diagrams, failure modes, and "
            "tiered interview questions with model answers."
        ),
        "appendices_summary": (
            "Quick-reference tables, a glossary, the answer-quality rubric, "
            "the principal's lens, and further reading — the book's last-hour revision layer."
        ),
        "image": "og/k8s-worksheet-book.png",
        "repo": "https://github.com/sanketsudake/k8s-worksheet",
        "pdf": "https://github.com/sanketsudake/k8s-worksheet/releases/latest/download/kubernetes-internals-worksheet.pdf",
    },
    "agentic-engineering": {
        "title": "Agentic Engineering Worksheet",
        "weight": 2,
        "chapters": 14,
        "parts": [
            ("Part A — Foundations", [1, 2, 3]),
            ("Part B — Capabilities", [4, 5, 6]),
            ("Part C — Coding agents", [7, 8]),
            ("Part D — Systems", [9, 10, 11, 12]),
            ("Part E — Judgment", [13, 14]),
            ("Reference", [15]),
        ],
        "summary": (
            "A trace-first handbook on building and operating AI agents — the agent "
            "loop, context engineering, tools and MCP, memory, retrieval, coding-agent "
            "harnesses, multi-agent systems, evals, guardrails, and production ops, "
            "with 35 end-to-end traces, labs, and per-level exams."
        ),
        "appendices_summary": (
            "Quick-reference tables, a glossary, the answer-quality rubric, "
            "the architect's lens, the open-source stack by layer, and further reading "
            "— the book's last-hour revision layer."
        ),
        "image": "og/agentic-engineering-book.png",
        "repo": "https://github.com/sanketsudake/agentic-engineering",
        "pdf": "https://github.com/sanketsudake/agentic-engineering/releases/latest/download/agentic-engineering-worksheet.pdf",
    },
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def toml_str(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def convert_mermaid(lines: list[str]) -> list[str]:
    """Fence-state-aware conversion: only ```mermaid pairs become shortcodes."""
    out, state = [], None  # state: None | "mermaid" | "other"
    for line in lines:
        stripped = line.strip()
        if state is None and stripped == "```mermaid":
            out.append("{{< mermaid >}}")
            state = "mermaid"
        elif state == "mermaid" and stripped == "```":
            out.append("{{< /mermaid >}}")
            state = None
        elif state is None and stripped.startswith("```"):
            out.append(line)
            state = "other"
        elif state == "other" and stripped == "```":
            out.append(line)
            state = None
        else:
            out.append(line)
    if state is not None:
        sys.exit("error: unbalanced code fence detected during mermaid conversion")
    return out


LINK_RE = re.compile(r"\]\((ch\d{2}|appendices)\.md(#[^)\s]+)?\)")


def rewrite_links(body: str, book: str, slug_by_file: dict[str, str], path: Path) -> str:
    """Rewrite the source's relative chapter links to absolute Hugo relrefs.

    `[text](ch03.md#anchor)` becomes `[text]({{< relref "/books/<book>/<slug>" >}}#anchor)`.
    Anchors pass through unchanged: Hugo's default (GitHub-style) heading IDs
    match the slugs the source repo's linkify step emits. Fenced code is skipped.
    """
    def repl(m: re.Match) -> str:
        target = slug_by_file.get(m.group(1))
        if target is None:
            sys.exit(f"error: {path}: link to unknown chapter file {m.group(1)}.md")
        return f']({{{{< relref "/books/{book}/{target}" >}}}}{m.group(2) or ""})'

    out, fence = [], False
    for line in body.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        out.append(line if fence else LINK_RE.sub(repl, line))
    return "\n".join(out)


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip())
    return m.group(1) if m else text.strip()


def extract_summary(body: str) -> str:
    """First sentence of the chapter opening, with markdown links flattened to text."""
    m = re.search(r"^## Why this chapter\n+(.+?)$", body, re.M)
    if not m:
        return ""
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", first_sentence(m.group(1)))


def parse_chapter(path: Path, number: int, appendices_summary: str) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("# "):
        sys.exit(f"error: {path} does not start with an H1")
    title = lines[0][2:].strip()
    body_lines = lines[1:]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    if title == "Appendices":
        slug, summary = "appendices", appendices_summary
    else:
        bare = re.sub(r"^Chapter \d+ — ", "", title)
        slug = slugify(bare)
        summary = extract_summary("\n".join(body_lines))
        if not summary:
            sys.exit(f"error: no 'Why this chapter' summary found in {path}")
    return {
        "number": number,
        "file": path.stem,
        "title": title,
        "slug": slug,
        "summary": summary,
        "body": "\n".join(convert_mermaid(body_lines)).rstrip() + "\n",
    }


def generated_comment(book: str, commit: str) -> str:
    return (f"# Generated by scripts/import-book.py from "
            f"sanketsudake/{book}@{commit} — do not edit by hand.")


def front_matter(book: str, commit: str, **fields: str) -> str:
    out = ["+++", generated_comment(book, commit)]
    out += [f"{k} = {v}" for k, v in fields.items()]
    out.append("+++")
    return "\n".join(out)


def build_index(book: str, cfg: dict, chapters: list[dict], commit: str, date: str) -> str:
    # Congo's prev/next arrows read backwards for weight-ordered sections;
    # the cascade flips them for every chapter at once. `repo` and `pdf` feed
    # the chapter call-to-action in layouts/books/single.html.
    fm = "\n".join([
        "+++",
        generated_comment(book, commit),
        f"title = {toml_str(cfg['title'])}",
        f"date = {date}",
        f"weight = {cfg['weight']}",
        f"summary = {toml_str(cfg['summary'])}",
        f"images = [{toml_str(cfg['image'])}]",
        f"repo = {toml_str(cfg['repo'])}",
        f"pdf = {toml_str(cfg['pdf'])}",
        "groupByYear = false",
        "[cascade]",
        "  invertPagination = true",
        "+++",
    ])
    by_num = {c["number"]: c for c in chapters}
    toc = []
    for part, nums in cfg["parts"]:
        toc.append(f"**{part}**\n")
        for n in nums:
            c = by_num[n]
            toc.append(f"- [{c['title']}]({{{{< relref \"/books/{book}/{c['slug']}\" >}}}})")
        toc.append("")
    return f"{fm}\n\n{chr(10).join(toc)}\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True, choices=sorted(BOOKS),
                    help="which book to import (its slug under /books/)")
    ap.add_argument("--source", help="path to the book's checkout "
                                     "(default: ../<book> next to this repo)")
    args = ap.parse_args()
    book, cfg = args.book, BOOKS[args.book]
    src = Path(args.source or (BLOG_ROOT.parent / book)).resolve()
    if not (src / "chapters").is_dir():
        sys.exit(f"error: {src} has no chapters/ directory")
    out_dir = BLOG_ROOT / "content" / "books" / book

    commit = subprocess.check_output(
        ["git", "-C", str(src), "rev-parse", "--short", "HEAD"], text=True).strip()
    date = subprocess.check_output(
        ["git", "-C", str(src), "log", "-1", "--format=%cI"], text=True).strip()

    n_app = cfg["chapters"] + 1
    files = [(src / "chapters" / f"ch{n:02d}.md", n) for n in range(1, n_app)]
    files.append((src / "chapters" / "appendices.md", n_app))
    chapters = [parse_chapter(p, n, cfg["appendices_summary"]) for p, n in files]
    slug_by_file = {c["file"]: c["slug"] for c in chapters}
    part_of = {n: part for part, nums in cfg["parts"] for n in nums}
    missing = [c["number"] for c in chapters if c["number"] not in part_of]
    if missing:
        sys.exit(f"error: chapters {missing} are not assigned to a part in BOOKS[{book!r}]")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    written = []
    for c in chapters:
        page_dir = out_dir / c["slug"]
        page_dir.mkdir()
        fm = front_matter(
            book, commit,
            title=toml_str(c["title"]),
            date=date,
            weight=str(c["number"]),
            summary=toml_str(c["summary"]),
            part=toml_str(part_of[c["number"]]),
            images=f"[{toml_str(cfg['image'])}]",
            showTableOfContents="true",
        )
        body = rewrite_links(c["body"], book, slug_by_file, src / "chapters" / f"{c['file']}.md")
        path = page_dir / "index.md"
        path.write_text(fm + "\n\n" + body, encoding="utf-8")
        written.append(path)

    index = out_dir / "_index.md"
    index.write_text(build_index(book, cfg, chapters, commit, date), encoding="utf-8")
    written.append(index)

    subprocess.check_call(
        [sys.executable, str(BLOG_ROOT / "scripts" / "md-one-sentence-per-line.py"),
         *map(str, written)])
    print(f"imported {len(chapters)} chapters from {book}@{commit} into {out_dir}")


if __name__ == "__main__":
    main()
