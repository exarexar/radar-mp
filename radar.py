#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar Mercado Público — alerta diaria de licitaciones de desarrollo de software,
pensada para tener tiempo real de preparar la propuesta.

Dos listas:
  · PARA PREPARAR   cierran entre 5 y 7 días hábiles (ventana por defecto).
                    Es la lista de trabajo: hay plazo para armar la oferta.
  · APARECIÓ TARDE  cierran en menos de 5 días hábiles Y es la primera vez que
                    se ven. Cubre las licitaciones que se publican con poco
                    aviso y que de otra forma nunca pasarían por la ventana.

Uso:
    export MP_TICKET="tu-ticket-de-api"
    python radar.py                       # ventana 5 a 7 días hábiles
    python radar.py --desde 4 --hasta 10  # otra ventana
    python radar.py --amplio              # incluye TI en general

Salidas (carpeta ./data):
    latest.json          resultado estructurado del último run
    informe.html         informe legible para abrir/compartir
    vistos.json          registro de códigos ya reportados
    historial/AAAA-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

API = "https://api.mercadopublico.cl/servicios/v1/publico"
TZ_OFFSET = timedelta(hours=-4)  # America/Santiago (se ajusta solo, ver ahora_cl)

RAIZ = Path(__file__).resolve().parent
DATA = RAIZ / "data"
CACHE = DATA / "cache"
HIST = DATA / "historial"

# Códigos ONU (UNSPSC) que usa Mercado Público.
# Prefijos: mientras más largo el prefijo, más específico el match.
CODIGOS_DESARROLLO = {
    # Servicios de ingeniería de software
    "811115": 10,   # Ingeniería de software o hardware
    "811118": 10,   # Programadores de sistemas
    "811116": 8,    # Sistemas de gestión de información
    "811119": 8,    # Servicios de sistemas de información
    "811122": 8,    # Mantenimiento y soporte de software
    "811121": 7,    # Servicios de datos / bases de datos
    "811112": 6,    # Servicios de programación de sistemas
    # Software (familia 4323)
    "432315": 6,    # Software funcional empresarial
    "432320": 8,    # Software de desarrollo / lenguajes
    "432321": 7,    # Software de gestión de datos
    "432323": 6,    # Software de sistemas de información
    "4323": 4,      # Software en general (más débil)
    # Servicios TI generales (solo suman en modo --amplio, ver AMPLIO_EXTRA)
}

CODIGOS_TI_AMPLIO = {
    "8111": 5,      # Servicios informáticos en general
    "8116": 4,      # Servicios de sistemas
    "4322": 2,      # Equipos de comunicación (débil)
    "4321": 2,      # Hardware (débil)
    "8112": 4,      # Servicios de datos
}

# Palabras clave. El peso es por aparición en el nombre; en descripción vale la mitad.
CLAVES_FUERTES = {
    "desarrollo de software": 12, "desarrollo de sistema": 12, "fabrica de software": 12,
    "fábrica de software": 12, "software a medida": 12, "desarrollo a medida": 12,
    "programacion": 9, "programación": 9, "desarrollo de aplicacion": 12,
    "desarrollo de aplicación": 12, "aplicacion movil": 11, "aplicación móvil": 11,
    "app movil": 10, "aplicacion web": 11, "aplicación web": 11, "plataforma web": 10,
    "sistema informatico": 10, "sistema informático": 10, "portal web": 8,
    "sitio web": 8, "pagina web": 7, "página web": 7, "desarrollo web": 11,
    "integracion de sistemas": 9, "integración de sistemas": 9,
    "servicios de desarrollo": 10, "implementacion de sistema": 8,
    "implementación de sistema": 8, "migracion de sistema": 8, "migración de sistema": 8,
    "mantencion de software": 9, "mantención de software": 9,
    "mantenimiento de software": 9, "mantencion de sistema": 8, "mantención de sistema": 8,
    "soporte y desarrollo": 9, "evolutivo": 7, "api rest": 8, "microservicio": 8,
    "backend": 7, "front end": 6, "frontend": 7, "base de datos": 5,
    "transformacion digital": 6, "transformación digital": 6, "erp": 6,
    "business intelligence": 6, "inteligencia de negocio": 6, "power bi": 5,
    "data warehouse": 6, "automatizacion de proceso": 6, "automatización de proceso": 6,
    "sistema de gestion": 5, "sistema de gestión": 5,
    "modulo informatico": 7, "módulo informático": 7, "aplicativo": 6,
    "levantamiento de requerimientos": 6, "analista programador": 10,
    "ingeniero de software": 10, "qa de software": 7, "testing de software": 7,
    "diseño ux": 4, "experiencia de usuario": 4, "ciberseguridad": 5,
}

