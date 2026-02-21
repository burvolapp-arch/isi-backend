# ISI Hardened Statistical Infrastructure Blueprint

**Document class:** Infrastructure Security Specification  
**Classification:** INTERNAL — Architecture-Critical  
**Date:** 2026-02-21  
**Status:** AUTHORITATIVE — Supersedes soft guidance in TIME_DIMENSION_V2_ARCHITECTURE.md  
**Audience:** Backend engineers, CI/CD pipeline operators, data integrity auditors  
**Companion:** `docs/TIME_DIMENSION_V2_ARCHITECTURE.md` (functional design)

---

## 0. Codebase Invariant Audit — Findings

Before specifying the hardened architecture, the following defects were identified in the current codebase. All must be resolved before or during the v2 migration.

| ID | Defect | Location | Severity |
|----|--------|----------|----------|
| **D-1** | **Rounding precision inconsistency.** Exporter uses `round(x, 8)`. Scenario engine uses `round(x, 10)`. Two different precision domains for the same logical values. | `export_isi_backend_v01.py` lines 839, 900, 984 vs `scenario.py` lines 389–391, 414–426 | **HIGH** — Breaks cross-module hash determinism |
| **D-2** | **Sort instability in exporter.** `build_isi_composite()` sorts by `-(composite)` only: `rows.sort(key=lambda x: -(x["isi_composite"] ...))`. No alphabetical tie-break. `build_axis_detail()` same pattern. `scenario.py` correctly uses `(-x[0], x[1])` for tie-break. | `export_isi_backend_v01.py` lines 944, 1008 vs `scenario.py` line 318 | **HIGH** — Non-deterministic rank for tied composites |
| **D-3** | **Non-atomic file writes.** `write_json()` writes directly to the final path via `open(filepath, "w")`. A crash mid-write produces a corrupt partial JSON file in the target directory. | `export_isi_backend_v01.py` line 513 | **HIGH** — Partial snapshot corruption |
| **D-4** | **JSON key order not canonicalized.** `json.dump(..., sort_keys=False)`. Key order depends on CPython dict insertion order. Not guaranteed across Python versions for hashing purposes. | `export_isi_backend_v01.py` line 515 | **MEDIUM** — File-level SHA-256 not reproducible across interpreter versions |
| **D-5** | **No computation hash.** No per-country computation hash exists anywhere. MANIFEST.json only contains file-level SHA-256 of serialized JSON. No mechanism to detect if the same source data + methodology produces the same result. | Entire codebase | **HIGH** — No reproducibility verification |
| **D-6** | **No methodology registry.** Classification thresholds and aggregation formula are hardcoded in two files (`export_isi_backend_v01.py` line 524: `classify_score()`, `scenario.py` lines 79–84: `_CLASSIFICATION_THRESHOLDS`). No frozen registry. A developer can change one and forget the other. | `export_isi_backend_v01.py`, `scenario.py` | **CRITICAL** — Dual-source-of-truth for thresholds |
| **D-7** | **"Latest" is implicit.** No registry file declares which year and methodology version is "latest." The API serves whatever files exist in `backend/v01/`. | `isi_api_v01.py` | **MEDIUM** — Implicit state |
| **D-8** | **MANIFEST has no snapshot-level provenance.** MANIFEST.json records file hashes but no methodology version, year, computation hashes, or pipeline version. | `scripts/generate_manifest.py` | **MEDIUM** — Insufficient provenance |

---

## 1. Determinism Specification

### 1.1 Global Rounding Constant

```python
# backend/constants.py — SINGLE SOURCE OF TRUTH

ROUND_PRECISION: int = 8

# All axis scores, composite scores, statistics, shares, and
# any floating-point value that enters storage or hashing
# MUST be rounded to exactly ROUND_PRECISION decimal places
# BEFORE any downstream use (classification, sorting, hashing,
# JSON serialization).

# This resolves D-1.
```

**Migration requirement:** `scenario.py` must change from `round(x, 10)` to `round(x, ROUND_PRECISION)`. The exporter already uses `round(x, 8)` — it must import `ROUND_PRECISION` instead of using the literal.

**Rounding rule:**
- Python's `round()` uses banker's rounding (round-half-to-even). This is acceptable and deterministic.
- **All rounding happens ONCE, at the earliest point where the value is finalized.** No double-rounding.
- Values are rounded BEFORE classification, BEFORE sorting, BEFORE hashing, BEFORE JSON serialization.

**Rounding order of operations (mandatory):**
```
1. Raw float from CSV parse
2. round(raw_float, ROUND_PRECISION) → axis_score
3. classify(axis_score) → classification  (uses already-rounded value)
4. composite = round(mean(rounded_axes), ROUND_PRECISION)
5. classify(composite) → composite_classification
6. sort(countries)  (uses rounded composites)
7. rank assignment
8. computation_hash(rounded values)
9. JSON serialization
```

### 1.2 Canonical Float Formatting for Hashing

```python
def canonical_float(value: float) -> str:
    """Convert a rounded float to its canonical string representation for hashing.

    Uses fixed-point notation with exactly ROUND_PRECISION decimal places.
    No scientific notation. No trailing zeros removal. No locale sensitivity.

    Examples:
        canonical_float(0.5)        → "0.50000000"
        canonical_float(0.11646504) → "0.11646504"
        canonical_float(1.0)        → "1.00000000"
        canonical_float(0.0)        → "0.00000000"
    """
    return f"{value:.{ROUND_PRECISION}f}"
```

**Invariant:** `canonical_float(round(x, ROUND_PRECISION))` produces identical output on CPython 3.10, 3.11, 3.12, 3.13, and 3.14. This is guaranteed because IEEE 754 double-precision can exactly represent all values with ≤8 significant decimal digits after rounding, and Python's `f"{x:.8f}"` uses the same `dtoa` implementation across versions.

### 1.3 Stable Sort Rules

**All ranked lists** (countries by composite, countries by axis score, partners by share) must use a **deterministic tie-break**:

```python
# Primary: score descending (highest dependency first)
# Secondary: ISO country code ascending (alphabetical)
countries.sort(key=lambda x: (-x["isi_composite"], x["country"]))
```

