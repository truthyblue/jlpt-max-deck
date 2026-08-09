(function () {
  "use strict";

  var VALID_TRACKS = ["vocabulary", "audio", "practice", "reference", "kanji"];
  var VALID_CATEGORIES = ["content", "display", "audio", "other"];
  var VALID_PRACTICE_TYPES = [
    "kanji_reading", "orthography", "word_formation", "context_defined",
    "paraphrase", "usage", "counter", "date", "month", "weekday"
  ];
  var PRACTICE_TYPE_ALIASES = {
    counter_reading: "counter",
    date_reading: "date",
    month_reading: "month",
    weekday_reading: "weekday"
  };
  var TRACK_LABELS = {
    vocabulary: "어휘",
    audio: "음성",
    practice: "실전",
    reference: "참조표",
    kanji: "한자"
  };
  var PLATFORM_LABELS = {
    ios: "iOS",
    android: "Android",
    desktop: "데스크톱",
    unknown: "기타 환경"
  };
  var ERROR_TOAST_DURATION_MS = 3000;

  function detectPlatform() {
    var platform = String(globalThis.ankiPlatform || "").toLowerCase();
    var root = document.documentElement;
    var isAnkiDroidClass = root && root.classList.contains("android");
    if (platform === "ankidroid" || isAnkiDroidClass) {
      return "android";
    }
    var isAnkiMobileClass = root && (
      root.classList.contains("iphone") || root.classList.contains("ipad")
    );
    if (platform === "mobile" || isAnkiMobileClass) {
      return "ios";
    }
    if (platform === "desktop") {
      return "desktop";
    }
    return "unknown";
  }

  function normalizeLevel(value) {
    var level = String(value || "").trim().toUpperCase();
    return /^N[1-5]$/.test(level) ? level : null;
  }

  function selectedCategory(root) {
    var category = root.querySelector(
      "[data-error-report-category] input:checked"
    );
    return category ? String(category.value || "") : "";
  }

  function contextFromRoot(root) {
    var track = String(root.getAttribute("data-report-track") || "").trim();
    var category = selectedCategory(root);
    var description = root.querySelector("[data-error-report-description]");
    if (
      VALID_TRACKS.indexOf(track) < 0 || !description ||
      VALID_CATEGORIES.indexOf(category) < 0
    ) {
      return null;
    }
    var contentRef = String(
      root.getAttribute("data-report-content-ref") || ""
    ).trim();
    var text = String(description.value || "").trim();
    var practiceType = String(
      root.getAttribute("data-report-practice-type") || ""
    ).trim();
    practiceType = PRACTICE_TYPE_ALIASES[practiceType] || practiceType;
    if (
      (track === "practice" && VALID_PRACTICE_TYPES.indexOf(practiceType) < 0) ||
      (track !== "practice" && practiceType)
    ) {
      return null;
    }
    if (!contentRef || contentRef.length > 160 || text.length < 2 || text.length > 1000) {
      return null;
    }
    return {
      schema_version: Number(root.getAttribute("data-report-schema-version")),
      deck_version: String(root.getAttribute("data-report-deck-version") || ""),
      platform: detectPlatform(),
      track: track,
      jlpt_level: normalizeLevel(root.getAttribute("data-report-level")),
      practice_type: practiceType || null,
      content_ref: contentRef,
      category: category,
      description: text
    };
  }

  function contextLabel(root) {
    var platform = detectPlatform();
    var track = String(root.getAttribute("data-report-track") || "");
    var level = normalizeLevel(root.getAttribute("data-report-level"));
    var pieces = [
      "v" + String(root.getAttribute("data-report-deck-version") || ""),
      PLATFORM_LABELS[platform] || PLATFORM_LABELS.unknown
    ];
    if (level) {
      pieces.push(level);
    }
    pieces.push(TRACK_LABELS[track] || track);
    return pieces.join(" · ");
  }

  function updateSubmitState(root) {
    var button = root.querySelector("[data-error-report-submit]");
    if (button) {
      button.disabled = !contextFromRoot(root);
    }
  }

  function hideToast(root) {
    var status = root.querySelector("[data-error-report-status]");
    if (root.__jlptMaxErrorToastTimer) {
      window.clearTimeout(root.__jlptMaxErrorToastTimer);
      root.__jlptMaxErrorToastTimer = null;
    }
    if (status) {
      status.textContent = "";
      status.hidden = true;
    }
  }

  function showToast(root, message) {
    var modal = root.querySelector("[data-error-report-modal]");
    var status = root.querySelector("[data-error-report-status]");
    if (!modal || modal.hidden || !status) {
      return;
    }
    hideToast(root);
    status.textContent = message;
    status.hidden = false;
    root.__jlptMaxErrorToastTimer = window.setTimeout(function () {
      hideToast(root);
    }, ERROR_TOAST_DURATION_MS);
  }

  function openModal(root) {
    var modal = root.querySelector("[data-error-report-modal]");
    var context = root.querySelector("[data-error-report-context]");
    var reference = root.querySelector("[data-error-report-reference]");
    var description = root.querySelector("[data-error-report-description]");
    var status = root.querySelector("[data-error-report-status]");
    var form = root.querySelector("[data-error-report-form]");
    var success = root.querySelector("[data-error-report-success]");
    var intro = root.querySelector("[data-error-report-intro]");
    if (
      !modal || !context || !reference || !description || !status ||
      !form || !success || !intro
    ) {
      return;
    }
    if (!success.hidden) {
      success.hidden = true;
      form.hidden = false;
    }
    intro.hidden = false;
    modal.setAttribute("aria-labelledby", "jlpt-max-error-report-title");
    context.textContent = contextLabel(root);
    reference.textContent = "현재 카드 식별 정보 포함";
    hideToast(root);
    modal.hidden = false;
    updateSubmitState(root);
    description.focus();
  }

  function closeModal(root) {
    var modal = root.querySelector("[data-error-report-modal]");
    hideToast(root);
    if (modal) {
      modal.hidden = true;
    }
  }

  function submitReport(root) {
    var payload = contextFromRoot(root);
    var status = root.querySelector("[data-error-report-status]");
    var submit = root.querySelector("[data-error-report-submit]");
    if (!payload || !status || !submit || typeof window.fetch !== "function") {
      showToast(root, "내용을 2자 이상 입력해 주세요.");
      return;
    }
    submit.disabled = true;
    submit.textContent = "전송 중…";
    hideToast(root);
    window.fetch(root.getAttribute("data-report-endpoint"), {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
      cache: "no-store",
      credentials: "omit",
      mode: "cors",
      referrerPolicy: "no-referrer"
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("report rejected");
      }
      return response.json();
    }).then(function (result) {
      if (!result || result.ok !== true || !result.report_id) {
        throw new Error("report response invalid");
      }
      hideToast(root);
      submit.textContent = "제보 보내기";
      var description = root.querySelector("[data-error-report-description]");
      if (description) {
        description.value = "";
      }
      var form = root.querySelector("[data-error-report-form]");
      var success = root.querySelector("[data-error-report-success]");
      var intro = root.querySelector("[data-error-report-intro]");
      var modal = root.querySelector("[data-error-report-modal]");
      if (form && success && intro && modal) {
        intro.hidden = true;
        form.hidden = true;
        success.hidden = false;
        modal.setAttribute(
          "aria-labelledby", "jlpt-max-error-report-success-title"
        );
        var close = success.querySelector("[data-error-report-close]");
        if (close) {
          close.focus();
        }
      }
    }).catch(function () {
      submit.textContent = "제보 보내기";
      submit.disabled = false;
      showToast(root, "전송하지 못했습니다. 다시 시도해 주세요.");
    });
  }

  function bindRoot(root) {
    if (root.getAttribute("data-error-report-bound") === "true") {
      return;
    }
    root.setAttribute("data-error-report-bound", "true");
    root.querySelectorAll("[data-error-report-open]").forEach(function (button) {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        openModal(root);
      });
    });
    root.querySelectorAll("[data-error-report-close]").forEach(function (button) {
      button.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        closeModal(root);
      });
    });
    var modal = root.querySelector("[data-error-report-modal]");
    var form = root.querySelector("[data-error-report-form]");
    var category = root.querySelector("[data-error-report-category]");
    var description = root.querySelector("[data-error-report-description]");
    if (!modal || !form || !category || !description) {
      return;
    }
    modal.addEventListener("click", function (event) {
      event.stopPropagation();
    });
    category.addEventListener("change", function () {
      updateSubmitState(root);
    });
    description.addEventListener("input", function () {
      updateSubmitState(root);
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      event.stopPropagation();
      submitReport(root);
    });
  }

  function initialize() {
    var roots = document.querySelectorAll("[data-jlpt-max-error-report]");
    var root = roots.length ? roots[roots.length - 1] : null;
    if (root) {
      bindRoot(root);
    }
  }

  if (globalThis.__JLPT_MAX_REPORT_TEST_MODE__) {
    globalThis.__JLPT_MAX_REPORT_TEST_API__ = {
      contextFromRoot: contextFromRoot,
      detectPlatform: detectPlatform,
      normalizeLevel: normalizeLevel
    };
    return;
  }

  initialize();
})();
