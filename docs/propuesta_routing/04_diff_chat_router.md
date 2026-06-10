# Diff de `app/routes/chat_router.py`

Cambios: (1) campo nuevo `ultimo_mood` en el request (D2), (2) early-return solo para
`critical`/`high` (D1), (3) cálculo stateless de `ultimo_modulo_critico` (D3),
(4) carga del check-in de hoy, (5) nuevos parámetros a `construir_prompt()`.

```diff
 from app.memory_service import (
     get_recent_memories,
     get_topic_patterns_cached,
     invalidate_patterns_cache,
     deactivate_event_memories,
     detectar_evento_proximo,
     get_dias_inactivo,
+    get_checkin_hoy_cached,
     MEMORY_WINDOW_DAYS_DEFAULT,
 )
```

```diff
 class ChatRequest(BaseModel):
     conversation: List[Message]
     user_id: Optional[str] = None
     perfil: Optional[Dict[str, Any]] = None
     ubicacion: Optional[UbicacionData] = None
+    ultimo_mood: Optional[str] = None   # mood del último turno del LLM (lo manda el frontend)
```

```diff
         ultimo_mensaje = body.conversation[-1].content if body.conversation else ""
         crisis = detectar_crisis(ultimo_mensaje)
+        crisis_score = crisis.get("score", 0.0)

-        if crisis["detected"]:
-            if crisis["log_level"] in ("critical", "high"):
-                background_tasks.add_task(
-                    feedback_repo.save_crisis_log,
-                    body.user_id,
-                    ultimo_mensaje,
-                    crisis["category"],
-                    crisis["log_level"],
-                )
+        if crisis["detected"]:
+            # Solo critical/high llegan acá (método, ideación, autolesión):
+            # respuesta determinística, sin LLM.
+            background_tasks.add_task(
+                feedback_repo.save_crisis_log,
+                body.user_id,
+                ultimo_mensaje,
+                crisis["category"],
+                crisis["log_level"],
+            )
             return {
                 "message":          crisis["message"],
                 "mood":             "sad",
                 "suggested_action": None,
                 "risk_level":       "high",
                 "nuevas_memorias":  None,
             }
+
+        # Señal media (overflow/implícitas): va al LLM con M19/M20 activado.
+        # Loguear también las medias para tener trazabilidad.
+        if crisis_score >= 0.35 and crisis.get("category"):
+            background_tasks.add_task(
+                feedback_repo.save_crisis_log,
+                body.user_id,
+                ultimo_mensaje,
+                crisis["category"],
+                crisis["log_level"],
+            )
```

```diff
         es_inicio_sesion = len(body.conversation) == 1
         num_interacciones = len(body.conversation)

         # Primera vez: primer mensaje de la sesión Y sin memorias previas de otras sesiones
         es_primera_vez = (num_interacciones == 1 and not memorias_vigentes)

         # Detectar reenganche: >5 días sin actividad
         dias_inactivo = 0
         if body.user_id and num_interacciones <= 4:
             # Solo consultamos al principio de la sesión para no repetir la llamada
             dias_inactivo = get_dias_inactivo(body.user_id)

+        # ¿El turno anterior estuvo en territorio de crisis? (stateless, D3)
+        # Se mira el score de los últimos 2 mensajes previos del usuario en el historial.
+        ultimo_modulo_critico = False
+        previos_usuario = [m.content for m in body.conversation[:-1] if m.role == "user"][-2:]
+        for msg_previo in previos_usuario:
+            if detectar_crisis(msg_previo).get("score", 0.0) >= 0.35:
+                ultimo_modulo_critico = True
+                break
+
+        # Check-in del día (Feature A) — cacheado 5 min en memory_service
+        checkin_hoy = None
+        if body.user_id:
+            try:
+                checkin_hoy = get_checkin_hoy_cached(body.user_id)
+            except Exception as e:
+                print(f"⚠️ No se pudo cargar el check-in: {e}")
+
+        # Últimos 4 mensajes del historial para las detecciones del router
+        historial_reciente = [m.model_dump() for m in body.conversation[-4:]]

         system_prompt = construir_prompt(
             perfil=perfil,
             memorias=memorias_vigentes,
             patrones=patrones,
             es_inicio_sesion=es_inicio_sesion,
             num_interacciones=num_interacciones,
             es_primera_vez=es_primera_vez,
             ubicacion=body.ubicacion.model_dump() if body.ubicacion else None,
             dias_inactivo=dias_inactivo,
+            checkin_hoy=checkin_hoy,
+            crisis_score=crisis_score,
+            ultimo_modulo_critico=ultimo_modulo_critico,
+            historial_reciente=historial_reciente,
+            mood_actual=body.ultimo_mood,
+            ultimo_mensaje=ultimo_mensaje,
         )
```

```diff
-        # Si llegamos acá, crisis["detected"] fue False (el early return arriba lo garantiza)
-        risk_level = "none"
+        # Si llegamos acá no hubo early-return; reportar el nivel real de señal
+        if crisis_score >= 0.35:
+            risk_level = "medium"
+        else:
+            risk_level = "none"
```

### Helper nuevo en `memory_service.py` (Feature A)

```python
# Caché de check-in por usuario: (user_id, fecha) → mood_value
_CHECKIN_CACHE: Dict[Tuple[str, str], Tuple[float, Optional[int]]] = {}
_CHECKIN_TTL_SECONDS = 300

def get_checkin_hoy_cached(user_id: str) -> Optional[int]:
    """mood_value (1-4) del check-in de hoy, o None. Cacheado 5 min."""
    from datetime import date
    hoy = date.today().isoformat()
    key = (user_id, hoy)
    now = time.time()
    cached = _CHECKIN_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]

    res = (
        supabase.table("daily_checkins")
        .select("mood_value")
        .eq("user_id", user_id)
        .eq("checkin_date", hoy)
        .limit(1)
        .execute()
    )
    valor = (res.data or [{}])[0].get("mood_value") if res.data else None
    _CHECKIN_CACHE[key] = (now + _CHECKIN_TTL_SECONDS, valor)
    return valor

def invalidate_checkin_cache(user_id: str) -> None:
    """Llamar desde checkin_router al guardar un check-in nuevo."""
    from datetime import date
    _CHECKIN_CACHE.pop((user_id, date.today().isoformat()), None)
```

> En `checkin_router.crear_checkin()` se agrega `invalidate_checkin_cache(body.user_id)`
> después del upsert, para que el chat lo vea al instante.

### Frontend (D2 — `ultimo_mood`)

En `chat.js`:
```diff
 let perfilCacheado = null;
+let ultimoMood = null;   // mood de la última respuesta de Numa

   // en _llamarBackend():
     body: JSON.stringify({
       conversation: conversationToSend,
       user_id: userId,
       perfil: perfilCacheado,
+      ultimo_mood: ultimoMood,
     })

   // en _procesarRespuesta():
   const mood = data.mood || 'neutral';
+  ultimoMood = mood;
```