**This resolves D-2.** The exporter currently omits the tie-break.

**Sort stability guarantee:** Python's `list.sort()` is a stable sort (Timsort). The two-key sort above is fully deterministic for any input.

### 1.4 Deterministic JSON Serialization

```python
def write_canonical_json(filepath: Path, data: object) -> None:
    """Write JSON in canonical form suitable for reproducible hashing.

    Rules:
    - sort_keys=True (alphabetical key order, deterministic across Python versions)
    - ensure_ascii=False (UTF-8 output, no \\uXXXX escapes for printable chars)
    - indent=2 (human-readable, stable across versions)
    - Trailing newline (POSIX convention)
    - No trailing whitespace
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    content += "\n"
    # Atomic write: write to temp, then rename (see §3)
    _atomic_write(filepath, content.encode("utf-8"))
```

**This resolves D-4.** Changing from `sort_keys=False` to `sort_keys=True`.

**Impact analysis:** This changes the byte content of existing JSON files. Therefore:
- All MANIFEST.json SHA-256 hashes will change.
- This is acceptable — the v1.0/2024 snapshot is re-materialized once under the new canonical serialization, and that becomes the frozen truth.
- Old `backend/v01/` files are NOT retroactively changed. They remain as-is for backward compatibility. The canonical form applies only to `backend/snapshots/` directories.

### 1.5 Hash Input Specification

See §2 for the full hash specification.

---

## 2. Hash Specification

### 2.1 Per-Country Computation Hash

Each country within a snapshot has a deterministic computation hash:

```python
import hashlib

def compute_country_hash(
    country_code: str,
    year: int,
    methodology_version: str,
    axis_scores: dict[str, float],       # {axis_slug: rounded_score}
    composite: float,                     # rounded
    data_window: str,
    methodology_params: dict,             # from registry
) -> str:
    """Compute SHA-256 hash of a country's snapshot computation.

    All float values MUST already be rounded to ROUND_PRECISION before calling.
    """
    # Axis scores in canonical order (alphabetical by slug)
    axis_slugs = sorted(axis_scores.keys())

    parts = [
        f"country={country_code}",
        f"year={year}",
        f"methodology={methodology_version}",
        f"data_window={data_window}",
    ]

    for slug in axis_slugs:
        parts.append(f"axis.{slug}={canonical_float(axis_scores[slug])}")

    parts.append(f"composite={canonical_float(composite)}")
    parts.append(f"aggregation_rule={methodology_params['aggregation_rule']}")

    # Weights in canonical order
    weights = methodology_params["axis_weights"]
    for slug in axis_slugs:
        parts.append(f"weight.{slug}={canonical_float(weights[slug])}")

    # Thresholds as canonical string
    thresholds = methodology_params["classification_thresholds"]
    for threshold, label in sorted(thresholds, key=lambda t: -t[0]):
        parts.append(f"threshold={canonical_float(threshold)}:{label}")

    parts.append(f"default_classification={methodology_params['default_classification']}")

    hash_input = "\n".join(parts) + "\n"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
```

**Properties:**
- **Canonical order:** All keys sorted alphabetically. Thresholds sorted descending by value.
- **No hidden parameters:** Every value that affects the computation is in the hash input.
- **Text-based:** Hash input is a human-readable text block, inspectable for debugging.
- **Newline-terminated:** Every field on its own line, final newline included.
- **Encoding:** UTF-8, explicitly specified.

### 2.2 Snapshot-Level Hash

The snapshot hash covers all 27 countries:

```python
def compute_snapshot_hash(country_hashes: dict[str, str]) -> str:
    """Compute the snapshot-level hash from all per-country hashes.

    country_hashes: {country_code: hex_hash} — must have exactly 27 entries.
    """
    if len(country_hashes) != 27:
        raise ValueError(f"Expected 27 country hashes, got {len(country_hashes)}")

    parts = []
    for code in sorted(country_hashes.keys()):
        parts.append(f"{code}={country_hashes[code]}")

    hash_input = "\n".join(parts) + "\n"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
```

### 2.3 HASH_SUMMARY.json

Each snapshot directory contains a `HASH_SUMMARY.json`:

```json
{
  "schema_version": 1,
  "year": 2024,
  "methodology_version": "v1.0",
  "snapshot_hash": "a1b2c3d4...",
  "computed_at": "2026-02-21T00:00:00+00:00",
  "computed_by": "export_isi_backend_v02.py@abc1234",
  "round_precision": 8,
  "country_hashes": {
    "AT": "e5f6a7b8...",
    "BE": "c9d0e1f2...",
    "...": "..."
  }
}
```

**Invariant:** This file is written LAST, after all other snapshot files. Its presence signals a complete, verified snapshot.

---

## 3. Atomic Snapshot Writing Protocol

### 3.1 Problem Statement (D-3)

Current `write_json()` writes directly to the final path. A crash, disk full, or kill -9 during the write loop produces a partial snapshot directory — some files written, others missing or truncated.

### 3.2 Protocol

```
1. Create temp directory: backend/snapshots/.tmp_{methodology}_{year}_{uuid}/
2. Write ALL snapshot files into temp directory:
   - isi.json
   - axis/{n}.json  (n = 1..6)
   - country/{CODE}.json  (27 files)
   - MANIFEST.json
3. Compute and verify ALL hashes.
4. Write HASH_SUMMARY.json into temp directory (LAST file written).
5. Verify: HASH_SUMMARY.json exists AND file_count matches expected.
6. Check: final directory backend/snapshots/{methodology}/{year}/ does NOT exist.
   If it exists → ABORT. Snapshot already materialized. Never overwrite.
7. Atomic rename: os.rename(temp_dir, final_dir)
   - On the same filesystem, rename() is atomic on POSIX.
   - Guarantees: either the full snapshot appears at the final path, or nothing does.
8. Log success with snapshot_hash.
```

### 3.3 Implementation Pseudocode

