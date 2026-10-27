/* Astra is a self-contained UI prototype. No API requests, project reads,
   credentials, simulation workers, or browser persistence are used. */
'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
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
  grid:'M3 3h18v18H3zM9 3v18M15 3v18M3 9h18M3 15h18',
  focus:'M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5M8 12h8m-4-4v8',
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
const state={session:'running',scene:'workcell',character:'standing',position:{x:1.4,y:.6},target:null,trail:[{x:0,y:0},{x:.7,y:.2},{x:1.4,y:.6}],recording:true,recordTime:24,simTime:42.6,resets:0,view:'live',grid:true,provider:'Claude',assistantBusy:false,assistantToken:0,commands:[],filter:'all',mapCursor:{x:0,y:0}};
let toastTimer, startTimer, motionTimer, assistantTimer;
function escapeHtml(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,3800);}
function timeText(t,decimal=false){const minutes=Math.floor(t/60).toString().padStart(2,'0');const seconds=decimal?(t%60).toFixed(1).padStart(4,'0'):Math.floor(t%60).toString().padStart(2,'0');return `${minutes}:${seconds}`;}
function timestamp(){return new Date().toLocaleTimeString('en-GB',{hour12:false});}
function addLog(command,accepted=true,reason='',latency='0.8 ms'){
  state.commands.unshift({time:timestamp(),command,accepted,reason,latency});state.commands=state.commands.slice(0,80);renderLog();
  $('#job-output').textContent+=`\n[${timestamp()}] ${command} → ${accepted?'accepted':`rejected: ${reason}`}`;
}
function renderLog(){$('#command-count').textContent=state.commands.length;$('#command-log').innerHTML=state.commands.length?state.commands.map(c=>`<div class="log-row"><span class="log-time">${c.time}</span><span class="log-command" title="${escapeHtml(c.command)}">${escapeHtml(c.command)}</span><span class="log-outcome ${c.accepted?'':'rejected'}" title="${escapeHtml(c.reason)}">${c.accepted?'✓ Accepted':`× ${escapeHtml(c.reason)}`}</span><span class="log-latency">${c.latency}</span></div>`).join(''):'<div class="log-row"><span class="muted">Commands will appear here.</span></div>';}

