import json
import time
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, UploadFile, File, Form
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

# 过滤 Windows asyncio 连接重置噪音日志
import logging
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 托管前端静态文件
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
IMAGES_DIR = os.path.join(FRONTEND_DIR, "generated")
os.makedirs(IMAGES_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/generated", StaticFiles(directory=IMAGES_DIR), name="generated")

@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/bg.mp4")
def bg_video():
    return FileResponse(r"d:\文件\大学\大模型\黑客松\UI背景.mp4", media_type="video/mp4")

@app.get("/ref/{name}")
def ref_image(name: str):
    return FileResponse(rf"d:\文件\大学\大模型\黑客松\画风参考图\{name}")

@app.get("/%E4%B9%A6%E7%9A%AE.png")
def book_cover():
    return FileResponse(os.path.join(FRONTEND_DIR, "书皮.png"), media_type="image/png")

@app.get("/placeholder.svg")
def placeholder():
    return FileResponse(os.path.join(FRONTEND_DIR, "placeholder.svg"), media_type="image/svg+xml")

@app.get("/turn.min.js")
def turn_js():
    return FileResponse(r"d:\文件\大学\大模型\黑客松\turn.js-master\turn.min.js", media_type="application/javascript")

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://aiapi.orbitai.global/v1"
)

chat_client = OpenAI(
    api_key=os.getenv("CHAT_API_KEY"),
    base_url=os.getenv("CHAT_API_URL", "https://api.aabao.top/v1")
)

SYSTEM_PROMPT = """你是一个专为 3-8 岁儿童设计的"互动绘本导演引擎"。将家长提供的日常小事转化为充满童趣、逻辑连贯的绘本。

规则：
1. 输出严格的 JSON 格式，不要有任何额外文字
2. 在中间页（第2页和第3页，或第3页和第4页）必须包含 interaction 分支选项
3. 其余页的 interaction 字段设为 null
4. image_prompt 必须包含 visual_anchors 内容，结尾加：--v 6.0, flat illustration, vector art, high quality, soft lighting
5. 绝不出现暴力、惊悚或不适宜儿童的内容

输出 JSON 结构：
{
  "book_metadata": {
    "title": "绘本标题",
    "ui_theme": "warm_yellow",
    "visual_anchors": "主角英文视觉特征"
  },
  "pages": [
    {
      "page_num": 1,
      "text": "故事文本30-50字",
      "tts_cue": "欢快地",
      "image_prompt": "中文图像提示词",
      "interaction": null
    },
    {
      "page_num": 3,
      "text": "故事文本",
      "tts_cue": "好奇地",
      "image_prompt": "中文图像提示词",
      "interaction": {
        "question": "你觉得小宝应该怎么做？",
        "options": [
          {"label": "勇敢向前走", "plot_pivot": "小宝鼓起勇气迈出第一步"},
          {"label": "先深呼吸一下", "plot_pivot": "小宝深呼吸后感觉好多了"}
        ]
      }
    }
  ]
}"""

class StoryRequest(BaseModel):
    event: str
    child_name: str = "小宝"
    child_age: int = 5
    art_style: str = "watercolor"
    visual_anchors: str = ""
    style_ref_url: str = ""
    page_count: int = 5  # 3, 5, or 7

STYLE_MAP = {
    "watercolor": "soft watercolor illustration, pastel colors, children's book style",
    "3d_clay": "3d claymation style, cute, smooth, octane render, soft studio lighting",
    "crayon_doodle": "crayon drawing style, colorful, hand-drawn, childlike",
    "ghibli": "Studio Ghibli style, warm, detailed, magical"
}

image_store: dict = {}   # story_id -> [url, ...]
prompt_store: dict = {}  # story_id -> [prompt, ...]
story_store: dict = {}   # story_id -> story_json

STORIES_DIR = os.path.join(FRONTEND_DIR, "generated", "stories")
os.makedirs(STORIES_DIR, exist_ok=True)

