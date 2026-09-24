"""Audit existing final PDFs without opening original time series."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

def main():
    p=argparse.ArgumentParser();p.add_argument('output_dir',type=Path);args=p.parse_args()
    qa=Path(__file__).resolve().parent/'figure_qa'
    pdfs=sorted((args.output_dir/'figures').glob('[0-9][0-9]_*.pdf'))
    pdfs=[x for x in pdfs if not x.name.endswith('.collision-audit.pdf')]
    if not pdfs:raise ValueError('No publication PDFs to audit')
    rows=[]
    for pdf in pdfs:
        text=subprocess.run([sys.executable,str(qa/'audit_pdf_text.py'),str(pdf),'--json'],capture_output=True,text=True)
        pdf.with_suffix('.text-audit.json').write_text(text.stdout,encoding='utf-8')
        collision=subprocess.run([sys.executable,str(qa/'audit_figure_collisions.py'),str(pdf),'--json-out',str(pdf.with_suffix('.collision-audit.json'))],capture_output=True,text=True)
        rows.append({'file':pdf.name,'text_exit':text.returncode,'collision_exit':collision.returncode})
        print(f'{pdf.name}: text={text.returncode}, collision={collision.returncode}')
        if text.returncode:print(text.stderr)
        if collision.returncode:print(collision.stdout,collision.stderr)
    (args.output_dir/'figure_qa_summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return int(any(x['text_exit'] or x['collision_exit'] for x in rows))

if __name__=='__main__':raise SystemExit(main())
