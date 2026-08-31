const API='/api/v1';
const projectId=document.body.dataset.projectId;
// ===== 分集 (episode) 支持 =====
let currentEpisodeId = new URLSearchParams(location.search).get('episode_id') || localStorage.getItem('n2d_episode_'+projectId) || null;
const epQuery = ()=> currentEpisodeId ? `?episode_id=${encodeURIComponent(currentEpisodeId)}` : '';
async function loadEpisodeBar(){
  const el=$('#sidebar-episode'); if(!el) return;
  try{
    const eps=await api(`/projects/${projectId}/episodes`);
    if(!eps.length){
      el.innerHTML=`<div class="sb-ep-row"><span class="muted">暂无分集</span><button class="btn secondary btn-sm" data-action="create-episode">新建分集</button></div>`;
      return;
    }
    if(!currentEpisodeId || !eps.some(e=>e.id===currentEpisodeId)) currentEpisodeId=eps[0].id;
    localStorage.setItem('n2d_episode_'+projectId, currentEpisodeId);
    el.innerHTML=`<label class="sb-ep-label">当前分集</label><div class="sb-ep-row"><select class="episode-select" data-episode-select>${eps.map(e=>`<option value="${e.id}" ${e.id===currentEpisodeId?'selected':''}>${e.title && e.title!==`第${e.episode_no}集` ? `第${e.episode_no}集 · ${esc(e.title)}` : esc(e.title||`第${e.episode_no}集`)}</option>`).join('')}</select><button class="btn secondary btn-sm" data-action="create-episode">+</button></div>`;
    appendEpisodeQuery();
  }catch(e){ el.innerHTML=empty(e.message); }
}
document.addEventListener('change',e=>{
  const sel=e.target.closest('[data-episode-select]'); if(!sel) return;
  currentEpisodeId=sel.value;
  localStorage.setItem('n2d_episode_'+projectId, currentEpisodeId);
  // 导航到带 episode_id 的当前页面
  const url=new URL(location.href);
  url.searchParams.set('episode_id', currentEpisodeId);
  location.href=url.toString();
});
document.addEventListener('click',async e=>{
  const b=e.target.closest('button[data-action="create-episode"]'); if(!b) return;
  try{
    await api(`/projects/${projectId}/episodes`,{method:'POST',body:'{}'});
    toast('分集已创建');
    location.reload();
  }catch(err){toast(err.message,true)}
});
const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const toast=(message,error=false)=>{const el=$('#toast');if(!el)return;el.textContent=message;el.style.borderColor=error?'var(--red)':'var(--line)';el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)};
async function api(path,options={}){const res=await fetch(API+path,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});let body={};try{body=await res.json()}catch{}if(!res.ok||body.success===false)throw new Error(body.error?.message||`请求失败（${res.status}）`);return body.data}
function formData(form){return Object.fromEntries(new FormData(form).entries())}
function empty(text){return `<div class="empty">${esc(text)}</div>`}
function status(v){return `<span class="status ${esc(v)}">${esc({draft:'草稿',queued:'排队中',running:'生成中',confirmed:'已确认',selected:'已选定',completed:'已完成',succeeded:'已完成',failed:'失败',keyframe_generating:'段首图生成中',h3_generating:'H3生成中',keyframe_review:'段首图待复核',keyframe_confirmed:'段首图已确认',h3_review:'H3待复核'}[v]||v||'未知')}</span>`}
// ===== 常驻侧栏：项目名 + 当前集 + 菜单高亮 + episode_id 注入 =====
function appendEpisodeQuery(){
  if(!currentEpisodeId) return;
  $$('#sidebar-menu .menu-item[href]').forEach(a=>{
    if(a.dataset.jobsLink || a.href.startsWith('#')) return;
    const u=new URL(a.href, location.origin); u.searchParams.set('episode_id', currentEpisodeId); a.href=u.toString();
  });
}
async function loadSidebar(){
  const projEl=$('#sidebar-project');
  if(projEl && projectId){
    try{
      const p=await api(`/projects/${projectId}`);
      projEl.innerHTML=`<div class="sb-project-name">${esc(p.name)}</div>${p.description?`<div class="sb-project-meta muted">${esc(p.description)}</div>`:''}`;
    }catch(e){projEl.innerHTML=empty(e.message)}
  }
  // 高亮当前菜单项
  const curPage=document.body.dataset.page;
  $$('#sidebar-menu .menu-item').forEach(m=>{
    if(m.dataset.page===curPage && !m.dataset.jobsLink) m.classList.add('active');
  });
  // 选集器 + 当前集 + 注入 episode_id
  await loadEpisodeBar();
}
async function loadProjects(){const el=$('#project-list');if(!el)return;try{const rows=await api('/projects');el.innerHTML=rows.length?rows.map(p=>`<article class="project-card"><h2>${esc(p.name)}</h2><p class="muted">${esc(p.description||'暂无项目描述')}</p><div class="card-meta"><span>${status(p.status)}</span><span>${p.target_duration_seconds||0} 秒</span></div><a class="btn" href="/projects/${p.id}">进入项目</a></article>`).join(''):empty('还没有项目，先创建一个制作项目。')}catch(e){el.innerHTML=empty(e.message);toast(e.message,true)}}
async function loadDetail(){try{const p=await api(`/projects/${projectId}`);$('#project-info').innerHTML=`<div class="page-heading"><div><p class="eyebrow">PROJECT</p><h1>${esc(p.name)}</h1><p class="muted">${esc(p.description||'暂无描述')}</p></div><div class="card-meta"><span>目标时长 ${p.target_duration_seconds||0} 秒</span><span>${esc(p.style_prompt||'未设置风格')}</span></div></div>`;$('#project-status').outerHTML=`<span id="project-status" class="badge ${esc(p.status)}">${esc(p.status)}</span>`;bindJobsDrawer();}catch(e){$('#project-info').innerHTML=empty(e.message);toast(e.message,true)}}
async function loadJobs(){try{const rows=await api(`/projects/${projectId}/jobs${epQuery()}`);$('#job-list').innerHTML=rows.length?rows.map(j=>`<div class="job-row"><div><strong>${esc(j.job_type)}</strong><div class="muted">${esc(j.created_at||'')}</div></div>${status(j.status)}</div>`).join(''):empty('暂无生成任务')}catch(e){$('#job-list').innerHTML=empty(e.message)}}
let _activeVersionId = null;
async function loadNovels(){
  try{
    const rows=await api(`/projects/${projectId}/novel-versions${epQuery()}`);
    $('#version-list').innerHTML=rows.length?rows.map(v=>`<div class="version-card ${v.is_active?'active':''}" data-version-id="${v.id}"><div><strong>V${v.version_no} · ${esc(v.title)}</strong><small>${v.text_length||0} 字 · ${esc(v.created_at||'')}</small>${v.text_preview?`<p class="preview">${esc(v.text_preview)}...</p>`:''}</div><div class="version-actions">${v.is_active?'<span class="badge confirmed">当前版本</span>':`<button class="btn secondary btn-sm" data-activate-version="${v.id}">激活</button>`}<button class="btn secondary btn-sm" data-view-source="${v.id}">查看原文</button></div></div>`).join(''):empty('还没有原稿版本');
    // 自动加载当前激活版本的原文和章节
    const active = rows.find(v=>v.is_active) || rows[0];
    if(active){
      _activeVersionId = active.id;
      await Promise.all([loadSourceText(active.id), loadChapters(active.id)]);
    }
  }catch(e){$('#version-list').innerHTML=empty(e.message);toast(e.message,true)}
}

