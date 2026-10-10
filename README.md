# OmniRoute Hermes Plugin

让 [Hermes Agent](https://github.com/NousResearch/hermes-agent)（moirai 定制底座）支持 **OmniRoute** 聚合 API 的模型、图片生成、网络搜索全功能。

OmniRoute 是自建 AI 聚合网关（aptapi.dev 核心应用），聚合火山引擎（Agent Plan / Coding Plan / Ark）、OpenCode Go 等上游，按 combo 路由 + 多策略负载分发。本插件把 OmniRoute 的 OpenAI 兼容面（`/v1/*`）注册为 Hermes 的一等 provider。

## 能力矩阵（2026-10-07 本机实测）

| 能力 | 端点 | 状态 | 说明 |
|---|---|---|---|
| LLM 对话 | `POST /v1/chat/completions` | ✅ 可用 | 任意 model 字段透传（如 `volcengine-agent/glm-5.3-flash`） |
| Codex/Responses | `POST /v1/responses` | ✅ 可用 | 火山 coding plan 官方推荐协议 |
| 图片生成 | `POST /v1/images/generations` | ✅ 可用 | 默认 **`doubao-seedream-5.0-pro`**（裸名）；size 用 1024 档（实测 1024×1024≈17s；2048×2048≈56s 会触发网关 30s 内部超时→502；最低 921600 像素）。返回火山 TOS URL，插件自动下载缓存 |
| 网络搜索 | `POST /v1/search` | ✅ 可用 | 当前 upstream: `duckduckgo-free`，keyless |
| 视频生成 | `POST /v1/videos/generations` | ⏳ 预留 | seedance 系列未在 OmniRoute 注册 provider，待 dashboard 配置后启用 |
| Embedding | `POST /v1/embeddings` | ⏳ 预留 | doubao/bge/openai 均未配好凭据，待配置 |
| TTS / STT | `POST /v1/audio/*` | ⏳ 预留 | 未配置凭据，待配置 |

## 安装

```bash
# 方式一：脚本安装（推荐）
bash install.sh --profile /path/to/hermes-profile --no-model --no-image --no-web-search

# 方式二：手动复制
cp -r plugins/ /path/to/hermes-profile/plugins/
```

OmniRoute 是 **keyless 网关**（任意 Bearer 放行、无 key 才 403），一般无需 API key；但 hermes 凭证系统要求非空 key，故 profile `.env` 写入占位值即可：

```bash
OMNIROUTE_API_KEY=local        # keyless 占位，任意值
OMNIROUTE_BASE_URL=http://localhost:20128/v1   # 默认值；本机容器实际 API 端口 20128
```

## 配置

以本机 moirai profile 为例（`C:\Users\jinnn\AppData\Local\hermes`）：

```yaml
# config.yaml
custom_providers:
  omniroute:
    base_url: http://localhost:20128/v1
    api_mode: codex_responses
web:
  search_backend: omniroute
image_gen:
  provider: omniroute
  model: doubao-seedream-5.0-pro
```

模型选择：`hermes model set omniroute/volcengine-agent/glm-5.3-flash`（或任一 combo/模型 id）。

## 插件结构

```
plugins/
├── _omniroute_common/config.py      # 共享配置：base_url/key 解析（env + 默认值）
├── model-providers/omniroute/       # LLM provider（codex_responses 默认；fetch_models 尝试+兜底）
├── image_gen/omniroute/             # 图片生成（doubao-seedream-5.0-pro，同步 ~25s）
└── web/omniroute/                   # 网络搜索（/v1/search → web results）
```

`video_gen/`、`tts/`、`transcription/` 骨架待 OmniRoute 侧注册对应 provider 后补充（见路线图）。

## 更新机制（自更新）

插件在**加载时**自检并自动更新（不跟随 hermes 主程序更新节奏），逻辑在本仓库内：

- **TTL 限频**：默认每 24h 检查一次，不频繁访问网络
- **best-effort**：网络失败、git 缺失、文件占用等一律只打 stderr 提示，**绝不阻断插件加载**
- **并发安全**：跨进程文件锁（CLI 与 Desktop 同时启动不冲突）
- **生效时机**：本次进程仍用旧代码，替换在**下次启动**生效

环境变量：

| 变量 | 说明 |
|---|---|
| `OMNIROUTE_SELF_UPDATE_URL` | 插件仓库 URL（默认 `jinnnyang/omniroute-hermes-plugin`） |
| `OMNIROUTE_SELF_UPDATE_TTL` | 检查间隔秒数（默认 `86400`；`0` = 每次加载都检查，`-1` = 禁用） |
| `OMNIROUTE_SELF_UPDATE_OFF` | `1`/`true`/`yes` 禁用自更新 |
| `OMNIROUTE_GIT` | git 可执行文件路径（默认取 PATH 上的 `git`） |

## 路线图

1. **第一版（当前）**：LLM + 图片生成 + 网络搜索三条实测链路
2. **第二版**：视频生成（seedance）——待 OmniRoute dashboard 注册 video provider
3. **第三版**：embedding / rerank（doubao-bge 系）、TTS、STT——待 OmniRoute 配好凭据

## 维护说明

- 开发在 `C:\Users\jinnn\Documents\omniroute-hermes-plugin`（独立仓库，照 volcengine-hermes-plugin 模式）
- hermes-agent fork（jinnnyang）的安装脚本通过 `plugins` stage 从本仓库部署到 profile；此后由本插件的自更新机制接管增量更新
- 本仓库所有"✅ 可用"能力均有 2026-10-07 端点实测记录（详见上方能力矩阵与各文件 docstring）
