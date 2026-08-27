from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


def test_python_docx_is_declared_as_a_project_dependency():
    requirements = (Path(__file__).parents[2] / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "python-docx>=1.1,<2" in requirements


def test_word_export_module_remains_importable_without_python_docx(monkeypatch):
    real_import = builtins.__import__

    def import_without_docx(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "docx" or name.startswith("docx."):
            raise ImportError("python-docx intentionally unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_docx)
    module_path = Path(__file__).parents[1] / "word_export.py"
    spec = importlib.util.spec_from_file_location("word_export_without_docx", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert module.Document is None
    with pytest.raises(RuntimeError, match="python-docx"):
        module.build_word_docx({"sections": []})


def test_application_module_imports_without_python_docx():
    script = textwrap.dedent(
        """
        import builtins

        real_import = builtins.__import__

        def import_without_docx(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "docx" or name.startswith("docx."):
                raise ImportError("python-docx intentionally unavailable")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = import_without_docx
        import request_ai_agent_i0_0.app
        """
    )
    project_root = Path(__file__).parents[2]

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
