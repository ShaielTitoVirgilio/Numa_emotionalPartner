import os
from supabase import Client, ClientOptions, create_client
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

# auto_refresh_token=False por el mismo motivo que en app/core/db.py y
# app/auth_service.py: que un cliente de este proceso no pueda quedarse con un
# threading.Timer refrescando tokens por su cuenta. Hoy este cliente solo hace
# .table(...) (push en main.py) y nunca establece sesion, asi que es prevencion.
supabase: Client = create_client(
    url, key, options=ClientOptions(auto_refresh_token=False)
)