# La palabra "software" sola vale poco: aparece igual en "compra de licencias de
# software". Suma solo cuando viene acompañada de un verbo de construcción.
CLAVES_FUERTES.update({
    "software": 3,
    "desarrollo de un software": 12, "construccion de software": 11,
    "construcción de software": 11, "sistema de informacion": 8,
    "sistema de información": 8, "gestion digital": 6, "gestión digital": 6,
    "gestion documental": 6, "gestión documental": 6,
    # Formas de decir «constrúyeme algo» que faltaban. Detectadas con datos reales.
    "desarrollo de plataforma": 12, "desarrollo de portal": 11,
    "desarrollo de sitio": 10, "desarrollo e implementacion": 10,
    "desarrollo e implementación": 10, "diseño y desarrollo": 11,
    "mantencion web": 8, "mantención web": 8, "mant. web": 8,
    "desarrollo y mantencion": 11, "desarrollo y mantención": 11,
    "plataforma informatica": 9, "plataforma informática": 9,
    "portal de tramites": 9, "portal de trámites": 9,
    "sistema web": 10, "software de gestion": 7, "software de gestión": 7,
})

# Cosas que se ven "TI" pero NO son desarrollo. Restan puntos.
CLAVES_RUIDO = {
    "toner": -12, "tóner": -12, "cartucho": -12, "impresora": -10, "fotocopiadora": -12,
    "notebook": -9, "computador": -7, "computadores": -9, "monitor": -6, "tablet": -6,
    "proyector": -8, "mouse": -8, "teclado": -8, "ups": -6, "servidor fisico": -8,
    "servidor físico": -8, "cableado estructurado": -12, "fibra optica": -10,
    "fibra óptica": -10, "camaras de seguridad": -12, "cámaras de seguridad": -12,
    "cctv": -12, "telefonia": -8, "telefonía": -8, "celulares": -9, "internet": -5,
    "enlace dedicado": -9, "arriendo de equipos": -10, "compra de licencias": -8,
    "licencias microsoft": -9, "licencia office": -9, "adobe": -6, "antivirus": -5,
    "insumos computacionales": -12, "equipamiento computacional": -9,
    "aseo": -15, "alimentacion": -15, "alimentación": -15, "vehiculo": -15,
    "vehículo": -15, "obras": -12,
    "capacitacion": -3, "capacitación": -3, "mobiliario": -15, "combustible": -15,
    # Compra de producto de estante, no desarrollo. Detectado con datos reales.
    "adquisicion de licencia": -14, "adquisición de licencia": -14,
    "adquisicion de licencias": -14, "adquisición de licencias": -14,
    "renovacion de licencia": -14, "renovación de licencia": -14,
    "renovacion de licencias": -14, "renovación de licencias": -14,
    "suscripcion de licencias": -14, "suscripción de licencias": -14,
    "compra de software": -12, "adquisicion de software": -12,
    "adquisición de software": -12, "licencia de software": -12,
    "licencias de software": -12, "licenciamiento": -10,
    "vmware": -14, "teamviewer": -14, "autocad": -14, "oracle": -6,
    "diseño asistido por computador": -14, "almacenamiento en la nube": -10,
    "soporte remoto": -8,
    # Rubros que no tienen nada que ver y colaban por palabras sueltas.
    "coffee break": -20, "medicamento": -20, "insumos medicos": -20,
    "insumos médicos": -20, "aire acondicionado": -20, "climatizacion": -20,
    "climatización": -20, "señaletica": -15, "señalética": -15,
    "vestuario": -20, "utiles de oficina": -20, "útiles de oficina": -20,
    # Homónimos: «programación» también es la cartelera de un teatro.
    "programacion artistica": -25, "programación artística": -25,
    "programacion cultural": -25, "programación cultural": -25,
    "programacion musical": -25, "programación musical": -25,
    "programacion de actividades": -22, "programación de actividades": -22,
    "escuela de folclore": -25, "espectaculo": -20, "espectáculo": -20,
    # Equipamiento de laboratorio que viene «con sistema informático en comodato».
    "reactivo": -22, "reactivos": -22, "comodato": -14, "analizador": -18,
    "hematologia": -22, "hematología": -22, "laboratorio clinico": -18,
    "laboratorio clínico": -18, "examenes bioquimicos": -22,
    "exámenes bioquímicos": -22, "serologicos": -22, "serológicos": -22,
    # Mesa de ayuda: es TI, pero no es construir software.
    "mesa de ayuda": -14, "mesa de servicios": -14, "help desk": -14,
    "soporte a usuarios": -10, "mesa de servicio": -14,
    # Digitalizar papeles es escanear, no programar.
    "digitalizacion de fichas": -16, "digitalización de fichas": -16,
    "digitalizacion de documentos": -14, "digitalización de documentos": -14,
    "escaneo": -12,
}


