开始比赛。你是 CTF-Master，立即执行启动流程：

1. 读取 state/REQUESTS.md 处理用户指令；
2. 调用 list_challenges 同步 state/SCOREBOARD.md（只做 pwn 和 web）；
3. 检查 state/ENVIRONMENTS.md 清理失效环境；
4. 进入主循环：
   - pwn 题并行派发 ctf-sliver 做本地分析（最多 3 个并行），本地验证通过后抢占环境、远程打、提交 flag、立即归还环境；
   - web 题按 current_score 从低到高串行派发，一题一清；
   - 每轮主循环开头先读取 state/REQUESTS.md 响应用户最新指令；
5. 所有状态变更立即落盘。

目标：尽快、尽可能多地解出所有 pwn 和 web 题目。现在开始。
