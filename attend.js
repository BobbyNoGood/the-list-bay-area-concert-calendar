/* attend.js - "Click If You Are Attending" guitar + Most popular sort.
   Loaded by index.html. Needs the Cloudflare Worker at API. */
(function () {
  var API = "https://attend.nogoodbobby55.workers.dev";
  var counts = {}, mine = {}, ready = false, mode = "date";

  function num(id) { return counts[id] || 0; }

  function label(going, c) {
    var n = c > 0 ? "<b>" + c + "</b> \u00b7 " : "";
    return "\ud83c\udfb8 " + n + (going ? "You\u2019re going \u2713" : "Click if you are attending");
  }

  window.attendBtn = function (e) {
    if (!ready || !e.id) return "";
    var going = !!mine[e.id];
    var when = mode === "pop" ? '<div class="city">' + esc(e.day) + "</div>" : "";
    return when + '<button type="button" class="attend' + (going ? " on" : "") +
      '" data-id="' + esc(e.id) + '" aria-pressed="' + going + '">' +
      label(going, num(e.id)) + "</button>";
  };

  function popSort(a, b) {
    return num(b.id) - num(a.id) || a.date.localeCompare(b.date) || a.venue.localeCompare(b.venue);
  }

  function setMode(m) {
    mode = m;
    var pop = m === "pop";
    window.attendSort = pop ? popSort : null;
    window.attendKey = pop ? function () { return "pop"; } : null;
    window.attendHead = pop ? function () { return "Most popular \ud83c\udfb8"; } : null;
    try { render(); } catch (err) {}
  }

  function addControls() {
    var clear = document.getElementById("clear");
    if (!clear || document.getElementById("sortMode")) return;
    var field = document.createElement("div");
    field.className = "field";
    field.innerHTML = '<select id="sortMode"><option value="date">Sort: By date</option>' +
      '<option value="pop">Sort: Most popular \ud83c\udfb8</option></select>';
    clear.parentNode.parentNode.insertBefore(field, clear.parentNode);
    document.getElementById("sortMode").addEventListener("change", function () { setMode(this.value); });
    var oldClear = clear.onclick;
    clear.onclick = function () {
      document.getElementById("sortMode").value = "date";
      mode = "date"; window.attendSort = null; window.attendKey = null; window.attendHead = null;
      if (oldClear) oldClear.apply(this, arguments);
    };
  }

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest ? ev.target.closest(".attend") : null;
    if (!b) return;
    ev.stopPropagation();
    ev.preventDefault();
    if (b.disabled) return;
    var id = b.getAttribute("data-id");
    b.disabled = true;
    fetch(API + "/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && typeof d.count === "number") {
        counts[id] = d.count;
        mine[id] = !!d.going;
        b.className = "attend" + (d.going ? " on" : "");
        b.setAttribute("aria-pressed", String(!!d.going));
        b.innerHTML = label(!!d.going, d.count);
      } else if (d && d.error === "too many") {
        alert("That's a lot of shows! You can mark up to 100.");
      }
    }).catch(function () {}).then(function () { b.disabled = false; });
  }, true);

  var css = document.createElement("style");
  css.textContent =
    ".attend{margin-top:8px;padding:7px 10px;min-height:0;font-size:13px;font-weight:700;" +
    "background:var(--panel2);border:1px solid var(--line);color:var(--muted);border-radius:999px;cursor:pointer}" +
    ".attend b{color:var(--text)}" +
    ".attend.on{background:var(--lime);border-color:var(--lime);color:#111}" +
    ".attend.on b{color:#111}";
  document.head.appendChild(css);

  fetch(API + "/counts").then(function (r) { return r.json(); }).then(function (d) {
    counts = d.counts || {};
    (d.mine || []).forEach(function (id) { mine[id] = true; });
    ready = true;
    addControls();
    try { render(); } catch (err) {}
  }).catch(function () {});
})();
