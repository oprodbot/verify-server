from flask import Flask, request, render_template_string
import json
import os
import bcrypt
from datetime import datetime, timedelta

app = Flask(__name__)
SOUBOR_TOKENU = "tokeny.json"
SOUBOR_RESETU = "resety.json"
SOUBOR_EMAIL_CHANGE = "email_change.json"


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


def zhashuj_heslo(plain):
    """Vrátí bcrypt hash jako string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


# ===== OVĚŘENÍ EMAILU =====

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


# ===== RESET HESLA (s bcrypt hashováním na serveru) =====

@app.route("/register-reset", methods=["POST"])
def register_reset():
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
        "hash": None,
        "vytvoreno": datetime.utcnow().isoformat(),
    }
    uloz_json(SOUBOR_RESETU, resety)
    return {"ok": True}


@app.route("/reset", methods=["GET", "POST"])
def reset():
    token = request.args.get("token", "")
    resety = nacti_json(SOUBOR_RESETU)

    if token not in resety:
        return render_template_string(
            STRANKA_CHYBA,
            sprava="Tento odkaz pro reset hesla je neplatný nebo expirovaný."
        ), 404

    # Token už byl použit – druhé kliknutí
    if resety[token]["hotovo"]:
        return render_template_string(
            STRANKA_CHYBA,
            sprava="This link has already been used. Please request a new reset link."
        ), 410

    if request.method == "POST":
        nove_heslo = request.form.get("heslo", "").strip()
        nove_heslo2 = request.form.get("heslo2", "").strip()

        if len(nove_heslo) < 4:
            return render_template_string(
                STRANKA_RESET_FORM, token=token, email=resety[token]["email"],
                chyba="Password must be at least 4 characters long."
            )
        if nove_heslo != nove_heslo2:
            return render_template_string(
                STRANKA_RESET_FORM, token=token, email=resety[token]["email"],
                chyba="Passwords do not match."
            )

        # Zhashuj heslo a ulož hash
        hash_str = zhashuj_heslo(nove_heslo)
        resety[token]["hotovo"] = True
        resety[token]["hash"] = hash_str
        resety[token]["dokonceno_kdy"] = datetime.utcnow().isoformat()
        uloz_json(SOUBOR_RESETU, resety)
        return render_template_string(STRANKA_RESET_HOTOVO, email=resety[token]["email"])

    return render_template_string(
        STRANKA_RESET_FORM, token=token, email=resety[token]["email"], chyba=None
    )


@app.route("/reset-status")
def reset_status():
    """Klient se ptá; po dokončení vrací hash (ne plaintext).
    Po 5 minutách od dokončení záznam vyčistíme."""
    token = request.args.get("token", "")
    resety = nacti_json(SOUBOR_RESETU)
    if token not in resety:
        return {"exists": False, "done": False}

    info = resety[token]

    # Cleanup: pokud je hotovo a uplynulo 5 min od dokončení, smaž
    if info.get("hotovo") and info.get("dokonceno_kdy"):
        dokonceno = datetime.fromisoformat(info["dokonceno_kdy"])
        if datetime.utcnow() - dokonceno > timedelta(minutes=5):
            del resety[token]
            uloz_json(SOUBOR_RESETU, resety)
            return {"exists": False, "done": False}

    return {
        "exists": True,
        "done": info["hotovo"],
        "email": info["email"],
        "new_password": info["hash"] if info["hotovo"] else None,
    }


# ===== ZMĚNA EMAILU (varianta C – dvojí potvrzení) =====

@app.route("/register-email-change", methods=["POST"])
def register_email_change():
    data = request.get_json()
    token_old = data.get("token_old")
    token_new = data.get("token_new")
    old_email = data.get("old_email")
    new_email = data.get("new_email")
    prezdivka = data.get("prezdivka", "")

    if not token_old or not token_new or not old_email or not new_email:
        return {"ok": False, "error": "missing data"}, 400

    zmeny = nacti_json(SOUBOR_EMAIL_CHANGE)
    zmeny = vycisti_stare(zmeny)

    spolecne_id = f"{token_old}::{token_new}"
    zmeny[spolecne_id] = {
        "token_old": token_old,
        "token_new": token_new,
        "old_email": old_email,
        "new_email": new_email,
        "prezdivka": prezdivka,
        "potvrzeno_stary": False,
        "potvrzeno_novy": False,
        "vytvoreno": datetime.utcnow().isoformat(),
    }
    uloz_json(SOUBOR_EMAIL_CHANGE, zmeny)
    return {"ok": True}


def _najdi_zmenu_podle_tokenu(zmeny, token, klic):
    for sid, info in zmeny.items():
        if info.get(klic) == token:
            return sid, info
    return None, None


@app.route("/confirm-email-old")
def confirm_email_old():
    token = request.args.get("token", "")
    zmeny = nacti_json(SOUBOR_EMAIL_CHANGE)
    sid, info = _najdi_zmenu_podle_tokenu(zmeny, token, "token_old")
    if not info:
        return render_template_string(STRANKA_CHYBA, sprava="Tento odkaz je neplatný nebo expirovaný."), 404

    if info["potvrzeno_stary"]:
        return render_template_string(
            STRANKA_EMAIL_OK,
            kdo="původní email",
            novy=info["new_email"],
            oba=info["potvrzeno_novy"]
        )

    info["potvrzeno_stary"] = True
    zmeny[sid] = info
    uloz_json(SOUBOR_EMAIL_CHANGE, zmeny)

    return render_template_string(
        STRANKA_EMAIL_OK,
        kdo="původní email",
        novy=info["new_email"],
        oba=info["potvrzeno_novy"]
    )


@app.route("/confirm-email-new")
def confirm_email_new():
    token = request.args.get("token", "")
    zmeny = nacti_json(SOUBOR_EMAIL_CHANGE)
    sid, info = _najdi_zmenu_podle_tokenu(zmeny, token, "token_new")
    if not info:
        return render_template_string(STRANKA_CHYBA, sprava="Tento odkaz je neplatný nebo expirovaný."), 404

    if info["potvrzeno_novy"]:
        return render_template_string(
            STRANKA_EMAIL_OK,
            kdo="nový email",
            novy=info["new_email"],
            oba=info["potvrzeno_stary"]
        )

    info["potvrzeno_novy"] = True
    zmeny[sid] = info
    uloz_json(SOUBOR_EMAIL_CHANGE, zmeny)

    return render_template_string(
        STRANKA_EMAIL_OK,
        kdo="nový email",
        novy=info["new_email"],
        oba=info["potvrzeno_stary"]
    )


@app.route("/email-change-status")
def email_change_status():
    token = request.args.get("token", "")
    zmeny = nacti_json(SOUBOR_EMAIL_CHANGE)
    sid, info = _najdi_zmenu_podle_tokenu(zmeny, token, "token_old")
    if not info:
        return {"exists": False, "done": False}
    return {
        "exists": True,
        "done": info["potvrzeno_stary"] and info["potvrzeno_novy"],
        "old_confirmed": info["potvrzeno_stary"],
        "new_confirmed": info["potvrzeno_novy"],
        "new_email": info["new_email"],
        "old_email": info["old_email"],
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
           box-shadow: 0 8px 32px rgba(0,0,0,0.08); text-align: center; max-width: 460px; }
  h1 { color: #c0392b; margin: 0 0 12px; font-size: 28px; }
  p { color: #666; margin: 0; }
  .x { font-size: 64px; margin-bottom: 16px; color: #c0392b; }
</style></head><body>
  <div class="karta">
    <div class="x">✗</div>
    <h1>Error</h1>
    <p>{{ sprava }}</p>
  </div>
</body></html>
"""

