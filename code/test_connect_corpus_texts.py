import csv,json,tempfile,unittest,zipfile
from pathlib import Path
from connect_corpus_texts import local_segments,locate,run

class ConnectTests(unittest.TestCase):
    def test_local_context_and_offsets(self):
        text='其他内容。前一句说明。建设社区养老服务中心。后一句说明。后续无关内容。'
        spans=local_segments(text)
        self.assertEqual(len(spans),1)
        self.assertIn('前一句说明',spans[0]['text'])
        self.assertNotIn('后续无关',spans[0]['text'])
        self.assertEqual(text[spans[0]['start']:spans[0]['end']],spans[0]['text'])
    def test_long_line_and_no_anchor(self):
        text='甲'*3000+'提供养老服务'+'乙'*3000
        self.assertLess(len(local_segments(text)[0]['text']),1700)
        self.assertEqual(local_segments('仅有重度残疾人护理补贴。'),[])
    def test_source_selection_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'data/metadata';p.mkdir(parents=True)
            reg={'a':dict(title='甲',scope='main_candidate'),'b':dict(title='乙',scope='main_candidate')}
            (p/'partial.jsonl').write_text(json.dumps(dict(record_key='a',title='甲',database_text='正文')),encoding='utf-8')
            full=p/'full.jsonl'
            full.write_text('\n'.join(json.dumps(dict(record_key=k,title=v['title'],database_text='正文')) for k,v in reg.items()),encoding='utf-8')
            winner,_=locate(root,reg)
            self.assertEqual(winner,full)
            (p/'conflict.jsonl').write_text(full.read_text()+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'覆盖相同'):locate(root,reg)
            self.assertEqual(locate(root,reg,full)[0],full.resolve())
    def test_title_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'source.jsonl';p.write_text(json.dumps(dict(record_key='a',title='错误标题',database_text='正文')),encoding='utf-8')
            with self.assertRaises(ValueError):locate(Path(tmp),{'a':dict(title='甲',scope='main_candidate')},p)
    def test_full_run_keeps_no_anchor_and_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);meta=root/'data/metadata';meta.mkdir(parents=True)
            rows=[dict(record_key='a',title='专项',scope='main_candidate',prior_group='专项制度候选',prior_reason='',source_url=''),
                  dict(record_key='b',title='综合',scope='main_candidate',prior_group='综合文件含措施线索',prior_reason='',source_url=''),
                  dict(record_key='c',title='储备',scope='reserve_pool',prior_group='低相关暂存',prior_reason='',source_url='')]
            original=[dict(record_key='a',title='专项',database_text='养老服务&nbsp;安排。'),
                      dict(record_key='b',title='综合',database_text='重度残疾人护理补贴。'),
                      dict(record_key='c',title='储备',database_text='为老年人提供社区照护。')]
            src=meta/'full.jsonl';src.write_text('\n'.join(json.dumps(r) for r in original),encoding='utf-8')
            before=src.read_bytes();output=root/'analysis/results';output.mkdir(parents=True)
            for filename in ['expanded_registry.csv','expanded_boundary_review.csv']:
                with (output/filename).open('w',encoding='utf-8',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            cfg=dict(research_root=str(root),output_relative='analysis',baseline_relative='baseline')
            run(cfg);run(cfg)
            values=[json.loads(s) for s in (output/'connected_main_analysis.jsonl').read_text().splitlines()]
            self.assertEqual(len(values),2)
            self.assertEqual(values[0]['original_text'],original[0]['database_text'])
            self.assertEqual(values[1]['analysis_ready'],0)
            self.assertEqual(src.read_bytes(),before)
            self.assertEqual(len(list((root/'analysis/logs').glob('previous_connected_*.zip'))),1)
            with zipfile.ZipFile(root/'analysis/return_connected_texts.zip') as z:
                self.assertNotIn('connected_registered_texts.jsonl',z.namelist())
if __name__=='__main__':unittest.main()
