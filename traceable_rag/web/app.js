const $ = (id) => document.getElementById(id);
let busy = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error('无法连接服务，请检查网络或联系管理员。');
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('服务返回异常，请稍后重试或联系管理员。');
  }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求格式有误，请检查输入。');
  return data;
}

async function refreshDocuments() {
  const documents = await api('/documents');
  $('count').textContent = documents.length;
  $('documents').replaceChildren();
  if (!documents.length) $('documents').append(element('p', '还没有文档，上传后即可开始提问。', 'muted'));
  for (const doc of documents) {
    const row = element('div', undefined, 'document');
    row.append(element('span', doc.file_type.toUpperCase(), 'file-icon'));
    const info = element('div');
    const name = element(doc.status === 'ready' ? 'a' : 'span', doc.file_name);
    if (doc.status === 'ready') name.href = `/documents/${encodeURIComponent(doc.document_id)}/file`;
    info.append(name, element('small', doc.status === 'ready' ? `已索引 · ${doc.chunk_count} 个证据块` : doc.status === 'failed' ? '导入失败 · 可重新上传' : '正在导入'));
    row.append(info);
    $('documents').append(row);
  }
}

$('files').addEventListener('change', async (event) => {
  const files = Array.from(event.target.files);
  event.target.disabled = true;
  const messages = [];
  for (const file of files) {
    $('upload-status').textContent = [...messages, `正在解析与索引：${file.name}…`].join('\n');
    try {
      const body = new FormData();
      body.append('file', file);
      const result = await api('/documents/upload', {method: 'POST', body});
      messages.push(`${file.name}：${result.duplicate ? '已存在，未重复入库' : `完成 · ${result.chunk_count} 个证据块`}`);
    } catch (error) {
      messages.push(`${file.name}：${error.message}`);
    }
  }
  $('upload-status').textContent = messages.join('\n');
  event.target.value = '';
  event.target.disabled = false;
  try { await refreshDocuments(); } catch (error) { $('upload-status').textContent += `\n${error.message}`; }
});

function locationText(location) {
  const parts = [];
  if (location.page_number) parts.push(`第 ${location.page_number} 页`);
  if (location.section_path) parts.push(location.section_path);
  if (location.paragraph_index) parts.push(`正文第 ${location.paragraph_index} 段`);
  if (location.table_index) parts.push(`第 ${location.table_index} 个表格 · 行 ${location.row_start}–${location.row_end}`);
  if (location.sheet_name) parts.push(`工作表：${location.sheet_name}`);
  if (location.cell_range) parts.push(`单元格：${location.cell_range}`);
  if (location.bbox) parts.push(`坐标：${location.bbox.map(value => value.toFixed(1)).join(', ')}`);
  return parts.join(' / ');
}

function addMessage(role, text) {
  const message = element('div', undefined, `message ${role}`);
  message.append(element('div', role === 'user' ? '你' : '知识库回答', 'message-label'));
  message.append(element('div', text, 'message-body'));
  $('messages').append(message);
  return message;
}

async function ask(question) {
  if (busy || !question.trim()) return;
  busy = true;
  $('send').disabled = true;
  $('welcome').hidden = true;
  $('question').value = '';
  addMessage('user', question);
  const message = addMessage('assistant', '正在检索文档并核对引用…');
  $('chat-area').scrollTop = $('chat-area').scrollHeight;
  try {
    const result = await api('/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question})});
    message.querySelector('.message-body').textContent = result.answer;
    if (result.citations.length) message.append(element('div', `${result.citations.length} 条原文证据 · 点击展开`, 'evidence-label'));
    for (const citation of result.citations) {
      const details = element('details', undefined, 'citation');
      details.append(element('summary', `[${citation.citation_id}] ${citation.file_name}`));
      details.append(element('p', locationText(citation.source_location)));
      details.append(element('pre', citation.text));
      const link = element('a', '下载原文件核对 ↗');
      link.href = `/documents/${encodeURIComponent(citation.document_id)}/file`;
      details.append(link);
      message.append(details);
    }
  } catch (error) {
    message.querySelector('.message-body').textContent = error.message;
    message.classList.add('error');
  } finally {
    busy = false;
    $('send').disabled = false;
    $('chat-area').scrollTop = $('chat-area').scrollHeight;
    $('question').focus();
  }
}

$('chat-form').addEventListener('submit', (event) => { event.preventDefault(); ask($('question').value); });
$('question').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); ask($('question').value); }
});
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => ask(button.dataset.question)));

async function initialize() {
  try {
    await refreshDocuments();
    const health = await api('/health');
    $('health').textContent = health.status === 'ok' ? '数据库已连接' : '服务待配置';
    $('setup').hidden = health.status === 'ok';
    $('upload-limit').textContent = `单文件最大 ${health.max_upload_mb} MB`;
    $('health').title = '状态检查不包含模型的实际调用结果';
  } catch (error) {
    $('health').textContent = '服务连接失败';
    $('upload-limit').textContent = '服务恢复后可查看上传限制';
    $('upload-status').textContent = error.message;
  }
}
initialize();
