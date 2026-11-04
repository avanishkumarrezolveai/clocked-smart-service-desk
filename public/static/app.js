'use strict';
const $ = id => document.getElementById(id);
const els = {
  content: $('conversation-content'), welcome: $('welcome'), messages: $('messages'), form: $('chat-form'), input: $('message-input'),
  send: $('send-button'), user: $('demo-user'), inspector: $('inspector'), traces: $('trace-events'), traceCount: $('trace-count'),
  modePill: $('mode-pill'), modeText: $('mode-text'), engineTag: $('engine-tag'), engineSubtitle: $('engine-subtitle'),
  engineDescription: $('engine-description'), voice: $('voice-button'), voiceCaption: $('voice-caption'), toast: $('toast')
};
let conversationState = {};
let isLoading = false;
let currentMode = 'demo';
let traceHistory = [];
let toastTimeout;
let recognizer;
let speechActive = false;

function node(tag, className = '', text = '') {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== '') el.textContent = String(text);
  return el;
}
function notify(text) {
  els.toast.textContent = text;
  els.toast.classList.add('show');
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => els.toast.classList.remove('show'), 3600);
}
function scrollBottom() {
  requestAnimationFrame(() => {
    const scroller = document.querySelector('.conversation-wrap');
    scroller.scrollTop = scroller.scrollHeight;
  });
}
function setLoading(on) {
  isLoading = on;
  els.send.disabled = on;
  els.input.disabled = on;
  els.user.disabled = on;
  document.querySelectorAll('.choice:not([disabled]), .asset-button:not([disabled]), .suggestion:not([disabled])').forEach(b => b.disabled = on);
  if (!on) els.input.focus();
}
function makeMessage(role, text) {
  if (els.welcome) els.welcome.hidden = true;
  const shell = node('article', 'message ' + role);
  const avatar = node('div', 'message-avatar', role === 'user' ? 'D' : '✳');
  avatar.setAttribute('aria-hidden', 'true');
  const body = node('div', 'message-body');
  body.append(node('div', 'message-role', role === 'user' ? 'YOU' : 'CLOCKED SERVICE DESK'));
  body.append(node('div', 'message-text', text));
  shell.append(avatar, body);
  els.messages.append(shell);
  scrollBottom();
  return body;
}
function makeCard(type, label) {
  const card = node('div', 'response-card ' + (type === 'complete' ? 'complete-card' : ''));
  card.append(node('div', 'response-card-label', label));
  return card;
}
function addKnowledge(body, card) {
  const box = makeCard('knowledge', 'KNOWLEDGE LIBRARY');
  box.append(node('div', 'knowledge-heading', card.title || 'Relevant guide'));
  box.append(node('div', 'knowledge-content', card.excerpt || ''));
  const ref = node('div', 'knowledge-ref');
  ref.append(node('span', '', card.id || 'KB'));
  ref.append(node('span', '', 'Synthetic knowledge article'));
  box.append(ref);
  body.append(box);
}
function addAssetCards(body, card) {
  const box = makeCard('assets', 'CHOOSE AN ASSET');
  const list = node('div', 'asset-list');
  (card.items || []).forEach(asset => {
    const b = node('button', 'asset-button');
    b.type = 'button';
    b.append(node('span', 'asset-icon', String(asset.device_type).toLowerCase().includes('laptop') ? '▰' : '▣'));
    const details = node('span', 'asset-details');
    details.append(node('strong', '', [asset.manufacturer, asset.model].filter(Boolean).join(' ')));
    details.append(node('small', '', [asset.asset_id, asset.device_type, asset.device_label].filter(Boolean).join(' · ')));
    b.append(details, node('span', 'asset-arrow', '→'));
    b.addEventListener('click', () => runAction('asset:' + asset.asset_id, b.textContent.split('·')[0].trim()));
    list.append(b);
  });
  box.append(list);
  body.append(box);
}
function addReview(body, card) {
  const r = card.record || {};
  const box = makeCard('review', 'READY FOR REVIEW');
  const grid = node('div', 'review-grid');
  [
    ['Ticket type', r.ticket_type], ['Offering', r.offering], ['Category', r.category],
    ['Subcategory', r.subcategory], ['Asset', r.asset], ['Reference', r.offering_id], ['Summary', r.summary]
  ].forEach(([k, v]) => {
    const item = node('div', 'review-item' + (k === 'Summary' ? ' wide' : ''));
    const label = node('label', '', k);
    item.append(label, node('strong', '', v || 'Not required'));
    grid.append(item);
  });
  Object.entries(r.fields || {}).filter(([k]) => !['issue_description', 'request_description', 'asset_id'].includes(k)).forEach(([k, v]) => {
    const item = node('div', 'review-item');
    item.append(node('label', '', k.split('_').join(' ')), node('strong', '', v));
    grid.append(item);
  });
  box.append(grid);
  body.append(box);
}
function addComplete(body, card) {
  const box = makeCard('complete', 'DEMONSTRATION RESULT');
  box.append(node('div', 'complete-emblem', '✓'));
  box.append(node('div', 'complete-heading', card.title || 'Completed'));
  if (card.reference) box.append(node('div', 'complete-ref', card.reference));
  box.append(node('div', 'complete-subtext', card.subtext || ''));
  body.append(box);
}
function addChoices(body, choices) {
  if (!choices || !choices.length) return;
  const group = node('div', 'choices');
  choices.forEach(choice => {
    const b = node('button', 'choice', choice.label || choice.value);
    b.type = 'button';
    b.addEventListener('click', () => runAction(choice.value, choice.label));
    group.append(b);
  });
  body.append(group);
}
function disablePreviousActions() {
  document.querySelectorAll('.choices button, .asset-list button').forEach(el => el.disabled = true);
}
function renderResult(result) {
  if (!result || typeof result.message !== 'string') throw new Error('Unexpected server response');
  conversationState = result.state || {};
  disablePreviousActions();
  const body = makeMessage('assistant', result.message);
  const card = result.card || {};
  if (card.type === 'knowledge') addKnowledge(body, card);
  else if (card.type === 'assets') addAssetCards(body, card);
  else if (card.type === 'review') addReview(body, card);
  else if (card.type === 'complete') addComplete(body, card);
  addChoices(body, result.choices || []);
  if (Array.isArray(result.trace) && result.trace.length) appendTraces(result.trace);
  scrollBottom();
}
function showTyping() {
  const body = makeMessage('assistant', '');
  const bubble = body.querySelector('.message-text');
  bubble.setAttribute('aria-label', 'Thinking');
  const dots = node('div', 'typing');
  for (let i = 0; i < 3; i++) dots.append(node('i'));
  bubble.append(dots);
  return body.parentNode;
}
async function post(path, data) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const res = await fetch(path, {method:'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data), signal: controller.signal});
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  } finally { clearTimeout(timer); }
}
async function sendText(text) {
  text = String(text || '').trim();
  if (!text || isLoading) return;
  makeMessage('user', text);
  els.input.value = '';
  resizeComposer();
  setLoading(true);
  const typing = showTyping();
  try {
    const result = await post('/api/chat', {text, user_id: els.user.value, state: conversationState});
    typing.remove();
    renderResult(result);
  } catch (e) {
    typing.remove();
    makeMessage('assistant', e.name === 'AbortError' ? 'The request took too long. Please try again.' : 'I could not complete that request. Please retry, or start a new conversation.');
    notify('Connection issue: ' + e.message);
  } finally { setLoading(false); }
}
async function runAction(action, label) {
  if (isLoading) return;
  makeMessage('user', label || action);
  setLoading(true);
  const typing = showTyping();
  try {
    const result = await post('/api/action', {action, user_id: els.user.value, state: conversationState});
    typing.remove();
    renderResult(result);
  } catch (e) {
    typing.remove();
    makeMessage('assistant', 'The action could not be completed. Please try again.');
    notify('Action failed: ' + e.message);
  } finally { setLoading(false); }
}
function appendTraces(events) {
  traceHistory.push(...events);
  traceHistory = traceHistory.slice(-48);
  els.traces.textContent = '';
  traceHistory.slice().reverse().forEach(item => {
    const card = node('div', 'trace-item');
    const top = node('div', 'trace-top');
    top.append(node('span', 'trace-type', String(item.endpoint || 'Action').toUpperCase()));
    const tag = node('span', 'trace-origin ' + (item.origin || 'demo'), item.origin === 'live' ? 'REAL API' : item.origin === 'error' ? 'API ERROR' : 'LOCAL');
    top.append(tag);
    card.append(top);
    const headline = item.origin === 'live' ? 'Clocked API completed' : item.origin === 'error' ? 'Clocked request failed' : 'Local workflow step';
    card.append(node('strong', '', headline));
    card.append(node('div', 'trace-detail', [item.detail, Number.isFinite(item.duration_ms) ? `${item.duration_ms} ms` : ''].filter(Boolean).join(' · ')));
    if (item.result && typeof item.result === 'object') {
      const details = node('details');
      details.append(node('summary', '', 'Inspect API response'));
      details.append(node('pre', '', JSON.stringify(item.result, null, 2).slice(0, 12000)));
      card.append(details);
    }
    els.traces.append(card);
  });
  els.traceCount.textContent = `${traceHistory.length} event${traceHistory.length === 1 ? '' : 's'}`;
}
function resetTraces() {
  traceHistory = [];
  els.traceCount.textContent = '0 events';
  els.traces.textContent = '';
  const e = node('div', 'trace-empty');
  e.append(node('span', '', '◎'), node('strong', '', 'No activity yet'), node('p', '', 'Make a request to see the decisions, validations and actions that shaped the response.'));
  els.traces.append(e);
}
function newConversation() {
  if (isLoading) return;
  conversationState = {};
  els.messages.textContent = '';
  els.welcome.hidden = false;
  els.input.value = '';
  resetTraces();
  els.input.focus();
  resizeComposer();
  notify('New conversation started');
}
function toggleInspector(show) {
  els.inspector.classList.toggle('open', show);
  $('nav-decisions').classList.toggle('active', show);
  $('nav-support').classList.toggle('active', !show);
  if (show) els.inspector.querySelector('.inspector-close').focus();
}
function resizeComposer() {
  els.input.style.height = 'auto';
  els.input.style.height = Math.min(120, Math.max(40, els.input.scrollHeight)) + 'px';
}
async function loadStatus() {
  try {
    const res = await fetch('/api/status', {cache:'no-store'});
    if (!res.ok) throw Error('Could not load status');
    const data = await res.json();
    currentMode = data.mode === 'live' ? 'live' : 'demo';
    els.modePill.classList.toggle('demo', currentMode !== 'live');
    els.modeText.textContent = currentMode === 'live' ? 'API configured' : 'Local demo';
    els.engineTag.className = 'engine-tag' + (currentMode === 'live' ? ' live' : '');
    els.engineTag.textContent = currentMode === 'live' ? 'LIVE CONNECTION CONFIGURED' : 'DEMONSTRATION MODE';
    els.engineSubtitle.textContent = currentMode === 'live' ? 'SDK connection enabled' : 'Safe, offline catalog logic';
    els.engineDescription.textContent = currentMode === 'live'
      ? 'Clocked requests are enabled. The activity log marks successful API calls and failures individually. A configured key is not proof of successful calls.'
      : 'No Clocked API key is configured. The service desk uses transparent local rules and sample data; these are never presented as real API decisions.';
    if (Array.isArray(data.users)) {
      els.user.textContent = '';
      data.users.forEach(u => {
        const o = document.createElement('option'); o.value = u.id; o.textContent = u.name + ' · ' + u.id; els.user.append(o);
      });
    }
  } catch(e) {notify('Could not reach the service desk. Please reload the page.');}
}
function setupVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    els.voice.title = 'Voice input is unavailable in this browser';
    els.voice.addEventListener('click', () => notify('Voice input is unavailable here. You can type your question instead.'));
    return;
  }
  recognizer = new SR();
  recognizer.lang = 'en-US';
  recognizer.interimResults = false;
  recognizer.maxAlternatives = 1;
  recognizer.onresult = event => {
    const transcript = event.results?.[0]?.[0]?.transcript;
    if (transcript) { els.input.value = transcript; resizeComposer(); els.input.focus(); notify('Voice captured. Review or send your message.'); }
  };
  recognizer.onend = () => {speechActive = false; els.voice.classList.remove('listening'); els.voiceCaption.textContent = 'Use voice or keyboard';};
  recognizer.onerror = () => notify('Voice input was unavailable. Please use the keyboard.');
  els.voice.addEventListener('click', () => {
    try {
      if (speechActive) recognizer.stop(); else recognizer.start();
      speechActive = !speechActive;
      els.voice.classList.toggle('listening', speechActive);
      els.voiceCaption.textContent = speechActive ? 'Listening…' : 'Use voice or keyboard';
    } catch (e) {notify('Voice input is unavailable right now.');}
  });
}
els.form.addEventListener('submit', e => {e.preventDefault(); sendText(els.input.value);});
els.input.addEventListener('input', resizeComposer);
els.input.addEventListener('keydown', e => {if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {e.preventDefault(); sendText(els.input.value);}});
document.querySelectorAll('.suggestion').forEach(btn => btn.addEventListener('click', () => sendText(btn.dataset.prompt)));
$('reset-button').addEventListener('click', newConversation);
els.user.addEventListener('change', newConversation);
$('show-inspector').addEventListener('click', () => toggleInspector(true));
$('nav-decisions').addEventListener('click', () => toggleInspector(true));
$('nav-support').addEventListener('click', () => toggleInspector(false));
$('close-inspector').addEventListener('click', () => toggleInspector(false));
$('clear-trace').addEventListener('click', resetTraces);
document.addEventListener('keydown', e => {if (e.key === 'Escape') toggleInspector(false);});
setupVoice(); loadStatus();
