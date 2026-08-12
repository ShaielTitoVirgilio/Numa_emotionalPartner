# Plan: respuestas de Numa en streaming (texto → voz fluida)

> Estado: **solo diseño, nada implementado todavía**. Este doc es la referencia para cuando se aplique.
> Objetivo: que cuando Numa "hable", el audio/texto empiece a salir apenas el modelo genera las primeras palabras, en vez de esperar el mensaje completo y recién ahí arrancar.

## Decisiones confirmadas (2026-08-11)

- **TTS = motor nativo del dispositivo, no un proveedor pago.** En la PWA web: `speechSynthesis` (Web Speech API), gratis, sin llamadas a ninguna API externa. Cuando se migre a la app nativa (ver `REACT_NATIVE_CONTEXT.md`, migración a **Expo/React Native**), el equivalente es **`expo-speech`**, que por debajo usa `AVSpeechSynthesizer` en iOS y `TextToSpeech` en Android — misma idea ("le paso un string, el dispositivo lo dice, encola solas las llamadas sucesivas"), mismo punto de enchufe en la arquitectura, solo cambia qué función de "hablar(oración)" se usa según la plataforma. Un TTS pago (ElevenLabs/PlayAI/etc.) queda descartado por ahora — ver aclaración de costos abajo.
- **Prioridad #1: no romper `_quitar_che`, `_aplanar_apertura`, `_quitar_cierre_presencia`, `_quitar_pregunta_final`.** Ante cualquier tensión entre "más fluido" y "puede alterar lo que ya filtran estas funciones", gana la segunda. La sección 5 tiene el análisis filtro por filtro que sostiene esta decisión.
- **Formato de salida del LLM: A.2.a** (mensaje en texto libre primero, JSON de metadata después — ver sección 3), porque reutiliza el parser de fallback que ya existe en `llm_client.py` en vez de escribir un parser incremental de JSON nuevo.

### Aclaración importante sobre costos

Van dos cosas separadas que es fácil confundir:

1. **Streaming del LLM (Opción A, backend↔Groq/OpenRouter)**: pedir `stream=True` en vez de `stream=False` **no cambia cuántos tokens se generan ni lo que se paga**. Es el mismo completion, la misma cantidad de tokens de salida — la única diferencia es que llegan de a pedacitos en vez de todos juntos al final. Esto se puede activar sin ningún costo extra.
2. **TTS pago (Opción C.2)**: acá sí hay costo por request (se le paga a ElevenLabs/PlayAI/etc. por cada mensaje convertido a audio). Es exactamente lo que se está evitando ahora usando Web Speech API / `expo-speech`, que no tienen costo por uso porque corren en el dispositivo del usuario.

O sea: el streaming del texto (backend) es gratis y se puede dejar armado ya. Lo que se pagaría es únicamente un TTS "de verdad" más adelante, si en algún momento se decide subir la calidad de voz — y ni siquiera hace falta para que el streaming se sienta fluido con Web Speech API / `expo-speech`.

---

## 1. Por qué esto no es "prender un flag" en Numa

En un chatbot que devuelve texto plano, streaming es trivial: mandás cada token tal cual sale del modelo. Numa **no** hace eso hoy, y por buenas razones que hay que respetar:

1. **El LLM no devuelve texto: devuelve un JSON envelope.**
   `{"message": "...", "mood": "...", "suggested_action": "...", "memories": [...]}`.
   El texto que hay que leer/hablar está *adentro* de un campo, no es todo el output.

2. **Se fuerza `response_format={"type": "json_object"}`** ([llm_client.py:104](../app/llm_client.py)).
   Esto le garantiza a la API que la respuesta completa es un JSON válido — pero como contrapartida, el modelo no puede "empezar por el texto libre": arma el objeto entero y typically no hay garantía de orden de streaming utilizable a nivel de texto plano.

3. **Hay post-procesamiento pesado sobre el mensaje YA COMPLETO** en [chat_router.py](../app/routes/chat_router.py):
   - `_quitar_che` — saca la muletilla "che" en cualquier parte del texto.
   - `_aplanar_apertura` — si el mensaje abre igual que el anterior ("Sentís que...", "Es como que..."), lo aplana. Solo mira el **arranque**.
   - `_quitar_cierre_presencia` — si las últimas 1-2 oraciones son un cierre tipo "acá estoy" repetido, las corta. Mira el **final**.
   - `_quitar_pregunta_final` — si hay racha de preguntas seguidas, recorta la pregunta del **final**.

   Los dos últimos filtros **necesitan saber que una oración es la última** del mensaje. Eso es imposible de saber mientras el modelo todavía está generando. Si mandás las palabras a la UI/voz apenas salen, para cuando el filtro decide "che, esta frase de cierre sobra", el usuario ya la escuchó.

4. **Fallback multi-proveedor.** `generate_response` prueba OpenRouter y si falla reintenta en Groq ([llm_client.py:96-127](../app/llm_client.py)). Si ya empezaste a mandarle chunks al usuario y el proveedor se cae a mitad de la respuesta, no podés "cambiar de proveedor" sin que el usuario haya visto/oído un mensaje cortado.

