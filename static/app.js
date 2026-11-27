/* sotto-notes - tiny vanilla front-end */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);

  const ICONS = {
    play: '<path d="M4.5 2.6v10.8L13 8z"/>',
    pause: '<path d="M4.5 2.5h2.4v11H4.5zM9.1 2.5h2.4v11H9.1z"/>',
    trash:
      '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.2h5.8l.6-8.2" />',
    download: '<path d="M8 2.5v7m0 0L5 6.6M8 9.5l3-2.9M3 12.5h10" />',
    upload:
      '<path d="M2 6.5v5A1.5 1.5 0 0 0 3.5 13h9a1.5 1.5 0 0 0 1.5-1.5v-5M8 11V2.5M5 5.5L8 2.5l3 3" />',
    back: '<path d="M9.5 3.5L5 8l4.5 4.5" />',
  };

  const icon = (name) => `<svg viewBox="0 0 16 16" aria-hidden="true">${ICONS[name]}</svg>`;
  const SUPPORTED = ["mp3", "wav", "m4a", "mp4", "ogg", "opus", "flac", "webm", "aac"];

  const state = {
    health: null,
    providers: [],
    provider: localStorage.getItem("sotto.provider") || "local",
    notes: [],
    note: null,
    jobId: null,
    pollTimer: null,
    view: "empty",
    audio: null,
    segmentEls: [],
    activeIndex: -1,
    saveTimer: null,
    saveSeq: 0,
    dirty: false,
    progress: null,
    lastManualScroll: 0,
  };

  const dom = {};

  /* ---------------------------------------------------------------- helpers */
  const pad = (n) => String(n).padStart(2, "0");

  function clock(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }

  function shortDate(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  let toastTimer = null;
  function toast(message, isError = false) {
    dom.toast.textContent = message;
    dom.toast.classList.toggle("error", isError);
    dom.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => dom.toast.classList.remove("show"), 4200);
  }

  function setStatus(kind, text) {
    dom.saveStatus.className = `status ${kind || ""}`.trim();
    dom.saveStatusText.textContent = text;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data.error || `Request failed (${response.status})`);
    }
    return data;
  }

  /* ------------------------------------------------------------------- init */
  async function init() {
    dom.view = $("#view");
    dom.library = $("#library");
    dom.libraryCount = $("#library-count");
    dom.toast = $("#toast");
    dom.saveStatus = $("#save-status");
    dom.saveStatusText = $("#save-status-text");
    dom.crumb = $("#crumb-title");
    dom.fileInput = $("#file-input");
    dom.engineLine = $("#engine-line");
    dom.brand = $("#brand");

    bindGlobal();

    try {
      const [health, providers, notes] = await Promise.all([
        api("/api/health"),
        api("/api/providers"),
        api("/api/notes"),
      ]);
      state.health = health;
      state.providers = providers.providers || [];
      state.notes = notes.notes || [];
    } catch (error) {
      dom.view.innerHTML =
        '<div class="loading">Could not reach the local server. Is it still running?</div>';
      toast(error.message, true);
      return;
    }

    const available = state.providers.filter((p) => p.available).map((p) => p.id);
    if (!available.includes(state.provider)) {
      state.provider = available[0] || "local";
    }

    const local = state.providers.find((p) => p.id === "local");
    if (local) {
      dom.engineLine.textContent = `${local.model} · cpu · ${local.available ? "ready" : "engine off"}`;
    }
    renderLibrary();
    renderEmpty();
  }

  function bindGlobal() {
    $("#new-note").addEventListener("click", () => {
      flushSave();
      state.note = null;
      state.jobId = null;
      dom.crumb.textContent = "new note";
      renderLibrary();
      renderEmpty();
    });

    dom.fileInput.addEventListener("change", () => {
      const file = dom.fileInput.files && dom.fileInput.files[0];
      dom.fileInput.value = "";
      if (file) startUpload(file);
    });

    document.addEventListener("dragover", (event) => event.preventDefault());
    document.addEventListener("drop", (event) => event.preventDefault());

    dom.view.addEventListener(
      "wheel",
      () => (state.lastManualScroll = Date.now()),
      { passive: true }
    );
    dom.view.addEventListener(
      "touchmove",
      () => (state.lastManualScroll = Date.now()),
      { passive: true }
    );

    document.addEventListener("keydown", (event) => {
      const tag = (event.target.tagName || "").toLowerCase();
      if (["input", "textarea", "select"].includes(tag) || event.target.isContentEditable) {
        return;
      }
      if (!state.audio) return;
      if (event.code === "Space") {
        event.preventDefault();
        togglePlay();
      } else if (event.code === "ArrowRight") {
        event.preventDefault();
        seekBy(5);
      } else if (event.code === "ArrowLeft") {
        event.preventDefault();
        seekBy(-5);
      }
    });

    window.addEventListener("beforeunload", (event) => {
      if (state.dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }

  /* --------------------------------------------------------------- library */
  function renderLibrary() {
    dom.library.textContent = "";
    dom.libraryCount.textContent = String(state.notes.length);

    if (!state.notes.length) {
      const empty = document.createElement("p");
      empty.className = "library-empty";
      empty.textContent = "No notes yet. Your first transcript will land here.";
      dom.library.appendChild(empty);
      return;
    }

    for (const item of state.notes) {
      const row = document.createElement("div");
      row.className = "lib-item" + (state.note && state.note.id === item.id ? " active" : "");
      row.setAttribute("role", "button");
      row.tabIndex = 0;

      const title = document.createElement("span");
      title.className = "lib-title";
      title.textContent = item.title || "Untitled";
      const meta = document.createElement("span");
      meta.className = "lib-meta";
      meta.textContent = `${clock(item.duration)} · ${item.segment_count} seg`;

      const del = document.createElement("button");
      del.type = "button";
      del.className = "lib-del";
      del.title = "Delete note";
      del.innerHTML = icon("trash");
      del.addEventListener("click", (event) => {
        event.stopPropagation();
        if (del.dataset.armed === "1") {
          removeNote(item.id);
          return;
        }
        del.dataset.armed = "1";
        del.classList.add("confirm");
        del.textContent = "delete?";
        setTimeout(() => {
          del.dataset.armed = "";
          del.classList.remove("confirm");
          del.innerHTML = icon("trash");
        }, 2600);
      });

      const open = () => openNote(item.id);
      row.addEventListener("click", open);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      });

      row.append(title, meta, del);
      dom.library.appendChild(row);
    }
  }

  async function refreshLibrary() {
    try {
      const data = await api("/api/notes");
      state.notes = data.notes || [];
      renderLibrary();
    } catch (err) {
      /* ignored: the sidebar is not critical */
    }
  }

  async function removeNote(id) {
    try {
      await api(`/api/notes/${id}`, { method: "DELETE" });
      if (state.note && state.note.id === id) {
        state.note = null;
        dom.crumb.textContent = "new note";
        renderEmpty();
      }
      await refreshLibrary();
      toast("Note deleted");
    } catch (error) {
      toast(error.message, true);
    }
  }

  /* ----------------------------------------------------------- empty state */
  function renderEmpty() {
    state.view = "empty";
    state.audio = null;
    state.segmentEls = [];
    dom.brand.classList.remove("is-playing");
    dom.view.scrollTop = 0;

    const dataDir = state.health ? state.health.data_dir : "~/.sotto-notes";
    dom.view.innerHTML = `
      <div class="view-inner">
        <div class="hero">
          <span class="eyebrow">local transcription</span>
          <h2>Turn audio into notes.</h2>
          <p>Drop a recording. Get a timeline you can replay, edit, and export.
             The audio and the transcript stay on this machine.</p>
        </div>

        <div class="drop" id="drop">
          <div class="drop-icon">${icon("upload")}</div>
          <h3>Drop an audio file</h3>
          <p class="sub">or <button type="button" class="link-btn" id="browse">browse your files</button></p>
          <div class="chips">${SUPPORTED.map((ext) => `<span class="chip">${ext}</span>`).join("")}</div>
        </div>

        <div class="provider-row">
          <div>
            <label for="provider-select">Engine</label>
            <p class="provider-note" id="provider-note"></p>
          </div>
          <div class="select-wrap">
            <select id="provider-select"></select>
          </div>
        </div>

        <p class="foot-note">
          faster-whisper · cpu<br />
          notes are saved as json in <code>${escapeHtml(dataDir)}</code>
        </p>
      </div>
    `;

    const drop = $("#drop");
    let depth = 0;
    drop.addEventListener("dragenter", (event) => {
      event.preventDefault();
      depth += 1;
      drop.classList.add("dragging");
    });
    drop.addEventListener("dragleave", () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) drop.classList.remove("dragging");
    });
    drop.addEventListener("dragover", (event) => event.preventDefault());
    drop.addEventListener("drop", (event) => {
      event.preventDefault();
      depth = 0;
      drop.classList.remove("dragging");
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) startUpload(file);
    });
    $("#browse").addEventListener("click", () => dom.fileInput.click());

    renderProviderSelect();
  }

  function renderProviderSelect() {
    const select = $("#provider-select");
    if (!select) return;
    select.textContent = "";
    for (const provider of state.providers) {
      const option = document.createElement("option");
      option.value = provider.id;
      option.textContent = provider.available
        ? `${provider.label} · ${provider.model}`
        : `${provider.label} (unavailable)`;
      option.disabled = !provider.available;
      option.selected = provider.id === state.provider;
      select.appendChild(option);
    }
    select.addEventListener("change", () => {
      state.provider = select.value;
      localStorage.setItem("sotto.provider", state.provider);
      updateProviderNote();
    });
    updateProviderNote();
  }

  function updateProviderNote() {
    const note = $("#provider-note");
    if (!note) return;
    const provider = state.providers.find((p) => p.id === state.provider);
    note.textContent = provider ? provider.detail : "No engine available";
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* ------------------------------------------------------------- uploading */
  async function startUpload(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!SUPPORTED.includes(ext)) {
      toast(`.${ext || "?"} is not a supported audio type`, true);
      return;
    }
    if (file.size > 512 * 1024 * 1024) {
      toast("File is larger than 512 MiB", true);
      return;
    }
    if (state.dirty) await flushSave();
    state.note = null;
    state.jobId = null;
    renderLibrary();
    renderProgress({ filename: file.name, stage: "Uploading to the local server", progress: 0 });

    try {
      const response = await fetch("/api/transcribe", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
          "X-Provider": state.provider,
        },
        body: file,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Upload failed");
      state.jobId = data.job_id;
      setStatus("dirty", "transcribing…");
      pollJob();
    } catch (error) {
      renderProgressError(error.message);
      setStatus("error", "failed");
    }
  }

  function renderProgress(job) {
    state.view = "progress";
    state.audio = null;
    state.segmentEls = [];
    dom.brand.classList.remove("is-playing");
    dom.view.scrollTop = 0;
    dom.crumb.textContent = "transcribing";
    dom.view.innerHTML = `
      <div class="progress-view">
        <div class="progress-card" id="progress-card">
          <div class="eq" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>
          <div class="file" id="prog-file"></div>
          <h2 id="prog-title">Listening closely</h2>
          <p class="stage" id="prog-stage">Queued</p>
          <div class="progress-num"><span id="prog-pct">0</span><small>%</small></div>
          <div class="bar"><i id="prog-bar"></i></div>
          <p class="progress-hint">The first run downloads the tiny faster-whisper model (~75&nbsp;MB) once,
             then everything runs offline. Keep this tab open.</p>
        </div>
      </div>
    `;
    state.progress = {
      file: $("#prog-file"),
      title: $("#prog-title"),
      stage: $("#prog-stage"),
      pct: $("#prog-pct"),
      bar: $("#prog-bar"),
    };
    state.progress.file.textContent = job.filename || "audio";
    updateProgress(job);
  }

  function updateProgress(job) {
    if (!state.progress) return;
    const pct = Math.round((job.progress || 0) * 100);
    state.progress.pct.textContent = String(pct);
    state.progress.bar.style.width = `${pct}%`;
    state.progress.stage.textContent = job.stage || "Working";
    if (job.status === "queued") {
      state.progress.title.textContent = "Waiting for the transcriber";
    } else if (pct < 4) {
      state.progress.title.textContent = "Loading the model";
    } else {
      state.progress.title.textContent = "Listening closely";
    }
  }

  function renderProgressError(message) {
    state.view = "progress";
    state.jobId = null;
    dom.crumb.textContent = "transcribing";
    dom.view.innerHTML = `
      <div class="progress-view">
        <div class="progress-card">
          <div class="eq" aria-hidden="true" style="opacity:.25"><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>
          <h2>That didn't work</h2>
          <p class="stage" id="prog-error"></p>
          <div style="margin-top:26px;display:flex;gap:8px;justify-content:center">
            <button class="btn primary" type="button" id="retry-empty">${icon("back")} Start over</button>
          </div>
        </div>
      </div>
    `;
    $("#prog-error").textContent = message;
    $("#retry-empty").addEventListener("click", () => {
      renderEmpty();
      setStatus("", "ready");
      dom.crumb.textContent = "new note";
    });
  }

  async function pollJob() {
    if (!state.jobId) return;
    try {
      const data = await api(`/api/jobs/${state.jobId}`);
      const job = data.job;
      if (job.status === "done") {
        state.jobId = null;
        setStatus("saved", "saved");
        await refreshLibrary();
        await openNote(job.note_id);
        toast("Transcript ready");
        return;
      }
      if (job.status === "error") {
        state.jobId = null;
        setStatus("error", "failed");
        renderProgressError(job.error || "Transcription failed");
        return;
      }
      updateProgress(job);
      state.pollTimer = setTimeout(pollJob, 700);
    } catch (error) {
      state.pollTimer = setTimeout(pollJob, 1500);
    }
  }

  /* ------------------------------------------------------------------- note */
  async function openNote(id) {
    clearTimeout(state.pollTimer);
    state.jobId = null;
    if (state.dirty) await flushSave();
    try {
      const data = await api(`/api/notes/${id}`);
      renderNote(data.note);
    } catch (error) {
      toast(error.message, true);
      renderEmpty();
    }
  }

  function renderNote(note) {
    state.note = note;
    state.view = "note";
    state.activeIndex = -1;
    state.segmentEls = [];
    state.dirty = false;
    setStatus("saved", "saved");
    dom.brand.classList.remove("is-playing");
    dom.crumb.textContent = note.title || "untitled";
    dom.view.scrollTop = 0;
    dom.view.innerHTML = "";

    const inner = document.createElement("div");
    inner.className = "view-inner";
    dom.view.appendChild(inner);

    /* head */
    const head = document.createElement("div");
    head.className = "note-head";

    const title = document.createElement("input");
    title.className = "title-input";
    title.value = note.title || "Untitled";
    title.setAttribute("aria-label", "Note title");
    title.addEventListener("input", () => {
      state.note.title = title.value;
      dom.crumb.textContent = title.value || "untitled";
      markDirty();
    });
    title.addEventListener("keydown", (event) => {
      if (event.key === "Enter") title.blur();
    });
    title.addEventListener("blur", () => flushSave());

    const meta = document.createElement("div");
    meta.className = "meta";
    const pills = [
      ["duration", clock(note.duration)],
      ["language", (note.language || "auto").toUpperCase()],
      ["engine", `${note.provider} · ${note.model}`],
      ["segments", String((note.segments || []).length)],
      ["saved", shortDate(note.updated_at)],
    ];
    for (const [label, value] of pills) {
      const pill = document.createElement("span");
      pill.className = "pill";
      const b = document.createElement("b");
      b.textContent = value;
      pill.append(`${label} `, b);
      meta.appendChild(pill);
    }

    const actions = document.createElement("div");
    actions.className = "note-actions";
    const exportLabel = document.createElement("span");
    exportLabel.className = "export-label";
    exportLabel.textContent = "export";
    const group = document.createElement("div");
    group.className = "export-group";
    for (const [fmt, label] of [["md", "Markdown"], ["srt", "SRT"], ["txt", "Text"]]) {
      const link = document.createElement("a");
      link.className = "btn";
      link.href = `/api/export/${note.id}?format=${fmt}`;
      link.download = "";
      link.innerHTML = icon("download");
      link.append(label);
      group.appendChild(link);
    }
    const del = document.createElement("button");
    del.type = "button";
    del.className = "btn danger";
    del.style.marginLeft = "auto";
    del.innerHTML = `${icon("trash")} Delete`;
    del.addEventListener("click", () => {
      if (del.dataset.armed === "1") {
        removeNote(note.id);
        return;
      }
      del.dataset.armed = "1";
      del.textContent = "Click again to delete";
      setTimeout(() => {
        del.dataset.armed = "";
        del.innerHTML = `${icon("trash")} Delete`;
      }, 3000);
    });
    actions.append(exportLabel, group, del);
    head.append(title, meta, actions);
    inner.appendChild(head);

    /* player */
    const player = document.createElement("div");
    player.className = "player";
    player.innerHTML = `
      <button class="play-btn" type="button" id="play-btn" aria-label="Play">${icon("play")}</button>
      <span class="player-time"><span id="cur-time">0:00</span><span class="sep">/</span><span id="dur-time">${clock(note.duration)}</span></span>
      <div class="seek" id="seek" role="slider" aria-label="Seek" tabindex="0">
        <div class="seek-track"><div class="seek-fill" id="seek-fill"></div><div class="seek-thumb" id="seek-thumb"></div></div>
      </div>
      <button class="speed-btn" type="button" id="speed-btn" title="Playback speed">1x</button>
    `;
    inner.appendChild(player);

    const audio = document.createElement("audio");
    audio.id = "player";
    audio.preload = "metadata";
    audio.src = `/media/${note.id}`;
    inner.appendChild(audio);
    state.audio = audio;
    bindPlayer(audio, player);

    /* speakers */
    const speakers = document.createElement("details");
    speakers.className = "speakers";
    const summary = document.createElement("summary");
    summary.textContent = "Speakers · manual labels";
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent =
      "Diarization is not automatic: label segments yourself and name the voices here. Labels are used in every export.";
    const grid = document.createElement("div");
    grid.className = "speaker-grid";
    for (let i = 1; i <= 4; i += 1) {
      const key = `S${i}`;
      const field = document.createElement("label");
      field.className = "speaker-field";
      const tag = document.createElement("span");
      tag.textContent = key;
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = `Voice ${i}`;
      input.value = (note.speakers && note.speakers[key]) || "";
      input.addEventListener("input", () => {
        if (input.value.trim()) {
          state.note.speakers[key] = input.value.trim();
        } else {
          delete state.note.speakers[key];
          for (const segment of state.note.segments) {
            if (segment.speaker === key) segment.speaker = "";
          }
          refreshSpeakerSelects();
        }
        markDirty();
      });
      input.addEventListener("blur", () => flushSave());
      field.append(tag, input);
      grid.appendChild(field);
    }
    speakers.append(summary, hint, grid);
    inner.appendChild(speakers);

    /* timeline */
    const timeline = document.createElement("div");
    timeline.className = "timeline";
    note.segments = note.segments || [];
    note.segments.forEach((segment, index) => {
      const article = document.createElement("article");
      article.className = "segment";

      const stamp = document.createElement("button");
      stamp.type = "button";
      stamp.className = "stamp";
      stamp.textContent = clock(segment.start);
      stamp.title = "Play from here";
      stamp.addEventListener("click", () => {
        if (!state.audio) return;
        state.audio.currentTime = segment.start;
        state.audio.play();
      });

      const dot = document.createElement("div");
      dot.className = "dot";

      const body = document.createElement("div");
      body.className = "seg-body";

      const textarea = document.createElement("textarea");
      textarea.className = "seg-text";
      textarea.rows = 1;
      textarea.value = segment.text || "";
      textarea.setAttribute("aria-label", `Segment ${index + 1} text`);
      textarea.addEventListener("input", () => {
        segment.text = textarea.value;
        autoGrow(textarea);
        markDirty();
      });
      textarea.addEventListener("blur", () => flushSave());

      const speakerSelect = document.createElement("select");
      speakerSelect.className = "speaker-select";
      speakerSelect.title = "Speaker label";
      fillSpeakerOptions(speakerSelect, segment.speaker);
      speakerSelect.addEventListener("change", () => {
        const value = speakerSelect.value;
        segment.speaker = value;
        if (value) {
          if (!state.note.speakers[value]) {
            state.note.speakers[value] = `Speaker ${value.slice(1)}`;
            const input = grid.querySelectorAll("input")[Number(value.slice(1)) - 1];
            if (input) input.value = state.note.speakers[value];
          }
          body.classList.add("has-speaker");
        } else {
          body.classList.remove("has-speaker");
        }
        speakerSelect.classList.toggle("has-value", Boolean(value));
        markDirty();
      });

      body.append(speakerSelect, textarea);
      if (segment.speaker) {
        body.classList.add("has-speaker");
        speakerSelect.classList.add("has-value");
      }
      article.append(stamp, dot, body);
      timeline.appendChild(article);
      state.segmentEls.push({
        el: article,
        stamp,
        start: segment.start,
        end: segment.end,
      });

      requestAnimationFrame(() => autoGrow(textarea));
    });
    inner.appendChild(timeline);

    if (!note.segments.length) {
      const empty = document.createElement("p");
      empty.className = "stage";
      empty.style.textAlign = "center";
      empty.textContent = "No speech was detected in this file.";
      inner.appendChild(empty);
    }

    requestAnimationFrame(() => autoGrowAll());
  }

  function autoGrow(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }

  function autoGrowAll() {
    dom.view.querySelectorAll(".seg-text").forEach(autoGrow);
  }

  function fillSpeakerOptions(select, current) {
    select.textContent = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "no speaker";
    select.appendChild(none);
    for (let i = 1; i <= 4; i += 1) {
      const key = `S${i}`;
      const option = document.createElement("option");
      option.value = key;
      option.textContent = (state.note.speakers && state.note.speakers[key]) || key;
      option.selected = key === current;
      select.appendChild(option);
    }
    if (current && !["S1", "S2", "S3", "S4"].includes(current)) {
      select.value = "";
    }
  }

  function refreshSpeakerSelects() {
    if (!state.note) return;
    const selects = dom.view.querySelectorAll(".speaker-select");
    selects.forEach((select) => {
      fillSpeakerOptions(select, select.value);
      select.classList.toggle("has-value", Boolean(select.value));
      const body = select.closest(".seg-body");
      if (body) body.classList.toggle("has-speaker", Boolean(select.value));
    });
  }

  /* ----------------------------------------------------------------- player */
  function bindPlayer(audio, player) {
    const playBtn = $("#play-btn", player);
    const curTime = $("#cur-time", player);
    const durTime = $("#dur-time", player);
    const fill = $("#seek-fill", player);
    const thumb = $("#seek-thumb", player);
    const seek = $("#seek", player);
    const speed = $("#speed-btn", player);

    const paint = () => {
      const duration = audio.duration || state.note.duration || 0;
      const ratio = duration ? Math.min(1, audio.currentTime / duration) : 0;
      fill.style.width = `${ratio * 100}%`;
      thumb.style.left = `${ratio * 100}%`;
      curTime.textContent = clock(audio.currentTime);
      durTime.textContent = clock(duration);
    };

    playBtn.addEventListener("click", togglePlay);
    audio.addEventListener("play", () => {
      playBtn.innerHTML = icon("pause");
      playBtn.setAttribute("aria-label", "Pause");
      player.classList.add("playing");
      dom.brand.classList.add("is-playing");
    });
    audio.addEventListener("pause", () => {
      playBtn.innerHTML = icon("play");
      playBtn.setAttribute("aria-label", "Play");
      player.classList.remove("playing");
      dom.brand.classList.remove("is-playing");
    });
    audio.addEventListener("timeupdate", () => {
      paint();
      updateActiveSegment(audio.currentTime);
    });
    audio.addEventListener("loadedmetadata", paint);
    audio.addEventListener("ended", () => {
      dom.brand.classList.remove("is-playing");
    });

    seek.addEventListener("click", (event) => {
      const rect = seek.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      if (audio.duration) audio.currentTime = ratio * audio.duration;
      paint();
    });
    seek.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") seekBy(5);
      if (event.key === "ArrowLeft") seekBy(-5);
    });

    const speeds = [1, 1.25, 1.5, 2];
    speed.addEventListener("click", () => {
      const index = speeds.findIndex((rate) => rate === audio.playbackRate);
      const next = speeds[(index + 1) % speeds.length];
      audio.playbackRate = next;
      speed.textContent = `${next}x`;
    });

    paint();
  }

  function togglePlay() {
    if (!state.audio) return;
    if (state.audio.paused) state.audio.play();
    else state.audio.pause();
  }

  function seekBy(delta) {
    if (!state.audio) return;
    const duration = state.audio.duration || Infinity;
    state.audio.currentTime = Math.min(
      duration,
      Math.max(0, state.audio.currentTime + delta)
    );
  }

  function updateActiveSegment(time) {
    let index = -1;
    for (let i = 0; i < state.segmentEls.length; i += 1) {
      const segment = state.segmentEls[i];
      if (time >= segment.start && time < segment.end) {
        index = i;
        break;
      }
    }
    if (index === -1) return;
    if (index === state.activeIndex) return;
    state.segmentEls.forEach((segment, i) =>
      segment.el.classList.toggle("active", i === index)
    );
    state.activeIndex = index;
    if (!state.audio || state.audio.paused) return;
    if (Date.now() - state.lastManualScroll < 4000) return;
    const target = state.segmentEls[index].el;
    target.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  /* -------------------------------------------------------------- autosave */
  function markDirty() {
    if (!state.note) return;
    state.dirty = true;
    setStatus("dirty", "unsaved");
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(saveNow, 650);
  }

  async function flushSave() {
    clearTimeout(state.saveTimer);
    if (state.dirty) await saveNow();
  }

  async function saveNow() {
    if (!state.note || !state.dirty) return;
    const note = state.note;
    const seq = ++state.saveSeq;
    const payload = {
      title: note.title,
      speakers: note.speakers,
      segments: note.segments.map((segment) => ({
        id: segment.id,
        start: segment.start,
        end: segment.end,
        text: segment.text,
        speaker: segment.speaker,
      })),
    };
    state.dirty = false;
    setStatus("dirty", "saving…");
    try {
      const data = await api(`/api/notes/${note.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (seq === state.saveSeq) {
        note.updated_at = data.note.updated_at;
        if (!state.dirty) setStatus("saved", "saved");
      }
      await refreshLibrary();
    } catch (error) {
      state.dirty = true;
      setStatus("error", "save failed");
      toast(`Could not save: ${error.message}`, true);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