async function loadSourceText(versionId){
  const panel=$('#source-panel');const viewer=$('#source-viewer');const meta=$('#source-meta');
  if(!panel||!viewer)return;
  panel.style.display='';
  viewer.innerHTML='<div class="loading">正在加载原文...</div>';
  try{
    const v=await api(`/novel-versions/${versionId}`);
    meta.textContent=` · V${v.version_no} · ${(v.source_text||'').length} 字`;
    viewer.textContent=v.source_text||'(空)';
  }catch(e){viewer.innerHTML=empty(e.message)}
}

async function loadChapters(versionId){
  const panel=$('#chapter-panel');const list=$('#chapter-list');const meta=$('#chapter-meta');
  if(!panel||!list)return;
  panel.style.display='';
  list.innerHTML='<div class="loading">正在加载章节...</div>';
  try{
    const rows=await api(`/novel-versions/${versionId}/chapters`);
    meta.textContent=` · 共 ${rows.length} 章`;
    list.innerHTML=rows.length?rows.map(c=>`<div class="chapter-row ${c.included?'':'excluded'}" data-chapter-id="${c.id}">
      <label class="chapter-include"><input type="checkbox" data-chapter-include="${c.id}" ${c.included?'checked':''}></label>
      <div class="chapter-info"><strong>第 ${c.sort_order} 节 · ${esc(c.title)}</strong><small>${c.text_length||0} 字</small>${c.content_preview?`<p class="preview">${esc(c.content_preview)}...</p>`:''}</div>
      <button class="btn secondary btn-sm" data-view-chapter="${c.id}">查看</button>
    </div>`).join(''):empty('尚未解析章节，点上方"重新解析章节"');
  }catch(e){list.innerHTML=empty(e.message)}
}
async function loadKeyframes(segmentId,container){try{const rows=await api(`/segments/${segmentId}/keyframes`);container.innerHTML=rows.length?`<div class="keyframe-grid">${rows.map(k=>`<div class="candidate keyframe ${k.status==='selected'?'selected':''}"><img src="/files/${projectId}/${esc(k.image_path)}" alt="段首图候选"><small>${status(k.status)}</small>${k.status==='selected'?'':'<button class="btn secondary btn-sm" data-select-keyframe="'+k.id+'">选定</button>'}</div>`).join('')}</div>`:empty('暂无段首图候选')}catch(e){container.innerHTML=empty(e.message)}}
async function loadH3(segmentId,container){try{const rows=await api(`/segments/${segmentId}/h3-generations`);container.innerHTML=rows.length?`<div class="video-grid">${rows.map(g=>`<div><video controls preload="metadata" src="/files/${projectId}/${esc(g.video_path||'')}"></video><div class="card-meta">${status(g.status)} ${g.status==='selected'?'':'<button class="btn secondary btn-sm" data-select-h3="'+g.id+'">选定</button>'}</div></div>`).join('')}</div>`:empty('暂无 H3 视频')}catch(e){container.innerHTML=empty(e.message)}}
// ============ 分镜编辑 (左侧菜单 + 单段详情) ============
let _currentSegmentId = null;
let _segmentsCache = [];

const beatFields=['start_ms','end_ms','shot_size','camera_movement','character_action','scene_change','lighting','composition','style','emotion','transition'];

function beatRow(b){
  const cells = beatFields.map(f=>{
    const isLong = ['character_action','scene_change','lighting','composition'].includes(f);
    const val = esc(b[f]);
    if(isLong) return `<td class="beat-long"><textarea data-field="${f}" rows="2">${val}</textarea></td>`;
    return `<td><input data-field="${f}" value="${val}" type="${f.includes('_ms')?'number':'text'}"></td>`;
  }).join('');
  return `<tr data-beat="${b.id}">${cells}<td><button class="btn danger btn-sm" data-delete-beat="${b.id}">删</button></td></tr>`;
}

