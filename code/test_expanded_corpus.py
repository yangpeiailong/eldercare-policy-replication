import json,tempfile,unittest,csv,zipfile
from pathlib import Path
from build_expanded_corpus import materialize,select_review,parsed_date,flatten_evidence,run

def row(k,g='综合文件含措施线索',duplicate=''):
    return dict(record_key=k,v02_category=g,duplicate_of=duplicate,title='测试政策',publish_year='2022',
                publish_date_raw='20220228',v02_reason='原筛选原因',text_preview='仅预览',date_review_flag='')

class ExpandedTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(parsed_date('20220228'),'2022-02-28')
        self.assertEqual(parsed_date('20220230'),'')
        self.assertEqual(parsed_date('2022-2-28'),'2022-02-28')
    def test_fragments_are_not_full_text(self):
        ds,_=materialize([row('a')],{}, {'a':dict(evidence=[dict(context='养老条款',source_url='不应拼入正文')])})
        self.assertEqual(ds[0]['text_status'],'evidence_only')
        self.assertEqual(ds[0]['original_chars'],0)
        self.assertEqual(ds[0]['evidence'],['养老条款'])
    def test_preserve_reserve_and_existing_duplicates(self):
        ds,dups=materialize([row('a'),row('b','低相关暂存'),row('c',duplicate='a')],{}, {})
        self.assertEqual(dups,['c'])
        self.assertEqual([d['scope'] for d in ds],['main_candidate','reserve_pool'])
    def test_duplicate_keys_fail(self):
        with self.assertRaises(ValueError):materialize([row('a'),row('a')],{}, {})
    def test_bounded_deterministic_sampling(self):
        ds,_=materialize([row(str(i)) for i in range(20)],{}, {})
        a=select_review(ds)
        self.assertEqual(len(a),8)
        self.assertEqual(a,select_review(list(reversed(ds))))
        self.assertTrue(all('仅台账' in r['excerpt_basis'] for r in a))
    def test_full_run_and_output_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'results/screening_v03';src.mkdir(parents=True)
            with (src/'screening_ledger_v03.csv').open('w',encoding='utf-8',newline='') as f:
                rows=[row('a','专项制度候选'),row('b')]
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            base=root/'baseline';base.mkdir()
            (base/'core_texts_with_supplements.jsonl').write_text(json.dumps(dict(record_key='a',original_text='专项全文')),encoding='utf-8')
            (src/'embedded_measure_evidence.jsonl').write_text(json.dumps(dict(record_key='b',evidence=['综合养老条款'])),encoding='utf-8')
            cfg=dict(research_root=str(root),baseline_relative='baseline',output_relative='analysis')
            output=root/'analysis/results';output.mkdir(parents=True)
            (output/'scope_summary.json').write_text('unchanged')
            run(cfg);run(cfg)
            self.assertEqual((output/'scope_summary.json').read_text(),'unchanged')
            summary=json.loads((output/'expanded_summary.json').read_text())
            self.assertEqual(summary['scope_counts']['main_candidate'],2)
            self.assertEqual(summary['main_text_status_counts'],{'original_text_available':1,'evidence_only':1})
            with zipfile.ZipFile(root/'analysis/return_expanded_corpus.zip') as z:
                self.assertNotIn('expanded_main_candidates.jsonl',z.namelist())
            self.assertEqual(len(list((root/'analysis/logs').glob('previous_expanded_*.zip'))),1)
if __name__=='__main__':unittest.main()
