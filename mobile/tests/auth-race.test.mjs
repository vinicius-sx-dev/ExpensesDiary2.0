import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { create } from 'zustand';

function moduleAt(path, imports, globals = {}) {
  const code = ts.transpileModule(fs.readFileSync(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: name => {
    if (!(name in imports)) throw Error(`Unexpected import ${name}`);
    return imports[name];
  }, process: { env: {} }, __DEV__: true, AbortController, setTimeout, clearTimeout, ...globals });
  return exports;
}
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const tick = () => new Promise(r => setImmediate(r));
function auth(vault) { return moduleAt('../src/stores/auth.ts', { zustand: { create }, '../lib/session': { vault } }); }

test('late refresh rejection cannot clear a new login or share its refresh', async () => {
  const vault = { get: async () => null, set: async () => {}, remove: async () => {} };
  const state = auth(vault);
  const pending = [];
  const { api } = moduleAt('../src/lib/api.ts', {
    './session': { deviceId: async () => 'device' }, '../stores/auth': state,
  }, { fetch: (url) => {
    if (!url.endsWith('/auth/refresh')) return Promise.resolve({ ok: true, status: 200, text: async () => '{}' });
    const d = deferred(); pending.push(d); return d.promise;
  }});
  state.useAuth.setState({ refresh: 'old-refresh' });
  const oldRequest = api('/auth/me').catch(e => e);
  await tick();
  await state.useAuth.getState().clear();
  state.useAuth.setState({ refresh: 'new-refresh' });
  const newRequest = api('/auth/me');
  await tick();
  assert.equal(pending.length, 2);
  pending[0].resolve({ ok: false, status: 401, text: async () => '{"detail":"expired"}' });
  await oldRequest;
  assert.equal(state.useAuth.getState().refresh, 'new-refresh');
  pending[1].resolve({ ok: true, status: 200, text: async () => '{"access_token":"new-access","refresh_token":"rotated"}' });
  await newRequest;
  assert.equal(state.useAuth.getState().refresh, 'rotated');
});

test('hydration cannot restore credentials after logout', async () => {
  const read = deferred();
  const { useAuth } = auth({ get: () => read.promise, set: async () => {}, remove: async () => {} });
  const hydrate = useAuth.getState().hydrate();
  await useAuth.getState().clear();
  read.resolve('stale-token');
  await hydrate;
  assert.equal(useAuth.getState().refresh, null);
});
