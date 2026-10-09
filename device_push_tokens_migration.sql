-- Tokens de push de las apps nativas (numa-mobile, iOS/Android) vía Expo Push.
-- Aparte de user_notifications (Web Push de la PWA): un usuario puede tener
-- varios dispositivos, y un mismo token puede pasar de un usuario a otro si
-- se cierra sesión y entra otra cuenta en el mismo teléfono.
create table if not exists public.device_push_tokens (
  token text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  platform text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists device_push_tokens_user_id_idx
  on public.device_push_tokens (user_id);

-- Solo el backend (service key) la toca; sin políticas = nadie más accede.
alter table public.device_push_tokens enable row level security;
