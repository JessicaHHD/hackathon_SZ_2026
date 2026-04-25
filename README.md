# 故事魔法师 · StoryBook MVP

AI 驱动的儿童互动绘本生成器。输入今天发生的小事，AI 自动生成专属绘本故事、配图，支持分支互动选择。

---

## 快速启动

```bash
cd backend
uv run uvicorn main:app --reload --port 8001
```

浏览器访问 `http://localhost:8001`（或双击 `start.bat`）

### API Keys（`backend/.env`）

```env
OPENAI_API_KEY=...   # 文字生成，模型 gpt-5.4，代理 https://aiapi.orbitai.global/v1
IMAGE_API_KEY=...    # 图片生成，模型 gpt-image-2，代理 https://api.apimart.ai/v1
CHAT_API_KEY=...     # 角色聊天，模型 claude-sonnet-4-6，代理 https://api.aabao.top/v1
CHAT_API_URL=...     # 角色聊天 API 地址
```

---

## 功能概览

| 模块 | 说明 |
|---|---|
| 角色库 | 创建/选择绘本主角，持久化到 localStorage |
| 故事生成 | 输入事件 → AI 生成 3/5/7 页故事（含分支剧情） |
| 插图生成 | 后台并行生成，前端每 5s 轮询；违规提示词自动重写重试（最多5次），失败兜底占位图 |
| 绘本阅读器 | turn.js 翻页动画，封面眼睛跟随鼠标，分支选项交互 |
| 分支续写 | 选择剧情分支后 AI 自动续写 2 页 |
| 角色聊天 | 与绘本主人公对话（Claude claude-sonnet-4-6） |
| 历史记录 | 已生成绘本持久化到磁盘 JSON，重启后可恢复 |
| 导入本地绘本 | 上传图片+文字+互动选项，生成自定义绘本 |
| 导入示例绘本 | 一键导入《小熊不怕打雷了》 |

**画风：** `watercolor`（水彩）/ `3d_clay`（3D黏土）/ `crayon_doodle`（蜡笔涂鸦）/ `ghibli`（吉卜力）

---

## API

### `POST /api/generate`

```json
{
  "event": "今天宝宝第一次自己刷牙",
  "child_name": "小宝",
  "child_age": 5,
  "art_style": "watercolor",
  "page_count": 5
}
```

立即返回故事 JSON（`image_url` 初始为空），图片后台并行生成。

### `GET /api/images/{story_id}`

轮询图片进度，返回当前已完成的 URL 列表。

### `POST /api/regenerate/{story_id}/{page_idx}`

重新生成指定页图片（自动重写违规提示词）。

### `POST /api/branch`

基于剧情分支续写 2 页。

### `POST /api/chat`

与绘本主人公角色扮演对话。

### `POST /api/import/custom`

上传本地绘本（multipart：title + pages_json + images）。

### `GET /api/stories` / `GET /api/stories/{story_id}` / `DELETE /api/stories/{story_id}`

历史绘本管理。

---

## 项目结构

```
storybook-mvp/
├── backend/
│   ├── main.py          # FastAPI：故事生成 + 图片生成 + 静态文件
│   ├── pyproject.toml   # uv 依赖管理
│   └── .env             # API Keys（勿提交）
└── frontend/
    ├── index.html       # Vue 3 单页应用（无构建步骤）
    ├── 书皮.png          # 封面素材
    └── generated/
        └── stories/     # 绘本 JSON 持久化
```

**技术栈：** FastAPI · uvicorn · openai · python-multipart · Vue 3 (CDN) · turn.js · dotLottie · canvas-confetti
