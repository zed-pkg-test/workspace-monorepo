#!/usr/bin/env python3
"""Enforce the permanent infrastructure/application repository boundary.

Policy: repo-boundary/infra-not-app-submodule/v1

An infrastructure repository must remain independent from application monorepos.
A Git submodule whose remote repository is named ``*-infra`` (including the
observed ``.infra`` and ``_infra`` spellings) is forbidden anywhere in a
monorepo. An infrastructure-looking path is also forbidden beneath ``apps/``.

A missing .gitmodules file is conforming. Invalid .gitmodules syntax fails
closed with exit status 2. Policy violations use exit status 1.
"""

from __future__ import annotations

import argparse
import configparser
import dataclasses
import json
import pathlib
import re
import sys
from typing import Iterable, Sequence
from urllib.parse import urlsplit

POLICY_ID = "repo-boundary/infra-not-app-submodule/v1"
_INFRA_NAME = re.compile(r"(?:^|[-._])infra$", re.IGNORECASE)


@dataclasses.dataclass(frozen=True, order=True)
class Violation:
    source: str
    section: str
    path: str
    url: str
    remote_repository: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


class GitmodulesError(ValueError):
    """Raised when a .gitmodules file cannot be validated safely."""


def _looks_like_infra(name: str) -> bool:
    value = name.strip().rstrip("/")
    if value.lower().endswith(".git"):
        value = value[:-4]
    return bool(_INFRA_NAME.search(value))


def remote_repository_name(url: str) -> str:
    """Return the repository basename from HTTPS, SSH, SCP, or relative URLs."""
    value = url.strip().rstrip("/")
    if not value:
        return ""

    if "://" in value:
        path = urlsplit(value).path
    elif re.match(r"^[^/\\]+@[^:]+:", value):
        # SCP-like Git syntax: git@github.com:owner/repository.git
        path = value.split(":", 1)[1]
    else:
        # Relative URLs and local paths are valid in .gitmodules.
        path = value.split("?", 1)[0].split("#", 1)[0]

    leaf = pathlib.PurePosixPath(path.replace("\\", "/")).name
    if leaf.lower().endswith(".git"):
        leaf = leaf[:-4]
    return leaf


def _normalized_path(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/")


def scan_text(text: str, *, source: str = ".gitmodules") -> list[Violation]:
    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
        delimiters=("=",),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,
        empty_lines_in_values=False,
    )
    parser.optionxform = str.lower

    try:
        parser.read_string(text, source=source)
    except configparser.Error as exc:
        raise GitmodulesError(f"{source}: invalid git config: {exc}") from exc

    violations: list[Violation] = []
    for section in parser.sections():
        if not section.lower().startswith("submodule "):
            continue

        path = _normalized_path(parser.get(section, "path", fallback=""))
        url = parser.get(section, "url", fallback="").strip()
        if not path or not url:
            missing = "path" if not path else "url"
            raise GitmodulesError(f"{source}: {section!r} is missing required {missing}")

        remote = remote_repository_name(url)
        parts = pathlib.PurePosixPath(path).parts
        path_leaf = parts[-1] if parts else ""
        under_apps = bool(parts) and parts[0].lower() == "apps"

        reasons: list[str] = []
        if _looks_like_infra(remote):
            reasons.append(
                f"remote repository {remote!r} identifies an infrastructure repository"
            )
        if under_apps and _looks_like_infra(path_leaf):
            reasons.append(f"apps path {path!r} identifies infrastructure")

        if reasons:
            violations.append(
                Violation(
                    source=source,
                    section=section,
                    path=path,
                    url=url,
                    remote_repository=remote,
                    reasons=tuple(reasons),
                )
            )

    return sorted(violations)


def scan_file(path: pathlib.Path) -> list[Violation]:
    if not path.exists():
        return []
    if not path.is_file():
        raise GitmodulesError(f"{path}: expected a regular file")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise GitmodulesError(f"{path}: cannot read UTF-8 content: {exc}") from exc
    return scan_text(text, source=str(path))


def _text_report(paths: Sequence[pathlib.Path], violations: Sequence[Violation]) -> str:
    if not violations:
        rendered = ", ".join(str(path) for path in paths)
        return f"OK {POLICY_ID}: {rendered}"

    lines = [
        f"ERROR {POLICY_ID}: {len(violations)} forbidden infrastructure submodule(s)"
    ]
    for item in violations:
        lines.append(
            f"- {item.source}: [{item.section}] path={item.path!r} "
            f"url={item.url!r}; {'; '.join(item.reasons)}"
        )
    lines.append(
        "Infrastructure and application code must remain in separate repositories; "
        "remove the .gitmodules entry and the gitlink from the monorepo."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        type=pathlib.Path,
        default=[pathlib.Path(".gitmodules")],
        help=".gitmodules files to inspect (default: ./.gitmodules)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable report",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths: list[pathlib.Path] = args.files or [pathlib.Path(".gitmodules")]
    findings: list[Violation] = []

    try:
        for path in paths:
            findings.extend(scan_file(path))
    except GitmodulesError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "policy_id": POLICY_ID,
                        "ok": False,
                        "error": str(exc),
                        "violations": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"ERROR {POLICY_ID}: {exc}", file=sys.stderr)
        return 2

    findings.sort()
    if args.json:
        print(
            json.dumps(
                {
                    "policy_id": POLICY_ID,
                    "ok": not findings,
                    "files": [str(path) for path in paths],
                    "violations": [item.as_dict() for item in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(_text_report(paths, findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
