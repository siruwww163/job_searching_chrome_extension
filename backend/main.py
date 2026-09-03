# ============================================================
# 公司背调 Chrome Extension 后端
#
# 功能：
# 1. 接收 Chrome Extension 传来的公司名称
# 2. 优先检查 SQLite 本地缓存，避免重复调用 Tavily 和 Claude
# 3. 没有缓存时，使用 Tavily 搜索公司的公开信息
# 4. 使用 Claude 判断公司类型、规模、所在地和雇主类型
# 5. 将研究结果和 Sources 保存到 SQLite
# 6. 支持 refresh=true 强制重新搜索并更新旧记录
#
# SQLite 的作用：
# - Popup 关闭后研究结果不会丢失
# - 重复搜索同一公司不会重复消耗 API
# - 如果旧结果不准确，可以通过 Refresh Research 重新搜索
# ============================================================

import os
import json
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tavily import TavilyClient
from anthropic import Anthropic


# ------------------------------------------------------------
# 读取 .env
# ------------------------------------------------------------

load_dotenv()


# ------------------------------------------------------------
# SQLite 数据库路径
#
# 数据库会创建在 backend/company_cache.db
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.path.join(
    BASE_DIR,
    "company_cache.db"
)


# ------------------------------------------------------------
# 初始化 SQLite
# ------------------------------------------------------------

def initialize_database():

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS company_cache (
                normalized_company TEXT PRIMARY KEY,
                company_input TEXT NOT NULL,
                report_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                searched_at TEXT NOT NULL
            )
            """
        )

        connection.commit()


initialize_database()


# ------------------------------------------------------------
# 公司名称标准化
#
# 当前先做最安全的处理：
# 去掉首尾空格 + 转成小写
#
# 暂时不自动删除 Inc / LLC 等内容，
# 避免错误地把不同公司合并成同一个缓存记录。
# ------------------------------------------------------------

def normalize_company_name(company: str) -> str:

    return " ".join(
        company.strip().lower().split()
    )


# ------------------------------------------------------------
# 从 SQLite 获取缓存
# ------------------------------------------------------------

def get_cached_company(company: str):

    normalized_company = normalize_company_name(company)

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                company_input,
                report_json,
                sources_json,
                searched_at
            FROM company_cache
            WHERE normalized_company = ?
            """,
            (normalized_company,)
        ).fetchone()

    if row is None:
        return None

    return {
        "report": json.loads(row["report_json"]),
        "sources": json.loads(row["sources_json"]),
        "searched_at": row["searched_at"],
        "from_cache": True
    }


# ------------------------------------------------------------
# 保存 / 更新 SQLite 缓存
# ------------------------------------------------------------

def save_company_cache(
    company: str,
    report: dict,
    sources: list
):

    normalized_company = normalize_company_name(company)

    searched_at = datetime.now(
        timezone.utc
    ).isoformat()

    with sqlite3.connect(DATABASE_PATH) as connection:

        connection.execute(
            """
            INSERT INTO company_cache (
                normalized_company,
                company_input,
                report_json,
                sources_json,
                searched_at
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(normalized_company)
            DO UPDATE SET
                company_input = excluded.company_input,
                report_json = excluded.report_json,
                sources_json = excluded.sources_json,
                searched_at = excluded.searched_at
            """,
            (
                normalized_company,
                company,
                json.dumps(report),
                json.dumps(sources),
                searched_at
            )
        )

        connection.commit()

    return searched_at


# ------------------------------------------------------------
# 初始化 FastAPI
# ------------------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# 初始化 Tavily 和 Claude
# ------------------------------------------------------------

tavily = TavilyClient()

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)


# ------------------------------------------------------------
# Backend 测试
# ------------------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "Company Research backend is running"
    }


# ------------------------------------------------------------
# 公司背调 API
#
# refresh=false:
# 优先使用缓存
#
# refresh=true:
# 忽略缓存，重新调用 Tavily + Claude
# ------------------------------------------------------------

