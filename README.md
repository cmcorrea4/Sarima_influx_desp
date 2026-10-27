# Pronóstico horario con SARIMA + InfluxDB 2.x + FastAPI (GitHub Codespaces)

API en **FastAPI** que consulta una serie de **InfluxDB 2.x**, pronostica las próximas horas con un modelo **SARIMA** entrenado en **Google Colab**, y la muestra en un **frontend HTML**. Todo corre en **GitHub Codespaces**.

```
 ┌──────────────┐  1. descarga 30 días   ┌──────────────┐
 │ Google Colab │ ─────────────────────▶ │  InfluxDB 2  │
 │  (entrena)   │                        │   (Cloud)    │
 └──────┬───────┘                        └──────▲───────┘
        │ 2. sarima_config.json                 │ 4. últimas 14 días (Flux)
        ▼                                       │
 ┌──────────────┐  3. git pull    ┌─────────────┴────────┐   5. JSON   ┌──────────────┐
 │    GitHub    │ ──────────────▶ │ Codespaces: FastAPI  │ ──────────▶ │ index.html   │
 │ repositorio  │                 │ + statsmodels SARIMA │             │ (Chart.js)   │
 └──────────────┘                 └──────────────────────┘             └──────────────┘
```

**Idea clave:** Colab entrena y exporta solo las órdenes `(p,d,q)(P,D,Q,s)` y los parámetros en un JSON. La API reconstruye el SARIMA con los datos más recientes de InfluxDB y aplica esos parámetros **sin reentrenar** (`model.filter(params)`), así el pronóstico siempre arranca desde la última hora medida. Usar JSON en vez de pickle evita los errores de versión entre Colab y Codespaces.

---

## Estructura

```
.
├── .devcontainer/devcontainer.json   # Configura el Codespace (Python 3.12, puerto 8000)
├── app/
│   ├── config.py                     # Variables de entorno
│   ├── influx.py                     # Consulta Flux + preparación horaria
│   ├── model.py                      # Carga el JSON y pronostica
│   └── main.py                       # Endpoints FastAPI + sirve el frontend
├── frontend/index.html               # Interfaz (gráfica, KPIs, tabla)
├── models/sarima_config.json         # Modelo exportado desde Colab
├── notebooks/entrenamiento_sarima_colab.ipynb
├── scripts/
│   ├── probar_conexion.py            # Verifica InfluxDB y lista measurements/fields
│   └── crear_modelo_demo.py          # Modelo de prueba con datos sintéticos
├── pruebas.http                      # Peticiones de prueba (extensión REST Client)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Paso 0 — Requisitos

- Cuenta de GitHub (Codespaces incluye horas gratis al mes).
- **InfluxDB accesible desde internet.** Codespaces y Colab corren en la nube: con InfluxDB Cloud funciona directo. Si su InfluxDB está en una red local (`192.168.x.x`, una Raspberry, un Jetson…), no lo podrán alcanzar; necesitará exponerlo con un túnel (Cloudflare Tunnel, Tailscale Funnel, ngrok).
- Sus datos: **URL, token, org y bucket**, más el nombre del **measurement** y del **field** a pronosticar.

> **Recomendado:** use un token **de solo lectura** para este proyecto. En InfluxDB Cloud: *Load Data → API Tokens → Generate API Token → Custom API Token* → marque **Read** solo en su bucket.

---

## Paso 1 — Crear el repositorio y abrir el Codespace

1. En GitHub: **New repository** → nombre p.ej. `sarima-influx-api` → marque *Add a README file* → **Create repository**.
2. En el repo: botón verde **Code → pestaña Codespaces → Create codespace on main**. Se abre VS Code en el navegador.
3. Arrastre el archivo `sarima-influx-api.zip` al explorador de archivos (panel izquierdo) del Codespace.
4. En la terminal (`Ctrl + ñ` o *Terminal → New Terminal*):

   ```bash
   unzip -o sarima-influx-api.zip -d /tmp/proyecto
   cp -r /tmp/proyecto/sarima-influx-api/. .
   rm sarima-influx-api.zip
   ls -a        # debe ver .devcontainer, app, frontend, models, notebooks...
   ```

5. Aplique la configuración del contenedor: `F1` → **Codespaces: Rebuild Container**. Al terminar instala las dependencias de `requirements.txt` automáticamente.
6. Suba los archivos al repositorio:

   ```bash
   git add .
   git commit -m "Estructura inicial: FastAPI + InfluxDB + SARIMA"
   git push
   ```

> Si prefiere hacerlo sin zip: puede crear cada archivo en el Codespace y pegar su contenido. Ojo: si sube carpetas desde la web de GitHub arrastrándolas, las carpetas ocultas (`.devcontainer`) y `.gitignore` a veces no se incluyen.

---

## Paso 2 — Guardar las credenciales como *Codespaces secrets*

El token **nunca** debe quedar en el código ni en un commit.

1. En el repo de GitHub: **Settings → Secrets and variables → Codespaces → New repository secret**.
2. Cree estos cuatro:

   | Nombre | Ejemplo |
   |---|---|
   | `INFLUX_URL` | `https://us-east-1-1.aws.cloud2.influxdata.com` |
   | `INFLUX_TOKEN` | `xxxxxxxx==` |
   | `INFLUX_ORG` | `mi-org` |
   | `INFLUX_BUCKET` | `sensores_iot` |

