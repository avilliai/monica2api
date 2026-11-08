# -*- coding: utf-8 -*-
import os

HTML_PART_1 = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Monica · 账号池管理与反向代理控制台</title>
  <!-- Google Fonts: Plus Jakarta Sans + JetBrains Mono -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <style>
    /* ==================== APOLLODORUS MOCHA & CREAM THEME ==================== */
    :root {
      --bg-canvas: #f8f5f0;
      --bg-subtle: #f2ede4;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #fffdfa;
      --bg-surface-hover: #fcf8f3;
      --border-dim: rgba(74, 48, 38, 0.08);
      --border-default: rgba(74, 48, 38, 0.14);
      --border-active: rgba(74, 48, 38, 0.28);
      --mocha-dark: #2d1c16;
      --mocha-primary: #4a3026;
      --mocha-hover: #5d3d31;
      --mocha-active: #3a241b;
      --mocha-dim: rgba(74, 48, 38, 0.06);
      --camel-primary: #bda081;
      --camel-light: #f3ece2;
      --sky-primary: #48789e;
      --sky-light: #eaf3f9;
      --sage-primary: #4a7558;
      --sage-light: #ebf3ee;
      --rose-primary: #c45761;
      --rose-light: #fbedee;
      --amber-primary: #b87a2a;
      --amber-light: #faf2e6;
      --text-primary: #2d1c16;
      --text-secondary: #665248;
      --text-tertiary: #99857b;
      --shadow-sm: 0 2px 8px rgba(50, 30, 22, 0.04);
      --shadow-md: 0 8px 24px rgba(50, 30, 22, 0.06);
      --shadow-lg: 0 16px 40px rgba(50, 30, 22, 0.09);
      --radius-sm: 8px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-full: 9999px;
      --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', 'Fira Code', Menlo, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-canvas);
      color: var(--text-primary);
      font-family: var(--font-sans);
      font-size: 14px;
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      -webkit-font-smoothing: antialiased;
    }

    /* 顶部导航 */
    .nav-bar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(255, 253, 249, 0.94);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-dim);
      padding: 0 32px;
      height: 66px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .nav-brand {
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      text-decoration: none;
    }
    .nav-logo-badge {
      width: 38px;
      height: 38px;
      background: var(--mocha-primary);
      border-radius: var(--radius-sm);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: var(--shadow-sm);
    }
    .pulse-dot {
      width: 10px;
      height: 10px;
      background: #4ade80;
      border-radius: 50%;
      box-shadow: 0 0 0 2px rgba(74, 222, 128, 0.25);
      animation: pulse 2s infinite ease-in-out;
    }
    @keyframes pulse {
      0%, 100% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.25); opacity: 0.7; }
    }
    .brand-title {
      font-size: 15px;
      font-weight: 800;
      letter-spacing: 0.5px;
      color: var(--mocha-dark);
      line-height: 1.2;
    }
    .brand-sub {
      font-size: 11px;
      color: var(--text-tertiary);
      letter-spacing: 0.3px;
    }

    /* 导航 Tab 胶囊 */
    .nav-tabs {
      display: flex;
      align-items: center;
      background: var(--bg-subtle);
      padding: 4px;
      border-radius: var(--radius-full);
      gap: 4px;
      border: 1px solid var(--border-dim);
    }
    .nav-tab-btn {
      border: none;
      background: transparent;
      color: var(--text-secondary);
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 600;
      padding: 7px 18px;
      border-radius: var(--radius-full);
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .nav-tab-btn:hover {
      color: var(--mocha-dark);
      background: rgba(255, 255, 255, 0.6);
    }
    .nav-tab-btn.active {
      background: var(--mocha-primary);
      color: #ffffff;
      box-shadow: 0 2px 8px rgba(74, 48, 38, 0.25);
    }

    .nav-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .auth-input-wrap {
      display: flex;
      align-items: center;
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-full);
      padding: 4px 12px;
      gap: 6px;
    }
    .auth-input-wrap input {
      border: none;
      background: transparent;
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-primary);
      width: 120px;
      outline: none;
    }

    .main-wrap {
      flex: 1;
      max-width: 1400px;
      width: 100%;
      margin: 0 auto;
      padding: 24px 32px 48px;
    }

    /* 页面分屏 */
    .tab-page {
      display: none;
      animation: fadeIn 0.25s ease-out;
    }
    .tab-page.active {
      display: block;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .card {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-lg);
      padding: 24px;
      box-shadow: var(--shadow-sm);
    }

    /* 指标卡 */
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    @media (max-width: 1024px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 640px) { .metric-grid { grid-template-columns: 1fr; } }

    .metric-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-md);
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-shadow: var(--shadow-sm);
    }
    .metric-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      color: var(--text-tertiary);
      font-size: 11.5px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .metric-value {
      font-size: 28px;
      font-weight: 800;
      color: var(--mocha-dark);
      font-family: var(--font-sans);
      letter-spacing: -0.5px;
      line-height: 1.1;
    }
    .metric-sub {
      font-size: 12px;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* 徽章 */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 9px;
      border-radius: var(--radius-full);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.3px;
    }
    .badge-success { background: var(--sage-light); color: var(--sage-primary); }
    .badge-warning { background: var(--amber-light); color: var(--amber-primary); }
    .badge-danger { background: var(--rose-light); color: var(--rose-primary); }
    .badge-neutral { background: var(--camel-light); color: var(--mocha-primary); }
    .badge-sky { background: var(--sky-light); color: var(--sky-primary); }

    /* 表格 */
    .table-container {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-sm);
    }
    .table-toolbar {
      padding: 16px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      border-bottom: 1px solid var(--border-dim);
      background: var(--bg-surface-elevated);
    }
    .filter-pills { display: flex; align-items: center; gap: 6px; }
    .filter-pill {
      border: 1px solid var(--border-dim);
      background: var(--bg-surface);
      color: var(--text-secondary);
      font-size: 12px;
      font-weight: 600;
      padding: 5px 12px;
      border-radius: var(--radius-full);
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .filter-pill:hover, .filter-pill.active {
      background: var(--mocha-primary);
      color: #ffffff;
      border-color: var(--mocha-primary);
    }
    .search-input {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-full);
      padding: 6px 14px;
      font-size: 12px;
      font-family: var(--font-sans);
      color: var(--text-primary);
      outline: none;
      width: 240px;
    }
    .search-input:focus { border-color: var(--mocha-primary); }

    table { width: 100%; border-collapse: collapse; text-align: left; }
    th {
      padding: 12px 18px;
      background: var(--bg-subtle);
      font-size: 11px;
      font-weight: 700;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--border-dim);
    }
    td {
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-dim);
      color: var(--text-primary);
      font-size: 13px;
      vertical-align: middle;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--bg-surface-hover); }

    /* 进度条 */
    .progress-bar-wrap {
      width: 100%;
      height: 6px;
      background: var(--bg-subtle);
      border-radius: var(--radius-full);
      overflow: hidden;
      margin-top: 4px;
    }
    .progress-bar-fill {
      height: 100%;
      border-radius: var(--radius-full);
      background: var(--mocha-primary);
      transition: width 0.3s ease;
    }

    /* 按钮 */
    .btn {
      border: none;
      background: var(--mocha-primary);
      color: #ffffff;
      font-family: var(--font-sans);
      font-size: 13px;
      font-weight: 600;
      padding: 8px 18px;
      border-radius: var(--radius-md);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
      box-shadow: var(--shadow-sm);
    }
    .btn:hover { background: var(--mocha-hover); box-shadow: var(--shadow-md); }
    .btn:active { background: var(--mocha-active); }
    .btn-secondary {
      background: var(--bg-surface);
      color: var(--text-primary);
      border: 1px solid var(--border-default);
    }
    .btn-secondary:hover { background: var(--bg-surface-hover); border-color: var(--border-active); }
    .btn-danger { background: var(--rose-primary); color: #ffffff; }
    .btn-danger:hover { background: #b04650; }
    .btn-sm { padding: 4px 10px; font-size: 11px; border-radius: var(--radius-sm); }

    /* 7 款官方免费模型卡片网格 */
    .models-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 20px;
    }
    .model-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-lg);
      padding: 22px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 16px;
      transition: all 0.25s ease;
      position: relative;
    }
    .model-card:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
      border-color: var(--camel-border);
    }
    .model-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }
    .model-title {
      font-size: 17px;
      font-weight: 800;
      color: var(--mocha-dark);
      letter-spacing: -0.2px;
    }
    .model-id-tag {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--sky-primary);
      background: var(--sky-light);
      padding: 3px 8px;
      border-radius: var(--radius-xs);
      display: inline-flex;
      align-items: center;
      gap: 5px;
      margin-top: 6px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .model-id-tag:hover {
      background: #d6e8f4;
    }
    .model-desc {
      font-size: 12.5px;
      color: var(--text-secondary);
      line-height: 1.6;
    }
    .model-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 14px;
      border-top: 1px solid var(--border-dim);
    }
    .model-meta {
      font-size: 11.5px;
      color: var(--text-tertiary);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* 终端控制台 */
    .terminal-window {
      background: #1e1715;
      border-radius: var(--radius-md);
      overflow: hidden;
      box-shadow: var(--shadow-lg);
      display: flex;
      flex-direction: column;
      height: 480px;
    }
    .terminal-bar {
      background: #2a201d;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .terminal-dots { display: flex; align-items: center; gap: 6px; }
    .terminal-dot { width: 11px; height: 11px; border-radius: 50%; }
    .dot-red { background: #ff5f56; }
    .dot-yellow { background: #ffbd2e; }
    .dot-green { background: #27c93f; }
    .terminal-title { color: #bda081; font-family: var(--font-mono); font-size: 12px; font-weight: 600; }
    .terminal-body {
      flex: 1;
      padding: 14px 16px;
      overflow-y: auto;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.6;
      color: #f3ece2;
    }
    .log-line { margin-bottom: 4px; word-break: break-all; }
    .log-time { color: #8e786b; margin-right: 8px; }
    .log-ok { color: #4ade80; }
    .log-warn { color: #fbbf24; }
    .log-err { color: #f87171; }
    .log-sys { color: #38bdf8; }

    /* 对话交互 */
    .chat-container {
      display: flex;
      flex-direction: column;
      height: calc(100vh - 170px);
      min-height: 540px;
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-sm);
    }
    .chat-toolbar {
      padding: 12px 20px;
      background: var(--bg-surface-elevated);
      border-bottom: 1px solid var(--border-dim);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      background: var(--bg-canvas);
    }
    .chat-bubble {
      max-width: 80%;
      padding: 14px 18px;
      border-radius: var(--radius-md);
      font-size: 13.5px;
      line-height: 1.6;
      box-shadow: var(--shadow-sm);
      word-break: break-word;
    }
    .bubble-user {
      align-self: flex-end;
      background: var(--mocha-primary);
      color: #ffffff;
      border-bottom-right-radius: 4px;
    }
    .bubble-assistant {
      align-self: flex-start;
      background: var(--bg-surface);
      color: var(--text-primary);
      border: 1px solid var(--border-dim);
      border-bottom-left-radius: 4px;
    }
    .chat-input-bar {
      padding: 16px 20px;
      background: var(--bg-surface);
      border-top: 1px solid var(--border-dim);
      display: flex;
      gap: 12px;
      align-items: flex-end;
    }
    .chat-textarea {
      flex: 1;
      resize: none;
      height: 48px;
      max-height: 140px;
      padding: 10px 14px;
      border: 1px solid var(--border-default);
      border-radius: var(--radius-md);
      font-family: var(--font-sans);
      font-size: 13.5px;
      color: var(--text-primary);
      background: var(--bg-surface-subtle);
      outline: none;
      transition: border-color 0.2s;
    }
    .chat-textarea:focus { border-color: var(--mocha-primary); background: var(--bg-surface); }

    /* 代码块与 Toast */
    .code-box {
      background: #1e1715;
      color: #f3ece2;
      border-radius: var(--radius-md);
      padding: 16px 20px;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.6;
      overflow-x: auto;
      position: relative;
    }
    .copy-btn {
      position: absolute;
      top: 10px;
      right: 12px;
      background: rgba(255, 255, 255, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: #f3ece2;
      font-size: 11px;
      padding: 4px 10px;
      border-radius: var(--radius-xs);
      cursor: pointer;
      font-family: var(--font-sans);
      transition: all 0.2s;
    }
    .copy-btn:hover { background: rgba(255, 255, 255, 0.25); }

    .toast-container {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 1000;
      display: flex;
      flex-direction: column;
      gap: 8px;
      pointer-events: none;
    }
    .toast {
      background: var(--mocha-dark);
      color: #ffffff;
      padding: 10px 18px;
      border-radius: var(--radius-md);
      font-size: 13px;
      font-weight: 500;
      box-shadow: var(--shadow-lg);
      pointer-events: auto;
      animation: slideIn 0.25s ease-out;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
  </style>
</head>
<body>

  <!-- 顶部导航栏 -->
  <header class="nav-bar">
    <div class="nav-brand" onclick="switchTab('accounts')">
      <div class="nav-logo-badge">
        <span class="pulse-dot"></span>
      </div>
      <div>
        <div class="brand-title">MONICA · GATEWAY</div>
        <div class="brand-sub">ACCOUNT POOL & REVERSE PROXY</div>
      </div>
    </div>

    <!-- 导航胶囊 Tabs (5大独立页面，拒绝堆叠在单一屏) -->
    <nav class="nav-tabs">
      <button class="nav-tab-btn active" id="tab-btn-accounts" onclick="switchTab('accounts')">📊 账号资产池</button>
      <button class="nav-tab-btn" id="tab-btn-register" onclick="switchTab('register')">⚡ 批量注册中心</button>
      <button class="nav-tab-btn" id="tab-btn-models" onclick="switchTab('models')">🤖 官方免费模型</button>
      <button class="nav-tab-btn" id="tab-btn-chat" onclick="switchTab('chat')">💬 在线交互与工具</button>
      <button class="nav-tab-btn" id="tab-btn-guide" onclick="switchTab('guide')">📖 接入指南</button>
    </nav>

    <!-- 右侧操作栏 -->
    <div class="nav-actions">
      <div class="auth-input-wrap" title="管理 API Key (自动保存至本地)">
        <span style="font-size: 11px; color: var(--text-tertiary);">KEY:</span>
        <input type="password" id="input-api-key" placeholder="API Key" onchange="saveApiKey(this.value)" />
      </div>
      <button class="btn btn-secondary btn-sm" onclick="refreshCurrentTab()" title="刷新数据">🔄 刷新</button>
    </div>
  </header>

  <!-- 主视图容器 -->
  <main class="main-wrap">
"""
