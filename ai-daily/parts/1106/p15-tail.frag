<nav class="rail" aria-label="版面快捷目录">
  <div class="rail-head">目录</div>
  <ol class="rail-list">
    <li><a href="#p01"><i>01</i><span>头条</span></a></li>
    <li><a href="#p02"><i>02</i><span>社论</span></a></li>
    <li><a href="#p03"><i>03</i><span>模型</span></a></li>
    <li><a href="#p04"><i>04</i><span>产品</span></a></li>
    <li><a href="#p05"><i>05</i><span>深读</span></a></li>
    <li><a href="#p06"><i>06</i><span>思路</span></a></li>
    <li><a href="#p07"><i>07</i><span>榜单</span></a></li>
    <li><a href="#p08"><i>08</i><span>安全</span></a></li>
    <li><a href="#p09"><i>09</i><span>学术</span></a></li>
    <li><a href="#p10"><i>10</i><span>资本</span></a></li>
    <li><a href="#p11"><i>11</i><span>算力</span></a></li>
    <li><a href="#p12"><i>12</i><span>行情</span></a></li>
    <li><a href="#p13"><i>13</i><span>回声</span></a></li>
    <li><a href="#p14"><i>14</i><span>星探</span></a></li>
    <li><a href="#p15"><i>15</i><span>快讯</span></a></li>
  </ol>
  <a class="rail-top" href="#top" title="回到顶部">↑ 顶</a>
</nav>

<button class="mob-btn" id="mobBtn" type="button" aria-controls="mobPanel" aria-expanded="false"><i>☰</i>目录</button>
<div class="mob-panel" id="mobPanel" role="dialog" aria-label="版面目录">
  <h6>版面目录 · 共 15 版 · 点一下跳过去</h6>
  <div class="mob-grid">
    <a href="#p01"><i>01</i>头条</a>
    <a href="#p02"><i>02</i>社论</a>
    <a href="#p03"><i>03</i>能力底座</a>
    <a href="#p04"><i>04</i>产品生态</a>
    <a href="#p05"><i>05</i>深读·能跑起来</a>
    <a href="#p06"><i>06</i>思路拆解</a>
    <a href="#p07"><i>07</i>开源榜</a>
    <a href="#p08"><i>08</i>安全治理</a>
    <a href="#p09"><i>09</i>学术前沿</a>
    <a href="#p10"><i>10</i>商业资本</a>
    <a href="#p11"><i>11</i>算力本地</a>
    <a href="#p12"><i>12</i>行情价目</a>
    <a href="#p13"><i>13</i>平台回声</a>
    <a href="#p14"><i>14</i>星探</a>
    <a href="#p15"><i>15</i>快讯</a>
  </div>
  <p class="mob-tip">宽屏时目录固定在右侧；窄屏（平板、手机）右侧放不下，改用这个面板。点任意一项会自动收起。</p>
  <a class="mob-top" href="#top">↑ 回到顶部</a>
</div>

<script>
(function(){
  var links = Array.prototype.slice.call(document.querySelectorAll('.rail-list a'));
  var secs = links.map(function(a){ return document.querySelector(a.getAttribute('href')); });
  var ticking = false;
  function update(){
    var mark = window.pageYOffset + window.innerHeight * 0.35;
    var idx = 0;
    for (var i = 0; i < secs.length; i++){
      if (secs[i] && secs[i].offsetTop <= mark) idx = i;
    }
    links.forEach(function(a, i){ a.classList.toggle('active', i === idx); });
    ticking = false;
  }
  function onScroll(){ if(!ticking){ ticking = true; window.requestAnimationFrame(update); } }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  update();

  // 窄屏目录面板
  var mb = document.getElementById('mobBtn');
  var mp = document.getElementById('mobPanel');
  if (mb && mp){
    function setOpen(open){
      document.body.classList.toggle('mob-open', open);
      mb.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    mb.addEventListener('click', function(){
      setOpen(!document.body.classList.contains('mob-open'));
    });
    mp.addEventListener('click', function(e){
      var t = e.target;
      while (t && t !== mp){
        if (t.tagName === 'A'){ setOpen(false); break; }
        t = t.parentNode;
      }
    });
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape') setOpen(false);
    });
  }
})();
</script>
