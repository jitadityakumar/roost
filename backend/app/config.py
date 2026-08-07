import os

BASE_DATA_DIR = os.environ.get(
    "ROOST_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"),
)
MEDIA_DIR = os.path.join(BASE_DATA_DIR, "media")
