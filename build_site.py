#!/usr/bin/env python3
"""将 Markdown Wiki 编译为可学习的静态 HTML 网站"""

import os
import re
import shutil
import markdown
from pathlib import Path

BASE_DIR = Path(__file__).parent
SITE_DIR = BASE_DIR / "site"
WIKI_DIR = BASE_DIR / "wiki"
RAW_DIR = BASE_DIR / "raw"
ASSETS_DIR = BASE_DIR / "assets"

# ===== 中文标题映射表 =====
TITLE_MAP = {
    "references.md": "参考文献",
    # 概念页
    "concepts/concept-object-detection.md": "目标检测算法",
    "concepts/concept-slam.md": "SLAM 同步定位与建图",
    "concepts/concept-path-planning.md": "路径规划算法",
    "concepts/concept-drone-control.md": "无人机飞控与控制",
    "concepts/concept-multi-sensor-fusion.md": "多传感器融合",
    "concepts/concept-reinforcement-learning.md": "强化学习",
    "concepts/method-model-deployment.md": "模型部署与推理加速",
    "concepts/concept-mqtt-engineering.md": "MQTT 工程开发教程",

    # 基本功概念页（新增）
    "concepts/concept-deep-learning-basics.md": "深度学习理论基础",
    "concepts/concept-training-methods.md": "训练方法与调优",
    "concepts/concept-model-evaluation.md": "模型评估指标体系",
    "concepts/concept-hyperparameter-tuning.md": "超参数调优实战",
    "concepts/concept-ai-interview-qa.md": "算法面试高频题",
    "concepts/concept-math-foundation.md": "数学基础（线代/概率/优化）",
    "concepts/concept-cv-classic-backbones.md": "经典骨干网络谱系",
    "concepts/concept-loss-functions.md": "损失函数大全",
    "concepts/concept-classical-ml-foundations.md": "经典机器学习基本功",
    "concepts/concept-vision-geometry-foundations.md": "视觉几何基本功",
    "concepts/concept-state-estimation-foundations.md": "状态估计基本功",
    "concepts/concept-planning-control-foundations.md": "规划与控制基本功",

    # 实体页
    "entities/dataset-visdrone.md": "VisDrone 数据集",
    "entities/dataset-dota.md": "DOTA 遥感数据集",
    "entities/product-px4-autopilot.md": "PX4 飞控固件",
    "entities/product-ros2.md": "ROS2 工程开发教程",
    "entities/org-eth-asl.md": "ETH Zurich ASL 实验室",
    "entities/org-zhejiang-u-fast-lab.md": "浙大 FAST-Lab",

    # 主题页
    "topics/roadmap-drone-ai-engineer.md": "无人机AI学习路线图",
    "topics/topic-perception-stack.md": "感知系统全栈",
    "topics/topic-slam-systems-comparison.md": "SLAM 系统选型对比",
    "topics/topic-sim-to-real.md": "仿真到真机 (Sim-to-Real)",

    # 项目专题页
    "topics/topic-license-plate-recognition.md": "车牌识别系统",
    "topics/topic-illegal-parking-system.md": "车辆违停取证系统",
    "topics/topic-crack-detection.md": "无人机道路裂缝检测",
    "topics/topic-precision-localization.md": "无人机精准定位系统",
    "topics/topic-precision-localization-code.md": "精准降落实际代码解析",

    # 基本功专题
    "topics/topic-ai-fundamentals-roadmap.md": "AI算法工程师基本功路线",
    "topics/topic-foundational-reading-list.md": "基本功书单与经典论文路线",

    # raw 资料
    "raw/project-license-plate-recognition.md": "车牌识别 — 原始技术资料",
    "raw/project-illegal-parking.md": "违停取证 — 原始技术资料",
    "raw/project-crack-detection.md": "裂缝检测 — 原始技术资料",
    "raw/project-precision-localization.md": "精准定位 — 原始技术资料",
    "raw/precision-landing-mqtt-code.txt": "精准降落实际代码",
    "raw/pascanu13.pdf": "Pascanu 2013 — 梯度裁剪论文",

    # 根文件
    "SCHEMA.md": "知识库规则配置",
    "resume-projects.md": "简历项目描述模板",
}

