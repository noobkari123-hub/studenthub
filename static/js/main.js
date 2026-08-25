(function () {
  "use strict";

  const root = document.documentElement;
  const themeToggle = document.getElementById("theme-toggle");
  const stored = localStorage.getItem("sh-theme");
  if (stored) root.setAttribute("data-theme", stored);
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches) root.setAttribute("data-theme", "dark");
  if (themeToggle) themeToggle.addEventListener("click", function () {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("sh-theme", next);
    themeToggle.textContent = next === "dark" ? "☾" : "☼";
  });

  const navToggle = document.getElementById("nav-toggle");
  const mainNav = document.getElementById("main-nav");
  if (navToggle && mainNav) navToggle.addEventListener("click", function () {
    const isOpen = mainNav.classList.toggle("open");
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  const modal = document.getElementById("auth-modal");
  const modalLogin = document.getElementById("modal-login");
  const modalSignup = document.getElementById("modal-signup");
  function openAuthModal(action) {
    if (!modal) return;
    const next = new URL(window.location.href);
    if (action) next.searchParams.set("ai_action", action);
    const nextValue = next.pathname + next.search;
    if (modalLogin) modalLogin.href = "/login?next=" + encodeURIComponent(nextValue);
    if (modalSignup) modalSignup.href = "/signup?next=" + encodeURIComponent(nextValue);
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }
  function closeAuthModal() {
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }
  document.querySelectorAll("[data-close-auth]").forEach(function (el) { el.addEventListener("click", closeAuthModal); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeAuthModal(); });

  const helperBtns = document.querySelectorAll(".helper-btn");
  const helperOutput = document.getElementById("helper-output");
  let requestBusy = false;

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (c) {
      return ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c];
    });
  }
  function renderMarkdown(text) {
    let html = escapeHtml(text || "");
    html = html.replace(/```([\s\S]*?)```/g, function (_, code) { return "<pre><code>" + code.trim() + "</code></pre>"; });
    html = html.replace(/^### (.*)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.*)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.*)$/gm, "<h2>$1</h2>");
    html = html.replace(/^\* (.*)$/gm, "<li>$1</li>");
    html = html.replace(/^- (.*)$/gm, "<li>$1</li>");
    html = html.replace(/^(\d+)\. (.*)$/gm, "<li>$2</li>");
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\n{2,}/g, "</p><p>");
    html = html.replace(/\n/g, "<br>");
    html = html.replace(/(<li>.*?<\/li>)(?:<br>)+(?=<li>)/g, "$1");
    return "<div class='helper-rich'><p>" + html + "</p></div>";
  }

  async function runHelper(btn) {
    const action = btn.getAttribute("data-action");
    if (!helperOutput || requestBusy) return;
    const topic = String(window.STUDENT_HUB_TOPIC || "").trim();
    const helperContext = String(window.STUDENT_HUB_CONTEXT || "").trim();
    if (!topic) {
      helperOutput.hidden = false;
      helperOutput.innerHTML = "<p>Please search for a question or topic first.</p>";
      return;
    }
    requestBusy = true;
    helperBtns.forEach(function (b) { b.disabled = true; });
    helperOutput.hidden = false;
    helperOutput.innerHTML = "<p>🧠 Thinking about this... <span class='loading-dots'>● ● ●</span></p>";
    try {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
      const resp = await fetch("/api/ai-helper", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ topic: topic, action: action, context: helperContext }),
      });
      const data = await resp.json().catch(function () { return {}; });
      if (resp.status === 401 && data.auth_required) {
        openAuthModal(action);
        return;
      }
      if (!resp.ok) {
        helperOutput.innerHTML = "<p>😕 " + escapeHtml(data.error || "I couldn't process this right now. Please try again.") + "</p>";
        return;
      }
      helperOutput.innerHTML = renderMarkdown(data.result || "No response was generated.");
      helperOutput.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      helperOutput.innerHTML = "<p>😕 Hmm, I couldn't reach the Teddy right now. Please try again.</p>";
    } finally {
      requestBusy = false;
      helperBtns.forEach(function (b) { b.disabled = false; });
    }
  }
  helperBtns.forEach(function (btn) { btn.addEventListener("click", function () { runHelper(btn); }); });

  const autoAction = window.STUDENT_HUB_AUTO_ACTION || "";
  if (autoAction) {
    const autoBtn = document.querySelector('.helper-btn[data-action="' + CSS.escape(autoAction) + '"]');
    if (autoBtn) setTimeout(function () { runHelper(autoBtn); }, 350);
  }
})();
