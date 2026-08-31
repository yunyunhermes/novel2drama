// ===== AI 助手浮窗对话窗 (需求A) =====
// 用 fetch + ReadableStream 解析 POST 返回的 SSE 流（EventSource 只支持 GET，故不用它）。
(function(){
  const API='/api/v1';
  const projectId=document.body.dataset.projectId||'';
  const $=q=>document.querySelector(q);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  let panelOpen=false;
  let busy=false;                 // 是否有 agent 在跑
  let currentSessionId=null;      // ACP sessionId（收到 session 事件后记录）
  let runningCtl=null;            // AbortController，用于取消本轮流
  let doing=false;                // 防止重复发消息

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
    const ta=$('#ai-input');
    ta.addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendCurrent();} });
    ta.addEventListener('input',()=>{ ta.style.height='auto'; ta.style.height=Math.min(ta.scrollHeight,120)+'px'; });
    if(!projectId){ $('#ai-hint').textContent='请进入任一项目后使用 AI 助手'; $('#ai-send').disabled=true; }
    // 默认渲染一条欢迎提示
    const m=msgs();
    m.innerHTML=`<div class="ai-empty">你好，我是 AI 助手。<br>可直接用自然语言指示我修改剧情、生成分镜、调整段落等。<br>写操作会弹卡片请您确认。</div>`;
  }

  function setOpen(open){ ensureDom(); panelOpen=open; $('#ai-panel').classList.toggle('closed',!open); if(open) $('#ai-input').focus(); }
  function togglePanel(){ setOpen(!panelOpen); }

  function setBusy(state){
    busy=state;
    $('#ai-fab').classList.toggle('busy',state);
    const d=$('#ai-status-dot'); d.className='dot'+(state?' busy':(currentSessionId?' on':''));
    const ctl=$('#ai-cancel'); if(ctl) ctl.disabled=!state;
  }

  const msgs=()=>$('#ai-msgs');
  function scrollBottom(){ const m=msgs(); if(m) m.scrollTop=m.scrollHeight; }

  function addUser(text){
    const wrap=document.createElement('div'); wrap.className='ai-msg user';
    wrap.innerHTML=`<div class="ai-bubble">${esc(text)}</div>`;
    msgs().appendChild(wrap); scrollBottom();
  }
  function addAssistantContainer(){
    const wrap=document.createElement('div'); wrap.className='ai-msg assistant';
    wrap.innerHTML=`<div class="ai-bubble" data-role="assistant"></div>`;
    msgs().appendChild(wrap); scrollBottom();
    return wrap.querySelector('.ai-bubble');
  }
  function appendAssistant(text){
    let b=msgs().querySelector('.ai-msg.assistant:last-child .ai-bubble');
    if(!b) b=addAssistantContainer();
    b.textContent+=text; scrollBottom();
  }
  // 工具调用状态行（返回行元素，便于后续 update）
  function addTool(label){
    const row=document.createElement('div'); row.className='ai-tool';
    row.innerHTML=`<span class="ic loading"></span><span class="t">${esc(label||'执行工具')}</span>`;
    msgs().appendChild(row); scrollBottom();
    return row;
  }
  function updateTool(row,status){
    if(!row) return;
    const ic=row.querySelector('.ic');
    ic.className='ic';
    if(status==='completed'||status==='succeeded'){ ic.textContent='✓'; ic.classList.add('ok'); }
    else if(status==='failed'||status==='error'){ ic.textContent='✕'; ic.classList.add('err'); }
    else { ic.classList.add('loading','spinner'); }
    if(status==='completed'||status==='succeeded'||status==='failed'||status==='error') row.dataset.done='1';
    scrollBottom();
  }

  // ---- 行为卡片 ----
  function addPermissionCard(ev){
    const wrap=document.createElement('div'); wrap.className='ai-perm'; wrap.dataset.requestId=ev.request_id;
    wrap.innerHTML=`
      <div class="ph"><span class="warn">⚠</span><span>请求确认：写操作</span></div>
      <div class="desc">${esc(ev.card||'执行操作')}</div>
      <div class="btns">
        <button class="btn btn-sm" data-opt="once">批准一次</button>
        <button class="btn btn-sm" data-opt="always">总是批准</button>
        <button class="btn danger btn-sm" data-opt="reject">拒绝</button>
      </div>`;
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
    doing=true; ta.value=''; ta.style.height='auto';
    addUser(text);
    setBusy(true);
    const ctl=new AbortController(); runningCtl=ctl;
    try{
      const res=await fetch(`${API}/agent/chat`,{
        method:'POST',headers:{'Content-Type':'application/json'},signal:ctl.signal,
        body:JSON.stringify({project_id:projectId||null,text:text}),
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
    }
  }

  async function consumeSSE(res){
    const reader=res.body.getReader();
    const decoder=new TextDecoder('utf-8');
    let buf='';
    while(true){
      const {done,value}=await reader.read();
      if(done) break;
      buf+=decoder.decode(value,{stream:true});
      let idx;
      while((idx=buf.indexOf('\n\n'))>=0){
        const raw=buf.slice(0,idx); buf=buf.slice(idx+2);
        const data=raw.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n');
        if(!data) continue;
        let ev; try{ev=JSON.parse(data);}catch(_){continue;}
        handleEvent(ev);
      }
    }
  }

  function handleEvent(ev){
    switch(ev.type){
      case 'session': currentSessionId=ev.sessionId||null; break;
      case 'agent_chunk': appendAssistant(ev.text||''); break;
      case 'tool':
        if(ev.status==='pending'){
          updateTool(addTool(ev.label||'执行工具'),'pending');
        }else{
          // 找到最近一条未完结的、label 相同的工具行更新它；否则新建
          let row=[...document.querySelectorAll('#ai-msgs .ai-tool')].reverse().find(r=>!r.dataset.done&&r.dataset.label===(ev.label||''));
          if(!row){ row=addTool(ev.label||'执行工具'); }
          else { row.dataset.label=row.dataset.label; }
          updateTool(row,ev.status);
        }
        break;
      case 'permission': addPermissionCard(ev); break;
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

  // 全局点击：权限卡片按钮
  document.addEventListener('click',e=>{
    const btn=e.target.closest('.ai-perm .btns .btn');
    if(btn){ const card=btn.closest('.ai-perm'); resolvePermission(card,btn.dataset.opt); e.preventDefault(); return; }
  });

  ensureDom();
  window.__aiAssistant={open:()=>setOpen(true),close:()=>setOpen(false),toggle:togglePanel,status:()=>({busy,session:currentSessionId})};
})();
