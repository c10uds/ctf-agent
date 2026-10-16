开始比赛。你是 CTF-Master，立即执行启动流程：

1. 读取 state/REQUESTS.md 处理用户指令；
2. 调用 list_challenges 同步 state/SCOREBOARD.md（只做 pwn 和 web）；
3. 扫 state/env-requests/ 处理存量环境申请；检查各 work/<id>/worker.pid 清理孤儿进程；
4. 检查 state/ENVIRONMENTS.md 清理失效环境；
5. 进入工作循环：
   - pwn 题并行派发 ctf-worker 进程做本地分析（最多 3 个并行），LOCAL_READY 后按环境仲裁协议分配环境、worker 远程打并自行提交 flag、你负责记账与归还环境；
   - web 题按 current_score 从低到高串行派发 worker，一题一清；
   - 每做一两个动作就检查一次 state/env-requests/ 和 state/REQUESTS.md；
6. 所有状态变更立即落盘。

目标：尽快、尽可能多地解出所有 pwn 和 web 题目。现在开始。
