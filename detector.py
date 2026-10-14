
from datetime import datetime, timezone

def analizar_apuesta(deporte, evento, mercado, cuota, probabilidad):
    """Analiza una oportunidad simulada usando probabilidad decimal."""
    if cuota <= 1 or not 0 <= probabilidad <= 1:
        raise ValueError("Cuota o probabilidad inválida")

    probabilidad_implicita = 1 / cuota
    ev = (probabilidad * cuota - 1) * 100

    if ev > 3:
        decision = "PENDIENTE DE VERIFICACION"
        motivo = "EV potencial positivo; verificar datos y riesgo"
    else:
        decision = "DESESTIMADA"
        motivo = "EV insuficiente"

    return {
        "fecha_revision": datetime.now(timezone.utc).isoformat(),
        "deporte": deporte,
        "evento": evento,
        "mercado": mercado,
        "cuota": cuota,
        "probabilidad_estimada": probabilidad,
        "probabilidad_implicita": round(probabilidad_implicita, 4),
        "ev_porcentaje": round(ev, 2),
        "decision": decision,
        "motivo": motivo
    }


if __name__ == "__main__":
    print("Sistema EV Multideporte iniciado")
    print("Motor de cálculo listo; sin datos deportivos conectados.")
  
