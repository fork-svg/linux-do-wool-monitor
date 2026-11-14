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

    # 解析消息
    # Telegram 预览页面的消息结构
    msg_pattern = r'<div class="tgme_widget_message_text[^>]*>([^<]*(?:<[^>]+>[^<]*)*)</div>'
    for match in re.finditer(msg_pattern, html, re.DOTALL):
        content = match.group(1)
        # 清理 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', content)
        text = text.strip()
        if text and len(text) > 20:
            messages.append({"text": text, "source": "telegram"})

    # 尝试另一种模式
    if not messages:
        msg_pattern2 = r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>'
        for match in re.finditer(msg_pattern2, html, re.DOTALL):
            content = match.group(1)
            text = re.sub(r'<[^>]+>', ' ', content).strip()
            if text and len(text) > 20:
                messages.append({"text": text, "source": "telegram"})

    # 如果还是空，尝试更宽松的匹配
    if not messages:
        # 提取所有看起来像帖子的内容
        post_blocks = re.findall(r'data-post="[^"]+">(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
        for block in post_blocks:
            text = re.sub(r'<[^>]+>', ' ', block).strip()
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 50 and ('key' in text.lower() or 'api' in text.lower() or '模型' in text or '免费' in text):
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
    model_patterns = [
        r'gpt-[34][\w.-]*', r'o[13][\w.-]*', r'chatgpt[\w.-]*',
        r'claude[-\s]?[3-9][\w.-]*', r'claude[-\s]?(?:opus|sonnet|haiku)[\w.-]*',
        r'gemini[-\s]?[\w.]+', r'deepseek[\w.-]*', r'ds-[\w.]+',
        r'glm-[\w.]+', r'qwen[\w.-]*', r'llama[-\s]?[\w.]+',
        r'midjourney', r'dalle[-\s]?[\w.]*',
    ]
    for pattern in model_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            m_clean = m.strip()
            if m_clean and m_clean not in models:
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


def main():
    print("=" * 50)
    print("🐑 Linux.do 羊毛监控")
    print("=" * 50)

    # 加载已有数据
    data = load_existing_data()
    existing_texts = {w.get("description", "")[:100] for w in data.get("wools", [])}
    print(f"已有数据: {len(existing_texts)} 条\n")

    # 获取消息
    messages = fetch_telegram_messages()
    print(f"\n共获取 {len(messages)} 条消息")

    new_count = 0
    for msg in messages:
        text = msg.get("text", "")
        text_hash = text[:100]

        if text_hash in existing_texts:
            continue

        # 检查是否是羊毛相关
        wool_keywords = ['api', 'key', '模型', '免费', '羊毛', '福利', 'gpt', 'claude', 'gemini', 'deepseek']
        if not any(kw in text.lower() for kw in wool_keywords):
            continue

        # 提取信息
        info = {
            "title": text[:50].replace('\n', ' '),
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
            existing_texts.add(text_hash)
            new_count += 1
            print(f"  + {info['title'][:40]}...")
            if info["models"]:
                print(f"    模型: {info['models'][:3]}")
            if info["keys"]:
                print(f"    Keys: {len(info['keys'])} 个")

    # 保存数据
    data["total_fetched"] = data.get("total_fetched", 0) + new_count
    save_data(data)
    print(f"\n✅ 新增 {new_count} 条，总计 {len(data['wools'])} 条")

    # 生成 README
    generate_readme(data)
    print("✅ README.md 已更新")


if __name__ == "__main__":
    main()
