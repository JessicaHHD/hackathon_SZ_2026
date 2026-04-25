# Storybook AI - Skills 参考文档

## Skill 1: extract_and_lock_visuals
将用户描述转化为稳定的视觉锚点（Visual Anchors）。

**输入**: 用户对孩子的原始描述
**输出**: 结构化英文标签，如 `a 5-year-old Asian boy, short hair, round face, wearing a yellow hoodie`

**调用时机**: 用户提交事件后、生成故事前

---

## Skill 2: content_security_auditor
对输入内容进行安全审查，过滤不适宜儿童的内容。

**输入**: 用户输入的事件文本
**输出**: `safe` / `unsafe`
**unsafe 处理**: 前端显示"这个故事可能不适合小宝宝，我们换一个神奇的冒险吧"

---

## Skill 3: get_art_style_prompt
将简单画风名称映射为专业图像生成提示词。

| style_name     | 提示词后缀 |
|----------------|-----------|
| watercolor     | soft watercolor illustration, pastel colors, children's book style |
| 3d_clay        | 3d claymation style, cute, smooth, octane render, soft studio lighting |
| crayon_doodle  | crayon drawing style, colorful, hand-drawn, childlike |
| ghibli         | Studio Ghibli style, warm, detailed, magical |

---

## Skill 4: rewrite_page
图片生成失败（违规）时，重新设计整页图像提示词。

**触发条件**: 图片 API 返回 `status: failed`
**策略**:
- 第1次失败：调用 `rewrite_page`，让 LLM 从头重新设计安全的图像提示词
- 后续失败：调用 `rewrite_prompt`，只做表面改写
- 最多重试 5 次，全部失败返回 `/placeholder.svg`

---

## Skill 5: import_custom_book
导入本地绘本，支持上传图片+文字+互动选项。

**接口**: `POST /api/import/custom`（multipart/form-data）
**字段**:
- `title`: 绘本标题
- `pages_json`: 页面数组 JSON，每页含 `text`、`interaction_question`、`interaction_options`
- `images`: 图片文件列表（顺序：封面、内页...、封底）

---

## JSON Schema 输出结构

```json
{
  "book_metadata": {
    "title": "string",
    "ui_theme": "soft_blue|warm_yellow|nature_green|dreamy_purple",
    "visual_anchors": "string (英文视觉特征)",
    "child_name": "string (主角名字)"
  },
  "pages": [
    {
      "page_num": 1,
      "text": "故事文本 30-50字",
      "tts_cue": "配音情感提示",
      "image_prompt": "中文图像提示词（含 visual_anchors）--v 6.0, flat illustration...",
      "interaction": null
    }
  ]
}
```

第3、4页 `interaction` 格式：
```json
{
  "question": "引导问题",
  "options": [
    { "label": "选项文字", "plot_pivot": "剧情走向" }
  ]
}
```
