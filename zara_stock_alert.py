"""
Alerta de stock de Zara -> email
--------------------------------
Revisa cada X minutos si una talla concreta de un producto de Zara está disponible
y, si lo está, envía un correo (una sola vez por talla hasta que vuelva a agotarse).

Requisitos:
    pip install requests

Configuración por variables de entorno (para no dejar contraseñas en el código):
    ZARA_EMAIL_FROM      -> tu Gmail, p.ej. marta@gmail.com
    ZARA_EMAIL_PASSWORD  -> contraseña de aplicación de Gmail (16 caracteres)
    ZARA_EMAIL_TO        -> destinatario (puede ser el mismo)

Uso:
    python zara_stock_alert.py          # bucle infinito, revisa cada INTERVALO_MIN
    python zara_stock_alert.py --once   # una sola comprobación (para el Programador de tareas)
"""

import json
import os
import random
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path

import requests

# ====================== CONFIGURACIÓN ======================
PRODUCT_URL = "https://www.zara.com/es/es/jersey-con-lana-y-alpaca-p09598251.html?v1=600958753&v2=2419844"
TALLAS = ["M"]            # tallas que te interesan, tal como aparecen en la web. [] = cualquiera
INTERVALO_MIN = 10        # minutos entre comprobaciones (no bajes de 5)
ESTADOS_DISPONIBLES = {"in_stock", "low_on_stock"}

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
EMAIL_FROM = os.environ.get("ZARA_EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("ZARA_EMAIL_PASSWORD")
EMAIL_TO = os.environ.get("ZARA_EMAIL_TO", EMAIL_FROM)

STATE_FILE = Path(__file__).with_name("zara_state.json")
# ===========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9",
}


def obtener_json(url: str) -> dict:
    """Zara devuelve los datos del producto en JSON si añades ajax=true a la URL."""
    sep = "&" if "?" in url else "?"
    r = requests.get(f"{url}{sep}ajax=true", headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def buscar_tallas(nodo, encontradas=None) -> dict:
    """Recorre el JSON buscando listas 'sizes' con 'name' y 'availability'.
    Se hace recursivo porque Zara cambia la estructura de vez en cuando."""
    if encontradas is None:
        encontradas = {}
    if isinstance(nodo, dict):
        sizes = nodo.get("sizes")
        if isinstance(sizes, list):
            for s in sizes:
                if isinstance(s, dict) and "name" in s and "availability" in s:
                    encontradas[str(s["name"]).strip()] = s["availability"]
        for v in nodo.values():
            buscar_tallas(v, encontradas)
    elif isinstance(nodo, list):
        for v in nodo:
            buscar_tallas(v, encontradas)
    return encontradas


def nombre_producto(data: dict) -> str:
    try:
        return data["product"]["name"]
    except (KeyError, TypeError):
        return "Producto de Zara"


def enviar_email(asunto: str, cuerpo: str) -> None:
    if not (EMAIL_FROM and EMAIL_PASSWORD and EMAIL_TO):
        raise RuntimeError("Faltan las variables de entorno del email.")
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.set_content(cuerpo)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
        smtp.send_message(msg)


def cargar_estado() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar_estado(estado: dict) -> None:
    STATE_FILE.write_text(json.dumps(estado, indent=2), encoding="utf-8")


def comprobar() -> None:
    data = obtener_json(PRODUCT_URL)
    tallas = buscar_tallas(data)
    if not tallas:
        print("⚠️  No encontré tallas en la respuesta. Puede que Zara haya cambiado el formato.")
        return

    objetivo = {t: a for t, a in tallas.items() if not TALLAS or t in TALLAS}
    print(time.strftime("%H:%M:%S"), objetivo)

    estado = cargar_estado()
    nuevas = []
    for talla, disp in objetivo.items():
        disponible = disp in ESTADOS_DISPONIBLES
        if disponible and not estado.get(talla):
            nuevas.append(talla)
        estado[talla] = disponible  # si se agota otra vez, volverá a avisar
    guardar_estado(estado)

    if nuevas:
        nombre = nombre_producto(data)
        enviar_email(
            f"🛍️ ¡Disponible en Zara! {nombre} – talla {', '.join(nuevas)}",
            f"{nombre}\nTallas disponibles: {', '.join(nuevas)}\n\nCómpralo aquí:\n{PRODUCT_URL}",
        )
        print("📧 Email enviado:", nuevas)


def main() -> None:
    if "--once" in sys.argv:
        comprobar()
        return
    while True:
        try:
            comprobar()
        except Exception as e:  # que un fallo puntual no tumbe el bucle
            print("Error:", e)
        # un poco de aleatoriedad para no hacer peticiones exactamente periódicas
        time.sleep(INTERVALO_MIN * 60 + random.randint(0, 60))


if __name__ == "__main__":
    main()
