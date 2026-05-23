from flask import Flask, request, render_template_string
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
SOUBOR_TOKENU = "tokeny.json"
SOUBOR_RESETU = "resety.json"


def nacti_json(soubor):
    if not os.path.exists(soubor):
        return {}
    try:
        with open(soubor, "r") as f:
            return json.load(f)
    except:
        return {}


def uloz_json(soubor, data):
    with open(soubor, "w") as f:
        json.dump(data, f, indent=2)


def vycisti_stare(data):
    ted = datetime.utcnow()
    nove = {}
    for token, info in data.items():
        vytvoreno = datetime.fromisoformat(info["vytvoreno"])
        if ted - vytvoreno < timedelta(hours=24):
            nove[token] = info
    return nove


# ===== OVĚŘENÍ EMAILU (původní) =====

@app.route("/register-token", methods=["POST"])
def register_token():
    data = request.get_json()
    token = data.get("token")
    email = data.get("email")
    if not token or not email:
        return {"ok": False, "error": "missing token or email"}, 400
    tokeny = nacti_json(SOUBOR_TOKENU)
    tokeny = vycisti_stare(tokeny)
    tokeny[token] = {
        "email": email,
        "overeno": False,
        "vytvoreno": datetime.utcnow().isoformat(),
    }
    uloz_json(SOUBOR_TOKENU, tokeny)
    return {"ok": True}


@app.route("/verify")
def verify():
    token = request.args.get("token", "")
    tokeny = nacti_json(SOUBOR_TOKENU)
    if token not in tokeny:
        return render_template_string(STRANKA_CHYBA, sprava="Tento odkaz je neplatný nebo expirovaný."), 404
    if tokeny[token]["overeno"]:
        return render_template_string(STRANKA_OK, email=tokeny[token]["email"], jiz="(už dříve)")
    tokeny[token]["overeno"] = True
    tokeny[token]["overeno_kdy"] = datetime.utcnow().isoformat()
    uloz_json(SOUBOR_TOKENU, tokeny)
    return render_template_string(STRANKA_OK, email=tokeny[token]["email"], jiz="")


@app.route("/status")
def status():
    token = request.args.get("token", "")
    tokeny = nacti_json(SOUBOR_TOKENU)
    if token not in tokeny:
        return {"exists": False, "verified": False}
    return {
        "exists": True,
        "verified": tokeny[token]["overeno"],
        "email": tokeny[token]["email"],
    }


# ===== RESET HESLA (nové) =====

@app.route("/register-reset", methods=["POST"])
def register_reset():
    """Appka pošle: { 'token': '...', 'email': '...' }"""
    data = request.get_json()
    token = data.get("token")
    email = data.get("email")
    if not token or not email:
        return {"ok": False, "error": "missing token or email"}, 400
    resety = nacti_json(SOUBOR_RESETU)
    resety = vycisti_stare(resety)
    resety[token] = {
        "email": email,
        "hotovo": False,
        "nove_heslo": None,
        "vytvoreno": datetime.utcnow().isoformat(),
    }
    uloz_json(SOUBOR_RESETU, resety)
    return {"ok": True}


@app.route("/reset", methods=["GET", "POST"])
def reset():
    """Uživatel sem klikne z mailu (GET = formulář, POST = uložení)."""
    token = request.args.get("token", "")
    resety = nacti_json(SOUBOR_RESETU)

    if token not in resety:
        return render_template_string(STRANKA_CHYBA, sprava="Tento odkaz pro reset hesla je neplatný nebo expirovaný."), 404

    if resety[token]["hotovo"]:
        return render_template_string(STRANKA_RESET_HOTOVO, email=resety[token]["email"])

    if request.method == "POST":
        nove_heslo = request.form.get("heslo", "").strip()
        nove_heslo2 = request.form.get("heslo2", "").strip()

        if len(nove_heslo) < 4:
            return render_template_string(
                STRANKA_RESET_FORM, token=token, email=resety[token]["email"],
                chyba="Heslo musí mít aspoň 4 znaky."
            )
        if nove_heslo != nove_heslo2:
            return render_template_string(
                STRANKA_RESET_FORM, token=token, email=resety[token]["email"],
                chyba="Hesla se neshodují."
            )

        resety[token]["hotovo"] = True
        resety[token]["nove_heslo"] = nove_heslo
        resety[token]["dokonceno_kdy"] = datetime.utcnow().isoformat()
        uloz_json(SOUBOR_RESETU, resety)
        return render_template_string(STRANKA_RESET_HOTOVO, email=resety[token]["email"])

    return render_template_string(
        STRANKA_RESET_FORM, token=token, email=resety[token]["email"], chyba=None
    )


