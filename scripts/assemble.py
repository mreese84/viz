"""Inline src/rides_data.js into src/template.html -> dist/index.html (one self-contained page)."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t = open(os.path.join(ROOT, "src", "template.html"), encoding="utf-8").read()
d = open(os.path.join(ROOT, "src", "rides_data.js"), encoding="utf-8").read()
os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
open(os.path.join(ROOT, "dist", "index.html"), "w", encoding="utf-8").write(t.replace("/*__DATA__*/", d))
print("wrote dist/index.html")
