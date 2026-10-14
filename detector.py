import os
import json
from datetime import datetime, timezone
from statistics import median
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import HTTPError

BASE_URL = "https://api.the-odds-api.com/v4"
API_KEY = os.environ.get("ODDS_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
DEPORTE = "basketball_nba"  # Prueba controlada para limitar consumo de API
UMBRAL_EV = 3.0
MIN_CASAS_REFERENCIA = 3


def peticion_json(url, datos=None, headers=None, metodo=None):
    solicitud = Request(url, data=datos, headers=headers or {}, method=metodo)
    try:
        with urlopen(solicitud, timeout=30) as respuesta:
            contenido = respuesta.read()
            return json.loads(contenido) if contenido else None
    except HTTPError as error:
        detalle = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {detalle}") from error


def consultar_api(ruta, parametros):
    if not API_KEY:
        raise RuntimeError("Falta ODDS_API_KEY")
    parametros = dict(parametros)
    parametros["apiKey"] = API_KEY
    return peticion_json(BASE_URL + ruta + "?" + urlencode(parametros))


def obtener_cuotas(deporte):
    return consultar_api(f"/sports/{deporte}/odds/", {
        "regions": "us", "markets": "h2h", "oddsFormat": "decimal"
    })


def supabase_post(tabla, registros, conflicto=None, devolver=False):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
    if not registros:
        return [] if devolver else 0
    endpoint = SUPABASE_URL + "/rest/v1/" + tabla
    if conflicto:
        endpoint += "?" + urlencode({"on_conflict": conflicto})
    preferencias = ["return=representation" if devolver else "return=minimal"]
    if conflicto:
        preferencias.insert(0, "resolution=merge-duplicates")
    resultado = peticion_json(
        endpoint,
        datos=json.dumps(registros).encode("utf-8"),
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": "Bearer " + SUPABASE_KEY,
            "Content-Type": "application/json",
            "Prefer": ",".join(preferencias),
        },
        metodo="POST",
    )
    return resultado if devolver else len(registros)


def guardar_eventos(eventos, deporte):
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
            "estado": "PROGRAMADO",
        })
    # Obtener identificadores internos para relacionar las observaciones.
    if not registros:
        return {}
    supabase_post("eventos", registros, conflicto="deporte,evento_externo_id")
    ids = [registro["evento_externo_id"] for registro in registros]
    endpoint = SUPABASE_URL + "/rest/v1/eventos?" + urlencode({
        "select": "id,evento_externo_id",
        "deporte": "eq." + deporte,
        "evento_externo_id": "in.(" + ",".join(ids) + ")",
    })
    filas = peticion_json(endpoint, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
    })
    return {fila["evento_externo_id"]: fila["id"] for fila in filas}


def extraer_casas(evento):
    casas = []
    for casa in evento.get("bookmakers", []):
        for mercado in casa.get("markets", []):
            if mercado.get("key") != "h2h":
                continue
            precios = {}
            for seleccion in mercado.get("outcomes", []):
                nombre = seleccion.get("name")
                precio = seleccion.get("price")
                if nombre and isinstance(precio, (int, float)) and precio > 1:
                    precios[nombre] = float(precio)
            if len(precios) >= 2:
                casas.append({
                    "nombre": casa.get("title") or casa.get("key") or "Desconocida",
                    "clave": casa.get("key") or casa.get("title") or "desconocida",
                    "precios": precios,
                })
    return casas


def analizar_evento(evento, evento_id):
    casas = extraer_casas(evento)
    registros = []
    for casa_objetivo in casas:
        for seleccion, cuota in casa_objetivo["precios"].items():
            probabilidades = []
            for referencia in casas:
                if referencia["clave"] == casa_objetivo["clave"]:
                    continue  # Evita estimar una cuota usando esa misma casa.
                precios = referencia["precios"]
                if seleccion not in precios:
                    continue
                suma_implicitas = sum(1 / valor for valor in precios.values())
                if suma_implicitas <= 0:
                    continue
                probabilidades.append((1 / precios[seleccion]) / suma_implicitas)

            probabilidad = median(probabilidades) if len(probabilidades) >= MIN_CASAS_REFERENCIA else None
            implicita = 1 / cuota
            ev = (probabilidad * cuota - 1) * 100 if probabilidad is not None else None
            if probabilidad is None:
                decision = "RECHAZADA"
                motivo = "Referencias insuficientes para estimar probabilidad"
            elif ev > UMBRAL_EV:
                decision = "OBSERVADA"
                motivo = "EV de consenso >3%; requiere validacion independiente"
            else:
                decision = "RECHAZADA"
                motivo = "EV de consenso no supera el umbral de 3%"

            registros.append({
                "evento_id": evento_id,
                "mercado": "h2h",
                "seleccion": seleccion,
                "casa_apuestas": casa_objetivo["nombre"],
                "cuota": round(cuota, 4),
                "probabilidad_estimada": round(probabilidad, 6) if probabilidad is not None else None,
                "probabilidad_implicita": round(implicita, 6),
                "ev_porcentaje": round(ev, 4) if ev is not None else None,
                "incertidumbre": "ALTA: estimacion de consenso de mercado, no modelo independiente",
                "decision": decision,
                "motivo_decision": motivo,
                "fuente_cuota": "The Odds API v4",
                "fuente_probabilidad": "Mediana de otras casas sin margen (The Odds API v4)" if probabilidad is not None else "Insuficiente",
                "modalidad": "SIMULADA",
            })
    return registros


def ejecutar():
    print("Sistema EV Multideporte - prueba NBA")
    print("Consulta:", datetime.now(timezone.utc).isoformat())
    cuotas = obtener_cuotas(DEPORTE)
    print("Eventos encontrados:", len(cuotas))
    mapa_ids = guardar_eventos(cuotas, DEPORTE)
    print("Eventos registrados o actualizados:", len(mapa_ids))

    observaciones = []
    for evento in cuotas:
        evento_id = mapa_ids.get(evento.get("id"))
        if evento_id is not None:
            observaciones.extend(analizar_evento(evento, evento_id))

    # Cada ejecución crea observaciones fechadas; no son apuestas ejecutadas.
    for inicio in range(0, len(observaciones), 100):
        supabase_post("oportunidades", observaciones[inicio:inicio + 100])

    candidatas = sum(fila["decision"] == "OBSERVADA" for fila in observaciones)
    print("Observaciones guardadas:", len(observaciones))
    print("Candidatas para revision independiente:", candidatas)
    print("Ninguna candidata se considera +EV confirmado ni apuesta realizada.")


if __name__ == "__main__":
    ejecutar()
