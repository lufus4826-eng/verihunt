#!/usr/bin/env python3
"""Token-saving helper CLI for VeriHunt v2.0 (standard library only).

Automates session setup, project recon, isolated test execution with
deterministic harness validation (00-common.md §3), batch round runs,
append-only worklog updates, log digest checks, and sandbox lifecycle.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


IGNORED_RECON_DIRS = frozenset(
    {
        ".git",
        ".bughunt",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "target",
        "bin",
        "obj",
        "dist",
        "build",
        ".gradle",
        ".idea",
        ".vs",
        "TestResults",
        "vendor",
        "coverage",
        ".next",
        ".nuxt",
        "out",
    }
)

SANDBOX_ALWAYS_EXCLUDE = frozenset(
    {
        ".git",
        ".bughunt",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".vs",
        "TestResults",
        ".idea",
        ".gradle",
    }
)

SNAPSHOT_FS_SKIP_DIRS = frozenset({".bughunt", ".git", "node_modules"})

INSTRUCTION_FILES = frozenset(
    {
        "agent.md",
        "agents.md",
        "gemini.md",
        "claude.md",
        ".cursorrules",
        "contributing.md",
    }
)

EXT_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".php": "PHP",
    ".rs": "Rust",
}

TEST_CODE_EXTS = frozenset(
    {
        ".py",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".mts",
        ".tsx",
        ".jsx",
        ".go",
        ".java",
        ".kt",
        ".cs",
        ".php",
        ".rs",
    }
)

BINARY_EXTS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".whl",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".class",
        ".jar",
        ".pyc",
        ".pyo",
        ".o",
        ".a",
        ".wasm",
        ".ttf",
        ".woff",
        ".woff2",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)

MANIFEST_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pytest.ini",
        "package.json",
        "tsconfig.json",
        "go.mod",
        "pom.xml",
        "composer.json",
        "cargo.toml",
        ".env.example",
        "dockerfile",
    }
)

ENTRY_FILENAMES = frozenset(
    {
        "main.py",
        "app.py",
        "server.py",
        "cli.py",
        "manage.py",
        "wsgi.py",
        "asgi.py",
        "__main__.py",
        "main.js",
        "app.js",
        "server.js",
        "index.js",
        "cli.js",
        "main.ts",
        "app.ts",
        "server.ts",
        "index.ts",
        "cli.ts",
        "main.go",
        "program.cs",
        "startup.cs",
        "main.rs",
        "index.php",
    }
)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
CONTROL_TEST_RE = re.compile(
    r"^(?:test_?|test(?=[A-Z])|TestR\d+H\d+_?)?[Cc]ontrol(?:[^a-zA-Z]|$|(?=[A-Z]))"
    r"|\(control\)"
    r"|\bcontrol\s*:",
)
CONTROL_CAMEL_RE = re.compile(r"^(?:test|Test(?:R\d+H\d+_)?)Control")

SUPPORTED_RUNNERS = (
    "auto",
    "pytest",
    "unittest",
    "node",
    "jest",
    "vitest",
    "mocha",
    "go",
    "maven",
    "gradle",
    "dotnet",
    "phpunit",
    "cargo",
)


@dataclass
class DigestResult:
    """Structured outcome of parsing a test runner log."""

    tid: str
    runner: str
    exit_code: Optional[int]
    duration_s: Optional[float] = None
    ran: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    control_status: str = "NOT_FOUND"
    control_names: List[str] = field(default_factory=list)
    harness_signals: List[str] = field(default_factory=list)
    status: str = "UNKNOWN"
    failures: List[str] = field(default_factory=list)
    data_race: bool = False
    log_path: str = ""
    log_lines: int = 0
    log_bytes: int = 0


def configure_stdio() -> None:
    """Force UTF-8 stdout/stderr so multi-byte output never crashes on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except OSError:
                pass


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from process output."""
    return ANSI_RE.sub("", text)


def trunc(text: str, limit: int = 160) -> str:
    """Collapse internal newlines/whitespace and truncate cleanly."""
    clean = " ".join(text.strip().split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)] + "..."


def is_control_name(test_name: str) -> bool:
    """Return True if a leaf test name denotes a VeriHunt control test.

    Avoids false positives on names such as ``test_access_control_bypass``.
    """
    leaf = test_name.strip()
    if "::" in leaf:
        leaf = leaf.split("::")[-1]
    if " › " in leaf:
        leaf = leaf.split(" › ")[-1]
    leaf = re.split(r"[\[(]", leaf, maxsplit=1)[0].strip()
    return bool(CONTROL_TEST_RE.match(leaf) or CONTROL_CAMEL_RE.match(leaf))


def resolve_root(root_arg: Optional[str]) -> Path:
    """Resolve project ROOT and ensure it is an existing directory."""
    root = Path(root_arg).resolve() if root_arg else Path.cwd().resolve()
    if not root.is_dir():
        raise SystemExit(f"[bh.py] ERROR: ROOT does not exist or is not a directory: {root}")
    return root


def resolve_session(
    s_arg: str, root_arg: Optional[str] = None, require_exists: bool = True
) -> Tuple[Path, Path, str, Path]:
    """Resolve (ROOT, S_dir, SNAME, CACHE_dir) from ``--s`` and optional ``--root``."""
    raw = Path(s_arg)
    if root_arg:
        root = resolve_root(root_arg)
        s_dir = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    else:
        if raw.is_absolute():
            s_dir = raw.resolve()
        else:
            cwd = Path.cwd().resolve()
            candidate = (cwd / raw).resolve()
            if not candidate.exists() and "/" not in s_arg and "\\" not in s_arg:
                alt = (cwd / ".bughunt" / s_arg).resolve()
                if alt.exists():
                    candidate = alt
            s_dir = candidate
        if s_dir.parent.name == ".bughunt":
            root = s_dir.parent.parent
        else:
            root = Path.cwd().resolve()

    if require_exists and not s_dir.is_dir():
        raise SystemExit(f"[bh.py] ERROR: Session directory not found: {s_dir}")

    sname = s_dir.name
    cache_dir = (root / ".bughunt" / ".cache").resolve()
    if s_dir.parent.name == ".bughunt":
        cache_dir = (s_dir.parent / ".cache").resolve()
    return root, s_dir, sname, cache_dir


def rel_posix(path: Path, base: Path) -> str:
    """Format a relative path with forward slashes when possible."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_git_repo(root: Path) -> bool:
    """Return True if ``root`` sits inside a git work tree."""
    if not shutil.which("git"):
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def take_snapshot(root: Path, forced_mode: Optional[str] = None) -> Tuple[str, List[str]]:
    """Record git status or file timestamp snapshot per 00-common.md §4."""
    use_git = forced_mode == "git" or (forced_mode is None and is_git_repo(root))
    if use_git:
        try:
            proc = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.quotepath=false",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain",
                    "--ignored",
                    "--",
                    ".",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if proc.returncode == 0:
                lines = [ln.rstrip("\r\n") for ln in proc.stdout.splitlines() if ln.strip()]
                return "git", lines
        except (OSError, subprocess.SubprocessError):
            pass

    entries: List[str] = []
    root_res = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root_res):
        dirnames[:] = sorted(d for d in dirnames if d not in SNAPSHOT_FS_SKIP_DIRS)
        dp = Path(dirpath)
        for fname in sorted(filenames):
            fp = dp / fname
            try:
                st = fp.lstat()
            except OSError:
                continue
            rel = fp.relative_to(root_res).as_posix()
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            entries.append(f"{rel}\t{mtime}")
    entries.sort()
    return "fs", entries


def _is_bughunt_git_line(line: str) -> bool:
    """Return True if a ``git status --porcelain`` line only concerns ``.bughunt/``."""
    path_part = line[3:].strip() if len(line) > 3 else line.strip()
    if " -> " in path_part:
        path_part = path_part.split(" -> ")[-1].strip()
    path_part = path_part.strip('"').replace("\\", "/")
    parts = [p for p in path_part.split("/") if p]
    return ".bughunt" in parts


