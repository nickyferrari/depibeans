// Browser checks for the draft graph editor. Runs inside the hardware-blocked preview:
//   (await import('/__ui-test.js')).run()
// Pointer input is synthetic but dispatched at the real on-screen element positions.
export async function run(){
 const results=[],requests=[];
 const realFetch=window.fetch;window.fetch=(url,options={})=>{requests.push((options.method||'GET')+' '+url);return realFetch(url,options);};
 const chart=()=>document.getElementById('graph-timeline'),ta=()=>document.getElementById('plan-editor');
 const plan=()=>JSON.parse(ta().value);
 const ev=()=>plan().events.map(e=>e.kind[0]+':'+e.delay_ms+':'+(e.value??e.protocol)).join(' ');
 const center=i=>{const r=chart().querySelector(`[data-event="${i}"]`).getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2];};
 const indexOf=(kind,ms)=>plan().events.findIndex(e=>e.kind===kind&&e.delay_ms===ms);
 const fire=(type,x,y,mods={})=>{const hit=document.elementFromPoint(x,y),target=hit&&chart().contains(hit)?hit:chart();target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,clientX:x,clientY:y,button:0,buttons:type==='pointerup'?0:1,pointerId:1,isPrimary:true,...mods}));};
 const drag=(a,b,mods={})=>{fire('pointerdown',a[0],a[1],mods);for(let i=1;i<=8;i++)fire('pointermove',a[0]+(b[0]-a[0])*i/8,a[1]+(b[1]-a[1])*i/8,mods);fire('pointerup',b[0],b[1],mods);};
 const click=(a,mods={})=>{fire('pointerdown',a[0],a[1],mods);fire('pointerup',a[0],a[1],mods);};
 const pxPerMs=()=>{const n=plan().events.length-1;return (center(n)[0]-center(0)[0])/(plan().events[n].delay_ms-plan().events[0].delay_ms);};
 const btn=name=>[...document.querySelectorAll('.ge-bar button')].find(b=>b.textContent===name);
 const key=(k,mods={})=>chart().dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true,...mods}));
 const selected=()=>[...chart().querySelectorAll('.ge-on')].map(n=>Number(n.dataset.event));
 const status=()=>document.getElementById('graph-message').textContent;
 const setPlan=fn=>{const p=plan();fn(p);ta().value=JSON.stringify(p,null,2);ta().dispatchEvent(new Event('input',{bubbles:true}));};
 const view=()=>[Number(document.getElementById('graph-start').value)*3600000,Number(document.getElementById('graph-span').value)*3600000].map(Math.round);
 const check=(name,pass,detail='')=>results.push({name,pass:!!pass,detail:String(detail)});
 const emptyAt=ms=>{const r=chart().getBoundingClientRect(),x0=center(0)[0];return [x0+ms*pxPerMs(),r.y+r.height*.45];};
 chart().scrollIntoView({block:'center'});await new Promise(r=>setTimeout(r,200));

 // Off-grid timestamps, entered through the JSON draft.
 setPlan(p=>{p.events.find(e=>e.protocol==='dark-reference').delay_ms=75430;p.events.find(e=>e.value==='500').delay_ms=100250;});
 const baseline=ev();
 check('5 one renderer: points stay editable after a JSON edit',chart().querySelectorAll('[data-event]').length===8&&chart().querySelectorAll('circle,rect[rx]').length===8,chart().querySelectorAll('[data-event]').length+' of 8');
 check('5 host Undo button retired (single history)',getComputedStyle(document.getElementById('graph-undo')).display==='none');

 // 3 precision
 click(center(indexOf('set',100250)));
 const timeField=document.getElementById('graph-time'),valueField=document.getElementById('graph-value');
 check('3 inspector shows exact time',timeField.value==='100.25',timeField.value);
 valueField.value='450';document.getElementById('graph-apply').click();
 check('3 intensity-only Apply keeps 100250 ms',ev().includes('s:100250:450'),ev());
 let a=center(indexOf('set',100250));drag(a,[a[0]+20000*pxPerMs(),a[1]]);
 const moved=plan().events.find(e=>e.value==='450');
 check('3 single drag: offset snaps, sub-grid remainder kept',moved.delay_ms%100===50&&Math.abs(moved.delay_ms-120250)<=200,moved.delay_ms);
 check('3 light value stays an integer string',typeof moved.value==='string'&&/^\d+$/.test(moved.value),JSON.stringify(moved.value));
 // box-select the two early measurements and drag them together
 const b0=center(indexOf('capture',30000)),b1=center(indexOf('capture',75430));
 drag([b0[0]-12,b0[1]-14],[b1[0]+12,b1[1]+14]);
 check('box select picks 2',selected().length===2,selected().join());
 a=center(indexOf('capture',30000));drag(a,[a[0]+15700*pxPerMs(),a[1]]);
 const caps=plan().events.filter(e=>e.kind==='capture').slice(0,2).map(e=>e.delay_ms);
 check('3 group drag keeps 45430 ms spacing',caps[1]-caps[0]===45430&&caps[0]%100===0,caps.join());
 check('2 selection follows the moved events',selected().length===2&&selected().every(i=>plan().events[i].kind==='capture'&&plan().events[i].delay_ms<100000),selected().join());

 // 1 undo / redo depth
 const afterThree=ev();
 btn('Undo').click();btn('Undo').click();btn('Undo').click();
 check('1 three undos return to the baseline',ev()===baseline,ev());
 btn('Redo').click();btn('Redo').click();btn('Redo').click();
 check('1 three redos return to the latest state',ev()===afterThree,ev());
 check('1 redo exhausted',btn('Redo').disabled);
 btn('Undo').click();
 const zoomBefore=view();btn('+').click();const zoomed=view();
 btn('Undo').click();
 check('1 undo keeps the zoomed view',view().join()===zoomed.join()&&zoomed[1]<zoomBefore[1],view().join());
 btn('Fit').click();
 // host action shares the history
 const beforeHost=ev();document.getElementById('graph-light').click();
 check('5 host "Add light change" selects the new point here',selected().length===1&&plan().events[selected()[0]].kind==='set',selected().join());
 check('1 a new edit clears redo',btn('Redo').disabled);
 btn('Undo').click();
 check('1 host action is undone by the same Undo',ev()===beforeHost,ev());
 btn('Redo').click();btn('Undo').click();
 while(!btn('Undo').disabled)btn('Undo').click();
 check('1 full unwind reaches the baseline',ev()===baseline,ev());
 while(!btn('Redo').disabled)btn('Redo').click();

 // 2 stable selection across an outside re-sort
 click(center(indexOf('capture',385000)));
 setPlan(p=>p.events.push({kind:'set',command:'intensity',value:'10',delay_ms:250000,relative:true}));
 check('2 selection survives an inserted event',selected().length===1&&plan().events[selected()[0]].delay_ms===385000,selected().join());
 const count=plan().events.length;btn('Delete').click();
 check('2 Delete removes the selected 385 s measurement only',plan().events.length===count-1&&indexOf('capture',385000)<0&&indexOf('capture',300000)>=0,ev());
 btn('Undo').click();

 // 4 protocol reuse
 const protocols=plan().protocols.map(p=>p.id).join();
 click(center(indexOf('capture',200000)));click(center(indexOf('capture',300000)),{shiftKey:true});
 check('shift-click extends selection',selected().length===2);
 key('c',{metaKey:true});click(emptyAt(215000));key('v',{metaKey:true});
 check('4 paste reuses protocol references',plan().protocols.map(p=>p.id).join()===protocols&&plan().events.filter(e=>e.protocol==='light-adapted').length===5,plan().protocols.map(p=>p.id).join()+' | '+ev());
 a=center(indexOf('capture',300000));click(a);drag(a,[a[0]+30000*pxPerMs(),a[1]],{altKey:true});
 check('4 Alt-drag duplicates and keeps the original',indexOf('capture',300000)>=0&&indexOf('capture',330000)>=0&&plan().protocols.map(p=>p.id).join()===protocols,ev());
 check('4 no "-copy-" protocols',!plan().protocols.some(p=>/copy/.test(p.id)));

 // paste bounds and collisions
 let before=ev();click(emptyAt(399000));key('v',{metaKey:true});
 check('paste past the end is refused',ev()===before&&/fit/i.test(status()),status());
 click(center(indexOf('capture',200000)));key('c',{metaKey:true});click(emptyAt(200000));key('v',{metaKey:true});
 check('paste onto an identical event is refused',ev()===before&&/Overlap/.test(status()),status());
 check('paste cursor drawn inside the plot',(()=>{const c=chart().querySelector('.ge-cursor');if(!c)return false;const g=chart().getBoundingClientRect(),x=c.getBoundingClientRect().x;return x>=g.x&&x<=g.right;})());

 // keyboard nudging
 click(center(indexOf('capture',200000)));const undoDepthProbe=ev();
 key('ArrowRight');key('ArrowRight');key('ArrowRight',{shiftKey:true});
 check('arrows nudge 0.1 s, Shift 1 s',indexOf('capture',201200)>=0,ev());
 btn('Undo').click();check('a run of nudges is one undo step',ev()===undoDepthProbe,ev());
 click(center(plan().events.findIndex(e=>e.kind==='set'&&e.delay_ms>0&&e.delay_ms<400000)));const lv=Number(plan().events[selected()[0]].value);
 key('ArrowDown');key('ArrowDown',{shiftKey:true});
 check('arrows change light by 1, Shift 10',Number(plan().events[selected()[0]].value)===lv-11,plan().events[selected()[0]].value);
 // boundary settings keep their time
 before=ev();click(center(0));key('ArrowRight');check('first light setting keeps t = 0',plan().events[0].delay_ms===0&&ev()===before,status());
 key('Delete');check('first light setting cannot be deleted',ev()===before,status());

 // zoom, pan, fit
 btn('Fit').click();const full=view(),mid=emptyAt(200000);
 chart().dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,ctrlKey:true,deltaY:-40,clientX:mid[0],clientY:mid[1]}));
 const z=view();check('ctrl/⌘-wheel zooms about the pointer',z[1]<full[1]&&z[0]>0&&z[0]+z[1]<full[1],z.join());
 chart().dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaX:80,deltaY:0,clientX:mid[0],clientY:mid[1]}));
 check('horizontal wheel pans',view()[0]>z[0]&&view()[1]===z[1],view().join());
 for(let i=0;i<40;i++)btn('+').click();check('zoom floor 2 s',view()[1]===2000,view().join());
 const label=[...chart().querySelectorAll('.ge-tick')].map(n=>n.textContent).find(t=>/\.\d s$/.test(t));check('0.1 s ticks at full zoom',!!label,label);
 key('f');check('F fits',view().join()===full.join(),view().join());

 // expand
 btn('Expand').click();await new Promise(r=>setTimeout(r,250));
 const big=chart().getBoundingClientRect();check('Expand fills the window with graph and script',document.querySelector('.ge-expanded').getBoundingClientRect().height>=innerHeight-2&&big.height>=200&&big.width>innerWidth*.9&&document.querySelector('.ge-code').getBoundingClientRect().height>=96,Math.round(big.width)+'×'+Math.round(big.height));
 a=center(indexOf('capture',200000));click(a);check('editing works while expanded',selected().length===1);
 key('Escape');key('Escape');await new Promise(r=>setTimeout(r,250));
 check('Esc collapses',!document.querySelector('.ge-expanded')&&chart().getBoundingClientRect().height<innerHeight*.6);

 // script panel: same plan as text, both directions
 const code=document.querySelector('.ge-code'),scriptState=()=>document.querySelector('.ge-script-state').textContent;
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const type=async text=>{code.focus();code.value=text;code.dispatchEvent(new Event('input',{bubbles:true}));await wait(400);};
 const lines=()=>code.value.split('\n');
 // Collapsing the fullscreen editor can leave the graph outside the viewport.
 // Synthetic pointer hits, like real mouse clicks, require a visible target.
 btn('Fit').click();chart().scrollIntoView({block:'center'});chart().focus();await wait(200);
 check('S script lists every event',lines().length===plan().events.length+1&&/^duration 400 s$/.test(lines()[0]),lines()[0]+' / '+lines().length+' lines');
 check('S exact times shown',lines().some(l=>/^100\.25\s+light \d+/.test(l))&&lines().some(l=>/measure dark-reference/.test(l)),lines().slice(1,5).join(' ; '));
 // graph -> script
 a=center(indexOf('capture',200000));click(a);key('ArrowRight');
 check('S graph edit rewrites the line',lines().some(l=>/^200\.1\s+measure light-adapted/.test(l)),lines().find(l=>/^200/.test(l)));
 const onLines=()=>[...document.querySelectorAll('.ge-gutter .ge-ln-on')].map(n=>Number(n.textContent));
 check('S selected point highlights its line',onLines().length===1&&/^200\.1/.test(lines()[onLines()[0]-1]),onLines().join());
 btn('Undo').click();
 // script -> graph
 const beforeScript=ev(),depth=()=>{let n=0;while(!btn('Undo').disabled){btn('Undo').click();n++;}for(let i=0;i<n;i++)btn('Redo').click();return n;};
 const d0=depth();
 await type(code.value.replace(/^100\.25(\s+)light \d+/m,'100.25$1light 321'));
 check('S typing a level updates the plan, time untouched',plan().events.some(e=>e.delay_ms===100250&&e.value==='321'),ev());
 check('S typed level moves the graph point',(()=>{const i=indexOf('set',100250),n=chart().querySelector(`[data-event="${i}"]`);return !!n;})());
 await type(code.value.replace(/^(400\s+light 0.*)$/m,'+10 measure light-adapted  # extra\n$1'));
 const lastCap=plan().events.filter(e=>e.kind==='capture').at(-1);
 check('S "+10" adds an event after the previous line, note kept as label',plan().events.some(e=>e.kind==='capture'&&e.label==='extra'),JSON.stringify(lastCap));
 check('S protocols unchanged by script edits',plan().protocols.map(p=>p.id).join()===protocols);
 check('S one typing burst is one undo step',depth()===d0+1,depth()+' vs '+d0);
 const good=ev();
 await type(code.value.replace('light 321','light 321.5'));
 check('S invalid line is flagged and the plan is untouched',ev()===good&&/^Line \d+: Light level/.test(scriptState())&&document.querySelectorAll('.ge-ln-error').length===1,scriptState());
 await type(code.value.replace('light 321.5','light 321').replace(/measure light-adapted\s+# extra/,'measure nothing-here'));
 check('S unknown protocol is refused with the available names',ev()===good&&/Unknown protocol/.test(scriptState())&&/light-adapted/.test(scriptState()),scriptState());
 await type(code.value.replace('measure nothing-here','measure light-adapted  # extra'));
 check('S fixing the line clears the error',scriptState()===''&&ev()===good,scriptState());
 await type(code.value+'\nevery 5 from 250 to 260 set FR 12');
 check('S "every" expands into plain events on other channels',plan().events.filter(e=>e.command==='FR'&&e.value==='12').map(e=>e.delay_ms).join()==='250000,255000,260000',ev());
 chart().focus();code.dispatchEvent(new Event('blur'));await wait(50);
 check('S leaving the script shows canonical lines',lines().filter(l=>/set FR 12/.test(l)).length===3&&!/every/.test(code.value));
 // caret selects in the graph
 code.focus();const target=lines().findIndex(l=>/^200\s+measure/.test(l)),offset=lines().slice(0,target).join('\n').length+1;code.setSelectionRange(offset,offset);code.dispatchEvent(new MouseEvent('click',{bubbles:true}));
 check('S caret on a line selects that point',selected().length===1&&plan().events[selected()[0]].delay_ms===200000,selected().join());
 // duration from script
 await type(code.value.replace(/^duration 400 s/,'duration 500 s'));
 check('S duration line changes the experiment duration',plan().studio.duration_ms===500000&&document.getElementById('studio-days').value==='500',plan().studio.duration_ms+' / '+document.getElementById('studio-days').value);
 chart().focus();code.dispatchEvent(new Event('blur'));await wait(50);
 btn('Undo').click();
 check('S undo restores duration and script together',plan().studio.duration_ms===400000&&/^duration 400 s/.test(code.value)&&document.getElementById('studio-days').value==='400',code.value.split('\n')[0]);
 while(depth()>d0)btn('Undo').click();
 check('S undo returns to the pre-script plan',ev()===beforeScript,ev());

 // adaptive units on a 3-day plan
 document.getElementById('studio-days').value=3;document.getElementById('duration-unit').value='days';document.getElementById('studio-days').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('studio-days').dispatchEvent(new Event('change',{bubbles:true}));
 const apply=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Apply duration');apply?.click();await new Promise(r=>setTimeout(r,200));btn('Fit').click();
 const dayTicks=[...chart().querySelectorAll('.ge-tick')].map(n=>n.textContent).filter(t=>/:|day/.test(t));check('multi-day axis uses clock/day labels',dayTicks.length>2,dayTicks.slice(0,4).join(' , '));
 click(center(indexOf('capture',200000)>=0?indexOf('capture',200000):1));check('inspector uses h:mm:ss on long plans',/^\d\d:\d\d:\d\d/.test(timeField.value),timeField.value);

 // isolation: another draft starts with empty history
 document.getElementById('new-experiment').click();await new Promise(r=>setTimeout(r,300));
 check('1 new draft clears undo and redo',btn('Undo').disabled&&btn('Redo').disabled);


 // Persistent repeats and preset insertion (draft-only).
 await type('duration 400 s\n0 light 0\n400 light 0\nrepeat 3 every 100 from 0\n  10 light 200\n  20 light 0\nend');
 chart().focus();code.dispatchEvent(new Event('blur'));await wait(80);
 check('R block produces six events and stays a block',plan().studio.repeats.length===1&&plan().events.filter(e=>e.repeat).length===6&&code.value.includes('repeat 3'));
 const askButton=name=>[...document.querySelectorAll('.ge-ask button')].find(b=>b.textContent===name);
 const repeatBefore=ev();click(center(indexOf('set',110000)));key('ArrowRight');
 check('R edit waits for scope confirmation',ev()===repeatBefore&&!document.querySelector('.ge-ask').hidden);
 askButton('Cancel').click();check('R cancel preserves plan',ev()===repeatBefore);
 click(center(indexOf('set',110000)));key('ArrowRight');askButton('Change all').click();
 check('R change all shifts corresponding instances',plan().events.filter(e=>e.repeat?.k===0).map(e=>e.delay_ms).join()==='10100,110100,210100');
 btn('Undo').click();check('R undo restores all instances',ev()===repeatBefore);
 click(center(indexOf('set',110000)));key('ArrowRight');
 check('R each edit asks again',!document.querySelector('.ge-ask').hidden);
 askButton('Only this').click();
 check('R detach changes one instance only',plan().events.some(e=>e.delay_ms===110100&&!e.repeat)&&plan().events.filter(e=>e.repeat).length===5);
 const detached=ev();await type(code.value+'\n');chart().focus();code.dispatchEvent(new Event('blur'));await wait(80);
 check('R script roundtrip keeps detached instance',ev()===detached&&plan().studio.repeats[0].skip.length===1);
 btn('Undo').click();
 for(const preset of ['dark','npq','response']){
  document.getElementById('new-experiment').click();await wait(100);
  const prior=JSON.stringify(plan());const menu=document.querySelector('.ge-insert');menu.value=preset;menu.dispatchEvent(new Event('change',{bubbles:true}));
  check('P '+preset+' inserts measurements',plan().events.some(e=>e.kind==='capture')&&JSON.stringify(plan())!==prior);
  btn('Undo').click();check('P '+preset+' one undo restores entire plan',JSON.stringify(plan())===prior);
 }
 check('UI start clearly named',document.getElementById('editor-start').textContent==='Review & start');
 check('UI run group separate from Save',document.querySelector('.run-controls')?.contains(document.getElementById('editor-start'))&&!document.querySelector('.run-controls')?.contains(document.getElementById('save-plan')));
 window.fetch=realFetch;
 const writes=requests.filter(r=>!r.startsWith('GET'));
 check('draft only: no POST requests during editing',writes.length===0,writes.join(' ; ')||requests.length+' GETs: '+[...new Set(requests)].join(' , '));
 return {passed:results.filter(r=>r.pass).length,failed:results.filter(r=>!r.pass),total:results.length,all:results.map(r=>(r.pass?'PASS ':'FAIL ')+r.name)};
}
