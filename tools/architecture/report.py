"""Publish static measurements without changing the enforced CI gates."""
import argparse
from collections import Counter
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def findings(directory):
    result = []
    for item in read_json(directory / 'pylint.txt'):
        path, line = item['path'].replace('\\', '/'), item['line']
        if item['symbol'] == 'duplicate-code':
            # Pylint attaches global duplicate reports to the last scanned module.
            location = re.search(r'^==([\w.]+):\[(\d+):\d+\]', item['message'], re.MULTILINE)
            if location:
                path, line = location[1].replace('.', '/') + '.py', int(location[2]) + 1
        result.append(dict(path=path, line=line, rule=item['symbol'],
                           name=item['obj'], message=item['message']))
    for item in read_json(directory / 'complexity.json'):
        if item['kind'] != 'Class' and item['rank'] in 'DEF':
            result.append(dict(path=item['path'], line=item['line'], rule='complexity',
                name=item['name'], message=f"{item['name']}: complexity {item['complexity']} ({item['rank']})"))
    return result


def identity(item):
    # Moving a function down the file does not create a new finding.
    message = item['message'].rstrip()
    if item['rule'] == 'duplicate-code':
        # Pylint may quote either source range (including different trailing
        # blank lines/comments). The same participating ranges are one finding.
        ranges = re.findall(r'^==([^\n]+):\[(\d+):(\d+)\]', message, re.MULTILINE)
        if ranges:
            message = str(sorted((module, int(end) - int(start)) for module, start, end in ranges))
    return (item['path'], item['rule'], item['name'], message)


def metrics(summary):
    result = {key: summary[key] for key in ('modules', 'import_edges', 'function_count')}
    result['pylint_total'] = sum(summary['warnings'].values())
    result.update({'pylint/' + k: v for k, v in summary['warnings'].items()})
    result.update({'complexity/' + k: summary['complexity_ranks'].get(k, 0) for k in 'ABCDEF'})
    result['complexity/D+'] = sum(summary['complexity_ranks'].get(k, 0) for k in 'DEF')
    return result


def escape(value, prop=False):
    result = str(value).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    return result.replace(':', '%3A').replace(',', '%2C') if prop else result


def annotation(item):
    path = item['path'].replace('\\', '/')
    if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or ':' in path:
        raise ValueError('Finding path must be repository-relative')
    line = max(1, int(item['line']))
    return (f"::warning file={escape(path, True)},line={line},title={escape(item['rule'], True)}::"
            + escape(item['message']))


def cell(value):
    return html.escape(str(value)).replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')


