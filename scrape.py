import json
import re
import urllib.request
import urllib.error
import time
import os
import hashlib
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

# ==============================================================
#  配置
# ==============================================================

ATHENS_OFFSET = timedelta(hours=3)

def get_athens_now():
    return datetime.now(timezone.utc) + ATHENS_OFFSET

def get_athens_today():
    return get_athens_now().strftime("%Y-%m-%d")

def split_list(value, fallback=None):
    if value is None or str(value).strip() == "":
        return list(fallback or [])
    return [x.strip() for x in re.split(r'[\n,;]+', str(value)) if x.strip()]

# ===== API Keys（多 Key 支持，逗号/换行/分号分隔）=====
GEMINI_PAID_KEYS = split_list(os.getenv("GEMINI_PAID_KEYS"))
GEMINI_FREE_KEYS = split_list(os.getenv("GEMINI_FREE_KEYS") or os.getenv("GEMINI_API_KEY"))
GROQ_KEYS = split_list(os.getenv("GROQ_KEYS") or os.getenv("GROQ_API_KEY"))
OPENROUTER_KEYS = split_list(os.getenv("OPENROUTER_KEYS") or os.getenv("OPENROUTER_API_KEY"))

# ===== 模型列表（按顺序尝试）=====
GEMINI_MODELS = split_list(os.getenv("GEMINI_MODELS"), [
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-flash-latest",
    "gemini-1.5-flash",
])

GROQ_MODELS = split_list(os.getenv("GROQ_MODELS"), [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
])

OPENROUTER_MODELS = split_list(os.getenv("OPENROUTER_MODELS"), [
    "deepseek/deepseek-chat-v3.1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "google/gemma-2-9b-it:free",
])

# ===== 翻译策略 =====
MAX_TRANSLATE_PER_RUN = 100
MIN_SCORE_TO_TRANSLATE = 1
CACHE_FILE = "translation_cache.json"
BRIEFING_TOP_N = 8
SOCIAL_TOP_N = 12

# ==============================================================
#  新闻源（含中文名）
# ==============================================================