3. Vuelva al Codespace: aparecerá un aviso para recargar y tomar los nuevos secrets → **Reload**. (Si no aparece: `F1` → *Codespaces: Rebuild Container*.)
4. Verifique: `echo $INFLUX_ORG` debe mostrar su organización.

Los datos que **no** son secretos van en un archivo `.env`:

```bash
cp .env.example .env
```

Edite `.env` y ponga **su** `INFLUX_MEASUREMENT` e `INFLUX_FIELD` (y el tag si filtra por dispositivo). Deje las líneas de URL/TOKEN/ORG/BUCKET como están o bórrelas: los secrets de Codespaces tienen prioridad sobre `.env`.

---

## Paso 3 — Probar la conexión con InfluxDB

```bash
python scripts/probar_conexion.py
```

Debe ver `Ping: OK`, la lista de measurements del bucket, los fields de su measurement y las últimas horas de la serie. Si el measurement o el field no aparecen, corrija `.env`.

---

## Paso 4 — Probar la API y el frontend en modo demo (opcional, 1 minuto)

Antes de tener el modelo real puede verificar que todo el montaje funciona con datos sintéticos:

```bash
python scripts/crear_modelo_demo.py
DEMO_MODE=true uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Codespaces detecta el puerto 8000 y ofrece **Open in Browser**. Si no, vaya a la pestaña **PORTS** (junto a la terminal) → icono 🌐 del puerto 8000.

- `https://<su-codespace>-8000.app.github.dev/` → frontend
- `https://<su-codespace>-8000.app.github.dev/docs` → documentación interactiva de la API

Detenga el servidor con `Ctrl + C`. Este modelo demo se reemplazará en el paso 6.

---

## Paso 5 — Entrenar el SARIMA en Google Colab

1. Abra Colab → **Archivo → Abrir notebook → pestaña GitHub** → escriba su usuario, elija el repo y abra `notebooks/entrenamiento_sarima_colab.ipynb`. (Si el repo es privado, marque *Include private repos* y autorice).
2. En la barra izquierda de Colab, icono 🔑 **Secrets**: cree `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` y active *Notebook access*.
3. En la celda de **Configuración** cambie `MEASUREMENT` y `FIELD` (los mismos del `.env`). Ajuste `DIAS_ENTRENAMIENTO` si tiene más o menos historia (mínimo 7 días).
4. **Entorno de ejecución → Ejecutar todas**. El notebook:
   - descarga los datos y los lleva a promedio horario (misma función que la API),
   - grafica la serie, la descomposición y ACF/PACF,
   - elige `d` con la prueba ADF y busca `(p,q)(P,Q)` por AIC con `s = 24` (≈ 2–5 min),
   - evalúa sobre las últimas 24 h contra una línea base ingenua estacional,
   - reentrena con todos los datos, revisa residuos y exporta `sarima_config.json`,
   - **verifica** que la reconstrucción que hará la API da exactamente el mismo pronóstico.

> **Ojo con `s`.** Con datos horarios y un ciclo diario, `s = 24`. Si su variable tiene otro ciclo, cámbielo: SARIMA tolera órdenes de más, pero un periodo estacional equivocado degrada mucho el pronóstico.

---

## Paso 6 — Llevar el modelo al repositorio

**Opción A (manual):** la celda *Descargar* baja `sarima_config.json`. En el Codespace, arrástrelo a la carpeta `models/` (reemplazando el demo) y:

```bash
git add models/sarima_config.json
git commit -m "Modelo SARIMA entrenado en Colab"
git push
```

**Opción B (automática desde Colab):**

1. Cree un token en GitHub: *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token* → **Only select repositories** (su repo) → *Repository permissions → Contents: Read and write*.
2. En los Secrets de Colab agregue `GITHUB_TOKEN` (ese token) y `GITHUB_REPO` (`su-usuario/sarima-influx-api`).
3. Ejecute la celda *Opción B*: clona el repo, copia el JSON a `models/`, hace commit y push.
4. En el Codespace traiga el cambio: `git pull`.

Guarde también el notebook ejecutado: en Colab, **Archivo → Guardar una copia en GitHub** → carpeta `notebooks/`.

