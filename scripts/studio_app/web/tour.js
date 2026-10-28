/* Interactive tutorial for the Digital Human Studio control center.
   A guided tour of numbered steps: each step spotlights one control, explains it, and either waits
   for you to use it (it advances by itself when the studio reports the result) or asks for Next.
   Skip at any time; the current step is remembered (localStorage) and the tour resumes from the
   sidebar. It talks to the page through app.js's globals (ui, setView, walkTo, ...) and the
   studio:event / studio:state / studio:view events the page dispatches. */
'use strict';
(function () {
  const STORE = 'dhs.tour.v1';
  const state = { active: false, index: 0, completed: false, dismissed: false, waiting: null, raf: 0, lastTarget: null };

  function load() { try { Object.assign(state, JSON.parse(localStorage.getItem(STORE) || '{}')); } catch (e) {} }
  function save() { try { localStorage.setItem(STORE, JSON.stringify({ index: state.index, completed: state.completed, dismissed: state.dismissed })); } catch (e) {} }
  const sessionRunning = () => ui.session && ui.session.phase === 'running';
  const sessionStarting = () => ui.session && ui.session.phase === 'starting';
  const st = () => ui.state || {};
  const relative = () => (typeof relativePosition === 'function' ? relativePosition() : null);
  const providerReady = () => !!(ui.providerInfo && (ui.providerInfo.has_key || ui.providerInfo.key_optional));
  const firstClipCard = () => $$('#skill-grid [data-card]').find(c => !c.querySelector('[data-skill="tracker"]')) || $('#skill-grid .skill-card');

  // ---------------------------------------------------------------- the steps
  const STEPS = [
    { id: 'welcome', title: 'Welcome to the studio', centered: true,
      body: `<p>This is a studio for directing a <strong>digital human</strong>: a physically simulated body that walks, performs motion clips, carries objects and can be dressed in different characters. You direct it by clicking, by composing sequences, or by talking to an assistant.</p>
             <p>This tutorial walks through every part of the interface in about fifteen minutes. Each step points at one control. When a step asks you to do something, it moves on by itself once the studio has done it. You can press <kbd>Skip tour</kbd> at any time and come back later from <em>Interactive tutorial</em> in the sidebar; it resumes where you left off. Keyboard: <kbd>→</kbd> next, <kbd>←</kbd> back, <kbd>Esc</kbd> hide.</p>
             <p>One thing to know before we start: the simulation runs on this machine's GPU inside a locked container. Starting it takes about a minute, and only one session runs at a time.</p>` },
    { id: 'nav', target: 'nav[aria-label="Main navigation"]', placement: 'right', title: 'The four views',
      body: `<p><strong>Live scene</strong> is where the character acts. <strong>Skill library</strong> holds every motion it can perform. <strong>Characters</strong> lists the bodies it can wear. <strong>Project</strong> shows the machine, the locked runtime and the recorded evidence of every session.</p><p>The assistant on the right stays with you in all four.</p>` },
    { id: 'scene', view: 'live', target: '#scene-select', placement: 'bottom', title: 'Choose a scene',
      body: `<p>A scene is a room with objects. <em>Flat floor</em> is an empty stage; <em>Workcell</em> is a small factory cell with a machine, a conveyor carrying a cup, a rack, pallets and a carton. The walls and furniture are real obstacles: the character collides with them, and nothing plans a path around them.</p><p>Pick <strong>Workcell</strong> for this tutorial.</p>`,
      doIt: () => { $('#scene-select').value = 'workcell'; $('#scene-select').dispatchEvent(new Event('change')); }, doItLabel: 'Select Workcell for me',
      done: () => $('#scene-select').value === 'workcell' },
    { id: 'controller', target: '#controller-select', placement: 'bottom', title: 'The controller',
      body: `<p>The <strong>tracker-driven walker</strong> is what moves the body. It is a motion tracker: a neural network that was trained once (by NVIDIA, on licensed motion capture) to make a simulated body follow a reference motion under real physics. The studio composes that reference live from licensed clips, so walking, turning and standing come from captured human motion, and nothing is trained here. Leave it on the walker.</p>` },
    { id: 'mode', target: '#mode-select', placement: 'bottom', title: 'Physical or kinematic',
      body: `<p><strong>Physical</strong>: the tracker drives the body's motors and physics decides what happens. Pushes, collisions and falls are real. This is the honest mode.</p><p><strong>Kinematic playback</strong>: the reference motion is written straight into the simulator every frame. Clips play exactly as captured, nothing can fall, but nothing can push back either. Use it for authoring and for previewing clips. Keep <strong>Physical</strong> for now.</p>` },
    { id: 'character', target: '#character-select', placement: 'bottom', title: 'Who is on stage',
      body: `<p>The <strong>Mannequin</strong> is the simulated body itself, drawn as capsules. The other entries are skinned characters whose rigs are aligned to that body and deformed from it every frame, so they move exactly as the physics does. Pick one if you like; the tutorial works with any of them.</p>` },
    { id: 'preview', target: '#resolution-select', placement: 'bottom', title: 'Preview size',
      body: `<p>The picture you will see is rendered by the simulation worker itself, so a bigger preview costs simulation speed. 960 × 540 is a good balance. Recordings are always written at 30 frames per second of simulated time, whatever the preview rate.</p>` },
    { id: 'start', target: '#end-session', placement: 'bottom', title: 'Start a session', action: 'Click Start session',
      body: `<p>Click <strong>Start session</strong>. The studio launches the simulation in its container, loads the tracker and the scene, and starts publishing frames. Expect about a minute; the overlay shows progress. Everything the session does is recorded under <code>diagnostics/</code> with a pass/fail gate at the end.</p>`,
      done: () => sessionRunning(), waitText: 'Waiting for the session to be running…', doIt: () => { if (!sessionRunning() && !sessionStarting()) startSession(); }, doItLabel: 'Start it for me' },
    { id: 'viewport', target: '.scene-panel', placement: 'bottom', title: 'The camera view',
      body: `<p>This is the live camera, following the character. The caption at the bottom names the character and its state; chips at the top show what skill is playing and which sequence step is running. The expand button on the left makes it fill the window (<kbd>Esc</kbd> to shrink).</p>` },
    { id: 'telemetry', target: '.telemetry', placement: 'top', title: 'Telemetry',
      body: `<p><strong>Character state</strong> is standing, walking, stopping, playing, paused or fallen, with the reference phase beside it. <strong>Pelvis speed</strong> and <strong>to destination</strong> are measured in metres. <strong>Control rate</strong> is how many simulation steps the machine manages per real second; 30 would be real time. <strong>Resets</strong> counts how often the character was put back at its spawn point.</p>` },
    { id: 'map-click', target: '#room-map', placement: 'right', title: 'Click to walk', action: 'Click an empty spot inside the room',
      body: `<p>The room map is a top-down plan in metres, centred on the <em>spawn</em> (where the character appeared). Click anywhere inside the room and the character walks there. It turns toward the point, walks, slows down and comes to a true standstill. Destinations outside the room are refused.</p>`,
      done: () => !!st().destination, waitText: 'Waiting for a destination…', doIt: () => walkTo(1.5, 0.8, 'spawn'), doItLabel: 'Send her to (1.5, 0.8)' },
    { id: 'map-arrive', target: '#room-map', placement: 'right', title: 'Arrival',
      body: `<p>Watch the dashed trail and the destination ring. The character counts as arrived within 0.3 m of the point, once its pelvis is slower than 0.15 m/s. The state goes walking → stopping → standing.</p>`,
      done: () => st().state === 'standing' && !!st().destination && (st().distance ?? 9) < 0.4, waitText: 'Waiting for her to arrive and stand…' },
    { id: 'map-object', target: '#room-map', placement: 'right', title: 'Objects', action: 'Click the cup on the map',
      body: `<p>The small round markers are <strong>objects</strong> the character can handle: the cup on the conveyor and the carton on a pallet. Each has an <em>approach point</em> (the dotted ring) where the character should stand to reach it. Click the cup marker to walk to its approach point.</p>`,
      done: () => ui.commands.some(c => /walk to cup/.test(c.command) && c.accepted), waitText: 'Waiting for a walk to the cup…', doIt: () => walkToObject('cup'), doItLabel: 'Walk to the cup for me' },
    { id: 'pause', target: '#pause-session', placement: 'top', title: 'Pause', action: 'Click Pause (or press Space)',
      body: `<p><strong>Pause</strong> freezes simulated time; the worker keeps listening, so the interface stays live. <strong>Stop</strong> ends walking, the playing skill and any running sequence, and holds the character where it is. <strong>Reset</strong> puts the character back at the spawn point; it is the only way to recover after a fall, and it is always explicit, never hidden.</p>`,
      done: () => !!st().paused, waitText: 'Waiting for pause…', doIt: () => { if (!st().paused) togglePause(); }, doItLabel: 'Pause for me' },
    { id: 'resume', target: '#pause-session', placement: 'top', title: 'Resume', action: 'Click Resume',
      body: `<p>Click <strong>Resume</strong>. Simulated time continues from exactly where it stopped; the pause is recorded in the session log with its real-world duration.</p>`,
      done: () => sessionRunning() && !st().paused, waitText: 'Waiting for resume…', doIt: () => { if (st().paused) togglePause(); }, doItLabel: 'Resume for me' },
    { id: 'record', target: '#record-toggle', placement: 'top', title: 'Record a segment', action: 'Click Record',
      body: `<p>The whole session is always recorded (<code>performance.mp4</code>, a trajectory trace, every command and its acknowledgement). <strong>Record</strong> marks a named segment inside that recording, so a take you like is easy to find afterwards. Click it now; click again later to close the segment (<kbd>Shift</kbd>+<kbd>R</kbd>).</p>`,
      done: () => !!st().recording, waitText: 'Waiting for a recording segment…', doIt: () => { if (!st().recording) toggleRecording(); }, doItLabel: 'Start a segment for me' },
    { id: 'push', target: '.direction-panel', placement: 'left', title: 'Manual direction and a push', action: 'Click the push button',
      body: `<p><strong>Walk relative</strong> sends the character a distance ahead and to the left of where it faces. <strong>Apply a push</strong> gives the body a velocity impulse in metres per second: a shove. In physical mode the tracker has to recover its balance for real; a hard enough push makes it fall, which shows a banner and asks for Reset. Try the default 1 m/s push.</p>`,
      done: () => ui.commands.some(c => /^push/.test(c.command) && c.accepted), waitText: 'Waiting for a push…', doIt: () => $('#push-character').click(), doItLabel: 'Push for me' },
    { id: 'log', target: '.acknowledgements', placement: 'top', title: 'Command activity',
      body: `<p>Every command you send is written to the session's command file and <strong>acknowledged</strong> by the worker with a result and a latency. Rejections say why: outside the room, fallen (reset required), unknown skill. The same log is saved with the session, so what happened is never in doubt.</p>` },
    { id: 'skills-nav', target: '[data-view="skills"]', placement: 'right', title: 'The skill library', action: 'Open the Skill library',
      body: `<p>Everything the character can perform lives here. Click <strong>Skill library</strong>.</p>`,
      done: () => ui.view === 'skills', doIt: () => setView('skills'), doItLabel: 'Open it for me' },
    { id: 'skills-toolbar', view: 'skills', target: '.library-toolbar', placement: 'bottom', title: 'Finding a skill',
      body: `<p>The library ships with 61 motion-capture clips under the BONES-SEED licence, plus anything you generate or compose. Search by words (<kbd>/</kbd> jumps here) and filter by category: locomotion, dance, gestures, idle, actions, floor work, generated, sequences. Every card records its source and licence.</p>` },
    { id: 'skill-card', view: 'skills', target: () => firstClipCard(), placement: 'right', title: 'A skill card',
      body: `<p>Hover the picture to see the clip animate. The badge says how the clip starts and ends (standing, crouching, on the floor): a clip that ends on the floor leaves the character there. <strong>ⓘ</strong> opens the details (duration, travel, source, licence, provenance; play at half speed or twice). <strong>+</strong> adds the clip to a sequence. <strong>Play</strong> performs it in the running session.</p>` },
    { id: 'play', view: 'skills', target: () => firstClipCard() && firstClipCard().querySelector('[data-skill]'), placement: 'right', title: 'Play a clip', action: 'Click Play on any clip',
      body: `<p>In a physical session the tracker follows the clip's motion under physics, starting from the way the character faces now. Acrobatic or floor clips can make it fall; that is physics being honest. Click <strong>Play</strong> on a clip you like; the tutorial switches to the live scene once it is accepted.</p>`,
      done: () => ui.commands.some(c => /^play /.test(c.command) && c.accepted), waitText: 'Waiting for a clip to play…', doIt: () => playSkill('dance_hiphop_power_step_r01_m48'), doItLabel: 'Play the hip-hop step for me' },
    { id: 'skill-chip', view: 'live', target: '.viewport-indicators', placement: 'bottom', title: 'What is playing',
      body: `<p>The chip shows the clip's name and frame progress. <strong>Stop</strong> interrupts it; the character then holds where it is. A clip that moves (a walk, a turn) carries the character with it, within the room.</p>` },
    { id: 'composer', view: 'skills', target: '#composer', placement: 'bottom', title: 'Compose a sequence',
      body: `<p>A <strong>sequence</strong> chains steps: walk to an object or back to the spawn, play clips, wait. The ✋ on a clip step lets the character <em>take</em> an object at a chosen frame of that clip (it snaps to the hand and follows it) and <em>put it down</em> at the end; the object is put down on whatever is under the hand. The worker waits for each step to finish before the next.</p><p>Three steps have been added for you: walk to the cup, a clip that takes the cup, walk back.</p>`,
      prepare: () => { if (!ui.composer.length) { ui.composer = [{ skill: 'walk_to', object: 'cup' }, { skill: 'pocket_searching_r01_m07', attach: { object: 'cup', body: 'RightHand', at_frame: 60 } }, { skill: 'walk_to', x: 0, y: 0, frame: 'spawn' }, { skill: 'release', object: 'cup' }]; renderComposer(); } } },
    { id: 'composer-run', view: 'skills', target: '#composer-run', placement: 'left', title: 'Run it in the scene', action: 'Click Run in scene',
      body: `<p>Click <strong>Run in scene</strong>. The sequence is sent to the worker as one command; the live view shows which step is running.</p>`,
      done: () => ui.commands.some(c => /^sequence/.test(c.command) && c.accepted), waitText: 'Waiting for the sequence to start…', doIt: () => composerRun(), doItLabel: 'Run it for me' },
    { id: 'sequence-watch', view: 'live', target: '.scene-panel', placement: 'bottom', title: 'Watch the sequence',
      body: `<p>Walk to the cup, take it at frame 60 of the clip, carry it back, put it down. The sequence chip counts the steps. Each step has a 90-second limit; a fall cancels the sequence and reports it. This step moves on when the worker reports the sequence finished.</p>`,
      done: () => ui.commands.some(c => /^sequence finished/.test(c.command)), waitText: 'Waiting for the sequence to finish (about 25 seconds)…' },
    { id: 'composer-save', view: 'skills', target: '#composer-save', placement: 'left', title: 'Save it as a skill', optional: true,
      body: `<p><strong>Save as skill</strong> stores the sequence in the library as a composite skill with its own card; it plays like any other and the assistant can call it by name. Give it a name like <code>fetch_the_cup</code> (one already exists from the studio's own tests). This step is optional: save it, or press Next.</p>` },
    { id: 'create', view: 'skills', target: '#create-skill', placement: 'left', title: 'Create a skill from words',
      body: () => (ui.boot && ui.boot.generation_available)
        ? `<p><strong>Create a skill</strong> describes a motion in plain words ("a person bows politely with the hands together") and a local text-to-motion model (NVIDIA Kimodo) generates it on this machine's GPU, on the same skeleton the body uses. It takes about half a minute, mostly loading the model, and needs the GPU free of a running session. The new clip joins the <em>Generated</em> category with its prompt, seed and model version recorded. Try it after the tutorial.</p>`
        : `<p><strong>Create a skill</strong> generates a motion from a text description with a local text-to-motion model. The generator is not installed on this machine yet; see <code>docs/MOTION_GENERATION.md</code>. Until then the description goes to the assistant.</p>` },
    { id: 'characters-nav', target: '[data-view="characters"]', placement: 'right', title: 'Characters', action: 'Open Characters',
      body: `<p>Click <strong>Characters</strong> to see the bodies the studio can render.</p>`, done: () => ui.view === 'characters', doIt: () => setView('characters'), doItLabel: 'Open it for me' },
    { id: 'characters', view: 'characters', target: '#character-grid', placement: 'top', title: 'Rigs and licences',
      body: `<p>Each card is a skinned rig prepared from a licence-checked download: its licence, source, vertex and joint counts, and how many of the body's 23 bones it maps. Rigs with other proportions are scaled to the body's height and keep their own shape. <strong>Use next</strong> selects a character for the next session; the choice is made before a session starts.</p>` },
    { id: 'assistant', target: '.assistant-panel', placement: 'left', title: 'The director’s assistant',
      body: `<p>The assistant does exactly what the buttons do, through the same commands, so everything it does is acknowledged and recorded. Choose a provider at the top: Claude, OpenAI, Gemini, Grok, OpenRouter, or a local LM Studio server. Keys are yours, stored only on this machine (the gear opens the settings) and never written into the project. <strong>Stop</strong> interrupts a turn. Tool calls it makes appear inline, with their results.</p>` },
    { id: 'assistant-send', target: '#chat-form', placement: 'left', title: 'Ask it something', action: 'Send a message',
      body: () => providerReady()
        ? `<p>Try: <em>“Where is she right now, and is she standing?”</em> The assistant reads the live state and answers. Later, try <em>“Walk to the carton, then do the hip-hop step.”</em> It will compose a sequence.</p>`
        : `<p>No provider is ready yet: pick one and enter a key (or start LM Studio locally). This step is optional; press Next to continue.</p>`,
      optional: true, done: () => providerReady() && ui.assistantAnswered, waitText: 'Waiting for the assistant to answer…',
      doIt: () => sendChat('Where is she right now, and is she standing?'), doItLabel: 'Send the question for me', skipIf: () => !providerReady() },
    { id: 'end', view: 'live', target: '#end-session', placement: 'bottom', title: 'End the session', action: 'Click End session',
      body: `<p><strong>End session</strong> asks the worker to finish cleanly: it closes the recording and the launcher runs the evidence gate (clean shutdown, matching frame and step counts, exit code). The result is written to the session's evidence folder. <strong>Force stop</strong> (the power icon) kills the container instead and records a failed session; use it only when something is stuck.</p>`,
      done: () => ui.session && ['ended', 'failed'].includes(ui.session.phase), waitText: 'Waiting for the session to close (about 20 seconds)…', doIt: () => endSession(), doItLabel: 'End it for me' },
    { id: 'project-nav', target: '[data-view="project"]', placement: 'right', title: 'Project', action: 'Open Project',
      body: `<p>Click <strong>Project</strong>.</p>`, done: () => ui.view === 'project', doIt: () => setView('project'), doItLabel: 'Open it for me' },
    { id: 'project', view: 'project', target: '.project-grid', placement: 'top', title: 'Evidence and the machine',
      body: `<p>The locked runtime image digest, the GPU and its load, the studio lock (one heavy GPU job at a time), running containers, and shortcuts: the direction document, the progress log and the <strong>diagnostics</strong> folder where every session's evidence lives (logs, command acknowledgements, the top-down plot, the outcome). The <em>Sessions</em> button in the live scene opens recent sessions and their recordings.</p>` },
    { id: 'done', centered: true, title: 'That is the whole studio',
      body: `<p>You can now start a session, direct the character from the map or the assistant, play and compose skills, pick up objects, generate new motions from words, change characters, and find the recording and evidence of everything afterwards.</p><p>Ideas: ask the assistant to <em>“invent a cheerful greeting, fetch the cup, carry it to the carton and bow”</em>; push the character mid-dance in physical mode; replay a saved sequence in kinematic mode with another character.</p><p>Reopen this tutorial any time from the sidebar; it restarts from the beginning once completed.</p>` },
  ];

  // ---------------------------------------------------------------- DOM
  let root, card, hole, overlay;
  function build() {
    overlay = document.createElement('div'); overlay.className = 'tour-overlay'; overlay.hidden = true;
    overlay.innerHTML = '<div class="tour-shade" data-side="top"></div><div class="tour-shade" data-side="bottom"></div><div class="tour-shade" data-side="left"></div><div class="tour-shade" data-side="right"></div><div class="tour-hole"></div>';
    card = document.createElement('section'); card.className = 'tour-card'; card.hidden = true; card.setAttribute('role', 'dialog'); card.setAttribute('aria-live', 'polite'); card.tabIndex = -1;
    document.body.append(overlay, card);
    hole = overlay.querySelector('.tour-hole');
    root = overlay;
  }
  function resolveTarget(step) { const t = typeof step.target === 'function' ? step.target() : (step.target ? document.querySelector(step.target) : null); return t && t.offsetParent !== null ? t : null; }

  function render() {
    const step = STEPS[state.index];
    const total = STEPS.length;
    const body = typeof step.body === 'function' ? step.body() : step.body;
    const waiting = state.waiting && step.done && !step.done();
    const buttons = [];
    if (state.index > 0) buttons.push('<button class="tour-btn" data-tour="back">← Back</button>');
    if (step.doIt && step.done && !step.done()) buttons.push(`<button class="tour-btn" data-tour="doit">${step.doItLabel || 'Do it for me'}</button>`);
    const last = state.index === total - 1;
    if (!step.done || step.done() || step.optional) buttons.push(`<button class="tour-btn primary" data-tour="next">${last ? 'Finish' : state.index === 0 ? 'Start the tour →' : 'Next →'}</button>`);
    else buttons.push('<button class="tour-btn primary" data-tour="next" disabled title="Do the action above first">Next →</button>');
    card.innerHTML = `<header><span class="tour-step">Step ${state.index + 1} of ${total}</span><span class="tour-spacer"></span><button class="tour-link" data-tour="hide" title="Hide (resume from the sidebar)">Hide</button><button class="tour-link" data-tour="skip">Skip tour</button></header>
      <h3>${step.title}</h3>${step.action ? `<div class="tour-action"><span class="tour-pointer">➜</span>${step.action}</div>` : ''}<div class="tour-body">${body}</div>
      ${waiting || (step.done && !step.done() && step.waitText) ? `<div class="tour-wait"><span class="spinner small"></span>${step.waitText || 'Waiting…'}</div>` : ''}
      <footer>${buttons.join('')}<span class="tour-progress"><span style="width:${Math.round((state.index) / (total - 1) * 100)}%"></span></span></footer>`;
    card.querySelectorAll('[data-tour]').forEach(b => b.onclick = () => ({ back, next, skip, hide, doit: doIt })[b.dataset.tour]());
    card.hidden = false; overlay.hidden = false;
    position();
    card.focus({ preventScroll: true });
  }

  function position() {
    const step = STEPS[state.index];
    const target = step.centered ? null : resolveTarget(step);
    const W = window.innerWidth, H = window.innerHeight;
    const shades = overlay.querySelectorAll('.tour-shade');
    if (!target) {
      hole.style.display = 'none';
      shades.forEach(s => { s.style.display = s.dataset.side === 'top' ? '' : 'none'; });
      shades[0].style.cssText = 'top:0;left:0;right:0;bottom:0';
      card.style.cssText = `left:${Math.max(16, W / 2 - 250)}px;top:${Math.max(16, H / 2 - card.offsetHeight / 2)}px;width:500px`;
      overlay.classList.add('tour-centered');
      return;
    }
    overlay.classList.remove('tour-centered');
    if (state.lastTarget !== target) { state.lastTarget = target; target.scrollIntoView({ block: 'center', inline: 'nearest' }); }
    const r = target.getBoundingClientRect();
    const pad = 8;
    const x = Math.max(0, r.left - pad), y = Math.max(0, r.top - pad), w = Math.min(W, r.right + pad) - x, h = Math.min(H, r.bottom + pad) - y;
    hole.style.display = '';
    hole.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
    shades.forEach(s => s.style.display = '');
    shades[0].style.cssText = `top:0;left:0;right:0;height:${y}px`;
    shades[1].style.cssText = `top:${y + h}px;left:0;right:0;bottom:0`;
    shades[2].style.cssText = `top:${y}px;left:0;width:${x}px;height:${h}px`;
    shades[3].style.cssText = `top:${y}px;left:${x + w}px;right:0;height:${h}px`;
    const cw = Math.min(400, W - 32), ch = card.offsetHeight || 300, gap = 14;
    let place = step.placement || 'right';
    const fits = { right: x + w + gap + cw <= W, left: x - gap - cw >= 0, bottom: y + h + gap + ch <= H, top: y - gap - ch >= 0 };
    if (!fits[place]) place = ['right', 'left', 'bottom', 'top'].find(p => fits[p]) || 'bottom';
    let left, top;
    if (place === 'right') { left = x + w + gap; top = y; }
    else if (place === 'left') { left = x - gap - cw; top = y; }
    else if (place === 'bottom') { left = x; top = y + h + gap; }
    else { left = x; top = y - gap - ch; }
    left = Math.max(16, Math.min(left, W - cw - 16)); top = Math.max(16, Math.min(top, H - ch - 16));
    card.style.cssText = `left:${left}px;top:${top}px;width:${cw}px`;
    card.dataset.place = place;
  }

  function tick() {
    if (!state.active) return;
    position();
    const step = STEPS[state.index];
    if (step.done && state.waiting && step.done()) { state.waiting = null; setTimeout(() => { if (state.active && STEPS[state.index] === step) next(); }, 700); }
    state.raf = requestAnimationFrame(tick);
  }

  function show(index) {
    state.index = Math.max(0, Math.min(STEPS.length - 1, index));
    const step = STEPS[state.index];
    if (step.skipIf && step.skipIf() && index > state.index - 1) { /* fallthrough: optional steps still render */ }
    if (step.view && ui.view !== step.view) setView(step.view);
    if (step.prepare) { try { step.prepare(); } catch (e) { console.error('tour prepare', e); } }
    if ($('#modal').open) closeModal();
    state.lastTarget = null;
    state.waiting = step.done && !step.done() ? step.id : null;
    save();
    render();
    updateSidebar();
  }
  function start(fromStart) { load(); state.active = true; state.completed = fromStart ? false : state.completed; state.dismissed = false; show(fromStart ? 0 : state.index); cancelAnimationFrame(state.raf); state.raf = requestAnimationFrame(tick); }
  function next() {
    if (state.index >= STEPS.length - 1) { finish(); return; }
    show(state.index + 1);
  }
  function back() { show(state.index - 1); }
  function doIt() { const step = STEPS[state.index]; try { step.doIt && step.doIt(); } catch (e) { toast(String(e)); } render(); }
  function hide() { state.active = false; state.dismissed = true; cancelAnimationFrame(state.raf); overlay.hidden = true; card.hidden = true; save(); updateSidebar(); toast('Tutorial hidden. Resume it from the sidebar.'); }
  function skip() { hide(); }
  function finish() { state.completed = true; state.index = 0; state.active = false; cancelAnimationFrame(state.raf); overlay.hidden = true; card.hidden = true; save(); updateSidebar(); toast('Tutorial complete. Reopen it from the sidebar any time.'); }

  function updateSidebar() {
    const label = $('#tutorial-progress'); if (!label) return;
    label.textContent = state.completed ? 'done' : state.index > 0 ? `${state.index + 1}/${STEPS.length}` : 'new';
  }

  function init() {
    build(); load();
    const button = $('#tutorial-button');
    if (button) button.onclick = () => { if (state.active) { hide(); return; } start(state.completed || state.index === 0); };
    updateSidebar();
    document.addEventListener('keydown', e => {
      if (!state.active || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      if (e.key === 'ArrowRight') { const s = STEPS[state.index]; if (!s.done || s.done() || s.optional) { e.preventDefault(); next(); } }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); back(); }
      else if (e.key === 'Escape') { hide(); }
    });
    window.addEventListener('resize', () => state.active && position());
    document.addEventListener('studio:assistant', e => { if (e.detail && e.detail.kind === 'done') ui.assistantAnswered = true; });
    document.addEventListener('studio:view', () => state.active && render());
    // first launch: offer the tour; a tour left in the middle: offer to resume
    if (!state.completed && !state.dismissed && state.index === 0) setTimeout(() => start(true), 900);
    else if (!state.completed && state.index > 0) setTimeout(() => toast(`Tutorial paused at step ${state.index + 1} of ${STEPS.length}: resume it from the sidebar.`), 1500);
  }
  window.studioTour = { start: () => start(true), resume: () => start(false), hide, next, back, steps: STEPS, state };
  if (window.ui && ui.boot) init(); else document.addEventListener('studio:ready', init, { once: true });
})();