NEWS_SOURCES = [
    # 希腊本地
    {"name": "Ekathimerini",       "name_zh": "希腊日报",       "url": "https://www.ekathimerini.com/feed/",                          "category": "greek_local",    "icon": "🇬🇷"},
    {"name": "Greek Reporter",     "name_zh": "希腊先驱报",     "url": "https://greekreporter.com/feed/",                             "category": "greek_local",    "icon": "🇬🇷"},
    {"name": "Keep Talking Greece","name_zh": "谈希腊",         "url": "https://www.keeptalkinggreece.com/feed/",                     "category": "greek_local",    "icon": "🇬🇷"},
    {"name": "Greek City Times",   "name_zh": "希腊城市时报",   "url": "https://greekcitytimes.com/feed/",                            "category": "greek_local",    "icon": "🇬🇷"},
    {"name": "Tornos News",        "name_zh": "托尔诺斯新闻",   "url": "https://www.tornosnews.gr/feed",                              "category": "greek_local",    "icon": "🇬🇷"},
    {"name": "The National Herald","name_zh": "国家先驱报",     "url": "https://www.thenationalherald.com/feed/",                     "category": "greek_local",    "icon": "🇬🇷"},
    {"name": "ANA-MPA",            "name_zh": "雅典通讯社",     "url": "https://www.amna.gr/rss/English",                             "category": "greek_local",    "icon": "🇬🇷"},

    # 希腊东正教
    {"name": "Orthodox Times",     "name_zh": "东正教时报",     "url": "https://orthodoxtimes.com/feed/",                             "category": "greek_orthodox", "icon": "☦️"},
    {"name": "Pemptousia",         "name_zh": "彭普图西亚",     "url": "https://pemptousia.com/feed/",                                "category": "greek_orthodox", "icon": "☦️"},
    {"name": "OrthoChristian",     "name_zh": "正统基督教网",   "url": "https://orthochristian.com/news.xml",                          "category": "greek_orthodox", "icon": "☦️"},
    {"name": "Mystagogy",          "name_zh": "奥秘教导",       "url": "https://www.johnsanidopoulos.com/feeds/posts/default?alt=rss","category": "greek_orthodox", "icon": "☦️"},
    {"name": "Public Orthodoxy",   "name_zh": "公共东正教",     "url": "https://publicorthodoxy.org/feed/",                           "category": "greek_orthodox", "icon": "🎓"},
    {"name": "Greek Orthodox Archdiocese", "name_zh": "希腊东正教总教区", "url": "https://www.goarch.org/-/news?_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_feed=rss", "category":"greek_orthodox","icon": "☦️"},
    {"name": "OCA",                "name_zh": "美国东正教会",   "url": "https://www.oca.org/news/headline-news/feed.xml",             "category": "greek_orthodox", "icon": "🏛️"},
    {"name": "Pravoslavie.ru",     "name_zh": "正教网",         "url": "https://pravoslavie.ru/news.xml",                             "category": "greek_orthodox", "icon": "☦️"},
    {"name": "Ancient Faith",      "name_zh": "古老信仰",       "url": "https://blogs.ancientfaith.com/feed/",                        "category": "greek_orthodox", "icon": "📻"},
    {"name": "Moscow Patriarchate","name_zh": "莫斯科牧首区",   "url": "http://feeds.feedburner.com/MoscowPatriarchate",              "category": "greek_orthodox", "icon": "🇷🇺"},
    {"name": "Romfea",             "name_zh": "Romfea希腊东正教", "url": "https://www.romfea.news/index.php?option=com_ninjarsssyndicator&feed_id=1&format=raw", "category": "greek_orthodox", "icon": "☦️"},

    # 欧洲
    {"name": "Euronews",           "name_zh": "欧洲新闻台",     "url": "https://www.euronews.com/rss",                                "category": "europe",         "icon": "🇪🇺"},
    {"name": "France 24",          "name_zh": "法国24台",       "url": "https://www.france24.com/en/rss",                             "category": "europe",         "icon": "🇫🇷"},
    {"name": "DW News",            "name_zh": "德国之声",       "url": "https://rss.dw.com/rdf/rss-en-all",                           "category": "europe",         "icon": "🇩🇪"},
    {"name": "BBC Europe",         "name_zh": "BBC欧洲",        "url": "https://feeds.bbci.co.uk/news/world/europe/rss.xml",          "category": "europe",         "icon": "🇬🇧"},
    {"name": "Guardian Europe",    "name_zh": "卫报欧洲",       "url": "https://www.theguardian.com/world/europe-news/rss",           "category": "europe",         "icon": "🇬🇧"},
    {"name": "POLITICO Europe",    "name_zh": "政客欧洲",       "url": "https://www.politico.eu/feed/",                               "category": "europe",         "icon": "🇪🇺"},
    {"name": "Balkan Insight",     "name_zh": "巴尔干洞察",     "url": "https://balkaninsight.com/feed/",                             "category": "europe",         "icon": "🌍"},

    # 全球
    {"name": "Al Jazeera",         "name_zh": "半岛电视台",     "url": "https://www.aljazeera.com/xml/rss/all.xml",                   "category": "global",         "icon": "🌍"},
    {"name": "BBC World",          "name_zh": "BBC世界",        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",                 "category": "global",         "icon": "🌍"},
    {"name": "Guardian World",     "name_zh": "卫报世界",       "url": "https://www.theguardian.com/world/rss",                       "category": "global",         "icon": "🌍"},
    {"name": "NPR",                "name_zh": "美国国家公共电台","url": "https://feeds.npr.org/1001/rss.xml",                          "category": "global",         "icon": "🎙️"},
    {"name": "The Hindu",          "name_zh": "印度教徒报",     "url": "https://www.thehindu.com/news/feeder/default.rss",            "category": "global",         "icon": "🇮🇳"},
    {"name": "Reuters World",      "name_zh": "路透社世界",     "url": "https://feeds.reuters.com/Reuters/worldNews",                 "category": "global",         "icon": "🌐"},

    # 科学 / 太空
    {"name": "NASA",               "name_zh": "美国宇航局",     "url": "https://www.nasa.gov/feed/",                                  "category": "science",        "icon": "🚀"},
    {"name": "Space.com",          "name_zh": "太空网",         "url": "https://www.space.com/feeds/all",                             "category": "science",        "icon": "🔭"},
    {"name": "Phys.org",           "name_zh": "物理学网",       "url": "https://phys.org/rss-feed/",                                  "category": "science",        "icon": "🔬"},
    {"name": "Nature",             "name_zh": "《自然》",       "url": "https://www.nature.com/nature.rss",                           "category": "science",        "icon": "🧬"},
]

# 大类（保留）
CATEGORIES = {
    "greek_local":    {"name_en": "Greece Local",    "name_zh": "希腊本地",   "icon": "🇬🇷", "color": "#0D5EAF"},
    "greek_orthodox": {"name_en": "Greek Orthodox",  "name_zh": "希腊东正教", "icon": "☦️",  "color": "#8B6914"},
    "europe":         {"name_en": "Europe",          "name_zh": "欧洲新闻",   "icon": "🇪🇺", "color": "#003399"},
    "global":         {"name_en": "Global",          "name_zh": "全球新闻",   "icon": "🌍",  "color": "#2E8B57"},
    "science":        {"name_en": "Science & Space", "name_zh": "科学太空",   "icon": "🔬",  "color": "#6A0DAD"},
}

# ==============================================================
#  内容主题分类（关键词智能识别）
# ==============================================================

TOPIC_META = {
    "religion_orthodox":  {"name_zh": "东正教",   "name_en": "Orthodox",      "icon": "☦️"},
    "religion_other":     {"name_zh": "其他宗教", "name_en": "Religion",      "icon": "🕊️"},
    "international":      {"name_zh": "国际",     "name_en": "International", "icon": "🌐"},
    "greece":             {"name_zh": "希腊本地", "name_en": "Greece",        "icon": "🇬🇷"},
    "europe":             {"name_zh": "欧洲",     "name_en": "Europe",        "icon": "🇪🇺"},
    "war_conflict":       {"name_zh": "战争冲突", "name_en": "Conflict",      "icon": "⚔️"},
    "business":           {"name_zh": "商业",     "name_en": "Business",      "icon": "💼"},
    "economy":            {"name_zh": "经济",     "name_en": "Economy",       "icon": "💰"},
    "energy":             {"name_zh": "能源",     "name_en": "Energy",        "icon": "⚡"},
    "technology":         {"name_zh": "科技",     "name_en": "Tech",          "icon": "💻"},
    "ai":                 {"name_zh": "AI",       "name_en": "AI",            "icon": "🤖"},
    "sports":             {"name_zh": "体育",     "name_en": "Sports",        "icon": "⚽"},
    "climate":            {"name_zh": "气候",     "name_en": "Climate",       "icon": "🌡️"},
    "disaster_earthquake":{"name_zh": "地震",     "name_en": "Earthquake",    "icon": "🌋"},
    "disaster_cyclone":   {"name_zh": "气旋",     "name_en": "Cyclone",       "icon": "🌀"},
    "disaster_flood":     {"name_zh": "洪涝",     "name_en": "Flood",         "icon": "🌊"},
    "disaster_wildfire":  {"name_zh": "森林火灾", "name_en": "Wildfire",      "icon": "🔥"},
    "space":              {"name_zh": "航天",     "name_en": "Space",         "icon": "🚀"},
    "astronomy":          {"name_zh": "天文",     "name_en": "Astronomy",     "icon": "🔭"},
    "stargazing":         {"name_zh": "观星",     "name_en": "Stargazing",    "icon": "✨"},
    "science":            {"name_zh": "科学",     "name_en": "Science",       "icon": "🔬"},
    "culture":            {"name_zh": "文化",     "name_en": "Culture",       "icon": "🎭"},
    "history":            {"name_zh": "历史",     "name_en": "History",       "icon": "📜"},
    "tourism":            {"name_zh": "旅游",     "name_en": "Tourism",       "icon": "🏖️"},
    "health":             {"name_zh": "健康",     "name_en": "Health",        "icon": "🏥"},
    "other":              {"name_zh": "其他",     "name_en": "Other",         "icon": "📰"},
}

TOPIC_RULES = [
    ("religion_orthodox", ["orthodox", "patriarch", "metropolitan", "bishop", "monastery", "liturgy",
                           "holy synod", "mount athos", "patriarchate", "ecumenical", "icon ", "iconostasis",
                           "πατριάρχης", "ορθόδοξ", "αρχιεπίσκοπος", "μητροπολίτης"]),
    ("religion_other",    ["vatican", "pope", "catholic", "protestant", "muslim", "islam", "jewish",
                           "buddhism", "religion", "religious", "interfaith"]),
    ("greece",            ["greece", "greek", "athens", "thessaloniki", "crete", "rhodes", "halkidiki",
                           "santorini", "mitsotakis", "syriza", "aegean"]),
    ("europe",            ["europe", "european union", " eu ", "brussels", "balkan", "balkans",
                           "nato", "germany", "france", "italy", "spain"]),
    ("war_conflict",      ["war", "conflict", "battle", "attack", "missile", "military", "troops",
                           "ukraine", "russia", "israel", "hamas", "gaza"]),
    ("international",     ["international", "world", "global", "foreign", "diplomacy", "summit",
                           "united nations", "un ", "embassy"]),
    ("business",          ["business", "market", "stock", "stocks", "company", "trade", "merger",
                           "investment", "investor", "earnings", "ipo"]),
    ("economy",           ["economy", "economic", "inflation", "tax", "budget", "recession", "gdp",
                           "unemployment", "fiscal"]),
    ("energy",            ["energy", "oil", "gas", "petroleum", "opec", "lng", "pipeline", "renewable"]),
    ("ai",                ["ai ", "artificial intelligence", "machine learning", "chatgpt", "openai",
                           "llm", "gemini", "claude"]),
    ("technology",        ["technology", "tech ", "software", "startup", "digital", "cyber",
                           "smartphone", "app ", "google", "microsoft", "apple", "meta"]),
    ("sports",            ["football", "soccer", "basketball", "olympic", "olympics", "match",
                           "league", "tournament", "champion", "uefa", "fifa", "nba"]),
    ("disaster_earthquake",["earthquake", "seismic", "tremor", "aftershock", "magnitude"]),
    ("disaster_cyclone",  ["cyclone", "hurricane", "typhoon", "tropical storm"]),
    ("disaster_flood",    ["flood", "flooding", "flash flood", "heavy rain", "rainstorm", "deluge"]),
    ("disaster_wildfire", ["wildfire", "forest fire", "blaze", "fire spreads", "bushfire"]),
    ("climate",           ["climate", "warming", "temperature", "heatwave", "weather", "drought",
                           "carbon", "emission"]),
    ("space",             ["nasa", "spacex", "rocket", "satellite", "launch", "astronaut", "iss ",
                           "moon mission", "mars mission", "spacecraft"]),
    ("astronomy",         ["astronomy", "telescope", "galaxy", "nebula", "exoplanet", "black hole",
                           "cosmic", "astrophysics"]),
    ("stargazing",        ["stargazing", "meteor shower", "night sky", "planet alignment",
                           "lunar eclipse", "solar eclipse"]),
    ("science",           ["research", "study finds", "scientists", "physics", "biology", "chemistry",
                           "medicine", "discovery"]),
    ("culture",           ["museum", "art ", "exhibition", "festival", "music", "theatre",
                           "theater", "concert", "film"]),
    ("history",           ["archaeology", "ancient", "heritage", "historical", "ruins", "artifact"]),
    ("tourism",           ["tourism", "tourist", "travel", "hotel", "island", "beach", "vacation"]),
    ("health",            ["health", "hospital", "doctor", "disease", "vaccine", "covid", "virus",
                           "outbreak"]),
]

def classify_topics(title, description, category):
    text = f"{title or ''} {description or ''}".lower()
    tags = []

    if category == "greek_orthodox":
        tags.append("religion_orthodox")
    elif category == "greek_local":
        tags.append("greece")
    elif category == "europe":
        tags.append("europe")
    elif category == "global":
        tags.append("international")
    elif category == "science":
        tags.append("science")

    for tag, keywords in TOPIC_RULES:
        for kw in keywords:
            if kw in text:
                if tag not in tags:
                    tags.append(tag)
                break

    return tags[:4] or ["other"]

# ==============================================================
#  评分
# ==============================================================

SCORE_KEYWORDS = {
    10: ["ecumenical patriarch", "bartholomew", "patriarch of constantinople", "holy synod"],
    8:  ["orthodox church", "archbishop", "mount athos", "athos", "metropolitan",
         "greek orthodox", "πατριάρχης", "ορθόδοξ", "monastery", "iconostasis"],
    6:  ["greece", "greek", "athens", "thessaloniki", "cyprus", "orthodox",
         "christian", "church", "religion", "faith", "synod", "liturgy", "icon"],
    4:  ["europe", "eu ", "european union", "balkan", "turkey", "erdogan",
         "ukraine", "russia", "middle east", "israel", "jerusalem"],
    2:  ["economy", "politics", "election", "war", "conflict", "summit"],
}

def score_article(title, description, category):
    text = ((title or '') + ' ' + (description or '')).lower()
    score = 0
    if category == 'greek_orthodox': score += 5
    elif category == 'greek_local': score += 4
    elif category == 'europe': score += 2
    elif category == 'global': score += 1
    for points, keywords in SCORE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                score += points
                break
    return min(score, 20)

# ==============================================================
#  HTML & 工具
# ==============================================================

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.skip = True
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.skip = False
    def handle_data(self, data):
        if not self.skip: self.result.append(data)
    def get_text(self):
        return ' '.join(''.join(self.result).split())

def strip_html(html_text):
    if not html_text: return ""
    s = HTMLStripper()
    try:
        s.feed(html_text)
        return s.get_text()
    except:
        return re.sub(r'<[^>]+>', '', html_text).strip()

def make_id(title, link):
    return hashlib.md5((str(title) + str(link)).encode()).hexdigest()[:16]

# ==============================================================
#  日期解析
# ==============================================================

MONTHS = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
          'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}

def parse_date(date_str):
    if not date_str:
        n = get_athens_now()
        return n.strftime("%Y-%m-%d"), n.strftime("%H:%M"), ""
    date_str = date_str.strip()

    m = re.search(r'(\d{1,2})\s+(\w{3})\s+(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?\s*([+-]\d{4}|GMT|UTC)?', date_str)
    if m:
        try:
            mon = MONTHS.get(m.group(2), 1)
            tz_str = m.group(7) or '+0000'
            if tz_str in ('GMT', 'UTC'): tz_str = '+0000'
            th = int(tz_str[:3]); tm = int(tz_str[0] + tz_str[3:5])
            tz = timezone(timedelta(hours=th, minutes=tm))
            dt = datetime(int(m.group(3)), mon, int(m.group(1)),
                          int(m.group(4)), int(m.group(5)),
                          int(m.group(6)) if m.group(6) else 0, tzinfo=tz)
            adt = dt.astimezone(timezone(ATHENS_OFFSET))
            return adt.strftime("%Y-%m-%d"), adt.strftime("%H:%M"), date_str
        except: pass

    m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?([+-]\d{2}:?\d{2}|Z)?', date_str)
    if m2:
        try:
            tz_part = m2.group(7) or 'Z'
            if tz_part == 'Z': tz = timezone.utc
            else:
                tz_part = tz_part.replace(':', '')
                th = int(tz_part[:3]); tm = int(tz_part[0] + tz_part[3:5])
                tz = timezone(timedelta(hours=th, minutes=tm))
            dt = datetime(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)),
                          int(m2.group(4)), int(m2.group(5)),
                          int(m2.group(6)) if m2.group(6) else 0, tzinfo=tz)
            adt = dt.astimezone(timezone(ATHENS_OFFSET))
            return adt.strftime("%Y-%m-%d"), adt.strftime("%H:%M"), date_str
        except: pass

    n = get_athens_now()
    return n.strftime("%Y-%m-%d"), n.strftime("%H:%M"), date_str

