#!/usr/bin/env python3
"""
Merge local XMLTV files and remote XMLTV URLs into one EPG file.

Inputs:
  data/epg/*.xml, *.xml.gz
  data/sources.txt

Output:
  docs/epg.xml
  reports/epg-report.txt
"""
from __future__ import annotations

import gzip
import io
import os
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DIR = ROOT / "data" / "epg"
SOURCES = ROOT / "data" / "sources.txt"
OUT_XML = ROOT / "docs" / "epg.xml"
OUT_REPORT = ROOT / "reports" / "epg-report.txt"

USER_AGENT = "EPG-Merger/1.0 (+https://github.com/)"
TIMEOUT = 45
MAX_BYTES = 80 * 1024 * 1024  # safety limit per source

def clean_text(value: str | None) -> str:
    return " ".join((value or "").split())

def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def parse_xml(data: bytes) -> ET.Element:
    # XMLTV files normally use UTF-8; ElementTree handles the XML declaration.
    return ET.fromstring(data)

def read_sources() -> list[str]:
    if not SOURCES.exists():
        return []
    result = []
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            result.append(line)
    return result

def fetch_url(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xml,text/xml,application/gzip,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        chunks = []
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError(f"source exceeds {MAX_BYTES // (1024*1024)} MB")
            chunks.append(chunk)
        data = b"".join(chunks)

    # Handle gzip by magic bytes, regardless of URL extension.
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data

def iter_xmltv(root: ET.Element) -> Iterable[ET.Element]:
    for child in root:
        if local_name(child.tag) in ("channel", "programme"):
            yield child

def channel_key(el: ET.Element) -> str:
    return (el.get("id") or "").strip()

def programme_key(el: ET.Element) -> tuple:
    channel = (el.get("channel") or "").strip()
    start = (el.get("start") or "").strip()
    stop = (el.get("stop") or "").strip()
    title = ""
    desc = ""
    for child in el:
        name = local_name(child.tag)
        if name == "title" and not title:
            title = clean_text("".join(child.itertext()))
        elif name == "desc" and not desc:
            desc = clean_text("".join(child.itertext()))
    return (channel, start, stop, title, desc)

def merge_element(dst: ET.Element, src: ET.Element) -> None:
    # Keep attributes from the first source; add missing attributes from later sources.
    for key, value in src.attrib.items():
        if key not in dst.attrib:
            dst.set(key, value)

def main() -> int:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    OUT_XML.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)

    sources = []
    for path in sorted(LOCAL_DIR.glob("*")):
        if path.is_file() and path.suffix.lower() in {".xml", ".gz"}:
            sources.append(("LOCAL", str(path.relative_to(ROOT)), path))

    remote_urls = read_sources()

    merged = ET.Element("tv")
    channel_map: dict[str, ET.Element] = {}
    programme_map: dict[tuple, ET.Element] = {}

    report = [
        "EPG MERGE REPORT",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        "",
    ]
    total_channels_before = 0
    total_programmes_before = 0
    success = 0
    failed = 0

    def consume(label: str, data: bytes) -> None:
        nonlocal total_channels_before, total_programmes_before
        root = parse_xml(data)
        if local_name(root.tag) != "tv":
            raise ValueError(f"root element is <{local_name(root.tag)}> instead of <tv>")

        channels = [e for e in iter_xmltv(root) if local_name(e.tag) == "channel"]
        programmes = [e for e in iter_xmltv(root) if local_name(e.tag) == "programme"]
        total_channels_before += len(channels)
        total_programmes_before += len(programmes)

        for ch in channels:
            cid = channel_key(ch)
            if not cid:
                continue
            if cid in channel_map:
                merge_element(channel_map[cid], ch)
            else:
                channel_map[cid] = ET.fromstring(ET.tostring(ch, encoding="utf-8"))

        for prog in programmes:
            key = programme_key(prog)
            if not key[0]:
                # Programme without channel id is not useful in XMLTV.
                continue
            if key not in programme_map:
                programme_map[key] = ET.fromstring(ET.tostring(prog, encoding="utf-8"))

    for kind, label, path in sources:
        try:
            data = path.read_bytes()
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            consume(label, data)
            success += 1
            report.append(f"[OK]   {kind:5} {label}")
        except Exception as exc:
            failed += 1
            report.append(f"[FAIL] {kind:5} {label} :: {type(exc).__name__}: {exc}")

    for url in remote_urls:
        try:
            data = fetch_url(url)
            consume("remote", data)
            success += 1
            report.append(f"[OK]   URL   {url}")
        except Exception as exc:
            failed += 1
            report.append(f"[FAIL] URL   {url} :: {type(exc).__name__}: {exc}")

    # Stable ordering makes generated commits less noisy.
    for cid in sorted(channel_map, key=str.casefold):
        merged.append(channel_map[cid])

    def prog_sort_key(item):
        el = item[1]
        return (
            (el.get("channel") or "").casefold(),
            (el.get("start") or ""),
            (el.get("stop") or ""),
            programme_key(el)[3].casefold(),
        )

    for _, prog in sorted(programme_map.items(), key=prog_sort_key):
        merged.append(prog)

    tree = ET.ElementTree(merged)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(OUT_XML, encoding="utf-8", xml_declaration=True)

    report += [
        "",
        f"Sources successful : {success}",
        f"Sources failed    : {failed}",
        f"Input channels    : {total_channels_before}",
        f"Output channels   : {len(channel_map)}",
        f"Input programmes  : {total_programmes_before}",
        f"Output programmes : {len(programme_map)}",
        f"Output file       : {OUT_XML.relative_to(ROOT)}",
    ]
    OUT_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("\n".join(report))
    # Do not fail the workflow just because one remote EPG failed.
    # Fail only if no usable source produced any EPG data.
    if not channel_map and not programme_map:
        print("ERROR: no usable EPG data was produced.", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
