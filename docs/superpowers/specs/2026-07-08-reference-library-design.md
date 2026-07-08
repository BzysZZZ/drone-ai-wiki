# 参考文献资料库页面设计

日期：2026-07-08
项目：drone-ai-wiki
状态：已确认设计，等待实现计划

## 背景

当前知识库是静态 Wiki 页面加 Flask/SQLite 动态笔记后端。页面由 `build_site.py` 从 `wiki/`、`raw/` 和根目录 Markdown 构建到 `site/`，右侧划线笔记通过 Flask API 保存到 SQLite。

新增功能目标是提供一个私有的“参考文献/资料地址”页面，用来手动记录看到的论文、文档、博客、视频、代码仓库等资料地址。用户希望保留一个大的文本编辑入口，但界面更像资料库，可以搜索、按标签查看、导出 Markdown，并方便未来迁移到新服务器。

## 目标

1. 新增一个“参考文献”页面，登录后才能查看和编辑。
2. 使用一个 Markdown 大文本域作为唯一编辑入口，降低录入成本。
3. 将 Markdown 自动解析成资料卡片列表，右侧作为主要资料库视图。
4. 支持搜索、标签筛选、打开链接、复制/导出 Markdown。
5. 数据保存在 SQLite 中，便于云端持久化；同时支持 Markdown 导出，便于迁移和备份。
6. 与现有 Flask 登录机制、构建脚本和导航结构保持一致。

## 非目标

1. 第一版不做逐条资料的独立 CRUD 表单。
2. 第一版不做自动抓取网页标题、摘要、favicon 或论文元数据。
3. 第一版不做 BibTeX、Zotero、EndNote 格式同步。
4. 第一版不做多用户权限模型，继续沿用当前单密码登录机制。
5. 第一版不做版本历史和回滚；后续可扩展。

## 录入格式

用户在 Markdown 文本域中维护资料，推荐一行一条：

```markdown
- [PX4 官方文档](https://docs.px4.io/) #px4 #飞控 官方文档入口
- [ROS2 Tutorials](https://docs.ros.org/) #ros2 #教程 从基础节点开始看
- [A Survey of UAV Autonomous Landing](https://example.com/paper.pdf) #论文 #精准降落 待读
```

解析规则：

1. 匹配 `- [标题](URL)` 作为主要资料条目。
2. 行内 `#标签` 解析为标签列表。
3. 去除标题、URL 和标签后剩余文本作为备注。
4. 无法完整匹配的行不丢弃，显示在“未解析行”提示区，并仍然随原文保存。
5. 空行和普通 Markdown 标题可保留在原文中；第一版预览重点展示可解析条目。

## 页面体验

页面采用资料库优先布局：

1. 左侧窄栏：原始 Markdown 文本域、保存按钮、保存状态、导出按钮。
2. 右侧主区：搜索框、标签筛选、条目统计、资料卡片列表。
3. 未登录状态：不展示任何参考文献内容，只显示登录提示，并复用现有登录流程。
4. 空内容状态：显示一段示例 Markdown，提示用户可以直接粘贴资料地址。
5. 移动端：上下布局，文本域在上，资料库视图在下。

资料卡片展示：

1. 标题。
2. URL 域名或完整链接。
3. 标签 chip。
4. 备注。
5. 打开链接按钮。

交互行为：

1. 文本域内容变化时，右侧预览实时更新。
2. 点击保存后写入后端 SQLite。
3. 搜索匹配标题、URL、标签和备注。
4. 点击标签后只显示该标签条目，再次点击或清除筛选恢复全部。
5. 导出 Markdown 从后端下载当前保存版本，避免导出未保存的误操作；前端可提示“有未保存修改”。

## 数据模型

新增 SQLite 表 `reference_documents`，保存整份 Markdown 文本：

