from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

@router.get("/portal", response_class=HTMLResponse)
async def portal_home():
    return RedirectResponse("/portal/login", status_code=302)

@router.get("/portal/login", response_class=HTMLResponse)
async def portal_login_page():
    return """
<!doctype html>
<html>
<head><meta charset="utf-8"/><title>Customer Login</title></head>
<body style="font-family:Arial; max-width:520px; margin:60px auto;">
  <h1>Customer Login</h1>
  <form method="POST" action="/portal/login">
    <label>Email</label><br/>
    <input name="email" required style="width:100%;padding:10px;margin-top:6px;"/><br/><br/>
    <label>Password</label><br/>
    <input name="password" type="password" required style="width:100%;padding:10px;margin-top:6px;"/><br/><br/>
    <button style="width:100%;padding:12px;">Login</button>
  </form>
</body>
</html>
"""

@router.post("/portal/login")
async def portal_login_submit(email: str = Form(...), password: str = Form(...)):
    # TEMP: just redirect for now (we’ll hook real auth next)
    return HTMLResponse(f"<h3>Logged in (placeholder)</h3><p>{email}</p><p><a href='/portal'>Back</a></p>")

@router.get("/portal/dashboard", response_class=HTMLResponse)
async def portal_dashboard():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Customer Dashboard</title>
  <style>
    body { font-family: Arial; max-width: 900px; margin: 40px auto; }
    a { display:block; margin: 10px 0; font-size: 18px; }
  </style>
</head>
<body>

  <h1>Customer Dashboard</h1>

  <p>Welcome to your AI control panel.</p>

  <a href="/admin">Admin Prompt Builder</a>
  <a href="/docs">API Docs</a>
  <a href="/portal/logout">Logout</a>

</body>
</html>
"""
