# Monica2API

针对 https://monica.im 的纯 HTTP 登录、Cookie 账号池、Dashboard 和 OpenAI Chat Completions 兼容层。

## 结论与架构

Monica 的 reCAPTCHA 出现在注册阶段：

1. 检查邮箱：/api/user/list_email_registered_v2
2. 浏览器完成 reCAPTCHA
3. 发送验证码：/api/user/send_email_verify_code_with_captcha
4. 邮箱 OTP 注册：/api/user/register_by_email

正常对话请求 /api/custom_bot/chat 只依赖已登录 Cookie 与 x-client-* 请求头。服务端对话、Cookie 探测、配额查询均使用 curl-cffi/httpx，运行 API 时不会启动浏览器。

Camoufox/Playwright 的职责集中在新账号注册；Cookie 失效时账号池会标记该账号，随后再执行注册或重新登录。

## 功能

- POST /v1/chat/completions：流式、非流式 OpenAI 兼容响应
- GET /v1/models
- 当前 Monica Web payload：bot_uid=monica、task_type=chat_with_custom_bot
- Cookie 连续使用与轮询机制：支持单账户连续使用 N 次（`.env` 中配置 `ACCOUNT_CONSECUTIVE_USES`）后再轮转，防止同 IP 摊大饼式频繁切换账户触发风控封禁
- 智能故障转移：账户达到批次次数、额度耗尽或异常时自动平滑切换到下一可用账户
- 完整 Dashboard：登录账号、手动添加 Cookie、启用/停用/删除、状态与额度查看
- 每个账号本地每日 40 次额度，按 Asia/Shanghai 零点自动重置
- 配额接口：GET /admin/cookies/{id}/quota
- Agent connection token：GET /admin/cookies/{id}/connection-token
- 可选的单账号与后台注册维护工具（浏览器依赖单独安装）
- Camoufox、Playwright、HTTP 三种注册后端
- Docker 部署和自动化测试

## 安装

~~~powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
~~~

以上是对话、登录、保活和 Dashboard 所需的轻量依赖，不包含浏览器。仅在维护可选注册工具时安装：

~~~powershell
pip install -r requirements-register.txt
python -m camoufox fetch
# 使用标准 Chromium 时：python -m playwright install chromium
~~~

### GOOGLE_SPEECH_API_KEY
过人机验证需要GOOGLE_SPEECH_API_KEY     
怎么获取问你自己的ai，获取后填入.env的对应配置项，否则无法过验证
## Cookie结构

data/cookies.json：

~~~json
[
  {
    "email": "user@example.com",
    "password": "Password1!",
    "cookie": "name=value; another=value",
    "disabled": false
  }
]
~~~

## 启动

~~~powershell
python main.py
~~~

dashboard默认地址：http://127.0.0.1:8000

~~~bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3-flash-preview","messages":[{"role":"user","content":"hi"}],"stream":false}'
~~~

## 注册
### dashboard
dashboard面板可操作注册

### CLI

~~~powershell
python -m register.monica_register
~~~

页面流程自动定位中英文控件：

- 使用电子邮件注册 / Sign up with email
- 邮箱
- 账号或昵称
- 密码
- 邮箱验证码
- 验证按钮

可见浏览器遇到 reCAPTCHA 后会保持窗口并等待完成，随后自动续接 OTP 和 Cookie 提取。

### API

~~~bash
curl -X POST http://127.0.0.1:8000/register/start \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"count":1,"concurrency":1,"backend":"camoufox","headless":false}'
~~~

任务查询：

~~~bash
curl http://127.0.0.1:8000/register/jobs/JOB_ID \
  -H "Authorization: Bearer change-me"
~~~

### 注册后端

- camoufox：注册默认方案，适合交互式 reCAPTCHA
- playwright：标准 Chromium
- auto：优先 Chromium，启动失败时切换 Camoufox
- http：已有短时 reCAPTCHA pass token 时，直接调用发送 OTP 与注册 JSON 接口

http 模式读取 MONICA_CAPTCHA_TOKEN 或 MONICA_CAPTCHA_TOKEN_FILE。Token 与浏览器会话、站点和时效绑定，项目不会把它写入账号文件。

## Dashboard 与账号管理

打开 `http://127.0.0.1:8000`，在页面输入 `.env` 的 `API_KEY`。API Key 仅保存在浏览器 localStorage。页面可以：

- 使用邮箱和密码调用 `/admin/accounts/login`，自动校验 Cookie 后加入池；
- 粘贴 Cookie Header 手动加入；
- 查看在线状态、今日已用/剩余次数和额度日期；
- 启用、停用、刷新、删除账号，或手动重置本地额度。

对话、保活、登录校验均走普通 HTTP；注册流程仍作为可选维护工具保留。

## 管理接口

- GET /admin/cookies
- POST /admin/cookies/reload
- POST /admin/cookies/refresh
- POST /admin/cookies/add
- POST /admin/accounts/login
- POST /admin/accounts/add
- POST /admin/accounts/reset-quotas
- POST /admin/cookies/{id}/refresh
- GET /admin/cookies/{id}/quota
- GET /admin/cookies/{id}/connection-token
- /admin/accounts/*：
- /admin/dashboard

## 测试

~~~powershell
python -m compileall -q app register
python -m unittest discover -s tests -v
~~~

## Docker

~~~bash
docker compose up -d --build
~~~

默认 Docker 镜像只安装 HTTP/API 依赖，不下载 Camoufox 或 Chromium；账号通过 Dashboard 登录或导入 Cookie。