# 页面元数据：从文件名推断标题和分组
def infer_title(path: Path) -> str:
    """先查中文映射表，没有则用 kebab-case → Title Case 推断"""
    # 构建相对路径 key
    rel = str(path.relative_to(path.parent.parent)).replace("\\", "/") if path.parent.parent else ""
    # 尝试直接匹配文件名
    for key, title in TITLE_MAP.items():
        if str(path).replace("\\", "/").endswith(key):
            return title
    # fallback
    stem = path.stem
    for prefix in ["concept-", "method-", "dataset-", "org-", "product-", "topic-", "entities/", "concepts/", "topics/"]:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    return stem.replace("-", " ").title()

def get_nav_group(rel: str) -> str:
    if rel.startswith("concepts/"):
        return "概念 · 理论"
    elif rel.startswith("entities/"):
        return "实体 · 工具"
    elif rel.startswith("topics/"):
        return "专题 · 项目"
    elif rel == "index.md":
        return "index"
    elif rel == "references.md":
        return "工具 · 私有"
    else:
        return "其他"

# 收集所有页面
def collect_pages():
    pages = {}
    # Wiki pages
    for md in sorted(WIKI_DIR.rglob("*.md")):
        rel = str(md.relative_to(WIKI_DIR)).replace("\\", "/")
        pages[rel] = {
            "path": md,
            "title": infer_title(md),
            "group": get_nav_group(rel),
            "url": rel.replace(".md", ".html"),
        }
    # Raw pages
    for md in sorted(RAW_DIR.glob("*.md")):
        rel = "raw/" + md.name
        pages[rel] = {
            "path": md,
            "title": infer_title(md),
            "group": "原始资料",
            "url": rel.replace(".md", ".html"),
        }
    # Root pages
    for md in [BASE_DIR / "SCHEMA.md", BASE_DIR / "resume-projects.md"]:
        if md.exists():
            pages[md.name] = {
                "path": md,
                "title": infer_title(md),
                "group": "系统文件",
                "url": md.name.replace(".md", ".html"),
            }
    return pages


def convert_wiki_links(text: str, pages: dict, url_prefix: str = "") -> str:
    """将 [[path]] Wiki 链接转为 HTML <a> 标签"""
    def replace_link(m):
        target = m.group(1).strip()
        # 处理相对路径
        if target.startswith("../"):
            target = target[3:]
        # 确定 URL
        if target.endswith(".md"):
            url = target.replace(".md", ".html")
        else:
            url = target + ".html"
        # 查找标题
        display = target.split("/")[-1].replace(".md", "").replace("-", " ").title()
        for k, v in pages.items():
            if k == target or k.endswith("/" + target) or k == target + ".md":
                display = v["title"]
                break
        return f'<a href="{url_prefix}{url}" class="wiki-link">{display}</a>'

    return re.sub(r'\[\[([^\]]+)\]\]', replace_link, text)


