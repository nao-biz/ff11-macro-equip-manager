"""Retrieve the same-branch (or PR base-branch) successful push baseline."""
import json
from pathlib import Path
from tools.architecture.previous import retrieve


def main():
    metadata=retrieve('ui-metrics.yml','ui-operation-metrics',Path('work/ui-metrics-previous'))
    Path('work').mkdir(exist_ok=True)
    Path('work/ui-metrics-previous.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False))


if __name__=='__main__':main()
