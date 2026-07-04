import ast
from pathlib import Path


def test_engine_has_no_framework_imports():
    """
    engine/ altındaki hiçbir dosya fastapi, httpx veya react import edemez.
    Bu, saf çekirdek (pure core) kuralıdır.
    """
    engine_dir = Path(__file__).parent.parent.parent / "src" / "backend" / "ensemble" / "engine"
    assert engine_dir.exists(), f"Engine dizini bulunamadı: {engine_dir}"

    forbidden_modules = {"fastapi", "httpx", "react", "starlette", "uvicorn"}
    violations = []

    for py_file in engine_dir.rglob("*.py"):
        content = py_file.read_text("utf-8")
        tree = ast.parse(content, filename=str(py_file))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    base_module = name.name.split(".")[0]
                    if base_module in forbidden_modules:
                        violations.append(f"{py_file.name}: import {name.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    base_module = node.module.split(".")[0]
                    if base_module in forbidden_modules:
                        violations.append(f"{py_file.name}: from {node.module} import ...")

    assert not violations, f"Yasaklı framework import'ları bulundu: {violations}"
