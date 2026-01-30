import os
import re
import json
import hashlib
from datetime import datetime, timezone, timedelta

import requests
import feedparser

WEBHOOK = os.environ["FEISHU_WEBHOOK"]
SEEN_FILE = "seen.json"

# =========================
# 1) 信息源（你可以随时增删）
# =========================
RSS_LIST = [
    # ---- 中文：投融资/商业科技/大事 ----
    "https://36kr.com/feed",
    "https://www.ithome.com/rss/",
    "https://www.jiqizhixin.com/rss",
    "https://www.qbitai.com/feed",

    # ---- 出海/海外创业/全球科技（相对稳定）----
    "http://feeds.venturebeat.com/VentureBeat",
    "https://www.generalist.com/feed",

    # ---- AI 供给侧关键更新（稳定）----
    "https://huggingface.co/blog/feed.xml",

    # ---- 可选：晚点（公共 RSSHub 可能不稳，稳定需自建 RSSHub）----
    "https://rsshub.app/latepost",
]

# =========================
# 2) 关键词（更贴近“投资 + 消费硬件 + 出海 + AI/机器人”）
# =========================
FUNDING_KWS_ZH = [
    "融资","投资","投融资","募资","领投","跟投","加码","独家","估值","战略投资",
    "并购","收购","合并","IPO","上市","招股书",
    "Pre-A","A轮","B轮","C轮","D轮","E轮","天使","种子","pre-ipo",
    "VC","PE","基金","GP","LP"
]

AI_ROBOT_KWS_ZH = [
    "AI","人工智能","大模型","模型","多模态","推理","训练","蒸馏","对齐",
    "Agent","智能体","RAG","Embedding","向量",
    "机器人","具身","具身智能","灵巧手","人形","自动驾驶","无人机","视觉",
    "芯片","GPU","算力","服务器","边缘计算","端侧",
    "OpenAI","英伟达","NVIDIA","微软","Meta","谷歌","Google","苹果","Apple",
    "字节","腾讯","阿里","华为","小米"
]

# —— 新增：消费硬件 / 智能产品（你要的重点）——
CONSUMER_HW_KWS_ZH = [
    "智能硬件","消费硬件","智能产品","硬件","可穿戴","智能穿戴",
    "耳机","TWS","音箱","音响","手表","手环","眼镜","AR眼镜","VR","MR",
    "相机","摄像头","运动相机","投影","投影仪","显示器","电视","路由器","NAS",
    "扫地机器人","洗地机","智能门锁","智能家居","智能家电","小家电",
    "机器人玩具","AI玩具","儿童硬件","学习机","故事机",
    "宠物智能","智能喂食","智能猫砂",
    "DTC","爆款","众筹","Kickstarter","Indiegogo","BOM","量产","代工","工厂","供应链"
]

# —— 新增：出海 / 海外创业（你要的重点）——
OVERSEAS_KWS_ZH = [
    "出海","海外","跨境","跨境电商","独立站","DTC","亚马逊","Amazon","Shopify",
    "海外市场","北美","欧洲","东南亚","中东","日本","拉美",
    "分销","渠道","经销商","代理","本地化","合规","认证","CE","FCC","UL",
    "关税","物流","仓","履约","FBA","品牌出海","海外投放"
]

# 英文补充（用于 VentureBeat / Generalist 等）
FUNDING_KWS_EN = ["funding","raised","raises","round","seed","series","valuation","invest","investment","acquisition","merger","ipo"]
AI_KWS_EN = ["ai","model","llm","multimodal","inference","training","agent","rag","embedding","robot","robotics","embodied","gpu","nvidia","openai","microsoft","meta","google","apple"]
CONSUMER_HW_KWS_EN = [
    "consumer","device","hardware","wearable","earbuds","headphones","smartwatch","smart glasses","ar","vr","mr",
    "smart home","robot vacuum","camera","projector","speaker",
    "kickstarter","indiegogo","manufacturing","mass production","supply chain","oem","odm","bom"
]
OVERSEAS_KWS_EN = ["overseas","global","cross-border","international","export","amazon","shopify","dtc","distributor","retail","channel","compliance","certification","fcc","ce","ul","tariff","logistics"]

# =========================
# 3) 降噪黑名单（宽泛关键词必备）
# =========================
BLACKLIST = ["壁纸","表情包","优惠","促销","打折","图赏","娱乐","影视","综艺","星座","玄学","彩票"]

# =========================
# 工具函数
# =========================
def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-12000:], f, ensure_ascii=False)

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
    # requests + UA 比 feedparser.parse(url) 稳定
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FeishuNewsBot/1.0)",
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
    r.raise_for_status()
    return feedparser.parse(r.content)

def classify(text: str):
    """
    四分类：funding / ai_robot / consumer_hw / overseas
    优先级：
      1) 融资
      2) AI/机器人
      3) 消费硬件
      4) 出海
    （优先级可以按你习惯再调整）
    """
    if contains_any(text, FUNDING_KWS_ZH) or contains_any(text, FUNDING_KWS_EN):
        return "funding"
    if contains_any(text, AI_ROBOT_KWS_ZH) or contains_any(text, AI_KWS_EN):
        return "ai_robot"
    if contains_any(text, CONSUMER_HW_KWS_ZH) or contains_any(text, CONSUMER_HW_KWS_EN):
        return "consumer_hw"
    if contains_any(text, OVERSEAS_KWS_ZH) or contains_any(text, OVERSEAS_KWS_EN):
        return "overseas"
    return None

# =========================
# 主逻辑
# =========================
def main():
    seen = load_seen()

    funding, ai_robot, consumer_hw, overseas, other = [], [], [], [], []

    tz_bj = timezone(timedelta(hours=8))
    run_time_bj = datetime.now(tz_bj).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(tz_bj).strftime("%Y-%m-%d")

    for rss in RSS_LIST:
        try:
            feed = parse_feed(rss)
            entries = getattr(feed, "entries", [])[:70]
        except Exception:
            # 某源失败直接跳过
            continue

        kept_this_source = 0
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

            cat = classify(text)
            seen.add(k)
            kept_this_source += 1

            if cat == "funding":
                funding.append((title, link))
            elif cat == "ai_robot":
                ai_robot.append((title, link))
            elif cat == "consumer_hw":
                consumer_hw.append((title, link))
            elif cat == "overseas":
                overseas.append((title, link))
            else:
                other.append((title, link))

            # 每个源最多取 3 条，保证多源露出
            if kept_this_source >= 3:
                break

    # 总量控制（你可按喜好改）
    funding = funding[:8]
    ai_robot = ai_robot[:8]
    consumer_hw = consumer_hw[:8]
    overseas = overseas[:8]
    other = other[:6]

    if not (funding or ai_robot or consumer_hw or overseas or other):
        save_seen(seen)
        return

    parts = [f"🗞 中文科技情报（{today}｜运行：{run_time_bj}）"]

    if funding:
        parts.append("\n【投融资】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in funding]))

    if ai_robot:
        parts.append("\n【AI / 机器人 / 具身】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in ai_robot]))

    if consumer_hw:
        parts.append("\n【消费硬件 / 智能产品】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in consumer_hw]))

    if overseas:
        parts.append("\n【出海 / 海外创业】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in overseas]))

    if other:
        parts.append("\n【其他精选】")
        parts.append("\n\n".join([f"- {t}\n{l}" for t, l in other]))

    feishu_send_text("\n".join(parts))
    save_seen(seen)

if __name__ == "__main__":
    main()
