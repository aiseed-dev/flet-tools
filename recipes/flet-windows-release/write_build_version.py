# SPDX-License-Identifier: MIT
# Copyright (c) 2026 aiseed-dev
# 雛形: https://github.com/aiseed-dev/flet-tools/tree/main/recipes/flet-windows-release

"""Write the app's version for a build: the git tag is the only source.

CI (windows-app.yml) runs this before building. For a tag ``<prefix>X.Y.Z``
(``app-v0.1.1`` with the default prefix) it writes ``X.Y.Z`` into the
git-ignored file given by ``--out`` and exports ``BUILD_VERSION`` so the step
that builds can pass ``--build-version``. For anything else (a push to a
branch, a manual run) it writes ``0.0.0.dev0+<short sha>`` and exports
nothing. Standard library only, so it runs before anything is installed.

    GITHUB_REF=refs/tags/app-v0.1.1 GITHUB_SHA=... \\
        python tools/write_build_version.py --out src/myapp/_build_version.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_TAG_REF = "refs/tags/"


def version_for(ref: str, sha: str, prefix: str = "app-v") -> tuple[str, bool]:
    """(version, is_release). Raises ValueError for a tag that is not <prefix>X.Y.Z."""
    if ref.startswith(_TAG_REF):
        name = ref[len(_TAG_REF):]
        match = re.fullmatch(re.escape(prefix) + r"(\d+\.\d+\.\d+)", name)
        if not match:
            raise ValueError(f"タグ {name} は {prefix}X.Y.Z（X・Y・Z は数字）の形ではありません")
        return match.group(1), True
    return f"0.0.0.dev0+{sha[:7]}", False


def write_build_version(version: str, path: Path) -> Path:
    path.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    return path


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="git のタグから、組み立てる版を書く")
    parser.add_argument("--out", required=True, type=Path,
                        help="書く先（例: src/myapp/_build_version.py）。.gitignore に入れておく")
    parser.add_argument("--tag-prefix", default="app-v", help="版のタグの頭（既定: app-v）")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    try:
        version, is_release = version_for(
            env.get("GITHUB_REF", ""), env.get("GITHUB_SHA", "0000000"), args.tag_prefix)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    path = write_build_version(version, args.out)
    print(f"{path} に版 {version} を書きました")
    github_env = env.get("GITHUB_ENV")
    if is_release and github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"BUILD_VERSION={version}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
