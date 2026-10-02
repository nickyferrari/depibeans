// Editable experiment components. Produces the same executable event schema as the graph.
(function(root){
const DAY=86400000, sources=[{title:'Murchie & Lawson (2013)',url:'https://doi.org/10.1093/jxb/ert208'},{title:'Baker (2008)',url:'https://doi.org/10.1146/annurev.arplant.59.032607.092759'},{title:'Govindjee & Seufferheld (2002)',url:'https://doi.org/10.1071/FP02061'}];
function number(x,min,max,label){if(x===null||x===undefined||String(x).trim()==='')throw Error('Enter '+label+'.');x=Number(x);if(!Number.isFinite(x)||x<min||x>max)throw Error(label+' must be '+min+'–'+max+'.');return x;}
function finish(p){p.events.sort((a,b)=>a.delay_ms-b.delay_ms);p.events.forEach((e,i)=>e.sequence=i);if(p.events.length>10000)throw Error('More than 10,000 events. Increase the light step or measurement interval.');return p;}
function light(t,v){return {kind:'set',relative:true,delay_ms:Math.round(t),command:'intensity',value:String(Math.round(v))};}
function waveMs(proto){const f=proto.fields,n=Number(f.NumberLoops),val=(key,i)=>{const a=String(f[key]).split(',');return a[Math.min(i,a.length-1)];},sec=s=>{const m=s.match(/^([\d.]+)(us|ms|s)$/);if(!m)throw Error('Use us, ms or s in pulse durations.');return +m[1]*{us:.000001,ms:.001,s:1}[m[2]];};let total=0;for(let i=0;i<n;i++)total+=Number(val('FramesPerLoop',i))*(sec(val('FrameInterval',i))+sec(val('Exposure',i))+.00007)*1000;return total;}
function compose(plan,c){const p=structuredClone(plan),duration=number(c.duration,1000,366*DAY,'Duration'),first=number(c.first,1,366,'First day'),last=number(c.last,first,366,'Last day');if(!Number.isInteger(first)||!Number.isInteger(last))throw Error('Use whole day numbers.');const dawn=number(c.dawn,0,24,'Lights on'),period=number(c.photoperiod,.001,24,'Photoperiod'),peak=number(c.peak,0,500,'Maximum intensity'),night=number(c.night,0,peak,'Night intensity'),step=number(c.step,1,86400,'Light step')*1000;if(dawn+period>24)throw Error('Lights on plus photoperiod must fit within one day.');if(!['constant','triangle','sine'].includes(c.shape))throw Error('Choose a base shape.');const start=(first-1)*DAY,end=Math.min(last*DAY,duration);if(start>=duration)throw Error('Day range starts after the experiment ends.');
const layers=(c.layers||[]).map(l=>({...l,amplitude:number(l.amplitude,-500,500,'Layer amplitude'),period:number(l.period,1,1440,'Layer period'),hold:number(l.hold,.01,1440,'Layer hold')}));for(const l of layers)if(l.hold>l.period)throw Error('Layer hold cannot exceed its period.');
const value=t=>{let h=(t%DAY)/3600000;if(h<dawn||h>=dawn+period)return night;const f=(h-dawn)/period;let v=night+(peak-night)*(c.shape==='constant'?1:c.shape==='triangle'?1-Math.abs(2*f-1):Math.sin(Math.PI*f));for(const l of layers){const elapsed=Math.round(t%DAY-dawn*3600000),periodMs=Math.round(l.period*60000),holdMs=Math.round(l.hold*60000),phase=elapsed/periodMs;v+=l.shape==='sine'?l.amplitude*Math.sin(2*Math.PI*phase):(elapsed%periodMs<holdMs?l.amplitude:0);}return Math.round(Math.max(0,Math.min(peak,v)));};
const times=new Set([start]);for(let day=first;day<=last;day++){const d=(day-1)*DAY,a=d+dawn*3600000,b=a+period*3600000;if(d<end)times.add(d);if(a<end)times.add(Math.round(a));if(b<end)times.add(Math.round(b));const samples=Math.ceil(period*3600000/step);if(samples*(last-first+1)>10000)throw Error('Increase the light step: this profile exceeds 10,000 samples.');for(let t=a;t<b&&t<end;t+=step)times.add(Math.round(t));for(const l of layers)if(l.shape==='pulse'){const count=Math.ceil(period*60/l.period);if(count*(last-first+1)>5000)throw Error('Increase the fluctuation period.');for(let i=0;i<count;i++)for(const t of [a+i*l.period*60000,a+i*l.period*60000+l.hold*60000])if(t<b&&t<end)times.add(Math.round(t));}}
let windows=[];if(c.holdMeasurements){windows=p.events.filter(e=>e.kind==='capture').map(e=>{const proto=p.protocols.find(x=>x.id===e.protocol);return [e.delay_ms-30000,e.delay_ms+waveMs(proto)+10000];});for(const [a,b]of windows){if(a>=start&&a<end)times.add(Math.round(a));if(b+1>=start&&b+1<end)times.add(Math.ceil(b+1));}}
let events=[...times].sort((a,b)=>a-b).filter(t=>t>=start&&t<end&&!windows.some(([a,b])=>t>a&&t<=b)).map(t=>light(t,value(t)));events=events.filter((e,i)=>i===0||e.value!==events[i-1].value);p.events=p.events.filter(e=>!(e.kind==='set'&&e.command==='intensity'&&e.delay_ms>=start&&e.delay_ms<end));p.events.push(...events);if(!p.events.some(e=>e.kind==='set'&&e.command==='intensity'&&e.delay_ms===duration))p.events.push(light(duration,0));p.studio={...p.studio,duration_ms:duration,light_components:structuredClone(c)};return finish(p);}
function fields(type,c){const pair=['dark-reference','light-adapted'].includes(type),frames=number(c.frames,1,50,'Frames per phase'),exposure=number(c.exposure,1,100000,'Exposure'),interval=number(c.interval,95,30000,'Frame interval');if(!Number.isInteger(frames))throw Error('Frames must be an integer.');return {NumberLoops:pair?'2':'1',FramesPerLoop:pair?frames+','+frames:String(frames),MeasuringLight:type==='background'?'0':'1',SaturationFlash:pair?'0,1':type==='saturation'?'1':'0',AuxFastSwitch:'0',Exposure:exposure+'us',FrameInterval:interval+'ms',ActinicShutter:'1'};}
function preset(c){const type=c.type,dark=number(c.darkMinutes,0,1440,'Dark adaptation')*60000,level=number(c.intensity,0,500,'Actinic intensity'),p={schema:'depibeans.experiment-plan/1',name:c.name||({'dark':'Dark yield · F₀ / Fm','npq':'NPQ induction and recovery','response':'Light response · Fs / Fm′'}[type]),execution:{capture_failure:'stop',on_stop_light:0},protocols:[],events:[light(0,0)],studio:{protocol_preset:{...c,sources,adaptation:'Operator-selected duration; confirm dark adaptation and saturation adequacy for the sample.'}}};
const proto=t=>{if(!p.protocols.some(x=>x.id===t))p.protocols.push({id:t,measurement_type:t,analysis:t,group:'*',sensors:['*'],fields:fields(t,c)});return t;},capture=(t,kind,label)=>p.events.push({kind:'capture',relative:true,delay_ms:Math.round(t),protocol:proto(kind),label});capture(30000,'background','Camera background');const ref=Math.max(75000,dark);capture(ref,'dark-reference','Dark F₀ / Fm');let end=ref+15000;
if(type==='npq'){const on=ref+25000,duration=number(c.lightMinutes,1,1440,'Light duration')*60000,n=number(c.count,1,100,'Light measurements'),recovery=number(c.recoveryMinutes,0,1440,'Recovery duration')*60000;if(!Number.isInteger(n))throw Error('Use a whole number of measurements.');p.events.push(light(on,level));for(let i=1;i<=n;i++){const at=i===n?duration-15000:duration*i/n;capture(on+at,'light-adapted','Light '+i);}const off=on+duration;p.events.push(light(off,0));end=off;if(recovery){const count=Math.max(1,Math.floor(recovery/60000));for(let i=1;i<=count;i++)capture(off+(i===count?recovery-15000:recovery*i/count),'saturation','Dark recovery '+i);end=off+recovery;}p.studio.phases={dark_reference_ms:ref,actinic_on_ms:on,actinic_off_ms:off,recovery_end_ms:end};}
else if(type==='response'){const levels=String(c.levels).split(',').map(v=>{if(!v.trim())throw Error('Enter comma-separated intensity steps.');return number(v.trim(),0,500,'Light response level');});if(!levels.length||levels.length>30)throw Error('Use 1–30 light steps.');const dwell=number(c.dwellMinutes,1,120,'Time per step')*60000;let t=ref+25000;for(const level of levels){p.events.push(light(t,level));capture(t+dwell-15000,'light-adapted','Light step '+level);t+=dwell;}end=t;}
else if(type!=='dark')throw Error('Choose a fluorescence protocol.');if(!p.events.some(e=>e.kind==='set'&&e.delay_ms===end))p.events.push(light(end,0));p.studio.duration_ms=end;finish(p);let previousEnd=-1;for(const e of p.events.filter(e=>e.kind==='capture')){const protocol=p.protocols.find(x=>x.id===e.protocol),wave=waveMs(protocol),a=e.delay_ms-30000,b=e.delay_ms+wave+10000;if(wave>30000)throw Error('Reduce frames or frame spacing: acquisition exceeds 30 seconds.');if(a<=previousEnd)throw Error('Measurements overlap. Increase phase duration or reduce measurement count.');if(p.events.some(x=>x.kind==='set'&&x.delay_ms>a&&x.delay_ms<=b))throw Error('A measurement overlaps a light transition. Reduce frames or increase phase duration.');previousEnd=b;}return p;}
root.ExperimentParts={compose,preset,waveMs,sources};if(typeof module!=='undefined')module.exports=root.ExperimentParts;
})(typeof globalThis!=='undefined'?globalThis:this);

/* Pure duration handling shared by graph authoring and executable serialization. */
(function(root){
 const MAX=366*86400000;
 const Timing={
  units:{seconds:1000,minutes:60000,hours:3600000,days:86400000},
  milliseconds(value,unit){const n=Number(value)*this.units[unit];if(!Number.isFinite(n)||n<1000||n>MAX)throw Error('Duration must be 1 second to 366 days.');return Math.round(n);},
  infer(p){const end=Math.max(0,...p.events.map(e=>e.delay_ms));return p.studio?.duration_ms??(end||86400000);},
  display(ms){for(const unit of ['days','hours','minutes'])if(ms>=this.units[unit]&&ms%this.units[unit]===0)return {value:ms/this.units[unit],unit};return {value:ms/1000,unit:'seconds'};},
  prepare(plan,ms,finalLight){
   if(!Number.isInteger(ms)||ms<1000||ms>MAX)throw Error('Invalid experiment duration');
   const p=structuredClone(plan),events=p.events;
   if(events.some(e=>e.delay_ms>ms))throw Error('An event is after the duration. Move it or extend the duration.');
   const last=[...events].sort((a,b)=>a.delay_ms-b.delay_ms).at(-1);
   if(!last||last.delay_ms!==ms||last.kind!=='set'||last.command!=='intensity')events.push({kind:'set',command:'intensity',value:String(finalLight),delay_ms:ms,relative:true,sequence:events.length,studio_terminal:true});
   p.studio={...p.studio,duration_ms:ms};return p;
  }
 };
 if(typeof module!=='undefined')module.exports=Timing;else root.PlanTiming=Timing;
})(typeof window!=='undefined'?window:this);

