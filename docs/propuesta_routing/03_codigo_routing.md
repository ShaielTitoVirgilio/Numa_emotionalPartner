# Código completo del routing

Dos archivos afectados: `app/crisis_detector.py` (paso 1) y `app/numa_prompt.py` (pasos 2-5).

---

## Paso 1 — `crisis_detector.py`: score continuo + señales implícitas

Cambios:
1. `CrisisResult` gana el campo `score: float`.
2. Nueva lista `IMPLICIT_RISK_PHRASES` (señales sin palabra directa — hoy invisibles para el detector).
3. Los niveles existentes mapean a score; las implícitas dan 0.40 (zona M19).
4. **Decisión D1**: `CRISIS_OVERFLOW` y las implícitas devuelven `detected=False` con score > 0 — es decir, NO hacen early-return: van al LLM con el módulo de riesgo activado. Solo método/ideación/autolesión siguen hardcodeados.

```python
# Agregar al CrisisResult:
class CrisisResult(TypedDict):
    detected: bool
    category: Optional[str]
    message: str
    resources: list[str]
    log_level: str       # "none" | "low" | "medium" | "high" | "critical"
    score: float         # NUEVO: 0.0-1.0, señal continua para el routing


# Nueva lista — señales implícitas (sección 6 de la guía):
IMPLICIT_RISK_PHRASES = [
    "ya lo decidí", "ya lo decidi",
    "no tiene caso seguir", "no tiene caso ya",
    "ya me voy", "este es mi último mensaje", "este es mi ultimo mensaje",
    "no quiero hablar más, solo voy a hacerlo", "solo voy a hacerlo",
    "nadie me va a extrañar", "nadie me extrañaría", "nadie me extranaria",
    "ya no importa nada", "nada va a cambiar nunca",
    "gracias por todo", "adiós a todos", "adios a todos",
    "ya está todo dicho", "ya esta todo dicho",
    "es la última vez que hablo", "es la ultima vez que hablo",
]

SCORE_POR_CATEGORIA = {
    "SUICIDE_METHOD":    0.95,
    "SUICIDAL_IDEATION": 0.85,
    "SELF_HARM":         0.65,
    "CRISIS_OVERFLOW":   0.45,
    "IMPLICIT_RISK":     0.40,
}
```

```python
def detectar_crisis(mensaje: str) -> CrisisResult:
    texto = mensaje.lower().strip()

    # ── 1. Método suicida (hardcoded, early-return) ──────────
    if _contiene(texto, SUICIDE_METHOD_PHRASES):
        resp = random.choice(RESPONSES_METHOD)
        return CrisisResult(
            detected=True, category="SUICIDE_METHOD",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="critical", score=SCORE_POR_CATEGORIA["SUICIDE_METHOD"],
        )

    # ── 2. Ideación suicida (hardcoded, early-return) ────────
    if _contiene(texto, SUICIDAL_IDEATION_PHRASES):
        resp = random.choice(RESPONSES_IDEATION)
        return CrisisResult(
            detected=True, category="SUICIDAL_IDEATION",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="critical", score=SCORE_POR_CATEGORIA["SUICIDAL_IDEATION"],
        )

    # ── 3. Autolesión (hardcoded, early-return) ──────────────
    if _contiene(texto, SELF_HARM_PHRASES):
        resp = random.choice(RESPONSES_SELF_HARM)
        return CrisisResult(
            detected=True, category="SELF_HARM",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="high", score=SCORE_POR_CATEGORIA["SELF_HARM"],
        )

    # ── 4. Desborde severo → AL LLM con M19 activado (D1) ────
    if _contiene(texto, CRISIS_OVERFLOW_PHRASES):
        return CrisisResult(
            detected=False, category="CRISIS_OVERFLOW",
            message="", resources=[],
            log_level="medium", score=SCORE_POR_CATEGORIA["CRISIS_OVERFLOW"],
        )

    # ── 5. Señales implícitas → AL LLM con M19 activado ──────
    if _contiene(texto, IMPLICIT_RISK_PHRASES):
        return CrisisResult(
            detected=False, category="IMPLICIT_RISK",
            message="", resources=[],
            log_level="medium", score=SCORE_POR_CATEGORIA["IMPLICIT_RISK"],
        )

    return CrisisResult(
        detected=False, category=None, message="",
        resources=[], log_level="none", score=0.0,
    )
```

