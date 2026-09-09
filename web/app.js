const $ = (id) => document.getElementById(id);
function chart(values) {
  const max = Math.max(5, ...values);
  const svg = $('chart');
  svg.replaceChildren();
  function node(tag, attrs, text) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    svg.append(n); return n;
  }
  for (let i = 0; i <= 4; i++) {
    const y = 190 - i * 42;
    node('line', {x1:45, x2:945, y1:y, y2:y, stroke:'#2c4552'});
    node('text', {x:35, y:y+4, fill:'#91aab8', 'text-anchor':'end', 'font-size':12}, (max*i/4).toFixed(1));
  }
  // The Qt implementation reverses the array against descending x positions;
  // in left-to-right chronological order, the incoming array is unchanged.
  values.forEach((v, i) => {
    const height = Math.max(0, v) / max * 168;
    const bar = node('rect', {x:49+i*30, y:190-height, width:22, height, rx:3, fill:'#48b9c5'});
    const title = document.createElementNS(svg.namespaceURI, 'title');
    title.textContent = `${58-i*2} minutes ago: ${v} L`; bar.append(title);
  });
  for (const [x, label] of [[45,'−60 min'],[345,'−40'],[645,'−20'],[945,'Now']])
    node('text', {x, y:218, fill:'#91aab8', 'font-size':12, 'text-anchor':x===945?'end':'start'}, label);
  svg.setAttribute('aria-label', `Last hour rainfall in litres, oldest to newest: ${values.join(', ')}`);
}
function render(state) {
  $('connection').textContent = state.demo ? 'Demo · simulated readings' : state.connected ? 'MQTT connected' : 'MQTT disconnected · retrying';
  $('connection').className = state.demo || state.connected ? 'good' : 'bad';
  for (const [kind, data] of Object.entries(state.sensors)) {
    if (!data) continue;
    const card = $(kind);
    card.querySelectorAll('[data-value]').forEach(el => {
      const value = data[el.dataset.value];
      el.textContent = value == null ? '—' : el.dataset.value === 'battery' ? value.toFixed(1) : value;
    });
    const age = Math.max(0, Math.floor(Date.now()/1000-data.updated_at));
    card.querySelector('.age').textContent = `Updated ${age < 60 ? age+'s' : Math.floor(age/60)+'m'} ago`;
    card.classList.toggle('stale', age > 300);
  }
  const s = state.sensors;
  if (s.house) { $('water').style.height = `${s.house.percent}%`; $('percent').textContent = `${Math.round(s.house.percent)}% full · 185 cm capacity`; }
  if (s.hill) { $('switch').textContent = `Switch state ${Number(s.hill.sstate)}`; $('switch').className = `badge ${s.hill.sstate ? 'good' : 'bad'}`; }
  if (s.valve) { $('valve-state').textContent = s.valve.open ? 'Open' : 'Closed'; $('valve-state').className = `metric ${s.valve.open ? 'good' : 'bad'}`; }
  if (s.rain) chart(s.rain.litres);
  $('errors').textContent = state.invalid_messages ? `${state.invalid_messages} invalid messages ignored.` : '';
}
async function refresh() {
  try {
    const response = await fetch('/api/state', {cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Server unavailable');
    render(await response.json());
  } catch {
    $('connection').textContent = 'Dashboard offline · retrying';
    $('connection').className = 'bad';
    document.querySelectorAll('.age').forEach(el => el.textContent = 'Connection lost · last known reading');
  } finally { setTimeout(refresh, 1000); }
}
refresh();