def save_story_json(story_id: str):
    data = story_store.get(story_id)
    if not data:
        return
    data = dict(data)
    data["pages"] = [dict(p, image_url=image_store[story_id][i]) for i, p in enumerate(data["pages"])]
    with open(os.path.join(STORIES_DIR, f"{story_id}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.get("/api/stories")
def list_stories():
    stories = []
    for fname in sorted(os.listdir(STORIES_DIR), reverse=True):
        if fname.endswith(".json"):
            with open(os.path.join(STORIES_DIR, fname), encoding="utf-8") as f:
                d = json.load(f)
            stories.append({"story_id": d["story_id"], "title": d["book_metadata"]["title"]})
    return {"stories": stories}

@app.get("/api/stories/{story_id}")
def get_story(story_id: str):
    path = os.path.join(STORIES_DIR, f"{story_id}.json")
    if not os.path.exists(path):
        return {"error": "not found"}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

@app.delete("/api/stories/{story_id}")
def delete_story(story_id: str):
    path = os.path.join(STORIES_DIR, f"{story_id}.json")
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}

@app.get("/api/images/{story_id}")
def get_images(story_id: str):
    return {"images": image_store.get(story_id, [])}

THUNDER_BEAR_DIR = r"d:\文件\大学\大模型\黑客松\已有绘本\book\components\ThunderBearReader"

@app.get("/api/import/thunder_bear")
def import_thunder_bear():
    import shutil
    with open(os.path.join(THUNDER_BEAR_DIR, "data", "thunder_bear.json"), encoding="utf-8") as f:
        data = json.load(f)
    story_id = "thunder_bear"
    pages = []
    # 封面
    pages.append({"page_num":0,"type":"cover","text":data["meta"]["title"],"image_url":"","interaction":None})
    for p in data["pages"]:
        if p["type"] == "static":
            img_key = p["image_key"]
            src = os.path.join(THUNDER_BEAR_DIR, "assets", f"{img_key}.png")
            dst = os.path.join(IMAGES_DIR, f"tb_{img_key}.png")
            shutil.copy2(src, dst)
            pages.append({"page_num":p["page_num"],"type":"story","text":p["text"],
                          "image_url":f"/generated/tb_{img_key}.png","interaction":None})
        elif p["type"] == "interactive":
            off_key = p["interaction"]["states"]["off"]["image_key"]
            on_key  = p["interaction"]["states"]["on"]["image_key"]
            for k in [off_key, on_key]:
                src = os.path.join(THUNDER_BEAR_DIR, "assets", f"{k}.png")
                dst = os.path.join(IMAGES_DIR, f"tb_{k}.png")
                if os.path.exists(src): shutil.copy2(src, dst)
            pages.append({"page_num":p["page_num"],"type":"story",
                          "text":p["interaction"]["states"]["off"]["text"],
                          "image_url":f"/generated/tb_{off_key}.png",
                          "interaction":{
                              "question": p["interaction"]["states"]["off"].get("user_hint","点击互动"),
                              "options":[p["interaction"]["states"]["on"]["text"]],
                              "plot_pivot": p["interaction"]["states"]["on"]["text"]
                          }})
    pages.append({"page_num":99,"type":"back","text":"故事结束，下次见！","image_url":"","interaction":None})
    # 初始化 store，让 regenerate 接口可用
    image_store[story_id] = [p["image_url"] for p in pages]
    prompt_store[story_id] = [
        p.get("text", "") and f"{data['meta']['title']} 绘本封面，水彩风格" if p["type"]=="cover"
        else (f"{data['meta']['title']} 绘本封底，水彩风格" if p["type"]=="back" else p.get("text",""))
        for p in pages
    ]
    result = {"story_id": story_id, "book_metadata":{"title":data["meta"]["title"],"ui_theme":"warm_yellow"}, "pages": pages}
    story_store[story_id] = result
    save_story_json(story_id)
    return result

@app.post("/api/regenerate/{story_id}/{page_idx}")
def regenerate_image(story_id: str, page_idx: int):
    # 若内存中没有，尝试从磁盘恢复
    if story_id not in story_store:
        path = os.path.join(STORIES_DIR, f"{story_id}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            story_store[story_id] = data
            image_store[story_id] = [p.get("image_url", "") for p in data["pages"]]
            prompt_store[story_id] = [p.get("image_prompt", p.get("text", "")) for p in data["pages"]]
    prompts = prompt_store.get(story_id)
    if not prompts or page_idx >= len(prompts):
        return {"error": "not found"}
    image_store[story_id][page_idx] = ""
    def regen():
        url = generate_image(prompts[page_idx])
        image_store[story_id][page_idx] = url
        if story_id in story_store:
            story_store[story_id]["pages"][page_idx]["image_url"] = url
            save_story_json(story_id)
    import threading
    threading.Thread(target=regen, daemon=True).start()
    return {"status": "regenerating"}

IMAGE_BASE = "https://api.apimart.ai/v1"
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY")
IMAGE_HEADERS = {"Authorization": f"Bearer {IMAGE_API_KEY}", "Content-Type": "application/json"}

def rewrite_prompt(prompt: str) -> str:
    try:
        msg = client.chat.completions.create(model="gpt-5.4", max_tokens=200, messages=[
            {"role":"system","content":"你是儿童绘本图像提示词专家。将用户提供的提示词改写为安全、无违规内容的英文图像提示词，适合儿童绘本风格。只输出改写后的提示词，不要其他内容。"},
            {"role":"user","content":f"改写这个提示词：{prompt}"}
        ])
        return msg.choices[0].message.content.strip()
    except:
        return prompt

def rewrite_page(original_prompt: str) -> str:
    """让 LLM 重新生成整页内容，返回新的 image_prompt"""
    try:
        msg = client.chat.completions.create(model="gpt-5.4", max_tokens=300, messages=[
            {"role": "system", "content": "你是儿童绘本创作专家。原始图像提示词因违规被拒绝，请重新设计这一页的故事内容，输出一个安全、适合儿童的新图像提示词（英文），不含任何暴力、恐怖或不适宜内容。只输出新的图像提示词，不要其他内容。"},
            {"role": "user", "content": f"原始提示词：{original_prompt}\n请重新设计并输出新的安全图像提示词："}
        ])
        return msg.choices[0].message.content.strip()
    except:
        return rewrite_prompt(original_prompt)

def generate_image(prompt: str, style_ref_url: str = "", retries: int = 5) -> str:
    """提交任务 → 轮询 → 下载保存到本地 → 返回本地路径"""
    current_prompt = prompt
    for attempt in range(retries):
        try:
            payload = {"model": "gpt-image-2", "prompt": current_prompt, "size": "1:1", "resolution": "1k", "n": 1}
            if style_ref_url:
                payload["style_reference"] = style_ref_url
            res = http_requests.post(f"{IMAGE_BASE}/images/generations", headers=IMAGE_HEADERS,
                json=payload, timeout=30)
            task_id = res.json()["data"][0]["task_id"]

            time.sleep(15)
            for _ in range(21):
                r = http_requests.get(f"{IMAGE_BASE}/tasks/{task_id}", headers=IMAGE_HEADERS, timeout=10)
                result = r.json()["data"]
                if result["status"] == "completed":
                    remote_url = result["result"]["images"][0]["url"][0]
                    img_data = http_requests.get(remote_url, timeout=30).content
                    filename = f"{task_id}.jpg"
                    filepath = os.path.join(IMAGES_DIR, filename)
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    return f"/generated/{filename}"
                if result["status"] == "failed":
                    print(f"[generate_image] failed, rewriting page (attempt {attempt})")
                    # 第一次失败：重写整页；后续失败：只改写提示词
                    current_prompt = rewrite_page(current_prompt) if attempt == 0 else rewrite_prompt(current_prompt)
                    break
                time.sleep(5)
        except Exception as e:
            print(f"[generate_image] attempt {attempt} error: {e}")
        if attempt < retries - 1:
            time.sleep(3)
    return "/placeholder.svg"

@app.post("/api/generate")
async def generate_story(req: StoryRequest):
    style_desc = STYLE_MAP.get(req.art_style, STYLE_MAP["watercolor"])
    user_prompt = f"""
请为以下事件生成一本互动绘本：
- 事件：{req.event}
- 主角名字：{req.child_name}
- 主角年龄：{req.child_age}岁
- 画风：{style_desc}
- 页数：{req.page_count}页（在第{req.page_count//2}页和第{req.page_count//2+1}页设置分支选项）
{f"- 主角外貌（visual_anchors）：{req.visual_anchors}" if req.visual_anchors else ""}

请直接输出 JSON，pages 数组包含 {req.page_count} 个元素，不要有任何其他文字。
"""
    message = client.chat.completions.create(
        model="gpt-5.4",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
    )

    text = message.choices[0].message.content
    start = text.find("{")
    end = text.rfind("}") + 1
    story_json = json.loads(text[start:end])
    story_id = str(int(time.time()))
    title = story_json["book_metadata"]["title"]
    anchors = story_json["book_metadata"].get("visual_anchors", "")
    story_json["book_metadata"]["child_name"] = req.child_name

    # 封面和封底
    cover = {"page_num":0,"type":"cover","text":title,"tts_cue":"庄重地",
             "image_prompt":f"儿童绘本封面，标题《{title}》，{anchors}，温馨插画，精美装帧","image_url":"","interaction":None}
    back  = {"page_num":99,"type":"back","text":"故事结束，下次见！","tts_cue":"温柔地",
             "image_prompt":f"儿童绘本封底，简洁温馨，小星星装饰，{anchors}，柔和背景","image_url":"","interaction":None}

    for page in story_json["pages"]:
        page["image_url"] = ""
    story_json["pages"] = [cover] + story_json["pages"] + [back]
    story_json["story_id"] = story_id

    total = len(story_json["pages"])
    image_store[story_id] = [""] * total
    prompt_store[story_id] = [p["image_prompt"] for p in story_json["pages"]]
    story_store[story_id] = story_json
    save_story_json(story_id)

    def bg_generate(ref_url: str):
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(generate_image, p["image_prompt"], ref_url): i
                      for i, p in enumerate(story_json["pages"])}
            for f, i in futures.items():
                url = f.result()
                image_store[story_id][i] = url
                if story_id in story_store:
                    story_store[story_id]["pages"][i]["image_url"] = url
                save_story_json(story_id)
    def bg_with_char():
        # 先生成角色形象参考图
        char_ref_url = ""
        if req.visual_anchors:
            char_prompt = f"儿童绘本角色设计，{req.visual_anchors}，全身正面，白色背景，水彩插画风格"
            char_ref_url = generate_image(char_prompt)
            if char_ref_url and story_id in story_store:
                story_store[story_id]["char_ref_url"] = char_ref_url
        bg_generate(char_ref_url or req.style_ref_url)

    import threading
    threading.Thread(target=bg_with_char, daemon=True).start()

    return story_json


class BranchRequest(BaseModel):
    story_id: str
    plot_pivot: str
    visual_anchors: str = ""
    art_style: str = "watercolor"

@app.post("/api/branch")
async def branch_story(req: BranchRequest):
    style_desc = STYLE_MAP.get(req.art_style, STYLE_MAP["watercolor"])
    prompt = f"""基于以下剧情转折，生成2页后续故事内容（JSON格式）：
剧情转折：{req.plot_pivot}
画风：{style_desc}
{f"主角外貌：{req.visual_anchors}" if req.visual_anchors else ""}

输出JSON：
{{"pages":[{{"page_num":1,"text":"故事文本30-50字","tts_cue":"情绪词","image_prompt":"中文图像提示词","interaction":null}},{{"page_num":2,"text":"故事文本","tts_cue":"情绪词","image_prompt":"中文图像提示词","interaction":null}}]}}
只输出JSON，不要其他文字。"""
    msg = client.chat.completions.create(
        model="gpt-5.4", max_tokens=1000,
        messages=[{"role":"user","content":prompt}]
    )
    text = msg.choices[0].message.content
    new_pages = json.loads(text[text.find("{"):text.rfind("}")+1])["pages"]
    for p in new_pages:
        p["image_url"] = ""

    # 追加到 story
    if req.story_id in image_store:
        base = len(image_store[req.story_id]) - 1  # 封底前插入
        for p in new_pages:
            image_store[req.story_id].insert(base, "")
            prompt_store[req.story_id].insert(base, p["image_prompt"])
            if req.story_id in story_store:
                story_store[req.story_id]["pages"].insert(base, p)
            base += 1
        def bg():
            for i, p in enumerate(new_pages):
                idx = len(image_store[req.story_id]) - 1 - len(new_pages) + i
                url = generate_image(p["image_prompt"])
                image_store[req.story_id][idx] = url
                if req.story_id in story_store:
                    story_store[req.story_id]["pages"][idx]["image_url"] = url
                save_story_json(req.story_id)
        import threading
        threading.Thread(target=bg, daemon=True).start()

    return {"pages": new_pages}


class ChatRequest(BaseModel):
    story_id: str
    character_name: str
    message: str
    history: list = []

@app.post("/api/chat")
async def chat_with_character(req: ChatRequest):
    story = story_store.get(req.story_id, {})
    title = story.get("book_metadata", {}).get("title", "这本绘本")
    anchors = story.get("book_metadata", {}).get("visual_anchors", "")
    system = f"""你是绘本《{title}》里的主人公{req.character_name}。{f"你的外貌：{anchors}。" if anchors else ""}
用3-8岁小朋友能理解的语言回答，活泼可爱，每次回复不超过50字。"""
    messages = [{"role":"system","content":system}]
    for h in req.history[-6:]:
        if h.get("role") in ("user","assistant") and h.get("content"):
            messages.append({"role":h["role"],"content":str(h["content"])})
    messages.append({"role":"user","content":req.message})
    msg = chat_client.chat.completions.create(model="claude-sonnet-4-6", max_tokens=150, messages=messages)
    return {"reply": msg.choices[0].message.content}


@app.post("/api/import/custom")
async def import_custom(
    title: str = Form(...),
    pages_json: str = Form(...),
    images: List[UploadFile] = File(default=[])
):
    """
    pages_json: JSON array of {text, interaction_question, interaction_options}
    images: uploaded files in order (index 0=cover, 1..N=pages, last=back)
    """
    story_id = f"custom_{int(time.time())}"
    pages_data = json.loads(pages_json)

    # save uploaded images
    saved_urls = []
    for i, f in enumerate(images):
        ext = os.path.splitext(f.filename)[1] or ".jpg"
        filename = f"{story_id}_p{i}{ext}"
        filepath = os.path.join(IMAGES_DIR, filename)
        with open(filepath, "wb") as out:
            out.write(await f.read())
        saved_urls.append(f"/generated/{filename}")

    # build pages
    pages = []
    # cover
    cover_url = saved_urls[0] if saved_urls else ""
    pages.append({"page_num": 0, "type": "cover", "text": title,
                  "image_url": cover_url, "image_prompt": f"{title} 绘本封面", "interaction": None})

    for i, pd in enumerate(pages_data):
        img_url = saved_urls[i + 1] if i + 1 < len(saved_urls) else ""
        interaction = None
        if pd.get("interaction_question") and pd.get("interaction_options"):
            opts = [o.strip() for o in pd["interaction_options"].split("\n") if o.strip()]
            interaction = {
                "question": pd["interaction_question"],
                "options": [{"label": o, "plot_pivot": o} for o in opts]
            }
        pages.append({"page_num": i + 1, "type": "story", "text": pd.get("text", ""),
                      "image_url": img_url, "image_prompt": pd.get("text", ""), "interaction": interaction})

    # back
    back_url = saved_urls[-1] if len(saved_urls) > len(pages_data) + 1 else ""
    pages.append({"page_num": 99, "type": "back", "text": "故事结束，下次见！",
                  "image_url": back_url, "image_prompt": f"{title} 绘本封底", "interaction": None})

    result = {"story_id": story_id, "book_metadata": {"title": title, "ui_theme": "warm_yellow"}, "pages": pages}
    image_store[story_id] = [p["image_url"] for p in pages]
    prompt_store[story_id] = [p["image_prompt"] for p in pages]
    story_store[story_id] = result
    save_story_json(story_id)
    return result
