"""Offline, bounded converter for the captured chamber's JavaScript subset.

Requires esprima only during conversion. Emits ordinary Python that uses the
DepiBeans experiment API; never imports or executes the legacy Java header.
Unsupported syntax is an error. This is migration tooling, not a JS sandbox.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import esprima

METHODS = {'setNumberLoops':'NumberLoops','setFramesPerLoop':'FramesPerLoop',
 'setMeasuringLight':'MeasuringLight','setSaturationFlash':'SaturationFlash',
 'setExposure':'Exposure','setFrameInterval':'FrameInterval'}

class Converter:
 def __init__(self): self.lines=[]
 def line(self,text,level):self.lines.append('    '*level+text)
 def name(self,name):
  if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name):raise ValueError('Unsupported identifier '+name)
  return 'v_'+name
 def expr(self,n):
  t=n['type']
  if t=='Literal':return repr(n['value'])
  if t=='Identifier':return self.name(n['name'])
  if t=='ArrayExpression':return '['+', '.join(self.expr(x) for x in n['elements'])+']'
  if t=='BinaryExpression':
   op=n['operator']
   if op not in ('+','-','*','/','<','<=','>','>=','==','!='):raise ValueError('Unsupported operator '+op)
   a,b=self.expr(n['left']),self.expr(n['right'])
   return f'js_add({a}, {b})' if op=='+' else f'({a} {op} {b})'
  if t=='UnaryExpression' and n['operator'] in ('+','-'):return '('+n['operator']+self.expr(n['argument'])+')'
  if t=='MemberExpression' and n['computed']:return self.expr(n['object'])+'['+self.expr(n['property'])+']'
  if t=='NewExpression' and n['callee']=={'type':'Identifier','name':'CameraProtocol'}:
   return 'session.new_protocol('+', '.join(self.expr(a) for a in n['arguments'])+')'
  if t=='CallExpression':
   c=n['callee'];args=', '.join(self.expr(a) for a in n['arguments'])
   if c['type']=='Identifier':
    name=c['name'];mapping={'wait':'experiment.wait','wait_until':'experiment.wait_until','EOD':'experiment.end_section','run_camera_protocol':'session.capture'}
    if name in mapping:return mapping[name]+'('+args+')'
    if name in ('set_intensity','set_FR'):return 'experiment.set('+repr(name[4:])+', '+args+')'
    if name not in self.functions:raise ValueError('Unknown function '+name)
    return self.name(name)+'('+args+')'
   raise ValueError('Unsupported call expression')
  raise ValueError('Unsupported expression '+t)
 def statement(self,n,level):
  t=n['type']
  if t in ('Program','BlockStatement'):
   for x in n['body']:self.statement(x,level)
  elif t=='VariableDeclaration':
   for d in n['declarations']:self.line(self.expr(d['id'])+' = '+(self.expr(d['init']) if d.get('init') else 'None'),level)
  elif t=='FunctionDeclaration':
   self.line('def '+self.name(n['id']['name'])+'('+', '.join(self.expr(p) for p in n['params'])+'):',level)
   self.statement(n['body'],level+1)
   if not n['body']['body']:self.line('pass',level+1)
  elif t=='ForStatement':
   self.statement(n['init'],level);self.line('while '+self.expr(n['test'])+':',level)
   self.line('session.tick()',level+1);self.statement(n['body'],level+1);self.statement(n['update'],level+1)
  elif t=='ExpressionStatement':self.statement(n['expression'],level)
  elif t=='AssignmentExpression':
   if n['operator'] not in ('=','+=','-='):raise ValueError('Unsupported assignment')
   self.line(self.expr(n['left'])+' '+n['operator']+' '+self.expr(n['right']),level)
  elif t=='UpdateExpression' and n['operator'] in ('++','--'):
   self.line(self.expr(n['argument'])+(' += 1' if n['operator']=='++' else ' -= 1'),level)
  elif t=='CallExpression':
   c=n['callee']
   if c['type']=='Identifier' and c['name']=='upload_camera_protocol':
    self.line('# Legacy upload_camera_protocol was already a no-op.',level);return
   if c['type']=='MemberExpression' and not c['computed']:
    obj=self.expr(c['object']);method=c['property']['name'];args=n['arguments']
    if len(args)!=1:raise ValueError('Expected one setter argument')
    val=self.expr(args[0])
    if method in METHODS:self.line(f'{obj}.fields[{METHODS[method]!r}] = {val}',level)
    elif method=='setAnalysisID':self.line(f'{obj}.analysis = {val}',level)
    elif method in ('setDelayCaptureBy','setDelayPostCaptureBy'):self.line('# Legacy '+method+' was ignored; timing comes from the chamber profile.',level)
    else:raise ValueError('Unsupported protocol method '+method)
   else:self.line(self.expr(n),level)
  else:raise ValueError('Unsupported statement '+t)
 def convert(self,source,name):
  tree=esprima.parseScript(source).toDict()
  self.functions={n['id']['name'] for n in tree['body'] if n['type']=='FunctionDeclaration'}
  self.lines=['"""Converted saved experiment. Compile only; no hardware access."""',
   'from depibeans.scripting import Experiment',
   'from depibeans.research_scripts import ScriptSession, js_add','',
   'def build():',f'    experiment = Experiment({name!r})','    session = ScriptSession(experiment)']
  # JavaScript function declarations are hoisted; keep definitions before calls.
  for n in tree['body']:
   if n['type']=='FunctionDeclaration':self.statement(n,1)
  for n in tree['body']:
   if n['type']!='FunctionDeclaration':self.statement(n,1)
  self.line('return session.compile()',1)
  self.lines += ['', 'if __name__ == "__main__":','    import json','    print(json.dumps(build(), indent=2))','']
  result='\n'.join(self.lines);compile(result,name,'exec');return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('reference',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=True);manifest=[]
 for source in sorted(a.reference.rglob('Body.js')):
  digest=hashlib.sha256(source.read_bytes()).hexdigest();name=source.parent.parent.name
  out=a.output/(name+'-'+digest[:8]+'.py')
  out.write_text(Converter().convert(source.read_text(),name))
  manifest.append({'source':str(source.relative_to(a.reference)),'source_sha256':digest,'python':out.name})
 (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'converted':len(manifest),'output':str(a.output)}))