> Nota: si rechazás D1, los bloques 4-5 vuelven a `detected=True` con la respuesta
> hardcodeada y el score igual sirve para M21 en el turno siguiente.

---

## Pasos 2-3 — `numa_prompt.py`: selector + detecciones

El archivo queda: `MODULOS` (ver `02_modulos.md`) + lo que sigue + los bloques dinámicos
existentes refactorizados a funciones `_bloque_*` (mismo contenido que hoy).

```python
# ══════════════════════════════════════════════════════════════
# ROUTING DE MÓDULOS
# ══════════════════════════════════════════════════════════════

# Orden canónico del prompt final: crisis arriba de todo, contrato JSON al final (D6).
_ORDEN_CANONICO = [
    "M20_crisis_explicita",
    "M19_crisis_implicita",
    "M21_post_contencion",
    "M01_persona_core",
    "M04_regla_preguntas",
    "M05_variedad_no_repeticion",
    "M06_conexion_humana",
    "M07_consejo_y_permiso",
    "M22_primer_mensaje_app",
    "M23_inicio_sesion_con_memoria",
    "M24_reenganche_inactividad",
    "M26_feedback_post_ejercicio",
    "M18_duelo_y_perdida",
    "M11_estado_triste_vacio",
    "M12_estado_ansioso_estresado",
    "M13_estado_abrumado",
    "M14_estado_enojado",
    "M15_buenas_noticias",
    "M10_calibracion_emocional_general",
    "M16_psicoeducacion",
    "M17_usuario_se_cierra",
    "M25_ejercicios_disponibles",
    "M02_tono_y_voz",
    "M03_longitud_y_estructura",
    "M08_memoria_reglas",
    "M09_formato_salida_json",   # el contrato cierra el prompt
]
_ORDEN_IDX = {mid: i for i, mid in enumerate(_ORDEN_CANONICO)}


def seleccionar_modulos(
    ultimo_mensaje: str,
    historial_reciente: list[dict],
    num_interacciones: int,
    mood_actual: str | None,
    checkin_hoy: int | None,
    es_primera_vez: bool,
    es_inicio_sesion: bool,
    tiene_memorias: bool,
    dias_inactivo: int,
    crisis_score: float,
    ultimo_modulo_critico: bool,
) -> list[str]:
    """Devuelve la lista ordenada de IDs de módulos a inyectar. Siempre múltiples."""
    modulos: list[str] = []

    # ── CRISIS primero ───────────────────────────────────────
    if crisis_score >= 0.60:
        modulos.append("M20_crisis_explicita")
    elif crisis_score >= 0.35:
        modulos.append("M19_crisis_implicita")

    if ultimo_modulo_critico:
        modulos.append("M21_post_contencion")

    # ── CORE ─────────────────────────────────────────────────
    modulos += [
        "M01_persona_core",
        "M04_regla_preguntas",
        "M05_variedad_no_repeticion",
        "M06_conexion_humana",
        "M07_consejo_y_permiso",
        "M09_formato_salida_json",
    ]

    # ── SESIÓN ───────────────────────────────────────────────
    if es_primera_vez:
        modulos.append("M22_primer_mensaje_app")
    elif es_inicio_sesion and tiene_memorias:
        modulos.append("M23_inicio_sesion_con_memoria")

    if dias_inactivo >= 5:
        modulos.append("M24_reenganche_inactividad")

    # ── POST-EJERCICIO (corta el resto — fix D5: con tono/voz) ──
    if ultimo_mensaje.strip().startswith("[Post-ejercicio"):
        modulos.append("M26_feedback_post_ejercicio")
        modulos += ["M02_tono_y_voz", "M03_longitud_y_estructura", "M08_memoria_reglas"]
        return _deduplicar_y_ordenar(modulos)

    # ── DETECCIÓN DE CONTEXTO EMOCIONAL ──────────────────────
    es_pregunta_info    = _detectar_pregunta_informativa(ultimo_mensaje)
    es_usuario_cerrado  = _detectar_usuario_cerrado(historial_reciente)
    es_duelo            = _detectar_duelo(ultimo_mensaje, historial_reciente)
    hay_buenas_noticias = _detectar_buenas_noticias(ultimo_mensaje, mood_actual, checkin_hoy)
    es_enojado          = _detectar_enojo(ultimo_mensaje, mood_actual)
    es_abrumado         = _detectar_abrumado(ultimo_mensaje, mood_actual)
    es_triste_vacio     = _detectar_tristeza_vacio(ultimo_mensaje, mood_actual, checkin_hoy)
    es_ansioso          = _detectar_ansioso(ultimo_mensaje, mood_actual, checkin_hoy)

    # ── SITUACIONALES EMOCIONALES (excluyentes; orden = prioridad) ──
    if es_duelo:
        modulos.append("M18_duelo_y_perdida")
    elif es_triste_vacio:
        modulos.append("M11_estado_triste_vacio")
    elif es_ansioso:
        modulos.append("M12_estado_ansioso_estresado")
    elif es_abrumado:
        modulos.append("M13_estado_abrumado")
    elif es_enojado:
        modulos.append("M14_estado_enojado")
    elif hay_buenas_noticias:
        modulos.append("M15_buenas_noticias")
    else:
        modulos.append("M10_calibracion_emocional_general")

    # ── SITUACIONALES DE CONTEXTO ────────────────────────────
    if es_pregunta_info:
        modulos.append("M16_psicoeducacion")
    if es_usuario_cerrado:
        modulos.append("M17_usuario_se_cierra")

    # ── EJERCICIOS ───────────────────────────────────────────
    # No ofrecer ejercicios en contexto de riesgo: compiten con la contención.
    if num_interacciones >= 4 and crisis_score < 0.35:
        modulos.append("M25_ejercicios_disponibles")

    # ── FONDO (tono, longitud, memoria) ──────────────────────
    modulos += ["M02_tono_y_voz", "M03_longitud_y_estructura", "M08_memoria_reglas"]

    return _deduplicar_y_ordenar(modulos)


def _deduplicar_y_ordenar(modulos: list[str]) -> list[str]:
    """Dedup + orden canónico (crisis primero, contrato JSON al final)."""
    unicos = list(dict.fromkeys(modulos))
    return sorted(unicos, key=lambda m: _ORDEN_IDX.get(m, 99))
```

