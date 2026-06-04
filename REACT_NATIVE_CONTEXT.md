# Contexto para nueva sesión — Migración Numa a React Native

Pegá este documento entero al inicio de la nueva sesión de Claude Code.

---

## Qué es Numa

App de apoyo emocional con IA. El usuario habla con "Numa" (un oso panda 🐼), que responde con empatía, guarda memorias de las conversaciones y sugiere ejercicios de bienestar. Actualmente es una PWA (FastAPI + Vanilla JS). El objetivo es migrar el frontend a React Native (Expo) manteniendo el backend intacto.

---

## Backend — NO se toca

**URL producción:** `https://web-production-3f4e4.up.railway.app`

El backend es FastAPI en Python, deployado en Railway. El frontend nuevo en React Native se conecta a esa URL. No hay que modificar ningún archivo del backend.

---

## Todos los endpoints

### Auth

**POST /register**
```json
// Request
{ "email": "string", "password": "string", "nombre": "string" }
// Response 200
{ "message": "Usuario creado correctamente", "user_id": "uuid" }
// Response 400 — email ya registrado
{ "detail": "Este email ya está registrado. Probá iniciando sesión." }
```

**POST /login**
```json
// Request
{ "email": "string", "password": "string" }
// Response 200
{
  "user_id": "uuid",
  "email": "string",
  "access_token": "jwt",
  "refresh_token": "string"
}
// Response 401
{ "detail": "Email o contraseña incorrectos" }
```

**POST /verify-email** — verifica OTP de 8 dígitos enviado por Supabase
```json
// Request
{ "email": "string", "token": "string" }
// Response 200 — misma forma que /login
{ "user_id": "uuid", "email": "string", "access_token": "jwt", "refresh_token": "string" }
// Response 400
{ "detail": "Código inválido o expirado" }
```

**POST /refresh**
```json
// Request
{ "refresh_token": "string" }
// Response 200 — misma forma que /login
```

**GET /profile/{user_id}**
```json
// Response 200
{
  "id": "uuid",
  "nombre": "string",
  "onboarding_completo": true,
  "pronombres": "string|null",
  "etapa_vida": "string|null",
  "que_le_pesa": "string|null",
  "como_reacciona": "string|null",
  "preferencias_extra": "string|null"
}
// Si no existe perfil devuelve: { "onboarding_completo": false }
```

### Onboarding

**POST /onboarding**
```json
// Request
{
  "user_id": "uuid",
  "answers": [
    { "pregunta_numero": 1, "pregunta": "string", "respuesta": "string" },
    // ... hasta pregunta 6
  ]
}
// Response 200
{ "message": "Onboarding guardado correctamente" }
```

Las 6 preguntas del onboarding (en orden):
1. "¿Cómo querés que te llame?" — texto libre
2. "¿Con qué pronombres te sentís más cómodo/a?" — opción única: Él / Ella / Prefiero que no use pronombres / Otro
3. "¿Cómo está tu vida ahora mismo?" — opción múltiple: Estudiando / Trabajando / Buscando trabajo / Con familia o pareja / Viviendo solo/a / Otra etapa
4. "¿Qué es lo que más te pesa últimamente?" — opción múltiple: El rendimiento / Las relaciones / No saber hacia dónde voy / El cuerpo o la salud / Nada en particular / Otro
5. "En momentos de estrés, ¿qué te pasa?" — opción múltiple: Me acelero / Me cierro / Me enojo / Busco distracción / Me cuesta darme cuenta
6. "¿Hay algo que querés que Numa sepa antes de empezar?" — textarea libre

### Chat

**POST /chat** — Rate limit: 18/minuto
```json
// Request
{
  "conversation": [
    { "role": "user", "content": "string" },
    { "role": "assistant", "content": "string" }
    // historial completo de la sesión
  ],
  "user_id": "uuid",          // opcional pero importante para memorias
  "perfil": null              // siempre null, el backend lo carga solo
}
// Response 200
{
  "message": "string",        // respuesta de Numa
  "mood": "neutral|calm|happy|excited|stressed|overwhelmed|sad|anxious",
  "suggested_action": "string|null",  // ID de ejercicio sugerido, o null
  "risk_level": "none|high",
  "nuevas_memorias": [        // puede ser null o array
    { "content": "string", "category": "string", "priority": 1-5 }
  ]
}
```

`suggested_action` puede ser uno de estos IDs: `respiracion_box`, `respiracion_478`, `respiracion_balance`, `respiracion_suspiro`, `respiracion_exhale`, `respiracion_activante`, `meditacion_bodyscan`, `meditacion_mindfulness`, `meditacion_lugar_seguro`, `meditacion_rio`, `meditacion_metta`, `meditacion_stop`, `yoga_cuello`, `yoga_ansiedad`, `lectura_motivacion`, `lectura_diaria`, `lectura_espiritual`, `lectura_autocompasion`

**POST /speech-to-text** — multipart/form-data
```
campo: file (audio binario, mínimo 5000 bytes)
// Response 200
{ "text": "string" }
```

### Check-in diario

**POST /checkin**
```json
{ "user_id": "uuid", "mood_value": 1-4 }
// 1=😔 2=😐 3=🙂 4=😄
// Response: { "ok": true, "mood_emoji": "string" }
```

**GET /checkin/today?user_id={uuid}**
```json
{ "checkin": { "mood_value": int, "mood_emoji": "string", "created_at": "iso" } | null }
```

**GET /checkin/history?user_id={uuid}&days=30**
```json
{ "checkins": [{ "mood_value": int, "mood_emoji": "string", "checkin_date": "yyyy-mm-dd" }] }
```

### Dashboard

