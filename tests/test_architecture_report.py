import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import contextlib
import io

from tools.architecture.previous import select_run
from tools.architecture.report import annotation, generate, identity, main


class ArchitectureReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.current = Path(self.temp.name) / 'current'
        self.previous = Path(self.temp.name) / 'previous'
        self.summary = dict(versions={'radon': '6'}, scope=['sample'], modules=2,
            import_edges=1, function_count=1, warnings={'protected-access': 1},
            complexity_ranks={'D': 1}, complex_functions=[])
        self.warning = dict(path='sample\\module.py', line=8, symbol='protected-access',
                            obj='run', message='Access to _state')
        self.block = dict(path='sample/module.py', line=8, kind='Function', rank='D',
                          name='run', complexity=22)
        for directory in (self.current, self.previous):
            directory.mkdir()
            self.write(directory, 'summary.json', self.summary)
            self.write(directory, 'pylint.txt', [self.warning])
            self.write(directory, 'complexity.json', [self.block])
            (directory / 'contracts.txt').write_text('Contracts: 12 kept, 1 broken.')

    def write(self, directory, name, data):
        (directory / name).write_text(json.dumps(data), encoding='utf-8')

    def report(self, **metadata):
        return generate(self.current, self.previous, metadata, {'境界': 'success'})

    def test_comparable_values_and_line_moves(self):
        self.write(self.current, 'pylint.txt', [dict(self.warning, line=80)])
        compact, detail, items, comparison = self.report(available=True)
        self.assertEqual(comparison['metrics']['modules']['delta'], 0)
        self.assertEqual((comparison['added'], comparison['resolved']), (0, 0))
        self.assertIn('12 適合 / 1 不適合', compact)
        self.assertIn('sample/module.py:80', detail)
        self.assertEqual(len(items), 2)

    def test_added_resolved_and_positive_negative_deltas(self):
        changed = dict(self.summary, modules=3, import_edges=0, warnings={})
        self.write(self.current, 'summary.json', changed)
        self.write(self.current, 'pylint.txt', [])
        self.write(self.current, 'complexity.json', [dict(self.block, complexity=23)])
        compact, _, items, comparison = self.report(available=True)
        self.assertEqual((comparison['added'], comparison['resolved']), (1, 2))
        self.assertTrue(items[0]['new'])
        self.assertIn('| modules | 3 | 2 | +1 |', compact)
        self.assertIn('| import_edges | 0 | 1 | -1 |', compact)

    def test_missing_or_incompatible_baseline_is_not_zero(self):
        for metadata in ({}, {'available': True}):
            self.write(self.previous, 'summary.json', dict(self.summary, versions={'radon': '7'}))
            compact, _, _, comparison = self.report(**metadata)
            self.assertFalse(comparison['comparable'])
            self.assertIsNone(comparison['metrics']['modules']['delta'])
            self.assertIn('比較不可', compact)

    def test_missing_previous_detail_keeps_current_report(self):
        (self.previous / 'complexity.json').unlink()
        _, detail, _, comparison = self.report(available=True)
        self.assertFalse(comparison['comparable'])
        self.assertIn('Access to _state', detail)

    def test_annotation_escaping_and_location(self):
        result = annotation(dict(path='sample/a,b.py', line=0, rule='a:b', message='a%\n::error::bad'))
        self.assertIn('file=sample/a%2Cb.py,line=1,title=a%3Ab', result)
        self.assertTrue(result.endswith('a%25%0A::error::bad'))
        with self.assertRaises(ValueError):
            annotation(dict(path='../outside.py', line=1, rule='test', message='test'))

    def test_duplicate_code_embedded_lines_and_trailing_newline_are_not_new(self):
        item = dict(path='sample.py', rule='duplicate-code', name='', message='==sample:[1:9]\nvalue\n')
        moved = dict(item, message='==sample:[2:10]\nvalue')
        self.assertEqual(identity(item), identity(moved))

    def test_select_previous_success_excludes_current_and_future(self):
        runs = [dict(id=i, conclusion=status, event=event) for i, status, event in
                [(12, 'success', 'push'), (11, 'success', 'push'), (10, 'failure', 'push'),
                 (9, 'success', 'pull_request'), (8, 'success', 'push')]]
        self.assertEqual(select_run(runs, 11)['id'], 8)
        self.assertIsNone(select_run(runs, 8))

    def test_publish_caps_annotations_but_preserves_all_details_and_gate_failure(self):
        self.write(self.current, 'pylint.txt', [dict(self.warning, obj=str(i)) for i in range(15)])
        summary_path = Path(self.temp.name) / 'step.md'
        output = io.StringIO()
        with patch('sys.argv', ['report', '--current', str(self.current), '--metadata', str(self.current / 'absent')]), \
                patch.dict('os.environ', {'GITHUB_STEP_SUMMARY': str(summary_path), 'BOUNDARY_OUTCOME': 'failure'}), \
                contextlib.redirect_stdout(output):
            main()
        self.assertEqual(output.getvalue().count('::warning '), 10)
        self.assertEqual(len(json.loads((self.current / 'findings.json').read_text(encoding='utf-8'))), 16)
        self.assertIn('failure', summary_path.read_text(encoding='utf-8'))
        self.assertIn('10 / 16', summary_path.read_text(encoding='utf-8'))

    def test_publish_incomplete_measurement(self):
        (self.current / 'summary.json').unlink()
        with patch('sys.argv', ['report', '--current', str(self.current), '--metadata', str(self.current / 'absent')]), \
                patch.dict('os.environ', {}, clear=True):
            main()
        self.assertIn('計測が完了していません', (self.current / 'report.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