def diff_snapshots(
    before_lines: List[str], after_lines: List[str], mode: str
) -> Dict[str, List[str]]:
    """Compare before/after snapshots ignoring ``.bughunt/`` paths."""
    if mode == "git":
        b_filtered = [ln for ln in before_lines if not _is_bughunt_git_line(ln)]
        a_filtered = [ln for ln in after_lines if not _is_bughunt_git_line(ln)]
        b_set = set(b_filtered)
        a_set = set(a_filtered)
        return {
            "new_or_changed": [ln for ln in a_filtered if ln not in b_set],
            "resolved": [ln for ln in b_filtered if ln not in a_set],
        }

    def parse_fs(lines: Iterable[str]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for ln in lines:
            if "\t" in ln:
                p, ts = ln.split("\t", 1)
                if not p.startswith(".bughunt/"):
                    mapping[p] = ts
        return mapping

    b_map = parse_fs(before_lines)
    a_map = parse_fs(after_lines)
    added = [p for p in sorted(a_map) if p not in b_map]
    removed = [p for p in sorted(b_map) if p not in a_map]
    modified = [p for p in sorted(a_map) if p in b_map and a_map[p] != b_map[p]]
    return {"added": added, "modified": modified, "removed": removed}


def find_prior_sessions(bughunt_dir: Path, current_sname: str) -> Tuple[List[Dict[str, object]], int]:
    """Return up to 5 newest prior session summaries and total prior count."""
    if not bughunt_dir.is_dir():
        return [], 0
    dirs = [
        d
        for d in bughunt_dir.iterdir()
        if d.is_dir() and d.name not in (".cache", current_sname)
    ]
    dirs.sort(key=lambda d: d.name, reverse=True)
    total = len(dirs)
    summaries: List[Dict[str, object]] = []
    for d in dirs[:5]:
        wl = d / "worklog.md"
        status = ""
        if wl.is_file():
            try:
                first = wl.read_text(encoding="utf-8", errors="replace").splitlines()
                status = first[0].strip() if first else ""
            except OSError:
                status = ""
        summaries.append(
            {
                "sname": d.name,
                "status": status,
                "has_report": (d / "bug-report.md").is_file(),
            }
        )
    return summaries, total


# ---------------------------------------------------------------------------
# Subcommand: init
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Create session directory tree, snapshot fs-before.txt, and init worklog."""
    root = resolve_root(args.root)
    bughunt_dir = root / ".bughunt"
    cache_dir = bughunt_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    base_name = datetime.now().strftime("%Y%m%d-%H%M%S")
    sname = base_name
    suffix = 2
    while (bughunt_dir / sname).exists():
        sname = f"{base_name}-{suffix}"
        suffix += 1

    s_dir = bughunt_dir / sname
    for sub in ("tests", "logs", "tmp"):
        (s_dir / sub).mkdir(parents=True, exist_ok=True)

    snap_mode, snap_lines = take_snapshot(root)
    (s_dir / "logs" / "fs-before.txt").write_text(
        ("\n".join(snap_lines) + "\n") if snap_lines else "", encoding="utf-8"
    )
    (s_dir / "logs" / ".snapshot-mode").write_text(snap_mode, encoding="utf-8")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    worklog_init = (
        "Status: In Progress - Phase 0\n\n"
        "# VeriHunt Worklog\n"
        f"- **Session Directory:** `.bughunt/{sname}`\n"
        f"- **Target ROOT:** `{root}`\n"
        f"- **Start Time:** `{now_str}`\n"
    )
    (s_dir / "worklog.md").write_text(worklog_init, encoding="utf-8")

    prior, prior_total = find_prior_sessions(bughunt_dir, sname)
    payload: Dict[str, object] = {
        "S": f".bughunt/{sname}",
        "SNAME": sname,
        "CACHE": str(cache_dir.resolve()),
        "ROOT": str(root),
        "snapshot": snap_mode,
        "prior_sessions": prior,
    }
    if prior_total > len(prior):
        payload["prior_sessions_total"] = prior_total
    print(json.dumps(payload, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: recon
# ---------------------------------------------------------------------------


def _is_test_relpath(rel_lower: str, fname_lower: str) -> bool:
    parts = rel_lower.split("/")
    if any(p in ("tests", "test", "__tests__", "spec") for p in parts[:-1]):
        return True
    return bool(
        fname_lower.startswith("test_")
        or "_test." in fname_lower
        or ".test." in fname_lower
        or ".spec." in fname_lower
        or fname_lower.endswith("test.java")
        or fname_lower.endswith("test.kt")
        or fname_lower.endswith("test.php")
        or fname_lower.endswith("tests.cs")
        or fname_lower.endswith("test.cs")
    )


def _read_manifest_entrypoints(root: Path, manifests: Sequence[str]) -> List[str]:
    entries: List[str] = []
    if "package.json" in manifests:
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8", errors="replace"))
            if isinstance(data.get("main"), str):
                entries.append(data["main"])
            bin_val = data.get("bin")
            if isinstance(bin_val, str):
                entries.append(bin_val)
            elif isinstance(bin_val, dict):
                entries.extend(str(v) for v in list(bin_val.values())[:3])
        except (OSError, ValueError):
            pass
    if "pyproject.toml" in manifests:
        try:
            txt = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
            in_scripts = False
            for ln in txt.splitlines():
                s = ln.strip()
                if s.startswith("["):
                    in_scripts = s in ("[project.scripts]", "[tool.poetry.scripts]")
                elif in_scripts and "=" in s and not s.startswith("#"):
                    entries.append(s.split("=", 1)[1].strip().strip("\"'"))
        except OSError:
            pass
    return entries


def _git_recon(root: Path) -> Tuple[List[str], List[str], str]:
    """Return (recent_fix_commits, churn_hotspots, churn_window_label)."""
    fixes: List[str] = []
    hotspots: List[str] = []
    window = "6m"
    try:
        fix_proc = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--oneline",
                "-i",
                "-E",
                "--grep=fix|bug|hotfix",
                "-n",
                "5",
                "--",
                ".",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if fix_proc.returncode == 0:
            fixes = [trunc(ln, 110) for ln in fix_proc.stdout.splitlines() if ln.strip()][:5]

        churn_proc = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--format=",
                "--name-only",
                "--since=6 months ago",
                "--",
                ".",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        def keep_git_file(p: str) -> bool:
            parts = [seg for seg in p.replace("\\", "/").split("/") if seg]
            return bool(parts) and not any(seg in IGNORED_RECON_DIRS for seg in parts)

        files = [ln.strip() for ln in churn_proc.stdout.splitlines() if ln.strip() and keep_git_file(ln.strip())]
        if not files:
            window = "last-50-commits"
            churn_proc = subprocess.run(
                ["git", "-C", str(root), "log", "--format=", "--name-only", "-n", "50", "--", "."],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            files = [ln.strip() for ln in churn_proc.stdout.splitlines() if ln.strip() and keep_git_file(ln.strip())]
        counts = Counter(files).most_common(5)
        hotspots = [f"{p} ({c})" for p, c in counts]
    except (OSError, subprocess.SubprocessError):
        pass
    return fixes, hotspots, window


def cmd_recon(args: argparse.Namespace) -> int:
    """Scan repository and emit a compact <=35-line project map starter."""
    root = resolve_root(args.root)
    max_lines = max(10, min(int(args.max_lines), 35))

    instructions: List[str] = []
    manifests: List[str] = []
    entry_candidates: List[str] = []
    test_files: List[str] = []
    test_dirs: Counter[str] = Counter()
    lang_loc: Counter[str] = Counter()
    dir_loc: Counter[str] = Counter()
    dir_files: Counter[str] = Counter()
    dir_langs: Dict[str, Counter[str]] = {}
    todo_hits: List[str] = []
    todo_total = 0
    total_loc = 0
    total_files = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_RECON_DIRS)
        dp = Path(dirpath)
        rel_dir = dp.relative_to(root).as_posix()
        depth = 0 if rel_dir == "." else rel_dir.count("/") + 1

        for fname in sorted(filenames):
            fp = dp / fname
            rel = fname if rel_dir == "." else f"{rel_dir}/{fname}"
            rel_lower = rel.lower()
            fname_lower = fname.lower()

            if fname_lower in INSTRUCTION_FILES or rel_lower == ".github/copilot-instructions.md":
                instructions.append(rel)

            if depth <= 2 and (
                fname_lower in MANIFEST_NAMES
                or fname_lower.startswith("requirements")
                or fname_lower.startswith("build.gradle")
                or fname_lower.startswith("jest.config.")
                or fname_lower.startswith("vitest.config.")
                or fname_lower.startswith("phpunit.xml")
                or fname_lower.endswith((".csproj", ".sln"))
            ):
                manifests.append(rel)

            if depth <= 3 and fname_lower in ENTRY_FILENAMES and len(entry_candidates) < 10:
                entry_candidates.append(rel)

            ext = fp.suffix.lower()
            if ext in BINARY_EXTS or fname_lower.endswith((".min.js", ".min.css", "-lock.json", ".lock")):
                continue

            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if size > 1_000_000:
                continue

            try:
                raw = fp.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:4096]:
                continue

            text = raw.decode("utf-8", errors="replace")
            lines_list = text.splitlines()
            loc = len(lines_list)
            total_files += 1
            total_loc += loc

            top_dir = "(root)" if rel_dir == "." else rel_dir.split("/", 1)[0] + "/"
            dir_loc[top_dir] += loc
            dir_files[top_dir] += 1
            lang = EXT_LANG.get(ext)
            if lang:
                lang_loc[lang] += loc
                dir_langs.setdefault(top_dir, Counter())[lang] += loc

            if _is_test_relpath(rel_lower, fname_lower):
                test_files.append(rel)
                test_dirs[top_dir] += 1

            if size <= 512_000:
                for idx, ln in enumerate(lines_list, 1):
                    if TODO_RE.search(ln):
                        todo_total += 1
                        if len(todo_hits) < 5:
                            todo_hits.append(f"{rel}:{idx}: {trunc(ln, 75)}")

    for ep in _read_manifest_entrypoints(root, manifests):
        if ep not in entry_candidates:
            entry_candidates.insert(0, ep)

    git_present = is_git_repo(root)
    fixes, hotspots, churn_window = _git_recon(root) if git_present else ([], [], "")

    if args.json:
        out_json = {
            "root": str(root),
            "git": git_present,
            "total_files": total_files,
            "total_loc": total_loc,
            "large_codebase": total_loc >= 50000,
            "instructions": instructions,
            "languages": dict(lang_loc.most_common()),
            "manifests": manifests,
            "entrypoints": entry_candidates[:8],
            "test_files_count": len(test_files),
            "test_dirs": dict(test_dirs.most_common(5)),
            "top_dirs": [
                {"dir": d, "loc": loc, "files": dir_files[d]}
                for d, loc in dir_loc.most_common(8)
            ],
            "todo_total": todo_total,
            "todo_samples": todo_hits,
            "git_fixes": fixes,
            "git_churn": hotspots,
        }
        print(json.dumps(out_json, ensure_ascii=False))
        return 0

    lines: List[str] = []
    large_tag = " LARGE(>=50k)" if total_loc >= 50000 else ""
    lines.append(
        f"RECON root={root} git={'yes' if git_present else 'no'} "
        f"files={total_files} loc={total_loc}{large_tag}"
    )
    lines.append(
        "instructions: " + (", ".join(instructions[:6]) if instructions else "none")
    )
    langs_str = ", ".join(f"{k}({v})" for k, v in lang_loc.most_common(5)) or "none"
    lines.append(f"languages(loc): {langs_str}")
    lines.append(
        "manifests: " + (", ".join(manifests[:10]) if manifests else "none")
    )
    lines.append(
        "entrypoints: " + (", ".join(entry_candidates[:8]) if entry_candidates else "none")
    )
    tdir_str = ", ".join(f"{d}({c})" for d, c in test_dirs.most_common(4)) or "none"
    lines.append(f"existing_tests: {len(test_files)} files [{tdir_str}]")

    lines.append("loc_by_dir:")
    for d, loc in dir_loc.most_common(6):
        top_lang = dir_langs.get(d, Counter()).most_common(1)
        ltag = f" [{top_lang[0][0]}]" if top_lang else ""
        lines.append(f"  {d} {loc} loc / {dir_files[d]} files{ltag}")

    lines.append(f"todo_hits: {todo_total}" + ("" if todo_hits else " (none)"))
    for hit in todo_hits[:4]:
        lines.append(f"  {hit}")

    if git_present:
        lines.append(f"git_churn ({churn_window}): " + (", ".join(hotspots[:5]) if hotspots else "none"))
        lines.append("git_fix_commits:" + ("" if fixes else " none"))
        for fx in fixes[:4]:
            lines.append(f"  {fx}")

    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [f"... (truncated to {max_lines} lines)"]

    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# Environment & Command Resolution Helpers
# ---------------------------------------------------------------------------


def build_isolated_env(cache_dir: Path, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return environment dict with UTF-8, no-bytecode, offline & cache isolation."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "MYPY_CACHE_DIR": str(cache_dir / "mypy"),
            "RUFF_CACHE_DIR": str(cache_dir / "ruff"),
            "GOPROXY": "off",
            "GOCACHE": str(cache_dir / "go-build"),
            "GOLANGCI_LINT_CACHE": str(cache_dir / "golangci-lint"),
            "CARGO_TARGET_DIR": str(cache_dir / "cargo-target"),
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "npm_config_offline": "true",
            "npm_config_cache": str(cache_dir / "npm"),
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "TERM": "dumb",
        }
    )
    if extra_env:
        env.update(extra_env)
    return env


def resolve_executable(cmd: List[str], cwd: Path, env: Dict[str, str]) -> List[str]:
    """Resolve Windows .cmd/.bat/.exe wrappers and relative scripts safely without shell=True."""
    if not cmd:
        return cmd
    exe = cmd[0]
    if "/" in exe or "\\" in exe or exe.startswith("."):
        cand = cwd / exe
        if cand.is_file():
            return [str(cand)] + cmd[1:]
        if os.name == "nt" and not cand.suffix:
            for ext in (".bat", ".cmd", ".exe"):
                alt = cwd / (exe + ext)
                if alt.is_file():
                    return [str(alt)] + cmd[1:]
        return cmd

    resolved = shutil.which(exe, path=env.get("PATH"))
    if resolved:
        return [resolved] + cmd[1:]
    return cmd


# ---------------------------------------------------------------------------
# Harness Validation & Log Parser (00-common.md §7)
# ---------------------------------------------------------------------------


def detect_runner(cmd: Optional[Sequence[str]], log_text: str) -> str:
    """Detect runner from command tokens first, then log output."""
    if cmd:
        joined = " ".join(cmd).lower()
        base0 = Path(cmd[0]).name.lower()
        if "pytest" in joined:
            return "pytest"
        if "unittest" in joined:
            return "unittest"
        if "vitest" in joined:
            return "vitest"
        if "jest" in joined:
            return "jest"
        if "mocha" in joined:
            return "mocha"
        if base0.startswith("node"):
            return "node"
        if base0 == "go" or base0.startswith("go."):
            return "go"
        if "mvn" in base0:
            return "maven"
        if "gradle" in base0:
            return "gradle"
        if base0.startswith("dotnet"):
            return "dotnet"
        if "phpunit" in joined:
            return "phpunit"
        if base0.startswith("cargo"):
            return "cargo"

    # Log-content auto-detection (handles `npm test`, `python test.py`, `bh.py check`)
    if (
        "test session starts" in log_text
        or re.search(r"^collected \d+ items", log_text, re.M)
        or re.search(
            r"^(?:=+\s*)?(?:\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed)\b.*|no tests ran)\bin\s+[\d.]+s(?:\s*=+)?$",
            log_text,
            re.M | re.I,
        )
    ):
        return "pytest"
    if re.search(r"^Ran \d+ tests? in [\d.]+s", log_text, re.M):
        return "unittest"
    if "TAP version" in log_text or (
        re.search(r"^# tests \d+", log_text, re.M) and re.search(r"^# pass \d+", log_text, re.M)
    ) or re.search(r"^[ℹi] tests \d+", log_text, re.M):
        return "node"
    if "Test Files" in log_text and re.search(r"Tests\s+.*\b(passed|failed)\b", log_text):
        return "vitest"
    if "Test Suites:" in log_text or re.search(
        r"^Tests:\s+\d+\s+(?:failed|passed|skipped|pending|todo|total)\b", log_text, re.M
    ):
        return "jest"
    if re.search(r"\b\d+ passing\b", log_text) and (
        "mocha" in log_text.lower() or re.search(r"\b\d+ failing\b", log_text)
    ):
        return "mocha"
    if (
        re.search(r"^=== RUN\s+", log_text, re.M)
        or re.search(r"^--- (PASS|FAIL):\s+", log_text, re.M)
        or "[build failed]" in log_text
        or "no test files" in log_text
    ):
        return "go"
    if "[INFO] Scanning for projects" in log_text or re.search(
        r"Tests run:\s*\d+,\s*Failures:\s*\d+", log_text
    ):
        return "maven"
    if "> Task :" in log_text or re.search(r"\d+ tests? completed", log_text):
        return "gradle"
    if (
        "Microsoft (R) Test Execution" in log_text
        or re.search(r"(?:Passed|Failed)!\s*-\s*Failed:\s*\d+", log_text)
        or re.search(r"\berror CS\d{4}\b", log_text)
    ):
        return "dotnet"
    if "PHPUnit " in log_text or re.search(r"Tests:\s*\d+,\s*Assertions:\s*\d+", log_text):
        return "phpunit"
    if re.search(r"test result:\s*(?:ok|FAILED)\.", log_text) or re.search(
        r"error\[E\d+\]:", log_text
    ):
        return "cargo"
    return "generic"


def _record_control(res: DigestResult, name: str, passed: bool) -> None:
    """Update control test tracking using worst-case precedence (FAIL beats PASS)."""
    if not is_control_name(name):
        return
    if name not in res.control_names:
        res.control_names.append(name)
    if not passed:
        res.control_status = "FAIL"
    elif res.control_status != "FAIL":
        res.control_status = "PASS"


def _parse_pytest(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    lines = text.splitlines()

    # Parse individual -v status lines and short test summary lines (handles spaces inside [parametrize])
    for ln in lines:
        m = re.match(
            r"^(\S+::.+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)(?:\s+\[\s*\d+%\])?\s*$",
            ln,
        )
        if m:
            _record_control(res, m.group(1), m.group(2) in ("PASSED", "XFAIL", "XPASS"))
            continue
        m_sum = re.match(
            r"^(FAILED|ERROR|SUBFAILED(?:\([^)]*\))?)\s+(\S+::.+?)(?:\s+-\s+.*)?$",
            ln,
        )
        if m_sum:
            _record_control(res, m_sum.group(2), False)

    # Parse bottom summary line: "=== 3 failed, 2 passed in 0.28s ===" or "-q": "3 failed, 2 passed in 0.28s"
    sum_matches = re.findall(
        r"^(?:=+\s*)?(\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed|deselected).*?)\s+in\s+[\d.]+s(?:\s*=+)?$",
        text,
        re.M | re.I,
    )
    if sum_matches:
        summary = sum_matches[-1]
        for count_s, kind in re.findall(
            r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected)",
            summary,
            re.I,
        ):
            c = int(count_s)
            k = kind.lower()
            if k == "passed":
                res.passed = c
            elif k == "failed":
                res.failed = c
            elif k.startswith("error"):
                res.errors = c
            elif k == "skipped":
                res.skipped = c
    else:
        # Fallback if no standard summary line (e.g. "no tests ran" or hard crash)
        m_no = re.search(r"collected\s+(\d+)\s+items", text)
        if m_no:
            res.ran = int(m_no.group(1))

    res.ran = max(res.ran, res.passed + res.failed + res.errors)

    # Extract concise failure/error messages (both FAILURES `E       ` and ERRORS `E   `)
    for ln in lines:
        m_err = re.match(r"^E\s{2,}(.+)$", ln)
        if m_err:
            msg = trunc(m_err.group(1), 150)
            if msg and msg not in res.failures and len(res.failures) < 3:
                res.failures.append(msg)
        elif re.match(r"^(FAILED|ERROR)\s+\S+", ln) and len(res.failures) < 3:
            if not res.failures:
                res.failures.append(trunc(ln, 150))

    # Harness breakdown signals per 00-common.md §7
    if exit_code in (2, 3, 4, 5):
        reason = {
            2: "exit=2 (collection/import/usage error)",
            3: "exit=3 (pytest internal error)",
            4: "exit=4 (file not found / bad args)",
            5: "exit=5 (no tests collected)",
        }[exit_code]
        res.harness_signals.append(reason)
    if res.errors > 0:
        res.harness_signals.append(f"pytest ERROR count={res.errors} (fixture/setup/collection)")
    for pat, label in (
        (r"ERROR collecting\b", "collection error"),
        (r"ImportError while importing test module", "ImportError during collection"),
        (r"\bModuleNotFoundError:", "ModuleNotFoundError"),
        (r"\bSyntaxError:", "SyntaxError"),
        (r"\bIndentationError:", "IndentationError"),
        (r"ERROR: file or directory not found", "test path not found"),
        (r"no tests ran", "no tests ran"),
        (r"INTERNALERROR>", "pytest INTERNALERROR"),
    ):
        if re.search(pat, text) and label not in res.harness_signals:
            res.harness_signals.append(label)
    if res.ran == 0 and "no tests ran" not in " ".join(res.harness_signals):
        res.harness_signals.append("ran 0 tests")


def _parse_unittest(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    lines = text.splitlines()
    for ln in lines:
        m = re.match(r"^(\S+)\s+\([^)]+\)\s+\.\.\.\s+(ok|FAIL|ERROR|skipped\b.*)$", ln)
        if m:
            _record_control(res, m.group(1), m.group(2) == "ok")
        m_hdr = re.match(r"^(FAIL|ERROR):\s+(\S+)\s+\(([^)]+)\)", ln)
        if m_hdr:
            _record_control(res, m_hdr.group(2), False)

    m_ran = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+([\d.]+)s", text)
    if m_ran:
        res.ran = int(m_ran.group(1))

    m_fail = re.search(
        r"FAILED\s+\(([^)]+)\)",
        text,
    )
    if m_fail:
        parts = m_fail.group(1)
        mf = re.search(r"failures=(\d+)", parts)
        me = re.search(r"errors=(\d+)", parts)
        ms = re.search(r"skipped=(\d+)", parts)
        res.failed = int(mf.group(1)) if mf else 0
        res.errors = int(me.group(1)) if me else 0
        res.skipped = int(ms.group(1)) if ms else 0
        res.passed = max(0, res.ran - res.failed - res.errors - res.skipped)
    elif re.search(r"^OK(?:\s+\(.*\))?$", text, re.M):
        ms = re.search(r"OK\s+\(skipped=(\d+)\)", text)
        res.skipped = int(ms.group(1)) if ms else 0
        res.passed = max(0, res.ran - res.skipped)

    # Inspect FAIL/ERROR blocks carefully (00-common.md §7: errors from import/setUp vs target exception)
    blocks = re.split(r"^={70}$", text, flags=re.M)
    import_setup_error = False
    for blk in blocks:
        blk_s = re.split(r"^-{70}\r?\nRan\s+\d+\s+tests?", blk, maxsplit=1, flags=re.M)[0].strip()
        if not (blk_s.startswith("ERROR:") or blk_s.startswith("FAIL:")):
            continue
        blk_lines = [ln for ln in blk_s.splitlines() if ln.strip()]
        header = blk_lines[0] if blk_lines else ""
        exc_line = blk_lines[-1] if blk_lines else ""
        if len(res.failures) < 3:
            res.failures.append(trunc(f"{header} -> {exc_line}", 150))

        if blk_s.startswith("ERROR:"):
            if (
                "unittest.loader" in header
                or "setUpClass" in header
                or "setUpModule" in header
                or "tearDownClass" in header
                or re.search(r": setUp \(", header)
                or re.search(
                    r"\b(ImportError|ModuleNotFoundError|SyntaxError|IndentationError)\b",
                    blk_s,
                )
            ):
                import_setup_error = True
            else:
                # Check if error occurred strictly inside .bughunt test file with NameError
                tb_files = re.findall(r'File "([^"]+)"', blk_s)
                if tb_files and ".bughunt" in tb_files[-1].replace("\\", "/") and exc_line.startswith(
                    "NameError:"
                ):
                    import_setup_error = True

    if res.ran == 0:
        res.harness_signals.append("Ran 0 tests")
    if import_setup_error:
        res.harness_signals.append("unittest error from import/setUp/syntax")
    elif res.errors > 0 and res.failed == 0 and not blocks:
        res.harness_signals.append(f"unittest errors={res.errors}")


def _parse_node(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    # TAP format (# tests N, # pass N, # fail N) OR spec format (ℹ tests N)
    for pat, attr in (
        (r"^(?:#|[ℹi])\s+tests\s+(\d+)", "ran"),
        (r"^(?:#|[ℹi])\s+pass\s+(\d+)", "passed"),
        (r"^(?:#|[ℹi])\s+fail\s+(\d+)", "failed"),
        (r"^(?:#|[ℹi])\s+skipped\s+(\d+)", "skipped"),
    ):
        matches = re.findall(pat, text, re.M)
        if matches:
            setattr(res, attr, int(matches[-1]))

    # Parse TAP individual results (indented leaf subtests too)
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m_tap = re.match(r"^\s*(not )?ok\s+\d+\s+-\s+(.+)$", ln)
        if m_tap:
            is_fail = bool(m_tap.group(1))
            name = m_tap.group(2).strip()
            is_suite = False
            err_lines: List[str] = []
            err_name = ""
            err_code = ""
            in_yaml_err = False
            for j in range(i + 1, min(i + 35, len(lines))):
                sub = lines[j].strip()
                if sub == "...":
                    break
                if sub in ("type: 'suite'", "failureType: 'subtestsFailed'"):
                    is_suite = True
                if sub.startswith("error: |-"):
                    in_yaml_err = True
                    continue
                if in_yaml_err:
                    if re.match(r"^[a-zA-Z_]+:", sub):
                        in_yaml_err = False
                    elif sub and not sub.startswith("Expected values to be"):
                        err_lines.append(sub)
                        continue
                if sub.startswith("name:"):
                    err_name = sub.split(":", 1)[1].strip().strip("'")
                elif sub.startswith("code:"):
                    err_code = sub.split(":", 1)[1].strip().strip("'")
                elif sub.startswith("error:") and not sub.endswith("|-"):
                    val = sub.split(":", 1)[1].strip().strip("'")
                    if val != "test failed":
                        err_lines.append(val)
            if not is_suite:
                _record_control(res, name, not is_fail)
                if is_fail and len(res.failures) < 3:
                    parts = [p for p in [err_name or err_code, " ".join(err_lines[:2])] if p]
                    detail = f"{name}: {' - '.join(parts)}" if parts else name
                    res.failures.append(trunc(detail, 150))
            continue

        m_spec = re.match(r"^\s*([✔✖])\s+(.+?)(?:\s+\([\d.]+ms\))?$", ln)
        if m_spec:
            is_fail = m_spec.group(1) == "✖"
            name = m_spec.group(2).strip()
            _record_control(res, name, not is_fail)
            if is_fail and len(res.failures) < 3:
                res.failures.append(trunc(name, 150))

    if not res.failures:
        for ln in lines:
            if ln.startswith("# Error:") or ln.startswith("# SyntaxError:"):
                res.failures.append(trunc(ln[2:], 150))
                if len(res.failures) >= 3:
                    break

    if res.ran == 0 and (res.passed or res.failed):
        res.ran = res.passed + res.failed

    # 00-common.md §7 Node harness breakdown signals
    for pat, label in (
        (r"\bMODULE_NOT_FOUND\b", "MODULE_NOT_FOUND"),
        (r"\bERR_MODULE_NOT_FOUND\b", "ERR_MODULE_NOT_FOUND"),
        (r"\bERR_REQUIRE_ESM\b", "ERR_REQUIRE_ESM"),
        (r"\bERR_UNKNOWN_FILE_EXTENSION\b", "ERR_UNKNOWN_FILE_EXTENSION"),
        (r"\bCannot find module\b", "Cannot find module"),
        (r"\bSyntaxError:", "SyntaxError"),
        (r"require is not defined in ES module scope", "ESM/CJS mismatch"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)

    if res.ran == 0:
        res.harness_signals.append("# tests 0")


def _parse_jest(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    m_line = re.search(r"^Tests:\s+(.+)$", text, re.M)
    if m_line:
        s = m_line.group(1)
        for val, kind in re.findall(r"(\d+)\s+(failed|passed|skipped|pending|todo|total)", s, re.I):
            n = int(val)
            k = kind.lower()
            if k == "failed":
                res.failed = n
            elif k == "passed":
                res.passed = n
            elif k in ("skipped", "pending"):
                res.skipped += n
            elif k == "total":
                res.ran = n
    if res.ran == 0:
        res.ran = res.passed + res.failed

    for ln in text.splitlines():
        m_ok = re.match(r"^\s*[✓✔]\s+(.+?)(?:\s+\(\d+\s*m?s\))?$", ln)
        if m_ok:
            _record_control(res, m_ok.group(1), True)
        m_bad = re.match(r"^\s*[✕×✖]\s+(.+?)(?:\s+\(\d+\s*m?s\))?$", ln)
        if m_bad:
            _record_control(res, m_bad.group(1), False)
            if len(res.failures) < 3:
                res.failures.append(trunc(m_bad.group(1), 150))
        m_blk = re.match(r"^\s*●\s+(.+)$", ln)
        if m_blk and "Test suite failed to run" not in m_blk.group(1):
            _record_control(res, m_blk.group(1), False)
            if len(res.failures) < 3 and m_blk.group(1) not in res.failures:
                res.failures.append(trunc(m_blk.group(1), 150))

    for pat, label in (
        (r"Test suite failed to run", "Test suite failed to run"),
        (r"No tests found", "No tests found"),
        (r"Cannot find module", "Cannot find module"),
        (r"\bSyntaxError:", "SyntaxError"),
        (r"Validation Error:", "Jest Validation Error"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0 and "No tests found" not in res.harness_signals:
        res.harness_signals.append("ran 0 tests")


def _parse_vitest(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    m_line = re.search(r"^\s*Tests\s+(.+)$", text, re.M)
    if m_line:
        s = m_line.group(1)
        for val, kind in re.findall(r"(\d+)\s+(failed|passed|skipped|todo)", s, re.I):
            n = int(val)
            k = kind.lower()
            if k == "failed":
                res.failed = n
            elif k == "passed":
                res.passed = n
            elif k == "skipped":
                res.skipped += n
        m_tot = re.search(r"\((\d+)\)", s)
        if m_tot:
            res.ran = int(m_tot.group(1))
    if res.ran == 0:
        res.ran = res.passed + res.failed

    for ln in text.splitlines():
        m_ok = re.match(r"^\s*[✓✔]\s+(.+?)(?:\s+\d+\s*m?s)?$", ln)
        if m_ok:
            _record_control(res, m_ok.group(1), True)
        m_bad = re.match(r"^\s*[×✕✖]\s+(.+?)(?:\s+\d+\s*m?s)?$", ln)
        if m_bad:
            _record_control(res, m_bad.group(1), False)
            if len(res.failures) < 3:
                res.failures.append(trunc(m_bad.group(1), 150))

    for pat, label in (
        (r"Failed to load", "Failed to load"),
        (r"No test files found", "No test files found"),
        (r"Transform failed", "Transform failed"),
        (r"Failed to resolve import", "Failed to resolve import"),
        (r"Cannot find module|Cannot find package|ERR_MODULE_NOT_FOUND", "Missing module"),
        (r"\bSyntaxError:", "SyntaxError"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0 and "No test files found" not in res.harness_signals:
        res.harness_signals.append("ran 0 tests")


def _parse_mocha(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    mp = re.search(r"(\d+)\s+passing", text)
    mf = re.search(r"(\d+)\s+failing", text)
    ms = re.search(r"(\d+)\s+pending", text)
    res.passed = int(mp.group(1)) if mp else 0
    res.failed = int(mf.group(1)) if mf else 0
    res.skipped = int(ms.group(1)) if ms else 0
    res.ran = res.passed + res.failed

    for ln in text.splitlines():
        m_ok = re.match(r"^\s*[✔✓]\s+(.+?)(?:\s+\(\d+ms\))?$", ln)
        if m_ok:
            _record_control(res, m_ok.group(1), True)
        m_bad = re.match(r"^\s*\d+\)\s+(.+?):?$", ln)
        if m_bad:
            _record_control(res, m_bad.group(1), False)
            if len(res.failures) < 3:
                res.failures.append(trunc(m_bad.group(1), 150))

    for pat, label in (
        (r"No test files found", "No test files found"),
        (r"Cannot find module|ERR_MODULE_NOT_FOUND|ERR_REQUIRE_ESM", "Module/ESM load error"),
        (r"\bSyntaxError:", "SyntaxError"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0:
        res.harness_signals.append("ran 0 tests")


def _parse_go(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    for ln in text.splitlines():
        m = re.match(r"^---\s+(PASS|FAIL|SKIP):\s+(\S+)", ln)
        if m:
            kind, name = m.group(1), m.group(2)
            # Count top-level tests (skip indented subtests if already counted? no, top-level starts at col 0)
            if kind == "PASS":
                res.passed += 1
                _record_control(res, name, True)
            elif kind == "FAIL":
                res.failed += 1
                _record_control(res, name, False)
                if len(res.failures) < 3:
                    res.failures.append(name)
            elif kind == "SKIP":
                res.skipped += 1
        elif re.match(r"^ok\s+\S+", ln) and res.passed == 0 and res.failed == 0:
            # Non-verbose `go test ./...`
            res.passed += 1

    res.ran = res.passed + res.failed
    if "WARNING: DATA RACE" in text or "race detected during execution of test" in text:
        res.data_race = True
        if len(res.failures) < 3:
            res.failures.insert(0, "WARNING: DATA RACE detected")

    for pat, label in (
        (r"\[build failed\]", "[build failed]"),
        (r"\[setup failed\]", "[setup failed]"),
        (r"no test files", "no test files"),
        (r"matched no packages", "matched no packages"),
        (r"testing: warning: no tests to run", "no tests to run"),
        (r"cannot find package|no required module provides package", "missing Go package"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0 and not any("no test" in s for s in res.harness_signals):
        res.harness_signals.append("ran 0 tests")


def _parse_maven(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    matches = re.findall(
        r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)",
        text,
    )
    if matches:
        # Prefer the final summary line if "Results:" section exists, else sum per-class lines
        if "Results:" in text:
            tail = text.split("Results:")[-1]
            m_tail = re.findall(
                r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)",
                tail,
            )
            chosen = m_tail[-1:] if m_tail else matches[-1:]
        else:
            chosen = matches[-1:]
        for r_s, f_s, e_s, s_s in chosen:
            res.ran += int(r_s)
            res.failed += int(f_s)
            res.errors += int(e_s)
            res.skipped += int(s_s)
        res.passed = max(0, res.ran - res.failed - res.errors - res.skipped)

    for ln in text.splitlines():
        m_f = re.search(r"([A-Za-z0-9_.$]+(?:\.[A-Za-z0-9_$]+)?)\s*<<<\s*(FAILURE|ERROR)!", ln)
        if m_f:
            _record_control(res, m_f.group(1).split(".")[-1], False)
            if len(res.failures) < 3:
                res.failures.append(trunc(ln, 150))
            continue
        m_err_sum = re.match(r"^\[ERROR\]\s+([A-Za-z0-9_$.]+:\d+\s+.+)$", ln)
        if m_err_sum:
            _record_control(res, m_err_sum.group(1).split(":")[0].split(".")[-1], False)
            if len(res.failures) < 3:
                res.failures.append(trunc(m_err_sum.group(1), 150))

    for pat, label in (
        (r"COMPILATION ERROR|Compilation failure", "COMPILATION ERROR"),
        (r"No tests were executed", "No tests were executed"),
        (r"Could not resolve dependencies|Cannot access .* in offline mode", "Dependency resolution error"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0 and "No tests were executed" not in res.harness_signals:
        res.harness_signals.append("Tests run: 0")


def _parse_gradle(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    m_comp = re.findall(r"(\d+)\s+tests?\s+completed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+skipped)?", text)
    if m_comp:
        for t_s, f_s, s_s in m_comp:
            res.ran += int(t_s)
            res.failed += int(f_s)
            res.skipped += int(s_s) if s_s else 0
        res.passed = max(0, res.ran - res.failed - res.skipped)

    for ln in text.splitlines():
        m_case = re.match(r"^\s*([A-Za-z0-9_.$> ]+?)\s+(PASSED|FAILED|SKIPPED)\s*$", ln)
        if m_case:
            name = m_case.group(1).strip().split(".")[-1].split(">")[-1].strip()
            st = m_case.group(2)
            _record_control(res, name, st != "FAILED")
            if st == "FAILED" and len(res.failures) < 3:
                res.failures.append(trunc(ln, 150))
            if not m_comp and st in ("PASSED", "FAILED"):
                res.ran += 1
                if st == "PASSED":
                    res.passed += 1
                else:
                    res.failed += 1

    for pat, label in (
        (r"Compilation failed", "Compilation failed"),
        (r"No tests found for given includes", "No tests found for given includes"),
        (r"Could not resolve|Could not GET|No cached version", "Dependency/offline error"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0 and exit_code != 0:
        res.harness_signals.append("ran 0 tests")
    elif res.ran == 0 and exit_code == 0 and "UP-TO-DATE" not in text:
        res.harness_signals.append("ran 0 tests")


def _parse_dotnet(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    m_sum = re.findall(
        r"(?:Passed|Failed)!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+),\s*Skipped:\s*(\d+),\s*Total:\s*(\d+)",
        text,
    )
    if m_sum:
        for f_s, p_s, s_s, t_s in m_sum:
            res.failed += int(f_s)
            res.passed += int(p_s)
            res.skipped += int(s_s)
            res.ran += int(t_s)
    else:
        for pat, attr in (
            (r"Total tests:\s*(\d+)", "ran"),
            (r"Passed:\s*(\d+)", "passed"),
            (r"Failed:\s*(\d+)", "failed"),
            (r"Skipped:\s*(\d+)", "skipped"),
        ):
            m = re.search(pat, text)
            if m:
                setattr(res, attr, int(m.group(1)))

    for ln in text.splitlines():
        m_ok = re.match(r"^\s*Passed\s+(\S+)", ln)
        if m_ok:
            _record_control(res, m_ok.group(1).split(".")[-1], True)
        m_bad = re.match(r"^\s*Failed\s+(\S+)", ln)
        if m_bad:
            _record_control(res, m_bad.group(1).split(".")[-1], False)
            if len(res.failures) < 3:
                res.failures.append(trunc(ln, 150))

    for pat, label in (
        (r"\berror CS\d+\b|Build FAILED\.", "C# compilation error"),
        (r"No test matches the given testcase filter|No test is available", "No test matched filter"),
        (r"\berror NU1[13]01\b", "NuGet restore/offline error"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0:
        res.harness_signals.append("ran 0 tests")


def _parse_phpunit(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    m_ok = re.search(r"OK\s+\((\d+)\s+tests?,\s*(\d+)\s+assertions?\)", text)
    if m_ok:
        res.ran = int(m_ok.group(1))
        res.passed = res.ran
    else:
        m_t = re.search(r"Tests:\s*(\d+),\s*Assertions:\s*\d+(.*)$", text, re.M)
        if m_t:
            res.ran = int(m_t.group(1))
            rest = m_t.group(2)
            mf = re.search(r"Failures:\s*(\d+)", rest)
            me = re.search(r"Errors:\s*(\d+)", rest)
            ms = re.search(r"Skipped:\s*(\d+)", rest)
            res.failed = int(mf.group(1)) if mf else 0
            res.errors = int(me.group(1)) if me else 0
            res.skipped = int(ms.group(1)) if ms else 0
            res.passed = max(0, res.ran - res.failed - res.errors - res.skipped)

    for ln in text.splitlines():
        m_case = re.match(r"^\d+\)\s+([A-Za-z0-9_\\]+::[A-Za-z0-9_]+)", ln)
        if m_case:
            _record_control(res, m_case.group(1), False)
            if len(res.failures) < 3:
                res.failures.append(trunc(ln, 150))

    for pat, label in (
        (r"No tests executed!", "No tests executed!"),
        (r"Cannot open file", "Cannot open file"),
        (r"Class .*?(?:not found|cannot be found)", "Class not found"),
        (r"Parse error:|Fatal error:", "PHP syntax/fatal error"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0 and "No tests executed!" not in res.harness_signals:
        res.harness_signals.append("ran 0 tests")


def _parse_cargo(text: str, exit_code: Optional[int], res: DigestResult) -> None:
    for ln in text.splitlines():
        m_case = re.match(r"^test\s+(\S+)\s+\.\.\.\s+(ok|FAILED|ignored)\b", ln)
        if m_case:
            name, st = m_case.group(1), m_case.group(2)
            if st != "ignored":
                _record_control(res, name, st == "ok")
            if st == "FAILED" and len(res.failures) < 3:
                res.failures.append(name)

    blocks = re.findall(
        r"test result:\s*(?:ok|FAILED)\.\s*(\d+)\s+passed;\s*(\d+)\s+failed;\s*(\d+)\s+ignored",
        text,
    )
    if blocks:
        for p_s, f_s, i_s in blocks:
            res.passed += int(p_s)
            res.failed += int(f_s)
            res.skipped += int(i_s)
        res.ran = res.passed + res.failed
    else:
        res.ran = res.passed + res.failed

    for pat, label in (
        (r"error\[E\d+\]:|could not compile", "Rust compilation error"),
        (r"no test target named|no bin target named|no matching package named", "Cargo target not found"),
        (r"can't find crate|failed to select a version", "Cargo dependency/offline error"),
    ):
        if re.search(pat, text):
            res.harness_signals.append(label)
    if res.ran == 0:
        res.harness_signals.append("running 0 tests")


PARSERS: Dict[str, Callable[[str, Optional[int], DigestResult], None]] = {
    "pytest": _parse_pytest,
    "unittest": _parse_unittest,
    "node": _parse_node,
    "jest": _parse_jest,
    "vitest": _parse_vitest,
    "mocha": _parse_mocha,
    "go": _parse_go,
    "maven": _parse_maven,
    "gradle": _parse_gradle,
    "dotnet": _parse_dotnet,
    "phpunit": _parse_phpunit,
    "cargo": _parse_cargo,
}


def evaluate_log(
    text: str,
    tid: str,
    runner: str = "auto",
    cmd: Optional[Sequence[str]] = None,
    log_path: str = "",
    duration_s: Optional[float] = None,
) -> DigestResult:
    """Parse raw log text and evaluate 00-common.md §7 harness integrity."""
    clean = strip_ansi(text)
    lines = clean.splitlines()
    exit_code: Optional[int] = None
    for ln in reversed(lines):
        m_exit = re.match(r"^exit=(-?\d+)\s*$", ln.strip())
        if m_exit:
            exit_code = int(m_exit.group(1))
            break

    chosen_runner = detect_runner(cmd, clean) if runner == "auto" else runner
    res = DigestResult(
        tid=tid,
        runner=chosen_runner,
        exit_code=exit_code,
        duration_s=duration_s,
        log_path=log_path,
        log_lines=len(lines),
        log_bytes=len(text.encode("utf-8", errors="replace")),
    )

    parser = PARSERS.get(chosen_runner)
    if parser:
        parser(clean, exit_code, res)
    else:
        # Generic fallback: look for last non-exit lines if exit != 0
        if exit_code not in (None, 0):
            tail = [trunc(ln, 150) for ln in lines if ln.strip() and not ln.startswith("exit=")][-2:]
            res.failures.extend(tail)

    if "[bh.py] TIMEOUT" in clean or exit_code == 124:
        res.harness_signals.append("command timeout")
        res.status = "TIMEOUT"
        return res

    if "[bh.py] EXEC_ERROR" in clean or exit_code == 127:
        res.harness_signals.append("command not found / launch error")
        res.status = "EXEC_ERROR"
        return res

    if res.control_status == "FAIL" and not res.tid.lower().startswith("baseline"):
        res.harness_signals.append("control test FAILED")
    elif res.tid.lower().startswith("baseline"):
        res.control_status = "N/A(baseline)"

    # Classify overall verdict readiness
    if res.harness_signals:
        res.status = "HARNESS_BROKEN"
    elif exit_code == 0 and res.failed == 0 and res.errors == 0 and (res.ran > 0 or chosen_runner == "generic"):
        res.status = "ALL_PASS"
    elif (res.failed > 0 or res.errors > 0 or res.data_race) and res.ran > 0:
        res.status = "VALID_BUG_FAIL"
    elif exit_code not in (None, 0):
        res.harness_signals.append(f"non-zero exit={exit_code} with ran={res.ran}")
        res.status = "HARNESS_BROKEN"
    else:
        res.status = "ALL_PASS" if exit_code == 0 else "UNKNOWN"
    return res


def format_digest(res: DigestResult) -> str:
    """Format a DigestResult into a strictly <=12-line stdout summary."""
    dur = f" duration={res.duration_s:.2f}s" if res.duration_s is not None else ""
    exit_s = str(res.exit_code) if res.exit_code is not None else "?"
    lines: List[str] = [
        f"[RUN] tid={res.tid} runner={res.runner} exit={exit_s} status={res.status}{dur}",
        f"counts: ran={res.ran} passed={res.passed} failed={res.failed} errors={res.errors} skipped={res.skipped}",
    ]

    ctrl_detail = f" ({', '.join(res.control_names[:2])})" if res.control_names else ""
    lines.append(f"control: {res.control_status}{ctrl_detail}")

    if res.harness_signals:
        lines.append("harness: BROKEN -> " + "; ".join(res.harness_signals[:4]))
    else:
        lines.append("harness: OK (0 §7 breakdown signals)")

    if res.data_race:
        lines.append("race: WARNING: DATA RACE detected")

    if res.failures:
        lines.append(f"failures ({len(res.failures)} shown):")
        for f_msg in res.failures[:3]:
            lines.append(f"  - {trunc(f_msg, 155)}")

    lines.append(f"log: {res.log_path} ({res.log_lines} lines, {res.log_bytes}B)")
    if len(lines) > 12:
        lines = lines[:11] + [lines[-1]]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subcommand: run & check
# ---------------------------------------------------------------------------


def _execute_to_log(
    cmd: List[str],
    cwd: Path,
    env: Dict[str, str],
    log_file: Path,
    timeout_s: int,
) -> Tuple[str, int, float]:
    """Execute ``cmd`` in ``cwd``, write raw output + exit=<code> to ``log_file``."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    resolved_cmd = resolve_executable(cmd, cwd, env)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            resolved_cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        duration = time.monotonic() - t0
        raw_out = proc.stdout or ""
        rc = proc.returncode
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - t0
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        raw_out = partial + f"\n[bh.py] TIMEOUT after {timeout_s}s\n"
        rc = 124
    except FileNotFoundError as exc:
        duration = time.monotonic() - t0
        raw_out = f"[bh.py] EXEC_ERROR: command not found: {cmd[0]} ({exc})\n"
        rc = 127
    except OSError as exc:
        duration = time.monotonic() - t0
        raw_out = f"[bh.py] EXEC_ERROR: {exc}\n"
        rc = 126

    if raw_out and not raw_out.endswith("\n"):
        raw_out += "\n"
    full_log = f"{raw_out}exit={rc}\n"
    log_file.write_text(full_log, encoding="utf-8")
    return full_log, rc, duration


def _split_cli_args(cmd_str: str) -> List[str]:
    """Split a command string preserving Windows backslashes and mid-token quotes."""
    if os.name != "nt":
        return shlex.split(cmd_str, posix=True)
    tokens: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    in_token = False
    i = 0
    n = len(cmd_str)
    while i < n:
        ch = cmd_str[i]
        if quote is not None:
            if ch == "\\" and quote == '"' and i + 1 < n and cmd_str[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            if ch == quote:
                quote = None
                i += 1
                continue
            buf.append(ch)
        else:
            if ch in (" ", "\t", "\r", "\n"):
                if in_token:
                    tokens.append("".join(buf))
                    buf.clear()
                    in_token = False
                i += 1
                continue
            in_token = True
            if ch in ('"', "'"):
                quote = ch
            else:
                buf.append(ch)
        i += 1
    if in_token:
        tokens.append("".join(buf))
    return tokens


def _parse_cmd_remainder(raw_cmd: List[str]) -> List[str]:
    cmd = list(raw_cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if len(cmd) == 1 and " " in cmd[0] and not Path(cmd[0]).exists() and not shutil.which(cmd[0]):
        cmd = _split_cli_args(cmd[0])
    return cmd


def _sanitize_tid(tid: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", tid.strip())
    if not clean or clean in (".", ".."):
        raise SystemExit(f"[bh.py] ERROR: Invalid TID: {tid!r}")
    return clean


def cmd_run(args: argparse.Namespace) -> int:
    """Execute one command, store full log, and print <=12-line digest."""
    root, s_dir, _, cache_dir = resolve_session(args.s, args.root)
    cmd = _parse_cmd_remainder(args.cmd)
    if not cmd:
        raise SystemExit("[bh.py] ERROR: No command provided after `--`")

    tid = _sanitize_tid(args.tid)
    cwd = Path(args.cwd).resolve() if args.cwd else root
    if not cwd.is_dir():
        raise SystemExit(f"[bh.py] ERROR: --cwd directory not found: {cwd}")

    log_name = f"{tid}{args.log_suffix}.log"
    log_file = s_dir / "logs" / log_name
    env = build_isolated_env(cache_dir)

    full_log, rc, duration = _execute_to_log(cmd, cwd, env, log_file, int(args.timeout))
    res = evaluate_log(
        full_log,
        tid=tid,
        runner=args.runner,
        cmd=cmd,
        log_path=rel_posix(log_file, root),
        duration_s=duration,
    )
    print(format_digest(res))
    if args.strict_exit:
        return rc
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Inspect existing S/logs/<TID>.log (or round/all) without re-running."""
    root, s_dir, _, _ = resolve_session(args.s, args.root)
    logs_dir = s_dir / "logs"
    if not logs_dir.is_dir():
        raise SystemExit(f"[bh.py] ERROR: Logs directory not found: {logs_dir}")

    if args.tid:
        tid = _sanitize_tid(args.tid)
        log_file = logs_dir / f"{tid}{args.log_suffix}.log"
        if not log_file.is_file():
            raise SystemExit(f"[bh.py] ERROR: Log file not found: {log_file}")
        txt = log_file.read_text(encoding="utf-8", errors="replace")
        res = evaluate_log(txt, tid=tid, runner=args.runner, log_path=rel_posix(log_file, root))
        print(format_digest(res))
        return 0

    if args.round is not None:
        pattern = rf"^r{args.round}_h\d+{re.escape(args.log_suffix)}\.log$"
        rx = re.compile(pattern)
        candidates = sorted(p for p in logs_dir.iterdir() if p.is_file() and rx.match(p.name))
    else:
        suffix = args.log_suffix
        pattern = f"*{suffix}.log"
        candidates = sorted(
            p
            for p in logs_dir.glob(pattern)
            if p.is_file() and (suffix or not p.stem.endswith("_fix"))
        )
    if not candidates:
        raise SystemExit(f"[bh.py] ERROR: No matching log files in {logs_dir} ({pattern})")

    results: List[DigestResult] = []
    for lf in candidates:
        tid = lf.stem
        if args.log_suffix and tid.endswith(args.log_suffix):
            tid = tid[: -len(args.log_suffix)]
        txt = lf.read_text(encoding="utf-8", errors="replace")
        results.append(evaluate_log(txt, tid=tid, runner=args.runner, log_path=rel_posix(lf, root)))

    print(format_round_table(results, header=f"[CHECK {len(results)} logs]"))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: round
# ---------------------------------------------------------------------------


def _find_python_exe(root: Path) -> str:
    for rel in (
        ".venv/Scripts/python.exe",
        ".venv/bin/python",
        "venv/Scripts/python.exe",
        "venv/bin/python",
    ):
        cand = root / rel
        if cand.is_file():
            return str(cand)
    return sys.executable


def _has_pytest(py_exe: str, env: Dict[str, str]) -> bool:
    try:
        proc = subprocess.run(
            [py_exe, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _discover_round_tests(
    base_root: Path, s_dir: Path, sname: str, round_num: Optional[int], in_fix: bool
) -> Dict[str, List[Path]]:
    """Discover hypothesis test files in S/tests and S/sandbox (or sandbox-fix)."""
    found: Dict[str, List[Path]] = {}
    r_pat = str(round_num) if round_num is not None else r"\d+"

    re_std = re.compile(rf"(?:^|_)r({r_pat})_h(\d+)(?:_|\.)", re.I)
    re_php_jvm_cs = re.compile(rf"BugHuntR({r_pat})H(\d+)(?:[A-Z0-9_]|Test|Tests|\.)", re.I)
    re_go_rs = re.compile(rf"bughunt_r({r_pat})_h(\d+)(?:_test\.go|\.rs)$", re.I)

    if in_fix:
        tests_dir = base_root / ".bughunt" / sname / "tests"
        sandbox_dir = base_root
    else:
        tests_dir = s_dir / "tests"
        sandbox_dir = s_dir / "sandbox"

    if tests_dir.is_dir():
        for fp in sorted(tests_dir.iterdir()):
            if not fp.is_file() or fp.suffix.lower() not in TEST_CODE_EXTS:
                continue
            m = re_std.search(fp.name) or re_php_jvm_cs.search(fp.name)
            if m:
                tid = f"r{m.group(1)}_h{m.group(2)}"
                found.setdefault(tid, []).append(fp)

    sandbox_skip = SANDBOX_ALWAYS_EXCLUDE | {"target", "bin", "obj", "build", "out"}
    if sandbox_dir.is_dir():
        for dirpath, dirnames, filenames in os.walk(sandbox_dir):
            dirnames[:] = sorted(d for d in dirnames if d not in sandbox_skip)
            dp = Path(dirpath)
            for fname in sorted(filenames):
                if Path(fname).suffix.lower() not in TEST_CODE_EXTS:
                    continue
                m = re_go_rs.search(fname) or re_php_jvm_cs.search(fname)
                if m:
                    tid = f"r{m.group(1)}_h{m.group(2)}"
                    found.setdefault(tid, []).append(dp / fname)

    def sort_key(tid: str) -> Tuple[int, int]:
        m = re.match(r"r(\d+)_h(\d+)", tid)
        return (int(m.group(1)), int(m.group(2))) if m else (9999, 9999)

    return {k: found[k] for k in sorted(found, key=sort_key)}


def _resolve_sandbox_root(primary: Path, s_dir: Path, cwd: Path) -> Path:
    """Return the active sandbox root (sandbox-fix, sandbox, or cwd) containing ``primary``."""
    primary_res = primary.resolve()
    for cand in ((s_dir / "sandbox-fix").resolve(), (s_dir / "sandbox").resolve()):
        if cand in primary_res.parents or primary_res == cand:
            return cand
    return cwd.resolve()


def _find_manifest_root(
    primary: Path,
    sb_root: Path,
    manifest_names: Tuple[str, ...] = (),
    glob_patterns: Tuple[str, ...] = (),
) -> Path:
    """Walk upward from ``primary`` to ``sb_root`` to find the nearest project/module manifest."""
    primary_res = primary.resolve()
    sb_res = sb_root.resolve()
    for parent in primary_res.parents:
        if any((parent / name).is_file() for name in manifest_names) or any(
            any(parent.glob(pat)) for pat in glob_patterns
        ):
            return parent
        if parent == sb_res:
            break
    return sb_res


def _build_auto_cmd(
    tid: str,
    files: List[Path],
    cwd: Path,
    s_dir: Path,
    sname: str,
    cache_dir: Path,
    runner_pref: str,
    py_exe: str,
    pytest_ok: Optional[bool],
    env: Dict[str, str],
) -> Tuple[List[str], Dict[str, str], str]:
    """Construct an appropriate isolated runner command for a discovered TID."""
    primary = files[0]
    ext = primary.suffix.lower()
    rel_files = [rel_posix(f, cwd) for f in files]
    m_tid = re.match(r"r(\d+)_h(\d+)", tid)
    r_num, h_num = (m_tid.group(1), m_tid.group(2)) if m_tid else ("0", "0")
    extra_env: Dict[str, str] = {}

    if ext == ".py":
        use_pytest = (runner_pref == "pytest") or (runner_pref == "auto" and bool(pytest_ok))
        prev_pp = env.get("PYTHONPATH", "")
        extra_env["PYTHONPATH"] = f"{cwd}{os.pathsep}{prev_pp}" if prev_pp else str(cwd)
        if use_pytest:
            return [py_exe, "-m", "pytest", *rel_files, "-p", "no:cacheprovider", "-v"], extra_env, "pytest"
        tdir_rel = rel_posix(primary.parent, cwd)
        return [
            py_exe,
            "-m",
            "unittest",
            "discover",
            "-s",
            tdir_rel,
            "-t",
            tdir_rel,
            "-p",
            primary.name,
            "-v",
        ], extra_env, "unittest"

    if ext in (".js", ".mjs", ".cjs", ".ts", ".mts", ".tsx", ".jsx"):
        chosen = runner_pref
        if chosen == "auto":
            # Prefer node --test for plain JS unless jest/vitest config exists
            if (cwd / "vitest.bughunt.config.mts").is_file() or (s_dir / "vitest.bughunt.config.mts").is_file():
                chosen = "vitest"
            elif (s_dir / "jest.bughunt.config.cjs").is_file():
                chosen = "jest"
            else:
                chosen = "node"
        if chosen == "jest":
            cfg_flag = (
                ["--config", rel_posix(s_dir / "jest.bughunt.config.cjs", cwd)]
                if (s_dir / "jest.bughunt.config.cjs").is_file()
                else []
            )
            return (
                [
                    "npx",
                    "--no-install",
                    "jest",
                    "--ci",
                    "--coverage=false",
                    f"--cacheDirectory={cache_dir / 'jest'}",
                    *cfg_flag,
                    "--runTestsByPath",
                    *rel_files,
                ],
                extra_env,
                "jest",
            )
        if chosen == "vitest":
            cfg = s_dir / "vitest.bughunt.config.mts"
            cfg_args = ["--config", rel_posix(cfg, cwd)] if cfg.is_file() else ["--coverage.enabled=false"]
            return ["npx", "--no-install", "vitest", "run", *cfg_args, *rel_files], extra_env, "vitest"
        if chosen == "mocha":
            return ["npx", "--no-install", "mocha", "--no-config", "--timeout", "10000", *rel_files], extra_env, "mocha"
        return ["node", "--test", "--test-reporter=tap", *rel_files], extra_env, "node"

    if ext == ".php":
        return [
            "php",
            "vendor/bin/phpunit",
            "--do-not-cache-result",
            "--no-coverage",
            rel_files[0],
        ], extra_env, "phpunit"

    if ext == ".go":
        sb_root = _resolve_sandbox_root(primary, s_dir, cwd)
        sandbox_base = _find_manifest_root(primary, sb_root, manifest_names=("go.mod",))
        rel = primary.resolve().parent.relative_to(sandbox_base.resolve()).as_posix()
        pkg_rel = "." if rel == "." else f"./{rel}"
        return [
            "go",
            "-C",
            str(sandbox_base),
            "test",
            "-count=1",
            "-v",
            "-run",
            f"TestR{r_num}H{h_num}",
            pkg_rel,
        ], extra_env, "go"

    if ext in (".java", ".kt"):
        sb_root = _resolve_sandbox_root(primary, s_dir, cwd)
        sandbox_base = _find_manifest_root(
            primary,
            sb_root,
            manifest_names=("pom.xml",),
            glob_patterns=("build.gradle*",),
        )
        filter_tok = f"BugHuntR{r_num}H{h_num}"
        if (sandbox_base / "pom.xml").is_file():
            return [
                "mvn",
                "-o",
                "-B",
                "-f",
                str(sandbox_base / "pom.xml"),
                "test",
                f"-Dtest={filter_tok}*",
                "-Dsurefire.failIfNoSpecifiedTests=false",
                "-DfailIfNoTests=false",
            ], extra_env, "maven"
        gw_name = "gradlew.bat" if os.name == "nt" else "gradlew"
        gradlew = next((p / gw_name for p in (sandbox_base, sb_root) if (p / gw_name).is_file()), None)
        exe = str(gradlew) if gradlew is not None else "gradle"
        return [exe, "-p", str(sandbox_base), "test", "--offline", "--tests", f"*{filter_tok}*"], extra_env, "gradle"

    if ext == ".cs":
        sb_root = _resolve_sandbox_root(primary, s_dir, cwd)
        proj_dir = _find_manifest_root(primary, sb_root, glob_patterns=("*.csproj",))
        csprojs = sorted(proj_dir.glob("*.csproj"))
        target = str(csprojs[0]) if csprojs else str(primary.parent)
        return [
            "dotnet",
            "test",
            target,
            "--no-restore",
            "--filter",
            f"FullyQualifiedName~BugHuntR{r_num}H{h_num}",
            "--logger",
            "console;verbosity=normal",
        ], extra_env, "dotnet"

    if ext == ".rs":
        sb_root = _resolve_sandbox_root(primary, s_dir, cwd)
        sandbox_base = _find_manifest_root(primary, sb_root, manifest_names=("Cargo.toml",))
        return [
            "cargo",
            "test",
            "--offline",
            "--locked",
            "--manifest-path",
            str(sandbox_base / "Cargo.toml"),
            "--test",
            f"bughunt_{tid}",
        ], extra_env, "cargo"

    raise SystemExit(f"[bh.py] ERROR: Cannot auto-detect runner for {primary}; pass --cmd-template")


def _expand_cmd_template(
    template: str,
    tid: str,
    files: List[Path],
    cwd: Path,
    s_dir: Path,
    sname: str,
    cache_dir: Path,
) -> List[str]:
    """Tokenize template BEFORE substituting paths so spaces in paths stay single args."""
    tokens = _split_cli_args(template)

    m_tid = re.match(r"r(\d+)_h(\d+)", tid)
    r_num, h_num = (m_tid.group(1), m_tid.group(2)) if m_tid else ("0", "0")
    rel_files = [rel_posix(f, cwd) for f in files]
    sb_root = _resolve_sandbox_root(files[0], s_dir, cwd)
    sandbox_base = _find_manifest_root(
        files[0],
        sb_root,
        manifest_names=("go.mod", "pom.xml", "Cargo.toml"),
        glob_patterns=("build.gradle*", "*.csproj"),
    )
    try:
        rel_pkg = files[0].parent.resolve().relative_to(sandbox_base.resolve()).as_posix()
        pkg = "." if rel_pkg == "." else f"./{rel_pkg}"
    except ValueError:
        pkg = "."

    subs = {
        "{file}": rel_files[0],
        "{files}": " ".join(rel_files),
        "{tid}": tid,
        "{TID}": tid,
        "{id}": f"R{r_num}-H{h_num}",
        "{filter}": f"BugHuntR{r_num}H{h_num}",
        "{RNHM}": f"BugHuntR{r_num}H{h_num}",
        "{pkg}": pkg,
        "{s}": rel_posix(s_dir, cwd),
        "{S}": rel_posix(s_dir, cwd),
        "{sname}": sname,
        "{SNAME}": sname,
        "{cache}": str(cache_dir),
        "{CACHE}": str(cache_dir),
        "{sandbox}": rel_posix(sb_root, cwd),
    }

    out: List[str] = []
    for tok in tokens:
        if tok == "{files}":
            out.extend(rel_files)
            continue
        val = tok
        for k, v in subs.items():
            if k in val:
                val = val.replace(k, v)
        out.append(val)
    return out


def format_round_table(results: List[DigestResult], header: str) -> str:
    """Render compact round summary table."""
    counts = Counter(r.status for r in results)
    summary_parts = [f"{k}={counts[k]}" for k in sorted(counts)]
    lines: List[str] = [
        f"{header} tests={len(results)} | {' '.join(summary_parts)}",
        "TID   | Status         | Exit | R/P/F/E | Control | Signal / First Failure",
        "------+----------------+------+---------+---------+----------------------------------------",
    ]
    for r in results:
        note = "-"
        if r.harness_signals:
            note = trunc("; ".join(r.harness_signals[:2]), 65)
        elif r.failures:
            extra = f" (+{len(r.failures) - 1})" if len(r.failures) > 1 else ""
            note = trunc(r.failures[0], 60) + extra
        exit_s = str(r.exit_code) if r.exit_code is not None else "?"
        lines.append(
            f"{r.tid:<5} | {r.status:<14} | {exit_s:<4} | "
            f"{r.ran}/{r.passed}/{r.failed}/{r.errors:<2} | {r.control_status:<7} | {note}"
        )
    if results:
        stems = [Path(r.log_path).stem if r.log_path else r.tid for r in results]
        tids_preview = stems[0] if len(stems) == 1 else f"{stems[0]}..{stems[-1]}"
        log_dir = Path(results[0].log_path).parent.as_posix()
        lines.append(f"logs: {log_dir}/{{{tids_preview}}}.log")
    return "\n".join(lines)


def cmd_round(args: argparse.Namespace) -> int:
    """Execute all tests for round N (or --all) and print compact round table."""
    if args.round is None and not args.all:
        raise SystemExit("[bh.py] ERROR: Specify --round N or --all")

    root, s_dir, sname, cache_dir = resolve_session(args.s, args.root)
    in_fix = bool(args.fix)
    log_suffix = args.log_suffix if args.log_suffix else ("_fix" if in_fix else "")

    if args.cwd:
        cwd = Path(args.cwd).resolve()
    elif in_fix:
        cwd = (s_dir / "sandbox-fix").resolve()
    else:
        cwd = root
    if not cwd.is_dir():
        raise SystemExit(f"[bh.py] ERROR: Execution cwd does not exist: {cwd}")

    search_root = cwd if in_fix else root
    discovered = _discover_round_tests(search_root, s_dir, sname, None if args.all else args.round, in_fix)

    if args.tids:
        wanted = {t.strip() for t in args.tids.split(",") if t.strip()}
        discovered = {k: v for k, v in discovered.items() if k in wanted}

    if not discovered:
        target_label = "all rounds" if args.all else f"round {args.round}"
        raise SystemExit(f"[bh.py] ERROR: No test files found for {target_label} under {search_root}")

    base_env = build_isolated_env(cache_dir)
    py_exe = _find_python_exe(root)
    pytest_ok: Optional[bool] = None
    if any(files[0].suffix.lower() == ".py" for files in discovered.values()):
        pytest_ok = _has_pytest(py_exe, base_env)

    tasks: List[Tuple[str, List[str], Dict[str, str], str]] = []
    for tid, files in discovered.items():
        if args.cmd_template:
            cmd = _expand_cmd_template(args.cmd_template, tid, files, cwd, s_dir, sname, cache_dir)
            extra_env: Dict[str, str] = {"PYTHONPATH": str(cwd)} if in_fix else {}
            runner_name = args.runner
        else:
            cmd, extra_env, runner_name = _build_auto_cmd(
                tid, files, cwd, s_dir, sname, cache_dir, args.runner, py_exe, pytest_ok, base_env
            )
        tasks.append((tid, cmd, extra_env, runner_name))

    def run_one(item: Tuple[str, List[str], Dict[str, str], str]) -> DigestResult:
        tid, cmd, extra_env, runner_name = item
        env = dict(base_env)
        env.update(extra_env)
        log_file = s_dir / "logs" / f"{tid}{log_suffix}.log"
        full_log, _, dur = _execute_to_log(cmd, cwd, env, log_file, int(args.timeout))
        return evaluate_log(
            full_log,
            tid=tid,
            runner=runner_name,
            cmd=cmd,
            log_path=rel_posix(log_file, root),
            duration_s=dur,
        )

    workers = max(1, int(args.parallel))
    results_map: Dict[str, DigestResult] = {}
    if workers == 1 or len(tasks) == 1:
        for item in tasks:
            res = run_one(item)
            results_map[res.tid] = res
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(run_one, item): item[0] for item in tasks}
            for fut in as_completed(futs):
                res = fut.result()
                results_map[res.tid] = res

    ordered = [results_map[item[0]] for item in tasks]
    tag = "ALL" if args.all else str(args.round)
    fix_tag = " (sandbox-fix)" if in_fix else ""
    print(format_round_table(ordered, header=f"[ROUND {tag}{fix_tag}]"))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: log
# ---------------------------------------------------------------------------


def cmd_log(args: argparse.Namespace) -> int:
    """Update line 1 status of S/worklog.md in-place and/or append entry text."""
    _, s_dir, _, _ = resolve_session(args.s, args.root)
    worklog = s_dir / "worklog.md"

    entry_parts: List[str] = []
    if args.entry:
        for item in args.entry:
            if item == "-":
                entry_parts.append(sys.stdin.read())
            else:
                entry_parts.append(item)
    if args.entry_file:
        ef = Path(args.entry_file)
        if not ef.is_file():
            raise SystemExit(f"[bh.py] ERROR: --entry-file not found: {ef}")
        entry_parts.append(ef.read_text(encoding="utf-8", errors="replace"))

    if args.status is None and not entry_parts:
        raise SystemExit("[bh.py] ERROR: Provide --status and/or --entry / --entry-file")

    if worklog.is_file():
        existing = worklog.read_text(encoding="utf-8", errors="replace")
    else:
        existing = "Status: In Progress\n\n# VeriHunt Worklog\n"

    lines = existing.splitlines()
    if not lines:
        lines = ["Status: In Progress"]

    if args.status is not None:
        st = args.status.strip()
        if st.lower().startswith("status:"):
            st = st.split(":", 1)[1].strip()
        lines[0] = f"Status: {st}"

    updated = "\n".join(lines).rstrip("\n") + "\n"
    appended_bytes = 0
    if entry_parts:
        entry_text = "\n".join(p.strip("\r\n") for p in entry_parts if p.strip("\r\n"))
        if entry_text:
            if not updated.endswith("\n\n"):
                updated += "\n"
            block = entry_text + "\n"
            updated += block
            appended_bytes = len(block.encode("utf-8"))

    tmp_file = s_dir / "worklog.md.tmp"
    tmp_file.write_text(updated, encoding="utf-8")
    os.replace(tmp_file, worklog)

    total_lines = len(updated.splitlines())
    print(f"[LOG] {lines[0]} | appended={appended_bytes}B | total_lines={total_lines}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: sandbox
# ---------------------------------------------------------------------------


def _remove_readonly_and_rmtree(path: Path) -> None:
    """Recursively remove directory tree, clearing Windows read-only bits."""
    if not path.exists():
        return

    def on_error(func: Callable, p: str, _exc_info: object) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda fn, p, exc: on_error(fn, p, exc))
    else:
        shutil.rmtree(path, onerror=on_error)


def _compute_sandbox_exclusions(root: Path, extra_excludes: Sequence[str]) -> Tuple[set[str], set[str]]:
    """Return (global_exclude_names, root_only_exclude_names). Never excludes ``vendor``."""
    global_excl = set(SANDBOX_ALWAYS_EXCLUDE)
    root_excl: set[str] = set()

    has_cargo_or_mvn = (root / "Cargo.toml").is_file() or (root / "pom.xml").is_file()
    has_gradle = any(root.glob("build.gradle*"))
    has_dotnet = any(root.glob("*.sln")) or any(root.glob("*.csproj")) or any(root.rglob("*.csproj"))
    has_any_manifest = (
        has_cargo_or_mvn
        or has_gradle
        or has_dotnet
        or (root / "pyproject.toml").is_file()
        or (root / "package.json").is_file()
        or (root / "go.mod").is_file()
        or (root / "composer.json").is_file()
    )

    if has_cargo_or_mvn or has_gradle or not has_any_manifest:
        global_excl.add("target")
    if has_dotnet or not has_any_manifest:
        global_excl.update({"bin", "obj"})
    if has_gradle or (root / "pom.xml").is_file():
        root_excl.update({"build", "out"})

    for ex in extra_excludes:
        ex_clean = ex.strip().strip("/\\")
        if ex_clean and ex_clean != "vendor":
            global_excl.add(ex_clean)

    global_excl.discard("vendor")
    root_excl.discard("vendor")
    return global_excl, root_excl


def _copy_project_tree(root: Path, dest: Path, global_excl: set[str], root_excl: set[str]) -> int:
    """Copy project from ``root`` to ``dest`` respecting exclusions. Returns copied file count."""
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    root_res = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root_res):
        dp = Path(dirpath)
        rel_dir = dp.relative_to(root_res)
        at_root = rel_dir == Path(".")

        filtered_dirs: List[str] = []
        for d in sorted(dirnames):
            if d in global_excl:
                continue
            if at_root and d in root_excl:
                continue
            cand = dp / d
            if cand.is_symlink() and not cand.exists():
                continue
            filtered_dirs.append(d)
        dirnames[:] = filtered_dirs

        out_dir = dest if at_root else (dest / rel_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for fname in sorted(filenames):
            src_f = dp / fname
            dst_f = out_dir / fname
            try:
                if src_f.is_symlink():
                    if not src_f.exists():
                        continue
                    shutil.copy2(src_f, dst_f, follow_symlinks=True)
                else:
                    shutil.copy2(src_f, dst_f)
                copied += 1
            except OSError:
                continue
    return copied


def _is_agent_sandbox_test(filename: str) -> bool:
    if Path(filename).suffix.lower() not in TEST_CODE_EXTS:
        return False
    return bool(
        re.match(r"^bughunt_r\d+_h\d+", filename, re.I)
        or re.match(r"^BugHuntR\d+H\d+", filename, re.I)
        or re.match(r"^test_r\d+_h\d+", filename, re.I)
    )


def _archive_sandbox_artifacts(s_dir: Path) -> Tuple[int, int]:
    """Archive agent-written tests and JVM reports from S/sandbox before deleting it."""
    sandbox_dir = s_dir / "sandbox"
    if not sandbox_dir.is_dir():
        return 0, 0
    archived_tests = 0
    archived_reports = 0
    sb_res = sandbox_dir.resolve()
    build_dirs = frozenset({"target", "build", "out", "bin", "obj", ".gradle"})
    for dirpath, dirnames, filenames in os.walk(sb_res):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", ".venv")]
        dp = Path(dirpath)
        for fname in filenames:
            fp = dp / fname
            rel = fp.relative_to(sb_res)
            rel_posix_s = rel.as_posix()
            in_build_dir = any(p in build_dirs for p in rel.parts[:-1])
            if not in_build_dir and _is_agent_sandbox_test(fname):
                dst = s_dir / "tests" / "sandbox" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fp, dst)
                archived_tests += 1
            elif (
                ("surefire-reports/" in rel_posix_s or "test-results/" in rel_posix_s)
                and "BugHunt" in fname
                and fname.endswith((".txt", ".xml"))
            ):
                dst = s_dir / "logs" / fname
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fp, dst)
                archived_reports += 1
    return archived_tests, archived_reports


def _replicate_tests_to_fix(s_dir: Path, sname: str, fix_dir: Path) -> int:
    """Replicate S/tests and sandbox tests into S/sandbox-fix per SKILL.md Phase 6.3."""
    replicated = 0
    fix_s_dir = fix_dir / ".bughunt" / sname
    for sub in ("tests", "logs", "tmp"):
        (fix_s_dir / sub).mkdir(parents=True, exist_ok=True)
    (fix_dir / ".bughunt" / ".cache").mkdir(parents=True, exist_ok=True)

    tests_dir = s_dir / "tests"
    if tests_dir.is_dir():
        for dirpath, _, filenames in os.walk(tests_dir):
            dp = Path(dirpath)
            rel = dp.relative_to(tests_dir)
            if rel.parts and rel.parts[0] == "sandbox":
                # Archived sandbox tests belong at their original relative path in sandbox-fix
                sub_rel = Path(*rel.parts[1:]) if len(rel.parts) > 1 else Path(".")
                target_dir = fix_dir / sub_rel
            else:
                target_dir = fix_s_dir / "tests" / rel
            target_dir.mkdir(parents=True, exist_ok=True)
            for fname in filenames:
                shutil.copy2(dp / fname, target_dir / fname)
                replicated += 1

    # Also copy live tests from S/sandbox if S/sandbox hasn't been cleaned yet
    sandbox_dir = s_dir / "sandbox"
    if sandbox_dir.is_dir():
        skip_sb = frozenset({".git", "node_modules", "target", "bin", "obj", "build", "out", ".gradle"})
        for dirpath, dirnames, filenames in os.walk(sandbox_dir):
            dirnames[:] = [d for d in dirnames if d not in skip_sb]
            dp = Path(dirpath)
            for fname in filenames:
                if _is_agent_sandbox_test(fname):
                    rel = (dp / fname).relative_to(sandbox_dir)
                    dst = fix_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dp / fname, dst)
                    replicated += 1
    return replicated


def _clean_new_agent_caches(root: Path, diff: Dict[str, List[str]], snap_mode: str) -> List[str]:
    """Delete only newly-created untracked __pycache__ or .pytest_cache outside .bughunt."""
    removed: List[str] = []
    if snap_mode == "git":
        candidates = []
        for ln in diff.get("new_or_changed", []):
            # Only untracked/ignored (?? or !!) — NEVER touch tracked Modified (M) files
            if len(ln) > 3 and ln[:2] in ("??", "!!"):
                p_str = ln[3:].strip().strip('"').replace("\\", "/")
                candidates.append(p_str)
    else:
        candidates = diff.get("added", [])

    for rel_s in candidates:
        parts = [p for p in rel_s.split("/") if p]
        if ".bughunt" in parts:
            continue
        cache_idx = next((i for i, p in enumerate(parts) if p in ("__pycache__", ".pytest_cache")), None)
        if cache_idx is None:
            continue
        target = root / Path(*parts[: cache_idx + 1])
        if target.exists():
            if target.is_dir():
                _remove_readonly_and_rmtree(target)
            else:
                target.unlink(missing_ok=True)
            removed.append(rel_posix(target, root))
    return sorted(set(removed))


def cmd_sandbox(args: argparse.Namespace) -> int:
    """Automate sandbox creation, sandbox-fix setup, and Phase 6 cleanup + cleanliness diff."""
    root, s_dir, sname, cache_dir = resolve_session(args.s, args.root)
    global_excl, root_excl = _compute_sandbox_exclusions(root, args.exclude or [])

    if args.mode == "create":
        sb_dir = s_dir / "sandbox"
        if sb_dir.exists():
            if not args.force:
                raise SystemExit(
                    f"[bh.py] ERROR: {sb_dir} already exists (pass --force to recreate)"
                )
            _remove_readonly_and_rmtree(sb_dir)
        t0 = time.monotonic()
        copied = _copy_project_tree(root, sb_dir, global_excl, root_excl)
        dur = time.monotonic() - t0
        excl_preview = ",".join(sorted(global_excl | root_excl)[:8])
        print(
            f"[SANDBOX create] path={rel_posix(sb_dir, root)} files={copied} "
            f"duration={dur:.2f}s excluded={excl_preview},..."
        )
        return 0

    if args.mode == "fix":
        fix_dir = s_dir / "sandbox-fix"
        if fix_dir.exists():
            if not args.force:
                raise SystemExit(
                    f"[bh.py] ERROR: {fix_dir} already exists (pass --force to recreate)"
                )
            _remove_readonly_and_rmtree(fix_dir)
        t0 = time.monotonic()
        copied = _copy_project_tree(root, fix_dir, global_excl, root_excl)
        replicated = _replicate_tests_to_fix(s_dir, sname, fix_dir)
        dur = time.monotonic() - t0
        print(
            f"[SANDBOX fix] path={rel_posix(fix_dir, root)} files={copied} "
            f"replicated_tests={replicated} duration={dur:.2f}s"
        )
        return 0

    # mode == "clean"
    archived_tests, archived_reports = _archive_sandbox_artifacts(s_dir)
    cleaned: List[str] = []
    for label, target in (
        ("sandbox", s_dir / "sandbox"),
        ("sandbox-fix", s_dir / "sandbox-fix"),
        ("tmp", s_dir / "tmp"),
        (".cache", cache_dir),
    ):
        if target.exists():
            _remove_readonly_and_rmtree(target)
            cleaned.append(label)

    # Read before snapshot & mode
    before_file = s_dir / "logs" / "fs-before.txt"
    mode_file = s_dir / "logs" / ".snapshot-mode"
    snap_mode = mode_file.read_text(encoding="utf-8").strip() if mode_file.is_file() else None
    before_lines = (
        before_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if before_file.is_file()
        else []
    )

    actual_mode, after_lines = take_snapshot(root, forced_mode=snap_mode)
    diff = diff_snapshots(before_lines, after_lines, actual_mode)
    removed_caches = _clean_new_agent_caches(root, diff, actual_mode)
    if removed_caches:
        actual_mode, after_lines = take_snapshot(root, forced_mode=actual_mode)
        diff = diff_snapshots(before_lines, after_lines, actual_mode)

    after_file = s_dir / "logs" / "fs-after.txt"
    after_file.write_text(
        ("\n".join(after_lines) + "\n") if after_lines else "", encoding="utf-8"
    )

    dirty_items: List[str] = []
    for k, items in diff.items():
        if k != "resolved" and k != "removed":
            dirty_items.extend(f"{k}: {it}" for it in items)

    lines = [
        f"[SANDBOX clean] archived_tests={archived_tests} archived_reports={archived_reports} "
        f"removed_dirs=[{', '.join(cleaned) or 'none'}]",
        f"snapshot_mode={actual_mode} auto_removed_caches=[{', '.join(removed_caches) or 'none'}]",
    ]
    if not dirty_items:
        lines.append("cleanliness: CLEAN (0 new/modified files outside .bughunt/)")
    else:
        lines.append(f"cleanliness: DIRTY ({len(dirty_items)} changes outside .bughunt/):")
        for item in dirty_items[:8]:
            lines.append(f"  - {trunc(item, 140)}")
        if len(dirty_items) > 8:
            lines.append(f"  ... (+{len(dirty_items) - 8} more in {rel_posix(after_file, root)})")
    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bh.py",
        description="VeriHunt v2.0 helper CLI: compact workspace, recon, test runner, and log tools.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_init = sub.add_parser("init", help="Initialize .bughunt session, fs-before.txt, and worklog.md")
    p_init.add_argument("--root", default=None, help="Project ROOT directory (default: cwd)")
    p_init.set_defaults(func=cmd_init)

    p_recon = sub.add_parser("recon", help="Emit <=35-line project map starter")
    p_recon.add_argument("--root", default=None, help="Project ROOT directory (default: cwd)")
    p_recon.add_argument("--max-lines", type=int, default=35, help="Max output lines (<=35)")
    p_recon.add_argument("--json", action="store_true", help="Output single-line JSON instead of text")
    p_recon.set_defaults(func=cmd_recon)

    p_run = sub.add_parser("run", help="Run a command with isolation, capture log, and print <=12-line digest")
    p_run.add_argument("--s", required=True, help="Session directory path (e.g. .bughunt/20261115-182000)")
    p_run.add_argument("--tid", required=True, help="Test/log ID (e.g. r1_h2 or baseline)")
    p_run.add_argument("--runner", choices=SUPPORTED_RUNNERS, default="auto", help="Test runner parser")
    p_run.add_argument("--cwd", default=None, help="Working directory override (default: ROOT)")
    p_run.add_argument("--root", default=None, help="Project ROOT override")
    p_run.add_argument("--timeout", type=int, default=600, help="Timeout in seconds (default: 600)")
    p_run.add_argument("--log-suffix", default="", help="Optional suffix for log filename (e.g. _fix)")
    p_run.add_argument("--strict-exit", action="store_true", help="Exit with subprocess return code")
    p_run.add_argument("cmd", nargs=argparse.REMAINDER, help="Command after --")
    p_run.set_defaults(func=cmd_run)

    p_round = sub.add_parser("round", help="Run all discovered tests for round N and print summary table")
    p_round.add_argument("--s", required=True, help="Session directory path")
    p_round.add_argument("--round", type=int, default=None, help="Round number N")
    p_round.add_argument("--all", action="store_true", help="Run all discovered rounds (e.g. in sandbox-fix)")
    p_round.add_argument("--tids", default=None, help="Comma-separated TID subset (e.g. r1_h1,r1_h3)")
    p_round.add_argument("--cmd-template", default=None, help="Command template using {file}, {tid}, etc.")
    p_round.add_argument("--runner", choices=SUPPORTED_RUNNERS, default="auto", help="Runner hint")
    p_round.add_argument("--cwd", default=None, help="Working directory override")
    p_round.add_argument("--fix", action="store_true", help="Run inside S/sandbox-fix and log as <TID>_fix.log")
    p_round.add_argument("--log-suffix", default="", help="Log filename suffix override")
    p_round.add_argument("--root", default=None, help="Project ROOT override")
    p_round.add_argument("--timeout", type=int, default=600, help="Per-test timeout in seconds")
    p_round.add_argument("--parallel", type=int, default=1, help="Parallel worker count (default: 1)")
    p_round.set_defaults(func=cmd_round)

    p_check = sub.add_parser("check", aliases=["digest"], help="Parse existing log(s) without re-running")
    p_check.add_argument("--s", required=True, help="Session directory path")
    p_check.add_argument("--tid", default=None, help="Single TID log to digest")
    p_check.add_argument("--round", type=int, default=None, help="Digest all logs for round N")
    p_check.add_argument("--all", action="store_true", help="Digest all logs in S/logs/")
    p_check.add_argument("--runner", choices=SUPPORTED_RUNNERS, default="auto", help="Runner parser")
    p_check.add_argument("--log-suffix", default="", help="Log filename suffix (e.g. _fix)")
    p_check.add_argument("--root", default=None, help="Project ROOT override")
    p_check.set_defaults(func=cmd_check)

    p_log = sub.add_parser("log", help="Update line 1 Status of S/worklog.md and append entry text")
    p_log.add_argument("--s", required=True, help="Session directory path")
    p_log.add_argument("--status", default=None, help="New line-1 Status text")
    p_log.add_argument("--entry", action="append", default=None, help="Entry text (repeatable; '-' for stdin)")
    p_log.add_argument("--entry-file", default=None, help="Read entry text from file")
    p_log.add_argument("--root", default=None, help="Project ROOT override")
    p_log.set_defaults(func=cmd_log)

    p_sb = sub.add_parser("sandbox", help="Manage S/sandbox, S/sandbox-fix, and Phase 6 cleanup")
    p_sb.add_argument("--s", required=True, help="Session directory path")
    p_sb.add_argument("--mode", required=True, choices=("create", "fix", "clean"), help="Sandbox action")
    p_sb.add_argument("--exclude", action="append", default=[], help="Extra directory names to exclude")
    p_sb.add_argument("--force", action="store_true", help="Overwrite existing sandbox/sandbox-fix")
    p_sb.add_argument("--root", default=None, help="Project ROOT override")
    p_sb.set_defaults(func=cmd_sandbox)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
