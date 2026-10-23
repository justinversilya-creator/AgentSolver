// frontend/js/api.js
/* ==========================================================================
   AgentSolve AI - API client
   Centralized access to the FastAPI backend.
   - Base URL is configurable in Settings (stored in this browser only).
   - Demo mode returns clearly labeled sample data with simulated progress.
   - No API keys or n8n credentials are ever stored or sent from this file.

   Expected backend contract (for future FastAPI integration):
     POST {base}/api/investigations         body: { question }  -> { id }
     GET  {base}/api/investigations/{id}    -> {
            id, status, question, agents: { research|solution|skeptic|validation|decision: { status, message } },
            sources: [{ title, url, verification }],
            report: { recommendation, alternatives, evidence, counterarguments, limitations, nextSteps, insufficientEvidence }
          }
   ========================================================================== */
(function (global) {
  "use strict";

  var STORAGE = {
    settings: "agentsolve.settings.v1",
    history: "agentsolve.history.v1",
    saved: "agentsolve.savedReports.v1"
  };

  var AGENTS = ["research", "solution", "skeptic", "validation", "decision"];
  var AGENT_STATUSES = ["idle", "queued", "running", "complete", "failed", "insufficient_evidence"];
  var RUN_STATUSES = ["queued", "running", "complete", "failed", "insufficient_evidence"];
  var VERIFICATION = ["verified", "unverified", "demo", "rejected"];

  var DEFAULTS = {
    apiBaseUrl: "http://localhost:8000",
    demoMode: true,
    timeoutMs: 15000
  };

  var DEMO_STEP_MS = 1800;
  var DEMO_PREFIX = "demo-";
  var HISTORY_LIMIT = 100;
  var SAVED_LIMIT = 200;

  /* ---------- Errors ---------- */
  var ApiError = (function () {
    function ApiError(message, status) {
      this.name = "ApiError";
      this.message = message;
      this.status = status || 0;
    }
    ApiError.prototype = Object.create(Error.prototype);
    ApiError.prototype.constructor = ApiError;
    return ApiError;
  })();

  function messageForStatus(status) {
    if (status === 400 || status === 422) return "The backend rejected this question. Revise it and try again.";
    if (status === 401 || status === 403) return "The backend refused access. Check the backend configuration.";
    if (status === 404) return "The requested investigation was not found.";
    if (status === 429) return "Too many requests. Wait a moment and try again.";
    if (status >= 500) return "The backend encountered an error. Try again shortly.";
    return "The backend returned an unexpected response (HTTP " + status + ").";
  }

  /* ---------- Helpers ---------- */
  function isHttpUrl(value) {
    if (typeof value !== "string" || !value) return false;
    try {
      var url = new URL(value);
      return url.protocol === "http:" || url.protocol === "https:";
    } catch (err) {
      return false;
    }
  }

  function readJson(key, fallback) {
    try {
      var raw = global.localStorage.getItem(key);
      if (!raw) return fallback;
      var parsed = JSON.parse(raw);
      return parsed === null || parsed === undefined ? fallback : parsed;
    } catch (err) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    try {
      global.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (err) {
      return false;
    }
  }

  function newId(prefix) {
    return (prefix || "") + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  /* ---------- Settings ---------- */
  var storedSettings = readJson(STORAGE.settings, {}) || {};
  var settings = {
    apiBaseUrl: typeof storedSettings.apiBaseUrl === "string" ? storedSettings.apiBaseUrl : DEFAULTS.apiBaseUrl,
    demoMode: storedSettings.demoMode === false ? false : DEFAULTS.demoMode,
    timeoutMs: DEFAULTS.timeoutMs
  };

  function getConfig() {
    return { apiBaseUrl: settings.apiBaseUrl, demoMode: settings.demoMode, timeoutMs: settings.timeoutMs };
  }

  function updateSettings(patch) {
    patch = patch || {};
    if (typeof patch.apiBaseUrl === "string") {
      settings.apiBaseUrl = patch.apiBaseUrl.trim().replace(/\/+$/, "");
    }
    if (typeof patch.demoMode === "boolean") {
      settings.demoMode = patch.demoMode;
    }
    writeJson(STORAGE.settings, { apiBaseUrl: settings.apiBaseUrl, demoMode: settings.demoMode });
    return getConfig();
  }

  /* ---------- HTTP ---------- */
  async function request(path, options) {
    options = options || {};
    var base = settings.apiBaseUrl;
    if (!isHttpUrl(base)) {
      throw new ApiError("The API base URL must start with http:// or https://. Update it in Settings.");
    }

    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, settings.timeoutMs) : null;

    var init = {
      method: options.method || "GET",
      headers: { Accept: "application/json" },
      credentials: "omit",
      cache: "no-store"
    };
    if (controller) init.signal = controller.signal;
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }

    var response;
    try {
      response = await fetch(base + path, init);
    } catch (err) {
      if (timer) clearTimeout(timer);
      if (err && err.name === "AbortError") {
        throw new ApiError("The request timed out. Check that the backend is running.");
      }
      throw new ApiError("Could not reach the AgentSolve backend. Check the API base URL in Settings.");
    }
    if (timer) clearTimeout(timer);

    var text;
    try {
      text = await response.text();
    } catch (err) {
      throw new ApiError("The response could not be read.", response.status);
    }

    if (!response.ok) {
      throw new ApiError(messageForStatus(response.status), response.status);
    }

    var data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }
    if (data === null || typeof data !== "object") {
      throw new ApiError("The server returned an unreadable response.", response.status);
    }
    return data;
  }

  /* ---------- Demo mode (clearly labeled placeholder data) ---------- */
  var demoRuns = {};

  var DEMO_SOURCES = [
    { title: "Sample source 1 (demo placeholder, not a real citation)", url: null, verification: "demo" },
    { title: "Sample source 2 (demo placeholder, not a real citation)", url: null, verification: "demo" },
    { title: "Sample source 3 (demo placeholder, not a real citation)", url: null, verification: "demo" }
  ];

  function demoAgentMessage(status) {
    if (status === "complete") return "Simulated step finished (demo).";
    if (status === "running") return "Simulated step in progress (demo).";
    return "Waiting for earlier steps (demo).";
  }

  function buildDemoReport(question) {
    return {
      question: question,
      demo: true,
      recommendation: {
        summary: "Demo layout only. The Decision agent's recommendation will appear here once the backend returns a verified report.",
        confidence: "Not assessed in demo mode"
      },
      alternatives: [
        { title: "Placeholder alternative A", description: "Illustrative candidate approach. This is not a research finding." },
        { title: "Placeholder alternative B", description: "Illustrative second candidate approach. This is not a research finding." }
      ],
      evidence: [
        { claim: "Placeholder evidence statement for layout testing.", sourceTitle: DEMO_SOURCES[0].title, url: null, verification: "demo" }
      ],
      counterarguments: ["Placeholder counterargument shown for layout testing (demo)."],
      limitations: ["Everything in demo mode is placeholder text and is not research output."],
      nextSteps: ["Enter the backend base URL in Settings and turn off demo mode to run a live investigation."],
      insufficientEvidence: false
    };
  }

  function buildDemoSnapshot(id) {
    var run = demoRuns[id];
    if (!run) throw new ApiError("The requested investigation was not found.", 404);

    var elapsed = Date.now() - run.startedAt;
    var doneCount = Math.min(AGENTS.length, Math.floor(elapsed / DEMO_STEP_MS));
    var finished = doneCount >= AGENTS.length;

    var agents = {};
    AGENTS.forEach(function (name, index) {
      var status;
      if (index < doneCount) status = "complete";
      else if (index === doneCount && !finished) status = "running";
      else status = "queued";
      agents[name] = { status: status, message: demoAgentMessage(status) };
    });

    return normalizeSnapshot({
      id: id,
      status: finished ? "complete" : "running",
      question: run.question,
      demo: true,
      agents: agents,
      sources: finished ? DEMO_SOURCES : [],
      report: finished ? buildDemoReport(run.question) : null
    }, id);
  }

  /* ---------- Normalization (never trust backend data blindly) ---------- */
  function normalizeSnapshot(raw, fallbackId) {
    raw = raw && typeof raw === "object" ? raw : {};

    var status = RUN_STATUSES.indexOf(raw.status) !== -1 ? raw.status : "failed";

    var agents = {};
    AGENTS.forEach(function (name) {
      var agent = raw.agents && typeof raw.agents === "object" && raw.agents[name] ? raw.agents[name] : {};
      agents[name] = {
        status: AGENT_STATUSES.indexOf(agent.status) !== -1 ? agent.status : "idle",
        message: typeof agent.message === "string" ? agent.message.slice(0, 300) : ""
      };
    });

    var sources = Array.isArray(raw.sources)
      ? raw.sources.slice(0, 50).map(function (source) {
          source = source && typeof source === "object" ? source : {};
          return {
            title: typeof source.title === "string" && source.title.trim()
              ? source.title.trim().slice(0, 300)
              : "Untitled source",
            url: isHttpUrl(source.url) ? source.url : null,
            verification: VERIFICATION.indexOf(source.verification) !== -1 ? source.verification : "unverified"
          };
        })
      : [];

    return {
      id: String(raw.id || fallbackId || ""),
      question: typeof raw.question === "string" ? raw.question : "",
      status: status,
      demo: raw.demo === true,
      agents: agents,
      sources: sources,
      report: raw.report && typeof raw.report === "object" ? raw.report : null
    };
  }

  /* ---------- Investigations ---------- */
  async function startInvestigation(question) {
    if (typeof question !== "string" || !question.trim()) {
      throw new ApiError("A research question is required.");
    }

    if (settings.demoMode) {
      var demoId = newId(DEMO_PREFIX);
      demoRuns[demoId] = { question: question.trim(), startedAt: Date.now() };
      return { id: demoId, demo: true };
    }

    var data = await request("/api/investigations", {
      method: "POST",
      body: { question: question.trim() }
    });
    if (typeof data.id !== "string" && typeof data.id !== "number") {
      throw new ApiError("The backend did not return an investigation id.");
    }
    return { id: String(data.id), demo: false };
  }

  async function getInvestigation(id) {
    if (typeof id !== "string" || !id) {
      throw new ApiError("A valid investigation id is required.");
    }
    if (id.indexOf(DEMO_PREFIX) === 0) {
      return buildDemoSnapshot(id);
    }
    var raw = await request("/api/investigations/" + encodeURIComponent(id));
    return normalizeSnapshot(raw, id);
  }

  /* ---------- History (stored locally in this browser) ---------- */
  function getHistory() {
    var list = readJson(STORAGE.history, []);
    return Array.isArray(list) ? list.filter(function (entry) {
      return entry && typeof entry.id === "string";
    }) : [];
  }

  function upsertHistory(snapshot, createdAt) {
    if (!snapshot || !snapshot.id) return null;
    var list = getHistory();
    var index = -1;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === snapshot.id) { index = i; break; }
    }
    var existingCreated = index !== -1 ? list[index].createdAt : null;
    var entry = {
      id: snapshot.id,
      question: snapshot.question || "",
      status: snapshot.status || "queued",
      demo: snapshot.demo === true,
      createdAt: existingCreated || createdAt || new Date().toISOString(),
      snapshot: snapshot
    };
    if (index !== -1) {
      list[index] = entry;
    } else {
      list.unshift(entry);
    }
    writeJson(STORAGE.history, list.slice(0, HISTORY_LIMIT));
    return entry;
  }

  /* ---------- Saved reports (stored locally in this browser) ---------- */
  function getSavedReports() {
    var list = readJson(STORAGE.saved, []);
    return Array.isArray(list) ? list.filter(function (entry) {
      return entry && typeof entry.id === "string" && entry.snapshot;
    }) : [];
  }

  function saveReport(snapshot) {
    if (!snapshot || !snapshot.id || !snapshot.report) {
      throw new ApiError("Only completed reports can be saved.");
    }
    var list = getSavedReports().filter(function (entry) { return entry.id !== snapshot.id; });
    var entry = {
      id: snapshot.id,
      question: snapshot.question || "",
      savedAt: new Date().toISOString(),
      snapshot: snapshot
    };
    list.unshift(entry);
    if (!writeJson(STORAGE.saved, list.slice(0, SAVED_LIMIT))) {
      throw new ApiError("The report could not be saved. Browser storage may be full or disabled.");
    }
    return entry;
  }

  function removeSavedReport(id) {
    var list = getSavedReports().filter(function (entry) { return entry.id !== id; });
    writeJson(STORAGE.saved, list);
    return list;
  }

  function clearLocalData() {
    try {
      global.localStorage.removeItem(STORAGE.history);
      global.localStorage.removeItem(STORAGE.saved);
    } catch (err) {
      return false;
    }
    return true;
  }

  global.AgentSolveAPI = {
    AGENTS: AGENTS.slice(),
    ApiError: ApiError,
    isHttpUrl: isHttpUrl,
    getConfig: getConfig,
    updateSettings: updateSettings,
    startInvestigation: startInvestigation,
    getInvestigation: getInvestigation,
    getHistory: getHistory,
    upsertHistory: upsertHistory,
    getSavedReports: getSavedReports,
    saveReport: saveReport,
    removeSavedReport: removeSavedReport,
    clearLocalData: clearLocalData
  };
})(window);