(function () {
    "use strict";

    const app = document.querySelector("[data-references-app]");
    if (!app) return;

    const state = {
        authenticated: false,
        content: "",
        savedContent: "",
        updatedAt: null,
        query: "",
        activeTag: "",
        saving: false,
        error: "",
    };

    async function requestJson(url, options) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: {"Content-Type": "application/json"},
            ...options,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        return data;
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function domainFromUrl(url) {
        try {
            return new URL(url).hostname.replace(/^www\./, "");
        } catch {
            return url;
        }
    }

    function formatBeijingTime(isoString) {
        if (!isoString) return "尚未保存";
        try {
            const date = new Date(isoString);
            return date.toLocaleString("zh-CN", {
                timeZone: "Asia/Shanghai",
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch {
            return isoString;
        }
    }

    function parseReferences(markdown) {
        const items = [];
        const warnings = [];
        const tagSet = new Set();
        const lines = String(markdown || "").split(/\r?\n/);
        const referenceLine = /^\s*[-*]\s+\[([^\]]+)\]\(([^)]+)\)\s*(.*)$/;
        const tagPattern = /(^|\s)#([\p{L}\p{N}_-]+)/gu;

        lines.forEach((line, index) => {
            const trimmed = line.trim();
            if (!trimmed || /^#{1,6}\s+/.test(trimmed)) return;

            const match = trimmed.match(referenceLine);
            if (!match) {
                warnings.push({line: index + 1, text: line});
                return;
            }

            const title = match[1].trim();
            const url = match[2].trim();
            const tail = match[3] || "";
            const tags = [];
            for (const tagMatch of tail.matchAll(tagPattern)) {
                tags.push(tagMatch[2]);
                tagSet.add(tagMatch[2]);
            }
            const note = tail.replace(tagPattern, " ").replace(/\s+/g, " ").trim();

            items.push({
                id: `${index + 1}-${url}`,
                line: index + 1,
                title,
                url,
                domain: domainFromUrl(url),
                tags,
                note,
            });
        });

        return {
            items,
            warnings,
            tags: Array.from(tagSet).sort((a, b) => a.localeCompare(b, "zh-CN")),
        };
    }

    function filteredItems(parsed) {
        const query = state.query.trim().toLowerCase();
        return parsed.items.filter((item) => {
            const matchesTag = !state.activeTag || item.tags.includes(state.activeTag);
            const text = `${item.title} ${item.url} ${item.tags.join(" ")} ${item.note}`.toLowerCase();
            const matchesQuery = !query || text.includes(query);
            return matchesTag && matchesQuery;
        });
    }

    function renderLogin() {
        app.innerHTML = `
            <section class="references-login">
                <h2>参考文献</h2>
                <p>该页面是私有资料库，登录后才能查看和编辑。</p>
                <form data-reference-login-form>
                    <input type="password" data-reference-password placeholder="输入笔记密码" autocomplete="current-password">
                    <button type="submit">登录</button>
                </form>
                <div class="references-error">${escapeHtml(state.error)}</div>
            </section>
        `;
        app.querySelector("[data-reference-login-form]").addEventListener("submit", async (event) => {
            event.preventDefault();
            const password = app.querySelector("[data-reference-password]").value;
            try {
                await requestJson("/api/login", {method: "POST", body: JSON.stringify({password})});
                state.authenticated = true;
                state.error = "";
                await loadReferences();
            } catch (error) {
                state.error = "登录失败：" + error.message;
                renderLogin();
            }
        });
    }

    function renderApp() {
        const parsed = parseReferences(state.content);
        const visibleItems = filteredItems(parsed);
        const dirty = state.content !== state.savedContent;
        app.innerHTML = `
            <section class="references-shell">
                <aside class="references-editor">
                    <div class="references-editor-header">
                        <h2>参考文献</h2>
                        <span class="references-save-state ${dirty ? "is-dirty" : ""}">${dirty ? "未保存" : "已保存"}</span>
                    </div>
                    <textarea data-reference-content spellcheck="false" placeholder="- [资料标题](https://example.com) #标签 备注"></textarea>
                    <div class="references-actions">
                        <button data-reference-save type="button" ${state.saving ? "disabled" : ""}>${state.saving ? "保存中" : "保存"}</button>
                        <a href="/api/references/export.md" download="references.md">导出 Markdown</a>
                    </div>
                    <p class="references-meta">最后保存：${escapeHtml(formatBeijingTime(state.updatedAt))}</p>
                    <p class="references-error">${escapeHtml(state.error)}</p>
                </aside>
                <section class="references-library">
                    <div class="references-toolbar">
                        <input data-reference-search value="${escapeHtml(state.query)}" placeholder="搜索标题、URL、标签、备注">
                        <button data-reference-clear type="button">清除筛选</button>
                    </div>
                    <div class="references-tags">
                        ${parsed.tags.map((tag) => `<button type="button" data-reference-tag="${escapeHtml(tag)}" class="${state.activeTag === tag ? "is-active" : ""}">#${escapeHtml(tag)}</button>`).join("")}
                    </div>
                    <div class="references-count">${visibleItems.length} / ${parsed.items.length} 条资料</div>
                    ${renderWarnings(parsed.warnings)}
                    <div class="references-list">${renderItems(visibleItems)}</div>
                </section>
            </section>
        `;

        const textarea = app.querySelector("[data-reference-content]");
        textarea.value = state.content;
        textarea.addEventListener("input", () => {
            state.content = textarea.value;
            renderApp();
            const nextTextarea = app.querySelector("[data-reference-content]");
            nextTextarea.focus();
            nextTextarea.selectionStart = nextTextarea.selectionEnd = state.content.length;
        });
        app.querySelector("[data-reference-save]").addEventListener("click", saveReferences);
        app.querySelector("[data-reference-search]").addEventListener("input", (event) => {
            state.query = event.target.value;
            renderApp();
            const nextSearch = app.querySelector("[data-reference-search]");
            nextSearch.focus();
            nextSearch.selectionStart = nextSearch.selectionEnd = state.query.length;
        });
        app.querySelector("[data-reference-clear]").addEventListener("click", () => {
            state.query = "";
            state.activeTag = "";
            renderApp();
        });
        app.querySelectorAll("[data-reference-tag]").forEach((button) => {
            button.addEventListener("click", () => {
                const tag = button.getAttribute("data-reference-tag");
                state.activeTag = state.activeTag === tag ? "" : tag;
                renderApp();
            });
        });
    }

    function renderWarnings(warnings) {
        if (!warnings.length) return "";
        return `<details class="references-warnings"><summary>${warnings.length} 行未解析</summary>${warnings.map((item) => `<div>第 ${item.line} 行：${escapeHtml(item.text)}</div>`).join("")}</details>`;
    }

    function renderItems(items) {
        if (!items.length) {
            return `<div class="references-empty">没有匹配的资料。可以在左侧添加：- [标题](https://example.com) #标签 备注</div>`;
        }
        return items.map((item) => `
            <article class="reference-card">
                <div class="reference-card-main">
                    <h3><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h3>
                    <div class="reference-url">${escapeHtml(item.domain)}</div>
                    ${item.note ? `<p>${escapeHtml(item.note)}</p>` : ""}
                    <div class="reference-tags">${item.tags.map((tag) => `<span>#${escapeHtml(tag)}</span>`).join("")}</div>
                </div>
                <a class="reference-open" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">打开</a>
            </article>
        `).join("");
    }

    async function loadReferences() {
        try {
            const data = await requestJson("/api/references");
            state.content = data.content || "";
            state.savedContent = state.content;
            state.updatedAt = data.updated_at;
            state.error = "";
            renderApp();
        } catch (error) {
            state.error = "加载失败：" + error.message;
            renderApp();
        }
    }

    async function saveReferences() {
        state.saving = true;
        state.error = "";
        renderApp();
        try {
            const data = await requestJson("/api/references", {
                method: "PUT",
                body: JSON.stringify({content: state.content}),
            });
            state.savedContent = state.content;
            state.updatedAt = data.updated_at;
            state.error = "";
        } catch (error) {
            state.error = "保存失败：" + error.message;
        } finally {
            state.saving = false;
            renderApp();
        }
    }

    async function init() {
        try {
            const me = await requestJson("/api/me");
            state.authenticated = Boolean(me.authenticated);
            if (!state.authenticated) {
                renderLogin();
                return;
            }
            await loadReferences();
        } catch (error) {
            state.error = "初始化失败：" + error.message;
            renderLogin();
        }
    }

    window.addEventListener("beforeunload", (event) => {
        if (state.content !== state.savedContent) {
            event.preventDefault();
            event.returnValue = "";
        }
    });

    init();
})();