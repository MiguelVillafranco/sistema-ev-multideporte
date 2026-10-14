
import os
import json
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError

BASE_URL = "https://api.the-odds-api.com/v4"

API_KEY = os.environ.get("ODDS_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")


def consultar_api(ruta, parametros):
    if not API_KEY:
        raise RuntimeError("Falta ODDS_API_KEY")

    parametros = dict(parametros)
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


def guardar_eventos(eventos, deporte):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY"
        )

    registros = []

    for evento in eventos:
        if not evento.get("id") or not evento.get("commence_time"):
            continue

        registros.append({
            "evento_externo_id": evento["id"],
            "deporte": deporte,
            "liga": deporte,
            "equipo_local": evento.get("home_team"),
            "equipo_visitante": evento.get("away_team"),
            "fecha_partido": evento["commence_time"],
            "estado": "PROGRAMADO"
        })

    if not registros:
        print("No hay eventos válidos para guardar.")
        return 0

    endpoint = (
        SUPABASE_URL
        + "/rest/v1/eventos?"
        + urlencode({
            "on_conflict": "deporte,evento_externo_id"
        })
    )

    datos = json.dumps(registros).encode("utf-8")

    solicitud = Request(
        endpoint,
        data=datos,
        headers={
            "apikey": SUPABASE_KEY,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,"
                      "return=minimal"
        },
        method="POST"
    )

    try:
        with urlopen(solicitud, timeout=30) as respuesta:
            if respuesta.status not in (200, 201, 204):
                raise RuntimeError(
                    f"Respuesta inesperada: {respuesta.status}"
                )

    except HTTPError as error:
        detalle = error.read().decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"Error guardando eventos en Supabase: "
            f"HTTP {error.code}: {detalle}"
        ) from error

    return len(registros)


def ejecutar():
    ahora = datetime.now(timezone.utc).isoformat()

    print("Sistema EV Multideporte")
    print("Consulta:", ahora)

    deportes = obtener_deportes()
    print("Deportes disponibles:", len(deportes))

    # Primera etapa: NBA para controlar
    # el consumo de solicitudes de la API.
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

    guardados = guardar_eventos(cuotas, deporte)

    print("Eventos enviados a Supabase:", guardados)
    print("Prueba terminada.")
    print("Aún no se calculan oportunidades +EV.")


if __name__ == "__main__":
    ejecutar()
