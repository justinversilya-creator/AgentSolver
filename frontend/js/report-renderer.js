// frontend/js/report-renderer.js
/* ==========================================================================
   AgentSolve AI - Report and evidence renderer
   Renders untrusted research content with DOM APIs only (no innerHTML).
   Source links are created only for valid http:// and https:// URLs.
   ========================================================================== */
(function (global) {
  "use strict";

  var VERIFY_LABELS = {
    verified: "Verified",
    unverified: "Not verified",
    demo: "Demo placeholder",
    rejected: "Rejected"
  };

  var VERIFY_CLASSES = {
    verified: "badge-success",
    unverified: "badge-muted",
    demo: "badge-navy",
    rejected: "badge-danger"
  };

  function isSafeUrl(url) {
    return global.AgentSolveAPI ? global.AgentSolveAPI.isHttpUrl(url) : false;
  }

  /**
   * Creates an element. Strings in children become text nodes.
   * options: { className, text, attrs }
   */
  function el(tag, options, children) {
    var node = document.createElement(tag);
    options = options || {};
    if (options.className) node.className = options.className;
    if (options.text !== undefined && options.text !== null) node.textContent = String(options.text);
    if (options.attrs) {
      Object.keys(options.attrs).forEach(function (key) {
        node.setAttribute(key, options.attrs[key]);
      });
    }
    (children || []).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function str(value, max) {
    if (typeof value === "number") return String(value);
    if (typeof value !== "string") return "";
    return value.slice(0, max || 2000);
  }

  function list(value) {
    return Array.isArray(value) ? value : [];
  }

  function verificationBadge(verification) {
    var key = VERIFY_LABELS[verification] ? verification : "unverified";
    return el("span", { className: "badge " + VERIFY_CLASSES[key], text: VERIFY_LABELS[key] });
  }

  function sourceLink(url) {
    if (isSafeUrl(url)) {
      return el("a", {
        className: "source-link",
        text: url,
        attrs: { href: url, target: "_blank", rel: "noopener noreferrer" }
      });
    }
    return el("span", { className: "source-link is-missing", text: "No valid source link" });
  }

  /* ---------- States ---------- */
  function renderEmpty(container, title, text) {
    clear(container);
    container.appendChild(el("div", { className: "state state-empty" }, [
      el("p", { className: "state-title", text: title }),
      el("p", { className: "state-text", text: text })
    ]));
  }

  function renderState(container, type, title, text) {
    clear(container);
    var role = type === "error" ? "alert" : "status";
    container.appendChild(el("div", {
      className: "state state-" + type,
      attrs: { role: role }
    }, [
      el("p", { className: "state-title", text: title }),
      text ? el("p", { className: "state-text", text: text }) : null
    ]));
  }

  /* ---------- Evidence panel ---------- */
  function renderEvidencePanel(container, sources, options) {
    options = options || {};
    var items = list(sources);
    clear(container);

    if (!items.length) {
      container.appendChild(el("div", { className: "state state-empty" }, [
        el("p", { className: "state-title", text: "No sources yet" }),
        el("p", {
          className: "state-text",
          text: options.emptyText || "Sources appear here as the Research agent gathers them. Only links that pass validation are shown."
        })
      ]));
      return;
    }

    if (options.demo) {
      container.appendChild(el("p", {
        className: "notice notice-navy",
        text: "Demo mode: these sources are placeholders, not real citations."
      }));
    }

    var listNode = el("ul", { className: "evidence-list" });
    items.forEach(function (source) {
      source = source && typeof source === "object" ? source : {};
      listNode.appendChild(el("li", { className: "evidence-item" }, [
        el("div", { className: "evidence-head" }, [
          el("p", { className: "evidence-title", text: str(source.title, 300) || "Untitled source" }),
          verificationBadge(source.verification)
        ]),
        sourceLink(source.url)
      ]));
    });
    container.appendChild(listNode);
  }

  /* ---------- Report ---------- */
  function section(id, title, body) {
    return el("section", {
      className: "report-section",
      attrs: { "aria-labelledby": id }
    }, [
      el("h4", { attrs: { id: id }, text: title }),
      body
    ]);
  }

  function emptyLine(text) {
    return el("p", { className: "help", text: text });
  }

  function renderReport(container, report, options) {
    options = options || {};
    if (!report || typeof report !== "object") {
      renderEmpty(container, "No report yet", "The final report appears here when the Decision agent completes.");
      return;
    }

    var isDemo = report.demo === true || options.demo === true;
    var rec = report.recommendation && typeof report.recommendation === "object" ? report.recommendation : {};
    var alternatives = list(report.alternatives);
    var evidence = list(report.evidence);
    var counterarguments = list(report.counterarguments);
    var limitations = list(report.limitations);
    var nextSteps = list(report.nextSteps);

    clear(container);

    var article = el("article", {
      className: "report",
      attrs: { "aria-labelledby": "report-title" }
    });

    article.appendChild(el("header", { className: "report-head" }, [
      el("p", {
        className: "eyebrow",
        text: isDemo ? "Demo report: sample layout only" : "Final report"
      }),
      el("h3", {
        className: "report-title",
        attrs: { id: "report-title" },
        text: str(report.question, 500) || options.question || "Research report"
      })
    ]));

    if (report.insufficientEvidence === true) {
      article.appendChild(el("div", {
        className: "notice notice-warning",
        attrs: { role: "status" },
        text: "Insufficient evidence: the agents could not verify enough sources for a firm recommendation. Treat the findings below as provisional."
      }));
    }

    /* Recommendation */
    article.appendChild(section("rep-recommendation", "Recommendation", el("div", {}, [
      el("p", { className: "recommendation", text: str(rec.summary, 2000) || "No recommendation was provided." }),
      rec.confidence
        ? el("p", { className: "help recommendation-meta", text: "Confidence: " + str(rec.confidence, 200) })
        : null
    ])));

    /* Alternatives */
    var altBody = alternatives.length
      ? el("ul", { className: "report-list" }, alternatives.map(function (alt) {
          alt = alt && typeof alt === "object" ? alt : {};
          return el("li", {}, [
            el("p", { className: "alt-title", text: str(alt.title, 300) || "Alternative" }),
            el("p", { text: str(alt.description, 1000) })
          ]);
        }))
      : emptyLine("No alternatives were recorded.");
    article.appendChild(section("rep-alternatives", "Alternatives", altBody));

    /* Evidence */
    var evidenceBody = evidence.length
      ? el("ul", { className: "report-list" }, evidence.map(function (item) {
          item = item && typeof item === "object" ? item : {};
          return el("li", {}, [
            el("p", { className: "evidence-claim", text: str(item.claim, 1000) || "Unstated claim" }),
            el("div", { className: "evidence-meta" }, [
              el("span", { text: str(item.sourceTitle, 300) || "Unknown source" }),
              sourceLink(item.url),
              verificationBadge(item.verification)
            ])
          ]);
        }))
      : emptyLine("No evidence claims were recorded.");
    article.appendChild(section("rep-evidence", "Evidence", evidenceBody));

    /* Counterarguments */
    var counterBody = counterarguments.length
      ? el("ul", { className: "report-list" }, counterarguments.map(function (text) {
          return el("li", { text: str(text, 1000) });
        }))
      : emptyLine("No counterarguments were recorded.");
    article.appendChild(section("rep-counter", "Counterarguments", counterBody));

    /* Limitations */
    var limitBody = limitations.length
      ? el("ul", { className: "report-list" }, limitations.map(function (text) {
          return el("li", { text: str(text, 1000) });
        }))
      : emptyLine("No limitations were recorded.");
    article.appendChild(section("rep-limits", "Limitations", limitBody));

    /* Next steps */
    var nextBody = nextSteps.length
      ? el("ol", { className: "report-ordered" }, nextSteps.map(function (text) {
          return el("li", { text: str(text, 1000) });
        }))
      : emptyLine("No next steps were recorded.");
    article.appendChild(section("rep-next", "Next steps", nextBody));

    container.appendChild(article);
  }

  global.ReportRenderer = {
    el: el,
    clear: clear,
    isSafeUrl: isSafeUrl,
    renderEmpty: renderEmpty,
    renderState: renderState,
    renderEvidencePanel: renderEvidencePanel,
    renderReport: renderReport
  };
})(window);