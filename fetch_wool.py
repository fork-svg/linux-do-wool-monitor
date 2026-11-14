#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linux.do 羊毛监控 - 使用 Playwright 绕过 Cloudflare
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 配置
BASE_URL = "https://linux.do"
CATEGORY_ID = 36  # 福利羊毛分类
OUTPUT_DIR = Path("data")
README_PATH = Path("README.md")


def fetch_with_playwright():
    """使用 Playwright 绕过 Cloudflare 获取数据"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("安装 playwright...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        from playwright.sync_api import sync_playwright

    all_topics = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 访问分类页面
        for page_num in range(3):
            url = f"{BASE_URL}/c/welfare/{CATEGORY_ID}"
            if page_num > 0:
                url += f"?page={page_num}"

            print(f"抓取第 {page_num + 1} 页: {url}")

            try:
                page.goto(url, timeout=30000, wait_until="networkidle")
                page.wait_for_timeout(3000)  # 等待 Cloudflare 验证

                # 检查是否通过 Cloudflare
                title = page.title()
                if "moment" in title.lower() or "challenge" in title.lower():
                    print("  Cloudflare 验证中，等待...")
                    page.wait_for_timeout(10000)

                # 获取页面内容
                content = page.content()

                # 检查是否有帖子列表
                if "topic-list" in content or "topic-list-item" in content:
                    print("  ✅ 成功获取页面")

                    # 使用 JavaScript 提取数据
                    topics = page.evaluate("""
                        () => {
                            const items = document.querySelectorAll('.topic-list-item');
                            const results = [];
                            items.forEach(item => {
                                const titleEl = item.querySelector('.title a, .main-link a');
                                const authorEl = item.querySelector('.posters a:last-child');
                                const viewsEl = item.querySelector('.views span');
                                const likesEl = item.querySelector('.likes span');
                                const activityEl = item.querySelector('.activity span');

                                if (titleEl) {
                                    results.push({
                                        title: titleEl.textContent.trim(),
                                        url: titleEl.href,
                                        author: authorEl ? authorEl.textContent.trim() : '',
                                        views: viewsEl ? parseInt(viewsEl.textContent.trim()) || 0 : 0,
                                        likes: likesEl ? parseInt(likesEl.textContent.trim()) || 0 : 0,
                                        activity: activityEl ? activityEl.textContent.trim() : '',
                                    });
                                }
                            });
                            return results;
                        }
                    """)

                    print(f"  发现 {len(topics)} 个帖子")
                    all_topics.extend(topics)
                else:
                    print(f"  ❌ 未找到帖子列表 (title: {title})")

            except Exception as e:
                print(f"  错误: {e}")

        browser.close()

    return all_topics


def extract_urls(text):
    """从文本中提取 URL"""
    if not text:
        return []
    pattern = r'https?://[^\s<>"\')\]]+'
    urls = re.findall(pattern, text)
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
    sk_pattern = r'sk-[a-zA-Z0-9_-]{20,}'
    keys.extend(re.findall(sk_pattern, text))
    code_pattern = r'(?:code|key|密钥|密码)[：:\s]*[`\s]*([a-zA-Z0-9_-]{16,})[`\s]*'
    for match in re.findall(code_pattern, text, re.IGNORECASE):
        if match not in keys:
            keys.append(match)
    return keys[:5]


def extract_models(text):
    """从文本中提取模型名称"""
    if not text:
        return []
    models = []
    model_patterns = [
        r'gpt-[34][\w.-]*', r'o[13][\w.-]*', r'chatgpt[\w.-]*',
        r'claude[-\s]?[3-9][\w.-]*', r'claude[-\s]?(?:opus|sonnet|haiku)[\w.-]*',
        r'gemini[-\s]?[\w.]+',
        r'deepseek[\w.-]*', r'ds-[\w.]+',
        r'glm-[\w.]+', r'chatglm[\w.]*',
        r'qwen[\w.-]*', r'qwq[\w.-]*',
        r'llama[-\s]?[\w.]+',
        r'midjourney', r'stable[-\s]?diffusion', r'dalle[-\s]?[\w.]*',
    ]
    for pattern in model_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            m_clean = m.strip()
            if m_clean and m_clean not in models:
                models.append(m_clean)
    return models[:10]


def fetch_topic_detail(url):
    """获取帖子详情"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(3000)

            content = page.content()

            # 提取帖子文本内容
            text = page.evaluate("""
                () => {
                    const posts = document.querySelectorAll('.cooked, .post-area');
                    return Array.from(posts).map(p => p.textContent).join('\\n');
                }
            """)

            browser.close()
            return text
        except Exception as e:
            print(f"    获取详情失败: {e}")
            browser.close()
            return None


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
    wools_sorted = sorted(wools, key=lambda x: x.get("created_at", "") or "", reverse=True)

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
        last_update=(data.get("last_update") or "N/A")[:19].replace("T", " "),
        total=len(wools),
    )

    for i, w in enumerate(wools_sorted[:100], 1):
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

    for i, w in enumerate(wools_sorted[:50], 1):
        readme += f"### {i}. {w.get('title', '')}\n\n"
        readme += f"- **链接**: {w.get('url', '')}\n"
        readme += f"- **作者**: @{w.get('author', '-')} | **时间**: {w.get('created_at', '')[:10]}\n"
        readme += f"- **浏览**: {w.get('views', 0)} | **点赞**: {w.get('likes', 0)}\n"

        if w.get("models"):
            readme += f"- **模型**: {', '.join(w.get('models', []))}\n"

        if w.get("urls"):
            readme += f"- **相关URL**:\n"
            for u in w.get("urls", [])[:5]:
                readme += f"  - {u}\n"

        if w.get("keys"):
            readme += f"- **Key**:\n"
            for k in w.get("keys", [])[:3]:
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
2. 使用 Playwright 绕过 Cloudflare 保护
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