def build_page(md_path: Path, rel_key: str, pages: dict) -> str:
    """将单个 Markdown 文件转换为完整 HTML"""
    with open(md_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # 计算相对路径前缀（修复子目录页面的侧边栏及正文链接）
    page_url = pages[rel_key]["url"]
    depth = page_url.count("/")
    url_prefix = "../" * depth if depth > 0 else ""

    # 转换 Wiki 链接（传入 url_prefix）
    raw = convert_wiki_links(raw, pages, url_prefix)

    # Markdown to HTML
    md = markdown.Markdown(extensions=["tables", "fenced_code", "codehilite", "toc"])
    body = md.convert(raw)

    title = pages[rel_key]["title"]
    group = pages[rel_key]["group"]
    is_references_page = rel_key == "references.md"
    reference_head_assets = (
        f'\n<link rel="stylesheet" href="{url_prefix}assets/references.css">'
        if is_references_page else ""
    )
    reference_script = (
        f'\n<script src="{url_prefix}assets/references.js" defer></script>'
        if is_references_page else ""
    )
    # 构建侧边栏
    nav_items = []
    ordered_groups = ["index", "概念 · 理论", "实体 · 工具", "专题 · 项目", "工具 · 私有", "原始资料", "系统文件"]
    for g in ordered_groups:
        items = [(k, v) for k, v in pages.items() if v["group"] == g and k != "index.md"]
        if items:
            nav_items.append(f'<div class="nav-group-title">{g}</div>')
            for k, v in items:
                active = ' class="active"' if k == rel_key else ""
                nav_items.append(f'<a href="{url_prefix}{v["url"]}"{active}>{v["title"]}</a>')

    nav_html = "\n".join(nav_items)

    annotation_panel_html = """
<aside class="annotation-panel" data-annotation-panel>
    <div class="annotation-panel-header">
        <div class="annotation-panel-title">划线笔记</div>
        <button class="annotation-toggle" data-annotation-toggle type="button" aria-label="切换笔记栏" aria-expanded="true">›</button>
    </div>
    <div class="annotation-panel-body" data-annotation-panel-body>
        <div class="annotation-empty">正在连接笔记服务...</div>
    </div>
</aside>
<div class="annotation-toolbar" data-annotation-toolbar></div>
"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — 无人机 AI 算法知识库</title>
<link rel="icon" type="image/svg+xml" href="{url_prefix}assets/favicon.svg">
<link rel="stylesheet" href="{url_prefix}assets/annotations.css">{reference_head_assets}
<style>
:root {{
    --bg: #ffffff;
    --sidebar-bg: #f6f8fa;
    --text: #24292f;
    --text-secondary: #57606a;
    --border: #d0d7de;
    --accent: #0969da;
    --accent-light: #ddf4ff;
    --code-bg: #f6f8fa;
    --table-stripe: #f6f8fa;
    --warning-bg: #fff8c5;
    --warning-border: #d4a72c;
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #0d1117;
        --sidebar-bg: #161b22;
        --text: #c9d1d9;
        --text-secondary: #8b949e;
        --border: #30363d;
        --accent: #58a6ff;
        --accent-light: #0d419d;
        --code-bg: #161b22;
        --table-stripe: #161b22;
        --warning-bg: #282800;
        --warning-border: #d4a72c;
    }}
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.7;
    display: flex;
    min-height: 100vh;
}}

/* 侧边栏 */
.sidebar {{
    width: 280px;
    min-width: 280px;
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border);
    padding: 24px 0;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
}}

.sidebar-header {{
    padding: 0 20px 16px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 8px;
}}

.sidebar-header h1 {{
    font-size: 18px;
    color: var(--text);
    font-weight: 700;
}}

.sidebar-header .subtitle {{
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 4px;
}}

.nav-group-title {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
    padding: 16px 20px 6px;
    font-weight: 600;
}}

.sidebar a {{
    display: block;
    padding: 6px 20px;
    color: var(--text);
    text-decoration: none;
    font-size: 14px;
    transition: background 0.15s;
    border-left: 3px solid transparent;
}}

.sidebar a:hover {{
    background: var(--accent-light);
    border-left-color: var(--accent);
    color: var(--accent);
}}

.sidebar a.active {{
    background: var(--accent-light);
    border-left-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
}}

.sidebar .index-link {{
    font-weight: 600;
    font-size: 15px;
    padding: 8px 20px;
    margin-bottom: 4px;
}}

/* 主内容区 */
.main {{
    flex: 1 1 auto;
    min-width: 0;
    width: 100%;
    padding: 40px 48px 80px;
    overflow-x: auto;
}}

.main h1 {{
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 8px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
}}

.main h2 {{
    font-size: 24px;
    font-weight: 600;
    margin-top: 32px;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
}}

.main h3 {{
    font-size: 20px;
    font-weight: 600;
    margin-top: 24px;
    margin-bottom: 8px;
}}

.main h4 {{
    font-size: 16px;
    font-weight: 600;
    margin-top: 20px;
    margin-bottom: 6px;
}}

.main p {{
    margin-bottom: 12px;
}}

.main ul, .main ol {{
    margin-bottom: 12px;
    padding-left: 24px;
}}

.main li {{
    margin-bottom: 4px;
}}

.main blockquote {{
    border-left: 4px solid var(--accent);
    padding: 8px 16px;
    margin: 16px 0;
    background: var(--accent-light);
    color: var(--text-secondary);
    border-radius: 0 6px 6px 0;
}}

.main blockquote p:last-child {{
    margin-bottom: 0;
}}

.main code {{
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
}}

.main pre {{
    background: var(--code-bg);
    padding: 16px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 16px 0;
    border: 1px solid var(--border);
}}

.main pre code {{
    background: none;
    padding: 0;
    font-size: 13px;
    line-height: 1.6;
}}

.main table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 14px;
}}

.main th {{
    background: var(--sidebar-bg);
    font-weight: 600;
    text-align: left;
    padding: 10px 14px;
    border: 1px solid var(--border);
}}

.main td {{
    padding: 10px 14px;
    border: 1px solid var(--border);
}}

.main tr:nth-child(even) td {{
    background: var(--table-stripe);
}}

.main hr {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 32px 0;
}}

.main a.wiki-link {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 500;
}}

.main a.wiki-link:hover {{
    text-decoration: underline;
}}

.main a[href^="http"] {{
    color: var(--accent);
}}

.main strong {{
    font-weight: 600;
}}

.page-meta {{
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 24px;
    padding: 8px 16px;
    background: var(--sidebar-bg);
    border-radius: 6px;
    border: 1px solid var(--border);
}}

/* 矛盾/警告样式 */
.warning-block {{
    background: var(--warning-bg);
    border: 1px solid var(--warning-border);
    border-radius: 8px;
    padding: 12px 16px;
    margin: 16px 0;
}}

/* 响应式 */
@media (max-width: 768px) {{
    body {{ flex-direction: column; }}
    .sidebar {{
        width: 100%; min-width: 100%; height: auto;
        position: relative; border-right: none; border-bottom: 1px solid var(--border);
        padding: 12px 0;
    }}
    .main {{ padding: 20px 16px 60px; }}
    .main h1 {{ font-size: 24px; }}
    .main h2 {{ font-size: 20px; }}
}}

/* 滚动条 */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--text-secondary); }}
</style>
</head>
<body>
<nav class="sidebar">
    <div class="sidebar-header">
        <h1>📚 无人机AI知识库</h1>
        <div class="subtitle">{len(pages)} 个页面 · 持续积累中</div>
    </div>
    <a href="{url_prefix}index.html" class="index-link{" active" if rel_key == "index.md" else ""}">🏠 知识库首页</a>
    {nav_html}
</nav>
<main class="main">
{body}
</main>
{annotation_panel_html}
<script src="{url_prefix}assets/annotations.js" defer></script>
{reference_script}
<script>
// 高亮当前页面
document.querySelectorAll('.sidebar a').forEach(a => {{
    if (a.getAttribute('href') === window.location.pathname.split('/').pop()) {{
        a.classList.add('active');
    }}
}});

// 所有外部链接在新标签打开
document.querySelectorAll('a[href^="http"]').forEach(a => {{
    a.setAttribute('target', '_blank');
    a.setAttribute('rel', 'noopener');
}});
</script>
</body>
</html>"""


def build_site():
    pages = collect_pages()
    print(f"Found {len(pages)} pages")

    # 清空并创建输出目录
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True)

    # 构建每个页面
    for rel_key, info in pages.items():
        html = build_page(info["path"], rel_key, pages)
        out_path = SITE_DIR / info["url"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [OK] {info['url']} ({info['title']})")

    # 复制 raw 目录下的非 Markdown 附件，供站点直接下载/打开。
    for raw_file in sorted(RAW_DIR.rglob("*")):
        if not raw_file.is_file() or raw_file.suffix.lower() == ".md":
            continue
        rel = raw_file.relative_to(RAW_DIR)
        out_path = SITE_DIR / "raw" / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_file, out_path)
        print(f"  [ASSET] raw/{rel}")


    # 复制前端静态资产。
    if ASSETS_DIR.exists():
        for asset_file in sorted(ASSETS_DIR.rglob("*")):
            if not asset_file.is_file():
                continue
            rel = asset_file.relative_to(ASSETS_DIR)
            out_path = SITE_DIR / "assets" / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset_file, out_path)
            print(f"  [ASSET] assets/{rel}")
    # 确保 index.html 存在
    if not (SITE_DIR / "index.html").exists():
        print("  [WARN] index.html not found")
    else:
        print(f"\n[DONE] Site built: {SITE_DIR}")
        print(f"   {len(pages)} pages total")
        print(f"   Entry: {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    build_site()






