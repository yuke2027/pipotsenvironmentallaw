"""Run preserved regression tests with every temporary file inside this workspace."""
from pathlib import Path
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
temporary=root/'.artifacts'/'legacy-temp'
temporary.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(temporary)
import pytest

if __name__=='__main__':
    raise SystemExit(pytest.main(sys.argv[1:] or ['tests','--no-cov','-q','--tb=short',
        '--basetemp',str(root/'.artifacts'/'legacy-tests-final'),'-o',f'cache_dir={root / ".artifacts" / "pytest-cache"}']))
