# Radar Mercado Público — desarrollo de software

Bot que cada día hábil revisa **todas las licitaciones activas** de Mercado Público,
se queda con las que **cierran dentro de 2 días hábiles** y son de **desarrollo de
software / programación**, y te deja un informe listo para decidir a qué postular.

---

> **¿Instalándolo tú mismo, sin ayuda técnica?** Abre `guia-instalacion.html` en el
> navegador: son 6 pasos con clics, sin escribir una sola línea de código. Este README
> es la referencia técnica de más abajo.

---

## 1. Pide el ticket de la API (5 minutos, gratis)

1. Entra a <https://api.mercadopublico.cl/modules/IniciarSesion.aspx>
2. Acepta los términos e inicia sesión con **Clave Única**.
3. Completa el formulario (nombre, RUT, correo).
4. El ticket llega automáticamente a tu correo. Se ve así:
   `F8537A18-6766-4DEF-9E59-426B4FEE2844`

Límite: **10.000 consultas diarias** por ticket. Este radar usa entre 50 y 150 al
día, así que sobra de lejos.

---

## 2. Corre el radar

### Opción A — En tu PC (para probar hoy mismo)

```bash
pip install -r requirements.txt
export MP_TICKET="tu-ticket-aqui"      # en Windows: set MP_TICKET=tu-ticket-aqui
python radar.py
```

Genera `data/informe.html` (ábrelo en el navegador) y `data/latest.json`.

Opciones:

| Comando | Qué hace |
|---|---|
| `python radar.py` | Ventana de 2 días hábiles, solo desarrollo |
| `python radar.py --dias 3` | Amplía la ventana a 3 días hábiles |
| `python radar.py --amplio` | Incluye TI en general (soporte, datos, infra) |
| `python radar.py --umbral 5` | Baja el filtro: más resultados, más ruido |

### Opción B — Automático con GitHub Actions (recomendado, gratis, sin servidor)

1. Crea un repositorio **privado** en GitHub y sube estos archivos.
2. En el repo: **Settings → Secrets and variables → Actions → New repository secret**
   - Nombre: `MP_TICKET` · Valor: tu ticket
   - (Opcional) `TELEGRAM_TOKEN` y `TELEGRAM_CHAT` para recibir el aviso por Telegram.
3. Listo. `.github/workflows/radar.yml` corre **de lunes a viernes** y deja el
   informe actualizado en `data/informe.html` dentro del repo.
4. Para probarlo sin esperar: pestaña **Actions → Radar Mercado Público → Run workflow**.

> El cron está en `30 11 * * 1-5` (11:30 UTC) = **08:30 en Chile en verano, 07:30 en
> invierno**. Si lo quieres siempre a las 08:00, cambia la hora dos veces al año o
> déjalo a las `00 12 * * 1-5`.

---

## 3. Cómo decide qué es "desarrollo"

Cada licitación recibe un puntaje (`fit`) que combina:

- **Código ONU / UNSPSC** del ítem: `811115xx` (ingeniería de software), `811118xx`
  (programadores de sistemas), `4323xxxx` (software). Ver `CODIGOS_DESARROLLO` en `radar.py`.
- **Palabras clave** en el título (peso completo) y en la descripción (peso mitad):
  "desarrollo de software", "plataforma web", "analista programador", etc.
- **Penalización por ruido**: tóner, notebooks, CCTV, cableado, licencias Office,
  aseo… todo lo que parece TI pero no lo es.

Entra al informe lo que supere `UMBRAL = 8`. **Todo eso está en las primeras 100
líneas de `radar.py` y se edita a mano** — después de una semana usándolo vas a
querer subir o bajar pesos según lo que te llegue.

Para calibrar rápido:

```bash
python radar.py --umbral 3   # ver qué se está quedando fuera
```

---

## 4. Detalles que importan

- **Días hábiles**: descuenta sábados, domingos y feriados chilenos. Los feriados se
  bajan de una API pública; si no responde, usa la lista local de `FERIADOS_FALLBACK`
  (2026 y 2027 ya están cargados).
- **La API de Mercado Público se cae seguido** (errores 500 intermitentes). El script
  reintenta 6 veces con espera creciente. Si un día devuelve 0 activas, es la API, no tú.
- **Caché**: los detalles se guardan en `data/cache/` por día, así no se gastan
  consultas repetidas si corres el script varias veces.
- **Historial**: cada corrida queda en `data/historial/AAAA-MM-DD.json`. Sirve para,
  en un par de meses, ver qué organismos licitan más y qué montos se manejan.

---

## 5. Compra Ágil

ChileCompra lanzó una API de Compra Ágil en beta (mayo 2026) pero todavía no publica
los endpoints. Mientras tanto, para compras bajo 100 UTM —que es donde hay mucho
trabajo chico de TI y se adjudica rápido— revisa a mano el buscador:

<https://buscador.mercadopublico.cl/compra-agil>

Cuando la documentación de esa API salga, se agrega como una función más en `radar.py`
sin tocar el resto.

---

## Pruebas

```bash
python test_radar.py
```

Valida el cálculo de días hábiles (incluidos feriados), el parseo de fechas, la
clasificación desarrollo vs. ruido y la generación del informe.
