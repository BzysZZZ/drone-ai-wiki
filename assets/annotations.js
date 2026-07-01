(function () {
    "use strict";

    const COLORS = ["yellow", "green", "blue", "pink", "purple", "orange", "cyan", "gray"];
    const state = {
        authenticated: false,
        annotations: [],
        currentSelection: null,
        saveTimers: new Map(),
        currentColor: "yellow",
    };

    const main = document.querySelector(".main");
    const panel = document.querySelector("[data-annotation-panel]");
    const panelBody = document.querySelector("[data-annotation-panel-body]");
    const toggleButton = document.querySelector("[data-annotation-toggle]");
    const toolbar = document.querySelector("[data-annotation-toolbar]");

    if (!main || !panel || !panelBody || !toggleButton || !toolbar) {
        return;
    }

    function pagePath() {
        const path = window.location.pathname || "/index.html";
        if (path === "/" || path.endsWith("/")) {
            return `${path}index.html`;
        }
        return path;
    }

    function setCollapsed(collapsed) {
        document.body.classList.toggle("annotation-panel-collapsed", collapsed);
        localStorage.setItem("annotation-panel-collapsed", collapsed ? "1" : "0");
        toggleButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
        toggleButton.textContent = collapsed ? "‹" : "›";
    }

    function ensurePanelOpen() {
        setCollapsed(false);
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatBeijingTime(isoString) {
        if (!isoString) return "";
        try {
            const match = isoString.match(
                /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/
            );
            if (!match) return isoString;
            const utc = new Date(Date.UTC(
                +match[1], +match[2] - 1, +match[3],
                +match[4], +match[5], +match[6]
            ));
            return utc.toLocaleString("zh-CN", {
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

    function getAnnotationDomPosition(annotation) {
        const el = document.querySelector(
            `.annotation-highlight[data-annotation-id="${annotation.id}"]`
        );
        if (!el) return Infinity;
        const range = document.createRange();
        range.setStartBefore(document.body);
        range.setEndBefore(el);
        return range.toString().length + range.commonAncestorContainer.textContent.indexOf(el.textContent || "");
    }

    async function requestJson(url, options) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: {"Content-Type": "application/json"},
            ...options,
        });
        const text = await response.text();
        const data = text ? JSON.parse(text) : {};
        if (!response.ok) {
            const error = new Error(data.error || `HTTP ${response.status}`);
            error.status = response.status;
            error.data = data;
            throw error;
        }
        return data;
    }

    function renderLogin(errorText) {
        panelBody.innerHTML = `
            <form class="annotation-login" data-annotation-login>
                <p class="annotation-muted">登录后可以在服务器保存划线和右侧笔记，多设备同步。</p>
                <input type="password" name="password" placeholder="笔记密码" autocomplete="current-password">
                <button class="annotation-button" type="submit">登录</button>
                ${errorText ? `<div class="annotation-error">${escapeHtml(errorText)}</div>` : ""}
            </form>
        `;
        const form = panelBody.querySelector("[data-annotation-login]");
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const password = new FormData(form).get("password");
            try {
                await requestJson("/api/login", {
                    method: "POST",
                    body: JSON.stringify({password}),
                });
                state.authenticated = true;
                await loadAnnotations();
            } catch (error) {
                renderLogin("密码不正确，或笔记服务未启动。");
            }
        });
    }

    function renderAnnotationList() {
        if (!state.authenticated) {
            renderLogin();
            return;
        }
        if (state.annotations.length === 0) {
            panelBody.innerHTML = `
                <div class="annotation-empty">
                    选中正文后点击“划线”或“笔记”。笔记会保存到服务器。
                </div>
            `;
            return;
        }

        const sorted = [...state.annotations].sort((a, b) => {
            return getAnnotationDomPosition(a) - getAnnotationDomPosition(b);
        });

        panelBody.innerHTML = `
            <div class="annotation-list">
                ${sorted.map(renderAnnotationCard).join("")}
            </div>
        `;

        panelBody.querySelectorAll(".annotation-card").forEach((card) => {
            card.addEventListener("click", (event) => {
                const target = event.target;
                if (target.closest("button, textarea, .annotation-note-preview")) return;
                panelBody.querySelectorAll(".annotation-card.is-expanded").forEach((c) => {
                    if (c !== card) c.classList.remove("is-expanded");
                });
                card.classList.toggle("is-expanded");
                if (card.classList.contains("is-expanded")) {
                    const ta = card.querySelector("[data-annotation-note]");
                    if (ta) setTimeout(() => ta.focus(), 100);
                }
            });
        });

        // 点击预览区 → 展开编辑
        panelBody.querySelectorAll(".annotation-note-preview").forEach((preview) => {
            preview.addEventListener("click", () => {
                const card = preview.closest(".annotation-card");
                if (!card || card.classList.contains("is-expanded")) return;
                panelBody.querySelectorAll(".annotation-card.is-expanded").forEach((c) => c.classList.remove("is-expanded"));
                card.classList.add("is-expanded");
                const ta = card.querySelector("[data-annotation-note]");
                if (ta) setTimeout(() => ta.focus(), 100);
            });
        });

        panelBody.querySelectorAll("[data-annotation-note]").forEach((textarea) => {
            textarea.addEventListener("input", () => {
                const id = Number(textarea.dataset.annotationNote);
                const annotation = state.annotations.find((item) => item.id === id);
                if (!annotation) return;
                annotation.note = textarea.value;
                debounceSave(id, {note: textarea.value});
                renderNotePreview(id, textarea.value);
            });
            textarea.addEventListener("focus", () => {
                const id = textarea.dataset.annotationNote;
                const hint = panelBody.querySelector(`[data-annotation-hint="${id}"]`);
                if (hint) hint.classList.add("is-visible");
            });
            textarea.addEventListener("blur", () => {
                const id = textarea.dataset.annotationNote;
                const hint = panelBody.querySelector(`[data-annotation-hint="${id}"]`);
                if (hint) hint.classList.remove("is-visible");
                // 自动折叠，显示渲染预览
                const card = textarea.closest(".annotation-card");
                if (card) card.classList.remove("is-expanded");
            });
            // image paste: clipboard → base64 → image markdown
            textarea.addEventListener("paste", (event) => {
                const items = event.clipboardData && event.clipboardData.items;
                if (!items) return;
                for (const item of items) {
                    if (item.type.startsWith("image/")) {
                        event.preventDefault();
                        const blob = item.getAsFile();
                        const reader = new FileReader();
                        reader.onload = () => {
                            const md = `![image](${reader.result})`;
                            const start = textarea.selectionStart;
                            const end = textarea.selectionEnd;
                            const val = textarea.value;
                            textarea.value = val.slice(0, start) + md + val.slice(end);
                            textarea.dispatchEvent(new Event("input", {bubbles: true}));
                        };
                        reader.readAsDataURL(blob);
                        break;
                    }
                }
            });
            // image drop
            textarea.addEventListener("drop", (event) => {
                const files = event.dataTransfer && event.dataTransfer.files;
                if (!files) return;
                for (const file of files) {
                    if (file.type.startsWith("image/")) {
                        event.preventDefault();
                        const reader = new FileReader();
                        reader.onload = () => {
                            const md = `![${file.name}](${reader.result})`;
                            textarea.value += md;
                            textarea.dispatchEvent(new Event("input", {bubbles: true}));
                        };
                        reader.readAsDataURL(file);
                        break;
                    }
                }
            });
            // initial render
            const id = Number(textarea.dataset.annotationNote);
            renderNotePreview(id, textarea.value);
        });

        panelBody.querySelectorAll("[data-annotation-color]").forEach((button) => {
            button.addEventListener("click", () => {
                const id = Number(button.dataset.annotationId);
                const color = button.dataset.annotationColor;
                updateColor(id, color);
            });
        });

        panelBody.querySelectorAll("[data-annotation-delete]").forEach((button) => {
            button.addEventListener("click", () => {
                const id = Number(button.dataset.annotationDelete);
                deleteAnnotation(id);
            });
        });

        panelBody.querySelectorAll("[data-annotation-jump]").forEach((button) => {
            button.addEventListener("click", () => {
                const id = Number(button.dataset.annotationJump);
                jumpToAnnotation(id);
            });
        });
    }

    function renderAnnotationCard(annotation) {
        const colorDots = COLORS.map((color) => {
            const active = annotation.color === color ? " is-active" : "";
            return `<button class="annotation-color-dot${active}" data-annotation-id="${annotation.id}" data-annotation-color="${color}" data-color="${color}" title="${color}" type="button" style="background:var(--annotation-${color})"></button>`;
        }).join("");
        const orphan = annotation.located === false ? " is-orphan" : "";
        const orphanText = annotation.located === false ? `<div class="annotation-error">原文定位失败，笔记仍已保留。</div>` : "";
        const noteText = escapeHtml(annotation.note || "");
        return `
            <article class="annotation-card${orphan}" data-annotation-card="${annotation.id}" data-color="${escapeHtml(annotation.color)}">
                <div class="annotation-color-strip">${colorDots}</div>
                <div class="annotation-quote">
                    <span class="annotation-color-indicator"></span>
                    <span class="annotation-quote-text">${escapeHtml(annotation.selected_text)}</span>
                </div>
                <div class="annotation-card-actions">
                    <button class="annotation-action-btn" data-annotation-jump="${annotation.id}" title="跳转到原文" type="button">↗</button>
                    <button class="annotation-action-btn is-danger" data-annotation-delete="${annotation.id}" title="删除" type="button">×</button>
                </div>
                <div class="annotation-card-body">
                    ${orphanText}
                    <textarea data-annotation-note="${annotation.id}" placeholder="LaTeX 公式用 $...$ 或 $$...$$，截图 Ctrl+V 粘贴">${noteText}</textarea>
                    <div class="annotation-formula-hint" data-annotation-hint="${annotation.id}">
                        公式示例：$E=mc^2$  $\sum_{i=1}^n x_i$
                    </div>
                    <div class="annotation-updated">${formatBeijingTime(annotation.updated_at)}</div>
                </div>
                <div class="annotation-note-preview" data-annotation-preview="${annotation.id}"></div>
            </article>
        `;
    }

    async function loadAnnotations() {
        try {
            const data = await requestJson(`/api/annotations?page=${encodeURIComponent(pagePath())}`);
            state.annotations = data.items || [];
            applyStoredHighlights();
            renderAnnotationList();
        } catch (error) {
            if (error.status === 401) {
                state.authenticated = false;
                renderLogin();
                return;
            }
            panelBody.innerHTML = `<div class="annotation-error">笔记服务不可用：${escapeHtml(error.message)}</div>`;
        }
    }

    function captureSelection() {
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            return null;
        }
        const range = selection.getRangeAt(0);
        if (!main.contains(range.commonAncestorContainer)) {
            return null;
        }
        const selectedText = selection.toString().trim();
        if (!selectedText) {
            return null;
        }

        const before = document.createRange();
        before.selectNodeContents(main);
        before.setEnd(range.startContainer, range.startOffset);

        const after = document.createRange();
        after.selectNodeContents(main);
        after.setStart(range.endContainer, range.endOffset);

        return {
            range: range.cloneRange(),
            selected_text: selectedText,
            prefix_text: before.toString().slice(-40),
            suffix_text: after.toString().slice(0, 40),
        };
    }

    function showToolbar(selectionInfo) {
        const rect = selectionInfo.range.getBoundingClientRect();
        if (!rect || rect.width === 0) return;
        toolbar.style.left = `${Math.max(12, rect.left + rect.width / 2 - 70)}px`;
        toolbar.style.top = `${Math.max(12, rect.top - 46)}px`;
        toolbar.classList.add("is-visible");
    }

    function hideToolbar() {
        toolbar.classList.remove("is-visible");
    }

    function clearBrowserSelection() {
        const selection = window.getSelection();
        if (selection) {
            selection.removeAllRanges();
        }
    }

    async function createAnnotation(color, openNote) {
        hideToolbar();
        if (!state.currentSelection) return;
        if (!state.authenticated) {
            ensurePanelOpen();
            renderLogin("请先登录再保存笔记。");
            return;
        }

        const payload = {
            page_path: pagePath(),
            selected_text: state.currentSelection.selected_text,
            prefix_text: state.currentSelection.prefix_text,
            suffix_text: state.currentSelection.suffix_text,
            color: color || "yellow",
            note: "",
        };
        try {
            const data = await requestJson("/api/annotations", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            const now = new Date().toISOString();
            const annotation = {
                ...payload,
                id: data.id,
                text_hash: "",
                created_at: now,
                updated_at: now,
                located: true,
            };
            highlightRange(state.currentSelection.range, annotation);
            state.annotations.push(annotation);
            renderAnnotationList();
            if (openNote) {
                ensurePanelOpen();
                const card = panelBody.querySelector(`[data-annotation-card="${annotation.id}"]`);
                if (card) card.classList.add("is-expanded");
                focusNote(annotation.id);
            }
            clearBrowserSelection();
            state.currentSelection = null;
        } catch (error) {
            ensurePanelOpen();
            panelBody.innerHTML = `<div class="annotation-error">保存失败：${escapeHtml(error.message)}</div>`;
        }
    }

    function getTextNodes(root) {
        const walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode(node) {
                    const parent = node.parentElement;
                    if (!parent) return NodeFilter.FILTER_REJECT;
                    if (parent.closest(".annotation-panel, .annotation-toolbar, script, style, textarea")) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    if (!node.nodeValue) return NodeFilter.FILTER_REJECT;
                    return NodeFilter.FILTER_ACCEPT;
                },
            }
        );
        const nodes = [];
        let current;
        while ((current = walker.nextNode())) {
            nodes.push(current);
        }
        return nodes;
    }

    function rangeFromOffsets(nodes, start, end) {
        let position = 0;
        let startNode = null;
        let startOffset = 0;
        let endNode = null;
        let endOffset = 0;

        for (const node of nodes) {
            const next = position + node.nodeValue.length;
            if (!startNode && start >= position && start <= next) {
                startNode = node;
                startOffset = start - position;
            }
            if (!endNode && end >= position && end <= next) {
                endNode = node;
                endOffset = end - position;
                break;
            }
            position = next;
        }

        if (!startNode || !endNode) return null;
        const range = document.createRange();
        range.setStart(startNode, startOffset);
        range.setEnd(endNode, endOffset);
        return range;
    }

    function findTextRange(annotation) {
        const nodes = getTextNodes(main);
        const fullText = nodes.map((node) => node.nodeValue).join("");
        let start = -1;
        const selected = annotation.selected_text || "";
        const prefix = annotation.prefix_text || "";
        const suffix = annotation.suffix_text || "";

        if (prefix || suffix) {
            const exact = `${prefix}${selected}${suffix}`;
            const exactIndex = fullText.indexOf(exact);
            if (exactIndex >= 0) {
                start = exactIndex + prefix.length;
            }
        }
        if (start < 0) {
            start = fullText.indexOf(selected);
        }
        if (start < 0) {
            return null;
        }
        return rangeFromOffsets(nodes, start, start + selected.length);
    }

    function highlightRange(range, annotation) {
        if (!range || range.collapsed) return false;
        const clickHandler = () => {
            ensurePanelOpen();
            jumpToAnnotation(annotation.id);
            setTimeout(() => focusNote(annotation.id), 500);
        };
        function createSpan(text) {
            const span = document.createElement("span");
            span.className = "annotation-highlight";
            span.setAttribute("data-annotation-id", String(annotation.id));
            span.setAttribute("data-color", annotation.color || "yellow");
            span.title = "点击查看笔记";
            span.textContent = text;
            return span;
        }

        try {
            // 优先使用 surroundContents：不破坏 DOM 结构，只在 range 两端插入标签
            const span = createSpan();
            range.surroundContents(span);
            span.addEventListener("click", clickHandler);
            return true;
        } catch (error) {
            // 如果 range 跨越元素边界，surroundContents 会失败
            // 改用遍历文本节点，逐个包裹，保持 block 结构完整
        }

        try {
            const spans = [];
            let root = range.commonAncestorContainer;
            if (root.nodeType === Node.TEXT_NODE) {
                root = root.parentNode;
            }

            // 收集 range 内所有文本节点（先收集再修改，避免 TreeWalker 失效）
            const treeWalker = document.createTreeWalker(
                root,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            const textNodes = [];
            let node;
            while ((node = treeWalker.nextNode())) {
                textNodes.push(node);
            }

            // 保存 range 边界（splitText 后 range 可能自动更新）
            const startContainer = range.startContainer;
            const startOffset = range.startOffset;
            const endContainer = range.endContainer;
            const endOffset = range.endOffset;

            for (const textNode of textNodes) {
                const testRange = document.createRange();
                testRange.selectNode(textNode);

                // 文本节点完全在 range 之前或之后，跳过
                if (range.compareBoundaryPoints(Range.START_TO_END, testRange) > 0 ||
                    range.compareBoundaryPoints(Range.END_TO_START, testRange) < 0) {
                    continue;
                }

                const text = textNode.textContent;
                let start = 0;
                let end = text.length;

                if (textNode === startContainer) {
                    start = startOffset;
                }
                if (textNode === endContainer) {
                    end = endOffset;
                }

                if (start >= end) continue;

                // 分割文本节点，提取选中的部分
                let selectedNode = textNode;
                if (start > 0) {
                    selectedNode = textNode.splitText(start);
                }
                // splitText 后 selectedNode 的长度是 text.length - start
                if (end < text.length) {
                    selectedNode.splitText(end - start);
                }

                const span = createSpan(selectedNode.textContent);
                span.addEventListener("click", clickHandler);
                selectedNode.parentNode.replaceChild(span, selectedNode);
                spans.push(span);
            }

            return spans.length > 0;
        } catch (error) {
            return false;
        }
    }

    function applyStoredHighlights() {
        for (const annotation of state.annotations) {
            const range = findTextRange(annotation);
            if (!range) {
                annotation.located = false;
                continue;
            }
            annotation.located = highlightRange(range, annotation);
        }
    }

    function debounceSave(id, patch) {
        if (state.saveTimers.has(id)) {
            clearTimeout(state.saveTimers.get(id));
        }
        const timer = setTimeout(() => {
            saveAnnotation(id, patch);
            state.saveTimers.delete(id);
        }, 450);
        state.saveTimers.set(id, timer);
    }

    async function saveAnnotation(id, patch) {
        try {
            await requestJson(`/api/annotations/${id}`, {
                method: "PUT",
                body: JSON.stringify(patch),
            });
            // update local updated_at to Beijing time
            const annotation = state.annotations.find((item) => item.id === id);
            if (annotation) {
                annotation.updated_at = new Date().toISOString();
            }
            // refresh time display in card without full re-render
            const card = panelBody.querySelector(`[data-annotation-card="${id}"]`);
            if (card) {
                const timeEl = card.querySelector(".annotation-updated");
                if (timeEl) timeEl.textContent = formatBeijingTime(annotation.updated_at);
            }
        } catch (error) {
            panelBody.insertAdjacentHTML(
                "afterbegin",
                `<div class="annotation-error">保存笔记失败：${escapeHtml(error.message)}</div>`
            );
        }
    }

    function updateColor(id, color) {
        const annotation = state.annotations.find((item) => item.id === id);
        if (!annotation) return;
        annotation.color = color;

        // 1. 更新左边高亮 span 的 data-color（用 setAttribute 确保 CSS 属性选择器命中）
        document.querySelectorAll(`[data-annotation-id="${id}"]`).forEach((el) => {
            el.setAttribute("data-color", color);
        });

        // 2. 原地更新右边卡片的颜色（不重建 DOM，保留展开态和编辑内容）
        const card = panelBody.querySelector(`[data-annotation-card="${id}"]`);
        if (card) {
            card.setAttribute("data-color", color);
            // 更新颜色条中所有小圆点的 active 状态
            card.querySelectorAll(".annotation-color-dot").forEach((dot) => {
                dot.classList.toggle("is-active", dot.dataset.annotationColor === color);
            });
        }

        saveAnnotation(id, {color});
    }

    async function deleteAnnotation(id) {
        try {
            await requestJson(`/api/annotations/${id}`, {method: "DELETE"});
            state.annotations = state.annotations.filter((item) => item.id !== id);
            document.querySelectorAll(`.annotation-highlight[data-annotation-id="${id}"]`).forEach((span) => {
                const parent = span.parentNode;
                while (span.firstChild) {
                    parent.insertBefore(span.firstChild, span);
                }
                parent.removeChild(span);
                parent.normalize();
            });
            renderAnnotationList();
        } catch (error) {
            panelBody.insertAdjacentHTML(
                "afterbegin",
                `<div class="annotation-error">删除失败：${escapeHtml(error.message)}</div>`
            );
        }
    }

    function focusNote(id) {
        const textarea = panelBody.querySelector(`[data-annotation-note="${id}"]`);
        if (textarea) {
            textarea.focus();
        }
    }

    /* ── KaTeX 懒加载 ── */
    let katexReady = false;
    let katexLoading = false;
    function ensureKatex() {
        return new Promise((resolve) => {
            if (katexReady) { resolve(); return; }
            if (katexLoading) {
                const check = setInterval(() => { if (katexReady) { clearInterval(check); resolve(); } }, 50);
                return;
            }
            katexLoading = true;
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css";
            document.head.appendChild(link);
            const script = document.createElement("script");
            script.src = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js";
            script.onload = () => { katexReady = true; resolve(); };
            script.onerror = () => { katexLoading = false; resolve(); };
            document.head.appendChild(script);
        });
    }

    /* ── 笔记预览渲染（纯文本 + LaTeX公式 + 图片） ── */
    async function renderNotePreview(id, text) {
        const preview = panelBody.querySelector(`[data-annotation-preview="${id}"]`);
        if (!preview) return;
        const raw = (text || "").trim();
        if (!raw) { preview.classList.remove("has-content"); preview.innerHTML = ""; return; }

        // 策略：先把公式块从文本中提取出来，防止 HTML escape 破坏公式
        const segments = [];
        let rest = raw;

        // 1. 提取块级公式 $$...$$
        rest = rest.replace(/\$\$([\s\S]*?)\$\$/g, (match, formula) => {
            segments.push({ type: "block-formula", content: formula.trim() });
            return `\x00BLOCK${segments.length - 1}\x00`;
        });
        // 吞掉块公式占位符前后的换行（textarea 中换行会转成 <br>，与公式块 margin 叠加后空白过大）
        rest = rest.replace(/\n+(\x00BLOCK\d+\x00)/g, "$1");
        rest = rest.replace(/(\x00BLOCK\d+\x00)\n+/g, "$1");

        // 2. 提取行内公式 $...$（不在 $$ 内的）
        rest = rest.replace(/\$([^\$\n]+?)\$/g, (match, formula) => {
            segments.push({ type: "inline-formula", content: formula.trim() });
            return `\x00INLINE${segments.length - 1}\x00`;
        });

        // 3. 提取图片 ![alt](url)
        rest = rest.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, url) => {
            segments.push({ type: "image", alt: alt, url: url });
            return `\x00IMG${segments.length - 1}\x00`;
        });

        // 4. 其余文本：escape HTML + 保留换行
        const parts = rest.split(/(\x00(?:BLOCK|INLINE|IMG)\d+\x00)/);
        let html = "";
        for (const part of parts) {
            const m = part.match(/^\x00(BLOCK|INLINE|IMG)(\d+)\x00$/);
            if (m) {
                const seg = segments[Number(m[2])];
                if (seg.type === "block-formula") {
                    await ensureKatex();
                    try {
                        html += `<div class="katex-block">${window.katex.renderToString(seg.content, {displayMode: true, throwOnError: false})}</div>`;
                    } catch(e) { html += `<code>$$${seg.content}$$</code>`; }
                } else if (seg.type === "inline-formula") {
                    if (katexReady) {
                        try {
                            html += window.katex.renderToString(seg.content, {throwOnError: false});
                        } catch(e) { html += `$${seg.content}$`; }
                    } else {
                        html += `$${seg.content}$`;
                    }
                } else if (seg.type === "image") {
                    html += `<img src="${escapeHtml(seg.url)}" alt="${escapeHtml(seg.alt)}" loading="lazy">`;
                }
            } else if (part) {
                html += escapeHtml(part).replace(/\n/g, "<br>");
            }
        }

        preview.innerHTML = html;
        preview.classList.add("has-content");
    }

    function jumpToAnnotation(id) {
        document.querySelectorAll(".annotation-highlight.is-active").forEach((item) => {
            item.classList.remove("is-active");
        });
        const highlight = document.querySelector(`.annotation-highlight[data-annotation-id="${id}"]`);
        const card = panelBody.querySelector(`[data-annotation-card="${id}"]`);
        if (highlight) {
            highlight.classList.add("is-active");
            highlight.scrollIntoView({behavior: "smooth", block: "center"});
        }
        if (card) {
            panelBody.querySelectorAll(".annotation-card.is-expanded").forEach((c) => {
                if (c !== card) c.classList.remove("is-expanded");
            });
            card.classList.add("is-expanded");
            card.scrollIntoView({behavior: "smooth", block: "nearest"});
        }
    }

    function setupToolbar() {
        toolbar.innerHTML = `
            <div class="annotation-toolbar-colors">
                ${COLORS.map(c => `<button class="annotation-color${state.currentColor === c ? ' is-active' : ''}" data-annotation-toolbar-color="${c}" data-color="${c}" title="${c}" type="button"></button>`).join('')}
            </div>
            <button class="annotation-button" data-annotation-create="note" type="button">💬 笔记</button>
        `;

        toolbar.querySelectorAll('[data-annotation-toolbar-color]').forEach(btn => {
            btn.addEventListener("click", () => {
                const color = btn.dataset.annotationToolbarColor;
                state.currentColor = color;
                toolbar.querySelectorAll('.annotation-color').forEach(b => b.classList.remove('is-active'));
                btn.classList.add('is-active');
                createAnnotation(color, false);
            });
        });

        toolbar.querySelector('[data-annotation-create="note"]').addEventListener("click", () => {
            createAnnotation(state.currentColor, true);
        });

        document.addEventListener("mouseup", () => {
            setTimeout(() => {
                const selectionInfo = captureSelection();
                if (!selectionInfo) {
                    hideToolbar();
                    return;
                }
                state.currentSelection = selectionInfo;
                showToolbar(selectionInfo);
            }, 0);
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                hideToolbar();
                clearBrowserSelection();
            }
        });
    }

    async function bootstrap() {
        setCollapsed(localStorage.getItem("annotation-panel-collapsed") === "1");
        toggleButton.addEventListener("click", () => {
            const collapsed = !document.body.classList.contains("annotation-panel-collapsed");
            setCollapsed(collapsed);
        });
        setupToolbar();

        try {
            const me = await requestJson("/api/me");
            state.authenticated = Boolean(me.authenticated);
            if (state.authenticated) {
                await loadAnnotations();
            } else {
                renderLogin();
            }
        } catch (error) {
            panelBody.innerHTML = `
                <div class="annotation-empty">
                    笔记服务未连接。部署 Flask API 并配置 Nginx 的 <code>/api/</code> 反代后即可使用云端同步笔记。
                </div>
            `;
        }
    }

    bootstrap();
})();