# ==============================================================
#  RSS 解析
# ==============================================================

def parse_rss(xml_text):
    items = []
    blocks = re.findall(r'<item[^>]*>(.*?)</item>', xml_text, re.DOTALL)
    if not blocks:
        blocks = re.findall(r'<entry[^>]*>(.*?)</entry>', xml_text, re.DOTALL)

    for block in blocks:
        item = {}
        t = re.search(r'<title[^>]*>(.*?)</title>', block, re.DOTALL)
        if t:
            raw = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', t.group(1).strip())
            item['title'] = strip_html(raw)
        for pat in [r'<link[^>]*>(https?://[^<]+)</link>',
                    r'<link[^>]+href=["\']([^"\']+)["\']',
                    r'<guid[^>]*isPermaLink=["\']true["\'][^>]*>(https?://[^<]+)</guid>']:
            lm = re.search(pat, block, re.DOTALL)
            if lm:
                item['link'] = lm.group(1).strip()
                break
        dm = re.search(r'<(?:description|summary|content(?::encoded)?)[^>]*>(.*?)</(?:description|summary|content(?::encoded)?)>', block, re.DOTALL)
        if dm:
            raw = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', dm.group(1).strip(), flags=re.DOTALL)
            item['description'] = strip_html(raw)[:600]
        dtm = re.search(r'<(?:pubDate|published|updated|dc:date)[^>]*>(.*?)</(?:pubDate|published|updated|dc:date)>', block, re.DOTALL)
        if dtm: item['raw_date'] = dtm.group(1).strip()
        for pat in [r'<media:content[^>]+url=["\']([^"\']+)["\']',
                    r'<media:thumbnail[^>]+url=["\']([^"\']+)["\']',
                    r'<enclosure[^>]+url=["\']([^"\']+\.(?:jpg|jpeg|png|webp|gif))["\']']:
            im = re.search(pat, block, re.IGNORECASE)
            if im: item['image'] = im.group(1); break
        if 'image' not in item and dm:
            im2 = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', dm.group(1))
            if im2: item['image'] = im2.group(1)
        if 'title' in item and 'link' in item:
            items.append(item)
    return items

