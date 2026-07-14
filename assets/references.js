(function () {
    "use strict";

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

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
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

    function normalizeUrl(rawUrl) {
        return String(rawUrl || "").trim().replace(/[),.;，。；、]+$/u, "");
    }

    function extractTags(text) {
        const tags = [];
        const tagPattern = /(^|\s)#([\p{L}\p{N}_-]+)/gu;
        for (const match of String(text || "").matchAll(tagPattern)) {
            tags.push(match[2]);
        }
        return tags;
    }

    function stripTags(text) {
        return String(text || "")
            .replace(/(^|\s)#([\p{L}\p{N}_-]+)/gu, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function firstTagIndex(text) {
        const match = /(^|\s)#([\p{L}\p{N}_-]+)/u.exec(String(text || ""));
        return match ? match.index + match[1].length : -1;
    }

    function addParsedItem(items, tagSet, lineNumber, title, url, tags, note) {
        const cleanUrl = normalizeUrl(url);
        if (!cleanUrl) return;
        const cleanTitle = String(title || "").trim() || domainFromUrl(cleanUrl);
        const uniqueTags = Array.from(new Set(tags.filter(Boolean)));
        uniqueTags.forEach((tag) => tagSet.add(tag));
        items.push({
            id: `${lineNumber}-${cleanUrl}`,
            line: lineNumber,
            title: cleanTitle,
            url: cleanUrl,
            domain: domainFromUrl(cleanUrl),
            tags: uniqueTags,
            note: String(note || "").replace(/\s+/g, " ").trim(),
        });
    }

    function parseReferences(markdown) {
        const items = [];
        const warnings = [];
        const tagSet = new Set();
        const lines = String(markdown || "").split(/\r?\n/);
        const markdownLink = /^\s*[-*]\s+\[([^\]]+)\]\((https?:\/\/[^)]+)\)\s*(.*)$/i;
        const looseUrl = /https?:\/\/[^\s<>)]+/i;

        lines.forEach((line, index) => {
            const lineNumber = index + 1;
            const trimmed = line.trim();
            if (!trimmed || /^#{1,6}\s+/.test(trimmed)) return;

            const markdownMatch = trimmed.match(markdownLink);
            if (markdownMatch) {
                const tail = markdownMatch[3] || "";
                addParsedItem(
                    items,
                    tagSet,
                    lineNumber,
                    markdownMatch[1],
                    markdownMatch[2],
                    extractTags(tail),
                    stripTags(tail)
                );
                return;
            }

            const urlMatch = trimmed.match(looseUrl);
            if (!urlMatch) {
                warnings.push({line: lineNumber, text: line});
                return;
            }

            const rawUrl = urlMatch[0];
            const url = normalizeUrl(rawUrl);
            const urlEnd = urlMatch.index + rawUrl.length;
            const beforeUrl = trimmed.slice(0, urlMatch.index).replace(/^[-*]\s+/, "").trim();
            const afterUrl = trimmed.slice(urlEnd).trim();
            const tags = extractTags(`${beforeUrl} ${afterUrl}`);

            if (beforeUrl) {
                addParsedItem(items, tagSet, lineNumber, beforeUrl, url, tags, stripTags(afterUrl));
                return;
            }

            const tagStart = firstTagIndex(afterUrl);
            if (tagStart >= 0) {
                const title = afterUrl.slice(0, tagStart).trim();
                const note = stripTags(afterUrl.slice(tagStart));
                addParsedItem(items, tagSet, lineNumber, title || domainFromUrl(url), url, tags, note);
                return;
            }

            addParsedItem(items, tagSet, lineNumber, afterUrl || domainFromUrl(url), url, tags, "");
        });

        return {
            items,
            warnings,
            tags: Array.from(tagSet).sort((a, b) => a.localeCompare(b, "zh-CN")),
        };
    }

    function normalizeTagList(tags) {
        return String(tags || "")
            .split(/[\s,，]+/)
            .map((tag) => tag.trim().replace(/^#/, ""))
            .filter(Boolean);
    }

    function formatReferenceLine(reference) {
        const url = normalizeUrl(reference.url);
        const title = String(reference.title || "").trim() || domainFromUrl(url);
        const tags = normalizeTagList(reference.tags).map((tag) => `#${tag}`).join(" ");
        const note = String(reference.note || "").trim();
        return [`- [${title}](${url})`, tags, note].filter(Boolean).join(" ");
    }

    function appendReferenceLine(content, reference) {
        const line = formatReferenceLine(reference);
        const current = String(content || "").replace(/\s+$/g, "");
        return current ? `${current}\n${line}` : line;
    }

    if (typeof window !== "undefined" && window.__REFERENCE_LIBRARY_TEST_HOOKS__) {
        window.__referenceLibraryInternals = {
            parseReferences,
            formatReferenceLine,
            appendReferenceLine,
        };
    }

    const app = document.querySelector("[data-references-app]");
    if (!app) return;

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
                state.error = `登录失败：${error.message}`;
                renderLogin();
            }
        });
    }

    function renderApp() {
        app.innerHTML = `
            <section class="references-shell">
                <aside class="references-editor">
                    <div class="references-editor-header">
                        <h2>参考文献</h2>
                        <span class="references-save-state" data-reference-save-state></span>
                    </div>
                    <form class="references-quick-add" data-reference-quick-add>
                        <input data-reference-add-title placeholder="标题，可留空">
                        <input data-reference-add-url placeholder="链接 URL">
                        <input data-reference-add-tags placeholder="标签，如 px4 ros2">
                        <input data-reference-add-note placeholder="备注">
                        <button type="submit">添加</button>
                    </form>
                    <textarea data-reference-content spellcheck="false" placeholder="可以直接粘贴 URL，也可以写：标题 https://example.com #标签 备注"></textarea>
                    <div class="references-format-hint">
                        支持：裸 URL、标题 + URL、URL + 标题、Markdown 链接。标签写成 #px4 或在快速添加里写 px4。
                    </div>
                    <div class="references-actions">
                        <button data-reference-save type="button"></button>
                        <a href="/api/references/export.md" download="references.md">导出 Markdown</a>
                    </div>
                    <p class="references-meta" data-reference-meta></p>
                    <p class="references-error" data-reference-error></p>
                </aside>
                <section class="references-library">
                    <div class="references-toolbar">
                        <input data-reference-search placeholder="搜索标题、URL、标签、备注">
                        <button data-reference-clear type="button">清除筛选</button>
                    </div>
                    <div class="references-tags" data-reference-tags></div>
                    <div class="references-count" data-reference-count></div>
                    <div data-reference-warnings></div>
                    <div class="references-list" data-reference-list></div>
                </section>
            </section>
        `;

        const textarea = app.querySelector("[data-reference-content]");
        const search = app.querySelector("[data-reference-search]");
        textarea.value = state.content;
        search.value = state.query;

        textarea.addEventListener("input", () => {
            state.content = textarea.value;
            updatePreview();
        });
        search.addEventListener("input", () => {
            state.query = search.value;
            updatePreview();
        });
        app.querySelector("[data-reference-save]").addEventListener("click", saveReferences);
        app.querySelector("[data-reference-clear]").addEventListener("click", () => {
            state.query = "";
            state.activeTag = "";
            search.value = "";
            updatePreview();
            search.focus();
        });
        app.querySelector("[data-reference-quick-add]").addEventListener("submit", (event) => {
            event.preventDefault();
            addQuickReference();
        });

        updatePreview();
    }

    function addQuickReference() {
        const titleInput = app.querySelector("[data-reference-add-title]");
        const urlInput = app.querySelector("[data-reference-add-url]");
        const tagsInput = app.querySelector("[data-reference-add-tags]");
        const noteInput = app.querySelector("[data-reference-add-note]");
        const url = normalizeUrl(urlInput.value);
        if (!url) {
            state.error = "请先填写链接 URL。";
            updatePreview();
            urlInput.focus();
            return;
        }

        state.content = appendReferenceLine(state.content, {
            title: titleInput.value,
            url,
            tags: tagsInput.value,
            note: noteInput.value,
        });
        app.querySelector("[data-reference-content]").value = state.content;
        titleInput.value = "";
        urlInput.value = "";
        tagsInput.value = "";
        noteInput.value = "";
        state.error = "";
        updatePreview();
        titleInput.focus();
    }

    function updatePreview() {
        const parsed = parseReferences(state.content);
        const visibleItems = filteredItems(parsed);
        const dirty = state.content !== state.savedContent;
        const saveState = app.querySelector("[data-reference-save-state]");
        const saveButton = app.querySelector("[data-reference-save]");

        saveState.textContent = dirty ? "未保存" : "已保存";
        saveState.classList.toggle("is-dirty", dirty);
        saveButton.textContent = state.saving ? "保存中" : "保存";
        saveButton.disabled = state.saving;
        app.querySelector("[data-reference-meta]").textContent = `最后保存：${formatBeijingTime(state.updatedAt)}`;
        app.querySelector("[data-reference-error]").textContent = state.error;
        app.querySelector("[data-reference-count]").textContent = `${visibleItems.length} / ${parsed.items.length} 条资料`;
        app.querySelector("[data-reference-warnings]").innerHTML = renderWarnings(parsed.warnings);
        app.querySelector("[data-reference-list]").innerHTML = renderItems(visibleItems);

        const tagsContainer = app.querySelector("[data-reference-tags]");
        tagsContainer.innerHTML = parsed.tags.map((tag) => (
            `<button type="button" data-reference-tag="${escapeHtml(tag)}" class="${state.activeTag === tag ? "is-active" : ""}">#${escapeHtml(tag)}</button>`
        )).join("");
        tagsContainer.querySelectorAll("[data-reference-tag]").forEach((button) => {
            button.addEventListener("click", () => {
                const tag = button.getAttribute("data-reference-tag");
                state.activeTag = state.activeTag === tag ? "" : tag;
                updatePreview();
            });
        });
    }

    function renderWarnings(warnings) {
        if (!warnings.length) return "";
        return `<details class="references-warnings"><summary>${warnings.length} 行未解析</summary>${warnings.map((item) => `<div>第 ${item.line} 行：${escapeHtml(item.text)}</div>`).join("")}</details>`;
    }

    function renderItems(items) {
        if (!items.length) {
            return `<div class="references-empty">没有匹配的资料。可以在左侧粘贴 URL，或使用快速添加表单。</div>`;
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
            state.error = `加载失败：${error.message}`;
            renderApp();
        }
    }

    async function saveReferences() {
        state.saving = true;
        state.error = "";
        updatePreview();
        try {
            const data = await requestJson("/api/references", {
                method: "PUT",
                body: JSON.stringify({content: state.content}),
            });
            state.savedContent = state.content;
            state.updatedAt = data.updated_at;
            state.error = "";
        } catch (error) {
            state.error = `保存失败：${error.message}`;
        } finally {
            state.saving = false;
            updatePreview();
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
            state.error = `初始化失败：${error.message}`;
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