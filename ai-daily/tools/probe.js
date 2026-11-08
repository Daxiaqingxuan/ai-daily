// 布局探针：CDP 连无头 Edge，量顶栏实际宽度并可选触发分享面板
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

const PORT = 9333;
const url = process.argv[2];
const shotPath = process.argv[3] || '';
const action = process.argv[4] || 'measure';

const TARGETS = {
  measure: `JSON.stringify({
    vw: innerWidth,
    topbar: (function(){var r=document.querySelector('.topbar').getBoundingClientRect();return {l:Math.round(r.left),w:Math.round(r.width),r:Math.round(r.right)};})(),
    brand: (function(){var r=document.querySelector('.brand').getBoundingClientRect();return {l:Math.round(r.left),w:Math.round(r.width)};})(),
    label: (function(){var r=document.querySelector('.issue-label').getBoundingClientRect();return {l:Math.round(r.left),w:Math.round(r.width),scrollW:document.querySelector('.issue-label').scrollWidth};})(),
    actions: (function(){var r=document.querySelector('.actions').getBoundingClientRect();return {l:Math.round(r.left),w:Math.round(r.width),r:Math.round(r.right)};})(),
    btns: Array.prototype.map.call(document.querySelectorAll('.actions .btn'), function(b){
      var r=b.getBoundingClientRect();
      return {id:b.id, l:Math.round(r.left), w:Math.round(r.width), hidden:b.hidden, txt:(b.textContent||'').trim()};
    })
  })`,
  share: `(async function(){
    document.getElementById('shareBtn').click();
    await new Promise(function(r){ setTimeout(r, 500); });
    return JSON.stringify({
      open: document.body.classList.contains('share-open'),
      title: document.getElementById('shareTitle').textContent,
      link: document.getElementById('shareLink').textContent,
      copyDisabled: document.getElementById('shareCopy').disabled,
      nativeHidden: document.getElementById('shareNative').hidden,
      note: document.getElementById('shareNote').textContent,
      disclaimer: (document.getElementById('shareDisclaimer')||{}).textContent || '',
      disclaimerVisible: (function(){var n=document.getElementById('shareDisclaimer');if(!n)return false;var r=n.getBoundingClientRect();return r.height>0 && r.top>=0 && r.bottom<=innerHeight;})(),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      sheet: (function(){var r=document.getElementById('shareSheet').getBoundingClientRect();return {w:Math.round(r.width),bottom:Math.round(r.bottom),top:Math.round(r.top)};})()
    });
  })()`,
  // 窄屏目录按钮的行为断言：首屏可见 → 下滚收起 → 上滚回来 → 回顶可见 → 开面板必可见。
  // 只看一张静态截图会漏掉「收起来就再也不回来」这种更糟的情形。
  mobbtn: `(async function(){
    var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
    var b = document.getElementById('mobBtn'), body = document.body, log = {};
    function snap(tag){
      if (!b) { log[tag] = 'NO #mobBtn'; return; }
      var r = b.getBoundingClientRect(), cs = getComputedStyle(b);
      log[tag] = {
        tucked: body.classList.contains('mob-btn-tuck'),
        opacity: Math.round(parseFloat(cs.opacity) * 100) / 100,
        size: Math.round(r.width) + 'x' + Math.round(r.height),
        right: Math.round(innerWidth - r.right),
        bottomGap: Math.round(innerHeight - r.bottom)
      };
    }
    snap('首屏');
    window.scrollBy({ top: 900, behavior: 'instant' }); await sleep(420); snap('下滚900');
    window.scrollBy({ top: -400, behavior: 'instant' }); await sleep(420); snap('上滚400');
    window.scrollTo({ top: 0, behavior: 'instant' }); await sleep(320); snap('回顶部');
    if (b) {
      b.click(); await sleep(300);
      log['开面板'] = { open: body.classList.contains('mob-open'),
                        opacity: Math.round(parseFloat(getComputedStyle(b).opacity) * 100) / 100 };
      b.click(); await sleep(200);
    }
    return JSON.stringify(log);
  })()`,
  flow: `(async function(){
    var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
    var body = document.body, log = {};
    document.getElementById('shareBtn').click();
    await sleep(380);
    log.opened = body.classList.contains('share-open');
    document.getElementById('shareCopy').click();
    await sleep(320);
    log.copyLabel = document.getElementById('shareCopy').textContent;
    log.copyDisabled = document.getElementById('shareCopy').disabled;
    document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
    await sleep(120);
    log.closedByEsc = !body.classList.contains('share-open');
    document.dispatchEvent(new KeyboardEvent('keydown', {key:'s', bubbles:true}));
    await sleep(320);
    log.openedByKey = body.classList.contains('share-open');
    document.getElementById('shareScrim').click();
    await sleep(120);
    log.closedByScrim = !body.classList.contains('share-open');
    return JSON.stringify(log);
  })()`,
  channels: `(async function(){
    var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
    var log = {};
    document.getElementById('shareBtn').click();
    await sleep(320);
    log.buttons = Array.prototype.map.call(document.querySelectorAll('.share-ch .btn'), function(b){
      var r = b.getBoundingClientRect();
      return {id:b.id, txt:b.textContent.trim(), w:Math.round(r.width), h:Math.round(r.height)};
    });
    log.actionBtns = Array.prototype.map.call(document.querySelectorAll('.share-actions .btn'), function(b){
      return {id:b.id, txt:b.textContent.trim(), hidden:b.hidden};
    });
    document.getElementById('shareWx').click();
    await sleep(380);
    log.wx = {open:document.getElementById('shareGuide').classList.contains('on'),
              title:document.getElementById('guideTitle').textContent,
              body:document.getElementById('guideBody').textContent};
    document.getElementById('shareQq').click();
    await sleep(300);
    log.qq = {title:document.getElementById('guideTitle').textContent,
              body:document.getElementById('guideBody').textContent};
    log.sheetTop = Math.round(document.getElementById('shareSheet').getBoundingClientRect().top);
    log.guideRect = (function(){var r=document.getElementById('shareGuide').getBoundingClientRect();
      return {l:Math.round(r.left),t:Math.round(r.top),w:Math.round(r.width),b:Math.round(r.bottom)};})();
    return JSON.stringify(log);
  })()`,
  gloss: `JSON.stringify((function(){
    function r(el){ if(!el) return null; var b=el.getBoundingClientRect();
      return {l:Math.round(b.left), r:Math.round(b.right), w:Math.round(b.width)}; }
    var g = document.querySelector('.gloss'), gg = document.querySelector('.gloss-grid');
    var cs = gg ? getComputedStyle(gg) : null;
    return {gloss:r(g), grid:r(gg), dt:r(document.querySelector('.gloss dt')),
            dd:r(document.querySelector('.gloss dd')),
            cols:cs && cs.columnCount, colW:cs && cs.columnWidth, gap:cs && cs.columnGap,
            disp:cs && cs.display, cssW:cs && cs.width, float:cs && cs.cssFloat,
            pDisp: g && getComputedStyle(g).display, pW: g && getComputedStyle(g).width};
  })())`,
  wide: `JSON.stringify((function(){
    var cw = document.documentElement.clientWidth, out = [];
    Array.prototype.forEach.call(document.querySelectorAll('body *'), function(el){
      var r = el.getBoundingClientRect();
      if (r.right > cw + 1 || r.width > cw + 1){
        out.push({tag:el.tagName, cls:String(el.className || '').slice(0, 34),
                  l:Math.round(r.left), r:Math.round(r.right), w:Math.round(r.width)});
      }
    });
    return {cw:cw, sw:document.documentElement.scrollWidth, iw:innerWidth, n:out.length, items:out.slice(0, 14)};
  })())`,
  paper: `(async function(){
    var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
    var de = document.documentElement, log = {};
    log.sw = de.scrollWidth; log.cw = de.clientWidth; log.vw = innerWidth;
    var d = document.querySelector('.digest');
    if (d){ var r = d.getBoundingClientRect();
      log.digest = {top:Math.round(r.top + scrollY), bottom:Math.round(r.bottom + scrollY), items:d.querySelectorAll('li').length}; }
    log.terms = [];
    var els = Array.prototype.slice.call(document.querySelectorAll('.term'));
    for (var i = 0; i < els.length; i++){
      var el = els[i];
      el.click();
      await sleep(80);
      var tip = el.querySelector('.tip'), tr = tip.getBoundingClientRect();
      log.terms.push({t:el.textContent.trim().slice(0, 10), l:Math.round(tr.left), r:Math.round(tr.right),
                      ok:tr.left >= 0 && tr.right <= innerWidth && tip.offsetWidth > 0});
    }
    log.swAfter = de.scrollWidth;
    return JSON.stringify(log);
  })()`,
  special: `(async function(){
    var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
    var log = {};
    // 1) 首屏落在最新一期（当天特刊 003-2），此时不该再提示「另有特刊」
    log.first = {
      label: document.getElementById('lblFull').textContent,
      frame: document.getElementById('paper').getAttribute('src'),
      url: location.search,
      barHidden: document.getElementById('spbar').hidden
    };
    // 2) 往期回顾是一份序列：特刊与正刊同列，编号带 -2
    var cards = [].slice.call(document.querySelectorAll('#shelfList .issue-card'));
    log.shelf = {
      count: cards.length,
      specials: cards.filter(function(c){ return c.classList.contains('is-special'); }).length,
      nos: cards.slice(0, 3).map(function(c){ return c.querySelector('.ic-no').textContent; })
    };
    // 3) 翻回当天正刊，横幅应出现，且不遮住正文
    var mainIdx = cards.findIndex(function(c){ return !c.classList.contains('is-special'); });
    cards[mainIdx].click();
    await sleep(500);
    var bar = document.getElementById('spbar'), br = bar.getBoundingClientRect();
    log.bar = {hidden: bar.hidden, top: Math.round(br.top), h: Math.round(br.height),
               txt: document.getElementById('spbarTxt').textContent};
    var v = document.getElementById('viewer').getBoundingClientRect();
    log.viewerTop = Math.round(v.top);
    log.gap = Math.round(v.top - br.bottom);
    // 4) 点横幅进特刊
    document.getElementById('spbarGo').click();
    await sleep(700);
    log.after = {
      frame: document.getElementById('paper').getAttribute('src'),
      label: document.getElementById('lblFull').textContent,
      url: location.search,
      barHidden: bar.hidden,
      hasSpecialClass: document.body.classList.contains('has-special'),
      curSpecial: document.querySelectorAll('#shelfList .issue-card.is-special.is-current').length
    };
    document.getElementById('shareBtn').click();
    await sleep(340);
    log.share = {link: document.getElementById('shareLink').textContent,
                 title: document.getElementById('shareTitle').textContent};
    return JSON.stringify(log);
  })()`,
};