### Funciones de detección (completas, sin stubs)

Las del spec, adoptadas con tres ajustes: (1) `_detectar_buenas_noticias` no se dispara por
checkin solo si el texto es negativo — el checkin 😄 es señal débil, va al final; (2)
`_detectar_usuario_cerrado` ignora mensajes `[Post-ejercicio...]`; (3) keywords con
variantes sin tilde donde faltaban.

```python
def _detectar_pregunta_informativa(mensaje: str) -> bool:
    """True si el usuario pide información/explicación, no habla de sí mismo."""
    texto = mensaje.lower().strip()
    TRIGGERS = [
        "qué es", "que es", "qué son", "que son",
        "por qué me pasa", "por que me pasa",
        "cómo funciona", "como funciona",
        "cómo se llama", "como se llama",
        "explicame", "explicá", "explica",
        "contame qué", "contame que",
        "qué significa", "que significa",
        "dame opciones", "dame ejemplos",
        "qué diferencia", "que diferencia", "cuál es la diferencia", "cual es la diferencia",
    ]
    return any(t in texto for t in TRIGGERS)


def _detectar_usuario_cerrado(historial: list[dict]) -> bool:
    """True si el usuario respondió ≤4 palabras en 2 de sus últimos 3 mensajes."""
    mensajes_usuario = [
        m["content"] for m in historial
        if m.get("role") == "user" and not str(m.get("content", "")).startswith("[Post-ejercicio")
    ][-3:]
    if len(mensajes_usuario) < 2:
        return False
    cortos = sum(1 for m in mensajes_usuario if len(m.split()) <= 4)
    return cortos >= 2


def _detectar_duelo(mensaje: str, historial: list[dict]) -> bool:
    texto = mensaje.lower()
    KEYWORDS = [
        "falleció", "fallecio", "murió", "murio", "se murió", "se murio",
        "se fue para siempre", "lo perdí", "la perdí", "lo perdi", "la perdi",
        "duelo", "me quedé sin", "me quede sin", "ya no está", "ya no esta",
        "extraño mucho", "extrano mucho", "lo echo de menos",
        "funeral", "velorio", "entierro", "se me fue",
    ]
    return any(k in texto for k in KEYWORDS)


def _detectar_buenas_noticias(mensaje: str, mood: str | None, checkin: int | None) -> bool:
    texto = mensaje.lower()
    KEYWORDS = [
        "aprobé", "aprobe", "me aprobaron", "me tomaron",
        "conseguí trabajo", "consegui trabajo", "me llamaron", "quedé en", "quede en",
        "gané", "gane", "me salió", "me salio", "lo logré", "lo logre",
        "por fin", "al final pude", "me fue bien",
        "estoy feliz", "estoy contento", "estoy contenta", "re bien",
        "buenas noticias", "te cuento algo bueno",
    ]
    if any(k in texto for k in KEYWORDS):
        return True
    if mood in ("happy", "excited"):
        return True
    return bool(checkin and checkin >= 4)


def _detectar_enojo(mensaje: str, mood: str | None) -> bool:
    texto = mensaje.lower()
    KEYWORDS = [
        "estoy re caliente", "me tiene podrido", "me tiene podrida",
        "me cagó", "me cago", "una bronca", "qué bronca", "que bronca",
        "me enojé", "me enoje", "odio", "no lo soporto", "me hizo mierda",
        "estoy harto", "estoy harta", "me tiene harto", "me tiene harta",
        "rabia", "furia", "me explotó", "me exploto", "me revientan", "estoy furioso", "estoy furiosa",
    ]
    return any(k in texto for k in KEYWORDS)


def _detectar_abrumado(mensaje: str, mood: str | None) -> bool:
    if mood == "overwhelmed":
        return True
    texto = mensaje.lower()
    KEYWORDS = [
        "no puedo más", "no puedo mas", "demasiado", "todo junto",
        "no llego", "me desbordó", "me desbordo", "no doy más", "no doy mas",
        "me explota la cabeza", "no sé por dónde empezar", "no se por donde empezar",
        "me ahogo", "me superó", "me supero", "estoy al límite", "al limite",
    ]
    return any(k in texto for k in KEYWORDS)


def _detectar_tristeza_vacio(mensaje: str, mood: str | None, checkin: int | None) -> bool:
    if mood == "sad":
        return True
    if checkin == 1:
        return True
    texto = mensaje.lower()
    KEYWORDS = [
        "me siento vacío", "me siento vacio", "me siento vacía", "me siento vacia",
        "no le veo sentido", "no tiene sentido", "nada importa", "para qué", "para que",
        "estoy bajón", "estoy bajon", "estoy mal", "ánimo por el piso", "animo por el piso",
        "me siento solo", "me siento sola", "no tengo ganas",
        "lloré", "llore", "me pesan", "sin energía", "sin energia",
        "agotado", "agotada", "desesperanza",
    ]
    return any(k in texto for k in KEYWORDS)


def _detectar_ansioso(mensaje: str, mood: str | None, checkin: int | None) -> bool:
    if mood in ("anxious", "stressed"):
        return True
    texto = mensaje.lower()
    KEYWORDS = [
        "ansiedad", "ansioso", "ansiosa", "me agarró pánico", "me agarro panico",
        "ataque de pánico", "ataque de panico",
        "no puedo respirar", "taquicardia", "me tiemblan",
        "nervioso", "nerviosa", "estoy agitado", "estoy agitada",
        "no puedo parar de pensar", "me da vueltas", "rumiando",
        "estrés", "estres", "estresado", "estresada", "me estreso",
        "preocupado", "preocupada",
    ]
    return any(k in texto for k in KEYWORDS)
```

