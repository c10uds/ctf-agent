# AIxCTF 自动解题系统一体化镜像
# 基座 ubuntu:24.04，容器启动后自动运行 CTF-Master 开始比赛

FROM ubuntu:24.04

# ---- apt 源切换为华为镜像（APT_MIRROR 置空可恢复官方源）----
ARG APT_MIRROR=mirrors.huaweicloud.com
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|http://archive.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://${APT_MIRROR}/ubuntu|g" \
        /etc/apt/sources.list.d/ubuntu.sources; \
    fi

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TERM=xterm-256color \
    JAVA_HOME=/opt/corretto \
    GHIDRA_INSTALL_DIR=/opt/ghidra \
    CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1 \
    PATH="/opt/corretto/bin:/opt/ctf-venv/bin:/root/.local/bin:$PATH"

# ---- 系统依赖 + CTF 常用工具 ----
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget git unzip zip xz-utils jq \
      file binutils socat netcat-openbsd \
      gdb gdb-multiarch gdbserver strace ltrace patchelf elfutils \
      qemu-user-static \
      sqlmap gobuster php-cli php-curl php-mbstring php-xml \
      nmap dnsutils p7zip-full \
      python3 python3-pip python3-venv \
      ruby ruby-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---- Amazon Corretto 21 JDK（Ubuntu 源 openjdk 的 build 元数据会让 Ghidra LaunchSupport 误判版本，勿用）----
ARG CORRETTO_URL=https://corretto.aws/downloads/latest/amazon-corretto-21-x64-linux-jdk.tar.gz
RUN wget -q "$CORRETTO_URL" -O /tmp/corretto.tgz \
    && mkdir -p /opt/corretto \
    && tar xzf /tmp/corretto.tgz -C /opt/corretto --strip-components=1 \
    && rm /tmp/corretto.tgz

# ---- Node.js 22 LTS ----
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- Google Chrome（chrome-devtools-mcp 用）----
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb \
    && apt-get update && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb && rm -rf /var/lib/apt/lists/*

# ---- opencode + chrome-devtools-mcp（构建期装好，运行期零下载）----
RUN npm i -g opencode-ai@1.19.2 chrome-devtools-mcp \
    && npm cache clean --force

# ---- uv + pyghidra-mcp（ghidra MCP，headless；固定用系统 python，避免下载托管解释器）----
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
RUN uv tool install --python /usr/bin/python3 pyghidra-mcp && pyghidra-mcp --help >/dev/null

# ---- Python pwn 工具链（venv 已前置到 PATH，exploit 直接用 python3 跑）----
# 含 pyghidra：归档脚本 tools/ghidra_export.py 用它打开 Ghidra 工程逐函数导出
RUN python3 -m venv /opt/ctf-venv \
    && /opt/ctf-venv/bin/pip install --no-cache-dir \
       pwntools checksec.py ROPgadget ropper requests websocket-client pyghidra==3.1.0 \
       pyjwt httpx beautifulsoup4 lxml

# ---- 反序列化 / JWT 辅助工具（构建期联网拉取，失败不阻塞；运行期也可临时补装）----
RUN git clone --depth 1 https://github.com/ambionics/phpggc /opt/phpggc 2>/dev/null || true; \
    git clone --depth 1 https://github.com/ticarpi/jwt_tool /opt/jwt_tool 2>/dev/null || true; \
    curl -sSL -o /opt/ysoserial.jar \
      https://github.com/frohoff/ysoserial/releases/download/v0.0.6/ysoserial-all.jar 2>/dev/null || true; \
    echo "phpggc: $(ls /opt/phpggc 2>/dev/null | wc -l) files; jwt_tool: $(ls /opt/jwt_tool 2>/dev/null | wc -l) files; ysoserial: $(stat -c%s /opt/ysoserial.jar 2>/dev/null || echo 0) bytes"

# ---- Ruby pwn 工具（GEM_SOURCE 可在 rubygems.org 不可达时指定镜像）----
ARG GEM_SOURCE=""
RUN if [ -n "$GEM_SOURCE" ]; then \
      gem install --no-document --clear-sources --source "$GEM_SOURCE" one_gadget seccomp-tools; \
    else \
      gem install --no-document one_gadget seccomp-tools; \
    fi

# ---- Ghidra（带 sha256 校验；GHIDRA_PROXY 可在 GitHub 不可达时指定代理前缀）----
ARG GHIDRA_VERSION=12.1.4
ARG GHIDRA_DATE=20260921
ARG GHIDRA_SHA256=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db
ARG GHIDRA_PROXY=""
RUN wget -q "${GHIDRA_PROXY}https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_DATE}.zip" -O /tmp/ghidra.zip \
    && echo "${GHIDRA_SHA256}  /tmp/ghidra.zip" | sha256sum -c - \
    && unzip -q /tmp/ghidra.zip -d /opt \
    && mv "/opt/ghidra_${GHIDRA_VERSION}_PUBLIC" /opt/ghidra \
    && rm /tmp/ghidra.zip

# ---- 应用文件（注意：docker/opencode.json 覆盖为 Linux 版配置）----
WORKDIR /app
COPY AGENTS.md README.md ./
COPY prompts/ prompts/
COPY tools/ tools/
COPY docker/gdbinit /etc/gdb/gdbinit
COPY docker/gdbinit /root/.gdbinit
COPY state/ state/
COPY docker/opencode.json opencode.json
COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/llm-forwarder.py /app/docker/llm-forwarder.py
COPY ctf.config.json /app/ctf.config.json
RUN chmod +x /entrypoint.sh tools/archive_challenge.sh

# 容器启动 = 自动开始比赛
ENTRYPOINT ["/entrypoint.sh"]
