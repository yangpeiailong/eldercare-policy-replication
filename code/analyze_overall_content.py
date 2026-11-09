"""扩大语料的整体内容探索：复用旧词典，文档提及及共现，不推断落实或因果。"""
import argparse,hashlib,html,json,re,sys,zipfile
from collections import Counter
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import median
from build_expanded_corpus import jsonrows,sha,csvout
from connect_corpus_texts import local_segments

TITLE_CLUES={
 '医疗健康':'医疗|卫生|健康|医药',
 '土地住房建设':'土地|国土|住房|城乡建设|小区改造|城市更新|用地',
 '产业经济消费':'产业|经济|消费|服务业|营商|投资|市场|旅游',
 '农村乡村发展':'农村|乡村|农业|扶贫|脱贫',
 '民政救助福利':'民政|救助|低保|最低生活保障|福利|特困',
 '教育就业人才':'教育|就业|人才|职业|培训',
 '综合发展规划':'国民经济|社会发展|政府工作|为民办实事',
 '标准质量安全':'标准|质量|安全|监管|监督'}

def normalize(text):return re.sub(r'\s+','',html.unescape(text or ''))
def mask_books(text):return re.sub(r'《[^》]{0,300}》',lambda m:' '*len(m.group()),text)
def rate(n,d):return round(n/d*100,2) if d else ''
def lexicon_patterns(lexicon):
    cats=lexicon.get('categories',[])
    if not cats:raise ValueError('旧词典缺少categories')
    names=[c['name'] for c in cats]
    if len(names)!=len(set(names)):raise ValueError('词典类别名重复')
    patterns={}
    for c in cats:
        if not isinstance(c.get('terms'),list) or not c['terms'] or not all(isinstance(t,str) and t for t in c['terms']):
            raise ValueError('词典类别terms须为非空字符串列表：'+c['name'])
        patterns[c['name']]=re.compile('|'.join(re.escape(t) for t in sorted(set(c['terms']),key=lambda t:(-len(t),t))))
    return cats,patterns

def prepare(records,lexicon,cfg):
    cats,patterns=lexicon_patterns(lexicon);docs=[];keys=set();examples={}
    for obj in records:
        key=obj['record_key']
        if key in keys:raise ValueError('正文记录record_key重复')
        keys.add(key)
        if obj.get('scope')!='main_candidate':raise ValueError('主体分析文件混入非主体范围')
        raw=obj.get('original_text') or ''
        if not isinstance(raw,str):raise ValueError('original_text不是字符串')
        decoded=html.unescape(raw)
        segments=local_segments(decoded)
        # 每个片段分别匹配，防止拼接后跨片段构造出关键词。
        local=[mask_books(normalize(s['text'])) for s in segments]
        full=mask_books(normalize(raw))
        hit_local={n:int(any(p.search(s) for s in local)) for n,p in patterns.items()}
        hit_whole={n:int(bool(p.search(full))) for n,p in patterns.items()}
        value=str(obj.get('publish_year_raw') or '').strip()
        year=int(value) if re.fullmatch(r'(?:19|20)\d{2}',value) else None
        period=next((label for lo,hi,label in cfg['periods'] if year is not None and lo<=year<=hi),'outside_configured_periods')
        title=obj.get('title','');group=obj['prior_group']
        clues=[name for name,exp in TITLE_CLUES.items() if re.search(exp,title)] if group=='综合文件含措施线索' else []
        if group=='综合文件含措施线索' and not clues:clues=['综合标题未分类']
        doc=dict(record_key=key,title=title,prior_group=group,year=year,period=period,
                 date_flagged=int(bool(obj.get('date_review_flag'))),quality_flagged=int(bool(obj.get('quality_flags'))),
                 original_chars=len(normalize(raw)),local_chars=sum(len(s) for s in local),
                 local_segment_count=len(local),body_hash=hashlib.sha256(normalize(raw).encode()).hexdigest(),
                 text_available=int(bool(raw.strip())),title_clues=clues,hits={'local_context':hit_local,'whole_document':hit_whole})
        docs.append(doc)
        # 每个类别×旧分组仅留两份确定性抽样证据，供结果解释，不估计准确率。
        for cat,p in patterns.items():
            if not hit_local[cat]:continue
            bucket=examples.setdefault((cat,group),[])
            signature=hashlib.sha256((key+cat).encode()).hexdigest()
            matching=next((s for s in local if p.search(s)),None)
            m=p.search(matching)
            e=dict(record_key=key,title=title,prior_group=group,category=cat,matched_term=m.group(),
                   context=matching[max(0,m.start()-120):m.end()+180],source_url=obj.get('source_url',''),
                   caution='局部词语提及，未核实是否为本文件措施或同一服务组合')
            bucket.append((signature,e));bucket.sort(key=lambda v:v[0]);del bucket[2:]
    cutoff=median([d['local_chars'] for d in docs]) if docs else 0
    for d in docs:d['length_group']='shorter' if d['local_chars']<=cutoff else 'longer'
    evidence=[e for bucket in examples.values() for _,e in bucket]
    return docs,cats,evidence,cutoff

