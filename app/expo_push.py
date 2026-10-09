# app/expo_push.py
"""
Push nativo (iOS/Android) vía Expo Push Service. Es el equivalente, para
numa-mobile, de lo que pywebpush hace para la PWA: el contenido del mensaje
(memorias/eventos) lo arma `construir_push_contextual`, esto solo lo entrega.

Los tokens (`ExponentPushToken[...]`) viven en `device_push_tokens`. Expo se
encarga de hablar con APNs/FCM; las credenciales de Apple/Google se cargan en
EAS, no acá.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.core.db import supabase
from app.core.observability import capturar_error

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_LOTE_MAX = 100  # límite de Expo por request


def token_valido(token: str) -> bool:
    return isinstance(token, str) and token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]")


def registrar_token(user_id: str, token: str, platform: Optional[str]) -> None:
    # upsert por token: si el teléfono cambió de cuenta, el token pasa al usuario nuevo.
    supabase.table("device_push_tokens").upsert(
        {"token": token, "user_id": user_id, "platform": platform, "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="token",
    ).execute()


def borrar_token(user_id: str, token: str) -> None:
    supabase.table("device_push_tokens").delete().eq("token", token).eq("user_id", user_id).execute()


def tokens_por_usuario() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    try:
        res = supabase.table("device_push_tokens").select("user_id, token").execute()
    except Exception as e:
        # Un problema con los tokens nativos no puede frenar el push web.
        capturar_error(e, contexto="expo_push_tokens_por_usuario")
        return out
    for r in res.data or []:
        out.setdefault(r["user_id"], []).append(r["token"])
    return out


def _borrar_tokens_muertos(tokens: List[str]) -> None:
    if not tokens:
        return
    try:
        supabase.table("device_push_tokens").delete().in_("token", tokens).execute()
    except Exception as e:
        capturar_error(e, contexto="expo_push_limpiar_tokens")


def enviar(mensajes: List[Dict[str, Any]]) -> Dict[str, bool]:
    """
    Envía [{to, title, body}, ...] a Expo. Devuelve {token: aceptado_por_expo}.
    Los tokens que Expo reporta como DeviceNotRegistered (app desinstalada o
    permiso revocado) se borran de la tabla. "Aceptado" significa que Expo
    tomó el mensaje, no que ya llegó al teléfono.
    """
    resultado: Dict[str, bool] = {}
    muertos: List[str] = []
    for i in range(0, len(mensajes), _LOTE_MAX):
        lote = [
            {"sound": "default", "channelId": "default", **m}
            for m in mensajes[i:i + _LOTE_MAX]
        ]
        try:
            r = httpx.post(EXPO_PUSH_URL, json=lote, timeout=20,
                           headers={"Accept": "application/json"})
            r.raise_for_status()
            tickets = r.json().get("data", [])
        except Exception as e:
            capturar_error(e, contexto="expo_push_envio")
            for m in lote:
                resultado[m["to"]] = False
            continue
        for m, t in zip(lote, tickets):
            ok = t.get("status") == "ok"
            resultado[m["to"]] = ok
            if not ok and (t.get("details") or {}).get("error") == "DeviceNotRegistered":
                muertos.append(m["to"])
    _borrar_tokens_muertos(muertos)
    return resultado
