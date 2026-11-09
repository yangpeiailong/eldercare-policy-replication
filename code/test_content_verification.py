import json,tempfile,unittest,zipfile
from pathlib import Path
from verify_content_findings import standardize,verify,context_check,run
from analyze_overall_content import run as overall_run,lexicon_patterns

LEX={'categories':[dict(name=n,dimension='服务内容',terms=[n]) for n in ['助餐服务','适老改造','智慧养老']]}
def d(k,year=2017,hit=1,form='意见',size='201-800'):
    return dict(record_key=k,title='养老'+form,prior_group='综合文件含措施线索',year=year,
        period='2015-2018' if year<2019 else '2019-2022',date_flagged=0,original_chars=500,
        local_chars=500,body_hash=k,title_form=form,length_bin=size,
        hits={'local_context':{n:hit for n in ['助餐服务','适老改造','智慧养老']}})
class VerificationTests(unittest.TestCase):
    def test_standardization_removes_composition_only_change(self):
        docs=[]
        for year,counts in [(2017,(10,90)),(2021,(90,10))]:
            for hit,count in [(1,counts[0]),(0,counts[1])]:
                docs += [d(str(year)+'_'+str(hit)+'_'+str(i),year,hit,'规划纲要' if hit else '意见') for i in range(count)]
        s,_=standardize(docs,'助餐服务')
        self.assertEqual(s['early_standardized_pct'],50)
        self.assertEqual(s['late_standardized_pct'],50)
        self.assertEqual(s['early_common_support'],100)
    def test_no_common_support_is_blank_not_zero(self):
        s,_=standardize([d('a')],'助餐服务')
        self.assertEqual(s['standardized_difference_pp'],'')
        self.assertEqual(s['eligible_strata'],0)
    def test_leave_out_year_and_exact_dedup(self):
        docs=[d('a',2017),d('b',2021),d('c',2022)]
        docs[2]['body_hash']='b'
        stats,_,_,_=verify(docs)
        r=next(r for r in stats if r['group']=='all_candidates' and r['variant']=='exact_same_body_sensitivity' and r['period']=='2019-2022')
        self.assertEqual(r['documents'],1)
        r=next(r for r in stats if r['group']=='all_candidates' and r['variant']=='leave_out_2021' and r['period']=='2019-2022')
        self.assertEqual(r['documents'],1)
    def test_same_document_different_segments(self):
        _,patterns=lexicon_patterns(LEX)
        ds={'a':d('a'),'b':d('b')}
        records=[dict(record_key='a',original_text='发展养老服务，推进智慧养老与适老改造。'),
                 dict(record_key='b',original_text='发展养老服务和智慧养老。'+'无关事项。'*500+'开展养老服务适老改造。')]
        checks,_,_=context_check(records,patterns,ds)
        self.assertEqual([r['same_local_segment'] for r in checks],[1,0])
    def test_full_run_preserves_previous_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=root/'analysis/results';result.mkdir(parents=True)
            content=root/'content';content.mkdir()
            (content/'lexicon_v01.json').write_text(json.dumps(LEX),encoding='utf-8')
            obj=dict(record_key='a',title='养老意见',scope='main_candidate',prior_group='综合文件含措施线索',
                original_text='开展智慧养老、适老改造和助餐服务。',publish_year_raw='2021',date_review_flag='',quality_flags='',source_url='')
            (result/'connected_main_analysis.jsonl').write_text(json.dumps(obj),encoding='utf-8')
            cfg=dict(research_root=str(root),output_relative='analysis',content_relative='content',
                periods=[[2015,2018,'2015-2018'],[2019,2022,'2019-2022']])
            overall_run(cfg);before=(result/'overall_summary.json').read_bytes()
            run(cfg);run(cfg)
            self.assertEqual((result/'overall_summary.json').read_bytes(),before)
            self.assertEqual(len(list((root/'analysis/logs').glob('previous_verification_*.zip'))),1)
            with zipfile.ZipFile(root/'analysis/return_content_verification.zip') as z:
                self.assertIn('verification_summary.json',z.namelist())
            (content/'lexicon_v01.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'不一致'):run(cfg)
if __name__=='__main__':unittest.main()