```python
import os
import uuid
import shutil
from pathlib import Path

SNAPSHOTS_ROOT = Path("backend/snapshots")

def materialize_snapshot(
    year: int,
    methodology: str,
    data: SnapshotData,
) -> None:
    """Write a complete snapshot atomically."""

    final_dir = SNAPSHOTS_ROOT / methodology / str(year)

    # ── FREEZE ENFORCEMENT ──
    if final_dir.exists():
        raise SnapshotExistsError(
            f"Snapshot already exists at {final_dir}. "
            f"Historical snapshots are immutable. "
            f"To publish revised data, register a new methodology version."
        )

    # ── TEMP DIRECTORY ──
    temp_name = f".tmp_{methodology}_{year}_{uuid.uuid4().hex[:8]}"
    temp_dir = SNAPSHOTS_ROOT / temp_name
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        # Write all files
        _write_snapshot_files(temp_dir, data)

        # Compute and write HASH_SUMMARY.json
        hash_summary = _compute_hash_summary(temp_dir, year, methodology, data)
        _write_canonical_json(temp_dir / "HASH_SUMMARY.json", hash_summary)

        # Verify completeness
        expected_files = 1 + 6 + 27 + 1 + 1  # isi + axes + countries + manifest + hash_summary
        actual_files = len(list(temp_dir.rglob("*.json")))
        if actual_files != expected_files:
            raise SnapshotIncompleteError(
                f"Expected {expected_files} files, found {actual_files}"
            )

        # ── ATOMIC PROMOTION ──
        os.rename(temp_dir, final_dir)

    except Exception:
        # Clean up temp directory on ANY failure
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
```

### 3.4 Crash Recovery

On startup, the exporter or a separate cleanup script scans `backend/snapshots/` for directories matching `.tmp_*`. These are remnants of failed materializations. They are **deleted unconditionally** — they never contain a complete, verified snapshot.

```python
def cleanup_partial_snapshots() -> int:
    """Remove any temp directories from failed materializations."""
    removed = 0
    for d in SNAPSHOTS_ROOT.iterdir():
        if d.is_dir() and d.name.startswith(".tmp_"):
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
```

---

## 4. Methodology Registry Enforcement Mechanism

### 4.1 Problem Statement (D-6)

Classification thresholds and the aggregation formula currently exist in **two independent locations**:

- `export_isi_backend_v01.py`: `classify_score()` with hardcoded thresholds
- `scenario.py`: `_CLASSIFICATION_THRESHOLDS` with hardcoded thresholds

A developer can change one and forget the other. There is no enforcement.

### 4.2 Single Source of Truth

```python
# backend/methodology.py — THE ONLY PLACE methodology parameters exist

from __future__ import annotations
import json
import hashlib
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parent / "snapshots" / "registry.json"

_registry_cache: dict[str, dict] | None = None


def _load_registry() -> dict[str, dict]:
    """Load and validate the methodology registry. Cached after first call."""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache

    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(
            f"Methodology registry not found: {REGISTRY_PATH}. "
            f"This file is required for all ISI operations."
        )

    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)

    registry: dict[str, dict] = {}
    for entry in raw["methodologies"]:
        version = entry["methodology_version"]
        _validate_methodology_entry(version, entry)
        registry[version] = entry

    # Validate latest pointer
    latest = raw.get("latest")
    if latest not in registry:
        raise ValueError(
            f"Registry 'latest' points to '{latest}' which is not in the registry."
        )

    registry["__latest__"] = latest
    _registry_cache = registry
    return registry


def get_methodology(version: str) -> dict:
    """Get a specific methodology version. Raises KeyError if not found."""
    reg = _load_registry()
    if version not in reg or version.startswith("__"):
        raise KeyError(f"Unknown methodology version: '{version}'")
    return reg[version]


def get_latest_methodology_version() -> str:
    """Get the version string of the latest methodology."""
    reg = _load_registry()
    return reg["__latest__"]


def get_latest_year() -> int:
    """Get the latest year from the registry."""
    reg = _load_registry()
    latest_v = reg["__latest__"]
    return reg[latest_v]["latest_year"]


def classify(score: float, methodology_version: str) -> str:
    """Classify a score using the thresholds from the specified methodology.

    THIS IS THE ONLY CLASSIFICATION FUNCTION. Both the exporter and the
    scenario engine MUST call this. No hardcoded thresholds elsewhere.
    """
    m = get_methodology(methodology_version)
    for threshold, label in m["classification_thresholds"]:
        if score >= threshold:
            return label
    return m["default_classification"]


def compute_composite(axis_scores: dict[str, float], methodology_version: str) -> float:
    """Compute composite using the methodology's aggregation rule.

    THIS IS THE ONLY COMPOSITE FUNCTION. Both the exporter and the
    scenario engine MUST call this. No hardcoded formula elsewhere.
    """
    m = get_methodology(methodology_version)
    rule = m["aggregation_rule"]
    weights = m["axis_weights"]

    if rule == "unweighted_arithmetic_mean":
        return sum(axis_scores.values()) / len(axis_scores)
    elif rule == "weighted_arithmetic_mean":
        total_weight = sum(weights[k] for k in axis_scores)
        return sum(axis_scores[k] * weights[k] for k in axis_scores) / total_weight
    else:
        raise ValueError(f"Unknown aggregation rule: {rule}")
```

### 4.3 Registry File Format

`backend/snapshots/registry.json`:

```json
{
  "schema_version": 1,
  "latest": "v1.0",
  "methodologies": [
    {
      "methodology_version": "v1.0",
      "label": "ISI Baseline Methodology — Unweighted HHI Mean",
      "frozen_at": "2026-02-21T00:00:00+00:00",
      "latest_year": 2024,
      "years_available": [2022, 2023, 2024],
      "aggregation_rule": "unweighted_arithmetic_mean",
      "aggregation_formula": "ISI_i = (A1 + A2 + A3 + A4 + A5 + A6) / 6",
      "axis_count": 6,
      "axis_slugs": [
        "critical_inputs", "defense", "energy",
        "financial", "logistics", "technology"
      ],
      "axis_weights": {
        "critical_inputs": 1.0,
        "defense": 1.0,
        "energy": 1.0,
        "financial": 1.0,
        "logistics": 1.0,
        "technology": 1.0
      },
      "classification_thresholds": [
        [0.50, "highly_concentrated"],
        [0.25, "moderately_concentrated"],
        [0.15, "mildly_concentrated"]
      ],
      "default_classification": "unconcentrated",
      "score_range": [0.0, 1.0],
      "round_precision": 8,
      "notes": "Initial methodology. All axes equally weighted."
    }
  ]
}
```

