"""探索性候选库统计。代码与数据分开，所有输入输出路径由参数提供。"""
import argparse,csv,json,re,statistics,hashlib
from pathlib import Path
from collections import Counter,defaultdict

def load(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def csvout(p,rows):
    if not rows:return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def norm(s):return re.sub(r'\s+','',s or '')
def main():
    a=argparse.ArgumentParser();a.add_argument('--core',required=True);a.add_argument('--ledger',required=True)
    a.add_argument('--recovery',required=True);a.add_argument('--out',required=True);args=a.parse_args()
    core=load(args.core);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with Path(args.ledger).open(encoding='utf-8-sig') as f:ledger=list(csv.DictReader(f))
    recovery=Path(args.recovery);rec={x['record_key']:x for x in load(recovery/'recovery_results.jsonl')}
    verified=load(recovery/'verified_beijing_attachment.jsonl')[0]
    citymap={'杭州市':'浙江省','大连市':'辽宁省','郑州市':'河南省','广州市':'广东省','青岛市':'山东省','东莞市':'广东省','厦门市':'福建省','深圳市':'广东省','苏州市':'江苏省','合肥市':'安徽省','西安市':'陕西省','宁波市':'浙江省','佛山市':'广东省','武汉市':'湖北省','长沙市':'湖南省','成都市':'四川省'}
    rows=[];textrows=[];reviews=[];attachment_reviews=[]
    for d in core:
        s=d['screening'];t=d['title'];body=d['database_text'];year=str(d.get('publish_year',''))
        groups=[x.strip() for x in d.get('matched_groups','').split(';') if x.strip()]
        prov=d.get('province','');basis='数据库省份字段' if prov else ''
        if not prov:
            cities=[g.split('==',1)[1] for g in groups if g.startswith('CITYPUB==')]
            ps={citymap[c] for c in cities if c in citymap}
            if len(ps)==1:prov=ps.pop();basis='城市检索分组映射，非发文级别判定'
        channels=sorted({g.split('==')[0] for g in groups if '==' in g})
        channel='+'.join(channels) or '未分组'
        # 多个类型可并存；通知常是承载规划、办法的外壳，不强制互斥。
        types=[label for label,pat in [('规划',r'规划'),('意见',r'意见'),('办法规定条例',r'办法|规定|条例'),('方案计划',r'方案|计划'),('标准规范指南',r'标准|规范|指南'),('通知通告公告',r'通知|通告|公告')] if re.search(pat,t)]
        types=types or ['其他标题形式']
        intro=norm(body[:1400]);interpret=bool(re.search(r'^一[、.．]制定背景|^制定背景|^一[、.．]出台背景|^政策解读',intro))
        flags=[]
        if interpret:flags.append('开头呈解读结构，需核查原文')
        if s.get('quality_flags'):flags.append('正文质量提示')
        if s.get('date_review_flag'):flags.append('日期疑点')
        if d.get('publish_date_raw')=='20000101':flags.append('疑似默认日期')
        if year and int(year)>2023:flags.append('2024及以后覆盖待核查')
        if len(body)==65536:flags.append('长度65536疑似截断')
        dateok=bool(year.isdigit() and 1900<=int(year)<=2023 and not s.get('date_review_flag') and d.get('publish_date_raw')!='20000101')
        r=rec.get(d['record_key'],{});attachments=[]
        for att in r.get('attachments',[]):
            if att.get('path'):
                path=recovery/att['path'];digest=hashlib.sha256(path.read_bytes()).hexdigest()
                attachments.append(dict(path=att['path'],sha256=digest,text_chars=att.get('text_chars',0),approved=False))
                attachment_reviews.append(dict(record_key=d['record_key'],title=t,source_url=att['url'],path=att['path'],sha256=digest,text_chars=att.get('text_chars',0),decision='已下载，尚未逐件核验标题和内容'))
        supplement=[]
        if d['record_key']==verified['record_key']:
            supplement=[dict(source_url=verified['source_url'],text=verified['candidate_text'],evidence=verified['evidence'],status='封面已核对；PDF文字层，表格未逐页校验')]
        row=dict(record_key=d['record_key'],title=t,publish_year_raw=year,publish_date_raw=d.get('publish_date_raw',''),
          date_usable_sensitivity=int(dateok),screening_category=s['v02_category'],publisher_raw=d.get('publisher',''),
          province_for_coverage=prov or '未确定',province_basis=basis,retrieval_channel=channel,
          title_types='；'.join(types),original_text_chars=len(body),review_flags='；'.join(flags),
          interpretation_structure_flag=int(interpret),quality_flag=int(bool(s.get('quality_flags'))),
          date_flag=int(bool(s.get('date_review_flag'))),source_fetch_status=r.get('status','未在本轮补取队列'),
          saved_attachment_items=len(attachments),verified_supplement_count=len(supplement),source_url=d.get('source_url',''))
        rows.append(row)
        textrows.append(dict(record_key=d['record_key'],title=t,original_text=body,supplemental_texts=supplement,
          attachment_candidates=attachments,sample_status='规则筛选核心候选，非最终有效政策',original_text_overwritten=False))
        if interpret:reviews.append(dict(record_key=d['record_key'],title=t,opening=body[:1400],source_url=d.get('source_url',''),decision='解读结构提示，暂不自动删除'))
    csvout(out/'core_candidate_catalog.csv',rows);csvout(out/'interpretation_review.csv',reviews);csvout(out/'attachment_association_review.csv',attachment_reviews)
    (out/'core_texts_with_supplements.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in textrows))
    counts=Counter(r['publish_year_raw'] or '缺失' for r in rows);safe=Counter(r['publish_year_raw'] for r in rows if r['date_usable_sensitivity']);strict=Counter(r['publish_year_raw'] for r in rows if r['date_usable_sensitivity'] and not r['interpretation_structure_flag'] and not r['quality_flag'])
    annual=[dict(year=y,all_candidates=counts[y],date_screened=safe[y],date_and_text_screened=strict[y]) for y in sorted(counts)]
    csvout(out/'annual_counts.csv',annual)
    for name,field in [('province_coverage','province_for_coverage'),('retrieval_channels','retrieval_channel'),('publisher_labels','publisher_raw'),('candidate_categories','screening_category')]:
        c=Counter(r[field] or '缺失' for r in rows);csvout(out/(name+'.csv'),[dict(label=k,count=v,share_pct=round(v/len(rows)*100,2)) for k,v in c.most_common()])
    c=Counter(typ for r in rows for typ in r['title_types'].split('；'));csvout(out/'title_types_multilabel.csv',[dict(title_type=k,count=v,denominator=len(rows)) for k,v in c.most_common()])
    categories=Counter(r['v02_category'] for r in ledger if not r['duplicate_of']);csvout(out/'corpus_flow.csv',[dict(category=k,count=v) for k,v in categories.items()])
    summary=dict(core_candidates=len(rows),date_screened=sum(safe.values()),date_and_text_screened=sum(strict.values()),
      date_flags=sum(r['date_flag'] for r in rows),quality_flags=sum(r['quality_flag'] for r in rows),
      interpretation_structure_flags=len(reviews),years_2024_onward=sum(int(r['publish_year_raw'] or 0)>=2024 for r in rows),
      province_coverage_labels=len({r['province_for_coverage'] for r in rows if r['province_for_coverage']!='未确定'}),
      province_undetermined=sum(r['province_for_coverage']=='未确定' for r in rows),
      median_original_chars=statistics.median(r['original_text_chars'] for r in rows),
      text_chars_min=min(r['original_text_chars'] for r in rows),text_chars_max=max(r['original_text_chars'] for r in rows),
      verified_supplement_docs=sum(r['verified_supplement_count']>0 for r in rows),attachment_download_items=len(attachment_reviews),
      attachment_unique_hashes=len({a['sha256'] for a in attachment_reviews}),
      core_source_input_sha256=hashlib.sha256(Path(args.core).read_bytes()).hexdigest(),
      note='所有统计针对候选库；筛除疑点是敏感性口径，不是最终样本。检索分组不是发文级别。')
    (out/'baseline_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    assert len(rows)==len({r['record_key'] for r in rows})==959
    assert sum(counts.values())==959 and sum(categories.values())==16337
    assert sum(len(x['supplemental_texts']) for x in textrows)==1
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
