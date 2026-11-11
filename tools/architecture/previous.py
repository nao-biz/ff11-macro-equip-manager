"""Download data from the preceding successful push measurement, using gh."""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlencode


def select_run(runs, current_id):
    candidates = [r for r in runs if int(r['id']) < current_id
                  and r['conclusion'] == 'success' and r['event'] == 'push']
    return max(candidates, key=lambda r: int(r['id']), default=None)


def gh(*args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True,
                            encoding='utf-8', check=True, timeout=90)
    return result.stdout


def main():
    destination = Path('work/architecture-previous')
    metadata = {'branch': os.environ['BASELINE_BRANCH'], 'available': False}
    try:
        query = urlencode(dict(branch=metadata['branch'], status='success', event='push', per_page=100))
        pages = json.loads(gh('api', '--paginate', '--slurp',
            f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/workflows/architecture.yml/runs?{query}"))
        run = select_run([r for page in pages for r in page['workflow_runs']],
                         int(os.environ['GITHUB_RUN_ID']))
        if run is None:
            metadata['reason'] = '前回の成功したpush計測がありません。'
        else:
            metadata.update(run_id=run['id'], url=run['html_url'], sha=run['head_sha'])
            gh('run', 'download', str(run['id']), '--repo', os.environ['GITHUB_REPOSITORY'],
               '--name', 'architecture-measurements', '--dir', str(destination))
            metadata['available'] = True
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        metadata['reason'] = '前回の計測またはArtifactを取得できませんでした（権限・保存期限・通信を確認）。'
    Path('work').mkdir(exist_ok=True)
    Path('work/architecture-previous.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == '__main__':
    main()
