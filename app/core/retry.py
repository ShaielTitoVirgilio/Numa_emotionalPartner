import time
from typing import Callable, TypeVar

T = TypeVar("T")


def with_retry(fn: Callable[[], T], max_attempts: int = 5, base_delay: float = 0.8) -> T:
    """
    Ejecuta fn() con reintentos y backoff lineal.
    Útil para operaciones contra Supabase que pueden fallar
    si el usuario aún no propagó en auth.users.

    Ejemplo de uso:
        with_retry(lambda: supabase.table("users_profiles").upsert({...}).execute())
    """
    last_error: Exception = Exception("No se pudo completar la operación")

    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (attempt + 1))  # 0.8s, 1.6s, 2.4s...

    raise last_error