'use strict';
const $ = id => document.getElementById(id);
let cameraView='live',currentPage='fleet',lastContact=0,serverOffset=0,lastLiveFrame=0,statusPending=false,liveStartPending=false;
let photoOffset=null,historyBefore=null,connectionFailed=true,commandPending=false;
let liveTimer=null,liveURL=null,liveFetching=false;
let state = null, catalog = [], selected = null, selectedPlan = null, toastTimer = null, account = null;
const text = (id,value) => { const el=$(id);if(el&&el.textContent!==String(value))el.textContent=value; };
async function api(path,data) {
  if(window.DEPI_HOSTED&&window.DEPI_TRANSPORT_AVAILABLE===false&&!(data===undefined&&new URL(path,location.origin).pathname==='/api/'+'status'))throw new Error('Chamber disconnected. Data and commands are unavailable.');
  const command=data!==undefined&&['/api/light','/api/capture','/api/run','/api/stop','/api/preview-light'].includes(path);
  if(command&&commandPending)throw new Error('Waiting for the current command response.');
  if(command){commandPending=true;text('command-state','Sending command…');applyControlPermissions();}
  try{
    const response=await fetch(path,data===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json','X-DepiBeans':'1'},body:JSON.stringify(data)});
    if(response.status===401){if(!window.DEPI_HOSTED)location.href='/login';else{account=null;connectionFailed=true;applyControlPermissions();}throw new Error('Sign in to continue.');}
    let result;try{result=await response.json();}catch(e){throw new Error(command?'Command outcome unknown. Check the chamber state before retrying.':'Controller connection unavailable.');}
    if(!response.ok)throw new Error(result.error||'The controller did not accept this request.');
    if(command)text('command-state','Controller accepted');
    return result;
  }catch(e){if(command)text('command-state',e instanceof TypeError?'Outcome unknown · check chamber state':'Command not confirmed');throw e;}
  finally{if(command){commandPending=false;applyControlPermissions();}}
}

function toast(message) { if(window.DEPI_HOSTED&&/disconnected|connection unavailable|restore saved profile/i.test(message))return; text('toast',message);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{$('toast').hidden=true;},6500); }
function navigate(page) {
  const fleet=page==='fleet',entering=currentPage==='fleet';
  currentPage=fleet?'fleet':'overview';if(fleet)$('measurement-average').hidden=true;
  document.querySelector('.header-actions').hidden=!fleet;
  $('fleet-brand').hidden=!fleet;$('chamber-context').hidden=fleet;$('chamber-nav').hidden=true;
  document.title=fleet?'DEPI · Fleet':'DEPI 1';updateChamberTitle();
  for(const section of document.querySelectorAll('.page')) section.hidden=fleet?section.id!=='fleet':section.id==='fleet';
  if(!fleet){
    prepareWorkspace();
    if(entering&&connected()&&account){cameraView='live';startLive().catch(e=>toast(e.message));loadPhotos(true).catch(e=>toast(e.message));}
    loadWorkspace().catch(e=>toast(e.message));
    if(page==='photos')$('photos-details').open=true;
    if(page!=='overview'&&$(page))$(page).scrollIntoView({block:'start'});
  }
}
for(const button of document.querySelectorAll('[data-page]'))button.addEventListener('click',()=>navigate(button.dataset.page));
for(const button of document.querySelectorAll('[data-open]'))button.addEventListener('click',()=>navigate(button.dataset.open));
function friendly(name) {
  const m=name.match(/^(.+)_\((\d{4}-\d{2}-\d{2})T(\d{2})\.(\d{2})/);
  return m?{name:m[1],date:`${m[2]} · ${m[3]}:${m[4]}`}:{name,date:''};
}
function duration(ms) { const h=ms/3600000;return h>=24?`${(h/24).toFixed(1)} days`:h>=1?`${h.toFixed(1)} hours`:`${Math.round(ms/60000)} min`; }
function renderRuns(runs) {
  runs=[...new Map([...olderRuns,...runs].filter(r=>r.mode==='hardware').map(r=>[r.id,r])).values()].sort((a,b)=>b.created-a.created);
  const container=$('run-list');container.replaceChildren();
  if(!runs.length){const p=document.createElement('p');p.className='help';p.textContent='No chamber runs yet.';container.append(p);return;}
  for(const run of runs){const row=document.createElement('div');row.className='run-row';const a=document.createElement('div'),b=document.createElement('span'),small=document.createElement('small');a.textContent=run.name;small.textContent=`${run.mode==='simulation'?'Simulation · no hardware output':'Chamber run'} · ${new Date(run.created*1000).toLocaleString()}`;a.append(small);b.textContent=`${run.state.replaceAll('_',' ')} · ${run.counts.completed||0}/${run.events} events`;const detail=document.createElement('button');detail.className='button secondary';detail.textContent='Details';detail.addEventListener('click',()=>openJob(run.id).catch(e=>toast(e.message)));row.append(a,b,detail);container.append(row);}
}
async function refreshStatus() {
  if(statusPending)return;statusPending=true;let statusReceived=false;
  try {
    state=await api('/api/status');statusReceived=true;connectionFailed=false;lastContact=performance.now();serverOffset=state.server_time*1000-Date.now();const fpga=state.devices.fpga_devices.length, cameras=state.devices.cameras.length;
    const fpgaLabel=fpga?`${fpga} detected`:'Not connected',camLabel=cameras?`${cameras} detected`:'Not connected';

    const notice=$('notice');notice.hidden=!state.last_error;if(state.last_error){notice.querySelector('strong').textContent='Run error';notice.querySelector('p').textContent=state.last_error;}
    text('fpga-status',fpgaLabel);text('camera-status',camLabel);if(!state.live?.running&&cameraView!=='live')text('camera-badge',camLabel);text('storage',`${state.free_gb} GB`);
    text('system-host',state.hostname);text('system-storage',`${state.free_gb} GB`);text('system-scripts',`${state.scripts} experiment plans`);text('system-fpga',fpgaLabel);text('system-camera',camLabel);
    text('system-controls',state.experiment_ready?'Experiment execution enabled · physical acceptance pending':state.commissioned?'Research and manual':state.manual_light_ready?'Main lights and snapshot':'Disabled until commissioning');text('commission-badge',state.commissioned?'Profile commissioned':'Not commissioned');
    text('checked-at',state.devices.checked_at?new Date(state.devices.checked_at*1000).toLocaleTimeString():'Checking…');text('device-errors',state.devices.errors.join(' · '));
    text('updated',`Updated ${new Date().toLocaleTimeString()}`);
    text('active-title',state.active?state.active.mode==='simulation'?'Simulation running':'Experiment running':'Idle');
    text('active-detail',state.active?state.active.name:'');$('stop').hidden=!state.active;$('experiment-running').hidden=!state.active;text('experiment-running-label',state.active?'Running experiment · '+state.active.name:'');


    text('lights-badge',state.manual_light_ready?'Manual control':'Unavailable');text('apply-light',state.manual_light_ready?'Apply intensity':'Hardware unavailable');
    text('capture-format',state.camera_capture_ready?'TIFF · uint16 / Mono12':'Camera setup pending');
    $('download-frame').hidden=!state.latest_frame;
    for(const button of document.querySelectorAll('[data-intensity]'))button.disabled=state.manual_light_ready&&Number(button.dataset.intensity)>state.limits.intensity[1];
    if(state.manual_light_ready&&state.limits.intensity){$('intensity').max=state.limits.intensity[1];$('intensity-number').max=state.limits.intensity[1];text('range-max',state.limits.intensity[1]);}
    if(cameras){text('camera-title','Camera detected');text('camera-message','Verify the acquisition settings and a captured image before enabling camera control.');}
    else {text('camera-title','Waiting for the chamber');text('camera-message','The camera image will appear here after the camera connection and capture path are verified.');}
    $('capture').disabled=!state.camera_capture_ready||!!state.active;
    $('live-toggle').disabled=!state.live_ready||cameraReserved()||account?.role==='viewer';
    $('saved-view').disabled=!state.latest_frame;
    text('live-toggle',cameraView==='live'&&state.live?.running?'Pause live':'Live view');
    text('capture','Save snapshot');
    if(cameraView==='live'&&state.live?.running&&currentPage==='overview'){
      text('capture-format','Live · not recorded');$('download-frame').hidden=true;
      if(!liveTimer){pollLive();liveTimer=setInterval(pollLive,1000);}
    }else{
      if(liveTimer){clearInterval(liveTimer);liveTimer=null;}
      if(liveURL){URL.revokeObjectURL(liveURL);liveURL=null;}
    }
    if(cameraView==='saved'&&state.latest_frame){
      $('camera-empty').hidden=true;$('camera-frame').hidden=false;$('camera-frame').alt='Last saved chamber photo';
      const imageURL='/api/frame?t='+state.latest_frame.created;
      if($('camera-frame').getAttribute('src')!==imageURL)$('camera-frame').src=imageURL;
      text('camera-badge','Saved · '+new Date(state.latest_frame.created*1000).toLocaleString());text('capture-format','Saved photo · TIFF');$('download-frame').hidden=false;
    }else if(!state.live?.running||cameraView==='paused'){
      $('camera-frame').hidden=true;$('camera-frame').removeAttribute('src');$('camera-empty').hidden=false;
      text('camera-title',state.active?'Camera in use':'Live view paused');text('camera-message',state.live?.error||'Select Live view to resume.');text('camera-badge','Live paused');$('download-frame').hidden=true;
    }
    renderRuns(state.recent);renderOperations();
    const readback=state.live?.settings;
    if(readback)text('preview-readback',`Camera reports ${readback.exposure_us} µs · ${readback.gain} dB · ${readback.width} × ${readback.height} · ${readback.pixel_format}`);
    text('apply-aux',state.commissioned?'Apply auxiliary settings':'Auxiliary hardware unavailable');text('aux-availability',state.commissioned?'Uses the commissioned channel limits.':'Auxiliary channels are not commissioned on this chamber.');
  } catch(error) {if(statusReceived){console.error('Controller status display error',error);text('updated','Connected · display update failed');return;}text('updated','Controller unavailable');$('notice').hidden=!!window.DEPI_HOSTED;$('notice').querySelector('strong').textContent='Disconnected';$('notice').querySelector('p').textContent='Controller unreachable. Controls disabled.';$('capture').disabled=true;$('apply-light').disabled=true;connectionFailed=true;updateFreshness();throw error;}finally{statusPending=false;}
  $('apply-light').disabled=!!state.active||account?.role==='viewer';
  applyControlPermissions();
  if(cameraView==='live'&&currentPage==='overview'&&!document.hidden&&!state.live?.running&&!cameraReserved()&&!state.live?.error&&!commandPending&&Date.now()-lastLiveStart>15000)startLive().catch(()=>{});
  if(account?.role==='viewer')for(const id of ['capture','apply-aux','stop'])$(id).disabled=true;
}
function setIntensity(value){$('intensity').value=value;$('intensity-number').value=value;}
$('intensity').addEventListener('input',()=>{$('intensity-number').value=$('intensity').value;});
$('intensity-number').addEventListener('input',()=>{$('intensity').value=$('intensity-number').value;});
for(const button of document.querySelectorAll('[data-intensity]'))button.addEventListener('click',()=>setIntensity(Number(button.dataset.intensity)));
$('apply-light').addEventListener('click',async()=>{try{const value=Number($('intensity-number').value);if(!Number.isFinite(value)||value<0||value>Number($('intensity-number').max))throw new Error('Choose an intensity within the displayed range.');if(state?.manual_light_ready){await api('/api/light',{command:'intensity',value,request_id:crypto.randomUUID()});text('light-result','Controller accepted the command. Physical output has no sensor confirmation.');}else{throw Error('Main-light hardware control is not ready on this chamber.');}toast($('light-result').textContent);await refreshStatus();}catch(e){toast(e.message);}});
$('apply-aux').addEventListener('click',async()=>{try{if(state.commissioned){const e={schema:'depibeans.experiment-plan/1',name:'Auxiliary lights',protocols:[],events:['FR','UVA','UVB'].map((command,i)=>({kind:'set',command,value:String(Number($('aux-'+command).value)),delay_ms:i,relative:true}))};const checked=await sendPlan('save',e);await api('/api/run',{experiment:checked.id,mode:'hardware',request_id:crypto.randomUUID()});toast('Auxiliary commands accepted.');}else{throw Error('Auxiliary channels require chamber commissioning.');}}catch(e){toast(e.message);}});
$('capture').addEventListener('click',async()=>{try{await api('/api/capture',{request_id:crypto.randomUUID()});toast('Snapshot accepted by controller. Open Photos for the saved result.');await refreshStatus();}catch(e){toast(e.message);}});
function renderCatalog(){}
function timeLabel(event){const total=Math.floor(event.delay_ms/1000),days=Math.floor(total/86400),h=String(Math.floor(total/3600)%24).padStart(2,'0'),m=String(Math.floor(total/60)%60).padStart(2,'0'),s=String(total%60).padStart(2,'0');return `${event.relative?'+':'Day '+days+' · '}${h}:${m}:${s}${event.delay_ms%1000?'.'+String(event.delay_ms%1000).padStart(3,'0'):''}`;}
async function selectExperiment(id){selected=id;selectedPlan=await api('/api/plan?id='+encodeURIComponent(id));}
$('stop').addEventListener('click',async()=>{try{await api('/api/stop',{});toast('Pause requested. Untriggered acquisitions are cancelled; triggered acquisitions finish. The stop-light setting is then applied if hardware responds.');await refreshStatus();}catch(e){toast(e.message);}});
$('logout').addEventListener('click',async()=>{try{if(window.DEPI_HOSTED){const r=await fetch('/logout',{method:'POST',headers:{'X-DepiBeans':'1'}});if(!r.ok)throw Error('Could not sign out. Try again.');}else await api('/logout',{});location.href='/login';}catch(e){toast(e.message);}});
async function initialize(){try{const response=await fetch('/api/account');if(response.ok){account=await response.json();$('logout').hidden=false;}}catch(e){}navigate('fleet');await refreshStatus();catalog=await api('/api/experiments');text('nav-count',catalog.length);text('library-count',catalog.length);renderCatalog();applyControlPermissions();}
initialize().catch(e=>{if(!window.DEPI_HOSTED)toast(e.message);});setInterval(()=>refreshStatus().catch(()=>{}),4000);

async function pollLive(){
  if(cameraView!=='live'||liveFetching||document.hidden||$('overview').hidden||!state?.live?.running)return;
  liveFetching=true;
  try{
    const r=await fetch('/api/frame?view=live&t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(6000)});
    if(!r.ok)throw new Error('Live frame unavailable');
    const blob=await r.blob();
    if(cameraView!=='live'||currentPage!=='overview'||!state?.live?.running)return;
    const acquired=Number(r.headers.get('X-Frame-Created'))*1000;
    if(!Number.isFinite(acquired)||acquired<=0||Date.now()+serverOffset-acquired>6000)throw new Error('Live frame is stale');
    if(acquired===lastLiveFrame){updateFreshness();return;}
    const next=URL.createObjectURL(blob),old=liveURL;const decoded=new Image();decoded.src=next;try{await decoded.decode();}catch(error){URL.revokeObjectURL(next);throw error;}
    if(cameraView!=='live'||currentPage!=='overview'){URL.revokeObjectURL(next);return;}
    lastLiveFrame=acquired;liveURL=next;
    $('camera-frame').src=next;$('camera-frame').hidden=false;$('camera-empty').hidden=true;
    if(old)URL.revokeObjectURL(old);
    $('camera-frame').alt='Live chamber camera feed';
    updateFreshness();
  }catch(e){
    if(cameraView==='live'&&state?.live?.running&&(Date.now()+serverOffset-lastLiveFrame>6000)){text('camera-badge','Live delayed · waiting for camera');$('camera-frame').hidden=true;$('camera-empty').hidden=false;text('camera-title','Waiting for live frame');text('camera-message','No new image received.');}
  }finally{liveFetching=false;}
}
$('live-toggle').addEventListener('click',async()=>{
  if(cameraView==='live'&&state?.live?.running){cameraView='paused';lastLiveFrame=0;await refreshStatus();return;}
  cameraView='live';try{await startLive();await refreshStatus();}catch(e){toast(e.message);}
});
$('saved-view').addEventListener('click',async()=>{cameraView='saved';try{await refreshStatus();}catch(e){toast(e.message);}});

async function startLive(){
  if(!connected()||currentPage!=='overview'||liveStartPending||!state?.live_ready||cameraReserved()||account?.role==='viewer')return;
  lastLiveStart=Date.now();cameraView='live';lastLiveFrame=0;$('camera-frame').hidden=true;$('camera-empty').hidden=false;
  text('camera-title','Connecting to live view');text('camera-message','Waiting for a fresh frame.');
  liveStartPending=true;
  try{if(!state.live?.running)await api('/api/capture',{view:'live',action:'start',request_id:crypto.randomUUID()});await refreshStatus();}
  finally{liveStartPending=false;}
}
function cameraReserved(){const n=state?.progress?.next_measurement;return !!state?.event_pending||!!(n&&n.due-(state.server_time||Date.now()/1000)<=40);}
function connected(){return !connectionFailed&&lastContact>0&&performance.now()-lastContact<10000;}
function applyControlPermissions(){
  const blocked=commandPending||!connected()||!account||account?.role==='viewer';
  for(const id of ['capture','apply-light','apply-aux','stop']){
    const button=$(id);button.disabled=blocked||!!state?.active;
  }
  for(const button of document.querySelectorAll('[data-write]'))button.disabled=blocked;
  for(const id of ['preview-apply','preview-reset','protocol-capture'])$(id).disabled=blocked||!!state?.active;
  $('protocol-capture').disabled=blocked||!!state?.active||!approvedProtocol();
  $('stop').disabled=blocked; $('apply-light').disabled=blocked||!!state?.active||!state?.manual_light_ready; $('apply-aux').disabled=blocked||!!state?.active||!state?.commissioned;
  $('capture').disabled=blocked||!!state?.active||!state?.camera_capture_ready;


}
function eventLabel(item){if(!item)return '—';const e=item.event;return `Step ${item.step}: ${e.kind==='capture'?'capture '+e.protocol:e.command+' → '+e.value}`;}
function ageLabel(seconds){return seconds<60?Math.max(0,Math.floor(seconds))+'s':seconds<3600?Math.floor(seconds/60)+'m':Math.floor(seconds/3600)+'h';}
function renderOperations(){
  const activity=state.active?state.active.name:'Idle';text('fleet-activity',activity);text('strip-activity',activity);
  text('fleet-camera',state.live?.running?'Live view in use':state.devices.cameras.length?'Detected at last check':'Not detected');
  const last=state.last_command;
  text('fleet-lights',last?`${last.detail.value} · ${last.execution==='completed'?'command completed':last.execution}`:'No command recorded');
  if(last)text('light-result',`Last requested: ${last.detail.command} ${last.detail.value} · ${last.execution}. Physical output unverified.`);
  text('system-uptime',ageLabel(state.uptime_seconds));
  text('system-memory',state.health?.memory_available_mb!=null?`${state.health.memory_available_mb.toLocaleString()} / ${state.health.memory_total_mb.toLocaleString()} MB`:'Unavailable');
  text('system-load',state.health?.load_1m?.toFixed(2)||'—');
  const progress=state.progress;$('run-progress').hidden=!progress;
  if(progress){$('progress-bar').max=progress.total||1;$('progress-bar').value=progress.completed;text('progress-text',`${progress.completed} / ${progress.total} events completed · ${ageLabel(state.server_time-progress.started)} elapsed`);text('next-event',progress.current?eventLabel(progress.current)+' · executing':progress.next?eventLabel(progress.next)+' · '+new Date(progress.next.due*1000).toLocaleTimeString():'Finishing');}
  const review=state.recent.find(r=>r.state==='needs_review');
  if(state.free_gb<5&&!state.last_error){$('notice').hidden=false;$('notice').querySelector('strong').textContent='Low disk space';$('notice').querySelector('p').textContent=state.free_gb+' GB free. Move saved captures to approved storage before starting a large acquisition.';}
  if(review&&!state.last_error){$('notice').hidden=false;$('notice').querySelector('strong').textContent='Review required';$('notice').querySelector('p').textContent='Check the latest run before another command.';}
  updateFreshness();
}
function updateFreshness(){
  const online=connected();const contact=lastContact?`Last contact ${ageLabel((performance.now()-lastContact)/1000)} ago`:'No current connection';
  $('fleet-connection').setAttribute('aria-label',online?'Connected':'Not connected');$('fleet-connection').title=online?'Connected':'Not connected';if(!online){text('fleet-activity','Last known: '+(state?.active?.name||'Idle'));text('fleet-camera','Unknown while disconnected');}$('fleet-connection').classList.toggle('offline',!online);
  text('fleet-contact',contact);text('strip-connection',online?'Connected':'Connection lost');
  const frameAge=lastLiveFrame?(Date.now()+serverOffset-lastLiveFrame)/1000:Infinity;
  text('strip-frame',cameraView==='saved'?'Saved photo':currentPage!=='overview'?'Live view not requested':cameraView==='paused'?'Live view paused':frameAge<=6?'Live frame '+ageLabel(frameAge)+' ago':state?.live?.running?'Waiting for fresh frame':'Live view paused');
  if(cameraView==='live'&&currentPage==='overview'&&state?.live?.running){
    if(frameAge>6||!online){text('camera-badge',online?'Waiting for live frame':'Connection lost');$('camera-frame').hidden=true;$('camera-empty').hidden=false;text('camera-title',online?'Waiting for a fresh frame':'Connection lost');text('camera-message',online?'The last frame is not shown as live.':'Reconnect before sending commands.');}
    if(frameAge<=6&&online)text('camera-badge','Live · '+new Date(lastLiveFrame).toLocaleTimeString());
  }
  if(!online){$('live-toggle').disabled=true;}
  applyControlPermissions();
}
$('open-chamber').addEventListener('click',()=>navigate('overview'));
setInterval(updateFreshness,1000);

async function loadPhotos(reset=false){
  if(reset){photoOffset=0;$('photo-grid').replaceChildren();}
  const query=new URLSearchParams({view:'gallery',offset:String(photoOffset||0),day:$('photo-date').value,q:$('photo-search').value,kind:$('photo-kind').value});
  const result=await api('/api/status?'+query);
  text('photo-count',result.total+' saved '+(result.total===1?'photo':'photos'));
  for(const item of result.items){
    const card=document.createElement('article');card.className='photo-card';
    const button=document.createElement('button');button.className='photo-open';button.setAttribute('aria-label','Open '+item.experiment+' '+new Date(item.created*1000).toLocaleString());
    const img=document.createElement('img');img.loading='lazy';img.alt=item.experiment;img.src='/api/frame?id='+item.id;button.append(img);
    const name=document.createElement('strong');name.textContent=item.experiment+(item.kind==='mean'?' · '+item.label+' · '+item.frame_count+' frames':'');
    const date=document.createElement('p');date.textContent=new Date(item.created*1000).toLocaleString();
    button.addEventListener('click',()=>{text('photo-title',item.experiment);text('photo-meta',new Date(item.created*1000).toLocaleString()+' · '+(item.bytes/1048576).toFixed(1)+' MB'+(item.kind==='mean'?' · '+item.frame_count+'-frame average · display 0–'+item.display_max.toFixed(1)+' raw units':''));$('photo-large').src='/api/frame?id='+item.id;$('photo-download').href='/api/frame.tif?id='+item.id;$('photo-dialog').showModal();});
    card.append(button,name,date);$('photo-grid').append(card);
  }
  photoOffset=result.next_offset;$('more-photos').hidden=photoOffset==null;
}
$('photo-kind').addEventListener('change',()=>loadPhotos(true).catch(e=>toast(e.message)));
$('filter-photos').addEventListener('click',()=>loadPhotos(true).catch(e=>toast(e.message)));
$('more-photos').addEventListener('click',()=>loadPhotos().catch(e=>toast(e.message)));
$('close-photo').addEventListener('click',()=>{$('photo-dialog').close();$('photo-large').removeAttribute('src');});
// Advanced workspace: all mutations use authenticated controller operations.
let workspace=null,editID=null,editVersion=null,protocolID=null,protocolVersion=null,jobRecord=null,lastLiveStart=0,protocolApproval=null,olderRuns=[],runOffset=0;
const protocolFields={NumberLoops:['Loops','1'],FramesPerLoop:['Frames per loop','1'],MeasuringLight:['Measuring light index','1'],SaturationFlash:['Saturation flash (0 / 1)','0'],AuxFastSwitch:['Auxiliary fast switch (0 / 1)','0'],Exposure:['Exposure','50us'],FrameInterval:['Frame interval','70ms'],ActinicShutter:['Actinic shutter (0 / 1)','0']};
for(const [key,[label,value]] of Object.entries(protocolFields)){const l=document.createElement('label');l.textContent=label;const input=document.createElement('input');input.id='proto-'+key;input.value=value;l.append(input);$('protocol-fields').append(l);}
function bind(id,fn){$(id).addEventListener('click',async()=>{try{await fn();}catch(e){toast(e.message);}});}
function downloadJSON(name,data){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function reloadLibrary(){catalog=await api('/api/experiments');text('library-count',catalog.length);renderCatalog();}
async function loadWorkspace(){
  const first=!workspace;workspace=await api('/api/status?view=workspace');
  if(first){$('preview-exposure').value=workspace.preview.exposure_us;$('preview-gain').value=workspace.preview.gain;}
  const list=$('protocol-list'),previous=list.value;list.replaceChildren(new Option('New protocol',''));
  for(const item of workspace.protocols)list.add(new Option(item.name+' · v'+item.version,item.id));list.value=previous;
  text('config-detail',JSON.stringify({camera:workspace.camera,controller:workspace.profile},null,2));
  const box=$('scheduled-list');box.replaceChildren();
  for(const row of workspace.schedules){const item=document.createElement('div');item.className='run-row';const label=document.createElement('span');label.textContent=new Date(row.due*1000).toLocaleString()+' · '+row.mode+' · '+row.state+(row.error?' · '+row.error:'');item.append(label);if(row.state==='queued'){const b=document.createElement('button');b.className='button secondary';b.textContent='Cancel';b.dataset.write='';b.addEventListener('click',async()=>{try{await api('/api/run',{operation:'cancel_schedule',id:row.id});await loadWorkspace();}catch(e){toast(e.message);}});item.append(b);}box.append(item);}
  if(!box.children.length){const p=document.createElement('p');p.className='help';p.textContent='No scheduled starts.';box.append(p);}applyControlPermissions();
}
function protocolDocument(){return {name:$('protocol-name').value.trim(),analysis:$('protocol-analysis').value.trim(),group:$('protocol-group').value.trim(),sensors:$('protocol-sensors').value.split(',').map(s=>s.trim()).filter(Boolean),fields:{...JSON.parse($('protocol-extra').value),...Object.fromEntries(Object.keys(protocolFields).map(key=>[key,$('proto-'+key).value.trim()]))}};}
function validationText(result){return `${result.events} events · ${result.frames} frames\nCompiled.\n${result.hardware_ready?'Ready to submit to chamber.':result.hardware_reasons.join('\n')}`;}
async function protocolAction(operation){const result=await api('/api/capture',{operation,protocol:protocolDocument(),id:protocolID,version:protocolVersion,request_id:crypto.randomUUID()});if(operation==='protocol_save'){protocolID=result.id;protocolVersion=result.version;await loadWorkspace();$('protocol-list').value=protocolID;}protocolApproval=result.hardware_ready?JSON.stringify(protocolDocument()):null;applyControlPermissions();text('protocol-result',operation==='protocol_capture'?'Acquisition accepted. See Recent runs for the outcome.':validationText(result)+(result.version?'\nSaved version '+result.version:''));await refreshStatus();}
bind('protocol-validate',()=>protocolAction('protocol_validate'));bind('protocol-save',()=>protocolAction('protocol_save'));bind('protocol-capture',()=>protocolAction('protocol_capture'));bind('protocol-export',()=>downloadJSON('camera-protocol.json',protocolDocument()));
$('protocol-list').addEventListener('change',async()=>{try{protocolID=$('protocol-list').value||null;protocolVersion=null;if(!protocolID)return;const doc=await api('/api/status?view=document&id='+encodeURIComponent(protocolID));protocolVersion=doc.version;const p=doc.body;$('protocol-name').value=p.name;$('protocol-analysis').value=p.analysis||p.name;$('protocol-group').value=p.group||'*';$('protocol-sensors').value=(p.sensors||['*']).join(',');for(const key of Object.keys(protocolFields))$('proto-'+key).value=p.fields[key]??protocolFields[key][1];$('protocol-extra').value=JSON.stringify(Object.fromEntries(Object.entries(p.fields).filter(([key])=>!(key in protocolFields))),null,2);text('protocol-result','Loaded version '+doc.version);}catch(e){toast(e.message);}});
async function applyPreview(reset=false){if(reset){$('preview-exposure').value=250;$('preview-gain').value=12;}await api('/api/capture',{operation:'preview_settings',exposure_us:Number($('preview-exposure').value),gain:Number($('preview-gain').value),request_id:crypto.randomUUID()});lastLiveFrame=0;text('preview-readback','Settings requested. Waiting for camera readback.');await refreshStatus();}
bind('preview-apply',()=>applyPreview());bind('preview-reset',()=>applyPreview(true));
async function sendPlan(operation,plan,extra={}){
  const encoded=JSON.stringify(plan),upload=crypto.randomUUID();
  if(new TextEncoder().encode(encoded).length>2000000)throw new Error('Plan exceeds 2 MB.');
  // Small, sequential chunks stay within the relay request limit, including Unicode.
  for(let i=0,sequence=0;i<encoded.length;i+=2000,sequence++)await api('/api/run',{operation:'upload_chunk',upload,sequence,chunk:encoded.slice(i,i+2000)});
  return api('/api/run',{operation,upload,...extra});
}
function starterPlan(){return {studio:{duration_ms:86400000},schema:'depibeans.experiment-plan/1',name:'New experiment',events:[{kind:'set',command:'intensity',value:'0',delay_ms:0,relative:true,sequence:0}],protocols:[],sections:[]};}
function loadEditor(plan,id=null,version=null,scroll=true){editID=id;editVersion=version;$('recovery-setting-review').hidden=!plan.recovery;$('review-recovery-state').checked=false;$('edit-name').value=plan.name;$('edit-repeat').value=1;$('plan-editor').value=JSON.stringify(plan,null,2);$('experiment-editor').open=true;$('recipe-steps').replaceChildren();text('plan-result',id?'Editing version '+version:'New copy · not saved');if(scroll)$('experiment-editor').scrollIntoView({behavior:'smooth',block:'start'});loadVersions().catch(e=>toast(e.message));}
function editorPlan(){const p=JSON.parse($('plan-editor').value);p.name=$('edit-name').value.trim();if(p.recovery&&$('review-recovery-state').checked)p.recovery.initial_state_review_required=false;return p;}
bind('new-experiment',()=>{loadEditor(starterPlan());addStep();});
bind('validate-plan',async()=>{const result=await sendPlan('validate',editorPlan());text('plan-result',validationText(result));});
bind('save-plan',async()=>{const result=await sendPlan('save',editorPlan(),{id:editID,version:editVersion});editID=result.id;editVersion=result.version;text('plan-result','Saved version '+editVersion+'\n'+validationText(result));await reloadLibrary();await selectExperiment(editID);await loadVersions();});
bind('export-editor',()=>downloadJSON('experiment-plan.json',editorPlan()));
bind('archive-plan',async()=>{if(!editID)throw new Error('Only a saved custom experiment can be archived.');await api('/api/run',{operation:'archive',id:editID,version:editVersion});text('plan-result','Archived. Existing runs and images were preserved.');editID=null;editVersion=null;selected=null;selectedPlan=null;await reloadLibrary();applyControlPermissions();});
$('import-plan').addEventListener('change',async()=>{try{const file=$('import-plan').files[0];if(!file)return;if(file.size>2000000)throw new Error('Plan exceeds 2 MB.');loadEditor(JSON.parse(await file.text()));}catch(e){toast(e.message);}});
function addStep(){const row=document.createElement('div');row.className='recipe-step';const kind=document.createElement('select');kind.setAttribute('aria-label','Step action');for(const [value,label] of [['set','Set light'],['wait','Wait'],['capture','Capture'],['at','At time']])kind.add(new Option(label,value));const target=document.createElement('input'),value=document.createElement('input');target.setAttribute('aria-label','Channel or protocol');value.setAttribute('aria-label','Setting or duration');const remove=document.createElement('button');remove.textContent='Remove';remove.addEventListener('click',()=>row.remove());function fields(){target.hidden=['wait','at'].includes(kind.value);value.hidden=kind.value==='capture';target.placeholder=kind.value==='capture'?'Protocol ID':'intensity / FR / UVA / UVB';value.placeholder=kind.value==='wait'?'10min':kind.value==='at'?'08:00':'0';}kind.addEventListener('change',fields);fields();row.append(kind,target,value,remove);$('recipe-steps').append(row);}
bind('add-step',addStep);
bind('compile-recipe',async()=>{const steps=[...$('recipe-steps').children].map(row=>{const [kind,target,value]=row.children;return kind.value==='set'?{kind:'set',command:target.value,value:Number(value.value)}:kind.value==='capture'?{kind:'capture',protocol:target.value}:kind.value==='wait'?{kind:'wait',duration:value.value}:{kind:'at',time:value.value};});let protocols=[];try{protocols=JSON.parse($('plan-editor').value).protocols||[];}catch(e){}for(const item of workspace?.protocols||[]){if(steps.some(s=>s.protocol===item.name)&&!protocols.some(p=>p.id===item.name)){const p=(await api('/api/status?view=document&id='+encodeURIComponent(item.id))).body;protocols.push({id:p.name,analysis:p.analysis,fields:p.fields,group:p.group,sensors:p.sensors});}}const result=await api('/api/run',{operation:'recipe',recipe:{name:$('edit-name').value,repeat:Number($('edit-repeat').value),steps,protocols}});$('plan-editor').value=JSON.stringify(result.plan,null,2);text('plan-result',validationText(result));$('plan-editor').dispatchEvent(new Event('input'));});
async function openJob(id){jobRecord=await api('/api/status?view=job&id='+encodeURIComponent(id));text('job-summary',jobRecord.plan.name+' · '+jobRecord.mode+' · '+jobRecord.state.replaceAll('_',' '));renderJobEvents(jobRecord);text('job-detail',JSON.stringify(jobRecord,null,2));$('discard-job').hidden=!['paused','needs_review','pending'].includes(jobRecord.state);$('prepare-recovery').hidden=!['paused','needs_review','pending'].includes(jobRecord.state);$('uncertain-review').hidden=!jobRecord.attempts.some(a=>a.state==='uncertain');$('omit-uncertain').checked=false;text('recovery-note','');$('bundle-links').replaceChildren();$('bundle-export').open=false;$('prepare-bundle').disabled=['running','pending'].includes(jobRecord.state);$('job-dialog').showModal();}
bind('close-job',()=>$('job-dialog').close());bind('export-job',()=>downloadJSON('run-report.json',jobRecord));bind('discard-job',async()=>{await api('/api/run',{operation:'discard',id:jobRecord.id});$('job-dialog').close();await refreshStatus();});
bind('export-config',async()=>{await loadWorkspace();downloadJSON('depi-1-configuration.json',{camera:workspace.camera,controller:workspace.profile,preview:workspace.preview});});bind('export-calibration',async()=>downloadJSON('calibration-points.json',await api('/api/status?view=calibration')));
bind('fit-calibration',async()=>{const result=await api('/api/run',{operation:'calibration_fit',samples:JSON.parse($('calibration-samples').value)});text('calibration-result',JSON.stringify(result,null,2));downloadJSON('calibration-fit.json',result);});
$('calibration-file').addEventListener('change',async()=>{try{const file=$('calibration-file').files[0];if(!file)return;if(file.size>2000000)throw new Error('Calibration exceeds 2 MB.');const result=await sendPlan('calibration_import',JSON.parse(await file.text()));text('calibration-result',result.points+' points imported. Hardware unchanged.');}catch(e){toast(e.message);}});
loadWorkspace().catch(e=>toast(e.message));

function approvedProtocol(){try{return protocolApproval===JSON.stringify(protocolDocument());}catch(e){return false;}}
function loadProtocolEditor(p){protocolID=null;protocolVersion=null;protocolApproval=null;$('protocol-list').value='';$('protocol-name').value=p.name||p.id||'Imported protocol';$('protocol-analysis').value=p.analysis||p.id||'';$('protocol-group').value=p.group||'*';$('protocol-sensors').value=(p.sensors||['*']).join(',');for(const key of Object.keys(protocolFields))$('proto-'+key).value=p.fields[key]??protocolFields[key][1];$('protocol-extra').value=JSON.stringify(Object.fromEntries(Object.entries(p.fields).filter(([key])=>!(key in protocolFields))),null,2);text('protocol-result','Imported into editor. Check timing before acquisition.');}
$('protocol-file').addEventListener('change',async()=>{try{const file=$('protocol-file').files[0];if(!file)return;if(file.size>12000)throw new Error('Protocol exceeds 12 KB. Import it as part of a complete experiment plan instead.');const p=JSON.parse(await file.text());if(!p.fields||typeof p.fields!=='object')throw new Error('Expected a camera protocol with fields.');loadProtocolEditor(p);}catch(e){toast(e.message);}});
function unusedRenderExperimentProtocols(plan){const box=$('experiment-protocols');box.replaceChildren();for(const proto of plan.protocols||[]){const row=document.createElement('div');row.className='run-row';const name=document.createElement('span');name.textContent=proto.id+' · '+(proto.analysis||'No analysis label');const b=document.createElement('button');b.className='button secondary';b.textContent='Open camera settings';b.addEventListener('click',()=>{navigate('overview');loadProtocolEditor(proto);document.querySelector('.work-area').open=true;document.querySelector('.work-area .work-body>details').open=true;$('protocol-name').scrollIntoView({behavior:'smooth',block:'center'});});row.append(name,b);box.append(row);}if(!box.children.length)box.textContent='No camera acquisitions in this experiment.';}
function renderJobEvents(report){const box=$('job-events');box.replaceChildren();const table=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');for(const name of ['Step','Action','State','Finished','Result']){const th=document.createElement('th');th.textContent=name;tr.append(th);}head.append(tr);table.append(head);const body=document.createElement('tbody');for(const a of report.attempts){const e=report.plan.events[a.seq],row=document.createElement('tr');for(const value of [a.seq+1,e.kind==='capture'?e.protocol:e.command+' → '+e.value,a.state,a.ended?new Date(a.ended*1000).toLocaleString():'—',a.result?.error||(a.result?.simulated?'Simulation':a.state==='completed'?'Controller completed':'—')]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}body.append(row);}table.append(body);box.append(table);}

bind('older-runs',async()=>{const result=await api('/api/status?view=runs&offset='+runOffset);olderRuns.push(...result.items);runOffset=result.next_offset;$('older-runs').hidden=runOffset==null;renderRuns(state.recent);});

bind('experiment-stop',async()=>{await api('/api/stop',{});toast('Pause requested. Stop-light handling follows acquisition cleanup.');await refreshStatus();});

async function loadVersions(){const select=$('plan-versions');select.replaceChildren();if(!editID){select.add(new Option('Save a custom plan first',''));return;}const rows=await api('/api/status?view=revisions&id='+encodeURIComponent(editID));for(const r of rows)select.add(new Option('Version '+r.version+' · '+new Date(r.created*1000).toLocaleString()+' · '+r.actor,String(r.version)));}
bind('load-plan-version',async()=>{if(!editID||!$('plan-versions').value)throw new Error('Select a saved version.');const r=await api('/api/status?view=revision&id='+encodeURIComponent(editID)+'&version='+$('plan-versions').value);loadEditor(r.body,r.id,r.head_version);text('plan-result','Loaded version '+r.version+' into the editor. Save creates a new version.');});
bind('prepare-recovery',async()=>{const r=await api('/api/run',{operation:'recovery_plan',id:jobRecord.id,omit_uncertain:$('omit-uncertain').checked});$('job-dialog').close();navigate('experiments');loadEditor(r.plan);text('plan-result',r.note);});
bind('prepare-bundle',async()=>{const result=await api('/api/status?view=bundle&id='+encodeURIComponent(jobRecord.id));const box=$('bundle-links');box.replaceChildren();for(const item of result.parts){const link=document.createElement('a');link.className='button secondary';link.textContent='Part '+(item.part+1)+' of '+result.parts.length+' · '+(item.bytes/1048576).toFixed(1)+' MB'+(item.kind==='mean'?' · '+item.frame_count+'-frame average · display 0–'+item.display_max.toFixed(1)+' raw units':'');link.href='/api/frame.tif?view=bundle&id='+encodeURIComponent(jobRecord.id)+'&part='+item.part;link.download='depi-run-part-'+(item.part+1)+'.zip';box.append(link);}});

// Graph authoring edits the same versioned plan used by the chamber controller.
(()=>{
const host=document.createElement('section');host.className='graph-studio';
host.innerHTML=`<div class="graph-title"><div><span class="eyebrow">EXPERIMENT COMPOSER</span><h2>Draw the conditions. Place the measurements.</h2></div><span class="small-badge">Chamber commands</span></div>
<p class="help">Drag a light point up or down to set its level, or sideways to change its time. Drag a capture marker to move acquisition. Changes stay in your draft until you save a version.</p>
<div class="button-row"><button id="graph-light" class="button secondary">+ Light change</button><button id="graph-capture" class="button secondary">+ Pulse acquisition</button><button id="graph-undo" class="button secondary">Undo</button><label>Time reference<select id="graph-basis"><option value="relative">Hours after start</option></select></label><label>Graph maximum (controller units)<input id="graph-max" type="number" min="1" max="65535" step="1" value="500"></label><label>Visible span (hours)<input id="graph-span" type="number" min="0.000001" max="8784" step="any" value="24"></label><label>View starts at (hours)<input id="graph-start" type="number" min="0" max="8784" step="any" value="0"></label></div>
<svg id="graph-timeline" viewBox="0 0 1000 310" aria-label="Editable light and camera timeline"></svg><p id="graph-message" class="help" aria-live="polite"></p>
<div id="graph-selection" class="form-grid"><label>Hour within visible day<input id="graph-time" type="number" min="0" step="any"></label><label>Light level (controller units)<input id="graph-value" type="number" min="0" max="65535" step="1"></label><button id="graph-apply" class="button secondary">Apply exact values</button><button id="graph-delete" class="button secondary">Delete selected event</button></div>
<details open class="pulse-panel"><summary>Inside the acquisition · saturation, measuring light & camera</summary><p class="help">Choose a capture marker to edit its protocol. Saturation is on during each frame interval; measuring light is on during exposure. These are controller settings, not measured output. Exposure is shared across phases to match the current camera adapter.</p><div class="button-row"><label>Protocol<select id="graph-protocol"></select></label><label>Camera exposure (µs)<input id="graph-exposure" type="number" min="1" max="1000000" value="50"></label><button id="graph-phase" class="button secondary">+ Phase</button></div><svg id="graph-pulses" viewBox="0 0 1000 225" aria-label="Acquisition phase timeline"></svg><p class="help">Enter exact phase settings below. Measuring and exposure marks are enlarged for visibility.</p><div class="table-wrap"><table><thead><tr><th>Phase</th><th>Frames</th><th>Interval (ms)</th><th>Saturation</th><th>Measuring channel</th><th>Actinic shutter</th><th></th></tr></thead><tbody id="graph-phases"></tbody></table></div><p id="graph-budget" class="help"></p></details>
<details class="fluorescence-panel" open><summary>Measured fluorescence · Fm & Fm′</summary><p class="help">Fm is the dark-adapted maximum; Fm′ is the light-adapted maximum. No measurements are available in this draft. Import a measured CSV for one plant/ROI with columns time_s,Fm,Fm_prime. Values must use the same fluorescence units and acquisition settings. Imported results are viewed locally, not saved with the experiment.</p><label>Measured results CSV<input id="graph-results" type="file" accept=".csv,text/csv"></label><svg id="graph-fluorescence" viewBox="0 0 1000 200" aria-label="Measured Fm and Fm prime"></svg><p id="graph-results-note" class="help">Waiting for measured data.</p></details>`;
$('experiment-editor').querySelector('.work-body').prepend(host);
const G=id=>$('graph-'+id);let selectedEvent=null,protocolIndex=0,history=[],drag=null,drawSpan=24*3600000,drawStart=0,yMax=155;let axisMs=3600000;function axisUnit(){return drawSpan<=600000?{ms:1000,name:'seconds',short:'s'}:drawSpan<=7200000?{ms:60000,name:'minutes',short:'min'}:{ms:3600000,name:'hours',short:'h'};}
function read(){const p=editorPlan();if(!Array.isArray(p.events)||!Array.isArray(p.protocols))throw Error('Plan requires events and protocols.');return p;}
function checkpoint(){history.push($('plan-editor').value);if(history.length>40)history.shift();}
function write(p){p.events.sort((a,b)=>Number(b.relative)-Number(a.relative)||a.delay_ms-b.delay_ms);p.events.forEach((e,i)=>e.sequence=i);$('plan-editor').value=JSON.stringify(p,null,2);text('plan-result','Unsaved graph changes · validate and save a version.');}
function guarded(fn){try{fn();}catch(e){G('message').textContent=e.message;}}
function svg(parent,tag,attrs={},label){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))el.setAttribute(k,v);if(label!==undefined)el.textContent=label;parent.append(el);return el;}
function chartBase(el,rows){el.replaceChildren();for(const [y,label]of rows){svg(el,'line',{x1:140,x2:960,y1:y,y2:y,stroke:'#d9e4df'});svg(el,'text',{x:12,y:y-8,fill:'#52675d','font-size':13},label);}}
function xy(ev,el){const p=el.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;return p.matrixTransform(el.getScreenCTM().inverse());}
function select(i,p){selectedEvent=i;const e=p.events[i];G('time').value=(e.delay_ms-drawStart)/axisMs;G('value').value=e.value??0;G('value').disabled=e.kind!=='set'||e.command!=='intensity';const choice=$('graph-event-protocol');if(choice){choice.parentElement.hidden=e.kind!=='capture';choice.replaceChildren();for(const proto of p.protocols)choice.add(new Option(proto.id,proto.id));choice.value=e.protocol||'';}if(e.kind==='capture'){$('plain-pulse-panel').open=true;protocolIndex=p.protocols.findIndex(x=>x.id===e.protocol);renderPulses(p);}G('message').textContent=e.kind==='capture'?`Selected acquisition: ${e.protocol}`:'Selected main-light change';}
function render(){guarded(()=>{const p=read(),el=G('timeline');drawSpan=Number(G('span').value)*3600000;drawStart=Number(G('start').value)*3600000;if(!Number.isFinite(drawSpan)||drawSpan<=0||!Number.isFinite(drawStart)||drawStart<0)throw Error('Choose a positive view span and a nonnegative start.');chartBase(el,[[205,'Main light'],[267,'Acquisition']]);const axis=axisUnit();axisMs=axis.ms;G('time').parentElement.firstChild.textContent='Time in view ('+axis.name+')';const basis=G('basis').value==='relative';G('message').textContent=basis?'Showing events relative to experiment start.':'Showing calendar events from day 0 midnight, America/Detroit. Initial start-relative events are preserved; switch time reference to edit them.';
yMax=Math.max(Number(G('max').value)||500,...p.events.filter(e=>e.kind==='set'&&e.command==='intensity').map(e=>Number(e.value)));const x=t=>140+(t-drawStart)/drawSpan*820,y=v=>205-v/yMax*160;
for(let i=0;i<=4;i++){const xx=140+i*205;svg(el,'line',{x1:xx,x2:xx,y1:30,y2:277,stroke:'#e8efeb'});svg(el,'text',{x:xx,y:303,'text-anchor':'middle',fill:'#64766c','font-size':12},`${Number((i*drawSpan/4/axisMs).toFixed(3))} ${axis.short}`);}svg(el,'text',{x:12,y:40,fill:'#64766c','font-size':12},`${yMax} units`);
const lights=p.events.map((e,i)=>({...e,index:i})).filter(e=>e.relative===basis&&e.kind==='set'&&e.command==='intensity').sort((a,b)=>a.delay_ms-b.delay_ms);let level=0,path='';for(const e of lights){if(e.delay_ms<=drawStart)level=Number(e.value);}path=`M140 ${y(level)}`;for(const e of lights.filter(e=>e.delay_ms>=drawStart&&e.delay_ms<=drawStart+drawSpan)){path+=` H${x(e.delay_ms)} V${y(Number(e.value))}`;}path+=' H960';svg(el,'path',{d:path,fill:'none',stroke:'#236c50','stroke-width':3});
for(const [i,e]of p.events.entries()){if(e.relative!==basis||e.delay_ms<drawStart||e.delay_ms>drawStart+drawSpan)continue;if(!(e.kind==='capture'||e.kind==='set'&&e.command==='intensity'))continue;const point=svg(el,e.kind==='capture'?'rect':'circle',e.kind==='capture'?{x:x(e.delay_ms)-7,y:249,width:14,height:25,rx:3,fill:'#b16a27'}:{cx:x(e.delay_ms),cy:y(Number(e.value)),r:7,fill:'#fff',stroke:'#236c50','stroke-width':3});point.setAttribute('tabindex','0');point.setAttribute('role','button');point.setAttribute('aria-label',`${e.kind==='capture'?'Acquisition':'Light'} at ${Number(((e.delay_ms-drawStart)/axisMs).toFixed(3))} ${axis.name}`);point.style.cursor='grab';point.addEventListener('click',()=>select(i,p));point.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' ')select(i,p);});point.addEventListener('pointerdown',ev=>{ev.preventDefault();select(i,p);checkpoint();drag={kind:'event',i,p:read(),span:drawSpan,start:drawStart,max:yMax};el.setPointerCapture(ev.pointerId);});}
renderPulses(p);});}
G('timeline').addEventListener('pointermove',ev=>{if(drag?.kind!=='event')return;const pos=xy(ev,G('timeline')),e=drag.p.events[drag.i];e.delay_ms=Math.round(Math.max(0,Math.min(durationMsInput(),drag.start+(pos.x-140)/820*drag.span)));if(e.kind==='set')e.value=String(Math.round(Math.max(0,Math.min(500,(205-pos.y)/160*drag.max))));write(drag.p);drag.i=drag.p.events.indexOf(e);selectedEvent=drag.i;G('time').value=(e.delay_ms-drawStart)/axisMs;G('value').value=e.value??0;render();});
function end(){drag=null;}G('timeline').addEventListener('pointerup',end);G('timeline').addEventListener('pointercancel',end);
function editable(p){}
G('light').onclick=()=>guarded(()=>{const p=read();editable(p);checkpoint();p.events.push({kind:'set',command:'intensity',value:'0',delay_ms:Math.round((Number(G('start').value)+Number(G('span').value)/2)*3600000),relative:G('basis').value==='relative'});const added=p.events.at(-1);write(p);select(p.events.indexOf(added),p);render();});
G('capture').onclick=()=>guarded(()=>{const p=read();editable(p);checkpoint();const id='Acquisition-'+crypto.randomUUID().slice(0,8);p.protocols.push({id,measurement_type:$('graph-measurement-type')?.value||'measuring',analysis:id,group:'*',sensors:['*'],fields:measurementFields($('graph-measurement-type')?.value||'measuring')});p.events.push({kind:'capture',protocol:id,delay_ms:Math.round((Number(G('start').value)+Number(G('span').value)/2)*3600000),relative:G('basis').value==='relative'});protocolIndex=p.protocols.length-1;const added=p.events.at(-1);write(p);select(p.events.indexOf(added),p);render();});
G('apply').onclick=()=>guarded(()=>{const p=read();editable(p);if(selectedEvent===null||!p.events[selectedEvent])throw Error('Select a point first.');const h=Number(G('time').value),v=Number(G('value').value);if(!G('time').value||!Number.isFinite(h)||h<0||h>drawSpan/axisMs||!Number.isInteger(v)||v<0||v>500)throw Error('Use a time within the visible window and an integer light level 0–500.');checkpoint();p.events[selectedEvent].delay_ms=Math.round(drawStart+h*axisMs);if(p.events[selectedEvent].kind==='set')p.events[selectedEvent].value=String(v);const edited=p.events[selectedEvent];write(p);selectedEvent=p.events.indexOf(edited);render();});
G('delete').onclick=()=>guarded(()=>{const p=read();editable(p);if(selectedEvent===null||!p.events[selectedEvent])throw Error('Select an event first.');if(p.events.length===1)throw Error('Keep at least one event.');checkpoint();p.events.splice(selectedEvent,1);selectedEvent=null;write(p);render();});G('undo').onclick=()=>{if(history.length){$('plan-editor').value=history.pop();selectedEvent=null;render();text('plan-result','Undo applied · draft not saved.');}};G('basis').onchange=()=>{selectedEvent=null;render();};G('max').oninput=render;G('span').oninput=render;G('start').oninput=render;
function durationMs(v){const m=String(v).match(/^\s*(\d+(?:\.\d+)?)\s*(us|ms|s|min|h|hr|day)\s*$/);if(!m)throw Error('Pulse duration needs explicit units.');return Number(m[1])*({us:.001,ms:1,s:1000,min:60000,h:3600000,hr:3600000,day:86400000}[m[2]]);}
function phases(p){const f=p.fields,n=Number(f.NumberLoops);if(!Number.isInteger(n)||n<1||n>255)throw Error('Protocol needs 1–255 phases.');const vals=(key,def)=>{const a=Array.isArray(f[key])?f[key]:String(f[key]??def).split(',');if(a.length!==1&&a.length!==n)throw Error(`${key} does not match the phase count.`);return Array.from({length:n},(_,i)=>a[a.length===1?0:i]);};const keys=['FramesPerLoop','FrameInterval','MeasuringLight','SaturationFlash','ActinicShutter','Exposure','AuxFastSwitch'];const all=Object.fromEntries(keys.map(k=>[k,vals(k,k==='ActinicShutter'?'1':'0')]));return Array.from({length:n},(_,i)=>Object.fromEntries(keys.map(k=>[k,all[k][i]])));}
function setPhases(p,rows){p.fields.NumberLoops=String(rows.length);for(const k of Object.keys(rows[0]))p.fields[k]=rows.map(r=>r[k]).join(',');}
function renderPulses(plan){const dropdown=G('protocol');dropdown.replaceChildren();plan.protocols.forEach((p,i)=>dropdown.add(new Option(p.id,i)));protocolIndex=Math.max(0,Math.min(protocolIndex,plan.protocols.length-1));dropdown.value=protocolIndex;const el=G('pulses');chartBase(el,[[55,'Saturation'],[112,'Measuring'],[169,'Camera exposure']]);G('phases').replaceChildren();const proto=plan.protocols[protocolIndex];if(!proto){G('budget').textContent='Add a pulse acquisition to define the measurement sequence.';return;}const rows=phases(proto),exp=durationMs(rows[0].Exposure);G('exposure').value=exp*1000;const periods=rows.map(r=>durationMs(r.FrameInterval)+durationMs(r.Exposure)+.07),total=rows.reduce((s,r,i)=>s+Number(r.FramesPerLoop)*periods[i],0);let elapsed=0;let shown=0;
rows.forEach((r,i)=>{const start=elapsed,frames=Number(r.FramesPerLoop),interval=durationMs(r.FrameInterval);elapsed+=frames*periods[i];const x=t=>140+t/total*820;for(const [key,yy,label] of [['SaturationFlash',25,'saturation'],['MeasuringLight',83,'measuring light']]){const hit=svg(el,'rect',{x:x(start),y:yy,width:Math.max(1,x(elapsed)-x(start)),height:31,fill: '#edf2ee',opacity:.55,tabindex:0,role:'button','aria-label':`Toggle phase ${i+1} ${label}`});const toggle=()=>guarded(()=>{const doc=read(),rr=phases(doc.protocols[protocolIndex]);checkpoint();rr[i][key]=Number(rr[i][key])?'0':'1';setPhases(doc.protocols[protocolIndex],rr);write(doc);renderPulses(doc);});hit.onclick=toggle;hit.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle();}};}svg(el,'text',{x:x(start)+4,y:18,fill:'#64766c','font-size':11},`P${i+1}`);for(let j=0;j<frames&&shown<800;j++,shown++){const t=start+j*periods[i];if(Number(r.SaturationFlash))svg(el,'rect',{x:x(t),y:29,width:Math.max(1,interval/total*820),height:25,fill:'#c98a36','pointer-events':'none'});if(Number(r.MeasuringLight))svg(el,'rect',{x:x(t+interval+.035),y:87,width:Math.max(2,durationMs(r.Exposure)/total*820),height:24,fill:'#338878','pointer-events':'none'});svg(el,'rect',{x:x(t+interval+.035),y:144,width:Math.max(2,durationMs(r.Exposure)/total*820),height:24,fill:'#6679be'});}const boundary=svg(el,'line',{x1:x(elapsed),x2:x(elapsed),y1:23,y2:179,stroke:'#506960','stroke-width':7,opacity:.35});boundary.style.cursor='ew-resize';boundary.addEventListener('pointerdown',ev=>{ev.preventDefault();checkpoint();drag={kind:'phase',i,p:read(),total,start,frames,exp:durationMs(r.Exposure)};el.setPointerCapture(ev.pointerId);});const tr=document.createElement('tr');const name=document.createElement('td');name.textContent=`${i+1}`;tr.append(name);for(const [key,type,min,max,value]of [['FramesPerLoop','number',1,100,frames],['FrameInterval','number',95,30000,interval],['SaturationFlash','number',0,1,Number(r.SaturationFlash)],['MeasuringLight','number',0,4,Number(r.MeasuringLight)],['ActinicShutter','number',0,1,Number(r.ActinicShutter)]]){const td=document.createElement('td'),input=document.createElement('input');Object.assign(input,{type,min,max,step:key==='FrameInterval'?'any':'1',value});input.setAttribute('aria-label',`Phase ${i+1} ${key}`);input.oninput=()=>guarded(()=>{if(!input.value||!input.checkValidity())throw Error('Invalid phase setting.');const p=read(),rs=phases(p.protocols[protocolIndex]);checkpoint();rs[i][key]=input.value+(key==='FrameInterval'?'ms':'');setPhases(p.protocols[protocolIndex],rs);write(p);});input.onblur=()=>guarded(()=>renderPulses(read()));td.append(input);tr.append(td);}const td=document.createElement('td'),del=document.createElement('button');del.textContent='Remove';del.className='text-button';del.onclick=()=>guarded(()=>{if(rows.length===1)throw Error('Keep at least one phase.');const p=read(),rs=phases(p.protocols[protocolIndex]);checkpoint();rs.splice(i,1);setPhases(p.protocols[protocolIndex],rs);write(p);renderPulses(p);});td.append(del);tr.append(td);G('phases').append(tr);});svg(el,'text',{x:140,y:210,fill:'#64766c','font-size':12},'0 ms');svg(el,'text',{x:960,y:210,'text-anchor':'end',fill:'#64766c','font-size':12},`${total.toFixed(3)} ms`);G('budget').textContent=`${rows.reduce((s,r)=>s+Number(r.FramesPerLoop),0)} frames · ${total.toFixed(3)} ms nominal waveform · ${rows.length} phases. ${shown>=800?'Display limited to 800 frame windows. ':''}Timing shown uses the current 35 µs pre/post convention; validate for controller limits. This protocol is shared by every capture that references its name.`;}
G('protocol').onchange=()=>guarded(()=>{protocolIndex=Number(G('protocol').value);renderPulses(read());});G('exposure').oninput=()=>guarded(()=>{if(!G('exposure').value||!G('exposure').checkValidity())throw Error('Use a positive camera exposure.');const p=read(),proto=p.protocols[protocolIndex];if(!proto)throw Error('Add an acquisition first.');checkpoint();const rs=phases(proto);rs.forEach(r=>r.Exposure=G('exposure').value+'us');setPhases(proto,rs);write(p);});G('exposure').onblur=()=>guarded(()=>renderPulses(read()));G('phase').onclick=()=>guarded(()=>{const p=read(),proto=p.protocols[protocolIndex];if(!proto)throw Error('Add an acquisition first.');const rows=phases(proto);if(rows.length>=255)throw Error('Maximum 255 phases.');checkpoint();rows.push({...rows.at(-1)});setPhases(proto,rows);write(p);renderPulses(p);});G('pulses').addEventListener('pointermove',ev=>guarded(()=>{if(drag?.kind!=='phase')return;const pos=xy(ev,G('pulses')),rows=phases(drag.p.protocols[protocolIndex]);const endMs=Math.max(drag.start+drag.frames*(drag.exp+95.07),(pos.x-140)/820*drag.total);rows[drag.i].FrameInterval=Math.max(95,(endMs-drag.start)/drag.frames-drag.exp-.07).toFixed(3)+'ms';setPhases(drag.p.protocols[protocolIndex],rows);write(drag.p);renderPulses(drag.p);}));G('pulses').addEventListener('pointerup',end);G('pulses').addEventListener('pointercancel',end);
G('results').onchange=async()=>{try{const file=G('results').files[0];if(!file)return;if(file.size>2000000)throw Error('CSV must be under 2 MB.');const lines=(await file.text()).trim().split(/\r?\n/),header=lines.shift().split(',').map(s=>s.trim());if(header.join(',')!=='time_s,Fm,Fm_prime')throw Error('CSV header must be time_s,Fm,Fm_prime.');const rows=lines.map(line=>line.split(',').map(s=>s.trim())).map(c=>{if(c.length!==3||!c[0])throw Error('Each row requires time_s and two result columns.');const r=c.map(v=>v===''?null:Number(v));if(r.some(v=>v!==null&&(!Number.isFinite(v)||v<0))||r.slice(1).every(v=>v===null))throw Error('Use nonnegative measurements; leave unavailable values blank.');return r;}).sort((a,b)=>a[0]-b[0]);if(!rows.length)throw Error('No measurements in CSV.');const el=G('fluorescence');chartBase(el,[[165,'Fluorescence']]);const xmax=Math.max(1,...rows.map(r=>r[0])),ymax=Math.max(1,...rows.flatMap(r=>r.slice(1).filter(v=>v!==null)));for(const [index,color,label]of [[1,'#236c50','Fm'],[2,'#b46b36','Fm′']]){const pts=rows.filter(r=>r[index]!==null);svg(el,'polyline',{points:pts.map(r=>`${140+r[0]/xmax*820},${165-r[index]/ymax*125}`).join(' '),fill:'none',stroke:color,'stroke-width':2});pts.forEach(r=>{const c=svg(el,'circle',{cx:140+r[0]/xmax*820,cy:165-r[index]/ymax*125,r:4,fill:color});svg(c,'title',{},`${label}: ${r[index]} at ${r[0]} s`);});svg(el,'text',{x:140+(index-1)*120,y:20,fill:color,'font-size':14},label);}svg(el,'text',{x:960,y:192,'text-anchor':'end',fill:'#64766c','font-size':12},`${xmax} seconds`);svg(el,'text',{x:12,y:45,fill:'#64766c','font-size':12},String(ymax));G('results-note').textContent=`${file.name} · ${rows.length} measured rows · local view only; not linked to a chamber run.`;}catch(e){G('results-note').textContent=e.message;G('fluorescence').replaceChildren();}};
const repeatBar=document.createElement('div');repeatBar.className='button-row';repeatBar.innerHTML='<label>Additional repeats of visible window<input id="graph-repeats" type="number" min="1" max="365" step="1" value="1"></label><button id="graph-repeat-window" class="button secondary">Repeat this window</button>';G('timeline').after(repeatBar);
G('repeat-window').onclick=()=>guarded(()=>{const p=read(),count=Number(G('repeats').value),period=Number(G('span').value)*3600000,start=Number(G('start').value)*3600000,basis=G('basis').value==='relative';if(!Number.isInteger(count)||count<1||count>365||!Number.isFinite(period)||period<=0)throw Error('Choose 1–365 repeats and a positive window length.');const source=p.events.filter(e=>e.relative===basis&&e.delay_ms>=start&&e.delay_ms<start+period);if(!source.length)throw Error('There are no events in the visible window.');if(p.events.length+source.length*count>10000)throw Error('Repeated plan exceeds 10,000 events.');const added=[];for(let n=1;n<=count;n++)for(const e of source){const next={...structuredClone(e),delay_ms:Math.round(e.delay_ms+n*period)};if(next.delay_ms>366*86400000)throw Error('Repeated plan exceeds one year.');if(p.events.some(old=>old.relative===basis&&old.delay_ms===next.delay_ms))throw Error('A repeated event overlaps an existing event. Change the window or remove that event first.');added.push(next);}checkpoint();p.events.push(...added);write(p);render();G('message').textContent=`Added ${added.length} real scheduled commands across ${count} additional windows. Save a version to retain them.`;});

