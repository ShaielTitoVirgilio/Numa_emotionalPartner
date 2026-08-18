# app/routes/tts_router.py
"""
Token de corta duración para que la app hable directo con Cartesia.

Por qué la app NO lleva la API key: una clave embebida en un binario se extrae
con herramientas estándar, y con la de Cartesia cualquiera podría gastar
nuestros créditos. Cartesia resuelve esto con tokens de corta duración
(https://docs.cartesia.ai/api-reference/auth/access-token): el servidor los
emite con su clave permanente, acotados en permisos y en tiempo.

Por qué la app habla DIRECTO con Cartesia y no a través nuestro: en una llamada
cada oración necesita su audio, y hacer que pase por nuestro servidor agrega un
salto de red completo a cada una — justo lo que se viene peleando por bajar.
Además el audio no nos consume ancho de banda ni memoria.

El token se pide una vez por hora (dura eso como máximo) y solo trae el permiso
de TTS: aunque se filtrara, no sirve para nada más y vence solo.
"""
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user_id
from app.core.config import config
from app.core.errors import MENSAJE_GENERICO
from app.core.logging_utils import log_event
from app.core.observability import capturar_error

router = APIRouter()

_CARTESIA_URL = "https://api.cartesia.ai/access-token"

# Duración que se le pide a Cartesia (su máximo es 1h) y margen con el que la
# app debería renovarlo. Se devuelve `expira_en_s` ya con el margen descontado
# para que el cliente no tenga que saber estos números ni acertarle al reloj.
_DURACION_S = 3600
_MARGEN_RENOVACION_S = 300

# Caché en proceso: el token no depende del usuario (es nuestro, con permiso de
# TTS y nada más), así que uno solo alcanza para todos. Sin esto, cada llamada
# de cada usuario pediría uno nuevo a Cartesia en cada renovación.
_token_cache: Optional[tuple[float, str]] = None


@router.get("/tts/token")
async def tts_token(_user_id: str = Depends(get_current_user_id)):
    """Devuelve un token efímero de Cartesia con permiso solo de TTS.

    Requiere sesión iniciada (como todo el resto de la API): no queremos que
    alguien sin cuenta se sirva de nuestros créditos.
    """
    if not config.tts_cartesia_habilitado:
        # No es un error: es el interruptor. La app lo lee y usa la voz del
        # sistema. Se responde 200 a propósito para que no aparezca como falla
        # en los logs ni en Sentry.
        return {"habilitado": False}

    global _token_cache
    ahora = time.time()
    if _token_cache and _token_cache[0] > ahora:
        return {
            "habilitado": True,
            "token": _token_cache[1],
            "expira_en_s": int(_token_cache[0] - ahora),
        }

    try:
        async with httpx.AsyncClient(timeout=10) as cliente:
            r = await cliente.post(
                _CARTESIA_URL,
                headers={
                    "Authorization": f"Bearer {config.CARTESIA_API_KEY}",
                    "Cartesia-Version": config.CARTESIA_VERSION,
                    "Content-Type": "application/json",
                },
                json={"grants": {"tts": True}, "expires_in": _DURACION_S},
            )
            r.raise_for_status()
            token = (r.json() or {}).get("token")
    except Exception as e:
        capturar_error(e, contexto="tts_token")
        # La app trata cualquier fallo como "usá la voz del sistema": que Numa
        # suene robótica es mucho mejor que que no hable.
        raise HTTPException(status_code=503, detail=MENSAJE_GENERICO)

    if not token:
        raise HTTPException(status_code=503, detail=MENSAJE_GENERICO)

    vence_en = ahora + _DURACION_S - _MARGEN_RENOVACION_S
    _token_cache = (vence_en, token)
    log_event("tts_token_emitido", endpoint="/tts/token", duracion_s=_DURACION_S)
    return {"habilitado": True, "token": token, "expira_en_s": int(vence_en - ahora)}


class FalloTTS(BaseModel):
    motivo: str
    status: Optional[int] = None


@router.post("/tts/fallo")
async def tts_fallo(body: FalloTTS, user_id: str = Depends(get_current_user_id)):
    """La app avisa que la voz falló, para que aparezca en Sentry.

    Existe porque el fallo que más importa —quedarse sin créditos de Cartesia—
    pasa del lado del CLIENTE: la app le pega directo a Cartesia, así que el
    servidor nunca se enteraría por su cuenta. Y es justo el que llega sin
    aviso previo y deja el modo llamada caído para todos.

    Se reporta desde el backend en vez de meter un SDK de Sentry en la app:
    una dependencia menos y un solo lugar donde está configurada la privacidad.
    No se manda nada del contenido de la conversación, solo el motivo y el
    código HTTP.
    """
    motivo = (body.motivo or "desconocido")[:60]
    # 402/429 = sin créditos o límite alcanzado. Se separa del resto porque no
    # es un error transitorio: hasta que alguien recargue, el modo llamada no
    # funciona para NINGÚN usuario.
    sin_creditos = body.status in (402, 429)
    capturar_error(
        RuntimeError(f"TTS Cartesia caído ({motivo}, HTTP {body.status})"),
        contexto="tts_sin_creditos" if sin_creditos else "tts_fallo",
        motivo=motivo,
        status=str(body.status),
    )
    log_event(
        "tts_fallo", endpoint="/tts/fallo", user_id=user_id,
        motivo=motivo, status=body.status, sin_creditos=sin_creditos,
    )
    return {"ok": True}
