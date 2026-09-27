/* Novaxis web-chat widget. One file, no dependencies.
   <script src="https://YOUR-WEB-HOST/widget.js" data-tenant="demo-hvac" data-api="https://YOUR-API-HOST"></script>
   Visitors get a signed token on first message; it lives in localStorage so a
   returning visitor threads into the same conversation. No personal data is stored.
   Voice: where the browser supports it, the mic button turns speech into the message and
   the speaker button reads replies aloud. Both run in the visitor's browser (Web Speech
   API): no audio reaches our servers, only the text, exactly as if typed. */
(function () {
  var script = document.currentScript;
  var tenant = script.getAttribute("data-tenant");
  var api = (script.getAttribute("data-api") || "").replace(/\/$/, "");
  if (!tenant) return;
  var key = "novaxis:" + tenant + ":visitor";
  var token = null;
  try { token = localStorage.getItem(key); } catch {}
  var lastId = null, loaded = false;

  var css = "#nvx-btn{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:28px;border:0;background:#1f2937;color:#fff;font-size:24px;cursor:pointer;z-index:99999}" +
    "#nvx-box{position:fixed;right:20px;bottom:88px;width:340px;max-width:calc(100vw - 40px);height:440px;max-height:70vh;background:#fff;border:1px solid #d1d5db;border-radius:12px;display:none;flex-direction:column;font:14px system-ui,sans-serif;z-index:99999;box-shadow:0 8px 24px rgba(0,0,0,.15)}" +
    "#nvx-log{flex:1;overflow:auto;padding:12px}.nvx-m{margin:6px 0;padding:8px 10px;border-radius:10px;max-width:85%;white-space:pre-wrap}.nvx-in{background:#e5e7eb;margin-left:auto}.nvx-out{background:#dbeafe}" +
    "#nvx-form{display:flex;border-top:1px solid #e5e7eb}#nvx-form input{flex:1;border:0;padding:12px;font:inherit}#nvx-form button{border:0;background:#1f2937;color:#fff;padding:0 16px;cursor:pointer}" +
    "#nvx-form .nvx-icon{background:#fff;color:#1f2937;padding:0 10px;font-size:18px}#nvx-form .nvx-on{background:#dbeafe}";
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  var btn = document.createElement("button"); btn.id = "nvx-btn"; btn.textContent = "\u{1F4AC}"; btn.title = "Chat with us";
  var box = document.createElement("div"); box.id = "nvx-box";
  box.innerHTML = '<div id="nvx-log"></div><form id="nvx-form"><input placeholder="Type a message" autocomplete="off"><button type="button" class="nvx-icon" id="nvx-speak" title="Read replies aloud" hidden>\u{1F508}</button><button type="button" class="nvx-icon" id="nvx-mic" title="Speak your message" hidden>\u{1F3A4}</button><button type="submit">Send</button></form>';
  document.body.appendChild(btn); document.body.appendChild(box);
  var log = box.querySelector("#nvx-log"), form = box.querySelector("#nvx-form"), input = form.querySelector("input");

  function add(dir, body) {
    var d = document.createElement("div"); d.className = "nvx-m " + (dir === "inbound" ? "nvx-in" : "nvx-out"); d.textContent = body; log.appendChild(d); log.scrollTop = log.scrollHeight;
  }

  // --- Voice, in the browser only -------------------------------------------------------
  var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var speakBtn = box.querySelector("#nvx-speak"), micBtn = box.querySelector("#nvx-mic");
  var speakKey = "novaxis:" + tenant + ":speak", speaking = false;
  try { speaking = localStorage.getItem(speakKey) === "1"; } catch {}
  function say(text) {
    if (!speaking || !window.speechSynthesis) return;
    var u = new SpeechSynthesisUtterance(text); u.lang = "en-GB"; window.speechSynthesis.speak(u);
  }
  if (window.speechSynthesis) {
    speakBtn.hidden = false; speakBtn.classList.toggle("nvx-on", speaking);
    speakBtn.onclick = function () {
      speaking = !speaking; speakBtn.classList.toggle("nvx-on", speaking);
      try { localStorage.setItem(speakKey, speaking ? "1" : "0"); } catch {}
      if (!speaking) window.speechSynthesis.cancel();
    };
  }
  if (Recognition) {
    micBtn.hidden = false;
    micBtn.onclick = function () {
      var rec = new Recognition(); rec.lang = "en-GB"; rec.interimResults = false; rec.maxAlternatives = 1;
      micBtn.classList.add("nvx-on"); input.placeholder = "Listening…";
      rec.onresult = function (e) { input.value = e.results[0][0].transcript; form.requestSubmit(); };
      rec.onend = function () { micBtn.classList.remove("nvx-on"); input.placeholder = "Type a message"; };
      rec.start();
    };
  }
  function poll() {
    // A new visitor has no history to load: everything from now on is new (and spoken).
    if (!token) { loaded = true; return; }
    var url = api + "/inbound/webchat/" + encodeURIComponent(tenant) + "/messages?visitor_token=" + encodeURIComponent(token) + (lastId ? "&after=" + encodeURIComponent(lastId) : "");
    fetch(url).then(function (r) { return r.ok ? r.json() : { messages: [] }; }).then(function (data) {
      // The first load after a page change shows the whole thread; later polls only replies.
      (data.messages || []).forEach(function (m) {
        if (m.direction === "outbound" || !loaded) add(m.direction, m.body);
        if (m.direction === "outbound" && loaded) say(m.body);
        lastId = m.id;
      });
      loaded = true;
    }).catch(function () {});
  }
  btn.onclick = function () { box.style.display = box.style.display === "flex" ? "none" : "flex"; if (box.style.display === "flex") { input.focus(); poll(); } };
  form.onsubmit = function (e) {
    e.preventDefault();
    var text = input.value.trim(); if (!text) return; input.value = "";
    add("inbound", text);
    fetch(api + "/inbound/webchat/" + encodeURIComponent(tenant), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: text, visitor_token: token, page: location.pathname })
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (data.visitor_token) { token = data.visitor_token; try { localStorage.setItem(key, token); } catch {} }
      if (data.message_id) lastId = data.message_id;
    }).catch(function () { add("outbound", "Sorry, something went wrong sending that. Please try again."); });
  };
  // Poll only while the chat is open: a closed widget on every page view costs nothing.
  setInterval(function () { if (box.style.display === "flex") poll(); }, 3000);
})();