const originalEditorPlan=editorPlan;editorPlan=function(){for(const input of host.querySelectorAll('#graph-phases input,#graph-exposure'))if(!input.value||!input.checkValidity())throw Error('Correct the invalid acquisition field before saving or validating.');return originalEditorPlan();};
const originalLoad=loadEditor;loadEditor=function(...args){originalLoad(...args);history=[];selectedEvent=null;protocolIndex=0;G('time').value=0;G('value').value=0;const p=args[0];G('basis').value='relative';const max=Math.max(0,...p.events.map(e=>e.delay_ms));G('span').value=Math.max(1/3600,PlanTiming.infer(p)/3600000);G('max').value=Math.max(500,...p.events.filter(e=>e.kind==='set'&&e.command==='intensity').map(e=>Number(e.value)));G('start').value=0;render();};$('plan-editor').addEventListener('input',render);
// Pure graph-plan transformations. No hardware calls or synthetic measurements.
const StudioPlan={
 day:86400000,
 integer(value,min,max,label){if(!Number.isInteger(value)||value<min||value>max)throw Error(`${label} must be ${min}–${max}.`);return value;},
 check(p){if(p.events.length>10000)throw Error('This plan exceeds the controller limit of 10,000 events.');if(p.events.some(e=>!Number.isInteger(e.delay_ms)||e.delay_ms<0||e.delay_ms>366*this.day))throw Error('Events must fall within one year.');p.events.sort((a,b)=>Number(b.relative)-Number(a.relative)||a.delay_ms-b.delay_ms);p.events.forEach((e,i)=>e.sequence=i);return p;},
 copyDays(plan,{source,first,last,relative}){this.integer(source,1,366,'Source day');this.integer(first,1,366,'First day');this.integer(last,first,366,'Last day');const p=structuredClone(plan),base=(source-1)*this.day;const events=p.events.filter(e=>e.relative===relative&&e.delay_ms>=base&&e.delay_ms<base+this.day);if(!events.length)throw Error('Draw at least one event on the source day first.');if(events.length*(last-first+1)>10000)throw Error('The repeated pattern exceeds 10,000 events.');p.events=p.events.filter(e=>e.relative!==relative||e.delay_ms<(first-1)*this.day||e.delay_ms>=last*this.day);for(let d=first;d<=last;d++)p.events.push(...events.map(e=>({...structuredClone(e),delay_ms:e.delay_ms-base+(d-1)*this.day})));return this.check(p);},
 measurements(plan,{first,last,startHour,endHour,everyMinutes,protocol,relative}){this.integer(first,1,366,'First day');this.integer(last,first,366,'Last day');if(![startHour,endHour,everyMinutes].every(Number.isFinite)||startHour<0||endHour>24||endHour<=startHour||everyMinutes<1/60)throw Error('Choose a daily window within 0–24 hours and a positive measurement interval of at least one second.');if(!plan.protocols.some(p=>p.id===protocol))throw Error('Add and select an acquisition protocol first.');const step=Math.round(everyMinutes*60000),span=(endHour-startHour)*3600000,count=Math.ceil(span/step);if(count*(last-first+1)>10000)throw Error('Measurement recurrence exceeds 10,000 events.');const p=structuredClone(plan);p.events=p.events.filter(e=>{if(e.kind!=='capture'||e.protocol!==protocol||e.relative!==relative)return true;const d=Math.floor(e.delay_ms/this.day)+1,h=(e.delay_ms%this.day)/3600000;return d<first||d>last||h<startHour||h>=endHour;});for(let d=first;d<=last;d++)for(let n=0;n<count;n++){const t=Math.round((d-1)*this.day+startHour*3600000+n*step);p.events.push({kind:'capture',protocol,delay_ms:t,relative});}return this.check(p);},
 durationDays(p){return Math.max(1,p.studio?.days||1,...p.events.filter(e=>!e.studio_terminal).map(e=>Math.floor(e.delay_ms/this.day)+1));}
};

// Experiment → day → acquisition navigation, over the original executable plan.
const studioHeader=document.createElement('section');studioHeader.className='studio-workflow';studioHeader.innerHTML=`
<div class="studio-intro"><div><span class="eyebrow">DESIGN AN EXPERIMENT</span><h2>One experiment. Every day. Every measurement.</h2><p>Shape the light on a day, apply it across your experiment, then decide when to measure.</p></div><label>Experiment duration<input id="studio-days" type="number" min="1" max="366" value="1"><span>days · start-relative days are 24-hour blocks</span></label></div>
<nav class="studio-nav" aria-label="Experiment design scale"><button id="studio-experiment" class="button secondary">1 · Experiment</button><button id="studio-day" class="button secondary">2 · Day pattern</button><button id="studio-acquisition" class="button secondary">3 · Acquisition</button><button id="studio-review" class="button secondary">4 · Review</button></nav>
<div id="studio-overview"><div class="studio-section-heading"><h3>Your complete experiment</h3><span id="studio-total"></span></div><p class="help">Select a day below to edit it. Each column shows that day’s peak commanded main-light level and camera acquisitions, in the selected time reference.</p><svg id="studio-overview-chart" viewBox="0 0 1000 180" aria-label="Experiment days and acquisitions"></svg></div>
<div id="studio-day-tools"><div class="studio-section-heading"><h3 id="studio-day-title">Day 1 · conditions and measurements</h3><div class="button-row"><button id="studio-prev" class="button secondary">← Previous day</button><label>Day<input id="studio-day-number" type="number" min="1" max="366" value="1"></label><button id="studio-next" class="button secondary">Next day →</button></div></div><p class="help">Draw this day below. Select a capture marker, then choose Acquisition to edit its pulses. Times on the graph are hours within this day. Light levels hold until the next command; add an explicit lights-off point when needed.</p>
<div class="studio-pattern"><h4>Apply this day’s pattern</h4><div class="button-row"><label>From day<input id="studio-first" type="number" min="1" max="366" value="1"></label><label>Through day<input id="studio-last" type="number" min="1" max="366" value="1"></label><button id="studio-copy" class="button secondary">Replace days with this pattern</button></div><p class="help">Replaces commands on the selected day range. Other days and the other time reference are preserved. Undo restores the previous plan.</p></div>
<div class="studio-pattern"><h4>When should the camera measure?</h4><div class="button-row"><label>From (hour of day)<input id="studio-measure-start" type="number" min="0" max="24" step="any" value="6"></label><label>Until, excluding (hour)<input id="studio-measure-end" type="number" min="0" max="24" step="any" value="22"></label><label>Every (minutes)<input id="studio-frequency" type="number" min="0.016667" step="any" value="30"></label><button id="studio-measure" class="button primary">Apply measurement schedule</button></div><p class="help">Uses the protocol selected in Acquisition and the day range above. Replaces matching acquisitions in that window, so applying twice does not duplicate them. Draw and copy light conditions first.</p></div></div>
<div id="studio-review-panel" hidden><h3>Review the actual chamber plan</h3><div id="studio-review-stats" class="studio-stats"></div><div id="studio-review-result" role="status">Validate the draft to calculate frames, waveform timing and hardware readiness.</div><button id="studio-check" class="button primary">Check draft with controller</button><p class="help">Save version below after review. Start on chamber applies to the selected saved version, not unsaved graph changes. Hardware execution requires a connected, commissioned chamber.</p></div>
<label class="studio-end"><input id="studio-end-off" type="checkbox" checked> End the experiment with main lights off at the end of the selected duration.</label><p id="studio-feedback" class="help" aria-live="polite"></p>`;
host.prepend(studioHeader);host.querySelector('.graph-title').hidden=true;host.querySelector('.graph-title').nextElementSibling.hidden=true;repeatBar.hidden=true;
const S=id=>$('studio-'+id);let studioView='experiment',studioDay=1;
const graphToolbar=G('light').parentElement,graphExplanation=G('timeline').nextElementSibling,pulsePanel=host.querySelector('.pulse-panel'),resultPanel=host.querySelector('.fluorescence-panel');
// Keep advanced hours/scale controls accessible without making them the main workflow.
const advanced=document.createElement('details');advanced.className='studio-advanced';const summary=document.createElement('summary');summary.textContent='Time reference and graph scale';advanced.append(summary);for(const id of ['basis','max','span','start'])advanced.append(G(id).parentElement);graphToolbar.after(advanced);
S('day-tools').children[1].after(graphToolbar,advanced,G('timeline'),G('message'),G('selection'));
const legacySteps=document.createElement('details');legacySteps.className='studio-advanced';legacySteps.innerHTML='<summary>Advanced step and JSON authoring</summary>';const steps=$('recipe-steps'),stepButtons=$('add-step').parentElement,stepHelp=stepButtons.nextElementSibling;steps.before(legacySteps);legacySteps.append(steps,stepButtons,stepHelp);$('edit-repeat').parentElement.hidden=true;
function studioMessage(message){S('feedback').textContent=message;}
function studioGuard(fn){try{fn();}catch(e){studioMessage(e.message);}}
function durationMsInput(){return PlanTiming.milliseconds(S('days').value,$('duration-unit')?.value||'days');}
function dayCount(){return Math.max(1,Math.ceil(durationMsInput()/86400000));}
function loadDuration(p){const d=PlanTiming.display(PlanTiming.infer(p));S('days').value=d.value;if($('duration-unit'))$('duration-unit').value=d.unit;}
function overview(){studioGuard(()=>{const p=read(),days=dayCount(),basis=G('basis').value==='relative',el=S('overview-chart');el.replaceChildren();const selected=p.events.filter(e=>e.relative===basis),maximum=Math.max(500,...selected.filter(e=>e.kind==='set'&&e.command==='intensity').map(e=>Number(e.value)));const captures=p.events.filter(e=>e.kind==='capture').length;S('total').textContent=`${days} days · ${p.events.length.toLocaleString()} commands · ${captures.toLocaleString()} acquisitions`;const cell=900/days;let hold=0;for(let d=1;d<=days;d++){const events=selected.filter(e=>e.delay_ms>=(d-1)*86400000&&e.delay_ms<d*86400000).sort((a,b)=>a.delay_ms-b.delay_ms),lights=events.filter(e=>e.kind==='set'&&e.command==='intensity');const max=Math.max(hold,...lights.map(e=>Number(e.value)));if(lights.length)hold=Number(lights.at(-1).value);const x=70+(d-1)*cell;const group=svg(el,'g',{tabindex:0,role:'button','aria-label':`Edit day ${d}`});svg(group,'rect',{x,y:20,width:Math.max(1,cell-2),height:115,rx:Math.min(4,cell/4),fill:d===studioDay?'#e0eee6':'#eff3f0',stroke:d===studioDay?'#236c50':'none'});svg(group,'rect',{x:x+1,y:112-max/maximum*80,width:Math.max(1,cell-4),height:Math.max(2,max/maximum*80),fill:'#438665'});const n=events.filter(e=>e.kind==='capture').length;if(n)svg(group,'circle',{cx:x+cell/2,cy:126,r:Math.min(4,cell/3),fill:'#b77835'});svg(group,'title',{},`Day ${d}: ${events.length} commands, ${n} acquisitions, peak ${max} units`);if(days<=20||d===1||d===days||d%5===0)svg(el,'text',{x:x+cell/2,y:158,'text-anchor':'middle','font-size':12,fill:'#51675b'},String(d));const open=()=>{studioDay=d;setStudioView('day');};group.onclick=open;group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}};}svg(el,'text',{x:12,y:158,'font-size':12,fill:'#51675b'},'Day');});}
function setStudioView(view){studioView=view;for(const key of ['experiment','day','acquisition','review']){S(key).classList.toggle('primary',key===view);S(key).classList.toggle('secondary',key!==view);S(key).setAttribute('aria-pressed',String(key===view));}S('overview').hidden=view!=='experiment';S('day-tools').hidden=view!=='day';S('review-panel').hidden=view!=='review';const day=view==='day';graphToolbar.hidden=!day;advanced.hidden=!day;G('timeline').hidden=!day;G('selection').hidden=!day;G('message').hidden=!day;pulsePanel.hidden=view!=='acquisition';resultPanel.hidden=view!=='review';if(day){studioDay=Math.min(dayCount(),Math.max(1,studioDay));S('day-number').value=studioDay;S('day-title').textContent=`Day ${studioDay} · conditions and measurements`;G('span').value=Math.min(24,(durationMsInput()-(studioDay-1)*86400000)/3600000);G('start').value=(studioDay-1)*24;render();}if(view==='experiment')overview();if(view==='acquisition')guarded(()=>renderPulses(read()));if(view==='review'){const p=read();S('review-stats').textContent=`${dayCount()} days / ${p.events.length} commands / ${p.events.filter(e=>e.kind==='capture').length} acquisitions`;}}
for(const key of ['experiment','day','acquisition','review'])S(key).onclick=()=>studioGuard(()=>setStudioView(key));
S('day-number').oninput=()=>studioGuard(()=>{studioDay=StudioPlan.integer(Number(S('day-number').value),1,dayCount(),'Day');setStudioView('day');});S('prev').onclick=()=>{studioDay--;setStudioView('day');};S('next').onclick=()=>{studioDay++;setStudioView('day');};
S('days').onchange=()=>studioGuard(()=>{const ms=durationMsInput(),p=JSON.parse($('plan-editor').value),oldMs=PlanTiming.infer(p);const last=[...p.events].sort((a,b)=>a.delay_ms-b.delay_ms).at(-1);if(last?.kind==='set'&&last.command==='intensity'&&last.delay_ms===oldMs)last.delay_ms=ms;if(p.events.some(e=>e.delay_ms>ms))throw Error('Move events beyond the new duration first.');checkpoint();p.studio={...p.studio,duration_ms:ms};write(p);S('last').value=dayCount();setStudioView('day');studioMessage('Duration updated.');});
S('copy').onclick=()=>studioGuard(()=>{const first=Number(S('first').value),last=Number(S('last').value);if(last>dayCount())throw Error('Day range exceeds experiment duration.');const p=StudioPlan.copyDays(read(),{source:studioDay,first,last,relative:G('basis').value==='relative'});checkpoint();write(p);selectedEvent=null;render();overview();studioMessage(`Day ${studioDay} applied to days ${first}–${last}. ${p.events.length} commands in the draft.`);});
S('measure').onclick=()=>studioGuard(()=>{for(const id of ['first','last','measure-start','measure-end','frequency'])if(!S(id).value||!S(id).checkValidity())throw Error('Complete the measurement window and day range with valid values.');const p=read(),first=Number(S('first').value),last=Number(S('last').value);if(last>dayCount())throw Error('Day range exceeds experiment duration.');const next=StudioPlan.measurements(p,{first,last,startHour:Number(S('measure-start').value),endHour:Number(S('measure-end').value),everyMinutes:Number(S('frequency').value),protocol:p.protocols[protocolIndex]?.id,relative:G('basis').value==='relative'});checkpoint();write(next);selectedEvent=null;render();overview();studioMessage(`${next.events.filter(e=>e.kind==='capture').length} acquisitions scheduled. Their camera frames and pulses use the selected acquisition protocol.`);});
S('check').onclick=async()=>{try{S('check').disabled=true;const p=read(),result=await sendPlan('validate',p),issues=[];const events=[...p.events].sort((a,b)=>Number(b.relative)-Number(a.relative)||a.delay_ms-b.delay_ms);for(let i=0;i<events.length-1;i++){const e=events[i],next=events[i+1];if(e.kind==='capture'&&e.relative===next.relative){const duration=(result.waveforms[e.protocol]?.duration_s||0)+30;if(next.delay_ms-e.delay_ms<duration*1000)issues.push(`Acquisition at ${(e.delay_ms/3600000).toFixed(3)} h leaves less than its waveform plus camera preparation and cleanup before the next command.`);}}const limit=workspace?.profile?.experiment_execution?.limits?.intensity?.[1]??workspace?.profile?.limits?.intensity?.[1];if(limit!==undefined&&events.some(e=>e.command==='intensity'&&Number(e.value)>limit))issues.push(`Main-light commands exceed this profile’s ${limit}-unit limit.`);const pixels=workspace?.camera?.width*workspace?.camera?.height,bytes=Number.isFinite(pixels)?result.frames*pixels*2:null;if(bytes!==null&&Number.isFinite(state?.free_gb)&&bytes/1e9>state.free_gb)issues.push('Estimated raw images exceed the controller’s currently available disk space.');S('review-stats').textContent=`${dayCount()} days / ${result.events.toLocaleString()} commands / ${result.frames.toLocaleString()} frames${bytes!==null?' / '+(bytes/1e9).toFixed(2)+' GB raw images':''}`;S('review-result').replaceChildren();for(const msg of ['Plan compiled successfully.',...result.hardware_reasons||[],...issues.slice(0,8),...(issues.length>8?[`${issues.length-8} additional timing conflicts.`]:[]),'Storage estimate excludes metadata and filesystem overhead. Camera transfer and recovery timing require physical verification.']){const line=document.createElement('p');line.textContent=msg;S('review-result').append(line);}text('plan-result',validationText(result));}catch(e){S('review-result').textContent=e.message;}finally{S('check').disabled=false;}};
S('end-off').parentElement.hidden=true;S('end-off').onchange=()=>studioGuard(()=>{checkpoint();write(read());render();overview();});
const oldWrite=write;write=function(p){const ms=durationMsInput();const prepared=PlanTiming.prepare(p,ms,Number($('editor-final-light')?.value||0));if(prepared.events.length>p.events.length)p.events.push(prepared.events.at(-1));p.studio=prepared.studio;StudioPlan.check(p);oldWrite(p);S('review-result').textContent='Draft changed. Check it again before starting.';};
const addAcquisition=G('capture').onclick;G('capture').onclick=()=>{const before=read().protocols.length;addAcquisition();if(read().protocols.length>before)setStudioView('acquisition');};
const oldLoadStudio=loadEditor;loadEditor=function(...args){oldLoadStudio(...args);studioMessage('');const p=args[0];S('end-off').checked=p.events.some(e=>e.studio_terminal)||!args[1];loadDuration(p);S('last').value=dayCount();S('first').value=1;studioDay=1;setStudioView('experiment');};
const oldNew=$('new-experiment');oldNew.addEventListener('click',()=>{S('days').value=1;$('duration-unit').value='days';S('last').value=1;const p=read();p.studio={duration_ms:86400000};write(p);setStudioView('day');});
setStudioView('experiment');

// Plain operator layout. Same plans, protocols, validation and version history.
const plain=document.createElement('div');plain.className='plain-editor';
plain.innerHTML=`<div class="plain-fields" id="plain-fields"></div><div class="plain-fields"><label>Baseline light (controller units)<input id="plain-baseline" type="number" min="0" max="65535" step="1" value="0"></label><button id="plain-set-baseline" class="button secondary">Set baseline</button></div><div class="button-row"><button id="plain-add-fluctuation" class="button secondary">Add fluctuation</button><button id="plain-measurements" class="button secondary">Measurements</button><button id="plain-pulses" class="button secondary">Pulse settings</button></div><details id="plain-fluctuation"><summary>Fluctuation</summary><div class="plain-fields"><label>Light level<input id="plain-level" type="number" min="0" max="65535" value="500"></label><label>From hour<input id="plain-from" type="number" min="0" max="24" value="6" step="any"></label><label>Until hour<input id="plain-until" type="number" min="0" max="24" value="22" step="any"></label><label>Hold for (minutes)<input id="plain-hold" type="number" min="0.001" value="5" step="any"></label><label>Repeat every (minutes)<input id="plain-every" type="number" min="0.001" value="30" step="any"></label><button id="plain-apply-fluctuation" class="button secondary">Apply fluctuation</button></div><p class="help">Returns to baseline after each hold. Uses the day range below. Reapplying replaces fluctuations created here in that range.</p></details><div class="plain-fields" id="plain-range"></div><details id="plain-measurement-panel"><summary>Measurement schedule</summary></details><details id="plain-pulse-panel"><summary>Pulse settings</summary></details><details id="plain-options"><summary>More settings</summary></details><details id="plain-checks"><summary>Checks and image budget</summary></details>`;
host.prepend(plain);const P=id=>$('plain-'+id);
const nameLabel=$('edit-name').parentElement;P('fields').append(nameLabel,S('days').parentElement);S('days').parentElement.querySelector('span').textContent='';S('days').parentElement.firstChild.textContent='Duration';S('days').min='0.000001';S('days').max='31622400';S('days').step='any';const unitLabel=document.createElement('label');unitLabel.textContent='Unit';const units=document.createElement('select');units.id='duration-unit';units.setAttribute('aria-label','Duration unit');for(const [v,t]of [['seconds','Seconds'],['minutes','Minutes'],['hours','Hours'],['days','Days']])units.add(new Option(t,v));units.value='days';unitLabel.append(units);S('days').parentElement.after(unitLabel);units.onchange=()=>S('days').onchange();
S('day-number').parentElement.firstChild.textContent='View day';P('range').append(S('day-number').parentElement,S('first').parentElement,S('last').parentElement);S('first').parentElement.firstChild.textContent='Apply from day';S('last').parentElement.firstChild.textContent='Through day';
const scheduleControls=S('measure').parentElement;P('measurement-panel').append(scheduleControls);S('measure').textContent='Apply schedule';
const scheduleNote=document.createElement('p');scheduleNote.className='help';scheduleNote.textContent='Uses the selected pulse protocol. Add a measurement below to create a protocol first. End hour is excluded.';P('measurement-panel').append(scheduleNote);
P('pulse-panel').append(pulsePanel);pulsePanel.open=true;pulsePanel.querySelector('summary').hidden=true;pulsePanel.querySelector('p').textContent='Toggle pulse lanes or drag phase boundaries. Exposure is shared across phases.';
P('options').append(advanced,S('copy'),legacySteps);S('copy').textContent='Copy displayed day to day range';
P('checks').append(S('review-panel'));P('options').append(resultPanel);resultPanel.open=false;resultPanel.style.display='none';legacySteps.style.display='none';S('review-panel').hidden=false;S('review-panel').querySelector('h3').hidden=true;S('review-panel').querySelector('.help').textContent='Start and Schedule save this draft before submitting it.';S('check').textContent='Check plan';
plain.append(graphToolbar,G('timeline'),G('message'),G('selection'),S('feedback'));G('light').textContent='Add light change';G('capture').textContent='Add measurement';G('apply').textContent='Apply';G('delete').textContent='Delete';
G('message').hidden=false;studioHeader.hidden=true;repeatBar.hidden=true;host.querySelector('.graph-title').hidden=true;
P('add-fluctuation').onclick=()=>P('fluctuation').open=!P('fluctuation').open;P('measurements').onclick=()=>P('measurement-panel').open=!P('measurement-panel').open;P('pulses').onclick=()=>P('pulse-panel').open=!P('pulse-panel').open;
function plainRange(){const first=StudioPlan.integer(Number(S('first').value),1,dayCount(),'First day'),last=StudioPlan.integer(Number(S('last').value),first,dayCount(),'Last day');return {first,last,relative:G('basis').value==='relative'};}
function plainNumber(id,min,max){const el=P(id),v=Number(el.value);if(!el.value||!el.checkValidity()||!Number.isFinite(v)||v<min||v>max)throw Error('Check '+el.parentElement.firstChild.textContent+'.');return v;}
P('set-baseline').onclick=()=>studioGuard(()=>{const p=read(),{first,last,relative}=plainRange(),level=plainNumber('baseline',0,65535);checkpoint();p.events=p.events.filter(e=>!(e.relative===relative&&e.kind==='set'&&e.command==='intensity'&&e.delay_ms%86400000===0&&e.delay_ms>=(first-1)*86400000&&e.delay_ms<last*86400000));for(let d=first;d<=last;d++)p.events.push({kind:'set',command:'intensity',value:String(level),delay_ms:(d-1)*86400000,relative});write(p);selectedEvent=null;render();studioMessage(`Baseline ${level} set for days ${first}–${last}. Existing later light changes are preserved.`);});
P('apply-fluctuation').onclick=()=>studioGuard(()=>{const p=read(),{first,last,relative}=plainRange(),base=plainNumber('baseline',0,65535),level=plainNumber('level',0,65535),from=plainNumber('from',0,24),until=plainNumber('until',0,24),hold=plainNumber('hold',.001,1440),every=plainNumber('every',.001,1440);if(until<=from||hold>every)throw Error('End must follow start; hold must not exceed the repeat interval.');const count=Math.ceil((until-from)*60/every);p.events=p.events.filter(e=>!(e.plain_fluctuation&&e.relative===relative&&(e.plain_day||Math.floor(e.delay_ms/86400000)+1)>=first&&(e.plain_day||Math.floor(e.delay_ms/86400000)+1)<=last));if(count*(last-first+1)*2+p.events.length>10000)throw Error('Too many events. Increase the interval or reduce the day range.');for(let d=first;d<=last;d++)for(let n=0;n<count;n++){const start=Math.round((d-1)*86400000+from*3600000+n*every*60000),end=Math.round(Math.min((d-1)*86400000+until*3600000,start+hold*60000));for(const [t,v]of [[start,level],[end,base]])p.events.push({kind:'set',command:'intensity',value:String(v),delay_ms:t,relative,plain_fluctuation:true,plain_day:d});}checkpoint();write(p);selectedEvent=null;render();studioMessage(`Fluctuations added to days ${first}–${last}. Check the graph before saving.`);});
setStudioView=function(view){studioView='day';studioDay=Math.min(dayCount(),Math.max(1,studioDay));S('day-number').value=studioDay;G('span').value=Math.min(24,(durationMsInput()-(studioDay-1)*86400000)/3600000);G('start').value=(studioDay-1)*24;graphToolbar.hidden=false;advanced.hidden=false;G('timeline').hidden=false;G('selection').hidden=false;pulsePanel.hidden=false;resultPanel.hidden=false;S('review-panel').hidden=false;if(view==='acquisition')P('pulse-panel').open=true;render();G('message').hidden=false;};
overview=function(){};
const plainLoad=loadEditor;loadEditor=function(...args){plainLoad(...args);const p=read(),initial=p.events.find(e=>e.kind==='set'&&e.command==='intensity'&&e.delay_ms===0&&e.relative===(G('basis').value==='relative'));P('baseline').value=initial?initial.value:0;setStudioView('day');};
setTimeout(()=>{$('graph-event-protocol').onchange=()=>guarded(()=>{if(selectedEvent===null)return;const p=read(),e=p.events[selectedEvent];if(e?.kind!=='capture')return;checkpoint();e.protocol=$('graph-event-protocol').value;write(p);select(selectedEvent,p);render();});},0);
const onAdd=G('capture').onclick;G('capture').onclick=()=>{onAdd();P('pulse-panel').open=true;};
$('experiment-editor').querySelector('summary').textContent='Edit experiment';
const lighting=document.createElement('details');lighting.className='editor-light-pattern';lighting.innerHTML=`<summary>Daily light window / ramp</summary><div class="plain-fields"><label>From hour<input id="pattern-from" type="number" min="0" max="24" step="any" value="6"></label><label>Until hour<input id="pattern-until" type="number" min="0" max="24" step="any" value="22"></label><label>Start intensity<input id="pattern-start" type="number" min="0" max="500" value="500"></label><label>End intensity<input id="pattern-end" type="number" min="0" max="500" value="500"></label><label>Ramp step (seconds)<input id="pattern-step" type="number" min="1" value="60"></label><button id="pattern-apply" class="button secondary">Apply to day range</button></div><p class="help">Equal intensities hold steady. Different intensities create a stepped ramp. Returns to baseline at the end.</p>`;P('fluctuation').before(lighting);
$('pattern-apply').onclick=()=>studioGuard(()=>{const {first,last,relative}=plainRange(),p=read();const num=id=>{const el=$(id);if(!el.value||!el.checkValidity())throw Error('Check '+el.parentElement.firstChild.textContent);return Number(el.value);};const from=num('pattern-from'),until=num('pattern-until'),low=num('pattern-start'),high=num('pattern-end'),step=num('pattern-step'),base=Number(P('baseline').value);if(until<=from)throw Error('End hour must follow start hour');const count=low===high?1:Math.ceil((until-from)*3600/step)+1;if(count*(last-first+1)+p.events.length>10000)throw Error('Increase ramp step: plan exceeds 10000 events');checkpoint();for(let d=first;d<=last;d++){const a=(d-1)*86400000+from*3600000,b=(d-1)*86400000+until*3600000;p.events=p.events.filter(e=>!(e.kind==='set'&&e.command==='intensity'&&e.relative===relative&&e.delay_ms>=a&&e.delay_ms<=b&&!e.studio_terminal));for(let i=0;i<count;i++){const t=count===1?a:Math.min(b-1,a+i*step*1000),f=count===1?0:Math.min(1,i/(count-1));p.events.push({kind:'set',command:'intensity',value:String(Math.round(low+(high-low)*f)),delay_ms:Math.round(t),relative});}p.events.push({kind:'set',command:'intensity',value:String(base),delay_ms:Math.round(b),relative});}write(p);selectedEvent=null;render();studioMessage('Light pattern applied.');});
const interpretation=document.createElement('label');interpretation.textContent='Measurement type';const kind=document.createElement('select');kind.id='editor-protocol-kind';for(const [v,label]of [['custom','Custom'],['background','Background'],['measuring','Measuring only'],['dark-reference','Dark reference: F₀ + Fm'],['light-adapted','Light adapted: Fs + Fm′'],['saturation','Saturation only']])kind.add(new Option(label,v));interpretation.append(kind);G('protocol').parentElement.after(interpretation);
kind.onchange=()=>guarded(()=>{const p=read(),proto=p.protocols[protocolIndex];if(!proto)throw Error('Add a measurement first');checkpoint();proto.measurement_type=kind.value;write(p);renderPulses(p);});
const renderPulseOriginal=renderPulses;renderPulses=function(p){renderPulseOriginal(p);kind.value=p.protocols[protocolIndex]?.measurement_type||'custom';};
const editorBase=editorPlan;editorPlan=function(){let p=editorBase();p.execution={...p.execution,capture_failure:$('editor-failure')?.value||p.execution?.capture_failure||'stop',on_stop_light:Number($('editor-stop-light')?.value??p.execution?.on_stop_light??0)};return PlanTiming.prepare(p,durationMsInput(),Number($('editor-final-light')?.value||0));};
const loadBase=loadEditor;loadEditor=function(...args){loadDuration(args[0]);if($('editor-stop-light'))$('editor-stop-light').value=args[0].execution?.on_stop_light??0;loadBase(...args);if($('editor-failure'))$('editor-failure').value=args[0].execution?.capture_failure||'stop';if($('editor-final-light'))$('editor-final-light').value=[...args[0].events].sort((a,b)=>a.delay_ms-b.delay_ms).at(-1)?.value||0;};

