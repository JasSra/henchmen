import sys
from pathlib import Path
Path(sys.argv[1]).write_text(sys.stdin.read(), encoding='utf-8')
