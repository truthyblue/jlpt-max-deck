"""Vocabulary card templates and rendering helpers for the public deck."""

from __future__ import annotations

import html

from public_ruby import kanji_only_ruby_html, plain_japanese


SOURCE_DISPLAY_NAMES = {
    "hackers": "해커스",
    "dongyang": "동양북스",
}
AUDIO_AUTOPLAY_SETTINGS = """
    <details class="audio-autoplay-settings" data-audio-autoplay-settings>
      <summary>
        <span>재생</span>
        <span class="audio-autoplay-state" data-audio-autoplay-state>단어</span>
      </summary>
      <div class="audio-autoplay-popover">
        <label class="audio-autoplay-switch">
          <span>예문 자동재생</span>
          <span class="audio-autoplay-control">
            <input type="checkbox" role="switch" data-audio-autoplay-enabled>
            <span class="audio-autoplay-track" aria-hidden="true"></span>
          </span>
        </label>
        <fieldset class="audio-autoplay-scope" data-audio-autoplay-scope disabled>
          <legend class="audio-slot">예문 자동재생 범위</legend>
          <div class="audio-autoplay-options">
            <label class="audio-autoplay-option">
              <input type="radio" name="jlpt-max-audio-autoplay-scope"
                     value="first" data-audio-autoplay-choice checked>
              <span class="audio-autoplay-label">첫 예문</span>
            </label>
            <label class="audio-autoplay-option">
              <input type="radio" name="jlpt-max-audio-autoplay-scope"
                     value="all" data-audio-autoplay-choice>
              <span class="audio-autoplay-label">모든 예문</span>
            </label>
          </div>
        </fieldset>
      </div>
    </details>"""
