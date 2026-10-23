// frontend/js/app.js
/* ==========================================================================
   AgentSolve AI - Application bootstrap
   Initializes and coordinates the frontend modules:
   api.js -> agent-status.js -> report-renderer.js -> research-form.js
   -> dashboard.js -> app.js
   ========================================================================== */
(function (global) {
  "use strict";

  var UPDATE_EVENT = "agentsolve:investigation-update";
  var OPEN_EVENT = "agentsolve:open";

  var state = {
    snapshot: null
  };

  var els = {
    evidence: null,
    report: null,
    save: null
  };

  var TERMINAL = ["complete", "insufficient_evidence", "failed"];

  function renderSnapshot(snapshot) {
    var R = global.ReportRenderer;
    var status = snapshot ? snapshot.status : null;

    if (!snapshot) {
      R.renderEvidencePanel(els.evidence, []);
      R.renderEmpty(
        els.report,
        "No report yet",
        "Start an investigation to see the recommendation, alternatives, evidence, counterarguments, limitations and next steps here."
      );
      els.save.hidden = true;
      return;
    }

    R.renderEvidencePanel(els.evidence, snapshot.sources, { demo: snapshot.demo });

    if (status === "queued" || status === "running") {
      R.renderState(
        els.report,
        "loading",
        "Agents are working",
        "The report appears here when the Decision agent finishes."
      );
    } else if (status === "failed") {
      R.renderState(
        els.report,
        "error",
        "The investigation did not finish.",
        "Review the agent cards above for the step that stopped."
      );
    } else if (snapshot.report) {
      R.renderReport(els.report, snapshot.report, {
        demo: snapshot.demo,
        question: snapshot.question
      });
    } else if (status === "insufficient_evidence") {
      R.renderState(
        els.report,
        "warning",
        "Insufficient evidence",
        "No firm recommendation could be verified for this question."
      );
    } else {
      R.renderEmpty(
        els.report,
        "No report returned",
        "The investigation finished without a report. Try again with a more specific question."
      );
    }

    var canSave = snapshot.report && (status === "complete" || status === "insufficient_evidence");
    els.save.hidden = !canSave;
    refreshSaveButton();
  }

  function isAlreadySaved(id) {
    return global.AgentSolveAPI.getSavedReports().some(function (entry) {
      return entry.id === id;
    });
  }

  function refreshSaveButton() {
    var snapshot = state.snapshot;
    if (!snapshot || !snapshot.report) {
      els.save.disabled = true;
      return;
    }
    var saved = isAlreadySaved(snapshot.id);
    els.save.disabled = saved;
    els.save.textContent = saved ? "Report saved" : "Save report";
  }

  function onSaveClick() {
    if (!state.snapshot || !state.snapshot.report) return;
    try {
      global.AgentSolveAPI.saveReport(state.snapshot);
      global.AgentStatus.setMessage("Report saved to Saved Reports.", "success");
    } catch (err) {
      global.AgentStatus.setMessage(err.message || "The report could not be saved.", "error");
    }
    refreshSaveButton();
  }

  function onUpdate(event) {
    var snapshot = event && event.detail ? event.detail.snapshot : null;
    if (!snapshot) return;
    state.snapshot = snapshot;
    renderSnapshot(snapshot);
  }

  function onOpen(event) {
    var snapshot = event && event.detail ? event.detail.snapshot : null;
    if (!snapshot) return;

    global.ResearchForm.cancel();
    state.snapshot = snapshot;

    global.Dashboard.showView("investigate");
    global.ResearchForm.setQuestion(snapshot.question || "");
    global.AgentStatus.update(snapshot);
    renderSnapshot(snapshot);

    var terminal = TERMINAL.indexOf(snapshot.status) !== -1;
    global.AgentStatus.setMessage(
      terminal
        ? "Loaded from your saved history on this device."
        : "Showing the last known status for this investigation. Live updates are not resumed automatically.",
      "info"
    );
  }

  function init() {
    if (!global.AgentSolveAPI || !global.AgentStatus || !global.ReportRenderer ||
        !global.ResearchForm || !global.Dashboard) {
      global.console.error("AgentSolve AI: one or more frontend modules failed to load. Check the script paths in index.html.");
      return;
    }

    els.evidence = document.getElementById("evidence-panel");
    els.report = document.getElementById("report-container");
    els.save = document.getElementById("save-report-btn");

    global.AgentStatus.init();
    global.Dashboard.init();
    global.ResearchForm.init();

    if (els.save) {
      els.save.addEventListener("click", onSaveClick);
    }

    document.addEventListener(UPDATE_EVENT, onUpdate);
    document.addEventListener(OPEN_EVENT, onOpen);

    renderSnapshot(null);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);