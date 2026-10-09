/**
 * แชทช่วยช้อป (เฟส 3) — วิดเจ็ตลอยมุมขวาล่าง
 *
 * ทางเข้า 3 ทาง: ปุ่มลอยบนหน้าค้นหา, "ถามเกี่ยวกับสินค้านี้" บนหน้าสินค้า, ปุ่มบนหน้าเปรียบเทียบ
 * ลำดับการแสดง: การ์ดสินค้า (ราคาจริงจากฐานข้อมูล) มาก่อน แล้วข้อความค่อยๆ ไหลตามมา (SSE)
 * ถ้า AI ใช้ไม่ได้ (โควตา/ปิดใช้/ล่ม) → สลับเป็นโหมดปุ่มเลือก: หมวด → งบ → การใช้งาน
 *
 * ต้องโหลดหลัง api.js (ใช้ apiFetch, priceHtml, compareButtonHtml, addToCart ฯลฯ)
 */
(function () {
  const DEVICE_KEY = "shopmarket_device_id";
  const SESSION_KEY = "shopmarket_chat_session";
  const LOG_KEY = "shopmarket_chat_log"; // ข้อความที่แสดงแล้ว (sessionStorage) ให้ย้ายหน้าแล้วบทสนทนาไม่หาย
  const MIN_INTERVAL_MS = 3000;

  let config = null; // {enabled, disclaimer, sample_questions, max_chars}
  let contextSkuId = null;
  let busy = false;
  let lastSentAt = 0;
  let guided = null; // สถานะโหมดปุ่มเลือก {category_id, max_price, use}
  let log = []; // [{role:"user"|"model"|"system", text, cards, suggestions, links, note, message_id, feedback, guided}]

  /* ---------- storage (ห่อ try/catch: บางเบราว์เซอร์ปิด storage) ---------- */
  const store = {
    get(k, s = localStorage) {
      try {
        return s.getItem(k);
      } catch {
        return null;
      }
    },
    set(k, v, s = localStorage) {
      try {
        if (v === null) s.removeItem(k);
        else s.setItem(k, v);
      } catch {}
    },
  };

  function deviceId() {
    let id = store.get(DEVICE_KEY);
    if (!id) {
      id = crypto.randomUUID ? crypto.randomUUID() : `d${Date.now()}${Math.random().toString(16).slice(2)}`;
      store.set(DEVICE_KEY, id);
    }
    return id;
  }

  function loadLog() {
    try {
      log = JSON.parse(store.get(LOG_KEY, sessionStorage) || "[]");
    } catch {
      log = [];
    }
  }

  function saveLog() {
    store.set(LOG_KEY, JSON.stringify(log.slice(-30)), sessionStorage);
  }

  /* ---------- DOM ---------- */
  let root, panel, list, input, sendBtn, counter, launcher;

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function build() {
    root = el(`<div class="chat-root"></div>`);
    launcher = el(`<button type="button" class="chat-launcher" aria-haspopup="dialog" aria-expanded="false">
        <span aria-hidden="true">💬</span><span class="chat-launcher-text">ถามผู้ช่วยช้อป</span></button>`);
    panel = el(`
      <section class="chat-panel" role="dialog" aria-modal="false" aria-labelledby="chat-title" hidden>
        <header class="chat-head">
          <div>
            <div class="chat-title" id="chat-title">ผู้ช่วยช้อป</div>
            <div class="chat-sub">ช่วยหาและเทียบสินค้าจากข้อมูลจริงในร้าน</div>
          </div>
          <div class="chat-head-actions">
            <button type="button" class="chat-icon-btn" data-act="reset" title="เริ่มคุยใหม่" aria-label="เริ่มคุยใหม่">↺</button>
            <button type="button" class="chat-icon-btn" data-act="close" title="ปิด" aria-label="ปิดแชท">✕</button>
          </div>
        </header>
        <div class="chat-list" role="log" aria-live="polite" aria-relevant="additions"></div>
        <form class="chat-form">
          <div class="chat-input-row">
            <textarea class="chat-input" rows="1" aria-label="พิมพ์คำถาม"
              placeholder="เช่น หาหูฟังไร้สาย งบไม่เกิน 1,500"></textarea>
            <button type="submit" class="chat-send" aria-label="ส่ง">➤</button>
          </div>
          <div class="chat-foot">
            <span class="chat-disclaimer"></span>
            <span class="chat-counter"></span>
          </div>
        </form>
      </section>`);
    root.append(launcher, panel);
    document.body.appendChild(root);

    list = panel.querySelector(".chat-list");
    input = panel.querySelector(".chat-input");
    sendBtn = panel.querySelector(".chat-send");
    counter = panel.querySelector(".chat-counter");
    panel.querySelector(".chat-disclaimer").textContent =
      config.disclaimer || "ตอบโดย AI อาจผิดพลาดได้ ราคาและเงื่อนไขที่ใช้จริงดูที่หน้าสินค้า อย่าใส่ข้อมูลส่วนตัว";

    launcher.addEventListener("click", () => open());
    panel.querySelector('[data-act="close"]').addEventListener("click", close);
    panel.querySelector('[data-act="reset"]').addEventListener("click", reset);
    panel.querySelector(".chat-form").addEventListener("submit", (e) => {
      e.preventDefault();
      send(input.value);
    });
    input.addEventListener("keydown", (e) => {
      // Enter = ส่ง, Shift+Enter = ขึ้นบรรทัดใหม่ (ไม่ส่งตอนกำลังเลือกคำไทยจาก IME)
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        send(input.value);
      }
    });
    input.addEventListener("input", () => {
      autoGrow();
      updateCounter();
    });
    panel.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
    // คลิกปุ่มใน list (ปุ่มที่สร้างจาก innerHTML) — ใช้ delegation
    list.addEventListener("click", onListClick);
    updateCounter();
  }

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }

  function maxChars() {
    return config?.max_chars || 500;
  }

  function updateCounter() {
    const n = input.value.length;
    counter.textContent = n > maxChars() * 0.8 ? `${n}/${maxChars()}` : "";
    counter.classList.toggle("over", n > maxChars());
  }

  function open(prefill) {
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    root.classList.add("open");
    if (!list.childElementCount) renderAll();
    if (prefill) {
      input.value = prefill;
      autoGrow();
      updateCounter();
    }
    setTimeout(() => input.focus(), 50);
    scrollDown();
  }

  function close() {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    root.classList.remove("open");
    launcher.focus();
  }

  function reset() {
    log = [];
    guided = null;
    saveLog();
    store.set(SESSION_KEY, null, sessionStorage);
    renderAll();
    input.focus();
  }

  function scrollDown() {
    list.scrollTop = list.scrollHeight;
  }

  /* ---------- การแสดงผล ---------- */
  function base() {
    return typeof pageBase === "function" ? pageBase() : "";
  }

  function cardHtml(p) {
    const id = p.product_id ?? p.id;
    const out = p.stock === 0;
    const lite = { ...p, id };
    return `
      <div class="chat-card">
        <a class="chat-card-thumb" href="${base()}pages/product-detail.html?id=${id}">${productThumb(p)}</a>
        <div class="chat-card-body">
          <a class="chat-card-name" href="${base()}pages/product-detail.html?id=${id}">${escapeHtml(p.name)}</a>
          <div class="product-price chat-card-price">${priceHtml(p)}</div>
          <div class="chat-card-meta">${p.review_count > 0 ? `⭐ ${p.rating} (${p.review_count})` : "ยังไม่มีรีวิว"}
            · ${escapeHtml(p.shop_name || "")}</div>
          <div class="chat-card-actions">
            <button type="button" class="btn btn-primary btn-xs" data-act="cart" data-id="${id}" ${out ? "disabled" : ""}>
              ${out ? "สินค้าหมด" : "ใส่ตะกร้า"}</button>
            ${compareButtonHtml(lite)}
          </div>
        </div>
      </div>`;
  }

  function chipsHtml(items, act) {
    return items.length
      ? `<div class="chat-chips" data-kind="${act}">${items
          .map((s, i) => `<button type="button" class="chat-chip" data-act="${act}" data-i="${i}">${escapeHtml(s.label ?? s)}</button>`)
          .join("")}</div>`
      : "";
  }

  function msgHtml(m, idx) {
    if (m.role === "user") return `<div class="chat-msg user"><div class="chat-bubble">${escapeHtml(m.text)}</div></div>`;
    if (m.role === "system") return `<div class="chat-msg system">${escapeHtml(m.text)}</div>`;
    const cards = (m.cards || []).map(cardHtml).join("");
    const isLast = idx === log.length - 1;
    return `
      <div class="chat-msg model" data-idx="${idx}">
        ${cards ? `<div class="chat-cards">${cards}</div>` : ""}
        ${m.text || m.pending
          ? `<div class="chat-bubble">${escapeHtml(m.text || "")}${m.pending ? `<span class="chat-typing" aria-label="กำลังพิมพ์"><i></i><i></i><i></i></span>` : ""}</div>`
          : ""}
        ${m.note ? `<div class="chat-note">${escapeHtml(m.note)}</div>` : ""}
        ${(m.links || []).length
          ? `<div class="chat-links">${m.links
              .map((l) => `<a href="${escapeHtml(safeUrl(l.url))}" class="chat-link">${escapeHtml(l.label)} →</a>`)
              .join("")}</div>`
          : ""}
        ${m.guided ? guidedHtml(m.guided) : ""}
        ${isLast && (m.suggestions || []).length ? chipsHtml(m.suggestions, "suggest") : ""}
        ${m.message_id && !m.pending
          ? `<div class="chat-feedback" role="group" aria-label="คำตอบนี้มีประโยชน์ไหม">
               <button type="button" class="chat-fb ${m.feedback === "up" ? "on" : ""}" data-act="fb" data-v="up"
                 aria-pressed="${m.feedback === "up"}" title="มีประโยชน์">👍</button>
               <button type="button" class="chat-fb ${m.feedback === "down" ? "on" : ""}" data-act="fb" data-v="down"
                 aria-pressed="${m.feedback === "down"}" title="ไม่มีประโยชน์">👎</button>
             </div>`
          : ""}
      </div>`;
  }

  /** ลิงก์จาก backend: อนุญาตเฉพาะ path ภายในเว็บ */
  function safeUrl(url) {
    if (typeof url !== "string" || !url.startsWith("/") || url.startsWith("//")) return "#";
    return url;
  }

  function welcomeHtml() {
    const samples = config?.sample_questions || [];
    return `
      <div class="chat-msg model welcome">
        <div class="chat-bubble">สวัสดีครับ ผมช่วยหาและเปรียบเทียบสินค้าในร้านได้ บอกได้เลยว่าอยากได้อะไร งบเท่าไหร่ ใช้ทำอะไร${
          contextSkuId ? " หรือถามเกี่ยวกับสินค้าที่เปิดดูอยู่ก็ได้ครับ" : ""
        }</div>
        ${chipsHtml(samples, "sample")}
        <div class="chat-policy-link"><a href="${base()}pages/chat-policy.html">ผู้ช่วยแนะนำสินค้าอย่างไร?</a></div>
      </div>`;
  }

  function renderAll() {
    list.innerHTML = (log.length ? "" : welcomeHtml()) + log.map(msgHtml).join("");
    scrollDown();
  }

  function renderMsg(idx) {
    const node = list.querySelector(`.chat-msg.model[data-idx="${idx}"]`);
    const html = msgHtml(log[idx], idx);
    if (node) node.replaceWith(el(html));
    else list.appendChild(el(html));
    // ปุ่มคำถามแนะนำมีได้เฉพาะคำตอบล่าสุด
    list.querySelectorAll(`.chat-msg.model:not([data-idx="${idx}"]) .chat-chips[data-kind="suggest"]`).forEach((c) => c.remove());
    scrollDown();
  }

  function push(m) {
    log.push(m);
    const idx = log.length - 1;
    if (list.querySelector(".welcome")) list.innerHTML = "";
    if (m.role === "model") renderMsg(idx);
    else list.appendChild(el(msgHtml(m, idx)));
    scrollDown();
    return idx;
  }

  /* ---------- ส่งข้อความ (SSE ผ่าน fetch เพราะ EventSource ส่ง POST ไม่ได้) ---------- */
  async function send(raw) {
    const text = (raw || "").trim();
    if (!text || busy) return;
    if (text.length > maxChars()) {
      showToast(`ข้อความยาวเกิน ${maxChars()} ตัวอักษร`, "error");
      return;
    }
    const wait = MIN_INTERVAL_MS - (Date.now() - lastSentAt);
    if (wait > 0) {
      showToast("ส่งเร็วไปนิด รอสักครู่แล้วค่อยถามต่อนะครับ", "error");
      return;
    }
    lastSentAt = Date.now();
    input.value = "";
    autoGrow();
    updateCounter();
    push({ role: "user", text });
    const idx = push({ role: "model", text: "", cards: [], pending: true });
    setBusy(true);

    const headers = { "Content-Type": "application/json", Accept: "text/event-stream" };
    const token = getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    try {
      res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          session_id: store.get(SESSION_KEY, sessionStorage),
          message: text,
          context_sku_id: contextSkuId,
          device_id: deviceId(),
        }),
      });
    } catch {
      return failTo(idx, "เชื่อมต่อไม่ได้ ลองใช้โหมดเลือกจากปุ่มแทนนะครับ", true);
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = Array.isArray(err.detail) ? err.detail.map((d) => d.msg).join(", ") : err.detail;
      if (err.fallback || res.status === 429 || res.status === 503 || res.status >= 500) {
        const msg =
          err.reason === "daily"
            ? "วันนี้ถามครบโควตาแล้ว ลองเลือกจากปุ่มด้านล่างแทนได้เลยครับ"
            : err.reason === "rate"
            ? "ส่งเร็วไปนิด ระหว่างนี้ลองเลือกจากปุ่มด้านล่างได้ครับ"
            : detail || "ผู้ช่วยตอบไม่ได้ชั่วคราว ลองเลือกจากปุ่มด้านล่างแทนนะครับ";
        return failTo(idx, msg, true);
      }
      return failTo(idx, detail || `เกิดข้อผิดพลาด (${res.status})`, false);
    }

    try {
      await readStream(res, idx);
    } catch {
      if (log[idx].pending) failTo(idx, "การเชื่อมต่อขาดระหว่างตอบ ลองใหม่อีกครั้งนะครับ", false);
    } finally {
      setBusy(false);
    }
  }

  async function readStream(res, idx) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let cut;
      while ((cut = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, cut);
        buf = buf.slice(cut + 2);
        handleEvent(block, idx);
      }
    }
    if (buf.trim()) handleEvent(buf, idx);
    if (log[idx].pending) {
      // stream จบโดยไม่มี done
      log[idx].pending = false;
      renderMsg(idx);
      saveLog();
    }
  }

  function handleEvent(block, idx) {
    let event = "message";
    const data = [];
    block.split("\n").forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    });
    let payload = {};
    try {
      payload = data.length ? JSON.parse(data.join("\n")) : {};
    } catch {
      return;
    }
    const m = log[idx];
    if (event === "meta") {
      if (payload.session_id) store.set(SESSION_KEY, payload.session_id, sessionStorage);
      m.message_id = payload.message_id;
      m.mode = payload.mode;
    } else if (event === "cards") {
      m.cards = payload.products || [];
      renderMsg(idx);
    } else if (event === "delta") {
      m.text = (m.text || "") + (payload.text || "");
      // อัปเดตเฉพาะ bubble ไม่ render การ์ดใหม่ทุก chunk
      const bubble = list.querySelector(`.chat-msg.model[data-idx="${idx}"] .chat-bubble`);
      if (bubble) {
        bubble.firstChild && bubble.firstChild.nodeType === 3
          ? (bubble.firstChild.nodeValue = m.text)
          : bubble.insertBefore(document.createTextNode(m.text), bubble.firstChild);
        scrollDown();
      } else renderMsg(idx);
    } else if (event === "done") {
      m.pending = false;
      m.message_id = payload.message_id || m.message_id;
      // ข้อความสุดท้ายที่ผ่านการตรวจแล้วจาก server เป็นตัวจริง (ถ้าไม่ผ่าน = "" แสดงเฉพาะการ์ด)
      m.text = typeof payload.text === "string" ? payload.text : m.text;
      m.suggestions = payload.suggestions || [];
      m.links = payload.links || [];
      m.note = payload.note || null;
      if (payload.fallback) {
        m.text = "";
        renderMsg(idx);
        saveLog();
        startGuided("ตอนนี้ผู้ช่วย AI ตอบไม่ได้ ลองเลือกจากปุ่มด้านล่างแทนนะครับ");
        return;
      }
      if (!m.text && !(m.cards || []).length && !m.links.length) {
        m.text = "ขออภัยครับ ตอนนี้ตอบคำถามนี้ไม่ได้ ลองถามใหม่อีกแบบได้ไหมครับ";
      }
      renderMsg(idx);
      saveLog();
    }
  }

  function failTo(idx, message, toGuided) {
    log.splice(idx, 1); // เอา bubble "กำลังพิมพ์" ออก
    renderAll();
    setBusy(false);
    if (toGuided) startGuided(message);
    else {
      push({ role: "system", text: message });
      saveLog();
    }
  }

  function setBusy(b) {
    busy = b;
    sendBtn.disabled = b;
    input.setAttribute("aria-busy", String(b));
  }

  /* ---------- โหมดปุ่มเลือก (ไม่ใช้ AI): หมวด → งบ → การใช้งาน → ผลลัพธ์ ---------- */
  function guidedHtml(g) {
    return `
      <div class="chat-guided">
        ${g.question ? `<div class="chat-guided-q">${escapeHtml(g.question)}</div>` : ""}
        ${(g.options || []).length ? chipsHtml(g.options, "guided") : ""}
      </div>`;
  }

  async function startGuided(message) {
    guided = {};
    if (message) push({ role: "system", text: message });
    await guidedStep();
  }

  async function guidedStep() {
    const q = new URLSearchParams();
    Object.entries(guided || {}).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && q.set(k, v));
    let step;
    try {
      step = await apiFetch(`/chat/guided${q.toString() ? `?${q}` : ""}`);
    } catch (err) {
      push({ role: "system", text: `โหลดตัวเลือกไม่สำเร็จ: ${err.message}` });
      return;
    }
    push({
      role: "model",
      text: step.step === "results" ? (step.products || []).length ? "นี่คือสินค้าที่ตรงกับที่เลือกครับ" : "ยังไม่มีสินค้าที่ตรงกับที่เลือกครับ" : "",
      cards: step.products || [],
      guided: step.step === "results" ? null : { step: step.step, question: step.question, options: step.options || [] },
      suggestions: step.step === "results" ? ["เริ่มเลือกใหม่"] : [],
    });
    saveLog();
  }

  /* ---------- คลิกในรายการข้อความ ---------- */
  async function onListClick(e) {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    const msgEl = btn.closest(".chat-msg");
    const idx = msgEl?.dataset.idx !== undefined ? Number(msgEl.dataset.idx) : -1;
    const m = log[idx];

    if (act === "sample") {
      send((config?.sample_questions || [])[Number(btn.dataset.i)]);
    } else if (act === "suggest") {
      const s = m?.suggestions?.[Number(btn.dataset.i)];
      if (s === "เริ่มเลือกใหม่") return startGuided();
      send(typeof s === "string" ? s : s?.label);
    } else if (act === "guided") {
      const opt = m?.guided?.options?.[Number(btn.dataset.i)];
      if (!opt) return;
      const key = { category: "category_id", budget: "max_price", use: "use" }[m.guided.step];
      push({ role: "user", text: opt.label });
      // "ไม่จำกัด/ไม่ระบุ" ต้องส่งค่าไปด้วย (เช่น "any") ไม่งั้น server จะถามขั้นเดิมซ้ำ
      guided = { ...(guided || {}), [key]: opt.value ?? "any" };
      m.guided = { ...m.guided, options: [] }; // เลือกแล้ว ไม่ให้กดซ้ำ
      renderMsg(idx);
      await guidedStep();
    } else if (act === "cart") {
      btn.disabled = true;
      try {
        await addToCart(Number(btn.dataset.id), 1);
        await renderCartBadge();
        showToast("เพิ่มลงตะกร้าแล้ว ✓");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    } else if (act === "fb" && m?.message_id) {
      const value = m.feedback === btn.dataset.v ? null : btn.dataset.v; // กดซ้ำ = ยกเลิก
      try {
        await apiFetch("/chat/feedback", {
          method: "POST",
          body: JSON.stringify({ message_id: m.message_id, value, device_id: deviceId() }),
        });
        m.feedback = value;
        saveLog();
        renderMsg(idx);
        if (value) showToast("ขอบคุณสำหรับความเห็นครับ");
      } catch (err) {
        showToast(err.message, "error");
      }
    }
  }

  /* ---------- เริ่มต้น ---------- */
  /**
   * เปิดใช้วิดเจ็ตบนหน้านี้
   * options.launcher: แสดงปุ่มลอย (หน้าค้นหา) — หน้าอื่นเปิดผ่านปุ่มของหน้าเอง
   * options.contextSkuId: สินค้าที่กำลังดู (หน้าสินค้า)
   */
  async function init(options = {}) {
    contextSkuId = options.contextSkuId || null;
    try {
      config = await apiFetch(`/chat/config?device_id=${encodeURIComponent(deviceId())}`);
    } catch {
      config = null;
    }
    // ปิดใช้ (flag/ยังไม่อยู่ในกลุ่ม rollout) → ไม่แสดงทางเข้าเลย
    if (!config || !config.enabled) return false;
    loadLog();
    build();
    if (!options.launcher) launcher.classList.add("chat-launcher-hidden");
    document.querySelectorAll("[data-chat-entry]").forEach((b) => (b.hidden = false));
    return true;
  }

  window.ShopChat = {
    init,
    open: (prefill) => panel && open(prefill),
    setContext: (id) => (contextSkuId = id || null),
    isReady: () => !!panel,
  };
})();
