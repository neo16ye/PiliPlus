#!/usr/bin/env python3

import os
import re
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path


PACKAGE = os.environ.get("TEST_PACKAGE", "com.example.piliplus.debug")
APK_PATH = os.environ.get(
    "TEST_APK", "build/app/outputs/flutter-apk/app-debug.apk"
)
VIDEO_URI = "bilibili://video/170001"
OUTPUT = Path(os.environ.get("TEST_OUTPUT", "test-output"))
OUTPUT.mkdir(parents=True, exist_ok=True)


def run(*args: str, capture: bool = False, check: bool = True):
    print("+", " ".join(args), flush=True)
    return subprocess.run(
        args,
        check=check,
        text=capture,
        capture_output=capture,
    )


def adb(*args: str, capture: bool = False, check: bool = True):
    return run("adb", *args, capture=capture, check=check)


def screenshot(name: str) -> Path:
    path = OUTPUT / f"{name}.png"
    started = time.monotonic()
    result = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        check=True,
        capture_output=True,
    )
    path.write_bytes(result.stdout)
    print(f"{name}: screenshot={time.monotonic() - started:.2f}s", flush=True)
    return path


def dump_ui(name: str) -> ET.Element:
    remote = f"/sdcard/{name}.xml"
    local = OUTPUT / f"{name}.xml"
    adb("shell", "uiautomator", "dump", remote)
    adb("pull", remote, str(local))
    return ET.parse(local).getroot()


def label(node: ET.Element) -> str:
    return " ".join(
        value for value in (node.get("content-desc"), node.get("text")) if value
    )


def bounds(node: ET.Element) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
    if not match:
        raise AssertionError(f"Invalid bounds for {label(node)!r}: {node.get('bounds')}")
    return tuple(map(int, match.groups()))


def find_node(root: ET.Element, needle: str, exact: bool = False):
    matches = []
    for node in root.iter("node"):
        value = label(node)
        if (value == needle) if exact else (needle in value):
            matches.append(node)
    if not matches:
        return None
    return max(matches, key=lambda node: (bounds(node)[2] - bounds(node)[0]) * (bounds(node)[3] - bounds(node)[1]))


def wait_for_node(needle: str, name: str, timeout: float = 15.0) -> ET.Element:
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        root = dump_ui(f"{name}-wait-{attempt}")
        node = find_node(root, needle)
        if node is not None:
            return node
        attempt += 1
        time.sleep(0.75)
    raise AssertionError(f"Timed out waiting for UI node containing {needle!r}")


def tap_node(node: ET.Element, x_fraction: float = 0.5, y_fraction: float = 0.5):
    left, top, right, bottom = bounds(node)
    x = round(left + (right - left) * x_fraction)
    y = round(top + (bottom - top) * y_fraction)
    adb("shell", "input", "tap", str(x), str(y))


def screen_size() -> tuple[int, int]:
    output = adb("shell", "wm", "size", capture=True).stdout
    match = re.search(r"Physical size: (\d+)x(\d+)", output)
    if not match:
        raise AssertionError(f"Cannot determine screen size: {output}")
    return int(match.group(1)), int(match.group(2))


