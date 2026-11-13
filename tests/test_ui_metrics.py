"""Measurement comparison and CI baseline selection contracts."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from tools.ui_metrics.report import generate
from tools.architecture.previous import retrieve


def sample(count=2):
    return dict(status='success',schema_version=1,suite_revision='suite1',environment={'tk':'8.6'},
                scenarios={'paste':dict(samples=[{'workers':count}],metrics={'workers':dict(min=count,max=count)})})


class MetricsReportTests(unittest.TestCase):
    def test_positive_and_negative_differences(self):
        for old,delta in ((1,1),(3,-1),(2,0)):
            report,result=generate(sample(),sample(old),dict(available=True,sha='abc',run_id=12))
            self.assertTrue(result['comparable'])
            self.assertEqual(result['metrics']['paste/workers']['delta'],delta)
            self.assertIn(f'{delta:+d}',report)
            self.assertIn('abc',report)

    def test_missing_invalid_or_changed_baseline_is_not_zero(self):
        variants=[None,{},dict(status='failed')]
        for key,value in [('suite_revision','suite2'),('environment',{'tk':'9'}),('schema_version',2),('scenarios',{})]:
            changed=sample();changed[key]=value;variants.append(changed)
        for previous in variants:
            report,result=generate(sample(),previous,dict(available=True))
            self.assertFalse(result['comparable'])
            self.assertIsNone(result['metrics']['paste/workers']['previous'])
            self.assertIsNone(result['metrics']['paste/workers']['delta'])
            self.assertIn('比較不可',report)

    def test_unstable_samples_and_failed_measurement(self):
        current=sample();current['scenarios']['paste']['metrics']['workers']['max']=3
        report,result=generate(current,sample(),dict(available=True))
        self.assertIn('2〜3',report)
        self.assertIsNone(result['metrics']['paste/workers']['delta'])
        report,result=generate(dict(status='failed'),sample(),{})
        self.assertIn('未完了',report);self.assertFalse(result['metrics'])

    def test_workflow_and_artifact_are_selected_and_current_run_excluded(self):
        runs=[dict(id=i,conclusion='success',event='push',head_sha=str(i),html_url='url') for i in (10,20,30)]
        with patch.dict(os.environ,BASELINE_BRANCH='main',GITHUB_REPOSITORY='owner/repo',GITHUB_RUN_ID='20'), \
             patch('tools.architecture.previous.gh',side_effect=[json.dumps([{'workflow_runs':runs}]),'']) as gh:
            result=retrieve('ui-metrics.yml','ui-operation-metrics',Path('work/unused'))
        self.assertEqual(result['run_id'],10)
        self.assertTrue(result['available'])
        self.assertIn('ui-metrics.yml/runs?',gh.call_args_list[0].args[-1])
        self.assertIn('ui-operation-metrics',gh.call_args_list[1].args)

    def test_failed_download_has_no_baseline(self):
        with patch.dict(os.environ,BASELINE_BRANCH='main',GITHUB_REPOSITORY='owner/repo',GITHUB_RUN_ID='20'), \
             patch('tools.architecture.previous.gh',side_effect=subprocess.TimeoutExpired('gh',90)) as gh:
            result=retrieve('ui-metrics.yml','ui-operation-metrics',Path('work/unused'))
        self.assertFalse(result['available'])
        gh.assert_called_once()


@unittest.skipUnless(os.environ.get('FF11_RUN_INTEGRATION')=='1','Synthetic Tk measurements')
class MeasurementTests(unittest.TestCase):
    def test_scenarios_repeat_and_include_registered_callbacks(self):
        from tools.ui_metrics.measure import measure
        result=measure(2)
        self.assertEqual(len(result['scenarios']),4)
        for data in result['scenarios'].values():
            self.assertEqual(len(data['samples']),2)
            for key,bounds in data['metrics'].items():
                self.assertEqual(bounds,dict(min=min(s[key] for s in data['samples']),
                                             max=max(s[key] for s in data['samples'])))
        self.assertGreaterEqual(result['scenarios']['navigation']['metrics']['workspace_rebuilds']['min'],3)
        self.assertGreaterEqual(result['scenarios']['palette_transfer']['metrics']['worker_calls']['min'],2)
