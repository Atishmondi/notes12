"""Manual smoke test for REAL Gemini extraction (V0 Step 4).

NOT production infrastructure and NOT part of the pytest suite.
Requires GEMINI_API_KEY in the environment (or --api-key). Never prints the key.

Run:  uv run scripts/gemini_smoke.py --case all [--model gemini-3.6-flash]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from notes12 import DEFAULT_MODEL, extract_notes

CASES = {
    "A": (
        "Photosynthesis is the process by which green plants, algae, and some bacteria "
        "convert light energy into chemical energy. Chlorophyll absorbs light, primarily "
        "in the blue and red portions of the spectrum. During the light-dependent reactions, "
        "water is split and oxygen is released, while ATP and NADPH are produced. "
        "In the Calvin cycle, ATP and NADPH are used to convert carbon dioxide "
        "into carbohydrates."
    ),
    "B": (
        "The first iPhone was introduced by Apple in 2007. The App Store launched in 2008, "
        "allowing users to install third-party applications. In 2010, Apple introduced the "
        "iPad, expanding its mobile computing product line. In 2015, Apple launched the "
        "Apple Watch, entering the smartwatch market. In 2020, Apple announced its transition "
        "from Intel processors to its own Apple silicon for Mac computers."
    ),
    "C": (
        "Regular exercise can improve cardiovascular fitness by strengthening the heart and "
        "improving circulation. It can also increase insulin sensitivity, helping the body "
        "regulate blood glucose more effectively. Resistance training can increase muscle mass, "
        "while aerobic exercise improves endurance. Adequate recovery is important because "
        "excessive training without sufficient rest can increase fatigue and reduce performance."
    ),
}


def run_case(name: str, text: str, model: str, api_key: str | None) -> None:
    doc = extract_notes(text, model=model, api_key=api_key)
    print(f"=== Test {name} (model={model}) ===")
    print(f"title: {doc.title}")
    print(f"summary: {doc.summary}")
    print(f"map_type: {doc.map_type}")
    print(f"nodes ({len(doc.nodes)}):")
    for node in doc.nodes:
        print(f"  - {node.id} | {node.label} | type={node.type} | {node.description}")
    print(f"relationships ({len(doc.relationships)}):")
    for rel in doc.relationships:
        print(f"  - {rel.source} -> {rel.target} | type={rel.type} | directed={rel.directed}")
    print("--- full JSON ---")
    print(doc.model_dump_json(indent=2))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["A", "B", "C", "all"], default="all")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    selected = ["A", "B", "C"] if args.case == "all" else [args.case]
    for name in selected:
        run_case(name, CASES[name], args.model, args.api_key)


if __name__ == "__main__":
    main()
