"""Render existing aggregate outputs; no corpus screening or new model fitting.
Usage: python plot_manuscript_figures.py --results <policy_patterns/results>
Or: python plot_manuscript_figures.py --bundles <folder containing both return ZIPs>
Outputs default to <results>/figures, or --output. Requires matplotlib, numpy.
"""
import argparse,csv,io,zipfile,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
P=argparse.ArgumentParser();P.add_argument('--results',type=Path);P.add_argument('--bundles',type=Path);P.add_argument('--output',type=Path)
a=P.parse_args()
if not a.results and not a.bundles:P.error('Specify --results or --bundles')
out=a.output or ((a.results or a.bundles)/'figures');out.mkdir(parents=True,exist_ok=True)
def read(name,bundle):
 if a.bundles:
  with zipfile.ZipFile(a.bundles/bundle) as z:s=z.read(name).decode('utf-8-sig')
 else:
  matches=list(a.results.rglob(name))
  if len(matches)!=1:raise ValueError(f'Expected one {name}; found {len(matches)}. Use --bundles or a narrower --results directory.')
  s=matches[0].read_text(encoding='utf-8-sig')
 return list(csv.DictReader(io.StringIO(s)))
rates=read('overall_category_rates.csv','return_overall_content.zip');annual=read('overall_annual_rates.csv','return_overall_content.zip')
sens=read('verification_sensitivity.csv','return_content_verification.zip');std=read('verification_standardized.csv','return_content_verification.zip')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#263746','text.color':'#263746','axes.edgecolor':'#84939d','svg.fonttype':'none','pdf.fonttype':42,'savefig.facecolor':'white'})
navy='#173b57';teal='#168b87';gold='#cb8b2c';grey='#7c8792';cols=[teal,gold,navy]
# Codes are inherited from the supplied output schema.
G='综合文件含措施线索'
periods=['2011-2014','2015-2018','2019-2022']
cn=['居家养老','社区养老','机构养老','医养结合','助餐服务','失能照护','适老改造','智慧养老','精神文化']
en=['Home-based care','Community-based care','Institutional care','Medical–care integration','Meal support','Disability-related care','Age-friendly adaptation','Smart eldercare','Social and cultural activities']
focus=['助餐服务','适老改造','智慧养老'];labels=['Meal support','Age-friendly adaptation','Smart eldercare']
def save(fig,name):
 for ext in ['png','pdf','svg']:fig.savefig(out/f'{name}.{ext}',dpi=400,bbox_inches='tight',pad_inches=.16)
 plt.close(fig)
def title(ax,s):ax.set_title(s,loc='left',fontweight='bold',fontsize=12,pad=14)
# 1. Workflow: the measurement step serves all three branches.
f,ax=plt.subplots(figsize=(12,7.6))
ax.set(xlim=(0,12),ylim=(0,7.6));ax.axis('off')
def box(x,y,w,h,head,body,color=navy):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.03,rounding_size=.10',facecolor='#f5f8fa',edgecolor=color,linewidth=1.2))
 ax.text(x+.17,y+h-.22,head,color=color,fontsize=10.8,fontweight='bold',va='top')
 ax.text(x+.17,y+h-.62,body,fontsize=9.3,va='top',linespacing=1.48)
def arrow(x,y,x2,y2):
 ax.add_patch(FancyArrowPatch((x,y),(x2,y2),arrowstyle='-|>',mutation_scale=13,color='#778c9a',lw=1.3,shrinkA=0,shrinkB=0))
