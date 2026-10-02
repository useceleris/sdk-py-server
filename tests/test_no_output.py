import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "useceleris_server"

# Any of these could carry the signing secret, a credential or the caller's
# claims out of the process.
OUTPUT_MODULES = {"logging", "warnings", "sys"}


def test_source_has_no_way_to_print_or_log() -> None:
    for path in SOURCE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                assert not imported & OUTPUT_MODULES, f"{path.name} imports output"
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in OUTPUT_MODULES, path.name
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", f"{path.name} prints"
