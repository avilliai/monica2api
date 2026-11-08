# Monica 注册器

运行：

~~~powershell
python -m register.monica_register
~~~

默认流程：

注册默认读取项目根目录的 `Webshare 10 proxies.txt`，支持每行
`IP:PORT:USERNAME:PASSWORD`、`HOST:PORT` 或 HTTP/HTTPS 代理 URL。
网页后台和命令行共用代理池；每个正在注册的线程独占一个代理，完成、失败或取消后释放。
并发数超过代理数量时，多余线程等待空闲代理，不会共享代理或回退直连。
代理按轮询顺序复用，同一线程的后续账号可能分配到新的代理。
仅注册浏览器及会话校验使用代理，邮箱服务保持原有连接方式。
可通过 `REGISTER_PROXY_FILE` 指定其他文件，设为空字符串可关闭。
默认文件不存在时保持原有直连行为；指定的其他文件不存在、文件为空或格式错误时会报错。
文件内容在进程内缓存，更新后请重启服务。代理凭据不会写入注册日志。

1. 创建临时邮箱
2. 打开 Monica 注册页
3. 点击“使用电子邮件注册”或 “Sign up with email”
4. 依次填写邮箱、账号/昵称、密码
5. 提交后等待可见 reCAPTCHA
6. 自动读取邮件 OTP
7. 填入验证码并验证
8. 校验 /api/user/me，提取 Monica Cookie

注册后端由 REGISTER_BROWSER_BACKEND 控制：

- camoufox
- playwright
- auto
- http

http 模式使用 app.services.monica_auth.MonicaAuthClient，依次调用：

- /api/user/list_email_registered_v2
- /api/user/send_email_verify_code_with_captcha
- /api/user/register_by_email

该模式读取 MONICA_CAPTCHA_TOKEN 或 MONICA_CAPTCHA_TOKEN_FILE。成功账号写入 register/monica_accounts.json，并由服务层自动合并至 data/cookies.json。
