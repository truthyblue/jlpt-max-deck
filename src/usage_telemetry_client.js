(function () {
  "use strict";

  var CONSENT_COOKIE = "jlpt_max_deck_usage_consent_v1";
  var INSTALLATION_COOKIE = "jlpt_max_deck_usage_installation_v1";
  var CURRENT_COUNTERS_COOKIE = "jlpt_max_deck_usage_current_v1";
  var PREVIOUS_COUNTERS_COOKIE = "jlpt_max_deck_usage_previous_v1";
  var PROMPT_COUNT_COOKIE = "jlpt_max_deck_usage_prompt_count_v1";
  var COOKIE_ATTRIBUTES = "; Max-Age=31536000; Path=/; SameSite=Lax";
  var VALID_TRACKS = ["vocabulary", "audio", "practice", "reference", "kanji"];
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

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function parseJson(value) {
    if (typeof value !== "string") {
      return null;
    }
    try {
      return JSON.parse(value);
    } catch (_error) {
      return null;
    }
  }

  function readCookie(name) {
    try {
      var prefix = name + "=";
      var cookies = String(document.cookie || "").split(";");
      for (var index = 0; index < cookies.length; index += 1) {
        var cookie = cookies[index].trim();
        if (cookie.indexOf(prefix) === 0) {
          return decodeURIComponent(cookie.slice(prefix.length));
        }
      }
    } catch (_error) {}
    return null;
  }

  function writeCookie(name, value) {
    try {
      document.cookie = name + "=" + encodeURIComponent(value) +
        COOKIE_ATTRIBUTES;
      return readCookie(name) === value;
    } catch (_error) {
      return false;
    }
  }

  function removeCookie(name) {
    try {
      document.cookie = name + "=; Max-Age=0; Path=/; SameSite=Lax";
    } catch (_error) {}
  }

  function cookieAvailable() {
    var probe = "jlpt_max_deck_usage_probe";
    var available = writeCookie(probe, "1");
    removeCookie(probe);
    return available;
  }

  function detectPlatform() {
    var platform = String(globalThis.ankiPlatform || "").toLowerCase();
    var root = document.documentElement;
    var isAnkiDroidClass = root && root.classList.contains("android");
    if (isAnkiDroidClass) {
      return "android";
    }
    if (platform === "ankidroid") {
      // Retain the legacy bridge fallback while excluding previewers that
      // expose only the platform label.
      return (
        typeof AnkiDroidJS !== "undefined" ||
        typeof globalThis.AnkiDroidJS !== "undefined"
      ) ? "android" : null;
    }
    var isAnkiMobileClass = root && (
      root.classList.contains("iphone") || root.classList.contains("ipad")
    );
    if (platform === "mobile" || isAnkiMobileClass) {
      return "ios";
    }
    return null;
  }

  function localDay() {
    var value = new Date();
    var year = String(value.getFullYear());
    var month = String(value.getMonth() + 1).padStart(2, "0");
    var day = String(value.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function normalizeLevel(value) {
    var level = String(value || "").trim().toUpperCase();
    return /^N[1-5]$/.test(level) ? level : null;
  }

  function normalizePracticeType(value) {
    var practiceType = String(value || "").trim();
    practiceType = PRACTICE_TYPE_ALIASES[practiceType] || practiceType;
    return VALID_PRACTICE_TYPES.indexOf(practiceType) >= 0
      ? practiceType
      : null;
  }

  function normalizedContext(root, platform) {
    var track = String(root.getAttribute("data-track") || "").trim();
    var version = String(root.getAttribute("data-deck-version") || "").trim();
    if (
      VALID_TRACKS.indexOf(track) < 0 ||
      !/^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(version)
    ) {
      return null;
    }
    var practiceType = normalizePracticeType(
      root.getAttribute("data-practice-type")
    );
    if (track === "practice" && !practiceType) {
      return null;
    }
    return {
      platform: platform,
      deckVersion: version,
      track: track,
      jlptLevel: normalizeLevel(root.getAttribute("data-level")),
      practiceType: track === "practice" ? practiceType : null
    };
  }

  function readConsent(policyVersion) {
    var consent = parseJson(readCookie(CONSENT_COOKIE));
    if (
      !isObject(consent) || consent.policy_version !== policyVersion ||
      (consent.choice !== "on" && consent.choice !== "off")
    ) {
      return null;
    }
    return consent.choice;
  }

  function writeConsent(policyVersion, choice) {
    return writeCookie(CONSENT_COOKIE, JSON.stringify({
      policy_version: policyVersion,
      choice: choice
    }));
  }

  function clearTransmittedUsageState() {
    removeCookie(INSTALLATION_COOKIE);
    removeCookie(CURRENT_COUNTERS_COOKIE);
    removeCookie(PREVIOUS_COUNTERS_COOKIE);
  }

  function clearUsageState() {
    clearTransmittedUsageState();
    removeCookie(PROMPT_COUNT_COOKIE);
  }

  function randomInstallationId() {
    try {
      if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
        return globalThis.crypto.randomUUID();
      }
      if (globalThis.crypto && typeof globalThis.crypto.getRandomValues === "function") {
        var bytes = new Uint8Array(16);
        globalThis.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        var hex = Array.prototype.map.call(bytes, function (byte) {
          return byte.toString(16).padStart(2, "0");
        }).join("");
        return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" +
          hex.slice(12, 16) + "-" + hex.slice(16, 20) + "-" + hex.slice(20);
      }
    } catch (_error) {}
    return null;
  }

  function ensureInstallationId() {
    var current = String(readCookie(INSTALLATION_COOKIE) || "");
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(current)) {
      return current;
    }
    var created = randomInstallationId();
    if (!created || !writeCookie(INSTALLATION_COOKIE, created)) {
      return null;
    }
    return created;
  }

  function emptyCounters() {
    return {schema_version: 1, days: {}, last_success_day: null};
  }

  function readCounterCookie(name) {
    var record = parseJson(readCookie(name));
    if (
      !isObject(record) ||
      !/^\d{4}-\d{2}-\d{2}$/.test(String(record.activity_day || "")) ||
      !isObject(record.state) ||
      !isObject(record.state.buckets)
    ) {
      return null;
    }
    return record;
  }

  function readCounters() {
    var counters = emptyCounters();
    [PREVIOUS_COUNTERS_COOKIE, CURRENT_COUNTERS_COOKIE].forEach(function (name) {
      var record = readCounterCookie(name);
      if (!record) {
        return;
      }
      counters.days[record.activity_day] = record.state;
      if (
        Number(record.state.last_success_total) > 0 &&
        (!counters.last_success_day ||
          record.activity_day > counters.last_success_day)
      ) {
        counters.last_success_day = record.activity_day;
      }
    });
    return counters;
  }

  function writeCounters(counters) {
    if (!isObject(counters) || !isObject(counters.days)) {
      return false;
    }
    var dayKeys = Object.keys(counters.days).filter(function (dayKey) {
      var day = counters.days[dayKey];
      return /^\d{4}-\d{2}-\d{2}$/.test(dayKey) &&
        isObject(day) && isObject(day.buckets);
    }).sort().slice(-2);
    var currentKey = dayKeys.length ? dayKeys[dayKeys.length - 1] : null;
    var previousKey = dayKeys.length > 1 ? dayKeys[dayKeys.length - 2] : null;
    var previousWritten = true;
    var currentWritten = true;
    if (previousKey) {
      previousWritten = writeCookie(PREVIOUS_COUNTERS_COOKIE, JSON.stringify({
        activity_day: previousKey,
        state: counters.days[previousKey]
      }));
    } else {
      removeCookie(PREVIOUS_COUNTERS_COOKIE);
    }
    if (currentKey) {
      currentWritten = writeCookie(CURRENT_COUNTERS_COOKIE, JSON.stringify({
        activity_day: currentKey,
        state: counters.days[currentKey]
      }));
    } else {
      removeCookie(CURRENT_COUNTERS_COOKIE);
    }
    return previousWritten && currentWritten;
  }

  function bucketKey(context) {
    return [
      context.deckVersion,
      context.track,
      context.jlptLevel || "",
      context.practiceType || ""
    ].join("|");
  }

  function incrementCounter(counters, dayKey, context) {
    var day = isObject(counters.days[dayKey]) ? counters.days[dayKey] : {
      total_answers: 0,
      last_success_total: 0,
      last_attempt_total: 0,
      buckets: {}
    };
    if (!isObject(day.buckets)) {
      day.buckets = {};
    }
    var key = bucketKey(context);
    var previous = Number.isInteger(day.buckets[key]) ? day.buckets[key] : 0;
    day.buckets[key] = previous + 1;
    day.total_answers = Number.isInteger(day.total_answers)
      ? day.total_answers + 1
      : 1;
    day.last_success_total = Number.isInteger(day.last_success_total)
      ? day.last_success_total
      : 0;
    day.last_attempt_total = Number.isInteger(day.last_attempt_total)
      ? day.last_attempt_total
      : 0;
    counters.days[dayKey] = day;
    return {day: day, newBucket: previous === 0};
  }

  function retainCurrentAndPreviousDay(counters, today) {
    var previousDays = Object.keys(counters.days).filter(function (dayKey) {
      return /^\d{4}-\d{2}-\d{2}$/.test(dayKey) && dayKey < today;
    }).sort();
    var previousDay = previousDays.length
      ? previousDays[previousDays.length - 1]
      : null;
    Object.keys(counters.days).forEach(function (dayKey) {
      if (dayKey !== today && dayKey !== previousDay) {
        delete counters.days[dayKey];
      }
    });
  }

  function shouldUpload(day, newBucket) {
    if (day.total_answers === 1 || newBucket) {
      return true;
    }
    if (day.last_success_total === 0) {
      return day.total_answers > day.last_attempt_total;
    }
    return day.total_answers - day.last_success_total >= 10;
  }

  function payloadDays(counters) {
    return Object.keys(counters.days).sort().map(function (activityDay) {
      var day = counters.days[activityDay];
      var entries = Object.keys(day.buckets || {}).sort().map(function (key) {
        var parts = key.split("|");
        return {
          deck_version: parts[0],
          track: parts[1],
          jlpt_level: parts[2] || null,
          practice_type: parts[3] || null,
          answer_count: day.buckets[key]
        };
      });
      return {activity_day: activityDay, entries: entries};
    }).filter(function (day) {
      return day.entries.length > 0;
    });
  }

  function byteLength(value) {
    if (typeof TextEncoder === "function") {
      return new TextEncoder().encode(value).length;
    }
    return unescape(encodeURIComponent(value)).length;
  }

  function buildSnapshotPayload(root, context, installationId, availableDays) {
    var envelope = {
      schema_version: Number(root.getAttribute("data-schema-version")),
      policy_version: Number(root.getAttribute("data-policy-version")),
      installation_id: installationId,
      platform: context.platform,
      days: []
    };
    var entryCount = 0;
    for (var index = 0; index < availableDays.length; index += 1) {
      var candidate = availableDays[index];
      if (entryCount + candidate.entries.length > 1000) {
        break;
      }
      envelope.days.push(candidate);
      var serialized = JSON.stringify(envelope);
      if (byteLength(serialized) > 65536) {
        envelope.days.pop();
        break;
      }
      entryCount += candidate.entries.length;
    }
    return envelope.days.length ? JSON.stringify(envelope) : null;
  }

  function sendSnapshot(root, context, installationId, counters, today) {
    if (typeof window.fetch !== "function" || window.__jlptMaxUsageUploadInFlight) {
      return;
    }
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      return;
    }
    var availableDays = payloadDays(counters);
    if (!availableDays.length) {
      return;
    }
    var payload = buildSnapshotPayload(
      root,
      context,
      installationId,
      availableDays
    );
    if (!payload) {
      return;
    }
    var days = JSON.parse(payload).days;
    var sentTotals = {};
    days.forEach(function (item) {
      sentTotals[item.activity_day] = item.entries.reduce(function (total, entry) {
        return total + entry.answer_count;
      }, 0);
    });
    var endpoint = root.getAttribute("data-endpoint");
    window.__jlptMaxUsageUploadInFlight = window.fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: payload,
      cache: "no-store",
      credentials: "omit",
      mode: "cors",
      referrerPolicy: "no-referrer"
    }).then(function (response) {
      if (!response.ok) {
        throw new Error("usage snapshot rejected");
      }
      var current = readCounters();
      Object.keys(sentTotals).forEach(function (activityDay) {
        if (activityDay < today) {
          delete current.days[activityDay];
          return;
        }
        var day = current.days[activityDay];
        if (isObject(day)) {
          day.last_success_total = Math.max(
            Number(day.last_success_total) || 0,
            sentTotals[activityDay]
          );
          day.last_attempt_total = day.last_success_total;
        }
      });
      current.last_success_day = today;
      writeCounters(current);
    }).catch(function () {}).then(function () {
      window.__jlptMaxUsageUploadInFlight = null;
    });
  }

  function updateSettingsLabel(root, choice) {
    var button = root.querySelector("[data-usage-telemetry-settings]");
    if (!button) {
      return;
    }
    button.textContent = choice === "on"
      ? "통계 켜짐"
      : choice === "off" ? "통계 꺼짐" : "통계 설정";
  }

  function focusModalStart(root) {
    var panel = root.querySelector(".usage-telemetry-panel");
    var title = root.querySelector(".usage-telemetry-title");
    if (panel) {
      panel.scrollTop = 0;
    }
    if (title && typeof title.focus === "function") {
      try {
        title.focus({preventScroll: true});
      } catch (_error) {
        title.focus();
      }
    }
    if (panel) {
      panel.scrollTop = 0;
    }
  }

  function renderModal(root, choice, forcedChoice) {
    var modal = root.querySelector("[data-usage-telemetry-modal]");
    var status = root.querySelector("[data-usage-telemetry-status]");
    var enable = root.querySelector("[data-usage-telemetry-enable]");
    var disable = root.querySelector("[data-usage-telemetry-disable]");
    var close = root.querySelector("[data-usage-telemetry-close]");
    if (!modal || !status || !enable || !disable || !close) {
      return;
    }
    var initialDecision = choice === null && forcedChoice;
    close.hidden = Boolean(initialDecision);
    if (choice === "on") {
      var counters = readCounters();
      var pending = Object.keys(counters.days).length > 0;
      status.textContent = "사용 통계를 공유하고 있습니다 · " + (
        counters.last_success_day
          ? "마지막 전송: " + counters.last_success_day
          : pending ? "전송 대기 중" : "아직 전송한 기록이 없습니다"
      );
      enable.hidden = true;
      disable.hidden = false;
      disable.textContent = "공유 끄기";
    } else if (choice === "off") {
      status.textContent = "사용 통계를 공유하지 않고 있습니다. 다시 켜면 새 설치 ID가 생성됩니다.";
      enable.hidden = false;
      disable.hidden = true;
    } else {
      status.textContent = "이 사용 통계는 동의하기 전에는 전송하지 않습니다.";
      enable.hidden = false;
      disable.hidden = false;
      disable.textContent = "공유하지 않기";
    }
    modal.hidden = false;
    focusModalStart(root);
  }

  function closeModal(root) {
    var modal = root.querySelector("[data-usage-telemetry-modal]");
    if (modal) {
      modal.hidden = true;
    }
  }

  function bindUi(root, policyVersion) {
    if (root.getAttribute("data-usage-telemetry-bound") === "true") {
      return;
    }
    root.setAttribute("data-usage-telemetry-bound", "true");
    var settings = root.querySelector("[data-usage-telemetry-settings]");
    var enable = root.querySelector("[data-usage-telemetry-enable]");
    var disable = root.querySelector("[data-usage-telemetry-disable]");
    var close = root.querySelector("[data-usage-telemetry-close]");
    var modal = root.querySelector("[data-usage-telemetry-modal]");
    if (!settings || !enable || !disable || !close || !modal) {
      return;
    }
    settings.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      renderModal(root, readConsent(policyVersion), false);
    });
    enable.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      clearUsageState();
      if (writeConsent(policyVersion, "on") && ensureInstallationId()) {
        updateSettingsLabel(root, "on");
        closeModal(root);
      }
    });
    disable.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      clearUsageState();
      writeConsent(policyVersion, "off");
      updateSettingsLabel(root, "off");
      closeModal(root);
    });
    close.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      closeModal(root);
    });
    modal.addEventListener("click", function (event) {
      event.stopPropagation();
    });
    if (typeof window.__jlptMaxUsageKeydownHandler === "function") {
      document.removeEventListener(
        "keydown",
        window.__jlptMaxUsageKeydownHandler
      );
    }
    window.__jlptMaxUsageKeydownHandler = function (event) {
      if (event.key === "Escape" && !modal.hidden && close.hidden) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener(
      "keydown",
      window.__jlptMaxUsageKeydownHandler
    );
  }

  function countPreConsentAnswer(root, policyVersion, promptAfter) {
    var raw = Number.parseInt(readCookie(PROMPT_COUNT_COOKIE) || "0", 10);
    var count = Number.isInteger(raw) && raw >= 0 ? raw + 1 : 1;
    writeCookie(PROMPT_COUNT_COOKIE, String(count));
    if (count >= promptAfter) {
      renderModal(root, readConsent(policyVersion), true);
    }
  }

  function initialize() {
    var roots = document.querySelectorAll("[data-jlpt-max-usage-telemetry]");
    var root = roots.length ? roots[roots.length - 1] : null;
    var platform = detectPlatform();
    if (!root || !platform || !cookieAvailable()) {
      return;
    }
    var policyVersion = Number(root.getAttribute("data-policy-version"));
    var promptAfter = Number(root.getAttribute("data-prompt-after"));
    var context = normalizedContext(root, platform);
    if (!Number.isInteger(policyVersion) || policyVersion !== 1 || !context) {
      return;
    }
    root.hidden = false;
    bindUi(root, policyVersion);
    var choice = readConsent(policyVersion);
    if (choice === null) {
      clearTransmittedUsageState();
    }
    updateSettingsLabel(root, choice);
    if (choice === "off") {
      return;
    }
    if (choice === null) {
      countPreConsentAnswer(root, policyVersion, promptAfter);
      return;
    }
    var installationId = ensureInstallationId();
    if (!installationId) {
      return;
    }
    var today = localDay();
    var counters = readCounters();
    retainCurrentAndPreviousDay(counters, today);
    var incremented = incrementCounter(counters, today, context);
    if (!writeCounters(counters)) {
      return;
    }
    if (shouldUpload(incremented.day, incremented.newBucket)) {
      incremented.day.last_attempt_total = incremented.day.total_answers;
      writeCounters(counters);
      sendSnapshot(root, context, installationId, counters, today);
    }
  }

  if (globalThis.__JLPT_MAX_USAGE_TEST_MODE__ === true) {
    globalThis.__JLPT_MAX_USAGE_TEST_API__ = {
      clearTransmittedUsageState: clearTransmittedUsageState,
      clearUsageState: clearUsageState,
      detectPlatform: detectPlatform,
      emptyCounters: emptyCounters,
      ensureInstallationId: ensureInstallationId,
      focusModalStart: focusModalStart,
      incrementCounter: incrementCounter,
      normalizeLevel: normalizeLevel,
      normalizePracticeType: normalizePracticeType,
      payloadDays: payloadDays,
      buildSnapshotPayload: buildSnapshotPayload,
      readCookie: readCookie,
      removeCookie: removeCookie,
      retainCurrentAndPreviousDay: retainCurrentAndPreviousDay,
      readConsent: readConsent,
      readCounters: readCounters,
      renderModal: renderModal,
      sendSnapshot: sendSnapshot,
      shouldUpload: shouldUpload,
      writeCookie: writeCookie,
      writeConsent: writeConsent,
      writeCounters: writeCounters
    };
    return;
  }

  initialize();
})();
