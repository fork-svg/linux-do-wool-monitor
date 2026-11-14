#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linux.do 羊毛监控 - 自动抓取福利羊毛分类的帖子
提取 URL、Key、Model、说明等关键信息
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# 配置
BASE_URL = "https://linux.do"
CATEGORY_ID = 36  # 福利羊毛分类
OUTPUT_DIR = Path("data")
README_PATH = Path("README.md")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
TIMEOUT = 10  # 请求超时秒数


def fetch_category_topics(page=0):
    """获取福利羊毛分类的帖子列表"""
    # 尝试多种 API 端点格式
    endpoints = [
        f"{BASE_URL}/c/{CATEGORY_ID}.json?page={page}",
        f"{BASE_URL}/c/welfare/{CATEGORY_ID}.json?page={page}",
        f"{BASE_URL}/c/welfare.json?page={page}",
    ]

    for url in endpoints:
        try:
            print(f"  尝试: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            print(f"  状态码: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  响应键: {list(data.keys())}")
                return data
            elif resp.status_code == 404:
                continue
            else:
                print(f"  响应: {resp.text[:200]}")
        except Exception as e:
            print(f"  请求失败: {e}")
            continue

    print("所有端点都失败")
    return None


def fetch_topic_detail(topic_id):
    """获取单个帖子的详细内容"""
    url = f"{BASE_URL}/t/topic/{topic_id}.json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"获取帖子 {topic_id} 详情失败: {e}")
        return None


def extract_urls(text):
    """从文本中提取 URL"""
    if not text:
        return []
    # 匹配 http/https URL
    pattern = r'https?://[^\s<>"\')\]]+'
    urls = re.findall(pattern, text)
    # 清理末尾的标点
    cleaned = []
    for u in urls:
        u = u.rstrip('.,;:!?')
        if u not in cleaned:
            cleaned.append(u)
    return cleaned


def extract_keys(text):
    """从文本中提取 API Key"""
    if not text:
        return []
    keys = []

    # 匹配 sk- 开头的 key (OpenAI 格式)
    sk_pattern = r'sk-[a-zA-Z0-9_-]{20,}'
    keys.extend(re.findall(sk_pattern, text))

    # 匹配 code: 或 key: 后面的内容
    code_pattern = r'(?:code|key|密钥|密码)[：:\s]*[`\s]*([a-zA-Z0-9_-]{16,})[`\s]*'
    for match in re.findall(code_pattern, text, re.IGNORECASE):
        if match not in keys:
            keys.append(match)

    # 匹配代码块中的内容
    codeblock_pattern = r'```(?:\w*\n)?([\s\S]*?)```'
    for block in re.findall(codeblock_pattern, text):
        for line in block.strip().split('\n'):
            line = line.strip()
            if line and len(line) > 10 and not line.startswith('#'):
                if line not in keys:
                    keys.append(line)

    return keys[:5]  # 最多返回5个key


def extract_models(text):
    """从文本中提取模型名称"""
    if not text:
        return []

    models = []

    # 常见模型名称模式
    model_patterns = [
        # OpenAI
        r'gpt-[34][\w.-]*', r'o[13][\w.-]*', r'chatgpt[\w.-]*',
        # Claude
        r'claude[-\s]?[3-9][\w.-]*', r'claude[-\s]?(?:opus|sonnet|haiku)[\w.-]*',
        # Gemini
        r'gemini[-\s]?[\w.]+',
        # DeepSeek
        r'deepseek[\w.-]*', r'ds-[\w.]+',
        # GLM
        r'glm-[\w.]+', r'chatglm[\w.]*',
        # Qwen
        r'qwen[\w.-]*', r'qwq[\w.-]*',
        # Llama
        r'llama[-\s]?[\w.]+',
        # 其他
        r'midjourney', r'stable[-\s]?diffusion', r'dalle[-\s]?[\w.]*',
    ]

    text_lower = text.lower()
    for pattern in model_patterns:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        for m in matches:
            m_clean = m.strip()
            if m_clean and m_clean not in models:
                models.append(m_clean)

    return models[:10]  # 最多返回10个模型


def extract_info_from_topic(topic_data):
    """从帖子数据中提取关键信息"""
    info = {
        "title": "",
        "url": "",
        "author": "",
        "created_at": "",
        "views": 0,
        "likes": 0,
        "replies": 0,
        "tags": [],
        "urls": [],
        "keys": [],
        "models": [],
        "description": "",
    }

    if not topic_data:
        return info

    info["title"] = topic_data.get("title", "")
    info["url"] = f"{BASE_URL}/t/topic/{topic_data.get('id', '')}"
    info["author"] = topic_data.get("poster_username", "") or topic_data.get("created_by", {}).get("username", "")
    info["created_at"] = topic_data.get("created_at", "")
    info["views"] = topic_data.get("views", 0)
    info["likes"] = topic_data.get("like_count", 0)
    info["replies"] = topic_data.get("posts_count", 1) - 1
    info["tags"] = topic_data.get("tags", [])

    # 合并所有帖子内容的文本
    all_text = info["title"] + " "
    posts = topic_data.get("post_stream", {}).get("posts", [])
    for post in posts[:5]:  # 只看前5楼
        raw = post.get("raw", "") or post.get("cooked", "")
        all_text += raw + " "

    # 清理 HTML 标签
    all_text = re.sub(r'<[^>]+>', ' ', all_text)
    all_text = re.sub(r'\[.*?\]', ' ', all_text)

    info["urls"] = extract_urls(all_text)
    info["keys"] = extract_keys(all_text)
    info["models"] = extract_models(all_text)

    # 提取说明（取前200字符）
    desc_pattern = r'[#\s]*(?:说明|介绍|描述|详情|内容|活动|规则)[：:\s]*([\s\S]{10,300}?)(?:\n\n|\n#|$)'
    desc_match = re.search(desc_pattern, all_text, re.IGNORECASE)
    if desc_match:
        info["description"] = desc_match.group(1).strip()[:200]
    else:
        # 取第一段的非标题内容
        lines = [l.strip() for l in all_text.split('\n') if l.strip() and not l.startswith('#')]
        if lines:
            info["description"] = lines[0][:200] if len(lines[0]) > 20 else ' '.join(lines[:3])[:200]

    return info


def load_existing_data():
    """加载已存在的数据"""
    data_file = OUTPUT_DIR / "wools.json"
    if data_file.exists():
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"wools": [], "last_update": None, "total_fetched": 0}


