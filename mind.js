(function () {
  "use strict";

  var DB_NAME = "yabot-mind";
  var DB_VER = 1;
  var STORE = "entries";
  var TZ = "America/Denver";

  var state = {
    mode: "conversation", // conversation | note
    lane: "conversation",
    speaker: "USER",
    amendId: null,
    entries: [],
    filter: ""
  };

  var el = {
    transcript: document.getElementById("transcript"),
    count: document.getElementById("tape-count"),
    text: document.getElementById("text"),
    speaker: document.getElementById("speaker"),
    speakerRow: document.getElementById("speaker-row"),
    search: document.getElementById("search"),
    amendHint: document.getElementById("amend-hint"),
    net: document.getElementById("net-pill")
  };

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          var os = db.createObjectStore(STORE, { keyPath: "id" });
          os.createIndex("ts", "ts", { unique: false });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function withStore(mode, fn) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, mode);
        var store = tx.objectStore(STORE);
        var result = fn(store);
        tx.oncomplete = function () { resolve(result); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function loadAll() {
    return withStore("readonly", function (store) {
      return new Promise(function (resolve, reject) {
        var req = store.index("ts").getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function () { reject(req.error); };
      });
    }).then(function (rows) {
      // getAll via index returns promise nested — flatten
      return rows;
    });
  }

  // Fix nested promise from withStore
  function loadEntries() {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readonly");
        var req = tx.objectStore(STORE).index("ts").getAll();
        req.onsuccess = function () {
          var rows = req.result || [];
          rows.sort(function (a, b) { return (a.ts || "").localeCompare(b.ts || ""); });
          resolve(rows);
        };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function putEntry(entry) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(entry);
        tx.oncomplete = function () { resolve(entry); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function putMany(entries) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        var store = tx.objectStore(STORE);
        entries.forEach(function (e) { store.put(e); });
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function kindFor(mode, lane, speaker) {
    if (mode === "note") return "note-" + lane;
    var sp = (speaker || "").toUpperCase();
    if (sp === "USER") return "prompt-" + lane;
    return "reply-" + lane;
  }

  function formatDenver(iso) {
    try {
      var d = new Date(iso);
      return new Intl.DateTimeFormat("en-US", {
        timeZone: TZ,
        year: "numeric", month: "short", day: "numeric",
        hour: "numeric", minute: "2-digit", second: "2-digit",
        hour12: true
      }).format(d) + " MT";
    } catch (e) {
      return iso;
    }
  }

  function render() {
    var q = (state.filter || "").trim().toLowerCase();
    var list = state.entries;
    if (q) {
      list = list.filter(function (e) {
        return (e.text || "").toLowerCase().indexOf(q) !== -1 ||
          (e.speaker || "").toLowerCase().indexOf(q) !== -1 ||
          (e.kind || "").toLowerCase().indexOf(q) !== -1 ||
          (e.lane || "").toLowerCase().indexOf(q) !== -1 ||
          (e.id || "").toLowerCase().indexOf(q) !== -1;
      });
    }
    el.count.textContent = "Mind tape: " + state.entries.length + " entries";
    if (!list.length) {
      el.transcript.innerHTML = '<div class="empty-mind">' +
        (state.entries.length ? "No matches." : "Mind tape is empty. Record a conversation or note below.<br><span style=\"font-size:.85em;opacity:.8\">Entries are stored on this device. Export to share.</span>") +
        "</div>";
      return;
    }
    var html = "";
    list.forEach(function (e) {
      var noteCls = (e.kind || "").indexOf("note-") === 0 ? " note" : "";
      html += '<article class="entry' + noteCls + '" data-id="' + esc(e.id) + '">';
      html += '<div class="entry-head">';
      html += '<span class="kind-badge">' + esc(e.kind) + "</span>";
      html += "<span>" + esc(e.speaker || "—") + "</span>";
      html += '<span class="when">' + esc(formatDenver(e.ts)) + "</span>";
      html += "</div>";
      html += '<div class="entry-text">' + esc(e.text) + "</div>";
      if (e.amends) {
        html += '<div class="entry-amends">amends ' + esc(e.amends) + "</div>";
      }
      html += "</article>";
    });
    el.transcript.innerHTML = html;
    el.transcript.scrollTop = el.transcript.scrollHeight;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function refresh() {
    state.entries = await loadEntries();
    render();
  }

  async function send() {
    var text = (el.text.value || "").trim();
    if (!text) return;
    var speaker = state.mode === "note"
      ? "NOTE"
      : ((el.speaker.value || state.speaker || "USER").trim() || "USER");
    var entry = {
      id: uuid(),
      ts: new Date().toISOString(),
      kind: kindFor(state.mode, state.lane, speaker),
      lane: state.lane,
      speaker: speaker,
      text: text,
      amends: state.amendId || null,
      device: "web",
      source: "rizal.pw"
    };
    await putEntry(entry);
    el.text.value = "";
    state.amendId = null;
    el.amendHint.hidden = true;
    await refresh();
    el.text.focus();
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll(".mode-row .toggle").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === mode);
    });
    el.speakerRow.style.display = mode === "note" ? "none" : "flex";
  }

  function setLane(lane) {
    state.lane = lane;
    document.querySelectorAll(".lane-row .toggle").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-lane") === lane);
    });
  }

  function setSpeaker(name) {
    state.speaker = name;
    el.speaker.value = name;
    document.querySelectorAll(".speaker-row .toggle").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-speaker") === name);
    });
  }

  function exportTape() {
    var day = new Date().toLocaleDateString("en-CA", { timeZone: TZ }); // YYYY-MM-DD
    var lines = state.entries.map(function (e) { return JSON.stringify(e); }).join("\n");
    if (lines) lines += "\n";
    download("mind-transcript-" + day + ".jsonl", lines, "application/x-ndjson");

    var md = "# ЯBOT Mind tape\n\nExported " + day + " (America/Denver calendar day).\n\n";
    state.entries.forEach(function (e) {
      md += "## " + e.kind + " · " + (e.speaker || "") + " · " + formatDenver(e.ts) + "\n\n";
      md += e.text + "\n\n";
      if (e.amends) md += "_amends `" + e.amends + "`_\n\n";
      md += "<!-- id: " + e.id + " -->\n\n";
    });
    download("mind-transcript-" + day + ".md", md, "text/markdown");
  }

  function download(name, body, type) {
    var blob = new Blob([body], { type: type });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  async function importFile(file) {
    var text = await file.text();
    var lines = text.split(/\r?\n/);
    var incoming = [];
    lines.forEach(function (line) {
      line = line.trim();
      if (!line) return;
      try {
        var obj = JSON.parse(line);
        if (obj && obj.id && obj.ts && obj.kind && obj.text != null) {
          if (!obj.device) obj.device = "web";
          if (!obj.source) obj.source = "rizal.pw";
          if (!obj.lane) obj.lane = "conversation";
          if (obj.amends === undefined) obj.amends = null;
          incoming.push(obj);
        }
      } catch (err) { /* skip bad lines */ }
    });
    if (!incoming.length) {
      alert("No valid Mind tape lines found.");
      return;
    }
    var have = {};
    state.entries.forEach(function (e) { have[e.id] = true; });
    var fresh = incoming.filter(function (e) { return !have[e.id]; });
    if (fresh.length) await putMany(fresh);
    await refresh();
    alert("Merged " + fresh.length + " new entries (deduped by id). Tape now " + state.entries.length + ".");
  }

  // UI wiring
  document.querySelectorAll(".mode-row .toggle").forEach(function (b) {
    b.addEventListener("click", function () { setMode(b.getAttribute("data-mode")); });
  });
  document.querySelectorAll(".lane-row .toggle").forEach(function (b) {
    b.addEventListener("click", function () { setLane(b.getAttribute("data-lane")); });
  });
  document.querySelectorAll(".speaker-row .toggle").forEach(function (b) {
    b.addEventListener("click", function () { setSpeaker(b.getAttribute("data-speaker")); });
  });
  el.speaker.addEventListener("input", function () {
    state.speaker = el.speaker.value;
    document.querySelectorAll(".speaker-row .toggle").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-speaker") === el.speaker.value);
    });
  });

  document.getElementById("btn-send").addEventListener("click", send);
  document.getElementById("btn-plus").addEventListener("click", function () { el.text.focus(); });
  el.text.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      send();
    }
  });
  document.getElementById("btn-export").addEventListener("click", exportTape);
  document.getElementById("import-file").addEventListener("change", function (ev) {
    var f = ev.target.files && ev.target.files[0];
    if (f) importFile(f).then(function () { ev.target.value = ""; });
  });
  document.getElementById("btn-amend").addEventListener("click", function () {
    if (!state.entries.length) return;
    var last = state.entries[state.entries.length - 1];
    state.amendId = last.id;
    el.amendHint.hidden = false;
    el.amendHint.textContent = "Next entry will amend " + last.id.slice(0, 8) + "… (NEVER-DELETE: correction is a new line)";
    el.text.focus();
  });
  el.search.addEventListener("input", function () {
    state.filter = el.search.value;
    render();
  });

  function updateNet() {
    if (!el.net) return;
    if (navigator.onLine) {
      el.net.textContent = "ONLINE (app stays local)";
      el.net.classList.add("online");
    } else {
      el.net.textContent = "OFFLINE";
      el.net.classList.remove("online");
    }
  }
  window.addEventListener("online", updateNet);
  window.addEventListener("offline", updateNet);
  updateNet();

  refresh().catch(function (err) {
    el.transcript.innerHTML = '<div class="empty-mind">Could not open Mind tape: ' + esc(String(err)) + "</div>";
  });
})();
