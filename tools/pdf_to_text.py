import sys, pypdf, pathlib
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2])
r = pypdf.PdfReader(str(src))
print(src.name, "pages:", len(r.pages))
parts = []
for i, p in enumerate(r.pages):
    try:
        t = p.extract_text() or ""
    except Exception as e:
        t = f"[extract error {e}]"
    parts.append(f"\n\n===== PAGE {i+1} =====\n{t}")
out.write_text("".join(parts), encoding="utf-8")
print("->", out, out.stat().st_size, "bytes")
