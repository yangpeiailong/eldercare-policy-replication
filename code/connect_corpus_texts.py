"""接回已采集正文并生成养老相关局部文本；不联网、不重筛候选。"""
import argparse,csv,hashlib,html,json,re,sys,zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from build_expanded_corpus import readcsv,jsonrows,sha,csvout

# 只用于定位局部分析文本，未命中不会删除文档，也不代表无关。
ANCHOR=re.compile(r'养老服务|养老机构|养老院|敬老院|居家养老|社区养老|医养结合|老年照护|老年人|老人|老龄|老年助餐|养老助餐|家庭养老床位|养老床位|养老设施|高龄津贴|高龄补贴|银发经济|智慧健康养老|健康养老|长期护理|长护险|适老化')

def norm(t):return re.sub(r'\s+','',html.unescape(t or ''))
def source_schema(p):
    try:
        for obj in jsonrows(p):
            return isinstance(obj,dict) and {'record_key','database_text'}.issubset(obj)
    except (OSError,UnicodeError,ValueError):pass
    return False

def source_stats(path,registry):
    seen=set();matched=0;main=0;nonempty=0;title_conflicts=0;duplicate_keys=0;malformed=0
    with path.open(encoding='utf-8-sig') as f:
        for line in f:
            if not line.strip():continue
            try:o=json.loads(line)
            except ValueError:malformed+=1;continue
            if not isinstance(o,dict):malformed+=1;continue
            k=o.get('record_key')
            if k not in registry:continue
            if k in seen:duplicate_keys+=1;continue
            seen.add(k);matched+=1
            if registry[k]['scope']=='main_candidate':main+=1
            if isinstance(o.get('database_text'),str) and o['database_text'].strip():nonempty+=1
            if o.get('title') and norm(o['title'])!=norm(registry[k]['title']):title_conflicts+=1
    return dict(path=str(path),matched_registered_keys=matched,matched_main_keys=main,
                nonempty_database_text_keys=nonempty,title_conflicts=title_conflicts,
                duplicate_keys=duplicate_keys,malformed_lines=malformed)

def locate(root,registry,explicit=None):
    if explicit:
        p=explicit.resolve()
        if not p.is_file() or not source_schema(p):raise ValueError('--input须为包含record_key和database_text的JSONL')
        reports=[source_stats(p,registry)]
    else:
        # 先查采集元数据；若没有覆盖主体的文件，再查其他data目录。
        reports=[];seen=set();needed=sum(r['scope']=='main_candidate' for r in registry.values())
        for base in [root/'data/metadata',root/'data']:
            if not base.exists():continue
            for p in sorted(base.rglob('*.jsonl')):
                if p in seen or 'policy_patterns' in p.parts:continue
                seen.add(p)
                if not source_schema(p):continue
                stat=source_stats(p,registry);reports.append(stat)
                print('校验已有数据入口：',p.name,'；对应主体候选：',stat['matched_main_keys'],flush=True)
            if any(r['matched_main_keys']==needed and not r['title_conflicts'] and not r['duplicate_keys'] and not r['malformed_lines'] for r in reports):break
    usable=[r for r in reports if r['matched_main_keys']>0 and not r['title_conflicts'] and not r['duplicate_keys'] and not r['malformed_lines']]
    if not usable:raise ValueError('未找到通过标识及标题校验的正文源。请用 --input 指定原始完整JSONL；不修改任何数据。')
    usable.sort(key=lambda r:(-r['matched_main_keys'],-r['matched_registered_keys'],-r['nonempty_database_text_keys'],r['path']))
    winner=usable[0]
    ties=[r for r in usable if (r['matched_main_keys'],r['matched_registered_keys'],r['nonempty_database_text_keys'])==(winner['matched_main_keys'],winner['matched_registered_keys'],winner['nonempty_database_text_keys'])]
    # 若并列文件字节不同，不能静默决定哪一版；由用户显式指定。
    if not explicit and len(ties)>1 and len({sha(Path(r['path'])) for r in ties})>1:
        raise ValueError('存在覆盖相同但内容不同的正文源，请用 --input 指定：'+' | '.join(r['path'] for r in ties))
    return Path(winner['path']),reports

def local_segments(text):
    spans=[(m.start(),m.end()) for m in re.finditer(r'[^。！？\r\n]+[。！？]?',text) if m.group().strip()]
    intervals=[]
    for i,(a,b) in enumerate(spans):
        for hit in ANCHOR.finditer(text,a,b):
            # 保留前后相邻句，但每个命中邻域最多约1600字，避免一行超长正文吞入整篇。
            left=max(spans[max(0,i-1)][0],hit.start()-600)
            right=min(spans[min(len(spans)-1,i+1)][1],hit.end()+1000)
            intervals.append((left,right))
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return [dict(start=a,end=b,text=text[a:b]) for a,b in merged]