ax.text(.1,7.31,'CORPUS CONSTRUCTION AND ANALYSIS',fontsize=16,fontweight='bold',color=navy)
box(.1,4.88,3.65,1.95,'01  Retrieve and deduplicate','16,908 retrieved records\n571 exact title-and-body duplicates\n16,337 retained records')
box(4.17,4.88,3.65,1.95,'02  Screen retained records','5,322 main candidates\n1,045 boundary records\n9,970 reserve records',teal)
box(8.24,4.88,3.65,1.95,'03  Assemble main corpus','912 specialized policy candidates\n47 implementation/process records\n4,363 broader measure-bearing records',teal)
arrow(3.79,5.86,4.12,5.86);arrow(7.86,5.86,8.19,5.86)
box(.1,2.85,11.79,1.44,'04  Apply the same measurement to all 5,322 main candidates','Extract eldercare-related passages and apply the fixed 20-category dictionary to each fragment.\nRecord document-level hits; retain candidates with no extracted passage in the denominator.')
arrow(10.065,4.84,10.065,4.34)
box(.1,.36,3.65,1.86,'Service profiles and trends','Full main corpus and broader subsets\nThree-period and annual profiles\n2011–2022 for the plotted trends\nFigures 2 and 3')
box(4.17,.36,3.65,1.86,'Focused period comparison','Broader candidates: 1,807 vs 1,404\n2015–2018 vs 2019–2022\nRaw and standardized rates; checks\nTable 2 and Figure 4',gold)
box(8.24,.36,3.65,1.86,'Joint mentions and context','Same 3,211 broader candidates\nCount shared and separate fragments\nRead selected passages for context\nFigure 5',teal)
for x in [1.925,5.995,10.065]:arrow(x,2.81,x,2.27)
ax.text(.1,.03,'Boundary and reserve records are outside the main analysis. Co-presence alone does not establish policy integration.',fontsize=8.8,color=grey)
save(f,'fig01_workflow')
# 2. Heatmap.
M=np.array([[float(next(r['mention_pct'] for r in rates if r['subset']=='all_candidates' and r['text_basis']=='local_context' and r['group']==G and r['period']==p and r['category']==c)) for p in periods] for c in cn])
f,ax=plt.subplots(figsize=(8.7,6));im=ax.imshow(M,cmap='YlGnBu',vmin=0,vmax=60,aspect='auto')
ax.set_xticks(range(3),['2011–2014\nn = 640','2015–2018\nn = 1,807','2019–2022\nn = 1,404']);ax.set_yticks(range(9),en);ax.tick_params(length=0);ax.tick_params(axis='x',pad=10)
for i in range(9):
 for j in range(3):ax.text(j,i,f'{M[i,j]:.2f}',ha='center',va='center',color='white' if M[i,j]>35 else navy,fontsize=11)
for s in ax.spines.values():s.set_visible(False)
cb=f.colorbar(im,ax=ax,shrink=.75,pad=.04);cb.set_label('Documents with a local mention (%)')
title(ax,'Service agendas in broader policy candidates');f.tight_layout();save(f,'fig02_service_profiles')
# 3. Three annual trajectories and a transparent denominator strip.
years=list(range(2011,2023));f,axs=plt.subplots(4,1,figsize=(9.5,8),sharex=True,gridspec_kw={'height_ratios':[1,1,1,.65]},layout='constrained')
for i,(cat,label,col) in enumerate(zip(focus,labels,cols)):
 rr=[next(r for r in annual if r['group']==G and r['category']==cat and int(r['database_year'])==y) for y in years]
 vals=[float(r['mention_pct']) for r in rr];axs[i].plot(years,vals,'o-',color=col,lw=2,ms=5);axs[i].set_ylim(0,23);axs[i].set_yticks([0,10,20]);axs[i].set_ylabel('%');axs[i].text(.015,.80,label,transform=axs[i].transAxes,color=col,fontweight='bold');axs[i].grid(axis='y',alpha=.18)
 for k in [0,-1]:axs[i].annotate(f'{vals[k]:.1f}',(years[k],vals[k]),xytext=(5,5),textcoords='offset points',fontsize=9)
ns=[int(next(r['documents'] for r in annual if r['group']==G and r['category']==focus[0] and int(r['database_year'])==y)) for y in years]
axs[3].bar(years,ns,color='#bdcbd4',width=.65);axs[3].set_ylabel('n');axs[3].set_xlabel('Database year');axs[3].set_xticks(years);axs[3].tick_params(axis='x',rotation=45)
for y,n in zip(years,ns):axs[3].text(y,n+9,str(n),ha='center',fontsize=8)
axs[3].set_ylim(0,max(ns)*1.32);axs[0].set_title('Annual local mention rates in broader policy candidates',loc='left',fontweight='bold',pad=12)
save(f,'fig03_annual_trajectories')
# 4. Raw differences and fixed checks. No inferential intervals are drawn.
variants=[('baseline','Raw comparison'),('without_date_flags','Exclude date flags'),('exact_same_body_sensitivity','Exact-body de-duplication'),('leave_out_2021','Omit 2021'),('leave_out_2022','Omit 2022')]
print('Sensitivity variants:',sorted(set(r['variant'] for r in sens)))
# Stable aliases accommodate schema labels used by the analysis script.
available=sorted(set(r['variant'] for r in sens))
for i,(key,label) in enumerate(variants):
 if key not in available:
  tokens={'exclude_date_flags':['date'],'min_text_200':['200'],'leave_out_2021':['2021'],'leave_out_2022':['2022']}[key]
  cand=[v for v in available if all(t in v for t in tokens)]
  if len(cand)!=1:raise ValueError((key,cand))
  variants[i]=(cand[0],label)
