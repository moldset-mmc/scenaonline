"""Presentation boundary: desktop Streamlit or the stateless HTML web UI."""
import os

if os.environ.get('SCENA_NATIVE_WEB') == '1':
    from scena_web.widgets import st
else:
    import streamlit as st