Cualquier plan de streaming para Numa tiene que resolver estos 4 puntos, no solo "conectar el stream de Groq al navegador".

---

## 2. Los 3 tramos del pipeline

```
[Groq/OpenRouter]  --(A)-->  [FastAPI backend]  --(B)-->  [Browser/frontend]  --(C)-->  [Voz]
     genera token             re-empaqueta y             recibe y renderiza          TTS habla
     a token                  filtra                     progresivamente
```

Cada tramo tiene sus propias opciones, independientes entre sí:

- **(A) LLM → backend**: ¿cómo pedimos y leemos el stream del modelo?
- **(B) backend → frontend**: ¿qué protocolo de transporte usamos para no esperar al final?
- **(C) texto → voz**: ¿quién convierte texto en audio, y con qué granularidad se lo alimentamos?

---

## 3. Opción A — LLM → backend: pedir el stream y separar "mensaje" de "metadata"

### A.1 Mecánica de la API (Groq/OpenRouter, ambos compatibles OpenAI SDK)

Hoy: `client.chat.completions.create(..., stream=False)` → devuelve el objeto completo de una.
Streaming: `client.chat.completions.create(..., stream=True)` → devuelve un iterador de `ChatCompletionChunk`. Cada chunk trae `chunk.choices[0].delta.content` (puede venir `None` en el primer/último chunk, o vacío). Se concatenan para reconstruir el texto completo.

```python
stream = cliente.chat.completions.create(
    model=modelo,
    stream=True,
    messages=[...],
    # OJO: ver A.2, response_format normalmente NO se puede combinar bien con esto
)
for chunk in stream:
    delta = chunk.choices[0].delta.content or ""
    if delta:
        yield delta
```

Groq en particular genera muy rápido (chips LPU) — el streaming ahí se nota muchísimo más que en un proveedor lento.

### A.2 El problema del JSON forzado — dos caminos

**Opción A.2.a — Abandonar `json_object` mode para el modo streaming, y pedir por prompt: "texto libre primero, JSON de metadata después".**

Formato de salida pedido al modelo (nuevo, solo para el modo streaming):
```
Todo el mensaje en texto plano, como si le hablaras directo a la persona.
{"mood": "calm", "suggested_action": null, "memories": [...]}
```
Sin comillas ni llaves alrededor del mensaje — recién arranca el JSON en la parte de metadata.

Esto **no es una idea nueva para este código**: el PASO 3 del parser actual (`llm_client.py:164-175`) *ya* asume que puede haber texto libre antes del primer `{` y lo trata como el mensaje real ("el texto antes del primer { es la respuesta real del modelo"). O sea, el parser de fallback que ya existe fue construido, sin saberlo, para este mismo formato. Reutilizarlo para streaming es más reforma que invención:

- Todo lo que llega **antes** del primer `{` → se manda en vivo al frontend (tramo B) apenas se completan palabras/oraciones.
- Todo lo que llega **desde** el primer `{` → se buffer­ea (no se muestra), y al terminar el stream se parsea con la misma lógica de `_reparar_json_truncado` que ya existe para truncamientos.

Contras: se pierde la garantía "capa 1" de JSON válido a nivel de API para la parte de metadata. Mitigado porque el parser de 3 pasos ya está pensado para esto, y el prompt puede reforzar el formato con ejemplos.

**Opción A.2.b — Mantener `json_object` estricto y parsear el JSON de forma incremental.**

Se necesita un mini-parser de streaming que sepa "estoy dentro del valor string de la clave `message`" y vaya emitiendo caracteres a medida que llegan, manejando comillas escapadas (`\"`, `\n`, unicode `\uXXXX`), y sepa detectar el cierre de ese campo para dejar de emitir. Es más robusto ante cualquier orden/formato que devuelva el modelo, pero es bastante más código y más superficie de bugs (un escape mal manejado corta el texto a la mitad).

**Recomendación para aprender/implementar primero: A.2.a.** Reusa código existente, es mucho menos propenso a bugs raros de parsing, y el riesgo (formato libre en vez de JSON estricto) ya está cubierto por el parser de fallback actual. A.2.b queda como mejora futura si A.2.a demuestra ser poco confiable en la práctica.

### A.3 Reasoning models (gpt-oss) y streaming

`core/llm.py` ya limpia bloques `<think>...</think>` y canales `harmony` del content completo (`strip_reasoning`). En streaming eso no se puede aplicar de la misma forma (el bloque puede llegar partido en varios chunks). Con el modelo default actual (`qwen/qwen3-32b`, `reasoning_effort="none"`) no debería aparecer nada de esto. Si en algún momento se cambia a un modelo de la familia `gpt-oss` (`reasoning_effort="low"`), hay que filtrar el bloque de razonamiento **antes** de mandar nada a streaming — ver gotcha en sección 7.

### A.4 Fallback de proveedor en modo streaming

Regla simple para no complicar de más: **el fallback (OpenRouter → Groq) solo se intenta si el error pasa ANTES de mandar el primer chunk al cliente** (falla al abrir la conexión / primer token). Si el stream se corta a mitad de camino después de ya haber mandado texto, no se reintenta con otro proveedor — se corta ahí y se cierra el mensaje con algo como "necesito repensar esto, ¿me lo repetís?" (similar al `_FALLBACK_RESPONSE` actual). Intentar "resumir" un mensaje a mitad con otro modelo daría un Frankenstein de estilos.