### 4.4 Enforcement Rules

| Rule | Mechanism |
|------|-----------|
| **No duplicate methodology versions.** | `_load_registry()` validates uniqueness. |
| **No modification of frozen methodologies.** | Registry file is checked into git. CI rejects PRs that modify any methodology entry where `frozen_at` is in the past. |
| **Classification thresholds are read-only from registry.** | `export_isi_backend_v01.py` and `scenario.py` must import `classify()` from `methodology.py`. Their local `classify_score()` and `_CLASSIFICATION_THRESHOLDS` are DELETED. |
| **Composite formula is read-only from registry.** | Both modules must import `compute_composite()` from `methodology.py`. |
| **CI check: no hardcoded thresholds.** | A grep-based CI check scans all Python files for `0.50`, `0.25`, `0.15` threshold literals outside `methodology.py` and `registry.json`. Fail on match. |
| **Registry hash.** | The registry file itself has a SHA-256 in MANIFEST.json. Any modification is detectable. |

### 4.5 Methodology Drift Detection

```python
def verify_methodology_consistency(methodology_version: str) -> list[str]:
    """Verify no code drift from registry-defined methodology.

    Returns list of errors. Empty list = consistent.
    """
    errors = []
    m = get_methodology(methodology_version)

    # Verify axis count
    if m["axis_count"] != len(m["axis_slugs"]):
        errors.append(f"axis_count ({m['axis_count']}) != len(axis_slugs) ({len(m['axis_slugs'])})")

    # Verify weights cover all axes
    if set(m["axis_weights"].keys()) != set(m["axis_slugs"]):
        errors.append(f"axis_weights keys do not match axis_slugs")

    # Verify thresholds are descending
    thresholds = [t[0] for t in m["classification_thresholds"]]
    if thresholds != sorted(thresholds, reverse=True):
        errors.append(f"classification_thresholds are not in descending order")

    # Verify score range
    if m["score_range"] != [0.0, 1.0]:
        errors.append(f"Unexpected score_range: {m['score_range']}")

    return errors
```

---

## 5. Cache System Redesign

### 5.1 Current Cache (Deficient)

```python
# Current: unkeyed, unbounded, preload-on-access
_cache: dict[str, Any] = {}  # key examples: "isi", "country:SE", "axis:1"
```

Problems:
- No year dimension
- No methodology dimension
- Unbounded — no eviction
- Implicit "latest" — whatever is loaded is the truth

### 5.2 Redesigned Cache

```python
from collections import OrderedDict
from typing import Any
from pathlib import Path
import json
import os
import threading

# Configuration
MAX_CACHED_YEARS: int = int(os.getenv("MAX_CACHED_YEARS", "5"))
SNAPSHOTS_ROOT: Path = Path(__file__).resolve().parent / "snapshots"


class SnapshotCache:
    """Year- and methodology-aware LRU cache for snapshot data.

    Cache key: (methodology_version, year, artifact_name)
    Eviction: LRU by (methodology, year) pair. When MAX_CACHED_YEARS is
    exceeded, the least-recently-used year-methodology pair is evicted entirely.

    Thread safety: All reads/writes are protected by a reentrant lock.
    """

    def __init__(self, max_years: int = MAX_CACHED_YEARS) -> None:
        self._max_years = max_years
        self._lock = threading.RLock()
        # OrderedDict for LRU tracking: key = (methodology, year)
        # value = dict[artifact_name, Any]
        self._store: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()

    def get(
        self, methodology: str, year: int, artifact: str
    ) -> Any | None:
        """Get a cached artifact. Returns None on miss. Moves to MRU on hit."""
        key = (methodology, year)
        with self._lock:
            if key not in self._store:
                return None
            bucket = self._store[key]
            if artifact not in bucket:
                return None
            # Move to end (most recently used)
            self._store.move_to_end(key)
            return bucket[artifact]

    def put(
        self, methodology: str, year: int, artifact: str, data: Any
    ) -> None:
        """Insert or update a cached artifact. Evicts LRU year if over limit."""
        key = (methodology, year)
        with self._lock:
            if key not in self._store:
                self._store[key] = {}
            self._store[key][artifact] = data
            self._store.move_to_end(key)
            # Evict oldest year-methodology pairs
            while len(self._store) > self._max_years:
                evicted_key, _ = self._store.popitem(last=False)
                # Log eviction for observability

    def get_or_load(
        self, methodology: str, year: int, artifact: str
    ) -> Any | None:
        """Cache-through loader. Loads from disk on miss."""
        cached = self.get(methodology, year, artifact)
        if cached is not None:
            return cached

        # Resolve file path
        filepath = self._resolve_path(methodology, year, artifact)
        if filepath is None or not filepath.is_file():
            return None

        with open(filepath, encoding="utf-8") as fh:
            data = json.load(fh)

        self.put(methodology, year, artifact, data)
        return data

    def _resolve_path(
        self, methodology: str, year: int, artifact: str
    ) -> Path | None:
        """Resolve artifact name to file path within snapshot directory."""
        snapshot_dir = SNAPSHOTS_ROOT / methodology / str(year)
        if not snapshot_dir.is_dir():
            return None

        # artifact examples: "isi", "country:SE", "axis:1", "meta"
        if artifact.startswith("country:"):
            code = artifact.split(":", 1)[1]
            return snapshot_dir / "country" / f"{code}.json"
        elif artifact.startswith("axis:"):
            n = artifact.split(":", 1)[1]
            return snapshot_dir / "axis" / f"{n}.json"
        else:
            return snapshot_dir / f"{artifact}.json"

    def stats(self) -> dict:
        """Return cache statistics for /ready endpoint."""
        with self._lock:
            return {
                "cached_year_methodology_pairs": len(self._store),
                "max_cached_years": self._max_years,
                "loaded_pairs": [
                    {"methodology": k[0], "year": k[1], "artifacts": len(v)}
                    for k, v in self._store.items()
                ],
            }
```

