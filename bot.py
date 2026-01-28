import requests
import feedparser
import hashlib
import json
import os
from datetime import datetime

WEBHOOK = os.environ["FEISHU_WEBHOOK"]

RSS_LIST = [
    "https://36kr.com/feed",
    "https://www.latepost.com/feed",
    "https://www.jiqizhixin.com/rss",
    "https://www.qbitai.com/feed",
    "https://www.ithome.com/rss/",
]

SEEN_FILE = "seen.json"

FUNDING_KWS = [
    "融资", "投资", "投融资", "领投", "跟投", "IPO", "上市", "并购", "收购", "战略投资",
    "Pre-A", "A轮", "B轮", "C轮", "D轮", "天使轮", "种子轮", "估值", "独家"
]

BIG_TECH_KWS = [
    "发布", "上线", "开源", "更新", "升级", "突破", "首发", "新款", "新品",
    "大模型", "GPT", "Claude", "Gemini", "Llama", "Sora",
    "AI", "机器人", "具身智能", "芯片", "GPU", "算力",
    "英伟达", "NVIDIA", "苹果", "Apple", "谷歌", "Google",
    "OpenAI", "微软", "Meta", "字节", "腾讯", "阿里",
    "政策", "监管", "禁令", "法案", "反垄断"
]

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-5000:], f, ensure_ascii=False)

def send(text):
    payload = {"msg_type": "text", "content": {"text": text}}
    requests.post(WEBHOOK, json=payload, timeout=10)

def uid(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def hit_any(text, kws):
    return any(k in text for k in kws)

def main():
    seen = load_seen()

    funding = []
    bigtech = []

    for rss in RSS_LIST:
        feed = feedparser.parse(rss)
        for e in feed.entries[:40]:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            summary = e.get("summary", "") or e.get("description", "") or ""
            text = f"{title} {summary}"

            if not title or not link:
                continue

            k = uid(link)
            if k in seen:
                continue

            is_funding = hit_any(text, FUNDING_KWS)
            is_bigtech = hit_any(text, BIG_TECH_KWS)

            if not (is_funding or is_bigtech):
                continue

            seen.add(k)

            if is_funding:
                funding.append((title, link))
            elif is_bigtech:
                bigtech.append((title, link))

    funding = funding[:6]
    bigtech = bigtech[:6]

    if not funding and not bigtech:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"🗞 中文科技情报晨报（{today}）\n"

    if funding:
        msg += "\n【投融资】\n" + "\n\n".join([f"- {t}\n{l}" for t, l in funding])

    if bigtech:
        msg += "\n\n【科技大事 / AI / 机器人】\n" + "\n\n".join([f"- {t}\n{l}" for t, l in bigtech])

    send(msg)
    save_seen(seen)

if __name__ == "__main__":
    main()
