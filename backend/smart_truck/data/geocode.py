"""Nominatim geocoding with on-disk cache (FR-002).

Run as a one-off batch::

    python -m smart_truck.data.geocode --route DR0027    # only route's customers
    python -m smart_truck.data.geocode --all             # full catalogue (~20 min)
    python -m smart_truck.data.geocode --limit 5         # smoke test

Reads ``customers.parquet``, geocodes each row using Nominatim
(public, no key, 1 req/sec), and writes ``lat``/``lon`` columns back
to ``customers.parquet``.

Results are cached in ``backend/data/geo_cache.json`` keyed by the
full address string. The cache is committed to the repo so teammates
don't re-hammer Nominatim. Misses are stored as ``null`` so we don't
retry — to refresh a bad result, delete the entry from the cache.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "backend" / "data"
PROCESSED = DATA_DIR / "processed"
CACHE_FILE = DATA_DIR / "geo_cache.json"

# We try Photon (Komoot's public OSM-based geocoder) first because it has
# generous rate limits and is reliable for European addresses, falling back
# to Nominatim if Photon is unavailable. Both are free and no key required.
PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "smart-truck/0.1 (interhack-bcn-2026-team@example.com)",
)

# Pause between requests. Photon is more permissive than Nominatim's
# 1 req/sec; we still pace at ~1 req/sec so the fallback path stays
# within Nominatim's policy if it kicks in.
REQUEST_INTERVAL_S = 1.05


def _load_cache() -> dict[str, list[float] | None]:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict[str, list[float] | None]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_query(street: object, postcode: object, city: object) -> str:
    """Compose the address string we send to Nominatim."""
    parts = []
    for v in (street, postcode, city):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if s:
            parts.append(s)
    return ", ".join(parts) + ", Spain"


class GeocoderTransientError(RuntimeError):
    """Raised on rate limits or other transient HTTP / network errors.

    Callers should NOT cache these as misses — the address might still
    resolve later. Re-raise or back off and retry.
    """


def _check_response(r: requests.Response, provider: str) -> None:
    """Raise :class:`GeocoderTransientError` on retry-able statuses."""
    if r.status_code in (403, 429):
        raise GeocoderTransientError(
            f"{provider} {r.status_code} (rate-limited / blocked); back off and retry"
        )
    if r.status_code >= 500:
        raise GeocoderTransientError(f"{provider} 5xx: {r.status_code}")
    if not r.ok:
        raise GeocoderTransientError(
            f"{provider} {r.status_code}: {r.text[:200]!r}"
        )


def _query_photon(address: str) -> tuple[float, float] | None:
    """Photon (Komoot). Returns (lat, lon), None if no record, or raises
    :class:`GeocoderTransientError` on rate limits / network errors."""
    try:
        r = requests.get(
            PHOTON_URL,
            params={"q": address, "limit": 1, "lang": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
    except requests.RequestException as e:
        raise GeocoderTransientError(f"photon network error: {e}") from e
    _check_response(r, "Photon")

    body = r.json()
    features = body.get("features", [])
    if not features:
        return None
    coords = features[0].get("geometry", {}).get("coordinates")
    if not coords or len(coords) < 2:
        return None
    # Photon returns [lon, lat]; we use (lat, lon).
    return float(coords[1]), float(coords[0])


def _query_nominatim(address: str) -> tuple[float, float] | None:
    """Nominatim (OpenStreetMap)."""
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "es",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
    except requests.RequestException as e:
        raise GeocoderTransientError(f"nominatim network error: {e}") from e
    _check_response(r, "Nominatim")

    body = r.json()
    if not body:
        return None
    return float(body[0]["lat"]), float(body[0]["lon"])


# Try providers in order. A confirmed miss (provider returned no record) on
# the primary falls through to the secondary — the providers index different
# OSM views and one may know an address the other doesn't.
PROVIDERS: list[tuple[str, callable]] = [
    ("photon", _query_photon),
    ("nominatim", _query_nominatim),
]


def _query_address(address: str) -> tuple[float, float] | None:
    """Try every provider until one returns a hit. Raises
    :class:`GeocoderTransientError` only if **every** provider erred
    transiently (i.e. we never got an authoritative answer).
    """
    last_error: GeocoderTransientError | None = None
    confirmed_miss = False
    for name, fn in PROVIDERS:
        try:
            result = fn(address)
        except GeocoderTransientError as e:
            last_error = e
            continue
        if result is not None:
            return result
        confirmed_miss = True
    if confirmed_miss:
        return None
    assert last_error is not None
    raise last_error


def geocode_one(
    street: object,
    postcode: object,
    city: object,
    cache: dict[str, list[float] | None],
) -> tuple[float, float] | None:
    """Cache-aware single geocode. Returns ``None`` if Nominatim has no record.

    Transient errors (rate limits, network) propagate as
    :class:`GeocoderTransientError` so the caller can decide whether to
    back off and retry. The cache only records confirmed hits and
    confirmed misses.
    """
    address = build_query(street, postcode, city)
    if address in cache:
        v = cache[address]
        return tuple(v) if v else None

    result = _query_address(address)
    cache[address] = list(result) if result else None
    return result


def geocode_dataframe(
    df: pd.DataFrame,
    cache: dict[str, list[float] | None] | None = None,
    pause_s: float = REQUEST_INTERVAL_S,
    progress_every: int = 25,
    max_transient_retries: int = 3,
    backoff_s: float = 60.0,
) -> pd.DataFrame:
    """Geocode a customer dataframe. Returns a new DataFrame with lat/lon.

    Behaviour:

    - Cache hits return immediately.
    - Cache misses query Nominatim, throttled to ``pause_s`` between
      requests.
    - Confirmed misses (Nominatim returned an empty result) are cached
      as ``None``.
    - Transient errors (HTTP 429/403/5xx, network failures) trigger a
      backoff (``backoff_s`` seconds) and up to ``max_transient_retries``
      retries on the same address. After exhausting retries, the address
      is left out of the cache so future runs will retry it.
    - The cache is persisted every ``progress_every`` new lookups and
      again at the end.
    """
    if cache is None:
        cache = _load_cache()

    lats: list[float | None] = []
    lons: list[float | None] = []
    n_new = 0
    n_transient_skip = 0

    for _, row in df.iterrows():
        address = build_query(row["street"], row["postcode"], row["city"])
        if address in cache:
            v = cache[address]
            result = tuple(v) if v else None
        else:
            result = None
            attempt = 0
            while True:
                try:
                    result = _query_address(address)
                    cache[address] = list(result) if result else None
                    n_new += 1
                    break
                except GeocoderTransientError as e:
                    attempt += 1
                    if attempt > max_transient_retries:
                        print(
                            f"  !! giving up on {address!r} after "
                            f"{max_transient_retries} transient errors ({e}); "
                            "leaving uncached for next run"
                        )
                        n_transient_skip += 1
                        break
                    print(
                        f"  ~ transient error ({e}); backing off {backoff_s:.0f}s "
                        f"and retrying ({attempt}/{max_transient_retries})"
                    )
                    time.sleep(backoff_s)
            time.sleep(pause_s)
            if n_new and n_new % progress_every == 0:
                _save_cache(cache)
                print(f"  ... {n_new} new geocodes, {len(cache)} total cached")

        if result:
            lats.append(result[0])
            lons.append(result[1])
        else:
            lats.append(None)
            lons.append(None)

    if n_new:
        _save_cache(cache)

    if n_transient_skip:
        print(
            f"  WARN: {n_transient_skip} addresses skipped due to transient errors; "
            "rerun later to fill them in."
        )

    df = df.copy()
    df["lat"] = lats
    df["lon"] = lons
    return df


def _filter_to_route(customers: pd.DataFrame, route: str) -> pd.DataFrame:
    """Return only customers active on the given route.

    The index of the returned slice is preserved (no ``reset_index``) so the
    caller can align lat/lon back into the master ``customers`` frame even
    when ``customer_id`` is non-unique (some clients appear multiple times
    in ``Direcciones`` with distinct delivery addresses).
    """
    deliveries = pd.read_parquet(PROCESSED / "deliveries.parquet")
    cust_ids = set(deliveries.loc[deliveries["route"] == route, "customer_id"].unique())
    return customers[customers["customer_id"].isin(cust_ids)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode customer addresses (Nominatim).")
    parser.add_argument(
        "--route",
        help="Only geocode customers active on this route code (e.g. DR0027).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Geocode all customers in the catalogue (default if --route absent).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N customers (smoke test).",
    )
    args = parser.parse_args()

    customers_path = PROCESSED / "customers.parquet"
    customers = pd.read_parquet(customers_path)
    print(f"Loaded {len(customers):,} customers from {customers_path.name}")

    target = customers
    if args.route:
        target = _filter_to_route(customers, args.route)
        print(f"  filtered to route {args.route}: {len(target)} customers")

    if args.limit:
        target = target.head(args.limit)
        print(f"  limited to first {len(target)} customers")

    cache = _load_cache()
    print(f"Cache: {len(cache)} entries at {CACHE_FILE}")

    geocoded = geocode_dataframe(target, cache=cache)

    # Persist lat/lon back into the master customers frame. We align on the
    # original DataFrame index (preserved through ``_filter_to_route`` and
    # ``geocode_dataframe``) — this is robust against non-unique
    # ``customer_id`` values, which do occur in ``Direcciones``.
    if "lat" not in customers.columns:
        customers["lat"] = pd.NA
        customers["lon"] = pd.NA
    customers.loc[geocoded.index, "lat"] = geocoded["lat"].values
    customers.loc[geocoded.index, "lon"] = geocoded["lon"].values
    customers.to_parquet(customers_path, index=False)

    n_with_coords = customers["lat"].notna().sum()
    print(
        f"Done. Customers with coords: {n_with_coords:,} / {len(customers):,} "
        f"(cache size: {len(cache)})"
    )


if __name__ == "__main__":
    main()
