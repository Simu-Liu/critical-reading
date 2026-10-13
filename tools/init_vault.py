"""Safely create the canonical empty ResearchVault structure and local config."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from config import REPO_ROOT

DIRECTORIES = (
    "knowledge", "knowledge/.meta/claims", "knowledge/.meta/gaps",
    "knowledge/_index", "knowledge/.meta/critical-reading", "vault", "vault/_index", "fulltext", "Notes",
    "templates", "templates/知识库模板",
)
TEMPLATES = (
    ("templates/critical-reading-template.md", "templates/critical-reading-template.md"),
    ("templates/personal-reading-template.md", "templates/personal-reading-template.md"),
    ("templates/知识库模板/README_知识库模板说明.md", "templates/知识库模板/README_知识库模板说明.md"),
    ("templates/知识库模板/主题模板.md", "templates/知识库模板/主题模板.md"),
    ("templates/知识库模板/概念模板.md", "templates/知识库模板/概念模板.md"),
    ("templates/知识库模板/方法模板.md", "templates/知识库模板/方法模板.md"),
    ("templates/知识库模板/关系模板.md", "templates/知识库模板/关系模板.md"),
    ("templates/知识库模板/争议模板.md", "templates/知识库模板/争议模板.md"),
    ("templates/知识库模板/综合模板.md", "templates/知识库模板/综合模板.md"),
)


def initialize(root: Path, config_path: Path | None = None) -> list[str]:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for relative in DIRECTORIES:
        target = root / relative
        if not target.exists():
            target.mkdir(parents=True)
            created.append(f"directory: {target}")
    for source_rel, target_rel in TEMPLATES:
        source, target = REPO_ROOT / source_rel, root / target_rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            created.append(f"template: {target}")
    destination = config_path or REPO_ROOT / "config.toml"
    if not destination.exists():
        example = (REPO_ROOT / "config.example.toml").read_text(encoding="utf-8")
        example = example.replace('vault_root = ""', f'vault_root = "{root.as_posix()}"')
        destination.write_text(example, encoding="utf-8")
        created.append(f"config: {destination}")
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, required=True, help="path for the new or existing Vault")
    parser.add_argument("--config", type=Path, help="local config output (created only when missing)")
    args = parser.parse_args()
    for item in initialize(args.vault_root, args.config):
        print(f"CREATED {item}")
    print("PASS: existing files were preserved; only missing directories, templates and config were created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
