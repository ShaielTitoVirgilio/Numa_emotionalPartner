-- ════════════════════════════════════════════════════════════════════
-- MEMORIA PROACTIVA — eventos con fecha sobre la tabla memories
-- ════════════════════════════════════════════════════════════════════
-- Un "event memory" es simplemente una fila de memories con event_date no nula.
-- Mantenemos todo en la misma tabla para reusar dedup, desactivación, RLS y el
-- borrado de cuenta (delete_all_user_data ya limpia memories).
--
-- Columnas:
--   event_date        → fecha real del evento (resuelta desde "el viernes", etc.)
--   event_title       → título corto del evento ("charla con el decano")
--   followed_up       → ya se conversó sobre el evento DESPUÉS de que ocurrió
--   reminder_push_sent→ ya se mandó el push de recordatorio (hoy/mañana) — anti-spam
--   followup_push_sent→ ya se mandó el push de follow-up (ayer/después) — anti-spam
--   last_proactive_at → última vez que se insertó en el prompt como mención proactiva
-- ════════════════════════════════════════════════════════════════════

alter table public.memories
  add column if not exists event_date         date,
  add column if not exists event_title        text,
  add column if not exists followed_up         boolean not null default false,
  add column if not exists reminder_push_sent  boolean not null default false,
  add column if not exists followup_push_sent  boolean not null default false,
  add column if not exists last_proactive_at   timestamptz;

-- Índice para get_proactive_memories: filtra por usuario + eventos activos con fecha.
create index if not exists idx_memories_event_date
  on public.memories (user_id, event_date)
  where event_date is not null and is_active = true;