def _compacta(pesos: dict[str, int]) -> dict[str, int]:
    """Normaliza las claves y funde los duplicados con/sin tilde.

    Sin esto «programación» y «programacion» quedaban como dos entradas distintas
    que colapsaban al mismo texto normalizado, así que cada una sumaba por
    separado y el peso real era el doble del declarado.
    """
    out: dict[str, int] = {}
    for k, v in pesos.items():
        nk = normaliza(k)
        if nk not in out or abs(v) > abs(out[nk]):
            out[nk] = v
    return out


# Las tablas se compactan más abajo, apenas normaliza() está disponible.

UMBRAL = 9       # puntaje mínimo para entrar al informe
HORIZONTE = 20   # días hábiles hacia adelante que se escanean
RECORDAR = 2     # días hábiles: recordatorio de cierre de algo ya reportado
MINIMO = 0       # días hábiles mínimos para reportar algo como oportunidad nueva

FERIADOS_FALLBACK = {
    # 2026
    "2026-01-01", "2026-04-03", "2026-04-04", "2026-05-01", "2026-05-21",
    "2026-06-21", "2026-06-29", "2026-07-16", "2026-08-15", "2026-09-18",
    "2026-09-19", "2026-10-12", "2026-10-31", "2026-11-01", "2026-12-08",
    "2026-12-25",
    # 2027 (referenciales; el script intenta traerlos de la API igual)
    "2027-01-01", "2027-03-26", "2027-03-27", "2027-05-01", "2027-05-21",
    "2027-06-21", "2027-06-28", "2027-07-16", "2027-08-15", "2027-09-18",
    "2027-09-19", "2027-10-11", "2027-10-31", "2027-11-01", "2027-12-08",
    "2027-12-25",
}


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def ahora_cl() -> datetime:
    """Hora local de Chile continental sin depender de tzdata del runner."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow() + TZ_OFFSET


_RX_CACHE: dict[str, re.Pattern] = {}


def contiene(texto: str, frase: str) -> bool:
    """Busca `frase` como palabra completa, no como trozo de otra palabra.

    Sin esto, «ui» calzaba dentro de «adqUIsición» y hacía que cualquier compra
    pública puntuara. Es el bug que metía coffee breaks en el informe.
    """
    rx = _RX_CACHE.get(frase)
    if rx is None:
        cuerpo = r"\s+".join(re.escape(p) for p in frase.split())
        rx = re.compile(rf"(?<![0-9a-z]){cuerpo}(?![0-9a-z])")
        _RX_CACHE[frase] = rx
    return rx.search(texto) is not None


def normaliza(txt: str) -> str:
    if not txt:
        return ""
    t = unicodedata.normalize("NFKD", str(txt).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t)


CLAVES_FUERTES = _compacta(CLAVES_FUERTES)
CLAVES_RUIDO = _compacta(CLAVES_RUIDO)


def feriados(anios: list[int]) -> set[str]:
    """Feriados de Chile. Intenta API pública; si falla, usa la lista local."""
    fer = set(FERIADOS_FALLBACK)
    for a in anios:
        for url in (f"https://api.boostr.cl/holidays/{a}.json",
                    f"https://apis.digital.gob.cl/fl/feriados/{a}"):
            try:
                r = requests.get(url, timeout=12)
                if r.status_code != 200:
                    continue
                js = r.json()
                items = js.get("data", js) if isinstance(js, dict) else js
                for it in items:
                    f = it.get("date") or it.get("fecha")
                    if f:
                        fer.add(str(f)[:10])
                break
            except Exception:
                continue
    return fer


def dias_habiles_adelante(inicio: date, n: int, fer: set[str]) -> date:
    """Devuelve la fecha del n-ésimo día hábil contando desde 'inicio' (excluido)."""
    d, contados = inicio, 0
    while contados < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in fer:
            contados += 1
    return d


def habiles_entre(a: date, b: date, fer: set[str]) -> int:
    if b < a:
        return -1
    d, n = a, 0
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in fer:
            n += 1
    return n


def parse_fecha(v) -> datetime | None:
    if not v:
        return None
    s = str(v).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# Cliente API
# --------------------------------------------------------------------------

CACHE_DIAS = 10   # cuántos días se reutiliza la ficha ya descargada


class MP:
    def __init__(self, ticket: str, pausa: float = 0.35):
        self.ticket = ticket
        self.pausa = pausa
        self.desde_cache = 0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "radar-mp/1.0 (monitoreo de licitaciones)"
        self.llamadas = 0

    def get(self, ruta: str, **params) -> dict | None:
        params["ticket"] = self.ticket
        url = f"{API}/{ruta}"
        espera = 2.0
        for intento in range(6):
            try:
                self.llamadas += 1
                r = self.s.get(url, params=params, timeout=90)
                if r.status_code == 200:
                    js = r.json()
                    if isinstance(js, dict) and js.get("Codigo") in (203, 204):
                        raise RuntimeError(f"API rechazó el ticket: {js.get('Mensaje')}")
                    time.sleep(self.pausa)
                    return js
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(espera)
                    espera = min(espera * 1.8, 30)
                    continue
                r.raise_for_status()
            except RuntimeError:
                raise
            except Exception as e:
                if intento == 5:
                    print(f"  ! fallo definitivo {ruta} {params.get('codigo','')}: {e}",
                          file=sys.stderr)
                    return None
                time.sleep(espera)
                espera = min(espera * 1.8, 30)
        return None

    def activas(self) -> list[dict]:
        js = self.get("licitaciones.json", estado="activas")
        return (js or {}).get("Listado", []) or []

    def detalle(self, codigo: str) -> dict | None:
        """Ficha completa. Se reutiliza la copia local mientras sea reciente.

        Los datos que dependen del tiempo (la fecha de cierre) NO se leen de aquí:
        main() usa siempre la fecha del listado de activas, que se baja fresca cada
        día. Lo cacheado es rubro, monto y descripción, que no cambian.
        """
        f = CACHE / f"{re.sub(r'[^A-Za-z0-9_-]', '_', codigo)}.json"
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                cuando = parse_fecha(d.get("_cached_at"))
                if cuando and (datetime.now() - cuando).days < CACHE_DIAS:
                    self.desde_cache += 1
                    return d
            except Exception:
                pass
        js = self.get("licitaciones.json", codigo=codigo)
        lst = (js or {}).get("Listado") or []
        if not lst:
            return None
        d = lst[0]
        d["_cached_at"] = datetime.now().isoformat()
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d


# --------------------------------------------------------------------------
# Puntaje de relevancia
# --------------------------------------------------------------------------

def codigos_onu(det: dict) -> list[str]:
    out = []
    for it in (det.get("Items") or {}).get("Listado", []) or []:
        c = it.get("CodigoProducto") or it.get("CodigoCategoria")
        if c:
            out.append(str(c))
    return out


def puntuar(det: dict, amplio: bool) -> tuple[int, list[str]]:
    razones, puntos = [], 0

    nombre = normaliza(det.get("Nombre"))
    desc = normaliza(det.get("Descripcion"))
    items_txt = normaliza(" ".join(
        f"{i.get('NombreProducto','')} {i.get('Descripcion','')}"
        for i in (det.get("Items") or {}).get("Listado", []) or []
    ))

    tabla = dict(CODIGOS_DESARROLLO)
    if amplio:
        for k, v in CODIGOS_TI_AMPLIO.items():
            tabla[k] = max(tabla.get(k, 0), v)

    mejor_cod, mejor_pts = None, 0
    for c in codigos_onu(det):
        for pref, pts in tabla.items():
            if c.startswith(pref) and pts > mejor_pts:
                mejor_cod, mejor_pts = c, pts
    if mejor_pts:
        puntos += mejor_pts
        razones.append(f"rubro ONU {mejor_cod}")

    # Las claves ya vienen normalizadas y sin duplicados desde _compacta().
    for k, pts in CLAVES_FUERTES.items():
        if contiene(nombre, k):
            puntos += pts
            razones.append(f"«{k}» en el título")
        elif contiene(desc, k) or contiene(items_txt, k):
            puntos += max(1, pts // 2)
            razones.append(f"«{k}» en el detalle")

    for k, pts in CLAVES_RUIDO.items():
        if contiene(nombre, k) or contiene(items_txt, k):
            puntos += pts
            razones.append(f"ruido: «{k}»")
        elif contiene(desc, k):
            puntos += pts // 2
            razones.append(f"ruido: «{k}» en el detalle")

    # dedup conservando orden
    vistos, limpias = set(), []
    for r in razones:
        if r not in vistos:
            vistos.add(r)
            limpias.append(r)
    return puntos, limpias[:6]


def monto(det: dict) -> str:
    m = det.get("MontoEstimado") or (det.get("Adjudicacion") or {}).get("Monto")
    mon = det.get("Moneda") or "CLP"
    if not m:
        return "no informado"
    try:
        return f"{float(m):,.0f} {mon}".replace(",", ".")
    except Exception:
        return f"{m} {mon}"


# --------------------------------------------------------------------------
# Informe
# --------------------------------------------------------------------------

def ficha_url(codigo: str) -> str:
    """Enlace directo a la ficha. Es el formato que usa Mercado Público, pero
    el sitio a veces exige sesión; por eso el informe ofrece también buscar_url."""
    return ("https://www.mercadopublico.cl/Procurement/Modules/RFB/"
            f"DetailsAcquisition.aspx?idlicitacion={quote(codigo)}")


def buscar_url(codigo: str) -> str:
    """Plan B: el buscador público, que no pide sesión."""
    return f"https://buscador.mercadopublico.cl/licitaciones?texto={quote(codigo)}"


def _filas(lista: list[dict], vacio: str) -> str:
    filas = []
    for r in lista:
        n = r["habiles_restantes"]
        urg = ("hoy" if n <= 0 else "1 día hábil" if n == 1
               else f"{n} días hábiles")
        cls = "crit" if n <= 1 else "alto" if n <= 4 else "medio"
        nueva = ' <span class="nueva">nueva</span>' if r.get("nuevo") else ""
        cod = r["codigo"]
        filas.append(f"""
      <tr>
        <td><span class="chip {cls}">{urg}</span><br><small>{r['cierre'][:16].replace('T',' ')}</small></td>
        <td><a href="{ficha_url(cod)}" target="_blank"><strong>{r['nombre']}</strong></a>{nueva}
            <br><small><code class="cod">{cod}</code> &middot; {r['tipo']} &middot;
             <a href="{ficha_url(cod)}" target="_blank">ficha</a> &middot;
             <a href="{buscar_url(cod)}" target="_blank">buscar en el portal</a></small>
            <div class="raz">{' &middot; '.join(r['razones'])}</div></td>
        <td>{r['organismo']}</td>
        <td class="num">{r['monto']}</td>
        <td class="num"><span class="pts">{r['puntaje']}</span></td>
      </tr>""")
    return "".join(filas) or f'<tr><td colspan="5" class="vacio">{vacio}</td></tr>'


def html(res: dict) -> str:
    cuerpo = _filas(res["nuevas"],
                    "Ninguna licitación de desarrollo nueva hoy dentro del horizonte.")

    recordatorios = res.get("por_cerrar") or []
    seccion_tarde = ""
    if recordatorios:
        seccion_tarde = f"""
