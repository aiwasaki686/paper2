import requests
import json
from datetime import datetime, timedelta
import os
import re

# -------------------------
# 設定
# --------------------------
TEAMS_WEBHOOK_URL = "https://chuouniv.webhook.office.com/webhookb2/c20db6ac-7e2c-456c-948f-6824def57b98@05bcfdea-243a-4f91-bbd6-49f7fdd85790/IncomingWebhook/23805873668445c88db4f16423a9ff34/85764259-5fc2-4338-b877-563b600528bc/V2bWKI4jyUZDOvPCDEDh3pvXGbS1K72HToFBrWB18rwqw1"

DAYS_BACK = 1
MAX_RESULTS = 20
LAST_DATE_FILE = "last_checked.txt"

THRESHOLD = 2  # スコア閾値（調整ポイント）

# --------------------------
# キーワード定義
# --------------------------

CORE_KEYWORDS = [
    "natural product",
    "peptide",
    "terpene",
    "alkaloid",
    "propanoid",
    "polyketide",
    "macrolide",
    "NRPS",
    "PKS",
    "RIPPS",
    "cyanobacteria",
    "cyanobacterium",
    "sponge"
]

REACTION_KEYWORDS = [
    "NMR", "DFT", "DP4", "CP3",
    "isolation", "toxicity", "biosynthesis"
]

ORGANIC_KEYWORDS = [
    "synthesis"
]

EXCLUDE_STRONG = [
    # 生物
    
    # 医療
   

    # 環境・表面
  
    
    # 材料
  

    # AI
  
]

EXCLUDE_MIDDLE = [
    # supramolecular
   

    # フレームワーク
   

    # 物性
   

    # 分析
   
]

EXCLUDE_WEAK = [
    # 計算
   

    # 総説系
    "review", "perspective", "account",
    "feature article", "minireview",
    "editorial", "commentary"
]

REACTION_LIKE_KEYWORDS = [
    # 基本
   
]

JOURNALS = [
    "Nature", "Nature Communications", "Nature Catalysis", "Nature Chemistry", "Nature Synthesis",
    "Science", "Chem", "Journal of the American Chemical Society", "Journal of Natural Products",
    "Angewandte Chemie International Edition", "Journal of Organic Chemistry",
    "Organic Letters", "Chemical Science", "Chemical Communications"
]

JOURNAL_ABBR = {
    "Organic Letters": "Org. Lett.",
    "Journal of the American Chemical Society": "J. Am. Chem. Soc.",
    "Angewandte Chemie International Edition": "Angew. Chem. Int. Ed.",
    "Chemical Science": "Chem. Sci.",
    "Chemical Communications": "Chem. Commun.",
    "Journal of Organic Chemistry": "J. Org. Chem.",
    "Nature Chemistry": "Nat. Chem.",
    "Nature Communications": "Nat. Commun.",
    "Science": "Science",
    "Chem": "Chem",
    "Journal of Natural Products": "J. Nat. Prod."
}

CORE_REQUIRED_JOURNALS = [
    "Chemical Science",
    "Chemical Communications"
]

def abbreviate_journal(name):
    return JOURNAL_ABBR.get(name, name)

def has_core_keyword(text):
    return any(k in text for k in CORE_KEYWORDS)

# --------------------------
# 前回確認日
# --------------------------
if os.path.exists(LAST_DATE_FILE):
    with open(LAST_DATE_FILE, "r") as f:
        last_checked = f.read().strip()