// Profile components and literature-based acquisition recipes are ordinary editable drafts.
const components=document.createElement('section');components.className='profile-components';components.innerHTML=`<div class="component-title"><h3>Light profile</h3><span>Controller units</span></div><div class="component-fields"><label>Shape<select id="component-shape"><option value="constant">Constant</option><option value="triangle">Triangle / ramp</option><option value="sine">Sinusoidal</option></select></label><label>Lights on (hour)<input id="component-dawn" type="number" min="0" max="24" step="any" value="6"></label><label>Photoperiod (hours)<input id="component-photoperiod" type="number" min="0.001" max="24" step="any" value="16"></label><label>Maximum intensity<input id="component-peak" type="number" min="0" max="500" value="500"></label><label>Night intensity<input id="component-night" type="number" min="0" max="500" value="0"></label><label>Light step (seconds)<input id="component-step" type="number" min="1" value="300"></label></div><div id="component-layers"></div><div class="button-row"><button id="component-add-layer" class="button secondary">+ Fluctuation</button><button id="component-apply" class="button primary">Apply light profile</button><label class="inline-check"><input id="component-hold" type="checkbox" checked> Hold light during camera measurements</label></div><p id="component-feedback" class="help" role="status">Replaces light changes in the chosen day range; keeps measurements. Result is limited to 0–maximum intensity.</p>`;
P('fields').after(components);components.querySelector('.button-row').before(P('range'));P('baseline').parentElement.parentElement.hidden=true;P('add-fluctuation').parentElement.hidden=true;P('fluctuation').hidden=true;lighting.hidden=true;
function addLayer(data={shape:'pulse',amplitude:-100,period:30,hold:5}){const row=document.createElement('div');row.className='component-layer';row.innerHTML='<label>Fluctuation<select data-layer="shape"><option value="pulse">Repeated step</option><option value="sine">Sine wave</option></select></label><label>Offset (units)<input data-layer="amplitude" type="number" min="-500" max="500"></label><label>Period (minutes)<input data-layer="period" type="number" min="1" max="1440" step="any"></label><label>Hold (minutes)<input data-layer="hold" type="number" min="0.01" max="1440" step="any"></label><button class="text-button" type="button" aria-label="Remove fluctuation">Remove</button>';for(const [key,value]of Object.entries(data))row.querySelector('[data-layer="'+key+'"]').value=value;const sync=()=>row.querySelector('[data-layer="hold"]').parentElement.hidden=row.querySelector('[data-layer="shape"]').value==='sine';row.querySelector('select').onchange=sync;sync();row.querySelector('button').onclick=()=>row.remove();$('component-layers').append(row);}
$('component-add-layer').onclick=()=>addLayer();
$('component-apply').onclick=()=>studioGuard(()=>{const {first,last}=plainRange(),c={duration:durationMsInput(),first,last,shape:$('component-shape').value,holdMeasurements:$('component-hold').checked,layers:[...$('component-layers').children].map(row=>Object.fromEntries([...row.querySelectorAll('[data-layer]')].map(el=>[el.dataset.layer,el.value])))};for(const k of ['dawn','photoperiod','peak','night','step']){const el=$('component-'+k);if(!el.value||!el.checkValidity())throw Error('Check '+el.parentElement.firstChild.textContent);c[k]=Number(el.value);}const p=ExperimentParts.compose(read(),c);checkpoint();write(p);selectedEvent=null;render();$('component-feedback').textContent=`Applied to days ${first}–${last} · ${p.events.filter(e=>e.command==='intensity').length} light changes. Drag any point to refine. Camera measurement windows hold the preceding light when enabled.`;});
const presets=document.createElement('section');presets.id='protocol-recipes';presets.className='protocol-recipes';presets.innerHTML=`<div class="component-title"><h3>Fluorescence protocol</h3><span>Editable starting points</span></div><div class="component-fields"><label>Protocol<select id="recipe-type"><option value="npq">NPQ induction + dark recovery</option><option value="dark">Dark yield · F₀ / Fm</option><option value="response">Light response · Fs / Fm′</option></select></label><label>Dark adaptation (minutes)<input id="recipe-dark" type="number" min="0" max="1440" value="20" step="any"></label><label data-recipe="npq">Actinic intensity<input id="recipe-intensity" type="number" min="0" max="500" value="500"></label><label data-recipe="npq">Light duration (minutes)<input id="recipe-light" type="number" min="1" max="1440" value="5" step="any"></label><label data-recipe="npq">Measurements in light<input id="recipe-count" type="number" min="1" max="100" value="3"></label><label data-recipe="npq">Dark recovery (minutes)<input id="recipe-recovery" type="number" min="0" max="1440" value="5" step="any"></label><label data-recipe="response" hidden>Intensity steps<input id="recipe-levels" value="100,200,300,400,500"></label><label data-recipe="response" hidden>Time per step (minutes)<input id="recipe-dwell" type="number" min="1" max="120" value="5" step="any"></label></div><details><summary>Acquisition defaults</summary><div class="component-fields"><label>Frames per phase<input id="recipe-frames" type="number" min="1" max="50" value="10"></label><label>Exposure (µs)<input id="recipe-exposure" type="number" min="1" max="100000" value="50"></label><label>Frame spacing (ms)<input id="recipe-interval" type="number" min="95" max="30000" value="95" step="any"></label></div></details><div class="button-row"><button id="recipe-build" class="button primary">Load protocol as new draft</button><span id="recipe-status" class="help" role="status"></span></div><p class="help">0 minutes means already dark-adapted. Confirm adaptation and pulse saturation for your plants. Loading replaces the draft; Undo restores it.</p><details class="protocol-basis"><summary>Method and references</summary><p>Background → dark F₀ / Fm → actinic Fs / Fm′ → optional dark recovery. Fv/Fm = (Fm − F₀) / Fm; ΦII = (Fm′ − Fs) / Fm′; NPQ = (Fm − Fm′) / Fm′. These DEPI templates adapt saturation-pulse methods; their timings are editable, not universal biological settings.</p><p>Light-response steps do not establish steady state automatically. Recovery records NPQ relaxation, not an automatic qE/qI separation. F₀′, qP and qL are omitted because the far-red channel is unavailable. Intensity remains in controller units until PPFD calibration.</p><p><a href="https://doi.org/10.1093/jxb/ert208" target="_blank" rel="noopener">Murchie & Lawson, 2013</a> · <a href="https://doi.org/10.1146/annurev.arplant.59.032607.092759" target="_blank" rel="noopener">Baker, 2008</a> · <a href="https://doi.org/10.1071/FP02061" target="_blank" rel="noopener">Govindjee & Seufferheld, 2002</a></p></details>`;
P('measurement-panel').before(presets);$('recipe-type').onchange=()=>{for(const e of presets.querySelectorAll('[data-recipe]'))e.hidden=e.dataset.recipe!==$('recipe-type').value;};
$('recipe-build').onclick=()=>{try{const c={type:$('recipe-type').value,darkMinutes:$('recipe-dark').value,intensity:$('recipe-intensity').value,lightMinutes:$('recipe-light').value,count:$('recipe-count').value,recoveryMinutes:$('recipe-recovery').value,levels:$('recipe-levels').value,dwellMinutes:$('recipe-dwell').value,frames:$('recipe-frames').value,exposure:$('recipe-exposure').value,interval:$('recipe-interval').value};const p=ExperimentParts.preset(c);checkpoint();loadEditor(p,null,null,false);selectedEvent=null;render();$('recipe-status').textContent=p.events.length+' events · '+Math.round(p.studio.duration_ms/1000)+' seconds · review the timeline before Start';}catch(e){$('recipe-status').textContent=e.message;}};
// In-place draft graph editor. Edits the plan draft only; no device requests.
// Integrated into the application editor scope. Uses the host's
// read/write/checkpoint/loadEditor so every editor action shares one renderer
// and one history.
// In-place draft graph editor. Edits the plan draft only; no device requests.
// Spliced into the portal's editor scope by the hosting relay. Uses the host's
// read/write/checkpoint/loadEditor so every editor action shares one renderer
// and one history.
// <editor-bundle> GENERATED by tools/build_ui.py from depibeans/ui/src/editor. Edit the sources, then rebuild.
// sources sha256 485ce8d55174e53d99d3d6c0b5885dfe40bc51d81ae0a26444446384f24b07d8
const DepiEditor = (() => {
// ---- constants.js ----------------------------------------------------------
// Limits shared by the graph, the script and the tests.
const GRID_MS = 100;            // timeline editing step: 0.1 s
const LIGHT_MAX = 500;          // main light, controller units (whole numbers)
const CHANNEL_MAX = 65535;      // FR / UVA / UVB raw channel range
const DAY_MS = 86400000;
const MIN_SPAN_MS = 2000;       // closest zoom
const HISTORY_LIMIT = 100;
const MAX_EVENTS = 10000;       // controller limit per plan
const LONG_PLAN_MS = 600000;    // from here on, times read as h:mm:ss
const UNIT_MS = { s: 1000, min: 60000, h: 3600000, d: DAY_MS };

// ---- plan.js ---------------------------------------------------------------
// Plan events: identity, boundaries, overlap rules and selection tracking.
// A plan is { events: [...], protocols: [...], studio: {...} }. Events carry
// delay_ms (whole ms), relative, kind 'set' | 'capture', and command/value or protocol.

const isLight = event => event.kind === 'set' && event.command === 'intensity';

// The first and final light settings define the run boundaries; their time is fixed.
const isAnchored = (event, endMs) =>
  isLight(event) && (event.delay_ms === 0 || event.delay_ms === endMs || !!event.studio_terminal);

// Everything that identifies an event except its position in the list.
function eventSignature(event) {
  const { sequence, ...rest } = event;
  return JSON.stringify(rest);
}

// What the script shows of an event; equal keys mean "the same line".
const eventKey = event =>
  [event.relative, event.delay_ms, event.kind, event.command ?? '', event.protocol ?? '', event.value ?? ''].join('|');

// Two events occupy the same slot when nothing could order them: same time base,
// same millisecond, and both measurements or both the same light channel.
const sameSlot = (a, b) =>
  a.relative === b.relative && a.delay_ms === b.delay_ms && a.kind === b.kind && (a.kind === 'capture' || a.command === b.command);

// First of `rows` that lands on an event outside `rows`, or null.
function findCollision(plan, rows) {
  const mine = new Set(rows);
  for (const row of rows) if (plan.events.some(event => !mine.has(event) && sameSlot(event, row))) return row;
  return null;
}

// True when any two events anywhere in the plan share a slot.
function hasOverlap(plan) {
  const seen = new Set();
  for (const event of plan.events) {
    const slot = JSON.stringify([event.relative, event.delay_ms, event.kind, event.kind === 'capture' ? '' : event.command || '']);
    if (seen.has(slot)) return true;
    seen.add(slot);
  }
  return false;
}

// A copy that is an ordinary event: no list position, not the run's final
// setting, not a member of a repeat.
function plainCopy(event) {
  const copy = structuredClone(event);
  delete copy.sequence;
  delete copy.studio_terminal;
  delete copy.repeat;
  return copy;
}

// Selection is kept as indices into plan.events. When the draft changes outside
// the editor (a host button, the JSON box, a re-sort) the same events are found
// again by signature; among identical events the n-th stays the n-th.
function remapSelection(previousSignatures, chosen, signatures) {
  const next = new Set();
  for (const index of chosen) {
    const signature = previousSignatures[index];
    if (signature === undefined) continue;
    let nth = 0;
    for (let k = 0; k < index; k++) if (previousSignatures[k] === signature) nth++;
    for (let k = 0; k < signatures.length; k++) {
      if (signatures[k] === signature && !next.has(k) && nth-- <= 0) { next.add(k); break; }
    }
  }
  return next;
}

// ---- time.js ---------------------------------------------------------------
// Time text. Plans store whole milliseconds; nothing here rounds a stored time.
// `long` selects clock notation (h:mm:ss, optional "2d " prefix) for plans of
// ten minutes or more; shorter plans read in seconds.

const isLongPlan = totalMs => totalMs >= LONG_PLAN_MS;

// Fixed decimals without trailing zeros: trimNumber(1.50, 3) -> "1.5".
const trimNumber = (value, decimals) => String(Number(value.toFixed(decimals)));

const pad2 = value => String(value).padStart(2, '0');

// Exact time, to the millisecond, as the script and inspector show it.
function exactTime(ms, long) {
  if (!long) return trimNumber(ms / 1000, 3);
  const days = Math.floor(ms / DAY_MS);
  const hours = Math.floor(ms % DAY_MS / 3600000);
  const minutes = Math.floor(ms % 3600000 / 60000);
  const [whole, part] = trimNumber(ms % 60000 / 1000, 3).split('.');
  return (days ? days + 'd ' : '') + pad2(hours) + ':' + pad2(minutes) + ':' + whole.padStart(2, '0') + (part ? '.' + part : '');
}

// Exact time with its unit, for messages and tooltips.
const timeLabel = (ms, long) => long ? exactTime(ms, long) : exactTime(ms, long) + ' s';

// Axis tick text at a given tick spacing.
function tickLabel(ms, stepMs, long) {
  if (!long) return trimNumber(ms / 1000, stepMs < 1000 ? 1 : 0) + ' s';
  if (stepMs >= DAY_MS) return 'day ' + (Math.floor(ms / DAY_MS) + 1);
  const days = Math.floor(ms / DAY_MS);
  let out = (days ? days + 'd ' : '') + pad2(Math.floor(ms % DAY_MS / 3600000)) + ':' + pad2(Math.floor(ms % 3600000 / 60000));
  if (stepMs < 60000) {
    const seconds = ms % 60000 / 1000;
    out += ':' + (stepMs < 1000 ? seconds.toFixed(1).padStart(4, '0') : pad2(Math.floor(seconds)));
  }
  return out;
}

// "12.5", "12.5 s", "0:02:05.5" or "1d 06:00:00" -> whole milliseconds.
function parseTime(raw, long) {
  const value = String(raw).trim().replace(/\s*s$/, '');
  if (/^\d+(\.\d+)?$/.test(value)) return Math.round(Number(value) * 1000);
  const match = value.match(/^(?:(\d+)d\s*)?(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/);
  if (!match) throw Error(long ? 'Enter time as h:mm:ss or seconds.' : 'Enter time in seconds.');
  return Math.round(((Number(match[1] || 0) * 24 + Number(match[2])) * 3600 + Number(match[3]) * 60 + Number(match[4])) * 1000);
}

// A time or a whole number of days ("5d"), used for periods and intervals.
function parseSpan(token, long) {
  const days = String(token).match(/^(\d+)d$/i);
  return days ? Number(days[1]) * DAY_MS : parseTime(token, long);
}

const signedSeconds = ms => (ms < 0 ? '−' : '+') + trimNumber(Math.abs(ms) / 1000, 3) + ' s';

// "duration" line: the largest unit that divides the duration exactly.
function durationText(ms) {
  for (const unit of ['d', 'h', 'min']) if (ms % UNIT_MS[unit] === 0) return ms / UNIT_MS[unit] + ' ' + unit;
  return trimNumber(ms / 1000, 3) + ' s';
}

// Repeat period: whole days as "2d", otherwise an exact time.
const periodText = (ms, long) => ms % DAY_MS === 0 ? ms / DAY_MS + 'd' : exactTime(ms, long);

// ---- chart.js --------------------------------------------------------------
// Drawing. Turns a draft and a view into SVG; holds no editor state and changes no plan.

const TICK_STEPS = [100, 200, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000, 600000, 900000, 1800000,
  3600000, 7200000, 10800000, 21600000, 43200000, DAY_MS, 2 * DAY_MS, 5 * DAY_MS, 10 * DAY_MS, 30 * DAY_MS, 60 * DAY_MS];
const LEVEL_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2500, 5000, 10000, 20000];

// The SVG uses one unit per CSS pixel, so text and points keep their size at any width.
function measureChart(chart) {
  const box = chart.getBoundingClientRect();
  const W = Math.max(480, Math.round(box.width) || 1000);
  const H = Math.max(240, Math.round(box.height) || 300);
  chart.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const left = 52, right = W - 18, top = 18, axis = H - 26, laneH = 30, lane = axis - laneH, bottom = lane - 14;
  return { W, H, left, right, top, bottom, lane, laneH, axis, width: right - left };
}

const tickStep = (spanMs, widthPx) => {
  const want = spanMs / Math.max(2, widthPx / 96);
  return TICK_STEPS.find(step => step >= want) || TICK_STEPS.at(-1);
};

const lightCeiling = (plan, configured) =>
  Math.max(1, Number(configured) || LIGHT_MAX, ...plan.events.filter(isLight).map(event => Number(event.value)));

// Position of an event in chart pixels; shared by drawing and box selection.
function eventPosition(event, geometry, view, yMax) {
  return {
    x: geometry.left + (event.delay_ms - view.start) / view.span * geometry.width,
    y: isLight(event) ? geometry.bottom - Number(event.value) / yMax * (geometry.bottom - geometry.top) : geometry.lane + geometry.laneH / 2,
  };
}

// model: { plan, view:{start,span}, endMs, long, yMax, geometry, eligible(event),
//          selection:Set<event>, cursor:number|null, box:{x,y,w,h}|null }
function drawChart(chart, svg, model) {
  const { plan, view, endMs, long, yMax, geometry: g, selection } = model;
  const x = ms => g.left + (ms - view.start) / view.span * g.width;
  const y = level => g.bottom - Number(level) / yMax * (g.bottom - g.top);
  const inView = ms => ms >= view.start && ms <= view.start + view.span;
  const indexOf = new Map(plan.events.map((event, index) => [event, index]));

  chart.replaceChildren();
  const clip = svg(svg(chart, 'defs'), 'clipPath', { id: 'ge-plot' });
  svg(clip, 'rect', { x: g.left, y: 0, width: g.width, height: g.H });

  const step = tickStep(view.span, g.width);
  for (let ms = Math.ceil(view.start / step) * step; ms <= view.start + view.span + 1e-6; ms += step) {
    const at = x(ms);
    svg(chart, 'line', { x1: at, x2: at, y1: g.top, y2: g.axis, class: 'ge-grid' });
    svg(chart, 'text', { x: at, y: g.axis + 17, 'text-anchor': at > g.right - 30 ? 'end' : at < g.left + 30 ? 'start' : 'middle', class: 'ge-tick' }, tickLabel(ms, step, long));
  }
  const levelStep = LEVEL_STEPS.find(candidate => yMax / candidate <= 5) || LEVEL_STEPS.at(-1);
  for (let level = 0; level <= yMax; level += levelStep) {
    svg(chart, 'line', { x1: g.left, x2: g.right, y1: y(level), y2: y(level), class: 'ge-grid' });
    svg(chart, 'text', { x: g.left - 8, y: y(level) + 4, 'text-anchor': 'end', class: 'ge-tick' }, String(level));
  }
  svg(chart, 'line', { x1: g.left, x2: g.right, y1: g.lane + g.laneH / 2, y2: g.lane + g.laneH / 2, class: 'ge-lane' });
  svg(chart, 'line', { x1: g.left, x2: g.right, y1: g.axis, y2: g.axis, class: 'ge-axis' });
  if (inView(endMs)) svg(chart, 'line', { x1: x(endMs), x2: x(endMs), y1: g.top, y2: g.axis, class: 'ge-end' });

  // The light trace is a step function: the level holds until the next setting.
  const rows = plan.events.filter(model.eligible);
  const lights = rows.filter(isLight).sort((a, b) => a.delay_ms - b.delay_ms);
  let level = 0;
  for (const event of lights) if (event.delay_ms <= view.start) level = event.value;
  let path = `M${g.left} ${y(level)}`;
  for (const event of lights) if (event.delay_ms > view.start && event.delay_ms <= view.start + view.span) path += ` H${x(event.delay_ms)} V${y(event.value)}`;
  path += ` H${Math.min(g.right, x(endMs))}`;
  svg(chart, 'path', { d: path, class: 'ge-trace', 'clip-path': 'url(#ge-plot)' });

  for (const event of rows) {
    if (!inView(event.delay_ms)) continue;
    const capture = event.kind === 'capture', on = selection.has(event), cx = x(event.delay_ms);
    const node = capture
      ? svg(chart, 'rect', { x: cx - 5, y: g.lane + 3, width: 10, height: g.laneH - 6, rx: 2 })
      : svg(chart, 'circle', { cx, cy: y(event.value), r: on ? 6 : 5 });
    node.setAttribute('class', 'ge-point ' + (capture ? 'ge-capture' : 'ge-light') + (on ? ' ge-on' : ''));
    node.dataset.event = indexOf.get(event);
    svg(node, 'title').textContent = (capture ? event.protocol : event.value) + ' · ' + timeLabel(event.delay_ms, long);
  }

  if (model.cursor !== null && inView(model.cursor)) {
    const cx = x(model.cursor);
    svg(chart, 'line', { x1: cx, x2: cx, y1: g.top, y2: g.axis, class: 'ge-cursor' });
    svg(chart, 'path', { d: `M${cx - 4} ${g.top - 7}h8l-4 6z`, class: 'ge-cursor-head' });
  }
  if (model.box) svg(chart, 'rect', { x: model.box.x, y: model.box.y, width: model.box.w, height: model.box.h, class: 'ge-box' });
}

// The one-line readout above the chart: the gesture in progress, or the selection.
function readoutText(selection, gesture, long) {
  if (gesture?.type === 'move' && gesture.moved) {
    const parts = [];
    if (gesture.dt) parts.push('Δt ' + signedSeconds(gesture.dt));
    if (gesture.dv) parts.push('Δ level ' + (gesture.dv > 0 ? '+' : '−') + Math.abs(gesture.dv));
    if (gesture.copying) parts.push('copy');
    return parts.join(' · ');
  }
  if (selection.size === 1) {
    const event = [...selection][0];
    return (event.kind === 'capture' ? event.protocol : 'level ' + event.value) + ' · ' + timeLabel(event.delay_ms, long);
  }
  if (selection.size > 1) {
    const times = [...selection].map(event => event.delay_ms);
    return `${selection.size} selected · ${timeLabel(Math.min(...times), long)} – ${timeLabel(Math.max(...times), long)}`;
  }
  return '';
}

// ---- history.js ------------------------------------------------------------
// One undo/redo history of draft texts, shared by the graph, the script and every
// host action that calls checkpoint(). A history belongs to one draft: opening
// another experiment clears it.

function createHistory(limit = HISTORY_LIMIT) {
  let undoStack = [];
  let redoStack = [];

  // Pops until a state different from `current` is found; the rest are no-ops
  // left by actions that checkpointed and then changed nothing.
  function travel(from, to, current) {
    let saved;
    do { saved = from.pop(); } while (saved !== undefined && saved === current);
    if (saved === undefined) return undefined;
    to.push(current);
    return saved;
  }

  return {
    // Records the draft as it is before a change. Returns whether a state was added.
    checkpoint(text) {
      if (!text) return false;
      const added = undoStack.at(-1) !== text;
      if (added) undoStack.push(text);
      if (undoStack.length > limit) undoStack.shift();
      redoStack = [];
      return added;
    },
    // Withdraws the checkpoint of a change that then failed.
    dropLast() { undoStack.pop(); },
    undo(current) { return travel(undoStack, redoStack, current); },
    redo(current) { return travel(redoStack, undoStack, current); },
    clear() { undoStack = []; redoStack = []; },
    get canUndo() { return undoStack.length > 0; },
    get canRedo() { return redoStack.length > 0; },
    get depth() { return undoStack.length; },
  };
}

// ---- layout.js -------------------------------------------------------------
// Page arrangement around the editor: the graph and script come first, generators
// are one collapsed section below them, and controls that only repeat what a field
// already does on commit are retired. Elements are moved, never recreated, so the
// host's own handlers and ids keep working.

function moveIfPresent(target, ...nodes) {
  for (const node of nodes) if (node) target.append(node);
}

function arrangeEditorPage({ $, G, frame, bar, readout }) {
  const document = frame.ownerDocument;

  // "Add light change" / "Add measurement" join the editor's own toolbar.
  const addLight = G('light'), addMeasurement = G('capture'), typeLabel = $('graph-measurement-type')?.parentElement;
  if (addLight && addMeasurement) {
    const row = addLight.parentElement;
    const group = document.createElement('span');
    group.className = 'ge-add';
    addLight.textContent = '+ Light';
    addLight.title = 'Add a light change in the middle of the view';
    addMeasurement.textContent = '+ Measurement';
    addMeasurement.title = 'Add a measurement of the chosen type in the middle of the view';
    if (typeLabel) {
      for (const node of [...typeLabel.childNodes]) if (node.nodeType === 3) node.textContent = '';   // the select carries its own accessible name
      typeLabel.classList.add('ge-add-type');
    }
    moveIfPresent(group, addLight, typeLabel, addMeasurement);
    bar.insertBefore(group, readout);
    if (row && !row.querySelector('button:not([hidden]):not(#graph-undo), select, input')) row.hidden = true;
  }

  // Generators write events into the same draft; they are tools, not the main view.
  const profile = document.querySelector('.profile-components'), range = $('plain-range');
  if (profile) {
    const generators = document.createElement('details');
    generators.className = 'ge-generators';
    const summary = document.createElement('summary');
    summary.textContent = 'Generators · daily light profile and day range';
    generators.append(summary);
    moveIfPresent(generators, range, profile);
    frame.after(generators);
  }

  // The duration field applies itself when committed (Enter or leaving the field),
  // through the host's validation. A second button for the same action is noise.
  for (const button of document.querySelectorAll('#experiment-editor button')) {
    if (button.textContent.trim() === 'Apply duration') button.hidden = true;
  }
}

// ---- presets.js ------------------------------------------------------------
// Presets and the clipboard add ordinary events to the one shared draft. Both must
// keep measurement protocols straight: reuse a protocol the plan already has, and
// never silently point an event at a different protocol of the same name.

const PRESET_DEFAULTS = {
  darkMinutes: 0, intensity: Math.min(LIGHT_MAX, 500), frames: 10, exposure: 50, interval: 100,
  lightMinutes: 5, count: 5, recoveryMinutes: 2, levels: '50,100,200,400', dwellMinutes: 2,
};

const PRESET_CHOICES = [
  ['npq', 'NPQ induction and recovery'],
  ['response', 'Light response steps'],
  ['dark', 'Dark yield · F₀ / Fm'],
  ['repeat', 'Repeat block'],
];

// Returns the name under which `protocol` is available in the plan, adding it if
// needed. The same definition is never stored twice: an identical protocol is reused
// whatever its name. A different protocol under the same name gets a numbered name.
function adoptProtocol(plan, protocol) {
  const definition = candidate => JSON.stringify({ ...candidate, id: null });
  const wanted = definition(protocol);
  const numbered = new RegExp('^' + protocol.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(-\\d+)?$');
  const same = plan.protocols.find(candidate => numbered.test(candidate.id) && definition(candidate) === wanted);
  if (same) return same.id;
  let id = protocol.id;
  for (let n = 2; plan.protocols.some(candidate => candidate.id === id); n++) id = protocol.id + '-' + n;
  plan.protocols.push({ ...structuredClone(protocol), id });
  return id;
}

// Events of a generated preset plan, shifted to start at `atMs`. An identical light
// setting already at that slot is left alone; anything else at an occupied slot is
// refused, so a preset never stacks a second measurement or a conflicting level.
// Adds the protocols the rows need to `plan`. Does not add the rows.
function presetRows(plan, preset, atMs, relative) {
  const names = new Map();
  for (const protocol of preset.protocols) names.set(protocol.id, adoptProtocol(plan, protocol));
  const rows = [];
  for (const source of preset.events) {
    const event = structuredClone(source);
    delete event.sequence;
    if (event.protocol) event.protocol = names.get(event.protocol) || event.protocol;
    event.delay_ms += atMs;
    event.relative = relative;
    const occupied = plan.events.find(other => sameSlot(other, event));
    if (occupied) {
      if (event.kind === 'capture' || JSON.stringify(occupied.value) !== JSON.stringify(event.value)) throw Error('Preset overlaps an existing event. Choose another time.');
      continue;
    }
    rows.push(event);
  }
  if (!rows.length) throw Error('Those events are already in the plan at this time.');
  return rows;
}

// Starter text for a repeat block: daily on plans of a day or more, otherwise a
// quarter of the plan, switching the light at 25 % and 75 % of each period.
function repeatTemplate(totalMs, atMs, long) {
  const period = totalMs >= DAY_MS ? DAY_MS : Math.max(1000, Math.floor(totalMs / 4 / 1000) * 1000);
  const count = Math.max(1, Math.floor((totalMs - atMs) / period));
  const at = fraction => exactTime(Math.round(period * fraction / GRID_MS) * GRID_MS, long);
  return `repeat ${count} every ${periodText(period, long)} from ${exactTime(atMs, long)}\n  ${at(.25)}  light 200\n  ${at(.75)}  light 0\nend`;
}

// Clipboard: the selected events relative to their first, with the protocols they use.
// `draft` identifies the draft they were copied from.
function makeClip(plan, rows, draft) {
  const start = Math.min(...rows.map(event => event.delay_ms));
  const used = new Set(rows.map(event => event.protocol).filter(Boolean));
  return {
    draft,
    events: structuredClone(rows).map(event => ({ ...event, delay_ms: event.delay_ms - start })),
    protocols: structuredClone(plan.protocols.filter(protocol => used.has(protocol.id))),
    span: Math.max(...rows.map(event => event.delay_ms)) - start,
  };
}

// Pasted events placed at `atMs`. Within the draft they were copied from, a pasted
// measurement keeps its protocol reference. In another draft the protocol is added
// when missing, or added under a numbered name when that draft defines it differently.
function pasteRows(plan, clip, atMs, relative, draft) {
  const names = new Map();
  const nameFor = id => {
    if (names.has(id)) return names.get(id);
    const source = clip.protocols.find(protocol => protocol.id === id);
    const present = plan.protocols.find(protocol => protocol.id === id);
    let use = id;
    if (!present) {
      if (!source) throw Error('Measurement protocol is unavailable.');
      plan.protocols.push(structuredClone(source));
    } else if (clip.draft !== draft && source && JSON.stringify(source) !== JSON.stringify(present)) {
      use = adoptProtocol(plan, source);
    }
    names.set(id, use);
    return use;
  };
  return clip.events.map(source => {
    const event = plainCopy(source);
    event.delay_ms = atMs + source.delay_ms;
    event.relative = relative;
    if (event.kind === 'capture') event.protocol = nameFor(event.protocol);
    return event;
  });
}

// ---- repeats.js ------------------------------------------------------------
// Repeat blocks. A block is stored with the draft in plan.studio.repeats:
//   { id, count, period_ms, start_ms, lines: [{ offset_ms, kind, ... }], skip: [[i, k], ...] }
// Every generated event is a real, executable event tagged repeat: { id, i, k }
// (block, iteration, line). `skip` lists instances that were deleted or detached,
// so regenerating the block does not bring them back.

const clampNumber = (value, low, high) => Math.max(low, Math.min(high, value));

const blocksOf = plan => Array.isArray(plan.studio?.repeats) ? plan.studio.repeats : [];

const blockOf = (plan, event) => event.repeat ? blocksOf(plan).find(block => block.id === event.repeat.id) || null : null;

const isSkipped = (block, i, k) => (block.skip || []).some(entry => entry[0] === i && entry[1] === k);

// One canonical shape for a stored block, so two descriptions of the same repeat
// compare equal whatever order their fields were written in.
function normalizeBlock(block) {
  const lines = block.lines.map(line => {
    const out = { offset_ms: line.offset_ms, kind: line.kind };
    for (const field of ['command', 'value', 'protocol', 'label']) if (line[field] !== undefined && line[field] !== '') out[field] = line[field];
    return out;
  });
  return { id: block.id, count: block.count, period_ms: block.period_ms, start_ms: block.start_ms, lines, skip: (block.skip || []).map(entry => [entry[0], entry[1]]) };
}

function makeInstance(block, i, k) {
  const line = block.lines[k];
  const event = { kind: line.kind, delay_ms: block.start_ms + i * block.period_ms + line.offset_ms, relative: true };
  if (line.kind === 'set') { event.command = line.command; event.value = line.value; }
  else event.protocol = line.protocol;
  if (line.label) event.label = line.label;
  event.repeat = { id: block.id, i, k };
  return event;
}

// Replaces every instance of `block` in the plan. Returns the new instances.
function expandBlock(plan, block) {
  plan.events = plan.events.filter(event => event.repeat?.id !== block.id);
  const made = [];
  for (let i = 0; i < block.count; i++)
    for (let k = 0; k < block.lines.length; k++)
      if (!isSkipped(block, i, k)) made.push(makeInstance(block, i, k));
  plan.events.push(...made);
  return made;
}

// Identifies a selection of repeat instances, so one answer to "Change all / Only
// this" can carry across a run of keyboard nudges on the same events.
const repeatSelectionKey = rows =>
  rows.filter(event => event.repeat).map(event => [event.repeat.id, event.repeat.i, event.repeat.k].join(':')).sort().join();

// What changed on each edited repeat instance, relative to the saved draft.
function repeatDeltas(basePlan, editedPlan, rows) {
  const deltas = [];
  for (const event of rows) {
    if (!blockOf(editedPlan, event)) continue;
    const { id, i, k } = event.repeat;
    const was = basePlan.events.find(old => old.repeat && old.repeat.id === id && old.repeat.i === i && old.repeat.k === k);
    if (!was) continue;
    deltas.push({ id, i, k, dt: event.delay_ms - was.delay_ms, dv: isLight(event) ? Number(event.value) - Number(was.value) : 0 });
  }
  return deltas;
}

// "Only this": the edited instances leave their block and become ordinary events.
function detachInstances(plan, rows) {
  for (const event of rows) {
    const block = blockOf(plan, event);
    if (!block) continue;
    (block.skip = block.skip || []).push([event.repeat.i, event.repeat.k]);
    delete event.repeat;
  }
  return rows;
}

// Deleting an instance removes it from that iteration only.
function skipInstances(plan, rows) {
  for (const event of rows) {
    const block = blockOf(plan, event);
    if (block) (block.skip = block.skip || []).push([event.repeat.i, event.repeat.k]);
  }
}

// "Change all": the change moves to the block's line and every instance is rebuilt.
// Returns the events to keep selected. Throws if any instance leaves the experiment.
function changeAllInstances(plan, rows, deltas, endMs) {
  const touched = new Map();
  const keep = rows.filter(event => !blockOf(plan, event));
  const wanted = [];
  for (const delta of deltas) {
    const block = blocksOf(plan).find(candidate => candidate.id === delta.id);
    if (!block) continue;
    wanted.push(delta);
    const mark = delta.id + ':' + delta.k;
    if (touched.has(mark)) continue;       // one line, one change, however many instances were dragged
    touched.set(mark, block);
    const line = block.lines[delta.k];
    line.offset_ms += delta.dt;
    if (line.kind === 'set' && line.command === 'intensity' && delta.dv) line.value = String(clampNumber(+line.value + delta.dv, 0, LIGHT_MAX));
  }
  for (const block of new Set(touched.values())) {
    const made = expandBlock(plan, block);
    if (made.some(event => event.delay_ms < 0 || event.delay_ms > endMs)) throw Error('That moves part of the repeat outside the experiment.');
    for (const delta of wanted) {
      if (delta.id !== block.id) continue;
      const again = made.find(event => event.repeat.i === delta.i && event.repeat.k === delta.k);
      if (again) keep.push(again);
    }
  }
  return keep;
}

// ---- script.js -------------------------------------------------------------
// The script: the draft's events as text, edited in step with the graph.
//
//   duration 400 s
//   <time> light <level>              main light, whole number 0–500
//   <time> measure <protocol>         a protocol already in the plan
//   <time> set <FR|UVA|UVB> <value>   other channels
//   ... # note                        kept as the event's label
//   +<time> ...                       after the previous line
//   abs <time> ...                    calendar-based event
//   every <interval> from <time> to <time> <action>       expands into plain events
//   repeat <count> every <period> [from <time>] ... end   stays a block
//
// Parsing never touches the plan. A script that does not parse or validate leaves
// the last valid draft exactly as it was.

const TIME = '(?:\\d+d\\s+)?\\d+:\\d{1,2}:\\d{1,2}(?:\\.\\d+)?|\\d+d|\\d+(?:\\.\\d+)?';
const EVERY = new RegExp(`^every\\s+(${TIME})\\s+from\\s+(${TIME})\\s+to\\s+(${TIME})\\s+(.+)$`, 'i');
const EVENT = new RegExp(`^(abs\\s+)?(\\+)?(${TIME})\\s+(.+)$`, 'i');
const REPEAT = new RegExp(`^repeat\\s+(\\d+)\\s+every\\s+(${TIME})(?:\\s+from\\s+(${TIME}))?\\s*:?$`, 'i');
const DURATION = /^duration\s+(\d+(?:\.\d+)?)\s*(s|min|h|d)$/i;

// An error that belongs to one line of the script (zero-based).
function scriptError(line, message) {
  const error = Error(message);
  error.line = line;
  return error;
}

const actionText = item => isLight(item) ? 'light ' + item.value : item.kind === 'set' ? `set ${item.command} ${item.value}` : 'measure ' + item.protocol;
const noteText = item => item.label ? '  # ' + String(item.label).replace(/\s+/g, ' ') : '';

// Plan -> text. Also returns, per line, the indices of the events that line stands
// for: one for a plain line, every instance for a line inside a repeat.
function composeScript(plan, { totalMs, long }) {
  const blocks = blocksOf(plan).filter(block => plan.events.some(event => event.repeat?.id === block.id));
  const plain = plan.events.map((event, index) => ({ event, index })).filter(({ event }) => !blocks.includes(blockOf(plan, event)));
  const times = plain.map(({ event }) => (event.relative ? '' : 'abs ') + exactTime(event.delay_ms, long));
  const width = Math.max(8, ...times.map(text => text.length)) + 2;
  const lines = ['duration ' + durationText(totalMs)];
  const lineEvents = [[]];
  plain.forEach(({ event, index }, n) => {
    lines.push(times[n].padEnd(width) + actionText(event) + noteText(event));
    lineEvents.push([index]);
  });
  for (const block of blocks) {
    lines.push('');
    lineEvents.push([]);
    lines.push(`repeat ${block.count} every ${periodText(block.period_ms, long)} from ${exactTime(block.start_ms, long)}`);
    lineEvents.push([]);
    const offsets = block.lines.map(line => exactTime(line.offset_ms, long));
    const offsetWidth = Math.max(8, ...offsets.map(text => text.length)) + 2;
    block.lines.forEach((line, k) => {
      lines.push('  ' + offsets[k].padEnd(offsetWidth) + actionText(line) + noteText(line));
      lineEvents.push(plan.events.map((event, index) => event.repeat && event.repeat.id === block.id && event.repeat.k === k ? index : -1).filter(index => index >= 0));
    });
    lines.push('end');
    lineEvents.push([]);
  }
  return { text: lines.join('\n'), lineEvents };
}

function parseAction(rest, line, protocols) {
  let label;
  const hash = rest.indexOf('#');
  if (hash >= 0) { label = rest.slice(hash + 1).trim(); rest = rest.slice(0, hash); }
  rest = rest.trim();
  let match;
  if ((match = rest.match(/^light\s+(\S+)$/i)) || (match = rest.match(/^set\s+intensity\s+(\S+)$/i))) {
    const level = Number(match[1]);
    if (!Number.isInteger(level) || level < 0 || level > LIGHT_MAX) throw scriptError(line, `Light level is a whole number 0–${LIGHT_MAX}.`);
    return { kind: 'set', command: 'intensity', value: String(level), label };
  }
  if ((match = rest.match(/^set\s+(FR|UVA|UVB)\s+(\S+)$/i))) {
    const value = Number(match[2]);
    if (!Number.isFinite(value) || value < 0 || value > CHANNEL_MAX) throw scriptError(line, `Channel value must be 0–${CHANNEL_MAX}.`);
    return { kind: 'set', command: match[1].toUpperCase(), value: String(value), label };
  }
  if ((match = rest.match(/^measure\s+(.+)$/i))) {
    const id = match[1].trim();
    if (!protocols.includes(id)) throw scriptError(line, `Unknown protocol "${id}". Available: ${protocols.join(', ') || 'none'}.`);
    return { kind: 'capture', protocol: id, label };
  }
  throw scriptError(line, 'Expected  light <level>,  measure <protocol>  or  set <channel> <value>.');
}

// Text -> { duration, items, blocks }. `items` are the events the text describes,
// each with the line it came from; repeat blocks are already expanded into items.
// `plan` supplies the protocol names and the existing blocks' skipped instances.
function parseScript(source, plan, { long }) {
  const protocols = plan.protocols.map(protocol => protocol.id);
  const items = [];
  const blocks = [];
  let duration = null;
  let previous = 0;
  let open = null;
  const timeOf = (token, line) => { try { return parseSpan(token, long); } catch (error) { throw scriptError(line, error.message); } };

  source.split('\n').forEach((raw, line) => {
    const text = raw.trim();
    let match;
    if (!text) return;
    if (text.startsWith('#')) throw scriptError(line, 'Put a note after an event:  100 light 500  # note');
    if (/^end$/i.test(text)) {
      if (!open) throw scriptError(line, '"end" without a repeat.');
      if (!open.lines.length) throw scriptError(open.line, 'The repeat is empty.');
      blocks.push(open);
      open = null;
      return;
    }
    if ((match = text.match(REPEAT))) {
      if (open) throw scriptError(line, 'Finish the previous repeat with "end" first.');
      const count = Number(match[1]), period = timeOf(match[2], line), start = match[3] ? timeOf(match[3], line) : 0;
      if (count < 1 || count > 1000) throw scriptError(line, 'Repeat 1–1000 times.');
      if (period < GRID_MS) throw scriptError(line, 'The period is too short.');
      open = { line, count, period_ms: period, start_ms: start, lines: [] };
      previous = 0;
      return;
    }
    if (/^repeat\b/i.test(text)) throw scriptError(line, 'Write  repeat 5 every 1d from 0  then the events, then  end');
    if ((match = text.match(DURATION))) {
      if (open) throw scriptError(line, 'Set the duration outside the repeat.');
      duration = Math.round(Number(match[1]) * UNIT_MS[match[2].toLowerCase()]);
      if (duration < 1000 || duration > 366 * DAY_MS) throw scriptError(line, 'Duration must be 1 second to 366 days.');
      return;
    }
    if (/^duration\b/i.test(text)) throw scriptError(line, 'Write the duration as  duration 400 s  (s, min, h or d).');
    if ((match = text.match(EVERY))) {
      if (open) throw scriptError(line, 'Use plain lines inside a repeat.');
      const step = timeOf(match[1], line), from = timeOf(match[2], line), to = timeOf(match[3], line), action = parseAction(match[4], line, protocols);
      if (step < 1) throw scriptError(line, 'The interval must be greater than zero.');
      if (to < from) throw scriptError(line, '"to" must not be earlier than "from".');
      if ((to - from) / step > MAX_EVENTS) throw scriptError(line, 'More than 10,000 events. Use a longer interval.');
      for (let t = from; t <= to; t += step) items.push({ ...action, delay_ms: t, relative: true, line });
      previous = items.at(-1).delay_ms;
      return;
    }
    if (!(match = text.match(EVENT))) throw scriptError(line, 'Start each line with a time:  120.5 light 300');
    let time = timeOf(match[3], line);
    if (match[2]) time += previous;
    previous = time;
    if (open) {
      if (match[1]) throw scriptError(line, 'Repeats use elapsed time.');
      open.lines.push({ ...parseAction(match[4], line, protocols), offset_ms: time, line });
      return;
    }
    items.push({ ...parseAction(match[4], line, protocols), delay_ms: time, relative: !match[1], line });
  });
  if (open) throw scriptError(open.line, 'This repeat needs an "end" line.');

  // Blocks are identified by their order in the text. A block keeps its skipped
  // instances while it still has the same number of lines.
  const existing = blocksOf(plan);
  blocks.forEach((block, n) => {
    block.id = 'r' + (n + 1);
    const prior = existing[n];
    block.skip = prior && prior.lines.length === block.lines.length ? (prior.skip || []).filter(entry => entry[0] < block.count) : [];
    if (block.count * block.lines.length > MAX_EVENTS) throw scriptError(block.line, 'More than 10,000 events in this repeat.');
    for (let i = 0; i < block.count; i++) {
      block.lines.forEach((line, k) => {
        if (isSkipped(block, i, k)) return;
        items.push({ kind: line.kind, command: line.command, value: line.value, protocol: line.protocol, label: line.label,
          delay_ms: block.start_ms + i * block.period_ms + line.offset_ms, relative: true, line: line.line, repeat: { id: block.id, i, k } });
      });
    }
  });
  return { duration, items, blocks };
}

// Rules that need the whole script: inside the experiment, one event per slot, not empty.
function checkParsedScript(parsed, endMs, long) {
  const seen = new Map();
  for (const item of parsed.items) {
    if (item.delay_ms > endMs) throw scriptError(item.line, `Time is after the end of the experiment (${timeLabel(endMs, long)}).`);
    const slot = [item.relative, item.delay_ms, item.kind, item.command ?? ''].join('|');
    if (seen.has(slot)) throw scriptError(item.line, `Same time as line ${seen.get(slot) + 1}.`);
    seen.set(slot, item.line);
  }
  if (!parsed.items.length) throw scriptError(0, 'Keep at least one event.');
}

// Parsed items -> event objects for the plan. A line that did not change keeps its
// existing event object, so fields the script does not show (anything the controller
// or another tool stored on the event) survive a script edit. Sets item.event.
function eventsFromScript(plan, parsed) {
  const pool = new Map();
  for (const event of plan.events) {
    const key = eventKey(event);
    if (!pool.has(key)) pool.set(key, []);
    pool.get(key).push(event);
  }
  const events = parsed.items.map(item => {
    let event = pool.get(eventKey(item))?.shift();
    if (!event) {
      event = { kind: item.kind, delay_ms: item.delay_ms, relative: item.relative };
      if (item.kind === 'set') { event.command = item.command; event.value = item.value; }
      else event.protocol = item.protocol;
    }
    if (item.label) event.label = item.label; else delete event.label;
    if (item.repeat) event.repeat = item.repeat; else delete event.repeat;
    item.event = event;
    return event;
  });
  const blocks = parsed.blocks.map(normalizeBlock);
  return { events, blocks };
}

// True when the script describes exactly the draft it was read from.
function scriptMatchesPlan(plan, events, blocks) {
  return events.length === plan.events.length
    && JSON.stringify(blocks.map(normalizeBlock)) === JSON.stringify(blocksOf(plan).map(normalizeBlock))
    && events.map(eventSignature).sort().join() === plan.events.map(eventSignature).sort().join();
}

// ---- editor.js -------------------------------------------------------------
// The experiment editor: a graph and a script over one draft.
//
// The draft itself belongs to the host application (the plan text box, validation,
// duration, saving). This controller edits it only through the `host` object it is
// given, so there is one write path, one history and one renderer:
//
//   host.read() / host.write(plan)      the draft, through the host's own validation
//   host.useCheckpoint / useRenderer    host actions share this history and renderer
//   host.aroundLoad                     opening another experiment resets the editor
//
// Nothing here sends a request or commands hardware.

const SCRIPT_LINE_PX = 20;        // must match the script's CSS line height
const NUDGE_RUN_MS = 1200;        // key presses closer than this are one undo step
const SCRIPT_RUN_MS = 2000;       // typing pauses shorter than this are one undo step
const REPEAT_ANSWER_MS = 6000;    // how long "Change all / Only this" carries to the next arrow-key nudge

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const snap = ms => Math.round(ms / GRID_MS) * GRID_MS;

function installEditor(host) {
  const { $, G, S, text, svg, xy } = host;
  const document = $('plan-editor').ownerDocument;
  const planBox = $('plan-editor');
  const MOD = /Mac|iP/.test(navigator.platform) ? '⌘' : 'Ctrl';

  const totalMs = () => host.totalMs();
  const long = () => isLongPlan(totalMs());
  const label = ms => timeLabel(ms, long());
  const relativeBasis = () => G('basis').value === 'relative';
  const eligible = event => event.relative === relativeBasis() && (isLight(event) || event.kind === 'capture');

  // ---- layout -----------------------------------------------------------------
  // The chart replaces the host's timeline element so its old listeners go with it.
  const oldChart = G('timeline');
  const chart = oldChart.cloneNode(false);
  oldChart.replaceWith(chart);
  const frame = document.createElement('div');
  frame.className = 'ge';
  chart.before(frame);
  const bar = document.createElement('div');
  bar.className = 'ge-bar';
  const readout = document.createElement('span');
  readout.className = 'ge-readout';
  bar.append(readout);
  const status = G('message');
  const inspect = G('selection');
  frame.append(bar, chart, inspect, status);
  inspect.classList.add('ge-inspector');
  status.classList.add('ge-status');
  chart.setAttribute('tabindex', '0');
  chart.setAttribute('aria-label', 'Experiment timeline. Drag points to edit. Drag empty space to select. Arrow keys nudge by 0.1 seconds or one light unit; Shift for 1 second or ten units. Command C, V, D, Z. Alt-drag duplicates.');

  // ---- state ------------------------------------------------------------------
  const history = createHistory();
  let chosen = new Set();          // indices into plan.events
  let ownSelected = null;          // what this editor last told the host was selected
  let knownText = null;            // draft text the selection indices refer to
  let knownSignatures = [];
  let restoring = false;           // an undo/redo is reloading the draft
  let draft = 0;                   // increases whenever another draft is opened
  let lastNudge = null;
  let scriptRun = 0;               // time of the last script edit in the current typing run
  let clip = null;
  let cursor = null;               // paste position, ms
  let gesture = null;
  let geometry = null;
  let view = { start: 0, span: 1 };
  let yMax = LIGHT_MAX;
  let note = '';

  const say = message => { note = message || ''; };
  // Every user action runs here: a failure becomes a message, never a half-applied edit.
  function act(fn) {
    try { fn(); }
    catch (error) {
      say(error.message);
      try { draw(); } catch (_) { status.textContent = error.message; }
    }
  }
  const picked = plan => [...chosen].map(index => plan.events[index]).filter(Boolean);

  // ---- history ----------------------------------------------------------------
  function checkpoint() {
    scriptRun = 0;
    lastNudge = null;
    return history.checkpoint(planBox.value);
  }
  host.useCheckpoint(checkpoint);

  function restore(saved) {
    scriptRun = 0;
    const keep = readView();
    restoring = true;
    try { host.reload(JSON.parse(saved)); } finally { restoring = false; }
    setView(keep.start, keep.span);
    chosen.clear();
    lastNudge = null;
    render();
  }
  function travel(direction, done) {
    const saved = history[direction](planBox.value);
    if (saved === undefined) return;
    restore(saved);
    text('plan-result', done + ' · draft not saved.');
    say('');
    draw();
  }
  const undo = () => travel('undo', 'Undo applied');
  const redo = () => travel('redo', 'Redo applied');

  // Opening, creating or importing an experiment is a new draft: nothing of the old
  // one may be undone into it or pasted onto it by index.
  host.aroundLoad(
    () => {
      if (restoring) return;
      scriptRun = 0; history.clear(); chosen.clear(); ownSelected = null; cursor = null; lastNudge = null; pendingRepeat = null; draft++; say('');
    },
    () => { if (!restoring) knownText = null; },
  );

  // ---- selection --------------------------------------------------------------
  function reconcile(plan) {
    const now = planBox.value;
    if (now === knownText) return;
    const signatures = plan.events.map(eventSignature);
    if (knownText !== null) {
      const next = remapSelection(knownSignatures, chosen, signatures);
      const hostIndex = host.selectedEvent.get();
      const valid = hostIndex !== null && !!plan.events[hostIndex];
      const hostPicked = valid && hostIndex !== ownSelected;        // e.g. "Add light change" selected its new point
      chosen = hostPicked || (valid && !next.size && chosen.size === 1) ? new Set([hostIndex]) : next;
    }
    knownText = now;
    knownSignatures = signatures;
  }
  function adopt(plan, rows) {
    chosen = new Set(rows.map(event => plan.events.indexOf(event)).filter(index => index >= 0));
    knownText = planBox.value;
    knownSignatures = plan.events.map(eventSignature);
  }

  // ---- committing a change ----------------------------------------------------
  // `timed` means event times changed, so slots must be checked. `keyRun` marks a
  // keyboard nudge, the only edit allowed to reuse the last repeat answer unasked.
  function commit(plan, rows, timed, keyRun = false) {
    if (rows.some(event => blockOf(plan, event))) { askRepeat(plan, rows, timed, keyRun); return false; }
    return commitNow(plan, rows, timed);
  }
  function commitNow(plan, rows, timed) {
    if (timed) {
      if (hasOverlap(plan)) throw Error('Overlapping events. Choose another time.');
      const hit = findCollision(plan, rows);
      if (hit) throw Error(`Overlaps an existing ${hit.kind === 'capture' ? 'measurement' : 'light setting'} at ${label(hit.delay_ms)}.`);
    }
    const added = checkpoint();
    try { host.write(plan); }
    catch (error) { if (added) history.dropLast(); throw error; }
    adopt(plan, rows);
    return true;
  }

  // ---- view -------------------------------------------------------------------
  // The visible window lives in the host's "View starts at" / "Visible span" fields (hours).
  const readView = () => ({ start: Number(G('start').value) * 3600000, span: Number(G('span').value) * 3600000 });
  function setView(start, span) {
    const all = totalMs();
    span = clamp(span, Math.min(MIN_SPAN_MS, all), all);
    start = clamp(start, 0, all - span);
    G('span').value = span / 3600000;
    G('start').value = start / 3600000;
  }
  function zoom(factor, about) {
    const now = readView();
    const pivot = about ?? now.start + now.span / 2;
    const span = clamp(now.span * factor, Math.min(MIN_SPAN_MS, totalMs()), totalMs());
    setView(pivot - (pivot - now.start) * span / now.span, span);
    render();
  }
  const fit = () => { setView(0, totalMs()); render(); };

  // ---- clipboard and editing --------------------------------------------------
  function copy() {
    const plan = host.read(), rows = picked(plan);
    if (!rows.length) throw Error('Nothing selected.');
    clip = makeClip(plan, rows, draft);
    say(`Copied ${rows.length}.`);
    paint();
  }
  function paste(at) {
    if (!clip) throw Error('Nothing copied.');
    const plan = host.read(), end = totalMs();
    at = snap(clamp(at ?? cursor ?? readView().start, 0, end));
    if (at + clip.span > end) throw Error(`Does not fit: needs ${trimNumber(clip.span / 1000, 3)} s before the end.`);
    const rows = pasteRows(plan, clip, at, relativeBasis(), draft);
    plan.events.push(...rows);
    commit(plan, rows, true);
    say(`Pasted ${rows.length} at ${label(at)}.`);
    render();
  }
  function duplicate() {
    const rows = picked(host.read());
    if (!rows.length) throw Error('Nothing selected.');
    copy();
    paste(Math.max(...rows.map(event => event.delay_ms)) + Math.max(GRID_MS, snap(clip.span * .1)));
  }
  function remove() {
    const plan = host.read(), end = totalMs();
    const rows = picked(plan).filter(event => !isAnchored(event, end));
    if (!rows.length) {
      if (chosen.size) throw Error('The first and final light settings cannot be deleted.');
      return;
    }
    skipInstances(plan, rows);
    const drop = new Set(rows);
    plan.events = plan.events.filter(event => !drop.has(event));
    commitNow(plan, []);
    say(`Deleted ${rows.length}.`);
    render();
  }
  function nudge(dt, dv) {
    const plan = host.read(), end = totalMs(), rows = picked(plan);
    if (!rows.length) return;
    const movable = rows.filter(event => !isAnchored(event, end)), lights = rows.filter(isLight);
    if (dt) {
      if (!movable.length) throw Error('The first and final light settings keep their time.');
      dt = clamp(dt, -Math.min(...movable.map(event => event.delay_ms)), end - Math.max(...movable.map(event => event.delay_ms)));
      movable.forEach(event => { event.delay_ms += dt; });
    }
    if (dv) {
      if (!lights.length) return;
      dv = clamp(dv, -Math.min(...lights.map(event => +event.value)), LIGHT_MAX - Math.max(...lights.map(event => +event.value)));
      lights.forEach(event => { event.value = String(+event.value + dv); });
    }
    if (!dt && !dv) return;
    const key = [...chosen].join();
    const sameRun = !rows.some(event => blockOf(plan, event)) && lastNudge && lastNudge.key === key && performance.now() - lastNudge.at < NUDGE_RUN_MS && history.canUndo;
    if (sameRun) {
      if (dt && findCollision(plan, rows)) throw Error('Overlaps an existing event.');
      host.write(plan);
      adopt(plan, rows);
    } else commit(plan, rows, !!dt, true);
    lastNudge = { key: [...chosen].join(), at: performance.now() };
    say('');
    render();
  }

  // ---- drawing ----------------------------------------------------------------
  function draw(plan) {
    plan = plan || gesture?.preview || host.read();
    view = readView();
    if (!(view.span > 0)) return;
    geometry = measureChart(chart);
    yMax = lightCeiling(plan, G('max').value);
    host.setViewState({ start: view.start, span: view.span, yMax });
    const selection = gesture?.rows ? new Set(gesture.rows) : new Set(picked(plan));
    drawChart(chart, svg, { plan, view, endMs: totalMs(), long: long(), yMax, geometry, eligible, selection, cursor, box: gesture?.type === 'box' ? gesture.box || null : null });
    readout.textContent = readoutText(selection, gesture, long());
    status.textContent = note || (selection.size || gesture ? '' : `Drag to move · drag empty space to select · Alt-drag copies · arrows nudge 0.1 s · ${MOD}-scroll zooms`);
    buttons.undo.disabled = !history.canUndo;
    buttons.redo.disabled = !history.canRedo;
    buttons.copy.disabled = buttons.duplicate.disabled = buttons.remove.disabled = !selection.size;
    buttons.paste.disabled = !clip;
    buttons.fit.disabled = view.start < 1 && Math.abs(view.span - totalMs()) < 1;
  }
  function paint(plan) { try { draw(plan); } catch (error) { status.textContent = error.message; } }

  // ---- inspector: exact values for the selection --------------------------------
  function inspector(plan) {
    const rows = picked(plan), one = rows.length === 1 ? rows[0] : null, time = G('time'), value = G('value');
    inspect.hidden = !rows.length;
    ownSelected = one ? plan.events.indexOf(one) : null;
    host.selectedEvent.set(ownSelected);
    if (!rows.length) return;
    time.type = 'text'; time.inputMode = 'decimal'; time.removeAttribute('min'); time.removeAttribute('step');
    value.min = 0; value.max = LIGHT_MAX; value.step = 1;
    time.parentElement.firstChild.textContent = one ? (long() ? 'Time (h:mm:ss)' : 'Time (s)') : 'Shift time (s)';
    value.parentElement.firstChild.textContent = one ? 'Light level' : 'Set light level';
    time.value = one ? exactTime(one.delay_ms, long()) : '0';
    time.dataset.original = time.value;
    time.disabled = !!one && isAnchored(one, totalMs());
    const lights = rows.filter(isLight);
    value.disabled = !lights.length;
    value.value = one ? (one.value ?? '') : (lights.length && lights.every(event => event.value === lights[0].value) ? lights[0].value : '');
    value.placeholder = one ? '' : 'unchanged';
    value.dataset.original = value.value;
    G('delete').textContent = 'Delete';
    const chooser = $('graph-event-protocol');
    if (chooser) {
      chooser.parentElement.hidden = !(one && one.kind === 'capture');
      chooser.parentElement.firstChild.textContent = 'Protocol';
      chooser.replaceChildren();
      plan.protocols.forEach(protocol => chooser.add(new Option(protocol.id, protocol.id)));
      chooser.value = one?.protocol || '';
    }
    if (one && one.kind === 'capture') {
      const index = plan.protocols.findIndex(protocol => protocol.id === one.protocol);
      if (index >= 0) host.setProtocolIndex(index);
    }
  }
  // Only a field the user actually changed is applied: changing the level never moves the time.
  function applyInspector() {
    const plan = host.read(), rows = picked(plan), end = totalMs();
    if (!rows.length) throw Error('Nothing selected.');
    const time = G('time'), value = G('value');
    const timeChanged = time.value !== time.dataset.original && !time.disabled;
    const valueChanged = value.value !== value.dataset.original && value.value !== '';
    if (!timeChanged && !valueChanged) return;
    if (timeChanged) {
      if (rows.length === 1) {
        const ms = parseTime(time.value, long());
        if (ms < 0 || ms > end) throw Error('Time must fall within the experiment duration.');
        rows[0].delay_ms = ms;
      } else {
        const seconds = Number(time.value);
        if (!Number.isFinite(seconds)) throw Error('Enter the shift in seconds.');
        const movable = rows.filter(event => !isAnchored(event, end)), dt = Math.round(seconds * 1000);
        if (movable.some(event => event.delay_ms + dt < 0 || event.delay_ms + dt > end)) throw Error('Shift moves an event outside the experiment.');
        movable.forEach(event => { event.delay_ms += dt; });
      }
    }
    if (valueChanged) {
      const level = Number(value.value);
      if (!Number.isInteger(level) || level < 0 || level > LIGHT_MAX) throw Error(`Light level is a whole number 0–${LIGHT_MAX}.`);
      rows.filter(isLight).forEach(event => { event.value = String(level); });
    }
    commit(plan, rows, true);
    say('');
    render();
  }

  // ---- the single renderer ------------------------------------------------------
  // Host actions call render() by name and arrive here.
  function render() {
    act(() => {
      const plan = host.read();
      reconcile(plan);
      inspector(plan);
      draw(plan);
      syncScript(plan);
      host.renderPulses(plan);
    });
  }
  const hostRender = host.useRenderer(render);

  // ---- pointer: mouse, pen and touch share these handlers -------------------------
  const timeAt = position => clamp(view.start + (position.x - geometry.left) / geometry.width * view.span, 0, totalMs());

  chart.addEventListener('pointerdown', event => act(() => {
    if (event.button !== 0 || !geometry) return;
    event.preventDefault();
    chart.focus({ preventScroll: true });
    say('');
    const position = xy(event, chart), hit = event.target.closest?.('[data-event]');
    if (hit) {
      const index = Number(hit.dataset.event);
      if (event.shiftKey) { chosen.has(index) ? chosen.delete(index) : chosen.add(index); render(); return; }
      const wasChosen = chosen.has(index);
      if (!wasChosen) chosen = new Set([index]);
      gesture = { type: 'move', base: host.read(), indices: [...chosen], hit: index, wasChosen, start: position, moved: false, dt: 0, dv: 0 };
    } else if (event.metaKey || position.y > geometry.axis) gesture = { type: 'pan', start: position, view: readView() };
    else gesture = { type: 'box', start: position, keep: new Set(event.shiftKey ? chosen : []), moved: false };
    try { chart.setPointerCapture(event.pointerId); } catch (_) { /* synthetic pointer */ }
    render();
  }));

  chart.addEventListener('pointermove', event => act(() => {
    const g = gesture;
    if (!g) return;
    const position = xy(event, chart), dx = position.x - g.start.x, dy = position.y - g.start.y;
    if (g.type === 'pan') { setView(g.view.start - dx / geometry.width * g.view.span, g.view.span); paint(); return; }
    if (!g.moved && Math.hypot(dx, dy) < 4) return;
    g.moved = true;
    if (g.type === 'box') {
      const x0 = Math.min(g.start.x, position.x), x1 = Math.max(g.start.x, position.x), y0 = Math.min(g.start.y, position.y), y1 = Math.max(g.start.y, position.y);
      g.box = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
      const plan = host.read();
      chosen = new Set(g.keep);
      plan.events.forEach((candidate, index) => {
        if (!eligible(candidate)) return;
        const at = eventPosition(candidate, geometry, view, yMax);
        if (at.x >= x0 && at.x <= x1 && at.y >= y0 && at.y <= y1 && at.x >= geometry.left && at.x <= geometry.right) chosen.add(index);
      });
      paint(plan);
      return;
    }
    // Move. The offset snaps to the grid; every event keeps its own sub-grid timing.
    const end = totalMs(), plan = structuredClone(g.base), source = g.indices.map(index => plan.events[index]);
    g.copying = event.altKey;
    let rows = source;
    if (g.copying) { rows = source.map(plainCopy); plan.events.push(...rows); }
    let dt = snap(dx / geometry.width * view.span), dv = Math.round(-dy / (geometry.bottom - geometry.top) * yMax);
    if (event.shiftKey) { if (Math.abs(dx) >= Math.abs(dy)) dv = 0; else dt = 0; }
    const movable = rows.filter(candidate => g.copying || !isAnchored(candidate, end)), lights = rows.filter(isLight);
    dt = movable.length ? clamp(dt, -Math.min(...movable.map(e => e.delay_ms)), end - Math.max(...movable.map(e => e.delay_ms))) : 0;
    dv = lights.length ? clamp(dv, -Math.min(...lights.map(e => +e.value)), LIGHT_MAX - Math.max(...lights.map(e => +e.value))) : 0;
    movable.forEach(e => { e.delay_ms += dt; });
    lights.forEach(e => { e.value = String(+e.value + dv); });
    Object.assign(g, { preview: plan, rows, dt, dv });
    paint(plan);      // nothing is written until the pointer is released
  }));

  function release(cancelled) {
    const g = gesture;
    gesture = null;
    if (!g) return;
    act(() => {
      if (g.type === 'move') {
        if (g.moved && !cancelled && (g.dt || g.dv)) {
          if (g.copying && !g.dt) throw Error('Drag sideways to place the copy.');
          commit(g.preview, g.rows, !!g.dt);
          if (g.copying) say(`Copied ${g.rows.length} to ${label(Math.min(...g.rows.map(e => e.delay_ms)))}.`);
        } else if (!g.moved && g.wasChosen && chosen.size > 1) chosen = new Set([g.hit]);
      } else if (g.type === 'box' && !g.moved && !cancelled) {
        chosen = new Set(g.keep);
        cursor = snap(timeAt(g.start));
      }
    });
    render();
  }
  chart.addEventListener('pointerup', () => release(false));
  chart.addEventListener('pointercancel', () => release(true));

  chart.addEventListener('wheel', event => {
    if (!geometry) return;
    const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY);
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      zoom(Math.exp(clamp(event.deltaY, -60, 60) * .01), timeAt(xy(event, chart)));
    } else if (horizontal || event.shiftKey) {
      event.preventDefault();
      const now = readView();
      setView(now.start + (horizontal ? event.deltaX : event.deltaY) / geometry.width * now.span, now.span);
      render();
    }   // a plain vertical wheel scrolls the page
  }, { passive: false });
  chart.addEventListener('dblclick', event => { if (!event.target.closest?.('[data-event]')) act(fit); });

  // ---- keyboard -----------------------------------------------------------------
  chart.addEventListener('keydown', event => {
    const key = event.key.toLowerCase(), mod = event.metaKey || event.ctrlKey;
    let fn = null;
    if (mod && key === 'z') fn = event.shiftKey ? redo : undo;
    else if (mod && key === 'y') fn = redo;
    else if (mod && key === 'c') fn = copy;
    else if (mod && key === 'x') fn = () => { copy(); remove(); };
    else if (mod && key === 'v') fn = () => paste();
    else if (mod && key === 'd') fn = duplicate;
    else if (mod && key === 'a') fn = () => { chosen = new Set(host.read().events.map((e, i) => eligible(e) ? i : -1).filter(i => i >= 0)); render(); };
    else if (mod) return;
    else if (key === 'delete' || key === 'backspace') fn = remove;
    else if (key === 'arrowleft' || key === 'arrowright') fn = () => nudge((key === 'arrowleft' ? -1 : 1) * (event.shiftKey ? 1000 : GRID_MS), 0);
    else if (key === 'arrowup' || key === 'arrowdown') fn = () => nudge(0, (key === 'arrowdown' ? -1 : 1) * (event.shiftKey ? 10 : 1));
    else if (key === 'escape') fn = () => {
      if (gesture) gesture = null;
      else if (chosen.size) chosen.clear();
      else if (frame.classList.contains('ge-expanded')) expand();
      say('');
      render();
    };
    else if (key === 'f') fn = fit;
    else if (key === '=' || key === '+') fn = () => zoom(1 / 1.5);
    else if (key === '-') fn = () => zoom(1.5);
    if (fn) { event.preventDefault(); act(fn); }
  });
  // Exact values apply when the field is committed (Enter or leaving it). An invalid
  // value is refused with a message and the draft is untouched.
  for (const field of [G('time'), G('value')]) {
    field.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); act(applyInspector); } });
    field.addEventListener('change', () => act(applyInspector));
  }

  // ---- toolbar ------------------------------------------------------------------
  const buttons = {};
  function tool(key, caption, title, fn, startsGroup) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ge-button';
    button.textContent = caption;
    button.title = title;
    if (startsGroup) button.dataset.group = 'start';
    button.onclick = () => { act(fn); chart.focus({ preventScroll: true }); };
    bar.append(button);
    buttons[key] = button;
  }
  function expand() {
    const on = frame.classList.toggle('ge-expanded');
    document.documentElement.classList.toggle('ge-lock', on);
    buttons.expand.textContent = on ? 'Collapse' : 'Expand';
    buttons.expand.title = on ? 'Return to the page (Esc)' : 'Use the full window';
    requestAnimationFrame(() => { paint(); chart.focus({ preventScroll: true }); });
  }
  tool('undo', 'Undo', `Undo (${MOD}Z)`, undo);
  tool('redo', 'Redo', `Redo (⇧${MOD}Z)`, redo);
  tool('copy', 'Copy', `Copy selection (${MOD}C)`, copy, true);
  tool('paste', 'Paste', `Paste at the cursor (${MOD}V)`, () => paste());
  tool('duplicate', 'Duplicate', `Duplicate after the selection (${MOD}D)`, duplicate);
  tool('remove', 'Delete', 'Delete selection (⌫)', remove);
  tool('out', '−', 'Zoom out (−)', () => zoom(1.5), true);
  tool('in', '+', 'Zoom in (+)', () => zoom(1 / 1.5));
  tool('fit', 'Fit', 'Show the whole experiment (F)', fit);
  tool('expand', 'Expand', 'Use the full window', expand, true);
  G('apply').onclick = () => act(applyInspector);
  G('apply').hidden = true;                  // the fields apply themselves; kept for scripts and tests
  G('delete').onclick = () => act(remove);

  // ---- repeat blocks: Change all / Only this --------------------------------------
  const ask = document.createElement('div');
  ask.className = 'ge-ask';
  ask.hidden = true;
  status.before(ask);
  let pendingRepeat = null;
  let repeatAnswer = null;

  function resolveRepeat(mode) {
    const job = pendingRepeat;
    pendingRepeat = null;
    ask.hidden = true;
    chart.focus({ preventScroll: true });      // keyboard shortcuts keep working after the answer
    if (!job || mode === 'cancel') { render(); return; }
    act(() => {
      if (job.baseText !== planBox.value) throw Error('The draft changed. Select the event again.');
      repeatAnswer = { key: job.key, mode, at: performance.now() };
      const rows = mode === 'one' ? detachInstances(job.plan, job.rows) : changeAllInstances(job.plan, job.rows, job.deltas, totalMs());
      commitNow(job.plan, rows, job.timed);
      say(mode === 'one' ? 'Changed this one only; it no longer follows the repeat.' : 'Changed every repeat.');
      render();
    });
  }
  // The edit is held, not written, until the question is answered.
  function askRepeat(plan, rows, timed, keyRun) {
    const key = repeatSelectionKey(rows);
    pendingRepeat = { plan, rows, timed, key, deltas: repeatDeltas(host.read(), plan, rows), baseText: planBox.value };
    if (keyRun && repeatAnswer && repeatAnswer.key === key && performance.now() - repeatAnswer.at < REPEAT_ANSWER_MS) { resolveRepeat(repeatAnswer.mode); return; }
    const block = blockOf(plan, rows.find(event => blockOf(plan, event)));
    ask.replaceChildren();
    const question = document.createElement('span');
    question.textContent = `Part of a repeat ×${block.count}.`;
    ask.append(question);
    for (const [mode, caption] of [['all', 'Change all'], ['one', 'Only this'], ['cancel', 'Cancel']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ge-button';
      button.textContent = caption;
      button.onclick = () => resolveRepeat(mode);
      ask.append(button);
    }
    ask.hidden = false;
    ask.querySelector('button').focus();
  }

  // ---- script panel ---------------------------------------------------------------
  const panel = document.createElement('div');
  panel.className = 'ge-script';
  const head = document.createElement('div');
  head.className = 'ge-script-head';
  const title = document.createElement('span');
  title.textContent = 'Script';
  const scriptState = document.createElement('span');
  scriptState.className = 'ge-script-state';
  const insert = document.createElement('select');
  insert.className = 'ge-insert';
  insert.setAttribute('aria-label', 'Insert a preset at the cursor');
  insert.add(new Option('Insert…', ''));
  for (const [value, caption] of PRESET_CHOICES) insert.add(new Option(caption, value));
  head.append(title, scriptState, insert);
  const body = document.createElement('div');
  body.className = 'ge-script-body';
  const gutter = document.createElement('div');
  gutter.className = 'ge-gutter';
  gutter.setAttribute('aria-hidden', 'true');
  const code = document.createElement('textarea');
  code.className = 'ge-code';
  code.rows = 10;
  code.spellcheck = false;
  for (const [name, value] of [['autocapitalize', 'off'], ['autocomplete', 'off'], ['wrap', 'off'], ['aria-label', 'Experiment script. One event per line: time, then light, measure or set. repeat blocks end with end.']]) code.setAttribute(name, value);
  body.append(gutter, code);
  panel.append(head, body);
  inspect.after(panel);

  let lineEvents = [];             // per script line, the indices of the events it stands for
  let mappedText = null;           // script text those indices were computed for
  let scriptPlanText = null;       // draft text the script currently represents
  let scriptProblem = null;        // { line, message } while the script is invalid
  let scriptTimer = null;
  let fromScript = false;          // a render caused by the script must not rewrite the script
  let gutterLines = 0;

  function paintScript() {
    const count = code.value.split('\n').length;
    if (count !== gutterLines) {
      gutter.replaceChildren();
      for (let i = 0; i < count; i++) { const number = document.createElement('div'); number.textContent = i + 1; gutter.append(number); }
      gutterLines = count;
    }
    const live = code.value === mappedText;
    [...gutter.children].forEach((number, i) => {
      number.className = scriptProblem && scriptProblem.line === i ? 'ge-ln-error' : live && (lineEvents[i] || []).some(index => chosen.has(index)) ? 'ge-ln-on' : '';
    });
    gutter.scrollTop = code.scrollTop;
    scriptState.textContent = scriptProblem ? `Line ${scriptProblem.line + 1}: ${scriptProblem.message}` : '';
    scriptState.classList.toggle('ge-script-error', !!scriptProblem);
    panel.classList.toggle('ge-script-invalid', !!scriptProblem);
  }
  function showScript(plan) {
    const composed = composeScript(plan, { totalMs: totalMs(), long: long() });
    code.value = mappedText = composed.text;
    lineEvents = composed.lineEvents;
    scriptPlanText = planBox.value;
    scriptProblem = null;
  }
  function syncScript(plan) {
    const focused = document.activeElement === code;
    if (fromScript) scriptPlanText = planBox.value;
    else if (planBox.value !== scriptPlanText || (!focused && !scriptProblem && code.value !== mappedText)) showScript(plan);
    paintScript();
    if (!focused && chosen.size && code.value === mappedText) {
      const line = lineEvents.findIndex(list => (list || []).some(index => chosen.has(index)));
      if (line >= 0) {
        const top = line * SCRIPT_LINE_PX;
        if (top < code.scrollTop || top > code.scrollTop + code.clientHeight - SCRIPT_LINE_PX * 2) code.scrollTop = Math.max(0, top - SCRIPT_LINE_PX * 2);
        gutter.scrollTop = code.scrollTop;
      }
    }
  }
  function caretLines() {
    const value = code.value;
    return [value.slice(0, code.selectionStart).split('\n').length - 1, value.slice(0, code.selectionEnd).split('\n').length - 1];
  }
  function showDuration(ms) {
    const shown = host.planTiming.display(ms);
    S('days').value = shown.value;
    $('duration-unit').value = shown.unit;
  }
  function renderFromScript() { fromScript = true; try { render(); } finally { fromScript = false; } }

  // Script -> draft. An invalid script is reported on its line and changes nothing.
  function applyScript() {
    clearTimeout(scriptTimer);
    scriptTimer = null;
    const source = code.value;
    let plan, parsed;
    try {
      plan = host.read();
      parsed = parseScript(source, plan, { long: long() });
      checkParsedScript(parsed, parsed.duration ?? totalMs(), long());
    } catch (error) {
      scriptProblem = { line: error.line ?? 0, message: error.message };
      paintScript();
      return;
    }
    const { events, blocks } = eventsFromScript(plan, parsed);
    const before = totalMs(), newDuration = parsed.duration !== null && parsed.duration !== before;
    if (newDuration || !scriptMatchesPlan(plan, events, blocks)) {
      const now = performance.now(), sameRun = scriptRun > 0 && now - scriptRun < SCRIPT_RUN_MS && history.canUndo;
      const added = sameRun ? false : checkpoint();
      scriptRun = now;
      try {
        if (newDuration) { showDuration(parsed.duration); plan.studio = { ...plan.studio, duration_ms: parsed.duration }; }
        plan.events = events;
        plan.studio = { ...plan.studio, repeats: blocks };
        if (!blocks.length) delete plan.studio.repeats;
        host.write(plan);
        if (newDuration) S('last').value = host.dayCount();
      } catch (error) {
        if (newDuration) showDuration(before);
        if (added) history.dropLast();
        scriptProblem = { line: 0, message: error.message };
        paintScript();
        return;
      }
    }
    scriptProblem = null;
    lineEvents = [];
    for (const item of parsed.items) {
      const index = plan.events.indexOf(item.event);
      if (index >= 0) (lineEvents[item.line] = lineEvents[item.line] || []).push(index);
    }
    mappedText = source;
    const [first, last] = caretLines(), rows = [];
    for (let line = first; line <= last; line++) for (const index of lineEvents[line] || []) rows.push(plan.events[index]);
    adopt(plan, rows);
    renderFromScript();
  }
  // The caret selects in the graph: a plain line selects its event, a repeat line every instance.
  function caretSelect() {
    if (scriptProblem || code.value !== mappedText) return;
    const [first, last] = caretLines(), next = new Set();
    for (let line = first; line <= last; line++) for (const index of lineEvents[line] || []) next.add(index);
    if (next.size === chosen.size && [...next].every(index => chosen.has(index))) return;
    chosen = next;
    renderFromScript();
  }
  // Presets write ordinary events and protocols into this draft, at the cursor.
  function insertPreset(type) {
    const at = snap(clamp(cursor ?? 0, 0, totalMs()));
    if (type === 'repeat') {
      code.value = code.value.replace(/\s+$/, '') + '\n\n' + repeatTemplate(totalMs(), at, long());
      code.focus();
      applyScript();
      return;
    }
    const plan = host.read(), end = totalMs();
    const preset = host.presets.preset({ type, ...PRESET_DEFAULTS });
    const rows = presetRows(plan, preset, at, relativeBasis());
    const needed = at + preset.studio.duration_ms;
    if (needed > end) { showDuration(needed); plan.studio = { ...plan.studio, duration_ms: needed }; }
    plan.events.push(...rows);
    try { commitNow(plan, rows, false); }
    catch (error) { showDuration(end); throw error; }
    S('last').value = host.dayCount();
    setView(0, totalMs());
    say(`Inserted ${rows.length} events at ${label(at)}. Edit them here or in the graph.`);
    render();
  }

  insert.onchange = () => { const type = insert.value; insert.value = ''; if (type) act(() => insertPreset(type)); };
  code.addEventListener('input', () => { paintScript(); clearTimeout(scriptTimer); scriptTimer = setTimeout(() => act(applyScript), 300); });
  code.addEventListener('scroll', () => { gutter.scrollTop = code.scrollTop; });
  for (const type of ['click', 'keyup', 'select']) {
    code.addEventListener(type, event => {
      if (type === 'keyup' && !/^(Arrow|Page)|^(Home|End)$/.test(event.key)) return;
      act(caretSelect);
    });
  }
  code.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); chart.focus({ preventScroll: true }); }
    else if (event.key === 'Tab') { event.preventDefault(); code.setRangeText('  ', code.selectionStart, code.selectionEnd, 'end'); }
  });
  code.addEventListener('blur', () => {
    if (scriptTimer) act(applyScript);
    scriptRun = 0;
    if (!scriptProblem) act(() => { showScript(host.read()); paintScript(); });
  });

  // ---- every host entry point uses this renderer ------------------------------------
  // The host finishes building its page after this editor installs; arrange once it has.
  queueMicrotask(() => { try { arrangeEditorPage({ $, G, frame, bar, readout }); paint(); } catch (error) { console.error('Editor layout unavailable', error); } });
  planBox.removeEventListener('input', hostRender);
  planBox.addEventListener('input', () => render());
  for (const id of ['max', 'span', 'start']) G(id).oninput = () => render();
  G('basis').onchange = () => { chosen.clear(); render(); };
  new ResizeObserver(() => { if (chart.getBoundingClientRect().width) paint(); }).observe(chart);
  render();
}
return { install: installEditor };
})();
// </editor-bundle>
// The editor works on the draft only through this interface. The three hooks are the
// only places it takes part in host behaviour: one history, one renderer, and a reset
// whenever another experiment is loaded.
try{DepiEditor.install({
 $,G,S,text,svg,xy,
 read:()=>read(),write:p=>write(p),renderPulses:p=>renderPulses(p),
 totalMs:()=>durationMsInput(),dayCount:()=>dayCount(),
 planTiming:PlanTiming,presets:ExperimentParts,
 reload:plan=>loadEditor(plan,editID,editVersion,false),
 selectedEvent:{get:()=>selectedEvent,set:value=>{selectedEvent=value;}},
 setProtocolIndex:index=>{protocolIndex=index;},
 setViewState:view=>{drawStart=view.start;drawSpan=view.span;axisMs=1000;yMax=view.yMax;},
 useCheckpoint:fn=>{checkpoint=fn;},
 useRenderer:fn=>{const prior=render;render=fn;return prior;},
 aroundLoad:(before,after)=>{const prior=loadEditor;loadEditor=function(...args){before();const result=prior(...args);after();return result;};},
});}catch(error){console.error('Graph editor unavailable',error);}

