(function () {
    "use strict";

    const state = {
        authenticated: false,
        notes: [],
        currentNote: null,
        dirty: false,
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

    function sanitizeNoteHtml(html) {
        return String(html || "")
            .replace(/<script[\s\S]*?<\/script>/gi, "")
            .replace(/<style[\s\S]*?<\/style>/gi, "")
            .replace(/<iframe[\s\S]*?<\/iframe>/gi, "")
            .replace(/<object[\s\S]*?<\/object>/gi, "")
            .replace(/<embed[\s\S]*?>/gi, "")
            .replace(/\son\w+=("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
            .replace(/\s(href|src)=("|')\s*javascript:[^"']*("|')/gi, " $1=\"#\"");
    }

    function htmlToText(html) {
        if (typeof document !== "undefined" && document.createElement) {
            const element = document.createElement("div");
            element.innerHTML = sanitizeNoteHtml(html);
            return element.textContent || "";
        }
        return sanitizeNoteHtml(html)
            .replace(/<[^>]+>/g, " ")
            .replace(/&nbsp;/g, " ")
            .replace(/&amp;/g, "&")
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">")
            .replace(/&quot;/g, '"')
            .replace(/&#039;/g, "'")
            .replace(/\s+/g, " ")
            .trim();
    }

    function noteTitleFromHtml(html) {
        const cleanHtml = sanitizeNoteHtml(html);
        if (typeof document !== "undefined" && document.createElement) {
            const element = document.createElement("div");
            element.innerHTML = cleanHtml;
            const firstBlock = element.querySelector("h1, h2, h3, p, div, li");
            const blockText = firstBlock ? (firstBlock.textContent || "").trim() : "";
            if (blockText) return blockText.slice(0, 80);
        }
        const blockMatch = cleanHtml.match(/<(h1|h2|h3|p|div|li)\b[^>]*>([\s\S]*?)<\/\1>/i);
        if (blockMatch) {
            const blockText = htmlToText(blockMatch[2]).trim();
            if (blockText) return blockText.slice(0, 80);
        }
        const text = htmlToText(cleanHtml).trim();
        return text ? text.slice(0, 80) : "Untitled note";
    }

    function formatTime(isoString) {
        if (!isoString) return "未保存";
        try {
            return new Date(isoString).toLocaleString("zh-CN", {
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

    if (typeof window !== "undefined" && window.__NOTES_TEST_HOOKS__) {
        window.__notesInternals = {sanitizeNoteHtml, noteTitleFromHtml};
    }

    const app = document.querySelector("[data-notes-app]");
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

    function renderLogin() {
        app.innerHTML = `
            <section class="notes-login">
                <h2>自定义笔记</h2>
                <p>该页面是私有富文本笔记，登录后才能查看和编辑。</p>
                <form data-notes-login-form>
                    <input type="password" data-notes-password placeholder="输入笔记密码" autocomplete="current-password">
                    <button type="submit">登录</button>
                </form>
                <div class="notes-error">${escapeHtml(state.error)}</div>
            </section>
        `;
        app.querySelector("[data-notes-login-form]").addEventListener("submit", async (event) => {
            event.preventDefault();
            const password = app.querySelector("[data-notes-password]").value;
            try {
                await requestJson("/api/login", {method: "POST", body: JSON.stringify({password})});
                state.authenticated = true;
                state.error = "";
                renderShell();
                await loadNotes();
            } catch (error) {
                state.error = `登录失败：${error.message}`;
                renderLogin();
            }
        });
    }

    function renderShell() {
        app.innerHTML = `
            <section class="notes-shell">
                <aside class="notes-list-panel">
                    <div class="notes-list-header">
                        <h2>自定义笔记</h2>
                        <button type="button" data-note-new>新建</button>
                    </div>
                    <div class="notes-list" data-notes-list></div>
                </aside>
                <section class="notes-editor-panel">
                    <div class="notes-editor-topbar">
                        <input data-note-title placeholder="未命名笔记">
                        <div class="notes-editor-actions">
                            <span data-note-status></span>
                            <button type="button" data-note-delete>删除</button>
                            <button type="button" data-note-save>保存</button>
                        </div>
                    </div>
                    <div class="notes-toolbar" data-notes-toolbar>
                        <button type="button" data-command="undo" title="撤销">↶</button>
                        <button type="button" data-command="redo" title="重做">↷</button>
                        <span class="notes-toolbar-separator"></span>
                        <select data-format-block title="段落样式">
                            <option value="P">正文</option>
                            <option value="H1">标题 1</option>
                            <option value="H2">标题 2</option>
                            <option value="H3">标题 3</option>
                        </select>
                        <select data-font-name title="字体">
                            <option value="Microsoft YaHei">微软雅黑</option>
                            <option value="SimSun">宋体</option>
                            <option value="Arial">Arial</option>
                            <option value="Consolas">Consolas</option>
                        </select>
                        <select data-font-size title="字号">
                            <option value="2">小</option>
                            <option value="3" selected>正文</option>
                            <option value="4">中</option>
                            <option value="5">大</option>
                            <option value="6">特大</option>
                        </select>
                        <span class="notes-toolbar-separator"></span>
                        <button type="button" data-command="bold" title="加粗"><strong>B</strong></button>
                        <button type="button" data-command="italic" title="斜体"><em>I</em></button>
                        <button type="button" data-command="underline" title="下划线"><u>U</u></button>
                        <button type="button" data-command="strikeThrough" title="删除线"><s>S</s></button>
                        <label title="文字颜色">A <input type="color" data-fore-color value="#24292f"></label>
                        <label title="高亮颜色">▣ <input type="color" data-back-color value="#fff8c5"></label>
                        <span class="notes-toolbar-separator"></span>
                        <button type="button" data-command="justifyLeft" title="左对齐">左</button>
                        <button type="button" data-command="justifyCenter" title="居中">中</button>
                        <button type="button" data-command="justifyRight" title="右对齐">右</button>
                        <button type="button" data-command="insertUnorderedList" title="无序列表">•</button>
                        <button type="button" data-command="insertOrderedList" title="有序列表">1.</button>
                        <button type="button" data-command="removeFormat" title="清除格式">清除</button>
                    </div>
                    <div class="notes-page-wrap">
                        <div class="notes-page" data-note-editor contenteditable="true"></div>
                    </div>
                    <div class="notes-error" data-notes-error></div>
                </section>
            </section>
        `;
        bindShellEvents();
        updateEditorState();
    }

    function bindShellEvents() {
        app.querySelector("[data-note-new]").addEventListener("click", createNote);
        app.querySelector("[data-note-save]").addEventListener("click", saveCurrentNote);
        app.querySelector("[data-note-delete]").addEventListener("click", deleteCurrentNote);
        app.querySelector("[data-note-title]").addEventListener("input", markDirty);
        app.querySelector("[data-note-editor]").addEventListener("input", markDirty);
        app.querySelectorAll("[data-command]").forEach((button) => {
            button.addEventListener("click", () => runCommand(button.getAttribute("data-command")));
        });
        app.querySelector("[data-format-block]").addEventListener("change", (event) => runCommand("formatBlock", event.target.value));
        app.querySelector("[data-font-name]").addEventListener("change", (event) => runCommand("fontName", event.target.value));
        app.querySelector("[data-font-size]").addEventListener("change", (event) => runCommand("fontSize", event.target.value));
        app.querySelector("[data-fore-color]").addEventListener("input", (event) => runCommand("foreColor", event.target.value));
        app.querySelector("[data-back-color]").addEventListener("input", (event) => runCommand("hiliteColor", event.target.value));
    }

    function runCommand(command, value = null) {
        const editor = app.querySelector("[data-note-editor]");
        editor.focus();
        document.execCommand(command, false, value);
        markDirty();
    }

    function markDirty() {
        if (!state.currentNote) return;
        state.dirty = true;
        updateEditorState();
    }

    function renderNotesList() {
        const list = app.querySelector("[data-notes-list]");
        if (!state.notes.length) {
            list.innerHTML = `<div class="notes-empty">还没有笔记，点击“新建”开始。</div>`;
            return;
        }
        list.innerHTML = state.notes.map((note) => `
            <button type="button" class="notes-list-item ${state.currentNote && state.currentNote.id === note.id ? "is-active" : ""}" data-note-id="${note.id}">
                <span>${escapeHtml(note.title)}</span>
                <small>${escapeHtml(formatTime(note.updated_at))}</small>
            </button>
        `).join("");
        list.querySelectorAll("[data-note-id]").forEach((button) => {
            button.addEventListener("click", () => selectNote(Number(button.getAttribute("data-note-id"))));
        });
    }

    function updateEditorState() {
        const hasNote = Boolean(state.currentNote);
        const title = app.querySelector("[data-note-title]");
        const editor = app.querySelector("[data-note-editor]");
        const saveButton = app.querySelector("[data-note-save]");
        const deleteButton = app.querySelector("[data-note-delete]");
        const status = app.querySelector("[data-note-status]");
        const error = app.querySelector("[data-notes-error]");

        title.disabled = !hasNote;
        editor.contentEditable = hasNote ? "true" : "false";
        saveButton.disabled = !hasNote || state.saving;
        deleteButton.disabled = !hasNote;
        saveButton.textContent = state.saving ? "保存中" : "保存";
        status.textContent = hasNote ? (state.dirty ? "未保存" : `已保存 ${formatTime(state.currentNote.updated_at)}`) : "请选择或新建笔记";
        error.textContent = state.error;
        renderNotesList();
    }

    function setCurrentNote(note) {
        state.currentNote = note;
        state.dirty = false;
        app.querySelector("[data-note-title]").value = note ? note.title : "";
        app.querySelector("[data-note-editor]").innerHTML = note ? sanitizeNoteHtml(note.content_html) : "";
        updateEditorState();
    }

    async function loadNotes() {
        try {
            const data = await requestJson("/api/notes");
            state.notes = data.items || [];
            state.error = "";
            renderNotesList();
            if (state.notes.length && !state.currentNote) {
                await selectNote(state.notes[0].id, {skipConfirm: true});
            }
        } catch (error) {
            state.error = `加载失败：${error.message}`;
            updateEditorState();
        }
    }

    async function selectNote(noteId, options = {}) {
        if (state.dirty && !options.skipConfirm && !window.confirm("当前笔记还没保存，确定切换吗？")) {
            return;
        }
        try {
            const note = await requestJson(`/api/notes/${noteId}`);
            state.error = "";
            setCurrentNote(note);
        } catch (error) {
            state.error = `打开失败：${error.message}`;
            updateEditorState();
        }
    }

    async function createNote() {
        if (state.dirty && !window.confirm("当前笔记还没保存，确定新建吗？")) return;
        try {
            const note = await requestJson("/api/notes", {
                method: "POST",
                body: JSON.stringify({title: "未命名笔记", content_html: "<p><br></p>"}),
            });
            state.notes.unshift({id: note.id, title: note.title, created_at: note.created_at, updated_at: note.updated_at});
            state.error = "";
            setCurrentNote(note);
            app.querySelector("[data-note-title]").focus();
            app.querySelector("[data-note-title]").select();
        } catch (error) {
            state.error = `新建失败：${error.message}`;
            updateEditorState();
        }
    }

    async function saveCurrentNote() {
        if (!state.currentNote) return;
        const titleInput = app.querySelector("[data-note-title]");
        const editor = app.querySelector("[data-note-editor]");
        const contentHtml = sanitizeNoteHtml(editor.innerHTML);
        const title = titleInput.value.trim() || noteTitleFromHtml(contentHtml);

        state.saving = true;
        state.error = "";
        updateEditorState();
        try {
            const note = await requestJson(`/api/notes/${state.currentNote.id}`, {
                method: "PUT",
                body: JSON.stringify({title, content_html: contentHtml}),
            });
            state.currentNote = note;
            state.dirty = false;
            titleInput.value = note.title;
            editor.innerHTML = sanitizeNoteHtml(note.content_html);
            state.notes = state.notes.map((item) => item.id === note.id ? {
                id: note.id,
                title: note.title,
                created_at: note.created_at,
                updated_at: note.updated_at,
            } : item);
        } catch (error) {
            state.error = `保存失败：${error.message}`;
        } finally {
            state.saving = false;
            updateEditorState();
        }
    }

    async function deleteCurrentNote() {
        if (!state.currentNote) return;
        if (!window.confirm(`确定删除“${state.currentNote.title}”吗？`)) return;
        const noteId = state.currentNote.id;
        try {
            await requestJson(`/api/notes/${noteId}`, {method: "DELETE"});
            state.notes = state.notes.filter((note) => note.id !== noteId);
            state.error = "";
            setCurrentNote(null);
            if (state.notes.length) {
                await selectNote(state.notes[0].id, {skipConfirm: true});
            }
        } catch (error) {
            state.error = `删除失败：${error.message}`;
            updateEditorState();
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
            renderShell();
            await loadNotes();
        } catch (error) {
            state.error = `初始化失败：${error.message}`;
            renderLogin();
        }
    }

    window.addEventListener("beforeunload", (event) => {
        if (state.dirty) {
            event.preventDefault();
            event.returnValue = "";
        }
    });

    init();
})();