---

## 4. Opción B — backend → frontend: cómo transportar los chunks

Tres formas típicas de "streamear" una respuesta HTTP:

| Opción | Cómo funciona | ¿Sirve para Numa? |
|---|---|---|
| **WebSocket** | Conexión bidireccional persistente | Sobra: no necesitamos que el cliente mande nada a mitad de la respuesta (todavía). Más infraestructura (reconexión, estado de conexión) de la que hace falta para esto. |
| **SSE nativo (`EventSource`)** | El browser abre la conexión con `new EventSource(url)` y el server manda `data: ...\n\n` | **No sirve directo acá**: `EventSource` solo soporta `GET` y **no permite mandar headers custom** (no hay forma de mandar `Authorization: Bearer <token>`, que es como Numa autentica cada request via `authHeaders()`). Se podría poner el token en la query string, pero eso [va contra buenas prácticas de manejo de credenciales](../app/core/auth.py) (queda en logs de acceso, historial, etc.). |
| **`fetch()` + `ReadableStream` manual** | `fetch(url, {method:'POST', headers, body})` y despues `response.body.getReader()` para leer de a pedazos | ✅ **Es la que corresponde acá.** Sigue siendo un `POST` normal con los headers de auth de siempre, solo que en vez de esperar `res.json()` se lee el body incrementalmente. |

### Formato de los chunks: NDJSON (una línea = un JSON)

En vez de inventar un framing propio, cada chunk que el backend escribe es una línea JSON:

```
{"type":"delta","text":"Hola, "}
{"type":"delta","text":"veo que "}
{"type":"delta","text":"venís con un día pesado."}
{"type":"final","mood":"calm","suggested_action":null,"risk_level":"none","nuevas_memorias":[...]}
```

El backend arma esto con un `StreamingResponse` (Starlette) que itera un generador Python (puede ser `def`, no hace falta pasar todo a `async` — Starlette ejecuta generadores sync en threadpool igual que ya se hace con los endpoints `def` actuales). El generador:

1. corre TODO el trabajo previo que ya existe hoy (detección de crisis, carga de perfil/memorias/patrones, armado del prompt) — esto **no cambia**, sigue siendo síncrono antes de abrir el stream;
2. si fue crisis confirmada (respuesta hardcodeada, sin LLM) → yieldea un único chunk `delta` con el mensaje completo y listo, para que el frontend no necesite un código distinto para ese caso;
3. si no, abre el stream del LLM (Opción A) y va yieldeando líneas `delta` a medida que se completan oraciones (ver sección 5, el "buffer de cola");
4. al final, yieldea una línea `final` con mood/suggested_action/memories ya parseados y filtrados;
5. dispara el guardado en Supabase (conversación + memorias) — mismo mecanismo de tarea en background que ya existe, solo que ahora se dispara al cierre del generador en vez de vía la dependencia `BackgroundTasks` inyectada (con `StreamingResponse` se le puede pasar un `background=BackgroundTask(...)` al armar la respuesta, o directamente llamar la función de guardado al final del generador).

### Frontend: leer el stream

```js
const res = await fetch("/chat", { method: "POST", headers: authHeaders({...}), body, signal });
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  let nl;
  while ((nl = buffer.indexOf("\n")) >= 0) {
    const linea = buffer.slice(0, nl);
    buffer = buffer.slice(nl + 1);
    if (!linea.trim()) continue;
    const evento = JSON.parse(linea);
    // evento.type === "delta" → ir pegando texto a la burbuja + alimentar cola de TTS
    // evento.type === "final" → aplicar mood/suggested_action/memorias, como hoy
  }
}
```

---

## 5. El punto central: qué filtro es compatible con streaming y cuál no (análisis exacto)

En vez de asumir "los filtros necesitan el mensaje completo", fui a mirar la regex real de cada uno en `chat_router.py` para saber con precisión cuáles se pueden correr en vivo, oración por oración, y cuáles necesitan esperar al final. Resultado: **dos son seguros de correr en vivo, dos no.**

### 5.1 `_quitar_che` — ✅ seguro oración por oración

El patrón que detecta "che" al arranque de frase es:
```python
r"(^|[.!?…]\s+)che\b\s*[,:;]?\s*([¿¡]*)([a-záéíóúñ])"
```
Matchea "che" en el arranque absoluto del string (`^`) **o** después de puntuación de cierre + espacio (`[.!?…]\s+`). Si el mensaje se corta en oraciones (`re.split(r"(?<=[.!?…])\s+", texto)`) y cada oración se le pasa a `_quitar_che` **como string independiente**, el `^` de la oración N cae exactamente en el mismo lugar donde antes caía `[.!?…]\s+` al final de la oración N-1 — el match da idéntico se lo mire en el mensaje completo o en la oración suelta. Los otros dos patrones (`, che,` en medio de la frase, `, che` de cierre, y el catch-all `\bche\b`) son intra-oración por construcción: nunca necesitan mirar más allá de la oración en la que están. **Conclusión: se corre sobre cada oración apenas se completa, sin esperar nada.**

