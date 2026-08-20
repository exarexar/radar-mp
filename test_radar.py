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

# ---------- 3b. regresión con datos REALES del 19-08-2026 ----------
# Estas 12 son exactamente lo que el bot reportó en producción ese día. Ocho eran
# basura que entró porque «ui» calzaba dentro de «adquisición». Sirven de ancla:
# si una futura edición de los pesos las deja pasar de nuevo, esta prueba falla.
REALES = [
    # (título, código ONU del ítem, ¿es desarrollo de software?)
    ("CONTRATACIÓN DE SISTEMA INFORMÁTICO PARA LA EMISIÓN DE LICENCIAS MÉDICAS", "81111500", True),
    ("CONTRATACION PLATAFORMA DE GESTION DIGITAL PARA ESTABLECIMIENTOS EDUCACIONALES", "81111500", True),
    ("SISTEMA DE GESTIÓN DOCUMENTAL Y COMPLEMENTOS", "81111500", True),
    ("ADQ. SOPORTE Y MANTENCION DE SOFTWARE XRY LABOCAR", "81112200", True),
    ("ADQUISICION DE LICENCIA VMWARE POR 12 MESES", "43233200", False),
    ("“ADQUISICIÓN DEL SERVICIO DE COFFEE BREAK SALUDABLE PARA ACTIVIDADES COMUNITARIAS", "90101600", False),
    ("Renovació de Licencia y almacenamiento en la nube sistema U+ ETA", "43233200", False),
    ("ADQ. INST. Y MANT. DE EQUIPOS AIRE ACONDICIONADO", "40101700", False),
    ("SUSCRIPCIÓN DE LICENCIAS DE SOFTWARE DE DISEÑO ASISTIDO POR COMPUTADOR CAD", "43232100", False),
    ("PTR N°431. COMPRA DE SOFTWARE DE SOPORTE REMOTO TEAMVIEWER CORPORATE.", "43233200", False),
    ("Adquisición Medicamentos Salud Sexual S.S.Coquimbo", "51101500", False),
    ("RENOV. DE LICENCIAS SOFTWARE PARA LA OF. REVISTA", "43233200", False),
]
fallos_reales, falsos_pos, falsos_neg = 0, 0, 0
for titulo, cod, es_dev in REALES:
    pts, _ = radar.puntuar(lic(titulo, "", cod), amplio=False)
    pasa = pts >= radar.UMBRAL
    ok = pasa == es_dev
    if not ok:
        fallos_reales += 1
        falsos_pos += pasa
        falsos_neg += es_dev
    print(f"    {'✓' if ok else '✗ FALLA'} [{pts:>4}] {'DEV ' if es_dev else 'ruido'} {titulo[:56]}")
assert fallos_reales == 0, (f"{fallos_reales} fallos con datos reales "
                            f"({falsos_pos} falsos positivos, {falsos_neg} perdidas)")
print(f"OK  regresión con los 12 resultados reales del 19-08-2026 "
      f"(4 desarrollo, 8 ruido, 0 errores)")

# ---------- 3c. corpus real: las 22 del 19-08-2026 en producción ----------
fx = json.loads((Path(__file__).parent / "fixtures" / "reales-2026-08-19.json")
                .read_text(encoding="utf-8"))
fp, fn, detalle = [], [], []
for c in fx["casos"]:
    det = {"Nombre": c["nombre"], "Descripcion": c["descripcion"],
           "Items": {"Listado": [{"CodigoProducto": o, "NombreProducto": "",
                                  "Descripcion": ""} for o in c["onu"]]}}
    pts, _ = radar.puntuar(det, amplio=False)
    pasa, debe = pts >= radar.UMBRAL, c["es_desarrollo"]
    if pasa and not debe:
        fp.append((c["nombre"][:50], pts, c["nota"]))
    if debe and not pasa:
        fn.append((c["nombre"][:50], pts))
    detalle.append((debe, pts, pasa, c["nombre"][:56]))

for debe, pts, pasa, n in sorted(detalle, key=lambda r: -r[1]):
    marca = ("✓" if pasa else "·") if debe else ("✗" if pasa else "✓")
    print(f"    {marca} [{pts:>4}] {'DEV  ' if debe else 'ruido'} {n}")

