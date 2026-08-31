// ===== AI 助手浮窗对话窗 (需求A) =====
// 用 fetch + ReadableStream 解析 POST 返回的 SSE 流（EventSource 只支持 GET，故不用它）。
// 会话/历史全后端持久化（SQLite），禁止 localStorage / IndexedDB；多人在不同浏览器
// 操作同一项目，靠「项目版本号轮询 + SSE 事件总线」自动刷新，保证数据一致。
(function(){
  const API='/api/v1';
  const projectId=document.body.dataset.projectId||'';
  // 当前对话上下文（谁·哪个项目的哪个页面·当前分集），从 URL/data 读取，禁 localStorage
  const page=document.body.dataset.page||'';
  const episodeId=(new URLSearchParams(location.search)).get('episode_id')||'';
  const operator=(new URLSearchParams(location.search)).get('as')||document.body.dataset.user||'工作台用户';
  const $=q=>document.querySelector(q);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  let panelOpen=false;
  let busy=false;                 // 是否有 agent 在跑
  let currentSessionId=null;      // ACP sessionId（取消用）
  let currentUiSession=null;      // UI 会话 id（后端持久化 key）
  let runningCtl=null;            // AbortController，用于取消本轮流
  let doing=false;                // 防止重复发消息
  let pendingAssistant='';        // 累积串，一次性设 textContent（避免逐 chunk 丢字）
  let pendingRefresh=false;       // agent 忙时收到数据变更，待本轮结束再刷新
  let _reloadT=null;              // 防抖的 reload 定时器
  let _sse=null;                  // SSE 订阅
  let lastVersion=-1;             // 版本号轮询打底

  function toast(m,err){ const el=$('#toast'); if(el){el.textContent=m;el.style.borderColor=err?'var(--red)':'var(--line)';el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600);} }

  // ---- 注入 DOM（如 base.html 已含则跳过）----
  function ensureDom(){
    if($('#ai-panel')) return;
    const wrap=document.createElement('div'); wrap.style.display='contents';
    wrap.innerHTML=`
      <button id="ai-fab" title="AI 助手" aria-label="AI 助手">☘<span class="fab-dot"></span></button>
      <div id="ai-panel" class="closed">
        <div class="ai-panel-head">
          <div class="t"><span class="dot" id="ai-status-dot"></span><span>AI 助手</span></div>
          <button class="ai-panel-close" id="ai-close" title="关闭" aria-label="关闭">×</button>
        </div>
        <div class="ai-sessbar">
          <select id="ai-sess-sel" aria-label="会话"></select>
          <button class="btn btn-sm" id="ai-sess-new" title="新建会话">＋ 新会话</button>
        </div>
        <div id="ai-msgs"></div>
        <div class="ai-input">
          <textarea id="ai-input" rows="1" placeholder="指示 agent 修改剧情、生成分镜…（回车发送）" aria-label="输入"></textarea>
          <div class="ai-actions">
            <span class="ai-hint" id="ai-hint">AI 助手可直连后端修改数据</span>
            <div class="right">
              <button class="btn secondary btn-sm" id="ai-cancel">停止</button>
              <button class="btn btn-sm" id="ai-send">发送</button>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(wrap);

    $('#ai-fab').addEventListener('click',togglePanel);
    $('#ai-close').addEventListener('click',()=>setOpen(false));
    $('#ai-send').addEventListener('click',()=>sendCurrent());
    $('#ai-cancel').addEventListener('click',doCancel);
    $('#ai-sess-new').addEventListener('click',newSession);
    $('#ai-sess-sel').addEventListener('change',()=>{ currentUiSession=$('#ai-sess-sel').value||null; if(currentUiSession) loadMessages(currentUiSession); });
    const ta=$('#ai-input');
    ta.addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendCurrent();} });
    ta.addEventListener('input',()=>{ ta.style.height='auto'; ta.style.height=Math.min(ta.scrollHeight,120)+'px'; });
    if(!projectId){ $('#ai-hint').textContent='请进入任一项目后使用 AI 助手'; $('#ai-send').disabled=true; $('#ai-sess-new').disabled=true; }
    else { initSessions(); subscribeRealtime(); }
  }

  function setOpen(open){ ensureDom(); panelOpen=open; $('#ai-panel').classList.toggle('closed',!open); if(open) $('#ai-input').focus(); }
  function togglePanel(){ setOpen(!panelOpen); }

  function setBusy(state){
    busy=state;
    $('#ai-fab').classList.toggle('busy',state);
    const d=$('#ai-status-dot'); d.className='dot'+(state?' busy':(currentUiSession?' on':''));
    const ctl=$('#ai-cancel'); if(ctl) ctl.disabled=!state;
  }

  const msgs=()=>$('#ai-msgs');
  function scrollBottom(){ const m=msgs(); if(m) m.scrollTop=m.scrollHeight; }

  // ---- 会话（后端持久化，多人共享）----
  async function initSessions(){
    try{
      const r=await fetch(`${API}/agent/sessions?project_id=${encodeURIComponent(projectId)}`);
      const b=await r.json();
      let list=b?.data||[];
      if(!list.length){
        const s=await newSession(true);
        return;
      }
      renderSessions(list);
      currentUiSession=list[0].id;
      loadMessages(currentUiSession);
    }catch(e){ toast('加载会话失败 '+e.message,true); }
  }
  function renderSessions(list){
    const sel=$('#ai-sess-sel'); if(!sel) return;
    sel.innerHTML=list.map(s=>`<option value="${esc(s.id)}">${esc(s.title||'新会话')} · ${(s.updated_at||'').slice(5,16).replace('T',' ')}</option>`).join('');
    sel.value=currentUiSession||'';
  }
  async function newSession(silent){
    try{
      const r=await fetch(`${API}/agent/sessions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:projectId})});
      const b=await r.json();
      if(!r.ok||b.success===false) throw new Error(b.error?.message||'新建失败 '+r.status);
      currentUiSession=b.data.id;
      await refreshSessionList();
      loadMessages(currentUiSession);
      if(!silent){ setOpen(true); $('#ai-input').focus(); }
      return b.data;
    }catch(e){ toast('新建会话失败 '+e.message,true); return null; }
  }
  async function refreshSessionList(){
    const r=await fetch(`${API}/agent/sessions?project_id=${encodeURIComponent(projectId)}`);
    const b=await r.json();
    renderSessions(b?.data||[]);
  }
  async function loadMessages(sid){
    const m=msgs(); if(!m) return;
    m.innerHTML='';
    try{
      const r=await fetch(`${API}/agent/sessions/${sid}`);
      const b=await r.json();
      if(!r.ok||b.success===false) throw new Error(b.error?.message||'读取失败');
      const msgsArr=b.data?.messages||[];
      if(!msgsArr.length){
        m.innerHTML=`<div class="ai-empty">你好，我是 AI 助手。<br>可直接用自然语言指示我修改剧情、生成分镜、调整段落等。<br>写操作会弹卡片请您确认。</div>`;
        return;
      }
      msgsArr.forEach(renderStored);
      scrollBottom();
    }catch(e){ toast('读取会话失败 '+e.message,true); m.innerHTML=`<div class="ai-empty">加载会话失败</div>`; }
  }
  function renderStored(msg){
    const role=msg.role, type=msg.type, c=msg.content||{};
    if(role==='user'){ addUser(c.text||''); }
    else if(role==='assistant'){ addAssistantContainer(); const b=[...document.querySelectorAll('#ai-msgs .ai-msg.assistant .ai-bubble')].pop(); if(b) b.textContent=c.text||''; }
    else if(role==='tool'){ const row=addTool(c.label||'执行工具',false); updateTool(row,c.status||'pending'); }
    else if(role==='permission'){ addPermissionCard({request_id:c.request_id,card:c.card},true); }
  }

  function addUser(text){
    const wrap=document.createElement('div'); wrap.className='ai-msg user';
    wrap.innerHTML=`<div class="ai-bubble">${esc(text)}</div>`;
    msgs().appendChild(wrap); scrollBottom();
  }
  function addAssistantContainer(reset=true){
    if(reset) pendingAssistant='';
    const wrap=document.createElement('div'); wrap.className='ai-msg assistant';
    wrap.innerHTML=`<div class="ai-bubble" data-role="assistant"></div>`;
    msgs().appendChild(wrap); scrollBottom();
    return wrap.querySelector('.ai-bubble');
  }
  function appendAssistant(text){
    let b=msgs().querySelector('.ai-msg.assistant:last-child .ai-bubble');
    if(!b) b=addAssistantContainer();
    pendingAssistant+=text;
    b.textContent=pendingAssistant;   // 一次性设完整累积串，防逐 chunk 追加丢字
    scrollBottom();
  }
  // 工具调用状态行（返回行元素，便于后续 update）
  function addTool(label,spinner=true){
    const row=document.createElement('div'); row.className='ai-tool';
    row.dataset.label=label||'执行工具';
    row.innerHTML=`<span class="ic${spinner?' spinner':''}"></span><span class="t">${esc(label||'执行工具')}</span>`;
    msgs().appendChild(row); scrollBottom();
    return row;
  }
  function updateTool(row,status){
    if(!row) return;
    const ic=row.querySelector('.ic');
    ic.className='ic';
    if(status==='completed'||status==='succeeded'){ ic.textContent='✓'; ic.classList.add('ok'); }
    else if(status==='failed'||status==='error'){ ic.textContent='✕'; ic.classList.add('err'); }
    else { ic.classList.add('spinner'); }
    if(status==='completed'||status==='succeeded'||status==='failed'||status==='error') row.dataset.done='1';
    scrollBottom();
  }

  // ---- 行为卡片 ----
  function addPermissionCard(ev,resolved){
    const wrap=document.createElement('div'); wrap.className='ai-perm'+(resolved?' resolved':''); wrap.dataset.requestId=ev.request_id||'';
    wrap.innerHTML=`
      <div class="ph"><span class="warn">⚠</span><span>请求确认：写操作</span></div>
      <div class="desc">${esc(ev.card||'执行操作')}</div>
      <div class="btns">${resolved?`<span class="verdict">已处理（不可再点）</span>`
        :`<button class="btn btn-sm" data-opt="once">批准一次</button>`+
         `<button class="btn btn-sm" data-opt="always">总是批准</button>`+
         `<button class="btn danger btn-sm" data-opt="reject">拒绝</button>`}</div>`;
    msgs().appendChild(wrap); scrollBottom();
    return wrap;
  }
  async function resolvePermission(card, option_id){
    const rid=card.dataset.requestId; if(!rid) return;
    const btns=card.querySelectorAll('.btns .btn');
    btns.forEach(b=>b.disabled=true);
    try{
      const r=await fetch(`${API}/agent/permission/${rid}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({option_id})});
      const b=await r.json().catch(()=>({}));
      if(!r.ok||b.success===false) throw new Error(b.error?.message||'响应失败 '+r.status);
      card.classList.add('resolved');
      card.querySelector('.btns').innerHTML=`<span class="verdict ${optClass(option_id)}">${optText(option_id)}</span>`;
      scrollBottom();
    }catch(e){ btns.forEach(b=>b.disabled=false); toast(e.message,true); }
  }
  function optClass(o){return o==='always'?'always':o==='reject'?'reject':'once';}
  function optText(o){return o==='always'?'已选择：总是批准':o==='reject'?'已选择：拒绝':'已选择：批准一次';}

  // ---- 发送 / SSE 流消费 ----
  async function sendCurrent(){
    const ta=$('#ai-input');
    const text=ta.value.trim();
    if(!text||doing) return;
    if(busy){ toast('上一轮仍在执行，可点「停止」或等它结束',true); return; }
    if(!currentUiSession){ const s=await newSession(true); if(!s) return; }
    doing=true; ta.value=''; ta.style.height='auto';
    addUser(text);
    setBusy(true);
    const ctl=new AbortController(); runningCtl=ctl;
    try{
      const res=await fetch(`${API}/agent/chat`,{
        method:'POST',headers:{'Content-Type':'application/json'},signal:ctl.signal,
        body:JSON.stringify({project_id:projectId||null,session_key:currentUiSession,text:text,episode_id:episodeId,page:page,operator:operator}),
      });
      if(!res.ok||!res.body){
        let err=null; try{err=(await res.json()).error?.message}catch(_){}
        throw new Error(err||`请求失败（${res.status}）`);
      }
      addAssistantContainer();
      await consumeSSE(res);
    }catch(e){
      if(e.name==='AbortError'){ appendAssistant('\n[已停止]'); }
      else { appendAssistant('\n[错误] '+e.message); }
    }finally{
      doing=false; setBusy(false); runningCtl=null;
      refreshSessionList();
      if(pendingRefresh){ pendingRefresh=false; scheduleReload(); }
    }
  }

  async function consumeSSE(res){
    const reader=res.body.getReader();
    const decoder=new TextDecoder('utf-8');
    let buf='';
    try{
      while(true){
        const {done,value}=await reader.read();
        if(done) break;
        buf+=decoder.decode(value,{stream:true});   // 跨 chunk 完整累积，不重新 new decoder
        let idx;
        while((idx=buf.indexOf('\n\n'))>=0){
          const raw=buf.slice(0,idx); buf=buf.slice(idx+2);
          const data=raw.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n');
          if(!data) continue;
          let ev; try{ev=JSON.parse(data);}catch(_){continue;}
          handleEvent(ev);
        }
      }
    }finally{
      // 冲刷 TextDecoder 残留多字节 + 处理尾部未拆分事件（防最后一条缺字）
      buf+=decoder.decode();
      if(buf.trim()){
        const data=buf.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n');
        if(data){ try{ handleEvent(JSON.parse(data)); }catch(_){} }
      }
    }
  }

  function handleEvent(ev){
    switch(ev.type){
      case 'session': currentSessionId=ev.sessionId||null; if(ev.sessionKey) currentUiSession=ev.sessionKey; break;
      case 'agent_chunk': appendAssistant(ev.text||''); break;
      case 'tool':
        if(ev.status==='pending'){
          updateTool(addTool(ev.label||'执行工具'),'pending');
        }else{
          // 找到最近一条未完结的、label 相同的工具行更新它；否则新建
          let row=[...document.querySelectorAll('#ai-msgs .ai-tool')].reverse().find(r=>!r.dataset.done&&r.dataset.label===(ev.label||''));
          if(!row){ row=addTool(ev.label||'执行工具'); }
          updateTool(row,ev.status);
        }
        break;
      case 'permission': addPermissionCard(ev,false); break;
      case 'error': appendAssistant('\n[错误] '+(ev.message||'agent 出错')); break;
      case 'done':
      case 'close':
      default:
        break;
    }
  }

  function doCancel(){
    if(!currentSessionId||!busy) return;
    if(runningCtl){ runningCtl.abort(); fetch(`${API}/agent/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:currentSessionId})}).catch(()=>{}); }
  }

  // ---- 实时刷新（数据变更 → 自动 reload 看到最新）----
  function subscribeRealtime(){
    if(_sse) return;                       // 防重复订阅
    try{
      _sse=new EventSource(`${API}/projects/${encodeURIComponent(projectId)}/events`);
      _sse.onmessage=(e)=>{
        try{ const ev=JSON.parse(e.data); if(ev.type==='data_changed'){ lastVersion=ev.version; handleDataChanged(ev.version); } }
        catch(_){}
      };
      _sse.onopen=()=>{ /* 恢复实时订阅 */ lastVersion=-1; };
      _sse.onerror=()=>{ /* SSE 断线：交给轮询打底，5s 后自动重连 */ };
    }catch(_){}
    // 兜底：版本号轮询（SSE 断线/静默时 5s 内一定看到最新）
    setInterval(async()=>{
      try{
        const r=await fetch(`${API}/projects/${encodeURIComponent(projectId)}/version`);
        const b=await r.json();
        const v=b?.data?.version??-1;
        if(lastVersion>=0 && v>=0 && v!==lastVersion){ lastVersion=v; handleDataChanged(v); }
        else if (lastVersion<0 && v>=0){ lastVersion=v; }
      }catch(_){}
    },5000);
  }
  function handleDataChanged(version){
    if(busy||doing){ pendingRefresh=true; return; }
    scheduleReload();
  }
  function scheduleReload(){
    if(_reloadT) return;
    _reloadT=setTimeout(()=>{ _reloadT=null; location.reload(); },400);
  }

  // 全局点击：权限卡片按钮
  document.addEventListener('click',e=>{
    const btn=e.target.closest('.ai-perm .btns .btn');
    if(btn){ const card=btn.closest('.ai-perm'); resolvePermission(card,btn.dataset.opt); e.preventDefault(); return; }
  });

  ensureDom();
  window.__aiAssistant={open:()=>setOpen(true),close:()=>setOpen(false),toggle:togglePanel,status:()=>({busy,session:currentSessionId,ui:currentUiSession}),reload:scheduleReload};
})();
