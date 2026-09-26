import zlib, base64
from pathlib import Path
_d = Path(__file__).resolve().parent
_B64 = "".join((_d / f"bridge_ops_impl.chunk{i}.b64").read_text() for i in range(3))
_src = zlib.decompress(base64.b64decode(_B64)).decode()
exec(compile(_src, "bridge_ops_impl.py", "exec"), globals())
