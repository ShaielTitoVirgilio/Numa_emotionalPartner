# app/streaming_buffer.py
"""
Buffer de retención para streaming del mensaje de Numa.

Por qué existe: _quitar_cierre_presencia y _quitar_pregunta_final (en
app/text_filters.py) necesitan saber cuáles son las oraciones FINALES del
mensaje — algo que no se puede saber mientras el LLM todavía está generando.
Esta clase resuelve eso reteniendo siempre las últimas RETENCION oraciones
sin emitir, y recién les aplica esos dos filtros cuando el stream cierra.

_quitar_che y _aplanar_apertura sí se pueden aplicar en vivo (no dependen del
final del mensaje) — se aplican apenas cada oración deja de estar retenida.

Ver docs/plan_streaming_voz.md sección 5 para el análisis completo de por qué
cada filtro es o no compatible con streaming, y scripts/test_buffer_streaming.py
para la prueba de equivalencia contra el pipeline no-streaming (6/6 casos
idénticos carácter por carácter).
"""

import re

from app.text_filters import (
    _quitar_che,
    _familia_apertura,
    _aplanar_apertura,
    _cierra_con_presencia,
    _quitar_cierre_presencia,
    _quitar_pregunta_final,
)

_RE_SPLIT_ORACIONES = re.compile(r"(?<=[.!?…])\s+")


class BufferStreamingMensaje:
    """Uso:

        buf = BufferStreamingMensaje(
            familia_apertura_previa=familia_apertura_previa,  # _familia_apertura(último msj de Numa)
            previo_cierre_presencia=previo_cierre_presencia,  # _cierra_con_presencia(último msj de Numa)
            preguntas_seguidas=preguntas_seguidas,
            crisis_score=crisis_score,
            ultimo_modulo_critico=ultimo_modulo_critico,
        )
        for delta in stream_llm:            # delta = pedacito de texto del LLM
            for oracion in buf.feed(delta):
                yield oracion                # ya limpia -> UI + cola de TTS
        for oracion in buf.cerrar():         # al cerrarse el stream del LLM
            yield oracion
        mensaje_final = buf.mensaje_completo()   # para guardar en Supabase
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

    def _resolver_apertura(self, texto: str) -> str:
        """Aplica _aplanar_apertura UNA sola vez, sobre la primera oración que
        se procesa (al vuelo en feed(), o recién en cerrar() si el mensaje
        entero cupo dentro de la cola de retención)."""
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
        lista (puede ser vacía) de oraciones YA LISTAS para mandar a UI/TTS."""
        self._crudo += delta
        partes = _RE_SPLIT_ORACIONES.split(self._crudo)
        if len(partes) <= 1:
            return []  # todavía no cerró ninguna oración

        # La última parte puede seguir creciendo (el LLM no mandó la
        # puntuación de cierre todavía) -> se queda en _crudo para la
        # próxima llamada a feed().
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
        """Llamar cuando el stream del LLM terminó (no hay más deltas). Corre
        los filtros de cierre (_quitar_cierre_presencia, _quitar_pregunta_final)
        sobre lo que quedó retenido y devuelve la(s) oración(es) final(es)."""
        cola = list(self._retenidas)
        if self._crudo.strip():
            cola.append(self._crudo.strip())
        self._retenidas, self._crudo = [], ""
        if not cola:
            return []

        texto_cola = _quitar_che(" ".join(cola))
        texto_cola = self._resolver_apertura(texto_cola)  # no-op si feed() ya lo resolvió

        # Reconstruye el largo del mensaje COMPLETO (no solo la cola) para que
        # los guards de ratio (0.4x, 0.35x) den el mismo resultado que si se
        # hubiera filtrado todo junto al final, como en el modo no-streaming.
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

        # Devolver la cola YA filtrada partida de nuevo en oraciones (no como
        # un solo bloque pegado): los filtros de cierre necesitaban ver el
        # texto completo de la cola para decidir qué cortar, pero una vez
        # decidido, no hay motivo para mandarle al frontend/TTS un solo
        # chunk gigante — eso es lo que hacía que mensajes cortos (2-3
        # oraciones, el caso más común) aparecieran "todos de una" en vez de
        # ir fluyendo oración por oración como el resto del mensaje.
        oraciones_finales = [o for o in _RE_SPLIT_ORACIONES.split(texto_cola) if o.strip()]
        return oraciones_finales or ([texto_cola] if texto_cola else [])

    def mensaje_completo(self) -> str:
        """El mensaje final reconstruido, para guardar en Supabase igual que hoy."""
        return " ".join(self._emitidas).strip()