---

## Pasos 4-5 — nueva `construir_prompt()` + bloque check-in

Los bloques dinámicos actuales (ubicación, perfil, reenganche dinámico, memorias,
patrones, contexto de sesión) se extraen tal cual a funciones `_bloque_ubicacion()`,
`_bloque_perfil()`, `_bloque_reenganche()`, `_bloque_memorias()`, `_bloque_patrones()`,
`_bloque_contexto_sesion()` — mismo texto que hoy, sin cambios de contenido, **salvo**:
- `_bloque_inicio_sesion()` desaparece (lo cubre M23 — decisión D4).
- `_bloque_reenganche()` queda solo con la parte dinámica (M24 tiene las instrucciones):

```python
def _bloque_reenganche(memorias, dias_inactivo) -> str:
    candidatas = []
    for m in memorias:
        if isinstance(m, dict):
            contenido = (m.get("content") or "").strip()
            prioridad = m.get("priority") or 3
        else:
            contenido, prioridad = str(m).strip(), 3
        if contenido:
            candidatas.append((prioridad, contenido))
    if not candidatas:
        return ""
    candidatas.sort(key=lambda x: x[0], reverse=True)
    memoria_reenganche = candidatas[0][1]
    semanas = dias_inactivo // 7
    dias_str = f"{dias_inactivo} días" if dias_inactivo < 14 else f"unas {semanas} semanas"
    return (
        f"DATOS DE REENGANCHE:\n"
        f"- El usuario lleva {dias_str} sin usar la app.\n"
        f'- Memoria disponible para reenganchar (usar según las instrucciones de reenganche): "{memoria_reenganche}"'
    )
```

