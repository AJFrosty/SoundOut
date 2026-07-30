import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from store import Store

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>SoundOut — island picture</title>
<style>
 body{font:15px/1.5 system-ui,sans-serif;margin:0;background:#0f1116;color:#e8eaed}
 header{padding:18px 22px;background:#161a22;border-bottom:1px solid #262b36}
 h1{margin:0;font-size:1.15rem;letter-spacing:.3px}
 .sub{color:#8b93a3;font-size:.82rem;margin-top:3px}
 main{padding:22px;max-width:1000px}
 .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}
 .tile{background:#161a22;border:1px solid #262b36;border-radius:10px;padding:14px}
 .tile b{display:block;font-size:1.7rem;font-weight:600}
 .tile span{color:#8b93a3;font-size:.75rem;text-transform:uppercase;letter-spacing:.07em}
 table{width:100%;border-collapse:collapse;background:#161a22;border:1px solid #262b36;border-radius:10px;overflow:hidden}
 th{text-align:left;padding:10px 14px;background:#1b202a;font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;color:#8b93a3}
 td{padding:11px 14px;border-top:1px solid #262b36}
 .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.75rem}
 .open{background:#12321f;color:#67d98d}.cut{background:#3a1418;color:#f38b8b}
 .warn{background:#3a2d10;color:#f0c060}
 .need{display:inline-block;background:#1e2530;border:1px solid #2c3543;border-radius:6px;padding:1px 7px;margin:1px;font-size:.76rem}
 .empty{padding:40px;text-align:center;color:#8b93a3}
 .unver{color:#f0c060}
</style></head><body>
<header><h1>SoundOut — island picture</h1>
<div class="sub" id="meta">waiting for reports…</div></header>
<main><div class="tiles" id="tiles"></div><div id="table"></div></main>
<script>
async function tick(){
 const s = await (await fetch('/state')).json();
 document.getElementById('meta').textContent =
   s.summary.observations + ' observations heard · ' + new Date().toLocaleTimeString();
 document.getElementById('tiles').innerHTML = [
   ['shelters', s.summary.shelters], ['people', s.summary.people],
   ['casualties', s.summary.casualties], ['cut off', s.summary.cut_off.length]
 ].map(([k,v]) => `<div class="tile"><span>${k}</span><b>${v}</b></div>`).join('');

 if(!s.shelters.length){document.getElementById('table').innerHTML =
   '<div class="empty">No reports yet. Transmit one with report.py</div>';return;}

 const rows = s.shelters.map(x => `<tr>
   <td><b>${x.shelter}</b>${x.authenticated?'':' <span class="unver">unverified</span>'}</td>
   <td>${x.occupancy} / ${x.capacity}${x.full?' <span class="pill warn">full</span>':''}</td>
   <td>${x.needs.map(n=>`<span class="need">${n}</span>`).join('')||'—'}</td>
   <td>${x.casualties||'—'}</td>
   <td><span class="pill ${['impassable','flooded','bridge down','landslide'].includes(x.access)?'cut':'open'}">${x.access}</span></td>
   <td>${x.heard_at.replace('T',' ').replace('+00:00','')}</td></tr>`).join('');

 document.getElementById('table').innerHTML = `<table><tr><th>shelter</th><th>occupancy</th>
   <th>needs</th><th>casualties</th><th>access</th><th>heard</th></tr>${rows}</table>`;
}
tick(); setInterval(tick, 2000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    database = "soundout.db"

    def do_GET(self):
        if self.path.startswith("/state"):
            store = Store(self.database)
            body = json.dumps({
                "shelters": store.view(),
                "summary": store.summary(),
            }).encode("utf-8")
            store.close()
            content = "application/json"
        else:
            body = PAGE.encode("utf-8")
            content = "text/html; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=str, default="soundout.db")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    Handler.database = args.db
    print(f"dashboard on http://localhost:{args.port}  (reading {args.db})")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