async function loadBeats(segmentId, container){
  try{
    const rows = await api(`/segments/${segmentId}/beats`);
    const labels = {start_ms:'开始',end_ms:'结束',shot_size:'景别',camera_movement:'运镜',character_action:'人物动作',scene_change:'场景变化',lighting:'光线',composition:'构图',style:'风格',emotion:'情绪',transition:'转场'};
    container.innerHTML = `<div class="beat-wrap"><table class="beat-table"><thead><tr>${beatFields.map(f=>`<th>${labels[f]||f}</th>`).join('')}<th></th></tr></thead><tbody>${rows.map(beatRow).join('')}</tbody></table></div><form class="beat-add" data-add-beat="${segmentId}"><button class="btn secondary btn-sm" type="submit">+ 新增节拍</button></form>`;
    if(!rows.length) container.innerHTML += empty('暂无节拍');
  }catch(e){container.innerHTML = empty(e.message)}
}

async function loadKeyframes(segmentId, container){
  try{
    const rows = await api(`/segments/${segmentId}/keyframes`);
    container.innerHTML = rows.length
      ? `<div class="keyframe-grid">${rows.map(k=>`<div class="candidate keyframe ${k.status==='selected'?'selected':''}"><img src="/files/${projectId}/${esc(k.image_path)}" alt="段首图"><small>${status(k.status)}</small>${k.status==='selected'?'<button class="btn secondary btn-sm" data-confirm-keyframe="'+k.id+'">确认</button>':'<button class="btn secondary btn-sm" data-select-keyframe="'+k.id+'">选定</button>'}</div>`).join('')}</div>`
      : empty('暂无段首图候选');
  }catch(e){container.innerHTML = empty(e.message)}
}

async function loadH3(segmentId, container){
  try{
    const rows = await api(`/segments/${segmentId}/h3-generations`);
    container.innerHTML = rows.length
      ? `<div class="video-grid">${rows.map(g=>`<div><video controls preload="metadata" src="/files/${projectId}/${esc(g.video_path||'')}"></video><div class="card-meta">${status(g.status)} ${g.status==='selected'?'':'<button class="btn secondary btn-sm" data-select-h3="'+g.id+'">选定</button>'}</div></div>`).join('')}</div>`
      : empty('暂无 H3 视频');
  }catch(e){container.innerHTML = empty(e.message)}
}

// 左侧菜单
async function loadSegmentMenu(){
  const el = $('#segment-menu');
  if(!el) return;
  await loadSourceRef();
  try{
    const rows = await api(`/projects/${projectId}/segments${epQuery()}`);
    _segmentsCache = rows;
    el.innerHTML = rows.length
      ? rows.map(s=>`<div class="segment-menu-item ${s.id===_currentSegmentId?'active':''}" data-segment-id="${s.id}"><span class="seg-no">第 ${s.sort_order} 段</span><span class="seg-summary">${esc((s.summary||'').slice(0,30))}</span><span class="seg-status">${status(s.status)}</span></div>`).join('')
      : empty('暂无段落');
    // 默认选中第一段
    if(!_currentSegmentId && rows.length) selectSegment(rows[0].id);
  }catch(e){el.innerHTML = empty(e.message)}
}

// 左侧原文参考面板：加载当前激活版本全文
async function loadSourceRef(){
  const viewer = $('#source-ref-viewer');
  if(!viewer) return;
  try{
    const versions = await api(`/projects/${projectId}/novel-versions${epQuery()}`);
    const active = versions.find(v=>v.is_active) || versions[0];
    if(!active){
      viewer.innerHTML = '尚无原文版本，请先到「小说版本」导入原稿。';
      return;
    }
    const v = await api(`/novel-versions/${active.id}`);
    $('#source-ref-meta').textContent = `V${v.version_no} · ${(v.source_text||'').length} 字`;
    viewer.textContent = v.source_text || '(空)';
  }catch(e){viewer.innerHTML = empty(e.message)}
}

// 右侧详情
async function loadSegmentDetail(segmentId){
  const el = $('#segment-detail');
  if(!el) return;
  const s = _segmentsCache.find(x=>x.id===segmentId);
  if(!s){el.innerHTML = empty('段不存在');return}
  el.innerHTML = `
    <div class="segment-detail-header">
      <div><h2>第 ${s.sort_order} 段</h2><span class="muted">${esc(s.summary||'')}</span></div>
      <div class="segment-actions">${status(s.status)}
        <button class="btn secondary btn-sm" data-build-prompt="${s.id}">构建 prompt</button>
        <button class="btn danger btn-sm" data-delete-segment="${s.id}">删除</button>
      </div>
    </div>
    <form data-edit-segment="${s.id}" class="segment-form">
      <label>剧情摘要<textarea name="summary" rows="3">${esc(s.summary)}</textarea></label>
      <div class="form-row"><label>段首衔接<input name="start_transition" value="${esc(s.start_transition)}"></label><label>段尾衔接<input name="end_transition" value="${esc(s.end_transition)}"></label></div>
      <button class="btn secondary btn-sm" type="submit">保存段落</button>
    </form>
    <div class="review-section">
      <div class="section-header"><h3>段首图</h3><button class="btn secondary btn-sm" data-generate-keyframes="${s.id}">生成段首图</button></div>
      <div data-keyframes="${s.id}" class="loading">加载中...</div>
    </div>
    <div class="review-section">
      <div class="section-header"><h3>H3 视频</h3><button class="btn secondary btn-sm" data-generate-h3="${s.id}">生成 H3</button></div>
      <div data-h3="${s.id}" class="loading">加载中...</div>
    </div>
    <div class="review-section">
      <div class="section-header"><h3>节拍表</h3></div>
      <div data-beats="${s.id}" class="loading">加载中...</div>
    </div>`;
  await Promise.all([
    loadBeats(s.id, $(`[data-beats="${s.id}"]`)),
    loadKeyframes(s.id, $(`[data-keyframes="${s.id}"]`)),
    loadH3(s.id, $(`[data-h3="${s.id}"]`))
  ]);
}

