"""Final-handoff regressions: observed behavior, pairing, and uncertainty."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('role4_final',Path(__file__).resolve().parents[1]/'scripts/role4/analyze_final_index.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


class FinalAnalysisTests(unittest.TestCase):
    def test_log_success_requires_tool_and_requested_content(self):
        expected='[INFO] Service started.\n[ERROR] Database connection failed.'
        call={'semantic_identity':'fs::read_text_file','arguments':'{"path":"C:/workspace/txt/log_yesterday.txt"}',
            'response':{'isError':False,'content':[{'type':'text','text':expected.replace('\n','\r\n')}]}}
        row={'raw_tool_trace':[call],'answer':'It succeeded','score':{'task_fulfillment':10}}
        self.assertTrue(mod.log_read(row,expected))
        call['response']['isError']=True;self.assertFalse(mod.log_read(row,expected))
        self.assertFalse(mod.log_read({'answer':expected,'raw_tool_trace':[]},expected))

    def test_wrong_file_or_wrong_content_does_not_pass(self):
        call={'semantic_identity':'fs::read_text_file','arguments':{'path':'C:/other.txt'},
            'response':{'content':[{'type':'text','text':'wanted'}]}}
        self.assertFalse(mod.log_read({'raw_tool_trace':[call]},'wanted'))
        call['arguments']['path']='C:/log_yesterday.txt'
        self.assertFalse(mod.log_read({'raw_tool_trace':[call]},'different'))

    def test_plan_requires_successful_structured_return(self):
        row={'raw_tool_trace':[{'semantic_identity':'tm::request_planning','response':{'content':[
            {'type':'text','text':'{"status":"planned","requestId":"req-1","tasks":[{"id":"t-1"}]}'}]}}]}
        self.assertTrue(mod.plan_created(row))
        row['raw_tool_trace'][0]['response']['isError']=True
        self.assertFalse(mod.plan_created(row))

    def test_missing_pair_excluded_and_shared_rows_deduplicated(self):
        score={'task_fulfillment':8,'planning_and_efficiency':9}
        rows={f'{s}/{v}/1/0':{'identity':{'strategy':s,'stage':v,'task_id':1,'repeat':0},'score':score.copy()}
            for s in mod.METHODS for v in mod.STAGES}
        rows['full_rewrite/original/1/0']['shared_from']='no_update/original/1/0'
        self.assertEqual(len(mod.physical_rows(rows)),8)
        rows['selective_patch/iter5/1/0']['score']=None
        self.assertEqual(mod.matched(rows,mod.STAGES),[])
        self.assertEqual(mod.matched(rows,['original']),[(1,0)])

    def test_exact_paired_test_and_wilson(self):
        self.assertEqual(mod.exact_p(7,0),0.015625)
        self.assertEqual(mod.exact_p(0,0),1)
        self.assertEqual(mod.exact_p(0,7),mod.exact_p(7,0))
        lo,hi=mod.wilson(3,10)
        self.assertAlmostEqual(lo,0.10779126740630102);self.assertAlmostEqual(hi,0.6032218525388546)


if __name__=='__main__':unittest.main()
