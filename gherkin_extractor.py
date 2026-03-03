"""
Extract Gherkin Feature blocks from text and write .feature files.
"""
import re
from pathlib import Path


FEATURE_BLOCK = re.compile(
    r"(?:^|\n)\s*Feature:\s*[^\n]+(?:\n(?!\s*Feature:)[^\n]*)*",
    re.MULTILINE | re.IGNORECASE,
)


def extract_feature_blocks(text: str) -> list[str]:
    """
    Extract Feature blocks from text. Returns list of raw Gherkin strings.
    """
    if not text or not text.strip():
        return []

    blocks: list[str] = []
    for m in FEATURE_BLOCK.finditer(text):
        block = m.group(0).strip()
        if "Scenario:" in block or "Scenario Outline:" in block:
            blocks.append(block)
    return blocks


def feature_to_filename(feature_block: str, index: int) -> str:
    """Generate a safe filename from a Feature block."""
    m = re.search(r"Feature:\s*(.+?)(?:\n|$)", feature_block, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        name = re.sub(r"[^\w\s-]", "", name)[:50]
        name = re.sub(r"\s+", "_", name).strip("_") or f"feature_{index}"
    else:
        name = f"feature_{index}"
    return f"{name}.feature"


def write_feature_files(feature_blocks: list[str], output_dir: Path) -> list[Path]:
    """
    Write each Feature block to a .feature file under output_dir/features/.
    Returns list of written file paths.
    """
    features_dir = output_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for i, block in enumerate(feature_blocks):
        fname = feature_to_filename(block, i)
        path = features_dir / fname
        path.write_text(block, encoding="utf-8")
        paths.append(path)

    return paths
