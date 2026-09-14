"""Initialize durable services once per application process."""
import threading
from scena_core import init_db
from scena_media import initialize

_lock = threading.Lock()
_ready = set()


def initialize_application(db_path):
    with _lock:
        if str(db_path) not in _ready:
            init_db(db_path)
            initialize()
            _ready.add(str(db_path))