# Tolerancia: los casos límite documentados pueden fallar, el resto no.
LIMITE = {"escanear fichas en papel, no desarrollo (caso límite)"}
fp_graves = [f for f in fp if f[2] not in LIMITE]
assert not fp_graves, f"falsos positivos no tolerados: {fp_graves}"
assert len(fp) <= 1, f"demasiados falsos positivos: {fp}"
assert len(fn) <= 1, f"se están perdiendo licitaciones reales: {fn}"
print(f"OK  corpus real de {len(fx['casos'])} licitaciones del {fx['fecha']}: "
      f"{len(fp)} falso positivo, {len(fn)} perdida "
      f"(de {fx['activas_ese_dia']} activas ese día)")

# El bug del doble conteo por tildes no puede volver.
assert len(radar.CLAVES_FUERTES) == len({radar.normaliza(k) for k in radar.CLAVES_FUERTES})
assert len(radar.CLAVES_RUIDO) == len({radar.normaliza(k) for k in radar.CLAVES_RUIDO})
_r = radar.puntuar(lic("Servicio de programación de sistemas"), amplio=False)[1]
assert len([x for x in _r if "programacion" in x]) == 1, \
    "«programación» y «programacion» no pueden sumar dos veces"
print("OK  sin doble conteo entre variantes con y sin tilde")

# El bug original, aislado: «ui» dentro de «adquisición» no puede puntuar.
assert not radar.contiene(radar.normaliza("Adquisición de camionetas"), "ui"), \
    "«ui» no puede calzar dentro de «adquisición»"
assert radar.contiene(radar.normaliza("Servicios de diseño UX y UI"), "ui"), \
    "«ui» sí debe calzar cuando es palabra suelta"
assert not radar.contiene(radar.normaliza("reprogramar la entrega"), "programacion")
assert radar.contiene(radar.normaliza("servicio de PROGRAMACIÓN web"), "programacion")
print("OK  las palabras clave calzan como palabra completa, no como trozo")

# ---------- 4. clasificación: nuevas / por cerrar ----------
HORIZONTE, RECORDAR, MINIMO = 20, 2, 0

def clasifica(restantes, ya_visto):
    """Réplica de la decisión que toma main() para cada licitación."""
    if not ya_visto and restantes >= MINIMO:
        return "nuevas"
    if ya_visto and restantes <= RECORDAR:
        return "por_cerrar"
    return "descartada"

casos_cls = [
    (20, False, "nuevas",     "aparece con el máximo de anticipación"),
    (14, False, "nuevas",     "licitación típica, se detecta apenas se publica"),
    (6,  False, "nuevas",     "publicada con poco aviso, igual se reporta"),
    (0,  False, "nuevas",     "cierra hoy y recién aparece: hay que avisar igual"),
    (14, True,  "descartada", "ya reportada y con plazo: no repetir"),
    (6,  True,  "descartada", "ya reportada, sigue con plazo"),
    (3,  True,  "descartada", "ya reportada, todavía fuera del recordatorio"),
    (2,  True,  "por_cerrar", "recordatorio: entra en la ventana de cierre"),
    (0,  True,  "por_cerrar", "recordatorio: cierra hoy"),
]
for restantes, visto, esperado, motivo in casos_cls:
    got = clasifica(restantes, visto)
    assert got == esperado, f"{restantes}d visto={visto}: dio {got}, esperaba {esperado} ({motivo})"
print(f"OK  clasificación con horizonte de {HORIZONTE} días hábiles ({len(casos_cls)} casos)")

# Nadie puede caer en las dos listas, y nada nuevo puede perderse.
for restantes in range(0, HORIZONTE + 1):
    assert clasifica(restantes, False) == "nuevas", \
        f"una licitación nueva a {restantes} días hábiles no puede descartarse"
    assert clasifica(restantes, True) in ("por_cerrar", "descartada")
print("OK  ninguna licitación nueva se pierde dentro del horizonte")