# ==============================================================
#  抓取（增强请求头，对抗 403）
# ==============================================================

def fetch_feed(source):
    print(f"  {source['icon']} {source['name_zh']} ({source['name']}) ...", end=" ", flush=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5',
        'Accept-Language': 'en-US,en;q=0.9,el;q=0.8,zh-CN;q=0.7',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Connection': 'keep-alive',
        'Referer': 'https://www.google.com/',
    }
    try:
        req = urllib.request.Request(source['url'], headers=headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
            for enc in ['utf-8', 'latin-1', 'iso-8859-7', 'windows-1253', 'windows-1251']:
                try: xml = raw.decode(enc); break
                except: continue
            else: xml = raw.decode('utf-8', errors='replace')

            items = parse_rss(xml)
            result = []
            for item in items:
                raw_date = item.pop('raw_date', '')
                ad, at, od = parse_date(raw_date)
                article = {
                    'id':            make_id(item.get('title',''), item.get('link','')),
                    'title':         item.get('title', ''),
                    'title_zh':      '',
                    'description':   item.get('description', ''),
                    'description_zh':'',
                    'link':          item.get('link', ''),
                    'image':         item.get('image', ''),
                    'source':        source['name'],
                    'source_zh':     source.get('name_zh', source['name']),
                    'icon':          source['icon'],
                    'category':      source['category'],
                    'topic_tags':    [],
                    'athens_date':   ad,
                    'athens_time':   at,
                    'original_date': od,
                    'score':         0,
                    'translated':    False,
                    'social_post':   '',
                }
                article['score'] = score_article(article['title'], article['description'], article['category'])
                article['topic_tags'] = classify_topics(article['title'], article['description'], article['category'])
                result.append(article)
            print(f"✅ {len(result)}")
            return result[:25]
    except Exception as e:
        print(f"❌ {str(e)[:60]}")
        return []

# ==============================================================
#  缓存
# ==============================================================

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ==============================================================
#  AI 调用：免费优先 / 多 Provider / 多 Key / 多模型 智能轮换
# ==============================================================

# 全局状态：标记已经失效/限流的 Key（本次运行内不再重试）
_dead_keys = set()
_error_stats = {}

def _record_error(provider, code, msg):
    key = f"{provider}_{code}"
    if key not in _error_stats:
        _error_stats[key] = {"count": 0, "sample": str(msg)[:120]}
    _error_stats[key]["count"] += 1

def print_error_stats():
    if not _error_stats:
        print("\n  ✅ 无 API 错误")
        return
    print("\n  📋 API 错误统计:")
    for k, v in sorted(_error_stats.items(), key=lambda x: -x[1]["count"]):
        print(f"    {k}: {v['count']} 次")
        print(f"      示例: {v['sample']}")

def show_alive_keys():
    af = sum(1 for i in range(len(GEMINI_FREE_KEYS)) if f"Gemini-Free#{i+1}" not in _dead_keys)
    ap = sum(1 for i in range(len(GEMINI_PAID_KEYS)) if f"Gemini-Paid#{i+1}" not in _dead_keys)
    ag = sum(1 for i in range(len(GROQ_KEYS)) if f"Groq#{i+1}" not in _dead_keys)
    ao = sum(1 for i in range(len(OPENROUTER_KEYS)) if f"OpenRouter#{i+1}" not in _dead_keys)
    print(f"  ❤️ 存活: G-Free {af}/{len(GEMINI_FREE_KEYS)} | G-Paid {ap}/{len(GEMINI_PAID_KEYS)} | "
          f"Groq {ag}/{len(GROQ_KEYS)} | OR {ao}/{len(OPENROUTER_KEYS)}")

def extract_json(text):
    if not text: return None
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text.strip())
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        text = text[start:end+1]
    try:
        return json.loads(text)
    except:
        return None


