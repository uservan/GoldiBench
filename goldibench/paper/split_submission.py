"""Split the compiled paper into the two CVPR submission files (2026-11-16): main paper (text, LLM usage statement,
references) and supplementary material (from the page titled "Supplementary Material" on).
The paper is compiled as one document so that cross-references between them work (CVPR author kit practice).
  python split_submission.py <compiled.pdf> [--out-dir DIR]     (needs pymupdf: pip install pymupdf)
Writes <name>_main.pdf and <name>_supp.pdf and prints the page counts."""
import argparse,os
import pymupdf

def main(pdf,out_dir):
    d=pymupdf.open(pdf)
    cut=next((i for i in range(len(d)) if 'Supplementary Material' in d[i].get_text()),None)
    if cut is None:raise SystemExit('no page with "Supplementary Material" found: is \\maketitlesupplementary in main.tex?')
    base=os.path.join(out_dir or os.path.dirname(os.path.abspath(pdf)),os.path.splitext(os.path.basename(pdf))[0])
    for part,(a,b) in (('main',(0,cut-1)),('supp',(cut,len(d)-1))):
        o=pymupdf.open();o.insert_pdf(d,from_page=a,to_page=b);o.save(f'{base}_{part}.pdf');print(f'{base}_{part}.pdf: {b-a+1} pages')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('pdf');ap.add_argument('--out-dir');a=ap.parse_args();main(a.pdf,a.out_dir)
