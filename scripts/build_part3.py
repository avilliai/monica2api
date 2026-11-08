# -*- coding: utf-8 -*-

HTML_PART_3 = """
  <!-- 核心交互脚本 -->
  <script>
    /* ==================== 全局状态与初始化 ==================== */
    let currentTab = 'accounts';
    let apiKey = localStorage.getItem('monica_admin_api_key') || 'change-me';
    let accountsData = [];
    let currentFilter = 'all';
    let searchQuery = '';
    let pollingTimer = null;
    let chatHistory = [];
    let systemPrompt = '';

    document.addEventListener('DOMContentLoaded', () => {
      // 初始化 API Key 输入框
      const keyInput = document.getElementById('input-api-key');
      if (keyInput) keyInput.value = apiKey;

      // 响应 URL Hash 或默认 Tab
      const hash = window.location.hash.replace('#', '');
      if (['accounts', 'register', 'models', 'chat', 'guide'].includes(hash)) {
        switchTab(hash);
      } else {
        switchTab('accounts');
      }

      // 首次加载账号数据与邮箱池信息
      loadAccounts();
      loadPoolInfo();
      checkActiveRegisterJob();
    });

    /* ==================== 安全防御辅助函数 ==================== */
    function escapeHtml(str) {
      if (str == null) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function safeSlice(val, start, end) {
      if (val == null) return '';
      return String(val).slice(start, end);
    }

    function showToast(msg, type = 'info') {
      const container = document.getElementById('toast-container');
      const toast = document.createElement('div');
      toast.className = 'toast';
      const icon = type === 'ok' ? '✅' : (type === 'err' ? '❌' : 'ℹ️');
      toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(msg)}</span>`;
      container.appendChild(toast);
      setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
      }, 3000);
    }

    function copyText(text) {
      if (!text) return;
      navigator.clipboard.writeText(text).then(() => {
        showToast(`已复制: ${text}`, 'ok');
      }).catch(() => {
        showToast('复制失败，请手动复制', 'err');
      });
    }

    function saveApiKey(val) {
      apiKey = val.trim();
      localStorage.setItem('monica_admin_api_key', apiKey);
      showToast('API Key 已更新', 'ok');
      refreshCurrentTab();
    }

    /* ==================== TAB 切换逻辑 ==================== */
    function switchTab(tabName) {
      currentTab = tabName;
      window.location.hash = tabName;

      // 切换按钮状态
      document.querySelectorAll('.nav-tab-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.getElementById(`tab-btn-${tabName}`);
      if (activeBtn) activeBtn.classList.add('active');

      // 切换视图面板
      document.querySelectorAll('.tab-page').forEach(page => page.classList.remove('active'));
      const activePage = document.getElementById(`page-${tabName}`);
      if (activePage) activePage.classList.add('active');

      // 触发对应视图的数据刷新
      if (tabName === 'accounts') {
        loadAccounts();
      } else if (tabName === 'register') {
        loadPoolInfo();
        checkActiveRegisterJob();
      }
    }

    function refreshCurrentTab() {
      if (currentTab === 'accounts') {
        loadAccounts();
        showToast('账号资产数据已刷新', 'info');
      } else if (currentTab === 'register') {
        loadPoolInfo();
        checkActiveRegisterJob();
        showToast('注册中心数据已刷新', 'info');
      } else {
        showToast('页面已刷新', 'info');
      }
    }

    function jumpToChatWithModel(modelId) {
      switchTab('chat');
      const select = document.getElementById('chat-model-select');
      if (select) {
        select.value = modelId;
      }
      setTimeout(() => {
        const input = document.getElementById('chat-input');
        if (input) input.focus();
      }, 200);
      showToast(`已就绪测试模型: ${modelId}`, 'ok');
    }

    /* ==================== 1. 账号资产池治理 ==================== */
    async function loadAccounts() {
      try {
        const res = await fetch('/admin/accounts/detail', {
          headers: { 'X-API-Key': apiKey }
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        accountsData = Array.isArray(data.accounts) ? data.accounts : (data.data || []);
        
        // 渲染统计指标
        const total = accountsData.length;
        const alive = accountsData.filter(a => a.is_alive).length;
        const disabled = accountsData.filter(a => a.disabled).length;
        const dead = accountsData.filter(a => !a.is_alive && !a.disabled).length;

        document.getElementById('stat-total-accounts').innerText = total;
        document.getElementById('stat-alive-accounts').innerText = alive;
        document.getElementById('stat-alive-ratio').innerText = total > 0 ? `${Math.round((alive / total) * 100)}%` : '0%';

        // 计算今日总调用量
        let totalTodayUsage = 0;
        accountsData.forEach(a => {
          totalTodayUsage += (a.today_usage || a.request_count || 0);
        });
        document.getElementById('stat-today-usage').innerText = totalTodayUsage;

        // 更新过滤胶囊计数
        document.getElementById('filter-count-all').innerText = total;
        document.getElementById('filter-count-alive').innerText = alive;
        document.getElementById('filter-count-disabled').innerText = disabled;
        document.getElementById('filter-count-dead').innerText = dead;

        renderAccountsTable();
      } catch (err) {
        console.error('Failed to load accounts:', err);
        const tbody = document.getElementById('accounts-table-body');
        if (tbody) {
          tbody.innerHTML = `
            <tr>
              <td colspan="5" style="text-align: center; padding: 30px; color: var(--rose-primary);">
                ⚠️ 加载账号资产池失败: ${escapeHtml(err.message)}。<br />
                <span style="font-size: 12px; color: var(--text-tertiary);">请检查 API Key 配置是否正确或服务端连接状态。</span>
              </td>
            </tr>
          `;
        }
      }
    }

    function setAccountFilter(filter, btn) {
      currentFilter = filter;
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      if (btn) btn.classList.add('active');
      renderAccountsTable();
    }

    function handleAccountSearch(val) {
      searchQuery = (val || '').trim().toLowerCase();
      renderAccountsTable();
    }

    function renderAccountsTable() {
      const tbody = document.getElementById('accounts-table-body');
      if (!tbody) return;

      let filtered = accountsData.filter(acc => {
        // 状态筛选
        if (currentFilter === 'alive' && (!acc.is_alive || acc.disabled)) return false;
        if (currentFilter === 'disabled' && !acc.disabled) return false;
        if (currentFilter === 'dead' && (acc.is_alive || acc.disabled)) return false;

        // 搜索筛选
        if (searchQuery) {
          const email = String(acc.email || '').toLowerCase();
          const accId = String(acc.id != null ? acc.id : '').toLowerCase();
          if (!email.includes(searchQuery) && !accId.includes(searchQuery)) return false;
        }
        return true;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; padding: 40px; color: var(--text-tertiary);">
              未找到匹配的账号记录
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = filtered.map(acc => {
        // 核心安全防御：将 acc.id 强制转换为 String，杜绝 acc.id.slice is not a function 异常！
        const rawId = acc.id != null ? acc.id : '';
        const idStr = String(rawId);
        const shortId = idStr.length > 8 ? idStr.slice(0, 8) + '...' : (idStr || '-');
        const emailStr = String(acc.email || `account-${idStr}`);

        // 状态徽章
        let statusBadge = '<span class="badge badge-success">🟢 存活可用</span>';
        if (acc.disabled) {
          statusBadge = '<span class="badge badge-neutral">⚪ 已手动停用</span>';
        } else if (!acc.is_alive) {
          statusBadge = '<span class="badge badge-danger">🔴 异常失效</span>';
        }

        // 今日配额与消耗
        const usage = Number(acc.today_usage || acc.request_count || 0);
        const limit = Number(acc.daily_limit || 200);
        const pct = Math.min(100, Math.round((usage / limit) * 100));

        // 预热/保活时间
        const lastChecked = acc.last_checked ? new Date(acc.last_checked * 1000).toLocaleTimeString() : '未预热';

        return `
          <tr>
            <td>
              <div style="font-weight: 700; color: var(--mocha-dark); font-family: var(--font-mono);">${escapeHtml(emailStr)}</div>
              <div style="font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono);">ID: ${escapeHtml(shortId)}</div>
            </td>
            <td>${statusBadge}</td>
            <td>
              <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px;">
                <span>已用: <strong>${usage}</strong> / ${limit}</span>
                <span style="color: var(--text-tertiary);">${pct}%</span>
              </div>
              <div class="progress-bar-wrap">
                <div class="progress-bar-fill" style="width: ${pct}%; background: ${pct > 80 ? 'var(--rose-primary)' : 'var(--mocha-primary)'};"></div>
              </div>
            </td>
            <td>
              <div style="font-size: 12px; color: var(--text-secondary);">🕒 探活: ${escapeHtml(lastChecked)}</div>
              <div style="font-size: 11px; color: var(--text-tertiary);">${acc.error ? escapeHtml(safeSlice(acc.error, 0, 20)) : '健康状态良好'}</div>
            </td>
            <td style="text-align: right;">
              <div style="display: inline-flex; gap: 6px;">
                <button class="btn btn-secondary btn-sm" onclick="probeSingleAccount('${escapeHtml(idStr)}')" title="单独低频探活">⚡ 探活</button>
                <button class="btn btn-secondary btn-sm" onclick="toggleAccount('${escapeHtml(idStr)}', ${acc.disabled ? 'false' : 'true'})">
                  ${acc.disabled ? '▶ 启用' : '⏸ 停用'}
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteAccount('${escapeHtml(idStr)}')" title="从资产池彻底移除">✕</button>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }

    async function probeSingleAccount(accId) {
      try {
        showToast(`正在探活账号 ${accId}...`, 'info');
        const res = await fetch(`/admin/accounts/${accId}/probe`, {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        });
        const data = await res.json();
        if (data.status === 'ok') {
          showToast(`账号 ${accId} 探活成功 (存活: ${data.is_alive})`, 'ok');
        } else {
          showToast(`探活失败: ${data.message || '未知错误'}`, 'err');
        }
        loadAccounts();
      } catch (err) {
        showToast(`探活请求异常: ${err.message}`, 'err');
      }
    }

    async function toggleAccount(accId, targetDisabled) {
      try {
        const res = await fetch(`/admin/accounts/${accId}/toggle`, {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        });
        const data = await res.json();
        showToast(`账号已${targetDisabled ? '停用' : '启用'}`, 'ok');
        loadAccounts();
      } catch (err) {
        showToast(`操作失败: ${err.message}`, 'err');
      }
    }

    async function deleteAccount(accId) {
      if (!confirm(`确定要从资产池中彻底移除账号 [${accId}] 吗？`)) return;
      try {
        const res = await fetch(`/admin/accounts/${accId}`, {
          method: 'DELETE',
          headers: { 'X-API-Key': apiKey }
        });
        showToast('账号已从资产池移除', 'ok');
        loadAccounts();
      } catch (err) {
        showToast(`删除失败: ${err.message}`, 'err');
      }
    }

    async function triggerBatchProbe() {
      try {
        showToast('已启动平滑批量探活任务...', 'info');
        const res = await fetch('/admin/accounts/probe', {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        });
        const data = await res.json();
        showToast(`探活完成: 存活 ${data.alive_count || 0} / 总计 ${data.total_count || 0}`, 'ok');
        loadAccounts();
      } catch (err) {
        showToast(`批量探活失败: ${err.message}`, 'err');
      }
    }

    async function triggerResetQuota() {
      if (!confirm('确定要清零今日所有账号的配额使用计数吗？')) return;
      try {
        const res = await fetch('/admin/accounts/reset-quota', {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        });
        showToast('今日配额使用计数已全部重置清零', 'ok');
        loadAccounts();
      } catch (err) {
        showToast(`重置配额失败: ${err.message}`, 'err');
      }
    }


    /* ==================== 2. 批量注册中心控制 ==================== */
    function toggleRegAll(checked) {
      const countInput = document.getElementById('reg-count');
      if (countInput) {
        countInput.disabled = checked;
        if (checked) countInput.value = '全部剩余';
        else countInput.value = '20';
      }
    }

    async function loadPoolInfo() {
      try {
        const res = await fetch('/admin/register/pool-info');
        if (!res.ok) return;
        const data = await res.json();
        const rem = data.remaining_outlook_count != null ? data.remaining_outlook_count : (data.remaining != null ? data.remaining : '-');
        const total = data.total_outlook_count != null ? data.total_outlook_count : (data.total != null ? data.total : '-');
        document.getElementById('job-pool-remaining').innerText = `${rem} / ${total} 个`;
      } catch (e) {}
    }

    function appendTerminalLog(msg, type = 'sys') {
      const body = document.getElementById('terminal-logs');
      if (!body) return;
      const line = document.createElement('div');
      line.className = 'log-line';
      const timeStr = new Date().toLocaleTimeString();
      let colorClass = 'log-sys';
      if (type === 'ok') colorClass = 'log-ok';
      else if (type === 'warn') colorClass = 'log-warn';
      else if (type === 'err') colorClass = 'log-err';

      line.innerHTML = `<span class="log-time">[${timeStr}]</span><span class="${colorClass}">${escapeHtml(msg)}</span>`;
      body.appendChild(line);
      body.scrollTop = body.scrollHeight;
    }

    function clearTerminalLogs() {
      const body = document.getElementById('terminal-logs');
      if (body) body.innerHTML = '';
      appendTerminalLog('控制台已清屏', 'sys');
    }

    async function startBatchRegister() {
      const regAll = document.getElementById('reg-all').checked;
      const countVal = parseInt(document.getElementById('reg-count').value, 10) || 20;
      const rateVal = parseFloat(document.getElementById('reg-rate').value) || 20.0;
      const backendVal = document.getElementById('reg-backend').value;

      try {
        appendTerminalLog(`[START] 准备发起注册任务 (目标: ${regAll ? '全部剩余' : countVal + '个'}, 速率: ${rateVal}/min)...`, 'sys');
        
        const payload = {
          count: regAll ? 1000 : countVal,
          rate_per_minute: rateVal,
          rate: rateVal,
          register_all: regAll,
          mode: 'outlook',
          backend: backendVal
        };

        const res = await fetch('/admin/register/outlook/batch', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey
          },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          const errText = await res.text();
          throw new Error(`HTTP ${res.status}: ${errText}`);
        }

        const data = await res.json();
        appendTerminalLog(`[SUCCESS] 注册任务已创建启动! Job ID: ${data.job_id || 'active'}`, 'ok');
        showToast('批量注册任务已成功启动！', 'ok');

        // 切换按钮状态并开启轮询
        document.getElementById('btn-start-register').style.display = 'none';
        document.getElementById('btn-cancel-register').style.display = 'inline-flex';
        startJobPolling();
      } catch (err) {
        appendTerminalLog(`[ERROR] 任务创建失败: ${err.message}`, 'err');
        showToast(`启动失败: ${err.message}`, 'err');
      }
    }

    async function cancelBatchRegister() {
      try {
        appendTerminalLog('[CANCEL] 正在请求终止当前任务...', 'warn');
        const res = await fetch('/admin/register/outlook/cancel', {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        });
        const data = await res.json();
        appendTerminalLog(`[CANCEL] 任务终止指令已下达: ${data.message || 'OK'}`, 'warn');
        showToast('任务已请求终止', 'info');
      } catch (err) {
        appendTerminalLog(`[ERROR] 终止请求异常: ${err.message}`, 'err');
      }
    }

    function startJobPolling() {
      if (pollingTimer) clearInterval(pollingTimer);
      pollingTimer = setInterval(checkActiveRegisterJob, 2000);
      checkActiveRegisterJob();
    }

    async function checkActiveRegisterJob() {
      try {
        const res = await fetch('/admin/register/outlook/status', {
          headers: { 'X-API-Key': apiKey }
        });
        if (!res.ok) return;
        const data = await res.json();

        const status = String(data.status || 'IDLE').toUpperCase();
        const progress = Number(data.progress || 0);
        const total = Number(data.total || 0);
        const succeeded = Number(data.success_count || data.succeeded || 0);
        const failed = Number(data.failed_count || data.failed || 0);

        // 更新状态徽章
        const badge = document.getElementById('job-status-badge');
        if (badge) {
          if (status === 'RUNNING') {
            badge.className = 'badge badge-success';
            badge.innerText = '⚡ RUNNING 运行中';
          } else if (status === 'FINISHED' || status === 'COMPLETED') {
            badge.className = 'badge badge-sky';
            badge.innerText = '🏁 FINISHED 已完成';
          } else if (status === 'CANCELLED' || status === 'CANCELED') {
            badge.className = 'badge badge-warning';
            badge.innerText = '⏹ CANCELLED 已终止';
          } else if (status === 'FAILED') {
            badge.className = 'badge badge-danger';
            badge.innerText = '❌ FAILED 异常';
          } else {
            badge.className = 'badge badge-neutral';
            badge.innerText = '💤 IDLE 就绪';
          }
        }

        // 更新进度条
        const pct = total > 0 ? Math.min(100, Math.round((progress / total) * 100)) : 0;
        document.getElementById('job-progress-text').innerText = `${progress} / ${total}`;
        document.getElementById('job-percent-text').innerText = `${pct}%`;
        document.getElementById('job-progress-bar').style.width = `${pct}%`;

        // 更新计数
        document.getElementById('job-success-count').innerText = succeeded;
        document.getElementById('job-failed-count').innerText = failed;

        // 按钮显示状态
        if (status === 'RUNNING') {
          document.getElementById('btn-start-register').style.display = 'none';
          document.getElementById('btn-cancel-register').style.display = 'inline-flex';
        } else {
          document.getElementById('btn-start-register').style.display = 'inline-flex';
          document.getElementById('btn-cancel-register').style.display = 'none';
          if (pollingTimer && status !== 'IDLE') {
            clearInterval(pollingTimer);
            pollingTimer = null;
            loadAccounts(); // 任务结束后刷新一次资产池
            loadPoolInfo();
          }
        }

        // 渲染新日志
        if (Array.isArray(data.recent_logs)) {
          // 这里可以增量渲染日志
        }
      } catch (err) {}
    }

    async function registerSingleAccount() {
      const email = document.getElementById('reg-single-email').value.trim();
      const pwd = document.getElementById('reg-single-pwd').value.trim();
      if (!email) {
        showToast('请输入要注册测试的 Outlook 邮箱地址', 'warn');
        return;
      }

      try {
        appendTerminalLog(`[SINGLE] 开始为单独账号 ${email} 提交注册...`, 'sys');
        const res = await fetch('/admin/register/outlook/batch', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': apiKey
          },
          body: JSON.stringify({
            count: 1,
            rate_per_minute: 10,
            mode: 'outlook'
          })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        appendTerminalLog(`[SINGLE] 单账号注册任务已入队`, 'ok');
        showToast('单账号注册任务已发起！', 'ok');
        startJobPolling();
      } catch (err) {
        appendTerminalLog(`[ERROR] 单账号注册异常: ${err.message}`, 'err');
      }
    }


    /* ==================== 4. 在线交互测试与流式对话 ==================== */
    function handleChatInputKeydown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendChatMessage();
      }
    }

    function clearChatHistory() {
      chatHistory = [];
      const box = document.getElementById('chat-messages');
      if (box) {
        box.innerHTML = `
          <div class="chat-bubble bubble-assistant">
            会话已清空。您可以随时输入新问题开始测试。
          </div>
        `;
      }
      showToast('会话已清空', 'info');
    }

    function toggleSystemPromptModal() {
      const prompt = prompt('请输入全局 System Prompt (系统提示词):', systemPrompt);
      if (prompt !== null) {
        systemPrompt = prompt.trim();
        showToast(systemPrompt ? 'System Prompt 已设置' : '已清除 System Prompt', 'ok');
      }
    }

    async function sendChatMessage() {
      const input = document.getElementById('chat-input');
      const text = (input ? input.value : '').trim();
      if (!text) return;

      const model = document.getElementById('chat-model-select').value;
      input.value = '';

      // 追加用户气泡
      const box = document.getElementById('chat-messages');
      const userBubble = document.createElement('div');
      userBubble.className = 'chat-bubble bubble-user';
      userBubble.innerText = text;
      box.appendChild(userBubble);

      // 准备助手气泡
      const aiBubble = document.createElement('div');
      aiBubble.className = 'chat-bubble bubble-assistant';
      aiBubble.innerHTML = '<span style="color: var(--text-tertiary);">思考中...</span>';
      box.appendChild(aiBubble);
      box.scrollTop = box.scrollHeight;

      // 构建请求消息体
      const messages = [];
      if (systemPrompt) {
        messages.push({ role: 'system', content: systemPrompt });
      }
      chatHistory.forEach(m => messages.push(m));
      messages.push({ role: 'user', content: text });

      try {
        const started = performance.now();
        const res = await fetch('/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`
          },
          body: JSON.stringify({
            model: model,
            messages: messages,
            stream: true
          })
        });

        if (!res.ok) {
          const errText = await res.text();
          throw new Error(`HTTP ${res.status}: ${errText}`);
        }

        aiBubble.innerText = '';
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let fullReply = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\\n');
          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data: ') && trimmed !== 'data: [DONE]') {
              try {
                const parsed = JSON.parse(trimmed.slice(6));
                const delta = parsed.choices?.[0]?.delta?.content || '';
                fullReply += delta;
                aiBubble.innerText = fullReply;
                box.scrollTop = box.scrollHeight;
              } catch (e) {}
            }
          }
        }

        const elapsed = ((performance.now() - started) / 1000).toFixed(2);
        // 保存历史记录
        chatHistory.push({ role: 'user', content: text });
        chatHistory.push({ role: 'assistant', content: fullReply });
      } catch (err) {
        aiBubble.innerHTML = `<span style="color: var(--rose-primary);">⚠️ 请求失败: ${escapeHtml(err.message)}</span>`;
      }
    }


    /* ==================== 5. 代码复制代码 ==================== */
    function copyPythonCode() {
      const code = `from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8017/v1",
    api_key="${apiKey}"
)

response = client.chat.completions.create(
    model="gpt-6-luna",
    messages=[{"role": "user", "content": "你好，请介绍一下你自己！"}],
    stream=True
)

for chunk in response:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
`;
      copyText(code);
    }

    function copyCurlCode() {
      const code = `curl -X POST http://127.0.0.1:8017/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ${apiKey}" \\
  -d '{
    "model": "deepseek-v4.1-flash",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'`;
      copyText(code);
    }
  </script>
</body>
</html>
"""