**GET /dashboard?user_id={uuid}**
```json
{
  "mood_semanal": [{ "fecha": "yyyy-mm-dd", "mood": "Bien|Regular|Mal|null", "value": 1-3|null }],
  "dias_activos_semana": int,
  "comparacion_semana": "muy_mejor|un_poco_mejor|similar|un_poco_peor|muy_peor|null",
  "checkins": [{ "mood_value": int, "mood_emoji": "string", "checkin_date": "string" }],
  "patrones": [{ "topic": "string", "count": int, "ultimo_contenido": "string|null" }],
  "resumen": "string"
}
```

### Feedback

**POST /feedback**
```json
{
  "user_id": "uuid|null",
  "texto": "string|null",
  "categoria": "general",
  "rating": int|null,
  "audio_base64": "string|null",
  "audio_mime": "string|null"
}
// Response: { "ok": true }
```

**POST /survey**
```json
{
  "user_id": "uuid|null",
  "session_length_s": int,
  "message_count": int,
  "answers": { "nps": int, "utilidad": "string|null", "opinion": "string|null", "features": "string|null", "fallas": "string|null" }
}
```

---

## Auth con Google OAuth (Supabase)

El login con Google se hace directamente desde el cliente usando el SDK de Supabase (no pasa por el backend propio).

- **Supabase URL:** `https://idbdvpykclbxdeoirsye.supabase.co`
- **Supabase Anon Key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlkYmR2cHlrY2xieGRlb2lyc3llIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI0ODQ5ODYsImV4cCI6MjA4ODA2MDk4Nn0.GEPzBysq6hKiH5UCIi443lEeM0gX17wAtZjp9ZAJUoM`

Flujo OAuth:
1. `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: URL_APP, queryParams: { prompt: 'select_account' } } })`
2. Google redirige de vuelta con `?code=` en los query params (PKCE flow)
3. `supabase.auth.exchangeCodeForSession(fullUrl)` para obtener la sesión
4. Guardar `{ user_id, email, access_token, refresh_token }` en AsyncStorage

Verificación de email:
- Al registrarse con email/password, Supabase envía un OTP de 8 dígitos al correo
- El usuario lo ingresa y se llama a `POST /verify-email`
- El OTP viene configurado en Supabase con SMTP de Brevo

Sesión expirada:
- Los access_token son JWT con expiración
- Para refrescar: `POST /refresh` con el refresh_token
- Si el refresh falla → logout y mostrar pantalla de auth

---

## Diseño visual — Paleta y estilo

```
Color principal:     #7db89e  (verde salvia — botones primarios, acentos)
Color fondo:         #f0f7f4  (verde muy claro — fondo de pantallas)
Color dark:          #2f4f45  (verde oscuro — textos principales, headers)
Color secundario:    #3a6b5a  (verde medio — textos secundarios)
Color claro:         #b7d3c6  (verde pálido — bordes, separadores)
Color error:         #e07070  (rojo suave — mensajes de error)
Color fondo card:    #eaf5f0  (verde muy claro — cards, recuadros)
Blanco:              #ffffff
Gris texto:          #aaa
```

Estilo general:
- Border radius generoso: 16px en cards y botones principales, 8px en botones secundarios
- Fuente: sistema (SF Pro en iOS, Roboto en Android) — no usa fuente custom
- Sombras sutiles: `0 12px 30px rgba(0,0,0,0.15)`
- Mascota: oso panda 🐼 — aparece en headers y mensajes de Numa
- Tono: cálido, cercano, argentino (voseo)

---

## Estructura de datos de ejercicios

Hay 4 tipos. Los datos completos están en `ejerciciosData.js` en el proyecto original — copiar ese archivo tal cual a `/src/data/ejerciciosData.ts` en el proyecto nuevo.

**Respiración:**
```typescript
{ id, nombre, descripcion, cientifico, instruccion,
  patron: { inhalar: number, retener: number, exhalar: number, esperar: number } }
```

**Meditación / Yoga:**
```typescript
{ id, nombre, descripcion, cientifico, tiempoPorPaso?: number,  // default 20s
  pasos: [{ pose: string, guia: string }] }
```

**Lectura:**
```typescript
{ id, nombre, emoji, descripcion,
  quotes: [{ quote: string, author: string }] }
```

---

## Plan de migración — fases

El trabajo está dividido en 12 fases. En esta nueva sesión se empieza por la **Fase 1**.

- **Fase 1** — Setup e infraestructura: crear proyecto Expo + TypeScript, estructura de carpetas, navegación base, AsyncStorage, cliente Supabase, variables de entorno → **primer QR para testear en Expo Go**
- **Fase 2** — UI de Auth (sin lógica)
- **Fase 3** — Auth funcional (login, registro, OTP, Google OAuth)
- **Fase 4** — Onboarding
- **Fase 5** — Chat (núcleo)
- **Fase 6** — Menú de ejercicios
- **Fase 7** — Motor de respiración (animaciones + audio)
- **Fase 8** — Motor meditación/yoga
- **Fase 9** — Lecturas
- **Fase 10** — Dashboard y check-in
- **Fase 11** — Notificaciones push
- **Fase 12** — Build para App Store y Play Store

---

## Instrucciones para el agente en la nueva sesión

1. Empezar por la **Fase 1** del plan
2. Usar **Expo con TypeScript** — `npx create-expo-app@latest numa-mobile --template blank-typescript`
3. El directorio de trabajo es la carpeta nueva del proyecto React Native, NO el proyecto FastAPI existente
4. El backend en Railway no se toca bajo ningún concepto
5. Para testing: correr `npx expo start` y darle al usuario el QR para escanear con **Expo Go** en su celular
6. Completar cada fase en su totalidad antes de pasar a la siguiente
7. Cuando una fase está completa y testeada, confirmar con el usuario antes de avanzar
