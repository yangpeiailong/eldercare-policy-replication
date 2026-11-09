"""规则复核V02：区分专项文件、综合政策内措施和过程材料；所有判断保留证据。"""
import argparse
import collections
import csv
import hashlib
import html
import json
from pathlib import Path
import random
import re
from audit_base import assess, norm, TOPIC

CARE = re.compile(r'养老服务|养老机构|养老院|敬老院|居家养老|社区养老|社区居家养老|医养结合|医养康养|老年照护|长期护理|长护险|适老(?:化)?改造|健康适老|老年用品|老年人运用智能技术|老年人信息获取|老年人健康科普|家庭养老床位|老年助餐|养老助餐|高龄津贴|高龄补贴|护理补贴|老年人.{0,6}照护|养老设施|养老床位|老年人照顾服务')
ACTION = re.compile(r'应当|不得|必须|给予|补贴|补助|资助|减免|免征|支持|鼓励|引导|加强|允许|调整用于|转型|预留|优先|减按|提升|普及|建立|健全|完善|制定|建设|提供|开展|推进|落实|纳入|新增|达到|以上|以下|不低于|不少于|负责|承担|拨付|安排|购买服务')
FORM = re.compile(r'关于|通知|意见|方案|办法|细则|规定|条例|规划|清单|标准|决定|公告|指导|措施|指南|规范|行动计划')
PROCESS = re.compile(r'申报|报送|评选|评审|认定|命名|名单|下拨|拨付|验收|督查|督察|检查|考核|培训班|统计调查|遴选|推荐|报备|续保|续签')


def body_type(title,text):
    opening=re.sub(r'\s+','',text[:1800])
    if re.search(r'讲话|工作报告|完成情况.{0,8}报告|工作总结',title):
        return '讲话报告单列'
    if re.search(r'(您|你们|贵委|委员|代表).{0,120}(提出|提案|建议).{0,120}收悉|现将.{0,30}(办理情况)?答复如下|现答复如下',opening):
        return '正文识别提案建议答复'
    if re.search(r'新华社.{0,35}电|本报讯|记者[：:]|记者.{0,20}报道',opening):return '正文疑似新闻报道'
    news_patterns=re.findall(r'《[^》]{2,120}》(?:指出|强调|提出|要求|明确)',opening)
    if len(news_patterns)>=2 and re.search(r'近日|日前|印发了|以下简称',opening):return '正文疑似政策发布报道'
    if re.search(r'记者问|问[:：]|答[:：]|政策解读|起草背景|出台背景',opening[:350]) and not re.search(r'现印发|现将|请.{0,10}贯彻|解读工作|宣传解读',opening[:350]):
        return '正文疑似解读问答'
    return ''


def clauses(text):
    # 统一换行后按句界提取；窗口最长600字符，不对全文做模型推断。
    found=[];seen=set()
    for m in CARE.finditer(text):
        left=max(text.rfind('。',0,m.start()),text.rfind('；',0,m.start()),text.rfind('\n',0,m.start()))+1
        ends=[p for p in [text.find('。',m.end()),text.find('；',m.end()),text.find('\n',m.end())] if p>=0]
        right=min(ends)+1 if ends else len(text)
        left=max(left,m.start()-260);right=min(right,m.end()+340)
        s=text[left:right].strip()
        if s in seen:continue
        seen.add(s)
        # 只标记词语共现，不宣称已确认政策承诺或因果。
        local=text[max(left,m.start()-220):min(right,m.end()+240)]
        if ACTION.search(local):found.append(dict(start=left,end=right,text=s,matched_care_term=m.group(),action_matches=sorted(set(ACTION.findall(local)))))
    return found


