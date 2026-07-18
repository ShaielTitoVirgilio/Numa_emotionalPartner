"""
Manda el mail de "Numa ya se puede descargar" a la lista de usuarios registrados
en la web, vía Brevo.

Uso:
    python scripts/send_download_announcement.py --test tu-mail@ejemplo.com
        -> manda SOLO a esa dirección, para revisar cómo queda antes de todo.

    python scripts/send_download_announcement.py --dry-run
        -> no manda nada, solo imprime a quién le mandaría y por qué salteo a alguien.

    python scripts/send_download_announcement.py --send
        -> manda de verdad a toda la lista (salteando los que ya estén en el log
           de enviados, para poder cortar y retomar sin duplicar envíos).

Requiere en .env: BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME.
"""

import argparse
import csv
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Numa")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = "/private/tmp/claude-501/-Users-mac-Numa-numa-mobile/0dfdbab9-e252-4b9c-afb4-328171b4b68c/scratchpad/emails_usuarios_web.csv"
SENT_LOG = os.path.join(SCRIPT_DIR, "_enviados_descarga_app.log")

TESTFLIGHT_URL = "https://testflight.apple.com/join/cj8M8f6Q"
GOOGLE_GROUP_URL = "https://groups.google.com/g/numa-beta"
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=app.numa.mobile"

SUBJECT = "Numa ya se puede descargar como app 🐼"


def render_html(nombre):
    saludo = f"Hola {nombre}," if nombre else "Hola,"
    return f"""
<div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width:560px; margin:0 auto; color:#2f4f45; font-size:17px;">
  <p style="font-size:44px; text-align:center; margin:0 0 8px;">🐼</p>
  <h1 style="font-size:28px; text-align:center; margin:0 0 24px;">¡Numa ya se puede descargar!</h1>

  <p style="font-size:17px; line-height:1.6;">{saludo}</p>
  <p style="font-size:17px; line-height:1.6;">
    Ya está lista la versión de prueba de la app de Numa para <strong>iOS</strong> y
    <strong>Android</strong>. Anda mucho más fluida que la web y tiene más funciones —
    y muy pronto <strong>la web va a dejar de funcionar</strong>, así que para seguir
    usando Numa vas a necesitar bajarte la app. ¡Ayudanos descargándola ya!
  </p>

  <div style="background:#eaf5f0; border:2px solid #7db89e; border-radius:12px; padding:20px 22px; margin:22px 0;">
    <p style="font-weight:800; margin:0 0 10px; font-size:18px;">iOS (TestFlight)</p>
    <ol style="padding-left:20px; margin:0 0 10px; line-height:2; font-size:16px; color:#3a6b5a;">
      <li>Descargá <strong>TestFlight</strong> desde la App Store</li>
      <li>Entrá a este link para sumarte y descargar Numa:<br>
        <a href="{TESTFLIGHT_URL}" style="color:#3a6b5a;">{TESTFLIGHT_URL}</a></li>
    </ol>
  </div>

  <div style="background:#eaf5f0; border:2px solid #7db89e; border-radius:12px; padding:20px 22px; margin:22px 0;">
    <p style="font-weight:800; margin:0 0 10px; font-size:18px;">Android</p>
    <ol style="padding-left:20px; margin:0 0 10px; line-height:2; font-size:16px; color:#3a6b5a;">
      <li>Unite al grupo de Google y tocá "Unirse al grupo":<br>
        <a href="{GOOGLE_GROUP_URL}" style="color:#3a6b5a;">{GOOGLE_GROUP_URL}</a></li>
      <li>Una vez adentro, entrá a la Play Store con el mismo link que aparece en el
        grupo (o con este):<br>
        <a href="{PLAY_STORE_URL}" style="color:#3a6b5a;">{PLAY_STORE_URL}</a></li>
    </ol>
    <p style="font-size:15px; color:#6b8e7d; margin:0; line-height:1.5;">
      A veces demora un poco en sincronizar que ya estás en el grupo y no te deja
      instalar al instante — si pasa eso, esperá unos minutos y probá de nuevo.
    </p>
  </div>

  <p style="font-size:16px; line-height:1.6;">Gracias por estar de este lado desde el principio 🐼</p>
</div>
""".strip()


def cargar_destinatarios(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cargar_ya_enviados():
    if not os.path.exists(SENT_LOG):
        return set()
    with open(SENT_LOG, encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def marcar_enviado(email):
    with open(SENT_LOG, "a", encoding="utf-8") as f:
        f.write(email + "\n")


def enviar(email, nombre):
    resp = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "to": [{"email": email, "name": nombre or email}],
            "subject": SUBJECT,
            "htmlContent": render_html(nombre),
        },
        timeout=15,
    )
    return resp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path al CSV de email,nombre,fecha_registro")
    parser.add_argument("--test", metavar="EMAIL", help="Manda solo un mail de prueba a esta dirección")
    parser.add_argument("--dry-run", action="store_true", help="No manda nada, solo simula")
    parser.add_argument("--send", action="store_true", help="Manda de verdad a toda la lista")
    parser.add_argument("--delay", type=float, default=0.4, help="Segundos de espera entre envíos")
    args = parser.parse_args()

    if not BREVO_API_KEY or not SENDER_EMAIL:
        sys.exit("Falta BREVO_API_KEY y/o BREVO_SENDER_EMAIL en el .env")

    if args.test:
        resp = enviar(args.test, "")
        print(resp.status_code, resp.text)
        return

    if not args.dry_run and not args.send:
        sys.exit("Elegí --test <email>, --dry-run, o --send")

    destinatarios = cargar_destinatarios(args.csv)
    ya_enviados = cargar_ya_enviados()

    print(f"Total en el CSV: {len(destinatarios)} — ya enviados antes: {len(ya_enviados)}")

    for row in destinatarios:
        email = row["email"].strip()
        nombre = row.get("nombre", "").strip()

        if email in ya_enviados:
            print(f"[salteado, ya enviado] {email}")
            continue

        if args.dry_run:
            print(f"[dry-run] mandaría a {email} ({nombre or 'sin nombre'})")
            continue

        resp = enviar(email, nombre)
        if resp.status_code in (200, 201):
            print(f"[OK] {email}")
            marcar_enviado(email)
        else:
            print(f"[ERROR {resp.status_code}] {email} -> {resp.text}")

        time.sleep(args.delay)


if __name__ == "__main__":
    main()
