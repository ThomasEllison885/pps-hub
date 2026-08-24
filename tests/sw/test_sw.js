/* Service worker behaviour, driven against the real static/sw.js.
 *
 * Run: node tests/sw/test_sw.js      (exits non-zero on any failure)
 *
 * This is a Node script rather than a pytest file because the thing under test
 * is JavaScript. Browser-level offline emulation was tried first and abandoned:
 * neither Playwright's setOffline nor its route interception reaches a service
 * worker's own fetch() in this setup, so the offline branch could not be proven
 * that way. Driving the handlers directly tests the shipped file itself.
 *
 * The assertion that matters most is "navigation is never cached". Every page
 * in the Hub sits behind a 30-day session cookie; a cached page is one that can
 * be served to the wrong person, or after sign-out, and a cached /login served
 * to a valid session is the Safari redirect loop from 0e3f5d2 made permanent.
 */
const { makeEnv, fire } = require('./harness');
let failures = 0;
const ok = (label, cond, extra='') => {
  if (!cond) failures++;
  console.log(`${cond ? 'PASS' : '**FAIL**'}  ${label}${extra ? ' — ' + extra : ''}`);
};
process.on('exit', () => {
  if (failures) {
    console.log(`\n${failures} failure(s)`);
    process.exitCode = 1;
  }
});

(async () => {
  // --- install precaches, and survives a missing asset ---
  let env = makeEnv();
  await fire(env.listeners, 'install', {});
  const keys = (await env.cacheObj.keys()).map(k => k.url).sort();
  ok('install precaches offline + static', keys.includes('/offline') && keys.includes('/static/pps-global.css'), JSON.stringify(keys));
  ok('install calls skipWaiting', env.sandbox.self._skipWaiting === true);

  env = makeEnv({ networkFails: true });
  await fire(env.listeners, 'install', {});
  ok('install survives every asset failing', env.sandbox.self._skipWaiting === true);

  // --- activate drops only OUR old caches ---
  env = makeEnv();
  await fire(env.listeners, 'activate', {});
  const del = env.sandbox.caches._deleted;
  ok('activate deletes the old version', del.includes('pps-static-old'));
  ok('activate keeps the current version', !del.includes('pps-static-TESTVER'));
  ok("activate leaves other origins' caches alone", !del.includes('someone-elses-cache'), JSON.stringify(del));
  ok('activate claims clients', env.sandbox.self._claimed === true);

  // --- fetch: what it refuses to touch ---
  const req = (url, extra={}) => Object.assign({ url, method: 'GET', mode: 'no-cors' }, extra);
  env = makeEnv();
  ok('POST is ignored',        undefined === await fire(env.listeners,'fetch',{request:req('https://hub.example/x',{method:'POST'})}));
  ok('cross-origin is ignored',undefined === await fire(env.listeners,'fetch',{request:req('https://other.example/x')}));
  // NB: this passes whether or not the explicit /api/ guard exists, because the
  // static-only rule already excludes it. Kept as a statement of the contract,
  // not as proof the guard is load-bearing — verified by mutation.
  ok('/api/ is ignored',       undefined === await fire(env.listeners,'fetch',{request:req('https://hub.example/api/thing')}));
  ok('non-static HTML GET ignored', undefined === await fire(env.listeners,'fetch',{request:req('https://hub.example/dashboard')}));

  // --- THE rule: navigation never comes from cache ---
  env = makeEnv();
  let res = await fire(env.listeners,'fetch',{request:req('https://hub.example/dashboard',{mode:'navigate'})});
  ok('navigation goes to the network', res && res.ok === true && res.url === 'https://hub.example/dashboard');
  ok('navigation is never cached', env.puts.length === 0, 'puts=' + JSON.stringify(env.puts));

  // --- offline navigation falls back to the precached offline page ---
  env = makeEnv({ networkFails: true, cachePreloaded: { '/offline': { ok:true, url:'/offline', body:'OFFLINE PAGE' } } });
  res = await fire(env.listeners,'fetch',{request:req('https://hub.example/dashboard',{mode:'navigate'})});
  ok('offline navigation serves /offline', res && res.body === 'OFFLINE PAGE', JSON.stringify(res && res.body));

  // --- and degrades further if even that is missing ---
  env = makeEnv({ networkFails: true });
  res = await fire(env.listeners,'fetch',{request:req('https://hub.example/dashboard',{mode:'navigate'})});
  ok('no offline page -> a 503, not a hang', res && res.status === 503);

  // --- static: cache first, then network ---
  env = makeEnv({ cachePreloaded: { 'https://hub.example/static/a.css': { ok:true, body:'CACHED CSS' } } });
  res = await fire(env.listeners,'fetch',{request:req('https://hub.example/static/a.css')});
  ok('static served from cache', res && res.body === 'CACHED CSS');

  env = makeEnv();
  res = await fire(env.listeners,'fetch',{request:req('https://hub.example/static/b.css')});
  ok('static falls through to network', res && res.ok === true);
  await new Promise(r => setTimeout(r, 10));
  ok('static response is stored', env.puts.includes('https://hub.example/static/b.css'), JSON.stringify(env.puts));

  // --- unregister message ---
  env = makeEnv();
  env.listeners['message']({ data: 'unregister' });
  await new Promise(r => setTimeout(r, 20));
  ok('unregister message removes the worker', env.sandbox.self._unregistered === true);
})();
