
import os
import json
from datetime import datetime, timezone
from urllib.request import urlopen
from urllib.parse import urlencode

BASE_URL = "https://api.the-odds-api.com/v4"
API_KEY = os.environ.get("ODDS_API_KEY")


def consultar_api(ruta, parametros):
    if not API_KEY:
        raise RuntimeError("Falta ODDS_API_KEY")

    parametros["apiKey"] = API_KEY
    url = BASE_URL + ruta + "?" + urlencode(parametros)

    with urlopen(url, timeout=30) as respuesta:
        return json.load(respuesta)


def obtener_deportes():
    return consultar_api("/sports/", {})


def obtener_cuotas(deporte):
    return consultar_api(
        f"/sports/{deporte}/odds/",
        {
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "decimal"
        }
    )


def ejecutar():
    ahora = datetime.now(timezone.utc).isoformat()
    deportes = obtener_deportes()

    print("Sistema EV Multideporte")
    print("Consulta:", ahora)
    print("Deportes disponibles:", len(deportes))

    # Primera prueba: solo un deporte para
    # limitar el consumo de la API.
    deporte = "basketball_nba"

    cuotas = obtener_cuotas(deporte)

    print("Deporte:", deporte)
    print("Eventos encontrados:", len(cuotas))

    for evento in cuotas[:5]:
        print(
            evento.get("home_team"),
            "vs",
            evento.get("away_team"),
            "| Inicio:",
            evento.get("commence_time"),
            "| Casas:",
            len(evento.get("bookmakers", []))
        )

    print("Prueba terminada.")
    print("Aún no se calculan oportunidades +EV.")


if __name__ == "__main__":
    ejecutar()
