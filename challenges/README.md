# 本地评测题（自测用）

用于端到端验证 AIxCTF 解题系统：4 道中等偏上难度的题（2 pwn + 2 web），配一个本地
「假平台」（`platform/fake_platform.py`，实现 aixctf-challenge MCP 的六个工具 + 附件下载 + 环境拉起）。

- `pwn/fmtstr/` —— 格式化字符串泄露（canary / PIE / libc）+ 栈溢出 ret2libc
- `pwn/noteheap/` —— 堆 UAF：unsorted bin 泄 libc → tcache poisoning → `free@got` 改 `system`
- `web/sqli/` —— 登录处 SQL 注入（password 先 MD5，只能从 username 注入；需带平台下发的请求头）
- `web/ssti/` —— Jinja2 模板注入（SSTI）RCE（`name` 过滤 `__`，用 `request.args` 绕）

## 准备

```bash
bash challenges/setup.sh          # 编译 pwn（需 Linux gcc）+ 装平台依赖
```

## 跑一轮完整评测

```bash
# 1) 本地网关 + 观测面板（同时是容器要连的隧道服务端），upstream 指向你的模型
python gateway/gateway.py --token test123 --upstream https://api.commandcode.ai/provider/v1 \
       --key $CMD_KEY --model deepseek/deepseek-v4.1-flash

# 2) 本地假平台
python challenges/platform/fake_platform.py --port 8080

# 3) ctf.config.json 指向它们（已被 .gitignore 排除），然后跑容器
docker build -t ctf-agent .
docker run --rm -v $PWD/state:/app/state -v $PWD/work:/app/work ctf-agent
```

平台日志会打印每次 `start_challenge` / `submit_flag` 的结果；`check_status` 可用
`mcp` 客户端调 `list_challenges` 查看每题 `solved`。

## 说明

- pwn 的 `dist/libc.so.6`、`dist/ld-linux-x86-64.so.2` 由 `setup.sh` 从构建机拷贝（未入库），
  solver 需要它们算偏移；两道题的参考解 `solve.py` 用于验证可解性，不参与 agent 评测。
- 假平台默认关掉 MCP SDK 的 DNS-rebinding 防护（容器通过 `host.docker.internal` 访问会被
  默认策略以 421 拒绝）。