else:
    last_checked = (datetime.utcnow() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")

# --------------------------
# abstract のHTMLタグ除去
# --------------------------
def clean_abstract(text):
    return re.sub('<.*?>', '', text)

# --------------------------
# 共通テキスト生成
# --------------------------
def build_text(item):
    title = item.get("title", [""])[0].lower()
    abstract = item.get("abstract", "")
    if abstract:
        abstract = clean_abstract(abstract).lower()
    return title + " " + abstract

# --------------------------
# スコアリング
# --------------------------
def score_paper(item):
    text = build_text(item)
    score = 0

    for kw in CORE_KEYWORDS:
        if kw in text:
            score += 7

    for kw in REACTION_KEYWORDS:
        if kw in text:
            score += 2

    for kw in ORGANIC_KEYWORDS:
        if kw in text:
            score += 1
            
    # ------------------
    # 減点
    # ------------------
    for kw in EXCLUDE_STRONG:
        if kw in text:
            score -= 5

    for kw in EXCLUDE_MIDDLE:
        if kw in text:
            score -= 3

    for kw in EXCLUDE_WEAK:
        if kw in text:
            score -= 1

    # ------------------
    # 反応っぽさチェック（超重要）
    # ------------------
    count = sum(1 for k in REACTION_LIKE_KEYWORDS if k in text)

    if count == 0:
        score -= 6
    elif count == 1:
        score -= 2
    else:
        score += 0

    return score

# --------------------------
# ノイズ除外
# --------------------------
#def is_noise(text):
#    return sum(k in text for k in EXCLUDE_KEYWORDS) >= 2

# --------------------------
# CrossRef取得
# --------------------------
def fetch_crossref(journal):
    query = " OR ".join(CORE_KEYWORDS + REACTION_KEYWORDS)
    url = "https://api.crossref.org/works"
    params = {
        "query.title": query,
        "filter": f"from-pub-date:{last_checked},type:journal-article,container-title:{journal}",
        "rows": MAX_RESULTS
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict) and "message" in data:
            return data["message"].get("items", [])
        else:
            return []
    except Exception as e:
        print(f"Error fetching {journal}: {e}")
        return []

# --------------------------
# データ取得
# --------------------------
all_items = []
for journal in JOURNALS:
    all_items.extend(fetch_crossref(journal))

# --------------------------
# フィルタリング
# --------------------------
filtered_items = []

for item in all_items:
    text = build_text(item)
    title = item.get("title", [""])[0].lower()
    journal = item.get("container-title", [""])[0].lower()

#    if is_noise(text):
#        continue

    # --------------------------
    # ⭐ CORE必須ジャーナルフィルタ
    # --------------------------
    if journal in [j.lower() for j in CORE_REQUIRED_JOURNALS]:
        if not has_core_keyword(text):
            continue

    score = score_paper(item)

    if score >= THRESHOLD:
        item["score"] = score
        filtered_items.append(item)

# スコア順にソート
filtered_items.sort(key=lambda x: x["score"], reverse=True)

if not filtered_items:
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "No paper today.",
                            "weight": "Bolder",
                            "size": "Medium"
                        }
                    ]
                }
            }
        ]
    }

    resp = requests.post(TEAMS_WEBHOOK_URL, json=card)
    print("新着なし通知送信:", resp.status_code)
    exit()

# --------------------------
# Adaptive Card
# --------------------------
# Adaptive Card 作成部分（修正版）
def create_adaptive_card(items):
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": []
                }
            }
        ]
    }

    body = card["attachments"][0]["content"]["body"]

    for idx, item in enumerate(items, start=1):
        title = item.get("title", ["No Title"])[0]
        doi = item.get("DOI", "")
        journal_raw = item.get("container-title", ["Unknown Journal"])[0]

        journal = abbreviate_journal(journal_raw)
        doi_url = f"https://doi.org/{doi}" if doi else ""

        # --------------------------
        # CORE判定（ここ重要）
        # --------------------------
        text_lower = title.lower()
        is_core = any(k.lower() in text_lower for k in CORE_KEYWORDS)

        # --------------------------
        # 番号スタイル（COREのみ強調）
        # --------------------------
        number_text = str(idx)

        number_color = "Attention" if is_core else "Default"
        number_weight = "Bolder" if is_core else "Default"

        # --------------------------
        # タイトル
        # --------------------------
        title_text = f"[{title}]({doi_url})" if doi_url else title

        # ==========================
        # ① ヘッダ行（番号 + ジャーナル）
        # ==========================
        body.append({
            "type": "ColumnSet",
            "spacing": "Medium",
            "columns": [
                # 番号（左）
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": number_text,
                            "weight": number_weight,
                            "color": number_color,
                            "size": "Medium",
                            "wrap": False
                        }
                    ]
                },

                # ジャーナル（右）
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": journal,
                            "horizontalAlignment": "Right",
                            "isSubtle": True,
                            "size": "Medium",
                            "wrap": False
                        }
                    ]
                }
            ]
        })

        # ==========================
        # ② タイトル行（別行）
        # ==========================
        body.append({
            "type": "TextBlock",
            "text": title_text,
            "wrap": True,
            "spacing": "None",
            "weight": "Bolder",
            "size": "Medium"
        })

        # ==========================
        # ③ Graphical Abstract（任意）
        # ==========================
        #ga_image_url = item.get("graphical_abstract_url", "")
        #if ga_image_url:
        #    body.append({
        #        "type": "Image",
        #        "url": ga_image_url,
        #        "size": "Medium",
        #        "spacing": "Small",
        #        "altText": "Graphical Abstract"
        #    })

    return card

# --------------------------
# Teams送信
# --------------------------
card = create_adaptive_card(filtered_items[:15])
resp = requests.post(TEAMS_WEBHOOK_URL, json=card)

print(resp.status_code)
print(f"{len(filtered_items)} 件ヒット")

# --------------------------
# 差分更新
# --------------------------
today = datetime.utcnow().strftime("%Y-%m-%d")
with open(LAST_DATE_FILE, "w") as f:
    f.write(today)