def call_gemini(prompt, max_tokens=600, temperature=0.3):
    """⭐ 免费 Key 优先，付费 Key 兜底"""
    if not (GEMINI_FREE_KEYS or GEMINI_PAID_KEYS):
        return None, "无Gemini Key"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
    }).encode("utf-8")

    last_err = "未尝试"

    # 免费 Key 优先 → 付费 Key 兜底
    for tier_name, keys in [("Free", GEMINI_FREE_KEYS), ("Paid", GEMINI_PAID_KEYS)]:
        for ki, key in enumerate(keys):
            key_id = f"Gemini-{tier_name}#{ki+1}"

            if key_id in _dead_keys:
                continue

            for model in GEMINI_MODELS:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                try:
                    req = urllib.request.Request(
                        url, data=payload,
                        headers={"Content-Type": "application/json"}, method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=40) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return text, f"{key_id}({model})"

                except urllib.error.HTTPError as e:
                    try:
                        err_body = e.read().decode("utf-8")[:150]
                    except:
                        err_body = ""
                    last_err = f"HTTP{e.code}"
                    _record_error(f"Gemini-{tier_name}", e.code, err_body)

                    # 401/403 = Key 无效；429 = 限流 → 永久跳过
                    if e.code in (401, 403, 429):
                        _dead_keys.add(key_id)
                        break

                    # 404 = 模型不存在 → 试下一个模型
                    if e.code == 404:
                        continue

                    continue

                except Exception as e:
                    last_err = str(e)[:80]
                    _record_error(f"Gemini-{tier_name}", "EXC", str(e))
                    continue

    return None, f"Gemini全失败({last_err})"


