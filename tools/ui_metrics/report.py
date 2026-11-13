"""Publish comparable operation counts; increases are observations, not gates."""
import argparse
import html
import json
import os
from pathlib import Path


def read(path):
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return None


def valid(data):
    try:
        return (data['status']=='success' and data['schema_version']==1
                and bool(data['suite_revision']) and bool(data['environment']) and bool(data['scenarios'])
                and all(s['metrics'] and s['samples'] and all(
                    type(v['min']) is int and type(v['max']) is int and 0<=v['min']<=v['max']
                    for v in s['metrics'].values()) for s in data['scenarios'].values()))
    except (TypeError,KeyError,AttributeError):return False


def cell(value):return html.escape(str(value)).replace('|','&#124;').replace('\n',' ')


def generate(current, previous, metadata):
    comparison=dict(comparable=False,baseline=metadata,metrics={})
    lines=['# UI操作の処理回数','', '回数の増加は調査の目安です。時間・メモリ使用量の保証ではありません。','']
    if not valid(current):
        comparison['reason']='今回の計測が未完了、または測定ファイルが不正です。'
        return '\n'.join(lines+[comparison['reason']]),comparison
    compatible=metadata.get('available') and valid(previous)
    if compatible:
        compatible=all(current[k]==previous[k] for k in ('schema_version','suite_revision','environment'))
        compatible=compatible and current['scenarios'].keys()==previous['scenarios'].keys()
        compatible=compatible and all(current['scenarios'][s]['metrics'].keys()==previous['scenarios'][s]['metrics'].keys() for s in current['scenarios'])
    comparison['comparable']=bool(compatible)
    comparison['reason']=None if compatible else metadata.get('reason') or '比較元が不足、または計測版・データ・実行環境・測定項目が異なります。'
    lines += [f"現在: commit `{cell(current.get('commit'))}` / run `{cell(current.get('run_id'))}`",
              f"比較元: commit `{cell(metadata.get('sha'))}` / run `{cell(metadata.get('run_id'))}`",'']
    if not compatible:lines+=['比較不可: '+cell(comparison['reason']),'']
    lines+=['| シナリオ / 項目 | 今回（最小〜最大） | 前回 | 差分 |','|---|---:|---:|---:|']
    for scenario,data in current['scenarios'].items():
        for metric,now in data['metrics'].items():
            old=previous['scenarios'][scenario]['metrics'][metric] if compatible else None
            stable=now['min']==now['max'] and old is not None and old['min']==old['max']
            delta=now['min']-old['min'] if stable else None
            key=scenario+'/'+metric
            comparison['metrics'][key]=dict(current=now,previous=old,delta=delta)
            render=lambda v:str(v['min']) if v['min']==v['max'] else f"{v['min']}〜{v['max']}"
            lines.append(f"| {cell(key)} | {render(now)} | {render(old) if old else '—'} | {f'{delta:+d}' if delta is not None else '—'} |")
    lines+=['','実行間で回数が揺れた項目は範囲を表示し、差分を算出しません。']
    return '\n'.join(lines)+'\n',comparison


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--current',default='work/ui-metrics')
    parser.add_argument('--previous',default='work/ui-metrics-previous')
    parser.add_argument('--metadata',default='work/ui-metrics-previous.json');args=parser.parse_args()
    directory=Path(args.current);directory.mkdir(parents=True,exist_ok=True)
    report,comparison=generate(read(directory/'measurement.json'),read(Path(args.previous)/'measurement.json'),
                              read(Path(args.metadata)) or dict(available=False,reason='比較元を取得していません。'))
    (directory/'report.md').write_text(report,encoding='utf-8')
    (directory/'comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as output:output.write(report)
    print(report)


if __name__=='__main__':main()