# Simulación del ciclo de vida completo de una licitación.
vida, registro = [], set()
for restantes in range(14, -1, -1):          # se publica con 14 días hábiles y va bajando
    cls = clasifica(restantes, "X" in registro)
    registro.add("X")
    if cls != "descartada":
        vida.append((restantes, cls))
assert vida[0] == (14, "nuevas"), "debe reportarse el primer día que aparece"
assert [c for _, c in vida].count("nuevas") == 1, "no puede reportarse como nueva dos veces"
assert vida[-1] == (0, "por_cerrar"), "debe recordarse el día que cierra"
print(f"OK  ciclo de vida: se avisa {len(vida)} veces en 15 días ({vida})")

# ---------- 5. informe HTML de punta a punta ----------
hoy = date(2026, 8, 17)
def op(nombre, org, dias, pts, monto, nuevo=True, cod="1509-12-LE26"):
    cierre = datetime(2026, 8, 17, 15) + timedelta(days=dias)
    return {"codigo": cod, "nombre": nombre, "organismo": org,
            "unidad": "", "tipo": "LE", "cierre": cierre.isoformat(),
            "habiles_restantes": radar.habiles_entre(hoy, cierre.date(), FER),
            "nuevo": nuevo, "visto_desde": "2026-08-17",
            "monto": monto, "puntaje": pts,
            "razones": ["rubro ONU 81111504", "«desarrollo de software» en el título"],
            "url": radar.ficha_url(cod), "descripcion": ""}

nuevas = [
    op("Desarrollo de plataforma web de trámites en línea", "I. Municipalidad de Ñuñoa", 26, 34, "28.000.000 CLP"),
    op("Servicio de desarrollo y mantención de sistema de gestión escolar", "Servicio Local de Educación Pública", 18, 41, "no informado", cod="2345-9-LP26"),
    op("Implementación de sistema informático de inventario", "Hospital Regional de Talca", 11, 22, "12.500.000 CLP", cod="887-3-LE26"),
]
cerrando = [op("Desarrollo de aplicación móvil para inspectores", "SEREMI de Salud", 2, 29,
               "6.800.000 CLP", nuevo=False, cod="4410-2-LE26")]

res = {
    "generado": "2026-08-17 07:30", "fecha": "2026-08-17",
    "horizonte": HORIZONTE, "fecha_hasta": "2026-09-14", "primera_corrida": False,
    "modo": "solo desarrollo",
    "resumen": {"activas_revisadas": 4312, "detalles_consultados": 386,
                "nuevas": len(nuevas), "por_cerrar": len(cerrando),
                "llamadas_api": 387},
    "nuevas": nuevas, "por_cerrar": cerrando, "oportunidades": nuevas,
}
out = Path(__file__).parent / "data" / "informe_demo.html"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(radar.html(res), encoding="utf-8")
txt = out.read_text(encoding="utf-8")
for esperado in ["Radar Mercado Público", "plataforma web de trámites",
                 "Nuevas oportunidades", "Cierran pronto",
                 "aplicación móvil para inspectores", ">nueva<"]:
    assert esperado in txt, f"falta «{esperado}» en el informe"
assert txt.count(">nueva<") == 3, "el badge «nueva» no coincide con las 3 nuevas"

# Los dos enlaces por licitación, y que el código vaya escapado en la URL.
assert txt.count("DetailsAcquisition.aspx?idlicitacion=") == 8, "faltan enlaces a la ficha"
assert txt.count("buscador.mercadopublico.cl/licitaciones?texto=") == 4, "falta el enlace de respaldo"
assert "idlicitacion=2345-9-LP26" in txt
assert 'class="cod">887-3-LE26<' in txt, "el código debe verse para copiar"
print(f"OK  informe HTML con secciones y doble enlace ({out.stat().st_size} bytes) -> {out}")

# informe sin nada nuevo y sin cierres: no debe aparecer la 2ª sección
vacio = dict(res, nuevas=[], por_cerrar=[], oportunidades=[],
             resumen=dict(res["resumen"], nuevas=0, por_cerrar=0))
htm = radar.html(vacio)
assert "Ninguna licitación de desarrollo nueva hoy" in htm
assert "Cierran pronto" not in htm
print("OK  informe HTML sin resultados")

print("\nTodas las pruebas pasaron.")
