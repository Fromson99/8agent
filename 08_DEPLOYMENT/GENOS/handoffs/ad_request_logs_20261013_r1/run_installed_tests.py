"""Keep multiprocessing's import of __main__ free of pytest runner side effects."""
if __name__ == '__main__':
    import runpy
    import sys
    runner = sys.argv.pop(1)
    sys.argv[0] = runner
    runpy.run_path(runner, run_name='installed_contract_runner')
