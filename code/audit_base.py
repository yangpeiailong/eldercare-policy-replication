"""离线保守初筛：不修改原始数据，不调用API；分类结果不是最终纳入判定。"""
import argparse
import collections
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import statistics
import unicodedata

TOPIC = r'养老服务|养老机构|养老院|敬老院|居家养老|社区养老|社区居家养老|社会养老服务|医养结合|医养康养|老年人照顾|老年人照护|老年人护理|老年人居家|老年助餐|养老助餐|老年人助餐|老年人能力评估|老年照护|长期护理|长护险|适老化|家庭养老床位|高龄津贴|高龄补贴|老年综合津贴|养老床位|老龄事业|老龄工作|老年人权益|优待老年人|老年人优待|银发经济|智慧健康养老|健康养老|老年健康|老年教育|老年友好|老年人运用智能技术|养老产业|养老服务业|社会养老体系'
RELATED = r'养老|老年|老龄|敬老|助老|医养|适老|银发|长护'


def norm(s):
    return re.sub(r'[\s\u200b-\u200f\ufeff]+', '', unicodedata.normalize('NFKC',html.unescape(s or '')))


def kind(title):
    if re.search(r'答复|回复|答复函|提案|建议的办理|建议办理|关于.*的建议$',title): return '提案建议答复等'
    if re.search(r'解读|答记者问|一图读懂|图解|新闻发布会',title): return '解读问答'
    if re.search(r'征求意见|草案',title): return '草案征求意见'
    if re.search(r'任免|任职|免职|干部任命',title): return '人事任免'
    if re.search(r'中标|采购公告|成交公告|招标公告|拟认定名单|拟命名|公示|表彰|评选|公布.*名单|公布.*模范',title): return '公示采购表彰等'
    if re.search(r'新闻|记者|领导讲话|工作总结|考察|调研|召开.*会议',title): return '新闻讲话总结疑似'
    return '其他文件待定'


def assess(d):
    title=d.get('title',''); text=html.unescape(d.get('database_text',''))
    doc_kind=kind(title)
    specific=bool(re.search(TOPIC,title))
    related=bool(re.search(RELATED,title))
    hits=list(re.finditer(TOPIC,text))
    if specific: relevance='标题明确相关'
    elif related and not ('养老保险' in title and not re.search(TOPIC,title)):
        relevance='标题相关但范围待定'
    elif hits: relevance='综合文件含相关内容'
    else: relevance='未检出明确养老服务线索'
    flags=[]
    n=len(text)
    if n==0: flags.append('空文本')
    elif n<400: flags.append('短文本仅提示回查')
    if n>=65536: flags.append('达到或超过65536字符需查截断')
    if re.search(r'附件|\.docx?\b|\.pdf\b|\.xlsx?\b',text,re.I) and n<800:
        flags.append('短通知疑似缺附件')
    if re.search(r'点击.{0,5}全文|查看.{0,5}全文|展开全部',text): flags.append('疑似网页截断提示')
    if re.search(r'验证码|访问过于频繁|Access Denied',text,re.I) and n<1500:flags.append('疑似拦截页')
    if doc_kind!='其他文件待定': category='辅助或非正式样本'
    elif specific: category='核心候选需核验'
    elif related: category='范围待定'
    elif hits: category='综合政策背景'
    else: category='低相关待核查'
    return dict(record_key=d['record_key'],title=title,publish_year=d.get('publish_year',''),
      publish_date_raw=d.get('publish_date_raw',''),publisher=d.get('publisher',''),
      region_raw=d.get('region',''),province_raw=d.get('province',''),
      category=category,document_type_hint=doc_kind,relevance_hint=relevance,
      text_chars=n,related_occurrences=len(hits),quality_flags=';'.join(flags),
      source_url=d.get('source_url',''),matched_groups=d.get('matched_groups',''),
      duplicate_of='',text_preview=text[:160])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args(); out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    docs=[json.loads(line) for line in Path(a.input).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    assert len({d['record_key'] for d in docs})==len(docs),'记录ID重复，先检查输入'
    rows=[]; representatives={}; same_body=collections.Counter(); candidates=[]
    for d in docs:
        row=assess(d); body=norm(d.get('database_text','')); title=norm(d.get('title',''))
        digest=hashlib.sha256(body.encode()).hexdigest() if body else ''
        if digest:same_body[digest]+=1
        # 仅“相同标准化标题+相同标准化正文”合并；其他相同正文仍保留待核查。
        key=(title,digest)
        if body and key in representatives: row['duplicate_of']=representatives[key]
        elif body: representatives[key]=d['record_key']
        rows.append(row)
        if row['category']=='核心候选需核验' and not row['duplicate_of']:
            candidates.append(dict(**d,audit=row))
    fields=list(rows[0]) if rows else ['record_key']
    with (out/'screening_ledger.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in rows:
            w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
    with (out/'core_candidates.jsonl').open('w',encoding='utf-8') as f:
        for d in candidates:f.write(json.dumps(d,ensure_ascii=False)+'\n')
    stats=dict(input_records=len(docs),title_and_body_duplicate_extra=sum(bool(r['duplicate_of']) for r in rows),
       all_nonempty_identical_body_extra=sum(n-1 for n in same_body.values()),
       category_counts=dict(collections.Counter(r['category'] for r in rows)),
       document_type_counts=dict(collections.Counter(r['document_type_hint'] for r in rows)),
       deduplicated_core_candidates=len(candidates),
       core_quality_flag_counts=dict(collections.Counter(flag for d in candidates for flag in d['audit']['quality_flags'].split(';') if flag)),
       text_length=dict(min=min(r['text_chars'] for r in rows),median=statistics.median(r['text_chars'] for r in rows),max=max(r['text_chars'] for r in rows)),
       empty_texts=sum(r['text_chars']==0 for r in rows),under400=sum(r['text_chars']<400 for r in rows),
       exactly65536=sum(r['text_chars']==65536 for r in rows),
       source_sha256=hashlib.sha256(Path(a.input).read_bytes()).hexdigest(),
       note='规则初筛，不是最终纳入样本；短文本不直接删除；核心集不完整，综合政策也可能包含重要措施。')
    (out/'screening_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