def call_groq(prompt, max_tokens=600, temperature=0.3):
    if not GROQ_KEYS:
        return None, "无Groq Key"

    url = "https://api.groq.com/openai/v1/chat/completions"
    last_err = "未尝试"

    for ki, key in enumerate(GROQ_KEYS):
        key_id = f"Groq#{ki+1}"
        if key_id in _dead_keys:
            continue

        for model in GROQ_MODELS:
            try:
                body = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }).encode("utf-8")
                req = urllib.request.Request(url, data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {key}",
                    }, method="POST")
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"].strip()
                    return text, f"{key_id}({model})"

            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode("utf-8")[:150]
                except:
                    err_body = ""
                last_err = f"HTTP{e.code}"
                _record_error("Groq", e.code, err_body)

                if e.code in (401, 403, 429):
                    _dead_keys.add(key_id)
                    break
                if e.code == 404:
                    continue
                continue

            except Exception as e:
                last_err = str(e)[:80]
                _record_error("Groq", "EXC", str(e))
                continue

    return None, f"Groq全失败({last_err})"


def call_openrouter(prompt, max_tokens=600, temperature=0.3):
    if not OPENROUTER_KEYS:
        return None, "无OpenRouter Key"

    url = "https://openrouter.ai/api/v1/chat/completions"
    last_err = "未尝试"

    for ki, key in enumerate(OPENROUTER_KEYS):
        key_id = f"OpenRouter#{ki+1}"
        if key_id in _dead_keys:
            continue

        for model in OPENROUTER_MODELS:
            try:
                body = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }).encode("utf-8")
                req = urllib.request.Request(url, data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {key}",
                        "HTTP-Referer": "https://github.com",
                        "X-Title": "Orthodox News Bot",
                    }, method="POST")
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data["choices"][0]["message"]["content"].strip()
                    return text, f"{key_id}({model})"

            except urllib.error.HTTPError as e:
                try:
                    err_body = e.read().decode("utf-8")[:150]
                except:
                    err_body = ""
                last_err = f"HTTP{e.code}"
                _record_error("OpenRouter", e.code, err_body)

                if e.code in (401, 403, 429):
                    _dead_keys.add(key_id)
                    break
                if e.code == 404:
                    continue
                continue

            except Exception as e:
                last_err = str(e)[:80]
                _record_error("OpenRouter", "EXC", str(e))
                continue

    return None, f"OpenRouter全失败({last_err})"


def ai_call(prompt, max_tokens=600, temperature=0.3):
    """智能调用：Gemini → Groq → OpenRouter，全 dead 立即返回"""
    text, provider = call_gemini(prompt, max_tokens, temperature)
    if text:
        return text, provider

    text2, provider2 = call_groq(prompt, max_tokens, temperature)
    if text2:
        return text2, provider2

    text3, provider3 = call_openrouter(prompt, max_tokens, temperature)
    if text3:
        return text3, provider3

    return None, "全部失败"


def ai_json(prompt, max_tokens=600, temperature=0.3):
    text, provider = ai_call(prompt, max_tokens, temperature)
    if not text:
        return None, provider
    return extract_json(text), provider


def has_alive_provider():
    """是否还有任何活的 Provider 可用"""
    af = sum(1 for i in range(len(GEMINI_FREE_KEYS)) if f"Gemini-Free#{i+1}" not in _dead_keys)
    ap = sum(1 for i in range(len(GEMINI_PAID_KEYS)) if f"Gemini-Paid#{i+1}" not in _dead_keys)
    ag = sum(1 for i in range(len(GROQ_KEYS)) if f"Groq#{i+1}" not in _dead_keys)
    ao = sum(1 for i in range(len(OPENROUTER_KEYS)) if f"OpenRouter#{i+1}" not in _dead_keys)
    return (af + ap + ag + ao) > 0

# ==============================================================
#  翻译
# ==============================================================