def generate(current, previous, metadata, gates, repository='', sha=''):
    summary = read_json(current / 'summary.json')
    current_findings = findings(current)
    prior = None
    reason = metadata.get('reason', '比較元を取得していません。')
    if metadata.get('available'):
        try:
            prior = read_json(previous / 'summary.json')
            if any(prior[k] != summary[k] for k in ('versions', 'scope')):
                prior = None
                reason = '計測ツールの版または対象範囲が異なるため比較しません。'
            else:
                prior_findings = findings(previous)
        except (OSError, ValueError, KeyError):
            prior = None
            reason = '比較元の計測ファイルが不足しているか、形式が不正です。'
    comparison = dict(baseline=metadata, comparable=prior is not None, reason=None if prior else reason)
    now = metrics(summary)
    before = metrics(prior) if prior else {}
    comparison['metrics'] = {key: dict(current=now.get(key, 0), previous=before.get(key, 0) if prior else None,
        delta=now.get(key, 0) - before.get(key, 0) if prior else None)
        for key in sorted(now.keys() | before.keys())}
    if prior:
        old_counts = Counter(map(identity, prior_findings))
        new_counts = Counter(map(identity, current_findings))
        comparison['added'] = sum((new_counts - old_counts).values())
        comparison['resolved'] = sum((old_counts - new_counts).values())
        remaining = new_counts - old_counts
        for item in current_findings:
            key = identity(item)
            item['new'] = remaining[key] > 0
            if item['new']:
                remaining[key] -= 1
    current_findings.sort(key=lambda f: (not f.get('new', False), f['rule'], f['path'], f['line']))
    lines = ['# アーキテクチャ計測', '', f'対象コミット: `{sha}`', '',
             '| CI合否条件 | 結果 |', '|---|---|']
    lines.extend(f'| {cell(k)} | {cell(v)} |' for k, v in gates.items())
    lines += ['', '以下の警告・複雑度はレビュー候補です。CIの合否条件とは分けて集計します。', '',
              f"比較ブランチ: {cell(metadata.get('branch', '未指定'))}"]
    if metadata.get('url'):
        lines += [f"比較元: [{cell(metadata.get('sha', '')[:12])}]({metadata['url']})"]
    if not prior:
        lines += ['差分: 比較不可。' + reason]
    else:
        lines += [f"指摘の増減: 新規 {comparison['added']} 件 / 解消 {comparison['resolved']} 件（行番号移動は同一扱い）。"]
    lines += ['', '| 指標 | 今回 | 前回 | 差分 |', '|---|---:|---:|---:|']
    for key, values in comparison['metrics'].items():
        old = values['previous'] if prior else '—'
        delta = f"{values['delta']:+d}" if prior else '—'
        lines.append(f"| {cell(key)} | {values['current']} | {old} | {delta} |")
    contract_text = (current / 'contracts.txt').read_text(encoding='utf-8')
    match = re.search(r'Contracts:\s*(\d+) kept,\s*(\d+) broken', contract_text)
    lines += ['', '全契約（観測用の循環依存検査を含む）: ' +
              (f'{match[1]} 適合 / {match[2]} 不適合。' if match else '詳細はcontracts.txtを参照。'), '',
              f'Annotations: 先頭 {min(10, len(current_findings))} / {len(current_findings)} 件（新規を優先）。',
              '全指摘・依存辺・複雑度・元出力は、この実行の **architecture-measurements** Artifactに保存します。', '',
              '## 複雑度の上位10件', '', '| 関数 | 場所 | 複雑度 | ランク |', '|---|---|---:|---|']
    for item in summary['complex_functions']:
        location = f"{item['path']}:{item['line']}"
        if repository and sha:
            location = f"[{cell(location)}](https://github.com/{repository}/blob/{sha}/{quote(item['path'])}#L{item['line']})"
        lines.append(f"| {cell(item['name'])} | {location} | {item['complexity']} | {item['rank']} |")
    compact = '\n'.join(lines) + '\n'
    lines += ['', '## 全指摘', '', '| 場所 | 規則 | 内容 |', '|---|---|---|']
    lines.extend(f"| {cell(f['path'])}:{f['line']} | {cell(f['rule'])} | {cell(f['message'])} |" for f in current_findings)
    return compact, '\n'.join(lines) + '\n', current_findings, comparison


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--current', type=Path, default=Path('work/architecture-baseline'))
    parser.add_argument('--previous', type=Path, default=Path('work/architecture-previous'))
    parser.add_argument('--metadata', type=Path, default=Path('work/architecture-previous.json'))
    args = parser.parse_args()
    metadata = read_json(args.metadata) if args.metadata.exists() else {}
    gates = {label: os.environ.get(key, '未実行') for label, key in
             [('計測', 'MEASURE_OUTCOME'), ('依存境界', 'BOUNDARY_OUTCOME'), ('保存API', 'API_OUTCOME')]}
    args.current.mkdir(parents=True, exist_ok=True)
    if (args.current / 'summary.json').exists():
        compact, detail, items, comparison = generate(args.current, args.previous, metadata, gates,
            os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('GITHUB_SHA', ''))
        for name, data in [('findings.json', items), ('comparison.json', comparison)]:
            (args.current / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        for item in items[:10]:
            print(annotation(item))
    else:
        compact = detail = '# アーキテクチャ計測\n\n計測が完了していません。計測ステップとArtifactの元出力を確認してください。\n'
    (args.current / 'report.md').write_text(detail, encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(compact)


if __name__ == '__main__':
    main()