### 5.2 `_aplanar_apertura` / `_familia_apertura` — ✅ seguro, pero es una decisión única al principio

El regex está anclado al arranque absoluto (`^\s*sent[ií]s\s+que\s+(.+)$`, con `re.DOTALL`). Solo puede matchear contra las primeras palabras del mensaje — nunca contra una oración del medio. El detalle del `(.+)$` con `DOTALL` es que técnicamente "agarra" todo lo que sigue, pero en la práctica no importa para streaming: lo único que hace el filtro es sacar el prefijo ("Sentís que ") y dejar el resto intacto. Trasladado a streaming: apenas se reconocen las primeras 2-4 palabras del mensaje, se decide **una sola vez** "¿el mensaje anterior de Numa abrió con la misma fórmula? → si sí, no emitas el prefijo, arrancá directo con el resto capitalizado". De ahí en adelante el resto del mensaje fluye sin que este filtro vuelva a intervenir. **No depende del final del mensaje.**

### 5.3 `_quitar_cierre_presencia` — ❌ necesita saber dónde termina el mensaje

Mira específicamente `partes[-2:]` — las **últimas dos oraciones** — y las compara contra el patrón de cierres tipo "acá estoy"/"te leo" con un límite de longitud (`<=60`/`<=70` caracteres). "Últimas" es una propiedad que no existe hasta que el modelo terminó de generar todo. **Solo puede correr una vez cerrado el stream del LLM.**

### 5.4 `_quitar_pregunta_final` — ❌ ídem, y encima compara contra el largo total del mensaje

El `while` puede sacar más de una oración final si hay una racha de preguntas seguidas, y el guard en `chat_router.py` exige `len(recortado) >= 0.35 * len(result["message"])` — una comparación contra el **largo del mensaje entero**, que por definición no se conoce hasta que terminó. **Ídem: solo corre al cierre del stream.**

### La consecuencia práctica: cola de 2 oraciones retenidas

No hay forma de evitar que 5.3 y 5.4 necesiten el final — hay que diseñar alrededor de eso, no pelearlo. Algoritmo, mientras van llegando los `delta` del LLM:

1. Acumular texto en un buffer y cortarlo en oraciones completas (`re.split(r"(?<=[.!?…])\s+", ...)`, la misma regex que ya usan estos filtros).
2. Mantener **como máximo 2 oraciones sin emitir** en todo momento (ring buffer chico). Cuando se completa una 3ra oración:
   - a la oración más vieja (la que ahora deja de estar entre las últimas 2) se le corre `_quitar_che` y, si es la primera oración del mensaje, `_aplanar_apertura`;
   - se emite esa oración ya filtrada como chunk `delta` (texto a la UI + a la cola de TTS);
   - se la saca del buffer.
3. Al terminar el stream del LLM, quedan en el buffer las últimas ≤2 oraciones. Recién ahí se corren `_quitar_cierre_presencia` y `_quitar_pregunta_final` sobre esas oraciones (con el mensaje completo ya armado para los checks de longitud), y el resultado (ya filtrado, puede ser más corto que lo generado) se manda como cierre.

`N=2` no es arbitrario: es exactamente la ventana que mira `_quitar_cierre_presencia` (`partes[-2:]`). Queda un caso borde: si `_quitar_pregunta_final` necesitara recortar una racha de **más de 2** preguntas seguidas, el algoritmo ya emitió la 3ra-desde-el-final antes de saber que hacía falta cortarla — se perdería ese recorte. Es un caso raro (el prompt ya le prohíbe al modelo preguntar en racha, esto es la red de seguridad determinística para cuando lo desobedece dos veces seguidas) y, si pasa, el resultado es "se coló una pregunta de más" — no rompe nada, solo no aplica el 100% del recorte en ese caso extremo. Se puede subir `N=3` si en la práctica se ve que pasa seguido; el costo es un poquito más de buffer retenido.

### Sobre mensajes cortos (el caso más común en Numa)

Si un mensaje típico de Numa tiene 2-3 oraciones (probable, dado el tono breve/mobile-first del prompt), reteniendo 2 de cola en todo momento, **buena parte o todo el mensaje termina cayendo dentro de esa cola** — o sea, el beneficio de "verlo/oírlo fluir en vivo" es chico en mensajes cortos y crece en mensajes largos. Esto es una limitación estructural (no se puede saber que algo "no es el final" hasta saber cuánto dura el mensaje), no un bug del diseño — y es un trade-off razonable: un mensaje corto de por sí se termina de generar rápido, así que la espera total ya es baja aunque no haya streaming real ahí. Donde el streaming se nota es en las respuestas más largas (reflejo + validación + cierre, que es como está armado el prompt en varios módulos).

### Una decisión más: texto (UI) y voz (TTS) van con el mismo criterio