<h2 class="sec">Cierran pronto <span>ya te las reportamos antes — última pasada antes de que se cierren</span></h2>
<table><thead><tr>
 <th>Cierre</th><th>Licitación</th><th>Organismo</th><th>Monto est.</th><th>Fit</th>
</tr></thead><tbody>{_filas(recordatorios, "")}</tbody></table>"""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar Mercado Público — {res['fecha']}</title>
<style>
 :root {{ color-scheme: light dark;
   --bg:#fbfaf9; --fg:#1c1a17; --mut:#6b6560; --line:#e6e2dd; --card:#fff;
   --crit:#b4351f; --alto:#a86718; --medio:#3f6f5c; }}
 @media (prefers-color-scheme: dark) {{ :root {{
   --bg:#171614; --fg:#eceae7; --mut:#9c958e; --line:#302d29; --card:#1f1e1b;
   --crit:#e8836c; --alto:#e0aa5f; --medio:#7fbfa5; }} }}
 * {{ box-sizing:border-box }}
 body {{ margin:0; padding:28px 20px 60px; background:var(--bg); color:var(--fg);
   font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }}
 .wrap {{ max-width:1080px; margin:0 auto }}
 h1 {{ font-size:23px; margin:0 0 4px; letter-spacing:-.01em }}
 .sub {{ color:var(--mut); font-size:13.5px; margin-bottom:22px }}
 .kpis {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:22px }}
 .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
   padding:12px 16px; min-width:130px }}
 .kpi b {{ display:block; font-size:26px; font-weight:600; letter-spacing:-.02em }}
 .kpi span {{ color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.05em }}
 table {{ width:100%; border-collapse:collapse; background:var(--card);
   border:1px solid var(--line); border-radius:10px; overflow:hidden }}
 th {{ text-align:left; font-size:11.5px; text-transform:uppercase; letter-spacing:.06em;
   color:var(--mut); padding:11px 14px; border-bottom:1px solid var(--line); font-weight:600 }}
 td {{ padding:14px; border-bottom:1px solid var(--line); vertical-align:top; font-size:14px }}
 tr:last-child td {{ border-bottom:0 }}
 a {{ color:inherit; text-decoration:none }} a:hover {{ text-decoration:underline }}
 small {{ color:var(--mut); font-size:12px }}
 .num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums }}
 .chip {{ display:inline-block; padding:2px 9px; border-radius:99px; font-size:11.5px;
   font-weight:600; border:1px solid currentColor }}
 .crit {{ color:var(--crit) }} .alto {{ color:var(--alto) }} .medio {{ color:var(--medio) }}
 .pts {{ color:var(--mut); font-size:12.5px }}
 .raz {{ color:var(--mut); font-size:12px; margin-top:5px }}
 .vacio {{ text-align:center; color:var(--mut); padding:44px 14px }}
 .sec {{ font-size:15px; margin:30px 0 11px; display:flex; align-items:baseline;
   gap:11px; flex-wrap:wrap; letter-spacing:-.01em }}
 .sec span {{ font-weight:400; font-size:12.5px; color:var(--mut) }}
 .nueva {{ display:inline-block; vertical-align:1px; margin-left:6px; padding:1px 7px;
   border-radius:99px; font-size:10.5px; font-weight:700; text-transform:uppercase;
   letter-spacing:.06em; background:var(--medio); color:var(--card) }}
 .cod {{ font:12px ui-monospace,SFMono-Regular,Menlo,monospace; background:var(--bg);
   border:1px solid var(--line); border-radius:4px; padding:1px 5px; user-select:all }}
 footer {{ color:var(--mut); font-size:12px; margin-top:22px }}
</style></head><body><div class="wrap">
<h1>Radar Mercado Público — desarrollo de software</h1>
<div class="sub">Horizonte: {res['horizonte']} días hábiles (cierres hasta el
 {res['fecha_hasta']}) &middot; generado el {res['generado']}</div>
<div class="kpis">
 <div class="kpi"><b>{res['resumen']['nuevas']}</b><span>nuevas hoy</span></div>
 <div class="kpi"><b>{res['resumen']['por_cerrar']}</b><span>cierran pronto</span></div>
 <div class="kpi"><b>{res['resumen']['activas_revisadas']}</b><span>activas revisadas</span></div>
 <div class="kpi"><b>{res['resumen']['detalles_consultados']}</b><span>fichas leídas</span></div>
</div>
<h2 class="sec">Nuevas oportunidades <span>primera vez que aparecen en el radar</span></h2>
<table><thead><tr>
 <th>Cierre</th><th>Licitación</th><th>Organismo</th><th>Monto est.</th><th>Fit</th>
</tr></thead><tbody>{cuerpo}</tbody></table>
{seccion_tarde}
<footer>Fuente: API de Mercado Público (ChileCompra). El puntaje «fit» es heurístico
 (rubro ONU + palabras clave); revisa siempre las bases antes de postular.</footer>
</div></body></html>"""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizonte", type=int, default=HORIZONTE,
                    help="días hábiles hacia adelante que se escanean")
    ap.add_argument("--recordar", type=int, default=RECORDAR,
                    help="recordar las ya reportadas cuando les queden N días hábiles")
    ap.add_argument("--minimo", type=int, default=MINIMO,
                    help="no reportar como nueva si le quedan menos de N días hábiles")
    ap.add_argument("--amplio", action="store_true", help="incluir TI en general")
    ap.add_argument("--umbral", type=int, default=UMBRAL)
    args = ap.parse_args()

    ticket = os.environ.get("MP_TICKET", "").strip()
    if not ticket:
        print("ERROR: falta la variable de entorno MP_TICKET", file=sys.stderr)
        return 2

    for d in (DATA, CACHE, HIST):
        d.mkdir(parents=True, exist_ok=True)

    hoy_dt = ahora_cl()
    hoy = hoy_dt.date()
    fer = feriados([hoy.year, hoy.year + 1])
    techo = dias_habiles_adelante(hoy, args.horizonte, fer)
    techo_dt = datetime.combine(techo, datetime.max.time())

    # Registro de códigos ya reportados, para distinguir lo que recién apareció.
    f_vistos = DATA / "vistos.json"
    primera_corrida = not f_vistos.exists()
    try:
        vistos = json.loads(f_vistos.read_text(encoding="utf-8"))
    except Exception:
        vistos, primera_corrida = {}, True

    print(f"[{hoy_dt:%Y-%m-%d %H:%M}] horizonte: {args.horizonte} días hábiles "
          f"(cierres hasta el {techo})")
    if primera_corrida:
        print("  (primera corrida: se reporta todo lo vigente y se siembra el registro)")

    mp = MP(ticket)
    activas = mp.activas()
    print(f"  licitaciones activas: {len(activas)}")
    if not activas:
        print("  ! la API no devolvió activas (puede estar caída); reintenta más tarde",
              file=sys.stderr)

    candidatos = []
    for lic in activas:
        fc = parse_fecha(lic.get("FechaCierre"))
        cod = lic.get("CodigoExterno")
        if not cod:
            continue
        # Si la lista no trae FechaCierre confiable, dejamos pasar al detalle.
        # Escaneamos 0..hasta: lo de la ventana, más lo que cierra antes (por si
        # recién apareció y nunca alcanzó a pasar por la ventana).
        if fc is None or (hoy_dt - timedelta(hours=12)) <= fc <= techo_dt:
            candidatos.append((cod, lic.get("Nombre", ""), fc))

    # Prefiltro barato por título para no gastar el cupo diario en ruido evidente.
    def vale_la_pena(nombre: str) -> bool:
        n = normaliza(nombre)
        if any(contiene(n, normaliza(k)) for k in CLAVES_FUERTES):
            return True
        # Raíces sueltas: aquí sí sirve la subcadena, porque son fragmentos de
        # palabra a propósito («informatic» cubre informático/informática).
        return any(t in n for t in ("informatic", "tecnolog", "digital", "sistema",
                                    "software", "aplicacion", "plataforma",
                                    "programa", "portal", "datos", "computa"))

    filtrados = [c for c in candidatos if c[2] is None or vale_la_pena(c[1])]
    print(f"  candidatos por fecha: {len(candidatos)} → a revisar en detalle: {len(filtrados)}")

    # La fecha de cierre viene del listado de activas, que se baja fresco cada día.
    # Si un organismo prorroga el plazo, esto lo refleja aunque la ficha esté en caché.
    cierres = {c[0]: c[2] for c in filtrados if c[2] is not None}

    detalles = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for d in ex.map(lambda c: mp.detalle(c[0]), filtrados):
            if d:
                detalles.append(d)
    print(f"  detalles obtenidos: {len(detalles)} "
          f"({mp.llamadas} llamadas a la API, {mp.desde_cache} desde caché)")

    nuevas, por_cerrar = [], []
    for det in detalles:
        codigo = det.get("CodigoExterno", "")
        fc = cierres.get(codigo) or parse_fecha(
            det.get("Fechas", {}).get("FechaCierre") or det.get("FechaCierre"))
        if fc is None or not (hoy_dt - timedelta(hours=12)) <= fc <= techo_dt:
            continue
        pts, razones = puntuar(det, args.amplio)
        if pts < args.umbral:
            continue

        restantes = habiles_entre(hoy, fc.date(), fer)
        ya_visto = codigo in vistos
        vistos.setdefault(codigo, hoy.isoformat())

        # Cada licitación se reporta UNA vez, apenas aparece. Después solo vuelve
        # como recordatorio cuando está por cerrarse.
        if not ya_visto and restantes >= args.minimo:
            destino = nuevas
        elif ya_visto and restantes <= args.recordar:
            destino = por_cerrar
        else:
            continue        # ya reportada y todavía con plazo: no repetir

        destino.append({
            "codigo": codigo,
            "nombre": (det.get("Nombre") or "").strip(),
            "organismo": (det.get("Comprador") or {}).get("NombreOrganismo", ""),
            "unidad": (det.get("Comprador") or {}).get("NombreUnidad", ""),
            "tipo": det.get("Tipo", ""),
            "cierre": fc.isoformat(),
            "habiles_restantes": restantes,
            "nuevo": not ya_visto,
            "visto_desde": vistos.get(codigo, hoy.isoformat()),
            "monto": monto(det),
            "puntaje": pts,
            "razones": razones,
            "url": ficha_url(codigo),
            "descripcion": (det.get("Descripcion") or "")[:900],
        })

    for lista in (nuevas, por_cerrar):
        lista.sort(key=lambda r: (r["habiles_restantes"], -r["puntaje"]))

    res = {
        "generado": hoy_dt.strftime("%Y-%m-%d %H:%M"),
        "fecha": hoy.isoformat(),
        "horizonte": args.horizonte,
        "fecha_hasta": techo.isoformat(),
        "primera_corrida": primera_corrida,
        "modo": "amplio" if args.amplio else "solo desarrollo",
        "resumen": {
            "activas_revisadas": len(activas),
            "detalles_consultados": len(detalles),
            "nuevas": len(nuevas),
            "por_cerrar": len(por_cerrar),
            "llamadas_api": mp.llamadas,
        },
        "nuevas": nuevas,
        "por_cerrar": por_cerrar,
        # Alias para compatibilidad: la lista principal de trabajo.
        "oportunidades": nuevas,
    }

    (DATA / "latest.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (HIST / f"{hoy.isoformat()}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "informe.html").write_text(html(res), encoding="utf-8")

    # El registro se poda para que no crezca sin control (90 días).
    corte = (hoy - timedelta(days=90)).isoformat()
    vistos = {k: v for k, v in vistos.items() if v >= corte}
    f_vistos.write_text(json.dumps(vistos, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    print(f"  → {len(nuevas)} nuevas, {len(por_cerrar)} por cerrar. "
          f"data/latest.json y data/informe.html listos.")
    for r in nuevas[:12]:
        print(f"     [{r['puntaje']:>3}] cierra en {r['habiles_restantes']}d  "
              f"{r['nombre'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
