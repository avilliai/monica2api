# -*- coding: utf-8 -*-

HTML_PART_2 = """
    <!-- ==================== 1. 账号资产池 TAB ==================== -->
    <div class="tab-page active" id="page-accounts">
      <!-- 4 大指标卡 -->
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-header">
            <span>总资产池容量</span>
            <span>📦</span>
          </div>
          <div class="metric-value" id="stat-total-accounts">-</div>
          <div class="metric-sub">
            <span class="badge badge-sky" id="stat-pool-capacity">Cookie 资产库</span>
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-header">
            <span>健康可用账号</span>
            <span>🟢</span>
          </div>
          <div class="metric-value" id="stat-alive-accounts" style="color: var(--sage-primary);">-</div>
          <div class="metric-sub">
            <span>可用率: <strong id="stat-alive-ratio">-</strong></span>
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-header">
            <span>今日配额消耗</span>
            <span>⚡</span>
          </div>
          <div class="metric-value" id="stat-today-usage" style="color: var(--mocha-primary);">-</div>
          <div class="metric-sub">
            <span>每日重置配额上限</span>
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-header">
            <span>平滑预热机制</span>
            <span>🔥</span>
          </div>
          <div class="metric-value" id="stat-warmer-status" style="font-size: 20px;">运行中</div>
          <div class="metric-sub">
            <span id="stat-warmer-desc">游标低频保活</span>
          </div>
        </div>
      </div>

      <!-- 表格及控制工具栏 -->
      <div class="table-container">
        <div class="table-toolbar">
          <div class="filter-pills">
            <button class="filter-pill active" onclick="setAccountFilter('all', this)">全部账号 (<span id="filter-count-all">0</span>)</button>
            <button class="filter-pill" onclick="setAccountFilter('alive', this)">🟢 健康可用 (<span id="filter-count-alive">0</span>)</button>
            <button class="filter-pill" onclick="setAccountFilter('disabled', this)">⚪ 已停用 (<span id="filter-count-disabled">0</span>)</button>
            <button class="filter-pill" onclick="setAccountFilter('dead', this)">🔴 异常/失效 (<span id="filter-count-dead">0</span>)</button>
          </div>

          <div style="display: flex; align-items: center; gap: 10px;">
            <input type="text" class="search-input" id="account-search" placeholder="🔍 搜索邮箱或账号 ID..." oninput="handleAccountSearch(this.value)" />
            <button class="btn btn-secondary btn-sm" onclick="triggerBatchProbe()" title="对存活账号低频平滑探活">⚡ 批量探活</button>
            <button class="btn btn-secondary btn-sm" onclick="triggerResetQuota()" title="重置今日调用配额计数">🔄 重置配额</button>
            <button class="btn btn-sm" onclick="switchTab('register')">➕ 注册新账号</button>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th style="width: 240px;">账号 / 邮箱</th>
              <th style="width: 120px;">运行状态</th>
              <th style="width: 220px;">今日消耗 / 每日配额</th>
              <th style="width: 180px;">保活与预热状态</th>
              <th style="width: 140px; text-align: right;">资产治理</th>
            </tr>
          </thead>
          <tbody id="accounts-table-body">
            <tr>
              <td colspan="5" style="text-align: center; padding: 40px; color: var(--text-tertiary);">
                正在加载账号资产池数据...
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>


    <!-- ==================== 2. 批量注册中心 TAB ==================== -->
    <div class="tab-page" id="page-register">
      <div style="display: grid; grid-template-columns: 460px 1fr; gap: 24px; align-items: start;">
        
        <!-- 左列：注册参数控制 -->
        <div style="display: flex; flex-direction: column; gap: 20px;">
          <!-- 核心策略卡片 -->
          <div class="card">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;">
              <h3 style="font-size: 16px; font-weight: 800; color: var(--mocha-dark);">⚡ Outlook 邮箱批量注册</h3>
              <span class="badge badge-success">自动平滑并发</span>
            </div>
            <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 18px; line-height: 1.5;">
              复用 Genspark 邮箱资产池（Outlook/Hotmail）。系统自动采用动态限速与无头指纹伪装，避免大批量瞬时请求触发云端防火墙。
            </p>

            <div style="display: flex; flex-direction: column; gap: 14px;">
              <div>
                <label style="font-size: 12px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px;">
                  注册数量 (COUNT)
                </label>
                <div style="display: flex; align-items: center; gap: 10px;">
                  <input type="number" id="reg-count" value="20" min="1" max="500" style="flex: 1; padding: 8px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 13px;" />
                  <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer;">
                    <input type="checkbox" id="reg-all" onchange="toggleRegAll(this.checked)" /> 注册剩余所有
                  </label>
                </div>
              </div>

              <div>
                <label style="font-size: 12px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px;">
                  平滑速率控制 (每分钟注册数量)
                </label>
                <div style="display: flex; align-items: center; gap: 10px;">
                  <input type="number" id="reg-rate" value="20" min="1" max="60" style="flex: 1; padding: 8px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 13px;" />
                  <span style="font-size: 12px; color: var(--text-tertiary);">个/分钟 (推荐20)</span>
                </div>
                <div style="font-size: 11px; color: var(--text-tertiary); margin-top: 4px;">如遇接口频率限制，算法将自适应平滑降速重试。</div>
              </div>

              <div>
                <label style="font-size: 12px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px;">
                  浏览器内核与指纹模式
                </label>
                <select id="reg-backend" style="width: 100%; padding: 8px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-size: 13px; background: var(--bg-surface); color: var(--text-primary);">
                  <option value="auto">自动选择最佳内核 (Auto Camoufox/Playwright)</option>
                  <option value="camoufox">Camoufox 反指纹反检测引擎</option>
                  <option value="playwright">原生 Playwright 无头内核</option>
                </select>
              </div>

              <div style="display: flex; gap: 10px; margin-top: 8px;">
                <button class="btn" style="flex: 1;" id="btn-start-register" onclick="startBatchRegister()">
                  🚀 启动批量注册任务
                </button>
                <button class="btn btn-danger" id="btn-cancel-register" onclick="cancelBatchRegister()" style="display: none;">
                  ⏹ 终止任务
                </button>
              </div>
            </div>
          </div>

          <!-- 单账号即时调试卡片 -->
          <div class="card">
            <h4 style="font-size: 14px; font-weight: 800; color: var(--mocha-dark); margin-bottom: 10px;">
              🔍 指定 Outlook 账号单独注册/重注
            </h4>
            <div style="display: flex; flex-direction: column; gap: 10px;">
              <input type="text" id="reg-single-email" placeholder="邮箱 (如 xxx@outlook.com)" style="padding: 7px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-size: 12px; font-family: var(--font-mono);" />
              <input type="password" id="reg-single-pwd" placeholder="密码 (留空则从邮箱池匹配)" style="padding: 7px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-size: 12px; font-family: var(--font-mono);" />
              <button class="btn btn-secondary btn-sm" onclick="registerSingleAccount()">⚡ 单账号注册测试</button>
            </div>
          </div>
        </div>

        <!-- 右列：macOS 风格终端日志与指标监控 -->
        <div style="display: flex; flex-direction: column; gap: 16px;">
          <!-- 任务状态总览条 -->
          <div class="card" style="padding: 18px 24px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
              <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 13px; font-weight: 700; color: var(--text-secondary);">当前任务状态:</span>
                <span class="badge badge-neutral" id="job-status-badge">IDLE 就绪</span>
              </div>
              <div style="font-size: 12px; color: var(--text-tertiary);" id="job-time-info">-</div>
            </div>

            <!-- 进度条 -->
            <div style="display: flex; align-items: center; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
              <span>任务执行进度 (<span id="job-progress-text">0 / 0</span>)</span>
              <span id="job-percent-text">0%</span>
            </div>
            <div class="progress-bar-wrap" style="height: 8px;">
              <div class="progress-bar-fill" id="job-progress-bar" style="width: 0%;"></div>
            </div>

            <!-- 成功/失败统计 -->
            <div style="display: flex; gap: 20px; margin-top: 14px; font-size: 12px;">
              <span>✅ 成功写入: <strong id="job-success-count" style="color: var(--sage-primary);">0</strong></span>
              <span>❌ 失败重试: <strong id="job-failed-count" style="color: var(--rose-primary);">0</strong></span>
              <span>📦 邮箱池可用剩余: <strong id="job-pool-remaining">-</strong></span>
            </div>
          </div>

          <!-- macOS 终端控制台 -->
          <div class="terminal-window">
            <div class="terminal-bar">
              <div class="terminal-dots">
                <span class="terminal-dot dot-red"></span>
                <span class="terminal-dot dot-yellow"></span>
                <span class="terminal-dot dot-green"></span>
              </div>
              <div class="terminal-title">MONICA-REGISTER-WORKER · LIVE CONSOLE</div>
              <div>
                <button class="btn btn-secondary btn-sm" style="background: rgba(255,255,255,0.08); color: #fff; border: none; padding: 2px 8px; font-size: 10px;" onclick="clearTerminalLogs()">清屏</button>
              </div>
            </div>
            <div class="terminal-body" id="terminal-logs">
              <div class="log-line"><span class="log-time">[SYSTEM]</span><span class="log-sys">终端就绪，点击左侧启动批量注册任务...</span></div>
            </div>
          </div>
        </div>

      </div>
    </div>


    <!-- ==================== 3. 官方免费模型 TAB (严格对齐 7 款官方免费模型) ==================== -->
    <div class="tab-page" id="page-models">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 22px;">
        <div>
          <h2 style="font-size: 20px; font-weight: 800; color: var(--mocha-dark);">🤖 Monica 官方开放免费模型列表</h2>
          <p style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">
            严格对齐 Monica 官方实机开放的 7 款免费基座模型，免消耗高阶算力，由账号资产池全自动平滑负载均衡。
          </p>
        </div>
        <span class="badge badge-success" style="font-size: 12px; padding: 5px 12px;">7 款模型已就绪</span>
      </div>

      <div class="models-grid">
        <!-- 1. GPT-6 Luna -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">OpenAI</span>
                <div class="model-title">GPT-6 Luna</div>
                <div class="model-id-tag" onclick="copyText('gpt-6-luna')" title="点击复制模型 ID">
                  gpt-6-luna 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              Monica 官方免费开放的旗舰轻量多模态模型，响应延迟极低，通用推理理解出众，日常交互与对话首选。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>⚡ 极速推理</span>
              <span>•</span>
              <span>128K 上下文</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('gpt-6-luna')">🚀 去对话测试</button>
          </div>
        </div>

        <!-- 2. DeepSeek-V4.1-Flash -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">DeepSeek</span>
                <div class="model-title">DeepSeek-V4.1-Flash</div>
                <div class="model-id-tag" onclick="copyText('deepseek-v4.1-flash')" title="点击复制模型 ID">
                  deepseek-v4.1-flash 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              深度求索新一代第4代超轻量 Flash 模型，代码补全、逻辑判断及中文常识问答具备顶尖吞吐性能。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>🚀 闪电吞吐</span>
              <span>•</span>
              <span>MoE 架构</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('deepseek-v4.1-flash')">🚀 去对话测试</button>
          </div>
        </div>

        <!-- 3. Gemini 3.5 Flash-Lite -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">Google</span>
                <div class="model-title">Gemini 3.5 Flash-Lite</div>
                <div class="model-id-tag" onclick="copyText('gemini-3.5-flash-lite')" title="点击复制模型 ID">
                  gemini-3.5-flash-lite 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              Google 3.5 世代轻量旗舰模型，首字到达延迟（TTFT）极低，兼具丰富的世界通识与跨语种摘要能力。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>🌐 跨语种旗舰</span>
              <span>•</span>
              <span>低延迟</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('gemini-3.5-flash-lite')">🚀 去对话测试</button>
          </div>
        </div>

        <!-- 4. Qwen3.8 Flash -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">Alibaba Qwen</span>
                <div class="model-title">Qwen3.8 Flash</div>
                <div class="model-id-tag" onclick="copyText('qwen3.8-flash')" title="点击复制模型 ID">
                  qwen3.8-flash 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              阿里通义千问最新 3.8 Flash 开源基座，深度契合中文语法习惯，文本长程润色与结构化抽取兼优。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>🇨🇳 中文卓越</span>
              <span>•</span>
              <span>长程润色</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('qwen3.8-flash')">🚀 去对话测试</button>
          </div>
        </div>

        <!-- 5. GLM 5.3 Flash -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">Zhipu AI</span>
                <div class="model-title">GLM 5.3 Flash</div>
                <div class="model-id-tag" onclick="copyText('glm-5.3-flash')" title="点击复制模型 ID">
                  glm-5.3-flash 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              智谱新一代高速基座，中文知识密度高，学术论述与逻辑问答平顺流利，支持高并发轻量对话。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>⚡ 智谱新基座</span>
              <span>•</span>
              <span>高知识密度</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('glm-5.3-flash')">🚀 去对话测试</button>
          </div>
        </div>

        <!-- 6. Gemini 3.1 Flash-Lite -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">Google</span>
                <div class="model-title">Gemini 3.1 Flash-Lite</div>
                <div class="model-id-tag" onclick="copyText('gemini-3.1-flash-lite')" title="点击复制模型 ID">
                  gemini-3.1-flash-lite 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              Google 3.1 极速轻量模型，高并发对话场景表现稳健，擅长短报文即时问答与结构化数据处理。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>⏱ 稳健响应</span>
              <span>•</span>
              <span>轻量高并发</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('gemini-3.1-flash-lite')">🚀 去对话测试</button>
          </div>
        </div>

        <!-- 7. Gemini 3 Flash -->
        <div class="model-card">
          <div>
            <div class="model-header">
              <div>
                <span class="badge badge-neutral" style="margin-bottom: 6px;">Google</span>
                <div class="model-title">Gemini 3 Flash</div>
                <div class="model-id-tag" onclick="copyText('gemini-3-flash')" title="点击复制模型 ID">
                  gemini-3-flash 📋
                </div>
              </div>
              <span class="badge badge-success">官方免费</span>
            </div>
            <p class="model-desc" style="margin-top: 12px;">
              Google 3 代 Flash 完整版本，逻辑严谨，上下文保持稳定，适合复杂多步骤分析与总结。
            </p>
          </div>
          <div class="model-footer">
            <div class="model-meta">
              <span>🎯 逻辑严谨</span>
              <span>•</span>
              <span>多步骤分析</span>
            </div>
            <button class="btn btn-sm" onclick="jumpToChatWithModel('gemini-3-flash')">🚀 去对话测试</button>
          </div>
        </div>
      </div>
    </div>


    <!-- ==================== 4. 在线交互与工具 TAB ==================== -->
    <div class="tab-page" id="page-chat">
      <div class="chat-container">
        <!-- 聊天顶部控制条 -->
        <div class="chat-toolbar">
          <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 13px; font-weight: 700; color: var(--text-secondary);">选择测试模型:</span>
            <select id="chat-model-select" style="padding: 6px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); font-size: 13px; font-weight: 600; color: var(--mocha-dark); background: var(--bg-surface); outline: none;">
              <optgroup label="🌟 官方免费模型 (Monica 免费开放)">
                <option value="gpt-6-luna">GPT-6 Luna (gpt-6-luna)</option>
                <option value="deepseek-v4.1-flash">DeepSeek-V4.1-Flash (deepseek-v4.1-flash)</option>
                <option value="gemini-3.5-flash-lite">Gemini 3.5 Flash-Lite (gemini-3.5-flash-lite)</option>
                <option value="qwen3.8-flash">Qwen3.8 Flash (qwen3.8-flash)</option>
                <option value="glm-5.3-flash">GLM 5.3 Flash (glm-5.3-flash)</option>
                <option value="gemini-3.1-flash-lite">Gemini 3.1 Flash-Lite (gemini-3.1-flash-lite)</option>
                <option value="gemini-3-flash" selected>Gemini 3 Flash (gemini-3-flash)</option>
              </optgroup>
              <optgroup label="🔧 基础通用模型">
                <option value="gpt-4o">GPT-4o (gpt-4o)</option>
                <option value="gpt-4o-mini">GPT-4o Mini (gpt-4o-mini)</option>
              </optgroup>
            </select>
          </div>

          <div style="display: flex; align-items: center; gap: 10px;">
            <button class="btn btn-secondary btn-sm" onclick="toggleSystemPromptModal()">⚙️ System Prompt</button>
            <button class="btn btn-secondary btn-sm" onclick="clearChatHistory()">🗑️ 清空会话</button>
          </div>
        </div>

        <!-- 消息显示区 -->
        <div class="chat-messages" id="chat-messages">
          <div class="chat-bubble bubble-assistant">
            👋 您好！我是 Monica2API 代理控制台助手。请在上方选择 7 款官方免费模型中的任意一款，输入您的问题即可开启流式对话测试。
          </div>
        </div>

        <!-- 底部输入框 -->
        <div class="chat-input-bar">
          <textarea class="chat-textarea" id="chat-input" placeholder="输入测试问题... (按 Enter 发送，Shift+Enter 换行)" onkeydown="handleChatInputKeydown(event)"></textarea>
          <button class="btn" id="btn-send-chat" onclick="sendChatMessage()">
            <span>发送</span>
            <span>➤</span>
          </button>
        </div>
      </div>
    </div>


    <!-- ==================== 5. 接入指南 TAB ==================== -->
    <div class="tab-page" id="page-guide">
      <div style="display: flex; flex-direction: column; gap: 24px; max-width: 960px;">
        <div class="card">
          <h2 style="font-size: 18px; font-weight: 800; color: var(--mocha-dark); margin-bottom: 8px;">
            📖 标准 OpenAI 兼容接口接入指引
          </h2>
          <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">
            本网关 100% 遵循 OpenAI REST API 规范，无缝集成 NextChat、ChatBox、LobeChat、LangChain、AutoGPT 等客户端或开发框架。
          </p>

          <div style="margin-top: 20px; display: flex; flex-direction: column; gap: 16px;">
            <div>
              <label style="font-size: 12px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px;">
                API BASE URL (基础接口地址)
              </label>
              <div class="code-box">
                <span id="guide-base-url">http://127.0.0.1:8017/v1</span>
                <button class="copy-btn" onclick="copyText(document.getElementById('guide-base-url').innerText)">复制</button>
              </div>
            </div>

            <div>
              <label style="font-size: 12px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px;">
                Python (OpenAI SDK 官方库) 代码示例
              </label>
              <div class="code-box">
                <pre><code>from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8017/v1",
    api_key="change-me"  # 填入您的 API Key
)

# 自由调用 7 款官方免费模型中的任意一款：
response = client.chat.completions.create(
    model="gpt-6-luna",  # 或 deepseek-v4.1-flash, gemini-3.5-flash-lite, qwen3.8-flash 等
    messages=[
        {"role": "user", "content": "你好，请介绍一下你自己！"}
    ],
    stream=True
)

for chunk in response:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)</code></pre>
                <button class="copy-btn" onclick="copyPythonCode()">复制代码</button>
              </div>
            </div>

            <div>
              <label style="font-size: 12px; font-weight: 700; color: var(--text-secondary); display: block; margin-bottom: 6px;">
                cURL 命令行请求测试
              </label>
              <div class="code-box">
                <pre><code>curl -X POST http://127.0.0.1:8017/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer change-me" \
  -d '{
    "model": "deepseek-v4.1-flash",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'</code></pre>
                <button class="copy-btn" onclick="copyCurlCode()">复制代码</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

  </main>

  <!-- Toast 提示容器 -->
  <div class="toast-container" id="toast-container"></div>
"""
