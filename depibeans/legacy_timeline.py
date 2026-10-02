"""Lossless, hardware-free intake of saved Phenomics XML timelines.

Records historical timestamps and errors without treating them as new commands.
Both 0.7 base36 epoch timestamps and 0.9 ISO timestamps are accepted.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET


def timestamp(value, version):
    if value is None:return None
    if version == '0.7':return int(value,36)
    return round(datetime.fromisoformat(value).timestamp()*1000)


def xml_record(element):
    return {'tag':element.tag,'attributes':dict(element.attrib),'text':element.text,
            'children':[xml_record(e) for e in element]}


def load_timeline(path):
    path=Path(path); data=path.read_bytes()
    if len(data)>32*1024*1024:raise ValueError('Timeline exceeds 32 MiB limit')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('DTD/entities are not supported')
    root=ET.fromstring(data)
    version=root.get('version')
    if root.tag!='Timeline' or version not in {'0.7','0.9'}:raise ValueError('Unsupported timeline format')
    events=[]; protocols=[]; sections=[]
    for analysis in root.findall('./PROTOCOLS/Analysis'):
        for p in analysis.findall('Protocol'):
            protocols.append({'analysis':analysis.get('id'),'id':p.get('id'),
                'group':p.findtext('SensorGroup'),'sensors':[e.text for e in p.findall('Sensor')],
                'fields':{e.get('key'):e.get('val') for e in p.findall('param')}})
    for section in root.findall('Section'):
        sections.append(dict(section.attrib))
        for stream in section:
            if stream.tag=='SetTimeline':
                entries=[(e,{'kind':'set','command':stream.get('type'),'value':e.get('val')}) for e in stream.findall('Event')]
            elif stream.tag=='ProtocolTimeline':
                entries=[(e,{'kind':'capture','analysis':stream.get('analysisID'),'protocol':p.get('id')}) for p in stream.findall('Protocol') for e in p.findall('Event')]
            else:
                # Preserve unknown streams in raw_tree; refuse to claim execution coverage.
                entries=[(e,{'kind':'unsupported','stream':stream.tag}) for e in stream.iter('Event')]
            for e,extra in entries:
                rel=e.get('rel')
                if rel not in {'true','false'}:raise ValueError('Missing/invalid event relativity')
                events.append(dict(extra,sequence=len(events),section=section.get('num'),
                    delay_ms=int(e.attrib['del'],36),relative=rel=='true',event_type=e.get('type'),
                    executed_start_ms=timestamp(e.get('exS'),version),
                    executed_end_ms=timestamp(e.get('exE'),version),record=xml_record(e)))
    if len(events)!=len(list(root.iter('Event'))):raise ValueError('Unmapped event hierarchy')
    timing=root.find('./Information/Timing')
    return {'schema':'depibeans.legacy-intake/1','source':str(path),'source_sha256':hashlib.sha256(data).hexdigest(),
            'legacy_version':version,'hardware_execution_authorized':False,
            'timing':dict(timing.attrib) if timing is not None else {},
            'sections':sections,'protocols':protocols,'events':events,'raw_tree':xml_record(root)}


def summary(plan):
    kinds=Counter(e['kind'] for e in plan['events'])
    return {'source':plan['source'],'sha256':plan['source_sha256'],'legacy_version':plan['legacy_version'],
            'events':len(plan['events']),'event_kinds':dict(kinds),'protocols':len(plan['protocols']),
            'recorded_errors':sum(count_tag(e['record'],'Exception') for e in plan['events'])}


def count_tag(node, tag):
    return int(node['tag']==tag)+sum(count_tag(c,tag) for c in node['children'])