AUDIO_INTERACTION = """
<script>
(function () {
  var AUDIO_AUTOPLAY_STORAGE_KEY = "jlpt-max-deck.audio-autoplay-mode.v1";
  var AUDIO_AUTOPLAY_SCOPE_STORAGE_KEY = "jlpt-max-deck.audio-autoplay-scope.v1";

  function removeQueueEnded(audio) {
    var cleanup = audio && audio.__jlptMaxQueueCleanup;
    if (typeof cleanup === "function") {
      cleanup();
    }
  }

  function resetDirectAudio(audio) {
    removeQueueEnded(audio);
    try {
      audio.pause();
    } catch (_error) {}
    try {
      audio.currentTime = 0;
    } catch (_error) {}
  }

  function nextAudioAttempt() {
    var attempt = (window.__jlptMaxAudioAttempt || 0) + 1;
    window.__jlptMaxAudioAttempt = attempt;
    return attempt;
  }

  function nextQueueToken() {
    var token = (window.__jlptMaxAudioQueueToken || 0) + 1;
    window.__jlptMaxAudioQueueToken = token;
    return token;
  }

  function clearQueueEnded() {
    var cleanup = window.__jlptMaxQueueCleanup;
    if (typeof cleanup === "function") {
      cleanup();
    }
    window.__jlptMaxQueueCleanup = null;
  }

  function cancelAudioQueue(stopActive) {
    var token = nextQueueToken();
    clearQueueEnded();
    if (stopActive) {
      var active = window.__jlptMaxClickAudio;
      if (active) {
        nextAudioAttempt();
        resetDirectAudio(active);
        window.__jlptMaxClickAudio = null;
      }
    }
    return token;
  }

  function recordPlayFailure(audio, error, automatic) {
    cancelAudioQueue(false);
    resetDirectAudio(audio);
    if (window.__jlptMaxClickAudio === audio) {
      window.__jlptMaxClickAudio = null;
    }
    if (automatic && error && error.name === "NotAllowedError") {
      audio.setAttribute("data-autoplay-blocked", "true");
      return;
    }
    var name = error && error.name ? error.name : "play-failed";
    audio.setAttribute("data-audio-error", name);
    if (window.console && typeof window.console.warn === "function") {
      window.console.warn("JLPT MAX audio playback failed", error);
    }
  }

  function startDirectAudio(audio, automatic, onEnded) {
    var attempt = nextAudioAttempt();
    var previous = window.__jlptMaxClickAudio;
    if (previous && previous !== audio) {
      resetDirectAudio(previous);
    }
    resetDirectAudio(audio);
    audio.removeAttribute("data-audio-error");
    audio.removeAttribute("data-autoplay-blocked");
    window.__jlptMaxClickAudio = audio;
    if (typeof onEnded === "function") {
      var cleanup = function () {
        audio.removeEventListener("ended", handleEnded);
        if (audio.__jlptMaxQueueCleanup === cleanup) {
          audio.__jlptMaxQueueCleanup = null;
        }
        if (window.__jlptMaxQueueCleanup === cleanup) {
          window.__jlptMaxQueueCleanup = null;
        }
      };
      var handleEnded = function () {
        cleanup();
        if (
          window.__jlptMaxClickAudio === audio &&
          window.__jlptMaxAudioAttempt === attempt
        ) {
          window.__jlptMaxClickAudio = null;
          onEnded();
        }
      };
      audio.__jlptMaxQueueCleanup = cleanup;
      window.__jlptMaxQueueCleanup = cleanup;
      audio.addEventListener("ended", handleEnded);
    }
    var started;
    try {
      started = audio.play();
    } catch (error) {
      recordPlayFailure(audio, error, automatic);
      return;
    }
    if (started && typeof started.catch === "function") {
      started.catch(function (error) {
        if (
          window.__jlptMaxClickAudio === audio &&
          window.__jlptMaxAudioAttempt === attempt
        ) {
          recordPlayFailure(audio, error, automatic);
        }
      });
    }
  }

  function playDirectAudio(audio, automatic) {
    cancelAudioQueue(true);
    startDirectAudio(audio, automatic, null);
  }

  function validAutoplayMode(mode) {
    return mode === "word" || mode === "first" || mode === "all";
  }

  function validAutoplayScope(scope) {
    return scope === "first" || scope === "all";
  }

  function readAutoplayScope() {
    try {
      var stored = window.localStorage.getItem(AUDIO_AUTOPLAY_SCOPE_STORAGE_KEY);
      if (validAutoplayScope(stored)) {
        window.__jlptMaxAutoplayScope = stored;
        return stored;
      }
    } catch (_error) {}
    var fallback = window.__jlptMaxAutoplayScope;
    return validAutoplayScope(fallback) ? fallback : "first";
  }

  function writeAutoplayScope(scope) {
    var saved = validAutoplayScope(scope) ? scope : "first";
    window.__jlptMaxAutoplayScope = saved;
    try {
      window.localStorage.setItem(AUDIO_AUTOPLAY_SCOPE_STORAGE_KEY, saved);
    } catch (_error) {}
    return saved;
  }

  function readAutoplayMode() {
    try {
      var stored = window.localStorage.getItem(AUDIO_AUTOPLAY_STORAGE_KEY);
      if (validAutoplayMode(stored)) {
        window.__jlptMaxAutoplayMode = stored;
        if (validAutoplayScope(stored)) {
          window.__jlptMaxAutoplayScope = stored;
        }
        return stored;
      }
    } catch (_error) {}
    var fallback = window.__jlptMaxAutoplayMode;
    return validAutoplayMode(fallback) ? fallback : "word";
  }

  function writeAutoplayMode(mode) {
    var saved = validAutoplayMode(mode) ? mode : "word";
    window.__jlptMaxAutoplayMode = saved;
    if (validAutoplayScope(saved)) {
      writeAutoplayScope(saved);
    }
    try {
      window.localStorage.setItem(AUDIO_AUTOPLAY_STORAGE_KEY, saved);
    } catch (_error) {}
    return saved;
  }

  function selectedAutoplayScope(choices) {
    for (var index = 0; index < choices.length; index += 1) {
      if (choices[index].checked && choices[index].value === "all") {
        return "all";
      }
    }
    return "first";
  }

  function renderAutoplaySettings(settings, mode) {
    var enabled = settings.querySelector("[data-audio-autoplay-enabled]");
    var scope = settings.querySelector("[data-audio-autoplay-scope]");
    var state = settings.querySelector("[data-audio-autoplay-state]");
    var choices = settings.querySelectorAll("[data-audio-autoplay-choice]");
    var activeScope = mode === "word" ? readAutoplayScope() : mode;
    enabled.checked = mode !== "word";
    scope.disabled = mode === "word";
    for (var index = 0; index < choices.length; index += 1) {
      choices[index].checked = choices[index].value === activeScope;
    }
    state.textContent = mode === "all" ? "전체" : mode === "first" ? "1개" : "단어";
  }

  function bindAutoplaySettings(mode) {
    var settings = document.querySelector("[data-audio-autoplay-settings]");
    if (!settings) {
      return mode;
    }
    renderAutoplaySettings(settings, mode);
    if (settings.getAttribute("data-audio-settings-bound") === "true") {
      return mode;
    }
    settings.setAttribute("data-audio-settings-bound", "true");
    settings.addEventListener("click", function (event) {
      event.stopPropagation();
    });
    settings.addEventListener("keydown", function (event) {
      event.stopPropagation();
    });
    var enabled = settings.querySelector("[data-audio-autoplay-enabled]");
    var choices = settings.querySelectorAll("[data-audio-autoplay-choice]");
    enabled.addEventListener("change", function () {
      var nextMode = this.checked ? selectedAutoplayScope(choices) : "word";
      nextMode = writeAutoplayMode(nextMode);
      renderAutoplaySettings(settings, nextMode);
      cancelAudioQueue(false);
    });
    for (var index = 0; index < choices.length; index += 1) {
      choices[index].addEventListener("change", function () {
        if (!this.checked || !enabled.checked) {
          return;
        }
        var nextMode = writeAutoplayMode(this.value);
        renderAutoplaySettings(settings, nextMode);
        cancelAudioQueue(false);
      });
    }
    return mode;
  }

  function autoplayPlayers(autoplayScope, mode) {
    var players = [];
    var wordAudio = autoplayScope.querySelector("audio.click-audio-player");
    if (wordAudio) {
      players.push(wordAudio);
    }
    if (mode === "word") {
      return players;
    }
    var card = autoplayScope.closest(".card-back");
    var examples = card && card.querySelectorAll(
      ".example-panel audio.click-audio-player"
    );
    if (!examples) {
      return players;
    }
    var exampleCount = mode === "first" ? Math.min(examples.length, 1) : examples.length;
    for (var index = 0; index < exampleCount; index += 1) {
      players.push(examples[index]);
    }
    return players;
  }

  function playQueueItem(players, index, queueToken, card) {
    if (
      index >= players.length ||
      window.__jlptMaxAudioQueueToken !== queueToken ||
      !document.documentElement.contains(card)
    ) {
      return;
    }
    startDirectAudio(players[index], true, function () {
      if (
        window.__jlptMaxAudioQueueToken === queueToken &&
        document.documentElement.contains(card)
      ) {
        playQueueItem(players, index + 1, queueToken, card);
      }
    });
  }

  function startAutoplayQueue(autoplayScope, mode) {
    var card = autoplayScope.closest(".card-back");
    var players = autoplayPlayers(autoplayScope, mode);
    if (!card || players.length === 0) {
      return;
    }
    for (var index = 0; index < players.length; index += 1) {
      players[index].setAttribute("preload", "auto");
      if (typeof players[index].load === "function") {
        players[index].load();
      }
    }
    var queueToken = cancelAudioQueue(true);
    playQueueItem(players, 0, queueToken, card);
  }

  function watchCardRemoval(card) {
    var previousObserver = window.__jlptMaxAudioObserver;
    if (previousObserver && typeof previousObserver.disconnect === "function") {
      previousObserver.disconnect();
    }
    if (!card || typeof window.MutationObserver !== "function") {
      return;
    }
    var observer = new MutationObserver(function () {
      if (!document.documentElement.contains(card)) {
        cancelAudioQueue(true);
        observer.disconnect();
        if (window.__jlptMaxAudioObserver === observer) {
          window.__jlptMaxAudioObserver = null;
        }
      }
    });
    observer.observe(document.documentElement, {childList: true, subtree: true});
    window.__jlptMaxAudioObserver = observer;
  }

  window.__jlptMaxPlayAudio = playDirectAudio;
  var staleAudio = window.__jlptMaxClickAudio;
  if (staleAudio && !document.documentElement.contains(staleAudio)) {
    cancelAudioQueue(true);
  }
  var triggers = document.querySelectorAll(".audio-trigger");
  for (var index = 0; index < triggers.length; index += 1) {
    var trigger = triggers[index];
    if (trigger.getAttribute("data-audio-bound") === "true") {
      continue;
    }
    trigger.setAttribute("data-audio-bound", "true");
    trigger.addEventListener("click", function (event) {
      event.stopPropagation();
      var scope = this.closest(".audio-scope");
      var direct = scope && scope.querySelector("audio.click-audio-player");
      if (direct) {
        playDirectAudio(direct, false);
        return;
      }
      var replay = scope && scope.querySelector(
        ".replay-button, .replaybutton, a[href^='playsound:']"
      );
      if (replay) {
        cancelAudioQueue(true);
        replay.click();
      }
    });
    trigger.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        this.click();
      }
    });
  }

  var autoplayScope = document.querySelector('[data-audio-autoplay="word"]');
  var autoplayMode = bindAutoplaySettings(readAutoplayMode());
  var interactionCard = autoplayScope
    ? autoplayScope.closest(".card-back")
    : document.querySelector(".card-back");
  watchCardRemoval(interactionCard);
  if (
    autoplayScope &&
    autoplayScope.getAttribute("data-audio-autoplay-started") !== "true"
  ) {
    autoplayScope.setAttribute("data-audio-autoplay-started", "true");
    startAutoplayQueue(autoplayScope, autoplayMode);
  }
})();
</script>
"""


