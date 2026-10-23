// frontend/js/research-form.js
/* ==========================================================================
   AgentSolve AI - Research form
   Validation, submission, duplicate-submission prevention, polling,
   loading and error states.
   Emits "agentsolve:investigation-update" with { snapshot } on every poll.
   ========================================================================== */
(function (global) {
  "use strict";

  var MIN_LENGTH = 10;
  var MAX_LENGTH = 500;
  var POLL_INTERVAL_MS = 1500;
  var MAX_POLLS = 400;
  var UPDATE_EVENT = "agentsolve:investigation-update";

  var els = {};
  var inFlight = false;
  var runToken = 0;

  function init() {
    els.form = document.getElementById("research-form");
    els.input = document.getElementById("research-question");
    els.error = document.getElementById("question-error");
    els.count = document.getElementById("char-count");
    els.submit = document.getElementById("submit-btn");
    els.reset = document.getElementById("reset-btn");
    els.report = document.getElementById("report-container");

    if (!els.form || !els.input) return;

    els.input.addEventListener("input", function () {
      updateCount();
      if (!els.error.hidden) {
        var check = validateQuestion();
        if (check.ok) clearError();
      }
    });

    els.input.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        if (!inFlight) els.submit.click();
      }
    });

    els.form.addEventListener("submit", onSubmit);

    els.reset.addEventListener("click", function () {
      if (inFlight) return;
      els.input.value = "";
      clearError();
      updateCount();
      els.input.focus();
    });

    updateCount();
  }

  function updateCount() {
    if (!els.count) return;
    els.count.textContent = els.input.value.length + " / " + MAX_LENGTH;
  }

  function validateQuestion() {
    var question = els.input.value.trim();
    if (!question) {
      return { ok: false, message: "Enter a research question to begin." };
    }
    if (question.length < MIN_LENGTH) {
      return { ok: false, message: "Make the question at least " + MIN_LENGTH + " characters so it can be investigated." };
    }
    if (question.length > MAX_LENGTH) {
      return { ok: false, message: "Keep the question under " + MAX_LENGTH + " characters." };
    }
    return { ok: true, value: question };
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.hidden = false;
    els.input.setAttribute("aria-invalid", "true");
  }

  function clearError() {
    els.error.textContent = "";
    els.error.hidden = true;
    els.input.removeAttribute("aria-invalid");
  }

  function setBusy(busy) {
    inFlight = busy;
    els.submit.disabled = busy;
    els.reset.disabled = busy;
    els.input.readOnly = busy;
    els.form.setAttribute("aria-busy", busy ? "true" : "false");
    els.submit.textContent = busy ? "Investigating..." : "Start Investigation";
  }

  function onSubmit(event) {
    event.preventDefault();
    if (inFlight) return;

    var check = validateQuestion();
    if (!check.ok) {
      showError(check.message);
      els.input.focus();
      return;
    }

    clearError();
    startRun(check.value);
  }

  async function startRun(question) {
    var token = ++runToken;
    setBusy(true);
    global.AgentStatus.reset();
    global.AgentStatus.setMessage("Submitting your question...", "info");
    global.ReportRenderer.renderState(
      els.report,
      "loading",
      "Investigation starting",
      "Agents will report progress here as they work."
    );

    var started;
    try {
      started = await global.AgentSolveAPI.startInvestigation(question);
    } catch (err) {
      fail(token, err);
      return;
    }
    if (token !== runToken) return;

    global.AgentSolveAPI.upsertHistory({
      id: started.id,
      question: question,
      status: "queued",
      demo: started.demo === true,
      agents: {},
      sources: [],
      report: null
    }, new Date().toISOString());

    poll(token, started.id, 0);
  }

  async function poll(token, id, attempt) {
    if (token !== runToken) return;

    if (attempt >= MAX_POLLS) {
      fail(token, new Error("The investigation is taking longer than expected. Check the backend and try again."));
      return;
    }

    var snapshot;
    try {
      snapshot = await global.AgentSolveAPI.getInvestigation(id);
    } catch (err) {
      fail(token, err);
      return;
    }
    if (token !== runToken) return;

    global.AgentStatus.update(snapshot);
    global.AgentSolveAPI.upsertHistory(snapshot);
    document.dispatchEvent(new CustomEvent(UPDATE_EVENT, { detail: { snapshot: snapshot } }));

    if (snapshot.status === "complete" || snapshot.status === "insufficient_evidence") {
      finish(token, snapshot);
      return;
    }

    if (snapshot.status === "failed") {
      fail(token, new Error("One of the agents reported a failure. Review the agent cards and try again."), true);
      return;
    }

    global.setTimeout(function () {
      poll(token, id, attempt + 1);
    }, POLL_INTERVAL_MS);
  }

  function finish(token, snapshot) {
    if (token !== runToken) return;
    setBusy(false);
    if (snapshot.status === "complete") {
      global.AgentStatus.setMessage("Investigation complete. Review the report below.", "success");
    } else {
      global.AgentStatus.setMessage("Evidence was insufficient for a firm recommendation. See the report for limitations.", "warning");
    }
  }

  function fail(token, err, fromSnapshot) {
    if (token !== runToken) return;
    setBusy(false);

    var message = err && err.message ? err.message : "Something went wrong. Try again.";
    global.AgentStatus.setMessage(message, "error");

    if (!fromSnapshot) {
      global.ReportRenderer.renderState(
        els.report,
        "error",
        "The investigation could not be completed.",
        message
      );
    }
  }

  function setQuestion(text) {
    if (!els.input) return;
    els.input.value = typeof text === "string" ? text : "";
    clearError();
    updateCount();
  }

  function cancel() {
    if (!inFlight) return;
    runToken += 1;
    setBusy(false);
    global.AgentStatus.setMessage("Live updates stopped. The investigation can be reopened from history.", "info");
  }

  function isBusy() {
    return inFlight;
  }

  global.ResearchForm = {
    init: init,
    setQuestion: setQuestion,
    cancel: cancel,
    isBusy: isBusy
  };
})(window);