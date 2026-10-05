-- ════════════════════════════════════════════════════════════════════
-- ENCUESTA "Danos tu opinión" — respuestas por pregunta (JSON)
-- ════════════════════════════════════════════════════════════════════
-- Las preguntas de la encuesta van a seguir cambiando, así que las respuestas
-- se guardan en una sola columna jsonb en vez de una columna por pregunta:
-- cambiar las preguntas no obliga a migrar la tabla.
--
--   respuestas → {"version": 1, "valoracion": 4, "sentir_despues": "algo_mejor",
--                 "sin_numa": "amigos_familia", "valora": ["privacidad"],
--                 "mejora": "texto libre"}
--                `version` identifica el set de preguntas (ver
--                frontend-móvil: src/data/encuestaPreguntas.ts).
--
-- rating y texto se siguen llenando (valoracion y mejora) para que
-- /admin/feedback y cualquier consulta vieja sigan funcionando.
--
-- Idempotente: se puede correr más de una vez. ⚠️ Correrla ANTES de desplegar
-- el backend: POST /feedback no falla si la columna no existe (devuelve ok con
-- warning), así que un deploy adelantado perdería respuestas en silencio.
-- ════════════════════════════════════════════════════════════════════

alter table public.user_feedback
  add column if not exists respuestas jsonb;