@app.route("/reset-status")
def reset_status():
    """Appka se ptá, jestli je reset hotový + dostane nové heslo."""
    token = request.args.get("token", "")
    resety = nacti_json(SOUBOR_RESETU)
    if token not in resety:
        return {"exists": False, "done": False}
    return {
        "exists": True,
        "done": resety[token]["hotovo"],
        "email": resety[token]["email"],
        "new_password": resety[token]["nove_heslo"] if resety[token]["hotovo"] else None,
    }


@app.route("/")
def home():
    return "<h1>Verify server běží.</h1>"


# ===== HTML šablony =====

STRANKA_OK = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Email ověřen</title>
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
</style></head><body>
  <div class="karta">
    <div class="check">✓</div>
    <h1>Email ověřen {{ jiz }}</h1>
    <p>Tvůj účet je nyní aktivní.<br>Můžeš se vrátit do aplikace a přihlásit se.</p>
    <p class="email">{{ email }}</p>
  </div>
</body></html>
"""

STRANKA_CHYBA = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Chyba</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #faf6f1;
         display: flex; justify-content: center; align-items: center;
         height: 100vh; margin: 0; }
  .karta { background: white; padding: 48px 56px; border-radius: 16px;
           box-shadow: 0 8px 32px rgba(0,0,0,0.08); text-align: center; max-width: 420px; }
  h1 { color: #c0392b; margin: 0 0 12px; font-size: 28px; }
  p { color: #666; margin: 0; }
  .x { font-size: 64px; margin-bottom: 16px; color: #c0392b; }
</style></head><body>
  <div class="karta">
    <div class="x">✗</div>
    <h1>Chyba</h1>
    <p>{{ sprava }}</p>
  </div>
</body></html>
"""

STRANKA_RESET_FORM = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Reset hesla</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #faf6f1;
         display: flex; justify-content: center; align-items: center;
         height: 100vh; margin: 0; }
  .karta { background: white; padding: 48px 56px; border-radius: 16px;
           box-shadow: 0 8px 32px rgba(0,0,0,0.08); max-width: 420px; width: 90%; }
  h1 { color: #1a1a1a; margin: 0 0 8px; font-size: 28px; }
  p.podtitulek { color: #888; margin: 0 0 24px; font-size: 14px; }
  .email { color: #1a1a1a; font-weight: 600; }
  label { display: block; color: #666; margin: 14px 0 6px; font-size: 13px; }
  input[type=password] { width: 100%; padding: 12px 14px; border: 1px solid #ddd;
                          border-radius: 8px; font-size: 16px; box-sizing: border-box;
                          outline: none; }
  input[type=password]:focus { border-color: #1a1a1a; }
  button { width: 100%; background: #1a1a1a; color: white; border: 0;
           padding: 14px; border-radius: 8px; font-size: 16px; font-weight: 600;
           margin-top: 22px; cursor: pointer; }
  button:hover { background: #333; }
  .chyba { background: #fee; color: #c0392b; padding: 10px 14px; border-radius: 8px;
           margin-top: 14px; font-size: 14px; }
</style></head><body>
  <div class="karta">
    <h1>Nastav nové heslo</h1>
    <p class="podtitulek">Pro účet <span class="email">{{ email }}</span></p>
    <form method="POST">
      <label>Nové heslo</label>
      <input type="password" name="heslo" required minlength="4" autofocus>
      <label>Heslo znovu</label>
      <input type="password" name="heslo2" required minlength="4">
      {% if chyba %}<div class="chyba">{{ chyba }}</div>{% endif %}
      <button type="submit">Uložit nové heslo</button>
    </form>
  </div>
</body></html>
"""

STRANKA_RESET_HOTOVO = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Heslo změněno</title>
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
</style></head><body>
  <div class="karta">
    <div class="check">✓</div>
    <h1>Heslo změněno</h1>
    <p>Tvé nové heslo bylo uloženo.<br>Vrať se do aplikace a přihlas se.</p>
    <p class="email">{{ email }}</p>
  </div>
</body></html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