// Restore saved duration and component fields with each draft.
const loadComponents=loadEditor;loadEditor=function(...args){loadComponents(...args);const c=args[0].studio?.light_components;if(c){$('component-shape').value=c.shape;for(const k of ['dawn','photoperiod','peak','night','step'])$('component-'+k).value=c[k];$('component-layers').replaceChildren();(c.layers||[]).forEach(addLayer);$('component-hold').checked=!!c.holdMeasurements;}else{$('component-layers').replaceChildren();}if(typeof selectEditorTab==='function')selectEditorTab(activeEditorTab||'light');};
G('undo').onclick=()=>{if(history.length){const p=JSON.parse(history.pop());loadEditor(p,editID,editVersion,false);selectedEvent=null;render();text('plan-result','Undo applied · draft not saved.');}};


})();
// Refresh completed measurement images without changing camera acquisition.
setInterval(()=>{if(currentPage==='overview'&&!document.hidden&&!$('photo-dialog').open)loadPhotos(true).catch(()=>{});},15000);

function measurementFields(type){const paired=['dark-reference','light-adapted'].includes(type);return {NumberLoops:paired?'2':'1',FramesPerLoop:paired?'10,10':'10',MeasuringLight:type==='background'?'0':'1',SaturationFlash:paired?'0,1':type==='saturation'?'1':'0',AuxFastSwitch:'0',Exposure:'50us',FrameInterval:'95ms',ActinicShutter:'1'};}
// One operator workspace, with measured results separate from experiment drafts.
const cameraGrid=document.querySelector('#overview .overview-grid');cameraGrid.classList.add('camera-measurement-grid');cameraGrid.append($('measurement-average'));
const runStrip=document.createElement('div');runStrip.className='measurement-status';runStrip.innerHTML='<div><span>Chamber</span><strong id="workspace-run-state">Connecting…</strong></div><div><span>Last completed measurement</span><strong id="workspace-last">No completed measurement</strong></div><div><span>Next measurement / start</span><strong id="workspace-next">Not scheduled</strong></div>';$('overview').prepend(runStrip);
const burst=document.createElement('button');burst.id='measuring-burst';burst.className='button primary';burst.textContent='Take measuring burst';burst.disabled=true;burst.title='Ten measuring-only frames, 50 µs exposure, averaged. No saturation pulse.';document.querySelector('.camera-footer').prepend(burst);
const burstInfo=document.createElement('p');burstInfo.className='help camera-burst-note';burstInfo.textContent='Measuring burst: 10 frames · 50 µs exposure · averaged image. This does not establish dark adaptation.';document.querySelector('.camera-footer').after(burstInfo);
let burstPending=false;
burst.onclick=async()=>{if(burstPending)return;burstPending=true;updateWorkspaceState();try{const response=await api('/api/capture',{operation:'measuring_burst',request_id:crypto.randomUUID()});toast('Measuring burst accepted. The completed average will appear beside the camera.');await refreshStatus();}catch(e){toast(e.message);}finally{burstPending=false;updateWorkspaceState();}};
function updateWorkspaceState(){
 if(!$('measuring-burst'))return;
 burst.disabled=burstPending||commandPending||!connected()||account?.role==='viewer'||!account||!!state?.active||!state?.measuring_burst_ready;
 text('workspace-run-state',!connected()?'Disconnected':state?.active?state.active.name+' · day '+(Math.floor(((state.server_time||0)-(state.progress?.started||state.server_time))/86400)+1)+' · '+(state.progress?.completed||0)+'/'+(state.progress?.total||0):connected()?(state?.event_pending?'Busy':state?.live?.running?'Idle · live view in use':'Idle')+(state?.commissioned===false?' · not commissioned':''):'Disconnected');
 const next=state?.progress?.next_measurement,scheduled=workspace?.schedules?.filter(s=>s.state==='queued'&&s.due>=(state?.server_time||0)).sort((a,b)=>a.due-b.due)[0];
 updateChamberTitle();
 if(!connected()&&!state)text('workspace-last','Unavailable while disconnected');
 text('workspace-next',!connected()?'Unavailable while disconnected':next?'Capture · '+new Date(next.due*1000).toLocaleString():scheduled?'Start · '+new Date(scheduled.due*1000).toLocaleString():'Not scheduled');
}
const oldPermissions=applyControlPermissions;applyControlPermissions=function(){oldPermissions();updateWorkspaceState();};
function prepareWorkspace(){if(!$('plan-editor').value){loadEditor(starterPlan(),null,null,false);text('plan-result','Draft');}loadFluorescence().catch(e=>text('science-note',e.message));}
document.querySelector('.experiment-workbench .panel-heading h2').textContent='Editing draft';
$('experiment-editor').querySelector('summary').textContent='Light and measurement editor';
const graphHelp=document.createElement('p');graphHelp.className='help';graphHelp.textContent='Drag green points to change light level and time. Drag amber markers to move measurements. Click a point for exact values.';$('graph-timeline').before(graphHelp);
const typeLabel=document.createElement('label');typeLabel.textContent='Measurement';const typeSelect=document.createElement('select');typeSelect.id='graph-measurement-type';typeSelect.setAttribute('aria-label','New measurement type');for(const [id,label] of [['measuring','Measuring only'],['saturation','Saturation measurement'],['dark-reference','Dark reference: F₀ + Fm'],['light-adapted','Light adapted: Fs + Fm′'],['background','Camera background']])typeSelect.add(new Option(label,id));typeLabel.append(typeSelect);$('graph-capture').before(typeLabel);
const protocolChoice=document.createElement('label');protocolChoice.textContent='Selected measurement protocol';const protocolSelect=document.createElement('select');protocolSelect.id='graph-event-protocol';protocolSelect.setAttribute('aria-label','Selected measurement protocol');protocolChoice.append(protocolSelect);$('graph-selection').prepend(protocolChoice);protocolChoice.hidden=true;
const science=document.createElement('section');science.id='fluorescence-results';science.className='panel science-panel';science.innerHTML=`<div class="panel-heading"><h2>Fluorescence measurements</h2><label>Completed run <select id="science-run" aria-label="Fluorescence run"></select></label></div><div class="detail-body"><p id="science-note" class="help">Loading measured results…</p><div id="fluorescence-primary" class="science-grid"></div><h3>Calculated results</h3><div id="fluorescence-derived" class="science-grid derived-grid"></div><details id="science-detail"><summary>Selected measurement: image, graph, and provenance</summary><div class="science-detail-grid"><div><h3 id="science-detail-title"></h3><img id="science-detail-image" alt="Selected fluorescence measurement"><div id="science-detail-navigation" class="science-detail-navigation" aria-label="Measurement image navigation" hidden><button id="science-detail-previous" class="science-nav-button" type="button" aria-label="Previous measurement image">←</button><span id="science-detail-position" aria-live="polite"></span><button id="science-detail-next" class="science-nav-button" type="button" aria-label="Next measurement image">→</button></div><p id="science-segmentation-key" class="segmentation-key" hidden><span class="detected-edge"></span>Detected region edge <span class="measurement-edge"></span>8 px measurement inset</p><p id="science-detail-scale" class="help"></p><a id="science-detail-download" class="text-button" download>Download measured TIFF</a></div><div><svg id="science-detail-chart" viewBox="0 0 600 250" role="img" aria-label="Selected fluorescence time series"></svg><p id="science-detail-method" class="help"></p><table><thead><tr><th>Measurement</th><th id="science-detail-scope">Value</th></tr></thead><tbody id="science-detail-values"></tbody></table><div id="science-leaf-section" hidden><h3>Regions</h3><p id="science-region-note" class="help"></p><label><input id="science-show-all-regions" type="checkbox"> Show all regions</label><table><thead><tr><th>Region</th><th>Mean</th><th>SD</th><th>Pixels</th></tr></thead><tbody id="science-leaf-values"></tbody></table></div></div></div></details></div>`;
document.querySelector('.experiment-workbench').after(science);
// Retain legacy plan bindings internally without exposing the retired library.
bind('reload-schedules',loadWorkspace);
let fluorescenceData=[],scienceSelection=null,scienceMetric='NPQ',sciencePointIndex=null,scienceSignature='',scienceLoading=false;
const metricOrder=['F0','Fm','Fm_prime','Fs','Fv','Fv_Fm','NPQ','PhiII'];
const metricLabels={F0:'F₀',Fm:'Fm',Fm_prime:'Fm′',Fs:'Fs',Fv:'Fv',Fv_Fm:'Fv/Fm',NPQ:'NPQ',PhiII:'ΦII'};
// Which pixels each stored number averages (depibeans/fluorescence.py). One vocabulary for tiles, detail and export.
const metricScope=key=>['Fv','Fv_Fm','NPQ','PhiII'].includes(key)?'signal_mask':'whole_frame';
const scopeWords={whole_frame:'Whole frame',signal_mask:'Plant pixels (signal mask)',region_inset:'Automatic region, inset'};
const metricStatistic=key=>['Fv_Fm','NPQ','PhiII'].includes(key)?'mean_of_per_pixel_ratios':'mean_of_pixels';
// Small regions can be included in the table; size alone does not determine validity.
const REGION_TABLE_FLOOR=0.02;
function scienceSvg(el,name,attrs,content){const node=document.createElementNS('http://www.w3.org/2000/svg',name);for(const [k,v]of Object.entries(attrs))node.setAttribute(k,v);if(content!==undefined)node.textContent=content;el.append(node);return node;}
function drawScienceChart(el,points,small=false,selectedPoint=null){
 el.replaceChildren();const rows=points.filter(p=>Number.isFinite(p.value));if(!rows.length)return;
 const w=600,h=250,pad=small?24:45;el.setAttribute('viewBox',`0 0 ${w} ${h}`);
 const maxX=Math.max(1,...rows.map(p=>p.time_s||0)),lo=Math.min(0,...rows.map(p=>p.value)),hi=Math.max(.001,...rows.map(p=>p.value)),range=Math.max(.001,hi-lo)*1.12;
 const x=p=>pad+(p.time_s||0)/maxX*(w-2*pad),y=p=>h-pad-(p.value-lo)/range*(h-2*pad);
 scienceSvg(el,'line',{x1:pad,x2:w-pad,y1:h-pad,y2:h-pad,stroke:'#bccbc2'});
 if(rows.length>1)scienceSvg(el,'polyline',{points:rows.map(p=>`${x(p)},${y(p)}`).join(' '),fill:'none',stroke:'#236c50','stroke-width':3});
 for(const p of rows){if(!small&&p===selectedPoint)scienceSvg(el,'circle',{cx:x(p),cy:y(p),r:14,fill:'#236c50','fill-opacity':.18,stroke:'#236c50','stroke-opacity':.45,'stroke-width':2,'pointer-events':'none',class:'science-chart-selection'});const c=scienceSvg(el,'circle',{cx:x(p),cy:y(p),r:small?5:6,fill:'#236c50',class:'science-chart-point',...(small?{}:{tabindex:0,role:'button'}),...(p===selectedPoint?{'aria-current':'true'}:{}),'aria-label':`${p.label||p.time_s+' seconds'}: ${p.value.toFixed(3)}`});scienceSvg(c,'title',{},`${p.label||p.time_s+' s'}: ${p.value.toFixed(3)}`);const select=()=>showScienceDetail(scienceMetric,p);c.onclick=select;c.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}};}
 if(!small){scienceSvg(el,'text',{x:pad,y:18,'font-size':13,fill:'#596a60'},hi.toFixed(3));scienceSvg(el,'text',{x:pad,y:h-8,'font-size':13,fill:'#596a60'},rows.length===1?'Reference':'0 s');if(rows.length>1)scienceSvg(el,'text',{x:w-pad,y:h-8,'text-anchor':'end','font-size':13,fill:'#596a60'},maxX.toFixed(1)+' s');}
}
function selectedScience(){return fluorescenceData.find(d=>d.id===scienceSelection);}
const fluorescenceColors=[[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]];
function fluorescenceColor(value){const scaled=Math.max(0,Math.min(1,value))*(fluorescenceColors.length-1),lower=Math.floor(scaled),upper=Math.min(fluorescenceColors.length-1,lower+1),mix=scaled-lower;return fluorescenceColors[lower].map((channel,index)=>Math.round(channel+(fluorescenceColors[upper][index]-channel)*mix));}
const fluorescencePalette=(()=>{const palette=new Uint8ClampedArray(256*3);for(let value=0;value<256;value++){const color=fluorescenceColor(value/255),offset=value*3;palette[offset]=color[0];palette[offset+1]=color[1];palette[offset+2]=color[2];}return palette;})();
function segmentationPreview(id){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src='/api/frame?id='+id;});}
function renderFluorescenceHeatmap(image,label,visible,segmentation){
 let canvas=$('science-detail-heatmap');
 if(!canvas){canvas=document.createElement('canvas');canvas.id='science-detail-heatmap';canvas.className='science-detail-heatmap';canvas.setAttribute('role','img');image.after(canvas);}
 image.hidden=true;canvas.hidden=!visible;canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);if(!visible)return;
 const segmented=!!(segmentation?.detected_image_id&&segmentation?.measurement_image_id);canvas.setAttribute('aria-label',label+' false-color heat map'+(segmented?' with numbered automatic regions':''));const token=String(Date.now()+Math.random());canvas.dataset.paintToken=token;
 const paint=async()=>{if(!image.naturalWidth||!image.naturalHeight)return;canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0);const frame=context.getImageData(0,0,canvas.width,canvas.height),pixels=frame.data;let alreadyColor=false;for(let i=0;i<pixels.length;i+=Math.max(4,Math.floor(pixels.length/4000/4)*4))if(pixels[i]!==pixels[i+1]||pixels[i+1]!==pixels[i+2]){alreadyColor=true;break;}if(!alreadyColor){for(let i=0;i<pixels.length;i+=4){if(pixels[i]===0&&pixels[i+1]===0&&pixels[i+2]===0)continue;const offset=pixels[i]*3;pixels[i]=fluorescencePalette[offset];pixels[i+1]=fluorescencePalette[offset+1];pixels[i+2]=fluorescencePalette[offset+2];}context.putImageData(frame,0,0);}if(!segmented)return;try{const [detected,measured]=await Promise.all([segmentationPreview(segmentation.detected_image_id),segmentationPreview(segmentation.measurement_image_id)]);if(canvas.dataset.paintToken!==token)return;const maskData=source=>{const buffer=document.createElement('canvas');buffer.width=canvas.width;buffer.height=canvas.height;const bufferContext=buffer.getContext('2d',{willReadFrequently:true});bufferContext.imageSmoothingEnabled=false;bufferContext.drawImage(source,0,0,canvas.width,canvas.height);return bufferContext.getImageData(0,0,canvas.width,canvas.height).data;},detectedPixels=maskData(detected),measurementPixels=maskData(measured),overlay=context.getImageData(0,0,canvas.width,canvas.height),output=overlay.data,w=canvas.width,h=canvas.height;const drawBoundary=(mask,color,radius)=>{const boundary=[];for(let y=1;y<h-1;y++)for(let x=1;x<w-1;x++){const pixel=(y*w+x)*4,value=mask[pixel];if(value&&((mask[pixel-4]!==value)||(mask[pixel+4]!==value)||(mask[pixel-w*4]!==value)||(mask[pixel+w*4]!==value)))boundary.push([x,y]);}for(const [x,y]of boundary)for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){const px=x+dx,py=y+dy;if(px<0||py<0||px>=w||py>=h)continue;const offset=(py*w+px)*4;output[offset]=color[0];output[offset+1]=color[1];output[offset+2]=color[2];output[offset+3]=255;}};drawBoundary(detectedPixels,[235,243,238],0);drawBoundary(measurementPixels,[255,153,31],1);context.putImageData(overlay,0,0);context.save();context.font=`bold ${Math.max(14,Math.round(w/55))}px system-ui`;context.textAlign='center';context.textBaseline='middle';context.lineWidth=Math.max(3,Math.round(w/350));for(const region of segmentation.regions||[]){const y=region.centroid?.[0],x=region.centroid?.[1];if(!Number.isFinite(x)||!Number.isFinite(y))continue;context.strokeStyle='#713800';context.fillStyle='#fff';context.strokeText(String(region.id),x*w/detected.naturalWidth,y*h/detected.naturalHeight);context.fillText(String(region.id),x*w/detected.naturalWidth,y*h/detected.naturalHeight);}context.restore();}catch(error){console.warn('Leaf overlay unavailable',error);}};
 image.onload=paint;if(image.complete)paint();
}
function showScienceDetail(key,point){
 const run=selectedScience(),metric=run?.metrics[key];if(!metric)return;const points=metric.points||[],sameMetric=scienceMetric===key,requested=point?points.indexOf(point):(sameMetric&&Number.isInteger(sciencePointIndex)?sciencePointIndex:points.length-1);scienceMetric=key;sciencePointIndex=Math.max(0,Math.min(points.length-1,requested<0?points.length-1:requested));const p=points[sciencePointIndex];text('science-detail-title',metric.label);const image=$('science-detail-image'),link=$('science-detail-download');image.hidden=!p?.image_id;link.hidden=!p?.image_id;
 if(p?.image_id){image.src='/api/frame?id='+p.image_id;image.alt=metric.label+' · '+(p.label||'');link.href='/api/frame.tif?id='+p.image_id;}
 const segmentation=run?.segmentation,state=segmentation?.state==='completed'&&segmentation?.detected_image_id&&segmentation?.measurement_image_id;$('science-segmentation-key').hidden=!state;renderFluorescenceHeatmap(image,metric.label,!!p?.image_id,state?segmentation:null);
 text('science-detail-scale',p?.image_id?`${p.label} · false color (viridis) · display ${metric.display_min||0}–${metric.display_max} ${metric.units||''}`+(state?` · ${segmentation.regions?.length||0} automatic regions; values use ${segmentation.measurement_inset_pixels||8} px inset`:''):'Not measured');
 const imagePoints=points.map((value,index)=>({value,index})).filter(entry=>entry.value.image_id),imageIndex=imagePoints.findIndex(entry=>entry.index===sciencePointIndex),navigation=$('science-detail-navigation'),previous=$('science-detail-previous'),next=$('science-detail-next');navigation.hidden=imagePoints.length<2||imageIndex<0;previous.disabled=imageIndex<=0;next.disabled=imageIndex<0||imageIndex>=imagePoints.length-1;text('science-detail-position',imageIndex>=0?`${imageIndex+1} of ${imagePoints.length} · ${p.label||p.time_s.toFixed(1)+' s'}`:'No image');previous.onclick=()=>{if(imageIndex>0)showScienceDetail(key,imagePoints[imageIndex-1].value);};next.onclick=()=>{if(imageIndex>=0&&imageIndex<imagePoints.length-1)showScienceDetail(key,imagePoints[imageIndex+1].value);};
 text('science-detail-scope',scopeWords[metricScope(key)]);text('science-detail-method',metric.method||metric.reason||'Not measured');renderMeasurementQuality(run);drawScienceChart($('science-detail-chart'),points,false,p);
 const table=$('science-detail-values');table.replaceChildren();for(const row of metric.points||[]){const tr=document.createElement('tr'),name=document.createElement('td'),value=document.createElement('td');name.textContent=row.label||row.time_s.toFixed(1)+' s';value.textContent=row.value.toFixed(3);tr.append(name,value);table.append(tr);}const leafSection=$('science-leaf-section'),leafTable=$('science-leaf-values'),leaves=p?.leaf_values||[];leafSection.hidden=!leaves.length;leafTable.replaceChildren();const largest=Math.max(0,...leaves.map(leaf=>Number(leaf.valid_pixels)||0)),shown=$('science-show-all-regions').checked?leaves:leaves.filter(leaf=>(Number(leaf.valid_pixels)||0)>=largest*REGION_TABLE_FLOOR),seg=run?.segmentation||{};text('science-region-note','Automatic regions'+(seg.algorithm_version?' · algorithm '+seg.algorithm_version:'')+(seg.status?' · '+String(seg.status).replaceAll('_',' '):'')+'. Not verified as individual leaves; a region may hold several leaves or part of one, and numbers are not tracked between runs.'+(shown.length<leaves.length?' '+(leaves.length-shown.length)+' small region'+(leaves.length-shown.length===1?'':'s')+' hidden below 2% of the largest region; choose Show all regions to include them. All regions remain in the export.':''));for(const leaf of shown){const tr=document.createElement('tr');for(const value of [leaf.id,Number.isFinite(leaf.mean)?leaf.mean.toFixed(3):'—',Number.isFinite(leaf.stdev)?leaf.stdev.toFixed(3):'—',leaf.valid_pixels]){const cell=document.createElement('td');cell.textContent=value;tr.append(cell);}leafTable.append(tr);} $('science-show-all-regions').onchange=()=>showScienceDetail(key,p);$('science-detail').open=true;
}
function renderScience(){
 const run=selectedScience();for(const id of ['fluorescence-primary','fluorescence-derived'])$(id).replaceChildren();
 text('science-note',run?new Date(run.completed_at*1000).toLocaleString()+' · latest completed observation':'No completed observation'); $('science-note').title=run?.qualification||'';
 for(const key of metricOrder){const metric=run?.metrics[key],point=metric?.points?.at(-1),card=document.createElement('button');card.className='science-card';card.type='button';card.setAttribute('aria-label','Inspect '+metricLabels[key]);card.disabled=!point;
 const title=document.createElement('span');title.className='science-card-label';title.textContent=metricLabels[key];const value=document.createElement('strong');value.textContent=point?point.value.toFixed(key==='F0'||key==='Fm'||key==='Fm_prime'||key==='Fs'||key==='Fv'?1:3):'Not measured';card.append(title,value);
 if(point?.image_id){const chart=document.createElementNS('http://www.w3.org/2000/svg','svg');chart.setAttribute('aria-label',metricLabels[key]+' time series');chart.classList.add('science-sparkline');drawScienceChart(chart,metric.points,true);chart.style.pointerEvents='none';card.append(chart);}
 const note=document.createElement('small');note.textContent=point?point.time_s.toFixed(1)+' s'+(['F0','Fm','Fv','Fv_Fm'].includes(key)?' · dark reference':''): 'Not measured';note.title=(point?.label||'')+' · '+(metric?.method||metric?.reason||'');card.append(note);card.onclick=()=>showScienceDetail(key);$(metricOrder.indexOf(key)<5?'fluorescence-primary':'fluorescence-derived').append(card);}
 renderMeasurementQuality(run);if($('science-detail').open)showScienceDetail(scienceMetric);
}
async function loadFluorescence(){if(scienceLoading||currentPage!=='overview')return;scienceLoading=true;try{const data=await api('/api/status?view=fluorescence');if(currentPage!=='overview')return;const last=data.last_completed;renderLatestAverage(last);text('workspace-last',last?`${last.experiment} · ${new Date(last.created*1000).toLocaleTimeString()}`:'No completed measurement');
 const signature=JSON.stringify(data.datasets);if(signature!==scienceSignature){scienceSignature=signature;const followLatest=!scienceSelection||scienceSelection===fluorescenceData[0]?.id;fluorescenceData=data.datasets||[];if(followLatest||!fluorescenceData.some(d=>d.id===scienceSelection))scienceSelection=fluorescenceData[0]?.id||null;const select=$('science-run');select.replaceChildren();for(const run of fluorescenceData)select.add(new Option(run.name+(run.completed_at?' · '+new Date(run.completed_at*1000).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):''),run.id));if(!fluorescenceData.length)select.add(new Option('No completed analysis',''));select.value=scienceSelection||'';renderScience();}
 }finally{scienceLoading=false;}}
