# Corrección del bug de documentación en `CLAUDE.md`

La sección **"LLM output format"** documenta el formato viejo (`memory` /
`memory_category` singular). El código real (`chat_router.py`, `numa_prompt.py`) usa
`memories[]` plural con `content`/`category`/`priority`, y las categorías válidas son 9,
no 6.

## Bloque actual (incorrecto)

````markdown
### LLM output format

The LLM always responds with JSON:
```json
{
  "message": "response text",
  "mood": "neutral|calm|happy|excited|stressed|overwhelmed|sad|anxious",
  "suggested_action": "ejercicio_id or null",
  "memory": "third-person sentence or null",
  "memory_category": "trabajo|relaciones|salud|identidad|emocional|otro|null"
}
```
````

## Bloque corregido (reemplazo propuesto)

````markdown
### LLM output format

The LLM always responds with JSON:
```json
{
  "message": "response text",
  "mood": "neutral|calm|happy|excited|stressed|overwhelmed|sad|anxious",
  "suggested_action": "ejercicio_id or null",
  "memories": [
    {
      "content": "third-person sentence with a concrete fact",
      "category": "trabajo|estudios|relaciones|salud|identidad|emocional|hobbies|vida_cotidiana|otro",
      "priority": 3
    }
  ]
}
```

`memories` is a list with 0–2 items (empty list if nothing personal was shared).
`priority` is 1–5 (validated/clamped in `chat_router.py`).
````

Además, cuando se implemente el routing, conviene actualizar en `CLAUDE.md` la fila de
`numa_prompt.py` en la tabla de arquitectura:

> `numa_prompt.py` | Builds the system prompt via module routing: ~26 specialized prompt
> modules (`MODULOS`) selected per message by `seleccionar_modulos()` (crisis score,
> mood, check-in, keywords), plus dynamic blocks (profile, memories, patterns, check-in,
> session context)

Y documentar la tabla nueva `exercise_ratings` en la sección "Database tables" cuando
Feature B esté implementada.