function selectSegment(segmentId){
  _currentSegmentId = segmentId;
  $$('.segment-menu-item').forEach(el=>el.classList.toggle('active', el.dataset.segmentId===segmentId));
  loadSegmentDetail(segmentId);
}

// 局部刷新 (不丢滚动位置)
async function refreshSegmentDetail(segmentId){
  const scrollY = window.scrollY;
  await loadSegmentDetail(segmentId || _currentSegmentId);
  window.scrollTo({top: scrollY, behavior: 'instant'});
}

async function refreshSegmentMenu(){
  await loadSegmentMenu();
}

let _exportOrderIds=[];
function renderExportOrder(confirmed){
  const el=$('#confirmed-segments'); if(!el) return;
  if(!confirmed.length){el.innerHTML=empty('暂无已确认段，请先完成 H3 复核');_exportOrderIds=[];return}
  _exportOrderIds=confirmed.map(s=>s.id);
  el.innerHTML=`<div class="export-order">${confirmed.map((s,i)=>`<div class="job-row"><span class="ord-no">${i+1}</span><span style="flex:1">第 ${s.sort_order} 段 · ${esc(s.summary||'')}</span><span class="button-row"><button class="btn secondary btn-sm" data-expt-up="${i}" ${i===0?'disabled':''}>↑</button><button class="btn secondary btn-sm" data-expt-down="${i}" ${i===confirmed.length-1?'disabled':''}>↓</button></span><span class="badge confirmed">已确认</span></div>`).join('')}</div><p class="muted form-hint">可用 ↑↓ 调整拼接顺序，随后创建导出。</p>`;
}
async function loadExports(){
  try{
    const segs=await api(`/projects/${projectId}/segments${epQuery()}`);
    const confirmed=segs.filter(s=>s.status==='confirmed');
    renderExportOrder(confirmed);
    const rows=await api(`/projects/${projectId}/exports${epQuery()}`);
    $('#export-list').innerHTML=rows.length?rows.map(x=>`<div class="export-row"><div><strong>${esc(x.title)}</strong><div class="muted">${esc(x.created_at||'')} · ${x.resolution||''}</div></div><div>${status(x.status)} ${x.output_path?`<a class="btn secondary btn-sm" href="/files/${projectId}/${esc(x.output_path)}" download>下载视频</a>`:''}</div></div>`).join(''):empty('暂无导出任务');
  }catch(e){toast(e.message,true)}
}
async function submit(url,body,success,refresh){try{await api(url,{method:'POST',body:JSON.stringify(body)});toast(success);if(refresh)await refresh()}catch(e){toast(e.message,true)}}
document.addEventListener('submit',e=>{const f=e.target;if(f.dataset.form==='create-project'){e.preventDefault();submit('/projects', {...formData(f),target_duration_seconds:Number(f.target_duration_seconds.value||0)},'项目创建成功',async()=>{f.reset();await loadProjects();closeModal('modal-create-project')})}if(f.dataset.form==='create-novel'){e.preventDefault();submit(`/projects/${projectId}/novel-versions`,{...formData(f),episode_id:currentEpisodeId},'版本保存成功',async()=>{f.reset();await loadNovels();closeModal('modal-create-novel')})}if(f.dataset.form==='create-segment'){e.preventDefault();submit(`/projects/${projectId}/segments`,{...formData(f),sort_order:Number(f.sort_order.value),episode_id:currentEpisodeId},'段落创建成功',async()=>{f.reset();await refreshSegmentDetail()})}if(f.dataset.form==='create-asset'){e.preventDefault();submit(`/projects/${projectId}/assets`,formData(f),'资产创建成功',async()=>{f.reset();await loadAssets();closeModal('modal-create-asset')})}if(f.dataset.form==='create-export'){e.preventDefault();submit(`/projects/${projectId}/exports`,{...formData(f),fps:Number(f.fps.value),episode_id:currentEpisodeId,segment_ids:_exportOrderIds},'导出任务已创建',async()=>{await loadExports();closeModal('modal-create-export')})}if(f.dataset.editSegment){e.preventDefault();submit(`/projects/${projectId}/segments/${f.dataset.editSegment}`,formData(f),'段落已保存',refreshSegmentDetail)}if(f.dataset.addBeat){e.preventDefault();submit(`/segments/${f.dataset.addBeat}/beats`,{sort_order:1,start_ms:0,end_ms:15000},'节拍已添加',refreshSegmentDetail)}});
document.addEventListener('click',async e=>{
  // 段菜单点击
  const menuItem = e.target.closest('.segment-menu-item');
  if(menuItem){selectSegment(menuItem.dataset.segmentId);return}
  // 新增段表单切换
  if(e.target.dataset.action==='show-create-segment'){
    const form=$('#create-segment-form');if(form)form.classList.toggle('hidden');return
  }
  const b=e.target.closest('button');if(!b)return;try{
    // 小说编辑页新交互
    if(b.dataset.action==='toggle-source'){const v=$('#source-viewer');if(v)v.classList.toggle('collapsed');return}
    if(b.dataset.action==='toggle-source-ref'){const v=$('#source-ref-viewer');if(v)v.classList.toggle('collapsed');return}
    if(b.dataset.action==='refresh-chapters'){if(_activeVersionId)return loadChapters(_activeVersionId);return}
    if(b.dataset.action==='parse-chapters'){
      if(!_activeVersionId){toast('请先选择版本',true);return}
      b.disabled=true;b.textContent='解析中...';
      try{
        const r=await api(`/novel-versions/${_activeVersionId}/parse-chapters`,{method:'POST'});
        toast(`解析完成：${r.parsed} 章`);
        await loadChapters(_activeVersionId);
      }catch(e){toast(e.message,true)}finally{b.disabled=false;b.textContent='重新解析章节'}
      return
    }
    if(b.dataset.viewSource){
      _activeVersionId=b.dataset.viewSource;
      await Promise.all([loadSourceText(_activeVersionId), loadChapters(_activeVersionId)]);
      return
    }
    if(b.dataset.viewChapter){
      const cid=b.dataset.viewChapter;
      try{
        const c=await api(`/chapters/${cid}`);
        // 用 modal 形式显示
        const modal=document.createElement('div');
        modal.className='chapter-modal';
        modal.innerHTML=`<div class="chapter-modal-inner"><div class="panel-title"><h2>第 ${c.sort_order} 节 · ${esc(c.title)}</h2><button class="btn secondary btn-sm" data-close-modal>关闭</button></div><div class="chapter-content">${esc(c.content)}</div></div>`;
        modal.addEventListener('click',ev=>{if(ev.target===modal||ev.target.dataset.closeModal!==undefined)modal.remove()});
        document.body.appendChild(modal);
      }catch(e){toast(e.message,true)}
      return
    }
    if(b.dataset.action==='refresh-projects')return loadProjects();if(b.dataset.action==='refresh-detail')return loadDetail();if(b.dataset.action==='refresh-novels')return loadNovels();if(b.dataset.action==='refresh-storyboard')return refreshSegmentDetail();if(b.dataset.action==='refresh-assets')return loadAssets();if(b.dataset.action==='refresh-exports')return loadExports();if(b.dataset.activateVersion){await api(`/projects/${projectId}/novel-versions/${b.dataset.activateVersion}/activate${epQuery()}`,{method:'POST'});toast('版本已激活');return loadNovels()}if(b.dataset.deleteSegment){if(confirm('确定删除这一段吗？')){await api(`/projects/${projectId}/segments/${b.dataset.deleteSegment}`,{method:'DELETE'});toast('段落已删除');return refreshSegmentDetail()}}if(b.dataset.deleteBeat){await api(`/beats/${b.dataset.deleteBeat}`,{method:'DELETE'});toast('节拍已删除');return refreshSegmentDetail()}if(b.dataset.selectCandidate){await api(`/asset-candidates/${b.dataset.selectCandidate}/select`,{method:'POST'});toast('候选图已选定');return loadAssets()}if(b.dataset.confirmAsset){await api(`/assets/${b.dataset.confirmAsset}/confirm`,{method:'POST'});toast('资产已确认');return loadAssets()}if(b.dataset.generateCandidates){return submit(`/assets/${b.dataset.generateCandidates}/candidates/generate`,{},'候选图生成任务已排队',loadAssets)}if(b.dataset.selectKeyframe){await api(`/keyframes/${b.dataset.selectKeyframe}/select`,{method:'POST'});toast('已选定候选，点「确认」进入 H3');return refreshSegmentDetail()}if(b.dataset.confirmKeyframe){await api(`/keyframes/${b.dataset.confirmKeyframe}/confirm`,{method:'POST'});toast('段首图已确认，可进入 H3');return refreshSegmentDetail()}if(b.dataset.selectH3){await api(`/h3-generations/${b.dataset.selectH3}/select`,{method:'POST'});toast('H3视频已选定');return refreshSegmentDetail()}if(b.dataset.generateKeyframes){return submit(`/segments/${b.dataset.generateKeyframes}/keyframes/generate`,{},'段首图生成任务已排队',refreshSegmentDetail)}if(b.dataset.generateH3){return submit(`/segments/${b.dataset.generateH3}/h3-generations`,{},'H3生成任务已排队',refreshSegmentDetail)}if(b.dataset.buildPrompt){const r=await api(`/segments/${b.dataset.buildPrompt}/keyframe-prompt/build`,{method:'POST'});toast(`prompt已构建：${(r.keyframe_prompt||'').slice(0,30)}`)}}catch(err){toast(err.message,true)}});
