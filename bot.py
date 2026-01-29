import os
import re
import json
import hashlib
from datetime import datetime, timezone, timedelta

import requests
import feedparser

WEBHOOK = os.environ["FEISHU_WEBHOOK"]

RSS_LIST = [
    "https://36kr.com/feed",
    "https://www.ithome.com/rss/",
    "https://www.jiqizhixin.com/rss",
    "https://www.qbitai.com/feed",
    "http://feeds.venturebeat.com/VentureBeat",
    "https://huggingface.co/blog/feed.xml",
    "https://rsshub.app/latepost",  # 公共 RSSHub 偶尔不稳属正常
]

SEEN_FILE = "seen.json"

FUNDING_KWS_ZH = [
    "融资","投资","投融资","募资","领投","跟投","加码","独家","估值","战略投资",
    "并购","收购","合并","IPO","上市","招股书",
    "Pre-A","A轮","B轮","C轮","D轮","E轮","天使","种子","pre-ipo","VC","PE","基金","GP","LP"
]
AI_ROBOT_KWS_ZH = [
    "AI","人工智能","大模型","模型","多模态","推理","训练","蒸馏","对齐",
    "Agent","智能体","RAG","Embedding","向量",
    "机器人","具身","具身智能","灵巧手","人形","自动驾驶","无人机","视觉",
    "芯片","GPU","算力","服务器","边缘计算","端侧",
    "OpenAI","英伟达","NVIDIA","微软","Meta","谷歌","Google","苹果","Apple",
    "字节","腾讯","阿里","华为","小米"
]
BIG_TECH_KWS_ZH = [
    "发布","上线","开源","更新","升级","推出","宣布","预告",
    "新品","新款","首发","量产","发布会",
    "政策","监管","条例","法案","反垄断","制裁","禁令",
    "裁员","重组","组织","业务调整","战略","合作","签约","财报","营收","利润","指引"
]
FUNDING_KWS_EN = ["funding","raised","raises","round","seed","series","valuation","invest","investment","acquisition","merger","ipo"]
AI_KWS_EN = ["ai","model","llm","multimodal","inference","training","agent","rag","embedding","robot","robotics","embodied","gpu","nvidia","openai","microsoft","meta","google","apple"]
BIG_TECH_KWS_EN = ["launch","released","release","announced","update","upgrade","open source","open-source","policy","regulation","ban","sanction","earnings","restructuring","layoff","partnership"]

BLACKLIST = ["壁纸","表情包","优惠","促销","打折","图赏","娱乐","影视","综艺","星座","玄学","彩票"]

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-8000:], f, ensure_ascii=False)

def uid(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def norm(s: str) -> str:
    s = s or ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def contains_any(text: str, kws) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in kws)

def is_blacklisted(text: str) -> bool:
    return any(b in text for b in BLACKLIST)

def feishu_send_text(text: str):
    payload = {"msg_type": "text", "content": {"text": text}}
    r = requests.post(WEBHOOK, json=payload, timeout=15)
    r.raise_for_status()

def parse_feed(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FeishuNewsBot/1.0)",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
    r.raise_for_status()
    return feedparser.parse(r.content)

def classify(text: str):
    if contains_any(text, FUNDING_KWS_ZH) or contains_any(text, FUNDING_KWS_EN):
        return "funding"
    if contains_any(text, AI_ROBOT_KWS_ZH) or contains_any(text, AI_KWS_EN):
        return "ai"
    if contains_any(text, BIG_TECH_KWS_ZH) or contains_any(text, BIG_TECH_KWS_EN):
        return "big"
    return None

def main():
    seen = load_seen()
    funding, ai_robot, bigtech, other = [], [], [], []
    stats = []

    # 运行时间：用北京时间固定展示，避免你看到“下午1点”误会时区
    tz_bj = timezone(timedelta(hours=8))
    run_time_bj = datetime.now(tz_bj).strftime("%Y-%m-%d %H:%M:%S")

    for rss in RSS_LIST:
        kept = 0
        err = ""

        try:
            feed = parse_feed(rss)
            entries = getattr(feed, "entries", [])[:60]
            for e in entries:
                title = norm(getattr(e, "title", "") or e.get("title", ""))
                link = norm(getattr(e, "link", "") or e.get("link", ""))
                summary = norm(getattr(e, "summary", "") or e.get("description", "") or "")

                if not title or not link:
                    continue

                text = f"{title} {summary}"
                if is_blacklisted(text):
                    continue

                k = uid(link)
                if k in seen:
                    continue

                cat =