### 5.3 Backward Compatibility Shim

Existing endpoints (`GET /isi`, `GET /country/{code}`, etc.) must continue to work without specifying year or methodology. They resolve to the latest:

```python
# In isi_api_v01.py

from backend.methodology import get_latest_methodology_version, get_latest_year

_snapshot_cache = SnapshotCache()


def _get_latest(artifact: str) -> Any | None:
    """Load an artifact from the latest snapshot. Drop-in replacement for _get_or_load()."""
    methodology = get_latest_methodology_version()
    year = get_latest_year()
    return _snapshot_cache.get_or_load(methodology, year, artifact)
```

All existing endpoint handlers change from `_get_or_load("isi", BACKEND_ROOT / "isi.json")` to `_get_latest("isi")`. No behavior change. No response shape change.

### 5.4 Memory Bounds

| Scenario | Cached Pairs | Estimated RSS |
|----------|-------------|---------------|
| Single year (current) | 1 | ~3 MB |
| 3 years × 1 methodology | 3 | ~9 MB |
| 5 years × 1 methodology | 5 (max default) | ~15 MB |
| 5 years × 2 methodologies | 5 (LRU evicts oldest) | ~15 MB |
| 10 years × 1 methodology (override) | 10 | ~30 MB |

Railway instances have 512 MB. Even at `MAX_CACHED_YEARS=10`, cache is <6% of available memory.

---

## 6. Freeze Policy Enforcement Logic

### 6.1 Core Rule

> **Once a snapshot directory `backend/snapshots/{methodology}/{year}/` exists, it is IMMUTABLE.**
>
> No file within it may be modified, added, or deleted.
>
> No exception. No override flag. No force mode.

### 6.2 Enforcement Points

#### 6.2.1 Exporter (Materialization Time)

```python
def materialize_snapshot(year: int, methodology: str, data: SnapshotData) -> None:
    final_dir = SNAPSHOTS_ROOT / methodology / str(year)

    if final_dir.exists():
        raise SnapshotExistsError(
            f"FREEZE VIOLATION: Snapshot {methodology}/{year} already exists. "
            f"Cannot overwrite historical truth. "
            f"If source data has been revised, register a new methodology version."
        )

    # ... atomic write protocol (§3) ...
```

**No `--force` flag.** No `--overwrite` flag. The code physically cannot overwrite a snapshot. A developer who needs to correct data must:

1. Register a new methodology version (e.g., `v1.0-rev1` or `v1.1`).
2. Materialize the correction as a new snapshot under the new version.
3. Old snapshot remains queryable.

#### 6.2.2 CI/CD Pipeline

```yaml
# .github/workflows/freeze_check.yml

- name: Verify snapshot immutability
  run: |
    # Check that no existing snapshot files were modified in this PR
    CHANGED=$(git diff --name-only origin/main...HEAD -- 'backend/snapshots/')
    if [ -n "$CHANGED" ]; then
      echo "FREEZE VIOLATION: Snapshot files modified:"
      echo "$CHANGED"
      exit 1
    fi
```

#### 6.2.3 Runtime (API Startup)

```python
# During lifespan startup
for methodology_dir in SNAPSHOTS_ROOT.iterdir():
    if not methodology_dir.is_dir() or methodology_dir.name.startswith("."):
        continue
    for year_dir in methodology_dir.iterdir():
        if not year_dir.is_dir():
            continue
        # Verify HASH_SUMMARY.json exists (completeness marker)
        hash_summary_path = year_dir / "HASH_SUMMARY.json"
        if not hash_summary_path.is_file():
            logger.error(f"INCOMPLETE SNAPSHOT: {year_dir} — missing HASH_SUMMARY.json")
            # Do not serve this snapshot
```

#### 6.2.4 Filesystem Permissions (Defense in Depth)

After successful materialization:

```python
import stat

def make_readonly(directory: Path) -> None:
    """Remove write permissions from all files in a snapshot directory."""
    for f in directory.rglob("*"):
        if f.is_file():
            f.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444
    directory.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP |
                    stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)    # 0o555
```

This is defense-in-depth. The primary protection is the code-level freeze check. The filesystem permissions are a secondary barrier against accidental `echo "oops" > backend/snapshots/v1.0/2024/isi.json`.

### 6.3 Revision Policy

| Scenario | Allowed? | Procedure |
|----------|----------|-----------|
| Correct a typo in a country name | ❌ No. Snapshot is immutable. | Register new methodology version. |
| Revise 2022 data because BIS corrected their dataset | ❌ No overwrite. | Register `v1.0-rev1` with notes documenting the BIS revision. Materialize new snapshots. |
| Add a 7th axis | ❌ Incompatible with v1.0 schema. | Register `v2.0` with `axis_count: 7`. Old snapshots remain 6-axis under v1.0. |
| Fix a bug in the composite formula | ❌ Formula change = methodology change. | Register new version. Backfill all years under new version. |
| Add a new year (2025) | ✅ Yes. | Materialize `v1.0/2025/` snapshot. Does not modify any existing snapshot. |

---

## 7. Attack Surface Audit Table

