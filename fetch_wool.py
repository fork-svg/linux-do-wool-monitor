#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Linux.do 羊毛监控 - 通过 Telegram 频道获取数据
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# 配置
TELEGRAM_CHANNEL = "linux_do_channel"
TELEGRAM_PREVIEW_URL = f"https://t.me/s/{TELEGRAM_CHANNEL}"
OUTPUT_DIR = Path("data")
README_PATH = Path("README.md")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def fetch_telegram_messages():
    """从 Telegram 公开预览页面获取消息"""
    print(f"获取 Telegram 频道: @{TELEGRAM_CHANNEL}")

    try:
        resp = requests.get(TELEGRAM_PREVIEW_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"请求失败: {e}")
        return []

    messages = []

    # 解析消息 - 使用更宽松的模式
    msg_pattern = r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>'
    for match in re.finditer(msg_pattern, html, re.DOTALL):
        content = match.group(1)
        # 清理 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'\s+', ' ', text).strip()
        if text and len(text) > 10:
            messages.append({"text": text, "source": "telegram"})

    # 如果上面的模式没匹配到，尝试整个消息块
    if not messages:
        # 尝试匹配整个消息块
        block_pattern = r'data-post="[^"]+"[^>]*>(.*?)</div>\s*(?:</div>)?\s*(?:</div>)?'
        for match in re.finditer(block_pattern, html, re.DOTALL):
            content = match.group(1)
            text = re.sub(r'<[^>]+>', ' ', content)
            text = re.sub(r'\s+', ' ', text).strip()
            if text and len(text) > 20:
                messages.append({"text": text, "source": "telegram"})

    # 尝试提取所有文本内容
    if not messages:
        # 提取所有看起来像帖子的内容
        all_text = re.findall(r'>([^<]{20,})<', html)
        for text in all_text:
            text = text.strip()
            if len(text) > 30 and any(kw in text.lower() for kw in ['api', 'key', '模型', '免费', '羊毛', 'gpt', 'claude']):
                messages.append({"text": text, "source": "telegram"})

    print(f"  发现 {len(messages)} 条消息")
    return messages


def fetch_from_web_cache():
    """尝试从 Google Cache 或其他缓存获取"""
    # 尝试从 Web Archive 获取
    print("尝试 Web Archive...")
    try:
        url = f"https://web.archive.org/web/2024/https://linux.do/c/welfare/36.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None


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
    # sk- 开头的 key
    sk_pattern = r'sk-[a-zA-Z0-9_-]{20,}'
    keys.extend(re.findall(sk_pattern, text))
    # code/key 后面的
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
    # 更精确的模式
    model_patterns = [
        r'\bgpt-4[o]?\b', r'\bgpt-4[-\s]?turbo\b', r'\bgpt-4\b',
        r'\bgpt-3\.?5\b', r'\bo1[-\s]?(?:preview|mini)?\b', r'\bo3[-\s]?(?:mini)?\b',
        r'\bclaude[-\s]?(?:3\.5|3|4)?[-\s]?(?:opus|sonnet|haiku)?\b',
        r'\bgemini[-\s]?(?:1\.5|2\.0|pro|flash|ultra)?\b',
        r'\bdeepseek[-\s]?(?:v3|r1|coder|chat)?\b',
        r'\bglm[-\s]?4\b', r'\bqwen[-\s]?(?:max|plus|turbo)?\b',
        r'\bllama[-\s]?3\.?1?\b', r'\bmidjourney\b',
    ]
    for pattern in model_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            m_clean = m.strip()
            if m_clean and m_clean not in models and len(m_clean) < 30:
                models.append(m_clean)
    return models[:10]