$('science-run').onchange=()=>{scienceSelection=$('science-run').value;sciencePointIndex=null;renderScience();};
setInterval(()=>{updateWorkspaceState();if(currentPage==='overview'&&!document.hidden)loadFluorescence().catch(()=>{});},5000);

const editorActions=document.createElement('div');editorActions.className='editor-actions';editorActions.innerHTML=`<div class="button-row"><strong id="editor-state">Draft</strong><button id="editor-start" class="button primary" data-write>Start now</button><label>Scheduled start<input id="editor-start-time" type="datetime-local"></label><button id="editor-schedule" class="button secondary" data-write>Schedule</button></div><p id="editor-submit-status" role="status"></p>`;
document.querySelector('.experiment-workbench .panel-heading').after(editorActions);
const endSettings=document.createElement('div');endSettings.className='plain-fields';endSettings.innerHTML=`<label>Final light intensity<input id="editor-final-light" type="number" min="0" max="500" step="1" value="0"></label><label>Light on pause or error<input id="editor-stop-light" type="number" min="0" max="500" step="1" value="0"></label><label>If camera frames are lost<select id="editor-failure"><option value="stop">Stop for review</option><option value="continue">Record failed measurement and continue</option></select></label><p class="help">Hardware or restoration errors always stop the run. Interrupted runs require review; missed pulses are never replayed automatically.</p>`;$('plain-options').prepend(endSettings);
$('save-plan').textContent='Save';editorActions.querySelector('.button-row').prepend($('save-plan'));
let editorBusy=false;
function editorPermissions(){const blocked=editorBusy||commandPending||!connected()||!account||account.role==='viewer';for(const id of ['editor-start','editor-schedule'])$(id).disabled=blocked||!!state?.active||!state?.experiment_ready; text('editor-state',editID?'Draft · editing v'+editVersion:'Draft');}
const basePermissions=applyControlPermissions;applyControlPermissions=function(){basePermissions();editorPermissions();};
async function submitEditor(schedule){if(editorBusy)return;let due;if(schedule){due=new Date($('editor-start-time').value).getTime()/1000;if(!Number.isFinite(due)||due<Date.now()/1000+30)throw Error('Choose a start at least 30 seconds ahead.');}const p=editorPlan();editorBusy=true;document.querySelector('.experiment-workbench').inert=true;editorPermissions();try{text('editor-submit-status','Checking and saving…');const checked=await sendPlan('validate',p);if(!checked.hardware_ready)throw Error(checked.hardware_reasons.join(' · '));if(!await confirmExperiment(p,checked,schedule,due)){text('editor-submit-status','Start cancelled. Draft unchanged.');return;}const saved=await sendPlan('save',p,{id:editID,version:editVersion});editID=saved.id;editVersion=saved.version;const request={experiment:saved.id,version:saved.version,mode:'hardware',request_id:crypto.randomUUID()};if(schedule)Object.assign(request,{operation:'schedule',due});await api('/api/run',request);text('editor-submit-status',schedule?'Scheduled · '+new Date(due*1000).toLocaleString():'Started · version '+saved.version);text('plan-result','Saved version '+saved.version);await loadVersions();await loadWorkspace();await refreshStatus();}catch(e){text('editor-submit-status',e.message);throw e;}finally{editorBusy=false;document.querySelector('.experiment-workbench').inert=false;editorPermissions();}}
bind('editor-start',()=>submitEditor(false));bind('editor-schedule',()=>submitEditor(true));
$('experiment-editor').addEventListener('input',()=>{text('editor-submit-status','');text('editor-state','Draft · unsaved changes');});
const scheduleHelp=document.createElement('p');scheduleHelp.className='help';scheduleHelp.textContent='Start and Schedule save and run the current draft. Intensity is in controller units, not PPFD.';editorActions.append(scheduleHelp);
$('plain-measurement-panel').querySelector('.help').textContent='Select a protocol in Pulse settings. Measurements reserve 30 seconds for camera preparation and 10 seconds for cleanup.';
$('graph-measurement-type').parentElement.firstChild.textContent='Add measurement type';
editorPermissions();