document.addEventListener('change',e=>{const input=e.target.closest('[data-field]');if(!input)return;const row=input.closest('tr');clearTimeout(row._timer);row._timer=setTimeout(()=>{const data={};row.querySelectorAll('[data-field]').forEach(x=>data[x.dataset.field]=x.type==='number'?Number(x.value):x.value);api(`/beats/${row.dataset.beat}`,{method:'PATCH',body:JSON.stringify(data)}).then(()=>toast('节拍已保存')).catch(err=>toast(err.message,true))},350)});
// 章节 included 切换
document.addEventListener('change',async e=>{
  const cb=e.target.closest('[data-chapter-include]');
  if(!cb)return;
  const cid=cb.dataset.chapterInclude;
  const included=cb.checked;
  try{
    await api(`/chapters/${cid}`,{method:'PATCH',body:JSON.stringify({included})});
    const row=cb.closest('.chapter-row');
    if(row)row.classList.toggle('excluded',!included);
    toast(included?'已加入分镜范围':'已排除');
  }catch(err){cb.checked=!included;toast(err.message,true)}
});

// 字数统计 + 文件上传
document.addEventListener('DOMContentLoaded',()=>{
  const ta=document.querySelector('textarea.source-editor');
  const counter=$('#novel-char-count');
  if(ta&&counter){
    const update=()=>{counter.textContent=`${ta.value.length} 字`};
    ta.addEventListener('input',update);update();
  }
  const fileInput=$('#novel-file');
  if(fileInput&&ta){
    fileInput.addEventListener('change',async e=>{
      const f=e.target.files[0];if(!f)return;
      try{
        const text=await f.text();
        ta.value=text;
        ta.dispatchEvent(new Event('input'));
        toast(`已读取 ${f.name}（${text.length} 字）`);
      }catch(err){toast('文件读取失败',true)}
    });
  }
});

