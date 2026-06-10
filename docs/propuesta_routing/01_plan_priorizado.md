# Propuesta Numa — Prompt-Routing + Features A/B

> Estado: **PROPUESTA — nada de esto está implementado todavía.**
> Archivos de esta propuesta:
> - `01_plan_priorizado.md` — este archivo (orden de trabajo + decisiones a aprobar)
> - `02_modulos.md` — los 26 módulos completos (el diccionario `MODULOS` listo para pegar)
> - `03_codigo_routing.md` — `seleccionar_modulos()`, detecciones, `construir_prompt()`, cambios a `crisis_detector.py`
> - `04_diff_chat_router.md` — diff de `chat_router.py`
> - `05_features_AB.md` — plan técnico Feature A (check-in) y Feature B (rating de ejercicios)
> - `06_claude_md_fix.md` — corrección del bug de documentación

---

## 1. Lista priorizada de cambios

| # | Cambio | Archivos | Por qué este orden |
|---|--------|----------|--------------------|
| 1 | **Mejorar `crisis_detector.py`**: score continuo 0.0–1.0 + frases implícitas nuevas ("ya lo decidí", "nadie me va a extrañar", despedidas) | `app/crisis_detector.py` | Es el insumo del routing (M19/M20/M21). Sin score no hay router de riesgo. |
| 2 | **Reescribir `numa_prompt.py`**: `NUMA_BASE` desaparece → `MODULOS` (26 módulos) + `seleccionar_modulos()` + 8 funciones de detección + nueva `construir_prompt()` | `app/numa_prompt.py` | El corazón de la tarea. Resuelve los problemas 1 (interrogatorio), 2 (repetición), 3 (conexión humana) y 4 (permiso) con módulos dedicados (M04, M05, M06, M07) que dejan de competir con texto irrelevante. |
| 3 | **Actualizar `chat_router.py`**: pasar los nuevos parámetros (`crisis_score`, `ultimo_modulo_critico`, `historial_reciente`, `mood_actual`, `ultimo_mensaje`, `checkin_hoy`) | `app/routes/chat_router.py` | Conecta el router al flujo real. |
| 4 | **Feature A — check-in en el prompt**: cargar `daily_checkins` de hoy (con caché 5 min) e inyectar `_bloque_checkin()` | `chat_router.py`, `numa_prompt.py` | Chico y de alto impacto; Numa hoy ignora el check-in. |
| 5 | **Feature B — rating 1–5 por ejercicio**: tabla `exercise_ratings`, endpoint `POST /exercise-rating`, frontend manda `[Post-ejercicio \| nombre]` al `/chat` real (M26) en vez de frase enlatada | SQL, `feedback_router.py`, `feedback_repository.py`, `feedbackPost.js`, `chat.js`, `motorRespiracion.js`, `motorGuiado.js` | Depende del módulo M26 (punto 2) y del endpoint nuevo. |
| 6 | **Fix `CLAUDE.md`**: formato viejo `memory`/`memory_category` singular → `memories[]` plural | `CLAUDE.md` | Trivial, va al final. |

---

## 2. Decisiones de diseño que necesito que apruebes

Estas son las cosas donde el spec dejaba un hueco o donde propongo desviarme levemente de él. Todo lo demás sigue el spec al pie de la letra.

### D1 — `CRISIS_OVERFLOW` deja de tener respuesta hardcodeada
Hoy "no aguanto más" / "quiero desaparecer" devuelven una frase enlatada sin pasar por el LLM. Propongo: **el early-return hardcodeado queda SOLO para `critical`/`high`** (método, ideación, autolesión — seguridad determinística). `CRISIS_OVERFLOW` pasa al LLM con score 0.45 → activa **M19 (crisis implícita)** y responde contextual, que es exactamente lo que la guía pide ("conectar antes de derivar"). Si preferís conservar el hardcode para overflow, el cambio es una línea.

### D2 — `mood_actual` lo manda el frontend
El backend es stateless y el request no trae el mood del turno anterior. Opciones: (a) query extra a `conversations`, o (b) el frontend ya tiene `data.mood` de cada respuesta → lo guarda y lo manda como `ultimo_mood` en el body. Propongo **(b)**: cero queries extra, un campo opcional nuevo en `ChatRequest`.

### D3 — `ultimo_modulo_critico` se calcula del historial, sin estado
No hay sesión en el server. Propongo: correr el score de crisis sobre los **últimos 2 mensajes previos del usuario** que ya vienen en `conversation`. Si alguno da ≥ 0.35 → `ultimo_modulo_critico=True` → se activa M21 (post-contención). Stateless, sin tabla nueva, sin query.

### D4 — Duplicación del spec resuelta: M23/M24 vs bloques dinámicos
El esqueleto del spec inyecta **M23** y además `_bloque_inicio_sesion()` (mismo contenido dos veces). Propongo: M23 ES el bloque de inicio de sesión (se elimina el bloque suelto). Para reenganche: **M24** contiene las instrucciones estáticas y `_bloque_reenganche()` queda solo con la parte dinámica (la memoria elegida + los días).

### D5 — Fix al early-return de post-ejercicio del spec
El `seleccionar_modulos()` del spec hace `return` para post-ejercicio **antes** de agregar M02 (tono), M03 (longitud) y M08 (memoria). La respuesta al feedback quedaría sin la voz de Numa. Propongo agregar esos tres antes del return.

### D6 — Orden final: M09 (formato JSON) al final del prompt
El spec lo pone en el medio del core. Los LLM atienden más al inicio y al final: crisis primero, **el contrato de salida JSON último**. `_deduplicar_y_ordenar()` aplica un orden canónico que garantiza eso.

### D7 — FK de `exercise_ratings` ✅ RESUELTA (verificada contra la base real)
El SQL del spec referenciaba `auth.users(id)`. Inspeccionada la base del proyecto Supabase
"NUMA": los usuarios están en `auth.users`, con perfil 1:1 en `public.users_profiles`
(FK a `auth.users`). Las tablas de datos de la app (`memories`, `conversations`,
`onboarding_answers`, `surveys`) referencian **`users_profiles.id`**, no `auth.users`
directamente. `exercise_ratings` sigue ese mismo patrón:
`user_id UUID NOT NULL REFERENCES public.users_profiles(id) ON DELETE CASCADE`
(el CASCADE acompaña al endpoint de borrado de cuenta). SQL final en `05_features_AB.md`.

---

## 3. Cómo el diseño supera los 4 problemas detectados

1. **Interrogatorio (~80% preguntas)** → M04 es módulo core, siempre presente, segundo en el orden (solo detrás de crisis): regla dura ≤50%, prohibición tras 2 "?" seguidos, las 4 alternativas con ejemplos BIEN/MAL.
2. **Repetición textual** → M05 core: prohibición absoluta + qué hacer cuando el usuario rescata una frase + qué hacer ante "ya me lo dijiste".
3. **Conexión humana ausente** → M06 core (módulo nuevo): regla "casi siempre nombrar el valor de abrirse con otro", con la puerta-no-reto y el caso "no tengo a nadie".
4. **Sin mecanismo de permiso** → M07 core: pedir permiso → si habilita → recomendación con disclaimer de IA + posibilidad-no-verdad.
5. **Bug CLAUDE.md** → punto 6.
