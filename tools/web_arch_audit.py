# -*- coding: utf-8 -*-
"""
web_arch_audit.py — Web App Architecture Sensor (Civil Calc / Panuwat Lab)

อ่านไฟล์ HTML/JS ไฟล์เดียว → วัด "สุขภาพโครงสร้างโค้ด" + ให้ verdict การแยก module
SENSOR-ONLY · ไม่แตะ/ไม่แก้โค้ดที่ตรวจ (อ่านอย่างเดียว)

5 checkpoints (adapt จาก skill panuwat-architecture-guard เป็นเวอร์ชัน web):
  1. file size (lines / KB)
  2. <script> block size — เฉพาะ JS (exclude non-JS: calc.py ฝัง type="text/python", ตาราง JSON)
  3. function length (brace-depth heuristic) — exclude เนื้อใน non-JS block + test-harness funcs
  4. cross-scope coupling: window.__* globals (distinct)
  5. responsibility count + SPLIT verdict

Usage:
  python web_arch_audit.py [file] [--json] [--jsonl PATH] [--label TAG]
    file          ไฟล์ที่ตรวจ (default: index.html · relative ต่อ cwd)
    --json        พิมพ์ report เป็น JSON (machine-readable)
    --jsonl PATH  append 1 บรรทัด snapshot (trend log) ลง PATH
    --label TAG   ติดป้าย snapshot ใน --jsonl (เช่น baseline / pr-2)

Exit code = 0 เสมอ (เป็น sensor ไม่ใช่ gate — ไม่ทำให้ CI build ล้ม)
"""
import re, sys, io, os, json, argparse, datetime

# คอนโซล Windows default cp874 จะ crash กับภาษาไทย → force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ---- thresholds (single-file web app) ----
TH_FILE    = (1500, 4000)   # 🟢 <1500 · 🟡 1500-4000 · 🔴 >4000  (lines)
TH_BLOCK   = (600, 1200)    # JS <script> block lines
TH_FUNC    = (60, 120)      # function body lines
TH_GLOBALS = 8              # >8 distinct window.__* = watch
TH_RESP    = 4              # >=4 responsibilities ในไฟล์เดียว = split signal

# script type ที่ถือเป็น JS — อย่างอื่น = non-JS (text/python, application/json, ...) → exclude
JS_TYPES = {"", "text/javascript", "application/javascript", "module", "text/babel"}

# test-harness funcs ใหญ่โดยธรรมชาติ (โค้ดทดสอบ ไม่ใช่ tangle ของแอป) — ไม่นับเป็น RED func
EXCLUDE_FUNCS = {"runTests", "runDesignAudit", "testHarness"}

# checkpoint 5: responsibility anchors (เจอ >=1 match = ไฟล์รับผิดชอบงานนั้น)
RESPONSIBILITIES = [
    ("render/UI",    r"renderVariant|bindResultPass|\.innerHTML"),
    ("calc-bridge",  r"loadPyodide|pyodide"),
    ("state/global", r"window\.__\w+"),
    ("export",       r"ExcelJS|exportExcel|\.xlsx"),
    ("a11y",         r"enhanceA11y|aria-"),
    ("audit/test",   r"runDesignAudit|runTests"),
]

SCRIPT_OPEN = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)

# NOTE (heuristic limit): func-length ใช้ brace-depth scan. Arrow แบบไม่มี block body
# (เช่น  const f = x => x + 1) จะไม่เจอ '{' ในกรอบค้นหา → ตั้ง length=1 (กัน runaway scan).
# พอสำหรับ sensor — โค้ดแอปส่วนใหญ่ใช้ `function`/`= function`/`() => {`.
FN_PAT = re.compile(
    r"(?:\bfunction\s+(\w+)\s*\()"
    r"|(?:\b(\w+)\s*=\s*(?:async\s*)?function\b)"
    r"|(?:\b(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"
    r"|(?:\bfunction\s+(\w+))"
)


def band(v, lo, hi):
    return "GREEN" if v < lo else ("YELLOW" if v < hi else "RED")


