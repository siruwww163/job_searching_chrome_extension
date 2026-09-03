# ============================================================
# 公司背调 Chrome Extension 后端
#
# 功能：
# 1. 接收 Chrome Extension 传来的公司名称
# 2. 使用 Tavily 从多个角度搜索公司的公开信息
# 3. 对搜索结果进行 URL 去重
# 4. 将搜索结果交给 Claude 分析
# 5. 判断公司类型、规模、所在地、Employer Type 和可信度
# 6. 将结构化的公司背调结果返回给 Chrome Extension
#
# 当前版本重点：
# Company Identity + Employer Verification
# ============================================================

import os
import json

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tavily import TavilyClient
from anthropic import Anthropic


# ------------------------------------------------------------
# 读取 .env 中的环境变量
# ------------------------------------------------------------

load_dotenv()


# ------------------------------------------------------------
# 初始化 FastAPI
# ------------------------------------------------------------

app = FastAPI()


# 允许 Chrome Extension 调用本地 FastAPI
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
# 测试 Backend 是否正常运行
# ------------------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Company Research backend is running"
    }


# ------------------------------------------------------------
# 公司背调 API
# ------------------------------------------------------------

@app.get("/research")
def research_company(company: str):

    # --------------------------------------------------------
    # Step 1:
    # 从不同角度搜索公司，而不是把所有问题塞进一个 query
    # --------------------------------------------------------

    # queries = [
    #     f'"{company}" official website company about headquarters founded',
    #     f'"{company}" company size employees industry headquarters',
    #     f'"{company}" staffing recruiting agency consulting jobs',
    #     f'"{company}" careers jobs employer',
    #     f'"{company}" company reviews scam legitimacy'
    # ]
    
    queries = [
        f'"{company}" official website company size headquarters founded industry',
        f'"{company}" staffing recruiting consulting aggregator employer jobs',
        f'"{company}" legitimacy reviews company background'
    ]


    # --------------------------------------------------------
    # Step 2:
    # 执行 Tavily 搜索并收集结果
    # --------------------------------------------------------

    sources = []

    for query in queries:

        search_response = tavily.search(
            query=query,
            search_depth="basic",
            max_results=3
        )

        results = search_response.get("results", [])

        for item in results:

            url = item.get("url", "")

            # URL 为空则跳过
            if not url:
                continue

            # 避免同一个网页重复出现
            if any(source["url"] == url for source in sources):
                continue

            sources.append({
                "title": item.get("title", ""),
                "url": url,
                "content": item.get("content", "")
            })


    # --------------------------------------------------------
    # Step 3:
    # 将搜索结果整理成 Claude 可以阅读的文本
    # --------------------------------------------------------

    source_text = ""

    for i, source in enumerate(sources, start=1):

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
    # Step 4:
    # 要求 Claude 根据搜索证据进行公司身份和雇主类型判断
    # --------------------------------------------------------

    prompt = f"""
You are helping a job seeker verify a company before applying for a job.

Company searched:
{company}

Your primary goal is to determine:

1. What company is this?
2. What does the company actually do?
3. How large is the company?
4. Where is the company headquartered and primarily based?
5. Is it an actual operating employer?
6. Is it a staffing or recruiting company?
7. Is it an IT consulting or staff augmentation company?
8. Does it resemble an ICC / IT consulting company?
9. Is it primarily a job board, aggregator, or lead-generation website?
10. Are there signs that a job seeker should verify it more carefully?

Use ONLY the supplied web search evidence.

Return valid JSON only.

Use this exact structure:

{{
    "company": "{company}",
    # "overview": "",
    "company_type": "",
    "employer_type": "",
    "industry": "",
    "company_size": "",
    # "founded": "",
    "headquarters": "",
    "primary_base": "",
    "official_website": "",
    # "ownership": "",
    "legitimacy_signal": "",
    "verification_confidence": "",
    # "why_this_classification": [],
    # "things_to_verify": []
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

Important rules:

- Do not invent information.
- Do not assume that a small company is illegitimate.
- Do not assume that a staffing or recruiting agency is illegitimate.
- Distinguish company type from legitimacy.
- Do not label a company a scam unless the supplied evidence strongly supports it.
- Prefer official company sources and reputable third-party sources over social media posts.
- If sources conflict, mention the conflict.
- If company size is a range, preserve the range.
- If an exact employee count cannot be verified, do not invent one.
- For headquarters, distinguish headquarters from other office locations.
- primary_base should identify the main country where the company appears to operate.
- If an official website can be identified, return the full URL.
- ownership should describe whether the company appears to be public, private, a subsidiary, or another identifiable ownership structure.
- why_this_classification should contain 2 to 5 short evidence-based reasons.
- things_to_verify should contain practical uncertainties a job seeker should check before applying.
- If information cannot be determined, use "Not clearly found".
- Do not include Markdown.
- Return JSON only.

SOURCES:

{source_text}
"""


    # --------------------------------------------------------
    # Step 5:
    # Claude 阅读搜索结果并生成结构化公司背调报告
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

    text_blocks = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ]

    report_text = "\n".join(text_blocks).strip()


    # --------------------------------------------------------
    # Step 6:
    # 清理 Claude 返回内容，并转换成 Python dictionary
    # --------------------------------------------------------
    cleaned_report_text = report_text.strip()

    # Claude 有时会把 JSON 包在 ```json ... ``` 里面
    if cleaned_report_text.startswith("```json"):
        cleaned_report_text = cleaned_report_text[7:]

    elif cleaned_report_text.startswith("```"):
        cleaned_report_text = cleaned_report_text[3:]

    # 去掉最后的 ```
    if cleaned_report_text.endswith("```"):
        cleaned_report_text = cleaned_report_text[:-3]

    cleaned_report_text = cleaned_report_text.strip()


    try:
        report = json.loads(cleaned_report_text)

    except json.JSONDecodeError:

        print("Claude returned invalid JSON:")
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
    # Step 7:
    # 返回给 Chrome Extension
    # --------------------------------------------------------

    return {
        "report": report,
        "sources": sources
    }