def translate_one(title, description):
    prompt = f"""你是专业东正教新闻翻译员。请将以下英文翻译为简体中文。

要求：
1. 翻译自然流畅，符合中文表达
2. 保留专有名词（人名、地名、教会名）的标准中文译名
3. 使用正确的东正教中文术语（如：牧首、都主教、修道院、圣山、神圣会议等）
4. 摘要控制在150字以内

原标题：{title}
原摘要：{description[:400] if description else ''}

严格按以下JSON格式返回，不要任何其他内容：
{{"title_zh": "翻译后的中文标题", "description_zh": "翻译后的中文摘要"}}"""

    data, provider = ai_json(prompt, max_tokens=700, temperature=0.2)
    if data and data.get("title_zh"):
        return data.get("title_zh", ""), data.get("description_zh", ""), provider
    return None, None, provider


def translate_all(articles, cache):
    today = get_athens_today()

    def priority(a):
        date_bonus = 100 if a['athens_date'] == today else 0
        return a['score'] + date_bonus

    candidates = [a for a in articles if a['score'] >= MIN_SCORE_TO_TRANSLATE]
    candidates.sort(key=priority, reverse=True)
    candidates = candidates[:MAX_TRANSLATE_PER_RUN]

    n_cache = n_done = n_fail = 0
    print(f"\n🌐 开始翻译 {len(candidates)} 条新闻...")
    show_alive_keys()

    for i, a in enumerate(candidates):
        if a['id'] in cache:
            c = cache[a['id']]
            a['title_zh'] = c.get('title_zh', '')
            a['description_zh'] = c.get('description_zh', '')
            a['translated'] = bool(a['title_zh'])
            n_cache += 1
            continue

        # 没有可用 Provider 就跳出
        if not has_alive_provider():
            print(f"  ⚠️ 所有 Provider 已耗尽，跳过剩余 {len(candidates)-i} 条")
            break

        print(f"  [{i+1}/{len(candidates)}] {a['title'][:55]}...", end=" ", flush=True)
        title_zh, desc_zh, provider = translate_one(a['title'], a['description'])

        if title_zh:
            a['title_zh'] = title_zh
            a['description_zh'] = desc_zh or ''
            a['translated'] = True
            cache[a['id']] = {
                'title_zh': title_zh,
                'description_zh': desc_zh or '',
                'cached_at': get_athens_now().strftime("%Y-%m-%d %H:%M"),
                'provider': provider,
            }
            n_done += 1
            print(f"✅ {provider}")
        else:
            n_fail += 1
            print(f"❌ {provider}")

        # 每 30 条显示一次存活情况
        if (i + 1) % 30 == 0:
            show_alive_keys()

        time.sleep(0.5)

    print(f"\n📊 翻译: 缓存 {n_cache} | 新译 {n_done} | 失败 {n_fail}")
    show_alive_keys()
    return articles

# ==============================================================
#  社交文案
# ==============================================================

def generate_social_post(article):
    title = article.get('title_zh') or article.get('title', '')
    desc = article.get('description_zh') or article.get('description', '')
    en_title = article.get('title', '')

    prompt = f"""你是专业宗教媒体运营。请根据下面的新闻，为 Facebook 生成3版文案。

新闻标题（中文）：{title}
新闻摘要：{desc[:300]}
原英文标题：{en_title[:200]}

要求生成3个版本：
1. 中文版（适合中文东正教受众，带emoji和hashtag）
2. 希腊语版（地道希腊东正教语气，带emoji和hashtag）
3. 英文版（国际受众，带emoji和hashtag）

每版控制在200字以内，结尾加3-5个相关hashtag。

严格按以下JSON格式返回：
{{
  "zh": "中文FB文案",
  "el": "希腊语FB文案",
  "en": "英文FB文案"
}}"""

    data, _ = ai_json(prompt, max_tokens=900, temperature=0.7)
    return data


def generate_all_social(articles, cache):
    today = get_athens_today()
    candidates = [a for a in articles
                  if a.get('translated') and a['athens_date'] == today]
    candidates.sort(key=lambda x: x['score'], reverse=True)
    candidates = candidates[:SOCIAL_TOP_N]

    print(f"\n📝 生成社交文案: {len(candidates)} 条")
    n_done = n_cache = n_fail = 0

    for i, a in enumerate(candidates):
        cache_key = f"social_{a['id']}"
        if cache_key in cache:
            a['social_post'] = cache[cache_key].get('content', '')
            n_cache += 1
            continue

        if not has_alive_provider():
            print(f"  ⚠️ 所有 Provider 已耗尽，跳过剩余 {len(candidates)-i} 条")
            break

        print(f"  [{i+1}/{len(candidates)}] {(a.get('title_zh') or a['title'])[:50]}...", end=" ", flush=True)
        result = generate_social_post(a)

        if result:
            a['social_post'] = json.dumps(result, ensure_ascii=False)
            cache[cache_key] = {
                'content': a['social_post'],
                'cached_at': get_athens_now().strftime("%Y-%m-%d %H:%M"),
            }
            n_done += 1
            print("✅")
        else:
            n_fail += 1
            print("❌")
        time.sleep(0.5)

    print(f"📊 文案: 缓存 {n_cache} | 新生成 {n_done} | 失败 {n_fail}")
    return articles

# ==============================================================
#  每日简报
# ==============================================================