Se podría ser más agresivo con el texto en pantalla que con la voz — por ejemplo mostrar la oración retenida apenas se genera y "corregirla" (editar el DOM) si el filtro de cierre después decide recortarla, ya que el texto se puede tachar/reemplazar sin que el usuario note mucho. La voz **no**: una vez dicha en voz alta, no se puede "desdecir". Para no meter dos códigos de camino distintos (uno optimista con corrección visual, otro conservador para audio) y priorizando **no romper nada** como pediste, la recomendación es que **texto y voz usen la misma cola de 2 oraciones** — ambos muestran/dicen exactamente lo mismo, en el mismo momento, ya filtrado. Es más simple de programar y de debuggear, y el costo (un poco menos "instantáneo" en pantalla) es aceptable. Si más adelante se quiere exprimir la UI de texto para que se sienta aún más rápida que la voz, se puede separar — pero no es necesario para la primera versión.

---

## 6. Opción C — texto → voz: dos caminos, distinta inversión

Hoy Numa **no tiene TTS** (solo STT: el micrófono transcribe con Whisper vía `speech_service.py`, pero nada convierte la respuesta de Numa en audio). Es una feature nueva. Opciones:

### C.1 Motor de voz nativo del dispositivo — ✅ decidido, así arranca

**Web (PWA actual):** `speechSynthesis` del navegador. 100% cliente, cero backend, cero costo por request. Encaja perfecto con el streaming por oraciones de la sección 5: cada vez que el frontend recibe una oración completa y filtrada (un `delta`), se hace:
```js
const utterance = new SpeechSynthesisUtterance(oracion);
utterance.lang = "es-AR"; // o la variante que corresponda
speechSynthesis.speak(utterance);
```
El navegador **encola automáticamente** los `speak()` sucesivos — mientras las oraciones lleguen más rápido de lo que tardan en decirse (muy probable con Groq), el habla sale continua sin cortes.