def get_attr(attrs, name):
    m = re.search(rf'\b{name}\s*=\s*["\']([^"\']*)["\']', attrs, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def is_js(type_attr):
    return type_attr.strip().lower() in JS_TYPES


def script_blocks(src):
    """คืน list ของ <script> block พร้อม type/id + ช่วง offset/บรรทัด"""
    out = []
    for m in SCRIPT_OPEN.finditer(src):
        cstart = m.end()
        close = src.find("</script>", cstart)
        if close == -1:
            continue
        out.append({
            "l0": src.count("\n", 0, m.start()) + 1,
            "l1": src.count("\n", 0, close) + 1,
            "span": src.count("\n", m.start(), close) + 1,
            "type": get_attr(m.group(1), "type"),
            "id": get_attr(m.group(1), "id"),
            "cstart": cstart, "cend": close,
        })
    return out


def mask_non_js(src, blocks):
    """แทนเนื้อใน non-JS block ด้วย space (คง \\n เพื่อรักษาเลขบรรทัด)
    → กัน function/def ใน calc.py / ก้อน JSON หลุดเข้าการนับ func"""
    nonjs = sorted((b for b in blocks if not is_js(b["type"])), key=lambda x: x["cstart"])
    if not nonjs:
        return src
    parts, prev = [], 0
    for b in nonjs:
        parts.append(src[prev:b["cstart"]])
        parts.append(re.sub(r"[^\n]", " ", src[b["cstart"]:b["cend"]]))
        prev = b["cend"]
    parts.append(src[prev:])
    return "".join(parts)


def scan_funcs(masked):
    """หา function + ความยาว (brace-depth) บน source ที่ mask non-JS แล้ว"""
    funcs, excluded = [], []
    for m in FN_PAT.finditer(masked):
        name = next((g for g in m.groups() if g), "anon")
        start_line = masked.count("\n", 0, m.start()) + 1
        i = masked.find("{", m.end(), m.end() + 300)  # cap search → กัน runaway บน arrow-expr
        length = 1
        if i != -1:
            depth, j = 0, i
            while j < len(masked):
                c = masked[j]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            length = masked.count("\n", i, j) + 1
        (excluded if name in EXCLUDE_FUNCS else funcs).append((name, start_line, length))
    return funcs, excluded


def analyze(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()

    nlines = src.count("\n") + 1
    kb = round(len(src.encode("utf-8")) / 1024, 1)

    blocks = script_blocks(src)
    js_blocks = [b for b in blocks if is_js(b["type"])]
    nonjs_blocks = [b for b in blocks if not is_js(b["type"])]
    biggest_js = sorted(js_blocks, key=lambda b: -b["span"])[:6]
    red_blocks = [b for b in js_blocks if b["span"] >= TH_BLOCK[1]]

    funcs, excluded_funcs = scan_funcs(mask_non_js(src, blocks))
    longest = sorted(funcs, key=lambda x: -x[2])[:12]
    red_funcs = [f for f in funcs if f[2] >= TH_FUNC[1]]

    win_names = sorted(set(re.findall(r"window\.(__\w+)", src)))
    resp_hits = [label for (label, pat) in RESPONSIBILITIES if re.search(pat, src)]

    file_band = band(nlines, *TH_FILE)
    if file_band == "RED" or red_blocks or len(resp_hits) >= TH_RESP:
        verdict = "SPLIT SOON"
        verdict_th = ("ไฟล์ใหญ่/รับผิดชอบหลายงาน — เขียนโค้ดใหม่เป็น module แยก "
                      "(อย่ายัดเข้าไฟล์เดิม) · วางแผน split ไฟล์เก่าเมื่อ trend แย่ลง")
    elif file_band == "YELLOW" or any(b["span"] >= TH_BLOCK[0] for b in js_blocks):
        verdict, verdict_th = "WATCH", "เริ่มโต — จับตา trend ทุก PR"
    else:
        verdict, verdict_th = "HEALTHY", "สุขภาพโครงสร้างดี"

    return {
        "path": path, "file": os.path.basename(path),
        "lines": nlines, "kb": kb, "verdict_file": file_band, "verdict": verdict,
        "verdict_th": verdict_th,
        "js_blocks": js_blocks, "nonjs_blocks": nonjs_blocks,
        "biggest_js": biggest_js, "red_blocks": red_blocks,
        "funcs": funcs, "longest": longest, "red_funcs": red_funcs,
        "excluded_funcs": excluded_funcs,
        "globals": win_names, "resp_hits": resp_hits,
    }


def to_report(r):
    """JSON-friendly report"""
    return {
        "file": r["file"], "lines": r["lines"], "kb": r["kb"],
        "verdict_file": r["verdict_file"], "verdict": r["verdict"],
        "js_blocks": len(r["js_blocks"]), "nonjs_blocks": len(r["nonjs_blocks"]),
        "biggest_js": [[b["l0"], b["l1"], b["span"], b["id"] or b["type"] or "anon"] for b in r["biggest_js"]],
        "excluded_blocks": [[b["l0"], b["l1"], b["span"], b["id"] or b["type"]] for b in r["nonjs_blocks"]],
        "func_count": len(r["funcs"]), "red_funcs": len(r["red_funcs"]),
        "longest_funcs": r["longest"], "excluded_funcs": r["excluded_funcs"],
        "globals": len(r["globals"]), "global_names": r["globals"],
        "responsibilities": len(r["resp_hits"]), "responsibility_hits": r["resp_hits"],
    }


def append_jsonl(r, path, label):
    snap = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "label": label, "file": r["file"],
        "lines": r["lines"], "kb": r["kb"],
        "verdict_file": r["verdict_file"], "verdict": r["verdict"],
        "js_blocks": len(r["js_blocks"]), "red_blocks": len(r["red_blocks"]),
        "func_count": len(r["funcs"]), "red_funcs": len(r["red_funcs"]),
        "globals": len(r["globals"]), "responsibilities": len(r["resp_hits"]),
        "biggest_js": ([r["biggest_js"][0]["span"], r["biggest_js"][0]["id"]] if r["biggest_js"] else None),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")


def print_human(r):
    P = print
    P("=" * 66)
    P(f" WEB ARCH AUDIT · {r['path']}")
    P("=" * 66)
    P(f"[FILE]   {r['lines']} lines · {r['kb']} KB · {r['verdict_file']}  (TH {TH_FILE})")
    P(f"[SCRIPT] {len(r['js_blocks'])} JS blocks · {len(r['nonjs_blocks'])} non-JS excluded")
    for b in r["nonjs_blocks"]:
        P(f"           excluded: {b['id'] or b['type']}  L{b['l0']}-{b['l1']} ({b['span']} ln)")
    P("  biggest JS blocks:")
    for b in r["biggest_js"]:
        P(f"    L{b['l0']}-{b['l1']}  = {b['span']} lines  [{band(b['span'], *TH_BLOCK)}]  {b['id'] or ''}")
    P(f"[FUNC]   {len(r['funcs'])} funcs (+{len(r['excluded_funcs'])} test excluded) · longest:")
    for name, ln, length in r["longest"][:8]:
        P(f"    {length:>4} lines  {name}  (L{ln})  [{band(length, *TH_FUNC)}]")
    P(f"[COUPLE] window.__* distinct={len(r['globals'])}  (TH >{TH_GLOBALS})")
    P(f"         {', '.join(r['globals']) if r['globals'] else '(none)'}")
    P(f"[RESP]   {len(r['resp_hits'])} responsibilities (TH >={TH_RESP}): {', '.join(r['resp_hits'])}")
    P("=" * 66)
    P(f" VERDICT: {r['verdict']} — file={r['verdict_file']} · {len(r['red_blocks'])} RED blocks · "
      f"{len(r['red_funcs'])} RED funcs · {len(r['globals'])} globals · {len(r['resp_hits'])} resp")
    P(f"          {r['verdict_th']}")
    P("=" * 66)


def main():
    ap = argparse.ArgumentParser(description="Web App Architecture Sensor (sensor-only)")
    ap.add_argument("file", nargs="?", default="index.html", help="ไฟล์ที่ตรวจ (default: index.html)")
    ap.add_argument("--json", action="store_true", help="พิมพ์ report เป็น JSON")
    ap.add_argument("--jsonl", metavar="PATH", help="append snapshot ลง trend log")
    ap.add_argument("--label", default="", help="ติดป้าย snapshot (เช่น baseline/pr-2)")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"[web-arch-audit] ERROR: ไม่พบไฟล์: {args.file}")
        return 0  # sensor ไม่ทำให้ build ล้ม

    r = analyze(args.file)

    if args.jsonl:
        append_jsonl(r, args.jsonl, args.label)

    if args.json:
        print(json.dumps(to_report(r), ensure_ascii=False, indent=2))
    else:
        print_human(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
