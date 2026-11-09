"""扩大候选语料登记与一次边界抽样；只读原库，标准库，无API调用。"""
import argparse,csv,hashlib,json,re,sys,zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

MAIN={'专项制度候选','专项实施过程候选','综合文件含措施线索'}
BORDER={'仅有服务词或形式待核查','相关文件待核查'}

def readcsv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def jsonrows(p):
    with p.open(encoding='utf-8-sig') as f:
        for line in f:
            if line.strip():yield json.loads(line)
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def csvout(p,rows,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def parsed_date(raw):
    raw=str(raw or '').strip()
    # 支持紧凑八位日期；只做格式验证，不代替发布日期核查。
    if re.fullmatch(r'\d{8}',raw):
        try:return datetime.strptime(raw,'%Y%m%d').strftime('%Y-%m-%d')
        except ValueError:return ''
    m=re.fullmatch(r'(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?',raw)
    if m:
        try:return datetime(*map(int,m.groups())).strftime('%Y-%m-%d')
        except ValueError:return ''
    return ''
def flatten_evidence(value):
    """只取现有证据中的文本，不把来源、关键词等元数据拼成条款。"""
    if isinstance(value,str):return [value] if value.strip() else []
    if isinstance(value,list):return [t for item in value for t in flatten_evidence(item)]
    if isinstance(value,dict):
        out=[]
        for k,v in value.items():
            if re.search(r'text|context|sentence|window|excerpt|evidence|片段|正文',k,re.I):out.extend(flatten_evidence(v))
        return out
    return []
def materialize(catalog,core,embedded):
    seen=set();docs=[];duplicates=[]
    for row in catalog:
        key=row['record_key']
        if not key or key in seen:raise ValueError('台账record_key为空或重复')
        seen.add(key)
        if row.get('duplicate_of','').strip():
            duplicates.append(key);continue
        group=row['v02_category'].strip()
        scope='main_candidate' if group in MAIN else 'boundary_pool' if group in BORDER else 'reserve_pool'
        original=str(core.get(key,{}).get('original_text') or '')
        ev=flatten_evidence(embedded.get(key,{}).get('evidence',[]))
        # 保留次序，去掉完全相同证据；不扩展词典。
        ev=list(dict.fromkeys(t.strip() for t in ev if t.strip()))
        status='original_text_available' if original.strip() else 'evidence_only' if ev else 'ledger_preview_only'
        docs.append(dict(record_key=key,title=row.get('title',''),scope=scope,prior_group=group,
            prior_reason=row.get('v02_reason',''),publish_year_raw=row.get('publish_year',''),
            publish_date_raw=row.get('publish_date_raw',''),parsed_calendar_date=parsed_date(row.get('publish_date_raw','')),
            date_review_flag=row.get('date_review_flag',''),quality_flags=row.get('quality_flags',''),
            document_type_hint=row.get('document_type_hint',''),body_type_hint=row.get('body_type_hint',''),
            source_url=row.get('source_url',''),text_status=status,original_chars=len(original),
            evidence_windows=len(ev),evidence_chars=sum(map(len,ev)),
            original_text=original,evidence=ev,ledger_text_preview=row.get('text_preview',''),
            ledger_evidence_preview=row.get('evidence_preview','')))
    return docs,duplicates

def select_review(docs,per_group=8):
    # 七大组各8份；辅助池按原排除原因轮转，避免只抽到占多数的提案答复。
    selected=[]
    for group in sorted({d['prior_group'] for d in docs}):
        candidates=[d for d in docs if d['prior_group']==group]
        buckets={}
        for d in sorted(candidates,key=lambda d:hashlib.sha256(d['record_key'].encode()).hexdigest()):
            buckets.setdefault(d['prior_reason'] or '无原因',[]).append(d)
        group_selected=[]
        while len(group_selected)<per_group and any(buckets.values()):
            for reason in sorted(buckets):
                if buckets[reason] and len(group_selected)<per_group:group_selected.append(buckets[reason].pop(0))
        selected.extend(group_selected)
    result=[]
    for d in selected:
        # 原文仅展示开头；若养老内容很靠后，只能看到预览，明确提示不能判断全文。
        if d['evidence']:
            parts=d['evidence'][:3];excerpt='\n【片段间不一定连续】\n'.join(t[:1000] for t in parts)
            basis='已有措施证据，最多前三段，每段1000字'
        elif d['original_text']:
            excerpt=d['original_text'][:3000];basis='原始正文开头，最多3000字'
        else:
            excerpt=d['ledger_evidence_preview'] or d['ledger_text_preview'];basis='仅台账短预览，不能据此认定全文无关'
        result.append({**{k:d[k] for k in ['record_key','title','scope','prior_group','prior_reason','publish_year_raw','source_url','text_status']},
                       'excerpt_basis':basis,'excerpt':excerpt,'review_document_form':'',
                       'review_service_relevance':'','review_action':'','review_note':''})
    return result

def run(cfg,per_group=8):
    root=Path(cfg['research_root']);source=root/'results/screening_v03'
    inputs={'ledger':source/'screening_ledger_v03.csv',
            'core_texts':root/cfg['baseline_relative']/'core_texts_with_supplements.jsonl',
            'embedded_evidence':source/'embedded_measure_evidence.jsonl'}
    for p in inputs.values():
        if not p.is_file():raise FileNotFoundError(str(p))
    catalog=readcsv(inputs['ledger'])
    required={'record_key','v02_category','duplicate_of'}
    if catalog and not required.issubset(catalog[0]):raise ValueError('台账缺必要字段：'+str(required-set(catalog[0])))
    def keyed(p):
        rows=list(jsonrows(p));result={r['record_key']:r for r in rows}
        if len(rows)!=len(result):raise ValueError('正文或证据record_key重复：'+str(p))
        return result
    core=keyed(inputs['core_texts']);embedded=keyed(inputs['embedded_evidence'])
    ledger_keys={r['record_key'] for r in catalog}
    if (set(core)|set(embedded))-ledger_keys:raise ValueError('正文或证据标识不在台账内')
    docs,duplicates=materialize(catalog,core,embedded)
    review=select_review(docs,per_group)
    out=root/cfg['output_relative'];results=out/'results';logs=out/'logs'
    results.mkdir(parents=True,exist_ok=True);logs.mkdir(parents=True,exist_ok=True)
    table_fields=['record_key','title','scope','prior_group','prior_reason','publish_year_raw','publish_date_raw',
                  'parsed_calendar_date','date_review_flag','quality_flags','document_type_hint','body_type_hint',
                  'source_url','text_status','original_chars','evidence_windows','evidence_chars']
    names=['expanded_registry.csv','expanded_main_candidates.jsonl','expanded_group_counts.csv',
           'expanded_year_counts.csv','expanded_boundary_review.csv','expanded_summary.json']
    existing=[results/n for n in names if (results/n).exists()]
    if existing:
        with zipfile.ZipFile(logs/('previous_expanded_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in existing:z.write(p,p.name)
    csvout(results/names[0],[{k:d[k] for k in table_fields} for d in docs],table_fields)
    with (results/names[1]).open('w',encoding='utf-8') as f:
        for d in docs:
            if d['scope']=='main_candidate':f.write(json.dumps(d,ensure_ascii=False)+'\n')
    counts=Counter((d['scope'],d['prior_group'],d['text_status']) for d in docs)
    groups=[dict(scope=s,prior_group=g,text_status=t,documents=n) for (s,g,t),n in sorted(counts.items())]
    csvout(results/names[2],groups,['scope','prior_group','text_status','documents'])
    annual=Counter((d['scope'],d['prior_group'],d['publish_year_raw'] or '缺失',bool(d['date_review_flag'])) for d in docs)
    years=[dict(scope=s,prior_group=g,database_year=y,date_flagged=int(flag),documents=n) for (s,g,y,flag),n in sorted(annual.items())]
    csvout(results/names[3],years,['scope','prior_group','database_year','date_flagged','documents'])
    rf=['record_key','title','scope','prior_group','prior_reason','publish_year_raw','source_url','text_status',
        'excerpt_basis','excerpt','review_document_form','review_service_relevance','review_action','review_note']
    csvout(results/names[4],review,rf)
    summary=dict(status='completed',created_at=datetime.now().astimezone().isoformat(),input_records=len(catalog),
        excluded_existing_exact_duplicates=len(duplicates),registered_documents=len(docs),
        scope_counts=dict(Counter(d['scope'] for d in docs)),group_counts=dict(Counter(d['prior_group'] for d in docs)),
        main_text_status_counts=dict(Counter(d['text_status'] for d in docs if d['scope']=='main_candidate')),
        review_sample_documents=len(review),sampling='每组按原因轮转，每组最多8份；非比例抽样，不估计总体准确率',
        limitations=['本轮登记候选，不宣告其全部为有效政策。','没有时间截断，没有按质量提示删除记录。',
                    'evidence_only只有旧证据片段，不能当作完整正文；original_text_available也不等于已核实完整。',
                    '登记保留旧分类及待定组，不根据抽样自动恢复或剔除记录。',
                    '抽样片段不足时保留无法判断，不反复追修少量文本。',
                    '日历日期只校验格式；默认20000101仍须按旧日期提示处理。'])
    (results/names[5]).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest=dict(created_at=summary['created_at'],config=cfg,inputs={k:dict(path=str(p),sha256=sha(p)) for k,p in inputs.items()},
                  script_sha256=sha(Path(__file__)),output_sha256={n:sha(results/n) for n in names})
    (logs/'latest_expanded_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    report=out/'return_expanded_corpus.zip'
    with zipfile.ZipFile(report,'w',zipfile.ZIP_DEFLATED) as z:
        for n in names[2:]:z.write(results/n,n)
        z.write(logs/'latest_expanded_manifest.json','latest_expanded_manifest.json')
    print('登记完成：',len(docs),'；主体候选：',summary['scope_counts'].get('main_candidate',0),'；边界样本：',len(review))
    print('主体候选文本及证据保存在本机：',results/names[1])
    print('请传回：',report)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'));a=ap.parse_args()
    run(json.loads(a.config.read_text(encoding='utf-8-sig')))
if __name__=='__main__':
    try:main()
    except Exception as e:print('运行失败：'+str(e),file=sys.stderr);sys.exit(1)
