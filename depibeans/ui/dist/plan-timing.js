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