| # | Adversarial Event | Detection | Prevention | Recovery |
|---|------------------|-----------|------------|----------|
| **T-1** | CSV file for 2022 changes silently in 2028 | `verify_snapshot.py --year 2022 --methodology v1.0` recomputes from CSV → hash mismatch detected | Git versioning of source CSVs. CI rejects CSV changes without methodology version bump. | Frozen snapshot is unaffected. CSV change only affects future materializations under new methodology. |
| **T-2** | Developer modifies classification thresholds but forgets to bump methodology version | CI grep check: scan for threshold literals outside `registry.json` and `methodology.py`. Fail on match. | Single-source classify() in `methodology.py`. No hardcoded thresholds anywhere else (D-6 resolution). | `verify_methodology_consistency()` detects parameter mismatch at pipeline runtime. |
| **T-3** | Python 3.12→3.14 produces slightly different float ordering | Fixed-precision `canonical_float()` with `round(x, 8)` + `f"{x:.8f}"` formatting eliminates platform variance. Hash is over formatted strings, not raw floats. | `ROUND_PRECISION=8` is within IEEE 754 exact-representation range. `f"{x:.8f}"` is deterministic across CPython versions. | Computation hash detects any divergence. |
| **T-4** | Snapshot directory partially written before crash | Atomic write protocol (§3): write to `.tmp_*` dir, then `os.rename()`. | `os.rename()` is atomic on POSIX for same-filesystem renames. | Startup cleanup deletes `.tmp_*` directories. Incomplete snapshots never reach final path. |
| **T-5** | Cache memory exhaustion | `MAX_CACHED_YEARS` env var bounds cache size. `SnapshotCache.stats()` exposed on `/ready`. | LRU eviction in `SnapshotCache`. Default limit: 5 year-methodology pairs (~15 MB). | Reduce `MAX_CACHED_YEARS`. Or increase Railway instance memory. |
| **T-6** | User manually edits a JSON snapshot file | MANIFEST.json SHA-256 check at API startup via `verify_manifest()`. Hash mismatch → log error, refuse to serve. | Filesystem permissions `chmod 0o444` on snapshot files (§6.2.4). | Re-materialize from source CSVs if needed (but never into the same snapshot directory — freeze policy). |
| **T-7** | Hash mismatch during recomputation (verify_snapshot.py) | CLI tool exits non-zero. Reports which countries/fields diverged. | This IS the detection mechanism. Causes are: CSV changed (T-1), methodology changed (T-2), or platform float issue (T-3). | Investigate root cause. If CSV revision: register new methodology. If platform issue: pin Python version. |
| **T-8** | Methodology removes or adds an axis | `methodology_registry.axis_count` changes → incompatible with existing snapshots. | Registry enforces axis_count per version. Old versions retain their axis_count. `compute_composite()` dynamically reads axis list from methodology. | New methodology version handles new axis set. Old snapshots remain valid under old methodology. |
| **T-9** | Two pipeline runs race to materialize the same (year, methodology) | First `os.rename()` succeeds. Second `os.rename()` fails because target exists (POSIX: `rename()` on existing directory fails with `OSError` unless target is empty). | Pre-check `final_dir.exists()` before writing. Second runner sees it and aborts. | No corruption. First-writer wins. |
| **T-10** | Registry.json itself is corrupted or manually edited | SHA-256 of `registry.json` in the root-level MANIFEST. Startup validation of registry structure. | Git tracking. CI validation. | Revert from git history. |

---

## 8. Failure Mode Handling

### 8.1 Failure Taxonomy

