"""Seed a demo library (no network) so the UI can be rendered and QA'd before real sources exist.
Posters are generated locally with Pillow. Run: python tools/seed_demo.py [--wipe]"""
import sys, time, random, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dreamreels.core import db
from dreamreels.core.paths import POSTER_CACHE, ensure_dirs
from PIL import Image, ImageDraw
DEMO = [
 ("pd","movie","Citizen Kane",1941,"Orson Welles","Drama, Mystery","A publishing tycoon's dying word sends a reporter through the ruins of a colossal life."),
 ("pd","movie","The Stranger",1946,"Orson Welles","Thriller, Film-Noir","A war-crimes investigator tracks a Nazi fugitive to a quiet Connecticut town."),
 ("pd","movie","His Girl Friday",1940,"Howard Hawks","Comedy, Romance","A newspaper editor schemes to keep his ace reporter and ex-wife from remarrying."),
 ("pd","movie","Night of the Living Dead",1968,"George A. Romero","Horror","Strangers barricade a farmhouse as the dead rise across rural Pennsylvania."),
 ("pd","movie","Nosferatu",1922,"F. W. Murnau","Horror, Fantasy","Count Orlok brings plague and shadow to a German port town."),
 ("pd","movie","Metropolis",1927,"Fritz Lang","Sci-Fi, Drama","In a towering future city, a privileged son discovers the workers who keep it alive."),
 ("pd","movie","Detour",1945,"Edgar G. Ulmer","Film-Noir, Crime","A hitchhiking pianist's ride east curdles into a nightmare of chance and guilt."),
 ("pd","movie","The Hitch-Hiker",1953,"Ida Lupino","Film-Noir, Thriller","Two fishing buddies pick up the wrong man on a desert road."),
 ("chan83","episode","The Zanti Misfits",1963,"Leonard Horn","Sci-Fi","The Outer Limits S01E14: alien criminals are exiled to a ghost town in the California desert."),
 ("chan83","episode","Sandkings",1995,"Stuart Gillard","Sci-Fi, Horror","The Outer Limits (1995) S01E01: a scientist breeds Martian insects in his barn."),
 ("chan83","episode","Time Enough at Last",1959,"John Brahm","Sci-Fi, Drama","The Twilight Zone S01E08: a bookish bank teller survives the end of the world."),
 ("toontown","short","Minnie the Moocher",1932,"Dave Fleischer","Animation","Betty Boop runs away from home and meets a ghostly walrus who sings Cab Calloway."),
 ("toontown","short","Bimbo's Initiation",1931,"Dave Fleischer","Animation","Bimbo falls into a secret society's surreal underground lair."),
 ("nas","movie","Heat",1995,"Michael Mann","Crime, Thriller","A master thief and the detective hunting him circle each other across Los Angeles."),
 ("nas","movie","Blade Runner",1982,"Ridley Scott","Sci-Fi, Noir","A blade runner hunts four replicants through a rain-soaked 2019 Los Angeles."),
 ("nas","movie","The Thing",1982,"John Carpenter","Horror, Sci-Fi","An Antarctic research crew is stalked by a shape-shifting alien."),
 ("nas","movie","Menace II Society",1993,"The Hughes Brothers","Crime, Drama","Caine tries to escape the cycle of violence in Watts after high school."),
 ("youtube","video","Air Force One press gaggle - full remarks",2026,"","News","Reporters question the President aboard Air Force One en route to the summit."),
 ("music","track","Blue in Green",1959,"Miles Davis","Jazz","Kind of Blue, track 3."),
]
PALETTES = [("#1e3a8a","#93c5fd"),("#7c2d12","#fdba74"),("#14532d","#86efac"),("#4a044e","#f0abfc"),("#0f172a","#cbd5e1"),("#7f1d1d","#fca5a5"),("#3f3f46","#e4e4e7")]
def poster(title, year):
    ensure_dirs(); p = POSTER_CACHE / ("demo_" + hashlib.md5(title.encode()).hexdigest()[:10] + ".png")
    if p.exists(): return str(p)
    a, b = random.Random(title).choice(PALETTES); img = Image.new("RGB", (400, 600), a); d = ImageDraw.Draw(img)
    for i in range(0, 600, 24): d.line([(0, i), (400, i + 120)], fill=b, width=1)
    d.rectangle([20, 380, 380, 580], fill=a); words = title.split(); lines = []; cur = ""
    for w in words:
        if len(cur + " " + w) > 16: lines.append(cur.strip()); cur = w
        else: cur += " " + w
    lines.append(cur.strip())
    for i, ln in enumerate(lines[:4]): d.text((32, 400 + i * 38), ln, fill="white")
    d.text((32, 545), str(year), fill=b); img.save(p); return str(p)
def main():
    wipe = "--wipe" in sys.argv; db.migrate(); c = db.connect()
    if wipe: c.execute("DELETE FROM items WHERE uid LIKE 'demo:%'")
    now = time.time()
    for i, (src, kind, title, year, director, genres, blurb) in enumerate(DEMO):
        uid = f"demo:{src}:{i}"; verified = 1 if src in ("nas", "toontown") or i % 2 == 0 else 0
        c.execute("""INSERT OR REPLACE INTO items(uid,source,kind,ext_id,title,year,blurb,director,genres,decade,poster_local,runtime_min,verified,verified_at,added,strict_pd)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (uid, src, kind, str(i), title, year, blurb, director, genres, (year // 10) * 10, poster(title, year), random.Random(uid).randint(65, 140), verified, now if verified else None, now - i * 3600, 1 if year <= 1930 else 0))
    c.execute("INSERT OR REPLACE INTO state(uid,resume_sec,duration_sec,last_played) VALUES('demo:nas:13',2400,10200,?)", (now,))
    c.execute("INSERT OR REPLACE INTO state(uid,resume_sec,duration_sec,last_played) VALUES('demo:pd:0',1500,7140,?)", (now - 100,))
    c.commit(); n = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]; c.close(); print(f"seeded; items={n}")
if __name__ == "__main__": main()
