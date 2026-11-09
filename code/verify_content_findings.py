"""仅验证既有三类议题及一组共现；固定对照，不扩词典、不调用API。"""
import argparse,hashlib,html,json,re,sys,zipfile
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from build_expanded_corpus import jsonrows,sha,csvout
from analyze_overall_content import lexicon_patterns,normalize,mask_books
from connect_corpus_texts import local_segments

FOCUS=['助餐服务','适老改造','智慧养老']
EARLY='2015-2018';LATE='2019-2022'
def title_form(title):
    # 互斥且按固定次序；只是标题形式，不等于法律效力或可执行性。
    if re.search('规划|纲要',title):return '规划纲要'
    if '意见' in title:return '意见'
    if re.search('方案|计划|工作要点|任务分工',title):return '方案计划要点'
    return '其他形式'
def length_bin(n):return '0-200' if n<=200 else '201-800' if n<=800 else '801-2000' if n<=2000 else '2001以上'
def pct(n,d):return round(100*n/d,3) if d else ''
def group_docs(docs,group):return docs if group=='all_candidates' else [d for d in docs if d['prior_group']==group]
def metrics(rows):
    n=len(rows);h={c:sum(d['hits']['local_context'][c] for d in rows) for c in FOCUS}
    both=sum(d['hits']['local_context']['适老改造'] and d['hits']['local_context']['智慧养老'] for d in rows)
    return dict(documents=n,**{c+'_docs':h[c] for c in FOCUS},**{c+'_pct':pct(h[c],n) for c in FOCUS},
                joint_docs=both,joint_pct=pct(both,n),adapt_among_smart_pct=pct(both,h['智慧养老']),
                smart_denominator=h['智慧养老'],small_joint_cell=int(both<10))

def standardize(docs,outcome,min_cell=5):
    # 两时期共同的标题形式×固定篇幅区间，合并样本数作共同权重；不外推无共同支持的文档。
    cells=defaultdict(lambda:{EARLY:[],LATE:[]})
    for d in docs:
        if d['period'] in [EARLY,LATE]:cells[(d['title_form'],d['length_bin'])][d['period']].append(d)
    eligible={k:v for k,v in cells.items() if all(len(v[p])>=min_cell for p in [EARLY,LATE])}
    total=sum(len(v[EARLY])+len(v[LATE]) for v in eligible.values())
    def value(d):
        if outcome=='joint':return int(d['hits']['local_context']['适老改造'] and d['hits']['local_context']['智慧养老'])
        return d['hits']['local_context'][outcome]
    detail=[];rates={EARLY:0.0,LATE:0.0}
    for k,v in sorted(eligible.items()):
        weight=(len(v[EARLY])+len(v[LATE]))/total
        for p in [EARLY,LATE]:
            hits=sum(value(d) for d in v[p]);rates[p]+=weight*hits/len(v[p])
            detail.append(dict(outcome=outcome,title_form=k[0],length_bin=k[1],period=p,
                               documents=len(v[p]),hit_documents=hits,pooled_weight=round(weight,6)))
    summary=dict(outcome=outcome,eligible_strata=len(eligible),total_strata=len(cells),minimum_per_period_per_stratum=min_cell,
        early_total=sum(d['period']==EARLY for d in docs),late_total=sum(d['period']==LATE for d in docs),
        early_common_support=sum(len(v[EARLY]) for v in eligible.values()),late_common_support=sum(len(v[LATE]) for v in eligible.values()),
        early_standardized_pct=round(100*rates[EARLY],3) if total else '',late_standardized_pct=round(100*rates[LATE],3) if total else '',
        standardized_difference_pp=round(100*(rates[LATE]-rates[EARLY]),3) if total else '')
    return summary,detail

