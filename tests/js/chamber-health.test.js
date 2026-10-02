const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../depibeans/ui/dist/app.js'),'utf8');
const fn=source.slice(source.indexOf('function attentionReason(){'),source.indexOf('\n// Chamber tabs:',source.indexOf('function attentionReason(){')));
function reason(state){return vm.runInNewContext(fn+';attentionReason()', {state,connected:()=>true});}
const healthy={active:{id:'new'},last_error:null,commissioned:false,experiment_ready:true,free_gb:410,recent:[{state:'needs_review'}],run_end:{state:'needs_review',time:10,light:{state:'not_sent',reason:'old failure'}}};
test('healthy running experiment stays green despite historical failures',()=>assert.equal(reason(healthy),null));
test('current errors and low disk remain visible during a run',()=>{assert.equal(reason({...healthy,last_error:'FPGA failure'}),'FPGA failure');assert.match(reason({...healthy,free_gb:2}),/Low disk/);});
test('unconfirmed shutdown remains visible until newer baseline',()=>{assert.match(reason({...healthy,active:null}),/Stop light not confirmed/);assert.equal(reason({...healthy,active:null,last_commanded_light:{time:11}}),null);});
test('unverified chamber does not turn green',()=>assert.equal(reason({...healthy,active:null,run_end:null,experiment_ready:false,manual_light_ready:false}),'No verified chamber controls'));
