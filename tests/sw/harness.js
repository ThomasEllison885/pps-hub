/* Loads the REAL static/sw.js into a stubbed worker global and drives its
   handlers. Tests the shipped file, not a copy of its logic. */
const fs = require('fs');
const vm = require('vm');

function makeEnv({ networkFails = false, cachePreloaded = {} } = {}) {
  const store = new Map(Object.entries(cachePreloaded));
  const listeners = {};
  const puts = [];
  const cacheObj = {
    async match(req) {
      const key = typeof req === 'string' ? req : req.url;
      return store.has(key) ? store.get(key) : undefined;
    },
    async add(req) {
      const url = typeof req === 'string' ? req : req.url;
      if (networkFails) throw new Error('offline');
      store.set(url, { ok: true, url, body: 'precached' });
    },
    async put(req, res) { puts.push(typeof req === 'string' ? req : req.url); store.set(req.url, res); },
    async keys() { return [...store.keys()].map(u => ({ url: u })); },
  };
  const sandbox = {
    console,
    URL,
    Response: class { constructor(body, init) { this.body = body; Object.assign(this, init || {}); this.ok = !init || !init.status || init.status < 400; } },
    Request: class { constructor(url, init) { this.url = String(url); Object.assign(this, init || {}); } },
    caches: {
      _names: ['pps-static-old', 'pps-static-TESTVER', 'someone-elses-cache'],
      _deleted: [],
      async open() { return cacheObj; },
      async keys() { return this._names; },
      async delete(n) { this._deleted.push(n); return true; },
      async match(u) { return cacheObj.match(u); },
    },
    fetch: async (req) => {
      if (networkFails) throw new TypeError('Failed to fetch');
      return { ok: true, type: 'basic', url: req.url || req, clone: () => ({}) };
    },
    self: {
      location: { origin: 'https://hub.example' },
      addEventListener: (t, fn) => { listeners[t] = fn; },
      skipWaiting: async () => { sandbox.self._skipWaiting = true; },
      clients: { claim: async () => { sandbox.self._claimed = true; }, matchAll: async () => [] },
      registration: { unregister: async () => { sandbox.self._unregistered = true; return true; } },
    },
  };
  sandbox.self.caches = sandbox.caches;
  vm.createContext(sandbox);
  const src = fs.readFileSync(
    require('path').join(__dirname, '..', '..', 'static', 'sw.js'), 'utf8')
                .replace('__SW_VERSION__', 'TESTVER');
  vm.runInContext(src, sandbox);
  return { sandbox, listeners, cacheObj, puts, store };
}

async function fire(listeners, type, event) {
  const waits = [];
  const responses = [];
  const e = Object.assign({
    waitUntil: (pr) => waits.push(pr),
    respondWith: (pr) => responses.push(pr),
  }, event);
  listeners[type](e);
  await Promise.all(waits);
  return responses.length ? await responses[0] : undefined;
}

module.exports = { makeEnv, fire };
