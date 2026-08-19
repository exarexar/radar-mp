#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aviso opcional por Telegram con el resultado del radar.

Necesita las variables de entorno TELEGRAM_TOKEN y TELEGRAM_CHAT.
Si no están, no hace nada y termina sin error.
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

token = os.environ.get("TELEGRAM_TOKEN", "").strip()
chat = os.environ.get("TELEGRAM_CHAT", "").strip()
if not token or not chat:
    print("Telegram no configurado; se omite el aviso.")
    sys.exit(0)

archivo = Path(__file__).resolve().parent / "data" / "latest.json"
if not archivo.exists():
    print("No hay data/latest.json; se omite el aviso.")
    sys.exit(0)

d = json.loads(archivo.read_text(encoding="utf-8"))
ops = d.get("oportunidades", [])
if not ops:
    print("Sin oportunidades hoy; se omite el aviso.")
    sys.exit(0)

lineas = [f"*Radar MP {d['fecha']}* — {len(ops)} oportunidades de desarrollo\n"]
for o in ops[:10]:
    cierre = o["cierre"][:16].replace("T", " ")
    lineas.append(f"• [{o['nombre'][:70]}]({o['url']})\n  cierra {cierre} · {o['organismo'][:45]}")
if len(ops) > 10:
    lineas.append(f"\n…y {len(ops) - 10} más en el informe.")

data = urlencode({
    "chat_id": chat,
    "text": "\n".join(lineas),
    "parse_mode": "Markdown",
    "disable_web_page_preview": "true",
}).encode()

with urlopen(Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)) as r:
    r.read()
print(f"Aviso enviado: {len(ops)} oportunidades.")