const openDraft=document.createElement('button');openDraft.className='button secondary';openDraft.textContent='Open';document.querySelector('.experiment-workbench .panel-heading .button-row').prepend(openDraft);
const draftDialog=document.createElement('dialog');draftDialog.id='draft-dialog';draftDialog.innerHTML='<h2>Open experiment</h2><label>Experiment<select id="draft-choice" aria-label="Saved editable experiment"></select></label><div class="button-row"><button id="draft-load" class="button primary">Open in editor</button><button id="draft-close" class="button secondary">Cancel</button></div>';
document.body.append(draftDialog);openDraft.onclick=async()=>{try{await loadWorkspace();const list=$('draft-choice');list.replaceChildren();for(const p of workspace.experiments)list.add(new Option(p.name+' · v'+p.version,p.id));$('draft-load').disabled=!list.options.length;if(!list.options.length)list.add(new Option('No saved drafts',''));draftDialog.showModal();}catch(e){toast(e.message);}};
$('draft-close').onclick=()=>draftDialog.close();$('draft-load').onclick=async()=>{try{const d=await api('/api/status?view=document&id='+encodeURIComponent($('draft-choice').value));loadEditor(d.body,d.id,d.version);draftDialog.close();editorPermissions();}catch(e){toast(e.message);}};

for(const id of ['plain-baseline','plain-level','graph-value'])$(id).max=500;

$('editor-final-light').addEventListener('change',()=>{try{const p=JSON.parse($('plan-editor').value),ms=PlanTiming.infer(p),last=[...p.events].sort((a,b)=>a.delay_ms-b.delay_ms).at(-1);if(last?.kind==='set'&&last.command==='intensity'&&last.delay_ms===ms)last.value=String(Number($('editor-final-light').value));$('plan-editor').value=JSON.stringify(p,null,2);$('plan-editor').dispatchEvent(new Event('input'));}catch(e){toast(e.message);}});
const runReview=document.createElement('dialog');runReview.innerHTML='<h2>Review experiment</h2><p id="run-review-summary"></p><p id="run-review-stop"></p><p>Intensity is in controller units. Confirm dark adaptation and pulse settings for this experiment.</p><div class="button-row"><button id="run-review-confirm" class="button primary">Start experiment</button><button id="run-review-cancel" class="button secondary">Back to editor</button></div>';document.body.append(runReview);
function confirmExperiment(p,checked,schedule,due){
 const end=Math.max(...p.events.map(e=>e.delay_ms)),lights=p.events.filter(e=>e.kind==='set'&&e.command==='intensity'),captures=p.events.filter(e=>e.kind==='capture').sort((x,y)=>x.delay_ms-y.delay_ms),peak=Math.max(0,...lights.map(e=>Number(e.value)));
 const span=ms=>{const total=Math.round(ms/1000),d=Math.floor(total/86400),h=Math.floor(total%86400/3600),m=Math.floor(total%3600/60),sec=total%60;return [d?d+' d':'',h?h+' h':'',m?m+' min':'',sec||!total?sec+' s':''].filter(Boolean).join(' ');};
 const clock=seconds=>new Date(seconds*1000).toLocaleString([], {weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
 const begins=schedule?due:(state?.server_time||Date.now()/1000),repeats=(p.studio?.repeats||[]).map(block=>block.lines.length+' event'+(block.lines.length===1?'':'s')+' × '+block.count).join(', ');
 text('run-review-summary',[p.name,'Runs '+span(end)+(schedule?' · starts '+clock(begins):' · starts when you confirm')+' · ends about '+clock(begins+end/1000),lights.length+' light change'+(lights.length===1?'':'s')+' · peak '+peak+' controller units (not measured light)',captures.length?captures.length+' measurement'+(captures.length===1?'':'s')+' · first at '+span(captures[0].delay_ms)+', last at '+span(captures.at(-1).delay_ms)+' · '+checked.frames+' frames':'No measurements',repeats?'Repeats: '+repeats:'','This draft is saved as a new version before it '+(schedule?'is scheduled.':'starts.')].filter(Boolean).join('\n'));text('run-review-stop','On pause/error: request light '+p.execution.on_stop_light+'. Transport faults require physical intervention.');text('run-review-confirm',schedule?'Schedule experiment':'Start experiment');return new Promise(resolve=>{function finish(value){runReview.close();resolve(value);}$('run-review-confirm').onclick=()=>finish(true);$('run-review-cancel').onclick=()=>finish(false);runReview.oncancel=event=>{event.preventDefault();finish(false);};runReview.showModal();});}
const quality=document.createElement('details');quality.id='measurement-quality';quality.innerHTML='<summary>Measurement timing and quality</summary><div id="measurement-quality-body"></div>';$('fluorescence-results').append(quality);
function renderMeasurementQuality(run){const box=$('measurement-quality-body');if(!box)return;box.replaceChildren();const rows=run?.quality||[];if(!rows.length){box.textContent='No per-acquisition quality records in this dataset.';return;}for(const q of rows){const row=document.createElement('p');const intended=q.intended_trigger?new Date(q.intended_trigger*1000).toLocaleTimeString():'unavailable',actual=q.actual_trigger?new Date(q.actual_trigger*1000).toLocaleTimeString():'not triggered / unavailable';row.textContent='Capture '+(q.capture_sequence+1)+' · '+(q.state||'completed')+' · intended '+intended+' · actual '+actual+' · lateness '+(Number.isFinite(q.lateness_s)?q.lateness_s.toFixed(3)+' s':'unavailable')+(q.notes?.length?' · '+q.notes.join(' · '):' · no recorded warnings');box.append(row);}if(rows.some(q=>q.notes?.length))quality.open=true;}
const stopped=document.createElement('div');stopped.id='stopped-run';stopped.className='notice';stopped.hidden=true;$('overview').prepend(stopped);
const stateBeforeStop=updateWorkspaceState;updateWorkspaceState=function(){stateBeforeStop();const end=state?.run_end;stopped.hidden=!!state?.active||!end||['completed','completed_with_errors'].includes(end.state);if(!stopped.hidden){const l=end.light;stopped.textContent='Run '+end.state.replaceAll('_',' ')+' · '+(l?.state==='completed'?'main light commanded '+l.requested:'stop light not confirmed: '+(l?.reason||l?.error||'unknown'))+'. Physical output is not measured.';}};
// Compact access to records and diagnostics; neither remains a main-page section.
const recordDialog=document.createElement('dialog');recordDialog.innerHTML='<div class="button-row"><h2>Run records</h2><button id="close-records" class="button secondary">Close</button></div>';const records=$('run-list').closest('article');records.querySelector('.panel-heading').remove();recordDialog.append(records);document.body.append(recordDialog);const recordButton=document.createElement('button');recordButton.textContent='Run details';recordButton.className='button secondary';recordButton.onclick=()=>recordDialog.showModal();editorActions.querySelector('.button-row').append(recordButton);$('close-records').onclick=()=>recordDialog.close();
const advancedDialog=document.createElement('dialog');advancedDialog.innerHTML='<div class="button-row"><h2>Advanced</h2><button id="close-advanced" class="button secondary">Close</button></div>';const systemBody=$('system-details').querySelector('.combined-body');advancedDialog.append(systemBody);$('system').remove();document.body.append(advancedDialog);const advancedButton=document.createElement('button');advancedButton.textContent='Advanced';advancedButton.className='button secondary';advancedButton.onclick=()=>advancedDialog.showModal();document.querySelector('.experiment-workbench .panel-heading .button-row').append(advancedButton);$('close-advanced').onclick=()=>advancedDialog.close();

const applyJson=document.createElement('button');applyJson.className='button secondary';applyJson.textContent='Load JSON into editor';applyJson.onclick=()=>{try{loadEditor(JSON.parse($('plan-editor').value),editID,editVersion,false);}catch(e){toast(e.message);}};$('plan-editor').after(applyJson);

// Latest observation stays above the editable experiment; both tabs share one draft.
const home=document.createElement('div');home.id='observation-home';home.className='observation-home';runStrip.after(home);home.append(science,$('measurement-average'));
science.querySelector('h2').textContent='Fluorescence';science.querySelector('.panel-heading label').firstChild.textContent='Run ';
const metricsNote=document.createElement('p');metricsNote.className='help metrics-population';metricsNote.textContent='F₀ / Fm / Fs / Fm′: full-frame means. Fv and ratios: signal mask.';science.querySelector('.detail-body').append(metricsNote);
const resultDialog=document.createElement('dialog');resultDialog.id='measurement-dialog';resultDialog.innerHTML='<div class="button-row"><h2>Observation detail</h2><button id="close-measurement" class="button secondary">Close</button></div>';resultDialog.append($('science-detail'),quality);document.body.append(resultDialog);$('close-measurement').onclick=()=>resultDialog.close();resultDialog.addEventListener('close',()=>{$('science-detail').open=false;});$('science-detail').querySelector('summary').hidden=true;
const detailBeforeModal=showScienceDetail;showScienceDetail=function(...args){detailBeforeModal(...args);if(!resultDialog.open)resultDialog.showModal();};
$('measurement-average').querySelector('h2').textContent='Latest captured image';
// Latest acquired phase average remains independent of the selected historical result run.
const scienceBeforeHome=renderScience;renderScience=function(){scienceBeforeHome();const run=selectedScience();metricsNote.textContent=run?.time_origin==='run_start'?'F₀ / Fm / Fs / Fm′: full-frame means. Fv and ratios: signal mask.':'Values use this run’s recorded analysis region. Select a metric for its method.';};
function renderLatestAverage(last){
 const panel=$('measurement-average');if(!last){panel.hidden=true;return;}if(currentPage!=='overview')return;panel.hidden=false;
 const image=$('measurement-average-image'),src='/api/frame?id='+encodeURIComponent(last.id);
 let canvas=$('measurement-average-heatmap');if(!canvas){canvas=document.createElement('canvas');canvas.id='measurement-average-heatmap';canvas.width=560;canvas.height=400;canvas.setAttribute('role','img');image.after(canvas);const legend=document.createElement('div');legend.className='observation-color-legend';legend.innerHTML='<span>Lower fluorescence</span><span class="observation-color-scale"></span><span>Higher fluorescence</span>';canvas.after(legend);}
 canvas.setAttribute('aria-label','Latest averaged fluorescence observation, false color');
 if(panel.dataset.imageId!==last.id){panel.dataset.imageId=last.id;canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);canvas.hidden=false;image.onload=()=>{if(panel.dataset.imageId===last.id&&image.naturalWidth){paintQuenchingImage(image,canvas);canvas.hidden=false;}};image.addEventListener('error',()=>{if(panel.dataset.imageId===last.id)canvas.hidden=true;},{once:true});image.src=src;if(image.complete&&image.naturalWidth)image.onload();}
 $('measurement-average-label').textContent=(last.experiment||'Unknown run')+' · '+(last.label||'Measurement')+' · '+(last.frame_count||'—')+' frames · '+new Date(last.created*1000).toLocaleString();
 $('measurement-average-download').href='/api/frame.tif?id='+encodeURIComponent(last.id);$('measurement-average-download').textContent='Download averaged TIFF';panel.querySelector('h2').textContent='Latest averaged observation';
}
var activeEditorTab='light';
const editorTabs=document.createElement('div');editorTabs.className='editor-tabs';editorTabs.setAttribute('role','tablist');editorTabs.setAttribute('aria-label','Experiment controls');editorTabs.innerHTML='<button id="tab-light" role="tab" aria-controls="light-tab" aria-selected="true">Light</button><button id="tab-camera" role="tab" aria-controls="camera-tab" aria-selected="false" tabindex="-1">Camera</button>';
const graphHost=$('plain-fields').closest('.graph-studio'),commonFields=$('plain-fields');graphHost.before(commonFields,editorTabs);commonFields.append($('plain-range'));const applyDuration=document.createElement('button');applyDuration.className='button secondary';applyDuration.textContent='Apply duration';applyDuration.onclick=()=>$('studio-days').onchange();$('duration-unit').parentElement.after(applyDuration);graphHost.id='light-tab';graphHost.setAttribute('role','tabpanel');graphHost.setAttribute('aria-labelledby','tab-light');const cameraTab=document.createElement('div');cameraTab.id='camera-tab';cameraTab.setAttribute('role','tabpanel');cameraTab.setAttribute('aria-labelledby','tab-camera');cameraTab.hidden=true;graphHost.after(cameraTab);cameraTab.append($('protocol-recipes'),$('plain-measurement-panel'),$('plain-pulse-panel'),cameraGrid,$('photos'));
// Keep the page visibility switch from unhiding an inactive tab's nested photo section.
$('photos').classList.remove('page');$('photos').hidden=false;
function selectEditorTab(which){activeEditorTab=which;graphHost.hidden=which!=='light';cameraTab.hidden=which!=='camera';for(const key of ['light','camera']){$('tab-'+key).setAttribute('aria-selected',String(key===which));$('tab-'+key).tabIndex=key===which?0:-1;}}
for(const key of ['light','camera']){$('tab-'+key).onclick=()=>selectEditorTab(key);$('tab-'+key).onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const next=key==='light'?'camera':'light';selectEditorTab(next);$('tab-'+next).focus();}};}
$('experiment-editor').open=true;$('experiment-editor').querySelector('summary').hidden=true;
// Camera settings retain the independent protocol importer under Advanced.
const independentProtocol=$('protocol-list').closest('details');if(independentProtocol){independentProtocol.querySelector('summary').textContent='Standalone acquisition / protocol import';advancedDialog.append(independentProtocol);}
const scheduleInput=$('editor-start-time').parentElement,scheduledButton=$('editor-schedule');const scheduleOptions=document.createElement('details');scheduleOptions.className='schedule-options';scheduleOptions.innerHTML='<summary>Schedule</summary>';const scheduleBody=document.createElement('div');scheduleBody.className='button-row';scheduleBody.append(scheduleInput,scheduledButton);scheduleOptions.append(scheduleBody);editorActions.querySelector('.button-row').append(scheduleOptions);scheduleHelp.remove();
const newNavigate=navigate;navigate=function(page){newNavigate(page);if(page!=='fleet'){selectEditorTab(page==='photos'?'camera':activeEditorTab);}};
$('experiment-editor').addEventListener('input',()=>{$('editor-submit-status').textContent='';});
const timingInfo=document.createElement('p');timingInfo.className='help';timingInfo.textContent='Camera reservations appear in the checked plan. Profile changes remain drafts until Review & start.';$('plain-checks').append(timingInfo);
// Repeated image requests retry transient publication delays without changing acquisition.
for(const id of ['measurement-average-image','science-detail-image']){$(id).addEventListener('error',function(){const src=this.getAttribute('src');if(!src||src.includes('&retry=')||this.dataset.retried===src)return;this.dataset.retried=src;setTimeout(()=>{if(this.getAttribute('src')===src)this.src=src+'&retry='+Date.now();},1500);});}
const exportValues=document.createElement('button');exportValues.className='text-button';exportValues.textContent='Export values';exportValues.onclick=async()=>{
 const run=selectedScience();if(!run)return;requestQuenchingLighting(run);if(quenchingPending.has(run.id))await quenchingPending.get(run.id);
 const commands=quenchingLighting.get(run.id)||[],intensity=time=>commands.filter(command=>command.time_s<=time).at(-1)?.intensity??'',quote=value=>{let cell=String(value??'');if(typeof value==='string'&&/^[=+\-@\t\r]/.test(cell)&&!/^-?\d/.test(cell))cell="'"+cell;return '"'+cell.replaceAll('"','""')+'"';};
 // Every row says which pixels, which statistic, when, on which chamber, and with which analysis.
 const iso=seconds=>seconds!==null&&seconds!==undefined&&Number.isFinite(Number(seconds))?new Date(Number(seconds)*1000).toISOString():'',origin=quenchingOrigin(run),seg=run.segmentation||{};
 const qualityOf=sequence=>(run.quality||[]).find(row=>row.capture_sequence===sequence)||{};
 const darkReference=time=>(run.metrics?.Fm?.points||[]).filter(point=>point.time_s<=time).sort((x,y)=>x.time_s-y.time_s).at(-1)?.capture_sequence??'';
 const rows=[['run_id','run','chamber','run_completed_utc','metric','time_s','time_origin','measured_at_utc','capture_sequence','scope','statistic','region_id','value','median','stdev','units','valid_pixels','retained_fraction','dark_reference_capture_sequence','commanded_intensity_controller_units','trigger_lateness_s','quality_notes','segmentation_algorithm','segmentation_status','method']];
 for(const [key,metric]of Object.entries(run.metrics||{}))for(const point of metric.points||[]){
  const q=qualityOf(point.capture_sequence),measured=q.actual_trigger??(origin!==null?origin+Number(point.time_s):null),light=intensity(point.time_s),paired=['NPQ','PhiII'].includes(key)?darkReference(point.time_s):'';
  const head=[run.id,run.name,state?.chamber_id||state?.chamber||'',iso(run.completed_at),key,point.time_s,run.time_origin||point.label,iso(measured),point.capture_sequence];
  const tail=[paired,light,Number.isFinite(q.lateness_s)?q.lateness_s:'',(q.notes||[]).join(' | '),seg.algorithm_version||'',seg.status||'',metric.method];
  rows.push([...head,metricScope(key),metricStatistic(key),'',point.value,'','',metric.units,point.valid_pixels,'',...tail]);
  for(const leaf of point.leaf_values||[])rows.push([...head,'region_inset_'+(seg.measurement_inset_pixels||8)+'px','mean_of_pixels_in_region',leaf.id,leaf.mean,leaf.median,leaf.stdev,metric.units,leaf.valid_pixels,leaf.retained_fraction,...tail]);
 }
 const url=URL.createObjectURL(new Blob(['\ufeff',rows.map(row=>row.map(quote).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download='DEPI-'+String(run.id).slice(0,12)+'-'+(iso(run.completed_at).slice(0,10)||'undated')+'-fluorescence.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
};

// One export menu for the selected run. All downloads use authenticated read APIs.
const exportMenu=document.createElement('details');exportMenu.className='science-export-menu';
const exportSummary=document.createElement('summary');exportSummary.textContent='Export';exportSummary.className='text-button';exportMenu.append(exportSummary);
const exportOptions=document.createElement('div');exportOptions.className='science-export-options';exportMenu.append(exportOptions);
const exportProgress=document.createElement('p');exportProgress.className='help';exportProgress.setAttribute('role','status');exportOptions.append(exportProgress);
function saveExport(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}
function exportZip(files){
 const enc=new TextEncoder(),parts=[],directory=[];let offset=0;
 const crc=data=>{let c=0xffffffff;for(const b of data){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;};
 for(const file of files){const name=enc.encode(file.name),data=file.data,checksum=crc(data),h=new Uint8Array(30+name.length),v=new DataView(h.buffer);v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint16(12,33,true);v.setUint32(14,checksum,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);h.set(name,30);parts.push(h,data);
 const c=new Uint8Array(46+name.length),d=new DataView(c.buffer);d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint16(8,0x800,true);d.setUint16(14,33,true);d.setUint32(16,checksum,true);d.setUint32(20,data.length,true);d.setUint32(24,data.length,true);d.setUint16(28,name.length,true);d.setUint32(42,offset,true);c.set(name,46);directory.push(c);offset+=h.length+data.length;}
 const size=directory.reduce((n,p)=>n+p.length,0),end=new Uint8Array(22),e=new DataView(end.buffer);e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,size,true);e.setUint32(16,offset,true);return new Blob([...parts,...directory,end],{type:'application/zip'});
}
async function chartImageExport(run){
 const files=[],manifest=[],enc=new TextEncoder();let total=0;
 for(const key of metricOrder){const metric=run.metrics?.[key];for(const point of metric?.points||[]){if(!point.image_id)continue;
  const q=(run.quality||[]).find(q=>q.capture_sequence===point.capture_sequence),origin=quenchingOrigin(run),stamp=q?.actual_trigger??(origin===null?null:origin+point.time_s);
  const name=key+'-capture-'+String(point.capture_sequence??manifest.length+1).padStart(3,'0')+'-'+String(point.time_s).replace('.','_')+'s';
  exportProgress.textContent='Preparing '+name+'…';
  const response=await fetch('/api/frame.tif?id='+encodeURIComponent(point.image_id),{cache:'no-store'});if(!response.ok)throw Error('Could not download '+name+' (HTTP '+response.status+')');
  const tiff=new Uint8Array(await response.arrayBuffer());total+=tiff.length;if(total>300*1024*1024)throw Error('Image package exceeds 300 MB. Download individual measured TIFFs from the chart.');files.push({name:'tiff/'+name+'.tif',data:tiff});
  const image=new Image();image.src='/api/frame?id='+encodeURIComponent(point.image_id);await image.decode();
  const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight+70;const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
  const frame=ctx.getImageData(0,0,image.naturalWidth,image.naturalHeight),pixels=frame.data;let colored=false;for(let i=0;i<pixels.length;i+=4){if(pixels[i]!==pixels[i+1]||pixels[i+1]!==pixels[i+2]){colored=true;break;}}
  if(!colored){for(let i=0;i<pixels.length;i+=4){const n=pixels[i]*3;pixels[i]=fluorescencePalette[n];pixels[i+1]=fluorescencePalette[n+1];pixels[i+2]=fluorescencePalette[n+2];}ctx.putImageData(frame,0,0);}
  ctx.fillStyle='#fff';ctx.fillRect(0,image.naturalHeight,canvas.width,70);ctx.fillStyle='#172b20';ctx.font='16px sans-serif';ctx.fillText(key+' · '+(stamp===null?'timestamp unavailable':new Date(stamp*1000).toISOString()),12,image.naturalHeight+22);ctx.fillText('Viridis · '+(metric.display_min??0)+'–'+metric.display_max+' '+(metric.units||'')+' · display preview; use TIFF for analysis',12,image.naturalHeight+46);
  const png=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!png)throw Error('Could not create PNG');const bytes=new Uint8Array(await png.arrayBuffer());total+=bytes.length;files.push({name:'false-color/'+name+'.png',data:bytes});
  manifest.push({metric:key,capture_sequence:point.capture_sequence,elapsed_seconds:point.time_s,measured_at_utc:stamp===null?null:new Date(stamp*1000).toISOString(),units:metric.units,display_min:metric.display_min??0,display_max:metric.display_max,tiff:'tiff/'+name+'.tif',png:'false-color/'+name+'.png',quality:q??null});
 }}
 if(!manifest.length)throw Error('No processed chart images are available for this run yet.');
 files.push({name:'manifest.json',data:enc.encode(JSON.stringify({run_id:run.id,name:run.name,images:manifest},null,2))});
 files.push({name:'README.txt',data:enc.encode('Processed images for the selected run. TIFFs preserve measured numerical pixels. PNGs are display-resolution false-color previews with the chart metric display scale; they are not numerical data. Each available chart measurement has its own files. Missing measurements are not synthesized. Raw acquisition frames are exported separately. UTC timestamps, elapsed time, scales and quality are in manifest.json.\n')});
 saveExport(exportZip(files),'DEPI-'+run.id.slice(0,12)+'-chart-images.zip');return manifest.length+' measurement images exported.';
}
let exportBusy=false;
function exportOption(label,action){const b=document.createElement('button');b.type='button';b.className='text-button';b.textContent=label;b.onclick=async()=>{if(exportBusy)return;const run=selectedScience();if(!run){exportProgress.textContent='Select a run first.';return;}exportBusy=true;for(const x of exportOptions.querySelectorAll('button'))x.disabled=true;exportProgress.textContent='Preparing export…';try{exportProgress.textContent=await action(run)||'Download ready.';}catch(e){exportProgress.textContent=e.message;}finally{exportBusy=false;for(const x of exportOptions.querySelectorAll('button'))x.disabled=false;}};exportOptions.insertBefore(b,exportProgress);}
exportOption('Data spreadsheet — CSV',async()=>{await exportValues.onclick();return 'Timestamped CSV downloaded. Opens in Excel; includes whole-frame and available per-region values.';});
exportOption('Processed chart images — ZIP',chartImageExport);
exportOption('Raw acquisition frames…',async run=>{const job=await quenchingJob(run);if(!job?.id)throw Error('Original acquisition record unavailable for this run.');await openJob(job.id);$('bundle-export').open=true;exportMenu.open=false;return 'Choose the raw-frame download options in the run window.';});
science.querySelector('.panel-heading').append(exportMenu);

const qualityButton=document.createElement('button');qualityButton.className='text-button';qualityButton.textContent='Timing & quality';qualityButton.onclick=()=>{renderMeasurementQuality(selectedScience());quality.open=true;if(!resultDialog.open)resultDialog.showModal();};science.querySelector('.detail-body').append(qualityButton);
const homeQuality=renderScience;renderScience=function(){homeQuality();const run=selectedScience(),n=(run?.quality||[]).filter(q=>q.notes?.length||q.state!=='completed').length;qualityButton.textContent=n?'Timing & quality · '+n+' notes':'Timing & quality';qualityButton.classList.toggle('quality-attention',n>0);exportValues.disabled=!run;};

// Observation-level profile. The light band uses acknowledged commands from the
// saved run record; it never represents measured irradiance or inferred PPFD.
const quenching=document.createElement('section');quenching.id='quenching-profile';quenching.innerHTML='<h3>Quenching profile</h3><div class="quenching-legend" aria-label="Toggle chart series"></div><div class="quenching-plot" id="quenching-fluorescence"></div><div class="quenching-plot" id="quenching-derived"></div><div class="quenching-hover" id="quenching-hover" role="tooltip" hidden><strong></strong><span class="quenching-hover-meta"></span><canvas width="176" height="128" aria-label="False-color source image"></canvas><span class="quenching-hover-light"></span></div>';
science.querySelector('.derived-grid').after(quenching);
const quenchingSpecs=[['F0','F₀','fluorescence'],['Fm','Fm','fluorescence'],['Fm_prime','Fm′','fluorescence'],['Fs','Fs','fluorescence'],['Fv_Fm','Fv/Fm','derived'],['NPQ','NPQ','derived'],['PhiII','ΦII','derived']];
const quenchingVisible=new Set(quenchingSpecs.map(row=>row[0])),quenchingLighting=new Map(),quenchingPhases=new Map(),quenchingPending=new Map(),quenchingImageCache=new Map();
const quenchingHover=quenching.querySelector('#quenching-hover');
for(const [key,label] of quenchingSpecs){const button=document.createElement('button');button.type='button';button.dataset.metric=key;button.setAttribute('aria-pressed','true');button.innerHTML='<span class="quenching-swatch"></span>';button.append(document.createTextNode(label));button.onclick=()=>{if(quenchingVisible.has(key))quenchingVisible.delete(key);else quenchingVisible.add(key);button.setAttribute('aria-pressed',String(quenchingVisible.has(key)));renderQuenching();};quenching.querySelector('.quenching-legend').append(button);}
function quenchingClock(seconds,unit){const value=seconds/(unit==='h'?3600:unit==='min'?60:1);return (value>=10?value.toFixed(0):value.toFixed(1)).replace(/\.0$/,'')+' '+unit;}
function quenchingOrigin(run){
 if(run?.run_start!==null&&run?.run_start!==undefined&&Number.isFinite(Number(run.run_start)))return Number(run.run_start);
 for(const metric of Object.values(run?.metrics||{}))for(const point of metric.points||[]){const q=(run.quality||[]).find(row=>row.capture_sequence===point.capture_sequence&&row.actual_trigger!==null&&row.actual_trigger!==undefined&&Number.isFinite(Number(row.actual_trigger)));if(q&&Number.isFinite(Number(point.time_s)))return Number(q.actual_trigger)-Number(point.time_s);}
 return null;
}
async function quenchingJob(run){
 if(!globalThis.crypto?.subtle)return null;
 let offset=0;
 while(offset!==null){const page=await api('/api/status?view=runs&offset='+offset);for(const item of page.items||[]){const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(item.id)));const hash=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');if(hash===run.id)return api('/api/status?view=job&id='+encodeURIComponent(item.id));}offset=page.next_offset??null;}
 return null;
}
function quenchingCommands(run,job){
 const origin=quenchingOrigin(run);if(origin===null||!job?.plan?.events)return [];
 return (job.attempts||[]).flatMap(attempt=>{const event=job.plan.events[attempt.seq],value=Number(event?.value),stamp=Number(attempt.ended);return attempt.state==='completed'&&attempt.ended!==null&&attempt.ended!==undefined&&event?.kind==='set'&&event.command==='intensity'&&Number.isFinite(value)&&Number.isFinite(stamp)?[{time_s:stamp-origin,intensity:value}]:[];}).sort((a,b)=>a.time_s-b.time_s);
}
function requestQuenchingLighting(run){
 if(!run||quenchingLighting.has(run.id)||quenchingPending.has(run.id))return;
 const task=quenchingJob(run).then(job=>{quenchingPhases.set(run.id,job?.plan?.studio?.phases||null);return quenchingCommands(run,job);}).catch(()=>[]).then(commands=>{quenchingLighting.set(run.id,commands);quenchingPending.delete(run.id);if(selectedScience()?.id===run.id)renderQuenching();});
 quenchingPending.set(run.id,task);
}
function quenchingSourceImage(id){
 if(!quenchingImageCache.has(id)){const image=new Image();image.onerror=()=>quenchingImageCache.delete(id);image.src='/api/frame?id='+encodeURIComponent(id);quenchingImageCache.set(id,image);if(quenchingImageCache.size>32)quenchingImageCache.delete(quenchingImageCache.keys().next().value);}
 return quenchingImageCache.get(id);
}
function paintQuenchingImage(image,canvas=quenchingHover.querySelector('canvas')){
 const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='#000';ctx.fillRect(0,0,canvas.width,canvas.height);
 const scale=Math.min(canvas.width/image.naturalWidth,canvas.height/image.naturalHeight),width=image.naturalWidth*scale,height=image.naturalHeight*scale;
 ctx.drawImage(image,(canvas.width-width)/2,(canvas.height-height)/2,width,height);
 const frame=ctx.getImageData(0,0,canvas.width,canvas.height),pixels=frame.data;let color=false;
 for(let i=0;i<pixels.length;i+=64)if(pixels[i]!==pixels[i+1]||pixels[i+1]!==pixels[i+2]){color=true;break;}
 if(!color){for(let i=0;i<pixels.length;i+=4){if(pixels[i]===0&&pixels[i+1]===0&&pixels[i+2]===0)continue;const offset=pixels[i]*3;pixels[i]=fluorescencePalette[offset];pixels[i+1]=fluorescencePalette[offset+1];pixels[i+2]=fluorescencePalette[offset+2];}ctx.putImageData(frame,0,0);}
}
let quenchingHoverToken=0;
function showQuenchingHover(target,run,key,point){
 const token=++quenchingHoverToken,metric=run.metrics[key],light=(quenchingLighting.get(run.id)||[]).filter(command=>command.time_s<=point.time_s).at(-1);
 const quality=(run.quality||[]).find(row=>row.capture_sequence===point.capture_sequence),warning=quality?.notes?.filter(Boolean).join(' · ');
 const unit=metric.units==='ratio'?'':metric.units||'';quenchingHover.querySelector('strong').textContent=metricLabels[key]+' '+point.value.toFixed(['Fm','Fm_prime','Fs'].includes(key)?1:3);
 quenchingHover.querySelector('.quenching-hover-meta').textContent=quenchingClock(point.time_s,point.time_s>=7200?'h':point.time_s>=120?'min':'s')+(unit?' · '+unit:'');
 quenchingHover.querySelector('.quenching-hover-light').textContent=[light?'Commanded light '+light.intensity+' controller units':'',warning?'Quality: '+warning:''].filter(Boolean).join(' · ');
 const canvas=quenchingHover.querySelector('canvas');canvas.hidden=!point.image_id;canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);canvas.setAttribute('aria-label',point.image_id?'Loading selected observation':'No image available');if(point.image_id){const context=canvas.getContext('2d');context.fillStyle='#b8c8bd';context.font='12px system-ui';context.fillText('Loading image…',12,24);}
 const neighbors=metric.points||[],index=neighbors.indexOf(point);for(const neighbor of [neighbors[index-1],neighbors[index+1]])if(neighbor?.image_id)quenchingSourceImage(neighbor.image_id);
 if(point.image_id){const image=quenchingSourceImage(point.image_id);const paint=()=>{if(token===quenchingHoverToken&&image.naturalWidth){paintQuenchingImage(image);canvas.setAttribute('aria-label',metricLabels[key]+' at '+point.time_s+' seconds, false-color image');}};if(image.complete)paint();else image.addEventListener('load',paint,{once:true});image.addEventListener('error',()=>{if(token===quenchingHoverToken)canvas.hidden=true;},{once:true});}
 quenchingHover.hidden=false;const area=quenching.getBoundingClientRect(),mark=target.getBoundingClientRect(),preferred=mark.right-area.left+9;
 quenchingHover.style.left=Math.max(0,preferred+quenchingHover.offsetWidth<=area.width?preferred:mark.left-area.left-quenchingHover.offsetWidth-9)+'px';
 quenchingHover.style.top=Math.max(0,Math.min(mark.top-area.top-12,area.height-quenchingHover.offsetHeight))+'px';
}
function quenchingSvg(host,run,kind,commands){
 host.replaceChildren();const metrics=quenchingSpecs.filter(row=>row[2]===kind&&quenchingVisible.has(row[0]));
 const points=metrics.flatMap(([key])=>(run.metrics?.[key]?.points||[]).filter(p=>Number.isFinite(Number(p.value))&&Number.isFinite(Number(p.time_s))).map(point=>({key,point})));
 if(!points.length){host.hidden=true;return;}host.hidden=false;
 const width=Math.max(260,Math.round(host.getBoundingClientRect().width)),height=kind==='fluorescence'?225:200,left=66,right=width-14,top=kind==='fluorescence'?48:20,bottom=height-42;
 const allTimes=quenchingSpecs.flatMap(([key])=>(run.metrics?.[key]?.points||[]).map(p=>Number(p.time_s)).filter(Number.isFinite));
 const maxTime=Math.max(1,...allTimes),unit=maxTime>=7200?'h':maxTime>=120?'min':'s',x=time=>left+Math.max(0,Math.min(maxTime,time))/maxTime*(right-left);
 const values=points.map(({point})=>Number(point.value)),niceCeiling=value=>{const magnitude=10**Math.floor(Math.log10(Math.max(value,0.000001))),step=[1,2,5,10].find(n=>n*magnitude>=value);return step*magnitude;};
 const rawLow=Math.min(0,...values),rawHigh=Math.max(0.001,...values),low=rawLow<0?-niceCeiling(-rawLow*1.08):0,upper=niceCeiling(rawHigh*1.08),y=value=>bottom-(value-low)/(upper-low)*(bottom-top);
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',kind==='fluorescence'?'F zero, Fm, Fm prime and Fs, whole-frame means, over capture time':'Fv over Fm, NPQ and Phi II, plant-pixel means, over capture time');host.append(svg);
 const ordered=commands.filter(c=>c.time_s<=maxTime);
 for(let i=0;i<ordered.length;i++){const command=ordered[i],start=Math.max(0,command.time_s),end=Math.min(maxTime,ordered[i+1]?.time_s??maxTime);
  if(command.intensity>0&&end>start)scienceSvg(svg,'rect',{x:x(start),y:top,width:x(end)-x(start),height:bottom-top,fill:'#f6dfae','data-actinic-phase':'plot'});
 }
 if(kind==='fluorescence'){
  let positiveSeen=false;const declared=quenchingPhases.get(run.id),hasRecovery=Number.isFinite(Number(declared?.recovery_end_ms))&&Number(declared.recovery_end_ms)>Number(declared.actinic_off_ms);
  for(let i=0;i<ordered.length;i++){const command=ordered[i],next=ordered[i+1],start=Math.max(0,command.time_s),end=Math.min(maxTime,next?.time_s??maxTime);if(end<=start)continue;
   const actinic=command.intensity>0,darkReference=(run.metrics?.Fm?.points||[]).some(point=>point.time_s>=start&&point.time_s<end),label=actinic?'Actinic · '+command.intensity+' controller units':positiveSeen?(hasRecovery?'Recovery':'Light off'):(darkReference?'Dark reference':'Light off');if(actinic)positiveSeen=true;
   scienceSvg(svg,'rect',{x:x(start),y:8,width:x(end)-x(start),height:24,fill:actinic?'#e6b865':'#f5f7fb','data-actinic-phase':actinic?'header':'off'});
   if(x(end)-x(start)>54)scienceSvg(svg,'text',{x:(x(start)+x(end))/2,y:24,'text-anchor':'middle','font-size':11,fill:'#526177'},x(end)-x(start)<190&&actinic?command.intensity+' units':label);
  }
  if(!ordered.length)scienceSvg(svg,'text',{x:left,y:24,'font-size':11,fill:'#65738a'},'Actinic intensity unavailable');
 }
 const ticks=[low,(low+upper)/2,upper];for(const value of ticks){const yy=y(value);scienceSvg(svg,'line',{x1:left,x2:right,y1:yy,y2:yy,stroke:'#e9eef4'});scienceSvg(svg,'text',{x:left-8,y:yy+4,'text-anchor':'end','font-size':11,fill:'#65738a'},kind==='fluorescence'?value.toFixed(0):value.toFixed(2));}
 scienceSvg(svg,'rect',{x:left,y:top,width:right-left,height:bottom-top,fill:'none',stroke:'#d8e2dc'});
 const unitSeconds=unit==='h'?3600:unit==='min'?60:1,displayMax=maxTime/unitSeconds,roughStep=displayMax/(width<470?3:5),magnitude=10**Math.floor(Math.log10(Math.max(roughStep,0.000001))),tickStep=[1,2,5,10].find(n=>n*magnitude>=roughStep)*magnitude;
 for(let value=0;value<=displayMax+tickStep*0.01;value+=tickStep){const time=value*unitSeconds;scienceSvg(svg,'text',{x:x(time),y:bottom+17,'text-anchor':value===0?'start':'middle','font-size':11,fill:'#65738a'},String(Number(value.toFixed(3))));}
 scienceSvg(svg,'text',{x:(left+right)/2,y:height-5,'text-anchor':'middle','font-size':12,fill:'#34465f'},'Elapsed time ('+unit+')');
 scienceSvg(svg,'text',{x:14,y:(top+bottom)/2,transform:`rotate(-90 14 ${(top+bottom)/2})`,'text-anchor':'middle','font-size':12,fill:'#34465f'},kind==='fluorescence'?'Whole frame (camera units)':'Plant pixels (unitless)');
 const hoverTargets=[];
 for(const [key] of metrics){const series=(run.metrics?.[key]?.points||[]).filter(p=>Number.isFinite(Number(p.value))&&Number.isFinite(Number(p.time_s))).sort((a,b)=>a.time_s-b.time_s),color={'F0':'#7a8594','Fm':'#b44756','Fm_prime':'#245bea','Fs':'#24765c','Fv_Fm':'#24633b','NPQ':'#b86f20','PhiII':'#7359a7'}[key];
  if(series.length>1)scienceSvg(svg,'polyline',{points:series.map(p=>x(p.time_s)+','+y(p.value)).join(' '),fill:'none',stroke:color,'stroke-width':2.2});
  for(const point of series){const flagged=(run.quality||[]).some(row=>row.capture_sequence===point.capture_sequence&&row.notes?.length);scienceSvg(svg,'circle',{cx:x(point.time_s),cy:y(point.value),r:4.5,fill:color,stroke:flagged?'#985611':'#fff','stroke-width':flagged?2:1.4});const hit=scienceSvg(svg,'circle',{cx:x(point.time_s),cy:y(point.value),r:16,fill:'transparent',role:'button',tabindex:0,'aria-label':metricLabels[key]+' '+point.value.toFixed(3)+' at '+quenchingClock(point.time_s,unit)+(flagged?'; quality note':'')+'; show image preview'});hit.style.cursor='pointer';hoverTargets.push({hit,key,point,x:x(point.time_s),y:y(point.value)});hit.onfocus=()=>showQuenchingHover(hit,run,key,point);hit.onblur=()=>{quenchingHover.hidden=true;++quenchingHoverToken;};hit.onclick=()=>showScienceDetail(key,point);hit.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showScienceDetail(key,point);}};}
 }
 let hovered=null;
 svg.onpointermove=event=>{const matrix=svg.getScreenCTM();if(!matrix)return;const cursor=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());let nearest=null,distance=22;for(const target of hoverTargets){const delta=Math.hypot(cursor.x-target.x,cursor.y-target.y);if(delta<distance){nearest=target;distance=delta;}}if(nearest===hovered)return;hovered=nearest;if(nearest)showQuenchingHover(nearest.hit,run,nearest.key,nearest.point);else{quenchingHover.hidden=true;++quenchingHoverToken;}};
 svg.onpointerleave=()=>{hovered=null;quenchingHover.hidden=true;++quenchingHoverToken;};
}
function renderQuenching(){const run=selectedScience();quenching.hidden=!run;if(!run)return;quenchingHover.hidden=true;++quenchingHoverToken;const commands=quenchingLighting.get(run.id)||[];quenchingSvg($('quenching-fluorescence'),run,'fluorescence',commands);quenchingSvg($('quenching-derived'),run,'derived',commands);requestQuenchingLighting(run);}
let quenchingWidth=0;new ResizeObserver(()=>{const width=Math.round(quenching.getBoundingClientRect().width);if(width!==quenchingWidth){quenchingWidth=width;if(selectedScience())renderQuenching();}}).observe(quenching);
const scienceBeforeQuenching=renderScience;renderScience=function(){scienceBeforeQuenching();renderQuenching();};

