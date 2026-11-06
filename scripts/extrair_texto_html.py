"""Print visible text and links from a saved HTML file.

Used to read reference pages without a headless browser and without adding
dependencies. It does not fetch anything.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo", type=Path)
    parser.add_argument("--limite", type=int, default=8000)
    args = parser.parse_args()

    bruto = args.arquivo.read_text(encoding="utf-8", errors="replace")

    print("--- LINKS ---")
    for link in dict.fromkeys(re.findall(r'href=["\']([^"\']+)', bruto)):
        print(link)

    print("--- SCRIPTS ---")
    for src in dict.fromkeys(re.findall(r'src=["\']([^"\']+)', bruto)):
        print(src)

    texto = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", bruto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", html.unescape(texto)).strip()

    print("--- TEXTO ---")
    print(texto[: args.limite])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
