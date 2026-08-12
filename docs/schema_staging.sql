-- ============================================================
-- Esquema de Numa, replicado de producción (proyecto NUMA,
-- idbdvpykclbxdeoirsye) para el proyecto de staging (numa-staging,
-- kwzgvjxyfjwdqljtcgsd).
--
-- Generado leyendo el esquema REAL vía el MCP de Supabase (information_schema,
-- pg_policies, pg_indexes) el 2026-08-12 — no es una reconstrucción a ojo
-- desde el código. No hay un schema.sql versionado en el repo hasta ahora;
-- este archivo es el primero. Si el esquema de producción cambia, hay que
-- regenerar/actualizar esto a mano (no hay sincronización automática, ver
-- docs/entornos.md sección 5).
--
-- Faltan sin migrar (no existen en producción tampoco, dato de auth.users):
-- el esquema de auth (users, sessions, etc.) lo maneja Supabase Auth solo,
-- no hace falta crearlo.
-- ============================================================

-- ── Extensiones ──────────────────────────────────────────────
create extension if not exists pgcrypto with schema extensions;   -- gen_random_uuid()
create extension if not exists vector with schema extensions;      -- memories.embedding


-- ── users_profiles ───────────────────────────────────────────
create table public.users_profiles (
  id uuid primary key references auth.users(id),
  onboarding_completo boolean default false,
  created_at timestamptz default now(),
  nombre text,
  prefiere_respuestas text default 'equilibradas'::text,
  pronombres text,
  como_reacciona text,
  preferencias_extra text,
  etapa_vida text,
  que_le_pesa text,
  apple_sub text unique
);

alter table public.users_profiles enable row level security;

create policy "Enable all for service role" on public.users_profiles
  for all to public using (true) with check (true);
create policy "Usuarios solo ven sus datos" on public.users_profiles
  for select to authenticated using (auth.uid() = id);


-- ── conversations ────────────────────────────────────────────
create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users_profiles(id),
  role text not null check (role = any (array['user'::text, 'assistant'::text])),
  content text not null,
  mood text,
  created_at timestamptz default now()
);

create index idx_conversations_user_mood
  on public.conversations (user_id, created_at desc) where (mood is not null);

alter table public.conversations enable row level security;

create policy "Allow insert" on public.conversations
  for insert to authenticated with check (auth.uid() = user_id);
create policy "Allow select own" on public.conversations
  for select to authenticated using (auth.uid() = user_id);
create policy "Users can read own conversations" on public.conversations
  for select to authenticated using (auth.uid() = user_id);
create policy "Usuario crea sus propias conversaciones" on public.conversations
  for insert to public with check (auth.uid() = user_id);
create policy "Usuario ve sus propias conversaciones" on public.conversations
  for select to public using (auth.uid() = user_id);


-- ── memories ─────────────────────────────────────────────────
create table public.memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users_profiles(id),
  content text not null,
  category text default 'general'::text,
  priority integer default 3,
  is_active boolean default true,
  source text default 'chat'::text,
  embedding extensions.vector(1536),
  created_at timestamptz default now(),
  -- Memoria proactiva (eventos con fecha, temas abiertos, recursos) —
  -- ver memories_event_migration.sql / docs proactive memory.
  event_date date,
  event_title text,
  followed_up boolean not null default false,
  reminder_push_sent boolean not null default false,
  followup_push_sent boolean not null default false,
  last_proactive_at timestamptz,
  status text not null default 'none'::text
    check (status = any (array['none'::text, 'open'::text, 'closed'::text])),
  helped_before boolean not null default false
);

create index idx_memories_event_date on public.memories (user_id, event_date)
  where (event_date is not null and is_active = true);
create index idx_memories_open_topics on public.memories (user_id, created_at)
  where (status = 'open'::text and is_active = true);
create index idx_memories_recursos on public.memories (user_id, created_at)
  where (helped_before = true and is_active = true);
create index memories_embedding_idx on public.memories
  using ivfflat (embedding vector_cosine_ops) with (lists = '100');

alter table public.memories enable row level security;

create policy "Allow insert" on public.memories
  for insert to authenticated with check (auth.uid() = user_id);
create policy "Allow select own" on public.memories
  for select to authenticated using (auth.uid() = user_id);
create policy "Allow update own" on public.memories
  for update to authenticated using (auth.uid() = user_id);
create policy "Users manage own memories" on public.memories
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Usuario actualiza sus propias memorias" on public.memories
  for update to public using (auth.uid() = user_id);
create policy "Usuario crea sus propias memorias" on public.memories
  for insert to public with check (auth.uid() = user_id);
