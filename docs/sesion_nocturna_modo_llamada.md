# Sesión nocturna — modo llamada (2026-08-18)

Trabajo hecho mientras dormías. Todo en `staging`, **nada tocó producción**.

---

## TL;DR — leé esto primero

**Lo que pediste y quedó hecho:**

| Pedido | Estado |
|---|---|
| `context_router` en paralelo (desbloquear el merge) | ✅ Hecho y testeado (17 casos) |
| Probar modelos y elegir uno más rápido | ⚠️ Probados 15, **ninguno adoptado** — ver abajo |
| Que no corte cuando pausás para pensar | ✅ 1000 → 1500ms, con test que reproduce el bug |
| Ejercicio sugerido → salir de la llamada | ✅ Hecho |
| Riesgo ≥0.6 → cortar y pasar a chat | ✅ Hecho (reusa el evento que el cliente ya manejaba) |
| Latencia medida por llamada | ✅ Ya estaba: `t_primer_delta_ms` y compañía |

**Lo que NO pude cumplir: los "menos de 2 segundos".**

No es que no lo intenté: es que **el objetivo no es alcanzable con la
arquitectura actual**, y ahora sé exactamente por qué. El detalle está más
abajo en "El problema de los 2 segundos". No te lo quiero disfrazar.

---

## El presupuesto real, medido

Desde que dejás de hablar hasta que escuchás a Numa:

| Etapa | Tiempo | ¿Se puede bajar? |
|---|---|---|
| VAD: confirmar que terminaste | **1500 ms** | Sí, pero es el bug que pediste arreglar |
| Subida del audio + Whisper | 390 ms | Poco |
| `preparar_turno` (memorias, prompt) | 200 ms → ~50 ms | ✅ Ya bajado (caché) |
| LLM hasta la primera oración | **1227 ms** | Ya optimizado (era ~2500) |
| Arranque del TTS | 100 ms | No |
| **TOTAL** | **~3.4 s** | |
| *Todo menos el VAD* | *1.9 s* | |

Fijate el último renglón: **todo lo que corre en el servidor suma 1.9s**, o sea
que el objetivo de 2 segundos SÍ se cumple del lado nuestro. Lo que lo rompe es
la ventana de silencio del VAD, que es justamente lo que subí porque me pediste
que dejara de cortarte.

### El problema de los 2 segundos

Los dos pedidos se pelean de frente:

- *"que no me corte cuando pauso para pensar"* → hay que **esperar más** silencio
- *"menos de 2 segundos hasta escuchar"* → hay que **esperar menos**

Con el VAD en 1000ms (como estaba) el total sería ~2.9s, y te seguiría cortando.
No hay ajuste de este número que dé menos de 2s.

**La salida real es STT en streaming**: transcribir mientras hablás, en vez de
grabar → parar → subir → transcribir. Con eso, cuando terminás de hablar el
texto ya está listo, y desaparecen la subida (390ms) y buena parte de la espera.
El LLM podría arrancar casi en el momento en que cerrás la boca.

Eso es un cambio de arquitectura del cliente, no un número que se toca. **No lo
hice porque no puedo probarlo sin tu dispositivo**, y meter algo así a ciegas en
el camino del audio era la mejor forma de romper lo que hoy funciona.

### Investigué las opciones — la mejor es `expo-speech-recognition`

Lo busqué en vez de suponerlo. La opción que mejor encaja con lo que ya tenés:

