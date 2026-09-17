import re, sys, json, pathlib, bisect

raw = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
noise = re.compile(r"^(===== PAGE \d+ =====|\d{2} \w+\s+\d{4} Page \d+ of.*|Table Definition \d+|Index Summary|Index Type|NOT UNIQUE|UNIQUE|Name)$")
lines = [l.strip() for l in raw if l.strip() and not noise.match(l.strip())]
IDENT = re.compile(r"^[A-Z][A-Z0-9_\$#]*$")

idx_tn = [i for i, l in enumerate(lines) if l.startswith("Table Name : ")]
tn_names = [lines[i][len("Table Name : "):].strip() for i in idx_tn]
marks = [(i, l) for i, l in enumerate(lines) if l in ("Column", "Type", "Nulls ?")]

chunks = []
for mi, (pos, lab) in enumerate(marks):
    if lab != "Column" or mi + 1 >= len(marks) or marks[mi+1][1] != "Type":
        continue
    t = marks[mi+1][0]
    types = lines[pos+1:t]
    nulls = []
    if mi + 2 < len(marks) and marks[mi+2][1] == "Nulls ?":
        nulls = lines[t+1:marks[mi+2][0]]
    names = lines[pos-len(types):pos]
    if len(names) != len(types) or not all(IDENT.match(n) for n in names):
        # zurueck laufen und nur ALL-CAPS sammeln
        names, j = [], pos - 1
        while j >= 0 and IDENT.match(lines[j]) and len(names) < len(types):
            names.append(lines[j]); j -= 1
        names.reverse()
    if len(nulls) != len(names):
        nulls = [""] * len(names)
    if names:
        chunks.append({"pos": pos, "cols": [{"name": a, "type": b, "null": c}
                                            for a, b, c in zip(names, types, nulls)]})

pos_list = [c["pos"] for c in chunks]
def first_chunk(tn_line):
    return bisect.bisect_left(pos_list, tn_line) - 1

tables = {}
for k, ti in enumerate(idx_tn):
    j = first_chunk(ti)
    j2 = first_chunk(idx_tn[k+1]) if k + 1 < len(idx_tn) else len(chunks)
    if j < 0:
        continue
    cols, seen = [], set()
    for ch in chunks[j:max(j2, j + 1)]:
        for c in ch["cols"]:
            if c["name"] not in seen:
                seen.add(c["name"]); cols.append(c)
    end_first = chunks[j]["pos"]
    desc_lines = [l for l in lines[end_first:ti] if not IDENT.match(l) and l not in ("Column", "Type", "Nulls ?", "NULL", "NOT NULL")]
    tables[tn_names[k]] = {"columns": cols, "desc": " ".join(desc_lines)[:1200]}

print(f"{len(tables)} Tabellen, {sum(len(t['columns']) for t in tables.values())} Spalten", file=sys.stderr)
pathlib.Path(sys.argv[2]).write_text(json.dumps(tables, indent=1), encoding="utf-8")