def calculate(docs,cats,cfg):
    names=[c['name'] for c in cats];dimensions={c['name']:c.get('dimension','未提供') for c in cats}
    coverage=[];pairs=[];annual=[];lengths=[]
    groups=['all_candidates']+sorted({d['prior_group'] for d in docs})
    groups+=['title_clue:'+n for n in list(TITLE_CLUES)+['综合标题未分类']]
    periods=['all_years']+[p[2] for p in cfg['periods']]
    for subset in ['all_candidates','without_date_flags']:
        base=[d for d in docs if subset=='all_candidates' or not d['date_flagged']]
        for basis in ['local_context','whole_document']:
            for period in periods:
                ps=[d for d in base if period=='all_years' or d['period']==period]
                for group in groups:
                    rs=[d for d in ps if group=='all_candidates' or
                        (group.startswith('title_clue:') and group.split(':',1)[1] in d['title_clues']) or d['prior_group']==group]
                    n=len(rs)
                    for name in names:
                        count=sum(d['hits'][basis][name] for d in rs)
                        coverage.append(dict(subset=subset,text_basis=basis,period=period,group=group,
                            dimension=dimensions[name],category=name,documents=n,hit_documents=count,
                            mention_pct=rate(count,n),small_group_flag=int(n<30),
                            available_text_docs=sum(d['text_available'] for d in rs),
                            nonempty_local_docs=sum(bool(d['local_chars']) for d in rs)))
                    # 组合仅在统一局部口径、全组及旧分组计算；不为每个标题线索增加大量小表。
                    if basis=='local_context' and not group.startswith('title_clue:'):
                        for a,b in combinations(names,2):
                            na=sum(d['hits'][basis][a] for d in rs);nb=sum(d['hits'][basis][b] for d in rs)
                            both=sum(d['hits'][basis][a] and d['hits'][basis][b] for d in rs)
                            pairs.append(dict(subset=subset,period=period,group=group,category_a=a,category_b=b,
                                dimension_a=dimensions[a],dimension_b=dimensions[b],documents=n,
                                a_docs=na,b_docs=nb,both_docs=both,both_pct=rate(both,n),
                                lift=round(both*n/(na*nb),3) if na*nb else '',small_cell_flag=int(both<10),
                                unit='同文局部片段集合共现，不保证同句或语义关联'))
    for year in sorted({d['year'] for d in docs if d['year'] is not None}):
        for group in ['all_candidates']+sorted({d['prior_group'] for d in docs}):
            rs=[d for d in docs if d['year']==year and (group=='all_candidates' or d['prior_group']==group)]
            for c in names:
                count=sum(d['hits']['local_context'][c] for d in rs)
                annual.append(dict(database_year=year,group=group,category=c,documents=len(rs),hit_documents=count,
                                   mention_pct=rate(count,len(rs)),date_flagged_docs=sum(d['date_flagged'] for d in rs),
                                   small_group_flag=int(len(rs)<30)))
    # 相同的全样本局部长度中位数，分组后不重新计算。
    for period in periods:
        for group in ['all_candidates']+sorted({d['prior_group'] for d in docs}):
            for size in ['shorter','longer']:
                rs=[d for d in docs if (period=='all_years' or d['period']==period) and
                    (group=='all_candidates' or d['prior_group']==group) and d['length_group']==size]
                for c in names:
                    count=sum(d['hits']['local_context'][c] for d in rs)
                    lengths.append(dict(period=period,group=group,length_group=size,category=c,documents=len(rs),
                                        hit_documents=count,mention_pct=rate(count,len(rs)),small_group_flag=int(len(rs)<30)))
    return coverage,pairs,annual,lengths