FRONT = """
<main class="card-shell card-front">
  <header class="card-header">
    <span class="level-pill">{{JLPT}}</span>
  </header>
  <section class="lexeme-block">
    <div class="lexeme-copy">
      <div class="word" lang="ja">{{Word}}</div>
    </div>
  </section>
</main>
"""


AUDIO_FRONT = """
<main class="card-shell card-front card-front-audio">
  <section class="audio-only-prompt" aria-label="단어 음성">
    {{WordAudio}}
  </section>
</main>
"""


BACK = """
<main class="card-shell card-back">
  <header class="card-header">
    <span class="level-pill">{{JLPT}}</span>""" + AUDIO_AUTOPLAY_SETTINGS + """
  </header>

  <section class="lexeme-block lexeme-answer audio-scope">
    <div class="lexeme-copy audio-trigger" role="button" tabindex="0"
         aria-label="단어 음성 재생">
      <div class="word" lang="ja">{{Word}}</div>
      <div class="reading" lang="ja">{{Reading}}</div>
    </div>
    <div class="hero-meaning">{{Meaning}}</div>
    <div class="metadata-pill">{{PartOfSpeech}}</div>
    <div class="audio-slot">{{WordAudio}}</div>
  </section>

  {{#Example1JP}}<section class="example-panel audio-scope">
    <div class="section-label">예문</div>
    <div class="example-copy audio-trigger" role="button" tabindex="0"
         aria-label="예문 음성 재생">
      <div class="example-jp" lang="ja">{{Example1JP}}</div>
    </div>
    <div class="audio-slot">{{Example1Audio}}</div>
    <div class="example-ko">{{Example1KO}}</div>
  </section>{{/Example1JP}}
  {{#Example2JP}}<section class="example-panel audio-scope">
    <div class="section-label">예문 2</div>
    <div class="example-copy audio-trigger" role="button" tabindex="0"
         aria-label="예문 2 음성 재생">
      <div class="example-jp" lang="ja">{{Example2JP}}</div>
    </div>
    <div class="audio-slot">{{Example2Audio}}</div>
    <div class="example-ko">{{Example2KO}}</div>
  </section>{{/Example2JP}}
  {{#Example3JP}}<section class="example-panel audio-scope">
    <div class="section-label">예문 3</div>
    <div class="example-copy audio-trigger" role="button" tabindex="0"
         aria-label="예문 3 음성 재생">
      <div class="example-jp" lang="ja">{{Example3JP}}</div>
    </div>
    <div class="audio-slot">{{Example3Audio}}</div>
    <div class="example-ko">{{Example3KO}}</div>
  </section>{{/Example3JP}}

  <footer class="compact-tools">
    {{#KanjiDetails}}<details class="kanji-disclosure">
      <summary id="kanji-summary" aria-controls="kanji-body">한자 정보</summary>
    </details>
    <div id="kanji-body" class="kanji-body" role="region"
         aria-label="한자 정보">{{KanjiDetails}}</div>{{/KanjiDetails}}

    <a class="dictionary-link"
       href="https://ja.dict.naver.com/#/search?query={{text:Word}}"
       aria-label="네이버 일본어사전에서 이 단어 검색">
      네이버 사전 <span aria-hidden="true">↗</span>
    </a>

    <details class="source-meta"><summary>출처</summary>
      <div class="source-popover">
        <div><span>뜻</span><span>{{MeaningSource}}</span></div>
        <div><span>품사</span><span>JMdict</span></div>
        {{#KanjiDetails}}<div><span>한자</span><span>일상무따</span></div>{{/KanjiDetails}}
        {{#Example1Source}}<div><span>예문</span><span>{{Example1Source}}</span></div>{{/Example1Source}}
      </div>
    </details>
  </footer>
</main>
""" + AUDIO_INTERACTION


