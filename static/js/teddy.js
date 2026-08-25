(function () {
  "use strict";
  const app = document.getElementById("teddy-app");
  if (!app) return;
  const loggedIn = app.dataset.loggedIn === "true";
  if (!loggedIn) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const history = document.getElementById("teddy-history");
  const conversation = document.getElementById("teddy-conversation");
  const input = document.getElementById("teddy-input");
  const composer = document.getElementById("teddy-composer");
  const send = document.getElementById("teddy-send");
  const newChat = document.getElementById("new-chat");
  const browseToggle = document.getElementById("browse-toggle");
  const menu = document.getElementById("teddy-menu");
  const sidebar = document.getElementById("teddy-sidebar");
  let activeChatId = document.querySelector(".history-item.active")?.dataset.chatId || null;
  let busy = false;
  let browse = false;

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c]));
  }

  // Protect math/code before normal HTML escaping and line-break processing.
  // MathJax then receives the original TeX delimiters unchanged.
  function markdown(text) {
    let source = String(text || "").replace(/\r\n?/g, "\n");
    const protectedParts = [];
    const protect = value => {
      const token = `@@TEDDY_PROTECTED_${protectedParts.length}@@`;
      protectedParts.push(value);
      return token;
    };

    // Normalize common model-escaped display delimiters.
    source = source.replace(/\\\\\[/g, "\\[").replace(/\\\\\]/g, "\\]");
    source = source.replace(/\\\\\(/g, "\\(").replace(/\\\\\)/g, "\\)");

    // Code blocks first.
    source = source.replace(/```([\\s\\S]*?)```/g, (_, code) => protect(`<pre><code>${escapeHtml(code.trim())}</code></pre>`));
    // Display math and inline math are protected from markdown/newline conversion.
    source = source.replace(/\\\[[\\s\\S]*?\\\]/g, m => protect(m));
    source = source.replace(/\\\([\\s\\S]*?\\\)/g, m => protect(m));
    source = source.replace(/\$\$[\\s\\S]*?\$\$/g, m => protect(m));
    source = source.replace(/(?<!\\)\$[^$\n]+(?<!\\)\$/g, m => protect(m));

    let s = escapeHtml(source);
    s = s.replace(/^### (.*)$/gm, "<h4>$1</h4>");
    s = s.replace(/^## (.*)$/gm, "<h3>$1</h3>");
    s = s.replace(/^# (.*)$/gm, "<h2>$1</h2>");
    s = s.replace(/^[-*] (.*)$/gm, "<li>$1</li>");
    s = s.replace(/^(\d+)\. (.*)$/gm, "<li>$2</li>");
    s = s.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>");

    protectedParts.forEach((part, index) => {
      const token = escapeHtml(`@@TEDDY_PROTECTED_${index}@@`);
      s = s.replace(token, part);
    });

    // Turn simple Markdown tables into HTML after math protection.
    s = s.replace(/(?:^|<br>)\|([^<\n]+)\|<br>\|(?:\s*:?-+:?\s*\|)+<br>((?:\|[^<\n]+\|(?:<br>|$))+)/g, (match, header, rows) => {
      const cells = header.split("|").map(x => x.trim()).filter(Boolean);
      const bodyRows = rows.split(/<br>/).filter(Boolean).map(row => row.split("|").map(x => x.trim()).filter(Boolean));
      let html = `<table><thead><tr>${cells.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>`;
      bodyRows.forEach(row => { html += `<tr>${row.map(c => `<td>${c}</td>`).join("")}</tr>`; });
      return `<br>${html}`;
    });

    return `<div class="teddy-rich"><p>${s}</p></div>`;
  }

  async function typesetMath(root) {
    if (!root || !window.MathJax) return;
    try {
      if (window.MathJax.typesetPromise) await window.MathJax.typesetPromise([root]);
      else if (window.MathJax.Hub) window.MathJax.Hub.Queue(["Typeset", window.MathJax.Hub, root]);
    } catch (e) {
      console.warn("Teddy MathJax rendering failed:", e);
    }
  }

  function scrollBottom() {
    requestAnimationFrame(() => {
      if (!conversation) return;
      conversation.scrollTop = conversation.scrollHeight;
    });
  }

  function messageElement(sender, content, pending) {
    const article = document.createElement("article");
    article.className = `teddy-message ${sender}${pending ? " pending" : ""}`;
    article.innerHTML = `<div class="message-avatar">${sender === "teddy" ? "🧸" : "👤"}</div><div class="message-body"><div class="message-name">${sender === "teddy" ? "Teddy" : "You"}</div><div class="message-content">${pending ? '<div class="teddy-thinking"><span></span><span></span><span></span> Teddy is thinking...</div>' : (sender === "teddy" ? markdown(content) : escapeHtml(content).replace(/\n/g,"<br>"))}</div></div>`;
    if (!pending && sender === "teddy") setTimeout(() => typesetMath(article.querySelector(".message-content")), 0);
    return article;
  }

  function showMessages(messages) {
    conversation.innerHTML = `<div class="teddy-message-list" id="teddy-message-list"></div>`;
    const target = document.getElementById("teddy-message-list");
    messages.forEach(m => target.appendChild(messageElement(m.sender, m.content, false)));
    setTimeout(() => typesetMath(target), 0);
    scrollBottom();
  }

  function renderHistory(chats) {
    if (!history) return;
    history.innerHTML = "";
    if (!chats.length) {
      history.innerHTML = `<div class="history-empty"><span>📝</span><p>Your chats will appear here.</p><small>Start a new conversation with Teddy.</small></div>`;
      return;
    }
    const now = new Date();
    const today = now.toDateString();
    const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
    const groups = {"Today": [], "Yesterday": [], "Older": []};
    chats.forEach(chat => {
      const d = new Date(chat.updated_at || chat.created_at);
      if (d.toDateString() === today) groups.Today.push(chat);
      else if (d.toDateString() === yesterday.toDateString()) groups.Yesterday.push(chat);
      else groups.Older.push(chat);
    });
    Object.entries(groups).forEach(([label, items]) => {
      if (!items.length) return;
      const heading = document.createElement("div"); heading.className = "history-label"; heading.textContent = label; history.appendChild(heading);
      items.forEach(chat => {
        const button = document.createElement("button");
        button.className = `history-item${String(chat.id) === String(activeChatId) ? " active" : ""}`;
        button.dataset.chatId = chat.id; button.title = chat.title;
        button.innerHTML = `<span>💬</span><span class="history-title">${escapeHtml(chat.title)}</span>`;
        button.addEventListener("click", () => openChat(chat.id));
        history.appendChild(button);
      });
    });
  }

  async function api(url, options = {}) {
    const headers = Object.assign({"Accept":"application/json", "X-CSRF-Token": csrf}, options.headers || {});
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const response = await fetch(url, Object.assign({}, options, {headers}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && data.login_url) window.location.href = data.login_url;
      const error = new Error(data.error || "Something went wrong.");
      error.type = data.error_type || "unknown";
      error.retryable = Boolean(data.retryable);
      throw error;
    }
    return data;
  }

  async function refreshChats() {
    const data = await api("/api/teddy/chats");
    renderHistory(data.chats || []);
    return data.chats || [];
  }

  async function createNewChat() {
    if (busy) return;
    const data = await api("/api/teddy/chats", {method:"POST", body:JSON.stringify({title:"New Chat"})});
    activeChatId = data.chat.id;
    renderHistory(await refreshChats());
    conversation.innerHTML = `<section class="teddy-welcome" id="empty-welcome"><div class="teddy-welcome-mark">🧸</div><span class="eyebrow-pill">AI TEDDY · FREE FOR STUDENTS 🎓</span><h1>What are we learning today?</h1><p>Ask Teddy anything about your studies. You can keep each subject in its own conversation.</p><div class="teddy-prompt-grid"><button data-prompt="Explain integration in a simple way.">💡 Explain a difficult topic</button><button data-prompt="Solve 2x + 5 = 15 step by step.">🧮 Solve a problem</button><button data-prompt="Help me make a study plan for my next exam.">📝 Prepare for an exam</button><button data-prompt="Quiz me on recursion in Python.">🧠 Quiz me</button></div></section>`;
    bindPrompts(); input.focus();
  }

  async function openChat(chatId) {
    if (busy) return;
    const data = await api(`/api/teddy/chats/${chatId}`);
    activeChatId = chatId;
    renderHistory((await api("/api/teddy/chats")).chats || []);
    showMessages(data.messages || []);
    sidebar.classList.remove("open");
    input.focus();
  }

  async function sendMessage(text) {
    if (!activeChatId) await createNewChat();
    if (!activeChatId || busy) return;
    busy = true;
    send.disabled = true;
    input.disabled = true;
    const empty = document.getElementById("empty-welcome");
    if (empty) empty.remove();
    let target = document.getElementById("teddy-message-list");
    if (!target) { conversation.innerHTML = `<div class="teddy-message-list" id="teddy-message-list"></div>`; target = document.getElementById("teddy-message-list"); }
    const userBubble = messageElement("user", text, false);
    target.appendChild(userBubble);
    const pending = messageElement("teddy", "", true); target.appendChild(pending); scrollBottom();
    try {
      const data = await api(`/api/teddy/chats/${activeChatId}/messages`, {method:"POST", body:JSON.stringify({message:text, use_web:browse})});
      pending.replaceWith(messageElement("teddy", data.teddy_message.content, false));
      const newTeddy = target.lastElementChild;
      if (newTeddy?.classList.contains("teddy")) await typesetMath(newTeddy.querySelector(".message-content"));
      if (data.sources && data.sources.length) {
        const sourceWrap = document.createElement("div");
        sourceWrap.className = "teddy-sources";
        sourceWrap.innerHTML = `<strong>🌐 Sources Teddy used</strong>${data.sources.map(s => `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer"><b>${escapeHtml(s.title)}</b><span>${escapeHtml(s.snippet || "")}</span></a>`).join("")}`;
        target.appendChild(sourceWrap);
      }
      await refreshChats();
    } catch (err) {
      userBubble.remove();
      const errorBubble = messageElement("teddy", `😕 ${err.message || "Teddy couldn't respond right now. Please try again."}`, false);
      if (err.retryable) {
        const retry = document.createElement("button");
        retry.type = "button"; retry.className = "teddy-retry"; retry.textContent = "Try again";
        retry.addEventListener("click", () => { retry.disabled = true; sendMessage(text); });
        errorBubble.querySelector(".message-content")?.appendChild(retry);
      }
      pending.replaceWith(errorBubble);
    } finally {
      busy = false; send.disabled = false; input.disabled = false; input.focus(); scrollBottom();
    }
  }

  function bindPrompts() {
    document.querySelectorAll("[data-prompt]").forEach(button => button.addEventListener("click", () => { input.value = button.dataset.prompt; resize(); input.focus(); }));
  }
  function resize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 180) + "px"; }

  composer?.addEventListener("submit", e => { e.preventDefault(); const text = input.value.trim(); if (!text || busy) return; input.value = ""; resize(); sendMessage(text); });
  input?.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); composer.requestSubmit(); } });
  input?.addEventListener("input", resize);
  newChat?.addEventListener("click", createNewChat);
  browseToggle?.addEventListener("click", () => { browse = !browse; browseToggle.classList.toggle("active", browse); browseToggle.setAttribute("aria-pressed", String(browse)); });
  menu?.addEventListener("click", () => sidebar.classList.toggle("open"));

  document.getElementById("rename-chat")?.addEventListener("click", async () => {
    if (!activeChatId || busy) return;
    const title = prompt("Rename this conversation:", document.querySelector(`.history-item[data-chat-id="${activeChatId}"] .history-title`)?.textContent || "");
    if (!title?.trim()) return;
    try { await api(`/api/teddy/chats/${activeChatId}`, {method:"PATCH", body:JSON.stringify({title:title.trim()})}); await refreshChats(); }
    catch (err) { alert(err.message); }
  });
  document.getElementById("delete-chat")?.addEventListener("click", async () => {
    if (!activeChatId || !confirm("Delete this conversation? This cannot be undone.")) return;
    try { await api(`/api/teddy/chats/${activeChatId}`, {method:"DELETE"}); activeChatId = null; const chats = await refreshChats(); if (chats[0]) openChat(chats[0].id); else createNewChat(); }
    catch (err) { alert(err.message); }
  });

  // Server-rendered messages need the same renderer.
  document.querySelectorAll("#teddy-message-list .teddy-message").forEach(article => {
    const contentEl = article.querySelector(".message-content");
    if (!contentEl) return;
    const raw = contentEl.textContent || "";
    if (article.classList.contains("teddy")) contentEl.innerHTML = markdown(raw);
    else contentEl.innerHTML = escapeHtml(raw).replace(/\n/g,"<br>");
  });
  const initialList = document.getElementById("teddy-message-list");
  if (initialList) setTimeout(() => typesetMath(initialList), 100);

  bindPrompts();
  const initialPrompt = new URLSearchParams(window.location.search).get("prompt");
  if (initialPrompt && input) { input.value = initialPrompt; resize(); input.focus(); }
  refreshChats().catch(() => {});
  resize();
  scrollBottom();
})();