// 项目详情页概览
async function loadOverview(){
  const el=$('#project-overview');if(!el)return;
  try{
    const [versions,segments,assets,jobs,exportsList]=await Promise.all([
      api(`/projects/${projectId}/novel-versions${epQuery()}`).catch(()=>[]),
      api(`/projects/${projectId}/segments${epQuery()}`).catch(()=>[]),
      api(`/projects/${projectId}/assets`).catch(()=>[]),
      api(`/projects/${projectId}/jobs${epQuery()}`).catch(()=>[]),
      api(`/projects/${projectId}/exports${epQuery()}`).catch(()=>[]),
    ]);
    const active=versions.find(v=>v.is_active);
    const totalChars=active?active.text_length||0:0;
    const confirmedSegs=segments.filter(s=>s.status==='confirmed').length;
    const runningJobs=jobs.filter(j=>j.status==='running'||j.status==='queued').length;
    const doneExports=exportsList.filter(x=>x.status==='completed'||x.status==='succeeded').length;
    el.innerHTML=`
      <div class="overview-card"><div class="num">${versions.length}</div><div class="lbl">原稿版本</div></div>
      <div class="overview-card"><div class="num">${totalChars}</div><div class="lbl">当前版本字数</div></div>
      <div class="overview-card"><div class="num">${segments.length}</div><div class="lbl">分镜段落</div></div>
      <div class="overview-card"><div class="num">${confirmedSegs}</div><div class="lbl">已确认段</div></div>
      <div class="overview-card"><div class="num">${assets.length}</div><div class="lbl">资产</div></div>
      <div class="overview-card"><div class="num">${runningJobs}</div><div class="lbl">进行中任务</div></div>
      <div class="overview-card"><div class="num">${doneExports}</div><div class="lbl">已完成导出</div></div>`;
  }catch(e){el.innerHTML=empty(e.message)}
}

// 任务动态抽屉：展开时才加载
function bindJobsDrawer(){
  const d=$('#jobs-drawer'); if(!d) return;
  if(!d._bound){ d._bound=true; d.addEventListener('toggle',()=>{ if(d.open && !d._loaded){ d._loaded=true; loadJobs(); } }); }
}
// 侧栏收起 / 展开
document.addEventListener('click',e=>{
  const t=e.target.closest('[data-action="toggle-sidebar"]'); if(!t) return;
  document.body.classList.toggle('sidebar-collapsed');
});
const page=document.body.dataset.page;
if(page==='projects')loadSidebar().then(loadProjects);
if(page==='project-detail'){(async()=>{await loadSidebar();await loadDetail();loadOverview();if(location.hash==='#jobs'){const d=$('#jobs-drawer');if(d){d.open=true;d.dispatchEvent(new Event('toggle'))}}})()}
if(page==='novel'){(async()=>{await loadSidebar();loadNovels()})()}
if(page==='storyboard'){(async()=>{await loadSidebar();loadSegmentMenu()})()}
if(page==='assets'){loadSidebar().then(loadAssets)}
if(page==='export'){(async()=>{await loadSidebar();loadExports()})()}
if(page==='keyframe-review'){(async()=>{await loadSidebar();loadKeyframeReview()})()}

