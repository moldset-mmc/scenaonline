"""Initialize durable services once per application process."""
import os
import threading
from scena_core import init_db
from scena_media import initialize

_lock = threading.Lock()
_ready = set()


def is_initialized(db_path):
    return str(db_path) in _ready


def initialize_application(db_path):
    with _lock:
        if str(db_path) not in _ready:
            # The launcher already completed these migrations before starting
            # its Streamlit child. The marker is scoped to that exact database.
            if not (os.environ.get('SCENA_CLOUD') == '1' and
                    os.environ.get('SCENA_INITIALIZED_DB') == str(db_path)):
                init_db(db_path)
                initialize()
            _ready.add(str(db_path))
