from pathlib import Path

part1 = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
  <title>Monica2API · 账号池调度与反代网关</title>
  <!-- Google Fonts: Plus Jakarta Sans + JetBrains Mono -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg-canvas: #f8f5f0;
      --bg-subtle: #f2ede4;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #fffdfa;
      --bg-surface-hover: #fcf8f3;
      --bg-glass: rgba(255, 253, 249, 0.92);
      --bg-input: #fbf9f6;

      --border-dim: rgba(74, 48, 38, 0.08);
      --border-default: rgba(74, 48, 38, 0.12);
      --border-active: rgba(74, 48, 38, 0.28);

      --mocha-dark: #2d1c16;
      --mocha-primary: #4a3026;
      --mocha-hover: #5d3d31;

      --camel-primary: #bda081;
      --camel-light: #f3ece2;
      --camel-border: rgba(189, 160, 129, 0.35);

      --sky-primary: #48789e;
      --sky-light: #eaf3f9;

      --rose-primary: #c45761;
      --rose-light: #fbedee;

      --sage-primary: #4a7558;
      --sage-light: #ebf3ee;

      --amber-primary: #b87a2a;
      --amber-light: #faf2e6;

      --text-primary: #2d1c16;
      --text-secondary: #665248;
      --text-tertiary: #99857b;
      --text-muted: #b5a49b;

      --shadow-sm: 0 2px 8px rgba(50, 30, 22, 0.04);
      --shadow-md: 0 8px 24px rgba(50, 30, 22, 0.06);
      --shadow-lg: 0 16px 40px rgba(50, 30, 22, 0.09);
      --shadow-hover: 0 14px 34px rgba(74, 48, 38, 0.12);

      --radius-xs: 6px;
      --radius-sm: 10px;
      --radius-md: 14px;
      --radius-lg: 20px;
      --radius-full: 9999px;

      --font-display: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-body: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-mono: 'JetBrains Mono', Consolas, monospace;
    }

    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-canvas);
      color: var(--text-primary);
      font-family: var(--font-body);
      font-size: 14px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      min-height: 100vh;
      background-image: 
        radial-gradient(circle at 10% 10%, rgba(243, 236, 226, 0.8) 0%, transparent 40%),
        radial-gradient(circle at 90% 90%, rgba(234, 243, 249, 0.6) 0%, transparent 45%);
    }

    ::-webkit-scrollbar { width: 7px; height: 7px; }
    ::-webkit-scrollbar-track { background: var(--bg-subtle); }
    ::-webkit-scrollbar-thumb { background: #d4c2b0; border-radius: var(--radius-full); }
    ::-webkit-scrollbar-thumb:hover { background: var(--camel-primary); }

    .nav-bar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-glass);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      border-bottom: 1px solid var(--border-default);
      box-shadow: 0 4px 20px rgba(50, 30, 22, 0.03);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 32px;
      height: 68px;
    }

    .nav-brand {
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      user-select: none;
    }

    .nav-brand-logo {
      width: 38px;
      height: 38px;
      background: linear-gradient(135deg, var(--mocha-primary), var(--mocha-hover));
      border-radius: var(--radius-sm);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 800;
      font-size: 17px;
      box-shadow: 0 4px 12px rgba(74, 48, 38, 0.2);
    }

    .nav-brand-text {
      font-family: var(--font-display);
      font-size: 17px;
      font-weight: 800;
      letter-spacing: 0.04em;
      color: var(--mocha-dark);
      line-height: 1.1;
    }

    .nav-brand-sub {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      color: var(--camel-primary);
      text-transform: uppercase;
    }

    .nav-links {
      display: flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-subtle);
      padding: 4px;
      border-radius: var(--radius-full);
      border: 1px solid var(--border-dim);
    }

    .nav-link {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 7px 16px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-secondary);
      border-radius: var(--radius-full);
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      user-select: none;
      border: none;
      background: transparent;
    }

    .nav-link:hover {
      color: var(--mocha-primary);
      background: rgba(255, 255, 255, 0.6);
    }

    .nav-link.active {
      background: var(--mocha-primary);
      color: #ffffff;
      box-shadow: 0 2px 10px rgba(74, 48, 38, 0.2);
    }

    .pulse-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--sage-primary);
      box-shadow: 0 0 8px var(--sage-primary);
      position: relative;
    }
    .pulse-dot.running {
      animation: pulseAnim 1.8s infinite;
    }
    @keyframes pulseAnim {
      0% { box-shadow: 0 0 0 0 rgba(74, 117, 88, 0.6); }
      70% { box-shadow: 0 0 0 8px rgba(74, 117, 88, 0); }
      100% { box-shadow: 0 0 0 0 rgba(74, 117, 88, 0); }
    }

    .nav-auth {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 8px 16px;
      font-family: var(--font-body);
      font-size: 13px;
      font-weight: 600;
      border-radius: var(--radius-full);
      border: 1px solid transparent;
      cursor: pointer;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      text-decoration: none;
      white-space: nowrap;
    }
    .btn-primary {
      background: var(--mocha-primary);
      color: #ffffff;
      box-shadow: 0 2px 10px rgba(74, 48, 38, 0.2);
    }
    .btn-primary:hover {
      background: var(--mocha-hover);
      transform: translateY(-1px);
      box-shadow: 0 4px 14px rgba(74, 48, 38, 0.25);
    }
    .btn-primary-highlight {
      background: linear-gradient(135deg, #5c3527 0%, #3d2118 100%);
      color: #ffffff;
      border: 1px solid rgba(255, 235, 215, 0.3);
      box-shadow: 0 3px 12px rgba(74, 48, 38, 0.28);
    }
    .btn-primary-highlight:hover {
      background: linear-gradient(135deg, #6e4131 0%, #4a281e 100%);
      transform: translateY(-1.5px);
      box-shadow: 0 6px 18px rgba(74, 48, 38, 0.35);
    }
    .btn-secondary {
      background: var(--bg-surface);
      border-color: var(--border-default);
      color: var(--text-primary);
      box-shadow: var(--shadow-sm);
    }
    .btn-secondary:hover {
      background: var(--bg-surface-hover);
      border-color: var(--border-active);
      color: var(--mocha-primary);
    }
    .btn-danger {
      background: var(--rose-primary);
      color: #ffffff;
    }
    .btn-danger:hover {
      background: #b0444e;
    }
    .btn-sm {
      padding: 5px 12px;
      font-size: 12px;
    }

    .main-wrap {
      max-width: 1280px;
      margin: 0 auto;
      padding: 32px 24px 80px;
    }

    .page-section {
      display: none;
      animation: fadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .page-section.active {
      display: block;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .hero-box {
      background: linear-gradient(145deg, #ffffff 0%, #faf6f0 100%);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-lg);
      padding: 36px 40px;
      box-shadow: var(--shadow-md);
      margin-bottom: 28px;
      position: relative;
      overflow: hidden;
    }
    .hero-box::after {
      content: '';
      position: absolute;
      top: -60px;
      right: -60px;
      width: 240px;
      height: 240px;
      background: radial-gradient(circle, rgba(189, 160, 129, 0.16) 0%, transparent 70%);
      border-radius: 50%;
      pointer-events: none;
    }

    .hero-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 5px 12px;
      background: var(--camel-light);
      border: 1px solid var(--camel-border);
      border-radius: var(--radius-full);
      font-size: 11.5px;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: var(--mocha-primary);
      margin-bottom: 12px;
      text-transform: uppercase;
    }

    .hero-title {
      font-family: var(--font-display);
      font-size: 30px;
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.25;
      color: var(--mocha-dark);
      margin-bottom: 10px;
    }
    .hero-title strong {
      background: linear-gradient(135deg, var(--mocha-dark), var(--mocha-hover));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .hero-desc {
      font-size: 14.5px;
      line-height: 1.6;
      color: var(--text-secondary);
      max-width: 800px;
      margin-bottom: 20px;
    }

    .telemetry-bar {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .telemetry-item {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      background: rgba(255, 255, 255, 0.85);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-full);
      font-size: 12.5px;
      color: var(--text-secondary);
      box-shadow: var(--shadow-sm);
    }
    .telemetry-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }

    .card {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-md);
      padding: 24px;
      box-shadow: var(--shadow-sm);
      margin-bottom: 24px;
    }
    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
      flex-wrap: wrap;
      gap: 12px;
    }
    .card-title {
      font-size: 17px;
      font-weight: 700;
      color: var(--mocha-dark);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .card-subtitle {
      font-size: 12.5px;
      color: var(--text-tertiary);
      margin-top: 2px;
    }

    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .metric-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-sm);
      padding: 16px 20px;
      box-shadow: var(--shadow-sm);
    }
    .metric-val {
      font-family: var(--font-mono);
      font-size: 26px;
      font-weight: 700;
      color: var(--mocha-dark);
      line-height: 1.1;
      margin-bottom: 4px;
    }
    .metric-label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-tertiary);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .filter-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .search-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--bg-input);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-full);
      padding: 6px 14px;
      flex: 1;
      max-width: 380px;
    }
    .search-wrap input {
      border: none;
      background: transparent;
      outline: none;
      font-family: var(--font-body);
      font-size: 13px;
      color: var(--text-primary);
      width: 100%;
    }

    .chip-group {
      display: flex;
      gap: 6px;
    }
    .chip {
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      border-radius: var(--radius-full);
      border: 1px solid var(--border-default);
      background: var(--bg-surface);
      color: var(--text-secondary);
      cursor: pointer;
      transition: all 0.2s;
    }
    .chip:hover {
      border-color: var(--camel-primary);
      color: var(--mocha-primary);
    }
    .chip.active {
      background: var(--camel-light);
      border-color: var(--camel-border);
      color: var(--mocha-primary);
      font-weight: 700;
    }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--border-dim);
      border-radius: var(--radius-sm);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }
    th {
      background: var(--bg-subtle);
      color: var(--text-secondary);
      font-weight: 600;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-default);
      font-size: 12px;
    }
    td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-dim);
      vertical-align: middle;
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--bg-surface-hover); }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 8px;
      border-radius: var(--radius-full);
      font-size: 11px;
      font-weight: 700;
      font-family: var(--font-mono);
    }
    .badge-alive {
      background: var(--sage-light);
      color: var(--sage-primary);
      border: 1px solid rgba(74, 117, 88, 0.25);
    }
    .badge-dead {
      background: var(--rose-light);
      color: var(--rose-primary);
      border: 1px solid rgba(196, 87, 97, 0.25);
    }
    .badge-off {
      background: var(--bg-subtle);
      color: var(--text-muted);
      border: 1px solid var(--border-default);
    }

    .quota-track {
      width: 100px;
      height: 6px;
      background: var(--bg-subtle);
      border-radius: 3px;
      overflow: hidden;
      margin-top: 4px;
    }
    .quota-bar {
      height: 100%;
      background: var(--sage-primary);
      border-radius: 3px;
      transition: width 0.3s;
    }
    .quota-bar.warning { background: var(--amber-primary); }
    .quota-bar.danger { background: var(--rose-primary); }

    .form-group {
      margin-bottom: 16px;
    }
    .form-label {
      display: block;
      font-size: 12px;
      font-weight: 700;
      color: var(--text-secondary);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .form-control {
      width: 100%;
      padding: 9px 12px;
      border: 1px solid var(--border-default);
      border-radius: var(--radius-xs);
      background: var(--bg-input);
      font-family: var(--font-body);
      font-size: 13.5px;
      color: var(--text-primary);
      outline: none;
      transition: all 0.2s;
    }
    .form-control:focus {
      border-color: var(--mocha-primary);
      box-shadow: 0 0 0 3px rgba(74, 48, 38, 0.08);
      background: #ffffff;
    }

    .job-box {
      background: #201815;
      color: #ede2db;
      border-radius: var(--radius-sm);
      padding: 16px;
      font-family: var(--font-mono);
      font-size: 12.5px;
      margin-top: 14px;
    }
    .job-log-stream {
      max-height: 200px;
      overflow-y: auto;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
      font-size: 12px;
      line-height: 1.6;
    }
    .job-log-line {
      color: #bfaaa0;
      margin-bottom: 2px;
    }
    .job-log-line.success { color: #8fdca6; }
    .job-log-line.warn { color: #f4c274; }
    .job-log-line.error { color: #ff9da8; }

    .model-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }
    .model-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-md);
      padding: 20px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s;
    }
    .model-card:hover {
      border-color: var(--camel-border);
      box-shadow: var(--shadow-hover);
      transform: translateY(-2px);
    }
    .model-name {
      font-family: var(--font-mono);
      font-size: 15px;
      font-weight: 700;
      color: var(--mocha-dark);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .model-desc {
      font-size: 13px;
      color: var(--text-secondary);
      margin: 10px 0 16px;
      line-height: 1.5;
    }

    .modal-backdrop {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(30, 18, 14, 0.45);
      backdrop-filter: blur(4px);
      z-index: 200;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal-backdrop.show { display: flex; }
    .modal-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-default);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 580px;
      padding: 28px;
      box-shadow: var(--shadow-lg);
      position: relative;
      animation: modalPop 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    @keyframes modalPop {
      from { transform: scale(0.95); opacity: 0; }
      to { transform: scale(1); opacity: 1; }
    }
    .modal-close {
      position: absolute;
      top: 20px;
      right: 20px;
      border: none;
      background: transparent;
      font-size: 18px;
      cursor: pointer;
      color: var(--text-tertiary);
    }

    .chat-box {
      display: flex;
      flex-direction: column;
      height: 540px;
      border: 1px solid var(--border-default);
      border-radius: var(--radius-md);
      background: var(--bg-surface);
      overflow: hidden;
    }
    .chat-messages {
      flex: 1;
      padding: 20px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .chat-msg {
      max-width: 80%;
      padding: 12px 16px;
      border-radius: var(--radius-sm);
      font-size: 13.5px;
      line-height: 1.6;
    }
    .chat-msg.user {
      align-self: flex-end;
      background: var(--mocha-primary);
      color: #ffffff;
      border-bottom-right-radius: 2px;
    }
    .chat-msg.assistant {
      align-self: flex-start;
      background: var(--bg-subtle);
      color: var(--text-primary);
      border-bottom-left-radius: 2px;
    }
    .chat-msg.tool {
      align-self: flex-start;
      background: var(--camel-light);
      border: 1px dashed var(--camel-primary);
      font-family: var(--font-mono);
      font-size: 12px;
    }
    .chat-input-bar {
      border-top: 1px solid var(--border-default);
      padding: 14px 18px;
      display: flex;
      gap: 10px;
      background: var(--bg-surface-elevated);
      align-items: center;
    }
    .chat-input-bar input {
      flex: 1;
      border: 1px solid var(--border-default);
      border-radius: var(--radius-full);
      padding: 10px 16px;
      outline: none;
      font-size: 13.5px;
      background: var(--bg-input);
    }
    .chat-input-bar input:focus {
      border-color: var(--mocha-primary);
      background: #ffffff;
    }
    
    pre code {
      font-family: var(--font-mono);
      font-size: 12px;
      background: #251c19;
      color: #ede0d8;
      padding: 14px;
      border-radius: var(--radius-sm);
      display: block;
      overflow-x: auto;
      line-height: 1.5;
    }
  </style>
</head>
<body>
"""

Path("app/templates/dashboard.html").write_text(part1, encoding="utf-8")
print("Part 1 written successfully.")
