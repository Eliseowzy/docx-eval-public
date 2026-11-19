import json,sys,glob
sys.path.insert(0,'harness'); import cases as R
sys.path.insert(0,'cases/layout/families/punct-compress-fit'); import generate as G
c=[x for x in R.discover() if x.id.endswith('punct-compress-fit/cases/marks.docx')][0]
W=[l['text'].replace(' ','') for p in json.load(open(c.oracle('lines.json')))['pages'] for l in p['lines']]
RUN=sys.argv[1] if len(sys.argv)>1 else None
EL=None
if RUN:
    E=json.load(open(f'runs/{RUN}/cases/{c.sha}.engine.json'))
    import collections
    EL=[]
    for p in E['pages']:
        rows=collections.defaultdict(list)
        for ch in p['chars']: rows[round(ch['y'],1)].append(ch)
        for y in sorted(rows): EL.append(''.join(x['t'] for x in sorted(rows[y],key=lambda x:x['x'])))
def first(lines):
    out=[];i=0
    for k,d,a in G.probes():
        c=0;f=None
        while c<51:
            f=f or len(lines[i]); c+=len(lines[i]); i+=1
        out.append(f-30)
    return out
fw=first(W); fe=first(EL) if EL else None
print('K digits: extra chars on line 1 for a=0..12')
for j,(k,d,a) in enumerate(G.probes()):
    if a==0: print(f"K={k} D={d} ",end='')
    print(f"{fw[j]}{'|'+str(fe[j]) if fe else ''}",end=' ')
    if a==12: print()
