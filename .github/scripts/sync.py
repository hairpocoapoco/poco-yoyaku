"""poco a poco の空き状況ページを読み取り、data.json を更新する。

公式ページ（https://hair-pocoapoco.com/res-time/）は、日付ごとに
  11/13（金）15：00～（KAZU)
  15：30カットのみ（湯本）
のような行が並ぶ形式。これを ["M/D", KAZU, 湯本] の配列に変換する。
  ""   = 空きなし
  null = その日の記載なし
  "*"  = カットのみ
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://hair-pocoapoco.com/res-time/"
OUT = "data.json"
JST = timezone(timedelta(hours=9))


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (poco-yoyaku sync)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def to_text(src: str) -> str:
    src = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", src)
    src = re.sub(r"(?i)<br\s*/?>", "\n", src)
    src = re.sub(r"(?i)</(p|div|h[1-6]|li|tr|td|th|section|article)>", "\n", src)
    src = re.sub(r"<[^>]+>", " ", src)
    src = html.unescape(src)
    trans = str.maketrans({"：": ":", "～": "~", "〜": "~", "（": "(", "）": ")", "　": " ",
                           **{chr(0xFF10 + i): str(i) for i in range(10)}, "／": "/"})
    return src.translate(trans)


DATE_RE = re.compile(r"(?<![\d/'’])(\d{1,2})/(\d{1,2})\s*\(\s*[月火水木金土日]\s*\)")
LABEL_RE = re.compile(r"\(\s*(KAZU|湯本)\s*\)")
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*(~)?\s*(\d{1,2}:\d{2})?")


def convert(raw: str) -> str:
    s = re.sub(r"\s+", "", raw).replace("空き出ました", "").replace("空きでました", "")
    if not s or "空きなし" in s or "お休み" in s or "休み" in s:
        return ""
    out = []
    for piece in re.split(r"[・,、/]", s):
        if not piece:
            continue
        cut = "カットのみ" in piece
        m = TIME_RE.search(piece)
        if not m:
            continue
        a, tilde, b = m.groups()
        label = f"{a}~{b}" if b else (f"{a}~" if tilde else a)
        out.append(label + ("*" if cut else ""))
    return "・".join(out)


def parse(text: str):
    dates = list(DATE_RE.finditer(text))
    rows = []
    seen = set()
    for i, m in enumerate(dates):
        md = f"{int(m.group(1))}/{int(m.group(2))}"
        if md in seen:
            continue
        end = dates[i + 1].start() if i + 1 < len(dates) else len(text)
        block = text[m.end():end]
        vals = {"KAZU": None, "湯本": None}
        pos = 0
        for lm in LABEL_RE.finditer(block):
            who = lm.group(1)
            if vals[who] is None:
                vals[who] = convert(block[pos:lm.start()])
            pos = lm.end()
        if vals["KAZU"] is None and vals["湯本"] is None:
            continue
        seen.add(md)
        k, y = vals["KAZU"], vals["湯本"]
        if not k and not y:
            continue  # どちらも空きなし
        rows.append([md, k, y])
    return rows


def main():
    text = to_text(fetch(URL))
    rows = parse(text)
    date_count = len(DATE_RE.findall(text))
    print(f"dates on page: {date_count}, rows with openings: {len(rows)}")
    if date_count < 5:
        print("ページの形式が変わった可能性があります。更新しません。", file=sys.stderr)
        sys.exit(1)
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f).get("data")
    except Exception:
        old = None
    now = datetime.now(JST).strftime("%Y-%m-%dT%H:%M:00+09:00")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": now, "source": URL, "data": rows}, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print("changed" if old != rows else "unchanged (timestamp only)")


if __name__ == "__main__":
    main()
