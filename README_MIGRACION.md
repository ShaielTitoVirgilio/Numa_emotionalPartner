# Migración Railway → Render

Plan acordado: producción (`numa`) en Render Starter (~$7/mes, no se
duerme); staging (`numa-dev`) en Free (se duerme con inactividad, sin
usuarios reales así que no importa). Región Ohio (US-East) para los dos —
la que se probó y confirmó el ahorro de latencia real.

**Estrategia de corte:** primero probamos todo en la URL propia de Render
(`*.onrender.com`), con Railway todavía sirviendo `soynuma.app` en
paralelo. Recién cuando esté confirmado, cambiamos el DNS. Cero downtime,
se puede volver atrás en cualquier momento sin perder nada.

## Paso 1 — Crear los dos servicios (vos, ~5 min)

1. En el dashboard de Render: **New → Blueprint**.
2. Elegí el repo `Numa_emotionalPartner`, rama **`infra/migracion-render`**
   (ahí vive el `render.yaml` — no hace falta mergearlo a `staging`/`main`
   primero, cada servicio va a bajar el código real de la rama que le
   corresponde: `numa` de `main`, `numa-dev` de `staging`).
3. Render va a mostrar un preview con los DOS servicios (`numa` y
   `numa-dev`) — confirmá.

## Paso 2 — Cargar los secretos (vos — no puedo tipear API keys)

Para **cada uno de los dos servicios**, pestaña **Environment**, cargá
(sacando los valores de tu Railway actual, service por service — ojo que
**`numa` usa el Supabase de PRODUCCIÓN y `numa-dev` el de `numa-staging` —
son proyectos distintos, no copies el mismo valor en los dos**):

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `OPENROUTER_API_KEY`
- `GROQ_API_KEY`
- `CARTESIA_API_KEY`
- `ADMIN_KEY`
- `VAPID_PRIVATE_KEY`
- `SENTRY_DSN`

**Confirmame estos dos puntos sueltos antes o mientras cargás:**
- ¿`CHAT_PROVIDER_LLAMADA` / `CHAT_MODEL_LLAMADA` están seteados con algo en
  tu Railway actual, o vacíos? (`render.yaml` no los declaró — si tienen
  valor en Railway, hay que agregarlos a mano también).
- ¿`ADMIN_KEY` querés que sea la MISMA en los dos entornos, o diferente por
  servicio? (cualquiera de las dos es válida, es tu decisión).

El resto de las variables (proveedor/modelo, no son secretos) ya están
cargadas por `render.yaml` — no hace falta tocarlas.

## Paso 3 — Avisame

Cuando los dos digan **"Live"**, seguimos yo con las pruebas: voy a entrar a
las dos URLs de Render (`https://numa.onrender.com` y
`https://numa-dev.onrender.com`, o las que Render les haya puesto) y
probar login, chat, y el resto, antes de tocar el dominio real.

## Paso 4 (después, con todo confirmado) — Dominio real

Cuando `numa` esté probado y anduvo bien un tiempo:
1. En el servicio `numa` de Render: **Settings → Custom Domains → Add
   Custom Domain** → `soynuma.app`. Render te va a dar un registro DNS para
   agregar (CNAME o A, según cómo lo tengas armado hoy).
2. Recién ahí, en tu proveedor de DNS, actualizás ese registro — **ese es
   el momento real del corte**, lo hacemos juntos, no antes.
3. Con el corte confirmado y estable, pausamos/borramos el servicio viejo
   en Railway.

## Pendiente aparte (no bloquea esta migración)

`numa-mobile`'s `eas.json` tiene la URL de `numa-dev` hardcodeada
(`web-production-d2bc4d.up.railway.app`) — hay que actualizarla a la URL
nueva de Render cuando se arme el próximo build de `numa-mobile`. No es
urgente ahora mismo.
