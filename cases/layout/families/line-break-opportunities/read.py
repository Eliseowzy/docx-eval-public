import json,sys,collections
sys.path.insert(0,'harness'); import cases as R
F='layout/families/line-break-opportunities/cases/'
probes=[chr(int(l.strip()[2:],16)) for l in open('cases/'+F+'probes.txt')]
def second_lines(lines):
    out=[]; prev=None
    for l in lines:
        k=''.join(l.split())
        if prev is not None and prev.startswith('aaaa'): out.append(k)
        prev=k
    return out
res={}
for mode in ('14','15'):
    c=[x for x in R.discover() if x.id==F+f'probes-c{mode}.docx'][0]
    W=[l['text'] for p in json.load(open(c.oracle('lines.json')))['pages'] for l in p['lines']]
    RUN=sys.argv[1] if len(sys.argv)>1 else 'lbo-1'
    E=json.load(open(f'runs/{RUN}/cases/{c.sha}.engine.json'))
    el=[]
    for p in E['pages']:
        rows=collections.defaultdict(list)
        for ch in p['chars']: rows[round(ch['y'],1)].append(ch)
        for y in sorted(rows): el.append(''.join(c['t'] for c in sorted(rows[y],key=lambda c:c['x'])))
    res[mode]=(second_lines(W),second_lines(el))
print('char     c14:Word engine   c15:Word engine')
for i,p in enumerate(probes):
    row=[]
    for mode in ('14','15'):
        w,e=res[mode]
        f=lambda s: '?' if i>=len(s) else ('break' if s[i].startswith('ghij') else 'keep' if s[i].startswith('abcdef') else s[i][:8])
        row+= [f(w),f(e)]
    mark='' if row[0]==row[1] and row[2]==row[3] else '  <-- differs'
    print(f"U+{ord(p):04X} {p!r:6s}", '  '.join(f"{x:6s}" for x in row), mark)