// ===== 段首图复核页 =====
function keyframeCandidates(s){
  if(!s.keyframes || !s.keyframes.length) return empty('暂无候选，点「生成」由 Z-Image 出图，稍后刷新查看。');
  return `<div class="keyframe-grid">${s.keyframes.map(k=>`<div class="candidate keyframe ${k.status==='selected'?'selected':''}"><img src="/files/${projectId}/${esc(k.image_path)}" alt="段首图候选"><div class="card-meta">${status(k.status)}${k.status==='selected'
    ?`<button class="btn secondary btn-sm" data-review-confirm-keyframe="${k.id}">确认</button>`
    :`<button class="btn secondary btn-sm" data-review-select-keyframe="${k.id}">选定</button>`}</div></div>`).join('')}</div>`;
}
async function loadKeyframeReview(){
  const el=$('#keyframe-review-list'); if(!el) return;
  el.innerHTML='<div class="loading">加载中...</div>';
  try{
    const segs=await api(`/projects/${projectId}/review/keyframes${epQuery()}`);
    if(!segs.length){el.innerHTML=empty('暂无分段，请先到「分镜编辑」创建或生成分段。');return}
    el.innerHTML=segs.map(s=>`
      <section class="review-section">
        <div class="segment-detail-header">
          <div><span class="seg-no">第 ${s.sort_order} 段</span><h3 style="margin:4px 0">${esc(s.summary||'(无摘要)')}</h3></div>
          <div class="segment-actions">${status(s.status)}
            <button class="btn secondary btn-sm" data-review-generate-keyframes="${s.id}">生成</button>
            <button class="btn secondary btn-sm" data-review-regenerate-keyframes="${s.id}">重抽</button>
          </div>
        </div>
        ${s.keyframe_prompt?`<p class="muted" style="font-size:12px;margin:0 0 12px">prompt：${esc(s.keyframe_prompt)}</p>`:''}
        ${keyframeCandidates(s)}
      </section>`).join('');
  }catch(e){el.innerHTML=empty(e.message)}
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button'); if(!b) return;
  if(b.dataset.action==='refresh-keyframe-review')return loadKeyframeReview();
  if(b.dataset.reviewGenerateKeyframes)return submit(`/segments/${b.dataset.reviewGenerateKeyframes}/keyframes/generate`,{},'段首图生成任务已排队',loadKeyframeReview);
  if(b.dataset.reviewRegenerateKeyframes)return submit(`/segments/${b.dataset.reviewRegenerateKeyframes}/keyframes/generate`,{},'重抽任务已排队',loadKeyframeReview);
  if(b.dataset.reviewSelectKeyframe){try{await api(`/keyframes/${b.dataset.reviewSelectKeyframe}/select`,{method:'POST'});toast('已选定候选，点「确认」进入 H3 阶段');await loadKeyframeReview()}catch(err){toast(err.message,true)}return}
  if(b.dataset.reviewConfirmKeyframe){try{await api(`/keyframes/${b.dataset.reviewConfirmKeyframe}/confirm`,{method:'POST'});toast('段首图已确认，可进入 H3 阶段');await loadKeyframeReview()}catch(err){toast(err.message,true)}return}
});

// ===== 15s 段复核页 =====
function h3Candidates(s){
  if(!s.h3_generations || !s.h3_generations.length) return empty('暂无视频，点「生成」由 H3 出片，稍后刷新查看。');
  return `<div class="video-grid">${s.h3_generations.map(g=>`<div><video controls preload="metadata" src="/files/${projectId}/${esc(g.video_path||'')}" ${g.thumbnail_path?`poster="/files/${projectId}/${esc(g.thumbnail_path)}"`:''}></video><div class="card-meta">${status(g.status)}${g.status==='selected'?'<b> · 已选</b>':`<button class="btn secondary btn-sm" data-review-select-h3="${g.id}">选定</button>`}</div></div>`).join('')}</div>`;
}
async function loadH3Review(){
  const el=$('#h3-review-list'); if(!el) return;
  el.innerHTML='<div class="loading">加载中...</div>';
  try{
    const segs=await api(`/projects/${projectId}/review/h3${epQuery()}`);
    if(!segs.length){el.innerHTML=empty('暂无分段，请先到「分镜编辑」创建或生成分段。');return}
    el.innerHTML=segs.map(s=>`
      <section class="review-section">
        <div class="segment-detail-header">
          <div><span class="seg-no">第 ${s.sort_order} 段</span><h3 style="margin:4px 0">${esc(s.summary||'(无摘要)')}</h3></div>
          <div class="segment-actions">${status(s.status)}
            <button class="btn secondary btn-sm" data-review-generate-h3="${s.id}">生成</button>
            <button class="btn secondary btn-sm" data-review-regenerate-h3="${s.id}">重抽</button>
          </div>
        </div>
        ${!s.selected_keyframe_id?`<p class="muted" style="font-size:12px;margin:0 0 12px">⚠ 该段尚未选定段首图，请先到「段首图复核」选定后再生成。</p>`:''}
        ${s.h3_prompt?`<p class="muted" style="font-size:12px;margin:0 0 12px">prompt：${esc(s.h3_prompt)}</p>`:''}
        ${h3Candidates(s)}
      </section>`).join('');
  }catch(e){el.innerHTML=empty(e.message)}
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button'); if(!b) return;
  if(b.dataset.action==='refresh-segment-review')return loadH3Review();
  if(b.dataset.reviewGenerateH3)return submit(`/segments/${b.dataset.reviewGenerateH3}/h3-generations`,{},'H3生成任务已排队',loadH3Review);
  if(b.dataset.reviewRegenerateH3)return submit(`/segments/${b.dataset.reviewRegenerateH3}/h3-generations`,{},'重抽任务已排队',loadH3Review);
  if(b.dataset.reviewSelectH3){try{await api(`/h3-generations/${b.dataset.reviewSelectH3}/select`,{method:'POST'});toast('H3视频已选定，该段确认通过');await loadH3Review()}catch(err){toast(err.message,true)}return}
});
if(page==='segment-review'){(async()=>{await loadSidebar();loadH3Review()})()}