---

## ⚠️ 免责声明

本项目仅供信息聚合和学习交流使用。使用任何 API Key 前请确认其合法性和使用条款。

---

*Last updated: {last_update}*
""".format(last_update=data.get("last_update", "N/A"))

    with open(README_PATH, 'w', encoding='utf-8') as f:
        f.write(readme)


def main():
    print("=" * 50)
    print("🐑 Linux.do 羊毛监控 (Playwright)")
    print("=" * 50)

    # 加载已有数据
    data = load_existing_data()
    existing_urls = {w.get("url") for w in data.get("wools", [])}
    print(f"已有数据: {len(existing_urls)} 条")

    # 获取帖子列表
    topics = fetch_with_playwright()
    print(f"\n共获取 {len(topics)} 个帖子")

    new_count = 0
    for topic in topics:
        url = topic.get("url", "")
        if url in existing_urls:
            print(f"  跳过已存在: {topic.get('title', '')[:30]}...")
            continue

        print(f"  + {topic.get('title', '')[:40]}...")

        # 获取详情提取更多信息
        detail_text = fetch_topic_detail(url)

        info = {
            "title": topic.get("title", ""),
            "url": url,
            "author": topic.get("author", ""),
            "views": topic.get("views", 0),
            "likes": topic.get("likes", 0),
            "created_at": topic.get("activity", ""),
            "models": [],
            "urls": [],
            "keys": [],
            "description": "",
        }

        if detail_text:
            info["models"] = extract_models(detail_text)
            info["urls"] = extract_urls(detail_text)
            info["keys"] = extract_keys(detail_text)
            info["description"] = detail_text[:200].strip()

        data["wools"].append(info)
        existing_urls.add(url)
        new_count += 1

    # 保存数据
    data["total_fetched"] = data.get("total_fetched", 0) + new_count
    save_data(data)
    print(f"\n✅ 新增 {new_count} 条，总计 {len(data['wools'])} 条")

    # 生成 README
    generate_readme(data)
    print("✅ README.md 已更新")


if __name__ == "__main__":
    main()
