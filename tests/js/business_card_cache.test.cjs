const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('card refreshes online, retains latest offline data, and never caches the cabinet', async () => {
  const handlers = {}, saved = new Map();
  let online = true, text = 'latest card';
  const context = {
    URL, Response,
    self: {location: {href:'https://mbstudio.scena.life/card/sw.js'}, addEventListener: (name, fn) => handlers[name] = fn},
    caches: {open: async () => ({put: async (key, response) => saved.set(key, response)}), match: async key => saved.get(key)?.clone()},
    fetch: async () => {
      if (!online) throw Error('offline');
      const response = new Response(text);
      Object.defineProperty(response, 'type', {value:'basic'});
      return response;
    },
  };
  vm.runInNewContext(fs.readFileSync('public/card/sw.js', 'utf8'), context);
  async function request(path, mode='navigate') {
    let response;
    const pending = [];
    handlers.fetch({request:{method:'GET', url:'https://mbstudio.scena.life' + path, mode},
      respondWith: promise => response = promise, waitUntil: promise => pending.push(promise)});
    if (!response) return null;
    const result = await response;
    await Promise.all(pending);
    return result;
  }
  assert.equal(await (await request('/card/')).text(), 'latest card');
  text = 'edited name';
  assert.equal(await (await request('/card/?utm_source=nfc')).text(), 'edited name');
  online = false;
  assert.equal(await (await request('/card/')).text(), 'edited name');
  assert.equal(await request('/?page=admin&section=pages&view=card'), null);
  assert.equal(await request('/card/private.json'), null);
  online = true;
  text = 'new portrait';
  await request('/card/portrait.webp?v=revision-2', 'no-cors');
  online = false;
  assert.equal(await (await request('/card/portrait.webp?v=revision-2', 'no-cors')).text(), 'new portrait');
});
