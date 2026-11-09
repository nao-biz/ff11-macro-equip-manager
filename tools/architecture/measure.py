"""Reproducible static baseline; observations are not a proof of cohesion."""
from pathlib import Path
import os
import sys
import json
import subprocess
from collections import Counter
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT/'work/architecture-tools'
sys.path[:0] = [str(TOOLS), str(ROOT)]
import grimp
from radon.complexity import cc_visit, cc_rank


def main():
    output = ROOT/'work/architecture-baseline'
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(TOOLS),str(ROOT))),
               PYLINTHOME=str(output/'pylint-cache'), PYTHONDONTWRITEBYTECODE='1')
    commands = {
        'pylint': ['-m','pylint','ff11reader','spec_manager','--disable=all',
                   '--enable=protected-access,cyclic-import,too-many-instance-attributes,too-many-public-methods,too-many-branches,too-many-statements,duplicate-code',
                   '--output-format=json','--reports=n','--score=n','--persistent=n'],
        'contracts': ['-c','from importlinter.cli import lint_imports_command; lint_imports_command()',
                      '--config','tools/architecture/contracts.ini','--no-cache','--no-logo'],
    }
    statuses = {}
    for name, args in commands.items():
        result = subprocess.run([sys.executable,'-X','utf8',*args],cwd=ROOT,env=env,
                                capture_output=True,text=True,encoding='utf-8')
        (output/(name+'.txt')).write_text(result.stdout,encoding='utf-8')
        (output/(name+'-stderr.txt')).write_text(result.stderr,encoding='utf-8')
        statuses[name] = result.returncode
    warnings = json.loads((output/'pylint.txt').read_text(encoding='utf-8'))
    if 'Contracts:' not in (output/'contracts.txt').read_text(encoding='utf-8'):
        raise RuntimeError('Import Linter could not complete; inspect raw output')
    if any(w['type'] in ('fatal','error') for w in warnings):
        raise RuntimeError('Pylint could not complete; inspect raw output')
    graph = grimp.build_graph('ff11reader','spec_manager',cache_dir=None)
    modules = sorted(graph.modules)
    edges = [(m,n) for m in modules for n in sorted(graph.find_modules_directly_imported_by(m))]
    incoming = Counter(n for m,n in edges)
    outgoing = Counter(m for m,n in edges)
    blocks = []
    for package in ('ff11reader','spec_manager'):
        for path in sorted((ROOT/package).rglob('*.py')):
            for block in cc_visit(path.read_text(encoding='utf-8-sig')):
                for item in ([block]+list(getattr(block,'methods',()))):
                    blocks.append(dict(path=path.relative_to(ROOT).as_posix(),line=item.lineno,
                        name=item.fullname,complexity=item.complexity,rank=cc_rank(item.complexity),
                        kind=type(item).__name__))
    blocks = list({(b['path'],b['line'],b['name'],b['kind']):b for b in blocks}.values())
    functions = [b for b in blocks if b['kind']!='Class']
    summary = dict(
        versions={name:version(name) for name in ('import-linter','grimp','pylint','radon')},
        scope=['ff11reader','spec_manager'], modules=len(modules), import_edges=len(edges),
        tool_exit_codes=statuses, warnings=dict(Counter(w['symbol'] for w in warnings)),
        protected_access_files=Counter(w['path'] for w in warnings if w['symbol']=='protected-access').most_common(10),
        function_count=len(functions), complexity_ranks=dict(Counter(b['rank'] for b in functions)),
        complex_functions=sorted(functions,key=lambda b:-b['complexity'])[:10],
        highest_fan_out=outgoing.most_common(10),highest_fan_in=incoming.most_common(10))
    (output/'imports.json').write_text(json.dumps(edges,indent=2),encoding='utf-8')
    (output/'complexity.json').write_text(json.dumps(blocks,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=False))


if __name__=='__main__': main()