f,axs=plt.subplots(1,3,figsize=(10.8,4.6),sharey=True,layout='constrained')
for ax,cat,label,col in zip(axs,focus,labels,cols):
 vals=[]
 for key,_ in variants:
  e=next(r for r in sens if r['group']==G and r['variant']==key and r['period']=='2015-2018');l=next(r for r in sens if r['group']==G and r['variant']==key and r['period']=='2019-2022');vals.append(float(l[cat+'_pct'])-float(e[cat+'_pct']))
 sr=next(r for r in std if r['group']==G and r['variant']=='baseline' and r['outcome']==cat);vals.append(float(sr['standardized_difference_pp']))
 yy=np.arange(6);ax.scatter(vals,yy,color=col,s=55,zorder=3)
 for v,y in zip(vals,yy):ax.text(v+.20,y,f'{v:.2f}',va='center',fontsize=9)
 ax.axvline(0,color=grey,lw=.8);ax.set_xlim(-.3,14);ax.set_xticks([0,5,10]);ax.grid(axis='x',alpha=.2);ax.set_title(label,fontsize=11,fontweight='bold');ax.set_xlabel('Later − earlier (percentage points)')
axs[0].set_yticks(range(6),[l for _,l in variants]+['Fixed-stratum standardization']);axs[0].invert_yaxis();f.suptitle('Direction of change under alternative descriptive specifications',fontsize=13,fontweight='bold')
save(f,'fig04_fixed_comparisons')
# 5. Joint mentions with explicit denominators and distance.
e=next(r for r in sens if r['group']==G and r['variant']=='baseline' and r['period']=='2015-2018')
l=next(r for r in sens if r['group']==G and r['variant']=='baseline' and r['period']=='2019-2022')
conditional=[100*int(r['joint_docs'])/int(r['smart_denominator']) for r in [e,l]]
if not a.bundles and list(a.results.rglob('verification_joint_counts.csv')):
 joint=read('verification_joint_counts.csv','')
 jr=[next(r for r in joint if r['group']==G and r['period']==row['period']) for row in [e,l]]
 for r,row in zip(jr,[e,l]):
  if (int(r['same_local_fragment'])+int(r['different_local_fragments'])!=int(row['joint_docs'])
      or int(r['joint_documents'])!=int(row['joint_docs'])
      or int(r['smart_denominator'])!=int(row['smart_denominator'])):
   raise ValueError('Joint-count table does not match the sensitivity table.')
 same=[int(r['same_local_fragment']) for r in jr]
else:
 joint=read('verification_joint_documents.csv','return_content_verification.zip')
 same=[sum(r['prior_group']==G and r['period']==p and r['same_local_segment']=='1' for r in joint) for p in ['2015-2018','2019-2022']]
different=[int(r['joint_docs'])-n for r,n in zip([e,l],same)]
f,axs=plt.subplots(1,2,figsize=(10,4.7),layout='constrained')
axs[0].bar([0,1],conditional,color=['#adc0cc',teal],width=.55)
for i,(v,t) in enumerate([(v, r['joint_docs']+' / '+r['smart_denominator']) for v,r in zip(conditional,[e,l])]):axs[0].text(i,v+1.3,f'{v:.2f}%\n{t}',ha='center',fontsize=10)
axs[0].set_xticks([0,1],['2015–2018','2019–2022']);axs[0].set_ylim(0,47);axs[0].set_ylabel('Adaptation mention among smart-eldercare documents (%)');title(axs[0],'A  Conditional co-presence')
axs[1].barh(['2015–2018','2019–2022'],same,color=teal,label='Same local fragment');axs[1].barh(['2015–2018','2019–2022'],different,left=same,color=gold,label='Different fragments');axs[1].invert_yaxis();axs[1].set_xlim(0,64);axs[1].set_xlabel('Documents mentioning both categories');title(axs[1],'B  Textual proximity of joint mentions')
axs[1].text(same[1]/2,1,str(same[1]),ha='center',va='center',color='white',fontweight='bold');axs[1].text(same[1]+different[1]/2,1,str(different[1]),ha='center',va='center',color='white',fontweight='bold');axs[1].text(2,0,str(different[0]),va='center');axs[1].legend(loc='upper left',bbox_to_anchor=(0,-.18),frameon=False,fontsize=9)
save(f,'fig05_joint_mentions')
(out/'figure_manifest.json').write_text(json.dumps({'source':'Existing returned aggregate outputs; no new formal analysis','group':G,'figures':[f'fig0{i}' for i in range(1,6)],'formats':['png','pdf','svg'],'png_dpi':400},indent=2),encoding='utf-8')
print(out.resolve())