// Original vector artwork: a tiny orthographic scene, drawn locally with SVG.
const projectPoint=(x,y,z=0)=>[450+(x-y)*42,261+(x+y)*19-z*54];
const pointString=p=>p.map(v=>v.toFixed(2)).join(',');
const poly=(points,fill,stroke='#748080',extra='')=>`<polygon points="${points.map(pointString).join(' ')}" fill="${fill}" stroke="${stroke}" stroke-width=".6" ${extra}/>`;
function box(x,y,z,w,d,h,colors=['#7a8587','#414c50','#596569']){const p=(a,b,c)=>projectPoint(x+a,y+b,z+c);return poly([p(0,0,0),p(w,0,0),p(w,0,h),p(0,0,h)],colors[1])+poly([p(w,0,0),p(w,d,0),p(w,d,h),p(w,0,h)],colors[2])+poly([p(0,0,h),p(w,0,h),p(w,d,h),p(0,d,h)],colors[0]);}
function floorLine(x1,y1,x2,y2,color,width=1,extra=''){const a=projectPoint(x1,y1),b=projectPoint(x2,y2);return `<path d="M${a}L${b}" stroke="${color}" stroke-width="${width}" fill="none" ${extra}/>`;}
function mannequin(x,y,scale=1,pose='standing',color='sage'){
  const palette=color==='peach'?['#d4b29a','#aa8e7a','#75645a']:['#c5cec2','#9daa9c','#6c7d70'];
  const moving=pose==='walking',fallen=pose==='fallen';
  return `<g transform="translate(${x} ${y}) scale(${scale})"><ellipse cy="2" rx="23" ry="8" fill="#0b1415" opacity=".33" filter="url(#softShadow)"/><g transform="${fallen?'translate(-29 -6) rotate(79)':''}"><path d="M-10-47 ${moving?'Q-20-27-27-8':'Q-13-25-12-6'}" stroke="${palette[2]}" stroke-width="11" stroke-linecap="round"/><path d="M-10-47 ${moving?'Q-20-27-27-8':'Q-13-25-12-6'}" stroke="${palette[1]}" stroke-width="8" stroke-linecap="round"/><path d="M6-45 ${moving?'Q19-27 23-5':'Q11-23 10-3'}" stroke="${palette[0]}" stroke-width="10" stroke-linecap="round"/><path d="${moving?'M-31-4l-8 3q-4 4 2 5h15v-7':'M-15-3l-5 5q-1 3 5 3h9V0'}" fill="${palette[1]}"/><path d="${moving?'M21-2l-1 6 17 1q5-2 0-4l-8-4':'M6 0v5l14 1q5-1 1-4l-8-3'}" fill="${palette[0]}"/><path d="M-15-59q14-5 26 0l-3 17-18 1Z" fill="${palette[1]}" stroke="${palette[2]}" stroke-width="1"/><path d="M-18-90q15-8 29-1l3 19-5 15-22 1-6-17Z" fill="url(#bodyMaterial)" stroke="${palette[1]}" stroke-width=".7"/><path d="M-2-88v28M-16-76l27-2" stroke="#738575" stroke-width=".6" opacity=".6"/><path d="M-18-85 ${moving?'Q-26-69-16-60':'Q-24-68-25-51'}" stroke="${palette[2]}" stroke-width="8" stroke-linecap="round"/><path d="M-18-85 ${moving?'Q-26-69-16-60':'Q-24-68-25-51'}" stroke="${palette[1]}" stroke-width="6" stroke-linecap="round"/><path d="M12-85 ${moving?'Q23-67 28-59':'Q20-67 19-50'}" stroke="${palette[0]}" stroke-width="8" stroke-linecap="round"/><ellipse cx="${moving?28:19}" cy="${moving?-56:-47}" rx="3.7" ry="6" fill="${palette[0]}"/><ellipse cx="${moving?-16:-25}" cy="${moving?-58:-48}" rx="3.2" ry="5.5" fill="${palette[1]}"/><path d="M-5-94v-8h9v8" fill="${palette[1]}"/><ellipse cx="-1" cy="-110" rx="10" ry="13" fill="${palette[0]}"/><path d="M4-121q9 8 3 18l-8 6q9-3 10-13 1-7-5-11" fill="${palette[1]}"/><path d="m7-111 3 3-3 1" stroke="${palette[1]}" fill="${palette[0]}"/><circle cx="-12" cy="-27" r="2" fill="${palette[2]}" opacity=".4"/><circle cx="11" cy="-24" r="2" fill="${palette[2]}" opacity=".3"/></g></g>`;
}
function renderScene(){
  let s=`<svg viewBox="0 0 900 475" role="img" aria-label="${state.scene==='flat'?'Flat floor':'Work cell'} illustrated scene"><defs><linearGradient id="floorMaterial" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#444a4a"/><stop offset="1" stop-color="#31393c"/></linearGradient><linearGradient id="bodyMaterial"><stop stop-color="#7d8e7e"/><stop offset=".5" stop-color="#c9d2c5"/><stop offset="1" stop-color="#a7b5a3"/></linearGradient><linearGradient id="machineMaterial" x2="0" y2="1"><stop stop-color="#87918e"/><stop offset="1" stop-color="#657574"/></linearGradient><filter id="softShadow"><feGaussianBlur stdDeviation="3"/></filter><filter id="roomShadow"><feGaussianBlur stdDeviation="9"/></filter></defs>`;
  s+=`<ellipse cx="466" cy="332" rx="319" ry="104" fill="#10191b" opacity=".5" filter="url(#roomShadow)"/>`;
  s+=box(-4.8,-3.9,-.17,9.6,7.8,.17,['url(#floorMaterial)','#242c30','#2b3438']);
  if(state.grid){s+='<g id="scene-grid" opacity=".47">';for(let x=-4;x<=4;x++)s+=floorLine(x,-3.9,x,3.9,'#6b7575',.5);for(let y=-3;y<=3;y++)s+=floorLine(-4.8,y,4.8,y,'#6b7575',.5);s+='</g>';}
  // Low perimeter gives the authoring stage a clean dollhouse silhouette.
  if(state.scene==='workcell'){
    s+=box(-4.8,-3.9,0,.13,7.8,.28,['#7e8987','#4b5557','#66716f']);
    s+=box(-4.8,-3.9,0,9.6,.13,.28,['#808b88','#4f5a5b','#677370']);
    s+=box(-4.3,-3.48,0,2.65,1.18,.1,['#7b7e6e','#525d56','#5c655c']);
    // Storage rack, shelves, cross braces, and packed cartons.
    for(const [x,y] of [[-4.2,-3.4],[-1.75,-3.4],[-4.2,-2.38],[-1.75,-2.38]])s+=box(x,y,0,.07,.07,2.5,['#8b8e82','#505f5e','#68746f']);
    for(const z of [.12,1.1,2.13])s+=box(-4.2,-3.4,z,2.52,1.1,.07,['#87907b','#535e55','#70775e']);
    for(const [x,y,z,w,d,h] of [[-3.95,-3.2,.2,.67,.62,.66],[-3.19,-3.2,.2,.58,.63,.66],[-2.5,-3.16,.2,.56,.65,.43],[-3.95,-3.2,1.18,.9,.66,.69],[-2.8,-3.2,1.18,.74,.63,.7]]){
      s+=box(x,y,z,w,d,h,['#b0a184','#82755f','#9b8c71']);
      const a=projectPoint(x+w*.5,y,z+h),b=projectPoint(x+w*.5,y+d,z+h);s+=`<path d="M${a}L${b}" stroke="#c0b493" stroke-width="3" opacity=".7"/>`;
    }
    // Rear industrial machine, raised base, dark glass, display, emergency switch.
    s+=box(.2,-3.4,0,2.32,1.52,.16,['#606c6e','#303d42','#445056']);
    s+=box(.28,-3.34,.16,2.16,1.42,2.18,['#9fa8a1','#647574','#80908a']);
    s+=box(.48,-3.37,.67,1.28,.04,1.33,['#4f6264','#263a42','#334e54']);
    s+=box(.58,-3.4,.79,1.08,.025,1.08,['#334a4e','#1e343d','#2c4148']);
    const win=projectPoint(1.6,-3.42,1.7);s+=`<path d="m${win} -30 36m34-29-20 25" stroke="#a1bcc0" opacity=".14" stroke-width="4"/>`;
    s+=box(1.9,-3.42,1.18,.36,.05,.57,['#465e5f','#334b52','#3b555a']);
    const screen=projectPoint(2.06,-3.46,1.55);s+=`<circle cx="${screen[0]}" cy="${screen[1]}" r="2" fill="#a5c9ac"/>`;
    const red=projectPoint(2.04,-3.47,.98);s+=`<circle cx="${red[0]}" cy="${red[1]}" r="2.8" fill="#d59b72"/>`;
    s+=box(.45,-3.4,.28,1.92,.03,.16,['#556968','#4a5c5a','#6d7f79']);
    s+=box(1.97,-2.65,2.34,.08,.08,.43,['#b5bba1','#8d9a82','#99a993']);
    s+=box(1.95,-2.67,2.68,.12,.12,.12,['#b6c9a4','#82a178','#90ac83']);
    // Conveyor faces forward: rollers, rail, legs, and a small package.
    for(const [x,y] of [[1.1,-1.35],[3.6,-1.35],[1.1,-.44],[3.6,-.44]])s+=box(x,y,0,.09,.09,.85,['#98a9a9','#52666c','#72858a']);
    s+=box(1,-1.45,.77,2.9,1.18,.18,['#5a6d70','#3c5057','#61777e']);
    for(let x=1.12;x<3.85;x+=.19){const a=projectPoint(x,-1.4,.99),b=projectPoint(x,-.33,.99);s+=`<path d="M${a}L${b}" stroke="#adbcba" stroke-width="5"/><path d="M${a[0]-1},${a[1]-1}L${b[0]-1},${b[1]-1}" stroke="#d1d8cb" stroke-width="1" opacity=".5"/>`;}
    s+=box(.99,-1.5,.96,2.95,.06,.12,['#b3c0b9','#6b8388','#92a4a3']);s+=box(.99,-.3,.96,2.95,.06,.12,['#b3c0b9','#6b8388','#92a4a3']);
    s+=box(2.9,-1.19,1.02,.58,.63,.4,['#c0aa86','#9a8161','#af9874']);
    // Marked lanes and safety bollards.
    for(const y of [.25,1.75])s+=floorLine(-.7,y,3.9,y,'#bbac6e',2.3,'opacity=".68"');
    s+=floorLine(-.7,.25,-.7,1.75,'#bbac6e',2.3,'opacity=".68"');
    for(const [x,y] of [[.3,-1.65],[3.95,-1.75]]){s+=box(x,y,0,.17,.17,.05,['#4e5752','#2c393c','#394b4c']);s+=box(x+.04,y+.04,.05,.09,.09,.67,['#d7be7c','#ad9250','#c6aa62']);s+=box(x+.035,y+.035,.43,.1,.1,.13,['#393e36','#30382f','#3b4439']);}
    // Foreground pallet and stacked crates.
    s+=box(-3.7,1.3,0,1.5,1.15,.12,['#b1a184','#6d624f','#8c7c61']);
    for(let y=1.31;y<2.4;y+=.23)s+=box(-3.7,y,.12,1.5,.17,.06,['#b4a284','#83745c','#a09070']);
    s+=box(-3.6,1.38,.18,.65,.8,.55,['#8c9b90','#536c68','#6e867b']);s+=box(-2.86,1.38,.18,.56,.8,.55,['#8f9d92','#566c67','#758b7f']);
    s+=floorLine(-4.05,1.05,-1.9,1.05,'#b5a46a',1.4,'stroke-dasharray="6 4"');s+=floorLine(-1.9,1.05,-1.9,2.7,'#b5a46a',1.4,'stroke-dasharray="6 4"');
    // Ghosted scene labels sit on the stage, not over the character.
    const label=projectPoint(-1.4,-2.25,.05);s+=`<text x="${label[0]}" y="${label[1]}" fill="#98a5a1" font-family="Arial,sans-serif" font-size="7" letter-spacing="1.5" transform="rotate(24 ${label})" opacity=".5">WORK CELL / 01</text>`;
  }
  if(state.trail.length>1){s+=`<path d="${state.trail.map((p,i)=>`${i?'L':'M'}${projectPoint(p.x,p.y,.01)}`).join(' ')}" fill="none" stroke="#c1ab8a" stroke-width="1.3" stroke-dasharray="4 5" opacity=".65"/>`;}
  if(state.target){const p=projectPoint(state.target.x,state.target.y,.02);s+=`<ellipse cx="${p[0]}" cy="${p[1]}" rx="13" ry="6" stroke="#efbc89" stroke-width="1.5" fill="#dba67615"/><path d="M${p[0]-4} ${p[1]}h8m-4-3v6" stroke="#e7b28a" stroke-width="1"/>`;}
  const [cx,cy]=projectPoint(state.position.x,state.position.y);s+=`<ellipse cx="${cx}" cy="${cy+2}" rx="21" ry="9" stroke="#d3b28b" stroke-width="1" fill="#c5ad7f0a" opacity=".8"/>`;
  s+=mannequin(cx,cy,.86,state.character);s+='</svg>';$('#scene-illustration').innerHTML=s;
}
const mapPoint=(x,y)=>[230+x*33,118-y*23];
function renderMap(){
  let s='<defs><pattern id="mapGrid" width="33" height="23" patternUnits="userSpaceOnUse" x="230" y="118"><path d="M33 0H0V23" fill="none" stroke="#344046" stroke-width=".5"/></pattern></defs><rect width="460" height="235" fill="#181e21"/><rect x="42" y="23" width="376" height="188" fill="url(#mapGrid)"/>';
  s+='<rect x="65" y="26" width="330" height="184" rx="2" fill="none" stroke="#526066" stroke-width="1"/>';
  if(state.scene==='workcell')s+='<g fill="#364247" stroke="#5b6d73" stroke-width=".7"><rect x="85" y="42" width="83" height="24" rx="2"/><rect x="233" y="42" width="78" height="36" rx="2"/><rect x="263" y="86" width="94" height="23" rx="2"/><rect x="108" y="150" width="48" height="29" rx="2"/></g><g font-family="Arial,sans-serif" font-size="7" fill="#8e9da3" text-anchor="middle"><text x="126" y="57">RACK</text><text x="272" y="63">MACHINE</text><text x="310" y="100">CONVEYOR</text><text x="132" y="167">PALLET</text></g><path d="M207 115v35h148" fill="none" stroke="#8f835d" opacity=".6" stroke-dasharray="5 4"/>';
  s+='<path d="M225 118h10m-5-5v10" stroke="#6b808b" stroke-width=".7"/><text x="215" y="135" font-size="6" fill="#627983" font-family="Arial">SPAWN</text>';
  if(state.trail.length>1)s+=`<path d="${state.trail.map((p,i)=>`${i?'L':'M'}${mapPoint(p.x,p.y)}`).join(' ')}" stroke="#93a49a" stroke-width="1" stroke-dasharray="3 3" fill="none"/>`;
  if(state.target){const [x,y]=mapPoint(state.target.x,state.target.y);s+=`<circle cx="${x}" cy="${y}" r="8" fill="#cc9c6c10" stroke="#d8b082"/><circle cx="${x}" cy="${y}" r="2" fill="#d8b082"/>`;}
  const [x,y]=mapPoint(state.position.x,state.position.y);s+=`<circle cx="${x}" cy="${y}" r="13" fill="#c1c7b610"/><path d="M0-7 5 6 0 3-5 6Z" transform="translate(${x},${y}) rotate(35)" fill="${state.character==='fallen'?'#e68d82':'#bdcbbf'}" stroke="#d1d9cf" stroke-width=".5"/>`;
  $('#room-map').innerHTML=s;
}
function sceneName(){return state.scene==='flat'?'Flat floor':'Work cell';}
function updateUI(){
  const running=state.session==='running',starting=state.session==='starting',fall=state.character==='fallen',title=state.character[0].toUpperCase()+state.character.slice(1);
  $('#session-badge').innerHTML=`<span class="status-dot" style="background:${running?'var(--mint)':starting?'var(--accent)':'#7e8d94'}"></span>${running?'Session live':starting?'Starting…':state.session==='failed'?'Session failed':'No session'}`;
  $('#sidebar-scene').textContent=sceneName();$('#sidebar-session-status').textContent=`Session 008 · ${state.session}`;
  $('#viewport-scene').textContent=sceneName();$('#viewport-empty').hidden=running||starting;$('#startup-overlay').hidden=!starting;
  $('#end-session').innerHTML=icon(running?'stop':'play')+(running?'End session':starting?'Starting…':'Start session');$('#end-session').disabled=starting;$('#force-stop').disabled=!running&&!starting;
  $('#scene-character-state').textContent=title;$('#character-label').textContent='SOMA-23';
  $('#state-value').innerHTML=`<span class="status-dot" style="background:${fall?'var(--red)':'var(--mint)'}"></span>${running?title:'Offline'}<small>${state.character==='walking'?'walk':state.character==='stopping'?'stop':'idle'}</small>`;$('#state-value').style.color=fall?'var(--red)':'var(--mint)';
  $('#sim-time').textContent=timeText(state.simTime,true);$('#speed-value').textContent=state.character==='walking'?'1.24':state.character==='standing'&&running?'0.04':'0.00';
  $('#distance-value').textContent=state.target?Math.hypot(state.target.x-state.position.x,state.target.y-state.position.y).toFixed(2):'—';$('#reset-value').textContent=state.resets;
  $('#pause-session').innerHTML=icon(state.character==='paused'?'play':'pause')+`<span>${state.character==='paused'?'Resume':'Pause'}</span>`;
  $('#record-toggle').classList.toggle('recording',state.recording);$('#record-toggle').innerHTML=`<span class="record-dot" style="background:${state.recording?'#e2967f':'#859393'}"></span><span>${state.recording?'Recording':'Record'}</span>${state.recording?`<span class="record-time">${timeText(state.recordTime)}</span>`:''}`;
  $('#record-label').textContent=state.recording?`REC ${timeText(state.recordTime)}`:'REC OFF';$('#fps-label').textContent=running?(state.character==='paused'?'PAUSED':'18 FPS'):'OFFLINE';
  $('#fall-banner').hidden=!fall||!running;
  for(const id of ['stop-walking','pause-session','reset-character','record-toggle','walk-relative','push-character'])$('#'+id).disabled=!running;
  $('#pause-session').disabled=!running||fall;$('#walk-relative').disabled=!running||fall;$('#push-character').disabled=!running||fall;
  $('#gpu-status').textContent=running||starting?'GPU busy':'GPU free';$('#gpu-load').textContent=running?'34%':'0%';$('#gpu-memory').textContent=running?'12.8 / 96 GB':'0.8 / 96 GB';
  $('#global-session-state').textContent=running?`${sceneName()} · ${fall?'Fallen — reset required':title}`:starting?'Starting session…':'No active session';$('#global-session-state').style.color=fall?'var(--red)':'';
  $('#container-status').textContent=running||starting?'1 container':'0 containers';$('#project-lock').textContent=running?'Live session holds the GPU lock':'GPU lock available';
  $('#assistant-context').textContent=sceneName();$('#assistant-state').textContent=running?title:'Offline';
  renderMap();renderScene();
}
function canCommand(command){if(state.session!=='running'){addLog(command,false,'No active session','—');toast('Start a session before directing the character.');return false;}if(state.character==='fallen'&&!['reset','quit','record'].includes(command)){addLog(command,false,'Reset required','0.3 ms');toast('Character has fallen. Reset to continue.');return false;}return true;}
function walkTo(x,y){
  if(!canCommand('destination'))return false;
  if(!Number.isFinite(x)||!Number.isFinite(y)){toast('Enter valid numeric coordinates.');return false;}
  if(Math.abs(x)>4.5||Math.abs(y)>3.5){addLog(`destination (${x.toFixed(1)}, ${y.toFixed(1)})`,false,'Out of bounds','0.3 ms');toast('Destination is outside the room. Choose a point inside the boundary.');return false;}
  if(state.character==='paused'){addLog('destination',false,'Session paused','0.3 ms');toast('Resume the session before walking.');return false;}
  state.target={x,y};state.character='walking';addLog(`walk_to (${x.toFixed(1)}, ${y.toFixed(1)})`);updateUI();return true;
}
function resetCharacter(){if(!canCommand('reset'))return;state.position={x:0,y:0};state.target=null;state.trail=[{x:0,y:0}];state.character='standing';state.resets++;addLog('reset → spawn (0.0, 0.0)',true,'','6.4 ms');updateUI();toast('Character returned to the spawn point.');}
function stopWalking(){if(!canCommand('stop'))return;state.target=null;if(state.character!=='paused')state.character='standing';addLog('stop walking');updateUI();}
function togglePause(){if(!canCommand('pause'))return;state.character=state.character==='paused'?(state.target?'walking':'standing'):'paused';addLog(state.character==='paused'?'pause':'resume');updateUI();}
function toggleRecording(){if(!canCommand('record'))return;state.recording=!state.recording;if(state.recording)state.recordTime=0;addLog(`record ${state.recording?'start':'stop'} · take-${state.resets+1}`);updateUI();toast(state.recording?'Recording a new demo segment.':'Demo segment marked complete. No real video is created.');}
function startSession(){if(state.session==='running'||state.session==='starting')return;state.session='starting';state.character='standing';state.target=null;state.position={x:0,y:0};state.trail=[];state.simTime=0;state.recording=false;state.recordTime=0;state.resets=0;updateUI();let stage=0;const labels=['Loading scene assets…','Preparing the tracker-driven walker…','Opening the preview…'];$('#startup-progress').style.width='8%';$('#startup-text').textContent='Initializing the local runtime…';addLog('start session · demo');startTimer=setInterval(()=>{stage++;if(stage>=4){clearInterval(startTimer);state.session='running';updateUI();addLog('preview ready');toast('Demo session ready. Click the map to walk.');return;}$('#startup-progress').style.width=`${stage*27}%`;$('#startup-text').textContent=labels[stage-1];},650);}
function endSession(force=false){if(!['running','starting'].includes(state.session))return;clearInterval(startTimer);interruptAssistant(false);state.session=force?'failed':'ended';state.character='standing';state.target=null;state.recording=false;addLog(force?'force stop · session failed':'quit · evidence complete',!force,force?'Force stopped':'',force?'—':'1.2 ms');updateUI();toast(force?'Demo session marked failed.':'Demo session ended cleanly. Recording and evidence would be saved.');}
function setView(view){if(!['live','skills','project'].includes(view))return;state.view=view;$$('.view').forEach(el=>{const active=el.id===`${view}-view`;el.hidden=!active;el.classList.toggle('active',active);});$$('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});$('#breadcrumb-title').textContent={live:'Live scene',skills:'Skill library',project:'Project'}[view];history.replaceState(null,'',`#${view}`);if(view==='skills')renderSkills();window.scrollTo({top:0,behavior:'instant'});}
function openModal(title,content){$('#modal-title').textContent=title;$('#modal-content').innerHTML=content;hydrateIcons($('#modal-content'));$('#modal').showModal();}
function closeModal(){$('#modal').close();}

// Skill catalogue is intentionally illustrative and does not imply licensed assets exist.
const skills=[
  {name:'Tracker-driven walker',tag:'locomotion',desc:'Walk to a destination, turn, slow down, and come to a stand.',time:'Continuous',pose:'walking',available:true,source:'Existing controller'},
  {name:'Standing idle',tag:'locomotion',desc:'A quiet, balanced pause between the next big ideas.',time:'8.0 s',pose:'standing'},
  {name:'Pick up an object',tag:'interaction',desc:'Reach toward an object and bring it into the hand.',time:'3.2 s',pose:'reach'},
  {name:'A friendly wave',tag:'expression',desc:'A simple greeting that brings a character to life.',time:'2.4 s',pose:'wave'},
  {name:'Sit & settle',tag:'interaction',desc:'Approach a seat, sit down, and settle into position.',time:'4.8 s',pose:'sit'},
  {name:'A little dance',tag:'expression',desc:'An expressive movement to give your scene some rhythm.',time:'6.5 s',pose:'dance'}
];
function skillArt(skill, suffix='card'){let body=mannequin(140,150,.95,skill.pose==='walking'?'walking':'standing');if(skill.pose==='wave')body=body.replace(/M12-85 Q20-67 19-50/g,'M12-85 Q30-103 24-123').replace('cx="19" cy="-47"','cx="24" cy="-126"');if(skill.pose==='reach')body=body.replace(/M12-85 Q20-67 19-50/g,'M12-85 Q30-81 43-87').replace('cx="19" cy="-47"','cx="46" cy="-88"');if(skill.pose==='dance')body=body.replace(/M12-85 Q20-67 19-50/g,'M12-85 Q34-91 43-105').replace('cx="19" cy="-47"','cx="44" cy="-108"').replace(/M-18-85 Q-24-68-25-51/g,'M-18-85 Q-34-86-40-106').replace('cx="-25" cy="-48"','cx="-41" cy="-108"');if(skill.pose==='sit')body=body.replace(/M-10-47 Q-13-25-12-6/g,'M-10-47 Q-40-48-35-6').replace(/M6-45 Q11-23 10-3/g,'M6-45 Q-15-43-10-3');const art = `<svg viewBox="0 0 280 175" aria-label="${skill.name} concept illustration"><defs><linearGradient id="bodyMaterial"><stop stop-color="#82917d"/><stop offset=".5" stop-color="#c4cbb8"/><stop offset="1" stop-color="#a6b59c"/></linearGradient></defs><g opacity=".17" stroke="#b6c3b1" stroke-width=".5"><path d="M0 120 140 55 280 120M0 145 140 80 280 145M0 170 140 105 280 170M35 175 140 130 245 175M35 105 175 170M70 88 210 153M105 72 245 137M245 105 105 170M210 88 70 153M175 72 35 137" fill="none"/></g><ellipse cx="140" cy="152" rx="49" ry="12" stroke="#c6b293" stroke-width=".7" fill="#bdac820a"/>${skill.pose==='reach'?'<path d="M180 110h45v36h-45Z" fill="#697b79" stroke="#91a09b"/><path d="m180 110 13-8h45l-13 8" fill="#8e9a8c"/>':''}${skill.pose==='sit'?'<path d="M118 115h34v7h-34Zm0 7v30m34-30v30m0-30V87h-5" fill="#8f9b88" stroke="#8f9b88" stroke-width="3"/>':''}${body}</svg>`;return art.replaceAll('bodyMaterial',`skillMaterial-${skill.pose}-${suffix}`).replaceAll('url(#softShadow)','none');}
function renderSkills(){const query=$('#skill-search').value.toLowerCase();const filtered=skills.filter(s=>(state.filter==='all'||state.filter===s.tag)&&`${s.name} ${s.desc} ${s.tag}`.toLowerCase().includes(query));$('#skill-grid').innerHTML=filtered.map(s=>`<article class="skill-card"><div class="skill-art">${skillArt(s)}<span class="skill-preview-badge">${s.available?'CONTROLLER':'CONCEPT'}</span><span class="skill-duration">${s.time}</span></div><div class="skill-card-content"><h3>${s.name}${s.available?'<span>● Ready</span>':''}</h3><p>${s.desc}</p><div class="skill-tags"><span>${s.tag}</span><span>SOMA-23</span></div><div class="skill-bottom"><span>${s.source||'Licence: not sourced'}</span><button class="button" data-skill="${s.name}"><i data-icon="${s.available?'play':'eye'}"></i>${s.available?'Try in scene':'Preview'}</button></div></div></article>`).join('');$('#skill-empty').hidden=filtered.length>0;hydrateIcons($('#skill-grid'));$$('[data-skill]').forEach(b=>b.onclick=()=>previewSkill(b.dataset.skill));}
function previewSkill(name){const skill=skills.find(s=>s.name===name);if(skill.available){setView('live');if(state.session==='running')walkTo(2.5,.3);else toast('Start a session, then click the map to try the walker.');return;}openModal(skill.name,`<div class="skill-art" style="height:240px;border-radius:6px;margin-bottom:17px">${skillArt(skill,'dialog')}</div><p>${skill.desc}</p><div class="modal-info">Concept preview only. This clip is not shipped or connected. A real asset needs source and licence verification before it joins the library.</div><div class="modal-actions"><button class="button" id="close-preview">Back to library</button></div>`);$('#close-preview').onclick=closeModal;}

const providerDefaults={'Claude':{model:'Sonnet',url:''},'OpenAI':{model:'Model name',url:'https://api.openai.com/v1'},'Google Gemini':{model:'Model name',url:'https://generativelanguage.googleapis.com/v1beta/openai'},'xAI Grok':{model:'Model name',url:'https://api.x.ai/v1'},'OpenRouter':{model:'Provider/model',url:'https://openrouter.ai/api/v1'},'LM Studio':{model:'Local model',url:'http://localhost:1234/v1'}};
const providerSettings={};
function updateProvider(){const p=providerSettings[state.provider]||{...providerDefaults[state.provider],thinking:'Default'};$('#provider-status').innerHTML=`<span class="status-dot"></span>Demo mode<span>·</span>${escapeHtml(p.model)}<span>·</span>${escapeHtml(p.thinking)} thinking`;$('.provider-logo').textContent=state.provider==='Claude'?'✳':state.provider==='LM Studio'?'◈':'✧';}
function settingsModal(){const p=providerSettings[state.provider]||{...providerDefaults[state.provider],thinking:'Default'};openModal(`${state.provider} settings`,`<p>Preview provider controls. Settings last only until this page is reloaded.</p><div class="modal-info">No connection is made. The key field is disabled in this mockup; do not enter real credentials.</div><label class="modal-field" style="margin-top:17px">API key<div class="key-row"><input type="password" placeholder="${state.provider==='LM Studio'?'Not required for local models':'No key · disabled in preview'}" disabled><button class="icon-button" aria-label="Show key unavailable in mockup" disabled><i data-icon="eye"></i></button></div></label><div class="settings-row"><label class="modal-field">Model<input id="settings-model" value="${escapeHtml(p.model)}" autocomplete="off"></label><button class="button" id="fetch-models">Fetch models</button></div><label class="modal-field">Thinking level<select id="settings-thinking">${['Default','Low','Medium','High','XHigh','Max'].map(v=>`<option ${v===p.thinking?'selected':''}>${v}</option>`).join('')}</select></label>${state.provider!=='Claude'?`<label class="modal-field">Base URL<input id="settings-url" value="${escapeHtml(p.url)}" autocomplete="off"></label>`:''}<div class="modal-actions"><button class="button ghost" id="forget-key">Forget stored key</button><button class="button primary" id="save-provider">Save demo settings</button></div>`);$('#fetch-models').onclick=()=>toast('Provider discovery is not connected in the mockup. Enter a model label to preview it.');$('#forget-key').onclick=()=>toast('No API keys are stored by this mockup.');$('#save-provider').onclick=()=>{providerSettings[state.provider]={model:$('#settings-model').value.trim()||providerDefaults[state.provider].model,thinking:$('#settings-thinking').value,url:$('#settings-url')?.value||''};updateProvider();closeModal();toast('Demo provider settings updated for this page only.');};}
function appendAssistant(text,tool){const el=document.createElement('div');el.className='assistant-message';el.innerHTML=`<div class="message-author"><span class="small-spark">✳</span>Astra<span>${timestamp().slice(0,5)}</span></div><p>${escapeHtml(text)}</p>${tool?`<details class="tool-call"><summary><span class="tool-check">✓</span>${escapeHtml(tool.label)}<span>demo</span><i data-icon="chevron-down"></i></summary><code>${escapeHtml(tool.code)}</code></details>`:''}`;$('#chat-messages').append(el);hydrateIcons(el);scrollChat();return el;}
function scrollChat(){$('#chat-messages').scrollTo({top:$('#chat-messages').scrollHeight,behavior:'smooth'});}
function interruptAssistant(show=true){if(!state.assistantBusy)return;state.assistantBusy=false;state.assistantToken++;clearTimeout(assistantTimer);$('#assistant-working').hidden=true;$('#send-message').disabled=false;if(show)appendAssistant('Stopped this assistant turn. You can send a new direction or keep using the manual controls.');}
function finishAssistant(){state.assistantBusy=false;$('#assistant-working').hidden=true;$('#send-message').disabled=false;}
function sendChat(text){text=text.trim();if(!text)return;interruptAssistant(false);const user=document.createElement('div');user.className='user-message';user.textContent=text;const stamp=document.createElement('span');stamp.textContent=timestamp().slice(0,5);user.append(stamp);$('#chat-messages').append(user);$('#chat-input').value='';state.assistantBusy=true;const token=++state.assistantToken;$('#assistant-working').hidden=false;$('#assistant-working-text').textContent='Planning the next move…';scrollChat();
  assistantTimer=setTimeout(()=>{if(token!==state.assistantToken)return;const t=text.toLowerCase();
    if(/skill|dance|wave|sit|running/.test(t)){appendAssistant('The tracker-driven walker is ready to try. The library also previews future skills like a wave, sitting, and dancing. Those are concepts and cannot play yet.',{label:'Browse skill library',code:'list_skills() → 1 available controller, 5 concepts'});setView('skills');}
    else if(/reset/.test(t)){resetCharacter();appendAssistant(state.session==='running'?'She’s back at the spawn point.':'Start a session first to reset the character.');}
    else if(/resume/.test(t)){if(state.character==='paused')togglePause();appendAssistant(state.session==='running'?'The demo session is running again.':'There is no session to resume.');}
    else if(/pause/.test(t)){if(state.character!=='paused')togglePause();appendAssistant(state.character==='paused'?'Simulation time is paused. You can still chat.':'The session could not be paused.');}
    else if(/end session/.test(t)){endSession();appendAssistant('The demo session has ended. A connected studio would save its evidence folder here.');}
    else if(/start session|load the/.test(t)&&state.session!=='running'){startSession();appendAssistant('Preparing a demo session. The progress overlay shows the startup flow.');}
    else if(/stop/.test(t)){stopWalking();appendAssistant('Stop requested. Manual controls stay available throughout the conversation.',{label:'Stop walking',code:'stop() → demo command'});}
    else if(/record/.test(t)){if(state.session==='running')toggleRecording();appendAssistant(state.session==='running'?`Demo recording ${state.recording?'started':'stopped'}.`:'Start a session before recording.');}
    else if(/walk|come back|conveyor|machine|start|rack/.test(t)){
      const destination=/back|starting|start/.test(t)?{x:0,y:0}: /machine/.test(t)?{x:.5,y:-1.4}:/rack/.test(t)?{x:-2,y:-1.1}:{x:2.5,y:.3};
      const accepted=walkTo(destination.x,destination.y);if(accepted){appendAssistant('I’ll take her there, then wait until she’s standing. You can interrupt me or send a new direction at any time.',{label:'Walk to destination',code:`walk_to({ x: ${destination.x}, y: ${destination.y}, frame: "spawn" }) → accepted`});$('#assistant-working-text').textContent='Waiting until standing…';const wait=()=>{if(token!==state.assistantToken)return;if(state.character==='standing'){appendAssistant('She’s arrived and standing. Ready for your next direction.');finishAssistant();}else if(state.character==='fallen'){appendAssistant('She has fallen. Reset her before giving another destination.');finishAssistant();}else if(state.session!=='running'){finishAssistant();}else assistantTimer=setTimeout(wait,200);};assistantTimer=setTimeout(wait,200);return;}appendAssistant('That direction could not be accepted. Check the session state, then reset or resume if needed.');
    }else if(/push/.test(t)){$('#push-x').value=/left/.test(t)?'0':'1';$('#push-y').value=/left/.test(t)?'1':'0';$('#push-character').click();appendAssistant('Applied the demo push using the manual velocity values. Strong pushes can trigger the fall state.');}
    else appendAssistant('This is a scripted UI demo. Try “walk to the conveyor,” “come back to start,” “pause,” “reset,” or “what skills are available?” A connected assistant would handle open-ended directions.');
    finishAssistant();
  },700);
}

$$('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));$('.brand').onclick=e=>{e.preventDefault();setView('live');};$('#workspace-info').onclick=()=>setView('project');$('#session-nav').onclick=()=>setView('live');
$('#end-session').onclick=()=>state.session==='running'?endSession():startSession();$('#empty-start').onclick=startSession;
$('#force-stop').onclick=()=>openModal('Force stop this session?',`<p>This marks the demo session as failed. In the connected studio, this is the emergency exit; a clean End session saves a completed performance.</p><div class="modal-actions"><button class="button" id="cancel-force">Keep session</button><button class="button" style="background:#57332f;border-color:#8c5147;color:#f6b8a3" id="confirm-force">Force stop</button></div>`);
$('#modal').addEventListener('click',e=>{if(e.target.id==='cancel-force')closeModal();if(e.target.id==='confirm-force'){closeModal();endSession(true);}if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
$('#close-modal').onclick=closeModal;
$('#scene-select').onchange=()=>{const next=$('#scene-select').value;if(state.session==='running'||state.session==='starting'){$('#scene-select').value=state.scene;toast('End the current session before choosing another scene.');return;}state.scene=next;updateUI();};
$('#resolution-select').onchange=()=>toast(`Demo preview set to ${$('#resolution-select').value}. Illustration size is unchanged.`);
$('#stop-walking').onclick=stopWalking;$('#pause-session').onclick=togglePause;$('#reset-character').onclick=resetCharacter;$('#fall-reset').onclick=resetCharacter;$('#record-toggle').onclick=toggleRecording;
$('#walk-relative').onclick=()=>{const x=$('#walk-x').value,y=$('#walk-y').value;if(!x.trim()||!y.trim())return toast('Enter both walking coordinates.');walkTo(state.position.x+Number(x),state.position.y+Number(y));};
$('#push-character').onclick=()=>{if(!canCommand('push'))return;const sx=$('#push-x').value,sy=$('#push-y').value;const vx=Number(sx),vy=Number(sy);if(!sx.trim()||!sy.trim()||!Number.isFinite(vx)||!Number.isFinite(vy)||Math.abs(vx)>8||Math.abs(vy)>8)return toast('Enter a velocity between −8 and 8 m/s for both axes.');if(state.character==='paused')return toast('Resume the session before applying a push.');addLog(`push (${vx.toFixed(1)}, ${vy.toFixed(1)})`);if(Math.hypot(vx,vy)>=3){state.character='fallen';state.target=null;toast('Demo fall triggered. Reset to continue.');}else toast('Demo impulse absorbed. Character remains upright.');updateUI();};
function mapCoords(event){const r=$('#room-map').getBoundingClientRect();const scale=Math.min(r.width/460,r.height/235);const ox=(r.width-460*scale)/2,oy=(r.height-235*scale)/2;return {x:((event.clientX-r.left-ox)/scale-230)/33,y:(118-(event.clientY-r.top-oy)/scale)/23};}
$('#room-map').addEventListener('click',event=>{const p=mapCoords(event);walkTo(p.x,p.y);});$('#room-map').addEventListener('mousemove',e=>{const p=mapCoords(e);$('#map-coordinates').textContent=`x: ${p.x.toFixed(1)}   y: ${p.y.toFixed(1)}`;});
$('#room-map').addEventListener('keydown',e=>{const delta={ArrowUp:[0,.5],ArrowDown:[0,-.5],ArrowLeft:[-.5,0],ArrowRight:[.5,0]}[e.key];if(delta){e.preventDefault();state.mapCursor.x=Math.max(-4.5,Math.min(4.5,state.mapCursor.x+delta[0]));state.mapCursor.y=Math.max(-3.5,Math.min(3.5,state.mapCursor.y+delta[1]));$('#map-coordinates').textContent=`Target: ${state.mapCursor.x.toFixed(1)}, ${state.mapCursor.y.toFixed(1)} · Enter to walk`;toast(`Map target (${state.mapCursor.x.toFixed(1)}, ${state.mapCursor.y.toFixed(1)}). Press Enter to walk.`);}if(e.key==='Enter'||e.key===' '){e.preventDefault();walkTo(state.mapCursor.x,state.mapCursor.y);}});
$('#clear-trail').onclick=()=>{state.trail=[{...state.position}];updateUI();toast('Trail cleared.');};$('#clear-log').onclick=()=>{state.commands=[];renderLog();};
$('#toggle-grid').onclick=()=>{state.grid=!state.grid;$('#toggle-grid').setAttribute('aria-pressed',String(state.grid));renderScene();};$('#reset-camera').onclick=()=>{renderScene();toast('Perspective view restored.');};$('#fullscreen').onclick=()=>{$('.scene-panel').classList.toggle('expanded');$('#fullscreen').setAttribute('aria-label',$('.scene-panel').classList.contains('expanded')?'Collapse preview':'Expand preview');};
$('#provider-select').onchange=()=>{state.provider=$('#provider-select').value;updateProvider();toast(`${state.provider} selected for preview. No provider is connected.`);};$('#provider-settings').onclick=settingsModal;
$('#chat-form').onsubmit=e=>{e.preventDefault();sendChat($('#chat-input').value);};$('#chat-input').onkeydown=e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();sendChat($('#chat-input').value);}};$('#interrupt-assistant').onclick=()=>interruptAssistant();$$('[data-prompt]').forEach(b=>b.onclick=()=>sendChat(b.dataset.prompt));$('#new-chat').onclick=()=>{interruptAssistant(false);$('#chat-messages').innerHTML='<div class="chat-day">NEW CONVERSATION</div>';appendAssistant('A fresh start. Tell me where to go, or explore the skill library. This conversation uses scripted demo replies.');};
$('#skill-search').oninput=renderSkills;$$('[data-filter]').forEach(b=>b.onclick=()=>{state.filter=b.dataset.filter;$$('[data-filter]').forEach(el=>el.classList.toggle('selected',el===b));renderSkills();});
$('#create-skill').onclick=()=>openModal('Create a skill',`<p>Describe a motion you’d like to add to your repertoire.</p><label class="modal-field">Motion description<input id="new-skill-description" placeholder="A slow, friendly wave with the right hand"></label><div class="modal-info">Text-to-motion generation is a future stage. This design preview does not generate, download, or save motion files.</div><div class="modal-actions"><button class="button primary" id="preview-idea">Preview request</button></div>`);
$('#modal').addEventListener('click',e=>{if(e.target.id==='preview-idea'){const value=$('#new-skill-description').value.trim();if(!value){$('#new-skill-description').focus();return;}closeModal();$('#chat-input').value=`Create a skill: ${value}`;toast('Idea added to the assistant composer. You can edit it before sending.');}});
$$('[data-resource]').forEach(b=>b.onclick=()=>openModal(b.dataset.resource,`<p>This would open <strong>${escapeHtml(b.dataset.resource)}</strong> from the connected desktop studio.</p><div class="modal-info">The mockup is self-contained. It does not read project files, launch applications, or run backend commands.</div>`));
const showGuide=()=>openModal('A little direction goes a long way',`<p>This is an interactive design study for Digital Human Studio. All controls operate on browser-only demo data.</p><div class="shortcut-row"><span>Click the room map</span><span>Walk to a destination</span></div><div class="shortcut-row"><span>Pause / resume</span><kbd>Space</kbd></div><div class="shortcut-row"><span>Reset character</span><kbd>R</kbd></div><div class="shortcut-row"><span>Record a segment</span><kbd>Shift R</kbd></div><div class="shortcut-row"><span>Send an assistant message</span><kbd>Ctrl Enter</kbd></div><div class="shortcut-row"><span>Search the skill library</span><kbd>/</kbd></div><p style="margin-top:18px">Try a push of 3 m/s to preview a fall. End the session to change scenes. Provider settings, the skill library, and job output are also interactive.</p>`);
$('#help-button').onclick=showGuide;$('#shortcuts-button').onclick=showGuide;
$('#session-details').onclick=()=>openModal('Session 008',`<p>Illustrative session details. These values are demo data.</p><dl class="facts"><div><dt>Scene</dt><dd>${sceneName()}</dd></div><div><dt>Controller</dt><dd>Tracker-driven walker</dd></div><div><dt>State</dt><dd>${state.session}</dd></div><div><dt>Simulation time</dt><dd>${timeText(state.simTime,true)}</dd></div><div><dt>Recording</dt><dd>${state.recording?'Active segment':'Not recording'}</dd></div></dl><div class="modal-info">Clean End session represents saving a performance and its evidence. Force stop represents a failed session.</div>`);
function toggleJobs(force){$('#job-drawer').hidden=typeof force==='boolean'?!force:!$('#job-drawer').hidden;$('#toggle-jobs').setAttribute('aria-expanded',String(!$('#job-drawer').hidden));}$('#toggle-jobs').onclick=()=>toggleJobs();$('#close-jobs').onclick=()=>toggleJobs(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('.scene-panel').classList.remove('expanded');return;}if(e.ctrlKey||e.metaKey||e.altKey||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||$('#modal').open||e.target.id==='room-map')return;if(e.key===' '&&state.view==='live'&&e.target.tagName!=='BUTTON'){e.preventDefault();togglePause();}if(e.key.toLowerCase()==='r'&&state.view==='live'){e.preventDefault();e.shiftKey?toggleRecording():resetCharacter();}if(e.key==='/'){e.preventDefault();setView('skills');$('#skill-search').focus();}});

// Browser-only animation. Simulated time freezes when the session is paused.
motionTimer=setInterval(()=>{if(state.session!=='running'||state.character==='paused'||document.hidden)return;state.simTime+=.1;if(state.recording)state.recordTime+=.1;if(state.character==='walking'&&state.target){const dx=state.target.x-state.position.x,dy=state.target.y-state.position.y;const d=Math.hypot(dx,dy);if(d<.12){state.position={...state.target};state.target=null;state.character='standing';addLog('arrived · standing',true,'','—');}else{state.position.x+=dx/d*.11;state.position.y+=dy/d*.11;if(Math.round(state.simTime*10)%3===0){state.trail.push({...state.position});if(state.trail.length>100)state.trail.shift();}}}updateUI();},100);
addLog('record start · take-1',true,'','0.6 ms');addLog('walk_to (2.5, 0.3)',true,'','0.8 ms');addLog('wait_until standing',true,'','3.2 s');
updateProvider();updateUI();renderSkills();setView(location.hash.slice(1)||'live');