// ---- 自己找浏览器、自己起 CDP ----
// 以前要人先手敲「msedge --headless --remote-debugging-port=9333」，
// 换台机器第一步就卡住。现在探针自己找、自己起、跑完自己收。
function findBrowser () {
  const cands = [];
  if (process.env.CHROME_PATH) cands.push(process.env.CHROME_PATH);
  if (process.platform === 'win32') {
    for (const base of [process.env['ProgramFiles(x86)'], process.env.ProgramFiles]) {
      if (!base) continue;
      cands.push(path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
      cands.push(path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'));
    }
  } else if (process.platform === 'darwin') {
    cands.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
    cands.push('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  }
  for (const p of cands) {
    try { if (p && fs.existsSync(p)) return p; } catch { /* ignore */ }
  }
  return '';
}

async function cdpList () {
  const res = await fetch(`http://127.0.0.1:${PORT}/json/list`);
  return res.json();
}

async function ensureBrowser () {
  try {
    const list = await cdpList();
    if (list.some(t => t.type === 'page')) return null;
  } catch { /* 端口没起来，下面自己起一个 */ }

  const exe = findBrowser();
  if (!exe) {
    throw new Error('端口 ' + PORT + ' 上没有浏览器，也没找到 Edge / Chrome。'
      + '装一个，或用 CHROME_PATH 指定可执行文件。');
  }
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-daily-probe-'));
  const child = spawn(exe, [
    '--headless=new',
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + profile,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    'about:blank',
  ], { stdio: 'ignore', detached: false });
  child.on('error', () => {});

  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 250));
    try {
      const list = await cdpList();
      if (list.some(t => t.type === 'page')) {
        return { child, profile };
      }
    } catch { /* 还没起来 */ }
  }
  child.kill();
  throw new Error('浏览器起来了但 15 秒内没有可用的 page target（' + exe + '）');
}

async function main () {
  const owned = await ensureBrowser();
  const list = await cdpList();
  const page = list.find(t => t.type === 'page');
  if (!page) throw new Error('没有可用的 page target');

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let seq = 0;
  const pending = new Map();
  const send = (method, params = {}) => new Promise((res, rej) => {
    const id = ++seq;
    pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params }));
  });
  ws.addEventListener('message', ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id); pending.delete(m.id);
      m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
    }
  });
  await new Promise(r => ws.addEventListener('open', r));

  await send('Emulation.setDeviceMetricsOverride', {
    width: Number(process.env.VW || 390),
    height: Number(process.env.VH || 844),
    // DSF=1 出「按 CSS 像素原尺寸」的图，适合放进 README（2x 的 PNG 往往 1 MB 以上）
    deviceScaleFactor: Number(process.env.DSF || 2),
    mobile: (process.env.VW || 390) < 800,
  });
  await send('Page.enable');
  const loaded = new Promise(r => {
    const h = ev => {
      const m = JSON.parse(ev.data);
      if (m.method === 'Page.loadEventFired') { ws.removeEventListener('message', h); r(); }
    };
    ws.addEventListener('message', h);
  });
  await send('Page.navigate', { url });
  await loaded;
  await new Promise(r => setTimeout(r, 1200));

  const out = await send('Runtime.evaluate', {
    expression: TARGETS[action] || 'null',
    returnByValue: true,
    awaitPromise: true,
  });
  const raw = out.result.value;
  console.log(typeof raw === 'string' ? JSON.stringify(JSON.parse(raw), null, 2) : JSON.stringify(out.result, null, 2));

  if (shotPath) {
    // SCROLL=<选择器>：截图前把某个元素滚进视口。报尾、图例都在长页末尾，
    // 不滚就只能截到首屏，靠肉眼猜「到底渲染出来没有」。
    if (process.env.SCROLL) {
      await send('Runtime.evaluate', {
        expression: `(function(){var el=document.querySelector(${JSON.stringify(process.env.SCROLL)});
          if(!el) return 'MISS';
          var y = el.getBoundingClientRect().top + window.pageYOffset - 180;
          window.scrollTo({top: y, behavior: 'instant'});
          return Math.round(el.getBoundingClientRect().top);})()`,
        returnByValue: true,
      });
      await new Promise(r => setTimeout(r, 700));
    }
    const s = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(shotPath, Buffer.from(s.data, 'base64'));
    console.log('SHOT ' + shotPath + ' ' + Buffer.from(s.data, 'base64').length + 'B');
  }
  ws.close();
  if (owned) {
    try { owned.child.kill(); } catch { /* ignore */ }
    try { fs.rmSync(owned.profile, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

main().catch(e => { console.error('ERR ' + e.message); process.exit(1); });