STRANKA_RESET_FORM = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Reset password</title>
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
    <h1>Set new password</h1>
    <p class="podtitulek">For account <span class="email">{{ email }}</span></p>
    <form method="POST" onsubmit="return validateForm()">
      <label>New password</label>
      <input type="password" id="heslo" name="heslo" required minlength="4" autofocus>
      <label>Repeat password</label>
      <input type="password" id="heslo2" name="heslo2" required minlength="4">
      {% if chyba %}<div class="chyba">{{ chyba }}</div>{% endif %}
      <button type="submit">Save new password</button>
    </form>
  </div>
  <script>
    function validateForm() {
      var h1 = document.getElementById("heslo").value;
      var h2 = document.getElementById("heslo2").value;
      if (h1.length < 4) {
        alert("Password must be at least 4 characters long.");
        return false;
      }
      if (h1 !== h2) {
        alert("Passwords do not match.");
        return false;
      }
      return true;
    }
  </script>
</body></html>
"""

STRANKA_RESET_HOTOVO = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Password changed</title>
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
    <h1>Password changed</h1>
    <p>You can close this tab and return to the app.</p>
    <p class="email">{{ email }}</p>
  </div>
</body></html>
"""

STRANKA_EMAIL_OK = """
<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><title>Změna emailu</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #faf6f1;
         display: flex; justify-content: center; align-items: center;
         height: 100vh; margin: 0; }
  .karta { background: white; padding: 48px 56px; border-radius: 16px;
           box-shadow: 0 8px 32px rgba(0,0,0,0.08); text-align: center; max-width: 460px; }
  h1 { color: #1a1a1a; margin: 0 0 12px; font-size: 26px; }
  p { color: #666; margin: 0 0 8px; font-size: 15px; line-height: 1.5; }
  .check { font-size: 64px; margin-bottom: 16px; }
  .email { color: #1a1a1a; font-weight: 600; }
  .hotovo { background: #e8f5e9; color: #2e7d32; padding: 12px;
            border-radius: 8px; margin-top: 16px; font-weight: 600; }
  .ceka { background: #fff8e1; color: #f57f17; padding: 12px;
          border-radius: 8px; margin-top: 16px; }
</style></head><body>
  <div class="karta">
    <div class="check">✓</div>
    <h1>Potvrzeno – {{ kdo }}</h1>
    <p>Děkujeme za potvrzení změny emailu na:</p>
    <p class="email">{{ novy }}</p>
    {% if oba %}
      <div class="hotovo">Oba emaily potvrzeny – změna se aplikuje v aplikaci.</div>
    {% else %}
      <div class="ceka">Čekáme ještě na potvrzení z druhého emailu.</div>
    {% endif %}
  </div>
</body></html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