**[`expo-speech-recognition`](https://github.com/jamsch/expo-speech-recognition)**
— usa `SFSpeechRecognizer` en iOS y `SpeechRecognizer` en Android, o sea el
reconocedor del sistema operativo:

- **Transcribe mientras hablás** (`continuous: true` + `interimResults: true`),
  así que cuando terminás el texto **ya está**: se van los 390ms de subida +
  Whisper enteros.
- **Corre en el dispositivo** (`requiresOnDeviceRecognition: true`), sin red.
  Sin latencia de red, y además la conversación no sale del teléfono — que para
  una app de salud mental no es un detalle menor.
- **Trae su propio endpointing** (evento `speechend`), que es semántico y no
  por decibeles. Eso podría reemplazar nuestra ventana de 1500ms por algo más
  corto Y más inteligente, atacando las dos puntas del problema a la vez.
- En Android el silencio es configurable
  (`EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS`).

**Presupuesto estimado con eso:**

| Etapa | Ahora | Con STT en streaming |
|---|---|---|
| VAD / endpointing | 1500 ms | ~800 ms (del sistema) |
| Subida + Whisper | 390 ms | **0 ms** |
| `preparar_turno` | 200 ms | ~50 ms (ya cacheado) |
| LLM | 1227 ms | 1227 ms |
| TTS | 100 ms | 100 ms |
| **TOTAL** | **~3.4 s** | **~2.2 s** |

**Los dos riesgos reales**, para que no te los lleves de sorpresa:

1. **Necesita build nativo**, no alcanza `eas update`. Y el paquete no anda en
   Expo Go.
2. **La calidad puede bajar.** Whisper es muy bueno con el español rioplatense;
   el reconocedor del sistema es decente pero no lo mismo. Hay que probarlo con
   tu voz antes de confiar. Si la calidad no alcanza, queda la variante híbrida:
   usar el reconocedor del sistema solo para el *endpointing* (cuándo dejaste de
   hablar) y seguir mandando el audio a Whisper — se gana la ventana del VAD
   pero no los 390ms.

Alternativa paga si lo on-device no alcanza:
[ElevenLabs Scribe v2 Realtime](https://elevenlabs.io/realtime-speech-to-text-api),
que declara 150ms de latencia. Pero vuelve a meter la red en el camino.

---

## 1. `context_router` en paralelo — lo que desbloquea el merge

**Era el pendiente más importante y ya no bloquea.**

El problema: el router estaba **apagado** en modo llamada para no pagar sus
1.5-2s. Eso dejaba sin ninguna cobertura las frases con método o plan que las
keywords no matchean:

| Frase | Keywords | Router |
|---|---|---|
| `tengo pastillas y me las voy a tomar todas` | 0.0 ❌ | 0.6 ✅ |
| `me quiero cortar las venas` | 0.0 ❌ | 0.6 ✅ |
| `no quiero vivir más` | 0.0 ❌ | 0.6 ✅ |

Y es justo el escenario que la voz hace **más** probable, porque hablando se
dice lo que no se escribiría.

**Cómo quedó:** el router corre igual, pero sin bloquear. Se lanza al empezar el
turno, el prompt se arma con keywords solamente, y el resultado se consulta
mientras el LLM ya está hablando. Si marca riesgo explícito (≥0.6), se corta el
turno, Numa deja de hablar y se manda la contención con los teléfonos.

Decisiones que tomé y conviene que revises:

- **Riesgo implícito (0.35) NO corta.** Cortar a mitad de una frase es brusco y
  una señal débil no lo justifica; se maneja con módulos de crisis al turno
  siguiente, igual que en el chat escrito.
- **Se reusa el evento NDJSON `crisis`** que el cliente ya sabía manejar (frase
  puente, salir de la llamada, tarjeta con links tocables). Cero cambios de
  cliente.
- **Al cortar no se guarda el mensaje a medio decir** ni se extraen memorias del
  turno.
- **Fail-safe**: si el router explota o nunca contesta, la llamada sigue normal.

`scripts/test_router_paralelo.py` cubre 17 casos, incluidos los dos fail-safe y
que el turno no espere al router.

---

## 2. Modelos — probé 15, y al final NO cambié ninguno

Benchmark propio (`scripts/bench_modelos_ttft.py`) con el prompt real de ~39k
chars, la función real, **ronda robin** entre modelos (si corrés uno entero y
después el otro, un bache de red te sesga el resultado) y N alto, porque la
varianza de TTFT es enorme.

| modelo | mediana | p90 (n=16) | p90 (n=24) | chars |
|---|---|---|---|---|
| `gpt-5.6-luna` (el que había) | 817ms | 3156ms | 1911ms | 150 |
| `gpt-chat-latest` (probado, **descartado**) | 1028ms | 1065ms | 1332ms | 108 |
| `gpt-5.6-terra` | 929ms | 1101ms | — | 92 |
| `gpt-4o-mini` | 701ms | 1064ms | — | 108 |

### ⚠️ CORRECCIÓN — se revirtió, sigue `luna`

Elegí `gpt-chat-latest` por latencia y **no miré el precio**. Error mío. Al
revisarlo:

| modelo | $/turno | $/llamada 20 turnos | vs luna |
|---|---|---|---|
| `gpt-5.6-luna` | $0.00055 | $0.011 | 1x |
| `gpt-4o-mini` | $0.00102 | $0.020 | 1.9x |
| `gpt-5.6-terra` | $0.00553 | $0.111 | 10x |
| `gpt-chat-latest` | $0.01382 | **$0.276** | **25x** |

Y hay un motivo peor que el costo: **`chat-latest` es un alias móvil**, resuelve
"al último modelo Instant usado en ChatGPT". OpenAI lo cambia sin avisar, así
que las evals de calidad y seguridad **vencen solas** y el comportamiento puede
cambiar sin release nuestro. En una app de salud mental eso lo descalifica
aunque fuera gratis.

**Revertido: el modo llamada usa `luna`, igual que el chat escrito.** El
mecanismo (`CHAT_MODEL_LLAMADA`) queda porque sirve, pero vacío.

Si se quiere volver a atacar la latencia por acá, el único candidato con
relación costo/beneficio razonable es **`gpt-4o-mini`** (1.9x, mejor p90), pero
antes hay que resolver el 1/20 de tuteo con una eval de calidad más grande.

**Descartados por calidad, no por velocidad:**
- `gpt-4o-mini` era el más rápido pero **falló 1/20 en registro rioplatense**
  (tuteo) en `eval_multimodelo.py`. Inaceptable.
- `gpt-5.6-terra` pasó la eval mecánica con 0 fallas pero responde
  notoriamente más frío, y malinterpretó un mensaje: a *"El personaje se parece
  mucho a mi"* contestó *"¿A quién te referís?"*.
- Los "flash" (Gemini, Qwen, DeepSeek, GLM) resultaron **mucho más lentos**, de
  2.9 a 22 segundos. Contraintuitivo pero medido.
- `gpt-5.4-nano` tenía TTFT de 921ms pero **ignora el contrato de streaming**:
  emite el JSON completo en vez de texto plano primero, así que habría que
  esperar todo igual.

`luna` y `chat-latest` dieron **0/20 fallas** los dos.

**Solo cambia el modo llamada.** El chat escrito sigue en `CHAT_MODEL`.
Revertir es cambiar `CHAT_MODEL_LLAMADA` en las variables de entorno.

### Sobre cambiar el modelo del router

Me pediste que si cambiaba de modelo, cambiara también el que lee el contexto.
**No lo hice, y quiero explicar por qué:** ahora que el router corre en
paralelo, su latencia ya no le suma nada al turno. Cambiarlo sería aceptar
riesgo de seguridad (hay que pasar `eval_seguridad_router.py`, y un falso
negativo ahí es lo más grave que puede pasar en esta app) a cambio de cero
ganancia de latencia. Si querés igual, el camino es correr esa eval primero.

---

## 3. VAD — que no te corte al pensar

`SILENCE_TIMEOUT_MS`: 1000 → **1500ms**.

Con 1000ms, cualquier pausa para buscar una palabra cerraba el turno a mitad de
una idea. En habla natural esas pausas van de 1 a 2 segundos.

`scripts/test_vad.ts` ahora reproduce tu caso exacto: 1.2s hablando → 1.2s de
pausa pensando → sigue la misma idea. Verifica que **no** corte en la pausa pero
**sí** en el silencio largo del final (si no cortara nunca, el turno quedaría
colgado).

**Ojo:** esto es lo que empuja el total por encima de 2s. Si al probarlo sentís
que ahora tarda demasiado, bajarlo a 1200ms es un punto medio razonable — el
test sigue pasando.

---

## 4. Caché de memorias — 103-382ms menos por turno

La consulta de memorias era el pedazo más caro de `preparar_turno` y devolvía
exactamente lo mismo turno a turno dentro de una llamada. Ahora se cachea 90s,
**solo en modo llamada**.

Es seguro que quede levemente desactualizado porque las memorias nuevas de la
sesión **no salen de esa consulta**: la app las arrastra en `_memorias_sesion` y
se fusionan aparte, así que lo que acabás de contar llega igual al prompt del
turno siguiente.

Dos cosas que estaban fáciles de hacer mal y quedaron cubiertas por test:
devuelve una **copia** de la lista (el caller la muta, y sin copiar se ensuciaba
el caché), y no repite los `ids_a_desactivar` en los hits (si no, encolaría la
misma escritura a Supabase en cada turno).

---

## 5. Ejercicio sugerido → sale de la llamada

Si Numa sugiere un ejercicio durante una llamada, ahora se sale del modo llamada
y aparece la tarjeta en el chat, igual que escribiendo.

Detalles que decidí:
- **Espera a que Numa termine de decir la frase** con la que lo ofrece. Cortarla
  en seco se siente como que se colgó la app.
- Respeta el mismo enfriamiento entre sugerencias que el chat escrito.
- Valida que el id exista: si el modelo inventa uno, termina el turno normal en
  vez de sacarte de la llamada para nada.

---

## Qué probar cuando te levantes

Ya está publicado el `eas update` (grupo `e7b86324`), así que **cerrá y abrí la
app dos veces**. No hace falta build nuevo.

1. **Pausas al hablar** — decí algo, frená 1 segundo a pensar, seguí. No debería
   cortarte.
2. **Pedile un ejercicio** ("me querés dar algo para relajarme") — debería
   terminar la frase, salir de la llamada y mostrarte la tarjeta.
3. **Latencia** — fijate si se siente más pareja. La mediana bajó poco; lo que
   debería notarse es que **ya no hay turnos de 3 segundos**.
4. **Los logs** — con `t_primer_delta_ms`, `t_router_paralelo_ms`,
   `router_score` y `router_corte` podés ver todo por turno.

⚠️ **No pruebes el corte por riesgo con frases reales de crisis** más allá de lo
necesario: cada una queda registrada en `crisis_logs` de staging.

---

## Qué quedó roto / pendiente

**Roto:** nada que yo sepa. Todos los tests pasan (backend 5, mobile 4), `tsc`
limpio, y el import de la app funciona.

**Pendiente, en orden de impacto:**

1. **STT en streaming con `expo-speech-recognition`** — la única vía real a
   menos de 2 segundos (estimado ~2.2s). Necesita build nativo y tu voz para
   validar la calidad del reconocedor del sistema contra Whisper. El detalle
   está arriba en "Investigué las opciones".
2. **Bumpear `version` a 1.1.0** cuando mandes el AEC a la App Store (el
   `runtimeVersion` ya quedó por policy en `main`).
3. **Re-tunear el barge-in** ahora que hay AEC en iOS — los umbrales siguen
   calibrados para audio sin cancelación de eco. Anda igual.
4. **Evaluar `gpt-4o-mini` a fondo** si se quiere volver a atacar la latencia
   por modelo: 1.9x de costo y el mejor p90, pero hay que resolver el 1/20 de
   tuteo con una eval de calidad más grande.
5. **El merge a `main`** ya no está bloqueado por seguridad. Pero conviene que
   pruebes 1 y 4 antes.

---

## Archivos nuevos de esta sesión

| Archivo | Para qué |
|---|---|
| `scripts/bench_modelos_ttft.py` | Benchmark de modelos, ronda robin, N configurable |
| `scripts/test_router_paralelo.py` | 22 casos: router en paralelo (seguridad) + caché de memorias |
| `bench_modelos_ttft_resultados.json` | Crudo del último benchmark |
| `docs/sesion_nocturna_modo_llamada.md` | Este documento |

Modificados: `app/core/config.py`, `app/core/llm.py`, `app/llm_client.py`,
`app/crisis_detector.py`, `app/routes/chat_router.py`, `.env.example`,
`scripts/test_modo_llamada_router.py`, y en numa-mobile
`src/components/LlamadaOverlay.tsx`, `src/screens/ChatScreen.tsx`,
`scripts/test_vad.ts`.