```sql
CREATE TABLE IF NOT EXISTS reference_documents (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

说明：

1. 第一版只有一份参考文献文档，因此固定 `id = 1`。
2. 保存整份 Markdown，而不是逐条拆表，保持数据模型简单。
3. 解析结果由前端即时计算，不作为持久化数据。
4. 未来可以在保留该表的基础上增加版本表或条目表。

## API 设计

沿用现有登录状态和 `require_login` 机制。

### GET /api/references

读取当前 Markdown 内容。

响应：

```json
{
  "content": "- [PX4 官方文档](https://docs.px4.io/) #px4 官方文档入口",
  "updated_at": "2026-07-08T10:00:00Z"
}
```

未登录返回 `401 authentication_required`。

### PUT /api/references

保存整份 Markdown。

请求：

```json
{
  "content": "- [PX4 官方文档](https://docs.px4.io/) #px4 官方文档入口"
}
```

响应：

```json
{
  "ok": true,
  "updated_at": "2026-07-08T10:00:00Z"
}
```

约束：

1. `content` 必须是字符串。
2. 第一版设置合理大小上限，例如 2 MB，避免误粘超大内容拖垮 SQLite 和浏览器。

### GET /api/references/export.md

下载当前保存版本的 Markdown。

响应头：

```text
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="references.md"
```

未登录返回 `401 authentication_required`。

## 构建集成

新增 `wiki/references.md`，用于生成 `site/references.html` 并进入左侧导航。

`build_site.py` 调整：

1. `TITLE_MAP` 增加 `references.md` 到“参考文献”。
2. `get_nav_group` 或页面收集逻辑增加“工具 · 私有”或“系统文件”中的参考文献入口。
3. 对 `references.md` 生成的页面注入参考文献应用容器。
4. 页面引入 `assets/references.css` 和 `assets/references.js`。
5. 构建时复制新增资源到 `site/assets/`。

参考文献页面 Markdown 可以很薄，只作为构建入口：

```markdown
# 参考文献

<div id="references-app"></div>
```

如果保持 Markdown 纯净，也可以让 `build_site.py` 在该页面正文后注入容器。

## 前端模块

新增：

1. `assets/references.js`
2. `assets/references.css`

`references.js` 负责：

1. 判断当前页面是否存在 `#references-app`。
2. 调用 `/api/me` 判断登录状态。
3. 登录后调用 `/api/references` 加载内容。
4. 渲染文本域、操作栏、搜索、标签筛选、卡片列表。
5. 实时解析 Markdown 行。
6. 保存内容到 `/api/references`。
7. 跳转 `/api/references/export.md` 下载 Markdown。

解析函数保持纯函数，方便测试和后续迁移：

```text
parseReferences(markdown) -> { items, warnings, tags }
```

## 错误处理

1. 未登录：页面仅显示登录提示，不请求参考文献内容。
2. 加载失败：显示错误信息和重试按钮。
3. 保存失败：不清空文本域，保留本地内容，提示失败原因。
4. 有未保存修改：显示状态提示；离开页面前可以提示确认。
5. 解析警告：显示未解析行数量和示例，不阻止保存。
6. 导出失败：提示先登录或稍后重试。

## 测试计划

后端单元测试：

1. 未登录访问 `GET /api/references` 返回 401。
2. 登录后 `GET /api/references` 返回默认空内容。
3. 登录后 `PUT /api/references` 保存内容成功。
4. 保存后再次读取内容一致。
5. `GET /api/references/export.md` 返回 Markdown 下载响应。
6. 超过大小上限的内容返回 400。

前端验证：

1. `node --check assets/references.js`。
2. 构建后确认 `site/references.html` 存在。
3. 构建后确认 `site/assets/references.js` 和 `site/assets/references.css` 存在。
4. 本地 Flask 服务验证 `/references.html`、`/api/references`、`/api/references/export.md`。
5. 手动验证未登录不可见、登录后可保存、刷新后内容仍在。

## 部署和迁移影响

新增数据仍在 SQLite 中。后续部署时需要继续避免覆盖 `server/data/annotations.db`。如果参考文献数据和划线笔记共用同一个数据库，则现有备份流程自动包含参考文献内容。

迁移时需备份：

```text
/var/www/drone-ai-wiki/server/data/annotations.db
```

导出的 `references.md` 是额外保险，方便在数据库迁移失败时恢复资料文本。

## 后续扩展

1. 保存历史版本和回滚。
2. 按条目结构化存储，支持阅读状态、重要程度、来源类型。
3. 自动抓取网页标题和摘要。
4. BibTeX 导入导出。
5. 按 Wiki 页面关联参考资料。
6. 与右侧划线笔记联动，把某条参考资料挂到具体知识点页面。