"""
Acceso a InfluxDB 2.x con el cliente oficial `influxdb-client` y consultas Flux.

La función principal, `leer_serie_horaria`, devuelve una pd.Series con índice
horario regular (UTC, sin zona) lista para alimentar el SARIMA. Es la MISMA
lógica que usa el notebook de Colab para entrenar, así el modelo ve en
producción datos preparados igual que en el entrenamiento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from influxdb_client import InfluxDBClient

from . import config

_client: InfluxDBClient | None = None


def get_client() -> InfluxDBClient:
    """Crea el cliente una sola vez y lo reutiliza."""
    global _client
    if _client is None:
        _client = InfluxDBClient(
            url=config.INFLUX_URL,
            token=config.INFLUX_TOKEN,
            org=config.INFLUX_ORG,
            timeout=30_000,
        )
    return _client


def cerrar_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def construir_flux(horas: int) -> str:
    """Consulta Flux: últimas `horas` horas, promedio por hora."""
    filtro_tag = ""
    if config.INFLUX_TAG_KEY and config.INFLUX_TAG_VALUE:
        filtro_tag = (f'\n  |> filter(fn: (r) => r["{config.INFLUX_TAG_KEY}"] == '
                      f'"{config.INFLUX_TAG_VALUE}")')
    return f'''
from(bucket: "{config.INFLUX_BUCKET}")
  |> range(start: -{horas + 2}h)
  |> filter(fn: (r) => r["_measurement"] == "{config.INFLUX_MEASUREMENT}")
  |> filter(fn: (r) => r["_field"] == "{config.INFLUX_FIELD}"){filtro_tag}
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false, timeSrc: "_start")
  |> keep(columns: ["_time", "_value"])
  |> sort(columns: ["_time"])
'''


def preparar_serie_horaria(tiempos, valores, horas: int) -> pd.Series:
    """
    Convierte (tiempos, valores) en una serie horaria regular:
      1. Índice en UTC sin zona horaria (statsmodels lo prefiere así).
      2. Si hay varias tablas (varios tags), promedia por hora.
      3. Descarta la hora en curso (está incompleta).
      4. Rellena huecos cortos por interpolación.
    """
    if len(tiempos) == 0:
        return pd.Series(dtype=float, name="valor")

    idx = pd.to_datetime(pd.Series(tiempos), utc=True).dt.tz_localize(None)
    s = pd.Series(np.asarray(valores, dtype=float), index=pd.DatetimeIndex(idx), name="valor")
    s = s.groupby(level=0).mean().sort_index()

    hora_actual = pd.Timestamp.now(tz="UTC").tz_localize(None).floor("h")
    s = s[s.index < hora_actual]
    if s.empty:
        return s

    rango = pd.date_range(s.index.min(), s.index.max(), freq="h")
    s = s.reindex(rango).interpolate(method="time", limit=6).ffill().bfill()
    s.index.name = "tiempo"
    return s.iloc[-horas:].asfreq("h")


def leer_serie_horaria(horas: int) -> pd.Series:
    """Lee las últimas `horas` horas (o datos sintéticos en DEMO_MODE)."""
    if config.DEMO_MODE:
        return serie_demo(horas)

    tablas = get_client().query_api().query(construir_flux(horas), org=config.INFLUX_ORG)
    tiempos, valores = [], []
    for tabla in tablas:
        for registro in tabla.records:
            if registro.get_value() is not None:
                tiempos.append(registro.get_time())
                valores.append(registro.get_value())
    return preparar_serie_horaria(tiempos, valores, horas)


def serie_demo(horas: int, semilla: int = 7) -> pd.Series:
    """Serie sintética tipo temperatura: ciclo diario + ruido."""
    fin = pd.Timestamp.now(tz="UTC").tz_localize(None).floor("h") - pd.Timedelta(hours=1)
    idx = pd.date_range(end=fin, periods=horas, freq="h")
    hora_local = (idx.hour - 5) % 24          # Medellín UTC-5: pico ~15:00 local
    rng = np.random.default_rng(semilla + int(fin.timestamp() // 3600))
    valores = 22 + 5 * np.sin(2 * np.pi * (hora_local - 9) / 24) + rng.normal(0, 0.6, horas)
    s = pd.Series(valores, index=idx, name="valor")
    s.index.name = "tiempo"
    return s.asfreq("h")