def process(doc):
    base=assess(doc); title=doc['title'];text=html.unescape(doc.get('database_text',''))
    hint=body_type(title,text)
    evidence=clauses(text)
    formal=bool(FORM.search(title))
    if base['document_type_hint']!='其他文件待定' or hint:
        category='辅助材料或类型待排查';reason=hint or base['document_type_hint']
    elif base['category']=='核心候选需核验':
        if not formal:category='相关文件待核查';reason='标题相关但正式文件形式不明确'
        elif PROCESS.search(title):category='专项实施过程候选';reason='标题相关，带申报评定拨付检查等过程线索'
        else:category='专项制度候选';reason='标题明确相关，未命中已定义辅助及过程规则'
    elif evidence and formal:
        category='综合文件含措施线索';reason='同句窗口内养老服务词与措施词共现，需核验语义'
    elif base['category']=='范围待定' or re.search(TOPIC,title):
        category='相关文件待核查';reason='养老保险或其他涉老领域，范围未定'
    elif CARE.search(text):category='仅有服务词或形式待核查';reason='有服务词，未满足本版措施窗口及文件形式规则'
    else:category='低相关暂存';reason='未检出本版养老服务措施线索，不直接认定无关'
    tail=norm(text[-1400:])
    dates=re.findall(r'(?:19|20)\d{2}年\d{1,2}月\d{1,2}日',tail)
    raw=doc.get('publish_date_raw','')
    date_flag='疑似默认日期20000101' if raw=='20000101' else ''
    if dates and raw[:4] and all(date[:4]!=raw[:4] for date in dates):
        date_flag+=';尾部日期候选与数据库年份不一致'
    return dict(**base,v02_category=category,v02_reason=reason,body_type_hint=hint,
                tail_date_candidates=';'.join(dict.fromkeys(dates)),date_review_flag=date_flag.strip(';'),
                measure_evidence_count=len(evidence),evidence_preview=evidence[0]['text'][:240] if evidence else ''),evidence


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    docs=[json.loads(l) for l in Path(args.input).read_text(encoding='utf-8-sig').splitlines() if l.strip()]
    rows=[];representatives={};core=[];embedded=[];core_blocked=[]
    for d in docs:
        row,ev=process(d);body=norm(d.get('database_text',''));key=(norm(d['title']),hashlib.sha256(body.encode()).hexdigest())
        if body and key in representatives:row['duplicate_of']=representatives[key]
        elif body:representatives[key]=d['record_key']
        rows.append(row)
        if row['duplicate_of']:continue
        cat=row['v02_category']
        if cat in ['专项制度候选','专项实施过程候选']:
            core.append(dict(**d,screening=row,measure_evidence=ev))
            if row['quality_flags']:core_blocked.append(row)
        if cat=='综合文件含措施线索':
            embedded.append(dict(record_key=d['record_key'],title=d['title'],source_url=d.get('source_url',''),
                publish_year=d.get('publish_year',''),evidence=ev,screening_reason=row['v02_reason']))
    def write_jsonl(name,data):
        with (out/name).open('w',encoding='utf-8') as f:
            for x in data:f.write(json.dumps(x,ensure_ascii=False)+'\n')
    def write_csv(name,data):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            fields=list(rows[0]);w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for x in data:w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in x.items()})
    write_csv('screening_ledger_v03.csv',rows);write_csv('core_text_recovery_queue.csv',core_blocked)
    write_csv('date_review_queue.csv',[r for r in rows if r['date_review_flag'] and not r['duplicate_of']])
    write_jsonl('specialized_candidates_v03.jsonl',core);write_jsonl('embedded_measure_evidence.jsonl',embedded)
    # 核查样本用于下一次人工/模型审读，不是已经完成的人工金标准。
    samples=[];rng=random.Random(20261027)
    for cat in sorted({r['v02_category'] for r in rows}):
        options=[r for r in rows if r['v02_category']==cat and not r['duplicate_of']]
        for row in rng.sample(options,min(8,len(options))):samples.append(row)
    write_csv('next_review_sample.csv',samples)
    dedup=[r for r in rows if not r['duplicate_of']]
    summary=dict(input_records=len(rows),duplicate_extras=len(rows)-len(dedup),
       category_counts=dict(collections.Counter(r['v02_category'] for r in rows)),
       category_counts_after_exact_title_body_dedup=dict(collections.Counter(r['v02_category'] for r in dedup)),
       v01_core_moved=collections.Counter(r['v02_category'] for r in rows if r['category']=='核心候选需核验'),
       core_candidate_count=len(core),core_with_quality_flags=len(core_blocked),
       core_date_review_count=sum(bool(d['screening']['date_review_flag']) for d in core),
       embedded_document_count=len(embedded),embedded_evidence_windows=sum(len(x['evidence']) for x in embedded),
       core_year_counts=dict(sorted(collections.Counter(x.get('publish_year','') for x in core).items())),
       review_sample_count=len(samples),rules_version='V03',
       note='探索性规则迭代；抽查未形成独立金标准，尚无准确率/召回率估计。候选数量不等于有效政策数。')
    (out/'screening_summary_v03.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    assert sum(summary['category_counts'].values())==len(docs)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