def generate_daily_briefing(articles):
    today = get_athens_today()
    today_articles = [a for a in articles if a['athens_date'] == today]
    today_articles.sort(key=lambda x: x['score'], reverse=True)
    top = today_articles[:BRIEFING_TOP_N]

    if not top:
        return {"summary": "今日暂无新闻", "highlights": [], "generated_at": "", "based_on_count": 0}

    if not has_alive_provider():
        return {"summary": "AI 服务暂不可用，请稍后查看", "highlights": [], "generated_at": "", "based_on_count": 0}

    news_list = ""
    for i, a in enumerate(top):
        t = a.get('title_zh') or a.get('title', '')
        d = (a.get('description_zh') or a.get('description', ''))[:150]
        news_list += f"\n{i+1}. [{a.get('source_zh') or a['source']}] {t}\n   {d}\n"

    prompt = f"""你是东正教新闻总编。今日（{today}）有以下重要新闻，请生成一份《今日东正教世界简报》。

{news_list}

请严格按以下JSON格式返回：
{{
  "summary": "200字左右的总体概述（中文），分3-4段，涵盖宗教动态、希腊本地、国际局势",
  "highlights": [
    {{"title": "要点1标题", "content": "要点1详情（30字内）", "tag": "宗教|希腊|国际"}},
    {{"title": "要点2标题", "content": "要点2详情", "tag": "宗教|希腊|国际"}},
    {{"title": "要点3标题", "content": "要点3详情", "tag": "宗教|希腊|国际"}}
  ],
  "ops_tips": "针对FB社交媒体运营的3条具体建议（中文，每条50字内）"
}}"""

    print(f"\n📰 生成今日简报...")
    data, provider = ai_json(prompt, max_tokens=1500, temperature=0.5)
    if data:
        data['generated_at'] = get_athens_now().strftime("%Y-%m-%d %H:%M")
        data['based_on_count'] = len(top)
        data['provider'] = provider
        print(f"  ✅ 简报已生成（{provider}）")
        return data

    print(f"  ❌ 简报生成失败")
    return {"summary": "简报生成失败，请稍后重试", "highlights": [], "generated_at": "", "based_on_count": 0}

# ==============================================================
#  主程序
# ==============================================================

def main():
    athens_now = get_athens_now()
    today = get_athens_today()

    print("=" * 70)
    print(f"  ☦️  Orthodox & Greece News Aggregator v5")
    print(f"  ⏰ Athens: {athens_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  🔑 Gemini Free: {len(GEMINI_FREE_KEYS)} | Paid: {len(GEMINI_PAID_KEYS)}")
    print(f"  🔑 Groq: {len(GROQ_KEYS)} | OpenRouter: {len(OPENROUTER_KEYS)}")
    print(f"  📋 模型: Gemini={GEMINI_MODELS} | Groq={GROQ_MODELS}")
    print(f"  📋 OpenRouter={OPENROUTER_MODELS}")
    print("=" * 70)

    print("\n📡 抓取新闻源...")
    all_articles = []
    source_stats = {}
    for source in NEWS_SOURCES:
        items = fetch_feed(source)
        all_articles.extend(items)
        cat = source['category']
        if cat not in source_stats:
            source_stats[cat] = {"count": 0, "sources": []}
        source_stats[cat]["count"] += len(items)
        source_stats[cat]["sources"].append({
            "name": source['name'],
            "name_zh": source.get('name_zh', source['name']),
            "count": len(items),
            "icon": source['icon'],
        })

    all_articles.sort(key=lambda x: (x.get('athens_date',''), x.get('athens_time','')), reverse=True)

    cache = load_cache()
    print(f"\n📦 缓存: {len(cache)} 条")
    all_articles = translate_all(all_articles, cache)
    all_articles = generate_all_social(all_articles, cache)
    briefing = generate_daily_briefing(all_articles)
    save_cache(cache)

    # 主题统计
    topic_stats = {}
    for a in all_articles:
        for tag in a.get('topic_tags', []):
            topic_stats[tag] = topic_stats.get(tag, 0) + 1

    today_count = sum(1 for a in all_articles if a.get('athens_date') == today)
    translated_total = sum(1 for a in all_articles if a.get('translated'))
    social_total = sum(1 for a in all_articles if a.get('social_post'))
    all_dates = sorted(set(a['athens_date'] for a in all_articles if a.get('athens_date')), reverse=True)

    print(f"\n{'='*70}")
    print(f"📊 最终统计:")
    print(f"  📰 总新闻: {len(all_articles)} | 今日: {today_count}")
    print(f"  🌐 已翻译: {translated_total} | 📝 已生成文案: {social_total}")
    print(f"  📆 日期范围: {len(all_dates)} 天 | 💾 缓存: {len(cache)} 条")
    print(f"  🏷️ 主题数: {len(topic_stats)}")
    print(f"{'='*70}")

    show_alive_keys()
    print_error_stats()

    os.makedirs("site", exist_ok=True)
    output = {
        "last_updated_utc":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "last_updated_athens": athens_now.strftime("%Y-%m-%d %H:%M:%S"),
        "today_athens":        today,
        "total_count":         len(all_articles),
        "today_count":         today_count,
        "translated_count":    translated_total,
        "social_count":        social_total,
        "sources_count":       len(NEWS_SOURCES),
        "available_dates":     all_dates[:30],
        "categories":          CATEGORIES,
        "topics":              TOPIC_META,
        "topic_stats":         topic_stats,
        "source_stats":        source_stats,
        "briefing":            briefing,
        "articles":            all_articles,
    }
    with open("site/news_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 完成！")

if __name__ == "__main__":
    main()
