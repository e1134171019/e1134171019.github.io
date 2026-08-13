import json
import os
from pathlib import Path
import numpy as np

model=Path(os.environ.get('GNM_MODEL','/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
out=Path('artifacts/gnm-face-semantic-probe'); out.mkdir(parents=True,exist_ok=True)
with np.load(model,allow_pickle=False) as d:
    names=[str(x) for x in d['vertex_group_names']]
    vg=np.asarray(d['vertex_groups'],dtype=np.float64)
    v=np.asarray(d['template_vertex_positions'],dtype=np.float64)

rows=[]
for i,n in enumerate(names):
    mask=vg[i] > 0.5
    count=int(mask.sum())
    if count:
        pts=v[mask]
        rows.append({'index':i,'name':n,'count':count,'min':pts.min(0).tolist(),'max':pts.max(0).tolist()})

face_keywords=('eye','iris','pupil','sclera','skin','hockey','mouth','lip','nose','brow','cheek','chin','jaw','neck','face','forehead','tongue','teeth')
relevant=[r for r in rows if any(k in r['name'].lower() for k in face_keywords)]
res={'group_count':len(names),'nonempty_count':len(rows),'relevant':relevant,'all_names':names}
(out/'gnm_face_semantics.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
print(json.dumps(res,indent=2))
