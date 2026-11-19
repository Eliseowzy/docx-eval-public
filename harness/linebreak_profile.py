# For every case whose first defect is a line break, compare Word's and the engine's lines at that spot:
# who broke earlier, by how many characters, what the boundary character is, and the line widths.
import json,os,collections,glob,unicodedata
import sys; R='runs/'+(sys.argv[1] if len(sys.argv)>1 else open('runs/BASELINE').read().strip())
S=json.load(open(R+'/summary.json'))
rows=[]
for r in S['cases']:
    if r.get('category')!='line-break': continue
    cmp=json.load(open(f"{R}/cases/{r['sha']}.cmp.json"))
    blk=next((p for p in cmp['pairs'] if 'tag' in p),None)
    if not blk or not blk['word'] or not blk['engine']: rows.append((r['case'],'one-sided',None,None,None)); continue
    w=blk['word'][0]['key']; e=blk['engine'][0]['key']
    # common prefix
    n=0
    while n<min(len(w),len(e)) and w[n]==e[n]: n+=1
    if len(w)>len(e) and w.startswith(e): kind='engine-earlier'
    elif len(e)>len(w) and e.startswith(w): kind='engine-later'
    else: kind='content-differs'
    diff=len(e)-len(w)
    bch=(w[n:n+1] or e[n:n+1])
    script='CJK' if any('CJK' in unicodedata.name(c,'') or 'HIRAGANA' in unicodedata.name(c,'') for c in w[:20]) else 'latin'
    rows.append((r['case'],kind,diff,bch,script, w[:40], e[:40]))
k=collections.Counter(x[1] for x in rows); print(k)
print('diff chars', collections.Counter(min(abs(x[2]),10) for x in rows if x[2] is not None).most_common())
print('script', collections.Counter((x[1],x[4]) for x in rows if len(x)>4))
for x in rows[:25]: print(x[1], x[2], x[3] if len(x)>3 else '', '|', x[5] if len(x)>5 else '', '|', x[6] if len(x)>6 else '', '|', x[0][-40:])