```python
CHECKIN_CALIBRACION = {
    1: ("😔", "marcó que está mal hoy",
        "Calibrá tu presencia hacia más cálida y más paciente. "
        "No lo menciones como dato ('vi que estás mal'). Solo dejate guiar por eso internamente."),
    2: ("😐", "marcó que está más o menos hoy",
        "Tono neutro, ni excesivamente animado ni excesivamente cuidadoso. "
        "Dejá que la conversación te diga a dónde ir."),
    3: ("🙂", "marcó que está bien hoy",
        "Podés ser más liviano si el tema lo permite. No fuerces profundidad si está tranquilo."),
    4: ("😄", "marcó que está muy bien hoy",
        "Si trae algo bueno, celebralo sin análisis. Sé natural y alegre. "
        "No fuerces lo emocional pesado."),
}

def _bloque_checkin(checkin_hoy: int) -> str:
    if checkin_hoy not in CHECKIN_CALIBRACION:
        return ""
    emoji, descripcion, instruccion = CHECKIN_CALIBRACION[checkin_hoy]
    return (
        f"ESTADO DEL DÍA (check-in de hoy: {emoji}):\n"
        f"El usuario {descripcion}.\n"
        f"{instruccion}\n"
        "IMPORTANTE: no lo menciones explícitamente. Solo usalo para calibrar internamente."
    )
```

```python
def construir_prompt(
    perfil=None,
    memorias=None,
    num_interacciones=0,
    es_primera_vez=False,
    patrones=None,
    es_inicio_sesion=False,
    ubicacion=None,
    dias_inactivo=0,
    checkin_hoy: int | None = None,
    crisis_score: float = 0.0,
    ultimo_modulo_critico: bool = False,
    historial_reciente: list | None = None,
    mood_actual: str | None = None,
    ultimo_mensaje: str = "",
) -> str:
    tiene_memorias = bool(memorias)

    modulos_ids = seleccionar_modulos(
        ultimo_mensaje=ultimo_mensaje,
        historial_reciente=historial_reciente or [],
        num_interacciones=num_interacciones,
        mood_actual=mood_actual,
        checkin_hoy=checkin_hoy,
        es_primera_vez=es_primera_vez,
        es_inicio_sesion=es_inicio_sesion,
        tiene_memorias=tiene_memorias,
        dias_inactivo=dias_inactivo,
        crisis_score=crisis_score,
        ultimo_modulo_critico=ultimo_modulo_critico,
    )

    secciones = [MODULOS[mid] for mid in modulos_ids if mid in MODULOS]

    # ── Bloques dinámicos (contexto personalizado) ──────────
    if ubicacion and (ubicacion.get("ciudad") or ubicacion.get("pais")):
        secciones.append(_bloque_ubicacion(ubicacion))
    if perfil:
        b = _bloque_perfil(perfil)
        if b:
            secciones.append(b)
    if dias_inactivo >= 5 and tiene_memorias:
        b = _bloque_reenganche(memorias, dias_inactivo)
        if b:
            secciones.append(b)
    if tiene_memorias:
        secciones.append(_bloque_memorias(memorias))
    if patrones:
        secciones.append(_bloque_patrones(patrones))
    if checkin_hoy is not None:
        b = _bloque_checkin(checkin_hoy)
        if b:
            secciones.append(b)

    # ── Contexto de sesión (datos operativos, al final) ─────
    secciones.append(_bloque_contexto_sesion(num_interacciones, es_primera_vez))

    return "\n\n---\n\n".join(s for s in secciones if s)
```

### Cuántos módulos carga un mensaje típico

| Contexto | Módulos | vs hoy |
|---|---|---|
| Charla neutra, sesión avanzada | M01,04,05,06,07 + M10 + M25 + M02,03,08,09 = 11 | NUMA_BASE entero (~530 líneas) siempre |
| Usuario triste, inicio de sesión | M01,04,05,06,07 + M23 + M11 + M02,03,08,09 = 11 | ídem |
| Post-ejercicio | M01,04,05,06,07 + M26 + M02,03,08,09 = 10 | ídem |
| Crisis implícita | M19 + core + M02,03,08,09 (sin M25) | ídem, sin jerarquía |