// Reopen the saved profile instead of replacing it with the starter on refresh.
// Reopen the saved profile instead of replacing it with the starter on refresh.
let profileRestoreStarted=false,profileEditEpoch=0;
const profileKey=()=> 'depibeans:last-profile:DEPI-1:'+String(account?.username||'local');
function rememberProfile(id){if(!id)return;try{localStorage.setItem(profileKey(),id);}catch(e){/* Server-saved profiles remain available through Open. */}}
const loadBeforeRemember=loadEditor;loadEditor=function(...args){profileEditEpoch++;loadBeforeRemember(...args);rememberProfile(args[1]);};
const saveBeforeRemember=sendPlan;sendPlan=async function(operation,...args){const result=await saveBeforeRemember(operation,...args);if(operation==='save')rememberProfile(result.id);return result;};
for(const event of ['input','change','pointerdown'])document.querySelector('.experiment-workbench').addEventListener(event,()=>{profileEditEpoch++;});
const prepareBeforeRestore=prepareWorkspace;prepareWorkspace=function(){prepareBeforeRestore();if(profileRestoreStarted)return;profileRestoreStarted=true;const epoch=profileEditEpoch;
(async()=>{try{await loadWorkspace();if(profileEditEpoch!==epoch)return;const saved=workspace.experiments||[];let preferred;try{preferred=localStorage.getItem(profileKey());}catch(e){}const row=saved.find(x=>x.id===preferred)||saved[0];if(!row)return;const doc=await api('/api/status?view=document&id='+encodeURIComponent(row.id));if(profileEditEpoch!==epoch)return;loadEditor(doc.body,doc.id,doc.version,false);text('plan-result','Restored saved profile · version '+doc.version);editorPermissions();}catch(e){profileRestoreStarted=false;toast('Could not restore saved profile. Use Open to retry. '+e.message);}})();};

// Portal presentation only: result tiles say what they measure, Save is kept apart
// from starting the chamber, and status is shown once. No requests, no commands.
(()=>{try{
 const WHOLE=new Set(['F0','Fm','Fm_prime','Fs']);
 const day=seconds=>{const d=new Date(seconds*1000),now=new Date(),same=d.toDateString()===now.toDateString();const midnight=value=>new Date(value.getFullYear(),value.getMonth(),value.getDate()).getTime(),age=Math.round((midnight(now)-midnight(d))/86400000);return {d,same,age,text:same?d.toLocaleTimeString():d.toLocaleDateString(undefined,{month:'short',day:'numeric'})+' '+d.toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})};};

 // 1. Each tile states its image region; the panel states the date and why Fv differs.
 const priorScience=renderScience;
 renderScience=function(){priorScience();try{annotateScience();}catch(error){console.error(error);}};
 function annotateScience(){const run=selectedScience();if(!run)return;
  const frame=Math.max(0,...metricOrder.map(k=>WHOLE.has(k)?run.metrics[k]?.points?.at(-1)?.valid_pixels||0:0));
  const cards=[...document.querySelectorAll('#fluorescence-primary .science-card,#fluorescence-derived .science-card')];
  metricOrder.forEach((key,n)=>{const card=cards[n],metric=run.metrics[key],point=metric?.points?.at(-1);if(!card||!point)return;
   let tag=card.querySelector('.tile-region');if(!tag){tag=document.createElement('em');tag.className='tile-region';card.querySelector('.science-card-label')?.after(tag);}
   const whole=WHOLE.has(key),share=frame&&point.valid_pixels?Math.round(point.valid_pixels/frame*100):null;
   tag.textContent=whole?'Whole frame':'Plant pixels'+(share?' · '+share+'%':'');tag.dataset.region=whole?'frame':'plant';
   card.title=(whole?'Mean of every pixel in the frame, background included.':'Mean over pixels that pass the plant-signal mask'+(share?' ('+share+'% of the frame)':'')+'.')+' '+(metric.method||'');});
  const when=day(run.completed_at),note=document.getElementById('science-note');
  if(note){note.textContent=when.d.toLocaleString()+(when.same?'':' · '+(when.age===1?'yesterday':when.age+' days ago'))+' · latest completed observation';note.classList.toggle('stale-result',!when.same);}
  const legend=[...document.querySelectorAll('#fluorescence-results .help,#fluorescence-results p')].find(p=>/full-frame means|recorded analysis region/.test(p.textContent));
  if(legend)legend.textContent='F₀, Fm, Fs and Fm′ average the whole frame, background included. Fv and the ratios average plant pixels only, pixel by pixel — so Fv can differ from Fm − F₀ calculated from the tiles, and the ratios differ from ratios of the tiles. Select a tile for its method.';};

 // Old results carry their date in the header strip.
 const priorAverage=renderLatestAverage;
 renderLatestAverage=function(last){priorAverage(last);if(!last)return;queueMicrotask(()=>{try{const when=day(last.created),el=document.getElementById('workspace-last');if(el){el.textContent=last.experiment+' · '+when.text+(when.same?'':' · '+(when.age===1?'yesterday':when.age+' days ago'));el.classList.toggle('stale-result',!when.same);}}catch(error){console.error(error);}});};

 // 2. Save edits the recipe. Review & start commands the chamber, after the existing review.
 const start=document.getElementById('editor-start'),schedule=document.getElementById('editor-schedule'),save=document.getElementById('save-plan'),stateLabel=document.getElementById('editor-state');
 if(start&&schedule&&save){start.textContent='Review & start';start.title='Checks the plan and shows a review before anything is sent to the chamber.';schedule.textContent='Schedule';
  const row=start.closest('.button-row'),run=document.createElement('div');run.className='run-controls';run.append(start);
  const timeLabel=document.getElementById('editor-start-time')?.closest('label');const menu=document.createElement('details');menu.className='schedule-options';const summary=document.createElement('summary');summary.textContent='Schedule';menu.append(summary);if(timeLabel)menu.append(timeLabel);menu.append(schedule);run.append(menu);for(const empty of row.querySelectorAll('.schedule-options'))if(!empty.querySelector('input,button'))empty.remove();
  const details=[...row.querySelectorAll('button')].find(b=>b.textContent.trim()==='Run details');if(details)document.querySelector('.experiment-workbench .panel-heading .button-row').append(details);row.append(run);row.classList.add('recipe-row');save.title='Saves this recipe as a new version. Does not start anything.';}

 // One status. The bottom line keeps validation results only.
 const result=document.getElementById('plan-result');let dirty=false;
 const showState=()=>{if(!stateLabel)return;const base=stateLabel.textContent.replace(/ · unsaved changes$/,'');if(dirty&&!/unsaved/.test(base))stateLabel.textContent=(/^Draft/.test(base)?base:'Draft')+' · unsaved changes';};
 if(result){const tidy=()=>{const t=result.textContent;if(/^(Restored saved profile|Editing version|New copy)/.test(t)){dirty=false;result.textContent='';}else if(/^(Unsaved graph changes|Undo applied|Redo applied)/.test(t)){dirty=true;result.textContent='';showState();}else if(/^Saved version/.test(t)){dirty=false;}result.hidden=!result.textContent;};new MutationObserver(tidy).observe(result,{childList:true,characterData:true,subtree:true});tidy();}
 const priorPermissions=editorPermissions;editorPermissions=function(){priorPermissions();try{if(stateLabel&&/^Draft · editing v/.test(stateLabel.textContent))stateLabel.textContent=stateLabel.textContent.replace('Draft · editing v','Draft · v');showState();}catch(error){console.error(error);}};
}catch(error){console.error('Portal presentation unavailable',error);}})();

function updateChamberTitle(){
 if(currentPage==='fleet'){document.title='DEPI · Fleet';return;}
 const name=$('chamber-context')?.querySelector('strong')?.textContent||state?.chamber||'DEPI 1';
 let status=controllerHealth(state,connected(),connectionFailed).state.toLowerCase();
 const progress=state?.progress;let remaining='';
 if(state?.active&&chamberEndEstimate?.id!==state.active.id){const id=state.active.id;chamberEndEstimate={id,end:null};api('/api/status?view=job&id='+encodeURIComponent(id)).then(job=>{if(state?.active?.id!==id)return;const events=job.plan?.events||[];if(events.length&&events.every(e=>e.relative===true)&&Number.isFinite(progress?.started)){const duration=job.plan.studio?.duration_ms??Math.max(...events.map(e=>e.delay_ms));chamberEndEstimate={id,end:progress.started+duration/1000};updateChamberTitle();}}).catch(()=>{});}
 if(state?.active&&chamberEndEstimate?.id===state.active.id&&Number.isFinite(chamberEndEstimate.end)){const seconds=Math.max(0,chamberEndEstimate.end-(state.server_time||Date.now()/1000));remaining=seconds>0?' · ~'+(seconds>=3600?Math.ceil(seconds/3600)+'h':Math.ceil(seconds/60)+'m')+' left':' · finishing';}
 else if(state?.active&&progress?.total)remaining=' · '+Math.round(progress.completed/progress.total*100)+'%';
 document.title=name+' · '+status+remaining;
}

var chamberEndEstimate = null;

// Secondary authoring actions stay available without competing with Save / Start.
(()=>{const heading=document.querySelector('.experiment-workbench .panel-heading .button-row');if(!heading)return;const menu=document.createElement('details');menu.className='experiment-options';const summary=document.createElement('summary');summary.textContent='Experiment options';menu.append(summary);const body=document.createElement('div');body.className='button-row';for(const button of [...heading.children])body.append(button);menu.append(body);heading.append(menu);})();

// One attention reason per chamber. It drives the Fleet dot, the word under the name and the single alert line.
function controllerHealth(value,fresh,failed=false){
 const experiment=value?.active?.name||'No active experiment';
 if(!fresh)return {level:'unknown',state:failed||value?'Status unavailable':'Checking…',experiment:'Experiment status unavailable',detail:'Waiting for a fresh controller response'};
 const end=value.run_end,light=value.last_commanded_light,recovered=light&&Number(light.time)>Number(end?.time);
 const fault=value.last_error||(Number.isFinite(value.free_gb)&&value.free_gb<5?'Low disk space':null)||(!value.active&&end&&!['completed','completed_with_errors'].includes(end.state)&&end.light?.state!=='completed'&&!recovered?'Stop light not confirmed':null);
 if(fault)return {level:'warn',state:'Needs attention',experiment,detail:String(fault)};
 if(value.manual_light_ready===true&&value.experiment_ready!==true)return {level:'ok',state:'Online · lighting only',experiment,detail:'Manual lighting enabled; camera experiments unavailable'};
 if(value.experiment_ready!==true&&value.commissioned!==true)return {level:'warn',state:'Online · setup incomplete',experiment,detail:'Controller connected; commissioning requirements incomplete'};
 return {level:'ok',state:value.active?'Running':'Online',experiment,detail:'Fresh controller response'};
}
function attentionReason(){
 if(typeof connected!=='function'||!connected()||!state)return null;
 if(state.last_error)return String(state.last_error);
 if(Number.isFinite(state.free_gb)&&state.free_gb<5)return 'Low disk space · '+state.free_gb+' GB free';
 // A historical failed run is a result to review, not evidence of a current fault.
 // Keep an unconfirmed stop visible until a later successful light command establishes a new baseline.
 const end=state.run_end,light=state.last_commanded_light;
 const recovered=light&&Number(light.time)>Number(end?.time);
 if(!state.active&&end&&!['completed','completed_with_errors'].includes(end.state)&&end.light?.state!=='completed'&&!recovered)return 'Stop light not confirmed: '+(end.light?.reason||end.light?.error||'unknown');
 if(state.commissioned===false&&!state.experiment_ready&&!state.manual_light_ready)return 'No verified chamber controls';
 return null;
}

// Chamber tabs: one header on every tab; Overview is the latest run's card, Results is the list of runs.
// Sections keep their ids and handlers; tabs only decide what shows.
(()=>{
 const ws=document.querySelector('.workspace'),header=document.querySelector('.app-header'),overview=$('overview');if(!ws||!header||!overview||typeof navigate!=='function')return;
 const TABS=[['overview','Overview'],['results','Results'],['plan','Plan'],['schedule','Schedule']];
 const pageTab={overview:'overview',experiments:'plan',photos:'results',system:'plan'};
 const tabs=document.createElement('nav');tabs.className='chamber-tabs';tabs.setAttribute('aria-label','Chamber sections');tabs.hidden=true;const buttons={};
 for(const [id,label]of TABS){const b=document.createElement('button');b.type='button';b.className='chamber-tab';b.textContent=label;b.dataset.tab=id;b.onclick=()=>select(id);tabs.append(b);buttons[id]=b;}
 header.after(tabs);
 const identity=document.createElement('div');identity.id='chamber-identity';identity.innerHTML='<span class="chamber-identity-bar" aria-hidden="true"></span><div class="chamber-identity-body"><h1 id="chamber-identity-name"></h1><p class="chamber-identity-status"><span id="chamber-identity-dot" class="chamber-identity-dot" role="img" aria-label="Checking"></span><span id="chamber-identity-state">Checking…</span></p><p id="chamber-identity-meta" class="chamber-identity-meta"></p><div id="chamber-identity-alerts" class="chamber-identity-alerts" role="status"></div></div>';
 overview.prepend(identity);
 // Results: the Fleet pattern one level down. Each run is a dot, a name, a time and a word.
 const runs=document.createElement('details');runs.id='run-cards';runs.className='run-cards';runs.innerHTML='<summary class="run-cards-title">Runs <span class="run-selection-summary"></span></summary><div class="run-cards-list" role="list"></div>';identity.after(runs);
 const science=$('fluorescence-results'),average=$('measurement-average');if(science&&average)science.after(average);
 const when=t=>t?new Date(t*1000).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'';
 const runColors={ok:'#27864b',warn:'#d19a1b',down:'#c83d3d',unknown:'#91a399'};
 function runLevel(s){if(!s)return 'unknown';if(['completed','running','pending','scheduled','queued'].includes(s))return 'ok';if(['needs_review','completed_with_errors','paused','uncertain'].includes(s))return 'warn';if(['failed','error','aborted','cancelled','canceled','stopped'].includes(s))return 'down';return 'unknown';}
 let runKey='';
 function renderRunCards(){
  const records=new Map((Array.isArray(state?.recent)?state.recent:[]).filter(r=>r.mode!=='simulation').map(r=>[r.id,r]));
  const datasets=typeof fluorescenceData!=='undefined'?fluorescenceData:[];const rows=new Map();
  for(const d of datasets)rows.set(d.id,{id:d.id,name:d.name,time:d.completed_at,state:records.get(d.id)?.state||'completed',data:true});
  for(const r of records.values())if(!rows.has(r.id))rows.set(r.id,{id:r.id,name:r.name,time:r.created,state:r.state,data:false});
  const list=[...rows.values()].sort((a,b)=>(b.time||0)-(a.time||0));
  const selected=typeof scienceSelection!=='undefined'?scienceSelection:null;
  const key=list.map(r=>r.id+':'+r.state+':'+(r.id===selected)).join('|');if(key===runKey)return;runKey=key;
  const chosen=list.find(r=>r.id===selected);runs.querySelector('.run-selection-summary').textContent=chosen?' · '+chosen.name+' · '+when(chosen.time)+' · '+String(chosen.state).replaceAll('_',' '):' · '+list.length+' runs';
  const box=runs.querySelector('.run-cards-list');box.replaceChildren();
  if(!list.length){const p=document.createElement('p');p.className='help';p.textContent='No runs yet.';box.append(p);}
  for(const r of list){const row=document.createElement('button');row.type='button';row.className='run-card';row.setAttribute('role','listitem');row.setAttribute('aria-current',String(r.id===selected));const level=runLevel(r.state);
   const dot=document.createElement('span');dot.className='run-card-dot';dot.style.background=runColors[level];dot.setAttribute('role','img');dot.setAttribute('aria-label',String(r.state||'').replaceAll('_',' '));
   const name=document.createElement('strong');name.textContent=r.name||'Run';const time=document.createElement('span');time.className='run-card-time';time.textContent=when(r.time);const word=document.createElement('span');word.className='run-card-state';const s=String(r.state||'unknown').replaceAll('_',' ');word.textContent=s.charAt(0).toUpperCase()+s.slice(1);
   row.append(dot,name,time,word);
   row.onclick=()=>{if(r.data&&typeof renderScience==='function'){scienceSelection=r.id;sciencePointIndex=null;const sel=$('science-run');if(sel)sel.value=r.id;renderScience();runKey='';renderRunCards();science?.scrollIntoView({behavior:'smooth',block:'start'});}else if(typeof openJob==='function')openJob(r.id).catch(e=>toast(e.message));};
   box.append(row);}
 }
 // The averaged TIFF preview shows an empty state instead of a broken image.
 const avg=$('measurement-average-image');if(avg){avg.addEventListener('error',()=>{avg.hidden=true;let e=$('measurement-average-empty');if(!e){e=document.createElement('p');e.id='measurement-average-empty';e.className='help';e.textContent='No image is available from the chamber right now.';avg.after(e);}e.hidden=false;});avg.addEventListener('load',()=>{avg.hidden=false;const e=$('measurement-average-empty');if(e)e.hidden=true;});}
 function select(id){ws.dataset.tab=id;for(const [k,b]of Object.entries(buttons))b.setAttribute('aria-current',String(k===id));if((id==='overview'||id==='results')&&typeof loadFluorescence==='function')loadFluorescence().catch(()=>{});if(id==='results')renderRunCards();window.dispatchEvent(new Event('resize'));}
 const baseNavigate=navigate;
 navigate=function(page){baseNavigate(page);const fleet=currentPage==='fleet';tabs.hidden=fleet;if(fleet){delete ws.dataset.tab;return;}select(pageTab[page]||'overview');};
 const colors={ok:'#27864b',warn:'#d19a1b',down:'#c83d3d',unknown:'#91a399'};
 function healthNow(){const h=controllerHealth(state,connected(),connectionFailed);return {level:h.level,word:h.state,reason:h.level==='warn'?h.detail:null};}
 function paint(){
  if(!ws.dataset.tab)return;
  $('chamber-identity-name').textContent=document.querySelector('#chamber-context strong')?.textContent||'DEPI 01';
  const h=healthNow(),dot=$('chamber-identity-dot');dot.style.background=colors[h.level];dot.setAttribute('aria-label',h.word);$('chamber-identity-state').textContent=h.word;
  const last=$('workspace-last')?.textContent||'—',next=$('workspace-next')?.textContent||'—';$('chamber-identity-meta').textContent='Last measurement: '+last+' · Next: '+next;
  const box=$('chamber-identity-alerts'),line=h.reason||'';if(box.dataset.key!==line){box.dataset.key=line;box.replaceChildren();if(line){const p=document.createElement('p');p.className='chamber-identity-alert';p.textContent=line;box.append(p);}}
  const accent=getComputedStyle(document.documentElement).getPropertyValue('--chamber-accent').trim();identity.style.setProperty('--accent',accent||'#9fb6a7');
  if(ws.dataset.tab==='results')renderRunCards();
 }
 setInterval(paint,1000);
})();

// Basement rail diagnostics. Candidate addresses are not a discovered inventory.
(()=>{
 const ws=document.querySelector('.workspace'),nav=document.querySelector('.chamber-tabs'),overview=$('overview');
 if(!ws||!nav||!overview)return;
 const RAILS=26,ALLOWED=['depi-two','depi-five'],pad=a=>String(a).padStart(2,'0');
 const tab=document.createElement('button');tab.type='button';tab.className='chamber-tab';tab.textContent='Lights · Manual';tab.hidden=true;nav.append(tab);
 const panel=document.createElement('article');panel.id='basement-lights';panel.className='basement-lights';
 panel.innerHTML='<div class="rail-head"><div><h2>Manual lights</h2><p>Send a level to one address at a time and watch the chamber. Nothing on this page is measured.</p></div><span id="rail-status" class="rail-status" role="status" data-level="wait">Waiting for controller</span></div>'
 +'<section class="rail-master">'
 +'<div class="rail-master-all"><div class="rail-master-title"><strong>All lights</strong><span>broadcast to every address</span></div><div class="rail-seg"><button type="button" id="rails-on" class="rail-on">On</button><button type="button" id="rails-off" class="rail-off">Off</button></div></div>'
 +'<div class="rail-master-level"><label for="rail-level"><strong>Level for On</strong><span>0–<span id="rail-level-max">100</span> controller units · Off always sends 0</span></label><div class="rail-level-row"><input id="rail-level-range" type="range" min="0" max="100" value="100" step="1" aria-label="Level for On, slider"><input id="rail-level" type="number" min="0" max="100" value="100" step="1" inputmode="numeric" aria-label="Level for On"></div><div class="rail-presets" role="group" aria-label="Level presets"><button type="button" data-level="10">10</button><button type="button" data-level="25">25</button><button type="button" data-level="50">50</button><button type="button" data-level="100">100</button></div></div>'
 +'<div class="rail-master-step"><div class="rail-master-title"><strong>Step through addresses</strong><span>turns the current address off, then the next one on</span></div><div class="rail-step-row"><button type="button" id="rail-prev" aria-label="Previous address">‹</button><output id="rail-step-current" aria-live="polite">Not started</output><button type="button" id="rail-next" aria-label="Next address">›</button><button type="button" id="rail-step-off" class="rail-off" aria-label="Turn the current address off">Off</button></div></div>'
 +'</section>'
 +'<p id="rail-command-result" class="rail-note" role="status" aria-live="polite" hidden></p>'
 +'<div class="rail-grid" role="list"></div>'
 +'<details class="rail-log"><summary>Command history <span id="rail-log-count"></span></summary><div class="rail-log-scroll"><table><thead><tr><th>Time</th><th>Target</th><th>Level</th><th>Outcome</th><th>Sent by</th></tr></thead><tbody id="rail-log-body"></tbody></table></div></details>'
 +'<p class="help">Addresses 1–26 are the SmartLight firmware’s candidate addresses, not detected rails. The light bus has no readback, so a card shows the last command the controller played, never whether the rail lit. Name each address as you identify its physical rail.</p>';
 overview.append(panel);
 const q=s=>panel.querySelector(s);
 const statusChip=q('#rail-status'),note=q('#rail-command-result'),level=q('#rail-level'),range=q('#rail-level-range'),levelMax=q('#rail-level-max'),grid=q('.rail-grid'),logBody=q('#rail-log-body'),logCount=q('#rail-log-count'),stepOut=q('#rail-step-current'),stepOff=q('#rail-step-off');
 const rows=new Map();let busy=false,inflight=null,identity=null,stepAt=null,logKey='';
 const allowed=()=>ALLOWED.includes(state?.chamber_id);
 const data=()=>state?.manual_lights||null;
 const maxLevel=()=>Number(data()?.limits?.[1]??100);
 const labelOf=a=>(data()?.labels?.[String(a)]||'').trim();
 const nameOf=a=>a===0?'all lights':'address '+pad(a)+(labelOf(a)?' ('+labelOf(a)+')':'');
 const when=t=>new Date(t*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit',second:'2-digit'}),brief=t=>new Date(t*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});
 function gate(){
  if(!connected())return['bad','Controller disconnected'];
  if(!data())return['wait','Manual controls not installed on this controller'];
  if(state.active)return['wait','Locked · experiment running'];
  if(state.event_pending)return['wait','Locked · hardware busy'];
  if(state.live?.running)return['wait','Locked · stop live view first'];
  if(!account||!['admin','operator'].includes(account.role))return['wait','Read-only access'];
  if(busy||commandPending)return['busy',inflight===null?'Sending…':'Sending to '+nameOf(inflight)+'…'];
  return['ok','Ready · output not measured'];
 }
 const ready=()=>allowed()&&gate()[0]==='ok';
 function say(message,kind){note.textContent=message;note.dataset.kind=kind||'info';note.hidden=!message;}
 function setLevel(v){const m=maxLevel();v=Math.round(Number(v));if(!Number.isFinite(v))v=m;v=Math.min(m,Math.max(0,v));level.value=String(v);range.value=String(v);}
 level.oninput=()=>{if(level.value!=='')range.value=level.value;};level.onchange=()=>setLevel(level.value);range.oninput=()=>{level.value=range.value;};
 for(const b of panel.querySelectorAll('.rail-presets button'))b.onclick=()=>setLevel(b.dataset.level);
 async function send(address,value){
  if(!ready())return false;
  const m=maxLevel();value=Number(value);
  if(!Number.isFinite(value)||value<0||value>m){say('Choose a level between 0 and '+m+'.','error');return false;}
  busy=true;inflight=address;say('');paint();
  try{
   const result=await api('/api/light',{operation:'rail',address,value,request_id:crypto.randomUUID()});
   if(result.state==='completed')say('Sent '+(value>0?value:'off')+' to '+nameOf(address)+' at '+when(Date.now()/1000)+'. Check the chamber.','ok');
   else say('Outcome '+result.state+' for '+nameOf(address)+'. Check the chamber before sending another command.','error');
   await refreshStatus();return result.state==='completed';
  }catch(e){say(nameOf(address)+': '+e.message+' No automatic retry.','error');return false;}
  finally{busy=false;inflight=null;paint();}
 }
 async function saveLabel(address,value){
  if(!ready())return false;busy=true;paint();
  try{await api('/api/light',{operation:'rail_label',address,label:value,request_id:crypto.randomUUID()});say(value.trim()?'Address '+pad(address)+' is now “'+value.trim()+'”.':'Label removed from address '+pad(address)+'.','ok');await refreshStatus();return true;}
  catch(e){say(e.message,'error');return false;}
  finally{busy=false;paint();}
 }
 for(let a=1;a<=RAILS;a++){
  const card=document.createElement('section');card.className='rail-card';card.setAttribute('role','listitem');card.dataset.state='none';
  card.innerHTML='<div class="rail-card-top"><span class="rail-lamp" aria-hidden="true"></span><span class="rail-number">'+pad(a)+'</span><span class="rail-chip"></span></div>'
  +'<button type="button" class="rail-label-btn" title="Name this address"><span class="rail-label-text"></span></button>'
  +'<form class="rail-label-form" hidden><input type="text" maxlength="80" placeholder="e.g. left wall, top" aria-label="Physical label for address '+pad(a)+'"><div class="rail-label-actions"><button type="submit">Save</button><button type="button" class="rail-cancel">Cancel</button></div></form>'
  +'<div class="rail-seg"><button type="button" class="rail-on" aria-label="Turn on address '+pad(a)+'">On</button><button type="button" class="rail-off" aria-label="Turn off address '+pad(a)+'">Off</button></div>'
  +'<p class="rail-meta"></p>';
  const row={card,chip:card.querySelector('.rail-chip'),labelBtn:card.querySelector('.rail-label-btn'),labelText:card.querySelector('.rail-label-text'),form:card.querySelector('.rail-label-form'),input:card.querySelector('.rail-label-form input'),cancel:card.querySelector('.rail-cancel'),on:card.querySelector('.rail-on'),off:card.querySelector('.rail-off'),meta:card.querySelector('.rail-meta')};
  row.on.onclick=()=>send(a,level.value);row.off.onclick=()=>send(a,0);
  row.labelBtn.onclick=()=>{if(!allowed())return;row.input.value=labelOf(a);row.form.hidden=false;row.labelBtn.hidden=true;row.input.focus();row.input.select();};
  row.cancel.onclick=()=>{row.form.hidden=true;row.labelBtn.hidden=false;row.labelBtn.focus();};
  row.input.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();row.cancel.onclick();}};
  row.form.onsubmit=async e=>{e.preventDefault();if(await saveLabel(a,row.input.value)){row.form.hidden=true;row.labelBtn.hidden=false;}};
  grid.append(card);rows.set(a,row);
 }
 q('#rails-on').onclick=()=>send(0,level.value);q('#rails-off').onclick=()=>send(0,0);
 async function step(dir){
  if(!ready())return;
  const next=stepAt===null?(dir>0?1:RAILS):((stepAt-1+dir+RAILS)%RAILS)+1;
  if(stepAt!==null&&!(await send(stepAt,0)))return;
  if(await send(next,level.value)){stepAt=next;paint();}
 }
 q('#rail-next').onclick=()=>step(1);q('#rail-prev').onclick=()=>step(-1);
 stepOff.onclick=()=>{if(stepAt!==null)send(stepAt,0);};
 tab.onclick=()=>{if(!allowed())return;ws.dataset.tab='lights';nav.querySelectorAll('button').forEach(b=>b.setAttribute('aria-current',String(b===tab)));paint();};
 const latest=(commands,a)=>commands.find(c=>c.address===a||c.address===0)||null;
 function paintLog(commands){
  const key=commands.length+':'+(commands[0]?.id||'')+':'+(commands[0]?.state||'')+':'+identity;if(key===logKey)return;logKey=key;
  logCount.textContent=commands.length?'('+commands.length+')':'';
  logBody.replaceChildren(...commands.slice(0,40).map(c=>{
   const tr=document.createElement('tr');
   const cells=[when(c.time),c.address===0?'All lights':pad(c.address)+(labelOf(c.address)?' · '+labelOf(c.address):''),Number(c.value)>0?String(c.value):'Off',c.state==='completed'?'Sent':c.state==='pending'?'Sending…':'Unknown'+(c.error?' · '+c.error:''),c.actor||'—'];
   cells.forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===3&&c.state!=='completed'&&c.state!=='pending')td.className='err';tr.append(td);});
   return tr;}));
 }
 function paint(){
  tab.hidden=!allowed();
  if(!allowed()){if(ws.dataset.tab==='lights')nav.querySelector('[data-tab="overview"]')?.click();return;}
  const d=data(),[lvl,words]=gate(),can=ready(),m=maxLevel();
  statusChip.dataset.level=lvl;statusChip.textContent=words;
  if(level.max!==String(m)){level.max=range.max=String(m);levelMax.textContent=String(m);setLevel(level.value);}
  if(identity!==state.chamber_id){identity=state.chamber_id;stepAt=null;logKey='';say('');}
  for(const b of panel.querySelectorAll('button'))if(!b.classList.contains('rail-cancel'))b.disabled=!can;
  stepOff.disabled=!can||stepAt===null;
  level.disabled=range.disabled=!can;
  stepOut.textContent=stepAt===null?'Not started':pad(stepAt)+(labelOf(stepAt)?' · '+labelOf(stepAt):'');
  const commands=d?.commands||[];
  for(const [a,row] of rows){
   const label=labelOf(a);row.labelText.textContent=label||'Name this address';row.labelBtn.classList.toggle('empty',!label);
   const c=latest(commands,a);let st='none',chip='No command',meta='Not yet commanded';
   if(busy&&(inflight===a||inflight===0)){st='sending';chip='Sending';meta='Waiting for the controller…';}
   else if(c){
    const ts=brief(c.time)+(c.actor?' · '+c.actor:'');
    if(c.state==='completed'){if(Number(c.value)>0){st='on';chip='Sent on · '+c.value;}else{st='off';chip='Sent off';}meta=(c.address===0?'All · ':'')+ts;}
    else if(c.state==='pending'){st='sending';chip='Sending';meta=ts;}
    else{st='unknown';chip='Unknown';meta=(c.error||'Outcome unknown')+' · '+ts;}
   }
   row.card.dataset.state=st;row.chip.textContent=chip;row.meta.textContent=meta;row.meta.title=meta;
  }
  paintLog(commands);
 }
 setInterval(paint,1000);paint();
})();