CSS = """
.card {
  --canvas: #f3f0e9;
  --surface: #fffdfa;
  --surface-muted: #f8f5ef;
  --ink: #242722;
  --ink-soft: #686c64;
  --line: #dedbd2;
  --level: #294f3c;
  --accent: #a9583e;
  --accent-soft: #f6e9e2;
  --reading-size: 20px;
  --meaning-size: 23px;
  --example-ruby-size: .55em;
  --kanji-glyph-size: 46px;
  --kanji-reading-size: 13px;
  box-sizing: border-box;
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Noto Sans KR", "Apple SD Gothic Neo", sans-serif;
  text-align: left;
}

.card.nightMode {
  --canvas: #181a18;
  --surface: #232623;
  --surface-muted: #2a2d29;
  --ink: #f2f1ec;
  --ink-soft: #b8bbb3;
  --line: #3b3f39;
  --level: #5f9476;
  --accent: #df8d70;
  --accent-soft: #402d27;
}

*, *::before, *::after { box-sizing: inherit; }
.card-shell { max-width: 640px; margin: 0 auto; padding: 16px 14px 28px; }
.card-header {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  min-height: 24px;
}
.level-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--level);
  color: #fff;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: .06em;
}
.audio-autoplay-settings {
  position: relative;
  z-index: 4;
  margin-left: auto;
}
.audio-autoplay-settings > summary {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 26px;
  padding: 3px 7px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface-muted);
  color: var(--ink);
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
  font-weight: 750;
  line-height: 1.2;
  list-style: none;
}
.audio-autoplay-settings > summary::-webkit-details-marker { display: none; }
.audio-autoplay-settings > summary::after {
  content: "▾";
  color: var(--ink-soft);
}
.audio-autoplay-settings[open] > summary::after { content: "▴"; }
.audio-autoplay-settings > summary:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.audio-autoplay-state { color: var(--ink-soft); font-weight: 650; }
.audio-autoplay-popover {
  box-sizing: border-box;
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 4;
  width: min(160px, calc(100vw - 20px));
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink);
}
.audio-autoplay-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  min-height: 25px;
  cursor: pointer;
  color: var(--ink);
  font-size: 11px;
  font-weight: 750;
  white-space: nowrap;
}
.audio-autoplay-control {
  position: relative;
  display: inline-flex;
}
.audio-autoplay-control input,
.audio-autoplay-option input {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}
.audio-autoplay-track {
  position: relative;
  display: inline-block;
  width: 27px;
  height: 15px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-muted);
}
.audio-autoplay-track::after {
  content: "";
  position: absolute;
  top: 2px;
  left: 2px;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--ink-soft);
  transition: transform 140ms ease, background 140ms ease;
}
.audio-autoplay-control input:checked + .audio-autoplay-track {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.audio-autoplay-control input:checked + .audio-autoplay-track::after {
  background: var(--accent);
  transform: translateX(12px);
}
.audio-autoplay-control input:focus-visible + .audio-autoplay-track {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.audio-autoplay-scope {
  min-width: 0;
  margin: 4px 0 0;
  padding: 0;
  border: 0;
}
.audio-autoplay-scope:disabled { opacity: 0.45; }
.audio-autoplay-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-muted);
}
.audio-autoplay-option {
  position: relative;
  min-width: 0;
  cursor: pointer;
}
.audio-autoplay-label {
  display: grid;
  place-items: center;
  min-height: 23px;
  padding: 2px 3px;
  border-radius: 4px;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 750;
  text-align: center;
  white-space: nowrap;
}
.audio-autoplay-option input:checked + .audio-autoplay-label {
  background: var(--accent-soft);
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}
.audio-autoplay-option input:focus-visible + .audio-autoplay-label {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.lexeme-block { padding: 18px 6px 14px; text-align: center; }
.card-front .lexeme-block { padding-top: min(17vh, 104px); }
.word {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(40px, 11vw, 58px);
  font-weight: 700;
  line-height: 1.18;
  overflow-wrap: anywhere;
}
.card-back .word { font-size: clamp(36px, 10vw, 52px); }
.reading { margin-top: 5px; color: var(--ink-soft); font-size: var(--reading-size); line-height: 1.4; }
.hero-meaning {
  max-width: 540px;
  margin: 10px auto 0;
  font-size: var(--meaning-size);
  font-weight: 730;
  line-height: 1.45;
}
.metadata-pill {
  display: inline-block;
  max-width: 100%;
  margin-top: 9px;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
}
.audio-trigger {
  cursor: pointer;
  border-radius: 8px;
  -webkit-tap-highlight-color: transparent;
}
.audio-trigger:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 4px;
}
.audio-trigger:active { opacity: .72; }
.click-audio-player { display: none; }
.tap-hint { margin-top: 10px; color: var(--ink-soft); font-size: 10px; letter-spacing: .03em; }
.audio-slot {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}
.card-front-audio {
  display: grid;
  place-items: center;
  min-height: 45vh;
}
.audio-only-prompt {
  display: grid;
  place-items: center;
  min-width: 64px;
  min-height: 64px;
}

.example-panel {
  margin-top: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
}
.section-label {
  margin-bottom: 6px;
  color: var(--accent);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .08em;
}
.example-jp {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 18px;
  line-height: 1.9;
}
.example-jp ruby,
.usage-pattern-jp ruby,
.usage-contrast-jp ruby {
  display: inline-grid;
  justify-items: center;
  vertical-align: baseline;
  line-height: 1;
  ruby-align: center;
  ruby-position: over;
  ruby-overhang: none;
}
.example-jp rb,
.usage-pattern-jp rb,
.usage-contrast-jp rb {
  display: block;
  grid-area: 1 / 1;
  align-self: baseline;
  line-height: 1;
}
.example-jp rt,
.usage-pattern-jp rt,
.usage-contrast-jp rt {
  display: block;
  grid-area: 1 / 1;
  align-self: start;
  justify-self: center;
  transform: translateY(-100%);
  color: var(--ink-soft);
  font-family: -apple-system, BlinkMacSystemFont, "Noto Sans JP", sans-serif;
  font-size: var(--example-ruby-size);
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}
.example-ko { margin-top: 7px; font-size: 16px; line-height: 1.55; }

.compact-tools {
  --tool-control-height: 30px;
  --tool-control-gap: 8px;
  position: relative;
  display: grid;
  grid-template-columns: max-content max-content minmax(0, 1fr) max-content;
  grid-template-areas:
    "kanji dictionary spacer source"
    "kanji-body kanji-body kanji-body kanji-body";
  column-gap: var(--tool-control-gap);
  row-gap: 8px;
  align-items: start;
  min-height: 52px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.compact-tools details > summary {
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  width: max-content;
  max-width: 100%;
  min-height: var(--tool-control-height);
  padding: 5px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  cursor: pointer;
  color: var(--ink);
  font-family: inherit;
  font-size: 11px;
  font-style: normal;
  font-weight: 750;
  letter-spacing: normal;
  list-style: none;
}
.compact-tools summary::-webkit-details-marker { display: none; }
.compact-tools details > summary::after {
  content: "▾";
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
}
.compact-tools details[open] > summary::after { content: "▴"; }
.kanji-disclosure { grid-area: kanji; min-width: 0; }
.compact-tools .kanji-disclosure > summary {
  min-height: var(--tool-control-height);
  padding: 5px 9px;
  border: 1px solid var(--line) !important;
  border-radius: 7px;
  background: var(--surface-muted) !important;
}
.kanji-body {
  grid-area: kanji-body;
  min-width: 0;
}
.kanji-disclosure:not([open]) + .kanji-body { display: none; }
.dictionary-link {
  grid-area: dictionary;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: var(--tool-control-height);
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface-muted);
  color: var(--ink);
  font-family: inherit;
  font-size: 11px;
  font-weight: 750;
  line-height: 1.2;
  text-decoration: none;
}
.dictionary-link:first-child { grid-area: kanji; }
.dictionary-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.dictionary-link:active { opacity: .72; }

.kanji-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 190px));
  justify-content: start;
  gap: 7px;
}
.kanji-entry {
  min-width: 0;
  padding: 11px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface-muted);
  text-align: center;
}
.kanji-glyph {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  margin: 0 auto 8px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  font-family: "Hiragino Mincho ProN", "Yu Mincho", serif;
  font-size: var(--kanji-glyph-size);
  font-weight: 700;
}
.kanji-hint { font-size: 15px; font-weight: 750; line-height: 1.4; }
.kanji-stats { margin-top: 2px; color: var(--ink-soft); font-size: 10px; line-height: 1.4; }
.kanji-readings { display: grid; gap: 3px; margin: 7px 0 0; text-align: left; }
.kanji-reading {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  column-gap: 8px;
  min-height: 24px;
}
.kanji-reading dt {
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 750;
  line-height: 1.35;
}
.kanji-reading dd {
  margin: 0;
  font-size: var(--kanji-reading-size);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.source-meta {
  position: relative;
  grid-area: source;
  justify-self: end;
}
.source-meta[open] { z-index: 2; }
.compact-tools .source-meta > summary {
  justify-content: flex-end;
  width: 44px;
  min-height: var(--tool-control-height) !important;
  margin-left: auto;
  padding: 5px 0 !important;
  color: var(--ink-soft) !important;
  font-size: 11px !important;
  font-weight: 600 !important;
}
.source-popover {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 1;
  display: grid;
  gap: 4px;
  width: max-content;
  max-width: calc(100vw - 28px);
  margin: 7px 0 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 10px;
  line-height: 1.45;
}
.source-popover > div { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 6px; }
.source-popover > div > span:first-child { font-weight: 750; }
.source-popover > div > span:last-child { overflow-wrap: anywhere; }

@media (max-width: 480px) {
  .card-shell { padding: 12px 10px 24px; }
  .lexeme-block { padding: 14px 4px 12px; }
  .card-front .lexeme-block { padding-top: min(15vh, 82px); }
  .card-back .word { font-size: clamp(34px, 10vw, 46px); }
  .hero-meaning { font-size: 22px; }
  .example-panel { padding: 11px 12px; }
  .example-jp { font-size: 17px; }
  .kanji-list { grid-template-columns: repeat(auto-fit, minmax(142px, 1fr)); }
}
"""


