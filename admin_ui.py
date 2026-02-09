from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    # Simple UI (no build tools, just HTML + JS)
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Prompt Builder Admin</title>
  <style>
    body { font-family: -apple-system, Arial, sans-serif; margin: 24px; max-width: 900px; }
    label { display:block; margin-top: 12px; font-weight: 600; }
    input, textarea { width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }
    textarea { min-height: 140px; }
    .row { display:flex; gap: 12px; }
    .row > div { flex: 1; }
    button { padding: 10px 14px; margin-top: 12px; cursor:pointer; }
    .btns { display:flex; gap: 10px; flex-wrap: wrap; }
    .small { color:#555; font-size: 13px; }
    .ok { color: #0a7a0a; }
    .err { color: #b00020; }
    pre { background:#f6f6f6; padding: 10px; overflow:auto; }
  </style>
</head>
<body>
  <h1>Prompt Builder Admin</h1>
  <div class="small">Uses your API: /api/prompt/generate, /api/prompt/save, /api/prompt/get</div>

  <label>Tenant Phone Number (THIS must match your Twilio "To" number)</label>
  <input id="phone" placeholder="+17042017393" />

  <div class="row">
    <div>
      <label>Business Name</label>
      <input id="business_name" placeholder="Sheriff Burger" />
    </div>
    <div>
      <label>Business Type</label>
      <input id="business_type" placeholder="food truck" />
    </div>
  </div>

  <label>Location</label>
  <input id="location" placeholder="Charlotte, NC" />

  <label>Services (comma-separated)</label>
  <input id="services" placeholder="Take orders, Menu questions, Hours/location, Catering inquiries" />

  <div class="row">
    <div>
      <label>Hours</label>
      <input id="hours" placeholder="Mon-Sat 11am-8pm" />
    </div>
    <div>
      <label>Tone</label>
      <input id="tone" placeholder="friendly, short, confident" />
    </div>
  </div>

  <label>Languages (comma-separated)</label>
  <input id="languages" placeholder="English, Spanish" />

  <label>Booking/Catering Instructions</label>
  <textarea id="booking_instructions" placeholder="If catering, collect event date, headcount, location, callback number."></textarea>

  <div class="btns">
    <button onclick="loadPrompt()">Load Existing</button>
    <button onclick="generatePrompt()">Generate Prompt</button>
    <button onclick="savePrompt()">Save Prompt</button>
  </div>

  <label>Generated / Current Prompt</label>
  <textarea id="prompt"></textarea>

  <div id="status" class="small"></div>
  <pre id="debug" class="small"></pre>

<script>
  function status(msg, ok=true) {
    const el = document.getElementById('status');
    el.className = "small " + (ok ? "ok" : "err");
    el.textContent = msg;
  }

  function debug(obj) {
    document.getElementById('debug').textContent = JSON.stringify(obj, null, 2);
  }

  function getPayload() {
    return {
      phone_number: document.getElementById('phone').value.trim(),
      business_name: document.getElementById('business_name').value.trim(),
      business_type: document.getElementById('business_type').value.trim(),
      location: document.getElementById('location').value.trim(),
      services: document.getElementById('services').value.split(",").map(s => s.trim()).filter(Boolean),
      hours: document.getElementById('hours').value.trim(),
      tone: document.getElementById('tone').value.trim(),
      languages: document.getElementById('languages').value.split(",").map(s => s.trim()).filter(Boolean),
      booking_instructions: document.getElementById('booking_instructions').value.trim()
    };
  }

  async function loadPrompt() {
    try {
      const phone = document.getElementById('phone').value.trim();
      if (!phone) return status("Enter phone_number first", false);

      const res = await fetch(`/api/prompt/get?phone_number=${encodeURIComponent(phone)}`);
      const data = await res.json();
      debug(data);

      if (!res.ok) return status(data.detail || "Load failed", false);

      document.getElementById('prompt').value = data.prompt || "";
      status("Loaded prompt from DB ✅");
    } catch (e) {
      status("Load error: " + e.message, false);
    }
  }

  async function generatePrompt() {
    try {
      const payload = getPayload();
      if (!payload.phone_number) return status("Enter phone_number first", false);

      const res = await fetch("/api/prompt/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      debug(data);

      if (!res.ok) return status(data.detail || "Generate failed", false);

      // If your API returns {prompt: "..."} this works.
      // If it returns {generated_prompt: "..."} change the line below.
      document.getElementById('prompt').value = data.prompt || data.generated_prompt || "";
      status("Generated prompt ✅ (not saved yet)");
    } catch (e) {
      status("Generate error: " + e.message, false);
    }
  }

  async function savePrompt() {
    try {
      const phone = document.getElementById('phone').value.trim();
      const prompt = document.getElementById('prompt').value;

      if (!phone) return status("Enter phone_number first", false);
      if (!prompt) return status("Prompt is empty", false);

      const res = await fetch("/api/prompt/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: phone, prompt })
      });
      const data = await res.json();
      debug(data);

      if (!res.ok) return status(data.detail || "Save failed", false);

      status("Saved prompt to DB ✅");
    } catch (e) {
      status("Save error: " + e.message, false);
    }
  }
</script>

</body>
</html>
"""