@app.get("/research")
def research_company(
    company: str,
    refresh: bool = False
):

    company = company.strip()


    # --------------------------------------------------------
    # Step 1:
    # 如果不是 Refresh，先检查 SQLite
    # --------------------------------------------------------

    if not refresh:

        cached_result = get_cached_company(company)

        if cached_result is not None:

            print(
                f"Cache hit: {company}"
            )

            return cached_result


    print(
        f"Running new research: {company}"
    )


    # --------------------------------------------------------
    # Step 2:
    # 两个 targeted Tavily searches
    # --------------------------------------------------------

    queries = [
        (
            f'"{company}" official website company LinkedIn '
            f'headquarters employees industry'
        ),
        (
            f'"{company}" employer staffing recruiting '
            f'consulting aggregator legitimacy'
        )
    ]


    # --------------------------------------------------------
    # Step 3:
    # Tavily 搜索 + URL 去重
    # --------------------------------------------------------

    sources = []

    for query in queries:

        search_response = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3
        )

        results = search_response.get(
            "results",
            []
        )

        for item in results:

            url = item.get(
                "url",
                ""
            )

            if not url:
                continue

            if any(
                source["url"] == url
                for source in sources
            ):
                continue

            sources.append({
                "title": item.get(
                    "title",
                    ""
                ),
                "url": url,
                "content": item.get(
                    "content",
                    ""
                )
            })


    # --------------------------------------------------------
    # Step 4:
    # 整理 Sources 给 Claude
    # --------------------------------------------------------

    source_text = ""

    for i, source in enumerate(
        sources,
        start=1
    ):

        source_text += f"""
SOURCE {i}

Title:
{source["title"]}

URL:
{source["url"]}

Content:
{source["content"]}

"""


    # --------------------------------------------------------
    # Step 5:
    # Claude Prompt
    # --------------------------------------------------------

    prompt = f"""
You are helping a job seeker quickly identify a company before applying.

Company searched:
{company}

Use ONLY the supplied web search evidence.

The user wants a quick company verification result, not a long research report.

Determine:

1. What type of company is this?
2. What industry is it in?
3. Approximately how large is it?
4. Where is it headquartered?
5. What country is it primarily based in?
6. Is it the likely direct employer?
7. Is it a staffing/recruiting agency, consulting/staff augmentation
   company, ICC, job board, aggregator, or another intermediary?
8. Is there an important verification concern?

Return valid JSON only.

Use EXACTLY these fields:

{{
    "company": "{company}",
    "company_type": "",
    "employer_type": "",
    "direct_employer": "",
    "industry": "",
    "company_size": "",
    "headquarters": "",
    "primary_base": "",
    "official_website": "",
    "legitimacy_signal": "",
    "verification_confidence": "",
    "warning": ""
}}

For employer_type, choose exactly one:

- Direct Employer
- Staffing / Recruiting Agency
- Consulting / Staff Augmentation
- ICC / IT Consulting
- Job Board / Aggregator
- Lead Generation
- Outsourcing Vendor
- Unknown

For direct_employer, choose exactly one:

- Yes
- Likely Yes
- Likely No
- No
- Unclear

For legitimacy_signal, choose exactly one:

- Established
- Likely Legitimate
- Needs Verification
- High Caution
- Insufficient Information

For verification_confidence, choose exactly one:

- High
- Medium
- Low

IMPORTANT RULES:

- Do not invent information.
- Do not assume a small company is illegitimate.
- Do not assume a staffing or recruiting company is illegitimate.
- Company legitimacy and direct-employer status are different questions.
- Do not call something a scam without strong evidence.
- Prefer official company sources and reputable company profiles.
- Be cautious about similarly named companies.
- Do not treat an unrelated company with a similar name as the same entity.
- If sources disagree about company size, preserve the range and briefly note the conflict.
- If sources disagree about headquarters, say the information conflicts.
- Do not invent an exact employee count.
- If information cannot be determined, return "Not clearly found".

WARNING RULES:

- warning must contain only ONE short sentence.
- warning must be no more than 25 words.
- Mention only the most important concern.
- Do not provide a long explanation.
- Do not provide recommendations or a paragraph.
- If no meaningful concern exists, return:
  "No major concern found."

Return JSON only.
Do not include Markdown.

SOURCES:

{source_text}
"""


    # --------------------------------------------------------
    # Step 6:
    # 调用 Claude
    # --------------------------------------------------------

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )


    # --------------------------------------------------------
    # Step 7:
    # 只提取 Claude TextBlock
    # --------------------------------------------------------

    text_blocks = [
        block.text
        for block in response.content
        if getattr(
            block,
            "type",
            None
        ) == "text"
    ]

    report_text = "\n".join(
        text_blocks
    ).strip()


    # --------------------------------------------------------
    # Step 8:
    # 清理 Markdown JSON fence
    # --------------------------------------------------------

    cleaned_report_text = report_text.strip()

    if cleaned_report_text.startswith(
        "```json"
    ):
        cleaned_report_text = (
            cleaned_report_text[7:]
        )

    elif cleaned_report_text.startswith(
        "```"
    ):
        cleaned_report_text = (
            cleaned_report_text[3:]
        )

    if cleaned_report_text.endswith(
        "```"
    ):
        cleaned_report_text = (
            cleaned_report_text[:-3]
        )

    cleaned_report_text = (
        cleaned_report_text.strip()
    )


    # --------------------------------------------------------
    # Step 9:
    # JSON parsing
    # --------------------------------------------------------

    try:

        report = json.loads(
            cleaned_report_text
        )

    except json.JSONDecodeError:

        print(
            "Claude returned invalid JSON:"
        )

        print(report_text)

        report = {
            "company": company,
            "company_type": "Not clearly found",
            "employer_type": "Unknown",
            "direct_employer": "Unclear",
            "industry": "Not clearly found",
            "company_size": "Not clearly found",
            "headquarters": "Not clearly found",
            "primary_base": "Not clearly found",
            "official_website": "Not clearly found",
            "legitimacy_signal": "Insufficient Information",
            "verification_confidence": "Low",
            "warning": "Could not parse AI response."
        }


    # --------------------------------------------------------
    # Step 10:
    # 缺失字段默认值
    # --------------------------------------------------------

    defaults = {
        "company": company,
        "company_type": "Not clearly found",
        "employer_type": "Unknown",
        "direct_employer": "Unclear",
        "industry": "Not clearly found",
        "company_size": "Not clearly found",
        "headquarters": "Not clearly found",
        "primary_base": "Not clearly found",
        "official_website": "Not clearly found",
        "legitimacy_signal": "Insufficient Information",
        "verification_confidence": "Low",
        "warning": "No major concern found."
    }

    for key, default_value in defaults.items():

        if (
            key not in report
            or report[key] is None
            or report[key] == ""
        ):
            report[key] = default_value


    # --------------------------------------------------------
    # Step 11:
    # 保存到 SQLite
    # --------------------------------------------------------

    searched_at = save_company_cache(
        company=company,
        report=report,
        sources=sources
    )


    # --------------------------------------------------------
    # Step 12:
    # 返回给 Extension
    # --------------------------------------------------------

    return {
        "report": report,
        "sources": sources,
        "searched_at": searched_at,
        "from_cache": False
    }