---

## Paso 7 — Ejecutar la API con datos reales

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abra el puerto 8000 en el navegador. El frontend:

- consulta `/api/prediccion` y dibuja histórico (azul), pronóstico (naranja, punteado) e intervalo de confianza,
- muestra último valor real, próxima hora, máximo esperado y hora del último dato en InfluxDB,
- convierte las horas UTC a la zona horaria del navegador (America/Bogota),
- lista la tabla del pronóstico y los metadatos/métricas del modelo.

Si entrena un modelo nuevo y hace `git pull` con el servidor corriendo, recárguelo sin reiniciar:

```bash
curl -X POST http://localhost:8000/api/modelo/recargar
```

---

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/` | Frontend |
| GET | `/docs` | Swagger UI (pruebe todo desde aquí) |
| GET | `/api/salud` | ¿Influx configurado? ¿modelo cargado? |
| GET | `/api/historico?horas=48` | Promedios horarios desde InfluxDB |
| GET | `/api/prediccion?horas=12&historia=48&confianza=0.95` | Pronóstico + intervalo + histórico para graficar |
| GET | `/api/modelo` | Órdenes, métricas, fecha y rango de entrenamiento |
| POST | `/api/modelo/recargar` | Relee `models/sarima_config.json` |

Ejemplo de respuesta de `/api/prediccion`:

```json
{
  "ultima_observacion": "2026-10-27T14:00:00Z",
  "horas_contexto_usadas": 336,
  "confianza": 0.95,
  "historico": [{"tiempo": "2026-10-27T14:00:00Z", "valor": 21.63}],
  "prediccion": [
    {"tiempo": "2026-10-27T15:00:00Z", "prediccion": 23.20,
     "limite_inferior": 21.95, "limite_superior": 24.45}
  ]
}
```

Todas las horas viajan en **UTC** (sufijo `Z`); el frontend las convierte a hora local.

---

## Paso 8 — Compartir la app

- **Mostrarla a otros mientras el Codespace corre:** pestaña **PORTS** → clic derecho en el 8000 → *Port Visibility → Public*. Cualquiera con el enlace la ve. (Por defecto es *Private*: solo usted, autenticado en GitHub).
- El Codespace se **detiene tras 30 min sin actividad**; no sirve como servidor permanente. Para dejarla publicada, despliegue el mismo repo en un servicio como Render, Railway o un VPS con Docker, definiendo allí las mismas variables de entorno.

---

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` | Sí | Conexión (como Codespaces secrets) |
| `INFLUX_MEASUREMENT`, `INFLUX_FIELD` | Sí | Serie a pronosticar (iguales a Colab) |
| `INFLUX_TAG_KEY`, `INFLUX_TAG_VALUE` | No | Filtro por tag, p.ej. `device` = `esp32_01` |
| `HORAS_CONTEXTO` | No (336) | Horas de historia que recibe el modelo antes de pronosticar |
| `MAX_HORAS_PREDICCION` | No (72) | Tope de horas a pronosticar |
| `DEMO_MODE` | No (false) | `true` usa datos sintéticos |
| `MODEL_PATH` | No | Ruta alternativa al JSON del modelo |

---

## Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| `Faltan variables de InfluxDB…` | No recargó el Codespace tras crear los secrets, o falta `INFLUX_MEASUREMENT`/`INFLUX_FIELD` en `.env`. |
| `Error consultando InfluxDB: (401) unauthorized` | Token inválido o sin permiso de lectura sobre el bucket. |
| `Error consultando InfluxDB: … timed out / connection refused` | La URL no es accesible desde internet (ver Paso 0) o está mal escrita (debe incluir `https://`). |
| `InfluxDB no devolvió datos…` | Measurement, field o tag mal escritos; o no hay datos recientes. Use `scripts/probar_conexion.py`. |
| `Se necesitan al menos N horas de datos…` | Hay pocos datos recientes; el sensor dejó de enviar o `HORAS_CONTEXTO` es muy bajo. |
| `El JSON no tiene los parámetros […]` | El JSON fue editado a mano o las órdenes no coinciden con los parámetros. Vuelva a exportar desde Colab. |
| `No hay modelo en models/sarima_config.json` | Falta el paso 6 o el paso 4 (demo). |
| El pronóstico se ve plano o desfasado | Revise `s` y la gráfica de evaluación del notebook; reentrene con más días. |
| Huecos largos en la serie | La API interpola huecos de hasta 6 h; si el sensor estuvo caído más tiempo, el pronóstico pierde calidad. |

---

## Reentrenar

Las condiciones cambian (estación del año, ubicación del sensor). Reentrene cada cierto tiempo repitiendo los pasos 5 y 6; la API no requiere cambios de código mientras el measurement/field sean los mismos.
