"""Maintain four generated AI-literature indexes without replacing user prose."""
from __future__ import annotations

import argparse
from pathlib import Path

from reading_common import ReadingError, emit_result, vault_root

START = '<!-- critical-reading:index:start -->'
END = '<!-- critical-reading:index:end -->'
FILTER = 'FROM "vault"\nWHERE type = "literature-note" AND note_origin != "user"'
QUERIES = {
    '文献索引.md': 'TABLE year AS 年份, journal AS 期刊, research_directions AS 方向, status AS 状态\n' + FILTER + '\nSORT year DESC, file.name ASC',
    '研究主题索引.md': 'TABLE rows.file.link AS 文献\n' + FILTER + '\nFLATTEN research_directions AS direction\nGROUP BY direction AS 研究方向\nSORT 研究方向 ASC',
    '研究方法索引.md': 'TABLE article_type AS 类型, model_system AS 模型, perturbation AS 干预, mechanism_axis AS 机制轴\n' + FILTER + '\nSORT model_system ASC, file.name ASC',
    '字段补全检查.md': 'TABLE zotero_key AS Zotero键, pdf_key AS 附件键, fulltext_path AS 全文, personal_note_path AS 个人页\n' + FILTER + '\nWHERE !zotero_key OR !pdf_key OR !fulltext_path OR !personal_note_path OR (research_relevance = "相关" AND !research_directions)\nSORT file.name ASC',
}


def plan(root):
    changes, warnings = {}, []
    for name, query in QUERIES.items():
        path = root / 'vault/_index' / name
        resolved = path.resolve()
        if not resolved.is_relative_to((root / 'vault').resolve()) or not resolved.is_relative_to(root.resolve()):
            raise ReadingError('Index path escapes the vault layer')
        block = START + '\n```dataview\n' + query + '\n```\n' + END
        if path.exists():
            text = path.read_text(encoding='utf-8-sig')
            if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
                warnings.append(f'Unmanaged existing index preserved; review/explicitly adapt its query: vault/_index/{name}')
                continue
            text = text[:text.index(START)] + block + text[text.index(END) + len(END):]
        else:
            text = '# ' + name[:-3] + '\n\n仅统计AI文献精读；全文、个人想法和Knowledge不重复计数。\n\n' + block + '\n'
        content = text.encode('utf-8')
        if not path.exists() or path.read_bytes() != content:
            changes[path] = content
    return changes, warnings


def refresh(root, dry_run=False):
    changes, warnings = plan(root)
    if not dry_run:
        for path, content in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return {'status': 'dry-run' if dry_run else 'updated' if changes else 'unchanged',
        'changed': [p.relative_to(root).as_posix() for p in changes], 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        emit_result(refresh(vault_root(args.vault), args.dry_run), True)
        return 0
    except (OSError, ReadingError) as exc:
        emit_result({'status': 'failed', 'errors': [str(exc)]}, True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
