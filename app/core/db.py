import httpx
from supabase import Client, ClientOptions, create_client
from app.core.config import config

# auto_refresh_token=False: este cliente usa la SERVICE_KEY (no vence) y hoy
# nunca establece una sesion de usuario — solo hace admin.* y get_user(jwt)
# explicito, que no pasan por _save_session(). Se deja apagado igual para que,
# si alguna vez se agrega aca una llamada que si deje sesion, no arranque el
# threading.Timer de refresco automatico que se reprograma solo para siempre
# (ver el comentario largo en app/auth_service.py, _auth_client).
# Cliente httpx propio, HTTP/1.1. El default de postgrest es http2=True: todos los
# threads comparten UN socket multiplexado y, con las consultas en paralelo de
# _preparar_turno (chat_router.py), a veces salta "[Errno 11] Resource
# temporarily unavailable" y el turno sale sin memorias/eventos. Con HTTP/1.1
# cada thread usa su propia conexion del pool.
# pool=5: si el pool se llena, falla rapido en vez de colgar 120s.
_http = httpx.Client(
    http2=False,
    timeout=httpx.Timeout(120, pool=5),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
    follow_redirects=True,
)

supabase: Client = create_client(
    config.SUPABASE_URL,
    config.SUPABASE_SERVICE_KEY,
    options=ClientOptions(auto_refresh_token=False, httpx_client=_http),
)
