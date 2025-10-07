import sys
from pathlib import Path
path = Path(sys.argv[1])
existing = path.read_text(encoding='utf-8') if path.exists() else ''
path.write_text(existing + sys.stdin.read(), encoding='utf-8')
