// Standalone browser verification. Requires preview.sh and a Chrome CDP port.
// Writes screenshots and a report only beside this script.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const here=path.dirname(fileURLToPath(import.meta.url));
const output=path.join(here,'verification');
await fs.mkdir(output,{recursive:true});
const port=process.env.ASTRA_CDP_PORT||'9224';
const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const target=targets.find(t=>t.type==='page');
const ws=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let next=0;const pending=new Map(),errors=[],requests=[],passed=[];
ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const p=pending.get(message.id);pending.delete(message.id);message.error?p.reject(message.error):p.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Network.requestWillBeSent')requests.push(message.params.request.url);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const shot=async name=>{const result=await send('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(output,`${name}.png`),Buffer.from(result.data,'base64'));};
const viewport=(width,height=1050)=>send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
const pass=message=>{passed.push(message);console.log('PASS',message);};
await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});await viewport(1600);
await send('Page.navigate',{url:'http://127.0.0.1:8787/'});
for(let n=0;n<100;n++){if(await evaluate('document.readyState === "complete" && !!document.querySelector("#scene-illustration svg")'))break;await sleep(50);}
await shot('live-desktop');
if(process.argv.includes('--screenshots-only')){await click('[data-view="skills"]');await shot('skills-desktop');await click('[data-view="project"]');await shot('project-desktop');await click('[data-view="live"]');ws.close();process.exit(0);}
for(const width of [1920,1600,1440,1280,1024,768,600,390,320]){
  await viewport(width,1000);
  for(const view of ['live','skills','project']){
    await click(`[data-view="${view}"]`);
    const layout=await evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');
    assert.ok(layout.scroll<=width,`${view} overflow at ${width}: ${JSON.stringify(layout)}`);
  }
  pass(`All three views fit ${width}px`);
}
await viewport(1600);await click('[data-view="skills"]');await shot('skills-desktop');
await evaluate('document.querySelector("#skill-search").value="wave";document.querySelector("#skill-search").dispatchEvent(new Event("input"));');
assert.equal(await evaluate('document.querySelectorAll(".skill-card").length'),1);
await click('[data-skill="A friendly wave"]');assert.equal(await evaluate('document.querySelector("#modal").open'),true);await click('#close-modal');
await evaluate('document.querySelector("#skill-search").value="";document.querySelector("#skill-search").dispatchEvent(new Event("input"));');
await click('[data-filter="interaction"]');assert.equal(await evaluate('document.querySelectorAll(".skill-card").length'),2);await click('[data-filter="all"]');
pass('Skill search, category filters, concept dialog');
await click('[data-view="project"]');await shot('project-desktop');await click('[data-resource="Mixar"]');assert.equal(await evaluate('document.querySelector("#modal").open'),true);await click('#close-modal');
await click('[data-view="live"]');
await click('#pause-session');const time=await evaluate('document.querySelector("#sim-time").textContent');await sleep(400);assert.equal(await evaluate('document.querySelector("#sim-time").textContent'),time);await click('#pause-session');
await click('#reset-character');assert.equal(await evaluate('document.querySelector("#reset-value").textContent'),'1');
const map=await evaluate('(()=>{const r=document.querySelector("#room-map").getBoundingClientRect();return {x:r.x+r.width*.57,y:r.y+r.height*.55}})()');
await send('Input.dispatchMouseEvent',{type:'mousePressed',x:map.x,y:map.y,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:map.x,y:map.y,button:'left',clickCount:1});
assert.match(await evaluate('document.querySelector("#state-value").textContent'),/Walking/);await sleep(1800);assert.match(await evaluate('document.querySelector("#state-value").textContent'),/Standing/);
pass('Pause freezes time, reset returns to spawn, real map click walks and arrives');
await evaluate('document.querySelector("#push-x").value="3"');await click('#push-character');assert.equal(await evaluate('document.querySelector("#fall-banner").hidden'),false);assert.match(await evaluate('document.querySelector("#global-session-state").textContent'),/Fallen/);assert.equal(await evaluate('document.querySelector("#walk-relative").disabled'),true);
await shot('fallen-state');await evaluate('document.querySelector("#room-map").dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}))');assert.match(await evaluate('document.querySelector("#command-log").textContent'),/Reset required/);await click('#fall-reset');assert.equal(await evaluate('document.querySelector("#fall-banner").hidden'),true);
await evaluate('document.querySelector("#walk-x").value="20"');await click('#walk-relative');assert.match(await evaluate('document.querySelector("#command-log").textContent'),/Out of bounds/);await evaluate('document.querySelector("#walk-x").value="2"');
pass('Fall blocks destinations until reset; out-of-bounds commands are rejected');
await click('#record-toggle');assert.match(await evaluate('document.querySelector("#record-toggle").textContent'),/^Record$/);await click('#record-toggle');assert.match(await evaluate('document.querySelector("#record-toggle").textContent'),/Recording/);
await click('#end-session');assert.equal(await evaluate('document.querySelector("#viewport-empty").hidden'),false);
await evaluate('document.querySelector("#scene-select").value="flat";document.querySelector("#scene-select").dispatchEvent(new Event("change"))');
await click('#end-session');assert.equal(await evaluate('document.querySelector("#startup-overlay").hidden'),false);await shot('startup-state');await sleep(2900);assert.equal(await evaluate('document.querySelector("#startup-overlay").hidden'),true);assert.match(await evaluate('document.querySelector("#viewport-scene").textContent'),/Flat floor/);
await evaluate('document.querySelector("#scene-select").value="workcell";document.querySelector("#scene-select").dispatchEvent(new Event("change"))');assert.equal(await evaluate('document.querySelector("#scene-select").value'),'flat');
await click('#force-stop');await click('#confirm-force');assert.match(await evaluate('document.querySelector("#session-badge").textContent'),/Session failed/);
pass('Recording, clean end, scene switch, startup, one-session guard, emergency failure state');
await evaluate('document.querySelector("#scene-select").value="workcell";document.querySelector("#scene-select").dispatchEvent(new Event("change"))');await click('#end-session');await sleep(2900);
await evaluate('document.querySelector("#chat-input").value="walk to the conveyor"');await click('#send-message');await sleep(800);assert.equal(await evaluate('document.querySelector("#assistant-working").hidden'),false);await click('#pause-session');await click('#interrupt-assistant');assert.equal(await evaluate('document.querySelector("#assistant-working").hidden'),true);await click('#pause-session');
await evaluate('document.querySelector("#chat-input").value="come back to start"');await click('#send-message');await sleep(2400);assert.equal(await evaluate('document.querySelector("#assistant-working").hidden'),true);
pass('Assistant wait can be interrupted; manual controls stay active; replacement direction completes');
await evaluate('document.querySelector("#provider-select").value="LM Studio";document.querySelector("#provider-select").dispatchEvent(new Event("change"))');await click('#provider-settings');assert.equal(await evaluate('document.querySelector("#modal input[type=password]").disabled'),true);await evaluate('document.querySelector("#settings-model").value="Local demo model"');await click('#save-provider');assert.match(await evaluate('document.querySelector("#provider-status").textContent'),/Local demo model/);
await click('#toggle-jobs');assert.equal(await evaluate('document.querySelector("#job-drawer").hidden'),false);await click('#close-jobs');await click('#fullscreen');assert.equal(await evaluate('document.querySelector(".scene-panel").classList.contains("expanded")'),true);await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});assert.equal(await evaluate('document.querySelector(".scene-panel").classList.contains("expanded")'),false);
pass('Provider settings stay in-memory; keys disabled; job drawer; expanded preview');
await viewport(390,844);await evaluate('scrollTo(0,0)');await shot('live-mobile');
assert.deepEqual(errors,[]);const external=requests.filter(url=>!url.startsWith('http://127.0.0.1:8787/')&&!url.startsWith('data:'));assert.deepEqual(external,[]);
assert.deepEqual(await evaluate('[...document.querySelectorAll("[id]")].map(e=>e.id).filter((v,i,a)=>a.indexOf(v)!==i)'),[]);pass('No browser exceptions, duplicate IDs, or external network requests');
await viewport(1600);await send('Page.reload');await sleep(400);await shot('live-desktop');
await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checkedAt:new Date().toISOString(),browser:await send('Browser.getVersion'),passed,errors,externalRequests:external,scope:'UI mockup only; no backend or simulation tests executed'},null,2)+'\n');
ws.close();
