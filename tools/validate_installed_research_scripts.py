from pathlib import Path
import json,runpy,traceback,collections
from depibeans.legacy_timeline import load_timeline
from depibeans.camera_protocol import compile_camera
root=Path.home()/'DepiBeans';scripts=root/'releases/linux-stage-20260915/examples/research'
results=[]
def norm(e):
 common=(e['relative'],e['delay_ms'],e['kind'])
 return common+((e['command'],float(e['value'])) if e['kind']=='set' else (e['protocol'],e['analysis']))
for item in json.loads((scripts/'manifest.json').read_text()):
 result=dict(item)
 try:
  plan=runpy.run_path(str(scripts/item['python']))['build']()
  old=load_timeline((root/'reference'/item['source']).parent.parent/'Timeline.xml')
  actual=collections.Counter(norm(e) for e in plan['events']);expected=collections.Counter(norm(e) for e in old['events'])
  missing=expected-actual;extra=actual-expected
  protocol_match={p['id']:(p['analysis'],compile_camera(p['fields'])) for p in plan['protocols']}=={p['id']:(p['analysis'],compile_camera(p['fields'])) for p in old['protocols']}
  section_match={(p['number'],p['relative'],p['delay_ms']) for p in plan['sections']}=={(int(p['num']),p['rel']=='true',int(p['del'],36)) for p in old['sections']}
  result.update(protocol_match=protocol_match,section_match=section_match,events=len(plan['events']),recorded_events=len(old['events']),match=actual==expected,missing=sum(missing.values()),extra=sum(extra.values()),first_missing=list(missing)[:3],first_extra=list(extra)[:3],event_types=dict(collections.Counter(e['event_type'] for e in old['events'])))
  (scripts/(item['python']+'.plan.json')).write_text(json.dumps(plan,indent=2)+'\n')
 except Exception as e:result['error']=str(e);traceback.print_exc()
 results.append(result)
report={'scripts':len(results),'compiled':sum('error' not in r for r in results),'exact_event_matches':sum(r.get('match',False) for r in results),'protocol_matches':sum(r.get('protocol_match',False) for r in results),'section_matches':sum(r.get('section_match',False) for r in results),'results':results}
(root/'data/research-script-parity.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='results'}))
for r in results:
 if not (r.get('match') and r.get('protocol_match') and r.get('section_match')):print(json.dumps(r))
