import json,sys
sys.path.insert(0,'harness'); import cases as R
sys.path.insert(0,'cases/layout/families/bracket-autospace'); import generate as G
c=[x for x in R.discover() if x.id.endswith('bracket-autospace/cases/groups.docx')][0]
W=[l['text'].replace(' ','') for p in json.load(open(c.oracle('lines.json')))['pages'] for l in p['lines']]
i=0;res={}
for oc,t,a in G.probes():
    need=31+20-(0)
    total=0;first=None
    # chars per paragraph: m + 3t + 1 + 20
    m=30-5*t//3
    need=m+3*t+1+20
    while total<need:
        first=first or len(W[i]);total+=len(W[i]);i+=1
    res.setdefault((oc,t),[]).append((a,first-(m+3*t) ))
for (oc,t),v in res.items():
    ok=[a for a,f in v if f>=1]
    print(oc,t,'smallest a with all on line 1:',ok[0] if ok else None)