def start_initial_playback(tag: str):
    width, height = screen_size()
    root = dump_ui(f"{tag}-controls")
    play = find_node(root, "播放", exact=True)
    if play is None:
        adb("shell", "input", "tap", str(width // 2), str(round(height * 0.18)))
        time.sleep(0.6)
        root = dump_ui(f"{tag}-controls-revealed")
        play = find_node(root, "播放", exact=True)
    if play is not None:
        tap_node(play)
        time.sleep(3)


def decode_png(path: Path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"Not a PNG: {path}")
    pos = 8
    payload = bytearray()
    width = height = color_type = bit_depth = None
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
                raise AssertionError(f"Unsupported screenshot PNG format: {bit_depth=}, {color_type=}, {interlace=}")
        elif chunk_type == b"IDAT":
            payload.extend(chunk)
        elif chunk_type == b"IEND":
            break
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(payload)
    rows = []
    previous = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        source = raw[offset : offset + stride]
        offset += stride
        row = bytearray(stride)
        for index, value in enumerate(source):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                decoded = value
            elif filter_type == 1:
                decoded = value + left
            elif filter_type == 2:
                decoded = value + up
            elif filter_type == 3:
                decoded = value + ((left + up) // 2)
            elif filter_type == 4:
                prediction = left + up - upper_left
                distances = (abs(prediction - left), abs(prediction - up), abs(prediction - upper_left))
                predictor = (left, up, upper_left)[distances.index(min(distances))]
                decoded = value + predictor
            else:
                raise AssertionError(f"Unknown PNG filter {filter_type}")
            row[index] = decoded & 0xFF
        rows.append(row)
        previous = row
    return width, height, channels, rows


def assert_motion(before: Path, after: Path, region: tuple[int, int, int, int], tag: str):
    width1, height1, channels1, rows1 = decode_png(before)
    width2, height2, channels2, rows2 = decode_png(after)
    if (width1, height1, channels1) != (width2, height2, channels2):
        raise AssertionError("Screenshot dimensions changed")
    left, top, right, bottom = region
    left, top = max(0, left), max(0, top)
    right, bottom = min(width1, right), min(height1, bottom)
    changed = non_black = total = 0
    for y in range(top, bottom, 3):
        row1, row2 = rows1[y], rows2[y]
        for x in range(left, right, 3):
            index = x * channels1
            rgb1 = row1[index : index + 3]
            rgb2 = row2[index : index + 3]
            total += 1
            if max(rgb1) > 24 or max(rgb2) > 24:
                non_black += 1
            if sum(abs(a - b) for a, b in zip(rgb1, rgb2)) > 30:
                changed += 1
    changed_ratio = changed / total
    non_black_ratio = non_black / total
    print(f"{tag}: changed={changed_ratio:.3f}, non_black={non_black_ratio:.3f}")
    if non_black_ratio < 0.08:
        raise AssertionError(f"{tag} is blank/black")
    if changed_ratio < 0.03:
        raise AssertionError(f"{tag} video surface is not advancing")


def capture_motion(tag: str, region: tuple[int, int, int, int]):
    before = screenshot(f"{tag}-before")
    time.sleep(2)
    after = screenshot(f"{tag}-after")
    assert_motion(before, after, region, tag)


def main():
    # The hosted emulator renders in software. Its native 1080x2400 screenshots
    # can each take around 14 seconds, making this three-cycle UI test consume
    # more than three minutes of the live stream before it finishes. Use a
    # phone-shaped half-resolution display so each frame capture is fast while
    # preserving the same Flutter navigation and Android texture behavior.
    adb("shell", "wm", "size", "540x1200")
    adb("shell", "wm", "density", "280")
    width, height = screen_size()
    adb("install", "-r", APK_PATH)
    adb("logcat", "-c")
    adb(
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-c",
        "android.intent.category.BROWSABLE",
        "-d",
        VIDEO_URI,
        PACKAGE,
    )
    wait_for_node("简介", "video-initial", timeout=45)
    start_initial_playback("video-initial")
    capture_motion(
        "video-initial",
        (0, round(height * 0.05), width, round(height * 0.31)),
    )

    for cycle in range(1, 4):
        adb("shell", "input", "keyevent", "4")
        mini = wait_for_node("应用内小窗：", f"cycle-{cycle}-mini", timeout=12)
        mini_bounds = bounds(mini)
        capture_motion(f"cycle-{cycle}-mini", mini_bounds)

        # Tap away from the center pause button and the top-right close button.
        tap_node(mini, x_fraction=0.22, y_fraction=0.62)
        wait_for_node("简介", f"cycle-{cycle}-restored", timeout=20)
        capture_motion(
            f"cycle-{cycle}-restored",
            (0, round(height * 0.05), width, round(height * 0.31)),
        )

    logs = adb("logcat", "-d", capture=True).stdout
    if "No Overlay widget found" in logs:
        raise AssertionError(
            "The app mini-player built a Tooltip without an Overlay ancestor"
        )
    if "setState() or markNeedsBuild() called during build" in logs:
        raise AssertionError("The app mini-player mutated reactive state during build")
    print("PASS: three consecutive app mini-player restore cycles", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        with (OUTPUT / "logcat.txt").open("w") as log:
            subprocess.run(["adb", "logcat", "-d", "-v", "time"], stdout=log, text=True)
