# -*- coding: utf-8 -*-
"""Re-embed calc.py IN-PLACE into index.html's <script id="calc-py-src"> block.
Safe to re-run after every calc.py edit (regex replace · count=1 · function-repl avoids
backslash/group-ref escaping). Verifies a sentinel symbol is present after embed."""
import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = r"C:\Users\Jone\Desktop\civilcalc-web"
calc = open(ROOT + r"\calc.py", encoding="utf-8").read()
html = open(ROOT + r"\index.html", encoding="utf-8").read()
assert "</script>" not in calc, "calc.py contains </script> — would break embed"

pat = re.compile(r'(<script id="calc-py-src" type="text/python">)(.*?)(</script>)', re.DOTALL)
m = pat.search(html)
assert m, "calc-py-src block not found in index.html"
old_len = len(m.group(2))
new_html = pat.sub(lambda mm: mm.group(1) + "\n" + calc + "\n" + mm.group(3), html, count=1)
open(ROOT + r"\index.html", "w", encoding="utf-8").write(new_html)

# sentinels: new cantilever symbols must now be present inside the embed
for sym in ("_cantilever_VM", "dev_length_top_tension_cm", "left_cantilever", "_design_one_cantilever"):
    assert sym in new_html, f"sentinel missing after embed: {sym}"
print(f"[embed] calc.py ({len(calc)} chars) → index.html · old block {old_len} chars · "
      f"new {len(calc)} · sentinels OK · index.html now {len(new_html)} chars")
