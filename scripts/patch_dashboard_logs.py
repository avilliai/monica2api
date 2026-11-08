from pathlib import Path

path = Path("app/templates/dashboard.html")
content = path.read_text(encoding="utf-8")

# Let's declare state variables before appendTerminalLog
state_vars = """    let lastRenderedJobId = null;
    let lastRenderedLogCount = 0;

    function appendTerminalLog(msg, type = 'sys') {"""

old_func_start = """    function appendTerminalLog(msg, type = 'sys') {"""
if old_func_start in content and "lastRenderedJobId" not in content:
    content = content.replace(old_func_start, state_vars, 1)

# Enhance appendTerminalLog to parse existing timestamp if present
old_append_body = """      const timeStr = new Date().toLocaleTimeString();
      let colorClass = 'log-sys';
      if (type === 'ok') colorClass = 'log-ok';
      else if (type === 'warn') colorClass = 'log-warn';
      else if (type === 'err') colorClass = 'log-err';

      line.innerHTML = `<span class="log-time">[${timeStr}]</span><span class="${colorClass}">${escapeHtml(msg)}</span>`;"""

new_append_body = """      let timeStr = new Date().toLocaleTimeString();
      let cleanMsg = msg;
      const m = msg.match(/^\\[(\\d{2}:\\d{2}:\\d{2})\\]\\s*(.*)$/);
      if (m) {
        timeStr = m[1];
        cleanMsg = m[2];
      }
      let colorClass = 'log-sys';
      if (type === 'ok') colorClass = 'log-ok';
      else if (type === 'warn') colorClass = 'log-warn';
      else if (type === 'err') colorClass = 'log-err';

      line.innerHTML = `<span class="log-time">[${timeStr}]</span><span class="${colorClass}">${escapeHtml(cleanMsg)}</span>`;"""

if old_append_body in content:
    content = content.replace(old_append_body, new_append_body, 1)

# Now replace the commented log render in checkActiveRegisterJob
old_render = """        // 渲染新日志
        if (Array.isArray(data.recent_logs)) {
          // 这里可以增量渲染日志
        }"""

new_render = """        // 增量渲染终端日志
        if (Array.isArray(data.recent_logs)) {
          if (data.job_id && data.job_id !== lastRenderedJobId) {
            lastRenderedJobId = data.job_id;
            lastRenderedLogCount = 0;
          }
          if (data.recent_logs.length > lastRenderedLogCount) {
            const newLogs = data.recent_logs.slice(lastRenderedLogCount);
            for (const logItem of newLogs) {
              const str = String(logItem);
              let type = 'sys';
              if (/\\[ERROR\\]|\\[ERR\\]|失败|Error|Exception/i.test(str)) {
                type = 'err';
              } else if (/\\[SUCCESS\\]|\\[OK\\]|成功/i.test(str)) {
                type = 'ok';
              } else if (/\\[WARN\\]|\\[WARNING\\]|警告|摩擦|退避/i.test(str)) {
                type = 'warn';
              }
              appendTerminalLog(str, type);
            }
            lastRenderedLogCount = data.recent_logs.length;
          }
        }"""

if old_render in content:
    content = content.replace(old_render, new_render, 1)

path.write_text(content, encoding="utf-8")
print("Successfully patched dashboard.html with real-time incremental log rendering!")
