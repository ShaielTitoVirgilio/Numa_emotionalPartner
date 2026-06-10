# Plan técnico — Feature A (check-in) y Feature B (rating de ejercicios)

## Feature A — Check-in diario en el prompt

Ya cubierta por los archivos anteriores. Resumen de piezas:

1. **Backend carga**: `get_checkin_hoy_cached(user_id)` en `memory_service.py` (caché 5 min
   por usuario+fecha, ver `04_diff_chat_router.md`). Se invalida desde `checkin_router`
   al guardar un check-in.
2. **Prompt**: `_bloque_checkin()` + `CHECKIN_CALIBRACION` en `numa_prompt.py`
   (ver `03_codigo_routing.md`). Instrucción explícita de NO recitarlo ("vi que estás mal"
   suena a robot) — solo calibración interna.
3. **Routing**: `checkin_hoy` también alimenta las detecciones (`checkin=1` refuerza
   M11 triste; `checkin=4` refuerza M15 buenas noticias).
4. **Memoria**: no se guarda como memoria — el check-in ya persiste en `daily_checkins`
   y el dashboard lo usa; duplicarlo en `memories` generaría ruido en los patrones.
   (El spec decía "guardarlo como contexto del mood si corresponde" — propongo NO hacerlo;
   decime si lo querés igual.)

Costo: 1 query liviana por usuario cada 5 min. Sin cambios de frontend.

---

## Feature B — Rating 1–5 por ejercicio por usuario

### B.1 — SQL (correr en Supabase)

```sql
CREATE TABLE exercise_ratings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- FK a users_profiles (mismo patrón que memories y conversations).
    -- ON DELETE CASCADE: al borrar la cuenta se borran sus ratings.
    user_id     UUID NOT NULL REFERENCES public.users_profiles(id) ON DELETE CASCADE,
    exercise_id TEXT NOT NULL,
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    valor_texto TEXT,                   -- "positive_high" | "positive_low" | "neutral" | "negative"
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX exercise_ratings_user_exercise_idx ON exercise_ratings (user_id, exercise_id);
ALTER TABLE exercise_ratings ENABLE ROW LEVEL SECURITY;  -- igual que el resto de las tablas
```

> Verificado contra la base real (proyecto Supabase "NUMA"): los usuarios viven en
> `auth.users` y cada uno tiene su fila 1:1 en `public.users_profiles` (que a su vez tiene
> FK a `auth.users`). Las tablas de datos de la app (`memories`, `conversations`,
> `onboarding_answers`, `surveys`) referencian `users_profiles.id` — `exercise_ratings`
> sigue ese mismo patrón. El backend usa la service key, así que RLS habilitado no afecta
> al endpoint.

Mapeo opción → rating (vive en el frontend, en `feedbackPost.js`):
```
✨ positive_high → 5
🌿 positive_low  → 4
😐 neutral       → 3
😔 negative      → 2
Saltar / sin respuesta → no se registra
```

### B.2 — Backend: endpoint nuevo

En `app/routes/feedback_router.py` (ya existe ese router; no hace falta uno nuevo):

