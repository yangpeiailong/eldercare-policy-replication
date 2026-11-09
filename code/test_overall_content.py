import json,tempfile,unittest,zipfile
from pathlib import Path
from analyze_overall_content import prepare,calculate,run,lexicon_patterns

CFG={'periods':[[2011,2014,'2011-2014'],[2015,2018,'2015-2018'],[2019,2022,'2019-2022']]}
LEX={'categories':[{'name':'机构','dimension':'服务任务','terms':['养老机构']},
                   {'name':'补贴','dimension':'支持安排','terms':['补贴']}]}
def doc(k,text,group='综合文件含措施线索',year='2021',flag=''):
    return dict(record_key=k,title='健康行动方案',scope='main_candidate',prior_group=group,
                original_text=text,publish_year_raw=year,date_review_flag=flag,quality_flags='',source_url='')

class OverallTests(unittest.TestCase):
    def test_same_body_same_primary_measure_across_groups(self):
        docs,_,_,_=prepare([doc('a','为老年人提供补贴，建设养老机构。'),
                           doc('b','为老年人提供补贴，建设养老机构。','专项制度候选')],LEX,CFG)
        self.assertEqual(docs[0]['hits'],docs[1]['hits'])
    def test_book_title_mask_and_no_anchor_denominator(self):
        records=[doc('a','参照《养老机构补贴办法》。'),doc('b','普通交通建设安排。')]
        docs,cats,_,_=prepare(records,LEX,CFG)
        self.assertEqual(sum(d['hits']['local_context']['机构'] for d in docs),0)
        cov,_,_,_=calculate(docs,cats,CFG)
        row=next(r for r in cov if r['subset']=='all_candidates' and r['text_basis']=='local_context' and r['period']=='all_years' and r['group']=='all_candidates' and r['category']=='机构')
        self.assertEqual(row['documents'],2)
        self.assertEqual(row['hit_documents'],0)
    def test_pair_counts_and_date_sensitivity(self):
        records=[doc('a','建设养老机构并给予补贴。'),doc('b','建设养老机构。',flag='日期待核查')]
        docs,cats,_,_=prepare(records,LEX,CFG)
        _,pairs,_,_=calculate(docs,cats,CFG)
        rows=[r for r in pairs if r['period']=='all_years' and r['group']=='all_candidates']
        self.assertEqual(rows[0]['documents'],2)
        self.assertEqual(rows[0]['both_docs'],1)
        self.assertEqual(rows[1]['documents'],1)
    def test_unknown_year_and_multilabel_title_clues(self):
        d=doc('a','为老年人提供服务。',year='未知');d['title']='医疗健康产业投资方案'
        docs,_,_,_=prepare([d],LEX,CFG)
        self.assertIsNone(docs[0]['year'])
        self.assertEqual(docs[0]['period'],'outside_configured_periods')
        self.assertIn('医疗健康',docs[0]['title_clues'])
        self.assertIn('产业经济消费',docs[0]['title_clues'])
    def test_invalid_lexicon_and_duplicate_keys_fail(self):
        with self.assertRaises(ValueError):lexicon_patterns({'categories':[{'name':'x','terms':[]}]})
        with self.assertRaises(ValueError):prepare([doc('a','老年人。'),doc('a','老年人。')],LEX,CFG)
    def test_full_run_isolation_and_no_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);results=root/'analysis/results';results.mkdir(parents=True)
            source=results/'connected_main_analysis.jsonl'
            source.write_text(json.dumps(doc('a','建设养老机构并给予补贴。')),encoding='utf-8')
            lex=root/'content';lex.mkdir();lp=lex/'lexicon_v01.json';lp.write_text(json.dumps(LEX),encoding='utf-8')
            before=lp.read_bytes();source_before=source.read_bytes()
            (results/'connected_summary.json').write_text('unchanged')
            cfg={**CFG,'research_root':str(root),'output_relative':'analysis','content_relative':'content'}
            run(cfg);run(cfg)
            self.assertEqual(lp.read_bytes(),before)
            self.assertEqual(source.read_bytes(),source_before)
            self.assertEqual((results/'connected_summary.json').read_text(),'unchanged')
            self.assertEqual(len(list((root/'analysis/logs').glob('previous_overall_*.zip'))),1)
            with zipfile.ZipFile(root/'analysis/return_overall_content.zip') as z:
                self.assertNotIn('overall_document_profiles.jsonl',z.namelist())
if __name__=='__main__':unittest.main()
