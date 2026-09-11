from pathlib import Path

from starlette.templating import Jinja2Templates

APP_ROOT = Path(__file__).parent.parent

templates = Jinja2Templates(directory=APP_ROOT / "templates")
