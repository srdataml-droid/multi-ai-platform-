/* Novaxis web-chat widget. One file, no dependencies.
   <script src="https://YOUR-WEB-HOST/widget.js" data-tenant="demo-hvac" data-api="https://YOUR-API-HOST"></script>
   Visitors get a signed token on first message; it lives in localStorage so a
   returning visitor threads into the same conversation. No personal data is stored. */
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
    "#nvx-form{display:flex;border-top:1px solid #e5e7eb}#nvx-form input{flex:1;border:0;padding:12px;font:inherit}#nvx-form button{border:0;background:#1f2937;color:#fff;padding:0 16px;cursor:pointer}";
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);
  var btn = document.createElement("button"); btn.id = "nvx-btn"; btn.textContent = "\u{1F4AC}"; btn.title = "Chat with us";
  var box = document.createElement("div"); box.id = "nvx-box";
  box.innerHTML = '<div id="nvx-log"></div><form id="nvx-form"><input placeholder="Type a message" autocomplete="off"><button type="submit">Send</button></form>';
  document.body.appendChild(btn); document.body.appendChild(box);
  var log = box.querySelector("#nvx-log"), form = box.querySelector("#nvx-form"), input = form.querySelector("input");

  function add(dir, body) {
    var d = document.createElement("div"); d.className = "nvx-m " + (dir === "inbound" ? "nvx-in" : "nvx-out"); d.textContent = body; log.appendChild(d); log.scrollTop = log.scrollHeight;
  }
  function poll() {
    if (!token) return;
    var url = api + "/inbound/webchat/" + encodeURIComponent(tenant) + "/messages?visitor_token=" + encodeURIComponent(token) + (lastId ? "&after=" + encodeURIComponent(lastId) : "");
    fetch(url).then(function (r) { return r.ok ? r.json() : { messages: [] }; }).then(function (data) {
      // The first load after a page change shows the whole thread; later polls only replies.
      (data.messages || []).forEach(function (m) { if (m.direction === "outbound" || !loaded) add(m.direction, m.body); lastId = m.id; });
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
