#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueba del radar con datos simulados (no llama a la API real)."""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radar  # noqa: E402


# ---------- 1. días hábiles ----------
FER = {"2026-08-15", "2026-09-18", "2026-09-19"}

casos = [
    (date(2026, 8, 17), 2, date(2026, 8, 19)),   # lun -> mié
    (date(2026, 8, 20), 2, date(2026, 8, 24)),   # jue -> lun (salta fin de semana)
    (date(2026, 8, 21), 2, date(2026, 8, 25)),   # vie -> mar
    (date(2026, 9, 16), 2, date(2026, 9, 21)),   # mié -> lun (salta 18 y 19 feriados)
    (date(2026, 8, 14), 1, date(2026, 8, 17)),   # vie, 15 feriado sábado -> lun
]
for inicio, n, esperado in casos:
    got = radar.dias_habiles_adelante(inicio, n, FER)
    assert got == esperado, f"días hábiles: {inicio}+{n} dio {got}, esperaba {esperado}"
print("OK  cálculo de días hábiles (5 casos, incluye feriados y fines de semana)")

assert radar.habiles_entre(date(2026, 8, 17), date(2026, 8, 17), FER) == 0
assert radar.habiles_entre(date(2026, 8, 17), date(2026, 8, 19), FER) == 2
assert radar.habiles_entre(date(2026, 9, 17), date(2026, 9, 21), FER) == 1
print("OK  hábiles restantes")

# ---------- 2. parseo de fechas ----------
for s in ["2026-08-19T15:00:00", "2026-08-19T15:00:00.000", "2026-08-19 15:00:00",
          "2026-08-19"]:
    assert radar.parse_fecha(s) is not None, s
assert radar.parse_fecha(None) is None
assert radar.parse_fecha("basura") is None
print("OK  parseo de fechas")

# ---------- 3. puntaje ----------
def lic(nombre, desc="", cod="81111504", item=""):
    return {"Nombre": nombre, "Descripcion": desc,
            "Items": {"Listado": [{"CodigoProducto": cod, "NombreProducto": item,
                                   "Descripcion": ""}]}}

pruebas = [
    ("Desarrollo de plataforma web de gestión municipal", "", "81111504", "", True),
    ("Servicio de desarrollo de software a medida para RRHH", "", "81111501", "", True),
    ("Contratación analista programador para mantención de sistema", "", "81111500", "", True),
    ("Adquisición de tóner e insumos computacionales", "", "44103103", "tóner", False),
    ("Compra de notebooks y monitores para funcionarios", "", "43211503", "notebook", False),
    ("Servicio de aseo integral edificio consistorial", "", "76111501", "", False),
    ("Cableado estructurado y cámaras de seguridad CCTV", "", "43222600", "cctv", False),
    ("Renovación licencias Microsoft Office 365", "", "43230000", "licencias microsoft", False),
]
fallos = 0
for nombre, desc, cod, item, esperado_ok in pruebas:
    pts, raz = radar.puntuar(lic(nombre, desc, cod, item), amplio=False)
    ok = pts >= radar.UMBRAL
    marca = "✓" if ok == esperado_ok else "✗ FALLA"
    if ok != esperado_ok:
        fallos += 1
    print(f"    {marca} [{pts:>4}] {nombre[:58]}")
assert fallos == 0, f"{fallos} casos de clasificación fallaron"
print("OK  clasificación desarrollo vs. ruido (8 casos)")

# ---------- 4. informe HTML de punta a punta ----------
hoy = date(2026, 8, 17)
def op(nombre, org, horas, pts, monto):
    cierre = datetime(2026, 8, 17, 9) + timedelta(hours=horas)
    return {"codigo": "1509-12-LE26", "nombre": nombre, "organismo": org,
            "unidad": "", "tipo": "LE", "cierre": cierre.isoformat(),
            "habiles_restantes": radar.habiles_entre(hoy, cierre.date(), FER),
            "monto": monto, "puntaje": pts,
            "razones": ["rubro ONU 81111504", "«desarrollo de software» en el título"],
            "url": radar.ficha_url("1509-12-LE26"), "descripcion": ""}

res = {
    "generado": "2026-08-17 08:30", "fecha": "2026-08-17",
    "ventana_dias_habiles": 2, "ventana_hasta": "2026-08-19",
    "modo": "solo desarrollo",
    "resumen": {"activas_revisadas": 1842, "detalles_consultados": 96,
                "oportunidades": 3, "cierran_hoy": 1, "cierran_manana": 1,
                "llamadas_api": 97},
    "oportunidades": [
        op("Desarrollo de plataforma web de trámites en línea", "I. Municipalidad de Ñuñoa", 6, 34, "28.000.000 CLP"),
        op("Servicio de desarrollo y mantención de sistema de gestión escolar", "Servicio Local de Educación Pública", 30, 41, "no informado"),
        op("Implementación de sistema informático de inventario", "Hospital Regional de Talca", 52, 22, "12.500.000 CLP"),
    ],
}
out = Path(__file__).parent / "data" / "informe_demo.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(radar.html(res), encoding="utf-8")
assert "Radar Mercado Público" in out.read_text(encoding="utf-8")
assert "plataforma web de trámites" in out.read_text(encoding="utf-8")
print(f"OK  informe HTML generado ({out.stat().st_size} bytes) -> {out}")

# informe vacío
vacio = dict(res, oportunidades=[], resumen=dict(res["resumen"], oportunidades=0,
                                                 cierran_hoy=0, cierran_manana=0))
assert "Nada que hacer hoy" in radar.html(vacio)
print("OK  informe HTML sin resultados")

print("\nTodas las pruebas pasaron.")