| Failure Mode | Symptoms | System Response | Operator Action |
|-------------|----------|----------------|-----------------|
| **Snapshot directory missing for requested (year, methodology)** | API returns 404 for year-specific queries. Latest-year endpoints may fail if latest snapshot is missing. | Cache miss → disk load → file not found → 404 or 503. | Run materializer for the missing year. |
| **HASH_SUMMARY.json missing from snapshot directory** | API refuses to serve that snapshot. Logged as INCOMPLETE SNAPSHOT. | Snapshot treated as non-existent. | Re-materialize (if snapshot dir was from a failed atomic write, delete it first — it shouldn't exist without HASH_SUMMARY). |
| **MANIFEST.json hash mismatch** | API logs `manifest_error` event. If `REQUIRE_DATA=1`, API refuses to start. | Degraded mode or startup abort. | Run `verify_snapshot.py`. Investigate cause. |
| **Registry.json missing** | API fails to start. `methodology.py` raises `FileNotFoundError`. | Hard startup failure. | Restore `registry.json` from git. |
| **Registry.json contains unknown methodology referenced by request** | `get_methodology()` raises `KeyError` → API returns 400. | Clean error response. | Register the methodology version in registry.json, or reject the request. |
| **Out-of-memory from cache** | Process killed by OOM killer. Railway restarts container. | Restart + empty cache (clean start). | Reduce `MAX_CACHED_YEARS`. |
| **Source CSV has NaN/Inf values** | `parse_float()` calls `fatal()` → exporter exits non-zero. | Materialization aborted. No snapshot produced. | Fix source data. Re-run exporter. |
| **Two exporters running simultaneously** | Second exporter's `os.rename()` fails. | First snapshot wins. Second aborts cleanly. Temp dir cleaned up. | No action needed. Idempotent outcome. |

### 8.2 Degraded Mode Definition

The API can operate in degraded mode when:

1. **Some snapshots are missing but the latest is available.** Historical endpoints return 404. Current endpoints work.
2. **MANIFEST hash mismatch but `REQUIRE_DATA=0`.** API serves data but logs warnings. `/ready` reports `integrity_verified: false`.
3. **Cache eviction under memory pressure.** Evicted snapshots are re-loaded from disk on next access. Slightly higher latency, no data loss.

The API **cannot** operate when:

1. **Registry.json is missing.** Hard dependency. No fallback.
2. **Latest snapshot is missing.** All existing endpoints (GET /isi, GET /country/...) depend on it.
3. **REQUIRE_DATA=1 and any integrity check fails.** Designed for production — fail loud.

---

## 9. CLI Verification Specification

### 9.1 Tool: `verify_snapshot.py`

```
Usage:
    python verify_snapshot.py --year YEAR --methodology VERSION [--verbose] [--recompute]
    python verify_snapshot.py --all [--verbose]

Arguments:
    --year          Reference year (e.g., 2024)
    --methodology   Methodology version (e.g., v1.0)
    --all           Verify all existing snapshots
    --verbose       Print per-country hash comparison
    --recompute     Recompute from source CSVs and compare (full pipeline verify)

Exit codes:
    0   All checks passed
    1   Hash mismatch detected
    2   Missing files or incomplete snapshot
    3   Registry error
    4   Source data error (CSV missing, parse failure)
```

### 9.2 Verification Levels

**Level 1 — Structural integrity (default)**
```
1. Verify snapshot directory exists.
2. Verify HASH_SUMMARY.json exists (completeness marker).
3. Verify MANIFEST.json exists and all listed files have matching SHA-256.
4. Verify all 27 country files + 6 axis files + isi.json present.
5. Verify HASH_SUMMARY.json.snapshot_hash matches recomputation from country_hashes.
```

**Level 2 — Content integrity (`--recompute`)**
```
All Level 1 checks, plus:
6. Load source CSVs for the given year from data/processed/.
7. Load methodology from registry.json.
8. Recompute axis scores using pipeline logic.
9. Round to ROUND_PRECISION.
10. Compute per-country hashes using compute_country_hash().
11. Compare against stored HASH_SUMMARY.json country_hashes.
12. Report any mismatches with full field-level diff.
```

### 9.3 Output Format

```
$ python verify_snapshot.py --year 2024 --methodology v1.0 --verbose

═══════════════════════════════════════════════════
  ISI Snapshot Verification — v1.0 / 2024
═══════════════════════════════════════════════════

  Directory:     backend/snapshots/v1.0/2024/
  HASH_SUMMARY:  present ✓
  MANIFEST:      present ✓
  File count:    36/36 ✓
  File hashes:   36/36 match ✓

  Country hashes:
    AT  e5f6a7b8...  ✓
    BE  c9d0e1f2...  ✓
    BG  a1b2c3d4...  ✓
    ...
    SK  f7e8d9c0...  ✓

  Snapshot hash:  a1b2c3d4e5f6a7b8...  ✓

  RESULT: PASS (36 files, 27 countries, 0 mismatches)

═══════════════════════════════════════════════════
```

**On failure:**

```
$ python verify_snapshot.py --year 2022 --methodology v1.0 --recompute

═══════════════════════════════════════════════════
  ISI Snapshot Verification — v1.0 / 2022
═══════════════════════════════════════════════════

  Directory:     backend/snapshots/v1.0/2022/
  HASH_SUMMARY:  present ✓
  MANIFEST:      present ✓
  File count:    36/36 ✓
  File hashes:   36/36 match ✓

  Recomputation from source CSVs:
    AT  stored=e5f6a7b8...  recomputed=e5f6a7b8...  ✓
    BE  stored=c9d0e1f2...  recomputed=c9d0e1f2...  ✓
    BG  stored=a1b2c3d4...  recomputed=XXXXXXXX...  ✗ MISMATCH
        axis_3_technology:  stored=0.12440000  recomputed=0.12510000
        Source: data/processed/tech/tech_dependency_2022_eu27.csv

  RESULT: FAIL (1 mismatch)
  EXIT CODE: 1

═══════════════════════════════════════════════════
```

### 9.4 CI Integration

```yaml
# .github/workflows/snapshot_verify.yml

name: Snapshot Integrity Verification
on:
  push:
    paths:
      - 'data/processed/**'
      - 'backend/snapshots/**'
  schedule:
    - cron: '0 6 * * 1'  # Every Monday at 06:00 UTC

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python verify_snapshot.py --all --recompute
```

---

## 10. Implementation Order

### 10.0 Pre-requisites (Before Any v2 Work)

| Step | Description | Resolves | Risk if skipped |
|------|-------------|----------|-----------------|
| **P-0** | Create `backend/constants.py` with `ROUND_PRECISION = 8`. | D-1 foundation | No single source of truth for precision |
| **P-1** | Fix exporter sort to include alphabetical tie-break: `key=lambda x: (-x["isi_composite"], x["country"])`. Same for axis detail sort. | D-2 | Non-deterministic rank for countries with identical composites |
| **P-2** | Update `scenario.py` to use `round(x, ROUND_PRECISION)` instead of `round(x, 10)`. Import from `constants.py`. | D-1 | Cross-module hash mismatch |
| **P-3** | Run full test suite. All 74 tests must pass. If any fail due to rounding change, update expected values. | — | Regression |

**These four steps are blocking. Nothing in the v2 work may proceed until P-0 through P-3 are complete and merged.**

### 10.1 Foundation Layer (Weeks 1–2)

| Step | Description | Dependency |
|------|-------------|------------|
| **F-1** | Create `backend/methodology.py` with `classify()`, `compute_composite()`, registry loader. | P-0 |
| **F-2** | Create `backend/snapshots/registry.json` with v1.0 methodology. | — |
| **F-3** | Delete `classify_score()` from `export_isi_backend_v01.py`. Import from `methodology.py`. | F-1 |
| **F-4** | Delete `_CLASSIFICATION_THRESHOLDS` and `classify()` from `scenario.py`. Import from `methodology.py`. | F-1 |
| **F-5** | Delete local `compute_composite()` from both modules. Import from `methodology.py`. | F-1 |
| **F-6** | Add `canonical_float()` and `compute_country_hash()` to a new `backend/hashing.py`. | P-0 |
| **F-7** | Create `write_canonical_json()` with `sort_keys=True` + atomic write pattern. | — |
| **F-8** | Create CI grep check for hardcoded threshold literals. | F-3, F-4 |
| **F-9** | Run test suite. All 74 tests must pass. | F-1 through F-5 |

### 10.2 Materialization Layer (Weeks 2–3)

| Step | Description | Dependency |
|------|-------------|------------|
| **M-1** | Extend exporter: `--year` and `--methodology` CLI args. | F-1 |
| **M-2** | Implement atomic snapshot write protocol (§3). | F-7 |
| **M-3** | Implement `HASH_SUMMARY.json` generation. | F-6 |
| **M-4** | Materialize `backend/snapshots/v1.0/2024/` from current data. | M-1, M-2, M-3 |
| **M-5** | Verify byte-level equivalence with `backend/v01/` (modulo key order change). | M-4 |
| **M-6** | Implement `make_readonly()` for snapshot directories (§6.2.4). | M-4 |
| **M-7** | Implement `.tmp_*` cleanup on startup. | M-2 |

### 10.3 Cache Layer (Week 3)

| Step | Description | Dependency |
|------|-------------|------------|
| **C-1** | Implement `SnapshotCache` class (§5.2). | — |
| **C-2** | Replace `_cache` dict and `_get_or_load()` in API with `SnapshotCache`. | C-1, M-4 |
| **C-3** | Add `_get_latest()` shim for existing endpoints. | C-2 |
| **C-4** | Expose cache stats on `/ready`. | C-1 |
| **C-5** | Run test suite. All 74 tests pass. Existing endpoint behavior unchanged. | C-2, C-3 |

### 10.4 Verification Layer (Weeks 3–4)

| Step | Description | Dependency |
|------|-------------|------------|
| **V-1** | Implement `verify_snapshot.py` Level 1 (structural). | M-3 |
| **V-2** | Implement `verify_snapshot.py` Level 2 (`--recompute`). | M-1, F-6 |
| **V-3** | Add CI workflow for weekly recomputation check. | V-2 |
| **V-4** | Test: verify 2024 snapshot → PASS. Tamper a file → verify detects → FAIL. | V-1 |

### 10.5 Historical Backfill (Weeks 4–6)

| Step | Description | Dependency |
|------|-------------|------------|
| **H-1** | Prepare year-specific CSVs for Axes 1,2,3,5,6 (2022, 2023). | External data work |
| **H-2** | Parameterize SIPRI window for Axis 4 historical data. | External data work |
| **H-3** | Materialize `v1.0/2022/` and `v1.0/2023/` snapshots. | M-1, H-1, H-2 |
| **H-4** | Update `registry.json` with `years_available: [2022, 2023, 2024]`. | H-3 |
| **H-5** | Run `verify_snapshot.py --all` → all pass. | V-2, H-3 |

### 10.6 API Extension (Weeks 5–7)

| Step | Description | Dependency |
|------|-------------|------------|
| **A-1** | Implement `/methodology/versions` endpoint. | F-2 |
| **A-2** | Implement `/country/{code}/history` endpoint (behind `ENABLE_TIME_SERIES` flag). | C-2, H-3 |
| **A-3** | Implement `/country/{code}/axis/{slug}/history` endpoint. | C-2, H-3 |
| **A-4** | Implement `/eu/history` endpoint. | C-2, H-3 |
| **A-5** | Extend `ScenarioRequest` with optional `year`/`methodology`. | C-2 |
| **A-6** | Extend scenario handler to load year-specific baselines. | A-5 |
| **A-7** | Add `hash_of_baseline_used` to scenario meta response. | A-6, F-6 |
| **A-8** | New endpoint tests. Existing 74 tests unchanged. | A-1 through A-7 |

### 10.7 Hardening & Launch (Weeks 7–8)

| Step | Description | Dependency |
|------|-------------|------------|
| **L-1** | Add CI freeze check for `backend/snapshots/` modifications. | — |
| **L-2** | Add CI check: no threshold literals outside methodology.py + registry.json. | F-8 |
| **L-3** | Deploy with `ENABLE_TIME_SERIES=0`. Monitor 48h. | All above |
| **L-4** | Enable `ENABLE_TIME_SERIES=1`. Monitor 48h. | L-3 |
| **L-5** | Remove feature flag. Time-series endpoints always available. | L-4 |
| **L-6** | Update `/ready` to include snapshot inventory and verification status. | L-5 |

### 10.8 Critical Path

```
P-0 → P-1 → P-2 → P-3 → F-1 → F-3/F-4/F-5 → F-9
                            ↓
                          F-6 → M-3 → M-4 → V-1 → V-4
                            ↓
                          F-7 → M-2 → M-4
                                       ↓
                                     C-1 → C-2 → C-5
                                       ↓
                                     H-3 → H-5 → A-2 → A-8 → L-3 → L-4 → L-5
```

**Minimum time to production-ready time series: 7 weeks.**  
**Risk-adjusted: 9 weeks** (SIPRI window parameterization).

---

## Appendix A: Constants Consolidated

```python
# backend/constants.py

ROUND_PRECISION: int = 8
NUM_AXES: int = 6
MAX_ADJUSTMENT: float = 0.20
SCENARIO_VERSION: str = "scenario-v1"
EU27_CODES: frozenset[str] = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])
```

## Appendix B: Snapshot Directory File Inventory

```
backend/snapshots/{methodology}/{year}/
├── isi.json                    # Composite scores, all 27 countries, sorted
├── country/
│   ├── AT.json                 # Full country detail
│   ├── BE.json
│   ├── ... (27 files)
│   └── SK.json
├── axis/
│   ├── 1.json                  # Per-axis detail across all countries
│   ├── 2.json
│   ├── ... (6 files)
│   └── 6.json
├── MANIFEST.json               # SHA-256 of all files in this directory
└── HASH_SUMMARY.json           # Computation hashes for all 27 countries + snapshot hash
```

**Total files per snapshot: 36** (1 + 27 + 6 + 1 + 1)  
**Total files for 3 years × 1 methodology: 108** + registry.json

## Appendix C: Scenario Engine v2 Hash Extension

The scenario `MetaBlock` must include a `baseline_hash` field:

```python
class MetaBlock(BaseModel):
    version: str                    # "scenario-v1"
    timestamp: str                  # ISO 8601
    bounds: dict[str, float]        # {"min": -0.2, "max": 0.2}
    year: int                       # Which year's baseline was used
    methodology: str                # Which methodology version
    data_window: str                # "2022–2024"
    baseline_hash: str              # SHA-256 from HASH_SUMMARY for target country
```

This makes scenario output traceable to a specific frozen baseline. If the baseline_hash matches the stored hash, the simulation is reproducible.

## Appendix D: Glossary

| Term | Definition |
|------|-----------|
| **Snapshot** | A complete set of materialized JSON files for one (year, methodology) pair. Immutable once created. |
| **Methodology** | A frozen, versioned definition of how ISI scores are computed (aggregation rule, weights, thresholds). |
| **Computation hash** | SHA-256 of the deterministic input vector (rounded scores + methodology parameters) for one country in one snapshot. |
| **Snapshot hash** | SHA-256 of all 27 computation hashes for one snapshot. |
| **Freeze** | The immutability guarantee: historical snapshots are never modified. |
| **Materialization** | The process of computing scores from source CSVs and writing them as JSON snapshot files. |
| **Atomic write** | Write to temp directory, verify, then `os.rename()` to final path. No partial writes possible. |
| **Canonical form** | JSON with `sort_keys=True`, floats formatted via `canonical_float()`. Deterministic byte representation. |

---

*End of document.*
