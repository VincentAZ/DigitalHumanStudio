#!/usr/bin/env python3
"""Resume large locked NVIDIA wheels using bounded HTTP ranges and final SHA-256."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import tomllib
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(package, output, workers, pypi_mirror, selected_wheel=None):
    wheels = package["wheels"]
    if selected_wheel:
        wheels = [w for w in wheels if Path(urllib.parse.urlsplit(w["url"]).path).name == selected_wheel]
    if len(wheels) != 1:
        raise RuntimeError("Select a target-specific lock with one wheel per requested package")
    wheel = wheels[0]
    url, expected_hash = wheel["url"], wheel["hash"].removeprefix("sha256:")
    if not url.startswith(("https://pypi.nvidia.com/", "https://files.pythonhosted.org/")):
        raise RuntimeError("This transport workaround requires a locked NVIDIA or PyPI artifact")
    filename = Path(urllib.parse.urlsplit(url).path).name
    locked_url = url
    if pypi_mirror:
        metadata_url = f"https://pypi.org/pypi/{package['name']}/{package['version']}/json"
        with urllib.request.urlopen(metadata_url, timeout=30) as response:
            release = json.load(response)
        mirrors = [f for f in release["urls"] if f["filename"] == filename
                   and f["digests"]["sha256"] == expected_hash]
        if len(mirrors) != 1 or not mirrors[0]["url"].startswith("https://files.pythonhosted.org/"):
            raise RuntimeError("No exact same-hash PyPI mirror; refusing a substitute artifact")
        url = mirrors[0]["url"]
    target = output / filename
    if target.exists():
        with target.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() == expected_hash:
                print(f"Verified existing {filename}", flush=True)
                return
        raise RuntimeError(f"Existing wheel checksum mismatch: {target}")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=30) as response:
        content_range = response.headers.get("Content-Range", "")
        if response.status != 206 or not content_range.startswith("bytes 0-0/") or len(response.read()) != 1:
            raise RuntimeError("Server did not honor the range probe")
        size = int(content_range.split("/")[1])
    chunk_size = 4 * 1024 * 1024
    parts = output / (filename + ".parts")
    parts.mkdir(exist_ok=True)
    manifest = {"url": url, "locked_url": locked_url, "sha256": expected_hash, "size": size, "chunk_size": chunk_size}
    manifest_path = parts / "manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        previous.setdefault("locked_url", previous["url"])
        if previous != manifest:
            raise RuntimeError("Partial download metadata changed")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    def chunk(index):
        start = index * chunk_size
        end = min(size, start + chunk_size) - 1
        part = parts / f"{index:06d}.part"
        length = end - start + 1
        if part.exists() and part.stat().st_size == length:
            return length
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}":
                        raise RuntimeError("Unexpected range response")
                    data = response.read(length + 1)
                    if len(data) != length:
                        raise RuntimeError("Incomplete range response")
                temporary = part.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(part)
                return length
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    count = (size + chunk_size - 1) // chunk_size
    done = 0
    started = last_report = time.monotonic()
    print(f"Fetching {filename}: {size / 1e9:.2f} GB in {count} resumable ranges", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(chunk, i) for i in range(count)]):
            done += future.result()
            now = time.monotonic()
            if now - last_report > 10 or done == size:
                print(f"{package['name']}: {done / size:.1%} ({done / 1e9:.2f}/{size / 1e9:.2f} GB)", flush=True)
                last_report = now
    digest = hashlib.sha256()
    temporary = target.with_suffix(".assembling")
    with temporary.open("wb") as dest:
        for i in range(count):
            data = (parts / f"{i:06d}.part").read_bytes()
            digest.update(data)
            dest.write(data)
    if digest.hexdigest() != expected_hash:
        raise RuntimeError("Assembled artifact failed the lock's SHA-256; retaining all diagnostics")
    temporary.replace(target)
    manifest.update(status="verified", elapsed_seconds=time.monotonic() - started)
    target.with_suffix(".provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"SHA-256 verified: {filename}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--package", action="append", required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--pypi-mirror", action="store_true", help="Require an identical filename and SHA-256 on PyPI")
    parser.add_argument("--wheel", action="append", default=[], metavar="PACKAGE=FILENAME",
                        help="Explicitly choose a wheel already present in the lock for an ambiguous package")
    args = parser.parse_args()
    if not 1 <= args.workers <= 32:
        parser.error("workers must be between 1 and 32")
    lock = tomllib.loads(args.lock.read_text())
    selected_wheels = dict(item.split("=", 1) for item in args.wheel)
    output = ROOT / ".downloads/wheels"
    output.mkdir(parents=True, exist_ok=True)
    for name in args.package:
        matches = [p for p in lock["package"] if p["name"] == name]
        if len(matches) != 1:
            raise RuntimeError(f"Ambiguous or missing locked package: {name}")
        fetch(matches[0], output, args.workers, args.pypi_mirror, selected_wheels.get(name))


if __name__ == "__main__":
    main()
