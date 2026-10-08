# OmniRoute 容器重建记录（2026-10-08）

## 改动

新增环境变量 `OMNIROUTE_DIRECT_HEADERS_TIMEOUT_MS=120000`（默认 30000）。
该变量是 OmniRoute 网关对**上游响应启动（TTFT）的超时**，源码位置：
`open-sse/utils/directResponseStartTimeout.ts`（`resolveDirectHeadersTimeoutMs()` 读取，
`DEFAULT_DIRECT_HEADERS_TIMEOUT_MS = 30_000`，设 `0` 或负数 = 禁用）。

背景：图片生成 2048×2048 档约 56s，原 30s 会触发
`Direct response did not start within 30000ms — retrying on a fresh socket` → 502。

## 重建前容器配置（docker inspect，2026-10-08）

- ENV: `API_PORT=20129` `OMNIROUTE_BASE_PATH=` `REQUIRE_API_KEY=false` `SETUP_COMPLETE=true`
  `DATA_DIR=/app/data` `PORT=20128` `DASHBOARD_PORT=20128` `OMNIROUTE_MEMORY_MB=1024`
  `NODE_OPTIONS=--max-old-space-size=1024` `OMNIROUTE_MIGRATIONS_DIR=/app/migrations`
- PORTS: `20128/tcp->20128`，`20129/tcp->20129`
- MOUNTS: `C:\Users\jinnn\AppData\Roaming\omniroute -> /app/data`
- IMAGE: `jinnnyang/omniroute:latest`
- RESTART: `unless-stopped`
- NETWORK: `bridge`

## 重建命令（本次执行 / 日后恢复）

```powershell
docker rm -f omniroute
docker run -d --name omniroute --restart unless-stopped `
  -p 20128:20128 -p 20129:20129 `
  -v "C:\Users\jinnn\AppData\Roaming\omniroute:/app/data" `
  -e PORT=20128 -e API_PORT=20129 -e DASHBOARD_PORT=20128 `
  -e REQUIRE_API_KEY=false -e SETUP_COMPLETE=true -e OMNIROUTE_MEMORY_MB=1024 `
  -e OMNIROUTE_DIRECT_HEADERS_TIMEOUT_MS=120000 `
  jinnnyang/omniroute:latest
```

注：`DATA_DIR`、`NODE_OPTIONS`、`NODE_VERSION`、`PATH`、`HOSTNAME`、`OMNIROUTE_MIGRATIONS_DIR`
为镜像内默认 env，未在 run 命令显式传入时沿用镜像默认值。
