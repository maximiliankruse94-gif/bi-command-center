"""Entwickler-Hilfsskript: alle lokalen XLSX klassifizieren und parsen."""
import sys, collections
sys.path.insert(0, '.')
from bi.sources.loader import fetch_local
from bi.detect import classify, PARSERS
from bi.config import workbooks
allissues = []
for wb in workbooks():
    fr = fetch_local(wb['local_file'])
    for tab, rows in fr.tabs.items():
        c = classify(wb['key'], tab, rows, expected_kinds=wb['expected_kinds'])
        n = ''
        if c.kind in PARSERS:
            p = PARSERS[c.kind].parse(rows, tab, wb['key'], **c.meta)
            n = f"rows={len(p.df)} issues={len(p.issues)}"
            allissues += p.issues
        if c.kind != wb['key'] or c.confidence < 0.9 or 'rows=0' in n or '-v' in sys.argv:
            print(f"{wb['key']:10} {tab!r:32} {c.kind:20} {c.confidence:.2f} {n} | {c.reasons[-1][:90]}")
print(collections.Counter((i.category, i.severity) for i in allissues))
if '-i' in sys.argv:
    for i in allissues:
        if i.severity != 'info' or '-ii' in sys.argv: print(i.severity, i.workbook, i.tab, i.row, i.message)
