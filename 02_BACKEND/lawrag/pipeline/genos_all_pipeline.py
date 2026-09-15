"""Retired legal meaning extraction; use genos_stages and term_generation.
Historical implementation is retained in the 20260915 schema-removal audit.
"""
def main(*args,**kwargs):
    raise ValueError('Legal meaning extraction is retired. Use 06_TOOLS/pipeline.py build-data-stages --stage all --run-id NAME')
if __name__=='__main__':main()
