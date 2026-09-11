import os, tempfile, tomllib
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(); os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(); os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp()
from dreamreels.core import config, db, ids
from dreamreels.badge.iim import badge_svg

def test_config_roundtrip():
    cfg = config.load(); cfg["publicdomain"]["decades"] = [1940, 1950]; cfg["tmdb"]["read_token"] = 'a"b'
    config.save(cfg); again = config.load()
    assert again["publicdomain"]["decades"] == [1940, 1950] and again["tmdb"]["read_token"] == 'a"b'
    assert again["publicdomain"]["strict_pd"] is True

def test_db_migrates_and_is_idempotent():
    assert db.migrate() == 1 and db.migrate() == 1
    c = db.connect(); names = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    assert {"items", "shows", "people", "state", "jobs", "yt_channels", "provenance"} <= names

def test_badge_is_deterministic_and_unique():
    a, b = badge_svg(seed=1), badge_svg(seed=1); c = badge_svg(seed=2)
    assert a == b and a != c and "Created with Creative Clarity" in a and a.count("<svg") == 1
    import re; assert not re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", a)

def test_install_id_stable():
    assert ids.install_id() == ids.install_id() and len(ids.install_id()) == 32