def kanji_details_html(details: list[dict[str, str]]) -> str:
    if not details:
        return ""
    entries: list[str] = []
    for detail in details:
        character = html.escape(detail["character"])
        study_hint = html.escape(detail["study_hint"])
        stats = " · ".join(
            part
            for part in (
                f"부수 {html.escape(detail['radical'])}" if detail["radical"] else "",
                f"{html.escape(detail['strokes'])}획" if detail["strokes"] else "",
            )
            if part
        )
        reading_rows = "".join(
            f'<div class="kanji-reading"><dt>{label}</dt><dd lang="ja">{html.escape(value)}</dd></div>'
            for label, value in (
                ("음독", detail["on_reading"]),
                ("훈독", detail["kun_reading"]),
            )
            if value
        )
        entries.append(
            '<article class="kanji-entry">'
            f'<div class="kanji-glyph" lang="ja">{character}</div>'
            '<div class="kanji-content">'
            f'<div class="kanji-hint">{study_hint}</div>'
            f'<div class="kanji-stats">{stats}</div>'
            f'<dl class="kanji-readings">{reading_rows}</dl>'
            "</div></article>"
        )
    return f'<div class="kanji-list">{"".join(entries)}</div>'


def example_display_html(example: dict[str, str]) -> str:
    japanese = example["japanese"]
    ruby = kanji_only_ruby_html(example.get("japanese_ruby", ""))
    if ruby and plain_japanese(ruby) == japanese:
        return ruby
    return html.escape(japanese)