def verify(docs):
    for d in docs:
        d['title_form']=title_form(d['title']);d['length_bin']=length_bin(d['local_chars'])
        year=d.get('year')
        d['period']=EARLY if year is not None and 2015<=year<=2018 else LATE if year is not None and 2019<=year<=2022 else 'outside_comparison'
        if not all(c in d['hits']['local_context'] for c in FOCUS):raise ValueError('原结果缺少验证类别')
    stats=[];adjusted=[];details=[];annual=[]
    groups=['all_candidates','专项制度候选','综合文件含措施线索']
    for group in groups:
        base=group_docs(docs,group)
        seen=set();dedup=[]
        for d in sorted(base,key=lambda d:d['record_key']):
            if d['original_chars']<200 or d['body_hash'] not in seen:dedup.append(d)
            if d['original_chars']>=200:seen.add(d['body_hash'])
        variants={'baseline':base,'without_date_flags':[d for d in base if not d['date_flagged']],
                  'exact_same_body_sensitivity':dedup}
        variants.update({'leave_out_'+str(y):[d for d in base if d['year']!=y] for y in range(2015,2023)})
        for variant,rows in variants.items():
            for period in [EARLY,LATE]:
                rs=[d for d in rows if d['period']==period]
                stats.append(dict(group=group,variant=variant,period=period,**metrics(rs)))
            # 标准化只做三个固定口径；逐年留出只看原始率，避免无穷扩展模型。
            if variant in ['baseline','without_date_flags','exact_same_body_sensitivity']:
                for outcome in FOCUS+['joint']:
                    s,dt=standardize(rows,outcome)
                    adjusted.append(dict(group=group,variant=variant,**s))
                    details.extend(dict(group=group,variant=variant,**r) for r in dt)
        for year in range(2011,2023):
            annual.append(dict(group=group,database_year=year,**metrics([d for d in base if d['year']==year])))
    return stats,adjusted,details,annual

def context_check(records,patterns,profiles):
    checks=[];excerpts=[];window_hashes=defaultdict(set)
    for obj in records:
        k=obj['record_key']
        if k not in profiles:raise ValueError('正文与逐文档结果标识不对应')
        d=profiles[k]
        if not (d['hits']['local_context']['适老改造'] and d['hits']['local_context']['智慧养老']):continue
        segments=[mask_books(normalize(s['text'])) for s in local_segments(html.unescape(obj['original_text']))]
        aa=[s for s in segments if patterns['适老改造'].search(s)]
        bb=[s for s in segments if patterns['智慧养老'].search(s)]
        joint=[s for s in segments if patterns['适老改造'].search(s) and patterns['智慧养老'].search(s)]
        hashes=[hashlib.sha256(s.encode()).hexdigest() for s in joint]
        for h in hashes:window_hashes[h].add(k)
        checks.append(dict(record_key=k,title=d['title'],prior_group=d['prior_group'],year=d['year'],
            period=d['period'],title_form=d['title_form'],local_chars=d['local_chars'],
            same_local_segment=int(bool(joint)),joint_segment_count=len(joint),joint_hashes=';'.join(hashes),
            date_flagged=d['date_flagged']))
        # 片段可能跨多句、跨多个事项，明确不认定语义整合。
        if joint:
            chosen=joint[0];ma=patterns['适老改造'].search(chosen);mb=patterns['智慧养老'].search(chosen)
            excerpt=chosen[max(0,min(ma.start(),mb.start())-100):min(len(chosen),max(ma.end(),mb.end())+150)]
            if len(excerpt)>1800:
                excerpt=chosen[max(0,ma.start()-100):ma.end()+150]+'【中间省略，不证明直接联系】'+chosen[max(0,mb.start()-100):mb.end()+150]
        else:
            def near(s,p):
                m=p.search(s);return s[max(0,m.start()-100):m.end()+150]
            excerpt=near(aa[0],patterns['适老改造'])+'【不同局部片段】'+near(bb[0],patterns['智慧养老']) if aa and bb else '原结果与当前抽取不一致，待核对'
        excerpts.append(dict(record_key=k,title=d['title'],prior_group=d['prior_group'],year=d['year'],
            same_local_segment=int(bool(joint)),excerpt=excerpt,caution='局部片段可包含多个事项，仅为共现距离证据'))
    for r in checks:
        r['largest_exact_segment_reuse_docs']=max((len(window_hashes[h]) for h in r.pop('joint_hashes').split(';') if h),default=0)
    reuse=[dict(segment_sha256=h,documents=len(keys),record_keys=';'.join(sorted(keys))) for h,keys in window_hashes.items() if len(keys)>1]
    # 固定按组和距离抽样，每格4条；不只抽联合正例。
    sampled=[]
    for group in sorted({r['prior_group'] for r in excerpts}):
        for proximity in [0,1]:
            options=[r for r in excerpts if r['prior_group']==group and r['same_local_segment']==proximity]
            sampled.extend(sorted(options,key=lambda r:hashlib.sha256(r['record_key'].encode()).hexdigest())[:4])
    return checks,reuse,sampled