// ===== Agent 分镜补全 (#5): 生成分镜 + 待应用 patch 预览/应用/拒绝 =====
async function loadPatches(){
  const el=$('#patch-list'); if(!el) return;
  try{
    const rows=await api(`/projects/${projectId}/agent-patches${epQuery()}`);
    const pending=rows.filter(p=>p.status==='pending');
    if(!pending.length){el.innerHTML=empty('暂无待应用的分镜 patch，可先点「AI 生成分镜」触发。');return}
    el.innerHTML=`<div class="panel-title"><h3>待应用 patch</h3><button class="btn secondary btn-sm" data-action="close-patches">收起</button></div>`+
      pending.map(p=>{
        let ops=[]; try{ops=(JSON.parse(p.patch_json)||{}).ops||[]}catch(e){}
        const segOps=ops.filter(o=>o.type==='create_segment');
        const summary=segOps.map(o=>o.data?.summary||'(无摘要)').join('；');
        return `<div class="patch-row"><div class="card-meta"><strong>${esc(p.created_at||'')}</strong><span>${segOps.length} 个新分段</span></div>
          <div class="muted" style="margin:6px 0">${esc(summary)}</div>
          <div class="button-row"><button class="btn secondary btn-sm" data-apply-patch="${p.id}">应用</button><button class="btn danger btn-sm" data-reject-patch="${p.id}">拒绝</button></div></div>`;
      }).join('');
  }catch(e){el.innerHTML=empty(e.message)}
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('button'); if(!b) return;
  if(b.dataset.action==='generate-storyboard')return submit(`/projects/${projectId}/storyboard/generate`,{episode_id:currentEpisodeId},'分镜生成任务已排队，稍后到「待应用 patch」查看',()=>{});
  if(b.dataset.action==='show-patches'){const el=$('#patch-list'); if(!el)return; el.classList.remove('hidden'); return loadPatches()}
  if(b.dataset.action==='close-patches'){const el=$('#patch-list'); if(el)el.classList.add('hidden'); return}
  if(b.dataset.applyPatch){try{const r=await api(`/agent-patches/${b.dataset.applyPatch}/apply`,{method:'POST'});toast(`已应用 ${(r&&r.applied_segments)||0} 段`);await loadPatches();await refreshSegmentMenu()}catch(err){toast(err.message,true)}return}
  if(b.dataset.rejectPatch){try{await api(`/agent-patches/${b.dataset.rejectPatch}/reject`,{method:'POST'});toast('已拒绝该 patch');await loadPatches()}catch(err){toast(err.message,true)}return}
});
// ===== 导出段顺序调整 (↑↓) =====
document.addEventListener('click',async e=>{
  const b=e.target.closest('button'); if(!b) return;
  if(b.dataset.exptUp===undefined && b.dataset.exptDown===undefined) return;
  const idUp=b.dataset.exptUp, idDown=b.dataset.exptDown;
  const i=idUp!==undefined?Number(idUp):Number(idDown);
  const j=idUp!==undefined?i-1:i+1;
  if(j<0||j>=_exportOrderIds.length)return;
  [_exportOrderIds[i],_exportOrderIds[j]]=[_exportOrderIds[j],_exportOrderIds[i]];
  try{
    const segs=await api(`/projects/${projectId}/segments${epQuery()}`);
    const byId={}; segs.forEach(s=>byId[s.id]=s);
    const ordered=_exportOrderIds.map(id=>byId[id]).filter(Boolean);
    renderExportOrder(ordered);
  }catch(err){toast(err.message,true)}
});

// ===== 资产：直接上传本地素材 + 列表渲染 =====
async function uploadForm(url, formData){
  const res=await fetch(API+url,{method:'POST',body:formData});
  let body={};try{body=await res.json()}catch{}
  if(!res.ok||body.success===false)throw new Error(body.error?.message||'上传失败（'+res.status+'）');
  return body.data;
}
document.addEventListener('submit',async e=>{
  const f=e.target; if(!f.dataset || f.dataset.form!=='upload-asset') return;
  e.preventDefault();
  try{
    await uploadForm(`/projects/${projectId}/assets/upload`,new FormData(f));
    toast('素材已上传'); f.reset(); await loadAssets(); closeModal('modal-upload-asset');
  }catch(err){toast(err.message,true)}
});
async function loadAssets(){
  const el=$('#asset-list'); if(!el) return;
  try{
    const rows=await api(`/projects/${projectId}/assets`);
    el.innerHTML=rows.length?rows.map(a=>`<article class="asset-card" data-asset-id="${a.id}">
      <div class="asset-head"><h3>${esc(a.name)}</h3>${status(a.status)}</div>
      <div class="asset-type">${a.asset_type==='character'?'角色':'场景'}</div>
      ${a.selected_image?`<img src="/files/${projectId}/${esc(a.selected_image)}" alt="素材图">`:`<div class="asset-placeholder">未选定素材图</div>`}
      <div class="card-meta"><span>${esc(a.description||'')}</span></div>
      <div class="button-row">
        <button class="btn secondary btn-sm" data-generate-candidates="${a.id}">生成候选</button>
        <button class="btn secondary btn-sm" data-confirm-asset="${a.id}">${a.status==='confirmed'?'已确认':'确认'}</button>
      </div></article>`).join(''):empty('暂无资产，点「新增资产」或「上传素材」。');
  }catch(e){el.innerHTML=empty(e.message);toast(e.message,true)}
}

// ===== 通用 Modal（新建栏浮窗化） =====
function openModal(id){const m=document.getElementById(id);if(m){m.classList.remove('hidden');document.body.classList.add('modal-open')}}
function closeModal(id){const m=id?document.getElementById(id):document.querySelector('.modal-mask:not(.hidden)');if(m)m.classList.add('hidden');document.body.classList.remove('modal-open')}
document.addEventListener('click',e=>{
  if(e.target.closest('[data-close-modal]')){closeModal();return}
  if(e.target.classList && e.target.classList.contains('modal-mask')){closeModal();return}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
document.addEventListener('click',e=>{
  const b=e.target.closest('button[data-action]');if(!b)return;
  const a=b.dataset.action;
  if(a==='open-create-project'){e.preventDefault();openModal('modal-create-project');return}
  if(a==='open-create-novel'){e.preventDefault();openModal('modal-create-novel');return}
  if(a==='open-create-asset'){e.preventDefault();openModal('modal-create-asset');return}
  if(a==='open-upload-asset'){e.preventDefault();openModal('modal-upload-asset');return}
  if(a==='open-create-export'){e.preventDefault();openModal('modal-create-export');return}
});