def run(cfg,lex_path=None):
    root=Path(cfg['research_root']);out=root/cfg['output_relative'];result=out/'results';logs=out/'logs'
    source=result/'connected_main_analysis.jsonl'
    lex_path=lex_path or root/cfg['content_relative']/'lexicon_v01.json'
    if not source.is_file() or not lex_path.is_file():raise FileNotFoundError('缺少输入：'+str(source)+' 或 '+str(lex_path))
    lex=json.loads(lex_path.read_text(encoding='utf-8-sig'))
    docs,cats,evidence,cutoff=prepare(list(jsonrows(source)),lex,cfg)
    print('主体候选：',len(docs),'；复用旧词典类别：',len(cats),'；开始文档提及及组合统计。',flush=True)
    coverage,pairs,annual,lengths=calculate(docs,cats,cfg)
    names=['overall_document_profiles.jsonl','overall_category_rates.csv','overall_category_pairs.csv',
           'overall_annual_rates.csv','overall_length_strata.csv','overall_evidence.csv',
           'overall_summary.json','overall_reading_notes.md']
    logs.mkdir(parents=True,exist_ok=True)
    previous=[result/n for n in names if (result/n).exists()]
    if previous:
        with zipfile.ZipFile(logs/('previous_overall_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'w',zipfile.ZIP_DEFLATED) as z:
            for p in previous:z.write(p,p.name)
    with (result/names[0]).open('w',encoding='utf-8') as f:
        for d in docs:f.write(json.dumps(d,ensure_ascii=False)+'\n')
    for filename,rows,fields in [
        (names[1],coverage,['subset','text_basis','period','group','dimension','category','documents','hit_documents','mention_pct','small_group_flag','available_text_docs','nonempty_local_docs']),
        (names[2],pairs,['subset','period','group','category_a','category_b','dimension_a','dimension_b','documents','a_docs','b_docs','both_docs','both_pct','lift','small_cell_flag','unit']),
        (names[3],annual,['database_year','group','category','documents','hit_documents','mention_pct','date_flagged_docs','small_group_flag']),
        (names[4],lengths,['period','group','length_group','category','documents','hit_documents','mention_pct','small_group_flag']),
        (names[5],evidence,['record_key','title','prior_group','category','matched_term','context','source_url','caution'])]:
        csvout(result/filename,rows,fields)
    summary=dict(status='completed',candidate_documents=len(docs),old_group_counts=dict(Counter(d['prior_group'] for d in docs)),
        date_flagged_documents=sum(d['date_flagged'] for d in docs),quality_flagged_documents=sum(d['quality_flagged'] for d in docs),
        documents_without_local_context=sum(not d['local_chars'] for d in docs),local_length_median=cutoff,
        configured_period_counts=dict(Counter(d['period'] for d in docs)),
        categories=[dict(name=c['name'],dimension=c.get('dimension','未提供')) for c in cats],
        dictionary_changed=False,title_clues_multilabel=True,
        primary_table=[r for r in coverage if r['subset']=='all_candidates' and r['text_basis']=='local_context' and r['period']=='all_years' and r['group']=='all_candidates'],
        limitations=['候选集经旧规则选择，不能据此推算全国政策总量或领域渗透率。',
                     '局部文本统一按定位词邻域提取；专项与综合文件都使用相同口径，全文只作对照。',
                     '无局部文本仍计入候选分母并标注，未按命中删除；这类零值不证明没有相关内容。',
                     '类别提及不等于措施、重视程度或实施效果；同文共现不代表同一服务配套。',
                     '标题线索多标签、仅供探索，不是经核实的政策领域分类。',
                     '按原配置时期提供对照，全年度另列；近期覆盖下降不能解释为政策减少。',
                     '剔除日期提示仅为敏感性口径；篇幅分层只作粗略对照，不消除混杂。'])
    (result/names[6]).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    notes='''# 整体内容探索读表顺序

1. overall_summary.json确认候选分母、旧词典类别、时期覆盖和文本缺口。
2. overall_category_rates.csv先看subset=all_candidates、text_basis=local_context、period=all_years；比较旧分组，不把既有分组区别都解释为发现。
3. 相同时期和相同分组下对照without_date_flags及篇幅分层。专题与综合文件比较均用局部文本；whole_document可显示全文范围差异，但不能作为主要组间比较。
4. 标题线索title_clue可重叠，不能加总；标题未分类不代表政策没有所属领域。
5. overall_category_pairs.csv的both_docs和lift要一起看；小于10的组合已标记。不同局部片段可能分别提到两类，不能称为语义配套，也不以高lift直接宣布重要发现。
6. 查看少量overall_evidence.csv原文，检查是否仅为引用、背景或其他对象；不要全面人工标注。
7. 有稳定且可解释的差异再组织论文；不自动筛选显著性，不把命中率排名当作重要性排名。

本轮不增加词典、不改旧分类、不补采、不调用模型。所有5322份候选均保留，不宣称是最终有效政策样本。日期未核实的记录也保留原始标记。
'''
    (result/names[7]).write_text(notes,encoding='utf-8')
    manifest=dict(created_at=datetime.now().astimezone().isoformat(),config=cfg,title_clue_patterns=TITLE_CLUES,
        inputs={str(source):sha(source),str(lex_path):sha(lex_path)},
        code_sha256={n:sha(Path(__file__).with_name(n)) for n in ['analyze_overall_content.py','connect_corpus_texts.py','build_expanded_corpus.py']},
        outputs={n:sha(result/n) for n in names})
    (logs/'latest_overall_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(out/'return_overall_content.zip','w',zipfile.ZIP_DEFLATED) as z:
        for n in names[1:]:z.write(result/n,n)
        z.write(logs/'latest_overall_manifest.json','latest_overall_manifest.json')
    print('完成；明细留在本机。请传回：',out/'return_overall_content.zip')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=Path(__file__).with_name('config.json'))
    p.add_argument('--lexicon',type=Path,help='可选指定旧词典路径')
    a=p.parse_args();run(json.loads(a.config.read_text(encoding='utf-8-sig')),a.lexicon)
if __name__=='__main__':
    try:main()
    except Exception as e:print('运行失败：'+str(e),file=sys.stderr);sys.exit(1)