```python
class ExerciseRatingRequest(BaseModel):
    user_id: str
    exercise_id: str
    rating: int = Field(..., ge=1, le=5)
    valor_texto: Optional[str] = None

@router.post("/exercise-rating")
def guardar_rating(body: ExerciseRatingRequest):
    try:
        supabase.table("exercise_ratings").insert({
            "user_id":     body.user_id,
            "exercise_id": body.exercise_id,
            "rating":      body.rating,
            "valor_texto": body.valor_texto,
        }).execute()
        invalidate_patterns_cache(body.user_id)  # el rating es info de preferencia
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

(Si preferís mantener el patrón repository: método `save_exercise_rating(...)` en
`feedback_repository.py` y el router lo llama. Mismo contenido.)

### B.3 — Frontend: flujo nuevo del feedback

**Hoy:** motor → `mostrarFeedback(nombre, cb)` → `getRespuestaNuma(valor)` (frase enlatada,
sin LLM) → `recibirFeedbackEjercicio(texto, respuestaEnlatada, valor)` → historial local,
nada persiste.

**Propuesta:** la respuesta la genera el LLM con M26; el rating se persiste.

1. **`motorRespiracion.js` / `motorGuiado.js`** — pasar el ejercicio completo, no solo el
   nombre. Ambos motores ya tienen el objeto del ejercicio (`data` /
   `datosEjercicioActual`) con `id` y `nombre`:
```js
// motorGuiado.js — finalizarEjercicio()
const ej = datosEjercicioActual;   // { id, nombre, ... }
mostrarFeedback(ej.nombre, (valor, textoOpcion) => {
    if (_onFeedbackRespuesta) _onFeedbackRespuesta(textoOpcion, valor, ej);
});
// motorRespiracion.js — ídem con su objeto `data` (propagar `data` hasta finalizarRespiracion,
// que hoy solo recibe el nombre).
```
   Quien cablea `_onFeedbackRespuesta` (app.js/utils.js) propaga la nueva firma
   `(textoOpcion, valor, ejercicio)` — desaparece el parámetro `respuestaNuma`.

2. **`feedbackPost.js`** — agregar el mapeo y exportarlo:
```js
export const VALOR_A_RATING = { positive_high: 5, positive_low: 4, neutral: 3, negative: 2 };
```
   `getRespuestaNuma()` y `RESPUESTAS_NUMA` NO se borran: quedan como fallback offline.

3. **`chat.js`** — reescribir `recibirFeedbackEjercicio`:
```js
export async function recibirFeedbackEjercicio(textoOpcion, valor, ejercicio) {
  agregarMensaje(textoOpcion, "user");

  const numaUser = localStorage.getItem('numa_user');
  const userId = numaUser ? JSON.parse(numaUser).user_id : null;

  // 1) Persistir rating (fire-and-forget, no bloquea la respuesta)
  if (userId && ejercicio?.id && VALOR_A_RATING[valor]) {
    fetch("/exercise-rating", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        exercise_id: ejercicio.id,
        rating: VALOR_A_RATING[valor],
        valor_texto: valor,
      }),
    }).catch(e => console.warn("No se pudo guardar el rating:", e));
  }

  // 2) Respuesta REAL de Numa vía LLM (activa M26 en el backend)
  const mensajePost = `[Post-ejercicio | ${ejercicio?.nombre || "ejercicio"}] ${textoOpcion}`;
  _prepararEnvio();
  try {
    const data = await _llamarBackend(mensajePost);   // ya manda historial + perfil
    _procesarRespuesta(data, mensajePost);            // ya actualiza historial y mood
  } catch (error) {
    // Fallback: frase enlatada si falla la red (comportamiento actual)
    ocultarTyping();
    const respuestaFallback = getRespuestaNuma(valor);
    agregarMensaje(respuestaFallback, "oso", _valorAMood(valor));
    historialConversacion.push({ role: "user", content: mensajePost });
    historialConversacion.push({ role: "assistant", content: respuestaFallback });
    _trimHistorial();
  }
}
```
   Notas:
   - `_llamarBackend(mensajePost)` mete `[Post-ejercicio | nombre] ...` como último mensaje
     de `conversation` → el backend lo detecta con `startswith("[Post-ejercicio")` → M26.
   - El nombre del ejercicio viaja en el mensaje, así M26 puede personalizar.
   - La sugerencia de otro ejercicio queda naturalmente suprimida: M25 no se carga en
     contexto post-ejercicio y M26 ordena `suggested_action = null`.

### B.4 — Uso futuro del rating (fuera de alcance de esta tanda, dejado anotado)

Con datos acumulados, `construir_prompt()` puede recibir un resumen
(`AVG(rating) GROUP BY exercise_id` del usuario) e inyectar en M25: "a este usuario la
respiración box le funciona (4.7/5); el body scan no (2.0/5) — priorizá lo primero,
evitá lo segundo". No lo incluyo ahora para no agregar una query más sin datos reales.

### B.5 — Orden de implementación de Feature B

1. SQL en Supabase (manual o migración).
2. Endpoint en `feedback_router.py`.
3. M26 ya existe (punto 2 del plan general).
4. Frontend: motores → `feedbackPost.js` → `chat.js`.
5. Prueba manual: terminar una respiración, elegir cada una de las 4 opciones, verificar
   fila en `exercise_ratings` y respuesta contextual (no enlatada) en el chat.
