(function () {
  "use strict";

  const languageSelect = document.getElementById("pg-language");
  const editor = document.getElementById("pg-editor");
  const runBtn = document.getElementById("pg-run");
  const output = document.getElementById("pg-output");
  const aiOutput = document.getElementById("pg-ai-output");

  if (!editor) return; // not on the playground page

  function setOutput(text, isError) {
    output.textContent = text;
    output.classList.toggle("pg-output-error", !!isError);
  }

  // ---- Run Code ----
  runBtn.addEventListener("click", async function () {
    const language = languageSelect.value;
    const code = editor.value;

    if (language === "javascript") {
      runJavaScriptClientSide(code);
      return;
    }

    if (language !== "python") {
      setOutput(
        "Server-side execution isn't available for " + language +
        " yet. Use the AI panel below to get an explanation or generated code.",
        false
      );
      return;
    }

    setOutput("Running…", false);
    try {
      const resp = await fetch("/api/run-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: language, code: code }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setOutput(data.error || "Something went wrong running your code.", true);
        return;
      }
      if (data.blocked_reason) {
        setOutput("Blocked by the playground sandbox: " + data.blocked_reason, true);
      } else if (data.timed_out) {
        setOutput("Your code took too long or used too many resources and was stopped " +
                   "(playground limit: a few seconds of CPU time).", true);
      } else if (data.stderr) {
        setOutput((data.stdout ? data.stdout + "\n" : "") + data.stderr, true);
      } else {
        setOutput(data.stdout || "(no output)", false);
      }
    } catch (e) {
      setOutput("Couldn't reach the server to run your code. Please try again.", true);
    }
  });

  // JavaScript never leaves the browser — this is the same sandboxing
  // any browser tab already gives untrusted JS (no filesystem/OS access);
  // we just capture console.log output into the output panel.
  function runJavaScriptClientSide(code) {
    const logs = [];
    const originalLog = console.log;
    console.log = function (...args) {
      logs.push(args.map(String).join(" "));
    };
    try {
      // eslint-disable-next-line no-new-func
      const fn = new Function(code);
      fn();
      setOutput(logs.join("\n") || "(no output — use console.log to print something)", false);
    } catch (e) {
      setOutput(logs.join("\n") + (logs.length ? "\n" : "") + "Error: " + e.message, true);
    } finally {
      console.log = originalLog;
    }
  }

  // ---- AI code assist buttons ----
  function wireAssistButton(id, action) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", async function () {
      aiOutput.hidden = false;
      aiOutput.textContent = "Working on it…";
      try {
        const resp = await fetch("/api/code-assist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: action,
            code: editor.value,
            language: languageSelect.value,
          }),
        });
        const data = await resp.json();
        if (resp.status === 401 && data.auth_required) {
          const login = new URL(data.login_url, window.location.origin);
          login.searchParams.set("next", window.location.pathname + window.location.search);
          window.location.href = login.toString();
          return;
        }
        if (!resp.ok) {
          aiOutput.textContent = data.error || "Couldn't get a response. Please try again.";
          return;
        }
        aiOutput.textContent = data.result || "No response.";
      } catch (e) {
        aiOutput.textContent = "Couldn't reach the AI assistant. Please try again.";
      }
    });
  }

  wireAssistButton("pg-explain", "explain_code");
  wireAssistButton("pg-debug", "debug_code");
  wireAssistButton("pg-improve", "improve_code");
  wireAssistButton("pg-convert", "convert_code");
})();
