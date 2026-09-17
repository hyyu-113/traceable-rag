from pathlib import Path

from test_loaders import document

from scripts.create_demo_data import create_demo_data
from traceable_rag.loaders import LoaderFactory


def test_demo_data_parses(tmp_path: Path) -> None:
    files = create_demo_data(tmp_path)
    assert len(files) == 3
    blocks = [LoaderFactory.load(document(path)) for path in files]
    assert any("600元" in block.text for block in blocks[0])
    assert any("20个工作日" in block.text for block in blocks[1])
    product = next(block for block in blocks[2] if "A100" in block.text)
    assert "1299" in product.text
    assert product.source_location.cell_range == "A1:E5"