def extract_linuxdo_link(text):
    """从文本中提取 linux.do 链接"""
    pattern = r'https://linux\.do/t/topic/\d+'
    matches = re.findall(pattern, text)
    return matches[0] if matches else None


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

    readme = f"""# 🐑 Linux.do 羊毛监控

自动监控 Linux.do 福利羊毛相关帖子，提取 API Key、模型、URL 等关键信息。

**更新频率**: 每 30 分钟自动更新一次

**最后更新**: {(data.get("last_update") or "N/A")[:19].replace("T", " ")}

**统计**: 共收录 **{len(wools)}** 条羊毛信息

---

## 📋 羊毛列表

| # | 标题 | 模型 | 浏览 | 点赞 | 时间 |
|---|------|------|------|------|------|
"""

    for i, w in enumerate(wools_sorted[:100], 1):
        title = w.get("title", "")[:45]
        if len(w.get("title", "")) > 45:
            title += "..."
        url = w.get("url", "")
        title_link = f"[{title}]({url})" if url else title

        models = w.get("models", [])
        models_str = ", ".join(models[:3]) if models else "-"
        if len(models) > 3:
            models_str += f" (+{len(models)-3})"

        views = w.get("views", 0)
        likes = w.get("likes", 0)
        created = w.get("created_at", "")[:10]

        readme += f"| {i} | {title_link} | {models_str} | {views} | {likes} | {created} |\n"

    readme += """
---

## 🔍 详情

<details>
<summary>点击展开详细信息（含 URL 和 Key）</summary>

"""

    for i, w in enumerate(wools_sorted[:50], 1):
        readme += f"### {i}. {w.get('title', '')}\n\n"
        if w.get("url"):
            readme += f"- **链接**: {w.get('url', '')}\n"
        readme += f"- **时间**: {w.get('created_at', '')[:10]}\n"
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
            desc = w.get('description', '')[:200]
            readme += f"- **说明**: {desc}\n"

        readme += "\n"

    readme += """</details>

---

## ⚙️ 工作原理

1. 每 30 分钟通过 GitHub Actions 自动运行
2. 从 Telegram 频道获取最新羊毛信息
3. 从内容中提取:
   - 📎 URL 链接
   - 🔑 API Key (自动部分隐藏)
   - 🤖 模型名称 (GPT, Claude, Gemini 等)
   - 📝 说明描述
4. 更新 README.md 和本地 JSON 数据

---

## 📊 数据来源

- **论坛**: [Linux.do](https://linux.do)
- **Telegram**: [@linux_do_channel](https://t.me/linux_do_channel)

---

## ⚠️ 免责声明

本项目仅供信息聚合和学习交流使用。使用任何 API Key 前请确认其合法性和使用条款。

---

*Last updated: """ + (data.get("last_update") or "N/A") + "*"

    with open(README_PATH, 'w', encoding='utf-8') as f:
        f.write(readme)


def get_clean_title(text):
    """提取干净的标题"""
    # 去掉 "@xxx 在 xxx 中发帖" 前缀
    match = re.search(r'在\s+(.+?)\s+中发帖', text)
    if match:
        title = match.group(1)
        # 截取第一个句号或换行
        title = re.split(r'[。\n]', title)[0]
        return title[:50]
    # 否则取前50字符
    return text[:50].replace('\n', ' ')


def main():
    print("=" * 50)
    print("🐑 Linux.do 羊毛监控")
    print("=" * 50)

    # 加载已有数据
    data = load_existing_data()
    existing_titles = set()
    for w in data.get("wools", []):
        # 用标题去重
        title = w.get("title", "")[:30]
        existing_titles.add(title)
    print(f"已有数据: {len(existing_titles)} 条\n")

    # 获取消息
    messages = fetch_telegram_messages()
    print(f"\n共获取 {len(messages)} 条消息")

    new_count = 0
    for msg in messages:
        text = msg.get("text", "")
        title = get_clean_title(text)
        title_key = title[:30]

        if title_key in existing_titles:
            continue

        # 必须包含明确的福利关键词
        wool_must_have = ['免费', '公益', '福利', '白嫖', '羊毛', '送', '赠送', '分享key', '免费key', '白送']
        has_wool_keyword = any(kw in text.lower() for kw in wool_must_have)

        if not has_wool_keyword:
            continue

        # 排除非福利内容
        exclude_patterns = ['求助', '怎么办', '请问', '问题', 'bug', '报错', '出错了']
        if any(p in text.lower() for p in exclude_patterns):
            continue

        # 提取信息
        info = {
            "title": title,
            "url": extract_linuxdo_link(text) or "",
            "models": extract_models(text),
            "urls": extract_urls(text),
            "keys": extract_keys(text),
            "description": text[:300],
            "views": 0,
            "likes": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "telegram",
        }

        if info["title"]:
            data["wools"].append(info)
            existing_titles.add(title_key)
            new_count += 1
            print(f"  + {info['title'][:50]}")
            if info["models"]:
                print(f"    模型: {info['models'][:3]}")
            if info["keys"]:
                print(f"    Keys: {len(info['keys'])} 个")
            if info["url"]:
                print(f"    URL: {info['url']}")

    # 保存数据
    data["total_fetched"] = data.get("total_fetched", 0) + new_count
    save_data(data)
    print(f"\n✅ 新增 {new_count} 条，总计 {len(data['wools'])} 条")

    # 生成 README
    generate_readme(data)
    print("✅ README.md 已更新")


if __name__ == "__main__":
    main()
