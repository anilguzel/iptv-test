"""Default research universe.

An approximate list of large, liquid BIST30-type names. Index membership
changes over time: verify against the current constituents before relying on
results, and remember that using today's members for the past adds
survivorship bias (names that dropped out are missing).
"""
from __future__ import annotations

BIST30_APPROX: list[str] = [
    "AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "CCOLA", "EKGYO",
    "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL",
    "KOZAL", "KRDMD", "MGROS", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE",
    "TCELL", "THYAO", "TOASO", "TTKOM", "TUPRS", "YKBNK",
]

# SMTK (SmartKem) and Nasdaq-listed small/mid-cap semiconductor, display and
# photonics names as a peer group. Hand-picked and approximate: edit freely.
# Delisted/unknown symbols are reported as missing, not fatal.
SMTK_PEERS: list[str] = [
    "SMTK", "KOPN", "VUZI", "MVIS", "PXLW", "POET", "LPTH", "AEHR", "ATOM", "NVTS",
    "INDI", "CEVA", "QUIK", "GSIT", "AOSL", "ACMR", "ICHR", "UCTT", "PDFS", "SKYT",
    "AXTI", "LASR", "DAIO", "AMBA", "SITM", "KLIC", "COHU", "FORM", "PLAB", "VECO",
]

# Candidate pool for the screened BIST research: the BIST30 names plus other
# large, long-listed stocks. The automation keeps only those that pass the
# history/volume screen (automation/jobs.json), so a wide pool is safe.
# KOZAL is left out: Yahoo answers 404 for it (ticker changed or delisted).
BIST_WIDE: list[str] = [s for s in BIST30_APPROX if s != "KOZAL"] + [
    "VAKBN", "HALKB", "TSKB", "SKBNK", "ISMEN", "TAVHL", "ULKER", "AEFES", "VESTL",
    "DOHOL", "OTKAR", "TTRAK", "KOZAA", "AKSEN", "ZOREN",
]

UNIVERSES: dict[str, list[str]] = {"BIST30": BIST30_APPROX, "BIST_WIDE": BIST_WIDE, "SMTK_PEERS": SMTK_PEERS}


def resolve_universe(spec: str) -> list[str]:
    """A named universe ("BIST30") or a comma-separated symbol list."""
    named = UNIVERSES.get(spec.strip().upper())
    if named:
        return list(named)
    return [s.strip().upper() for s in spec.split(",") if s.strip()]
