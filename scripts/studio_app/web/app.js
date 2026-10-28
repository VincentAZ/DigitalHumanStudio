/* Digital Human Studio interface (Astra redesign), connected to the Python back end through the
   Qt WebChannel object `bridge` (scripts/studio_app/bridge.py). Payloads are JSON strings. */
'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// ---- icons (inline SVG, from the Astra design) ------------------------------------------------
const paths = {
  scene:'m12 3 9 5v8l-9 5-9-5V8l9-5Zm0 0v9m9-4-9 4-9-4m9 4v9',
  library:'M4 4h6v7H4zM14 4h6v7h-6zM4 15h6v5H4zM14 15h6v5h-6z',
  folder:'M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11H3V7Z',
  'chevron-right':'m9 5 7 7-7 7','chevron-down':'m6 9 6 6 6-6','chevron-up':'m6 15 6-6 6 6',
  shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6',
  help:'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4m0 3v.1',
  command:'M8 8V5a2 2 0 1 0-2 2h12a2 2 0 1 0-2-2v14a2 2 0 1 0 2-2H6a2 2 0 1 0 2 2V8',
  history:'M3 11a9 9 0 1 1 2 7M3 5v6h6m3-4v6l4 2',
  stop:'M6 6h12v12H6z',power:'M12 2v9M7 5a9 9 0 1 0 10 0',
  expand:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5',
  pause:'M8 5v14M16 5v14',play:'m8 4 12 8-12 8V4Z',
  reset:'M3 10a9 9 0 1 1 1 8M3 4v6h6',
  map:'m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16',
  cursor:'m4 3 15 9-7 1-3 7-5-17Z',sliders:'M4 7h16M4 17h16M8 4v6M16 14v6',
  'arrow-right':'M4 12h16m-6-6 6 6-6 6','arrow-up':'M12 20V4m-6 6 6-6 6 6','arrow-up-right':'M5 19 19 5M5 5h14v14',
  wind:'M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h6a3 3 0 1 1-3 3',
  info:'M12 11v6m0-10v.1',terminal:'m4 6 5 6-5 6m9 0h7',
  sparkles:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4',
  edit:'M13 5H4v15h15v-9M17 3l4 4-10 10-5 1 1-5L17 3Z',
  settings:'m10 3 4 0 1 3 3 1 2 3-2 3 0 3-3 2-3-1-3 1-3-2 0-3-2-3 2-3 3-1 1-3Z',
  close:'m6 6 12 12M6 18 18 6',plus:'M12 4v16M4 12h16',search:'M21 21l-5-5',
  layers:'m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5',
  cpu:'M6 6h12v12H6zM9 9h6v6H9zM9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4',
  lock:'M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4',link:'m10 13 4-4m-5 7-2 2a4 4 0 0 1-5-5l5-5a4 4 0 0 1 6 0m-2-3 2-2a4 4 0 0 1 5 5l-5 5a4 4 0 0 1-6 0',
  character:'M7 21v-7l-3-4 3-2h10l3 2-3 4v7m-5-7v7',file:'M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h8',
  alert:'m12 3 10 18H2L12 3Zm0 6v5m0 3v.1',eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z'
};
function icon(name){let circles='';if(['help','info'].includes(name))circles='<circle cx="12" cy="12" r="9"/>';if(name==='settings')circles='<circle cx="12" cy="12" r="3"/>';if(name==='search')circles='<circle cx="10" cy="10" r="7"/>';if(name==='character')circles='<circle cx="12" cy="4" r="2"/>';if(name==='eye')circles='<circle cx="12" cy="12" r="3"/>';return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${circles}<path d="${paths[name]||paths.scene}"/></svg>`;}
function hydrateIcons(root=document){$$('i[data-icon]',root).forEach(el=>el.innerHTML=icon(el.dataset.icon));}
hydrateIcons();

// ---- helpers -------------------------------------------------------------------------------
function escapeHtml(value){return String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4200);}
function timeText(t,decimal=false){t=Math.max(0,t||0);const minutes=Math.floor(t/60).toString().padStart(2,'0');const seconds=decimal?(t%60).toFixed(1).padStart(4,'0'):Math.floor(t%60).toString().padStart(2,'0');return `${minutes}:${seconds}`;}
function timestamp(){return new Date().toLocaleTimeString('en-GB',{hour12:false});}
function parse(json){try{return JSON.parse(json);}catch(e){return null;}}
function capitalize(s){s=String(s||'');return s?s[0].toUpperCase()+s.slice(1):'';}
function openModal(title,content){$('#modal-title').textContent=title;$('#modal-content').innerHTML=content;hydrateIcons($('#modal-content'));$('#modal').showModal();}
function closeModal(){$('#modal').close();}

// ---- state ---------------------------------------------------------------------------------
const ui = {
  bridge:null, boot:null, view:'live', filter:'all',
  session:{phase:'none'}, state:null, startedAt:0, lastJobLine:'',
  trail:[], commands:[], recordStart:null, mapCursor:{x:0,y:0}, lastPosition:null,
  provider:'', providerInfo:null, assistantBusy:false, pendingText:null, current:null, currentParagraph:null,
  host:{}, skills:[], project:{}, characters:[], composer:[], generation:null
};
const rpc=(name,...args)=>new Promise(resolve=>ui.bridge[name](...args,resolve));   // WebChannel slots return through a callback
const running=()=>ui.session.phase==='running';
const starting=()=>ui.session.phase==='starting';
const fallen=()=>!!(ui.state&&ui.state.fallen);

// ---- scene / map ---------------------------------------------------------------------------
function selectedScene(){const id=$('#scene-select').value;return (ui.boot?.scenes||[]).find(s=>s.id===id)||{name:'Flat floor',items:[],objects:[],room_half_size:6};}
function activeObjects(){if((running()||starting())&&ui.session.scene_objects)return ui.session.scene_objects;return selectedScene().objects||[];}
function objectPosition(o){const live=ui.state&&ui.state.objects&&ui.state.objects[o.name];const p=(live&&live.position)||o.center||[0,0,0];return {x:p[0],y:p[1],z:p[2]||0,attached:live?live.attached_to:null};}
function activeSceneName(){if(running()||starting())return ui.session.scene?capitalize(ui.session.scene.replace(/_/g,' ')):'Flat floor';return selectedScene().name;}
function activeItems(){if((running()||starting())&&ui.session.scene_items)return ui.session.scene_items;return selectedScene().items||[];}
function activeHalf(){if(ui.state&&ui.state.room_half_size)return ui.state.room_half_size;return selectedScene().room_half_size||6;}
function relativePosition(){if(!ui.state||!ui.state.root_xy)return null;const spawn=ui.state.spawn_xy||[0,0];return {x:ui.state.root_xy[0]-spawn[0],y:ui.state.root_xy[1]-spawn[1]};}
function relativeDestination(){if(!ui.state||!ui.state.destination)return null;const spawn=ui.state.spawn_xy||[0,0];return {x:ui.state.destination[0]-spawn[0],y:ui.state.destination[1]-spawn[1]};}
const MAP={w:460,h:320,pad:16};
function mapGeom(){const half=activeHalf();const scale=(MAP.h-2*MAP.pad)/(2*half);return {half,scale,cx:MAP.w/2,cy:MAP.h/2};}
function mapPoint(x,y){const g=mapGeom();return [g.cx+x*g.scale,g.cy-y*g.scale];}
function itemPolygon(item){const [cx,cy]=item.center||[0,0];const [sx,sy]=item.size||[1,1];const a=(item.yaw_deg||0)*Math.PI/180;const c=Math.cos(a),s=Math.sin(a);return [[-sx/2,-sy/2],[sx/2,-sy/2],[sx/2,sy/2],[-sx/2,sy/2]].map(([dx,dy])=>mapPoint(cx+dx*c-dy*s,cy+dx*s+dy*c));}
function colourOf(item,alpha){const c=item.colour||[0.5,0.55,0.55];return `rgba(${Math.round(c[0]*255)},${Math.round(c[1]*255)},${Math.round(c[2]*255)},${alpha})`;}
function renderMap(){
  const g=mapGeom();const half=g.half;
  let s=`<rect width="${MAP.w}" height="${MAP.h}" fill="#181e21"/>`;
  const [x0,y0]=mapPoint(-half,half),[x1,y1]=mapPoint(half,-half);
  s+='<g stroke="#2f3a40" stroke-width=".5">';
  for(let m=-Math.floor(half);m<=Math.floor(half);m++){const [gx]=mapPoint(m,0);const [,gy]=mapPoint(0,m);s+=`<path d="M${gx} ${y0}V${y1}"/><path d="M${x0} ${gy}H${x1}"/>`;}
  s+='</g>';
  s+=`<rect x="${x0}" y="${y0}" width="${x1-x0}" height="${y1-y0}" rx="2" fill="none" stroke="#526066"/>`;
  for(const item of activeItems()){
    const pts=itemPolygon(item).map(p=>p.map(v=>v.toFixed(1)).join(',')).join(' ');
    s+=`<polygon points="${pts}" fill="${item.collision?colourOf(item,.32):'none'}" stroke="${colourOf(item,.8)}" stroke-width=".7" stroke-dasharray="${item.collision?'':'2 2'}"/>`;
    const [sx,sy]=item.size||[0,0];
    const name=String(item.name||item.kind);
    if(!['wall','marking'].includes(item.kind)&&Math.min(sx,sy)>=0.7&&!/_(load|leg_[a-z])$/.test(name)){const [lx,ly]=mapPoint(item.center[0],item.center[1]);s+=`<text class="map-item-label" x="${lx}" y="${ly+2}">${escapeHtml(name.replace(/_/g,' '))}</text>`;}
  }
  for(const o of activeObjects()){const p=objectPosition(o);const [ox,oy]=mapPoint(p.x,p.y);const [ax,ay]=mapPoint((o.approach||[p.x,p.y])[0],(o.approach||[p.x,p.y])[1]);s+=`<g class="map-object" data-object="${escapeHtml(o.name)}" style="cursor:pointer"><title>${escapeHtml(o.description||o.name)} — click to walk to it</title><circle cx="${ax}" cy="${ay}" r="2.2" fill="none" stroke="#d8b082" stroke-width=".6" stroke-dasharray="1.5 1.5"/><circle cx="${ox}" cy="${oy}" r="${p.attached?6:4.5}" fill="${p.attached?'#e8c58d':'#f0d9a8'}" stroke="#8f7a56" stroke-width=".8"/><text class="map-item-label" x="${ox}" y="${oy-7}">${escapeHtml(o.name)}${p.attached?' · in hand':''}</text></g>`;}
  const [sx,sy]=mapPoint(0,0);s+=`<path d="M${sx-5} ${sy}h10m-5-5v10" stroke="#6b808b" stroke-width=".7"/><text x="${sx-8}" y="${sy+13}" font-size="6" fill="#627983" font-family="Arial">SPAWN</text>`;
  s+=`<text class="map-bounds-note" x="${x1+6}" y="${y1-2}">±${half} m</text>`;
  if(ui.trail.length>1)s+=`<path d="${ui.trail.map((p,i)=>`${i?'L':'M'}${mapPoint(p.x,p.y).map(v=>v.toFixed(1)).join(' ')}`).join(' ')}" stroke="#93a49a" stroke-width="1" stroke-dasharray="3 3" fill="none"/>`;
  const dest=relativeDestination();
  if(dest){const [dx,dy]=mapPoint(dest.x,dest.y);s+=`<circle cx="${dx}" cy="${dy}" r="8" fill="#cc9c6c10" stroke="#d8b082"/><circle cx="${dx}" cy="${dy}" r="2" fill="#d8b082"/>`;}
  const pos=relativePosition();
  if(pos&&running()){const [px,py]=mapPoint(pos.x,pos.y);const yawDeg=(ui.state.yaw||0)*180/Math.PI;const colour=fallen()?'#e68d82':ui.state.state==='walking'?'#bdd8c1':ui.state.state==='paused'?'#9aa3a6':'#bdcbbf';s+=`<circle cx="${px}" cy="${py}" r="13" fill="#c1c7b610"/><path d="M0-7 5 6 0 3-5 6Z" transform="translate(${px},${py}) rotate(${90-yawDeg})" fill="${colour}" stroke="#d1d9cf" stroke-width=".5"/>`;}
  $('#room-map').innerHTML=s;
}
function mapCoords(event){const r=$('#room-map').getBoundingClientRect();const scale=Math.min(r.width/MAP.w,r.height/MAP.h);const ox=(r.width-MAP.w*scale)/2,oy=(r.height-MAP.h*scale)/2;const g=mapGeom();return {x:((event.clientX-r.left-ox)/scale-g.cx)/g.scale,y:(g.cy-(event.clientY-r.top-oy)/scale)/g.scale};}

// ---- commands ------------------------------------------------------------------------------
function addLog(command,accepted=true,reason='',latency='—',info=false){
  ui.commands.unshift({time:timestamp(),command,accepted,reason,latency,info});ui.commands=ui.commands.slice(0,120);renderLog();
}
function renderLog(){$('#command-count').textContent=ui.commands.length;$('#command-log').innerHTML=ui.commands.length?ui.commands.map(c=>`<div class="log-row${c.info?' info':''}"><span class="log-time">${c.time}</span><span class="log-command${c.info?' info':''}" title="${escapeHtml(c.command)}">${escapeHtml(c.command)}</span><span class="log-outcome ${c.accepted?'':'rejected'}" title="${escapeHtml(c.reason)}">${c.info?'':c.accepted?'✓ Accepted':`× ${escapeHtml(c.reason)}`}</span><span class="log-latency">${escapeHtml(c.latency)}</span></div>`).join(''):'<div class="log-row"><span class="muted">Commands and worker events appear here.</span></div>';}
function canCommand(label){
  if(!running()){addLog(label,false,'No running session');toast(starting()?'The session is still starting.':'Start a session before directing the character.');return false;}
  if(fallen()&&!['reset','quit','record','stop'].includes(label.split(' ')[0])){addLog(label,false,'Reset required');toast('Character has fallen. Reset to continue.');return false;}
  return true;
}
function send(command,label){
  rpc('sendCommand',JSON.stringify(command)).then(error=>{if(error){addLog(label,false,error);toast(error);}});
  return true;
}
function walkTo(x,y,frame='spawn'){
  const label=`walk to (${x.toFixed(2)}, ${y.toFixed(2)}) ${frame}`;
  if(!canCommand(label))return false;
  if(!Number.isFinite(x)||!Number.isFinite(y)){toast('Enter valid numeric coordinates.');return false;}
  if(ui.state&&ui.state.paused){addLog(label,false,'Session paused');toast('Resume the session before walking.');return false;}
  if(frame==='spawn'){const half=activeHalf();if(Math.abs(x)>half||Math.abs(y)>half){addLog(label,false,'Out of bounds');toast(`Destination is outside the ±${half} m room.`);return false;}}
  return send({cmd:'destination',x:Number(x.toFixed(3)),y:Number(y.toFixed(3)),frame},label);
}
function walkToObject(name){const label=`walk to ${name}`;if(!canCommand(label))return false;if(ui.state&&ui.state.paused){toast('Resume the session first.');return false;}return send({cmd:'destination',object:name,frame:'spawn'},label);}
function resetCharacter(){if(!canCommand('reset'))return;send({cmd:'reset'},'reset');}
function stopWalking(){if(!canCommand('stop'))return;send({cmd:'stop'},'stop');}
function togglePause(){if(!canCommand('pause'))return;const paused=!!(ui.state&&ui.state.paused);send({cmd:paused?'resume':'pause'},paused?'resume':'pause');}
function toggleRecording(){if(!canCommand('record'))return;const active=!!(ui.state&&ui.state.recording);send({cmd:'record',action:active?'stop':'start',name:`segment-${Math.floor(Date.now()/1000)}`},active?'record stop':'record start');}
function startSession(){
  if(running()||starting())return;
  rpc('startSession',$('#controller-select').value,$('#scene-select').value,$('#resolution-select').value,$('#mode-select').value,$('#character-select').value).then(error=>{
    if(error){toast(error);return;}
    ui.trail=[];ui.state=null;ui.recordStart=null;ui.startedAt=Date.now();ui.lastJobLine='';
    addLog(`start session · ${activeSceneName()}`,true,'','—',true);
  });
}
function endSession(){if(!running()){toast(starting()?'The session is still starting; use force stop if it must end now.':'No session to end.');return;}rpc('endSession').then(error=>{if(error)toast(error);else toast('Ending the session: the worker finishes the recording and the launcher records the evidence.');});}
function forceStop(){rpc('forceStop').then(result=>{toast(result||'Stop requested.');addLog('force stop',true,'','—',true);});}

// ---- rendering of the live view --------------------------------------------------------------
function updateUI(){
  const run=running(),start=starting(),fall=fallen(),state=ui.state||{};
  const title=run?capitalize(state.state||'standing'):start?'Starting':'Offline';
  const scene=activeSceneName();
  $('#session-badge').innerHTML=`<span class="status-dot" style="background:${run?'var(--mint)':start?'var(--accent)':'#7e8d94'}"></span>${run?'Session live':start?'Starting…':ui.session.phase==='failed'?'Session failed':ui.session.phase==='ended'?'Session ended':'No session'}`;
  $('#sidebar-scene').textContent=run||start?scene:'No session';
  $('#sidebar-session-status').textContent=run||start?`${ui.session.name||'launching'} · ${ui.session.phase}`:'Start one from the live scene';
  $('#session-details-label').textContent=run||start?(ui.session.name||'Session'):'Sessions';
  $('#viewport-scene').textContent=scene;
  $('#viewport-empty').hidden=run||start;$('#startup-overlay').hidden=!start;$('#preview-frame').hidden=!run;
  $('#end-session').innerHTML=icon(run?'stop':'play')+(run?'End session':start?'Starting…':'Start session');$('#end-session').disabled=start;$('#force-stop').disabled=!run&&!start;
  for(const id of ['scene-select','controller-select','resolution-select','mode-select','character-select'])$('#'+id).disabled=run||start;
  $('#scene-character-state').textContent=run&&state.skill?`Playing ${state.skill.name||state.skill.id}`:title;
  const sk=run&&state.skill;const frames=sk&&sk.frames?sk.frames:0;const frame=sk?Math.min(frames,(sk.frame||0)+1):0;
  $('#skill-chip').hidden=!sk;if(sk)$('#skill-chip').innerHTML=`<span class="status-dot"></span>${escapeHtml(sk.name||sk.id)} <span class="chip-progress"><span style="width:${frames?Math.round(frame/frames*100):0}%"></span></span>${frames?`${frame}/${frames}`:''}${sk.loops_left>1?` ×${sk.loops_left}`:''}`;
  const sq=run&&state.sequence;$('#sequence-chip').hidden=!sq;if(sq)$('#sequence-chip').innerHTML=`<span class="status-dot"></span>${escapeHtml(sq.name||'sequence')} · step ${Math.max(0,sq.index)+1}/${sq.total}${sq.step?` · ${escapeHtml(String(sq.step).replace(/_/g,' '))}`:''}`;
  $('#character-label').textContent=run&&ui.session.character?ui.session.character:'SOMA-23';
  const phase=state.phase?String(state.phase):'';
  $('#state-value').innerHTML=`<span class="status-dot" style="background:${fall?'var(--red)':run?'var(--mint)':'#7e8d94'}"></span>${title}<small>${escapeHtml(phase)}</small>`;$('#state-value').style.color=fall?'var(--red)':run?'var(--mint)':'#9aa5aa';
  $('#sim-time').textContent=timeText(state.sim_time||0,true);
  $('#speed-value').textContent=run?(state.speed||0).toFixed(2):'0.00';
  $('#distance-value').textContent=run&&state.destination?(state.distance||0).toFixed(2):'—';
  $('#rate-value').textContent=run&&state.steps_per_wall_second?state.steps_per_wall_second.toFixed(1):'—';
  $('#reset-value').textContent=state.resets||0;
  $('#pause-session').innerHTML=icon(state.paused?'play':'pause')+`<span>${state.paused?'Resume':'Pause'}</span>`;
  const rec=!!state.recording&&run;const recTime=rec&&ui.recordStart!=null?timeText(state.sim_time-ui.recordStart):'';
  $('#record-toggle').classList.toggle('recording',rec);$('#record-toggle').innerHTML=`<span class="record-dot" style="background:${rec?'#e2967f':'#859393'}"></span><span>${rec?'Recording':'Record'}</span>${rec?`<span class="record-time">${recTime}</span>`:''}`;
  $('#record-chip').hidden=!rec;$('#record-label').textContent=`REC ${recTime}`;
  $('#fps-label').textContent=run?(state.paused?'PAUSED':`${state.mode==='kinematic'?'KINEMATIC · ':''}${(state.preview_size||[]).join('×')||'LIVE'}`):start?'STARTING':'OFFLINE';
  $('#fall-banner').hidden=!fall||!run;
  for(const id of ['stop-walking','pause-session','reset-character','record-toggle','walk-relative','push-character'])$('#'+id).disabled=!run;
  $('#pause-session').disabled=!run||fall;$('#walk-relative').disabled=!run||fall;$('#push-character').disabled=!run||fall;
  $('#global-session-state').textContent=run?`${scene} · ${fall?'Fallen — reset required':title}`:start?'Starting session…':'No active session';$('#global-session-state').style.color=fall?'var(--red)':'';
  $('#assistant-context').textContent=run||start?scene:'No session';$('#assistant-state').textContent=run?title:start?'Starting':'Offline';
  renderMap();
}
function onLiveState(state){
  const previous=ui.state;ui.state=state;
  try{document.dispatchEvent(new CustomEvent('studio:state',{detail:state}));}catch(err){}
  if(state.recording&&!(previous&&previous.recording))ui.recordStart=state.sim_time;
  if(!state.recording)ui.recordStart=null;
  const pos=relativePosition();
  if(pos&&!state.paused){const last=ui.trail[ui.trail.length-1];if(!last||Math.hypot(last.x-pos.x,last.y-pos.y)>0.02){ui.trail.push(pos);if(ui.trail.length>3000)ui.trail.shift();}}
  updateUI();
}
function onSession(session){
  const before=ui.session.phase;ui.session=session;
  if(session.phase==='starting'&&before!=='starting'){ui.startedAt=ui.startedAt||Date.now();ui.trail=[];ui.state=null;}
  if(session.phase==='running'&&before!=='running'){toast(`Session ${session.name} is live. Click the map to walk.`);addLog('session running',true,'','—',true);}
  if(['ended','failed'].includes(session.phase)&&['starting','running'].includes(before)){
    ui.state=null;ui.startedAt=0;
    const outcome=session.outcome||{};
    const text=session.phase==='ended'?`Session ended cleanly (${outcome.steps??'?'} steps). Recording: ${session.recording||'see the session folder'}`:`Session failed: ${session.message||outcome.status||'see the job output'}`;
    toast(text);addLog(session.phase==='ended'?'session ended · evidence recorded':'session failed',session.phase==='ended',session.phase==='ended'?'':'see job output','—',true);
    $('#viewport-empty p').textContent=text;
    ui.bridge.projectFacts(json=>{ui.project=parse(json)||ui.project;renderProject();});
  }
  if(session.phase==='failed'&&before==='starting'&&session.message){$('#viewport-empty p').textContent=session.message;toast(session.message);}
  updateUI();
}
function tickStartup(){if(!starting())return;const elapsed=(Date.now()-(ui.startedAt||Date.now()))/1000;$('#startup-progress').style.width=`${Math.min(95,elapsed/75*100).toFixed(0)}%`;$('#startup-elapsed').textContent=`${elapsed.toFixed(0)} s · real sessions take about a minute`;$('#startup-text').textContent=ui.lastJobLine||'Launching the runtime…';}
function onAck(record){
  if(record.event==='command'){
    const c=record.command||{};let label=c.cmd||'command';
    if(c.cmd==='destination')label=c.object?`walk to ${c.object}`:`walk to (${Number(c.x).toFixed(2)}, ${Number(c.y).toFixed(2)}) ${c.frame||'spawn'}`;
    else if(c.cmd==='push')label=`push (${c.vx}, ${c.vy}) m/s`;
    else if(c.cmd==='play_skill')label=`play ${skillTitle(c.skill)}${c.loops>1?` ×${c.loops}`:''}${c.speed&&c.speed!==1?` @${c.speed}`:''}`;
    else if(c.cmd==='sequence')label=`sequence ${c.name||''} (${(c.steps||[]).length} steps)`;
    else if(c.cmd==='attach')label=`attach ${c.object} to ${c.body||'RightHand'}`;
    else if(c.cmd==='release')label=`release ${c.object}`;
    else if(c.cmd==='place_object')label=`place ${c.object}`;
    if(c.sequence_step!=null)label=`↳ ${label}`;
    else if(c.cmd==='record')label=`record ${c.action} ${c.name||''}`.trim();
    const ok=record.result==='accepted';
    addLog(label,ok,ok?'':`${String(record.result||'rejected').replace(/^rejected_/,'').replace(/_/g,' ')}${record.reason?` · ${record.reason}`:''}`,record.ack_latency_ms!=null?`${Number(record.ack_latency_ms).toFixed(1)} ms`:'—');
    if(c.cmd==='play_skill'&&ok&&!c.sequence_step)toast(`Playing ${skillTitle(c.skill)} (${Number(record.duration_s||0).toFixed(1)} s).`);
    if(c.cmd==='sequence'&&ok)toast(`Sequence started: ${(c.steps||[]).length} steps.`);
    return;
  }
  const extras={fall_detected:'reset required',session_started:record.scene?`scene ${String(record.scene).split('/').pop()}${record.mode==='kinematic'?' · kinematic':''}`:'flat floor',paused:record.wall_seconds!=null?`${Number(record.wall_seconds).toFixed(1)} s`:'',segment_saved:record.name||'',
    skill_finished:`${skillTitle(record.skill)}${record.interrupted?' · interrupted':''}`,sequence_step_done:`${record.sequence||''} · ${String(record.skill||'').replace(/_/g,' ')}`,sequence_finished:`${record.sequence||''} · ${record.status||''}${record.reason?' · '+record.reason:''}`,attached:`${record.object} → ${record.body}`,released:record.object||''};
  if(record.event==='sequence_finished')toast(`Sequence ${record.sequence||''} ${record.status}${record.reason?': '+record.reason:''}.`);
  addLog(`${String(record.event||'event').replace(/_/g,' ')}${extras[record.event]?' · '+extras[record.event]:''}`,record.event!=='fall_detected','', `t=${Number(record.sim_time||0).toFixed(1)}s`,true);
  if(record.event==='fall_detected')toast('The character has fallen. Reset to continue.');
}

// ---- views ---------------------------------------------------------------------------------
function setView(view){if(!['live','skills','characters','project'].includes(view))return;ui.view=view;$$('.view').forEach(el=>{const active=el.id===`${view}-view`;el.hidden=!active;el.classList.toggle('active',active);});$$('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});$('#breadcrumb-title').textContent={live:'Live scene',skills:'Skill library',characters:'Characters',project:'Project'}[view];try{history.replaceState(null,'',`#${view}`);}catch(e){}try{document.dispatchEvent(new CustomEvent('studio:view',{detail:view}));}catch(e){}if(view==='skills')renderSkills();if(view==='characters')renderCharacters();if(view==='project')renderProject();window.scrollTo({top:0,behavior:'instant'});}

// ---- skills --------------------------------------------------------------------------------
const CATEGORY_NAMES={locomotion:'Locomotion',dance:'Dance',gesture:'Gestures',idle:'Idle',action:'Actions',floor:'Floor',generated:'Generated',sequence:'Sequences'};
function skillTitle(id){const s=ui.skills.find(x=>x.id===id);return s?s.name:String(id||'').replace(/_/g,' ');}
function mannequin(x,y,scale=1,pose='standing'){
  const s=scale;const walking=pose==='walking';
  return `<g transform="translate(${x},${y}) scale(${s})" stroke="#bdd8c1" stroke-width="3" stroke-linecap="round" fill="none"><circle cx="0" cy="-118" r="9" fill="#bdd8c1" stroke="none"/><path d="M0-106v48"/><path d="M0-96l${walking?'-14 26':'-12 30'}"/><path d="M0-96l${walking?'15 24':'12 30'}"/><path d="M0-58l${walking?'-14 44 -3 14':'-8 44 -2 14'}"/><path d="M0-58l${walking?'16 40 8 18':'8 44 2 14'}"/></g>`;
}
function skillArt(skill){
  if(skill.thumbnail)return `<img src="${escapeHtml(skill.thumbnail)}" data-preview="${escapeHtml(skill.preview||'')}" data-still="${escapeHtml(skill.thumbnail)}" alt="" loading="lazy">`;
  if(skill.kind==='sequence')return `<svg viewBox="0 0 280 175" aria-hidden="true"><g opacity=".17" stroke="#b6c3b1" stroke-width=".5"><path d="M0 120 140 55 280 120M0 145 140 80 280 145M0 170 140 105 280 170" fill="none"/></g>${(skill.steps||[]).slice(0,4).map((st,i)=>`<g transform="translate(${60+i*55},150)">${mannequin(0,0,.55,st.skill==='walk_to'?'walking':'standing')}</g>`).join('')}${(skill.steps||[]).slice(0,3).map((st,i)=>`<path d="M${82+i*55} 118h20" stroke="#d8b082" stroke-width="1.2" stroke-dasharray="2 2"/>`).join('')}</svg>`;
  return `<svg viewBox="0 0 280 175" aria-hidden="true"><g opacity=".17" stroke="#b6c3b1" stroke-width=".5"><path d="M0 120 140 55 280 120M0 145 140 80 280 145M0 170 140 105 280 170M35 175 140 130 245 175M35 105 175 170M70 88 210 153M105 72 245 137M245 105 105 170M210 88 70 153M175 72 35 137" fill="none"/></g><ellipse cx="140" cy="152" rx="49" ry="12" stroke="#c6b293" stroke-width=".7" fill="#bdac820a"/>${mannequin(140,150,.95,skill.category==='locomotion'?'walking':'standing')}</svg>`;
}
function poseBadge(skill){if(!skill.entry_pose)return '';const same=skill.entry_pose===skill.exit_pose;return `<span class="pose-badge" title="Starts ${skill.entry_pose}, ends ${skill.exit_pose}">${same?escapeHtml(skill.entry_pose):`${escapeHtml(skill.entry_pose)} → ${escapeHtml(skill.exit_pose)}`}</span>`;}
function renderFilters(){
  const counts={};for(const s of ui.skills)counts[s.category]=(counts[s.category]||0)+1;
  const order=['locomotion','dance','gesture','idle','action','floor','generated','sequence'];const cats=order.filter(c=>counts[c]).concat(Object.keys(counts).filter(c=>!order.includes(c)));
  $('#skill-filters').innerHTML=`<button data-filter="all" class="${ui.filter==='all'?'selected':''}">All skills</button>`+cats.map(c=>`<button data-filter="${escapeHtml(c)}" class="${ui.filter===c?'selected':''}">${escapeHtml(CATEGORY_NAMES[c]||capitalize(c))} <small>${counts[c]}</small></button>`).join('');
  $$('#skill-filters [data-filter]').forEach(b=>b.onclick=()=>{ui.filter=b.dataset.filter;renderSkills();});
}
function renderSkills(){
  renderFilters();
  const query=$('#skill-search').value.toLowerCase();
  const filtered=ui.skills.filter(s=>(ui.filter==='all'||ui.filter===s.category)&&`${s.name} ${s.description} ${s.category} ${(s.tags||[]).join(' ')} ${s.id}`.toLowerCase().includes(query));
  $('#skill-grid').innerHTML=filtered.map(s=>`<article class="skill-card" data-card="${escapeHtml(s.id)}"><div class="skill-art">${skillArt(s)}<span class="skill-preview-badge">${s.available?'CONTROLLER':s.kind==='sequence'?'SEQUENCE':s.category==='generated'?'GENERATED':'CLIP'}</span><span class="skill-duration">${escapeHtml(s.duration||'')}${s.loop?' · loop':''}</span></div><div class="skill-card-content"><h3>${escapeHtml(s.name)}${s.available?'<span>● Ready</span>':''}</h3><p>${escapeHtml(s.description)}</p><div class="skill-tags">${poseBadge(s)}${(s.tags||[s.category]).filter(t=>!['SOMA-23','mocap','standing','crouching','floor','in place'].includes(t)).slice(0,4).map(t=>`<span>${escapeHtml(t)}</span>`).join('')}</div><div class="skill-bottom"><span title="${escapeHtml(s.licence||'')}${s.attribution?' · '+escapeHtml(s.attribution):''}"><i data-icon="shield"></i>${escapeHtml(s.licence||s.source||'')}</span><span class="skill-buttons">${s.available?'':`<button class="icon-button" data-details="${escapeHtml(s.id)}" title="Details" aria-label="Details"><i data-icon="info"></i></button><button class="icon-button" data-compose="${escapeHtml(s.id)}" title="Add to sequence" aria-label="Add to sequence"><i data-icon="plus"></i></button>`}<button class="button" data-skill="${escapeHtml(s.id)}"><i data-icon="play"></i>${s.available?'Try in scene':'Play'}</button></span></div></div></article>`).join('');
  $('#skill-empty').hidden=filtered.length>0;$('#skill-count').textContent=ui.skills.length;$('#nav-skill-count').textContent=ui.skills.length;hydrateIcons($('#skill-grid'));
  $$('[data-skill]').forEach(b=>b.onclick=()=>playSkill(b.dataset.skill));
  $$('[data-details]').forEach(b=>b.onclick=()=>skillModal(b.dataset.details));
  $$('[data-compose]').forEach(b=>b.onclick=()=>composerAdd({skill:b.dataset.compose}));
  $$('.skill-art img[data-preview]').forEach(img=>{if(!img.dataset.preview)return;img.onmouseenter=()=>{img.src=img.dataset.preview;};img.onmouseleave=()=>{img.src=img.dataset.still;};});
  renderComposer();
}
function playSkill(id,options={}){
  const skill=ui.skills.find(s=>s.id===id);if(!skill)return;
  if(skill.available){setView('live');if(running())walkTo(2,0,'local');else toast('Start a session, then click the map or use Walk relative to try the walker.');return;}
  if(!canCommand(`play ${skill.name}`))return;
  if(skill.kind==='sequence'){rpc('runSequence',skill.id,JSON.stringify(skill.steps||[])).then(json=>{const r=parse(json)||{};if(r.error)toast(r.error);else setView('live');});return;}
  rpc('playSkill',id,JSON.stringify({loops:options.loops||1,speed:options.speed||1})).then(json=>{const result=parse(json)||{};if(result.error){toast(result.error);return;}if(result.result&&result.result!=='accepted')toast(`Rejected: ${String(result.result).replace(/^rejected_/,'').replace(/_/g,' ')}${result.reason?' · '+result.reason:''}`);else setView('live');});
}
function skillModal(id){
  const s=ui.skills.find(x=>x.id===id);if(!s)return;
  const prov=s.provenance||{};
  const rows=[['Category',CATEGORY_NAMES[s.category]||s.category],['Duration',s.duration_s?`${s.duration_s.toFixed(2)} s · ${s.frames||'?'} frames`:'—'],['Pose',s.entry_pose?`starts ${s.entry_pose}, ends ${s.exit_pose}`:'—'],['Travel',s.travel_m!=null?`${s.travel_m.toFixed(2)} m${s.turn_deg?`, turns ${s.turn_deg.toFixed(0)}°`:''}`:'—'],['Source',`${s.source||'—'}${s.clip?` · ${s.clip}`:''}`],['Licence',`${s.licence||'—'}${s.attribution?` · ${s.attribution}`:''}`],['Provenance',[prov.actor?`actor ${prov.actor}`:'',prov.protomotions_revision?`ProtoMotions ${prov.protomotions_revision.slice(0,10)}`:'',prov.model?`model ${prov.model}`:'',prov.prompt?`prompt “${prov.prompt}”`:'',prov.created_utc||''].filter(Boolean).join(' · ')||'—'],['Folder',s.folder||'']];
  openModal(s.name,`<div class="skill-detail"><div class="skill-detail-art">${s.preview?`<img src="${escapeHtml(s.preview)}" alt="">`:skillArt(s)}</div><p>${escapeHtml(s.description)}</p>${s.kind==='sequence'?`<ol class="step-list">${(s.steps||[]).map(st=>`<li>${escapeHtml(stepLabel(st))}</li>`).join('')}</ol>`:''}<dl class="facts">${rows.map(([k,v])=>`<div><dt>${k}</dt><dd class="${k==='Folder'?'path':''}">${escapeHtml(v)}</dd></div>`).join('')}</dl><div class="modal-actions"><button class="button" data-open="path:${escapeHtml(s.folder||'')}">Open folder</button>${s.kind!=='sequence'?`<button class="button" id="play-slow">Play at half speed</button><button class="button" id="play-twice">Play twice</button>`:''}${s.category==='generated'||s.kind==='sequence'?`<button class="button" id="delete-skill">Remove from library</button>`:''}<button class="button primary" id="play-now"><i data-icon="play"></i>Play in scene</button></div></div>`);
  $$('#modal-content [data-open]').forEach(b=>b.onclick=()=>rpc('openResource',b.dataset.open).then(error=>{if(error)toast(error);}));
  $('#play-now').onclick=()=>{closeModal();playSkill(id);};
  if($('#play-slow'))$('#play-slow').onclick=()=>{closeModal();playSkill(id,{speed:0.5});};
  if($('#play-twice'))$('#play-twice').onclick=()=>{closeModal();playSkill(id,{loops:2});};
  if($('#delete-skill'))$('#delete-skill').onclick=()=>{rpc('skillAction','delete',id).then(error=>{if(error)toast(error);else{closeModal();toast('Removed from the library.');}});};
}
// ---- sequence composer
function stepLabel(st){if(st.skill==='walk_to')return st.object?`walk to ${st.object}`:`walk to (${st.x}, ${st.y})`;if(st.skill==='wait')return `wait ${st.seconds||1} s`;if(st.skill==='attach')return `attach ${st.object} to ${st.body||'RightHand'}`;if(st.skill==='release')return `release ${st.object}`;if(st.skill==='stand')return 'stand';let label=skillTitle(st.skill);if(st.loops>1)label+=` ×${st.loops}`;if(st.attach)label+=` (take ${st.attach.object})`;if(st.release)label+=` (put down ${st.release.object})`;return label;}
function composerAdd(step){ui.composer.push(step);renderComposer();toast(`Added: ${stepLabel(step)}`);}
function renderComposer(){
  const bar=$('#composer');bar.hidden=ui.composer.length===0;$('#composer-count').textContent=`${ui.composer.length} step${ui.composer.length===1?'':'s'}`;
  $('#composer-steps').innerHTML=ui.composer.map((st,i)=>`<span class="composer-step"><b>${i+1}</b>${escapeHtml(stepLabel(st))}${st.skill!=='walk_to'&&st.skill!=='wait'&&st.skill!=='stand'&&st.skill!=='attach'&&st.skill!=='release'?`<button data-grab="${i}" title="Take an object during this clip">✋</button>`:''}<button data-remove="${i}" aria-label="Remove step">×</button></span>`).join('');
  $$('#composer-steps [data-remove]').forEach(b=>b.onclick=()=>{ui.composer.splice(Number(b.dataset.remove),1);renderComposer();});
  $$('#composer-steps [data-grab]').forEach(b=>b.onclick=()=>grabModal(Number(b.dataset.grab)));
  const objects=activeObjects();$('#composer-walk').innerHTML='<option value="">Add walk to…</option>'+objects.map(o=>`<option value="object:${escapeHtml(o.name)}">walk to ${escapeHtml(o.name)}</option>`).join('')+'<option value="spawn">walk back to the spawn</option>';
}
function grabModal(index){
  const step=ui.composer[index];const objects=activeObjects();
  openModal('Take or put down an object during this clip',`<p>${escapeHtml(stepLabel(step))}: the object snaps to the hand at the chosen frame and follows it until it is put down.</p><label class="modal-field">Take<select id="grab-object"><option value="">nothing</option>${objects.map(o=>`<option value="${escapeHtml(o.name)}" ${step.attach&&step.attach.object===o.name?'selected':''}>${escapeHtml(o.name)}</option>`).join('')}</select></label><div class="settings-row"><label class="modal-field">Hand<select id="grab-hand"><option>RightHand</option><option ${step.attach&&step.attach.body==='LeftHand'?'selected':''}>LeftHand</option></select></label><label class="modal-field">At frame<input id="grab-frame" type="number" min="0" value="${step.attach?step.attach.at_frame||0:30}"></label></div><label class="modal-field">Put down at the end<select id="grab-release"><option value="">keep holding</option>${objects.map(o=>`<option value="${escapeHtml(o.name)}" ${step.release&&step.release.object===o.name?'selected':''}>${escapeHtml(o.name)}</option>`).join('')}</select></label><div class="modal-actions"><button class="button primary" id="grab-save">Apply</button></div>`);
  $('#grab-save').onclick=()=>{const obj=$('#grab-object').value;const rel=$('#grab-release').value;if(obj)step.attach={object:obj,body:$('#grab-hand').value,at_frame:Number($('#grab-frame').value)||0};else delete step.attach;if(rel)step.release={object:rel};else delete step.release;closeModal();renderComposer();};
}
function composerRun(){if(!ui.composer.length)return;if(!canCommand('sequence'))return;rpc('runSequence','composed',JSON.stringify(ui.composer)).then(json=>{const r=parse(json)||{};if(r.error)toast(r.error);else setView('live');});}
function composerSave(){
  if(!ui.composer.length)return;
  openModal('Save the sequence as a skill',`<label class="modal-field">Name (letters, digits, underscores)<input id="seq-name" placeholder="fetch_the_cup" autocomplete="off"></label><label class="modal-field">Description<input id="seq-description" placeholder="Walks to the cup, picks it up and brings it back" autocomplete="off"></label><ol class="step-list">${ui.composer.map(st=>`<li>${escapeHtml(stepLabel(st))}</li>`).join('')}</ol><div class="modal-actions"><button class="button primary" id="seq-save">Save</button></div>`);
  $('#seq-name').focus();
  $('#seq-save').onclick=()=>{const name=$('#seq-name').value.trim().toLowerCase().replace(/[\s-]+/g,'_');const description=$('#seq-description').value.trim()||`Sequence of ${ui.composer.length} steps`;rpc('saveSequence',name,description,JSON.stringify(ui.composer)).then(json=>{const r=parse(json)||{};if(r.error){toast(r.error);return;}closeModal();ui.composer=[];toast(`Saved ${name} to the library.`);});};
}
// ---- text-to-motion generation
function createSkillModal(){
  const available=!!(ui.boot&&ui.boot.generation_available);
  openModal('Create a skill',`<p>Describe a motion in plain words. ${available?'The local text-to-motion model (Kimodo, SOMA skeleton) generates it and the clip joins the library.':'Text-to-motion generation is not installed on this machine yet; the description goes to the assistant instead.'}</p><label class="modal-field">Motion description<input id="new-skill-description" placeholder="A person waves hello with the right hand" autocomplete="off"></label><div class="settings-row"><label class="modal-field">Seconds<input id="new-skill-seconds" type="number" min="1" max="10" step="0.5" value="4"></label><label class="modal-field">Name (optional)<input id="new-skill-name" placeholder="wave_hello" autocomplete="off"></label></div><div class="modal-info" id="generation-status">${available?'Generation takes one to three minutes. The physics session keeps running meanwhile.':'See docs/MOTION_GENERATION.md for the install steps.'}</div><div class="modal-actions">${available?'<button class="button primary" id="generate-skill"><i data-icon="sparkles"></i>Generate</button>':'<button class="button primary" id="preview-idea">Send to the assistant</button>'}</div>`);
  $('#new-skill-description').focus();
  if($('#generate-skill'))$('#generate-skill').onclick=()=>{const description=$('#new-skill-description').value.trim();if(!description){$('#new-skill-description').focus();return;}const name=$('#new-skill-name').value.trim().toLowerCase().replace(/[\s-]+/g,'_');rpc('generateSkill',description,Number($('#new-skill-seconds').value)||4,name,0).then(error=>{if(error){toast(error);return;}$('#generate-skill').disabled=true;$('#generate-skill').innerHTML='<span class="spinner small"></span>Generating…';$('#generation-status').textContent='Generating the motion… this takes one to three minutes.';});};
}
function onGeneration(p){
  ui.generation=p;const status=$('#generation-status');
  if(p.status==='running'){if(status)status.textContent=`Generating “${p.description}”…`;return;}
  if(p.status==='failed'){toast(`Generation failed: ${p.error||'see .runtime/assistant-generate.log'}`);if(status)status.textContent=`Failed: ${p.error||''}`;const b=$('#generate-skill');if(b){b.disabled=false;b.innerHTML=icon('sparkles')+'Generate';}return;}
  toast(`New skill ready: ${p.skill||p.name||'generated'}.`);if($('#modal').open&&status)closeModal();ui.filter='generated';$('#skill-search').value='';setView('skills');
}
// ---- characters
function renderCharacters(){
  const list=ui.characters||[];$('#character-count').textContent=list.length;$('#nav-character-count').textContent=list.length;
  $('#character-grid').innerHTML=list.map(c=>`<article class="skill-card character-card"><div class="skill-art">${c.thumbnail?`<img src="${escapeHtml(c.thumbnail)}" alt="">`:`<svg viewBox="0 0 280 175" aria-hidden="true"><ellipse cx="140" cy="152" rx="49" ry="12" stroke="#c6b293" stroke-width=".7" fill="#bdac820a"/>${mannequin(140,150,.95)}</svg>`}<span class="skill-preview-badge">${c.id?'RIG':'BUILT IN'}</span></div><div class="skill-card-content"><h3>${escapeHtml(c.name)}</h3><p>${escapeHtml(c.description||'')}</p><div class="skill-tags">${c.vertices?`<span>${c.vertices} vertices</span>`:''}${c.joints?`<span>${c.joints} joints</span>`:''}${c.mapped?`<span>${c.mapped}/23 bodies mapped</span>`:''}${(c.unmapped||[]).length?`<span title="${escapeHtml(c.unmapped.join(', '))}">${c.unmapped.length} unmapped</span>`:''}</div><div class="skill-bottom"><span title="${escapeHtml(c.licence_url||'')}"><i data-icon="shield"></i>${escapeHtml(c.licence||'')}${c.source?` · ${escapeHtml(c.source)}`:''}</span><button class="button" data-character="${escapeHtml(c.id)}"><i data-icon="character"></i>Use next</button></div></div></article>`).join('');
  hydrateIcons($('#character-grid'));
  $$('[data-character]').forEach(b=>b.onclick=()=>{$('#character-select').value=b.dataset.character;setView('live');toast(`${b.dataset.character||'Mannequin'} will be used by the next session.`);});
}
function fillCharacters(){$('#character-select').innerHTML=(ui.characters||[]).map(c=>`<option value="${escapeHtml(c.id)}">${escapeHtml(c.id?c.name:'Mannequin')}</option>`).join('');}

// ---- project -------------------------------------------------------------------------------
function renderProject(){
  const p=ui.project||{};
  $('#project-root').textContent=p.root||'';$('#fact-root').textContent=p.root||'—';$('#fact-image').textContent=p.image||'—';$('#fact-image').title=p.image||'';
  $('#fact-interface').textContent=p.python?`Python ${p.python} · PySide6 ${p.pyside} · Qt ${p.qt}`:'—';
  $('#fact-m1').textContent=p.milestone1||'—';$('#fact-m3').textContent=p.milestone3||'—';
  $('#project-notes').innerHTML=(p.progress||[]).map(h=>`<div class="project-note"><span class="status-dot"></span><div><strong>${escapeHtml(h)}</strong></div></div>`).join('')||'<div class="project-note"><div><p>No progress entries found.</p></div></div>';
}
function renderHost(){
  const h=ui.host||{};const gpu=h.gpu||{};
  const name=gpu.name||'GPU';const load=gpu.utilization!=null?`${gpu.utilization}%`:'—';
  const mem=gpu.memory_used!=null?`${(gpu.memory_used/1024).toFixed(1)} / ${(gpu.memory_total/1024).toFixed(0)} GB`:'—';
  $('#gpu-status').textContent=h.busy?'GPU busy':gpu.name?'GPU free':'GPU —';$('#gpu-dot').style.background=h.busy?'var(--accent)':'var(--mint)';
  $('#gpu-short-name').textContent=name.replace(/^NVIDIA\s+/,'');$('#gpu-load').textContent=load;$('#gpu-memory').textContent=mem;$('#gpu-mini-meter').style.width=`${gpu.utilization||0}%`;
  $('#container-status').textContent=`${(h.containers||[]).length} container${(h.containers||[]).length===1?'':'s'}`;
  $('#gpu-name').textContent=name.replace(/^NVIDIA\s+/,'');$('#gpu-detail').textContent=gpu.name?`${gpu.temperature} °C · ${gpu.power} W`:'nvidia-smi not available';
  $('#gpu-meter').style.width=`${gpu.utilization||0}%`;$('#gpu-load-value').textContent=load;$('#gpu-memory-value').textContent=mem;
  $('#project-lock').textContent=h.lock?'GPU lock held by a studio job':'GPU lock free';
  $('#project-containers').textContent=(h.containers||[]).length?(h.containers||[]).join(', '):'No running containers';
}

// ---- providers and assistant ---------------------------------------------------------------
function refreshProvider(){
  ui.provider=$('#provider-select').value;
  return rpc('providerInfo',ui.provider).then(json=>{const info=parse(json)||{};ui.providerInfo=info;
  const ready=info.has_key||info.key_optional;
  const keyText=info.has_key?'Key set':info.key_optional?'Local, no key':'No key';
  $('#provider-status').innerHTML=`<span class="status-dot" style="background:${ready?'var(--mint)':'var(--red)'}"></span>${keyText}<span>·</span>${escapeHtml(info.model||'default model')}<span>·</span>${escapeHtml(info.thinking||'default')} thinking`;
  $('.provider-logo').textContent=ui.provider==='anthropic'?'✳':ui.provider==='lmstudio'?'◈':'✧';
  $('#assistant-footnote').textContent=ready?'The assistant only does what the buttons can do':info.key_status||'';});
}
function settingsModal(){
  const info=ui.providerInfo||{};const placeholder=info.stored_key?'A key is stored; paste a new one to replace it':info.has_key?`Key from the environment (${info.env}); paste one to store it`:info.key_optional?'Not required for a local server':'Paste an API key';
  openModal(`${escapeHtml(info.title||ui.provider)} settings`,`<p>${escapeHtml(info.key_status||'')}</p><label class="modal-field" style="margin-top:17px">API key<div class="key-row"><input id="settings-key" type="password" placeholder="${escapeHtml(placeholder)}" autocomplete="off"><button class="icon-button" id="show-key" aria-label="Show key" type="button"><i data-icon="eye"></i></button></div></label><div class="settings-row"><label class="modal-field">Model<input id="settings-model" value="${escapeHtml(info.model||'')}" autocomplete="off" list="model-options"><datalist id="model-options">${(info.models||[]).map(m=>`<option value="${escapeHtml(m)}">`).join('')}</datalist><div class="model-list" id="model-list">${(info.models||[]).map(m=>`<button type="button" data-model="${escapeHtml(m)}">${escapeHtml(m)}</button>`).join('')}</div></label><button class="button" id="fetch-models" type="button">Fetch models</button></div><label class="modal-field">Thinking level<select id="settings-thinking">${(ui.boot.thinking_levels||['default']).map(v=>`<option ${v===(info.thinking||'default')?'selected':''}>${v}</option>`).join('')}</select></label>${info.kind!=='agent_sdk'?`<label class="modal-field">Base URL<input id="settings-url" value="${escapeHtml(info.base_url||'')}" autocomplete="off"></label>`:''}<div class="modal-info">Stored in ~/.config/digital-human-studio/providers.json (mode 600), never in the project.${info.kind==='agent_sdk'?' Claude needs an Anthropic API key; the claude.ai sign-in cannot be used by applications.':''}</div><div class="modal-actions"><button class="button ghost" id="forget-key" type="button">Forget stored key</button><button class="button primary" id="save-provider" type="button">Save</button></div>`);
  const bindModels=()=>$$('#model-list [data-model]').forEach(b=>b.onclick=()=>{$('#settings-model').value=b.dataset.model;});
  bindModels();
  $('#show-key').onclick=()=>{const k=$('#settings-key');k.type=k.type==='password'?'text':'password';};
  $('#fetch-models').onclick=()=>{$('#fetch-models').disabled=true;$('#fetch-models').textContent='Fetching…';ui.bridge.fetchModels(ui.provider,$('#settings-key').value.trim(),$('#settings-url')?.value.trim()||'');};
  ui.onModels=payload=>{const button=$('#fetch-models');if(button){button.disabled=false;button.textContent='Fetch models';}if(payload.error){toast(`Fetch models: ${payload.error}`);return;}const list=$('#model-list');if(list){list.innerHTML=payload.models.map(m=>`<button type="button" data-model="${escapeHtml(m)}">${escapeHtml(m)}</button>`).join('');$('#model-options').innerHTML=payload.models.map(m=>`<option value="${escapeHtml(m)}">`).join('');bindModels();if(!payload.models.includes($('#settings-model').value)&&payload.models.length)$('#settings-model').value=payload.models[0];}toast(`${payload.models.length} models listed.`);};
  $('#forget-key').onclick=()=>{rpc('forgetKey',ui.provider).then(()=>{refreshProvider();$('#settings-key').placeholder='Stored key removed';toast('Stored key removed.');});};
  $('#save-provider').onclick=()=>{rpc('saveProvider',ui.provider,JSON.stringify({api_key:$('#settings-key').value,model:$('#settings-model').value,thinking:$('#settings-thinking').value,base_url:$('#settings-url')?.value||''})).then(error=>{if(error){toast(error);return;}closeModal();refreshProvider();toast('Settings saved. They apply to the next conversation.');});};
}
function scrollChat(){$('#chat-messages').scrollTo({top:$('#chat-messages').scrollHeight,behavior:'smooth'});}
function assistantMessage(){const el=document.createElement('div');el.className='assistant-message';el.innerHTML=`<div class="message-author"><span class="small-spark">✳</span>Assistant<span>${timestamp().slice(0,5)}</span></div>`;$('#chat-messages').append(el);ui.current=el;ui.currentParagraph=null;return el;}
function paragraph(){if(!ui.current)assistantMessage();if(!ui.currentParagraph){ui.currentParagraph=document.createElement('p');ui.current.append(ui.currentParagraph);}return ui.currentParagraph;}
function appendNote(text,cls=''){const el=assistantMessage();const p=document.createElement('p');if(cls)p.className=cls;p.textContent=text;el.append(p);ui.current=null;scrollChat();}
function setBusy(busy,text='Thinking…'){ui.assistantBusy=busy;$('#assistant-working').hidden=!busy;$('#assistant-working-text').textContent=text;$('#send-message').disabled=false;}
function sendChat(text){
  text=text.trim();if(!text)return;
  if(ui.assistantBusy){ui.pendingText=text;ui.bridge.assistantStop();$('#assistant-working-text').textContent='Stopping the current turn, then sending your message…';$('#chat-input').value='';return;}
  const user=document.createElement('div');user.className='user-message';user.textContent=text;const stamp=document.createElement('span');stamp.textContent=timestamp().slice(0,5);user.append(stamp);$('#chat-messages').append(user);
  $('#chat-input').value='';assistantMessage();setBusy(true);scrollChat();
  rpc('assistantSend',ui.provider,text).then(error=>{if(error){ui.current=null;setBusy(false);appendNote(error,'error');toast(error);}});
}
function onAssistantEvent(e){
  if(e.kind==='text'){paragraph().textContent+=e.delta||'';}
  else if(e.kind==='tool_call'){
    if(!ui.current)assistantMessage();
    const d=document.createElement('details');d.className='tool-call';d.open=true;d.dataset.tool=e.name;
    d.innerHTML=`<summary><span class="tool-check running">…</span>${escapeHtml(e.name)}<span>running</span><i data-icon="chevron-down"></i></summary><code>${escapeHtml(e.name)}(${escapeHtml(JSON.stringify(e.arguments||{}))})</code>`;
    hydrateIcons(d);ui.current.append(d);ui.currentParagraph=null;$('#assistant-working-text').textContent=`Running ${e.name}…`;
  }
  else if(e.kind==='tool_result'){
    const pending=[...(ui.current?ui.current.querySelectorAll('details.tool-call'):[])].reverse().find(d=>d.dataset.tool===e.name&&!d.dataset.done)||null;
    const failed=!!(e.result&&e.result.error);const summary=JSON.stringify(e.result??{});
    if(pending){pending.dataset.done='1';pending.open=failed;const check=pending.querySelector('.tool-check');check.textContent=failed?'×':'✓';check.className=`tool-check${failed?' failed':''}`;pending.querySelector('summary>span:nth-child(2)').textContent=failed?'failed':'done';pending.querySelector('code').innerHTML+=`<br>→ ${escapeHtml(summary.length>600?summary.slice(0,600)+'…':summary)}`;}
    $('#assistant-working-text').textContent='Thinking…';
  }
  else if(e.kind==='error'){const p=document.createElement('p');p.className='error';p.textContent=e.message||'error';(ui.current||assistantMessage()).append(p);ui.currentParagraph=null;}
  else if(e.kind==='done'){
    if(ui.current&&e.text&&!ui.current.querySelector('p')){const p=document.createElement('p');p.textContent=e.text;ui.current.append(p);}
    ui.current=null;ui.currentParagraph=null;setBusy(false);
    if(ui.pendingText){const next=ui.pendingText;ui.pendingText=null;sendChat(next);}
  }
  scrollChat();
}
function newConversation(){ui.pendingText=null;ui.bridge.assistantStop();ui.bridge.assistantNew();ui.current=null;setBusy(false);$('#chat-messages').innerHTML='<div class="chat-day">NEW CONVERSATION</div>';appendNote('Tell me where she should go, what to record, or ask what the studio can do right now.');}

// ---- modals --------------------------------------------------------------------------------
function sessionModal(){
  if(running()||starting()){
    const s=ui.session;
    openModal(s.name||'Session',`<dl class="facts"><div><dt>Scene</dt><dd>${escapeHtml(activeSceneName())}</dd></div><div><dt>Controller</dt><dd>${escapeHtml(s.controller||'')}</dd></div><div><dt>Container</dt><dd>${escapeHtml(s.container||'')}</dd></div><div><dt>Started</dt><dd>${escapeHtml(s.started_utc||'')}</dd></div><div><dt>Output</dt><dd class="path">${escapeHtml(s.output||'')}</dd></div></dl><div class="modal-info">End session saves the recording and evidence. Force stop records a failed session.</div><div class="modal-actions"><button class="button" data-open="path:${escapeHtml(s.output||'')}">Open session folder</button><button class="button" data-open="path:${escapeHtml(s.evidence||'')}">Open evidence</button></div>`);
  } else {
    const sessions=(ui.project.sessions||[]);
    openModal('Recent sessions',`<p>Recorded live sessions, newest first. Each folder holds the recording (performance.mp4), the trajectory and the command log.</p><div class="session-list">${sessions.map(s=>`<button data-open="path:${escapeHtml(s.output)}"><span>${escapeHtml(s.name)}<br><small>${escapeHtml(s.created)} · ${escapeHtml(s.scene)} · ${escapeHtml(s.controller||'')}</small></span><small>${escapeHtml(s.status)}${s.steps?` · ${s.steps} steps`:''}</small></button>`).join('')||'<p>No sessions yet.</p>'}</div>`);
  }
  $$('#modal-content [data-open]').forEach(b=>b.onclick=()=>rpc('openResource',b.dataset.open).then(error=>{if(error)toast(error);}));
}
const showGuide=()=>openModal('A little direction goes a long way',`<p>Start a session, then direct the character by clicking the room map, with the manual controls, or by telling the assistant what to do.</p><div class="shortcut-row"><span>Click the room map</span><span>Walk to a destination</span></div><div class="shortcut-row"><span>Pause / resume</span><kbd>Space</kbd></div><div class="shortcut-row"><span>Reset character</span><kbd>R</kbd></div><div class="shortcut-row"><span>Record a segment</span><kbd>Shift R</kbd></div><div class="shortcut-row"><span>Send an assistant message</span><kbd>Ctrl Enter</kbd></div><div class="shortcut-row"><span>Search the skill library</span><kbd>/</kbd></div><div class="shortcut-row"><span>Click an object on the map</span><span>Walk to it</span></div><div class="shortcut-row"><span>Skill card ＋</span><span>Add it to a sequence</span></div><p style="margin-top:18px">Physical mode lets physics decide (the character can fall); kinematic playback plays clips exactly. After a fall, destinations are rejected until Reset. One session runs at a time because the GPU is shared. End session saves the recording and evidence; force stop records a failed session.</p>`);

// ---- wiring --------------------------------------------------------------------------------
function wire(){
  $$('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));$('.brand').onclick=e=>{e.preventDefault();setView('live');};$('#workspace-info').onclick=()=>setView('project');$('#session-nav').onclick=()=>setView('live');
  $('#end-session').onclick=()=>running()?endSession():startSession();$('#empty-start').onclick=startSession;
  $('#force-stop').onclick=()=>openModal('Force stop this session?',`<p>This stops the worker container immediately. The launcher records a failed session; the recording so far is kept in the session folder. Use End session for a clean finish.</p><div class="modal-actions"><button class="button" id="cancel-force">Keep session</button><button class="button" style="background:#57332f;border-color:#8c5147;color:#f6b8a3" id="confirm-force">Force stop</button></div>`);
  $('#modal').addEventListener('click',e=>{if(e.target.id==='cancel-force')closeModal();if(e.target.id==='confirm-force'){closeModal();forceStop();}if(e.target.id==='close-preview')closeModal();if(e.target.id==='preview-idea'){const value=$('#new-skill-description').value.trim();if(!value){$('#new-skill-description').focus();return;}closeModal();$('#chat-input').value=`Create a skill: ${value}`;$('#chat-input').focus();}if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
  $('#close-modal').onclick=closeModal;
  $('#scene-select').onchange=()=>{updateUI();};
  $('#stop-walking').onclick=stopWalking;$('#pause-session').onclick=togglePause;$('#reset-character').onclick=resetCharacter;$('#fall-reset').onclick=resetCharacter;$('#record-toggle').onclick=toggleRecording;
  $('#walk-relative').onclick=()=>{const x=$('#walk-x').value,y=$('#walk-y').value;if(!x.trim()||!y.trim())return toast('Enter both walking distances.');walkTo(Number(x),Number(y),'local');};
  $('#push-character').onclick=()=>{if(!canCommand('push'))return;const vx=Number($('#push-x').value),vy=Number($('#push-y').value);if(!Number.isFinite(vx)||!Number.isFinite(vy)||Math.abs(vx)>6||Math.abs(vy)>6)return toast('Enter a velocity between −6 and 6 m/s for both axes.');if(ui.state&&ui.state.paused)return toast('Resume the session before applying a push.');send({cmd:'push',vx,vy},`push (${vx}, ${vy}) m/s`);};
  $('#room-map').addEventListener('click',event=>{const g=event.target.closest&&event.target.closest('[data-object]');if(g){walkToObject(g.dataset.object);return;}const p=mapCoords(event);walkTo(p.x,p.y,'spawn');});
  $('#room-map').addEventListener('mousemove',e=>{const p=mapCoords(e);$('#map-coordinates').textContent=`x: ${p.x.toFixed(1)}   y: ${p.y.toFixed(1)}`;});
  $('#room-map').addEventListener('keydown',e=>{const delta={ArrowUp:[0,.5],ArrowDown:[0,-.5],ArrowLeft:[-.5,0],ArrowRight:[.5,0]}[e.key];const half=activeHalf();if(delta){e.preventDefault();ui.mapCursor.x=Math.max(-half,Math.min(half,ui.mapCursor.x+delta[0]));ui.mapCursor.y=Math.max(-half,Math.min(half,ui.mapCursor.y+delta[1]));$('#map-coordinates').textContent=`Target: ${ui.mapCursor.x.toFixed(1)}, ${ui.mapCursor.y.toFixed(1)} · Enter to walk`;}if(e.key==='Enter'||e.key===' '){e.preventDefault();walkTo(ui.mapCursor.x,ui.mapCursor.y,'spawn');}});
  $('#clear-trail').onclick=()=>{ui.trail=[];const pos=relativePosition();if(pos)ui.trail.push(pos);renderMap();};$('#clear-log').onclick=()=>{ui.commands=[];renderLog();};
  $('#fullscreen').onclick=()=>{$('.scene-panel').classList.toggle('expanded');$('#fullscreen').setAttribute('aria-label',$('.scene-panel').classList.contains('expanded')?'Collapse preview':'Expand preview');};
  $('#provider-select').onchange=()=>{refreshProvider();newConversation();};$('#provider-settings').onclick=settingsModal;
  $('#chat-form').onsubmit=e=>{e.preventDefault();sendChat($('#chat-input').value);};$('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();sendChat($('#chat-input').value);}};
  $('#interrupt-assistant').onclick=()=>{ui.bridge.assistantStop();$('#assistant-working-text').textContent='Stopping…';};
  $$('[data-prompt]').forEach(b=>b.onclick=()=>sendChat(b.dataset.prompt));$('#new-chat').onclick=newConversation;
  $('#skill-search').oninput=renderSkills;
  $('#create-skill').onclick=createSkillModal;
  $('#composer-run').onclick=composerRun;$('#composer-save').onclick=composerSave;$('#composer-clear').onclick=()=>{ui.composer=[];renderComposer();};
  $('#composer-add-wait').onclick=()=>composerAdd({skill:'wait',seconds:1});
  $('#composer-add-walk').onclick=()=>{const v=$('#composer-walk').value;if(!v)return toast('Choose where to walk.');if(v==='spawn')composerAdd({skill:'walk_to',x:0,y:0,frame:'spawn'});else composerAdd({skill:'walk_to',object:v.slice(7)});$('#composer-walk').value='';};
  $('#refresh-characters').onclick=()=>rpc('listCharacters').then(json=>{ui.characters=parse(json)||ui.characters;fillCharacters();renderCharacters();toast('Characters refreshed.');});
  $('#scene-select').addEventListener('change',renderComposer);
  $$('[data-resource]').forEach(b=>b.onclick=()=>rpc('openResource',b.dataset.resource).then(error=>{if(error)toast(error);}));
  $('#refresh-project').onclick=()=>ui.bridge.projectFacts(json=>{ui.project=parse(json)||ui.project;renderProject();toast('Project facts refreshed.');});
  $('#help-button').onclick=showGuide;$('#shortcuts-button').onclick=showGuide;$('#session-details').onclick=sessionModal;
  const toggleJobs=force=>{$('#job-drawer').hidden=typeof force==='boolean'?!force:!$('#job-drawer').hidden;$('#toggle-jobs').setAttribute('aria-expanded',String(!$('#job-drawer').hidden));};
  $('#toggle-jobs').onclick=()=>toggleJobs();$('#close-jobs').onclick=()=>toggleJobs(false);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('.scene-panel').classList.remove('expanded');return;}if(e.ctrlKey||e.metaKey||e.altKey||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||$('#modal').open||e.target.id==='room-map')return;if(e.key===' '&&ui.view==='live'&&e.target.tagName!=='BUTTON'){e.preventDefault();togglePause();}if(e.key.toLowerCase()==='r'&&ui.view==='live'){e.preventDefault();e.shiftKey?toggleRecording():resetCharacter();}if(e.key==='/'){e.preventDefault();setView('skills');$('#skill-search').focus();}});
  setInterval(tickStartup,500);
}

function jobLine(text){const pre=$('#job-output');pre.textContent=(pre.textContent+text).split('\n').slice(-400).join('\n');pre.scrollTop=pre.scrollHeight;const lines=text.split('\n').map(l=>l.trim()).filter(Boolean);if(lines.length)ui.lastJobLine=lines[lines.length-1].slice(0,110);}
function handleEvent(e){
  const p=e.payload;
  try{document.dispatchEvent(new CustomEvent('studio:'+e.kind,{detail:p}));}catch(err){}
  if(e.kind==='session')onSession(p);
  else if(e.kind==='ack')onAck(p);
  else if(e.kind==='host'){ui.host=p||{};renderHost();}
  else if(e.kind==='job')jobLine(p.text||'');
  else if(e.kind==='assistant')onAssistantEvent(p);
  else if(e.kind==='models'&&ui.onModels)ui.onModels(p);
  else if(e.kind==='skills'){ui.skills=p||[];if(ui.view==='skills')renderSkills();else{$('#nav-skill-count').textContent=ui.skills.length;}}
  else if(e.kind==='generation')onGeneration(p);
}
// The page polls the bridge about 15 times a second; events come back numbered and in order.
function pollTick(){
  if(ui.polling||!ui.bridge)return;ui.polling=true;
  rpc('poll',ui.cursor||0,ui.stateToken||'').then(json=>{
    ui.polling=false;const p=parse(json);if(!p)return;
    ui.cursor=p.seq;
    for(const e of p.events||[]){try{handleEvent(e);}catch(err){console.error('event',e.kind,err);}}
    if(p.state){ui.stateToken=p.state_token;onLiveState(p.state);}
    if(p.frame&&p.frame!==ui.frameToken){ui.frameToken=p.frame;$('#preview-frame').src=p.frame;}
    if(p.phase!==ui.session.phase&&!['ended','failed'].includes(p.phase)){ui.session.phase=p.phase;updateUI();}
  }).catch(()=>{ui.polling=false;});
}

function init(boot){
  ui.boot=boot;ui.skills=boot.skills||[];ui.project=boot.project||{};ui.cursor=boot.seq||0;ui.host=boot.host||{};
  $('#scene-select').innerHTML=boot.scenes.map(s=>`<option value="${escapeHtml(s.id)}" title="${escapeHtml(s.description)}">${escapeHtml(s.name)}</option>`).join('');
  if(boot.scenes.some(s=>s.id==='workcell'))$('#scene-select').value='workcell';
  $('#controller-select').innerHTML=boot.controllers.map(c=>`<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`).join('');
  $('#resolution-select').innerHTML=boot.previews.map(p=>`<option value="${p}" ${p==='960x540'?'selected':''}>${p.replace('x',' × ')}</option>`).join('');
  $('#mode-select').innerHTML=(boot.modes||[]).map(m=>`<option value="${escapeHtml(m.id)}" title="${escapeHtml(m.description)}">${escapeHtml(m.name)}</option>`).join('');
  ui.characters=boot.characters||[];fillCharacters();
  $('#provider-select').innerHTML=boot.providers.map(p=>`<option value="${escapeHtml(p.id)}">${escapeHtml(p.title)}</option>`).join('');
  $('#profile-initial').textContent=(boot.user||'u')[0].toUpperCase();$('#profile-name').innerHTML=`${escapeHtml(boot.user||'user')}<small>Local workspace</small>`;$('#workspace-root').textContent=boot.root||'Local project';
  wire();refreshProvider();renderSkills();renderCharacters();renderProject();renderLog();renderHost();
  $('#chat-messages').innerHTML='<div class="chat-day">TODAY</div>';appendNote('Tell me where she should go, what to record, or ask what the studio can do right now.');
  if(boot.session)onSession(boot.session);else updateUI();
  setView(location.hash.slice(1)||'live');
  setInterval(pollTick,66);
  try{document.dispatchEvent(new CustomEvent('studio:ready'));}catch(e){}
}

new QWebChannel(qt.webChannelTransport,channel=>{ui.bridge=channel.objects.bridge;ui.bridge.bootstrap(json=>{const boot=parse(json);if(!boot){document.body.innerHTML='<p style="padding:40px">The interface could not read the project state.</p>';return;}init(boot);});});