def run(cfg):
    root=Path(cfg['research_root']);out=root/cfg['output_relative'];result=out/'results';logs=out/'logs'
    paths=dict(profiles=result/'overall_document_profiles.jsonl',texts=result/'connected_main_analysis.jsonl',
               lexicon=root/cfg['content_relative']/'lexicon_v01.json',previous_manifest=logs/'latest_overall_manifest.json')
    for p in paths.values():
        if not p.is_file():raise FileNotFoundError(str(p))
    prior=json.loads(paths['previous_manifest'].read_text(encoding='utf-8-sig'))
    for p in [paths['texts'],paths['lexicon']]:
        if prior['inputs'].get(str(p))!=sha(p):raise ValueError('正文或词典与上一轮结果不一致，请先重跑整体分析：'+str(p))
    if prior['outputs'].get('overall_document_profiles.jsonl')!=sha(paths['profiles']):raise ValueError('逐文档结果与上轮记录不一致')
    docs=list(jsonrows(paths['profiles']));profiles={d['record_key']:d for d in docs}
    if len(profiles)!=len(docs):raise ValueError('逐文档结果record_key重复')
    print('输入版本核对通过；固定验证助餐、适老改造、智慧养老及后两者共现。',flush=True)
    stats,adjusted,details,annual=verify(docs)
    _,patterns=lexicon_patterns(json.loads(paths['lexicon'].read_text(encoding='utf-8-sig')))
    checks,reuse,evidence=context_check(jsonrows(paths['texts']),patterns,profiles)
    names=['verification_sensitivity.csv','verification_standardized.csv','verification_common_strata.csv',
           'verification_annual_joint.csv','verification_joint_documents.csv','verification_exact_segment_reuse.csv',
           'verification_joint_evidence.csv','verification_summary.json']
    existing=[result/n for n in names if (result/n).exists()]
    if existing:
        with zipfile.ZipFile(logs/('previous_verification_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in existing:z.write(p,p.name)
    tables=[stats,adjusted,details,annual,checks,reuse,evidence]
    empty_fields=[['group','variant','period'],['group','variant','outcome'],['group','variant','outcome'],
                  ['group','database_year'],['record_key','same_local_segment'],['segment_sha256','documents','record_keys'],['record_key','excerpt']]
    for name,rows,fields in zip(names,tables,empty_fields):csvout(result/name,rows,list(rows[0]) if rows else fields)
    summary=dict(status='completed',candidate_documents=len(docs),fixed_comparison=[EARLY,LATE],
        fixed_outcomes=FOCUS+['适老改造与智慧养老共现'],joint_documents=len(checks),
        same_local_segment_documents=sum(r['same_local_segment'] for r in checks),repeated_exact_joint_segments=len(reuse),
        standardized_baseline=[r for r in adjusted if r['variant']=='baseline'],
        limitations=['结果属于探索后验证，未预注册；不作为独立确认性证据。',
                     '共同分层标准化只比较两期均至少5份的标题形式×篇幅层；排除部分样本须同时报告覆盖。',
                     '标题形式与固定篇幅区间只是粗略控制，不能消除年份、地区及政策来源混杂。',
                     '完全同正文或同局部片段敏感性不识别改写转载、政策家族或同源近似文本。',
                     '同一局部片段可包含相邻句和多个事项，不代表语义整合。',
                     '日期采用数据库年份；未检验的2023年以后不据此作趋势结论。',
                     '固定输出全部对照，不根据是否符合预期选择结果。'])
    (result/names[-1]).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest=dict(created_at=datetime.now().astimezone().isoformat(),config=cfg,
        inputs={k:dict(path=str(p),sha256=sha(p)) for k,p in paths.items()},script_sha256=sha(Path(__file__)),
        outputs={n:sha(result/n) for n in names})
    (logs/'latest_verification_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(out/'return_content_verification.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n in names:z.write(result/n,n)
        z.write(logs/'latest_verification_manifest.json','latest_verification_manifest.json')
    print('验证完成；请传回：',out/'return_content_verification.zip')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    a=p.parse_args();run(json.loads(a.config.read_text(encoding='utf-8-sig')))
if __name__=='__main__':
    try:main()
    except Exception as e:print('运行失败：'+str(e),file=sys.stderr);sys.exit(1)
