const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../static/app.js', 'utf8');
const functions = source.slice(source.indexOf('function showPublicLanding()'), source.indexOf('function openModal('));
function context(values = {}) {
  const app = {innerHTML: 'ORIGINAL SERVER HTML', querySelector: () => true};
  const main = {innerHTML: ''};
  const calls = [];
  const ctx = {URLSearchParams, publicLanding: 'ORIGINAL SERVER HTML', location: {hash:'', search:''}, user:null, initialized:true, initializationError:'', pollTimer:0, routeVersion:0, clearTimeout(){}, calls, app, main,
    $: s => s === '#app' ? app : main, shell: route => calls.push(['shell',route]), studio: () => calls.push(['studio']), accountPage: () => calls.push(['account']), documentsPage: async () => calls.push(['documents']), walletPage: async () => calls.push(['wallet']), needAccount(){}, esc: String, goto: route => calls.push(['goto',route]),
    ...values};
  vm.createContext(ctx); vm.runInContext(functions, ctx); return ctx;
}

test('anonymous root keeps server-rendered marketing before and after initialization', async () => {
  for (const initialized of [false, true]) {
    const ctx = context({initialized}); await ctx.render();
    assert.equal(ctx.app.innerHTML, 'ORIGINAL SERVER HTML'); assert.equal(ctx.calls.length, 0);
  }
});

test('a studio click before config finishes loads then opens studio after init', async () => {
  const ctx = context({initialized:false, location:{hash:'#studio',search:''}});
  await ctx.render(); assert.match(ctx.app.innerHTML, /Opening your writing studio/); assert.equal(ctx.calls.length,0);
  ctx.initialized = true; await ctx.render(); assert.deepEqual(ctx.calls, [['shell','studio'],['studio']]);
});

test('signed-in root and app deep links retain application routes', async () => {
  for (const [hash, user, wanted] of [['',{name:'User'},'studio'], ['#documents',null,'documents'],['#wallet',null,'wallet'],['#account',null,'account']]) {
    const ctx = context({location:{hash,search:''},user}); await ctx.render();
    assert.deepEqual(ctx.calls, [['shell',wanted],[wanted]]);
  }
});

test('reset, checkout and setup URLs do not enter the marketing landing', () => {
  for (const search of ['?reset=token','?checkout=success','?setup=1']) {
    const ctx = context({location:{hash:'',search}}); assert.equal(ctx.showPublicLanding(),false);
  }
});

test('returning to root restores cached server content without needing another request', async () => {
  const ctx = context(); ctx.app.innerHTML='WORKSPACE'; ctx.app.querySelector=()=>null; await ctx.render();
  assert.equal(ctx.app.innerHTML,'ORIGINAL SERVER HTML'); assert.equal(ctx.calls.length,0);
});

test('server failure leaves public content readable and explains unavailable studio', async () => {
  const ctx = context({initializationError:'unavailable'}); await ctx.render(); assert.equal(ctx.app.innerHTML,'ORIGINAL SERVER HTML');
  ctx.location.hash='#studio'; await ctx.render(); assert.match(ctx.main.innerHTML,/could not connect/); assert.deepEqual(ctx.calls,[['shell','studio']]);
});

test('skip-to-content hash does not remount or discard a draft', () => {
  let callback, focused=0, saved=0, rendered=0;
  const handler = source.split('\n').find(line => line.startsWith("window.addEventListener('hashchange'"));
  vm.runInNewContext(handler, {window:{addEventListener:(name, cb)=>callback=cb,scrollTo(){}},location:{hash:'#main'},document:{getElementById:()=>({focus:()=>focused++})},saveDraft:()=>saved++,render:()=>rendered++});
  callback(); assert.equal(focused,1); assert.equal(saved,0); assert.equal(rendered,0);
});
