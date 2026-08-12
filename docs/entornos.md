# Entornos: producción y NumaDev (pruebas)

Guía para tener un lugar donde probar cambios **con el celular, como un usuario
real**, antes de que toquen a nadie. Lo que ya está hecho en el código está
marcado ✅; lo que falta necesita tu cuenta y lo hacés vos.

---

## El mapa

```
                    ┌─ rama main ──────→ Railway "numa"      ─→ Supabase PRODUCCIÓN
   tu repo          │                    soynuma.app                 (usuarios reales)
                    │
                    └─ rama staging ───→ Railway "numa-dev"  ─→ Supabase PRUEBAS
                                         numa-dev.up.railway.app      (datos descartables)
```

Las dos apps móviles salen del mismo repo `numa-mobile`, cambiando el perfil de
build de EAS (`preview` = pruebas, `production` = real).

**La regla que no se rompe:** el entorno de pruebas **nunca** apunta a la base de
producción. Si lo hiciera, cada mensaje de prueba escribiría memorias,
conversaciones y `crisis_logs` sobre usuarios reales.

---

## Lo que ya está listo en el código ✅

| Qué | Dónde |
|---|---|
| Variable `APP_ENTORNO` (`production` / `staging`) | `app/core/config.py` |
| La PWA se instala como **"Numa DEV"**, ícono aparte | `serve_manifest()` en `app/main.py` |
| Franja naranja "STAGING — datos de prueba" en pantalla | `frontend/modules/entorno.js` |
| Endpoint `/api/entorno` | `app/main.py` |
| Todas las variables documentadas | `.env.example` |
| Sentry con scrubbing de datos sensibles | `app/core/observability.py` |
| El `user_id` se adjunta a los errores de Sentry | `app/core/auth.py` |
| Verificador de Sentry | `scripts/verificar_sentry.py` |
| URL del backend configurable por perfil de build | `numa-mobile/src/constants.ts` + `eas.json` |

---

## 1. Sentry (30 minutos, gratis)

Hoy la app atrapa 22 tipos de error distintos y **no te enterás de ninguno**.

1. Creá una cuenta en [sentry.io](https://sentry.io) → proyecto nuevo → plataforma **FastAPI**.
2. Copiá el DSN (`https://…@…ingest.sentry.io/…`).
3. Ponelo en el `.env` local y en las variables de Railway:

```
SENTRY_DSN=<tu dsn>
SENTRY_ENVIRONMENT=production      # en numa-dev poné: staging
SENTRY_TRACES_SAMPLE_RATE=0.1      # 10% de requests con datos de performance
```

4. Comprobá que llega de verdad:

```bash
venv/bin/python scripts/verificar_sentry.py
```

Manda 2 errores de prueba y **verifica antes que no se filtre nada privado**
(body, cookies, headers de auth). Si algún check falla, corta y no reporta.

`SENTRY_TRACES_SAMPLE_RATE=0.1` es lo que te va a mostrar a qué se van los
segundos **con usuarios reales**, no en tu máquina.

---

## 2. Backend de pruebas (NumaDev)

### 2.1 Base de datos separada ✅ ya hecho

Proyecto `numa-staging` creado (`kwzgvjxyfjwdqljtcgsd`, región `us-west-2` —
producción está en `sa-east-1`; quedó así porque se creó antes de fijar esto,
no afecta funcionalidad, solo un pelín de latencia extra al medir tiempos).

El esquema completo (10 tablas, políticas RLS, índices, extensión `pgvector`)
se replicó leyendo la estructura REAL de producción vía el MCP de Supabase y
se aplicó a staging. Queda versionado en `schema_staging.sql` (raíz del repo)
por si hay que reconstruirlo alguna vez. **No hay sincronización automática**:
si el esquema de producción cambia, hay que actualizar ese archivo a mano y
reaplicarlo.

Credenciales de `numa-staging`:
```
SUPABASE_URL=https://kwzgvjxyfjwdqljtcgsd.supabase.co
SUPABASE_SERVICE_KEY=<Settings → API → service_role — no se puede sacar por MCP, andá al dashboard>
```

> No reutilices el proyecto de producción "filtrando por usuario de prueba".
> Un bug en una query de prueba te toca datos reales.

**Deuda técnica encontrada en el camino (existe en producción, no se tocó):**
varias tablas (`conversations`, `memories`, `onboarding_answers`, `crisis_logs`,
`users_profiles`) tienen políticas RLS duplicadas que hacen lo mismo — reflejo
de migraciones que se fueron acumulando. `get_advisors` las señala como
`multiple_permissive_policies`/`auth_rls_initplan` (funcionan bien, solo son
más lentas de lo necesario a escala). Se replicaron tal cual para que staging
sea un espejo fiel; limpiarlas es un trabajo aparte, sobre producción, con su
propio cuidado.

### 2.2 Rama y servicio

```bash
git checkout -b staging
git push -u origin staging
```

En Railway: **New Service** → mismo repo → branch `staging` → nombre `numa-dev`.
Variables (tomá `.env.example` como lista):

```
APP_ENTORNO=staging
SUPABASE_URL=<el de staging>
SUPABASE_SERVICE_KEY=<el de staging>
SENTRY_ENVIRONMENT=staging
ADMIN_KEY=<uno distinto al de producción>
… (las claves de LLM pueden ser las mismas)
```

### 2.3 Instalarla en el celular

Abrí la URL de `numa-dev` en el celular → "Agregar a pantalla de inicio".
Queda como **"Numa DEV"**, un ícono separado de Numa, con franja naranja.
Eso es tu Expo Go para la web: sin build y sin store.

---

## 3. App móvil de pruebas

Ya tenías el perfil `preview` con `distribution: internal` en `eas.json`: eso
genera un build real instalable por link, sin App Store. Lo que faltaba era que
apuntara al backend de pruebas, y eso ya quedó configurable.

1. En `eas.json`, reemplazá los `REEMPLAZAR_POR_…` de los perfiles
   `development` y `preview` por la URL de `numa-dev` y las credenciales del
   Supabase de staging.
2. Build de pruebas:

```bash
cd /Users/mac/Numa/numa-mobile
eas build --profile preview --platform ios
```

3. EAS te da un link para instalar en el celu. Esa app pega contra NumaDev.
4. Para producción no cambia nada: `eas build --profile production`.

**Verificá siempre a dónde apunta un build** antes de confiar en él: el perfil
`production` es el único con la URL real, y está escrita explícita en `eas.json`.

---

## 4. El flujo de todos los días

```
1. Trabajás en local            →  uvicorn app.main:app --reload
2. Push a staging               →  Railway despliega numa-dev solo
3. Probás en el celu con "Numa DEV" (datos descartables)
4. Si está bien: merge a main   →  Railway despliega producción
```

Para el móvil, entre el 2 y el 3 va un `eas build --profile preview` (o un
`eas update --channel preview` si el cambio es solo de JS, que es instantáneo y
no requiere build nuevo).

---

## 5. Lo que falta y no está resuelto

- **Métricas de producto propias** (cuánto tardó cada etapa, qué modelo
  respondió, qué módulos del prompt se activaron): la idea es una tabla en
  Supabase escrita en background y consultada desde el `/dashboard` que ya
  existe. Todavía no está hecho.
- **Errores del frontend**: si la PWA revienta en el celular de alguien, no te
  enterás. Sentry tiene SDK de browser; habría que sumarlo con la misma
  política de privacidad que el del backend.
- **Migraciones de esquema**: hoy no hay un mecanismo para mantener el Supabase
  de staging sincronizado con el de producción. Por ahora es a mano.