def save_data(data):
    """保存数据"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    data_file = OUTPUT_DIR / "wools.json"
    data["last_update"] = datetime.now(timezone.utc).isoformat()
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_readme(data):
    """生成 README.md"""
    wools = data.get("wools", [])

    # 按时间排序（新的在前）
    wools_sorted = sorted(wools, key=lambda x: x.get("created_at", ""), reverse=True)

    readme = """# 🐑 Linux.do 羊毛监控

自动监控 [Linux.do 福利羊毛分类](https://linux.do/c/welfare/36) 的帖子，提取 API Key、模型、URL 等关键信息。

**更新频率**: 每 30 分钟自动更新一次

**最后更新**: {last_update}

**统计**: 共收录 **{total}** 条羊毛信息

---

## 📋 羊毛列表

| # | 标题 | 模型 | 作者 | 浏览 | 点赞 | 时间 |
|---|------|------|------|------|------|------|
""".format(
        last_update=data.get("last_update", "N/A")[:19].replace("T", " "),
        total=len(wools),
    )

    for i, w in enumerate(wools_sorted[:100], 1):  # 最多显示100条
        title = w.get("title", "")[:40]
        if len(w.get("title", "")) > 40:
            title += "..."
        title_link = f"[{title}]({w.get('url', '')})"

        models = w.get("models", [])
        models_str = ", ".join(models[:3]) if models else "-"
        if len(models) > 3:
            models_str += f" (+{len(models)-3})"

        author = w.get("author", "-") or "-"
        views = w.get("views", 0)
        likes = w.get("likes", 0)
        created = w.get("created_at", "")[:10]

        readme += f"| {i} | {title_link} | {models_str} | @{author} | {views} | {likes} | {created} |\n"

    readme += """
---

## 🔍 详情

<details>
<summary>点击展开详细信息（含 URL 和 Key）</summary>

"""

    for i, w in enumerate(wools_sorted[:50], 1):  # 详情只显示前50条
        readme += f"### {i}. {w.get('title', '')}\n\n"
        readme += f"- **链接**: {w.get('url', '')}\n"
        readme += f"- **作者**: @{w.get('author', '-')} | **时间**: {w.get('created_at', '')[:10]}\n"
        readme += f"- **浏览**: {w.get('views', 0)} | **点赞**: {w.get('likes', 0)} | **回复**: {w.get('replies', 0)}\n"

        if w.get("tags"):
            readme += f"- **标签**: {', '.join(w.get('tags', []))}\n"

        if w.get("models"):
            readme += f"- **模型**: {', '.join(w.get('models', []))}\n"

        if w.get("urls"):
            readme += f"- **相关URL**:\n"
            for u in w.get("urls", [])[:5]:
                readme += f"  - {u}\n"

        if w.get("keys"):
            readme += f"- **Key**:\n"
            for k in w.get("keys", [])[:3]:
                # 部分隐藏 key
                if len(k) > 10:
                    masked = k[:6] + "****" + k[-4:]
                else:
                    masked = "****"
                readme += f"  - `{masked}`\n"

        if w.get("description"):
            readme += f"- **说明**: {w.get('description', '')[:150]}\n"

        readme += "\n"

    readme += """</details>

---

## ⚙️ 工作原理

1. 每 30 分钟通过 GitHub Actions 自动运行
2. 抓取 Linux.do 福利羊毛分类的最新帖子
3. 从帖子内容中提取:
   - 📎 URL 链接
   - 🔑 API Key (自动部分隐藏)
   - 🤖 模型名称 (GPT, Claude, Gemini 等)
   - 📝 说明描述
4. 更新 README.md 和本地 JSON 数据

---

## 📊 数据来源

- **论坛**: [Linux.do](https://linux.do)
- **分类**: [福利羊毛](https://linux.do/c/welfare/36)
- **API**: Discourse JSON API

---

## ⚠️ 免责声明

本项目仅供信息聚合和學習交流使用。使用任何 API Key 前请确认其合法性和使用条款。

---

*Last updated: {last_update}*
""".format(last_update=data.get("last_update", "N/A"))

    with open(README_PATH, 'w', encoding='utf-8') as f:
        f.write(readme)


def main():
    print("=" * 50)
    print("🐑 Linux.do 羊毛监控")
    print("=" * 50)

    # 加载已有数据
    data = load_existing_data()
    existing_ids = {w.get("topic_id") for w in data.get("wools", [])}
    print(f"已有数据: {len(existing_ids)} 条")

    new_count = 0
    # 抓取前3页帖子
    for page in range(3):
        print(f"\n抓取第 {page + 1} 页...")
        topics_data = fetch_category_topics(page)

        if not topics_data or "topic_list" not in topics_data:
            print(f"第 {page + 1} 页获取失败，跳过")
            continue

        topics = topics_data.get("topic_list", {}).get("topics", [])
        print(f"  发现 {len(topics)} 个帖子")

        for topic in topics:
            topic_id = topic.get("id")
            if topic_id in existing_ids:
                print(f"  - 跳过已存在: {topic.get('title', '')[:30]}...")
                continue

            print(f"  + 获取详情: {topic.get('title', '')[:30]}...")
            detail = fetch_topic_detail(topic_id)

            if detail:
                info = extract_info_from_topic(detail)
                info["topic_id"] = topic_id
                data["wools"].append(info)
                existing_ids.add(topic_id)
                new_count += 1

                # 显示提取结果
                if info["models"]:
                    print(f"    模型: {', '.join(info['models'][:3])}")
                if info["urls"]:
                    print(f"    URL: {len(info['urls'])} 个")
                if info["keys"]:
                    print(f"    Key: {len(info['keys'])} 个")

                time.sleep(0.5)  # 避免请求过快

        time.sleep(1)  # 页间延迟

    # 保存数据
    data["total_fetched"] = data.get("total_fetched", 0) + new_count
    save_data(data)
    print(f"\n✅ 新增 {new_count} 条，总计 {len(data['wools'])} 条")

    # 生成 README
    generate_readme(data)
    print(f"✅ README.md 已更新")


if __name__ == "__main__":
    main()
