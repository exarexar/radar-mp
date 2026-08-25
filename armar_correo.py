#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Arma el correo diario a partir de data/latest.json.

Escribe correo.html y deja el asunto en la variable ASUNTO del workflow.
Si no hay nada que informar, no escribe el archivo y el workflow salta el envío:
más vale no mandar correo que mandar uno vacío todos los días.
"""

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
datos = RAIZ / "data" / "latest.json"

if not datos.exists():
    print("No hay data/latest.json; no se envía correo.")
    sys.exit(0)

d = json.loads(datos.read_text(encoding="utf-8"))
nuevas = d.get("nuevas", [])
cerrando = d.get("por_cerrar", [])

if not nuevas and not cerrando:
    print("Sin novedades; no se envía correo.")
    sys.exit(0)

ICONO = {"roja": "🚩", "amarilla": "⚠️", "verde": "✅", "sin_monto": "❓"}
COLOR = {"roja": "#b4351f", "amarilla": "#a86718", "verde": "#3f6f5c",
         "sin_monto": "#6b6560"}


SELLO = {"go": ("GO", "#3f6f5c"), "revisar": ("REVISAR", "#a86718"),
         "nogo": ("NO GO", "#b4351f")}


def bloque(r):
    p = r.get("precio") or {}
    nivel = p.get("nivel", "sin_monto")
    plazo = ("cierra hoy" if r["habiles_restantes"] <= 0
             else "cierra mañana" if r["habiles_restantes"] == 1
             else f"{r['habiles_restantes']} días hábiles")
    v = r.get("veredicto")
    sello = ""
    if v in SELLO:
        txt, col = SELLO[v]
        sello = (f'<span style="font-size:10.5px;font-weight:700;letter-spacing:.06em;'
                 f'color:{col};border:1px solid {col};border-radius:4px;padding:1px 6px;'
                 f'margin-right:6px">{txt}</span>')
    return f"""
  <tr><td style="padding:16px 0;border-bottom:1px solid #e6e2dd">
    <div style="font-size:15px;font-weight:600;line-height:1.4">
      {sello}<a href="{r['url']}" style="color:#1c1a17;text-decoration:none">{r['nombre']}</a>
    </div>
    <div style="font-size:13px;color:#6b6560;margin-top:4px">
      {r['organismo']} &middot; {r['monto']} &middot; <b>{plazo}</b>
      &middot; código <code>{r['codigo']}</code>
    </div>
    <div style="font-size:13px;color:{COLOR[nivel]};margin-top:7px;font-weight:600">
      {ICONO[nivel]} {p.get('etiqueta','')}
    </div>
    <div style="font-size:13px;color:#4a4540;margin-top:3px">{p.get('detalle','')}</div>
  </td></tr>"""


# Mismo orden que el informe HTML: lo accionable, lo urgente, lo descartado.
vale = [r for r in nuevas if r.get("veredicto") != "nogo"]
nogo = [r for r in nuevas if r.get("veredicto") == "nogo"]


def seccion(titulo, lista, apagada=False):
    if not lista:
        return ""
    op = ' style="opacity:.65"' if apagada else ""
    return (f'<h2 style="font-size:16px;margin:26px 0 4px">{titulo} ({len(lista)})</h2>'
            f'<table width="100%" cellpadding="0" cellspacing="0"{op}>'
            f'{"".join(bloque(r) for r in lista)}</table>')


secciones = (seccion("Vale la pena", vale)
             + seccion("Cierran pronto", cerrando)
             + seccion("Descartadas — el presupuesto no calza", nogo, apagada=True))

html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
 max-width:660px;margin:0 auto;padding:20px;color:#1c1a17">
<h1 style="font-size:19px;margin:0 0 4px">Radar Mercado Público — {d['fecha']}</h1>
<p style="font-size:13.5px;color:#6b6560;margin:0 0 18px">
 {len(vale)} oportunidades que vale la pena mirar y {len(cerrando)} por cerrar,
 de {d['resumen']['activas_revisadas']:,} licitaciones activas revisadas.
 {len(nogo)} quedaron descartadas por presupuesto.
</p>
{secciones}
<p style="font-size:12px;color:#6b6560;margin-top:26px;border-top:1px solid #e6e2dd;
 padding-top:14px">
 🚩 marca licitaciones cuyo presupuesto no calza con el trabajo que piden.
 El informe completo va adjunto. Si un enlace pide iniciar sesión, busca el código
 en buscador.mercadopublico.cl.
</p></div>""".replace(",", ".")

(RAIZ / "correo.html").write_text(html, encoding="utf-8")

asunto = f"Radar MP {d['fecha']}: {len(vale)} oportunidades"
if cerrando:
    asunto += f", {len(cerrando)} por cerrar"
if os.environ.get("GITHUB_ENV"):
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as fh:
        fh.write(f"ASUNTO={asunto}\n")
print(f"Correo listo: {asunto}")
