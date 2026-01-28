import os
import re
import json
import hashlib
from datetime import datetime

import requests
import feedparser

# ========== 1) 飞书 Webhook ==========
WEBHOOK = os.environ["FEISHU_WEBHOOK"]

# ========== 2) RSS 源 ==========
# 说明：
# - 网站 RSS：稳定
# - 公众号 RSS：通过 RSSHub 的 /wechat/sogou/:id 转换（可能需自建 RSSHub 才稳定）:contentReference[oaicite:4]{index=4}
#
# 你需要把下面这些 <MP_ID_...> 改成你在搜狗微信上找到的公众号 id
RSS_LIST = [
    # ---- 中文网站（科技 + 融资 + 大事）----
    "https://36kr.com/feed",
    "https://www.ithome.com/rss/",
    "https://www.jiqizhixin.com/rss",
    "https://www.qbitai.com/feed",

    # ---- 出海/全球 AI（可选，但非常建议）----
    "http://feeds.venturebeat.com/VentureBeat",   # VentureBeat RSS（AI/企业科技/投融资）
    "https://huggingface.co/blog/feed.xml",       # Hugging Face Blog（模型/生态关键更新）

    # ---- 中文公众号（把下面 MP_ID_* 换成你查到的 id）----
    # RSSHub 微信 Sogou 路由：/wechat/sogou/:id :contentReference[oaicite:5]{index=5}
    # 示例（请你替换成真实 id）：
    "https://rsshub.app/wechat/sogou/MP_ID_QBITAI",        # 量子位 公众号（示例占位）
    "https://rsshub.app/wechat/sogou/MP_ID_JIQIZHIXIN",    # 机器之心 公众号（示例占位）
    "https://rsshub.app/wechat/sogou/MP_ID_BAIJING",       # 白鲸出海 公众号（示例占位）
    "https://rsshub.app/wechat/sogou/MP_ID_TOUZHONG",      # 投中网 公众号（示例占位）
]

SEEN_FILE = "seen.json"

# ========== 3) 关键词：分三类 ==========
FUNDING_KWS_ZH = [
    "融资", "投资", "投融资", "领投", "跟投", "独家", "估值",
    "Pre-A", "A轮", "B轮", "C轮", "D轮", "天使轮", "种子轮",
    "并购", "收购", "IPO", "上市"
]

BIG_TECH_KWS_ZH = [
    "发布", "上线", "开源", "更新", "升级", "重大", "突破", "首发", "新品", "新款",
    "芯片", "GPU", "算力", "服务器", "数据中心",
    "政策", "监管", "法案", "反垄断"
]

AI_ROBOT_KWS_ZH = [
    "AI", "大模型", "模型", "推理", "训练", "多模态", "Agent", "RAG",
    "机器人", "具身", "具身智能", "灵巧手", "视觉", "端侧", "自动驾驶",
    "GPT", "Claude", "Gemini", "Llama", "Sora",
    "OpenAI", "英伟达", "NVIDIA", "微软", "Meta", "谷歌", "Google",
    "字节", "腾讯", "阿里", "华为"
]

# 英文源补充（出海/AI）
FUNDING_KWS_EN = ["funding", "raises", "raised", "round", "seed", "series a", "series b", "ipo", "acquisition", "acquires"]
AI_KWS_EN = ["ai", "model", "llm", "inference", "training", "agent", "robot", "embodied", "nvidia", "gpu", "openai", "google", "meta", "microsoft"]

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    # 防止文件无限变大
    seen_list = list(seen)[-8000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen_list, f, ensure_ascii=False)

def uid(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def norm(s: str) -> str:
    s = s or ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def hit_any(text: str, kws) -> bool:
    text_l = text.lower()
    for k in kws:
        if k.lower() in text_l:
            return True
    return False

def feishu_send_text(text: str):
    payload = {"msg_type": "text", "content": {"text": text}}
    r = requests.post(WEBHOOK, json=payload, timeout=15)
    r.raise_for_status()

def main():
    seen = load_seen()

    funding = []
    bigtech = []
    ai_robot = []

    for rss in RSS_LIST:
        feed = feedparser.parse(rss)
        entries = getattr(feed, "entries", [])[:60]

        for e in entries:
            title = norm(getattr(e, "title", "") or e.get("title", ""))
            link = norm(getattr(e, "link", "") or e.get("link", ""))
            summary = norm(getattr(e, "summary", "") or e.get("summary", "") or e.get("description", ""))

            if not title or not link:
                continue

            k = uid(link)
            if k in seen:
                continue

            text = f"{title} {summary}"

            # 中文关键词命中
            is_funding_zh = hit_any(text, FUNDING_KWS_ZH)
            is_bigtech_zh = hit_any(text, BIG_TECH_KWS_ZH)
            is_ai_zh = hit_any(text, AI_ROBOT_KWS_ZH)

            # 英文关键词命中（对出海源更友好）
            is_funding_en = hit_any(text, FUNDING_KWS_EN)
            is_ai_en = hit_any(text, AI_KWS_EN)

            is_funding = is_funding_zh or is_funding_en
            is_ai = is_ai_zh or is_ai_en
            is_bigtech = is_bigtech_zh

            if not (is_funding or is_ai or is_bigtech):
                continue

            seen.add(k)

            # 分类优先级：融资 > AI/机器人 > 科技大事
            if is_funding:
                funding.append((title, link))
            elif is_ai:
                ai_robot.append((title, link))
            else:
                bigtech.append((title, link))

    # 控制条数避免刷屏
    funding = funding[:6]
    ai_robot = ai_robot[:6]
    bigtech = bigtech[:6]

    if not (funding or ai_robot or bigtech):
        return

    today = datetime.now().strftime("%Y-%m-%d")
    parts = [f"🗞 中文科技情报（{today}）"]

    if funding:
        parts.append("\n【投融资】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in funding]))

    if ai_robot:
        parts.append("\n【AI / 机器人 / 出海AI】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in ai_robot]))

    if bigtech:
        parts.append("\n【科技大事】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in bigtech]))

    feishu_send_text("\n".join(parts))
    save_seen(seen)

if __name__ == "__main__":
    main()
