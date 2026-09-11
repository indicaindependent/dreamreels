"""No Qt, no network: parser, scoring, decode-proof negative control, tool discovery."""
import os, pathlib, sys
from dreamreels.dreamy import agent
from dreamreels.sources import archive_org as ia
from dreamreels.core import tools

def test_parse_person_decade_question():
    q = agent.parse("was Orson Welles in any movies from the 1940s?")
    assert q["intent"] == "question" and q["person"] == "Orson Welles" and q["decade"] == 1940 and not q["youtube"]

def test_parse_find_genre_decade():
    q = agent.parse("find me 1940s film noir")
    assert q["intent"] == "find" and q["genre"] == "Film-Noir" and q["decade"] == 1940 and q["person"] is None

def test_parse_youtube_latest():
    q = agent.parse("find me the latest video showing Trump talking on Air Force One")
    assert q["youtube"] and q["latest"] and "air force one" in q["free"]

def test_emoji_stripped_from_labels():
    b = agent._btn("check", "\U0001F1FA\U0001F1F8 President speaks \u2705", uid="x")
    assert b["label"] == "President speaks"

def test_candidates_prefer_mp4_and_skip_parts():
    meta = {"files": [{"name": "a.ogv", "size": 900_000_000}, {"name": "a.mp4", "size": 700_000_000}, {"name": "a_part_1_of_2.mp4", "size": 300_000_000}, {"name": "a.txt", "size": 10}]}
    c = ia.candidates(meta, "a")
    assert [x["name"] for x in c][0] == "a.mp4" and any(x["part"] for x in c) and all(x["name"] != "a.txt" for x in c)

def test_blocklist():
    assert ia.blocked("Hardcore XXX something") and not ia.blocked("The Stranger (1946)")

def test_verify_decode_negative_control(tmp_path):
    bogus = tmp_path / "not_a_video.mp4"; bogus.write_bytes(b"<html>nope</html>")
    ok, note, dur = ia.verify_decode(str(bogus), frames=4, timeout=30)
    assert ok is False and dur == 0.0 and note

def test_ytdlp_path_is_executable_or_none():
    p = tools.ytdlp_path()
    assert p is None or (os.path.isfile(p) and os.access(p, os.X_OK))