**iOS / Android (app nativa vía React Native + Expo):** `REACT_NATIVE_CONTEXT.md` ya documenta la migración planeada a Expo. El equivalente directo de `speechSynthesis` ahí es **[`expo-speech`](https://docs.expo.dev/versions/latest/sdk/speech/)**, que por debajo usa `AVSpeechSynthesizer` en iOS y el motor `TextToSpeech` de Android — misma API mental (`Speech.speak(oracion, { language: "es-AR" })`), mismo comportamiento de encolar llamadas sucesivas. **No hace falta ningún código nativo Swift/Kotlin aparte**: es un paquete de Expo, se integra con `npx expo install expo-speech` cuando llegue la Fase 5 (Chat) o una fase de voz del plan de migración.

O sea: la arquitectura de streaming (secciones 3, 4 y 5 — cómo se corta el mensaje en oraciones filtradas) es **la misma en las 3 plataformas**. Lo único que cambia entre web / iOS / Android es una función chica tipo `hablar(oracion)`, con una implementación por plataforma:

| Plataforma | Implementación de `hablar(oracion)` |
|---|---|
| Web (PWA) | `speechSynthesis.speak(new SpeechSynthesisUtterance(oracion))` |
| iOS / Android (Expo) | `Speech.speak(oracion, { language })` de `expo-speech` |

Contras a tener en cuenta en ambos casos: voz "de robot" (no es una voz entrenada tipo asistente premium), calidad/disponibilidad de voces en español varía por SO, y en iOS (Safari y también `expo-speech` sobre `AVSpeechSynthesizer`) suele hacer falta que el primer audio dispare dentro de un gesto de usuario (un tap) — conviene "despertar" el motor en la primera interacción del usuario con el chat, no recién cuando llega la primera respuesta.

### C.2 TTS "de verdad" (voz entrenada, tipo la que tendría un "acompañante emocional") — fase futura

Proveedores con streaming de audio: ElevenLabs (streaming API), OpenAI TTS (streaming), PlayAI (Groq lo ofrece como proveedor de voz separado de los modelos de texto), Azure/Google Cloud TTS streaming.

Esto es un pipeline aparte, más grande:
- El backend manda cada oración ya filtrada (misma cola de la sección 5) a la API de TTS elegida, que devuelve audio (streaming de bytes, típicamente MP3/Opus en chunks).
- Esos bytes hay que relayarlos al frontend — o en el mismo canal NDJSON (como base64, más pesado) o en un endpoint de audio aparte.
- En el frontend, reproducir audio que va llegando de a pedazos requiere `MediaSource Extensions` (`SourceBuffer.appendBuffer()`) para que no haya micro-cortes entre chunk y chunk, o una cola de `<audio>`/`AudioBufferSourceNode` por oración (más simple, con un mini-gap perceptible entre oraciones si no se afina el crossfade).
- Costo por mensaje (llamada a la API de TTS) y latencia extra (generar audio no es instantáneo).

**Recomendación**: arrancar por C.1 para aprender y validar el pipeline completo, dejar C.2 como mejora de "calidad de voz" una vez que A+B+C.1 ya funcionan de punta a punta. Son intercambiables sin rehacer nada de los tramos A y B — el punto de enchufe es el mismo (oración filtrada y lista → "algo" la convierte en sonido).

---

## 7. Riesgos y gotchas a tener en cuenta al implementar

- **Buffering de proxy en el hosting.** Si el deploy (Render/Railway/lo que sea, ver `Procfile`) o algún CDN/proxy delante bufferea la respuesta completa antes de mandarla al cliente, todo el trabajo de streaming se pierde (el navegador igual recibe todo junto al final). Hay que probarlo contra el entorno real, no solo `localhost`, y puede requerir headers específicos (`X-Accel-Buffering: no` en nginx, por ejemplo) según dónde esté deployado.
- **iOS Safari y `speechSynthesis`.** Puede necesitar que la primera invocación de audio ocurra dentro de un gesto de usuario (tap) en esa sesión de página — conviene "despertar" el motor de voz (un `speak("")` silencioso) en el primer tap del usuario en el chat, no recién cuando llega la primera respuesta.
- **`AbortController` / timeout de 25s ya existente** (`CHAT_TIMEOUT_MS` en `chat.js`). Con streaming, 25s puede ser corto o largo según cómo se mida (¿desde el primer byte o desde el último?) — probablemente conviene medir "silencio entre chunks" en vez de tiempo total, para no cortar una respuesta larga que sigue fluyendo bien.
- **Interrupción por el usuario.** Si el usuario escribe un mensaje nuevo mientras Numa todavía está "hablando" (streameando + TTS en curso), hay que: `speechSynthesis.cancel()` + abortar el `fetch` en curso (mismo `AbortController` de siempre) antes de mandar el mensaje nuevo.
- **Mensaje de crisis / `_FALLBACK_RESPONSE`.** No pasan por el LLM, así que "llegan" instantáneos — no hay nada que streamear de verdad. Para que la UI/voz no se sienta inconsistente (todo lo demás fluye, esto aparece de golpe), se puede fragmentar client-side con un timer simple (efecto máquina de escribir) antes de alimentar la cola de TTS. Es cosmético, no bloqueante.
- **`/chat/guest`** (modo invitado) usa el mismo `LLMClient.generate_response` — si se decide migrar streaming, hay que decidir si aplica ahí también o se deja para después (tiene su propio rate-limit y no persiste nada).
- **Reasoning models.** Si algún día `GROQ_MODEL`/`CHAT_MODEL` pasa a una familia con razonamiento obligatorio visible en el stream (gpt-oss con `reasoning_format=raw`, por ejemplo), hay que filtrar el bloque de razonamiento ANTES de la lógica de la sección 5, si no se cuela como si fuera parte del mensaje.
- **Memorias/mood en la UI.** Hoy `_procesarRespuesta` en `chat.js` usa `data.mood` para el estado del oso (`setBearState`) y el indicador de mood ANTES de terminar de mostrar el mensaje. Con streaming, `mood` recién se sabe en el chunk `final` (al cierre) — el oso va a "reaccionar" un toque después de que el mensaje ya arrancó a mostrarse/hablarse. Es un cambio de UX menor a decidir (¿está bien que el mood llegue al final, o conviene pedirle al modelo que lo mande primero en el JSON de metadata para adelantarlo un poco?).

---

## 8. Qué NO cambia

- Todo el pipeline de **detección/verificación de crisis** (`crisis_detector.py`, `crisis_verifier.py`) sigue corriendo síncrono, ANTES de abrir cualquier stream. Esto es no negociable: no se puede empezar a "hablar" antes de saber si hace falta la respuesta de emergencia.
- La carga de perfil/memorias/patrones/check-in y el armado del `system_prompt` (`construir_prompt`) siguen igual, síncronos, antes de la llamada al LLM.
- El guardado en Supabase (`conversation_repo.save`, memorias, `marcar_evento_followup`, etc.) se sigue disparando como tarea de background — solo cambia el momento exacto en que se dispara (al cerrar el generador del stream en vez de al final del `return` normal).
- `/chat/history` (rehidratar el chat al abrir la app) no necesita streaming — son mensajes ya guardados, se devuelven de una.

---

## 9. Plan de implementación por fases (para cuando se aplique)

1. **Fase 0 — decisiones (ya confirmadas, ver arriba):**
   - Formato A.2.a (mensaje libre + JSON al final) ✅.
   - TTS fase 1 = motor nativo del dispositivo (Web Speech API en la PWA, `expo-speech` en iOS/Android cuando exista la app RN) ✅. Proveedor pago queda descartado por ahora.
   - Cola de retención = 2 oraciones, misma cola para texto en UI y para voz ✅.
   - Pendiente de decidir (no bloquea el resto): ¿streaming en `/chat` nomás, o también `/chat/guest`? → recomendado empezar solo por `/chat` (con cuenta), sumar `/chat/guest` después si se valida bien.

2. **Fase 1 — `app/llm_client.py`:** nuevo método `generate_response_stream(...)` (generador) que abre el stream con `stream=True`, corta en el primer `{` para separar mensaje de metadata cruda, y al agotarse reusa `_reparar_json_truncado` + el parseo/validaciones que ya existen para la metadata.

3. **Fase 2 — `app/routes/chat_router.py`:** nuevo endpoint (o el mismo `/chat` con streaming condicional) que arma el `StreamingResponse` con la lógica de "cola de una oración" de la sección 5, reusando `_quitar_che`, `_aplanar_apertura`, `_quitar_cierre_presencia`, `_quitar_pregunta_final` tal cual están, solo reordenando CUÁNDO se llaman (por oración vs. al cierre).

4. **Fase 3 — `frontend/modules/chat.js`:** reemplazar `_llamarBackend`/`_procesarRespuesta` por la versión con `reader.read()` + parseo NDJSON de la sección 4, actualizando la burbuja de a poco (`bubble.innerText += ...`) en vez de crearla ya completa.

5. **Fase 4 — TTS (web):** función `hablar(oracion)` que envuelve `speechSynthesis.speak()`, alimentada por la misma cola de 2 oraciones que actualiza la UI (sección 5). Sumar un toggle de "voz activada/desactivada" (no forzar audio a quien no lo pidió) y "despertar" el motor en el primer gesto del usuario (iOS Safari). Cuando exista la app RN, esta misma función se reimplementa con `expo-speech` — el resto de la arquitectura (streaming, cola de oraciones, filtros) no cambia.

6. **Fase 5 — interrupción:** cancelar TTS + abortar fetch si el usuario manda un mensaje nuevo mientras Numa sigue hablando.

7. **Fase 6 (futura, opcional) — TTS real (C.2):** swap del `speechSynthesis.speak()` por una llamada a un proveedor de voz con audio streaming, sin tocar los tramos A/B.

---

## 10. Implementación de referencia del buffer (Python, ya validada)

Código completo de la clase que implementa la cola de 2 oraciones de la sección 5. **Es código de referencia, todavía no está enganchado a `llm_client.py`/`chat_router.py`** — vive para revisar/copiar cuando se aplique.

Se validó importando las funciones REALES de `chat_router.py` (`_quitar_che`, `_familia_apertura`, `_aplanar_apertura`, `_cierra_con_presencia`, `_quitar_cierre_presencia`, `_quitar_pregunta_final`, sin reescribirlas) y comparando, para 6 mensajes de prueba (che disperso, apertura repetida, racha de preguntas, mensaje corto, mensaje largo, crisis activa), el resultado de:
- pasar el mensaje completo por el pipeline de filtros actual (todo junto, como hoy), vs.
- "streamearlo" palabra por palabra a través del buffer y juntar lo que va emitiendo.

**Los 6 casos dieron carácter-por-carácter idénticos.** Script de la prueba: `scripts/test_buffer_streaming.py` (ver más abajo para copiarlo si se quiere re-correr).

```python
import re

_RE_SPLIT_ORACIONES = re.compile(r"(?<=[.!?…])\s+")


class BufferStreamingMensaje:
    """Retiene las últimas RETENCION oraciones sin emitir mientras el LLM
    sigue generando, para que _quitar_cierre_presencia y _quitar_pregunta_final
    (que necesitan saber cuáles son las oraciones FINALES del mensaje) sigan
    dando el mismo resultado que en el modo no-streaming.

    Asume que ya le llega SOLO la parte "mensaje" del stream (la separación
    mensaje/JSON de metadata pasa antes, en generate_response_stream).

    Uso:
        buf = BufferStreamingMensaje(
            familia_apertura_previa=familia_apertura_previa,  # de _familia_apertura(msj anterior de Numa)
            previo_cierre_presencia=previo_cierre_presencia,  # de _cierra_con_presencia(msj anterior de Numa)
            preguntas_seguidas=preguntas_seguidas,             # ya calculado hoy, sin cambios
            crisis_score=crisis_score,
            ultimo_modulo_critico=ultimo_modulo_critico,
        )
        for delta in stream_llm:                  # delta = pedacito de texto del LLM
            for oracion in buf.feed(delta):
                yield oracion                      # ya limpia -> mandar a UI + cola de TTS
        for oracion in buf.cerrar():               # al cerrarse el stream
            yield oracion
        mensaje_final = buf.mensaje_completo()     # para guardar en Supabase
    """

    RETENCION = 2  # coincide con la ventana que mira _cierra_con_presencia (partes[-2:])

    def __init__(self, *, familia_apertura_previa, previo_cierre_presencia,
                 preguntas_seguidas, crisis_score, ultimo_modulo_critico):
        self._crudo = ""            # texto sin cortar en oraciones todavía
        self._retenidas = []        # oraciones completas esperando turno (≤ RETENCION)
        self._emitidas = []         # oraciones ya devueltas (para reconstruir el mensaje completo)
        self._primera_oracion_pendiente = True
        self._familia_apertura_previa = familia_apertura_previa
        self._previo_cierre_presencia = previo_cierre_presencia
        self._preguntas_seguidas = preguntas_seguidas
        self._crisis_score = crisis_score
        self._ultimo_modulo_critico = ultimo_modulo_critico

    def _resolver_apertura(self, texto):
        """Aplica _aplanar_apertura UNA sola vez, sobre la primera oración
        que se procesa (sea al vuelo en feed() o recién en cerrar() si el
        mensaje entero cupo en la cola)."""
        if not self._primera_oracion_pendiente:
            return texto
        self._primera_oracion_pendiente = False
        familia = _familia_apertura(texto)
        if familia and familia == self._familia_apertura_previa:
            aplanado = _aplanar_apertura(texto)
            if aplanado and aplanado != texto and len(aplanado) >= 10:
                return aplanado
        return texto

    def feed(self, delta: str):
        """Alimenta un pedacito de texto que llegó del LLM. Devuelve una
        lista (puede ser vacía) de oraciones YA LISTAS para mandar."""
        self._crudo += delta
        partes = _RE_SPLIT_ORACIONES.split(self._crudo)
        if len(partes) <= 1:
            return []  # todavía no cerró ninguna oración

        # La última parte puede seguir creciendo (el LLM no mandó la
        # puntuación de cierre todavía) -> se queda en _crudo para la
        # próxima llamada.
        *completas, self._crudo = partes
        self._retenidas.extend(completas)

        salida = []
        while len(self._retenidas) > self.RETENCION:
            cruda = self._retenidas.pop(0)
            limpia = _quitar_che(cruda)
            limpia = self._resolver_apertura(limpia)
            self._emitidas.append(limpia)
            salida.append(limpia)
        return salida

    def cerrar(self):
        """Llamar cuando el stream del LLM terminó. Corre los filtros de
        cierre (_quitar_cierre_presencia, _quitar_pregunta_final) sobre lo
        que quedó retenido y devuelve la(s) oración(es) final(es)."""
        cola = list(self._retenidas)
        if self._crudo.strip():
            cola.append(self._crudo.strip())
        self._retenidas, self._crudo = [], ""
        if not cola:
            return []

        texto_cola = _quitar_che(" ".join(cola))
        texto_cola = self._resolver_apertura(texto_cola)  # no-op si ya se resolvió en feed()

        # Reconstruye el largo del mensaje COMPLETO (no solo la cola) para
        # que los guards de ratio (0.4x, 0.35x) den el mismo resultado que
        # si se hubiera filtrado todo junto al final, como hoy.
        largo_emitido = len(" ".join(self._emitidas))
        espacio = 1 if self._emitidas else 0
        largo_total_original = largo_emitido + espacio + len(texto_cola)

        if (self._crisis_score < 0.35 and not self._ultimo_modulo_critico
                and self._previo_cierre_presencia and _cierra_con_presencia(texto_cola)):
            recortado = _quitar_cierre_presencia(texto_cola)
            largo_total_recortado = largo_emitido + espacio + len(recortado)
            if recortado and len(recortado) >= 40 and largo_total_recortado >= 0.4 * largo_total_original:
                texto_cola = recortado

        if (self._preguntas_seguidas >= 2 and self._crisis_score < 0.35
                and not self._ultimo_modulo_critico
                and texto_cola.rstrip().rstrip("\"'” ").endswith("?")):
            recortado = _quitar_pregunta_final(texto_cola)
            largo_total_recortado = largo_emitido + espacio + len(recortado)
            if recortado and len(recortado) >= 40 and largo_total_recortado >= 0.35 * largo_total_original:
                texto_cola = recortado

        self._emitidas.append(texto_cola)
        return [texto_cola]

    def mensaje_completo(self) -> str:
        """El mensaje final reconstruido, para guardar en Supabase igual que hoy."""
        return " ".join(self._emitidas).strip()
```

### Cómo se engancharía (boceto, sección 9 fases 1-2)

```python
# app/llm_client.py — nuevo método generador
def generate_response_stream(self, conversation, system_prompt, ...):
    ...
    vimos_json = False
    json_crudo = ""
    for chunk in stream:  # cliente.chat.completions.create(..., stream=True)
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        if not vimos_json:
            idx = delta.find("{")
            if idx == -1:
                yield ("mensaje", delta)
            else:
                if delta[:idx]:
                    yield ("mensaje", delta[:idx])
                json_crudo += delta[idx:]
                vimos_json = True
        else:
            json_crudo += delta
    # Reusa el parseo de 3 pasos (incl. _reparar_json_truncado) que ya
    # existe para el modo no-streaming, aplicado a json_crudo.
    yield ("metadata", parsear_metadata(json_crudo))
```

```python
# app/routes/chat_router.py — generador para el StreamingResponse
def _stream_chat(...):
    buf = BufferStreamingMensaje(
        familia_apertura_previa=familia_apertura_previa,   # calculado ANTES, como hoy
        previo_cierre_presencia=previo_cierre_presencia,   # calculado ANTES, como hoy
        preguntas_seguidas=preguntas_seguidas,
        crisis_score=crisis_score,
        ultimo_modulo_critico=ultimo_modulo_critico,
    )
    metadata = None
    for tipo, valor in llm.generate_response_stream(...):
        if tipo == "mensaje":
            for oracion in buf.feed(valor):
                yield json.dumps({"type": "delta", "text": oracion}) + "\n"
        else:
            metadata = valor
    for oracion in buf.cerrar():
        yield json.dumps({"type": "delta", "text": oracion}) + "\n"

    mensaje_final = buf.mensaje_completo()
    # ... validar memorias/mood/suggested_action de `metadata` igual que hoy ...
    yield json.dumps({"type": "final", "mood": metadata["mood"], ...}) + "\n"
    # ... disparar guardado en background con mensaje_final, igual que hoy ...
```

`familia_apertura_previa` y `previo_cierre_presencia` son EXACTAMENTE los mismos cálculos que hoy hace `chat_router.py` mirando el último mensaje de Numa en `conversation` (nada cambia ahí) — solo que ahora se calculan ANTES de abrir el stream en vez de compararse contra el mensaje actual después.
