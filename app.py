from flask import Flask, request, render_template_string
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
SOUBOR_TOKENU = "tokeny.json"


def nacti_tokeny():
    if not os.path.exists(SOUBOR_TOKENU):
        return {}
    try:
        with open(SOUBOR_TOKENU, "r") as f:
            return json.load(f)
    except:
        return {}


def uloz_tokeny(data):
    with open(SOUBOR_TOKENU, "w") as f:
        json.dump(data, f, indent=2)


def vycisti_stare(data):
    ted = datetime.utcnow()
    nove = {}
    for token, info in data.items():
        vytvoreno = datetime.fromisoformat(info["vytvoreno"])
        if ted - vytvoreno < timedelta(hours=24):
            nove[token] = info
    return nove


@app.route("/register-token", methods=["POST"])
def register_token():
    data = request.get_json()
    token = data.get("token")
    email = data.get("email")
    if not token or not email:
        return {"ok": False, "error": "missing token or email"}, 400
    tokeny = nacti_tokeny()
    tokeny = vycisti_stare(tokeny)
    tokeny[token] = {
        "email": email,
        "overeno": False,
        "vytvoreno": datetime.utcnow().isoformat(),
    }
    uloz_tokeny(tokeny)
    return {"ok": True}


@app.route("/verify")
def verify():
    token = request.args.get("token", "")
    tokeny = nacti_tokeny()
    if token not in tokeny:
        return render_template_string(STRANKA_CHYBA, sprava="Tento odkaz je neplatný nebo expirovaný."), 404
    if tokeny[token]["overeno"]:
        return render_template_string(STRANKA_OK, email=tokeny[token]["email"], jiz="(už dříve)")
    tokeny[token]["overeno"] = True
    tokeny[token]["overeno_kdy"] = datetime.utcnow().isoformat()
    uloz_tokeny(tokeny)
    return render_template_string(STRANKA_OK, email=tokeny[token]["email"], jiz="")


@app.route("/status")
def status():
    token = request.args.get("token", "")
    tokeny = nacti_tokeny()
    if token not in tokeny:
        return {"exists": False, "verified": False}
    return {
        "exists": True,
        "verified": tokeny[token]["overeno"],
        "email": tokeny[token]["email"],
    }


@app.route("/")
def home():
    return "<h1>Verify server běží.</h1>"


STRANKA_OK = """
<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Email ověřen</title>
  <style>
    body { font-family: -apple-system, sans-serif; background: #faf6f1;
           display: flex; justify-content: center; align-items: center;
           height: 100vh; margin: 0; }
    .karta { background: white; padding: 48px 56px; border-radius: 16px;
             box-shadow: 0 8px 32px rgba(0,0,0,0.08); text-align: center; max-width: 420px; }
    h1 { color: #1a1a1a; margin: 0 0 12px; font-size: 28px; }
    p { color: #666; margin: 0; font-size: 16px; }
    .check { font-size: 64px; margin-bottom: 16px; }
    .email { color: #1a1a1a; font-weight: 600; margin-top: 12px; }
  </style>
</head>
<body>
  <div class="karta">
    <div class="check">✓</div>
    <h1>Email ověřen {{ jiz }}</h1>
    <p>Tvůj účet je nyní aktivní.<br>Můžeš se vrátit do aplikace a přihlásit se.</p>
    <p class="email">{{ email }}</p>
  </div>
</body>
</html>
"""

STRANKA_CHYBA = """
<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Chyba</title>
  <style>
    body { font-family: -apple-system, sans-serif; background: #faf6f1;
           display: flex; justify-content: center; align-items: center;
           height: 100vh; margin: 0; }
    .karta { background: white; padding: 48px 56px; border-radius: 16px;
             box-shadow: 0 8px 32px rgba(0,0,0,0.08); text-align: center; max-width: 420px; }
    h1 { color: #c0392b; margin: 0 0 12px; font-size: 28px; }
    p { color: #666; margin: 0; }
    .x { font-size: 64px; margin-bottom: 16px; color: #c0392b; }
  </style>
</head>
<body>
  <div class="karta">
    <div class="x">✗</div>
    <h1>Chyba</h1>
    <p>{{ sprava }}</p>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
