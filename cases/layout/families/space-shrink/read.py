import json,sys,collections
MODE='15'
sys.path.insert(0,'harness'); import cases as R
sys.path.insert(0,'cases/layout/families/space-shrink'); import generate as G
c=[x for x in R.discover() if x.id.endswith(f'space-shrink/cases/words-c{MODE}.docx')][0]
def words(lines):
    out=[];i=0
    for kind,n,o in G.probes():
        need=(n+(4 if kind=='latin' else 3))*5
        got=None;total=0
        while total<need:
            k=len(lines[i].replace(' ',''))
            got=got if got is not None else k//5;total+=k;i+=1
        out.append(got)
    return out
W=[l['text'] for p in json.load(open(c.oracle('lines.json')))['pages'] for l in p['lines']]
fw=words(W)
fe=None
if len(sys.argv)>1:
    E=json.load(open(f'runs/{sys.argv[1]}/cases/{c.sha}.engine.json'))
    EL=[]
    for p in E['pages']:
        rows=collections.defaultdict(list)
        for ch in p['chars']: rows[round(ch['y'],1)].append(ch)
        for y in sorted(rows):
            cs=sorted(rows[y],key=lambda x:x['x']); s='';last=None
            for x in cs:
                if last is not None and x['x']-last>3: s+=' '
                s+=x['t'];last=x['x']+x['w']
            EL.append(s)
    fe=words(EL)
print('words on line 1 (all N fit = N), per overflow o=-2..18')
j=0
for kind,n in [(k,n) for k in G.KINDS for n in G.WORDS]:
    print(kind,'N=',n,' '.join(f"{o}:{fw[j+k]}{'|'+str(fe[j+k]) if fe else ''}" for k,o in enumerate(G.OVER) if True))
    j+=len(G.OVER)