def run(cfg,explicit=None):
    root=Path(cfg['research_root']);out=root/cfg['output_relative'];results=out/'results';logs=out/'logs'
    registry_path=results/'expanded_registry.csv'
    rows=readcsv(registry_path);registry={r['record_key']:r for r in rows}
    if len(registry)!=len(rows):raise ValueError('登记表record_key重复')
    source,reports=locate(root,registry,explicit)
    print('选定正文源：',source,flush=True)
    # 接回全体登记记录的正文，保留储备池，避免日后重新寻找入口。
    connected={}
    for obj in jsonrows(source):
        k=obj.get('record_key')
        if k not in registry:continue
        value=obj.get('database_text')
        text=value if isinstance(value,str) else ''
        connected[k]=dict(text=text,text_path=obj.get('text_path',''))
    # V05核心正文仅作为主源缺失正文时的补充，不混用附件补充文本。
    corepath=root/cfg['baseline_relative']/'core_texts_with_supplements.jsonl'
    fallback={o['record_key']:o.get('original_text','') for o in jsonrows(corepath)} if corepath.is_file() else {}
    logs.mkdir(parents=True,exist_ok=True)
    names=['connected_registered_texts.jsonl','connected_main_analysis.jsonl','connected_text_catalog.csv',
           'connected_coverage.csv','connected_review_excerpts.csv','connected_summary.json']
    existing=[results/n for n in names if (results/n).exists()]
    if existing:
        with zipfile.ZipFile(logs/('previous_connected_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in existing:z.write(p,p.name)
    catalog=[];samples=[];coverage=Counter();reviewkeys=set()
    reviewpath=results/'expanded_boundary_review.csv'
    if reviewpath.is_file():reviewkeys={r['record_key'] for r in readcsv(reviewpath)}
    with (results/names[0]).open('w',encoding='utf-8') as allfile,(results/names[1]).open('w',encoding='utf-8') as mainfile:
        for r in rows:
            k=r['record_key'];text=connected.get(k,{}).get('text','');origin='database_text'
            if not text.strip() and fallback.get(k,'').strip():text=fallback[k];origin='V05_original_text_fallback'
            if not text.strip():origin='missing_text'
            # 原始正文原样保存；另设解码后的局部文本及其坐标，保持可追溯。
            decoded=html.unescape(text);segments=local_segments(decoded) if text.strip() else []
            state='available' if text.strip() else 'missing'
            meta={**r,'connected_text_status':state,'connected_text_origin':origin,'connected_chars':len(text),
                  'local_segment_count':len(segments),'local_chars':sum(len(s['text']) for s in segments),
                  'connected_body_sha256':hashlib.sha256(text.encode()).hexdigest() if text else '',
                  'anchor_terms_present':int(bool(segments))}
            catalog.append(meta);coverage[(r['scope'],r['prior_group'],state)]+=1
            allfile.write(json.dumps(dict(record_key=k,title=r['title'],scope=r['scope'],prior_group=r['prior_group'],
                         text_status=state,text_origin=origin,original_text=text),ensure_ascii=False)+'\n')
            if r['scope']=='main_candidate':
                analysis=text if r['prior_group']!='综合文件含措施线索' else '\n\n'.join(s['text'] for s in segments)
                mainfile.write(json.dumps(dict(**meta,original_text=text,decoded_local_segments=segments,
                    analysis_text=analysis,analysis_basis='whole_document' if r['prior_group']!='综合文件含措施线索' else 'anchor_local_context',
                    analysis_ready=int(bool(analysis.strip()))),ensure_ascii=False)+'\n')
            if k in reviewkeys:
                excerpt='\n【片段间不一定连续】\n'.join(s['text'][:900] for s in segments[:3]) if segments else decoded[:2000]
                samples.append(dict(record_key=k,title=r['title'],scope=r['scope'],prior_group=r['prior_group'],
                    prior_reason=r['prior_reason'],source_url=r['source_url'],text_status=state,
                    excerpt_basis='锚点局部上下文，最多前三段' if segments else '无锚点或无正文，仅展示开头；不能据此认定无关',
                    excerpt=excerpt,review_note=''))
    fields=list(catalog[0]) if catalog else ['record_key']
    csvout(results/names[2],catalog,fields)
    cov=[dict(scope=s,prior_group=g,text_status=t,documents=n) for (s,g,t),n in sorted(coverage.items())]
    csvout(results/names[3],cov,['scope','prior_group','text_status','documents'])
    csvout(results/names[4],samples,['record_key','title','scope','prior_group','prior_reason','source_url','text_status','excerpt_basis','excerpt','review_note'])
    main=[r for r in catalog if r['scope']=='main_candidate']
    summary=dict(status='completed',selected_source=str(source),registered_documents=len(rows),
        connected_registered_documents=sum(r['connected_text_status']=='available' for r in catalog),
        main_candidate_documents=len(main),connected_main_documents=sum(r['connected_text_status']=='available' for r in main),
        main_without_anchor=sum(not r['anchor_terms_present'] for r in main),review_excerpts=len(samples),
        source_candidates=reports,coverage=cov,
        limitations=['接回的是已采集的数据库正文，不保证已核实完整。','锚点局部文本是分析入口，不是语义确认的养老措施。',
                     '没有依据锚点、篇幅或旧分类新增剔除；未检出锚点的记录仍保留。',
                     '坐标对应HTML实体解码后的正文，原始正文另行原样保存。','旧日期及质量标记保留；未重新抓取或修订。'])
    (results/names[5]).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest=dict(created_at=datetime.now().astimezone().isoformat(),config=cfg,anchor_regex=ANCHOR.pattern,
        inputs={str(p):sha(p) for p in [registry_path,source]+([corepath] if corepath.is_file() else [])},
        script_sha256=sha(Path(__file__)),outputs={n:sha(results/n) for n in names})
    (logs/'latest_connected_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(out/'return_connected_texts.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n in names[3:]:z.write(results/n,n)
        z.write(logs/'latest_connected_manifest.json','latest_connected_manifest.json')
    print('主体候选：',len(main),'；已接回正文：',summary['connected_main_documents'])
    print('全量原文及主体分析文本留在本机；请传回：',out/'return_connected_texts.zip')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    ap.add_argument('--input',type=Path,help='可选：指定包含record_key、database_text的原始JSONL')
    a=ap.parse_args();run(json.loads(a.config.read_text(encoding='utf-8-sig')),a.input)
if __name__=='__main__':
    try:main()
    except Exception as e:print('运行失败：'+str(e),file=sys.stderr);sys.exit(1)