create policy "Usuario ve sus propias memorias" on public.memories
  for select to public using (auth.uid() = user_id);


-- ── onboarding_answers ───────────────────────────────────────
create table public.onboarding_answers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.users_profiles(id),
  pregunta_numero integer not null,
  pregunta text not null,
  respuesta text not null,
  created_at timestamptz default now()
);

alter table public.onboarding_answers enable row level security;

create policy "Allow insert" on public.onboarding_answers
  for insert to authenticated with check (auth.uid() = user_id);
create policy "Usuario crea sus propias respuestas" on public.onboarding_answers
  for insert to public with check (auth.uid() = user_id);
create policy "Usuario ve sus propias respuestas" on public.onboarding_answers
  for select to public using (auth.uid() = user_id);


-- ── daily_checkins ───────────────────────────────────────────
-- Sin FK a propósito (igual que en producción): el user_id es un uuid suelto.
create table public.daily_checkins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  mood_value smallint not null check (mood_value >= 1 and mood_value <= 4),
  mood_emoji text not null,
  checkin_date date not null default current_date,
  created_at timestamptz default now(),
  unique (user_id, checkin_date)
);

create index idx_daily_checkins_user_date
  on public.daily_checkins (user_id, checkin_date desc);

alter table public.daily_checkins enable row level security;

create policy "Users can insert own checkins" on public.daily_checkins
  for insert to public with check (auth.uid() = user_id);
create policy "Users can update own checkins" on public.daily_checkins
  for update to public using (auth.uid() = user_id);
create policy "Users can view own checkins" on public.daily_checkins
  for select to public using (auth.uid() = user_id);


-- ── exercise_ratings ─────────────────────────────────────────
create table public.exercise_ratings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users_profiles(id),
  exercise_id text not null,
  rating integer not null check (rating >= 1 and rating <= 5),
  valor_texto text,
  created_at timestamptz default now()
);

create index exercise_ratings_user_exercise_idx
  on public.exercise_ratings (user_id, exercise_id);

alter table public.exercise_ratings enable row level security;
-- Sin políticas explícitas en producción: con RLS activado y sin policy,
-- solo service_role puede acceder (que es como el backend siempre entra).


-- ── crisis_logs ──────────────────────────────────────────────
create table public.crisis_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id),
  mensaje_usuario text,
  categoria text not null,
  notas_equipo text,
  log_level text not null default 'high'::text,
  revisado boolean default false,
  created_at timestamptz not null default now()
);

create index idx_crisis_created on public.crisis_logs (created_at desc);
create index idx_crisis_level on public.crisis_logs (log_level);
create index idx_crisis_revisado on public.crisis_logs (revisado) where (revisado = false);
create index idx_crisis_user on public.crisis_logs (user_id);

alter table public.crisis_logs enable row level security;

create policy "Users manage own crisis logs" on public.crisis_logs
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "service_role_crisis_all" on public.crisis_logs
  for all to public using (true) with check (true);


-- ── crisis_pendientes ────────────────────────────────────────
-- Sin FK a propósito (igual que en producción).
create table public.crisis_pendientes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,
  mensaje_preview text,
  categoria text,
  log_level text,
  revisado boolean,
  created_at timestamptz default now()
);

alter table public.crisis_pendientes enable row level security;
-- Sin políticas explícitas en producción: solo service_role accede.


-- ── user_notifications ───────────────────────────────────────
create table public.user_notifications (
  user_id uuid primary key references auth.users(id),
  subscription_data jsonb not null,
  created_at timestamptz default timezone('utc'::text, now())
);

alter table public.user_notifications enable row level security;

create policy "User can delete own notifications" on public.user_notifications
  for delete to authenticated using (user_id = auth.uid());
create policy "User can insert own notifications" on public.user_notifications
  for insert to authenticated with check (user_id = auth.uid());
create policy "User can update own notifications" on public.user_notifications
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "User can view own notifications" on public.user_notifications
  for select to authenticated using (user_id = auth.uid());


-- ── user_feedback ────────────────────────────────────────────
create table public.user_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id),
  texto text,
  rating smallint check (rating >= 1 and rating <= 5),
  rating_recomendaria smallint check (rating_recomendaria >= 1 and rating_recomendaria <= 5),
  created_at timestamptz not null default now()
);
comment on column public.user_feedback.rating_recomendaria is
  '¿Recomendarías o usarías Numa? (1-5). Pregunta separada de "rating" (opinión general).';

create index idx_user_feedback_created on public.user_feedback (created_at desc);
create index idx_user_feedback_user on public.user_feedback (user_id);

alter table public.user_feedback enable row level security;

create policy "service_role_all" on public.user_feedback
  for all to public using (true) with check (true);
