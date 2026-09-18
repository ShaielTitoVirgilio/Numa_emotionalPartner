from supabase import Client, ClientOptions, create_client
from app.core.config import config

# auto_refresh_token=False: este cliente usa la SERVICE_KEY (no vence) y hoy
# nunca establece una sesion de usuario — solo hace admin.* y get_user(jwt)
# explicito, que no pasan por _save_session(). Se deja apagado igual para que,
# si alguna vez se agrega aca una llamada que si deje sesion, no arranque el
# threading.Timer de refresco automatico que se reprograma solo para siempre
# (ver el comentario largo en app/auth_service.py, _auth_client).
supabase: Client = create_client(
    config.SUPABASE_URL,
    config.SUPABASE_SERVICE_KEY,
    options=ClientOptions(auto_refresh_token=False),
)
