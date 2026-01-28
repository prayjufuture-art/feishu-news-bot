import os
import re
import json
import hashlib
from datetime import datetime

import requests
import feedparser

WEBHOOK = os.environ["FEISHU_WEBHOOK"]

# 你可以继续加源；公众号/晚点走 RSSHub 的话，公共实例偶尔不稳属正常
RSS_LIST = [
    # 中文网站
    "https://36kr.com/feed",
    "https://www.ithome.com/rss/",
    "https://www.jiqizhixin.com/rss",
    "https://www.qbitai.com/feed",

    # 出海/AI（可选）
    "http://feeds.venturebeat.com/VentureBeat",
    "https://huggingface.co/blog/feed.xml",

    # 晚点文章（RSSHub 路由，公共实例可能不稳）
    "https://rsshub.app/latepost",
]

SEEN_FILE = "seen.json"

# -----------------------------
# 更宽泛的关键词（中文）
# -----------------------------
FUNDING_KWS_ZH = [
    "融资", "投资", "投融资", "募资", "领投", "跟投", "加码", "独家",
    "估值", "战略投资", "并购", "收购", "合并", "IPO", "上市", "招股书",
    "Pre-A", "A轮", "B轮", "C轮", "D轮", "E轮", "天使", "种子", "pre-ipo",
    "基金", "GP", "LP", "VC", "PE"
]

AI_ROBOT_KWS_ZH = [
    "AI", "人工智能", "大模型", "模型", "多模态", "推理", "训练", "蒸馏", "对齐",
    "Agent", "智能体", "RAG", "检索", "Embedding", "向量",
    "机器人", "具身", "具身智能", "灵巧手", "人形", "自动驾驶", "无人机", "视觉",
    "芯片", "GPU", "算力", "推理卡", "服务器", "边缘计算", "端侧", "OS", "操作系统",
    "OpenAI", "英伟达", "NVIDIA", "微软", "Meta", "谷歌", "Google", "苹果", "Apple",
    "字节", "腾讯", "阿里", "华为", "小米"
]

BIG_TECH_KWS_ZH = [
    "发布", "上线", "开源", "更新", "升级", "推出", "宣布", "预告",
    "新品", "新款", "首发", "量产", "发布会",
    "政策", "监管", "条例", "法案", "反垄断", "制裁", "禁令",
    "裁员", "重组", "组织", "业务调整", "战略", "合作", "签约", "收缩", "扩张",
    "财报", "营收", "利润", "指引"
]

# -----------------------------
# 更宽泛的关键词（英文）
# -----------------------------
FUNDING_KWS_EN = [
    "funding", "raised", "raises", "round", "seed", "series", "pre-seed",
    "valuation", "invest", "investment", "backed", "backing",
    "acquire", "acquires", "acquisition", "merger", "ipo", "public offering"
]

AI_KWS_EN = [
    "ai", "artificial intelligence", "model", "llm", "multimodal",
    "inference", "training", "agent", "rag", "embedding",
    "robot", "robotics", "embodied", "humanoid",
    "gpu", "compute", "nvidia", "openai", "microsoft", "meta", "google", "apple"
]

BIG_TECH_KWS_EN = [
    "launch", "released", "release", "announced", "update", "upgraded", "open-source", "open source",
    "policy", "regulation", "ban", "sanction", "earnings", "restructuring", "layoff", "partnership"
]

# 噪音黑名单（宽泛情况下用来降噪）
BLACKLIST = [
    "壁纸", "表情包", "优惠", "促销", "打折", "评测", "图赏", "娱乐", "游戏", "影视", "综艺",
    "星座", "玄学", "彩票"
]

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

def classify(text: str):
    """
    返回: "funding" | "ai" | "big" | None
    分类更宽泛：任一命中即归类；都不命中则 None
    """
    # 中文命中
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
    per_source_kept = {}  # 每个源至少保留 1 条

    for rss in RSS_LIST:
        feed = feedparser.parse(rss)
        entries = getattr(feed, "entries", [])[:60]
        kept_this_source = 0

        for e in entries:
            title = norm(getattr(e, "title", "") or e.get("title", ""))
            link = norm(getattr(e, "link", "") or e.get("link", ""))
            summary = norm(getattr(e, "summary", "") or e.get("description", "") or "")

            if not title or not link:
                continue

            text = f"{title} {summary}"

            # 黑名单先过滤（否则宽泛会太吵）
            if is_blacklisted(text):
                continue

            k = uid(link)
            if k in seen:
                continue

            cat = classify(text)
            seen.add(k)
            kept_this_source += 1

            # 分类入桶：未命中任何关键词也保留到 other（保底）
            if cat == "funding":
                funding.append((title, link))
            elif cat == "ai":
                ai_robot.append((title, link))
            elif cat == "big":
                bigtech.append((title, link))
            else:
                other.append((title, link))

            # 每个源最多先拿 3 条，避免某个源刷屏
            if kept_this_source >= 3:
                break

        per_source_kept[rss] = kept_this_source

    # 总量控制：避免消息过长
    funding = funding[:8]
    ai_robot = ai_robot[:8]
    bigtech = bigtech[:8]
    other = other[:6]

    # 如果“除了36kr都没拉到”，other/ai/big 也会给你一些保底（只要源能拉到）
    if not (funding or ai_robot or bigtech or other):
        save_seen(seen)
        return

    today = datetime.now().strftime("%Y-%m-%d")
    parts = [f"🗞 中文科技情报（{today}）"]

    if funding:
        parts.append("\n【投融资】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in funding]))

    if bigtech:
        parts.append("\n【科技大事】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in bigtech]))

    if ai_robot:
        parts.append("\n【AI / 机器人 / 出海AI】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in ai_robot]))

    if other:
        parts.append("\n【其他精选（保底）】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in other]))

    # 附带：每个源实际抓到多少条（可选，方便你排查；不想要就删掉下面这段）
    stats_lines = [f"- {rss}: kept={per_source_kept.get(rss,0)}" for rss in RSS_LIST]
    parts.append("\n【抓取统计】\n" + "\n".join(stats_lines))

    feishu_send_text("\n".join(parts))
    save_seen(seen)

if __name__ == "__main__":
    main()
