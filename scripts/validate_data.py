"""Validate the synthetic catalog and asset relationships. Pure Python 3."""
from pathlib import Path
import csv, collections, sys
root=Path(__file__).resolve().parents[1]
folder=root/'data'

def load(name):
    with (folder/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def ids(rows,field,name):
    x=[r[field] for r in rows]
    assert len(x)==len(set(x)), f'Duplicate {field} in {name}'
    assert all(x), f'Blank {field} in {name}'
    return set(x)

users=load('users.csv');assets=load('assets.csv');services=load('service_offerings.csv');incidents=load('incident_offerings.csv')
offerings=load('offerings.csv');cats=load('categories.csv');subs=load('subcategories.csv');maps=load('offering_mappings.csv')
fields=load('offering_fields.csv');manifest=load('knowledge_manifest.csv');queues=load('live_chat_queues.csv')
assert len(users)==200 and len(assets)==200 and len(services)==200 and len(cats)==200 and len(subs)>=200
assert len(incidents)==15 and len(offerings)==len(services)+len(incidents)
userids=ids(users,'user_id','users');assetids=ids(assets,'asset_id','assets');serviceids=ids(services,'offering_id','services');incidentids=ids(incidents,'offering_id','incidents')
offerids=ids(offerings,'offering_id','offerings');catids=ids(cats,'category_id','categories');subids=ids(subs,'subcategory_id','subcategories')
assert serviceids|incidentids==offerids
assert all(a['user_id'] in userids for a in assets), 'Unknown asset owner'
assert all(s['category_id'] in catids for s in subs), 'Unknown subcategory parent'
catby={c['category_id']:c for c in cats};subby={s['subcategory_id']:s for s in subs};offby={o['offering_id']:o for o in offerings}
seen=set()
for m in maps:
    k=(m['offering_id'],m['category_id'],m['subcategory_id'])
    assert k not in seen, f'Duplicate mapping: {k}'
    seen.add(k)
    assert k[0] in offby and k[1] in catby and k[2] in subby, f'Unknown mapping reference: {k}'
    assert subby[k[2]]['category_id']==k[1], f'Wrong subcategory parent: {k}'
    assert catby[k[1]]['ticket_type_id']==offby[k[0]]['ticket_type_id'], f'Ticket type mismatch: {k}'
assert all(f['offering_id'] in offerids for f in fields), 'Unknown offering field reference'
assert all((root / k['path']).is_file() for k in manifest), 'Missing knowledge document'
for q in queues:
    if q['category_id']:
        assert q['category_id'] in catby
        assert catby[q['category_id']]['ticket_type_id']==q['ticket_type_id']
assert all(len([m for m in maps if m['offering_id']==o])>0 for o in offerids), 'Offering without mappings'
print('VALIDATION PASSED')
for n,l in [('Users',users),('Assets',assets),('Service offerings',services),('Incident offerings',incidents),('All offerings',offerings),('Categories',cats),('Subcategories',subs),('Valid catalog mappings',maps),('Offering fields',fields),('Knowledge documents',manifest),('Live Chat queues',queues)]:print(f'  {n}: {len(l)}')
counts=collections.Counter(a['user_id'] for a in assets)
print('  DEMO001 asset count:',counts['DEMO001'])
