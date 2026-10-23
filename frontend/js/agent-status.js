// frontend/js/agent-status.js
/* ==========================================================================
   AgentSolve AI - Agent status display
   Updates the five agent cards and the research progress section.
   Only reports statuses supplied by the workflow (or clearly labeled demo).
   All text is set with textContent. No innerHTML.
   ========================================================================== */
(function (global) {
  "use strict";

  var AGENTS = global.AgentSolveAPI ? global.AgentSolveAPI.AGENTS : ["research", "solution", "skeptic", "validation", "decision"];

  var STATUS_LABELS = {
    idle: "Not started",
    queued: "Queued",
    running: "Running",
    complete: "Complete",
    failed: "Failed",
    insufficient_evidence: "Insufficient evidence"
  };

  var DEFAULT_MESSAGES = {
    idle: "Waiting for an investigation.",
    queued: "Waiting for earlier steps.",
    running: "Working on this step.",
    complete: "Step finished.",
    failed: "This step did not finish.",
    insufficient_evidence: "Not enough verified evidence for this step."
  };

  var els = {
    cards: {},
    label: null,
    count: null,
    bar: null,
    fill: null,
    message: null
  };

  function init() {
    AGENTS.forEach(function (name) {
      els.cards[name] = document.querySelector('[data-agent="' + name + '"]');
    });
    els.label = document.getElementById("progress-label");
    els.count = document.getElementById("progress-count");
    els.bar = document.getElementById("progress-bar");
    els.fill = document.getElementById("progress-fill");
    els.message = document.getElementById("status-message");
    reset();
  }

  function setCard(name, agent, demo) {
    var card = els.cards[name];
    if (!card) return;

    var status = STATUS_LABELS[agent.status] ? agent.status : "idle";
    var label = STATUS_LABELS[status];

    card.setAttribute("data-status", status);

    var badge = card.querySelector('[data-role="status"]');
    if (badge) {
      badge.textContent = demo && status !== "idle" ? "Simulated: " + label : label;
      badge.className = "status-badge status-" + status;
    }

    var message = card.querySelector('[data-role="message"]');
    if (message) {
      message.textContent = agent.message || DEFAULT_MESSAGES[status];
    }
  }

  function setProgress(completeCount, runStatus, demo) {
    var total = AGENTS.length;
    var percent = Math.round((completeCount / total) * 100);

    if (els.fill) els.fill.style.width = percent + "%";
    if (els.bar) els.bar.setAttribute("aria-valuenow", String(percent));
    if (els.count) els.count.textContent = completeCount + " of " + total + " agents complete";

    var label;
    if (runStatus === "complete") label = "Investigation complete.";
    else if (runStatus === "insufficient_evidence") label = "Evidence was insufficient for a firm recommendation.";
    else if (runStatus === "failed") label = "The investigation stopped before completion.";
    else if (runStatus === "queued") label = "Investigation queued.";
    else label = "Investigation in progress.";

    if (els.label) {
      els.label.textContent = demo ? label + " (demo simulation)" : label;
    }
  }

  function setMessage(text, kind) {
    if (!els.message) return;
    els.message.textContent = text || "";
    els.message.className = "status-message" + (kind ? " is-" + kind : "");
  }

  function reset() {
    AGENTS.forEach(function (name) {
      setCard(name, { status: "idle", message: "" }, false);
    });
    setProgress(0, "idle", false);
    if (els.label) els.label.textContent = "Waiting for a research question.";
    setMessage("", null);
  }

  function update(snapshot) {
    if (!snapshot) return;
    var agents = snapshot.agents || {};
    var demo = snapshot.demo === true;
    var complete = 0;

    AGENTS.forEach(function (name) {
      var agent = agents[name] || { status: "idle", message: "" };
      setCard(name, agent, demo);
      if (agent.status === "complete") complete += 1;
    });

    setProgress(complete, snapshot.status, demo);
  }

  global.AgentStatus = {
    init: init,
    reset: reset,
    update: update,
    setMessage: setMessage
  };
})(window);