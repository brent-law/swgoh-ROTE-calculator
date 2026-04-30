#!/usr/bin/env python3
"""
Rise of the Empire — TB Planner
Self-contained launcher: downloads swgoh-comlink, serves the web app, opens your browser.

To run directly:  python rote_planner.py
To build .exe:    pip install pyinstaller && pyinstaller --onefile --name ROTE_Planner rote_planner.py
"""

import os
import sys
import json
import re
import platform
import subprocess
import threading
import webbrowser
import time
import socket
import urllib.request
import urllib.error
import unicodedata
import base64
import io
import zipfile
import tarfile
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
try:
    from rote_ops_fallback import build_wiki_tb_defs as _build_wiki_tb_defs_from_module
except Exception:
    _build_wiki_tb_defs_from_module = None
try:
    from swgoh_comlink import SwgohComlink as _StatCalcComlinkClient
    from swgoh_comlink import StatCalc as _LocalStatCalc
    from swgoh_comlink import GameDataBuilder as _StatCalcGameDataBuilder
    _STATCALC_IMPORT_ERROR = ""
except Exception as _statcalc_import_exc:
    _StatCalcComlinkClient = None
    _LocalStatCalc = None
    _StatCalcGameDataBuilder = None
    _STATCALC_IMPORT_ERROR = str(_statcalc_import_exc)

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in a separate thread."""
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except Exception:
                pass
        return super().server_bind()
from pathlib import Path
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ─── CONFIG ──────────────────────────────────────────────────────────────────
COMLINK_PORT   = 3000
APP_PORT       = 8080
APP_NAME       = "rote-tb-planner"
COMLINK_REPO   = "https://api.github.com/repos/swgoh-utils/swgoh-comlink/releases/latest"
AUTO_OPEN_BROWSER = True

# Resolve base directory (works both as .py and compiled .exe)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

COMLINK_DIR = BASE_DIR / ".comlink"
APP_LOG_PATH = BASE_DIR / "rote_planner_startup.log"

class _TeeStream:
    def __init__(self, original, logfile):
        self._original = original
        self._logfile = logfile
        self.encoding = getattr(original, "encoding", "utf-8")

    def write(self, data):
        try:
            self._original.write(data)
        except Exception:
            pass
        try:
            self._logfile.write(data)
        except Exception:
            pass
        return len(data)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass
        try:
            self._logfile.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self._original.isatty()
        except Exception:
            return False

    def fileno(self):
        return self._original.fileno()

def _install_startup_log():
    try:
        APP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(APP_LOG_PATH, "a", encoding="utf-8", errors="replace", buffering=1)
        log_file.write("\n" + "="*72 + "\n")
        log_file.write(time.strftime("Startup log opened %Y-%m-%d %H:%M:%S\n"))
        sys.stdout = _TeeStream(sys.stdout, log_file)
        sys.stderr = _TeeStream(sys.stderr, log_file)
        return True
    except Exception:
        return False

def _bind_app_server(preferred_port, host="127.0.0.1", search_limit=25):
    last_error = None
    for offset in range(search_limit + 1):
        port = int(preferred_port) + offset
        try:
            server = ThreadingHTTPServer((host, port), Handler)
            return server, port
        except OSError as exc:
            last_error = exc
            continue
    raise OSError(
        f"Could not bind an app server port from {preferred_port} to {preferred_port + search_limit}: {last_error}"
    )

# ─── EMBEDDED WEB APP ────────────────────────────────────────────────────────
HTML_APP = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Rise of the Empire — TB Planner</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Rajdhani:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#080c14;--bg2:#0d1220;--bg3:#111827;--bg4:#1a2236;
  --ds:#c0392b;--ds-dim:#5c1a14;--ds-glow:rgba(192,57,43,0.15);
  --mx:#27ae60;--mx-dim:#0d4a22;--mx-glow:rgba(39,174,96,0.15);
  --ls:#2980b9;--ls-dim:#0d2e4a;--ls-glow:rgba(41,128,185,0.15);
  --bonus:#8e44ad;--bonus-dim:#3b1a5e;--bonus-glow:rgba(142,68,173,0.15);
  --gold:#f0c040;--gold2:#c8a020;--silver:#a0aab4;
  --text:#e8eaf0;--text2:#c4d2e5;--text3:#a8bbd3;
  --border:rgba(255,255,255,0.07);--border2:rgba(255,255,255,0.13);
  --radius:8px;--radius-lg:14px;
}
html{font-size:17px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;min-height:100vh;line-height:1.35}
body::before{content:'';position:fixed;inset:0;background:
  radial-gradient(ellipse at 15% 50%,rgba(192,57,43,0.05) 0%,transparent 55%),
  radial-gradient(ellipse at 85% 50%,rgba(41,128,185,0.05) 0%,transparent 55%),
  radial-gradient(ellipse at 50% 5%,rgba(39,174,96,0.04) 0%,transparent 45%);
  pointer-events:none;z-index:0}
header{position:relative;z-index:2;padding:1.5rem 2rem 0;border-bottom:1px solid var(--border2)}
h1{font-family:'Orbitron',monospace;font-size:1.4rem;font-weight:700;letter-spacing:.12em;color:var(--gold);text-shadow:0 0 24px rgba(240,192,64,.35)}
.subtitle{font-size:.84rem;color:var(--text2);letter-spacing:.05em;margin-top:3px}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:var(--text3)}
.status-dot.online{background:var(--mx)}
.status-dot.offline{background:var(--ds)}
.nav-tabs{display:flex;gap:0;margin-top:1.25rem}
.nav-tab{font-family:'Rajdhani',sans-serif;font-size:.82rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:.5rem 1.25rem;border:1px solid var(--border2);border-bottom:none;background:transparent;color:var(--text2);cursor:pointer;transition:all .2s;border-radius:var(--radius) var(--radius) 0 0}
.nav-tab[hidden]{display:none !important}
.nav-tab:hover{color:var(--text);background:rgba(255,255,255,.03)}
.nav-tab.active{background:var(--bg3);color:var(--gold);border-color:rgba(240,192,64,.4);border-bottom-color:var(--bg3)}
.main{position:relative;z-index:1;padding:1.5rem 2rem}
.panel{display:none}.panel.active{display:block}
.card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1.25rem;margin-bottom:1rem}
.card-title{font-family:'Orbitron',monospace;font-size:.72rem;letter-spacing:.12em;color:var(--text2);text-transform:uppercase;margin-bottom:1rem;display:flex;align-items:center;gap:8px}
.card-title::after{content:'';flex:1;height:1px;background:var(--border)}
.field{margin-bottom:.75rem}
.field label{display:block;font-size:.78rem;color:var(--text2);letter-spacing:.04em;margin-bottom:4px}
.field input,.field select,.field textarea{width:100%;background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);padding:.45rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.9rem;outline:none;transition:border-color .2s}
.field input:focus,.field select:focus,.field textarea:focus{border-color:rgba(240,192,64,.5)}
.field small{display:block;font-size:.72rem;color:var(--text3);margin-top:3px}
.field textarea{resize:vertical;min-height:70px;font-size:.78rem;line-height:1.4}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.btn{font-family:'Orbitron',monospace;font-size:.72rem;letter-spacing:.1em;padding:.55rem 1.25rem;border:1px solid var(--border2);background:transparent;color:var(--text2);border-radius:var(--radius);cursor:pointer;transition:all .2s}
.btn:hover{border-color:var(--text2);color:var(--text)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn-gold{border-color:var(--gold2);color:var(--gold)}
.btn-gold:hover:not(:disabled){background:var(--gold);color:var(--bg);border-color:var(--gold)}
.btn-scan-loud{
  position:relative;
  border-color:#36f3a2;
  color:#ecfff6;
  background:linear-gradient(135deg,rgba(18,122,76,.95),rgba(30,186,116,.98));
  box-shadow:0 0 0 1px rgba(54,243,162,.24),0 0 18px rgba(54,243,162,.42),0 0 38px rgba(54,243,162,.22);
  text-shadow:0 0 10px rgba(255,255,255,.18);
  animation:scanPulse 1.8s ease-in-out infinite;
}
.btn-scan-loud:hover:not(:disabled){
  color:#ffffff;
  border-color:#8cffca;
  background:linear-gradient(135deg,rgba(23,145,92,1),rgba(43,221,141,1));
  box-shadow:0 0 0 1px rgba(140,255,202,.34),0 0 22px rgba(54,243,162,.55),0 0 48px rgba(54,243,162,.28);
  transform:translateY(-1px) scale(1.01);
}
.btn-scan-loud:disabled{
  animation:none;
  box-shadow:none;
}
@keyframes scanPulse{
  0%,100%{box-shadow:0 0 0 1px rgba(54,243,162,.22),0 0 14px rgba(54,243,162,.32),0 0 30px rgba(54,243,162,.16)}
  50%{box-shadow:0 0 0 1px rgba(140,255,202,.34),0 0 26px rgba(54,243,162,.62),0 0 60px rgba(54,243,162,.3)}
}
.btn-scan-repeat{
  border-color:rgba(165,190,220,.28);
  color:#cfe0f3;
  background:rgba(43,58,84,.86);
  box-shadow:0 0 0 1px rgba(165,190,220,.08);
  animation:none;
  text-shadow:none;
}
.btn-scan-repeat:hover:not(:disabled){
  border-color:rgba(210,226,248,.44);
  color:#f5fbff;
  background:rgba(58,77,108,.96);
  box-shadow:0 0 0 1px rgba(210,226,248,.14),0 0 16px rgba(102,144,198,.16);
  transform:translateY(-1px);
}
.scan-complete-banner{
  display:none;
  margin:10px 0 6px;
  padding:12px 16px;
  border-radius:12px;
  border:1px solid rgba(70,210,140,.32);
  background:linear-gradient(135deg,rgba(18,76,55,.88),rgba(26,108,72,.82));
  box-shadow:0 0 0 1px rgba(70,210,140,.08),0 0 24px rgba(39,174,96,.18);
}
.scan-complete-banner.show{display:block}
.scan-complete-title{
  font-family:'Orbitron',monospace;
  font-size:.84rem;
  letter-spacing:.08em;
  color:#bff4d9;
  margin-bottom:4px;
}
.scan-complete-sub{
  font-size:.78rem;
  color:#edf9f1;
  line-height:1.45;
}
.btn-full{display:block;width:100%;text-align:center}
.pill-toggle{display:inline-flex;border:1px solid var(--border2);border-radius:20px;overflow:hidden}
.pill-btn{font-family:'Rajdhani',sans-serif;font-size:.76rem;font-weight:600;letter-spacing:.06em;padding:3px 12px;background:transparent;border:none;color:var(--text2);cursor:pointer;transition:all .15s}
.pill-btn.active{background:var(--gold);color:var(--bg)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:1.25rem}
.metric{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:.75rem 1rem}
.metric-label{font-size:.68rem;letter-spacing:.08em;color:var(--text2);text-transform:uppercase;margin-bottom:4px}
.metric-val{font-family:'Orbitron',monospace;font-size:1.2rem;font-weight:600;color:var(--text)}
.metric-val.gold{color:var(--gold)}.metric-val.green{color:var(--mx)}.metric-val.purple{color:#c39bd3}
.prog-wrap{height:3px;background:var(--bg4);border-radius:2px;overflow:hidden}
.prog-fill{height:100%;border-radius:2px;transition:width .4s;max-width:100%}
.prog-fill.gold{background:var(--gold)}.prog-fill.green{background:var(--mx)}
hr.sep{border:none;border-top:1px solid var(--border);margin:1rem 0}
/* ── IMPORT ── */
.import-banner{background:rgba(240,192,64,.06);border:1px solid rgba(240,192,64,.2);border-radius:var(--radius-lg);padding:1rem 1.25rem;margin-bottom:1rem;display:flex;align-items:flex-start;gap:1rem}
.import-icon{font-size:1.5rem;flex-shrink:0;margin-top:2px}
.import-text h3{font-size:.85rem;font-weight:600;color:var(--gold);margin-bottom:3px}
.import-text p{font-size:.78rem;color:var(--text2);line-height:1.5}
.comlink-input-row{display:flex;gap:8px;align-items:flex-end}
.comlink-input-row .field{flex:1;margin-bottom:0}
.status-bar{display:flex;align-items:center;gap:8px;font-size:.75rem;padding:6px 10px;border-radius:var(--radius);margin-top:8px}
.status-bar.ok{background:rgba(39,174,96,.1);border:1px solid var(--mx-dim);color:var(--mx)}
.status-bar.err{background:rgba(192,57,43,.1);border:1px solid var(--ds-dim);color:var(--ds)}
.status-bar.loading{background:rgba(240,192,64,.08);border:1px solid rgba(240,192,64,.2);color:var(--gold2)}
.member-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;max-height:280px;overflow-y:auto;margin-top:10px}
.member-card{background:var(--bg4);border:1px solid var(--border);border-radius:var(--radius);padding:6px 10px;font-size:.78rem}
.member-name{color:var(--text);font-weight:600}
.member-gp{color:var(--text2);font-family:'Orbitron',monospace;font-size:.72rem}
.member-relic-bar{display:flex;gap:2px;margin-top:4px;flex-wrap:wrap}
.relic-pip{width:8px;height:8px;border-radius:50%;background:var(--bg3);border:1px solid var(--border2)}
.relic-pip.r5{background:#8e44ad}.relic-pip.r7{background:var(--gold)}
/* ── ROSTER ANALYSIS ── */
.unit-check-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin-top:8px}
.unit-check{background:var(--bg4);border:1px solid var(--border);border-radius:var(--radius);padding:8px 10px}
.unit-check-name{font-size:.78rem;font-weight:600;color:var(--text);margin-bottom:3px}
.unit-check-stat{font-size:.74rem;color:var(--text2)}
.unit-check-stat .count{color:var(--gold);font-family:'Orbitron',monospace;font-weight:600}
.unit-check-stat .count.good{color:var(--mx)}.unit-check-stat .count.warn{color:var(--gold2)}.unit-check-stat .count.bad{color:var(--ds)}
/* ── SETTINGS GRID ── */
.settings-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:1.25rem}
.falloff-viz{display:flex;gap:3px;align-items:flex-end;height:40px}
.daily-table{width:100%;border-collapse:collapse;font-size:.78rem}
.daily-table th{font-size:.69rem;letter-spacing:.08em;color:var(--text2);text-transform:uppercase;padding:6px 8px;text-align:left;border-bottom:1px solid var(--border)}
.daily-table td{padding:5px 8px;border-bottom:1px solid var(--border)}
.daily-table td input{width:100%;background:var(--bg4);border:1px solid var(--border2);border-radius:5px;padding:2px 6px;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.8rem;outline:none;text-align:center}
/* ── PLANNER ── */
.chain-select{display:flex;gap:8px;margin-bottom:1rem}
.chain-pill{font-family:'Rajdhani',sans-serif;font-size:.78rem;font-weight:600;letter-spacing:.08em;padding:.35rem 1rem;border:1px solid var(--border2);border-radius:20px;background:transparent;color:var(--text2);cursor:pointer;transition:all .2s}
.chain-pill.ds.active{background:var(--ds-glow);border-color:var(--ds);color:var(--ds)}
.chain-pill.mx.active{background:var(--mx-glow);border-color:var(--mx);color:var(--mx)}
.chain-pill.ls.active{background:var(--ls-glow);border-color:var(--ls);color:var(--ls)}
.planet-chain{display:flex;flex-direction:column;gap:0}
.planet-row{display:flex;gap:10px;align-items:flex-start}
.chain-col{display:flex;flex-direction:column;align-items:center;width:28px;flex-shrink:0;padding-top:1rem}
.chain-seg{width:2px;flex:1;min-height:30px}
.chain-seg.ds{background:linear-gradient(to bottom,var(--ds),var(--ds-dim))}
.chain-seg.mx{background:linear-gradient(to bottom,var(--mx),var(--mx-dim))}
.chain-seg.ls{background:linear-gradient(to bottom,var(--ls),var(--ls-dim))}
.chain-seg.bonus{background:repeating-linear-gradient(to bottom,var(--bonus) 0,var(--bonus) 5px,transparent 5px,transparent 10px)}
.chain-dot{width:10px;height:10px;border-radius:50%;border:2px solid;flex-shrink:0}
.chain-dot.ds{border-color:var(--ds);background:var(--ds-dim)}
.chain-dot.mx{border-color:var(--mx);background:var(--mx-dim)}
.chain-dot.ls{border-color:var(--ls);background:var(--ls-dim)}
.pcard{flex:1;min-width:0;background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1rem;margin-bottom:10px;transition:border-color .2s;position:relative;overflow:hidden}
.pcard.ds{border-color:var(--ds-dim)}.pcard.mx{border-color:var(--mx-dim)}.pcard.ls{border-color:var(--ls-dim)}
.pcard.bonus-card{border-color:var(--bonus-dim);border-style:dashed}
.pcard.s3.ds{border-color:var(--ds)}.pcard.s3.mx{border-color:var(--mx)}.pcard.s3.ls{border-color:var(--ls)}.pcard.s3.bonus-card{border-color:var(--bonus)}
.pcard.s2{border-color:var(--gold2)}.pcard.s1{border-color:var(--silver)}
.pcard.locked-planet{opacity:.35;pointer-events:none}
.pcard-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.pcard-name{font-family:'Orbitron',monospace;font-size:.72rem;font-weight:600;letter-spacing:.06em}
.roster-sort-btn{background:transparent;border:none;color:var(--text3);cursor:pointer;text-align:left;padding:2px 4px;font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;font-family:'Rajdhani',sans-serif;transition:color .15s}.roster-sort-btn:hover,.roster-sort-btn.active{color:var(--gold)}
.align-badge{font-size:.66rem;font-weight:600;letter-spacing:.05em;padding:2px 8px;border-radius:12px}
.align-badge.ds{background:var(--ds-glow);color:var(--ds);border:1px solid var(--ds-dim)}
.align-badge.mx{background:var(--mx-glow);color:var(--mx);border:1px solid var(--mx-dim)}
.align-badge.ls{background:var(--ls-glow);color:var(--ls);border:1px solid var(--ls-dim)}
.align-badge.bonus{background:var(--bonus-glow);color:#c39bd3;border:1px solid var(--bonus-dim)}
.align-badge.bonus-locked{background:rgba(74,85,104,.2);color:var(--text3);border:1px solid var(--border)}
.stars-row{display:flex;gap:2px;margin-bottom:5px}
.star{font-size:13px;color:var(--text3)}.star.on{color:var(--gold)}
.pts-row{font-size:.78rem;color:var(--text2);margin-bottom:6px}
.pts-row b{color:var(--text)}
.msec{margin-bottom:8px}
.msec-head{font-size:.68rem;letter-spacing:.08em;color:var(--text3);text-transform:uppercase;margin-bottom:5px;display:flex;align-items:center;gap:6px}
.msec-head::after{content:'';flex:1;height:1px;background:var(--border)}
.cm-row{display:grid;grid-template-columns:5rem 1fr 1fr;gap:5px;align-items:center;margin-bottom:4px}
.cm-row-label{font-size:.74rem;color:var(--text2)}
.mini-in{background:var(--bg4);border:1px solid var(--border2);border-radius:5px;padding:3px 6px;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.78rem;outline:none;text-align:center;width:100%}
.mini-in:focus{border-color:rgba(240,192,64,.5)}
.mini-label{font-size:.64rem;color:var(--text3);text-align:center;margin-bottom:2px}
.mini-val{font-size:.72rem;color:var(--text3);text-align:center}
.ops-row{display:flex;gap:5px;margin-bottom:3px;flex-wrap:wrap}
.ops-btn{width:26px;height:22px;border-radius:4px;border:1px solid var(--border2);background:var(--bg4);color:var(--text3);font-size:.65rem;font-weight:600;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .15s}
.ops-btn.on{background:var(--gold);border-color:var(--gold);color:var(--bg)}
.ops-pts-note{font-size:.7rem;color:var(--text3)}
.sm-box{background:rgba(142,68,173,.08);border:1px solid var(--bonus-dim);border-radius:var(--radius);padding:7px 10px;margin-bottom:8px}
.sm-box-label{font-size:.68rem;color:#d8b9ff;margin-bottom:4px}
.sm-progress-row{display:flex;align-items:center;gap:8px}
.sm-pbar{flex:1;height:4px;background:var(--bg4);border-radius:2px;overflow:hidden}
.sm-pfill{height:100%;background:var(--bonus);border-radius:2px;transition:width .3s}
.sm-note{font-size:.7rem;color:var(--text3);margin-top:4px}
.gp-deploy-note{font-size:.72rem;color:var(--text3);white-space:nowrap}
.pnote{font-size:.72rem;margin-top:5px}
.pnote.maxed{color:var(--mx)}.pnote.need{color:var(--text3)}
.bonus-horiz{height:2px;width:40px;background:repeating-linear-gradient(to right,var(--bonus) 0,var(--bonus) 5px,transparent 5px,transparent 10px);margin-top:12px}
/* ── DAY PLAN ── */
.day-block{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1rem;margin-bottom:10px}
.day-block-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.day-title{font-family:'Orbitron',monospace;font-size:.78rem;letter-spacing:.08em;color:var(--gold)}
.day-chains-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.day-chain{border-radius:var(--radius);padding:.75rem}
.day-chain.ds{background:var(--ds-glow);border:1px solid var(--ds-dim)}
.day-chain.mx{background:var(--mx-glow);border:1px solid var(--mx-dim)}
.day-chain.ls{background:var(--ls-glow);border:1px solid var(--ls-dim)}
.day-chain.bonus{background:var(--bonus-glow);border:1px solid var(--bonus-dim)}
.day-chain-title{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;font-weight:600;margin-bottom:5px}
.day-chain.ds .day-chain-title{color:var(--ds)}.day-chain.mx .day-chain-title{color:var(--mx)}.day-chain.ls .day-chain-title{color:var(--ls)}.day-chain.bonus .day-chain-title{color:#c39bd3}
.day-planet-name{font-family:'Orbitron',monospace;font-size:.72rem;color:var(--text);margin-bottom:2px}
.day-stars{font-size:.78rem;color:var(--gold);margin-bottom:2px}
.day-action{font-size:.74rem;color:var(--text2);line-height:1.45}
.day-breakdown{font-size:.68rem;color:var(--text3);line-height:1.5;margin-top:2px}
.day-advance{font-size:.7rem;color:var(--text3);margin-top:4px}
.day-preload{font-size:.7rem;color:#d8b9ff;font-style:italic}
.day-notes{margin-top:8px;padding-top:8px;border-top:1px solid var(--border)}
.day-note{font-size:.75rem;color:var(--text2);padding:2px 0}
.day-note.bonus{color:#c39bd3}
.dayplan-warning{background:rgba(240,192,64,.06);border:1px solid rgba(240,192,64,.2)}
.dayplan-warning.confirmed{background:rgba(39,174,96,.08);border-color:rgba(39,174,96,.25)}
.dayplan-warning-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.dayplan-warning-copy{font-size:.8rem;color:var(--text2);line-height:1.6;max-width:980px}
.dayplan-warning-note{font-size:.72rem;color:var(--gold);margin-top:.45rem;line-height:1.5}
.dayplan-algo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:1rem}
.dayplan-algo-card{background:rgba(255,255,255,.02);border:1px solid var(--border);border-radius:var(--radius);padding:.85rem}
.dayplan-algo-title{font-family:'Orbitron',monospace;font-size:.68rem;letter-spacing:.08em;color:var(--text);margin-bottom:.35rem}
.dayplan-algo-desc{font-size:.76rem;color:var(--text2);line-height:1.5;min-height:4.2em}
.dayplan-algo-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:.65rem}
.dayplan-algo-badge{font-size:.66rem;letter-spacing:.06em;text-transform:uppercase;padding:3px 8px;border-radius:999px;border:1px solid var(--border2);color:var(--text2)}
.dayplan-algo-badge.quality{border-color:rgba(39,174,96,.28);color:var(--mx)}
.dayplan-algo-badge.complexity{border-color:rgba(240,192,64,.28);color:var(--gold)}
.dayplan-algo-badge.runtime{border-color:rgba(41,128,185,.28);color:#7fb6de}
.ops-layout{display:grid;grid-template-columns:minmax(280px,340px) 1fr;gap:12px;align-items:start}
.ops-sidebar{display:flex;flex-direction:column;gap:10px}
.ops-main-pane{min-width:0}
.ops-day-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:.9rem 1rem}
.ops-day-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.ops-day-title{font-family:'Orbitron',monospace;font-size:.7rem;letter-spacing:.08em;color:var(--gold)}
.ops-day-points{font-size:.72rem;color:var(--mx);font-family:'Orbitron',monospace}
.ops-day-line{font-size:.75rem;color:var(--text2);line-height:1.5;padding:2px 0}
.ops-day-line strong{color:var(--text)}
.ops-planet-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.ops-planet-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1rem}
.ops-planet-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px}
.ops-planet-name{font-family:'Orbitron',monospace;font-size:.74rem;letter-spacing:.06em;color:var(--text)}
.ops-planet-meta{font-size:.7rem;color:var(--text3);margin-top:3px}
.ops-planet-summary{font-size:.74rem;color:var(--text2);text-align:right}
.ops-planet-summary strong{color:var(--gold)}
.ops-platoon{border:1px solid var(--border);border-radius:var(--radius);padding:.7rem .8rem;margin-top:8px;background:rgba(255,255,255,.015)}
.ops-platoon.complete{border-color:var(--mx-dim);background:rgba(39,174,96,.06)}
.ops-platoon-header{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.ops-platoon-title{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text2)}
.ops-platoon-status{font-size:.7rem;color:var(--text3)}
.ops-platoon-status.complete{color:var(--mx)}
.ops-req-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:3px 0}
.ops-req-name{font-size:.74rem;color:var(--text)}
.ops-req-sub{font-size:.68rem;color:var(--text3)}
.ops-req-count{font-size:.72rem;color:var(--text2);font-family:'Orbitron',monospace;white-space:nowrap}
.ops-req-count.good{color:var(--mx)}
.ops-req-count.warn{color:var(--gold)}
.ops-empty{padding:1.2rem;border:1px dashed var(--border2);border-radius:var(--radius-lg);font-size:.76rem;color:var(--text2);text-align:center}
.ops-day-picker{cursor:pointer;transition:transform .15s,border-color .15s,box-shadow .15s}
.ops-day-picker:hover{transform:translateY(-1px)}
.ops-day-picker.active{box-shadow:0 0 0 1px rgba(255,255,255,.08),0 0 18px rgba(255,255,255,.06)}
.ops-day-kicker{font-size:.66rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text2)}
.ops-day-sub{font-size:.75rem;color:var(--text2);margin-top:4px;line-height:1.5}
.ops-main-stage{display:flex;flex-direction:column;gap:12px}
.ops-planet-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.ops-planet-pill{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:.85rem .95rem;cursor:pointer;transition:border-color .15s,transform .15s,box-shadow .15s}
.ops-planet-pill:hover{transform:translateY(-1px);border-color:var(--border2)}
.ops-planet-pill.active{border-color:rgba(240,192,64,.45);box-shadow:0 0 0 1px rgba(240,192,64,.12)}
.ops-planet-pill-name{font-family:'Orbitron',monospace;font-size:.7rem;letter-spacing:.06em;color:var(--text)}
.ops-planet-pill-meta{font-size:.7rem;color:var(--text3);margin-top:4px;line-height:1.5}
.ops-planet-pill-today{font-size:.74rem;color:var(--text2);margin-top:8px}
.ops-stage-card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1rem}
.ops-stage-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:.85rem}
.ops-stage-title{font-family:'Orbitron',monospace;font-size:.8rem;letter-spacing:.08em;color:var(--gold)}
.ops-stage-sub{font-size:.76rem;color:var(--text2);line-height:1.55;margin-top:4px;max-width:760px}
.ops-stage-meta{font-size:.72rem;color:var(--text2);text-align:right;line-height:1.55}
.ops-platoon-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.ops-platoon-day{border:1px solid var(--border);border-radius:var(--radius-lg);padding:.85rem;background:rgba(255,255,255,.015)}
.ops-platoon-day.complete{border-color:var(--mx)}
.ops-platoon-day.partial{border-color:#2980b9;background:rgba(41,128,185,.08)}
.ops-platoon-day.impossible{border-color:var(--ds);background:rgba(192,57,43,.08)}
.ops-platoon-day.ready{border-color:var(--gold2)}
.ops-platoon-day-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:.7rem}
.ops-platoon-day-title{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text2)}
.ops-platoon-day-badge{display:inline-flex;align-items:center;gap:6px;font-size:.68rem;color:var(--text2);text-align:right}
.ops-platoon-day-dot{width:10px;height:10px;border-radius:50%;border:2px solid var(--border2);flex-shrink:0}
.ops-platoon-day.complete .ops-platoon-day-dot{border-color:var(--mx);background:rgba(39,174,96,.2)}
.ops-platoon-day.partial .ops-platoon-day-dot{border-color:#3498db;background:rgba(52,152,219,.2)}
.ops-platoon-day.impossible .ops-platoon-day-dot{border-color:var(--ds);background:rgba(192,57,43,.2)}
.ops-platoon-day.ready .ops-platoon-day-dot{border-color:var(--gold2);background:rgba(240,192,64,.18)}
.ops-slot-list{display:flex;flex-direction:column;gap:8px}
.ops-slot-card{border:1px solid var(--border);border-radius:var(--radius);padding:.6rem .7rem;background:rgba(0,0,0,.14)}
.ops-slot-name{font-size:.75rem;color:var(--text);font-weight:600;line-height:1.35}
.ops-slot-assignee{font-size:.74rem;color:var(--gold);margin-top:3px}
.ops-slot-assignee.unassigned{color:var(--text3)}
.ops-slot-meta{font-size:.68rem;color:var(--text3);line-height:1.5;margin-top:3px}
.ops-missing-card{margin-top:12px;border:1px dashed rgba(192,57,43,.4);border-radius:var(--radius-lg);padding:.9rem 1rem;background:rgba(192,57,43,.06)}
.ops-missing-title{font-family:'Orbitron',monospace;font-size:.68rem;letter-spacing:.08em;color:#ffb3ac;text-transform:uppercase;margin-bottom:6px}
.ops-missing-text{font-size:.78rem;color:var(--text2);line-height:1.55}
.ops-missing-subtitle{font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:#ffb3ac;margin-top:.75rem;margin-bottom:.35rem}
.ops-missing-line{font-size:.75rem;color:var(--text2);line-height:1.5;padding:2px 0}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
@media(max-width:980px){.ops-layout{grid-template-columns:1fr}}
@media(max-width:768px){header,.main{padding:1rem}.day-chains-grid{grid-template-columns:1fr}.settings-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <h1>⚔ Rise of the Empire — TB Planner</h1>
      <div class="subtitle">Star Wars: Galaxy of Heroes | Territory Battle Calculator</div>
    </div>
    <div style="text-align:right;padding-top:4px">
      <div style="font-size:.68rem;color:var(--text2)">swgoh-comlink</div>
      <div style="display:flex;align-items:center;gap:8px;justify-content:flex-end">
        <div style="font-size:.72rem;font-family:'Orbitron',monospace">
          <span class="status-dot" id="comlink-dot"></span><span id="comlink-label">checking...</span>
        </div>
        <button id="retry-comlink-btn"
          onclick="recheckComlink(this)"
          style="font-size:.6rem;padding:2px 8px;font-family:'Rajdhani',sans-serif;font-weight:600;
                 letter-spacing:.04em;border:1px solid var(--border2);background:transparent;
                 color:var(--text2);border-radius:4px;cursor:pointer;line-height:1.6"
          onmouseover="this.style.borderColor='var(--gold2)';this.style.color='var(--gold)'"
          onmouseout="this.style.borderColor='var(--border2)';this.style.color='var(--text2)'">
          &#8635; Retry
        </button>
      </div>
    </div>
  </div>
  <div class="nav-tabs">
    <button class="nav-tab active" data-tab="setup" onclick="showTab('setup')">Guild Overview</button>
    <button class="nav-tab" data-tab="planner" onclick="showTab('planner')">Planet Planner</button>
    <button class="nav-tab" data-tab="dayplan" onclick="showTab('dayplan')">Day-by-Day Plan</button>
    <button class="nav-tab" data-tab="operations" onclick="showTab('operations')" hidden>Operations</button>
    <button class="nav-tab" data-tab="guides" onclick="showTab('guides')">Guides</button>
    <button class="nav-tab" data-tab="roster" onclick="showTab('roster')">Roster</button>
  </div>
</header>

<div class="main">

<div class="panel active" id="panel-setup">

  <!-- Live Import via Comlink -->
  <div class="card" id="comlink-import-card">
    <div class="card-title">Live Guild Import</div>
    <div class="import-banner">
      <div class="import-icon">🔌</div>
      <div class="import-text">
        <h3>Import directly from the game</h3>
        <p>Enter any guild member's ally code to automatically fetch your guild's GP, member list, and roster data. <br>
        Ally codes look like: <code style="color:var(--gold);font-size:.75rem">658-388-776</code></p>
      </div>
    </div>
    <div class="comlink-input-row">
      <div class="field">
        <label>Ally Code (any guild member)</label>
        <input type="text" id="ally-code-input" placeholder="658-388-776" maxlength="12">
      </div>
      <button class="btn btn-gold" id="fetch-guild-btn" onclick="fetchGuildByAllyCode()" style="height:36px;margin-bottom:0;white-space:nowrap">⟳ Fetch Guild</button>
    </div>
    <div id="import-status-bar" style="display:none"></div>
    <div id="member-display" style="display:none">
      <hr class="sep">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div style="font-size:.8rem;font-weight:600;color:var(--text)" id="guild-name-display">—</div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-scan-loud" style="font-size:.68rem;padding:7px 14px;font-weight:700" onclick="scanAndAnalyze()" id="scan-btn">⚡ Scan Rosters</button>
          <div style="font-size:.72rem;color:var(--text2);font-family:'Orbitron',monospace" id="member-gp-display">—</div>
        </div>
      </div>
      <div id="scan-complete-banner" class="scan-complete-banner"></div>
      <div class="member-grid" id="member-grid"></div>
      <div id="roster-analysis" style="display:none;margin-top:12px">
        <div style="font-size:.72rem;color:var(--text2);margin-bottom:8px">Key ROTE units at Relic 5+ across guild</div>
        <div class="unit-check-grid" id="unit-check-grid"></div>
      </div>
    </div>
  </div>

  <div class="settings-grid">
    <!-- Guild Stats -->
    <div class="card">
      <div class="card-title">Guild Stats</div>
      <div class="field">
        <label>Total Guild Galactic Power</label>
        <input type="number" id="guild-gp" value="400000000" oninput="onStatsChange()">
        <small>Auto-filled on import. Edit if needed.</small>
      </div>
      <div class="field">
        <label>Active Members</label>
        <input type="number" id="guild-members" value="50" min="1" max="50" oninput="onStatsChange()">
      </div>
      <hr class="sep">
      <div class="metrics" style="grid-template-columns:1fr 1fr;margin-bottom:0">
        <div class="metric"><div class="metric-label">Est. Stars</div><div class="metric-val gold" id="s-stars">—</div></div>
        <div class="metric"><div class="metric-label">Ops Filled</div><div class="metric-val green" id="s-ops">—</div></div>
      </div>
    </div>

    <!-- CM Estimates -->
    <div class="card">
      <div class="card-title">Mission Completion Estimates</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:.75rem;color:var(--text2)">Mode</span>
        <div class="pill-toggle">
          <button class="pill-btn active" id="mode-pct-btn" onclick="setCmMode('pct')">% Rate</button>
          <button class="pill-btn" id="mode-count-btn" onclick="setCmMode('count')"># Count</button>
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label id="cm-base-label">CM base %</label>
          <input type="number" id="cm-base" value="70" min="0" max="100" oninput="onFalloffChange()">
          <small>Day 1 / first planet</small>
        </div>
        <div class="field">
          <label id="cm-falloff-label">CM falloff % per planet</label>
          <input type="number" id="cm-falloff" value="10" min="0" max="100" oninput="onFalloffChange()">
        </div>
      </div>
      <div class="row2">
        <div class="field">
          <label id="fleet-base-label">Fleet base %</label>
          <input type="number" id="fleet-base" value="50" min="0" max="100" oninput="onFalloffChange()">
        </div>
        <div class="field">
          <label id="fleet-falloff-label">Fleet falloff % per planet</label>
          <input type="number" id="fleet-falloff" value="15" min="0" max="100" oninput="onFalloffChange()">
        </div>
      </div>
      <div id="falloff-viz" style="margin-top:4px">
        <div style="font-size:.6rem;color:var(--text3);margin-bottom:4px;text-transform:uppercase;letter-spacing:.06em">Rate by planet depth</div>
        <div class="falloff-viz" id="fviz"></div>
        <div style="display:flex;gap:3px;margin-top:2px" id="fviz-labels"></div>
      </div>
      <hr class="sep" style="margin:10px 0">
      <button class="btn btn-gold btn-full" onclick="applyDefaultsToPlanner()">⟶ Apply to Planet Planner</button>
      <div id="apply-status" style="font-size:.68rem;color:var(--mx);text-align:center;margin-top:6px;min-height:16px"></div>
    </div>

    <!-- Daily Undeployed GP -->
    <div class="card">
      <div class="card-title">Daily Undeployed GP</div>
      <div style="font-size:.72rem;color:var(--text2);line-height:1.6;margin-bottom:10px">Account for members who miss a day. Set undeployed GP per day.</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:.75rem;color:var(--text2)">Mode</span>
        <div class="pill-toggle">
          <button class="pill-btn active" id="undep-pct-btn" onclick="setUndepMode('pct')">% of GP</button>
          <button class="pill-btn" id="undep-flat-btn" onclick="setUndepMode('flat')">Flat GP</button>
        </div>
      </div>
      <table class="daily-table">
        <thead><tr><th>Day</th><th id="undep-col-hdr">Undeployed %</th><th>Effective GP</th></tr></thead>
        <tbody id="undep-tbody"></tbody>
      </table>
      <button class="btn" style="font-size:.62rem;padding:3px 10px;margin-top:8px;font-family:'Rajdhani',sans-serif;letter-spacing:.05em" onclick="fillSameUndep()">Fill all from Day 1</button>
    </div>
  </div>
</div>

<div class="panel" id="panel-planner">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem">
    <div class="chain-select">
      <button class="chain-pill ds active" onclick="showChain('ds')">⚫ Dark Side</button>
      <button class="chain-pill mx" onclick="showChain('mx')">🟢 Mixed</button>
      <button class="chain-pill ls" onclick="showChain('ls')">🔵 Light Side</button>
    </div>
  </div>
  <div id="chain-ds" class="planet-chain"></div>
  <div id="chain-mx" class="planet-chain" style="display:none"></div>
  <div id="chain-ls" class="planet-chain" style="display:none"></div>
</div>

<div class="panel" id="panel-operations">
  <div class="metrics" id="ops-metrics">
    <div class="metric"><div class="metric-label">Projected Platoons</div><div class="metric-val green" id="ops-total-platoons">—</div></div>
    <div class="metric"><div class="metric-label">Projected Ops Points</div><div class="metric-val gold" id="ops-total-points">—</div></div>
    <div class="metric"><div class="metric-label">Definitions Loaded</div><div class="metric-val" id="ops-def-status">—</div></div>
    <div class="metric"><div class="metric-label">Roster Coverage</div><div class="metric-val purple" id="ops-roster-status">—</div></div>
  </div>
  <div class="card" style="margin-bottom:1rem">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
      <div>
        <div class="card-title" style="margin-bottom:.5rem">Operations Planner</div>
        <div style="font-size:.76rem;color:var(--text2);line-height:1.5">
          Platoons are planned automatically from scanned rosters and the current day-by-day focus order. Focus planets get first claim on eligible units, then remaining capacity is used to preload other open platoons.
        </div>
      </div>
      <button class="btn btn-gold" onclick="refreshOperationsPlanning(true)">⟳ Refresh Operations</button>
    </div>
  </div>
  <div class="ops-layout">
    <div class="ops-sidebar">
      <div id="ops-day-overview"></div>
    </div>
    <div id="ops-planet-list" class="ops-main-pane"></div>
  </div>
</div>

<div class="panel" id="panel-dayplan">
  <div class="card dayplan-warning" id="dayplan-warning-card">
    <div class="dayplan-warning-head">
      <div>
        <div class="card-title" style="margin-bottom:.55rem">Optimizer Warning</div>
        <div class="dayplan-warning-copy">
          These optimization passes can take a long time, especially after scanned rosters and operations assignments are folded into the search. On slower machines the app may appear to hang while a long-running algorithm is still working.
        </div>
        <div class="dayplan-warning-note">
          ADAM is currently the slowest option and may still take 1+ hours on larger guild states. "All Algorithms" runs every option back-to-back, then compares the best path from each one, so it should only be used when you're prepared for a 2+ hour full pass. Rule of thumb: use Greedy for quick checks, PSO or GA for serious planning, and reserve ADAM or All Algorithms for long unattended runs.
        </div>
      </div>
      <button id="dayplan-warning-btn" class="btn btn-gold" onclick="confirmOptimizerWarning()" style="white-space:nowrap">
        I Understand
      </button>
    </div>
    <div id="dayplan-algo-guide" class="dayplan-algo-grid"></div>
  </div>
  <div class="metrics" id="plan-metrics">
    <div class="metric"><div class="metric-label">Total Est. Stars</div><div class="metric-val gold" id="pm-stars">—</div></div>
    <div class="metric"><div class="metric-label">Max Possible</div><div class="metric-val" id="pm-max">—</div></div>
    <div class="metric"><div class="metric-label">Bonus Planets</div><div class="metric-val purple" id="pm-bonus">—</div></div>
    <div class="metric"><div class="metric-label">Ops Filled</div><div class="metric-val green" id="pm-ops">—</div></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:1rem">
    <!-- Algorithm selector -->
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:.6rem">
      <select id="algo-sel" style="flex:1;background:var(--bg4);border:1px solid var(--border2);
        border-radius:var(--radius);padding:.38rem .65rem;color:var(--text);
        font-family:'Rajdhani',sans-serif;font-size:.82rem" onchange="updateDayPlanUiState()">
        <option value="">Choose an optimization algorithm...</option>
        <option value="greedy">Greedy Enumeration (Rule-Based)</option>
        <option value="sa">Simulated Annealing</option>
        <option value="pso">Particle Swarm Optimization</option>
        <option value="ga">Genetic Algorithm</option>
        <option value="adam">Adam Optimizer</option>
        <option value="all">All Algorithms (Compare Best Result)</option>
      </select>
    </div>
    <!-- Progress-fill button -->
    <div style="position:relative;margin-bottom:.4rem;border-radius:var(--radius);overflow:hidden">
      <div id="opt-pfill" style="position:absolute;inset:0;width:0%;
        background:var(--gold);opacity:.22;transition:width .12s ease;pointer-events:none"></div>
      <button id="quick-plan-btn" class="btn btn-gold btn-full" onclick="startOptimization()"
        style="position:relative;z-index:1;width:100%;margin:0" disabled>
        ⟳ Run Optimization
      </button>
    </div>
  </div>
  <div id="opt-status-line" style="font-size:.7rem;color:var(--text3);margin-bottom:.75rem;text-align:center">
    Select an algorithm and click Run to generate the optimal TB plan.
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:.85rem">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <select id="export-plan-mode" style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);padding:.35rem .6rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.8rem">
        <option value="all">One PDF with all days</option>
        <option value="separate">Separate PDF windows by day</option>
      </select>
      <select id="export-plan-detail-mode" style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);padding:.35rem .6rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.8rem">
        <option value="detailed">Detailed platoons</option>
        <option value="condensed">Condensed platoons</option>
      </select>
      <button id="export-plan-pdf-btn" class="btn" onclick="exportCurrentPlanPdf()" disabled>
        Export Plan PDF
      </button>
    </div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button id="export-plan-snapshot-btn" class="btn" onclick="exportPlannerSnapshot()" disabled>
        Save Plan Snapshot
      </button>
      <label class="btn" style="display:inline-flex;align-items:center;cursor:pointer">
        Load Plan Snapshot
        <input type="file" accept=".json" id="plan-snapshot-input" style="display:none" onchange="importPlannerSnapshot(this)">
      </label>
    </div>
  </div>
  <div id="day-plan-output"></div>
</div>

<div class="panel" id="panel-guides">
  <!-- Header: member selector + save/load -->
  <div style="display:flex;justify-content:space-between;align-items:center;
              flex-wrap:wrap;gap:10px;margin-bottom:1rem">
    <div style="display:flex;align-items:center;gap:10px;flex:1;min-width:200px">
      <label style="font-size:.72rem;color:var(--text2);white-space:nowrap">Viewing for:</label>
      <select id="guide-member-sel" onchange="updateGuideChecks()"
        style="flex:1;background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
               padding:.35rem .6rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem">
        <option value="">-- Scan rosters first --</option>
      </select>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <button onclick="exportGuide()" title="Save squads to shareable JSON file"
        style="font-size:.68rem;padding:5px 12px;font-family:'Orbitron',monospace;letter-spacing:.06em;
               border:1px solid var(--gold2);background:transparent;color:var(--gold);border-radius:var(--radius);cursor:pointer">
        &#128190; Save Guide
      </button>
      <label title="Load squads from JSON file"
        style="font-size:.68rem;padding:5px 12px;font-family:'Orbitron',monospace;letter-spacing:.06em;
               border:1px solid var(--border2);background:transparent;color:var(--text2);border-radius:var(--radius);
               cursor:pointer;display:inline-block">
        &#128194; Load Guide
        <input type="file" accept=".json" id="guide-import-input" style="display:none"
               onchange="importGuide(this)">
      </label>
    </div>
  </div>

  <!-- Two-pane layout -->
  <div style="display:grid;grid-template-columns:260px 1fr;gap:1rem;min-height:500px">
    <!-- Left: Planet list -->
    <div id="guide-planet-list"
      style="overflow-y:auto;max-height:calc(100vh - 220px);border:1px solid var(--border);
             border-radius:var(--radius);padding:6px 0">
      <!-- Rendered by JS renderGuidePlanetList() -->
    </div>
    <!-- Right: Mission detail -->
    <div id="guide-mission-panel"
      style="overflow-y:auto;max-height:calc(100vh - 220px);border:1px solid var(--border);
             border-radius:var(--radius);padding:1rem">
      <div style="display:flex;align-items:center;justify-content:center;height:100%;
                  color:var(--text3);font-size:.8rem;text-align:center">
        Select a planet mission from the left to view and manage squads.
      </div>
    </div>
  </div>

  <!-- Squad Editor Modal -->
  <div id="squad-editor-overlay"
    onclick="if(event.target===this) closeSquadEditor()"
    style="position:fixed;inset:0;background:#060b14;z-index:40000;
           display:none;align-items:flex-start;justify-content:center;padding:20px 14px;overflow-y:auto">
    <div style="position:relative;background:#0f1627;border:1px solid rgba(255,255,255,.14);border-radius:12px;
                padding:1.25rem 1.5rem 1.5rem;width:min(620px,100%);max-height:calc(100vh - 40px);overflow-y:auto;
                box-shadow:0 18px 48px rgba(0,0,0,.58)">
      <div style="position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;align-items:center;margin:0 -1.5rem 1rem;padding:1.1rem 1.5rem .9rem;background:#0f1627;border-bottom:1px solid rgba(255,255,255,.08)">
        <div style="font-family:'Orbitron',monospace;font-size:.85rem;letter-spacing:.08em;
                    color:var(--gold)" id="squad-editor-title">Add Squad</div>
        <button onclick="closeSquadEditor()"
          style="display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;background:#141d31;border:1px solid var(--border2);color:var(--text2);font-size:1rem;line-height:1;border-radius:50%;cursor:pointer;flex-shrink:0">&#x2715;</button>
      </div>
      <!-- Difficulty -->
      <div class="field" style="margin-bottom:.75rem">
        <label style="font-size:.68rem">Difficulty</label>
        <div style="display:flex;gap:8px;margin-top:4px" id="diff-selector">
          <button onclick="selectDiff('auto')"   id="diff-auto"   class="diff-btn diff-active-auto"   style="flex:1;padding:6px;font-size:.7rem;border-radius:6px;cursor:pointer;border:2px solid #27ae60;background:rgba(39,174,96,.2);color:#2ecc71;font-family:'Rajdhani',sans-serif;font-weight:700">&#10003; Auto</button>
          <button onclick="selectDiff('easy')"   id="diff-easy"   class="diff-btn"                    style="flex:1;padding:6px;font-size:.7rem;border-radius:6px;cursor:pointer;border:2px solid var(--border2);background:transparent;color:var(--text2);font-family:'Rajdhani',sans-serif;font-weight:700">&#128077; Easy</button>
          <button onclick="selectDiff('medium')" id="diff-medium" class="diff-btn"                    style="flex:1;padding:6px;font-size:.7rem;border-radius:6px;cursor:pointer;border:2px solid var(--border2);background:transparent;color:var(--text2);font-family:'Rajdhani',sans-serif;font-weight:700">&#9888; Medium</button>
          <button onclick="selectDiff('hard')"   id="diff-hard"   class="diff-btn"                    style="flex:1;padding:6px;font-size:.7rem;border-radius:6px;cursor:pointer;border:2px solid var(--border2);background:transparent;color:var(--text2);font-family:'Rajdhani',sans-serif;font-weight:700">&#128683; Hard</button>
        </div>
      </div>
      <!-- Leader -->
      <div class="field" style="margin-bottom:.75rem">
        <label id="se-leader-label" style="font-size:.68rem">Squad Leader <span style="color:var(--text3)">(character name)</span></label>
        <input id="se-leader" type="text" list="se-unit-list" placeholder="e.g. Sith Eternal Emperor"
          autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
          style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                 padding:.45rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.9rem;width:100%;box-sizing:border-box">
      </div>
      <!-- Members -->
      <div class="field" style="margin-bottom:.75rem">
        <label id="se-members-label" style="font-size:.68rem">Other Members <span style="color:var(--text3)">(up to 4 unique units)</span></label>
        <div id="se-type-hint" style="font-size:.62rem;color:var(--text3);margin:.2rem 0 .35rem">Start typing to narrow the list. Units must be unique within a squad.</div>
        <div id="se-starting-label" style="display:none;font-size:.62rem;color:var(--gold);margin:.3rem 0 .25rem">Starting Ships (required)</div>
        <div id="se-slot-wrap-1" style="margin-bottom:6px">
          <div id="se-slot-label-1" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Member 2</div>
          <input id="se-m1" type="text" list="se-unit-list" placeholder="Member 2"
            autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
            style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
        <div id="se-slot-wrap-2" style="margin-bottom:6px">
          <div id="se-slot-label-2" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Member 3</div>
          <input id="se-m2" type="text" list="se-unit-list" placeholder="Member 3"
            autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
            style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
        <div id="se-slot-wrap-3" style="margin-bottom:6px">
          <div id="se-slot-label-3" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Member 4</div>
          <input id="se-m3" type="text" list="se-unit-list" placeholder="Member 4"
            autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
            style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
        <div id="se-reinforcement-label" style="display:none;font-size:.62rem;color:var(--text3);margin:.55rem 0 .25rem">Reinforcements (optional)</div>
        <div id="se-slot-wrap-4" style="margin-bottom:6px">
          <div id="se-slot-label-4" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Member 5</div>
          <input id="se-m4" type="text" list="se-unit-list" placeholder="Member 5"
            autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
            style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
        <div id="se-slot-wrap-5" style="display:none;margin-bottom:6px">
          <div id="se-slot-label-5" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Reinforcement 1</div>
          <input id="se-m5" type="text" list="se-unit-list" placeholder="Reinforcement 1"
            autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
            style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
        <div id="se-slot-wrap-6" style="display:none;margin-bottom:6px">
          <div id="se-slot-label-6" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Reinforcement 2</div>
          <input id="se-m6" type="text" list="se-unit-list" placeholder="Reinforcement 2"
            autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
            style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
      <div id="se-slot-wrap-7" style="display:none">
        <div id="se-slot-label-7" style="font-size:.62rem;color:var(--text3);margin-bottom:2px">Reinforcement 3</div>
        <input id="se-m7" type="text" list="se-unit-list" placeholder="Reinforcement 3"
          autocomplete="off" oninput="refreshSquadEditorSuggestions(this)" onfocus="refreshSquadEditorSuggestions(this)"
          style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                   padding:.4rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
        </div>
        <datalist id="se-unit-list"></datalist>
      </div>
      <!-- Territory Battle Omicrons -->
      <div class="field" id="se-omicron-wrap" style="display:none;margin-bottom:.75rem">
        <label id="se-omicron-label" style="font-size:.68rem">Required Territory Battle Omicrons</label>
        <div id="se-omicron-hint" style="font-size:.62rem;color:var(--text3);margin:.2rem 0 .4rem">
          Check the Territory Battle omicrons this squad needs to function as intended.
        </div>
        <div id="se-omicron-list" style="display:flex;flex-direction:column;gap:8px"></div>
      </div>
      <!-- Notes -->
      <div class="field" style="margin-bottom:.75rem">
        <label style="font-size:.68rem">Notes / Strategy</label>
        <textarea id="se-notes" placeholder="Strategy notes, tips, mod recommendations..."
          rows="3"
          style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                 padding:.45rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;
                 width:100%;box-sizing:border-box;resize:vertical"></textarea>
      </div>
      <!-- Video URL -->
      <div class="field" style="margin-bottom:1rem">
        <label style="font-size:.68rem">YouTube URL <span style="color:var(--text3)">(optional)</span></label>
        <input id="se-video" type="url" placeholder="https://youtube.com/watch?v=..."
          style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
                 padding:.45rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem;width:100%;box-sizing:border-box">
      </div>
      <!-- Buttons -->
      <div style="display:flex;gap:8px;justify-content:flex-end">
        <button onclick="closeSquadEditor()"
          style="font-size:.75rem;padding:6px 16px;border:1px solid var(--border2);background:transparent;
                 color:var(--text2);border-radius:var(--radius);cursor:pointer;font-family:'Rajdhani',sans-serif">
          Cancel
        </button>
        <button onclick="saveSquadEditor()"
          style="font-size:.75rem;padding:6px 16px;border:1px solid var(--gold2);background:var(--gold);
                 color:var(--bg);border-radius:var(--radius);cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:700">
          Save Squad
        </button>
      </div>
    </div>
  </div>
</div>

<div class="panel" id="panel-roster">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:1rem;flex-wrap:wrap">
    <div style="flex:1;min-width:200px">
      <select id="roster-member-sel" onchange="loadMemberRoster(this.value)"
        style="width:100%;background:var(--bg4);border:1px solid var(--border2);
               border-radius:var(--radius);padding:.4rem .65rem;color:var(--text);
               font-family:'Rajdhani',sans-serif;font-size:.9rem">
        <option value="">-- Select guild member --</option>
      </select>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <input id="roster-search" type="text" placeholder="Search units..."
        oninput="filterRoster()"
        style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
               padding:.38rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;
               font-size:.85rem;width:180px">
      <select id="roster-filter" onchange="filterRoster()"
        style="background:var(--bg4);border:1px solid var(--border2);border-radius:var(--radius);
               padding:.38rem .65rem;color:var(--text);font-family:'Rajdhani',sans-serif;font-size:.85rem">
        <option value="all">All Units</option>
        <option value="chars">Characters Only</option>
        <option value="ships">Ships Only</option>
        <option value="r5plus">R5+ Only</option>
        <option value="r7plus">R7+ Only</option>
        <option value="r9plus">R9+ Only</option>
        <option value="g12plus">G12+ Only</option>
      </select>
    </div>
    <div id="roster-summary" style="font-size:.72rem;color:var(--text2)"></div>
  </div>

  <!-- Sort bar -->
  <div id="roster-sort-bar" style="display:grid;grid-template-columns:1.7fr .8fr .7fr .8fr .9fr 3fr;
              gap:4px;padding:4px 8px;background:var(--bg2);border-radius:var(--radius);
              margin-bottom:4px;font-size:.62rem;letter-spacing:.06em;text-transform:uppercase;
              color:var(--text3)">
    <button onclick="sortRoster('name')"    id="rs-name"  class="roster-sort-btn">Character</button>
    <button onclick="sortRoster('type')"    id="rs-type"  class="roster-sort-btn">Type</button>
    <button onclick="sortRoster('stars')"   id="rs-stars" class="roster-sort-btn">★</button>
    <button onclick="sortRoster('level')"   id="rs-level" class="roster-sort-btn">Gear/Relic</button>
    <button onclick="sortRoster('power')"   id="rs-power" class="roster-sort-btn">Power</button>
    <span style="padding:2px 4px">Abilities</span>
  </div>

  <div id="roster-list"
    style="overflow-y:auto;max-height:calc(100vh - 260px)">
    <div style="color:var(--text3);font-size:.8rem;padding:2rem;text-align:center">
      Select a guild member above to view their roster.<br>
      <span style="font-size:.7rem">Run Scan Rosters first from the Guild Overview tab.</span>
    </div>
  </div>
</div>

<script>
// DATA
// ── Mission point values verified from swgoh.wiki + gaming-fans.com ──
// cmPts:    territory points per player per FULL CM completion (both waves)
// fleetPts: territory points per player per fleet mission completion
// opsVal:   territory points per filled ops platoon (same for all members)
// Sources: wiki tables (zones 1-2), gaming-fans walkthroughs (zones 3-6)
const DS_CHAIN = [
  {id:'mustafar',  name:'Mustafar',     align:'ds',zone:1,cms:4,fleets:1,sms:0,                                        cmPts:200000,  fleetPts:400000,  opsVal:10000000, stars:[116406250,186250000,248333333]},
  {id:'geonosis',  name:'Geonosis',     align:'ds',zone:2,cms:4,fleets:1,sms:0,                                        cmPts:250000,  fleetPts:500000,  opsVal:11000000, stars:[148125000,237000000,316000000]},
  {id:'dathomir',  name:'Dathomir',     align:'ds',zone:3,cms:4,fleets:0,sms:1,smLabel:'Special Mission',              cmPts:341250,  fleetPts:0,       opsVal:13200000, stars:[158960938,254337500,339116667]},
  {id:'medstation',name:'Med. Station', align:'ds',zone:4,cms:4,fleets:0,sms:1,smLabel:'Special Mission',              cmPts:493594,  fleetPts:0,       opsVal:18480000, stars:[235143105,400243583,500304479]},
  {id:'malachor',  name:'Malachor',     align:'ds',zone:5,cms:4,fleets:0,sms:0,                                        cmPts:721744,  fleetPts:0,       opsVal:33264000, stars:[341250768,620455942,729948167]},
  {id:'deathstar', name:'Death Star',   align:'ds',zone:6,cms:4,fleets:1,sms:0,                                        cmPts:1151719, fleetPts:2303438, opsVal:86486400, stars:[582632425,1059331682,1246272567]},
];
const MX_CHAIN = [
  {id:'corellia',name:'Corellia', align:'mx',zone:1,cms:3,fleets:1,sms:1,smLabel:'Special Mission',                   cmPts:200000,  fleetPts:400000,  opsVal:10000000, stars:[111718750,178750000,238333333]},
  {id:'felucia', name:'Felucia',  align:'mx',zone:2,cms:4,fleets:1,sms:0,                                             cmPts:250000,  fleetPts:500000,  opsVal:11000000, stars:[148125000,237000000,316000000]},
  {id:'tatooine',name:'Tatooine', align:'mx',zone:3,cms:3,fleets:1,sms:1,smLabel:'Unlock Mandalore Special Mission',smThreshold:25,smUnlocks:'mandalore', cmPts:341250, fleetPts:682500, opsVal:13200000, stars:[190953125,305525000,407366667]},
  {id:'kessel',  name:'Kessel',   align:'mx',zone:4,cms:3,fleets:1,sms:1,smLabel:'Special Mission',                   cmPts:493594,  fleetPts:987188,  opsVal:18480000, stars:[235143105,400243583,500304479]},
  {id:'vandor',  name:'Vandor',   align:'mx',zone:5,cms:3,fleets:1,sms:1,smLabel:'Special Mission',                   cmPts:721744,  fleetPts:1443488, opsVal:33264000, stars:[341250768,620455942,729948167]},
  {id:'hoth',    name:'Hoth',     align:'mx',zone:6,cms:4,fleets:1,sms:0,                                             cmPts:1151719, fleetPts:2303438, opsVal:86486400, stars:[582632425,1059331682,1246272567]},
];
const LS_CHAIN = [
  {id:'coruscant',name:'Coruscant', align:'ls',zone:1,cms:4,fleets:1,sms:0,                                           cmPts:200000,  fleetPts:400000,  opsVal:10000000, stars:[116406250,186250000,248333333]},
  {id:'bracca',   name:'Bracca',    align:'ls',zone:2,cms:3,fleets:1,sms:1,smLabel:'Bracca SM (→ Zeffo at 30)',smThreshold:30,smUnlocks:'zeffo', cmPts:250000, fleetPts:500000, opsVal:11000000, stars:[142265625,227625000,303500000]},
  {id:'kashyyyk', name:'Kashyyyk',  align:'ls',zone:3,cms:3,fleets:1,sms:1,smLabel:'Special Mission',                 cmPts:341250,  fleetPts:682500,  opsVal:13200000, stars:[190953125,305525000,407366667]},
  {id:'lothal',   name:'Lothal',    align:'ls',zone:4,cms:3,fleets:1,sms:0,                                           cmPts:493594,  fleetPts:987188,  opsVal:18480000, stars:[246742558,419987333,524984167]},
  {id:'kafrene',  name:'Kafrene',   align:'ls',zone:5,cms:4,fleets:1,sms:0,                                           cmPts:721744,  fleetPts:1443488, opsVal:33264000, stars:[341250768,620455942,729948167]},
  {id:'scarif',   name:'Scarif',    align:'ls',zone:6,cms:4,fleets:1,sms:0,                                           cmPts:1151719, fleetPts:2303438, opsVal:86486400, stars:[555710999,1010383635,1188686629]},
];
const BONUS_PLANETS = [
  {id:'mandalore',name:'Mandalore',align:'bonus',zone:4,cms:4,fleets:0,sms:0,                                         cmPts:493594,  fleetPts:0,       opsVal:18480000, stars:[197748650,316397840,396497300],unlockedBy:'tatooine',unlockedAt:25},
  {id:'zeffo',    name:'Zeffo',    align:'bonus',zone:3,cms:3,fleets:0,sms:1,smLabel:'Clone Trooper Special Mission', cmPts:341250,  fleetPts:682500,  opsVal:13200000, stars:[143589583,229743333,287179167],unlockedBy:'bracca',unlockedAt:30},
];
const ALL_PLANETS=[...DS_CHAIN,...MX_CHAIN,...LS_CHAIN,...BONUS_PLANETS];

// Key ROTE units for roster analysis (defId: display name, minRelic: minimum relic needed)

// ── Combat Mission database ───────────────────────────────────────────────
// Sources: Artoo's RoTE guide, starwars-fans.com, swgoh.wiki
// alignment: 'ds'=dark side, 'ls'=light side, 'mx'=mixed/any
// minRelic: minimum relic for ALL units in this CM
// requiredUnits: specific defIds that MUST be present (SMs)
// topTeams: community-recommended auto teams (faction/unit focused)
const ROTE_MISSIONS = {
  // ── PHASE 1 ──────────────────────────────────────────────────────────────
  mustafar: { zone:1, minRelic:5, cms:[
    {name:'CM 1 (B2s/Magnas)',   align:'ds', topTeams:['Inquisitorius','First Order','Sith','Dark Side GL']},
    {name:'CM 2 (Nute wave)',    align:'ds', topTeams:['Inquisitorius','SEE+Empire','First Order']},
    {name:'CM 3 (Geos wave)',    align:'ds', topTeams:['SLKR First Order','SEE+Wat','Empire']},
    {name:'CM 4 (Lord Vader)',   align:'ds', topTeams:['Inquisitorius'], requiredUnits:['LORDVADER'],
     note:'Lord Vader required'},
  ], sm:null},
  corellia: { zone:1, minRelic:5, cms:[
    {name:'CM 1 (Jabba)',        align:'mx', topTeams:['Jabba Hutt Crime','Bounty Hunters']},
    {name:'CM 2 (Open)',         align:'mx', topTeams:['JTR Resistance','Rey+Finn','Rogue One','Any strong team']},
    {name:'CM 3 (Open)',         align:'mx', topTeams:['Palpatine Empire','JTR','Jabba']},
  ], sm:{name:'Corellia SM',align:'mx',minRelic:5,topTeams:['Any mixed R5'],note:'Generic mixed SM'}},
  coruscant: { zone:1, minRelic:5, cms:[
    {name:'CM 1 (Jedi)',         align:'ls', topTeams:['JML+JKL Jedi','Mace Windu Jedi','Padme Jedi']},
    {name:'CM 2 (Mace)',         align:'ls', topTeams:['Mace+Fisto+JMK+KAM+GK','JML Jedi']},
    {name:'CM 3 (Bad Batch)',    align:'ls', topTeams:['Bad Batch','Mando Marauders','Rebel Fighters']},
    {name:'CM 4 (Open)',         align:'ls', topTeams:['Bad Batch','JTR+BB8','Mando Marauders']},
  ], sm:null},
  // ── PHASE 2 ──────────────────────────────────────────────────────────────
  geonosis: { zone:2, minRelic:6, cms:[
    {name:'CM 1 (Reek)',         align:'ds', topTeams:['SEE+Wat+GG+Nute+Jango','Inquisitorius']},
    {name:'CM 2 (Acklay)',       align:'ds', topTeams:['Inquisitorius (no GI)','GI lead Inquisitors']},
    {name:'CM 3 (Nexu)',         align:'ds', topTeams:['Lord Vader+Piett+Tarkin+Palp+Thrawn','Tarkin Empire']},
    {name:'CM 4 (Open)',         align:'ds', topTeams:['Sith','SEE+Empire','SLKR FO']},
  ], sm:null},
  felucia: { zone:2, minRelic:6, cms:[
    {name:'CM 1 (Hondo wave)',   align:'mx', topTeams:['GAS 501st','Rex Clone Troopers']},
    {name:'CM 2 (Jabba)',        align:'mx', topTeams:['Jabba Hutt Crime','BHs']},
    {name:'CM 3 (Open)',         align:'mx', topTeams:['Bounty Hunters','Hondo+BH','Mandalorian']},
    {name:'CM 4 (Open)',         align:'mx', topTeams:['Any strong mixed R6']},
  ], sm:null},
  bracca: { zone:2, minRelic:6, cms:[
    {name:'CM 1 (Jedi)',         align:'ls', topTeams:['JKL+JML+GMY+Bastila+Shaak Ti']},
    {name:'CM 2 (JTR)',          align:'ls', topTeams:['JTR+BB8+R2+C3PO+RH Finn','Rey+Resistance']},
    {name:'CM 3 (Open)',         align:'ls', topTeams:['Rey','Jedi','Rebel Fighters']},
  ], sm:{name:'Bracca SM → Zeffo (30 completions)',align:'ls',minRelic:7,
    requiredUnits:['JEDIKNIGHTCAL','CEREJUNDA'],
    topTeams:['Cal Kestis + Cere Junda team'],
    note:'Cal Kestis + Cere Junda required at R7'}},
  // ── PHASE 3 ──────────────────────────────────────────────────────────────
  dathomir: { zone:3, minRelic:7, cms:[
    {name:'CM 1 (Empire)',       align:'ds', topTeams:['Empire (Thrawn/Vader/Piett)']},
    {name:'CM 2 (Inq.)',         align:'ds', topTeams:['Inquisitorius GL lead']},
    {name:'CM 3 (Open DS)',      align:'ds', topTeams:['SEE','SLKR','LV Empire']},
    {name:'CM 4 (Open DS)',      align:'ds', topTeams:['Sith','Dark Side GL']},
  ], sm:{name:'Dathomir SM',align:'ds',minRelic:7,topTeams:['Dark Side R7'],note:'Generic DS SM'}},
  tatooine: { zone:3, minRelic:7, cms:[
    {name:'CM 1 (Fennec BH)',    align:'mx', topTeams:['Fennec+Bounty Hunters','Jabba BH']},
    {name:'CM 2 (Jabba)',        align:'mx', topTeams:['Jabba Hutt Crime','Jabba solo carry']},
    {name:'CM 3 (Rey/Padme)',    align:'mx', topTeams:['Rey+CAT+Padme+GK+AT','Padme Jedi']},
    {name:'CM 4 (Open)',         align:'mx', topTeams:['Any mixed R7','Executor+BH fleet']},
  ], sm:{name:'Krayt Dragon SM → Mandalore (25)',align:'mx',minRelic:5,
    requiredUnits:['QIRA','YOUNGHAN'],
    topTeams:['Qi\'ra + Young Han Solo team'],
    note:'Qi\'ra + Young Han Solo required (R5+)'}},
  kashyyyk: { zone:3, minRelic:7, cms:[
    {name:'CM 1 (Wookies)',      align:'ls', topTeams:['Saw Gerrera+Rebel Fighters','Rogue One']},
    {name:'CM 2 (Open LS)',      align:'ls', topTeams:['Rebel Fighters','Jedi','Bad Batch']},
    {name:'CM 3 (Open LS)',      align:'ls', topTeams:['Any LS R7','JML Jedi']},
  ], sm:{name:'Kashyyyk SM',align:'ls',minRelic:7,
    requiredUnits:['SAWGERRERA'],
    topTeams:['Saw Gerrera + Rebel Fighters (Cassian, K2SO, Jan Erso, Luthen)'],
    note:'Saw Gerrera + Rebel Fighters at R7'}},
  zeffo: { zone:3, minRelic:7, cms:[
    {name:'CM 1 (UFU Top)',      align:'ls', topTeams:['Rey+RJT+CLS+Cere+Cal Kestis']},
    {name:'CM 2 (UFU Mid)',      align:'mx', topTeams:['Unaligned Force Users R7']},
    {name:'CM 3 (LS)',           align:'ls', topTeams:['Cere+Cal Kestis Jedi']},
    {name:'CM 4 (Open)',         align:'mx', topTeams:['Any mixed R7']},
  ], sm:{name:'Zeffo SM',align:'ls',minRelic:7,
    requiredUnits:['JEDIKNIGHTCAL','CEREJUNDA'],
    topTeams:['Cal Kestis + Cere Junda'],note:'Cal+Cere required'}},
  // ── PHASE 4 ──────────────────────────────────────────────────────────────
  medstation: { zone:4, minRelic:7, cms:[
    {name:'CM 1 (DS)',           align:'ds', topTeams:['Empire','Sith','Dark Side GL']},
    {name:'CM 2 (DS)',           align:'ds', topTeams:['LV Empire','Inquisitorius']},
    {name:'CM 3 (DS)',           align:'ds', topTeams:['SEE','SLKR','Darth Vader']},
    {name:'CM 4 (DS)',           align:'ds', topTeams:['Any Dark Side R7']},
  ], sm:{name:'Med Station SM',align:'ds',minRelic:7,topTeams:['Dark Side R7']}},
  kessel: { zone:4, minRelic:7, cms:[
    {name:'CM 1 (MX)',           align:'mx', topTeams:['Jabba','BHs','Mixed R7']},
    {name:'CM 2 (MX)',           align:'mx', topTeams:['Any mixed R7']},
    {name:'CM 3 (MX)',           align:'mx', topTeams:['Any mixed R7']},
  ], sm:{name:'Kessel SM',align:'mx',minRelic:8,
    requiredUnits:['QIRA','L3_37'],
    topTeams:['Baylan Skoll+Shin Hati+Marrok+Qi\'ra+L3-37'],
    note:'Qi\'ra + L3-37 at R8+ required'}},
  lothal: { zone:4, minRelic:7, cms:[
    {name:'CM 1 (LS)',           align:'ls', topTeams:['Rebel Fighters','Jedi','Bad Batch']},
    {name:'CM 2 (LS)',           align:'ls', topTeams:['Any LS R7']},
    {name:'CM 3 (LS)',           align:'ls', topTeams:['Any LS R7']},
  ], sm:null},
  mandalore: { zone:4, minRelic:8, cms:[
    {name:'CM 1 (DTMG)',         align:'ds', topTeams:['Imperial Remnant at R8 (Moff Gideon lead)'],
     requiredUnits:['MOFFGIDEONS3'],note:'Dark Trooper Moff Gideon required'},
    {name:'CM 2 (DS)',           align:'ds', topTeams:['Imperial Remnant R8','Empire']},
    {name:'CM 3 (DS)',           align:'ds', topTeams:['Any DS R8']},
    {name:'CM 4 (DS)',           align:'ds', topTeams:['Any DS R8']},
  ], sm:null},
  // ── PHASE 5 ──────────────────────────────────────────────────────────────
  malachor: { zone:5, minRelic:7, cms:[
    {name:'CM 1',align:'ds',topTeams:['Any DS R7']},
    {name:'CM 2',align:'ds',topTeams:['Any DS R7']},
    {name:'CM 3',align:'ds',topTeams:['Any DS R7']},
    {name:'CM 4',align:'ds',topTeams:['Any DS R7']},
  ], sm:null},
  vandor: { zone:5, minRelic:7, cms:[
    {name:'CM 1',align:'mx',topTeams:['Any mixed R7']},
    {name:'CM 2',align:'mx',topTeams:['Any mixed R7']},
    {name:'CM 3',align:'mx',topTeams:['Any mixed R7']},
  ], sm:{name:'Vandor SM',align:'mx',minRelic:7,topTeams:['Mixed R7']}},
  kafrene: { zone:5, minRelic:7, cms:[
    {name:'CM 1',align:'ls',topTeams:['Any LS R7']},
    {name:'CM 2',align:'ls',topTeams:['Any LS R7']},
    {name:'CM 3',align:'ls',topTeams:['Any LS R7']},
    {name:'CM 4',align:'ls',topTeams:['Any LS R7']},
  ], sm:null},
  // ── PHASE 6 ──────────────────────────────────────────────────────────────
  deathstar: { zone:6, minRelic:9, cms:[
    {name:'CM 1 (Darth Vader)',  align:'ds', topTeams:['Darth Vader solo/lead R9+'],
     requiredUnits:['VADER'],note:'Darth Vader R9 required'},
    {name:'CM 2 (Iden Versio)',  align:'ds', topTeams:['Iden Versio+SLKR+Darth Malgus+Darth Malak+Sith Empire Trooper'],
     requiredUnits:['IDENVERSIOEMPIRE'],note:'Iden Versio + 4 DS R9'},
    {name:'CM 3 (DS)',           align:'ds', topTeams:['Any DS R9']},
    {name:'CM 4 (DS)',           align:'ds', topTeams:['Any DS R9']},
  ], sm:null},
  hoth: { zone:6, minRelic:9, cms:[
    {name:'CM 1',align:'mx',topTeams:['Any mixed R9']},
    {name:'CM 2',align:'mx',topTeams:['Any mixed R9']},
    {name:'CM 3',align:'mx',topTeams:['Any mixed R9']},
    {name:'CM 4',align:'mx',topTeams:['Any mixed R9']},
  ], sm:null},
  scarif: { zone:6, minRelic:9, cms:[
    {name:'CM 1',align:'ls',topTeams:['Rogue One R9','Any LS R9']},
    {name:'CM 2',align:'ls',topTeams:['Any LS R9']},
    {name:'CM 3',align:'ls',topTeams:['Any LS R9']},
    {name:'CM 4',align:'ls',topTeams:['Any LS R9']},
  ], sm:null},
};

// Specific units required for key missions (defId: display name)
const KEY_MISSION_UNITS = {
  LORDVADER:              'Lord Vader',
  VADER:                  'Darth Vader',
  IDENVERSIOEMPIRE:       'Iden Versio',
  JEDIKNIGHTCAL:          'Jedi Knight Cal Kestis',
  CEREJUNDA:              'Cere Junda',
  SAWGERRERA:             'Saw Gerrera',
  MANDALORBOKATAN:        'Bo-Katan (Mand\'alor)',
  THEMANDALORIANBESKARARMOR: 'The Mandalorian (Beskar Armor)',
  QIRA:                   'Qi\'ra',
  YOUNGHAN:               'Young Han Solo',
  L3_37:                  'L3-37',
  MOFFGIDEONS3:           'Dark Trooper Moff Gideon',
};

// Assess a single member's likelihood on a given mission
function assessMission(roster, pid, missionType){
  // missionType: 'cm' or 'sm'
  const planet = ROTE_MISSIONS[pid];
  if(!planet || !roster) return null;

  const mission = missionType==='sm' ? planet.sm : planet.cms[0]; // use first CM as baseline
  if(!mission) return {rating:'n/a', label:'No mission', color:'var(--text3)'};

  const minRelic = mission.minRelic || planet.minRelic;
  const requiredUnits = mission.requiredUnits || [];

  // Check specific required units
  const missingReq = requiredUnits.filter(defId=>{
    const u = roster.find(r=>unitMatchesDefId(r, defId));
    return !u || u.rarity<7 || u.relic<minRelic;
  });
  if(missingReq.length>0){
    const names = missingReq.map(d=>KEY_MISSION_UNITS[d]||d).join(', ');
    return {rating:'cannot', label:'Missing: '+names, color:'var(--ds)'};
  }

  // Count units at required relic (regardless of alignment — player knows their faction)
  const qualifying = roster.filter(u=>u.rarity===7 && u.relic>=minRelic).length;
  if(qualifying>=15) return {rating:'strong',  label:qualifying+' R'+minRelic+'+ units',  color:'var(--mx)'};
  if(qualifying>=10) return {rating:'good',    label:qualifying+' R'+minRelic+'+ units',  color:'#27ae60'};
  if(qualifying>=5)  return {rating:'ok',      label:qualifying+' R'+minRelic+'+ units',  color:'var(--gold2)'};
  if(qualifying>=3)  return {rating:'marginal',label:qualifying+'/5 R'+minRelic+'+ units',color:'#e67e22'};
  return                     {rating:'cannot', label:qualifying+'/5 R'+minRelic+'+ units',color:'var(--ds)'};
}

// Full member capability report across all planets
function buildMemberReport(ac){
  const roster = guildRosters[ac];
  if(!roster || roster.length===0) return null;

  const ALL=[...DS_CHAIN,...MX_CHAIN,...LS_CHAIN,...BONUS_PLANETS];
  return ALL.map(p=>{
    const planet = ROTE_MISSIONS[p.id];
    if(!planet) return {planetId:p.id, name:p.name, cms:[], sm:null};

    const minR = planet.minRelic;
    const qualifying = roster.filter(u=>u.rarity===7&&u.relic>=minR).length;
    const cmRating = qualifying>=5?'good':qualifying>=3?'marginal':'cannot';
    const cmColor  = qualifying>=5?'var(--mx)':qualifying>=3?'var(--gold2)':'var(--ds)';

    // SM check
    let smResult = null;
    if(planet.sm){
      smResult = assessMission(roster, p.id, 'sm');
    }

    return {
      planetId: p.id,
      name: p.name,
      align: p.align,
      zone: planet.zone,
      minRelic: minR,
      qualifying,
      cmRating, cmColor,
      cmLabel: qualifying+' R'+minR+'+ units',
      topTeams: planet.cms[0]?.topTeams||[],
      sm: smResult,
      smLabel: planet.sm?.name||null,
    };
  });
}

const KEY_UNITS = [
  {defId:'GRANDINQUISITOR',name:'Grand Inquisitor',relic:5},
  {defId:'LORDVADER',name:'Lord Vader',relic:5},
  {defId:'VADER',name:'Darth Vader',relic:5},
  {defId:'SEVENTHSISTER',name:'Seventh Sister',relic:5},
  {defId:'THIRDSISTER',name:'Third Sister',relic:5},
  {defId:'JYNERSO',name:'Jyn Erso',relic:5},
  {defId:'CASSIANANDOR',name:'Cassian Andor',relic:5},
  {defId:'K2SO',name:'K-2SO',relic:5},
  {defId:'MANDALORBOKATAN',name:'Bo-Katan (Mand\'alor)',relic:5},
  {defId:'THEMANDALORIANBESKARARMOR',name:'The Mandalorian (Beskar Armor)',relic:5},
  {defId:'JEDIKNIGHTCAL',name:'Jedi Knight Cal Kestis',relic:5},
  {defId:'CEREJUNDA',name:'Cere Junda',relic:5},
  {defId:'JABBATHEHUTT',name:'Jabba the Hutt',relic:5},
  {defId:'FENNECSHAND',name:'Fennec Shand',relic:5},
];

// Per-planet state
const pState={};
ALL_PLANETS.forEach(p=>{pState[p.id]={cmRateOverride:null,fleetRateOverride:null,cmCountOverride:null,fleetCountOverride:null,ops:[false,false,false,false,false,false],smReady:false,smCount:0,gpDeploy:0,preloaded:0};});
const dailyUndep=Array(6).fill(0);
let undepMode='pct',cmMode='pct';
let guildRosters={};  // allyCode -> simplified roster
const APP_STATE_VERSION = 5;
const NAV_TABS = ['setup','planner','dayplan','operations','guides','roster'];
const OPS_MEMBER_DAILY_CAP = 10;
const OPTIMIZER_ALGO_META = {
  greedy: {
    label: 'Greedy Enumeration',
    quality: '5/10 quality',
    complexity: '2/10 complexity',
    runtime: 'Short runtime',
    description: 'Follows the strongest immediate star gains first. Fastest option, but it can miss better long-range preload paths.'
  },
  sa: {
    label: 'Simulated Annealing',
    quality: '8/10 quality',
    complexity: '6/10 complexity',
    runtime: 'Medium runtime',
    description: 'Explores nearby plan variations and occasionally accepts weaker moves early so it can escape local traps.'
  },
  pso: {
    label: 'Particle Swarm',
    quality: '8/10 quality',
    complexity: '7/10 complexity',
    runtime: 'Medium-long runtime',
    description: 'Lets many candidate plans move together toward strong focus orders and preload patterns found across the search.'
  },
  ga: {
    label: 'Genetic Algorithm',
    quality: '9/10 quality',
    complexity: '8/10 complexity',
    runtime: 'Long runtime',
    description: 'Breeds high-performing plans across generations. Usually one of the strongest choices for balancing stars, focus, and preload value.'
  },
  adam: {
    label: 'Adam Optimizer',
    quality: '6/10 quality',
    complexity: '9/10 complexity',
    runtime: 'Very long runtime',
    description: 'Pushes the plan with gradient-like updates in a noisy discrete search space. Powerful when it lands well, but still the least predictable and slowest option here.'
  },
  all: {
    label: 'All Algorithms',
    quality: 'Comparison pass',
    complexity: '10/10 complexity',
    runtime: 'Extreme runtime',
    description: 'Runs every algorithm in sequence, then keeps the best final path. Highest confidence, longest wait.'
  }
};
let _opsDefinitions = {};
let _opsLoadPromise = null;
let _opsPoolByDefId = null;
let _opsDefinitionsSourceLabel = '';
let _lastPlanResult = null;
let _greedyGenomeCache = null;
let _saveStateTimer = null;
let _appStateHydrating = false;
let _optimizerWarningAccepted = false;
let _planDirty = false;
let _opsSelectedDay = 1;
let _opsSelectedPlanet = '';

function getAlgoMeta(key){
  return OPTIMIZER_ALGO_META[key] || {label:key || 'Unknown'};
}

function hasCompletedOptimization(){
  return !!(_lastPlanResult && Array.isArray(_lastPlanResult.days) && _lastPlanResult.days.length);
}

function canViewOperationsTab(){
  return hasCompletedOptimization() && !_planDirty;
}

function updateOperationsTabVisibility(){
  const tab = document.querySelector('.nav-tab[data-tab="operations"]');
  if(!tab) return;
  const visible = canViewOperationsTab();
  tab.hidden = !visible;
  if(!visible){
    tab.classList.remove('active');
    if(document.getElementById('panel-operations')?.classList.contains('active')){
      showTab('dayplan');
    }
  }
}

function renderDayPlanGuide(){
  const host = document.getElementById('dayplan-algo-guide');
  if(!host) return;
  const order = ['greedy','sa','pso','ga','adam','all'];
  host.innerHTML = order.map(key=>{
    const meta = getAlgoMeta(key);
    return '<div class="dayplan-algo-card">'
      + '<div class="dayplan-algo-title">'+meta.label+'</div>'
      + '<div class="dayplan-algo-desc">'+meta.description+'</div>'
      + '<div class="dayplan-algo-meta">'
      + '<span class="dayplan-algo-badge quality">'+meta.quality+'</span>'
      + '<span class="dayplan-algo-badge complexity">'+meta.complexity+'</span>'
      + '<span class="dayplan-algo-badge runtime">'+meta.runtime+'</span>'
      + '</div></div>';
  }).join('');
}

function updateDayPlanUiState(options={}){
  const preserveStatus = !!options.preserveStatus;
  const status = document.getElementById('opt-status-line');
  const sel = document.getElementById('algo-sel');
  const btn = document.getElementById('quick-plan-btn');
  const exportBtn = document.getElementById('export-plan-pdf-btn');
  const snapshotBtn = document.getElementById('export-plan-snapshot-btn');
  const warningBtn = document.getElementById('dayplan-warning-btn');
  const warningCard = document.getElementById('dayplan-warning-card');
  const confirmed = !!_optimizerWarningAccepted;
  const selected = String(sel?.value || '').trim();

  if(warningCard) warningCard.classList.toggle('confirmed', confirmed);
  if(warningBtn){
    warningBtn.disabled = confirmed;
    warningBtn.textContent = confirmed ? 'Warning Confirmed' : 'I Understand';
  }
  if(sel) sel.disabled = !confirmed || _optRunning;
  if(btn) btn.disabled = !confirmed || !selected || _optRunning;
  if(exportBtn) exportBtn.disabled = _optRunning || !hasCompletedOptimization();
  if(snapshotBtn) snapshotBtn.disabled = _optRunning || !hasCompletedOptimization();
  if(_optRunning || !status || preserveStatus) return;

  if(!confirmed){
    status.textContent = 'Review and confirm the optimizer warning above before choosing an algorithm.';
    return;
  }
  if(!selected){
    status.textContent = 'Choose an algorithm to enable the optimizer.';
    return;
  }
  if(_planDirty){
    status.textContent = 'Planner inputs changed after the last run. Select an algorithm and rerun to refresh the plan.';
    return;
  }
  if(hasCompletedOptimization()){
    status.textContent = 'Select an algorithm and click Run to refresh or compare the current saved plan.';
    return;
  }
  status.textContent = 'Select an algorithm and click Run to generate the optimal TB plan.';
}

function confirmOptimizerWarning(){
  if(_optimizerWarningAccepted) return;
  _optimizerWarningAccepted = true;
  updateDayPlanUiState();
  queueSaveAppState();
}

// COMLINK STATUS

// ── GUIDE SYSTEM ──────────────────────────────────────────────────────────────

// Planet → missions definition (editable labels can be overridden in guideData)
const PLANET_MISSIONS = {
  mustafar:   {phase:1,align:'ds',relic:5,name:'Mustafar', missions:[
    {id:'nute',  label:'Dark Side Combat 1', type:'cm',    pointsSingle:100000, points:200000, unitsText:'Dark Side'},
    {id:'wat',   label:'Dark Side Combat 2', type:'cm',    pointsSingle:100000, points:200000, unitsText:'Dark Side'},
    {id:'geo',   label:'Dark Side Combat 3', type:'cm',    pointsSingle:100000, points:200000, unitsText:'Dark Side'},
    {id:'lv',    label:'Lord Vader',         type:'cm',    pointsSingle:100000, points:200000, unitsText:'Dark Side, Lord Vader', req:['LORDVADER']},
    {id:'fleet', label:'Fleet',              type:'fleet', pointsSingle:400000, points:400000, unitsText:'Dark Side Fleet'},
  ]},
  corellia:   {phase:1,align:'mx',relic:5,name:'Corellia', missions:[
    {id:'combat', label:'Mixed Combat',            type:'cm',    pointsSingle:100000, points:200000, unitsText:'Mixed'},
    {id:'jabba',  label:'Jabba the Hutt',          type:'cm',    pointsSingle:100000, points:200000, unitsText:'Jabba the Hutt, Bounty Hunter, Smuggler, Hutt Cartel'},
    {id:'aphra',  label:'Doctor Aphra',            type:'cm',    pointsSingle:100000, points:200000, unitsText:'Doctor Aphra, Droids, Smuggler, Hutt Cartel'},
    {id:'fleet',  label:"Lando's Falcon Fleet",    type:'fleet', pointsSingle:400000, points:400000, unitsText:"Mixed Fleet, Lando's Millennium Falcon"},
    {id:'sm',     label:"Qi'ra + Young Han [SM]",  type:'sm',    req:['QIRA','YOUNGHAN'], unitsText:"Qi'ra, Young Han Solo", rewardText:'15 Mk III Guild Tokens'},
  ]},
  coruscant:  {phase:1,align:'ls',relic:5,name:'Coruscant', missions:[
    {id:'combat',  label:'Light Side Combat 1', type:'cm',    pointsSingle:100000, points:200000, unitsText:'Light Side'},
    {id:'combat2', label:'Light Side Combat 2', type:'cm',    pointsSingle:100000, points:200000, unitsText:'Light Side'},
    {id:'jedi',    label:'Jedi',                type:'cm',    pointsSingle:100000, points:200000, unitsText:'Jedi'},
    {id:'mace',    label:'Mace / Kit',          type:'cm',    pointsSingle:100000, points:200000, unitsText:'Jedi, Mace Windu, Kit Fisto', req:['MACEWINDU','KITFISTO']},
    {id:'fleet',   label:'Outrider Fleet',      type:'fleet', pointsSingle:400000, points:400000, unitsText:'Light Side Fleet, Outrider'},
  ]},
  geonosis:   {phase:2,align:'ds',relic:6,name:'Geonosis', missions:[
    {id:'reek',   label:'Dark Side Combat 1', type:'cm',    pointsSingle:125000, points:250000, unitsText:'Dark Side'},
    {id:'acklay', label:'Dark Side Combat 2', type:'cm',    pointsSingle:125000, points:250000, unitsText:'Dark Side'},
    {id:'nexu',   label:'Dark Side Combat 3', type:'cm',    pointsSingle:125000, points:250000, unitsText:'Dark Side'},
    {id:'combat', label:'Geonosians',         type:'cm',    pointsSingle:125000, points:250000, unitsText:'Dark Side, Geonosian'},
    {id:'fleet',  label:'Fleet',              type:'fleet', pointsSingle:500000, points:500000, unitsText:'Dark Side Fleet'},
  ]},
  felucia:    {phase:2,align:'mx',relic:6,name:'Felucia', missions:[
    {id:'combat', label:'Mixed Combat',      type:'cm',    pointsSingle:125000, points:250000, unitsText:'Mixed'},
    {id:'bh',     label:'Young Lando',       type:'cm',    pointsSingle:125000, points:250000, unitsText:'Young Lando Calrissian, Scoundrel, Smuggler'},
    {id:'jabba',  label:'Jabba the Hutt',    type:'cm',    pointsSingle:125000, points:250000, unitsText:'Jabba the Hutt, Bounty Hunter, Smuggler, Hutt Cartel'},
    {id:'hondo',  label:'Hondo [SM]',        type:'sm',    estimateGroup:'cm', pointsSingle:125000, points:250000, unitsText:'Hondo Ohnaka, Scoundrel, Smuggler, Bounty Hunter'},
    {id:'fleet',  label:'Fleet',             type:'fleet', pointsSingle:500000, points:500000, unitsText:'Mixed Fleet'},
  ]},
  bracca:     {phase:2,align:'ls',relic:6,name:'Bracca', missions:[
    {id:'jtr',   label:'Light Side Combat 1',  type:'cm',    pointsSingle:125000, points:250000, unitsText:'Light Side'},
    {id:'jedi',  label:'Jedi',                  type:'cm',    pointsSingle:125000, points:250000, unitsText:'Jedi'},
    {id:'open',  label:'Light Side Combat 2',   type:'cm',    pointsSingle:125000, points:250000, unitsText:'Light Side'},
    {id:'fleet', label:'Fleet',                 type:'fleet', pointsSingle:500000, points:500000, unitsText:'Light Side Fleet'},
    {id:'sm',    label:'Unlock Zeffo [SM]',     type:'sm',    relic:7, req:['JEDIKNIGHTCAL','CEREJUNDA'], unitsText:'Cere Junda, Jedi Knight Cal Kestis', rewardText:'15 Mk III Guild Tokens', unlocks:'zeffo'},
  ]},
  dathomir:   {phase:3,align:'ds',relic:7,name:'Dathomir', missions:[
    {id:'cm1', label:'Dark Side Combat 1', type:'cm', pointsSingle:162500, points:341250, unitsText:'Dark Side'},
    {id:'cm2', label:'Dark Side Combat 2', type:'cm', pointsSingle:162500, points:341250, unitsText:'Dark Side'},
    {id:'cm3', label:'Empire',             type:'cm', pointsSingle:162500, points:341250, unitsText:'Empire, Dark Side'},
    {id:'cm4', label:'Doctor Aphra',       type:'cm', pointsSingle:162500, points:341250, unitsText:'Doctor Aphra, Dark Side, Droids, Hutt Cartel'},
    {id:'sm',  label:'Merrin [SM]',        type:'sm', unitsText:'Nightsister, Merrin', rewardText:'Merrin shards'},
  ]},
  tatooine:   {phase:3,align:'mx',relic:7,name:'Tatooine', missions:[
    {id:'combat', label:'Mixed Combat',           type:'cm',    pointsSingle:162500, points:341250, unitsText:'Mixed'},
    {id:'jabba',  label:'Jabba the Hutt',         type:'cm',    pointsSingle:162500, points:341250, unitsText:'Jabba the Hutt, Bounty Hunter, Smuggler, Hutt Cartel'},
    {id:'fennec', label:'Fennec Shand',           type:'cm',    pointsSingle:162500, points:341250, unitsText:'Fennec Shand, Bounty Hunter, Smuggler, Hutt Cartel'},
    {id:'fleet',  label:'Executor Fleet',         type:'fleet', pointsSingle:682500, points:682500, unitsText:'Mixed Fleet, Executor'},
    {id:'rey',    label:'Third Sister [SM]',      type:'sm',    unitsText:'Inquisitorius, Third Sister', rewardText:'Third Sister shards'},
    {id:'sm',     label:'Unlock Mandalore [SM]',  type:'sm',    req:['MANDALORBOKATAN','THEMANDALORIANBESKARARMOR'], unitsText:"Bo-Katan (Mand'alor), The Mandalorian (Beskar Armor)", rewardText:'15 Mk III Guild Tokens', unlocks:'mandalore'},
  ]},
  kashyyyk:   {phase:3,align:'ls',relic:7,name:'Kashyyyk', missions:[
    {id:'wookies', label:'Wookiees',             type:'cm',    pointsSingle:162500, points:341250, unitsText:'Wookiee'},
    {id:'cm2',     label:'Light Side Combat 1',  type:'cm',    pointsSingle:162500, points:341250, unitsText:'Light Side'},
    {id:'cm3',     label:'Light Side Combat 2',  type:'cm',    pointsSingle:162500, points:341250, unitsText:'Light Side'},
    {id:'fleet',   label:'Profundity Fleet',     type:'fleet', pointsSingle:682500, points:682500, unitsText:'Light Side Fleet, Profundity'},
    {id:'sm',      label:'Saw Gerrera [SM]',     type:'sm',    req:['SAWGERRERA'], unitsText:'Rebel Fighter, Saw Gerrera', rewardText:'50 Mk II Guild Tokens'},
  ]},
  zeffo:      {phase:3,align:'ls',relic:7,name:'Zeffo (Bonus)', missions:[
    {id:'ufu_top', label:'UFU Combat 1',             type:'cm', pointsSingle:162500, points:341250, unitsText:'Unaligned Force User'},
    {id:'ufu_mid', label:'UFU Combat 2',             type:'cm', pointsSingle:162500, points:341250, unitsText:'Unaligned Force User'},
    {id:'cal',     label:'Jedi Knight Cal Kestis',   type:'cm', pointsSingle:487500, points:1023750, unitsText:'Jedi Knight Cal Kestis, Cere Junda, Light Side', req:['JEDIKNIGHTCAL','CEREJUNDA']},
    {id:'sm',      label:'Clone Trooper [SM]',       type:'sm', unitsText:'Clone Trooper', rewardText:'Special mission reward'},
  ]},
  medstation: {phase:4,align:'ds',relic:8,name:'Med Station', missions:[
    {id:'cm1', label:'Dark Side Combat 1',           type:'cm', pointsSingle:219375, points:493594, unitsText:'Dark Side'},
    {id:'cm2', label:'Dark Side Combat 2',           type:'cm', pointsSingle:219375, points:493594, unitsText:'Dark Side'},
    {id:'cm3', label:'Dark Side Combat 3',           type:'cm', pointsSingle:219375, points:493594, unitsText:'Dark Side'},
    {id:'cm4', label:'Dark Trooper Moff Gideon',     type:'cm', pointsSingle:219375, points:493594, unitsText:'Dark Trooper Moff Gideon, Imperial Remnant', req:['MOFFGIDEONS3']},
    {id:'sm',  label:'Great Mothers [SM]',           type:'sm', unitsText:'Night Trooper, Imperial Remnant, Great Mothers', rewardText:'Special mission reward'},
  ]},
  kessel:     {phase:4,align:'mx',relic:8,name:'Kessel', missions:[
    {id:'cm1',   label:'Mixed Combat 1',            type:'cm',    pointsSingle:219375, points:493594, unitsText:'Mixed'},
    {id:'cm2',   label:'Mixed Combat 2',            type:'cm',    pointsSingle:219375, points:493594, unitsText:'Mixed'},
    {id:'cm3',   label:'Hutt Cartel',               type:'cm',    pointsSingle:219375, points:493594, unitsText:'Hutt Cartel'},
    {id:'fleet', label:'Fleet',                     type:'fleet', pointsSingle:987188, points:987188, unitsText:'Mixed Fleet'},
    {id:'sm',    label:"Qi'ra + L3-37 [SM]",        type:'sm',    req:['QIRA','L3_37'], unitsText:"Qi'ra, L3-37", rewardText:'15 Mk III Guild Tokens'},
  ]},
  lothal:     {phase:4,align:'ls',relic:8,name:'Lothal', missions:[
    {id:'jmk',   label:'Jedi',                      type:'cm',    pointsSingle:219375, points:493594, unitsText:'Jedi'},
    {id:'cm2',   label:'Phoenix',                   type:'cm',    pointsSingle:219375, points:493594, unitsText:'Phoenix'},
    {id:'cm3',   label:'Light Side Combat',         type:'cm',    pointsSingle:219375, points:493594, unitsText:'Light Side'},
    {id:'fleet', label:'Fleet',                     type:'fleet', pointsSingle:987188, points:987188, unitsText:'Light Side Fleet'},
  ]},
  mandalore:  {phase:4,align:'ds',relic:8,name:'Mandalore (Bonus)', missions:[
    {id:'dtmg',  label:'Dark Trooper Moff Gideon',  type:'cm',    pointsSingle:219375, points:493594, unitsText:'Dark Trooper Moff Gideon, Imperial Remnant', req:['MOFFGIDEONS3']},
    {id:'cm2',   label:'Dark Side Combat 1',        type:'cm',    pointsSingle:219375, points:493594, unitsText:'Dark Side'},
    {id:'cm3',   label:'Dark Side Combat 2',        type:'cm',    pointsSingle:219375, points:493594, unitsText:'Dark Side'},
    {id:'cm4',   label:"Bo-Katan (Mand'alor)",      type:'cm',    relic:9, pointsSingle:658125, points:1480782, unitsText:"Bo-Katan (Mand'alor), Light Side, Mandalorian", req:['MANDALORBOKATAN']},
  ]},
  malachor:   {phase:5,align:'ds',relic:8,name:'Malachor', missions:[
    {id:'cm1', label:'Dark Side Combat 1',               type:'cm', pointsSingle:307125, points:721744, unitsText:'Dark Side'},
    {id:'cm2', label:'Dark Side Combat 2',               type:'cm', pointsSingle:307125, points:721744, unitsText:'Dark Side'},
    {id:'cm3', label:'Dark Side Combat 3',               type:'cm', pointsSingle:307125, points:721744, unitsText:'Dark Side'},
    {id:'cm4', label:'Eighth / Fifth / Seventh Sister',  type:'cm', pointsSingle:721744, points:721744, unitsText:'Eighth Brother, Fifth Brother, Seventh Sister'},
  ]},
  vandor:     {phase:5,align:'mx',relic:8,name:'Vandor', missions:[
    {id:'cm1',   label:'Mixed Combat 1',                  type:'cm',    pointsSingle:307125, points:721744, unitsText:'Mixed'},
    {id:'cm2',   label:'Mixed Combat 2',                  type:'cm',    pointsSingle:307125, points:721744, unitsText:'Mixed'},
    {id:'cm3',   label:'Jabba the Hutt',                  type:'cm',    pointsSingle:307125, points:721744, unitsText:'Jabba the Hutt, Hutt Cartel, Smuggler, Bounty Hunter'},
    {id:'fleet', label:'Fleet',                           type:'fleet', pointsSingle:1443488, points:1443488, unitsText:'Mixed Fleet'},
    {id:'sm',    label:'Young Han + Vandor Chewie [SM]',  type:'sm',    unitsText:'Young Han Solo, Vandor Chewbacca', rewardText:'Special mission reward'},
  ]},
  kafrene:    {phase:5,align:'ls',relic:8,name:'Kafrene', missions:[
    {id:'cm1',   label:'Light Side Combat 1',             type:'cm',    pointsSingle:307125, points:721744, unitsText:'Light Side'},
    {id:'cm2',   label:'Light Side Combat 2',             type:'cm',    pointsSingle:307125, points:721744, unitsText:'Light Side'},
    {id:'cm3',   label:'Light Side Combat 3',             type:'cm',    pointsSingle:307125, points:721744, unitsText:'Light Side'},
    {id:'cm4',   label:'Cassian Andor + K-2SO',           type:'cm',    pointsSingle:307125, points:721744, unitsText:'Cassian Andor, K-2SO, Rebel Fighter, Light Side, Rogue One', req:['CASSIANANDOR','K2SO']},
    {id:'fleet', label:'Fleet',                           type:'fleet', pointsSingle:1443488, points:1443488, unitsText:'Light Side Fleet'},
  ]},
  deathstar:  {phase:6,align:'ds',relic:9,name:'Death Star', missions:[
    {id:'cm3',   label:'Dark Side Combat 1',              type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Dark Side'},
    {id:'cm4',   label:'Dark Side Combat 2',              type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Dark Side'},
    {id:'dv',    label:'Darth Vader',                     type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Darth Vader, Dark Side', req:['VADER']},
    {id:'iden',  label:'Iden Versio',                     type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Iden Versio, Dark Side, Empire, Imperial Trooper', req:['IDENVERSIOEMPIRE']},
    {id:'fleet', label:'Fleet',                           type:'fleet', pointsSingle:2303438, points:2303438, unitsText:'Dark Side Fleet'},
  ]},
  hoth:       {phase:6,align:'mx',relic:9,name:'Hoth', missions:[
    {id:'cm1',   label:'Mixed Combat 1',                  type:'cm', pointsSingle:460668, points:1151719, unitsText:'Mixed'},
    {id:'cm2',   label:'Mixed Combat 2',                  type:'cm', pointsSingle:460668, points:1151719, unitsText:'Mixed'},
    {id:'cm3',   label:'Jabba the Hutt',                  type:'cm', pointsSingle:460668, points:1151719, unitsText:'Jabba the Hutt, Smuggler, Bounty Hunter, Hutt Cartel'},
    {id:'cm4',   label:'Doctor Aphra [SM]',               type:'sm', estimateGroup:'cm', pointsSingle:460668, points:1151719, unitsText:'Doctor Aphra, BT-1, 0-0-0'},
    {id:'fleet', label:'Fleet',                           type:'fleet', pointsSingle:2303438, points:2303438, unitsText:'Mixed Fleet'},
  ]},
  scarif:     {phase:6,align:'ls',relic:9,name:'Scarif', missions:[
    {id:'cm1',   label:'Light Side Combat 1',             type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Light Side'},
    {id:'cm2',   label:'Light Side Combat 2',             type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Light Side'},
    {id:'cm3',   label:'Baze / Chirrut / SRP',            type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Baze Malbus, Chirrut Imwe, Scarif Rebel Pathfinder, Light Side'},
    {id:'cm4',   label:'Cassian / Pao / K-2SO',           type:'cm',    pointsSingle:460668, points:1151719, unitsText:'Cassian Andor, Pao, K-2SO, Light Side'},
    {id:'fleet', label:'Fleet',                           type:'fleet', pointsSingle:2303438, points:2303438, unitsText:'Light Side Fleet'},
  ]},
};

function missionRelicRequirement(planet, mission){
  return Number(mission?.relic || planet?.relic || 0);
}

function missionEstimateGroup(mission){
  if(!mission) return 'none';
  if(mission.estimateGroup) return mission.estimateGroup;
  if(mission.type === 'fleet') return Number(mission.points || 0) > 0 ? 'fleet' : 'none';
  return Number(mission.points || 0) > 0 ? 'cm' : 'none';
}

function getPlanetMissionBuckets(pid){
  const planet = PLANET_MISSIONS[pid];
  const missions = Array.isArray(planet?.missions) ? planet.missions : [];
  return {
    all: missions,
    combat: missions.filter(m=>missionEstimateGroup(m)==='cm'),
    fleet: missions.filter(m=>missionEstimateGroup(m)==='fleet'),
    special: missions.filter(m=>m.type==='sm')
  };
}

function getPlanetMissionEstimateMeta(pid){
  const buckets = getPlanetMissionBuckets(pid);
  return {
    ...buckets,
    combatTotalPoints: buckets.combat.reduce((sum, mission)=>sum + (Number(mission.points) || 0), 0),
    fleetTotalPoints: buckets.fleet.reduce((sum, mission)=>sum + (Number(mission.points) || 0), 0),
    nonPointSpecial: buckets.special.filter(m=>missionEstimateGroup(m)==='none')
  };
}

function projectCombatMissionPoints(mission, expectedCompletions){
  const full = Number(mission?.points || 0);
  const single = Number(mission?.pointsSingle || 0) || full;
  if(full <= 0) return 0;
  if(single > 0 && single < full){
    const fullClears = Math.floor(expectedCompletions);
    const partial = (expectedCompletions - fullClears) >= 0.5 ? single : 0;
    return (fullClears * full) + partial;
  }
  return Math.round(expectedCompletions) * full;
}

function projectFleetMissionPoints(mission, expectedCompletions){
  const full = Number(mission?.points || 0);
  if(full <= 0) return 0;
  return Math.round(expectedCompletions) * full;
}

function formatGuideMissionReward(mission){
  if(!mission) return '';
  const full = Number(mission.points || 0);
  const single = Number(mission.pointsSingle || 0);
  if(full > 0){
    if(single > 0 && single !== full) return fmt(single)+' -> '+fmt(full)+' territory points per member';
    return fmt(full)+' territory points per member';
  }
  return mission.rewardText || '';
}

// Mutable guide data — squads[missionKey] = array of squad objects
let guideData = normalizeGuideData({version:1, squads:{}});
let _activeGuide = null; // {planetId, missionId}
let _editingSquad = null; // {planetId, missionId, squadId} or null for new
let _guideDiff = 'auto'; // current difficulty selector state
const GUIDE_TB_OMICRON_AREA = 7;
let _guideTbOmicronMap = {};
let _guideTbOmicronLoadPromise = null;
let _guideEditorTbOmicronSelections = new Set();

function _mKey(pid, mid){ return pid+'___'+mid; }
function _getSquads(pid, mid){ return guideData.squads[_mKey(pid,mid)] || []; }
function _setSquads(pid, mid, arr){
  guideData.squads[_mKey(pid,mid)] = (Array.isArray(arr) ? arr : []).map(normalizeGuideSquad);
  queueSaveAppState();
}

// Populate member dropdown from scanned rosters
function populateMemberDropdown(){
  const sel = document.getElementById('guide-member-sel');
  if(!sel) return;
  const acs = Object.keys(guildRosters);
  const memberData = document.getElementById('guild-name-display')?.dataset?.members;
  let nameMap = {};
  if(memberData){
    try{
      JSON.parse(memberData).forEach(m=>{
        const ac = m.allyCode||m.allycode||m.ally_code||m.playerId||m.memberExternalId;
        const nm = m.playerName||m.name||ac;
        if(ac) nameMap[String(ac)] = nm;
      });
    }catch(e){}
  }
  sel.innerHTML = '<option value="">-- Select member --</option>' +
    acs.map(ac=>'<option value="'+ac+'">'+escHtml(nameMap[ac]||ac)+'</option>').join('');

  if(_activeGuide) renderGuideMission(_activeGuide.pid, _activeGuide.mid);
}

// Render the left planet list
function renderGuidePlanetList(){
  const el = document.getElementById('guide-planet-list');
  if(!el) return;

  const phases = [1,2,3,4,5,6];
  const alignOrder = {ds:'Dark Side',mx:'Mixed',ls:'Light Side'};
  const alignColors = {ds:'var(--ds)',mx:'var(--mx)',ls:'var(--ls)'};
  const bonusPlanets = ['zeffo','mandalore'];

  let html = '';
  phases.forEach(ph=>{
    const planets = Object.entries(PLANET_MISSIONS)
      .filter(([,p])=>p.phase===ph)
      .sort((a,b)=>{
        const order = {ds:0,mx:1,ls:2};
        return (order[a[1].align]||0)-(order[b[1].align]||0);
      });

    html += '<div style="font-size:.58rem;letter-spacing:.1em;text-transform:uppercase;'+
      'color:var(--text3);padding:6px 10px 3px;margin-top:4px">Phase '+ph+'</div>';

    planets.forEach(([pid, planet])=>{
      const isBonus = bonusPlanets.includes(pid);
      const clr = alignColors[planet.align]||'var(--text)';
      const isExpanded = !!_expandedPlanets[pid];
      const squadCount = planet.missions.reduce((n,m)=>n+_getSquads(pid,m.id).length,0);
      const badge = squadCount>0
        ? '<span style="font-size:.58rem;background:var(--bg4);border-radius:10px;padding:1px 6px;'+
          'color:var(--gold)">'+squadCount+'</span>' : '';

      html += '<div style="padding:5px 10px;cursor:pointer;border-left:3px solid '+
        (isExpanded?'var(--gold2)':'transparent')+';'+
        'transition:all .15s" onmouseover="this.style.background=\'var(--bg4)\'"'+
        ' onmouseout="this.style.background=\'transparent\'"'+
        ' onclick="toggleGuidePlanet(\''+pid+'\')"'+
        ' id="gp-'+pid+'">';
      html += '<div style="display:flex;justify-content:space-between;align-items:center">';
      html += '<span style="font-size:.75rem;font-weight:600;color:'+clr+
        (isBonus?';font-style:italic':'')+'">'+(isBonus?'⊕ ':'')+escHtml(planet.name)+'</span>';
      html += badge;
      html += '</div></div>';

      // Mission rows (shown/hidden per planet toggle)
      html += '<div id="gm-'+pid+'" style="display:'+(isExpanded?'block':'none')+'">';
      planet.missions.forEach(m=>{
        const mSquads = _getSquads(pid, m.id);
        const typeIcon = m.type==='sm'?'★':m.type==='fleet'?'⚓':'⚔';
        const typeClr  = m.type==='sm'?'#c39bd3':m.type==='fleet'?'#5dade2':'var(--text2)';
        const isActive = _activeGuide&&_activeGuide.pid===pid&&_activeGuide.mid===m.id;

        html += '<div onclick="openGuideMission(\''+pid+'\',\''+m.id+'\')" '+
          'id="gmi-'+pid+'-'+m.id+'" '+
          'style="display:flex;justify-content:space-between;align-items:center;'+
          'padding:4px 10px 4px 22px;cursor:pointer;font-size:.72rem;transition:all .15s;'+
          (isActive?'background:var(--bg4);border-left:3px solid var(--gold2);':'')+'"'+
          ' onmouseover="this.style.background=\'var(--bg4)\'"'+
          ' onmouseout="this.style.background=\''+(isActive?'var(--bg4)':'transparent')+'\'">';
        html += '<span style="color:'+typeClr+'">'+typeIcon+'</span>';
        html += '<span style="flex:1;padding:0 6px;color:var(--text)">'+escHtml(m.label)+'</span>';
        html += '<span style="font-size:.62rem;color:var(--text3)">'+(mSquads.length||'')+'</span>';
        html += '<button onclick="event.stopPropagation();openSquadEditor(\''+pid+'\',\''+m.id+'\',null)" '+
          'title="Add squad" '+
          'style="margin-left:6px;background:transparent;border:1px solid var(--border2);color:var(--text2);'+
          'border-radius:4px;width:18px;height:18px;cursor:pointer;font-size:.7rem;line-height:1;padding:0">+</button>';
        html += '</div>';
      });
      html += '</div>';
    });
  });

  el.innerHTML = html;
}

let _expandedPlanets = {};
function toggleGuidePlanet(pid){
  _expandedPlanets[pid] = !_expandedPlanets[pid];
  const el = document.getElementById('gm-'+pid);
  const hdr = document.getElementById('gp-'+pid);
  if(!el) return;
  el.style.display = _expandedPlanets[pid] ? 'block' : 'none';
  if(hdr) hdr.style.borderLeftColor = _expandedPlanets[pid] ? 'var(--gold2)' : 'transparent';
  queueSaveAppState();
}

function openGuideMission(pid, mid){
  _activeGuide = {pid, mid};
  renderGuidePlanetList(); // refresh active state
  renderGuideMission(pid, mid);
  queueSaveAppState();
}

function renderGuideMission(pid, mid){
  const el = document.getElementById('guide-mission-panel');
  if(!el) return;

  const planet  = PLANET_MISSIONS[pid];
  const mission = planet?.missions.find(m=>m.id===mid);
  if(!planet||!mission){ el.innerHTML=''; return; }

  const squads = _getSquads(pid, mid);
  const alignClr = {ds:'var(--ds)',mx:'var(--mx)',ls:'var(--ls)'}[planet.align]||'var(--text)';
  const typeLabel = mission.unlocks
    ? 'Special Unlock Mission'
    : (mission.type==='sm' ? 'Special Mission' : mission.type==='fleet' ? 'Fleet Mission' : 'Combat Mission');
  const isFleetMission = mission.type === 'fleet';
  const missionRelic = missionRelicRequirement(planet, mission);
  const missionRequirementLabel = isFleetMission
    ? ('Phase '+planet.phase+' &middot; 7-star ships required')
    : ('Phase '+planet.phase+' &middot; R'+missionRelic+'+ required');

  // Member roster check helper
  const selectedAc = document.getElementById('guide-member-sel')?.value||'';
  const memberRoster = selectedAc ? guildRosters[selectedAc] : null;

  function checkRosterForSquad(squad){
    if(!memberRoster) return null; // no member selected
    const relic = missionRelic;
    const rawMembers = (squad.members||[]).slice(0, isFleetMission ? GUIDE_FLEET_MEMBER_INPUT_IDS.length : GUIDE_STANDARD_MEMBER_INPUT_IDS.length);
    const rawMemberDefIds = Array.isArray(squad.memberDefIds) ? squad.memberDefIds : [];
    const requiredTbOmicronMap = {};
    if(!isFleetMission){
      getGuideSquadTbOmicronRequirements(squad).forEach(req=>{
        const key = defIdKey(req.unitDefId);
        if(!key) return;
        if(!requiredTbOmicronMap[key]) requiredTbOmicronMap[key] = [];
        requiredTbOmicronMap[key].push(req);
      });
    }
    const entries = [];
    const leaderName = String(squad.leader||'').trim();
    const leaderDefId = normalizeDefId(squad.leaderDefId).toUpperCase();
    if(leaderName || rawMembers.length){
      entries.push({
        slot:'leader',
        label:isFleetMission ? 'Capital Ship' : 'Leader',
        name:leaderName,
        defId:leaderDefId,
        required:true
      });
    }

    if(isFleetMission){
      GUIDE_FLEET_STARTER_INPUT_IDS.forEach((id, idx)=>{
        entries.push({
          slot:'starter',
          label:'Starter '+(idx+1),
          name:String(rawMembers[idx]||'').trim(),
          defId:normalizeDefId(rawMemberDefIds[idx]).toUpperCase(),
          required:true
        });
      });
      GUIDE_FLEET_REINFORCEMENT_INPUT_IDS.forEach((id, offset)=>{
        const idx = offset + GUIDE_FLEET_STARTER_INPUT_IDS.length;
        const name = String(rawMembers[idx]||'').trim();
        if(!name) return;
        entries.push({
          slot:'reinforcement',
          label:'Reinforcement '+(offset+1),
          name,
          defId:normalizeDefId(rawMemberDefIds[idx]).toUpperCase(),
          required:false
        });
      });
    } else {
      rawMembers.forEach((name, idx)=>{
        const trimmed = String(name||'').trim();
        if(!trimmed) return;
        entries.push({
          slot:'member',
          label:'Member '+(idx+1),
          name:trimmed,
          defId:normalizeDefId(rawMemberDefIds[idx]).toUpperCase(),
          required:true
        });
      });
    }

    if(!entries.length) return null; // empty squad, no check

    const results = entries.map(entry=>{
      if(!entry.name){
        return {
          ...entry,
          ok:false,
          reason:isFleetMission ? 'No ship assigned' : 'No unit assigned'
        };
      }
      if(isFleetMission && entry.slot === 'leader' && !_isCapitalShipRef(entry.defId || entry.name)){
        return {...entry, ok:false, reason:'Not a capital ship'};
      }
      if(isFleetMission && entry.slot !== 'leader' && _isCapitalShipRef(entry.defId || entry.name)){
        return {...entry, ok:false, reason:'Capital ships can only be leaders'};
      }
      const ru = findRosterUnitByRef(memberRoster, entry.name, entry.defId);
      if(!ru) return {...entry, ok:false, reason:'Not in roster'};
      if(Number(ru.rarity)<7) return {...entry, ok:false, reason:'Not 7-star'};
      if(!isFleetMission && Number(ru.relic)<relic) return {
        ...entry,
        ok:false,
        reason:'R'+(ru.relic||0)+' (need R'+relic+')'
      };
      if(!isFleetMission){
        const omicronReqs = requiredTbOmicronMap[defIdKey(entry.defId || ru.defId || entry.name)] || [];
        if(omicronReqs.length){
          const unlockedTbOmicronKeys = new Set(
            (ru.skills || [])
              .filter(skill=>skill && skill.hasOmicron && Number(skill.omicronArea || 0) === GUIDE_TB_OMICRON_AREA)
              .map(skill=>normalizeGuideSkillKey(skill.skillId || skill.id))
              .filter(Boolean)
          );
          const missingOmicrons = omicronReqs.filter(req=>
            !unlockedTbOmicronKeys.has(normalizeGuideSkillKey(req.skillId))
          );
          if(missingOmicrons.length){
            return {
              ...entry,
              ok:false,
              reason:'Missing TB omicron: '+missingOmicrons.map(req=>req.skillName || req.skillId).join(', ')
            };
          }
          return {
            ...entry,
            ok:true,
            reason:'R'+ru.relic+' | TB omi ready'
          };
        }
      }
      return {
        ...entry,
        ok:true,
        reason:isFleetMission ? '7-star ready' : ('R'+ru.relic)
      };
    });

    const allOk = results.every(r=>r.ok);
    const failCount = results.filter(r=>!r.ok).length;
    const tip = results.map(r=>{
      const nameText = r.name ? (' - '+r.name) : '';
      return (r.ok?'✓ ':'✗ ')+r.label+nameText+' ('+r.reason+')';
    }).join('\n');
    return {ok:allOk, reason:tip, results, failCount};
  }

  const diffStyles = {
    auto:   {bg:'rgba(39,174,96,.15)',  border:'#27ae60', dot:'#2ecc71', label:'Auto'},
    easy:   {bg:'rgba(52,152,219,.15)', border:'#2980b9', dot:'#3498db', label:'Easy'},
    medium: {bg:'rgba(241,196,15,.15)', border:'#d4ac0d', dot:'#f1c40f', label:'Medium'},
    hard:   {bg:'rgba(192,57,43,.15)',  border:'#922b21', dot:'#e74c3c', label:'Hard'},
  };

  let html = '';
  // Header
  html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:1rem">';
  html += '<div>';
  html += '<div style="font-family:\'Orbitron\',monospace;font-size:.85rem;letter-spacing:.06em;color:var(--text)">'+
    escHtml(planet.name)+' — '+escHtml(mission.label)+'</div>';
  html += '<div style="font-size:.65rem;color:'+alignClr+';margin-top:2px">'+typeLabel+' &middot; '+missionRequirementLabel+'</div>';
  if(mission.unitsText){
    html += '<div style="font-size:.72rem;color:var(--text2);margin-top:6px">Allowed / required units: <span style="color:var(--text)">'+escHtml(mission.unitsText)+'</span></div>';
  }
  const rewardSummary = formatGuideMissionReward(mission);
  if(rewardSummary){
    html += '<div style="font-size:.7rem;color:var(--text2);margin-top:3px">Mission reward: <span style="color:var(--text)">'+escHtml(rewardSummary)+'</span></div>';
  }
  html += '</div>';
  html += '<button onclick="openSquadEditor(\''+pid+'\',\''+mid+'\',null)" '+
    'style="font-size:.7rem;padding:5px 14px;border:1px solid var(--gold2);background:var(--gold);'+
    'color:var(--bg);border-radius:var(--radius);cursor:pointer;font-family:\'Rajdhani\',sans-serif;font-weight:700;white-space:nowrap">'+
    '+ Add Squad</button>';
  html += '</div>';

  if(squads.length===0){
    html += '<div style="color:var(--text3);font-size:.8rem;padding:1rem 0;text-align:center">'+
      'No squads yet. Click <b>+ Add Squad</b> to create the first one.</div>';
  } else {
    squads.forEach((squad, idx)=>{
      const ds = diffStyles[squad.difficulty||'auto'];
      const rCheck = checkRosterForSquad(squad);
      // Overall pass/fail icon in header
      const checkIcon = rCheck===null ? '' :
        rCheck.ok
          ? '<span title="'+escHtml(rCheck.reason)+'" style="color:#2ecc71;font-size:.85rem;cursor:help">&#10003; Ready</span>'
          : '<span title="'+escHtml(rCheck.reason)+'" style="color:#e74c3c;font-size:.85rem;cursor:help">&#10007; '+rCheck.failCount+' missing</span>';

      const members = (squad.members||[]).slice(0, isFleetMission ? GUIDE_FLEET_MEMBER_INPUT_IDS.length : GUIDE_STANDARD_MEMBER_INPUT_IDS.length);
      const squadId = squad.id;
      const resultList = Array.isArray(rCheck?.results) ? rCheck.results : [];
      const leaderResult = resultList.find(r=>r.slot==='leader') || null;
      const starterResults = resultList.filter(r=>r.slot==='starter');
      const reinforcementResults = resultList.filter(r=>r.slot==='reinforcement');
      const memberResults = resultList.filter(r=>r.slot==='member');

      function renderGuideUnitResult(result, fallbackName){
        if(!result){
          return '<span style="color:var(--text3)">'+escHtml(fallbackName || 'Unassigned')+'</span>';
        }
        const clr = result.ok ? '#2ecc71' : '#e74c3c';
        const icon = result.ok ? '✓' : '✗';
        const text = result.name || 'Missing assignment';
        return '<span title="'+escHtml(result.reason)+'" style="color:'+clr+';cursor:help">'+icon+' '+escHtml(result.label)+': '+escHtml(text)+'</span>';
      }

      html += '<div style="margin-bottom:10px;border:1px solid '+ds.border+';border-radius:8px;'+
        'background:'+ds.bg+';overflow:hidden">';

      // Squad header (always visible)
      html += '<div style="display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer" '+
        'onclick="toggleSquad(\'sq-body-'+squadId+'\')">';
      html += '<span style="width:10px;height:10px;border-radius:50%;background:'+ds.dot+';flex-shrink:0"></span>';
      html += '<span style="font-size:.8rem;font-weight:700;color:var(--text);flex:1">'+escHtml(squad.leader||'Unknown Leader')+'</span>';
      html += '<span style="font-size:.62rem;color:'+ds.dot+'">'+ds.label+'</span>';
      html += checkIcon;
      html += '<span style="color:var(--text3);font-size:.75rem">&#9660;</span>';
      html += '</div>';

      // Squad body (collapsible)
      html += '<div id="sq-body-'+squadId+'" style="display:none;border-top:1px solid '+ds.border+';padding:8px 10px">';
      if(squad.leader){
        html += '<div style="font-size:.72rem;color:var(--text2);margin-bottom:4px">'+
          '<span style="color:var(--text3)">'+(isFleetMission ? 'Capital: ' : 'Leader: ')+'</span>'+
          (rCheck ? renderGuideUnitResult(leaderResult, squad.leader) : '<span>'+escHtml(squad.leader)+'</span>')+
          '</div>';
      }
      if(isFleetMission){
        const starterFallbacks = GUIDE_FLEET_STARTER_INPUT_IDS.map((id, idx)=>String(members[idx]||'').trim()).filter((name, idx)=>name || starterResults[idx]);
        if(starterFallbacks.length || starterResults.length){
          const starterHtml = (starterResults.length ? starterResults : starterFallbacks.map((name, idx)=>({label:'Starter '+(idx+1), name})))
            .map((entry, idx)=>rCheck ? renderGuideUnitResult(entry, starterFallbacks[idx]) : '<span>'+escHtml(entry.name || ('Starter '+(idx+1)))+'</span>')
            .join(', ');
          html += '<div style="font-size:.72rem;color:var(--text2);margin-bottom:4px">'+
            '<span style="color:var(--text3)">Starting: </span>'+starterHtml+'</div>';
        }
        if(reinforcementResults.length || members.slice(3).some(name=>String(name||'').trim())){
          const reinforcementFallbacks = members.slice(3).map(name=>String(name||'').trim()).filter(Boolean);
          const reinforcementHtml = (rCheck ? reinforcementResults : reinforcementFallbacks.map((name, idx)=>({label:'Reinforcement '+(idx+1), name})))
            .map((entry, idx)=>rCheck ? renderGuideUnitResult(entry, reinforcementFallbacks[idx]) : '<span>'+escHtml(entry.name)+'</span>')
            .join(', ');
          if(reinforcementHtml){
            html += '<div style="font-size:.72rem;color:var(--text2);margin-bottom:4px">'+
              '<span style="color:var(--text3)">Reinforcements: </span>'+reinforcementHtml+'</div>';
          }
        }
      } else if(members.length){
        const memberHtml = (rCheck ? memberResults : members.filter(name=>String(name||'').trim()).map((name, idx)=>({label:'Member '+(idx+1), name})))
          .map((entry, idx)=>rCheck ? renderGuideUnitResult(entry, members[idx]) : '<span>'+escHtml(entry.name)+'</span>')
          .join(', ');
        html += '<div style="font-size:.72rem;color:var(--text2);margin-bottom:4px">'+
          '<span style="color:var(--text3)">Members: </span>'+memberHtml+'</div>';
      }
      if(squad.notes){
        html += '<div style="font-size:.72rem;color:var(--text2);margin-bottom:4px">'+
          '<span style="color:var(--text3)">Notes: </span>'+escHtml(squad.notes)+'</div>';
      }
      const requiredTbOmicrons = getGuideSquadTbOmicronRequirements(squad);
      if(requiredTbOmicrons.length){
        const byUnit = {};
        requiredTbOmicrons.forEach(req=>{
          const unitLabel = req.unitName || defIdToName(req.unitDefId, '');
          if(!byUnit[unitLabel]) byUnit[unitLabel] = [];
          byUnit[unitLabel].push(req.skillName || req.skillId);
        });
        const omicronText = Object.entries(byUnit)
          .map(([unitName, skills])=>unitName + ': ' + skills.join(', '))
          .join(' | ');
        html += '<div style="font-size:.72rem;color:var(--text2);margin-bottom:4px">'+
          '<span style="color:var(--text3)">TB Omicrons: </span>'+escHtml(omicronText)+'</div>';
      }
      const watchUrl = normalizeExternalUrl(squad.videoUrl);
      if(watchUrl){
        html += '<div style="margin-bottom:4px">'+
          '<a href="'+escHtml(watchUrl)+'" target="_blank" rel="noopener noreferrer" '+
          'style="font-size:.7rem;color:var(--gold);text-decoration:none">&#9654; Watch Video</a></div>';
      }
      // Controls
      html += '<div style="display:flex;gap:6px;margin-top:8px;justify-content:flex-end">';
      if(idx>0) html += '<button onclick="moveSquad(\''+pid+'\',\''+mid+'\','+idx+',-1)" title="Move up" '+
        'style="font-size:.65rem;padding:2px 8px;border:1px solid var(--border2);background:transparent;'+
        'color:var(--text2);border-radius:4px;cursor:pointer">&#8593;</button>';
      if(idx<squads.length-1) html += '<button onclick="moveSquad(\''+pid+'\',\''+mid+'\','+idx+',1)" title="Move down" '+
        'style="font-size:.65rem;padding:2px 8px;border:1px solid var(--border2);background:transparent;'+
        'color:var(--text2);border-radius:4px;cursor:pointer">&#8595;</button>';
      html += '<button onclick="openSquadEditor(\''+pid+'\',\''+mid+'\',\''+squadId+'\')" '+
        'style="font-size:.65rem;padding:2px 8px;border:1px solid var(--border2);background:transparent;'+
        'color:var(--text2);border-radius:4px;cursor:pointer">Edit</button>';
      html += '<button onclick="deleteSquad(\''+pid+'\',\''+mid+'\',\''+squadId+'\')" '+
        'style="font-size:.65rem;padding:2px 8px;border:1px solid var(--ds-dim);background:transparent;'+
        'color:var(--ds);border-radius:4px;cursor:pointer">Delete</button>';
      html += '</div>';
      html += '</div></div>';
    });
  }

  el.innerHTML = html;
}

function toggleSquad(id){
  const el = document.getElementById(id);
  if(!el) return;
  el.style.display = el.style.display==='none' ? 'block' : 'none';
}

function updateGuideChecks(){
  if(_activeGuide) renderGuideMission(_activeGuide.pid, _activeGuide.mid);
  queueSaveAppState();
}

// ── Squad CRUD ────────────────────────────────────────────────────────────────

function _getGuideMissionMeta(pid, mid){
  return PLANET_MISSIONS?.[pid]?.missions?.find(m=>m.id===mid) || null;
}

function _getGuideMissionUnitGroup(pid, mid){
  const mission = _getGuideMissionMeta(pid, mid);
  return mission?.type === 'fleet' ? 'ships' : 'chars';
}

const GUIDE_STANDARD_MEMBER_INPUT_IDS = ['se-m1','se-m2','se-m3','se-m4'];
const GUIDE_FLEET_MEMBER_INPUT_IDS = ['se-m1','se-m2','se-m3','se-m4','se-m5','se-m6','se-m7'];
const GUIDE_FLEET_STARTER_INPUT_IDS = ['se-m1','se-m2','se-m3'];
const GUIDE_FLEET_REINFORCEMENT_INPUT_IDS = ['se-m4','se-m5','se-m6','se-m7'];
const CAPITAL_SHIP_DEFIDS = new Set([
  'CAPITALCHIMAERA','CHIMAERA',
  'CAPITALEXECUTOR','EXECUTOR',
  'CAPITALEXECUTRIX','EXECUTRIX',
  'CAPITALFINALIZER','FINALIZER',
  'CAPITALJEDICRUISER','ENDURANCE',
  'CAPITALLEVIATHAN','LEVIATHAN',
  'CAPITALMALEVOLENCE','MALEVOLENCE',
  'CAPITALMONCALAMARICRUISER','HOMEONE',
  'CAPITALNEGOTIATOR','NEGOTIATOR',
  'CAPITALPROFUNDITY','PROFUNDITY',
  'CAPITALRADDUS','RADDUS',
  'CAPITALSTARDESTROYER','EXECUTRIX'
].map(defIdKey));

function _isGuideFleetMission(pid, mid){
  return _getGuideMissionMeta(pid, mid)?.type === 'fleet';
}

function _getGuideEditorMemberInputIds(pid, mid){
  return _isGuideFleetMission(pid, mid) ? GUIDE_FLEET_MEMBER_INPUT_IDS : GUIDE_STANDARD_MEMBER_INPUT_IDS;
}

function _guideUnitSelectionKey(name, defId=''){
  const resolvedDefId = normalizeDefId(defId || resolveUnitNameToDefId(name)).toUpperCase();
  if(resolvedDefId) return 'DEF:'+resolvedDefId;
  const normalizedName = normalizeUnitName(name);
  return normalizedName ? ('NAME:'+normalizedName) : '';
}

function _isCapitalShipRef(nameOrDefId){
  const key = defIdKey(resolveUnitNameToDefId(nameOrDefId) || nameOrDefId);
  return CAPITAL_SHIP_DEFIDS.has(key);
}

function normalizeGuideSkillKey(skillId){
  return defIdKey(skillId);
}

function normalizeGuideTbOmicronRequirement(entry){
  const source = (entry && typeof entry === 'object') ? entry : {};
  const unitDefId = normalizeDefId(
    source.unitDefId ||
    source.defId ||
    source.unitId ||
    source.characterDefId ||
    source.ownerDefId
  ).toUpperCase();
  const skillId = normalizeDefId(
    source.skillId ||
    source.abilityId ||
    source.id
  ).toUpperCase();
  if(!unitDefId || !skillId) return null;
  const unitName = String(
    source.unitName ||
    source.characterName ||
    source.ownerName ||
    defIdToName(unitDefId, '')
  ).trim();
  const skillName = String(source.skillName || source.name || skillId).trim();
  return {
    unitDefId,
    unitName: unitName || defIdToName(unitDefId, ''),
    skillId,
    skillName: skillName || skillId,
  };
}

function getGuideSquadTbOmicronRequirements(squad){
  return Array.isArray(squad?.requiredTbOmicrons)
    ? squad.requiredTbOmicrons.map(normalizeGuideTbOmicronRequirement).filter(Boolean)
    : [];
}

function syncGuideEditorTbOmicronSelectionsFromDom(){
  const inputs = Array.from(document.querySelectorAll('#se-omicron-list input[data-guide-omicron="1"]'));
  if(inputs.length){
    _guideEditorTbOmicronSelections = new Set(
      inputs
        .filter(input=>input.checked)
        .map(input=>normalizeGuideSkillKey(input.dataset.skillId || input.value))
        .filter(Boolean)
    );
  }
  return _guideEditorTbOmicronSelections;
}

function toggleGuideTbOmicronSelection(input){
  const key = normalizeGuideSkillKey(input?.dataset?.skillId || input?.value);
  if(!key) return;
  if(input.checked) _guideEditorTbOmicronSelections.add(key);
  else _guideEditorTbOmicronSelections.delete(key);
}

function collectGuideEditorCharacterUnits(){
  if(!_editingSquad) return [];
  const ids = ['se-leader'].concat(_getGuideEditorMemberInputIds(_editingSquad.pid, _editingSquad.mid));
  const seen = new Set();
  const units = [];
  ids.forEach(id=>{
    const value = String(document.getElementById(id)?.value || '').trim();
    const defId = normalizeDefId(resolveUnitNameToDefId(value)).toUpperCase();
    if(!defId || seen.has(defIdKey(defId))) return;
    if(inferUnitCombatType({defId}) === 2) return;
    seen.add(defIdKey(defId));
    units.push({defId, name:value || defIdToName(defId, '')});
  });
  return units;
}

async function ensureGuideTbOmicronMap(force=false){
  if(!force && Object.keys(_guideTbOmicronMap || {}).length) return _guideTbOmicronMap;
  if(_guideTbOmicronLoadPromise && !force) return _guideTbOmicronLoadPromise;
  _guideTbOmicronLoadPromise = fetch('/api/guide-tb-omicrons', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:'{}'
  }).then(resp=>resp.json())
    .then(data=>{
      if(data?.status === 'ok' && data.units && typeof data.units === 'object'){
        _guideTbOmicronMap = data.units;
      }
      return _guideTbOmicronMap;
    })
    .catch(err=>{
      console.warn('[ROTE] TB omicron metadata unavailable:', err.message);
      return _guideTbOmicronMap;
    })
    .finally(()=>{
      _guideTbOmicronLoadPromise = null;
      renderGuideTbOmicronOptions();
    });
  return _guideTbOmicronLoadPromise;
}

function renderGuideTbOmicronOptions(){
  const wrap = document.getElementById('se-omicron-wrap');
  const list = document.getElementById('se-omicron-list');
  const hint = document.getElementById('se-omicron-hint');
  if(!wrap || !list || !_editingSquad) return;

  if(_getGuideMissionUnitGroup(_editingSquad.pid, _editingSquad.mid) === 'ships'){
    wrap.style.display = 'none';
    list.innerHTML = '';
    return;
  }

  syncGuideEditorTbOmicronSelectionsFromDom();
  const units = collectGuideEditorCharacterUnits();
  if(!units.length){
    wrap.style.display = 'none';
    list.innerHTML = '';
    return;
  }

  if(!Object.keys(_guideTbOmicronMap || {}).length && _guideTbOmicronLoadPromise){
    wrap.style.display = 'block';
    hint.textContent = 'Loading Territory Battle omicron data...';
    list.innerHTML = '<div style="font-size:.72rem;color:var(--text3)">Checking available Territory Battle omicrons for the selected units...</div>';
    return;
  }

  const sections = [];
  const visibleKeys = new Set();
  units.forEach(unit=>{
    const abilities = Array.isArray(_guideTbOmicronMap?.[normalizeDefId(unit.defId).toUpperCase()])
      ? _guideTbOmicronMap[normalizeDefId(unit.defId).toUpperCase()]
      : [];
    if(!abilities.length) return;
    const rows = abilities.map(ability=>{
      const skillKey = normalizeGuideSkillKey(ability.skillId);
      if(!skillKey) return '';
      visibleKeys.add(skillKey);
      return '<label style="display:flex;align-items:flex-start;gap:8px;padding:7px 9px;border:1px solid var(--border2);border-radius:8px;background:rgba(255,255,255,.02);cursor:pointer">'
        + '<input type="checkbox" data-guide-omicron="1" data-skill-id="'+escHtml(ability.skillId)+'" data-skill-name="'+escHtml(ability.name || ability.skillId)+'" data-unit-defid="'+escHtml(unit.defId)+'" data-unit-name="'+escHtml(unit.name)+'" '
        + (_guideEditorTbOmicronSelections.has(skillKey) ? 'checked ' : '')
        + 'onchange="toggleGuideTbOmicronSelection(this)" style="margin-top:2px">'
        + '<div>'
        + '<div style="font-size:.76rem;color:var(--text);font-weight:600">'+escHtml(ability.name || ability.skillId)+'</div>'
        + '<div style="font-size:.62rem;color:var(--text3)">Territory Battle omicron on '+escHtml(unit.name)+'</div>'
        + '</div></label>';
    }).filter(Boolean).join('');
    if(rows){
      sections.push('<div style="border:1px solid var(--border);border-radius:10px;padding:9px 10px;background:rgba(0,0,0,.08)">'
        + '<div style="font-size:.68rem;color:var(--gold);margin-bottom:7px;font-weight:700">'+escHtml(unit.name)+'</div>'
        + '<div style="display:flex;flex-direction:column;gap:6px">'+rows+'</div>'
        + '</div>');
    }
  });

  _guideEditorTbOmicronSelections = new Set(
    [..._guideEditorTbOmicronSelections].filter(key=>visibleKeys.has(key))
  );

  if(!sections.length){
    wrap.style.display = 'none';
    list.innerHTML = '';
    return;
  }

  wrap.style.display = 'block';
  hint.textContent = 'Check the Territory Battle omicrons this squad needs to function as intended.';
  list.innerHTML = sections.join('');
}

function collectGuideEditorRequiredTbOmicrons(){
  return Array.from(document.querySelectorAll('#se-omicron-list input[data-guide-omicron="1"]:checked')).map(input=>
    normalizeGuideTbOmicronRequirement({
      unitDefId: input.dataset.unitDefid,
      unitName: input.dataset.unitName,
      skillId: input.dataset.skillId,
      skillName: input.dataset.skillName,
    })
  ).filter(Boolean);
}

function _getGuideEditorTakenKeys(exemptInputId=''){
  const taken = new Set();
  if(!_editingSquad) return taken;
  const ids = ['se-leader'].concat(_getGuideEditorMemberInputIds(_editingSquad.pid, _editingSquad.mid));
  ids.forEach(id=>{
    if(id === exemptInputId) return;
    const value = String(document.getElementById(id)?.value || '').trim();
    const key = _guideUnitSelectionKey(value);
    if(key) taken.add(key);
  });
  return taken;
}

function _collectGuideEditorOptions(group, role='member', exemptInputId=''){
  rebuildUnitNameIndex();
  const seen = new Set();
  const opts = [];
  const wantShips = group === 'ships';
  const leaderOnlyCapitalShips = wantShips && role === 'leader';
  const memberExcludesCapitalShips = wantShips && role !== 'leader';
  const takenKeys = _getGuideEditorTakenKeys(exemptInputId);

  Object.entries(PLAYABLE_NAME_BY_DEFID).forEach(([defId, name])=>{
    if(!name || name === '(unknown)') return;
    const key = defIdKey(defId);
    const isShip = KNOWN_SHIP_DEFIDS.has(key);
    if(isShip !== wantShips) return;
    const isCapitalShip = CAPITAL_SHIP_DEFIDS.has(key);
    if(leaderOnlyCapitalShips && !isCapitalShip) return;
    if(memberExcludesCapitalShips && isCapitalShip) return;
    if(takenKeys.has(_guideUnitSelectionKey(name, defId))) return;
    if(seen.has(name)) return;
    seen.add(name);
    opts.push(name);
  });

  Object.values(guildRosters).forEach(roster=>(roster||[]).forEach(unit=>{
    const name = defIdToName((unit.defId||'').split(':')[0], unit.name);
    if(!name || name === '(unknown)' || seen.has(name)) return;
    if(isShipUnit(unit) !== wantShips) return;
    const unitDefId = normalizeDefId(unit?.defId);
    const isCapitalShip = CAPITAL_SHIP_DEFIDS.has(defIdKey(unitDefId));
    if(leaderOnlyCapitalShips && !isCapitalShip) return;
    if(memberExcludesCapitalShips && isCapitalShip) return;
    if(takenKeys.has(_guideUnitSelectionKey(name, unitDefId))) return;
    seen.add(name);
    opts.push(name);
  }));

  opts.sort((a,b)=>a.localeCompare(b));
  return opts;
}

function _rankGuideEditorOptions(options, query){
  const q = normalizeUnitName(query);
  if(!q) return options.slice(0, 80);
  const starts = [];
  const contains = [];
  options.forEach(name=>{
    const norm = normalizeUnitName(name);
    if(norm.startsWith(q)) starts.push(name);
    else if(norm.includes(q)) contains.push(name);
  });
  return starts.concat(contains).slice(0, 80);
}

function _buildUnitDatalist(pid, mid, query='', inputId='se-leader'){
  const dl=document.getElementById('se-unit-list');
  if(!dl)return;
  const group = _getGuideMissionUnitGroup(pid, mid);
  const role = inputId === 'se-leader' ? 'leader' : 'member';
  const opts = _rankGuideEditorOptions(_collectGuideEditorOptions(group, role, inputId), query);
  dl.innerHTML=opts.map(n=>`<option value="${escHtml(n)}">`).join('');
}

function _configureSquadEditorForMission(pid, mid){
  const mission = _getGuideMissionMeta(pid, mid);
  const isFleet = mission?.type === 'fleet';
  const leaderLabel = document.getElementById('se-leader-label');
  const membersLabel = document.getElementById('se-members-label');
  const typeHint = document.getElementById('se-type-hint');
  const startingLabel = document.getElementById('se-starting-label');
  const reinforcementLabel = document.getElementById('se-reinforcement-label');
  const leaderInput = document.getElementById('se-leader');
  const omicronWrap = document.getElementById('se-omicron-wrap');
  const slotConfigs = isFleet
    ? [
        {id:'se-m1', label:'Starting Ship 1', placeholder:'e.g. Darth Vader\'s TIE Advanced x1', visible:true},
        {id:'se-m2', label:'Starting Ship 2', placeholder:'Starting Ship 2', visible:true},
        {id:'se-m3', label:'Starting Ship 3', placeholder:'Starting Ship 3', visible:true},
        {id:'se-m4', label:'Reinforcement 1', placeholder:'Reinforcement 1', visible:true},
        {id:'se-m5', label:'Reinforcement 2', placeholder:'Reinforcement 2', visible:true},
        {id:'se-m6', label:'Reinforcement 3', placeholder:'Reinforcement 3', visible:true},
        {id:'se-m7', label:'Reinforcement 4', placeholder:'Reinforcement 4', visible:true},
      ]
    : [
        {id:'se-m1', label:'Member 2', placeholder:'Member 2', visible:true},
        {id:'se-m2', label:'Member 3', placeholder:'Member 3', visible:true},
        {id:'se-m3', label:'Member 4', placeholder:'Member 4', visible:true},
        {id:'se-m4', label:'Member 5', placeholder:'Member 5', visible:true},
        {id:'se-m5', label:'', placeholder:'', visible:false},
        {id:'se-m6', label:'', placeholder:'', visible:false},
        {id:'se-m7', label:'', placeholder:'', visible:false},
      ];

  if(leaderLabel){
    leaderLabel.innerHTML = isFleet
      ? 'Capital Ship Leader <span style="color:var(--text3)">(capital ship name)</span>'
      : 'Squad Leader <span style="color:var(--text3)">(character name)</span>';
  }
  if(membersLabel){
    membersLabel.innerHTML = isFleet
      ? 'Fleet Ships <span style="color:var(--text3)">(3 starters required, up to 4 reinforcements optional)</span>'
      : 'Other Members <span style="color:var(--text3)">(up to 4 unique characters)</span>';
  }
  if(typeHint){
    typeHint.textContent = isFleet
      ? 'Start typing to narrow the list. Fleet guides require 1 capital ship leader, 3 starting ships, and may add up to 4 reinforcements. Units must be unique.'
      : 'Start typing to narrow the list. This mission accepts characters only, and each unit can only appear once in the squad.';
  }
  if(leaderInput){
    leaderInput.placeholder = isFleet ? 'e.g. Leviathan' : 'e.g. Sith Eternal Emperor';
  }
  if(startingLabel) startingLabel.style.display = isFleet ? 'block' : 'none';
  if(reinforcementLabel) reinforcementLabel.style.display = isFleet ? 'block' : 'none';
  if(omicronWrap && isFleet) omicronWrap.style.display = 'none';

  slotConfigs.forEach((cfg, idx)=>{
    const input = document.getElementById(cfg.id);
    const wrap = document.getElementById('se-slot-wrap-'+(idx+1));
    const slotLabel = document.getElementById('se-slot-label-'+(idx+1));
    if(wrap) wrap.style.display = cfg.visible ? 'block' : 'none';
    if(slotLabel) slotLabel.textContent = cfg.label;
    if(input) input.placeholder = cfg.placeholder;
  });
}

function refreshSquadEditorSuggestions(input){
  if(!_editingSquad) return;
  const query = typeof input === 'string' ? input : (input?.value || '');
  const inputId = typeof input === 'string' ? 'se-leader' : (input?.id || 'se-leader');
  _buildUnitDatalist(_editingSquad.pid, _editingSquad.mid, query, inputId);
  renderGuideTbOmicronOptions();
}

function ensureSquadEditorPortal(){
  const overlay = document.getElementById('squad-editor-overlay');
  if(!overlay) return null;
  if(overlay.parentElement !== document.body){
    document.body.appendChild(overlay);
  }
  return overlay;
}

function openSquadEditor(pid, mid, squadId){
  _editingSquad = {pid, mid, squadId};
  _configureSquadEditorForMission(pid, mid);
  _buildUnitDatalist(pid, mid, '', 'se-leader');
  const isEdit = squadId !== null;

  document.getElementById('squad-editor-title').textContent = isEdit ? 'Edit Squad' : 'Add Squad';

  if(isEdit){
    const squad = _getSquads(pid,mid).find(s=>s.id===squadId);
    if(!squad) return;
    document.getElementById('se-leader').value = squad.leader||'';
    const mems = squad.members||[];
    GUIDE_FLEET_MEMBER_INPUT_IDS.forEach((id,i)=>{
      document.getElementById(id).value = mems[i]||'';
    });
    document.getElementById('se-notes').value  = squad.notes||'';
    document.getElementById('se-video').value  = squad.videoUrl||'';
    _guideEditorTbOmicronSelections = new Set(
      getGuideSquadTbOmicronRequirements(squad)
        .map(req=>normalizeGuideSkillKey(req.skillId))
        .filter(Boolean)
    );
    selectDiff(squad.difficulty||'auto');
  } else {
    document.getElementById('se-leader').value = '';
    GUIDE_FLEET_MEMBER_INPUT_IDS.forEach(id=>{ document.getElementById(id).value=''; });
    document.getElementById('se-notes').value = '';
    document.getElementById('se-video').value = '';
    _guideEditorTbOmicronSelections = new Set();
    selectDiff('auto');
  }

  const ov = ensureSquadEditorPortal();
  if(ov){ ov.style.display='flex'; }
  document.body.style.overflow = 'hidden';
  renderGuideTbOmicronOptions();
  ensureGuideTbOmicronMap();
  setTimeout(()=>{
    refreshSquadEditorSuggestions(document.getElementById('se-leader'));
    document.getElementById('se-leader').focus();
  }, 100);
}

function closeSquadEditor(){
  const ov = document.getElementById('squad-editor-overlay');
  if(ov){ ov.style.display='none'; }
  _editingSquad = null;
  _guideEditorTbOmicronSelections = new Set();
  document.body.style.overflow = '';
}

function selectDiff(d){
  _guideDiff = d;
  const styles = {
    auto:   {border:'#27ae60',bg:'rgba(39,174,96,.2)',clr:'#2ecc71'},
    easy:   {border:'#2980b9',bg:'rgba(52,152,219,.2)',clr:'#3498db'},
    medium: {border:'#d4ac0d',bg:'rgba(241,196,15,.2)',clr:'#f1c40f'},
    hard:   {border:'#922b21',bg:'rgba(192,57,43,.2)',clr:'#e74c3c'},
  };
  ['auto','easy','medium','hard'].forEach(k=>{
    const btn = document.getElementById('diff-'+k);
    if(!btn) return;
    const s = styles[k];
    if(k===d){
      btn.style.border='2px solid '+s.border;
      btn.style.background=s.bg;
      btn.style.color=s.clr;
    } else {
      btn.style.border='2px solid var(--border2)';
      btn.style.background='transparent';
      btn.style.color='var(--text2)';
    }
  });
}

function _genId(){
  return Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,7);
}

function saveSquadEditor(){
  if(!_editingSquad) return;
  const {pid, mid, squadId} = _editingSquad;
  const isFleetMission = _getGuideMissionUnitGroup(pid, mid) === 'ships';
  const expectedCombatType = isFleetMission ? 2 : 1;
  const memberInputIds = _getGuideEditorMemberInputIds(pid, mid);

  const leader = document.getElementById('se-leader').value.trim();
  if(!leader){ alert('Squad leader name is required.'); return; }
  const leaderDefId = resolveUnitNameToDefId(leader);
  if(leaderDefId && inferUnitCombatType({defId:leaderDefId}) !== expectedCombatType){
    alert(expectedCombatType === 2
      ? 'Fleet missions can only use ship names.'
      : 'Combat and special missions can only use character names.');
    return;
  }
  if(isFleetMission && !_isCapitalShipRef(leaderDefId || leader)){
    alert('Fleet mission leaders must be capital ships.');
    return;
  }

  const rawMembers = memberInputIds.map(id=>document.getElementById(id).value.trim());
  if(isFleetMission && rawMembers.slice(0, GUIDE_FLEET_STARTER_INPUT_IDS.length).some(name=>!name)){
    alert('Fleet guides require 3 starting ships before they can be saved.');
    return;
  }
  const members = rawMembers.slice();
  const memberDefIds = rawMembers.map(name=>name ? resolveUnitNameToDefId(name) : '');
  const invalidMember = memberDefIds.find(defId=>defId && inferUnitCombatType({defId}) !== expectedCombatType);
  if(invalidMember){
    alert(expectedCombatType === 2
      ? 'Fleet missions can only use ship names.'
      : 'Combat and special missions can only use character names.');
    return;
  }
  if(isFleetMission && memberDefIds.find(defId=>defId && _isCapitalShipRef(defId))){
    alert('Capital ships can only be used in the fleet leader slot.');
    return;
  }

  const duplicateName = (() => {
    const seen = new Map();
    const allEntries = [{slot:'Leader', name:leader, defId:leaderDefId}]
      .concat(rawMembers.filter(Boolean).map((name, idx)=>({
        slot:isFleetMission
          ? (idx < GUIDE_FLEET_STARTER_INPUT_IDS.length ? ('Starting Ship '+(idx+1)) : ('Reinforcement '+(idx + 1 - GUIDE_FLEET_STARTER_INPUT_IDS.length)))
          : ('Member '+(idx+1)),
        name,
        defId: resolveUnitNameToDefId(name)
      })));
    for(const entry of allEntries){
      const key = _guideUnitSelectionKey(entry.name, entry.defId);
      if(!key) continue;
      if(seen.has(key)) return entry.name || seen.get(key).name;
      seen.set(key, entry);
    }
    return '';
  })();
  if(duplicateName){
    alert('Each squad slot must use a unique unit. Duplicate found: '+duplicateName);
    return;
  }
  const notes    = document.getElementById('se-notes').value.trim();
  const videoUrl = normalizeExternalUrl(document.getElementById('se-video').value.trim());
  const requiredTbOmicrons = isFleetMission ? [] : collectGuideEditorRequiredTbOmicrons();

  const squads = _getSquads(pid, mid);

  if(squadId){
    // Edit existing
    const idx = squads.findIndex(s=>s.id===squadId);
    if(idx>=0){
      squads[idx] = normalizeGuideSquad({
        ...squads[idx],
        leader,
        leaderDefId,
        members,
        memberDefIds,
        notes,
        videoUrl,
        requiredTbOmicrons,
        difficulty:_guideDiff
      });
    }
  } else {
    // New squad
    squads.push(normalizeGuideSquad({
      id:_genId(),
      leader,
      leaderDefId,
      members,
      memberDefIds,
      notes,
      videoUrl,
      requiredTbOmicrons,
      difficulty:_guideDiff,
      order:squads.length
    }));
  }

  _setSquads(pid, mid, squads);
  closeSquadEditor();
  renderGuidePlanetList();
  renderGuideMission(pid, mid);
}

function deleteSquad(pid, mid, squadId){
  if(!confirm('Delete this squad?')) return;
  const squads = _getSquads(pid,mid).filter(s=>s.id!==squadId);
  _setSquads(pid,mid,squads);
  renderGuidePlanetList();
  renderGuideMission(pid,mid);
}

function moveSquad(pid, mid, fromIdx, delta){
  const squads = _getSquads(pid,mid);
  const toIdx = fromIdx+delta;
  if(toIdx<0||toIdx>=squads.length) return;
  [squads[fromIdx],squads[toIdx]] = [squads[toIdx],squads[fromIdx]];
  _setSquads(pid,mid,squads);
  renderGuideMission(pid,mid);
}

// ── Save / Load ───────────────────────────────────────────────────────────────
function exportGuide(){
  const json = JSON.stringify(normalizeGuideData(guideData), null, 2);
  const blob = new Blob([json], {type:'application/json'});
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url;
  a.download = 'rote-guide.json';
  a.click();
  URL.revokeObjectURL(url);
}

function importGuide(input){
  const file = input.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = e=>{
    try{
      const data = JSON.parse(e.target.result);
      if(!data.squads) throw new Error('Invalid guide file format');
      guideData = normalizeGuideData(data);
      renderGuidePlanetList();
      if(_activeGuide) renderGuideMission(_activeGuide.pid, _activeGuide.mid);
      queueSaveAppState();
      showImportStatus('Guide loaded — '+Object.keys(data.squads).length+' missions with squads','ok');
    } catch(err){
      alert('Failed to load guide file: '+err.message);
    }
    input.value='';
  };
  reader.readAsText(file);
}

// Call renderGuides when tab opens
function initGuideTab(){
  refreshGuideUnitLinks();
  renderGuidePlanetList();
  populateMemberDropdown();
  if(Object.keys(_expandedPlanets).length===0){
    // Expand all Phase 1 planets by default on a fresh session
    ['mustafar','corellia','coruscant'].forEach(pid=>{
      if(!_expandedPlanets[pid]){ toggleGuidePlanet(pid); }
    });
  }
}



// ROSTER VIEWER

let _rosterData  = [];    // current member's full roster (simplified units)
let _rosterSort  = {key:'name', dir:1};

// Format a defId into a readable name
// LORDVADER -> "Lord Vader", GRANDMASTEROBIWAN -> "Grand Master Obiwan"
// Authoritative defId→name table (270 characters from swgoh.gg, April 2026)
// Keys are Base IDs from comlink definitionId (prefix before ":")
const UNIT_NAMES = {
  "50RT":'50R-T',
  AAYLASECURA:'Aayla Secura',
  ADMINISTRATORLANDO:'Lando Calrissian',
  ADMIRALACKBAR:'Admiral Ackbar',
  ADMIRALPIETT:'Admiral Piett',
  ADMIRALRADDUS:'Admiral Raddus',
  AHSOKATANO:"Ahsoka Tano (Snips)",
  AMILYNHOLDO:'Amilyn Holdo',
  ANAKINKNIGHT:'Jedi Knight Anakin',
  ARCTROOPER501ST:'ARC Trooper',
  ARMORER:'The Armorer',
  ASAJVENTRESS:'Asajj Ventress',
  AURRA_SING:'Aurra Sing',
  B1BATTLEDROIDV2:'B1 Battle Droid',
  B2SUPERBATTLEDROID:'B2 Super Battle Droid',
  BADBATCHECHO:'Echo',
  BADBATCHHUNTER:'Hunter',
  BADBATCHOMEGA:'Omega',
  BADBATCHTECH:'Tech',
  BADBATCHWRECKER:'Wrecker',
  BARRISSOFFEE:'Barriss Offee',
  BASTILASHAN:'Bastila Shan',
  BASTILASHANDARK:'Bastila Shan (Fallen)',
  BAZEMALBUS:'Baze Malbus',
  BB8:'BB-8',
  BENSOLO:'Ben Solo',
  BIGGSDARKLIGHTER:'Biggs Darklighter',
  BISTAN:'Bistan',
  BOBAFETT:'Boba Fett',
  BOBAFETTSCION:'Boba Fett, Scion of Jango',
  BODHIROOK:'Bodhi Rook',
  BOKATAN:'Bo-Katan Kryze',
  BOOMADIER:'Gungan Boomadier',
  BOSSK:'Bossk',
  BOSSNASS:'Boss Nass',
  BOUSHH:'Boushh (Leia Organa)',
  BT1:'BT-1',
  C3POCHEWBACCA:'Threepio & Chewie',
  C3POLEGENDARY:'C-3PO',
  CADBANE:'Cad Bane',
  CALKESTIS:'Cal Kestis',
  CANDEROUSORDO:'Canderous Ordo',
  CAPTAINDROGAN:'Captain Drogan',
  CAPTAINREX:'Captain Rex',
  CAPTAINTARPALS:'Captain Tarpals',
  CARADUNE:'Cara Dune',
  CARTHONASI:'Carth Onasi',
  CASSIANANDOR:'Cassian Andor',
  CC2224:'CC-2224 "Cody"',
  CEREJUNDA:'Cere Junda',
  CHEWBACCALEGENDARY:'Chewbacca',
  CHIEFCHIRPA:'Chief Chirpa',
  CHIEFNEBIT:'Chief Nebit',
  CHIRRUTIMWE:'Chirrut Îmwe',
  CHOPPERS3:'Chopper',
  CLONESERGEANTPHASEI:'Clone Sergeant - Phase I',
  CLONEWARSCHEWBACCA:'Clone Wars Chewbacca',
  COLONELSTARCK:'Colonel Starck',
  COMMANDERAHSOKA:'Commander Ahsoka Tano',
  COMMANDERLUKESKYWALKER:'Commander Luke Skywalker',
  CORUSCANTUNDERWORLDPOLICE:'Coruscant Underworld Police',
  COUNTDOOKU:'Count Dooku',
  CT210408:'CT-21-0408 "Echo"',
  CT5555:'CT-5555 "Fives"',
  CT7567:'CT-7567 "Rex"',
  DAKA:'Old Daka',
  DARKTROOPER:'Dark Trooper',
  DARTHBANE:'Darth Bane',
  DARTHMALAK:'Darth Malak',
  DARTHMALGUS:'Darth Malgus',
  DARTHNIHILUS:'Darth Nihilus',
  DARTHREVAN:'Darth Revan',
  DARTHSIDIOUS:'Darth Sidious',
  DARTHSION:'Darth Sion',
  DARTHTALON:'Darth Talon',
  DARTHTRAYA:'Darth Traya',
  DASHRENDAR:'Dash Rendar',
  DATHCHA:'Dathcha',
  DEATHTROOPER:'Death Trooper',
  DENGAR:'Dengar',
  DIRECTORKRENNIC:'Director Krennic',
  DOCTORAPHRA:'Doctor Aphra',
  DROIDEKA:'Droideka',
  EETHKOTH:'Eeth Koth',
  EIGHTHBROTHER:'Eighth Brother',
  EMBO:'Embo',
  EMPERORPALPATINE:'Emperor Palpatine',
  ENFYSNEST:'Enfys Nest',
  EPIXFINN:'Resistance Hero Finn',
  EPIXPOE:'Resistance Hero Poe',
  EWOKELDER:'Ewok Elder',
  EWOKSCOUT:'Ewok Scout',
  EZRABRIDGERS3:'Ezra Bridger',
  FENNECSHAND:'Fennec Shand',
  FIFTHBROTHER:'Fifth Brother',
  FINN:'Finn',
  FIRSTORDEREXECUTIONER:'First Order Executioner',
  FIRSTORDEROFFICERMALE:'First Order Officer',
  FIRSTORDERSPECIALFORCESPILOT:'First Order SF TIE Pilot',
  FIRSTORDERTIEPILOT:'First Order TIE Pilot',
  FIRSTORDERTROOPER:'First Order Stormtrooper',
  FOSITHTROOPER:'Sith Trooper',
  FULCRUMAHSOKA:'Ahsoka Tano (Fulcrum)',
  GAMORREANGUARD:'Gamorrean Guard',
  GARSAXON:'Gar Saxon',
  GENERALHUX:'General Hux',
  GENERALKENOBI:'General Kenobi',
  GENERALSKYWALKER:'General Skywalker',
  GEONOSIANBROODALPHA:'Geonosian Brood Alpha',
  GEONOSIANSOLDIER:'Geonosian Soldier',
  GEONOSIANSPY:'Geonosian Spy',
  GLLEIA:'Leia Organa',
  GLREY:'Rey',
  GRANDADMIRALTHRAWN:'Grand Admiral Thrawn',
  GRANDINQUISITOR:'Grand Inquisitor',
  GRANDMASTERLUKE:'Jedi Master Luke Skywalker',
  GRANDMASTERYODA:'Grand Master Yoda',
  GRANDMOFFTARKIN:'Grand Moff Tarkin',
  GREEDO:'Greedo',
  GREEFKARGA:'Greef Karga',
  GRIEVOUS:'General Grievous',
  GUNGANPHALANX:'Gungan Phalanx',
  HANSOLO:'Han Solo',
  HERASYNDULLAS3:'Hera Syndulla',
  HERMITYODA:'Hermit Yoda',
  HK47:'HK-47',
  HONDO:'Hondo Ohnaka',
  HOTHHAN:'Captain Han Solo',
  HOTHLEIA:'Rebel Officer Leia Organa',
  HOTHREBELSCOUT:'Hoth Rebel Scout',
  HOTHREBELSOLDIER:'Hoth Rebel Soldier',
  HUMANTHUG:'Mob Enforcer',
  IDENVERSIOEMPIRE:'Iden Versio',
  IG11:'IG-11',
  IG12:'IG-12 & Grogu',
  IG86SENTINELDROID:'IG-86 Sentinel Droid',
  IG88:'IG-88',
  IMAGUNDI:'Ima-Gun Di',
  IMPERIALPROBEDROID:'Imperial Probe Droid',
  IMPERIALSUPERCOMMANDO:'Imperial Super Commando',
  JABBATHEHUTT:'Jabba the Hutt',
  JANGOFETT:'Jango Fett',
  JARJARBINKS:'Jar Jar Binks',
  JAWA:'Jawa',
  JAWAENGINEER:'Jawa Engineer',
  JAWASCAVENGER:'Jawa Scavenger',
  JEDIKNIGHTCAL:'Jedi Knight Cal Kestis',
  JEDIKNIGHTCONSULAR:'Jedi Consular',
  JEDIKNIGHTGUARDIAN:'Jedi Knight Guardian',
  JEDIKNIGHTLUKE:'Jedi Knight Luke Skywalker',
  JEDIKNIGHTREVAN:'Jedi Knight Revan',
  JEDIMASTERKENOBI:'Jedi Master Kenobi',
  JOLEEBINDO:'Jolee Bindo',
  JUHANI:'Juhani',
  JYNERSO:'Jyn Erso',
  K2SO:'K-2SO',
  KANANJARRUSS3:'Kanan Jarrus',
  KELLERANBEQ:'Kelleran Beq',
  KIADIMUNDI:'Ki-Adi-Mundi',
  KITFISTO:'Kit Fisto',
  KRRSANTAN:'Krrsantan',
  KUIIL:'Kuiil',
  KYLEKATARN:'Kyle Katarn',
  KYLOREN:'Kylo Ren',
  KYLORENUNMASKED:'Kylo Ren (Unmasked)',
  L3_37:'L3-37',
  LOBOT:'Lobot',
  LOGRAY:'Logray',
  LORDVADER:'Lord Vader',
  LUKESKYWALKER:'Luke Skywalker (Farmboy)',
  LUMINARAUNDULI:'Luminara Unduli',
  LUTHENRAEL:'Luthen Rael',
  MACEWINDU:'Mace Windu',
  MAGMATROOPER:'Magmatrooper',
  MAGNAGUARD:'IG-100 MagnaGuard',
  MANDALORBOKATAN:'Bo-Katan (Mand\'alor)',
  MARAJADE:'Mara Jade, The Emperor\'s Hand',
  MASTERQUIGON:'Master Qui-Gon',
  MAUL:'Darth Maul',
  MAULS7:'Maul',
  MERRIN:'Merrin',
  MISSIONVAO:'Mission Vao',
  MOFFGIDEONS1:'Moff Gideon',
  MOFFGIDEONS3:'Dark Trooper Moff Gideon',
  MONMOTHMA:'Mon Mothma',
  MOTHERTALZIN:'Mother Talzin',
  NIGHTSISTERACOLYTE:'Nightsister Acolyte',
  NIGHTSISTERINITIATE:'Nightsister Initiate',
  NIGHTSISTERSPIRIT:'Nightsister Spirit',
  NIGHTSISTERZOMBIE:'Nightsister Zombie',
  NINTHSISTER:'Ninth Sister',
  NUTEGUNRAY:'Nute Gunray',
  OLDBENKENOBI:'Obi-Wan Kenobi (Old Ben)',
  PADAWANOBIWAN:'Padawan Obi-Wan',
  PADMEAMIDALA:'Padmé Amidala',
  PAO:'Pao',
  PAPLOO:'Paploo',
  PAZVIZSLA:'Paz Vizsla',
  PHASMA:'Captain Phasma',
  PLOKOON:'Plo Koon',
  POE:'Poe Dameron',
  POGGLETHELESSER:'Poggle the Lesser',
  PRINCESSKNEESAA:'Princess Kneesaa',
  PRINCESSLEIA:'Princess Leia',
  QIRA:'Qi\'ra',
  QUEENAMIDALA:'Queen Amidala',
  QUIGONJINN:'Qui-Gon Jinn',
  R2D2_LEGENDARY:'R2-D2',
  RANGETROOPER:'Range Trooper',
  RESISTANCEPILOT:'Resistance Pilot',
  RESISTANCETROOPER:'Resistance Trooper',
  REY:'Rey (Scavenger)',
  REYJEDITRAINING:'Rey (Jedi Training)',
  ROSETICO:'Rose Tico',
  ROYALGUARD:'Royal Guard',
  SABINEWRENS3:'Sabine Wren',
  SANASTARROS:'Sana Starros',
  SAVAGEOPRESS:'Savage Opress',
  SAWGERRERA:'Saw Gerrera',
  SCARIFREBEL:'Scarif Rebel Pathfinder',
  SCOUTTROOPER_V3:'Scout Trooper',
  SECONDSISTER:'Second Sister',
  SEVENTHSISTER:'Seventh Sister',
  SHAAKTI:'Shaak Ti',
  SHORETROOPER:'Shoretrooper',
  SITHASSASSIN:'Sith Assassin',
  SITHMARAUDER:'Sith Marauder',
  SITHPALPATINE:'Sith Eternal Emperor',
  SITHTROOPER:'Sith Empire Trooper',
  SMUGGLERCHEWBACCA:'Veteran Smuggler Chewbacca',
  SMUGGLERHAN:'Veteran Smuggler Han Solo',
  SNOWTROOPER:'Snowtrooper',
  STAP:'STAP',
  STARKILLER:'Starkiller',
  STORMTROOPER:'Stormtrooper',
  STORMTROOPERHAN:'Stormtrooper Han',
  SUNFAC:'Sun Fac',
  SUPREMELEADERKYLOREN:'Supreme Leader Kylo Ren',
  T3_M4:'T3-M4',
  TALIA:'Talia',
  TARFFUL:'Tarfful',
  TARONMALICOS:'Taron Malicos',
  TEEBO:'Teebo',
  THEMANDALORIAN:'The Mandalorian',
  THEMANDALORIANBESKARARMOR:'The Mandalorian (Beskar Armor)',
  THIRDSISTER:'Third Sister',
  TIEFIGHTERPILOT:'TIE Fighter Pilot',
  TRENCH:'Admiral Trench',
  TRIPLEZERO:'0-0-0',
  TUSKENCHIEFTAIN:'Tusken Chieftain',
  TUSKENHUNTRESS:'Tusken Warrior',
  TUSKENRAIDER:'Tusken Raider',
  TUSKENSHAMAN:'Tusken Shaman',
  UGNAUGHT:'Ugnaught',
  UNDERCOVERLANDO:'Skiff Guard (Lando Calrissian)',
  URORRURRR:'URoRRuR\'R\'R',
  VADER:'Darth Vader',
  VEERS:'General Veers',
  VISASMARR:'Visas Marr',
  WAMPA:'Wampa',
  WATTAMBOR:'Wat Tambor',
  WEDGEANTILLES:'Wedge Antilles',
  WICKET:'Wicket',
  YOUNGCHEWBACCA:'Vandor Chewbacca',
  YOUNGHAN:'Young Han Solo',
  YOUNGLANDO:'Young Lando Calrissian',
  ZAALBAR:'Zaalbar',
  ZAMWESELL:'Zam Wesell',
  ZEBS3:'Garazeb "Zeb" Orrelios',
  ZORIIBLISS_V2:'Zorii Bliss',
};

// Zeta & omicron ability names per unit (swgoh.gg, April 2026)
const UNIT_ABILITIES = {
  "50RT":{z:["Sabacc Shuffle", "Spare Parts"],o:["Spare Parts"]},
  AAYLASECURA:{z:[],o:[]},
  ADMINISTRATORLANDO:{z:[],o:[]},
  ADMIRALACKBAR:{z:[],o:["Rebel Coordination"]},
  ADMIRALPIETT:{z:["Suborbital Strike", "The Emperor's Trap"],o:[]},
  ADMIRALRADDUS:{z:["Inspiring Maneuver", "Transmission from Scarif"],o:["Rebel Assault"]},
  AHSOKATANO:{z:["Daring Padawan"],o:[]},
  AMILYNHOLDO:{z:["Quiet Confidence"],o:[]},
  ANAKINKNIGHT:{z:["Righteous Fury"],o:[]},
  ARCTROOPER501ST:{z:["ARC Arsenal"],o:[]},
  ARMORER:{z:["Earn Your Signet"],o:[]},
  ASAJVENTRESS:{z:["Nightsister Swiftness", "Rampage"],o:["Rampage"]},
  AURRA_SING:{z:["Game Plan", "Snipers Expertise"],o:[]},
  B1BATTLEDROIDV2:{z:["Droid Battalion"],o:[]},
  B2SUPERBATTLEDROID:{z:["Reactive Protocol"],o:[]},
  BADBATCHECHO:{z:["One That Survives"],o:[]},
  BADBATCHHUNTER:{z:["A Different Path"],o:[]},
  BADBATCHOMEGA:{z:["Adaptive Learner", "Part of the Squad"],o:["Part of the Squad"]},
  BADBATCHTECH:{z:["Clone Interpreter"],o:[]},
  BADBATCHWRECKER:{z:["Dauntless Commando"],o:[]},
  BARRISSOFFEE:{z:["Swift Recovery"],o:[]},
  BASTILASHAN:{z:["Initiative"],o:[]},
  BASTILASHANDARK:{z:["Sith Apprentice"],o:[]},
  BAZEMALBUS:{z:[],o:[]},
  BB8:{z:["Roll with the Punches", "Self-Preservation Protocol"],o:[]},
  BENSOLO:{z:["Family Legacy", "Force Dyad", "Redeemed"],o:["Force Dyad", "Obscured", "Redeemed"]},
  BIGGSDARKLIGHTER:{z:[],o:[]},
  BISTAN:{z:[],o:[]},
  BOBAFETT:{z:["Bounty Hunter's Resolve"],o:[]},
  BOBAFETTSCION:{z:["Fett Legacy"],o:["Dangerous Reputation", "Dual Barrage", "Fett Legacy"]},
  BODHIROOK:{z:["Double Duty"],o:[]},
  BOKATAN:{z:["Stronger Together"],o:[]},
  BOOMADIER:{z:["Grand Army Specialist"],o:[]},
  BOSSK:{z:["On The Hunt", "Trandoshan Rage"],o:[]},
  BOSSNASS:{z:["Ankura Resilience", "Boss of Otoh Gunga"],o:["Boss of Otoh Gunga"]},
  BOUSHH:{z:["Fearless"],o:["Ubese Ogygian Cloak"]},
  BT1:{z:["Homicidal Counterpart"],o:["Homicidal Counterpart"]},
  C3POCHEWBACCA:{z:["Chewie's Rage"],o:[]},
  C3POLEGENDARY:{z:["Oh My Goodness!", "Wait for Me!"],o:[]},
  CADBANE:{z:[],o:[]},
  CALKESTIS:{z:["I'm Persistent", "Not So Fast"],o:["I'm Persistent"]},
  CANDEROUSORDO:{z:["I Like a Challenge"],o:[]},
  CAPTAINDROGAN:{z:["Coordinated Shot", "Second in Command"],o:["Second in Command"]},
  CAPTAINREX:{z:["Master Marksman", "The Lost Commander"],o:["The Lost Commander"]},
  CAPTAINTARPALS:{z:["Mesa Tink Of Something"],o:["Mesa Tink Of Something"]},
  CARADUNE:{z:["Ex-Rebel Shock Trooper"],o:[]},
  CARTHONASI:{z:["Soldier of the Old Republic"],o:["Soldier of the Old Republic"]},
  CASSIANANDOR:{z:["Groundwork"],o:["Groundwork"]},
  CC2224:{z:["Ghost Company Commander"],o:[]},
  CEREJUNDA:{z:["Determined Assault", "Rekindle"],o:["Rekindle"]},
  CHEWBACCALEGENDARY:{z:["Loyal Friend", "Raging Wookiee"],o:[]},
  CHIEFCHIRPA:{z:["Simple Tactics"],o:["Simple Tactics"]},
  CHIEFNEBIT:{z:[],o:["Raiding Parties"]},
  CHIRRUTIMWE:{z:[],o:[]},
  CHOPPERS3:{z:[],o:[]},
  CLONESERGEANTPHASEI:{z:[],o:[]},
  CLONEWARSCHEWBACCA:{z:["Defiant Roar"],o:[]},
  COLONELSTARCK:{z:["Imperial Intelligence"],o:[]},
  COMMANDERAHSOKA:{z:["Force Leap", "Her Own Path", "Shien"],o:[]},
  COMMANDERLUKESKYWALKER:{z:["It Binds All Things", "Learn Control", "Rebel Maneuvers"],o:[]},
  CORUSCANTUNDERWORLDPOLICE:{z:[],o:[]},
  COUNTDOOKU:{z:["Flawless Riposte"],o:[]},
  CT210408:{z:["Domino Squad"],o:[]},
  CT5555:{z:["Domino Squad", "Tactical Awareness"],o:[]},
  CT7567:{z:["Captain of the 501st"],o:[]},
  DAKA:{z:["Serve Again"],o:[]},
  DARKTROOPER:{z:["Bombarding Reinforcements"],o:[]},
  DARTHBANE:{z:["Only The Strong Survive", "Rule of Two", "Soul Sever"],o:["Essence of Dominance", "Malevolent Whirlwind", "Rule of Two"]},
  DARTHMALAK:{z:["Gnawing Terror", "Jaws of Life"],o:[]},
  DARTHMALGUS:{z:["Dark Deception", "Unfettered Rage"],o:["Deprive Senses", "Korriban's Legacy", "Legacy of Power"]},
  DARTHNIHILUS:{z:["Lord of Hunger", "Strength of the Void"],o:[]},
  DARTHREVAN:{z:["Conqueror", "Lord of the Sith", "Villain"],o:[]},
  DARTHSIDIOUS:{z:["Sadistic Glee"],o:["Sadistic Glee"]},
  DARTHSION:{z:["Lord of Pain"],o:[]},
  DARTHTALON:{z:["Proven Loyalty"],o:["Sith Cruelty"]},
  DARTHTRAYA:{z:["Compassion is Weakness", "Lord of Betrayal"],o:["Lord of Betrayal"]},
  DASHRENDAR:{z:["Hotshot"],o:["Prepared for Anything"]},
  DATHCHA:{z:[],o:[]},
  DEATHTROOPER:{z:["Krennic's Guard"],o:[]},
  DENGAR:{z:["Grizzled Veteran"],o:[]},
  DIRECTORKRENNIC:{z:["Director of Advanced Weapons Research"],o:["Immeasurable Power"]},
  DOCTORAPHRA:{z:["Dangerous Tech", "Droid Savant", "Suspended Doctorate"],o:["Droid Savant", "Rogue Archaeology", "Suspended Doctorate"]},
  DROIDEKA:{z:["Deflector Shield Generator"],o:["Deflector Shield Generator"]},
  EETHKOTH:{z:[],o:[]},
  EIGHTHBROTHER:{z:["Bladed Hilt"],o:["More Than Enough"]},
  EMBO:{z:["The Quiet Assassin", "Way of the Kyuzo"],o:["Way of the Kyuzo"]},
  EMPERORPALPATINE:{z:["Crackling Doom", "Emperor of the Galactic Empire"],o:[]},
  ENFYSNEST:{z:["Fighting Instinct"],o:[]},
  EPIXFINN:{z:["Spark of Resistance"],o:[]},
  EPIXPOE:{z:["Spark of Resistance"],o:[]},
  EWOKELDER:{z:[],o:[]},
  EWOKSCOUT:{z:[],o:[]},
  EZRABRIDGERS3:{z:["Flourish"],o:[]},
  FENNECSHAND:{z:["Making an Impression"],o:[]},
  FIFTHBROTHER:{z:["Shrouded in Darkness"],o:["I Sense Those We Seek"]},
  FINN:{z:["Balanced Tactics"],o:["Balanced Tactics"]},
  FIRSTORDEREXECUTIONER:{z:[],o:[]},
  FIRSTORDEROFFICERMALE:{z:[],o:[]},
  FIRSTORDERSPECIALFORCESPILOT:{z:[],o:[]},
  FIRSTORDERTIEPILOT:{z:["Keen Eye"],o:["Keen Eye"]},
  FIRSTORDERTROOPER:{z:["Return Fire"],o:[]},
  FOSITHTROOPER:{z:["Emperor's Legacy"],o:[]},
  FULCRUMAHSOKA:{z:["Whirlwind"],o:["Perseverance"]},
  GAMORREANGUARD:{z:["Loyal Enforcer"],o:["Loyal Enforcer"]},
  GARSAXON:{z:["Mandalorian Retaliation"],o:[]},
  GENERALHUX:{z:["Boundless Ambition"],o:[]},
  GENERALKENOBI:{z:["Soresu"],o:[]},
  GENERALSKYWALKER:{z:["Furious Slash", "General of the 501st", "Hero with no Fear", "The Chosen One"],o:[]},
  GEONOSIANBROODALPHA:{z:["Geonosian Swarm", "Queen's Will"],o:[]},
  GEONOSIANSOLDIER:{z:[],o:[]},
  GEONOSIANSPY:{z:[],o:[]},
  GLLEIA:{z:["Forever Our Princess", "Galactic Legend", "I Know", "Rebel Ambush", "Righteous Retribution", "Tactical Offensive"],o:[]},
  GLREY:{z:["Galactic Legend", "Lifeblood", "Manifest Inspiration", "Relentless Advance", "Sudden Whirlwind", "Wisdom of the Sacred Texts"],o:[]},
  GRANDADMIRALTHRAWN:{z:["Ebb and Flow", "Legendary Strategist"],o:[]},
  GRANDINQUISITOR:{z:["Compassion Leaves a Trail", "Master Inquisitorius", "Pain Can Break Anyone"],o:["Compassion Leaves a Trail", "Master Inquisitorius", "Ready to Die?"]},
  GRANDMASTERLUKE:{z:["Efflux", "Galactic Legend", "Indomitable Blast", "Jedi Legacy", "Legend of the Jedi", "They Grow Beyond"],o:[]},
  GRANDMASTERYODA:{z:["Battle Meditation", "Grand Master's Guidance"],o:[]},
  GRANDMOFFTARKIN:{z:["Callous Conviction", "Tighten the Grip"],o:[]},
  GREEDO:{z:["Threaten"],o:[]},
  GREEFKARGA:{z:["Bring Them in Cold", "Sweeten the Deal"],o:[]},
  GRIEVOUS:{z:["Daunting Presence", "Metalloid Monstrosity"],o:[]},
  GUNGANPHALANX:{z:["Let Mesa Help"],o:["Let Mesa Help"]},
  HANSOLO:{z:["Shoots First"],o:[]},
  HERASYNDULLAS3:{z:["Play to Strengths"],o:["Rise Together"]},
  HERMITYODA:{z:["Do or Do Not", "Strength Flows From the Force"],o:[]},
  HK47:{z:["Loyalty to the Maker", "Self-Reconstruction"],o:[]},
  HONDO:{z:["I Don't Want to Kill You Per Se", "That's Just Good Business"],o:["That's Just Good Business"]},
  HOTHHAN:{z:["Nick of Time"],o:[]},
  HOTHLEIA:{z:["Dauntless"],o:["Battlefront Command"]},
  HOTHREBELSCOUT:{z:[],o:[]},
  HOTHREBELSOLDIER:{z:[],o:[]},
  HUMANTHUG:{z:[],o:[]},
  IDENVERSIOEMPIRE:{z:["First In, Last Out"],o:["Exactly as Planned"]},
  IG11:{z:["Child's Favor"],o:[]},
  IG12:{z:["Yes. Yes. Yes."],o:["Yes. Yes. Yes."]},
  IG86SENTINELDROID:{z:[],o:[]},
  IG88:{z:["Adaptive Aim Algorithm"],o:[]},
  IMAGUNDI:{z:[],o:[]},
  IMPERIALPROBEDROID:{z:["Imperial Logistics"],o:["Imperial Logistics"]},
  IMPERIALSUPERCOMMANDO:{z:[],o:[]},
  JABBATHEHUTT:{z:["Crime Lord", "Crumb's Revenge", "Galactic Legend", "His High Exaltedness", "Illicit Business", "The Illustrious"],o:[]},
  JANGOFETT:{z:["Anything to Get Ahead", "Notorious Reputation"],o:[]},
  JARJARBINKS:{z:["Mesa Okeyday", "Mooie-Mooie, I Love You", "Wesa Warriors"],o:["Mesa Okeyday", "Mooie-Mooie, I Love You", "Uh Oh, Big Boomas"]},
  JAWA:{z:[],o:[]},
  JAWAENGINEER:{z:[],o:[]},
  JAWASCAVENGER:{z:[],o:[]},
  JEDIKNIGHTCAL:{z:["Impetuous Assault", "Jedi Survivor", "Windmill Defense"],o:["Impetuous Assault", "Weight of the Galaxy", "Whirlwind Slam"]},
  JEDIKNIGHTCONSULAR:{z:[],o:[]},
  JEDIKNIGHTGUARDIAN:{z:[],o:[]},
  JEDIKNIGHTLUKE:{z:["Jedi Knight's Resolve", "Return of the Jedi"],o:[]},
  JEDIKNIGHTREVAN:{z:["Direct Focus", "General", "Hero"],o:[]},
  JEDIMASTERKENOBI:{z:["Ardent Bladework", "Galactic Legend", "Harmonious Will", "Hello There", "I Will Do What I Must", "May The Force Be With You"],o:[]},
  JOLEEBINDO:{z:["That Looks Pretty Bad"],o:[]},
  JUHANI:{z:["Cathar Resilience"],o:["Cathar Resilience"]},
  JYNERSO:{z:["Fierce Determination", "Into the Fray"],o:["Fierce Determination"]},
  K2SO:{z:["Reprogrammed Imperial Droid"],o:[]},
  KANANJARRUSS3:{z:["Total Defense"],o:[]},
  KELLERANBEQ:{z:["Jedi Bravery", "The Sabered Hand"],o:["By The Will Of The Council"]},
  KIADIMUNDI:{z:["Jedi Council"],o:[]},
  KITFISTO:{z:[],o:[]},
  KRRSANTAN:{z:["Champion of the Fighting Pits"],o:["Champion of the Fighting Pits"]},
  KUIIL:{z:["Frontier Wisdom"],o:[]},
  KYLEKATARN:{z:["Power of the Valley"],o:["Blue Milk Run"]},
  KYLOREN:{z:["Outrage"],o:[]},
  KYLORENUNMASKED:{z:["Merciless Pursuit", "Scarred"],o:[]},
  L3_37:{z:["For the Droids"],o:[]},
  LOBOT:{z:[],o:[]},
  LOGRAY:{z:["Shaman's Insight"],o:[]},
  LORDVADER:{z:["Dark Harbinger", "Galactic Legend", "My New Empire", "Twisted Prophecy", "Unshackled Emotions", "Vindictive Storm"],o:[]},
  LUKESKYWALKER:{z:["A New Hope", "Draw a Bead"],o:["Draw a Bead"]},
  LUMINARAUNDULI:{z:["Elegant Steps"],o:["Master Healer's Blessing"]},
  LUTHENRAEL:{z:["A Sunless Space"],o:["Dreams With Ghosts", "Tools of My Enemy", "What Do I Sacrifice?"]},
  MACEWINDU:{z:["Sense Weakness", "This Party's Over", "Vaapad"],o:["Sense Weakness"]},
  MAGMATROOPER:{z:[],o:[]},
  MAGNAGUARD:{z:["Stunning Strike"],o:[]},
  MANDALORBOKATAN:{z:["Darksaber Flourish", "Reinforcements Have Arrived", "Way of the Mandalore"],o:["For Mandalore!", "Reinforcements Have Arrived", "Way of the Mandalore"]},
  MARAJADE:{z:["Infiltrate and Disrupt", "Ultimate Predator"],o:["The Emperor's Hand"]},
  MASTERQUIGON:{z:["Stay Close to Me"],o:["Stay Close to Me"]},
  MAUL:{z:["Dancing Shadows"],o:[]},
  MAULS7:{z:["Bound By Hatred", "Fervent Rush", "Seething Rage"],o:[]},
  MERRIN:{z:["Shadow Stride", "Vengeful Bond"],o:["Last of the Nightsisters"]},
  MISSIONVAO:{z:["Me and Big Z Forever"],o:[]},
  MOFFGIDEONS1:{z:["Control the Situation", "Tactical Deployment"],o:[]},
  MOFFGIDEONS3:{z:["Dark Trooper Beskar Armor", "Shadow Contingency", "Unwavering Presence"],o:["Dark Trooper Beskar Armor", "Shadow Contingency", "Strategic Onslaught"]},
  MONMOTHMA:{z:["Alliance Chancellor", "This Is Our Rebellion"],o:[]},
  MOTHERTALZIN:{z:["Plaguebearer", "The Great Mother"],o:[]},
  NIGHTSISTERACOLYTE:{z:[],o:[]},
  NIGHTSISTERINITIATE:{z:["Nightsister Retaliation"],o:[]},
  NIGHTSISTERSPIRIT:{z:[],o:[]},
  NIGHTSISTERZOMBIE:{z:[],o:[]},
  NINTHSISTER:{z:["Can't Stop the Empire", "Ground Pound"],o:["Can't Stop the Empire"]},
  NUTEGUNRAY:{z:["Viceroy's Reach"],o:[]},
  OLDBENKENOBI:{z:["Devoted Protector", "If You Strike Me Down"],o:[]},
  PADAWANOBIWAN:{z:["Nobility in Restraint"],o:["Nobility in Restraint"]},
  PADMEAMIDALA:{z:["Always a Choice", "Unwavering Courage"],o:[]},
  PAO:{z:["For Pipada"],o:[]},
  PAPLOO:{z:["Don't Hold Back"],o:[]},
  PAZVIZSLA:{z:["Legacy of House Vizsla", "Vengeful Incineration"],o:["Legacy of House Vizsla"]},
  PHASMA:{z:["Fire at Will"],o:["Fire at Will"]},
  PLOKOON:{z:[],o:[]},
  POE:{z:[],o:[]},
  POGGLETHELESSER:{z:[],o:["Hive Tactics"]},
  PRINCESSKNEESAA:{z:["Yub Nub"],o:["Bright Tree Village"]},
  PRINCESSLEIA:{z:["Against All Odds"],o:["Against All Odds"]},
  QIRA:{z:["Insult to Injury"],o:[]},
  QUEENAMIDALA:{z:["Loyal Bodyguard", "My Place is with My People"],o:["I am Queen Amidala", "Loyal Bodyguard", "My Place is with My People"]},
  QUIGONJINN:{z:["Agility Training"],o:["Agility Training"]},
  R2D2_LEGENDARY:{z:["Combat Analysis", "Number Crunch"],o:[]},
  RANGETROOPER:{z:[],o:[]},
  RESISTANCEPILOT:{z:[],o:[]},
  RESISTANCETROOPER:{z:[],o:[]},
  REY:{z:["Focused Strikes"],o:[]},
  REYJEDITRAINING:{z:["Insight", "Inspirational Presence", "Virtuous Protector"],o:[]},
  ROSETICO:{z:["Valiant Spirit"],o:["Valiant Spirit"]},
  ROYALGUARD:{z:["Unyielding Defender"],o:[]},
  SABINEWRENS3:{z:["Demolish"],o:[]},
  SANASTARROS:{z:["Rebel Sympathizer"],o:["Rebel Sympathizer"]},
  SAVAGEOPRESS:{z:["Brute"],o:["Brute"]},
  SAWGERRERA:{z:["Adapt and Survive", "Freedom Isn't Free"],o:["Freedom Isn't Free"]},
  SCARIFREBEL:{z:[],o:[]},
  SCOUTTROOPER_V3:{z:["Imperial Vanguard", "Strategic Assessment"],o:["Imperial Vanguard"]},
  SECONDSISTER:{z:["Everyone is Expendable"],o:["They Will Never Be Victorious"]},
  SEVENTHSISTER:{z:["Guess Again", "ID9 Enemy Intelligence"],o:["Guess Again"]},
  SHAAKTI:{z:["Heightened Reflexes", "Unity Wins War"],o:[]},
  SHORETROOPER:{z:[],o:[]},
  SITHASSASSIN:{z:[],o:[]},
  SITHMARAUDER:{z:[],o:[]},
  SITHPALPATINE:{z:["Deception", "Galactic Legend", "Sith Eternal", "So Be It, Jedi", "Sow Discord", "Unraveled Destiny"],o:[]},
  SITHTROOPER:{z:[],o:[]},
  SMUGGLERCHEWBACCA:{z:["Let the Wookiee Win"],o:[]},
  SMUGGLERHAN:{z:["Swindle"],o:[]},
  SNOWTROOPER:{z:[],o:[]},
  STAP:{z:["Single Trooper Aerial Platform"],o:["Single Trooper Aerial Platform"]},
  STARKILLER:{z:["Force Energy", "Imbued Lightsaber Strike"],o:["Boundless Force Throw", "Force Repulse", "There is Much Conflict in You"]},
  STORMTROOPER:{z:["Wall of Stormtroopers"],o:[]},
  STORMTROOPERHAN:{z:["Bluff"],o:[]},
  SUNFAC:{z:[],o:[]},
  SUPREMELEADERKYLOREN:{z:["Brutal Assault", "Furious Onslaught", "Galactic Legend", "Press the Advantage", "Stasis Strike", "Supreme Leader"],o:[]},
  T3_M4:{z:["Combat Logic Upgrade", "Master Gearhead"],o:["Master Gearhead"]},
  TALIA:{z:[],o:[]},
  TARFFUL:{z:["Better Together", "It's All in the Fur"],o:["It's All in the Fur"]},
  TARONMALICOS:{z:["Echo of the Fallen Order", "Strength is Power", "Vile Thrash"],o:["Die, Whelp!", "Echo of the Fallen Order", "Strength is Power"]},
  TEEBO:{z:[],o:[]},
  THEMANDALORIAN:{z:["Asset Acquisition", "Disciplined Bounty Hunter"],o:[]},
  THEMANDALORIANBESKARARMOR:{z:["Protective Intuition", "Seasoned Tactics"],o:[]},
  THIRDSISTER:{z:["Harbored Aggression", "Reckless Sweep", "Unyielding Onslaught"],o:["Driven by Revenge", "Harbored Aggression", "Reckless Sweep"]},
  TIEFIGHTERPILOT:{z:[],o:[]},
  TRENCH:{z:["Feared Tactician", "I Smell Fear, and It Smells Good", "Net Positive"],o:["Feared Tactician", "I Smell Fear, and It Smells Good", "Unfinished Business"]},
  TRIPLEZERO:{z:["Drain Organics"],o:["Specialized in Torture"]},
  TUSKENCHIEFTAIN:{z:["Ceremonial Dance", "Nomadic People"],o:["Nomadic People"]},
  TUSKENHUNTRESS:{z:["Centuries of Tradition", "Finishing Strikes"],o:["Centuries of Tradition"]},
  TUSKENRAIDER:{z:[],o:["Strength in Numbers"]},
  TUSKENSHAMAN:{z:[],o:[]},
  UGNAUGHT:{z:[],o:[]},
  UNDERCOVERLANDO:{z:["Covert Coordination"],o:["Agent On The Inside"]},
  URORRURRR:{z:[],o:[]},
  VADER:{z:["Inspiring Through Fear", "Merciless Massacre", "No Escape"],o:[]},
  VEERS:{z:["Aggressive Tactician"],o:[]},
  VISASMARR:{z:["Returned to the Light"],o:[]},
  WAMPA:{z:["Cornered Beast", "Furious Foe"],o:["Cornered Beast"]},
  WATTAMBOR:{z:["Mass Manufacture"],o:[]},
  WEDGEANTILLES:{z:[],o:[]},
  WICKET:{z:["Furtive Tactics"],o:[]},
  YOUNGCHEWBACCA:{z:["Ferocious Protector"],o:[]},
  YOUNGHAN:{z:["Ready For Anything"],o:[]},
  YOUNGLANDO:{z:["Perfect Timing"],o:[]},
  ZAALBAR:{z:["Mission's Guardian"],o:[]},
  ZAMWESELL:{z:["Shapeshifter"],o:["Shapeshifter"]},
  ZEBS3:{z:["Staggering Sweep"],o:[]},
  ZORIIBLISS_V2:{z:["Spice Runner Skills", "There's More of Us"],o:["There's More of Us"]},
};

// All ship names (70 ships, swgoh.gg April 2026)
const SHIP_NAMES = [
  'Ahsoka Tano\'s Jedi Starfighter',
  'Anakin\'s Eta-2 Starfighter',
  'B-28 Extinction-class Bomber',
  'BTL-B Y-wing Starfighter',
  'Biggs Darklighter\'s X-wing',
  'Bistan\'s U-wing',
  'Cassian\'s U-wing',
  'Chimaera',
  'Clone Sergeant\'s ARC-170',
  'Comeuppance',
  'Ebon Hawk',
  'Emperor\'s Shuttle',
  'Endurance',
  'Executor',
  'Executrix',
  'Finalizer',
  'First Order SF TIE Fighter',
  'First Order TIE Fighter',
  'Fury-class Interceptor',
  'Gauntlet Starfighter',
  'Geonosian Soldier\'s Starfighter',
  'Geonosian Spy\'s Starfighter',
  'Ghost',
  'Han\'s Millennium Falcon',
  'Home One',
  'Hound\'s Tooth',
  'Hyena Bomber',
  'IG-2000',
  'Imperial TIE Bomber',
  'Imperial TIE Fighter',
  'Jedi Consular\'s Starfighter',
  'Kylo Ren\'s Command Shuttle',
  'Lando\'s Millennium Falcon',
  'Leviathan',
  'MG-100 StarFortress SF-17',
  'Malevolence',
  'Marauder',
  'Mark VI Interceptor',
  'Negotiator',
  'Outrider',
  'Phantom II',
  'Plo Koon\'s Jedi Starfighter',
  'Poe Dameron\'s X-wing',
  'Profundity',
  'Punishing One',
  'Raddus',
  'Raven\'s Claw',
  'Razor Crest',
  'Rebel B-wing',
  'Rebel Y-wing',
  'Resistance X-wing',
  'Rex\'s ARC-170',
  'Rey\'s Millennium Falcon',
  'Rogue One',
  'Scimitar',
  'Scythe',
  'Sith Fighter',
  'Slave I',
  'Sun Fac\'s Geonosian Starfighter',
  'TIE Advanced x1',
  'TIE Dagger',
  'TIE Defender',
  'TIE Echelon',
  'TIE Reaper',
  'TIE Silencer',
  'TIE/IN Interceptor Prototype',
  'Umbaran Starfighter',
  'Vulture Droid',
  'Wedge Antilles\'s X-wing',
  'Xanadu Blood',
];

const EXTRA_UNIT_NAMES = {
  '4LOM':'4-LOM',
  APPO:'CC-1119 "Appo"',
  ASAJJDARKDISCIPLE:'Asajj Ventress (Dark Disciple)',
  BATCHERS3:'Batcher',
  BAYLANSKOLL:'Baylan Skoll',
  BRUTUS:'Brutus',
  CAPTAINENOCH:'Captain Enoch',
  CAPTAINSILVO:'Captain Silvo',
  CASSIANUNDERCOVER:'Cassian Andor (Undercover)',
  CINTA:'Cinta Kaz',
  CROSSHAIRS3:'Crosshair (Scarred)',
  DARKREY:'Rey (Dark Side Vision)',
  DEATHTROOPERPERIDEA:'Death Trooper (Peridea)',
  DEDRAMEERO:'Dedra Meero',
  DEPABILLABA:'Depa Billaba',
  DISGUISEDCLONETROOPER:'Disguised Clone Trooper',
  EZRAEXILE:'Ezra Bridger (Exile)',
  GENERALSYNDULLA:'General Syndulla',
  GLAHSOKATANO:'Ahsoka Tano',
  GLHONDO:'Pirate King Hondo Ohnaka',
  GREATMOTHERS:'Great Mothers',
  HUNTERS3:'Hunter (Mercenary)',
  HUYANG:'Huyang',
  IG90:'IG-90',
  INQUISITORBARRISS:'Inquisitor Barriss',
  ITHANO:'Captain Ithano',
  JEDIMASTERMACEWINDU:'Jedi Master Mace Windu',
  JOCASTANU:'Jocasta Nu',
  KIX:'Kix',
  KLEYA:'Kleya Marki',
  KXSECURITYDROID:'KX Security Droid',
  MAJORPARTAGAZ:'Major Partagaz',
  MARROK:'Marrok',
  MAULHATEFUELED:'Maul (Hate-Fueled)',
  MAZKANATA:'Maz Kanata',
  MORGANELSBETH:'Morgan Elsbeth',
  NIGHTTROOPER:'Night Trooper',
  OMEGAS3:'Omega (Fugitive)',
  OPERATIVE:'CX-2',
  PADAWANSABINE:'Padawan Sabine Wren',
  QUIGGOLD:'Quiggold',
  SCORCH:'RC-1262 "Scorch"',
  SHINHATI:'Shin Hati',
  SM33:'SM-33',
  STORMTROOPERLUKE:'Stormtrooper Luke',
  STRANGER:'The Stranger',
  VADERDUELSEND:"Darth Vader (Duel's End)",
  VANE:'Vane',
  VANGUARDTEMPLEGUARD:'Temple Guard',
  VEL:'Vel Sartha',
  WRECKERS3:'Wrecker (Mercenary)',
  YODACHEWBACCA:'Yoda & Chewie',
  ZUCKUSS:'Zuckuss',
};

const SHIP_NAME_BY_DEFID = {
  ARC170CLONESERGEANT:"Clone Sergeant's ARC-170",
  ARC170REX:"Rex's ARC-170",
  BWINGREBEL:'Rebel B-wing',
  CAPITALCHIMAERA:'Chimaera',
  CAPITALEXECUTOR:'Executor',
  CAPITALFINALIZER:'Finalizer',
  CAPITALJEDICRUISER:'Endurance',
  CAPITALLEVIATHAN:'Leviathan',
  CAPITALMALEVOLENCE:'Malevolence',
  CAPITALMONCALAMARICRUISER:'Home One',
  CAPITALNEGOTIATOR:'Negotiator',
  CAPITALPROFUNDITY:'Profundity',
  CAPITALRADDUS:'Raddus',
  CAPITALSTARDESTROYER:'Executrix',
  COMEUPPANCE:'Comeuppance',
  COMMANDSHUTTLE:"Kylo Ren's Command Shuttle",
  EBONHAWK:'Ebon Hawk',
  EMPERORSSHUTTLE:"Emperor's Shuttle",
  FIRSTORDERTIEECHELON:'TIE Echelon',
  FURYCLASSINTERCEPTOR:'Fury-class Interceptor',
  GAUNTLETSTARFIGHTER:'Gauntlet Starfighter',
  GEONOSIANSTARFIGHTER1:"Sun Fac's Geonosian Starfighter",
  GEONOSIANSTARFIGHTER2:"Geonosian Soldier's Starfighter",
  GEONOSIANSTARFIGHTER3:"Geonosian Spy's Starfighter",
  GHOST:'Ghost',
  HOUNDSTOOTH:"Hound's Tooth",
  HYENABOMBER:'Hyena Bomber',
  IG2000:'IG-2000',
  JEDISTARFIGHTERAHSOKATANO:"Ahsoka Tano's Jedi Starfighter",
  JEDISTARFIGHTERANAKIN:"Anakin's Eta-2 Starfighter",
  JEDISTARFIGHTERCONSULAR:"Jedi Consular's Starfighter",
  BLADEOFDORIN:"Plo Koon's Jedi Starfighter",
  MARAUDER:'Marauder',
  MG100STARFORTRESSSF17:'MG-100 StarFortress SF-17',
  MILLENNIUMFALCON:"Han's Millennium Falcon",
  MILLENNIUMFALCONEP7:"Rey's Millennium Falcon",
  MILLENNIUMFALCONPRISTINE:"Lando's Millennium Falcon",
  OUTRIDER:'Outrider',
  PHANTOM2:'Phantom II',
  PUNISHINGONE:'Punishing One',
  RAVENSCLAW:"Raven's Claw",
  RAZORCREST:'Razor Crest',
  ROGUEONESHIP:'Rogue One',
  SCYTHE:'Scythe',
  SITHBOMBER:'B-28 Extinction-class Bomber',
  SITHFIGHTER:'Sith Fighter',
  SITHINFILTRATOR:'Scimitar',
  SLAVE1:'Slave I',
  SITHSUPREMACYCLASS:'Mark VI Interceptor',
  TIEADVANCED:'TIE Advanced x1',
  TIEBOMBERIMPERIAL:'Imperial TIE Bomber',
  TIEDAGGER:'TIE Dagger',
  TIEDEFENDER:'TIE Defender',
  TIEFIGHTERFIRSTORDER:'First Order TIE Fighter',
  TIEFIGHTERFOSF:'First Order SF TIE Fighter',
  TIEFIGHTERIMPERIAL:'Imperial TIE Fighter',
  TIEINTERCEPTOR:'TIE/IN Interceptor Prototype',
  TIEREAPER:'TIE Reaper',
  TIESILENCER:'TIE Silencer',
  UMBARANSTARFIGHTER:'Umbaran Starfighter',
  UWINGROGUEONE:"Cassian's U-wing",
  UWINGSCARIF:"Bistan's U-wing",
  VULTUREDROID:'Vulture Droid',
  XANADUBLOOD:'Xanadu Blood',
  XWINGBLACKONE:"Poe Dameron's X-wing",
  XWINGRED2:"Wedge Antilles's X-wing",
  XWINGRED3:"Biggs Darklighter's X-wing",
  XWINGRESISTANCE:'Resistance X-wing',
  YWINGCLONEWARS:'BTL-B Y-wing Starfighter',
  YWINGREBEL:'Rebel Y-wing',
};

const CHARACTER_NAME_BY_DEFID = {
  ...UNIT_NAMES,
  ...EXTRA_UNIT_NAMES,
};

const PLAYABLE_NAME_BY_DEFID = {
  ...CHARACTER_NAME_BY_DEFID,
  ...SHIP_NAME_BY_DEFID,
};

// Sorted list of all playable character names (for datalists)
const ALL_CHAR_NAMES = [
  '0-0-0',
  '50R-T',
  'ARC Trooper',
  'Aayla Secura',
  'Admiral Ackbar',
  'Admiral Piett',
  'Admiral Raddus',
  'Admiral Trench',
  'Ahsoka Tano',
  'Ahsoka Tano (Fulcrum)',
  'Amilyn Holdo',
  'Asajj Ventress',
  'Aurra Sing',
  'B1 Battle Droid',
  'B2 Super Battle Droid',
  'BB-8',
  'BT-1',
  'Barriss Offee',
  'Bastila Shan',
  'Bastila Shan (Fallen)',
  'Baze Malbus',
  'Ben Solo',
  'Biggs Darklighter',
  'Bistan',
  'Bo-Katan (Mand\'alor)',
  'Bo-Katan Kryze',
  'Boba Fett',
  'Boba Fett, Scion of Jango',
  'Bodhi Rook',
  'Boss Nass',
  'Bossk',
  'Boushh (Leia Organa)',
  'C-3PO',
  'CC-2224 "Cody"',
  'CT-21-0408 "Echo"',
  'CT-5555 "Fives"',
  'CT-7567 "Rex"',
  'Cad Bane',
  'Cal Kestis',
  'Canderous Ordo',
  'Captain Drogan',
  'Captain Han Solo',
  'Captain Phasma',
  'Captain Rex',
  'Captain Tarpals',
  'Cara Dune',
  'Carth Onasi',
  'Cassian Andor',
  'Cere Junda',
  'Chewbacca',
  'Chief Chirpa',
  'Chief Nebit',
  'Chirrut Îmwe',
  'Chopper',
  'Clone Sergeant - Phase I',
  'Clone Wars Chewbacca',
  'Colonel Starck',
  'Commander Ahsoka Tano',
  'Commander Luke Skywalker',
  'Coruscant Underworld Police',
  'Count Dooku',
  'Dark Trooper',
  'Dark Trooper Moff Gideon',
  'Darth Bane',
  'Darth Malak',
  'Darth Malgus',
  'Darth Maul',
  'Darth Nihilus',
  'Darth Revan',
  'Darth Sidious',
  'Darth Sion',
  'Darth Talon',
  'Darth Traya',
  'Darth Vader',
  'Dash Rendar',
  'Dathcha',
  'Death Trooper',
  'Dengar',
  'Director Krennic',
  'Doctor Aphra',
  'Droideka',
  'Echo',
  'Eeth Koth',
  'Eighth Brother',
  'Embo',
  'Emperor Palpatine',
  'Enfys Nest',
  'Ewok Elder',
  'Ewok Scout',
  'Ezra Bridger',
  'Fennec Shand',
  'Fifth Brother',
  'Finn',
  'First Order Executioner',
  'First Order Officer',
  'First Order SF TIE Pilot',
  'First Order Stormtrooper',
  'First Order TIE Pilot',
  'Gamorrean Guard',
  'Gar Saxon',
  'Garazeb "Zeb" Orrelios',
  'General Grievous',
  'General Hux',
  'General Kenobi',
  'General Skywalker',
  'General Veers',
  'Geonosian Brood Alpha',
  'Geonosian Soldier',
  'Geonosian Spy',
  'Grand Admiral Thrawn',
  'Grand Inquisitor',
  'Grand Master Yoda',
  'Grand Moff Tarkin',
  'Greedo',
  'Greef Karga',
  'Gungan Boomadier',
  'Gungan Phalanx',
  'HK-47',
  'Han Solo',
  'Hera Syndulla',
  'Hermit Yoda',
  'Hondo Ohnaka',
  'Hoth Rebel Scout',
  'Hoth Rebel Soldier',
  'Hunter',
  'IG-100 MagnaGuard',
  'IG-11',
  'IG-12 & Grogu',
  'IG-86 Sentinel Droid',
  'IG-88',
  'Iden Versio',
  'Ima-Gun Di',
  'Imperial Probe Droid',
  'Imperial Super Commando',
  'Jabba the Hutt',
  'Jango Fett',
  'Jar Jar Binks',
  'Jawa',
  'Jawa Engineer',
  'Jawa Scavenger',
  'Jedi Consular',
  'Jedi Knight Anakin',
  'Jedi Knight Cal Kestis',
  'Jedi Knight Guardian',
  'Jedi Knight Luke Skywalker',
  'Jedi Knight Revan',
  'Jedi Master Kenobi',
  'Jedi Master Luke Skywalker',
  'Jolee Bindo',
  'Juhani',
  'Jyn Erso',
  'K-2SO',
  'Kanan Jarrus',
  'Kelleran Beq',
  'Ki-Adi-Mundi',
  'Kit Fisto',
  'Krrsantan',
  'Kuiil',
  'Kyle Katarn',
  'Kylo Ren',
  'Kylo Ren (Unmasked)',
  'L3-37',
  'Lando Calrissian',
  'Leia Organa',
  'Lobot',
  'Logray',
  'Lord Vader',
  'Luke Skywalker (Farmboy)',
  'Luminara Unduli',
  'Luthen Rael',
  'Mace Windu',
  'Magmatrooper',
  'Mara Jade, The Emperor\'s Hand',
  'Master Qui-Gon',
  'Maul',
  'Merrin',
  'Mission Vao',
  'Mob Enforcer',
  'Moff Gideon',
  'Mon Mothma',
  'Mother Talzin',
  'Nightsister Acolyte',
  'Nightsister Initiate',
  'Nightsister Spirit',
  'Nightsister Zombie',
  'Ninth Sister',
  'Nute Gunray',
  'Obi-Wan Kenobi (Old Ben)',
  'Old Daka',
  'Omega',
  'Padawan Obi-Wan',
  'Padmé Amidala',
  'Pao',
  'Paploo',
  'Paz Vizsla',
  'Plo Koon',
  'Poe Dameron',
  'Poggle the Lesser',
  'Princess Kneesaa',
  'Princess Leia',
  'Qi\'ra',
  'Queen Amidala',
  'Qui-Gon Jinn',
  'R2-D2',
  'Range Trooper',
  'Rebel Officer Leia Organa',
  'Resistance Hero Finn',
  'Resistance Hero Poe',
  'Resistance Pilot',
  'Resistance Trooper',
  'Rey',
  'Rey (Jedi Training)',
  'Rey (Scavenger)',
  'Rose Tico',
  'Royal Guard',
  'STAP',
  'Sabine Wren',
  'Sana Starros',
  'Savage Opress',
  'Saw Gerrera',
  'Scarif Rebel Pathfinder',
  'Scout Trooper',
  'Second Sister',
  'Seventh Sister',
  'Shaak Ti',
  'Shoretrooper',
  'Sith Assassin',
  'Sith Empire Trooper',
  'Sith Eternal Emperor',
  'Sith Marauder',
  'Sith Trooper',
  'Skiff Guard (Lando Calrissian)',
  'Snowtrooper',
  'Starkiller',
  'Stormtrooper',
  'Stormtrooper Han',
  'Sun Fac',
  'Supreme Leader Kylo Ren',
  'T3-M4',
  'TIE Fighter Pilot',
  'Talia',
  'Tarfful',
  'Taron Malicos',
  'Tech',
  'Teebo',
  'The Armorer',
  'The Mandalorian',
  'The Mandalorian (Beskar Armor)',
  'Third Sister',
  'Threepio & Chewie',
  'Tusken Chieftain',
  'Tusken Raider',
  'Tusken Shaman',
  'Tusken Warrior',
  'URoRRuR\'R\'R',
  'Ugnaught',
  'Vandor Chewbacca',
  'Veteran Smuggler Chewbacca',
  'Veteran Smuggler Han Solo',
  'Visas Marr',
  'Wampa',
  'Wat Tambor',
  'Wedge Antilles',
  'Wicket',
  'Wrecker',
  'Young Han Solo',
  'Young Lando Calrissian',
  'Zaalbar',
  'Zam Wesell',
  'Zorii Bliss',
];
// backwards-compat alias
const _KNOWN_NAMES = UNIT_NAMES;

 // backwards-compat alias

const UNIT_NAME_ALIASES = {
  'bam': 'THEMANDALORIANBESKARARMOR',
  'mando (beskar)': 'THEMANDALORIANBESKARARMOR',
  'mando beskar': 'THEMANDALORIANBESKARARMOR',
  'bo-katan mandalor': 'MANDALORBOKATAN',
  'bo-katan mand\'alor': 'MANDALORBOKATAN',
  'bo-katan (mand\'alor)': 'MANDALORBOKATAN',
  'dtmg': 'MOFFGIDEONS3',
  'dark rey': 'DARKREY',
  'rey (dark side vision)': 'DARKREY',
  'padme amidala': 'PADMEAMIDALA',
  'blade of dorin': 'BLADEOFDORIN',
  'plo koon\'s jedi starfighter': 'BLADEOFDORIN',
  'plokoonsjedistarfighter': 'BLADEOFDORIN',
  'sun fac\'s geonosian starfighter': 'GEONOSIANSTARFIGHTER1',
  'geonosian soldier\'s starfighter': 'GEONOSIANSTARFIGHTER2',
  'geonosian spy\'s starfighter': 'GEONOSIANSTARFIGHTER3',
  'btl-b y-wing starfighter': 'YWINGCLONEWARS',
  'rebel y-wing': 'YWINGREBEL',
  'scythe': 'SCYTHE',
  'omega (fugitive)': 'OMEGAS3',
  'padawan sabine wren': 'PADAWANSABINE',
  'sabine wren (padawan)': 'PADAWANSABINE',
  'rc-1262 "scorch"': 'SCORCH',
  'rc-1262 scorch': 'SCORCH',
  'temple guard': 'VANGUARDTEMPLEGUARD',
  'vanguard temple guard': 'VANGUARDTEMPLEGUARD',
  'wrecker (mercenary)': 'WRECKERS3',
  'omega': 'BADBATCHOMEGA',
  'wrecker': 'BADBATCHWRECKER',
};

const KNOWN_SHIP_DEFIDS = new Set([
  'AHSOKATANOSTARFIGHTER','ANAKINSETA2STARFIGHTER','BIGGSDARKLIGHTERSXWING',
  'BISTANSUWING','CASSIANSUWING','CHIMAERA','EXECUTOR','EXECUTRIX','FINALIZER',
  'FURYCLASSINTERCEPTOR','GAUNTLETSTARFIGHTER','GHOST','HANSMILLENNIUMFALCON',
  'HOMEONE','HOUNDSTOOTH','HYENABOMBER','IG2000','IMPERIALTIEBOMBER',
  'IMPERIALTIEFIGHTER','KYLORENCOMMANDSHUTTLE','LANDOSMILLENNIUMFALCON',
  'LEVIATHAN','MALEVOLENCE','MARAUDER','NEGOTIATOR','OUTRIDER','PHANTOMII',
  'PLOKOONSTARFIGHTER','POEXWING','PROFUNDITY','PUNISHINGONE','RADDUS',
  'RAVENSCLAW','RAZORCREST','REBELBWING','REBELYWING','RESISTANCEXWING',
  'REYSMILLENNIUMFALCON','SCIMITAR','SCYTHE','SITHFIGHTER','SLAVEI',
  'SUNFACGEONOSIANSTARFIGHTER','TIEADVANCEDX1','TIEDAGGER','TIEDEFENDER',
  'TIEECHELON','TIEREAPER','TIESILENCER','UMBARAN','VULTUREDROID',
  'WEDGEXWING','XANADUBLOOD','EBONHAWK','COMEUPPANCE','ENDURANCE',
  'MARKVINTERCEPTOR'
].concat(Object.keys(SHIP_NAME_BY_DEFID).map(defIdKey)));

const KNOWN_CHARACTER_DEFIDS = new Set(
  Object.keys(CHARACTER_NAME_BY_DEFID).map(defIdKey)
);

let _unitNameIndex = null;

function normalizeDefId(defId){
  return String(defId||'').split(':')[0].trim();
}

function defIdKey(defId){
  return normalizeDefId(defId).toUpperCase().replace(/_/g,'');
}

function normalizeUnitName(name){
  return String(name||'')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g,'')
    .toLowerCase()
    .replace(/&/g,' and ')
    .replace(/[^a-z0-9]+/g,'')
    .trim();
}

function defIdToName(defId, nameKeyHint) {
  // 1. Exact Base ID match (270 chars from swgoh.gg, authoritative)
  const raw = (defId || '').split(':')[0].trim();
  if (UNIT_NAMES[raw])              return UNIT_NAMES[raw];
  // 2. Uppercase
  const upper = raw.toUpperCase();
  if (UNIT_NAMES[upper])            return UNIT_NAMES[upper];
  // 3. Strip underscores then uppercase (e.g. AURRA_SING → AURRASING)
  const noUnd = upper.replace(/_/g,'');
  if (UNIT_NAMES[noUnd])            return UNIT_NAMES[noUnd];
  // 4. nameKey hint from API if it looks like a real name
  if (nameKeyHint && nameKeyHint.length > 2 && !/^[A-Z0-9_:]+$/.test(nameKeyHint))
    return nameKeyHint;
  // 5. Fallback: space-insertion best-effort
  return raw.replace(/_/g,' ')
    .replace(/([a-z])([A-Z])/g,'$1 $2')
    .split(' ').filter(Boolean)
    .map(w=>w.charAt(0).toUpperCase()+w.slice(1).toLowerCase())
    .join(' ') || defId || '(unknown)';
}

function inferUnitCombatType(unit){
  const ct = Number(unit?.combatType);
  if(ct === 1 || ct === 2) return ct;
  if(typeof unit?.modsPresent === 'boolean') return unit.modsPresent ? 1 : 2;
  return KNOWN_SHIP_DEFIDS.has(defIdKey(unit?.defId||unit?.baseId)) ? 2 : 1;
}

function isShipUnit(unit){
  return inferUnitCombatType(unit) === 2;
}

function normalizeRosterUnit(unit){
  if(!unit || typeof unit !== 'object') return unit;
  const defId = normalizeDefId(unit.defId || unit.baseId);
  return {...unit, defId, combatType: inferUnitCombatType(unit), power: Number(unit.power)||0};
}

function normalizeGuildRostersData(rosters){
  const out = {};
  Object.entries(rosters||{}).forEach(([allyCode, roster])=>{
    out[String(allyCode)] = Array.isArray(roster) ? roster.map(normalizeRosterUnit) : [];
  });
  return out;
}

function defIdToName(defId, nameKeyHint) {
  const raw = normalizeDefId(defId);
  const upper = raw.toUpperCase();
  const noUnd = upper.replace(/_/g,'');
  if (PLAYABLE_NAME_BY_DEFID[raw])   return PLAYABLE_NAME_BY_DEFID[raw];
  if (PLAYABLE_NAME_BY_DEFID[upper]) return PLAYABLE_NAME_BY_DEFID[upper];
  if (PLAYABLE_NAME_BY_DEFID[noUnd]) return PLAYABLE_NAME_BY_DEFID[noUnd];
  if (nameKeyHint && nameKeyHint.length > 2 && !/^[A-Z0-9_:]+$/.test(nameKeyHint))
    return nameKeyHint;
  return raw.replace(/_/g,' ')
    .replace(/([a-z])([A-Z])/g,'$1 $2')
    .split(' ').filter(Boolean)
    .map(w=>w.charAt(0).toUpperCase()+w.slice(1).toLowerCase())
    .join(' ') || defId || '(unknown)';
}

function inferUnitCombatType(unit){
  const key = defIdKey(unit?.defId||unit?.baseId);
  if(KNOWN_SHIP_DEFIDS.has(key)) return 2;
  if(KNOWN_CHARACTER_DEFIDS.has(key)) return 1;
  const ct = Number(unit?.combatType);
  if(ct === 1 || ct === 2) return ct;
  if(typeof unit?.name === 'string'){
    const normalizedName = normalizeUnitName(unit.name);
    const mapped = (_unitNameIndex || rebuildUnitNameIndex())[normalizedName];
    const candidate = Array.isArray(mapped) ? mapped[0] : mapped;
    if(candidate){
      const candidateKey = defIdKey(candidate);
      if(KNOWN_SHIP_DEFIDS.has(candidateKey)) return 2;
      if(KNOWN_CHARACTER_DEFIDS.has(candidateKey)) return 1;
    }
  }
  return 1;
}

function normalizeRosterUnit(unit){
  if(!unit || typeof unit !== 'object') return unit;
  const defId = normalizeDefId(unit.defId || unit.baseId);
  return {...unit, defId, combatType: inferUnitCombatType(unit), power: Number(unit.power)||0};
}

function unitMatchesDefId(unit, defId){
  const target = normalizeDefId(defId).toUpperCase();
  return !!target && normalizeDefId(unit?.defId).toUpperCase() === target;
}

function _addUnitNameIndex(index, name, defId){
  const cleanName = normalizeUnitName(name);
  const cleanDefId = normalizeDefId(defId).toUpperCase();
  if(!cleanName || !cleanDefId) return;
  const existing = index[cleanName];
  if(!existing){
    index[cleanName] = cleanDefId;
    return;
  }
  if(existing === cleanDefId) return;
  if(Array.isArray(existing)){
    if(!existing.includes(cleanDefId)) existing.push(cleanDefId);
    return;
  }
  index[cleanName] = [existing, cleanDefId];
}

function rebuildUnitNameIndex(){
  const index = {};
  Object.entries(PLAYABLE_NAME_BY_DEFID).forEach(([defId, name])=>_addUnitNameIndex(index, name, defId));
  Object.entries(UNIT_NAME_ALIASES).forEach(([name, defId])=>_addUnitNameIndex(index, name, defId));
  Object.values(guildRosters).forEach(roster=>{
    (roster||[]).forEach(unit=>{
      const defId = normalizeDefId(unit?.defId);
      const name = defIdToName(defId, unit?.name);
      _addUnitNameIndex(index, name, defId);
    });
  });
  _unitNameIndex = index;
  return index;
}

function resolveUnitNameToDefId(name){
  const rawDefId = normalizeDefId(name).toUpperCase();
  if(rawDefId && (PLAYABLE_NAME_BY_DEFID[rawDefId] || UNIT_ABILITIES[rawDefId])) return rawDefId;
  const aliasMatch = UNIT_NAME_ALIASES[normalizeUnitName(name)];
  if(aliasMatch) return normalizeDefId(aliasMatch).toUpperCase();
  const match = (_unitNameIndex || rebuildUnitNameIndex())[normalizeUnitName(name)];
  if(Array.isArray(match)) return match.length === 1 ? match[0] : '';
  return match || '';
}

function findRosterUnitByRef(roster, displayName, defId){
  if(!Array.isArray(roster)) return null;
  const resolvedDefId = normalizeDefId(defId || resolveUnitNameToDefId(displayName)).toUpperCase();
  if(resolvedDefId){
    const byDefId = roster.find(unit=>unitMatchesDefId(unit, resolvedDefId));
    if(byDefId) return byDefId;
  }
  const targetName = normalizeUnitName(displayName);
  if(!targetName) return null;
  return roster.find(unit=>
    normalizeUnitName(defIdToName(normalizeDefId(unit?.defId), unit?.name)) === targetName
  ) || null;
}

function normalizeGuideSquad(squad){
  const source = (squad && typeof squad === 'object') ? squad : {};
  const leaderRaw = source.leader;
  let leader = typeof leaderRaw === 'string'
    ? leaderRaw.trim()
    : String(leaderRaw?.name || leaderRaw?.label || '').trim();
  const leaderDefId = normalizeDefId(
    source.leaderDefId ||
    leaderRaw?.defId ||
    leaderRaw?.id ||
    resolveUnitNameToDefId(leader)
  ).toUpperCase();
  if(!leader && leaderDefId) leader = defIdToName(leaderDefId, '');

  const rawMembers = Array.isArray(source.members) ? source.members.slice(0, GUIDE_FLEET_MEMBER_INPUT_IDS.length) : [];
  const rawMemberDefIds = Array.isArray(source.memberDefIds) ? source.memberDefIds.slice(0, GUIDE_FLEET_MEMBER_INPUT_IDS.length) : [];
  const members = [];
  const memberDefIds = [];
  let lastFilledMemberIdx = -1;

  for(let idx = 0; idx < Math.max(rawMembers.length, rawMemberDefIds.length); idx++){
    const member = rawMembers[idx];
    const rawDefId = rawMemberDefIds[idx];
    const memberName = typeof member === 'string'
      ? member.trim()
      : String(member?.name || member?.label || '').trim();
    const memberDefId = normalizeDefId(
      rawDefId ||
      member?.defId ||
      member?.id ||
      resolveUnitNameToDefId(memberName)
    ).toUpperCase();
    if(memberName || memberDefId) lastFilledMemberIdx = idx;
  }

  for(let idx = 0; idx <= lastFilledMemberIdx; idx++){
    const member = rawMembers[idx];
    const memberName = typeof member === 'string'
      ? member.trim()
      : String(member?.name || member?.label || '').trim();
    const memberDefId = normalizeDefId(
      rawMemberDefIds[idx] ||
      member?.defId ||
      member?.id ||
      resolveUnitNameToDefId(memberName)
    ).toUpperCase();
    const displayName = memberName || (memberDefId ? defIdToName(memberDefId, '') : '');
    members.push(displayName || '');
    memberDefIds.push(memberDefId);
  }

  const validUnitKeys = new Set(
    [leaderDefId].concat(memberDefIds).map(defIdKey).filter(Boolean)
  );
  const requiredTbOmicrons = [];
  const seenTbOmicrons = new Set();
  (Array.isArray(source.requiredTbOmicrons) ? source.requiredTbOmicrons : []).forEach(entry=>{
    const normalized = normalizeGuideTbOmicronRequirement(entry);
    if(!normalized) return;
    if(!validUnitKeys.has(defIdKey(normalized.unitDefId))) return;
    const key = defIdKey(normalized.unitDefId) + '|' + normalizeGuideSkillKey(normalized.skillId);
    if(seenTbOmicrons.has(key)) return;
    seenTbOmicrons.add(key);
    requiredTbOmicrons.push(normalized);
  });

  return {
    ...source,
    id: source.id || (Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,7)),
    leader,
    leaderDefId,
    members,
    memberDefIds,
    notes: String(source.notes || '').trim(),
    videoUrl: normalizeExternalUrl(source.videoUrl),
    requiredTbOmicrons,
    difficulty: source.difficulty || 'auto',
    order: Number.isFinite(source.order) ? source.order : 0,
  };
}

function normalizeGuideData(data){
  const source = (data && typeof data === 'object') ? data : {};
  const squads = {};
  Object.entries(source.squads || {}).forEach(([key, value])=>{
    squads[key] = Array.isArray(value) ? value.map(normalizeGuideSquad) : [];
  });
  return {version:2, squads};
}

function refreshGuideUnitLinks(){
  guideData = normalizeGuideData(guideData);
}

function getPlanetMetaById(pid){
  return ALL_PLANETS.find(p=>p.id===pid) || BONUS_PLANETS.find(p=>p.id===pid) || null;
}

function getGuildMemberNameMap(){
  const summary = getCurrentGuildSummary();
  const out = {};
  (summary?.members || []).forEach(member=>{
    const allyCode = String(member?._resolvedAllyCode || getMemberAllyCode(member) || '').trim();
    if(!allyCode) return;
    out[allyCode] = member?._resolvedName || getMemberName(member) || allyCode;
  });
  return out;
}

function allyCodeToMemberName(allyCode){
  const key = String(allyCode || '').trim();
  if(!key) return '';
  return getGuildMemberNameMap()[key] || key;
}

function aggregateOpsRequirements(platoon){
  const needs = {};
  (platoon||[]).forEach(slot=>{
    const defId = resolveOpsRequirementDefId(
      slot?.defId || slot?.unitDefId || slot?.baseId,
      slot?.name
    );
    if(!defId) return;
    const combatType = inferUnitCombatType({defId});
    const minRarity = Math.max(1, Number(slot?.minRarity ?? slot?.requiredRarity ?? 7) || 7);
    const minRelic = combatType === 2 ? 0 : Math.max(0, Number(slot?.minRelic ?? slot?.requiredRelic ?? 0) || 0);
    const key = [defId.toUpperCase(), minRarity, minRelic].join('|');
    if(!needs[key]){
      needs[key] = {
        key,
        defId: defId.toUpperCase(),
        name: defIdToName(defId, slot?.name),
        need: 0,
        minRarity,
        minRelic,
        combatType
      };
    }
    needs[key].need += 1;
  });
  return Object.values(needs).sort((a,b)=>
    (a.minRelic - b.minRelic)
    || (a.need - b.need)
    || a.name.localeCompare(b.name)
  );
}

function resolveOpsRequirementDefId(defId, displayName){
  const normalized = normalizeDefId(defId).toUpperCase();
  if(normalized && !normalized.startsWith('WIKI_')) return normalized;
  const resolved = normalizeDefId(resolveUnitNameToDefId(displayName)).toUpperCase();
  if(resolved) return resolved;
  const fallback = normalizeUnitName(displayName);
  return fallback ? ('WIKI_' + fallback.toUpperCase()) : normalized;
}

function normalizeOperationsDefinitionsData(rawDefs){
  const out = {};
  Object.entries(rawDefs||{}).forEach(([pid, rawPlanet])=>{
    const meta = getPlanetMetaById(pid) || {};
    const rawPlatoons = Array.isArray(rawPlanet?.platoons) ? rawPlanet.platoons : (Array.isArray(rawPlanet) ? rawPlanet : []);
    const platoons = rawPlatoons.map((rawPlatoon, idx)=>{
      const requirements = Array.isArray(rawPlatoon?.requirements)
        ? rawPlatoon.requirements.map(req=>{
            const defId = resolveOpsRequirementDefId(req?.defId, req?.name);
            const combatType = inferUnitCombatType({defId});
            return {
              key: req?.key || [defId, Number(req?.minRarity)||7, combatType===2?0:(Number(req?.minRelic)||0)].join('|'),
              defId,
              name: defIdToName(defId, req?.name),
              need: Math.max(1, Number(req?.need)||1),
              minRarity: Math.max(1, Number(req?.minRarity)||7),
              minRelic: combatType===2 ? 0 : Math.max(0, Number(req?.minRelic)||0),
              combatType
            };
          })
        : aggregateOpsRequirements(rawPlatoon);
      const totalSlots = Number(rawPlatoon?.totalSlots)
        || requirements.reduce((sum, req)=>sum + (Number(req.need)||0), 0);
      return {
        id: Number(rawPlatoon?.id) || (idx + 1),
        totalSlots,
        requirements,
        rewardPts: Number(rawPlatoon?.rewardPts) || Number(meta.opsVal) || 0
      };
    }).filter(platoon=>platoon.requirements.length > 0);
    if(platoons.length){
      out[pid] = {
        planetId: pid,
        name: meta.name || pid,
        zone: Number(meta.zone)||0,
        align: meta.align || '',
        opsVal: Number(meta.opsVal)||0,
        platoons
      };
    }
  });
  return out;
}

function invalidateOperationsCaches(){
  _opsPoolByDefId = null;
  _lastPlanResult = null;
  _lastPlanStars = null;
  _greedyGenomeCache = null;
}

function buildOpsCandidatePool(){
  const pool = {};
  Object.entries(guildRosters||{}).forEach(([allyCode, roster])=>{
    (roster||[]).forEach(rawUnit=>{
      const unit = normalizeRosterUnit(rawUnit);
      const defId = normalizeDefId(unit?.defId);
      if(!defId) return;
      const combatType = inferUnitCombatType(unit);
      const entry = {
        key: String(allyCode)+'|'+defId.toUpperCase(),
        allyCode: String(allyCode),
        defId: defId.toUpperCase(),
        name: defIdToName(defId, unit?.name),
        rarity: Number(unit?.rarity)||0,
        relic: combatType===2 ? 0 : (Number(unit?.relic)||0),
        combatType
      };
      if(!pool[entry.defId]) pool[entry.defId] = [];
      pool[entry.defId].push(entry);
    });
  });
  Object.values(pool).forEach(list=>{
    list.sort((a,b)=>
      (a.rarity - b.rarity)
      || (a.relic - b.relic)
      || String(a.allyCode).localeCompare(String(b.allyCode))
    );
  });
  _opsPoolByDefId = pool;
  return pool;
}

function getOpsCandidatePool(){
  return _opsPoolByDefId || buildOpsCandidatePool();
}

function hasOperationsDefinitions(){
  return !!Object.keys(_opsDefinitions||{}).length;
}

function createOperationsSimState(detailed=false){
  const planets = {};
  Object.entries(_opsDefinitions||{}).forEach(([pid, planet])=>{
    planets[pid] = {
      completedPlatoons: 0,
      completedPoints: 0,
      platoons: planet.platoons.map(platoon=>({
        completed: false,
        completedDay: 0,
        filled: platoon.requirements.map(()=>0),
        assignments: detailed ? platoon.requirements.map(()=>[]) : null
      }))
    };
  });
  return {planets};
}

function getOpsRequirementRemaining(platoonState, reqIdx, requirement){
  return Math.max(0, (Number(requirement?.need)||0) - (Number(platoonState?.filled?.[reqIdx])||0));
}

function getPotentialOpsCandidates(requirement){
  const defId = normalizeDefId(requirement?.defId).toUpperCase();
  const pool = getOpsCandidatePool()[defId] || [];
  return pool.filter(candidate=>{
    if(candidate.rarity < (Number(requirement?.minRarity)||0)) return false;
    if((Number(requirement?.combatType)||inferUnitCombatType({defId})) === 1
      && candidate.relic < (Number(requirement?.minRelic)||0)) return false;
    return true;
  });
}

function canEventuallyCompletePlatoon(pid, platoonIdx, opsState){
  const planetDef = _opsDefinitions[pid];
  const planetState = opsState?.planets?.[pid];
  if(!planetDef || !planetState) return false;
  const platoonDef = planetDef.platoons[platoonIdx];
  const platoonState = planetState.platoons[platoonIdx];
  if(!platoonDef || !platoonState) return false;
  if(platoonState.completed) return true;
  return platoonDef.requirements.every((requirement, reqIdx)=>{
    const remaining = getOpsRequirementRemaining(platoonState, reqIdx, requirement);
    if(remaining <= 0) return true;
    return getPotentialOpsCandidates(requirement).length >= remaining;
  });
}

function getAssignableOpsCandidates(requirement, assignedUnits, planetUsage){
  const defId = normalizeDefId(requirement?.defId).toUpperCase();
  const pool = getOpsCandidatePool()[defId] || [];
  return pool.filter(candidate=>{
    if(assignedUnits.has(candidate.key)) return false;
    if(candidate.rarity < (Number(requirement?.minRarity)||0)) return false;
    if((Number(requirement?.combatType)||inferUnitCombatType({defId})) === 1
      && candidate.relic < (Number(requirement?.minRelic)||0)) return false;
    return (planetUsage[candidate.allyCode] || 0) < OPS_MEMBER_DAILY_CAP;
  });
}

function chooseBestOpsCandidate(candidates, requirement, planetUsage){
  return [...candidates].sort((a,b)=>{
    const usageDiff = (planetUsage[a.allyCode]||0) - (planetUsage[b.allyCode]||0);
    if(usageDiff) return usageDiff;
    const needsRelic = (Number(requirement?.combatType)||inferUnitCombatType({defId:requirement?.defId})) === 1;
    if(needsRelic && a.relic !== b.relic) return a.relic - b.relic;
    if(a.rarity !== b.rarity) return a.rarity - b.rarity;
    return a.name.localeCompare(b.name) || String(a.allyCode).localeCompare(String(b.allyCode));
  })[0] || null;
}

function previewPlatoonCompletion(pid, platoonIdx, opsState, dayUsage, planetUsage, day){
  const planetDef = _opsDefinitions[pid];
  const planetState = opsState?.planets?.[pid];
  if(!planetDef || !planetState) return null;
  const platoonDef = planetDef.platoons[platoonIdx];
  const platoonState = planetState.platoons[platoonIdx];
  if(!platoonDef || !platoonState || platoonState.completed) return null;
  const tempAssigned = new Set(dayUsage?.assignedUnits || []);
  const tempUsage = {...planetUsage};
  const reqOrder = platoonDef.requirements.map((requirement, reqIdx)=>({
    requirement,
    reqIdx,
    remaining: getOpsRequirementRemaining(platoonState, reqIdx, requirement)
  })).filter(entry=>entry.remaining > 0);
  reqOrder.sort((a,b)=>{
    const aAvail = getAssignableOpsCandidates(a.requirement, tempAssigned, tempUsage).length;
    const bAvail = getAssignableOpsCandidates(b.requirement, tempAssigned, tempUsage).length;
    return (aAvail - bAvail)
      || (a.remaining - b.remaining)
      || a.requirement.name.localeCompare(b.requirement.name);
  });
  const assignments = [];
  for(const entry of reqOrder){
    for(let i=0; i<entry.remaining; i++){
      const candidates = getAssignableOpsCandidates(entry.requirement, tempAssigned, tempUsage);
      const chosen = chooseBestOpsCandidate(candidates, entry.requirement, tempUsage);
      if(!chosen) return null;
      tempAssigned.add(chosen.key);
      tempUsage[chosen.allyCode] = (tempUsage[chosen.allyCode] || 0) + 1;
      assignments.push({
        day,
        reqIdx: entry.reqIdx,
        defId: entry.requirement.defId,
        name: entry.requirement.name,
        minRelic: entry.requirement.minRelic,
        minRarity: entry.requirement.minRarity,
        allyCode: chosen.allyCode,
        unitKey: chosen.key
      });
    }
  }
  return assignments;
}

function applyOpsAssignments(pid, platoonIdx, opsState, dayUsage, planetUsage, assignments, detailed=false){
  if(!assignments || !assignments.length) return {slotsFilled:0, completed:false, pointsEarned:0, assignments:[]};
  const planetDef = _opsDefinitions[pid];
  const planetState = opsState.planets[pid];
  const platoonDef = planetDef.platoons[platoonIdx];
  const platoonState = planetState.platoons[platoonIdx];
  let slotsFilled = 0;
  assignments.forEach(assignment=>{
    dayUsage.assignedUnits.add(assignment.unitKey);
    planetUsage[assignment.allyCode] = (planetUsage[assignment.allyCode] || 0) + 1;
    platoonState.filled[assignment.reqIdx] = (platoonState.filled[assignment.reqIdx] || 0) + 1;
    if(detailed && Array.isArray(platoonState.assignments?.[assignment.reqIdx])){
      platoonState.assignments[assignment.reqIdx].push({
        allyCode: assignment.allyCode,
        unitKey: assignment.unitKey,
        day: assignment.day
      });
    }
    slotsFilled += 1;
  });
  const completed = platoonDef.requirements.every((requirement, reqIdx)=>
    (platoonState.filled[reqIdx] || 0) >= (Number(requirement.need)||0)
  );
  if(completed && !platoonState.completed){
    platoonState.completed = true;
    platoonState.completedDay = assignments[0]?.day || 0;
    planetState.completedPlatoons += 1;
    planetState.completedPoints += Number(platoonDef.rewardPts)||0;
  }
  return {
    slotsFilled,
    completed,
    pointsEarned: completed ? (Number(platoonDef.rewardPts)||0) : 0,
    assignments
  };
}

function fillPlatoonPartially(pid, platoonIdx, opsState, dayUsage, planetUsage, day, detailed=false){
  const planetDef = _opsDefinitions[pid];
  const planetState = opsState?.planets?.[pid];
  if(!planetDef || !planetState) return {slotsFilled:0, completed:false, pointsEarned:0, assignments:[]};
  const platoonDef = planetDef.platoons[platoonIdx];
  const platoonState = planetState.platoons[platoonIdx];
  if(!platoonDef || !platoonState || platoonState.completed) return {slotsFilled:0, completed:false, pointsEarned:0, assignments:[]};
  const reqOrder = platoonDef.requirements.map((requirement, reqIdx)=>({
    requirement,
    reqIdx,
    remaining: getOpsRequirementRemaining(platoonState, reqIdx, requirement)
  })).filter(entry=>entry.remaining > 0);
  reqOrder.sort((a,b)=>{
    const aAvail = getAssignableOpsCandidates(a.requirement, dayUsage.assignedUnits, planetUsage).length;
    const bAvail = getAssignableOpsCandidates(b.requirement, dayUsage.assignedUnits, planetUsage).length;
    return (aAvail - bAvail)
      || (b.remaining - a.remaining)
      || a.requirement.name.localeCompare(b.requirement.name);
  });
  const assignments = [];
  reqOrder.forEach(entry=>{
    let remaining = getOpsRequirementRemaining(platoonState, entry.reqIdx, entry.requirement);
    while(remaining > 0){
      const candidates = getAssignableOpsCandidates(entry.requirement, dayUsage.assignedUnits, planetUsage);
      const chosen = chooseBestOpsCandidate(candidates, entry.requirement, planetUsage);
      if(!chosen) break;
      assignments.push({
        day,
        reqIdx: entry.reqIdx,
        defId: entry.requirement.defId,
        name: entry.requirement.name,
        minRelic: entry.requirement.minRelic,
        minRarity: entry.requirement.minRarity,
        allyCode: chosen.allyCode,
        unitKey: chosen.key
      });
      dayUsage.assignedUnits.add(chosen.key);
      planetUsage[chosen.allyCode] = (planetUsage[chosen.allyCode] || 0) + 1;
      platoonState.filled[entry.reqIdx] = (platoonState.filled[entry.reqIdx] || 0) + 1;
      if(detailed && Array.isArray(platoonState.assignments?.[entry.reqIdx])){
        platoonState.assignments[entry.reqIdx].push({
          allyCode: chosen.allyCode,
          unitKey: chosen.key,
          day
        });
      }
      remaining -= 1;
    }
  });
  const completed = platoonDef.requirements.every((requirement, reqIdx)=>
    (platoonState.filled[reqIdx] || 0) >= (Number(requirement.need)||0)
  );
  let pointsEarned = 0;
  if(completed && !platoonState.completed){
    platoonState.completed = true;
    platoonState.completedDay = day;
    planetState.completedPlatoons += 1;
    planetState.completedPoints += Number(platoonDef.rewardPts)||0;
    pointsEarned = Number(platoonDef.rewardPts)||0;
  }
  return {slotsFilled: assignments.length, completed, pointsEarned, assignments};
}

function buildOperationsDayPriorities(dayPlan, bonusPlanets=[]){
  const priorities = [];
  OPT_CKEYS.forEach(chainKey=>{
    const chain = dayPlan?.chains?.[chainKey];
    if(!chain?.planet) return;
    const stars = Number(chain.stars)||0;
    const priority = chain.status === 'preload'
      ? 10
      : chain.status === 'commit'
        ? (stars >= 3 ? 130 : stars >= 2 ? 120 : 110)
        : 20;
    priorities.push({
      pid: chain.planet.id,
      priority,
      label: chain.status === 'preload' ? 'Preload' : ('Commit ' + Math.max(1, stars) + '★')
    });
  });
  (bonusPlanets||[]).forEach(bp=>{
    if(!bp?.planet?.id) return;
    priorities.push({pid: bp.planet.id, priority: 5, label:'Bonus'});
  });
  return priorities.sort((a,b)=>b.priority - a.priority || a.pid.localeCompare(b.pid));
}

function allocateOperationsForDay(day, dayPlan, opsState, detailed=false){
  if(!hasOperationsDefinitions() || !scannedRosterCount()) return {pointsEarned:0, completedPlatoons:[], slotsFilled:0, planets:{}};
  const priorities = buildOperationsDayPriorities(dayPlan, dayPlan?.bonusPlanets || []);
  const dayUsage = {assignedUnits:new Set()};
  const summary = {pointsEarned:0, completedPlatoons:[], slotsFilled:0, planets:{}};
  priorities.forEach(entry=>{
    const pid = entry.pid;
    const planetDef = _opsDefinitions[pid];
    const planetState = opsState?.planets?.[pid];
    if(!planetDef || !planetState) return;
    const planetUsage = {};
    const planetSummary = summary.planets[pid] = {
      priority: entry.priority,
      label: entry.label,
      completedToday: 0,
      slotsFilled: 0,
      pointsEarned: 0,
      assignments: []
    };

    while(true){
      const fillable = planetDef.platoons.map((platoon, platoonIdx)=>{
        const progress = planetState.platoons[platoonIdx];
        if(!progress || progress.completed) return null;
        const preview = previewPlatoonCompletion(pid, platoonIdx, opsState, dayUsage, planetUsage, day);
        if(!preview) return null;
        const filledNow = progress.filled.reduce((sum, val)=>sum + (Number(val)||0), 0);
        const remaining = Math.max(0, platoon.totalSlots - filledNow);
        return {platoonIdx, preview, filledNow, remaining};
      }).filter(Boolean);
      if(!fillable.length) break;
      fillable.sort((a,b)=>
        (b.filledNow - a.filledNow)
        || (a.remaining - b.remaining)
        || (a.preview.length - b.preview.length)
        || (a.platoonIdx - b.platoonIdx)
      );
      const chosen = fillable[0];
      const applied = applyOpsAssignments(pid, chosen.platoonIdx, opsState, dayUsage, planetUsage, chosen.preview, detailed);
      planetSummary.slotsFilled += applied.slotsFilled;
      summary.slotsFilled += applied.slotsFilled;
      if(applied.assignments?.length){
        planetSummary.assignments.push({
          platoonIdx: chosen.platoonIdx,
          completed: applied.completed,
          pointsEarned: applied.pointsEarned,
          entries: applied.assignments
        });
      }
      if(applied.completed){
        planetSummary.completedToday += 1;
        planetSummary.pointsEarned += applied.pointsEarned;
        summary.pointsEarned += applied.pointsEarned;
        summary.completedPlatoons.push({pid, platoonIdx:chosen.platoonIdx, points:applied.pointsEarned});
      }
    }

    const partialOrder = planetDef.platoons.map((platoon, platoonIdx)=>{
      const progress = planetState.platoons[platoonIdx];
      if(!progress || progress.completed) return null;
      if(!canEventuallyCompletePlatoon(pid, platoonIdx, opsState)) return null;
      const filledNow = progress.filled.reduce((sum, val)=>sum + (Number(val)||0), 0);
      return {platoonIdx, filledNow, remaining: platoon.totalSlots - filledNow};
    }).filter(Boolean).sort((a,b)=>
      (b.filledNow - a.filledNow)
      || (a.remaining - b.remaining)
      || (a.platoonIdx - b.platoonIdx)
    );
    partialOrder.forEach(entry2=>{
      const applied = fillPlatoonPartially(pid, entry2.platoonIdx, opsState, dayUsage, planetUsage, day, detailed);
      planetSummary.slotsFilled += applied.slotsFilled;
      summary.slotsFilled += applied.slotsFilled;
      if(applied.assignments?.length){
        planetSummary.assignments.push({
          platoonIdx: entry2.platoonIdx,
          completed: applied.completed,
          pointsEarned: applied.pointsEarned,
          entries: applied.assignments
        });
      }
      if(applied.completed){
        planetSummary.completedToday += 1;
        planetSummary.pointsEarned += applied.pointsEarned;
        summary.pointsEarned += applied.pointsEarned;
        summary.completedPlatoons.push({pid, platoonIdx:entry2.platoonIdx, points:applied.pointsEarned});
      }
    });
  });
  return summary;
}

function summarizeOperationsState(opsState, daySummaries=[]){
  const planetStats = {};
  const activeBonusIds = getActiveBonusPlanetIdsFromPlanDays(daySummaries);
  let totalCompleted = 0;
  let totalPlatoons = 0;
  let totalPoints = 0;
  Object.entries(_opsDefinitions||{}).forEach(([pid, planetDef])=>{
    const meta = getPlanetMetaById(pid);
    if(meta?.unlockedBy && !activeBonusIds.has(pid)) return;
    const planetState = opsState?.planets?.[pid];
    const completedPlatoons = planetState?.completedPlatoons || 0;
    const totalPlanetPlatoons = planetDef.platoons.length;
    const totalSlots = planetDef.platoons.reduce((sum, platoon)=>sum + (Number(platoon.totalSlots)||0), 0);
    const slotsFilled = planetState
      ? planetState.platoons.reduce((sum, platoon)=>sum + platoon.filled.reduce((inner, value)=>inner + (Number(value)||0), 0), 0)
      : 0;
    const points = completedPlatoons * (Number(planetDef.opsVal)||0);
    planetStats[pid] = {completedPlatoons, totalPlatoons:totalPlanetPlatoons, totalSlots, slotsFilled, points};
    totalCompleted += completedPlatoons;
    totalPlatoons += totalPlanetPlatoons;
    totalPoints += points;
  });
  return {totalCompleted, totalPlatoons, totalPoints, planetStats, days:daySummaries};
}

function initRosterTab(){
  const sel = document.getElementById('roster-member-sel');
  if(!sel) return;
  const acs = Object.keys(guildRosters);
  const memberData = document.getElementById('guild-name-display')?.dataset?.members;
  let nameMap = {};
  if(memberData){
    try{
      JSON.parse(memberData).forEach(m=>{
        const ac=m.allyCode||m.allycode||m.ally_code||m.playerId||m.memberExternalId;
        const nm=m.playerName||m.name||ac;
        if(ac) nameMap[String(ac)]=nm;
      });
    }catch(e){}
  }
  sel.innerHTML='<option value="">-- Select member ('+acs.length+' scanned) --</option>'+
    acs.map(ac=>'<option value="'+ac+'">'+escHtml(nameMap[ac]||ac)+'</option>').join('');
}

function loadMemberRoster(ac){
  if(!ac){ _rosterData=[]; renderRosterList(); return; }
  const roster = Array.isArray(guildRosters[ac]) ? guildRosters[ac].map(normalizeRosterUnit) : [];
  if(!roster||roster.length===0){
    document.getElementById('roster-list').innerHTML=
      '<div style="color:var(--ds);font-size:.8rem;padding:2rem;text-align:center">'+
      'No roster data for this member. Run Scan Rosters first.</div>';
    return;
  }
  _rosterData = roster;
  filterRoster();
  queueSaveAppState();
}

let _rosterFiltered = [];

function filterRoster(){
  const search = (document.getElementById('roster-search')?.value||'').toLowerCase();
  const filter = document.getElementById('roster-filter')?.value||'all';
  _rosterFiltered = _rosterData.filter(u=>{
    const name = defIdToName((u.defId||'').split(':')[0], u.name).toLowerCase();
    if(search && !name.includes(search) && !u.defId.toLowerCase().includes(search)) return false;
    const ct = inferUnitCombatType(u);
    if(filter==='chars'&&ct!==1)return false;
    if(filter==='ships'&&ct!==2)return false;
    if(filter==='r5plus' && (ct!==1||(Number(u.relic)||0)<5)) return false;
    if(filter==='r7plus' && (ct!==1||(Number(u.relic)||0)<7)) return false;
    if(filter==='r9plus' && (ct!==1||(Number(u.relic)||0)<9)) return false;
    if(filter==='g12plus'&& (ct!==1||(Number(u.gear)||0)<12)) return false;
    return true;
  });
  sortRoster(_rosterSort.key, true);
}

function sortRoster(key, keepDir){
  const allowed = new Set(['name','type','stars','level','power']);
  if(!allowed.has(key)) key = 'name';
  if(!keepDir){
    if(_rosterSort.key===key) _rosterSort.dir *= -1;
    else {
      _rosterSort.key=key;
      _rosterSort.dir=(key==='name'?1:-1);
    }
  } else if(!allowed.has(_rosterSort.key)){
    _rosterSort = {key:'name', dir:1};
  }
  // Update sort button styles
  document.querySelectorAll('.roster-sort-btn').forEach(b=>b.classList.remove('active'));
  const colMap={name:'rs-name',type:'rs-type',stars:'rs-stars',level:'rs-level',power:'rs-power'};
  const btn=document.getElementById(colMap[_rosterSort.key]);
  if(btn) btn.classList.add('active');

  const d=_rosterSort.dir;
  _rosterFiltered.sort((a,b)=>{
    switch(_rosterSort.key){
      case 'name':     return d*(defIdToName((a.defId||'').split(':')[0],a.name).localeCompare(defIdToName((b.defId||'').split(':')[0],b.name)));
      case 'type':     return d*(inferUnitCombatType(a)-inferUnitCombatType(b));
      case 'stars':    return d*(a.rarity-b.rarity);
      case 'level':    return d*((a.relic>0?a.relic+20:a.gear)-(b.relic>0?b.relic+20:b.gear));
      case 'power':    return d*((Number(a.power)||0)-(Number(b.power)||0));
      default: return 0;
    }
  });
  renderRosterList();
}

function fallbackAbilityName(skill, idx, counters){
  const skillId = String(skill?.id || '').toLowerCase();
  if(skill?.name) return String(skill.name).trim();
  if(skillId.startsWith('basicskill')) return 'Basic';
  if(skillId.startsWith('leaderskill')) return 'Leader';
  if(skillId.startsWith('uniqueskill')){
    counters.unique += 1;
    return counters.unique === 1 ? 'Unique' : ('Unique '+counters.unique);
  }
  if(skillId.startsWith('specialskill')){
    counters.special += 1;
    return 'Special '+counters.special;
  }
  if(skillId.startsWith('contract')){
    counters.contract += 1;
    return counters.contract === 1 ? 'Contract' : ('Contract '+counters.contract);
  }
  if(skillId.startsWith('crew')){
    counters.crew += 1;
    return counters.crew === 1 ? 'Crew' : ('Crew '+counters.crew);
  }
  if(skillId.startsWith('hardware')){
    counters.hardware += 1;
    return counters.hardware === 1 ? 'Hardware' : ('Hardware '+counters.hardware);
  }
  if(skillId.startsWith('ultimateability')) return 'Ultimate';
  return 'Ability '+(idx+1);
}

function abilityLevelLabel(skill){
  if(skill?.kind === 'ultimate' || skill?.unlocked) return 'Unlocked';
  const level = Number(skill?.level)||0;
  if(level > 0) return 'Lv '+level;
  const tier = Number(skill?.tier)||0;
  return tier > 0 ? 'Tier '+tier : '';
}

function formatUnitPower(value){
  const power = Number(value)||0;
  return power > 0 ? power.toLocaleString() : '<span style="color:var(--text3)">-</span>';
}

function renderAbilitySummary(rawDefId, unit){
  const skills = Array.isArray(unit?.skills) ? unit.skills : [];
  if(!skills.length){
    return '<span style="color:var(--text3)">Re-scan to load abilities</span>';
  }
  const counters = {special:0, unique:0, contract:0, crew:0, hardware:0};
  return skills.map((skill, idx)=>{
    const displayName = fallbackAbilityName(skill, idx, counters);
    const levelLabel = abilityLevelLabel(skill);
    const badges = [];
    if(skill?.hasZeta){
      badges.push('<span style="font-size:.56rem;color:#b58cff;border:1px solid rgba(181,140,255,.45);border-radius:999px;padding:0 5px">Z</span>');
    }
    if(skill?.hasOmicron){
      badges.push('<span style="font-size:.56rem;color:#ff8d8d;border:1px solid rgba(255,141,141,.45);border-radius:999px;padding:0 5px">O</span>');
    }
    return '<div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start;font-size:.64rem;line-height:1.25;margin-bottom:2px">'+
      '<span style="color:var(--text)">'+escHtml(displayName)+'</span>'+
      '<span style="display:flex;gap:4px;align-items:center;white-space:nowrap;color:var(--text3)">'+
        badges.join('')+
        (levelLabel?'<span>'+escHtml(levelLabel)+'</span>':'')+
      '</span>'+
    '</div>';
  }).join('');
}

function renderRosterList(){
  const el=document.getElementById('roster-list');
  if(!el) return;

  const chars=_rosterFiltered.filter(u=>!isShipUnit(u));
  const ships=_rosterFiltered.filter(u=>isShipUnit(u));
  const total=_rosterFiltered.length;
  const summary=document.getElementById('roster-summary');
  if(summary){
    const r7=chars.filter(u=>(Number(u.relic)||0)>=7).length;
    const r5=chars.filter(u=>(Number(u.relic)||0)>=5).length;
    const abilityHint = chars.length && !chars.some(u=>Array.isArray(u.skills) && u.skills.length>0)
      ? ' | re-scan rosters to load ability details'
      : '';
    const powerHint = total && !_rosterFiltered.some(u=>(Number(u.power)||0)>0)
      ? ' | re-scan rosters to load unit power'
      : '';
    summary.textContent=total+' units | '+chars.length+' characters | '+ships.length+' ships | '+
      r7+' R7+ | '+r5+' R5+'+abilityHint+powerHint;
  }

  if(total===0){
    el.innerHTML='<div style="color:var(--text3);font-size:.8rem;padding:2rem;text-align:center">'+
      'No units match the current filter.</div>';
    return;
  }

  function renderRows(units){
    return units.map(u=>{
      const raw_did=(u.defId||'').split(':')[0];
      const name=defIdToName(raw_did, u.name);
      const isShip=isShipUnit(u);
      const rosterLevelStr=isShip
        ? '<span style="color:var(--text3)">-</span>'
        : (u.relic>0?('<span style="color:var(--gold)">R'+u.relic+'</span>'):('G'+u.gear));
      const rosterTypeStr=isShip?'Ship':'Character';
      const rosterStarStr=Array.from({length:Number(u.rarity)||0}, ()=> '&#9733;').join('');
      const rosterLevelClr=isShip ? 'var(--text3)' : (u.relic>=9?'#e74c3c':u.relic>=7?'var(--gold)':
                            u.relic>=5?'#27ae60':'var(--text3)');
      const rosterPowerStr=formatUnitPower(u.power);
      const rosterAbilityHtml=renderAbilitySummary(raw_did, u);
      return '<div style="display:grid;grid-template-columns:1.7fr .8fr .7fr .8fr .9fr 3fr;'+
        'gap:6px;padding:6px 8px;border-bottom:1px solid var(--border);align-items:flex-start;'+
        'transition:background .1s" onmouseover="this.style.background=\'var(--bg4)\'"'+
        ' onmouseout="this.style.background=\'transparent\'">'+
        '<span style="font-size:.78rem;font-weight:600;color:var(--text)">'+escHtml(name)+'</span>'+
        '<span style="font-size:.7rem;color:var(--text2)">'+rosterTypeStr+'</span>'+
        '<span style="font-size:.7rem;color:var(--gold2)">'+rosterStarStr+'</span>'+
        '<span style="font-size:.75rem;color:'+rosterLevelClr+'">'+rosterLevelStr+'</span>'+
        '<span style="font-size:.72rem;color:var(--text2)">'+rosterPowerStr+'</span>'+
        '<div style="font-size:.64rem;color:var(--text2)">'+rosterAbilityHtml+'</div>'+
        '</div>';
    }).join('');
  }

  let html='';
  function makeSection(label,count,id,open,rows){
    return`<div style="margin-bottom:4px">
      <div onclick="document.getElementById('${id}').style.display=document.getElementById('${id}').style.display==='none'?'block':'none';this.querySelector('.rsec-icon').textContent=document.getElementById('${id}').style.display==='none'?'▸':'▾'"
        style="display:flex;justify-content:space-between;align-items:center;padding:5px 10px;
        background:var(--bg2);cursor:pointer;border-bottom:1px solid var(--border)">
        <span style="font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;color:var(--text2)">
          <span class="rsec-icon">${open?'▾':'▸'}</span> ${label}
          <span style="color:var(--text3)">(${count})</span>
        </span>
      </div>
      <div id="${id}" style="display:${open?'block':'none'}">${rows}</div>
    </div>`;
  }
  if(chars.length) html+=makeSection('Characters',chars.length,'rc-chars',true,renderRows(chars));
  if(ships.length) html+=makeSection('Ships',ships.length,'rc-ships',false,renderRows(ships));
  el.innerHTML=html;
}


async function recheckComlink(btn){
  if(btn){btn.textContent='...';btn.disabled=true;}
  const b=document.getElementById('comlink-offline-banner');
  if(b)b.remove();
  const r=await checkComlinkStatus();
  // If server is restarting comlink, wait 5s then check again
  if(r&&r.restarted){
    if(btn) btn.textContent='Restarting...';
    await new Promise(res=>setTimeout(res,5000));
    await checkComlinkStatus();
  }
  if(btn){btn.textContent='\u8635 Retry';btn.disabled=false;}
}

async function checkComlinkStatus(){
  const dot=document.getElementById('comlink-dot');
  const lbl=document.getElementById('comlink-label');
  try{
    const ctrl=new AbortController();
    const t=setTimeout(()=>ctrl.abort(),6000);
    const r=await fetch('/api/status',{method:'GET',signal:ctrl.signal});
    clearTimeout(t);
    const d=await r.json();
    if(d.comlink==='online'){
      dot.className='status-dot online';
      lbl.textContent='online'+(d.version&&d.version!='?'?' v'+d.version:'');
      // Remove offline banner if present
      const ob=document.getElementById('comlink-offline-banner');
      if(ob)ob.remove();
      // Enable live import controls
      const fb=document.getElementById('fetch-guild-btn');
      const sb=document.getElementById('scan-btn');
      if(fb){fb.disabled=false;fb.title='';}
      if(sb){sb.disabled=false;sb.title='';}
    } else {
      dot.className='status-dot offline';
      lbl.textContent='offline';
      // Disable live import, show help
      const fb=document.getElementById('fetch-guild-btn');
      const sb=document.getElementById('scan-btn');
      if(fb){fb.disabled=true;fb.title='Comlink offline — click Retry in the header';}
      if(sb){sb.disabled=true;sb.title='Comlink offline — click Retry in the header';}
      const tip = d.reason||d.tip||'';
      if(tip){
        const banner=document.createElement('div');
        banner.style.cssText='font-size:.7rem;background:rgba(192,57,43,.1);border:1px solid var(--ds-dim);border-radius:8px;padding:8px 12px;margin-top:8px;color:var(--text2);line-height:1.6';
        banner.innerHTML='<b style="color:var(--ds)">Comlink offline</b><br>'+
          'To diagnose, open <a href="http://localhost:3000/" target="_blank" style="color:var(--gold)">http://localhost:3000/</a> in a new browser tab.<br>'+
          (d.reason?'Error: '+escHtml(d.reason)+'<br>':'') +
          'See the <b>terminal window</b> where the planner is running for startup errors.<br>'+
          'Most common fix: <b>right-click the comlink .exe in .comlink folder → Properties → check Unblock → OK</b>, then re-run the planner.';
        const existing=document.getElementById('comlink-offline-banner');
        if(existing)existing.remove();
        banner.id='comlink-offline-banner';
        const card=document.getElementById('comlink-import-card');
        if(card)card.appendChild(banner);
      }
    }
  }catch(e){
    dot.className='status-dot offline';
    lbl.textContent=(e.name==='AbortError')?'timeout':'not running';
    // Remove offline banner to avoid stale messages
    const b=document.getElementById('comlink-offline-banner');
    if(e.name!=='AbortError'&&!b){
      // Only show banner for genuine offline (not just slow server)
    }
  }
  // Re-check every 30 seconds
  setTimeout(checkComlinkStatus, 30000);
  return d;
}

// LIVE IMPORT
function showImportStatus(msg,type){
  const el=document.getElementById('import-status-bar');
  el.style.display='block';
  el.className='status-bar '+type;
  el.textContent=msg;
}

function showScanCompleteBanner(done,total,failed){
  const el = document.getElementById('scan-complete-banner');
  if(!el) return;
  const loaded = Math.max(0, Number(done)||0);
  const members = Math.max(0, Number(total)||0);
  const misses = Math.max(0, Number(failed)||0);
  const detail = misses
    ? loaded+'/'+members+' members were scanned. '+misses+' roster'+(misses===1?' was':'s were')+' not loaded and may need a retry.'
    : loaded+'/'+members+' members were scanned successfully. Guides, roster checks, operations, and planning now use this scan.';
  el.innerHTML = '<div class="scan-complete-title">Roster Scan Complete</div>'
    + '<div class="scan-complete-sub">'+escHtml(detail)+'</div>';
  el.classList.add('show');
}

function hideScanCompleteBanner(){
  const el = document.getElementById('scan-complete-banner');
  if(!el) return;
  el.classList.remove('show');
  el.innerHTML = '';
}

function setScanButtonState(mode){
  const btn = document.getElementById('scan-btn');
  if(!btn) return;
  btn.classList.remove('btn-scan-loud','btn-scan-repeat');
  if(mode === 'repeat'){
    btn.classList.add('btn','btn-scan-repeat');
    btn.textContent = 'Scan Again?';
    btn.disabled = false;
    btn.style.fontSize = '.68rem';
    btn.style.padding = '7px 14px';
    btn.style.fontWeight = '700';
    return;
  }
  btn.classList.add('btn','btn-scan-loud');
  btn.textContent = '⚡ Scan Rosters';
  btn.disabled = false;
  btn.style.fontSize = '.68rem';
  btn.style.padding = '7px 14px';
  btn.style.fontWeight = '700';
}

let _primaryAllyCode='';

function extractGuildSummary(data){
  if(data?._debug_keys){
    console.log('[ROTE] Guild response top-level keys:', data._debug_keys);
    console.log('[ROTE] Profile keys:', data._debug_profile_keys);
  }

  const root = data?.guild || data || {};
  const profile = root.profile || root.data || root.guildInfo || {};
  const members = root.member || root.members || root.roster || profile.member || [];
  const name = profile.name || profile.guildName || root.name || root.guildName || 'Unknown Guild';

  const gp = Number(
    profile.guildPower || profile.galacticPower || profile.galactic_power ||
    root.guildPower    || root.galacticPower    || 0
  );

  function getMemberGP(member){
    if(member.galacticPower) return Number(member.galacticPower);
    if(member.memberContribution){
      if(Array.isArray(member.memberContribution)){
        const contribution = member.memberContribution.find(c=>c.type===1||c.contributionType==='GALACTIC_POWER');
        return contribution ? Number(contribution.currentValue||contribution.lifetimeValue||0) : 0;
      }
      return Number(member.memberContribution)||0;
    }
    return 0;
  }

  function getMemberName(member){
    return member.playerName || member.name || member.playerInfo?.playerName || '?';
  }

  function getMemberAllyCode(member){
    return member.allyCode || member.allycode || member.ally_code || member.playerId || null;
  }

  if(members.length === 0){
    console.warn('[ROTE] No members found. Full response:', JSON.stringify(data).slice(0,500));
    return {
      error:
        'Guild found but 0 members returned. Check console (F12) for raw response. Keys seen: '+
        JSON.stringify(data?._debug_keys || Object.keys(root).slice(0,10))
    };
  }

  return {
    name,
    gp: gp || members.reduce((sum, member)=>sum + getMemberGP(member), 0),
    members: members.map(member=>({
      ...member,
      _resolvedName: getMemberName(member),
      _resolvedGp: getMemberGP(member),
      _resolvedAllyCode: getMemberAllyCode(member)
    }))
  };
}

function renderGuildSummary(summary, {silent=false, preserveScans=false} = {}){
  const members = Array.isArray(summary?.members) ? summary.members : [];
  if(!summary || !members.length) return false;

  if(!preserveScans){
    guildRosters = {};
    _platoonAnalysis = {};
    invalidateOperationsCaches();
    _rosterData = [];
    _rosterFiltered = [];
    rebuildUnitNameIndex();
    const rosterAnalysis = document.getElementById('roster-analysis');
    if(rosterAnalysis) rosterAnalysis.style.display='none';
    hideScanCompleteBanner();
    setScanButtonState('primary');
  }

  document.getElementById('guild-gp').value = Number(summary.gp) || 0;
  document.getElementById('guild-members').value = members.length || 50;

  const guildDisplay = document.getElementById('guild-name-display');
  guildDisplay.textContent = summary.name+' ('+members.length+' members)';
  guildDisplay.dataset.members = JSON.stringify(members);
  guildDisplay.dataset.guildName = summary.name;

  document.getElementById('member-gp-display').textContent = fmtM(summary.gp||0);

  const grid = document.getElementById('member-grid');
  grid.innerHTML = members.map(member=>{
    const n = member._resolvedName || member.playerName || member.name || '?';
    const gpM = Number(member._resolvedGp ?? member.galacticPower ?? 0);
    return '<div class="member-card"><div class="member-name">'+escHtml(n)+'</div>'+
           '<div class="member-gp">'+fmtM(gpM)+'</div></div>';
  }).join('');

  const memberDisplay = document.getElementById('member-display');
  memberDisplay.style.display='block';
  memberDisplay.dataset.guildSummary = JSON.stringify({
    name: summary.name,
    gp: summary.gp,
    members
  });

  if(!silent){
    showImportStatus('✓ Imported "'+summary.name+'" — '+members.length+' members, '+fmtM(summary.gp||0)+' GP','ok');
  }
  onStatsChange();
  populateMemberDropdown();
  initRosterTab();
  queueSaveAppState();
  return true;
}

function getCurrentGuildSummary(){
  const raw = document.getElementById('member-display')?.dataset?.guildSummary;
  if(!raw) return null;
  try{
    const parsed = JSON.parse(raw);
    return parsed && Array.isArray(parsed.members) ? parsed : null;
  }catch(e){
    return null;
  }
}

async function fetchGuildByAllyCode(){
  const raw=document.getElementById('ally-code-input').value.trim().replace(/[-\s]/g,'');
  if(!raw){showImportStatus('Enter an ally code first.','err');return;}
  _primaryAllyCode=raw;
  showImportStatus('Fetching player data...','loading');
  document.getElementById('fetch-guild-btn').disabled=true;
  try{
    const r=await fetch('/api/guild-by-allycode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({allyCode:raw})});
    const d=await r.json();
    if(d.error){
      showImportStatus('Error: '+d.error,'err');
      if(d._debug_player){
        console.warn('[ROTE] Player response sample:', d._debug_player);
      }
      return;
    }
    parseAndDisplayGuild(d);
  }catch(e){
    showImportStatus('Request failed: '+e.message,'err');
  }finally{
    document.getElementById('fetch-guild-btn').disabled=false;
  }
}

function parseAndDisplayGuild(data, options={}){
  const summary = extractGuildSummary(data);
  if(summary.error){
    showImportStatus(summary.error, 'err');
    return false;
  }
  return renderGuildSummary(summary, options);
}

function sleep(ms){return new Promise(r=>setTimeout(r,ms));}

// Fetch with hard timeout - prevents any single request hanging the entire scan
async function fetchRoster(ac, timeoutMs=10000){
  const ctrl = new AbortController();
  const timer = setTimeout(()=>ctrl.abort(), timeoutMs);
  try{
    const r = await fetch('/api/roster', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({allyCode: String(ac)}),
      signal: ctrl.signal
    });
    clearTimeout(timer);
    return await r.json();
  }catch(e){
    clearTimeout(timer);
    if(e.name==='AbortError') return {error:'timeout'};
    return {error: e.message};
  }
}

function scannedRosterCount(){
  return Object.values(guildRosters).filter(roster=>Array.isArray(roster) && roster.length > 0).length;
}

function recountKeyUnits(){
  const counts = {};
  KEY_UNITS.forEach(unit=>{ counts[normalizeDefId(unit.defId).toUpperCase()] = 0; });
  Object.values(guildRosters).forEach(roster=>{
    KEY_UNITS.forEach(unit=>{
      const found = (roster||[]).find(entry=>unitMatchesDefId(entry, unit.defId));
      if(found && (Number(found.relic)||0) >= (unit.relic||0)){
        counts[normalizeDefId(unit.defId).toUpperCase()]++;
      }
    });
  });
  return counts;
}

let _scanCancelled = false;
function cancelScan(btn){ _scanCancelled=true; if(btn) btn.textContent='Stopping...'; }

async function scanRosters(){
  const membersData = document.getElementById('guild-name-display').dataset.members;
  if(!membersData){showImportStatus('Fetch guild data first.','err');return;}
  const members = JSON.parse(membersData);
  const total = members.length;
  const btn = document.getElementById('scan-btn');
  _scanCancelled = false;
  try{
    await fetch('/api/reset-scan-session', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  }catch(err){
    console.warn('[ROTE] Scan session reset skipped:', err.message);
  }

  guildRosters = {};
  _platoonAnalysis = {};
  _rosterData = [];
  _rosterFiltered = [];
  invalidateOperationsCaches();
  rebuildUnitNameIndex();
  updateOperationsTabVisibility();
  populateMemberDropdown();
  initRosterTab();
  const rosterAnalysis = document.getElementById('roster-analysis');
  if(rosterAnalysis) rosterAnalysis.style.display='none';
  hideScanCompleteBanner();
  setScanButtonState('primary');
  [...document.getElementById('member-grid').querySelectorAll('.member-card')].forEach(card=>{
    card.style.borderColor = 'rgba(93,173,226,0.18)';
  });

  // Build/show progress UI
  let pb = document.getElementById('scan-pb');
  if(!pb){
    pb = document.createElement('div'); pb.id='scan-pb';
    pb.style.cssText='margin-top:8px;background:var(--bg4);border-radius:3px;overflow:hidden;display:none';
    pb.innerHTML='<div id="scan-pb-track" style="height:5px;overflow:hidden">'+
      '<div id="scan-pb-fill" style="height:100%;background:var(--gold);width:0%;transition:width .3s;border-radius:3px"></div></div>'+
      '<div style="display:flex;justify-content:space-between;margin-top:4px">'+
      '<span id="scan-pb-text" style="font-size:.65rem;color:var(--text2)"></span>'+
      '<button onclick="cancelScan(this)" style="font-size:.6rem;color:var(--ds);background:transparent;border:none;cursor:pointer">Cancel</button></div>';
    document.getElementById('member-display').appendChild(pb);
  }
  pb.style.display='block';
  const pbf = document.getElementById('scan-pb-fill');
  const pbt = document.getElementById('scan-pb-text');
  btn.disabled=true; btn.textContent='Scanning...';
  showImportStatus('Starting a fresh roster scan for '+total+' members...','loading');
  const unitCounts = {};
  KEY_UNITS.forEach(u=>unitCounts[normalizeDefId(u.defId).toUpperCase()]=0);

  // Sequential with retry + comlink health monitoring
  // Sequential avoids overwhelming comlink; retry handles transient failures
  const REQ_DELAY = 100;    // ms between requests (~10 req/sec, well under 20/sec limit)
  const RETRY_DELAY = 2000; // ms before retry on failure
  const HEALTH_INTERVAL = 5; // check comlink health every N members
  let done = 0;
  let failed = 0;
  let consecFails = 0;
  const t0 = Date.now();

  for(let i=0; i<members.length && !_scanCancelled; i++){
    const m = members[i];
    const ac = m.allyCode||m.allycode||m.ally_code||m.playerId||m.memberExternalId||m.externalId;

    if(!ac){ done++; continue; }

    // If comlink went offline, wait for recovery before continuing
    if(consecFails >= 3){
      if(pbt) pbt.textContent = 'Comlink offline — waiting for recovery...';
      // Ask server to check + auto-restart comlink
      for(let attempt=0; attempt<12 && !_scanCancelled; attempt++){
        await sleep(3000);
        try{
          const h = await fetch('/api/comlink-health',{method:'POST',
            headers:{'Content-Type':'application/json'},body:'{}'});
          const hd = await h.json();
          if(hd.alive){ consecFails=0; break; }
          if(pbt) pbt.textContent='Comlink offline — retry '+(attempt+1)+'/12...';
        }catch(e){}
      }
      if(consecFails >= 3){
        // Still offline after 36 seconds
        showImportStatus('Comlink could not recover. Scan stopped at '+done+'/'+total+' members.','err');
        break;
      }
    }

    // Fetch with retry
    let data = null;
    for(let attempt=0; attempt<3; attempt++){
      try { data = await fetchRoster(ac); } catch(e){ data = {error: String(e)}; }
      if(data && data.roster && data.roster.length > 0) break;
      if(attempt < 2 && !_scanCancelled){
        const delay = RETRY_DELAY * (attempt + 1);
        if(pbt) pbt.textContent=`Retrying ${ac.slice(0,8)}... (${attempt+1}/2)`;
        await sleep(delay);
      }
    }

    // Log failure to server for troubleshooting
    if(!data || !data.roster || data.roster.length === 0){
      fetch('/api/log-scan-failure', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({allyCode: ac, memberIndex: i,
          error: data?.error || data?.message || 'empty roster',
          responseKeys: data ? Object.keys(data) : []})
      }).catch(()=>{});
    }

    const cards = [...document.getElementById('member-grid').querySelectorAll('.member-card')];
    if(data && data.roster && data.roster.length > 0){
      const normalizedRoster = data.roster.map(normalizeRosterUnit);
      guildRosters[ac] = normalizedRoster;
      KEY_UNITS.forEach(u=>{
        const unit=normalizedRoster.find(x=>unitMatchesDefId(x, u.defId));
        if(unit&&(Number(unit.relic)||0)>=(u.relic||0)) unitCounts[normalizeDefId(u.defId).toUpperCase()]++;
      });
      if(cards[i]) cards[i].style.borderColor='rgba(39,174,96,0.4)';
      consecFails = 0;
    } else {
      failed++;
      consecFails++;
      if(cards[i]) cards[i].style.borderColor='rgba(192,57,43,0.4)';
      console.warn('Roster failed for',ac, data);
    }

    done++;
    const pct = Math.round(done/total*100);
    const elapsed = (Date.now()-t0)/1000;
    const rate = elapsed>0 ? done/elapsed : 1;
    const remSec = Math.ceil((total-done)/rate);
    if(pbf) pbf.style.width=pct+'%';
    if(pbt) pbt.textContent=done+'/'+total+' scanned'+(failed?' | '+failed+' failed':'')+' | ~'+remSec+'s left';

    if(i < members.length-1) await sleep(REQ_DELAY);
  }

  if(_scanCancelled){
    showImportStatus('Scan cancelled — '+done+' of '+total+' members scanned.','err');
  }
  pb.style.display='none';
  btn.disabled=false;
  if(!_scanCancelled){
    invalidateOperationsCaches();
    rebuildUnitNameIndex();
    refreshGuideUnitLinks();
    renderRosterAnalysis(unitCounts, scannedRosterCount() || done);
    updateDefaultsFromRosterScan();
    populateMemberDropdown();
    initRosterTab();
    showScanCompleteBanner(scannedRosterCount() || done, total, failed);
    setScanButtonState('repeat');
    queueSaveAppState();
  } else {
    setScanButtonState('primary');
  }
}

function updateDefaultsFromRosterScan(){
  // After scanning, auto-update CM completion defaults per planet based on actual capability
  const ALL=[...DS_CHAIN,...MX_CHAIN,...LS_CHAIN,...BONUS_PLANETS];
  ALL.forEach(p=>{
    const cap=calcMemberCapability(p.id);
    if(!cap)return;
    // Use actual member capability rate as CM default for this planet
    const rate=cap.cmPct/100;
    pState[p.id].cmRateOverride=Math.round(rate*100);
    // Fleet rate slightly lower (not all capable members have fleet deployed)
    pState[p.id].fleetRateOverride=Math.round(Math.min(rate*0.85,100));
  });
  if(document.getElementById('chain-ds').innerHTML) rebuildPlannerChains();
}

function renderRosterAnalysis(counts,total){
  const grid=document.getElementById('unit-check-grid');
  grid.innerHTML=KEY_UNITS.map(u=>{
    const c=counts[normalizeDefId(u.defId).toUpperCase()]||0;
    const cls=c>=total*0.8?'good':c>=total*0.5?'warn':'bad';
    const pct=total?Math.round(c/total*100):0;
    return `<div class="unit-check"><div class="unit-check-name">${escHtml(u.name)}</div><div class="unit-check-stat"><span class="count ${cls}">${c}/${total}</span> at R${u.relic}+ (${pct}%)</div></div>`;
  }).join('');
  document.getElementById('roster-analysis').style.display='block';
}

// UTILS
const fmt=n=>Math.round(n).toLocaleString();
const fmtM=n=>n>=1e9?(n/1e9).toFixed(2)+'B':(n/1e6).toFixed(1)+'M';
const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const escHtml=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const guildGP=()=>parseFloat(document.getElementById('guild-gp').value)||400000000;
function parseClampedNumber(value, fallback, minValue, maxValue, asInt=false){
  const parsed = asInt ? parseInt(value, 10) : parseFloat(value);
  if(!Number.isFinite(parsed)) return fallback;
  return clamp(parsed, minValue, maxValue);
}

function missionEstimateFieldLimit(){
  return cmMode === 'count' ? 50 : 100;
}

function sanitizeMissionEstimateInput(id){
  const input = document.getElementById(id);
  if(!input) return 0;
  const fallbackMap = {
    'cm-base': 70,
    'cm-falloff': 10,
    'fleet-base': 50,
    'fleet-falloff': 15,
  };
  const maxValue = missionEstimateFieldLimit();
  const fallback = Math.min(fallbackMap[id] ?? 0, maxValue);
  const value = parseClampedNumber(input.value, fallback, 0, maxValue, false);
  input.min = '0';
  input.max = String(maxValue);
  input.value = String(value);
  return value;
}

function sanitizeMissionEstimateInputs(){
  ['cm-base','cm-falloff','fleet-base','fleet-falloff'].forEach(sanitizeMissionEstimateInput);
}

const members=()=>parseClampedNumber(document.getElementById('guild-members').value,50,1,50,true);
const cmBase=()=>sanitizeMissionEstimateInput('cm-base');
const cmFall=()=>sanitizeMissionEstimateInput('cm-falloff');
const flBase=()=>sanitizeMissionEstimateInput('fleet-base');
const flFall=()=>sanitizeMissionEstimateInput('fleet-falloff');

function normalizeExternalUrl(rawUrl){
  const raw = String(rawUrl || '').trim();
  if(!raw) return '';
  if(/^(https?:)?\/\//i.test(raw)){
    return /^https?:\/\//i.test(raw) ? raw : ('https:' + raw);
  }
  if(/^(javascript|data|file|vbscript):/i.test(raw)) return '';
  if(/^[a-z0-9.-]+\.[a-z]{2,}(\/|$)/i.test(raw)){
    return 'https://' + raw;
  }
  return raw;
}

function chainDepth(pid){
  for(const[i,p]of DS_CHAIN.entries())if(p.id===pid)return i;
  for(const[i,p]of MX_CHAIN.entries())if(p.id===pid)return i;
  for(const[i,p]of LS_CHAIN.entries())if(p.id===pid)return i;
  return 3;
}
function effectiveCmRate(pid){
  const s=pState[pid];
  if(cmMode==='count'){const ov=s.cmCountOverride;return ov!==null?ov/members():clamp((cmBase()-cmFall()*chainDepth(pid))/100,0,1);}
  if(s.cmRateOverride!==null)return s.cmRateOverride/100;
  return clamp((cmBase()-cmFall()*chainDepth(pid))/100,0,1);
}
function effectiveFleetRate(pid){
  const s=pState[pid];
  if(cmMode==='count'){const ov=s.fleetCountOverride;return ov!==null?ov/members():clamp((flBase()-flFall()*chainDepth(pid))/100,0,1);}
  if(s.fleetRateOverride!==null)return s.fleetRateOverride/100;
  return clamp((flBase()-flFall()*chainDepth(pid))/100,0,1);
}
function calcPlanetPts(pid,day=1){
  const p    = ALL_PLANETS.find(x=>x.id===pid);
  const s    = pState[p.id];
  const active = activeMemberCount();
  const cmRate = effectiveCmRate(pid);
  const flRate = effectiveFleetRate(pid);
  const missionMeta = getPlanetMissionEstimateMeta(pid);
  const fallbackCombatTotal = (p.cms || 0) * (p.cmPts || 0);
  const fallbackFleetTotal = (p.fleets || 0) * (p.fleetPts || 0);
  const cmExpected = active * cmRate;
  const flExpected = active * flRate;
  const cmCompletions = Math.floor(cmExpected);
  const cmPartialClear = (cmExpected - cmCompletions) >= 0.5 ? 1 : 0;
  const flCompletions = Math.round(flExpected);
  const cmPts = missionMeta.combat.length
    ? missionMeta.combat.reduce((sum, mission)=>sum + projectCombatMissionPoints(mission, cmExpected), 0)
    : Math.round(cmExpected) * fallbackCombatTotal;
  const flPts = missionMeta.fleet.length
    ? missionMeta.fleet.reduce((sum, mission)=>sum + projectFleetMissionPoints(mission, flExpected), 0)
    : flCompletions * fallbackFleetTotal;

  const opsAvailable = !p.unlockedBy || bonusUnlocked(p.id);
  const projected = opsAvailable ? getProjectedOpsPlanetStats(pid) : null;
  const isolated = opsAvailable ? _platoonAnalysis[pid] : null;
  const opsFilled = projected
    ? projected.completedPlatoons
    : (isolated?.filter(platoon=>platoon.fillable).length || 0);
  const opsPts = projected
    ? projected.points
    : (opsFilled * p.opsVal);

  const preload = s.preloaded || 0;

  // Available deployment GP for this day
  const gpAvail = gpForDay(day);

  return {total:cmPts+flPts+opsPts+preload, cmPts, flPts, opsPts, preload,
          opsFilled, gpAvail, cmExpected, flExpected, cmCompletions, cmPartialClear, flCompletions,
          cmMissionCount: missionMeta.combat.length || p.cms || 0,
          fleetMissionCount: missionMeta.fleet.length || p.fleets || 0};
}
function calcStars(pid,day=1){
  const p=ALL_PLANETS.find(x=>x.id===pid);const{total}=calcPlanetPts(pid,day);
  let star=0;for(let i=0;i<3;i++)if(total>=p.stars[i])star=i+1;return{star,total};
}
function bonusUnlocked(bonusId){
  const b=BONUS_PLANETS.find(x=>x.id===bonusId);
  if(!b || !b.unlockedBy || !pState[b.unlockedBy]) return false;
  const source = pState[b.unlockedBy];
  if(typeof source.smReady === 'boolean') return source.smReady;
  return (source.smCount||0)>=b.unlockedAt;
}

function createBonusActivationState(){
  const state = {};
  BONUS_PLANETS.forEach(planet=>{
    state[planet.id] = {
      eligible: bonusUnlocked(planet.id),
      activeFromDay: 0,
      unlockedOnDay: 0,
      banked: 0,
      done: false
    };
  });
  return state;
}

function getActiveBonusPlanetsForDay(bonusState, dayNumber){
  return BONUS_PLANETS
    .filter(planet=>{
      const state = bonusState?.[planet.id];
      return !!state?.eligible
        && !state.done
        && Number(state.activeFromDay || 0) > 0
        && Number(dayNumber || 0) >= Number(state.activeFromDay || 0);
    })
    .map(planet=>({planet, state: bonusState[planet.id]}));
}

function scheduleUnlockedBonusPlanets(bonusState, sourcePlanetId, dayNumber, notices=null){
  BONUS_PLANETS.forEach(planet=>{
    const state = bonusState?.[planet.id];
    if(!state?.eligible || state.done) return;
    if(planet.unlockedBy !== sourcePlanetId) return;
    if(Number(state.activeFromDay || 0) > 0) return;
    const activeFromDay = Number(dayNumber || 0) + 1;
    if(activeFromDay > 6) return;
    state.activeFromDay = activeFromDay;
    state.unlockedOnDay = Number(dayNumber || 0);
    if(Array.isArray(notices)){
      notices.push(
        planet.name+' unlocks on Day '+activeFromDay
        +' after '+(getPlanetMetaById(sourcePlanetId)?.name || sourcePlanetId)+' reaches 1-star.'
      );
    }
  });
}

function getActiveBonusPlanetIdsFromPlanDays(days){
  const ids = new Set();
  (days || []).forEach(dayPlan=>{
    (dayPlan?.bonusPlanets || []).forEach(entry=>{
      const pid = entry?.planet?.id;
      if(pid) ids.add(pid);
    });
  });
  return ids;
}

// SETTINGS
function onStatsChange(){
  const guildMembersInput = document.getElementById('guild-members');
  if(guildMembersInput){
    guildMembersInput.value = String(parseClampedNumber(guildMembersInput.value, 50, 1, 50, true));
  }
  invalidateOperationsCaches();
  buildUndepTable();
  calcSummary();
  queueSaveAppState();
}

function updateCmModeUi(){
  document.getElementById('mode-pct-btn').classList.toggle('active',cmMode==='pct');
  document.getElementById('mode-count-btn').classList.toggle('active',cmMode==='count');
  const ic=cmMode==='count';
  document.getElementById('cm-base-label').textContent=ic?'CM clear members':'CM base %';
  document.getElementById('cm-falloff-label').textContent=ic?'CM falloff (members)':'CM falloff %';
  document.getElementById('fleet-base-label').textContent=ic?'Fleet completions':'Fleet base %';
  document.getElementById('fleet-falloff-label').textContent=ic?'Fleet falloff (members)':'Fleet falloff %';
  sanitizeMissionEstimateInputs();
}

function setCmMode(mode){
  cmMode=mode;
  updateCmModeUi();
  const ic=mode==='count';const m=members();
  if(ic){document.getElementById('cm-base').value=Math.round(m*.7);document.getElementById('cm-falloff').value=Math.round(m*.1);document.getElementById('fleet-base').value=Math.round(m*.5);document.getElementById('fleet-falloff').value=Math.round(m*.15);}
  else{document.getElementById('cm-base').value=70;document.getElementById('cm-falloff').value=10;document.getElementById('fleet-base').value=50;document.getElementById('fleet-falloff').value=15;}
  onFalloffChange();
}
function onFalloffChange(){sanitizeMissionEstimateInputs();invalidateOperationsCaches();renderFalloffViz();calcSummary();queueSaveAppState();}
function renderFalloffViz(){
  const viz=document.getElementById('fviz');const lblEl=document.getElementById('fviz-labels');
  const ic=cmMode==='count';
  // 6 planets = zones 1-6; each has its own CM/fleet % estimate
  const ZONE_NAMES=['Z1 R5','Z2 R6','Z3 R7','Z4 R8','Z5 R9','Z6 R9'];
  const ZONE_COLORS=['#5dade2','#27ae60','#d4ac0d','#e67e22','#9b59b6','#e74c3c'];
  const cmVals=Array.from({length:6},(_,i)=>Math.max(0,cmBase()-i*cmFall()));
  const flVals=Array.from({length:6},(_,i)=>Math.max(0,flBase()-i*flFall()));
  const max=Math.max(...cmVals,...flVals,1);
  viz.innerHTML=Array.from({length:6},(_,i)=>{
    const ch=Math.round(cmVals[i]/max*40);const fh=Math.round(flVals[i]/max*40);
    const zc=ZONE_COLORS[i];
    return`<div style="flex:1;display:flex;flex-direction:column;align-items:stretch;border-left:2px solid ${zc};padding-left:3px">
      <div style="display:flex;gap:2px;align-items:flex-end;height:44px">
        <div title="CM: ${Math.round(cmVals[i])}%" style="flex:1;height:${ch}px;background:var(--gold);border-radius:2px 2px 0 0;opacity:.85"></div>
        <div title="Fleet: ${Math.round(flVals[i])}%" style="flex:1;height:${fh}px;background:var(--ls);border-radius:2px 2px 0 0;opacity:.7"></div>
      </div>
      <div style="font-size:.58rem;color:${zc};text-align:center;margin-top:2px;letter-spacing:.04em">${ZONE_NAMES[i]}</div>
      <div style="font-size:.6rem;color:var(--gold);text-align:center">${ic?Math.round(cmVals[i]):Math.round(cmVals[i])+'%'}</div>
      <div style="font-size:.6rem;color:var(--ls);text-align:center">${ic?Math.round(flVals[i]):Math.round(flVals[i])+'%'}</div>
    </div>`;
  }).join('');
  lblEl.innerHTML='<div style="display:flex;gap:10px;align-items:center;margin-top:4px;font-size:.62rem;color:var(--text3)"><span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;background:var(--gold);border-radius:2px;display:inline-block"></span>CM %</span><span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;background:var(--ls);border-radius:2px;display:inline-block"></span>Fleet %</span><span style="color:var(--text3)">Left border = zone / relic requirement</span></div>';
}
function updateUndepModeUi(){
  document.getElementById('undep-pct-btn').classList.toggle('active',undepMode==='pct');
  document.getElementById('undep-flat-btn').classList.toggle('active',undepMode==='flat');
  document.getElementById('undep-col-hdr').textContent=undepMode==='pct'?'Undeployed %':'Undeployed GP';
}

function setUndepMode(mode){
  undepMode=mode;
  updateUndepModeUi();
  buildUndepTable();
  queueSaveAppState();
}

function setDailyUndepValue(dayIdx, rawValue){
  dailyUndep[dayIdx]=parseFloat(rawValue)||0;
  const gpTotal=guildGP();
  const u=dailyUndep[dayIdx]||0;
  const eff=undepMode==='pct'?gpTotal*(1-u/100):gpTotal-u;
  const effCell=document.getElementById('undep-eff-'+dayIdx);
  if(effCell) effCell.textContent=fmtM(Math.max(0,eff));
  invalidateOperationsCaches();
  calcSummary();
  queueSaveAppState();
}

function buildUndepTable(){
  const gpTotal=guildGP();
  document.getElementById('undep-tbody').innerHTML=Array.from({length:6},(_,i)=>{
    const u=dailyUndep[i]||0;
    const eff=undepMode==='pct'?gpTotal*(1-u/100):gpTotal-u;
    return`<tr><td style="color:var(--gold);font-family:'Orbitron',monospace;font-size:.7rem">D${i+1}</td><td><input type="number" min="0" max="${undepMode==='pct'?100:gpTotal}" value="${u}" oninput="setDailyUndepValue(${i}, this.value)"></td><td id="undep-eff-${i}" style="font-family:'Orbitron',monospace;font-size:.72rem;color:var(--text)">${fmtM(Math.max(0,eff))}</td></tr>`;
  }).join('');
}
function fillSameUndep(){const v=dailyUndep[0]||0;for(let i=1;i<6;i++)dailyUndep[i]=v;buildUndepTable();invalidateOperationsCaches();calcSummary();queueSaveAppState();}
function applyDefaultsToPlanner(){
  ALL_PLANETS.forEach(p=>{
    const d=chainDepth(p.id);
    const cmR=clamp(cmBase()-cmFall()*d,0,100);const flR=clamp(flBase()-flFall()*d,0,100);
    if(cmMode==='pct'){pState[p.id].cmRateOverride=cmR;pState[p.id].fleetRateOverride=flR;}
    else{pState[p.id].cmCountOverride=Math.round(members()*cmR/100);pState[p.id].fleetCountOverride=Math.round(members()*flR/100);}
  });
  rebuildPlannerChains();
  const el=document.getElementById('apply-status');el.textContent='✓ Applied to all planets';setTimeout(()=>el.textContent='',2500);
  invalidateOperationsCaches();
  calcSummary();
  queueSaveAppState();
}

function buildAppStateSnapshot(options={}){
  const includeVolatile = !!options.includeVolatile;
  const snapshot = {
    version: APP_STATE_VERSION,
    savedAt: new Date().toISOString(),
    primaryAllyCode: _primaryAllyCode,
    guideData: normalizeGuideData(guideData),
    opsDefinitions: normalizeOperationsDefinitionsData(_opsDefinitions),
    pState: JSON.parse(JSON.stringify(pState)),
    cmMode,
    undepMode,
    dailyUndep: [...dailyUndep],
    settings: {
      guildGp: guildGP(),
      guildMembers: members(),
      cmBase: cmBase(),
      cmFalloff: cmFall(),
      fleetBase: flBase(),
      fleetFalloff: flFall(),
    },
    optimizerWarningAccepted: _optimizerWarningAccepted,
    operationsSelection: {day: _opsSelectedDay, planet: _opsSelectedPlanet},
    activeGuide: _activeGuide,
    expandedGuidePlanets: _expandedPlanets,
  };
  if(includeVolatile){
    snapshot.guildSummary = getCurrentGuildSummary();
    snapshot.guildRosters = normalizeGuildRostersData(guildRosters);
    snapshot.lastPlanStars = _lastPlanStars;
    snapshot.lastPlanResult = _lastPlanResult;
    snapshot.platoonAnalysis = _platoonAnalysis;
    snapshot.selectedGuideMember = document.getElementById('guide-member-sel')?.value || '';
    snapshot.selectedRosterMember = document.getElementById('roster-member-sel')?.value || '';
  }
  return snapshot;
}

async function saveAppState(){
  if(_appStateHydrating) return;
  const snapshot = buildAppStateSnapshot();
  await fetch('/api/app-state', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify(snapshot)
  });
}

function queueSaveAppState(delay=250){
  if(_appStateHydrating) return;
  clearTimeout(_saveStateTimer);
  _saveStateTimer = setTimeout(()=>{
    saveAppState().catch(err=>console.warn('[ROTE] State save skipped:', err.message));
  }, delay);
}

function applyPersistedAppState(state, options={}){
  if(!state || typeof state !== 'object') return;
  const allowVolatile = !!options.allowVolatile;
  _appStateHydrating = true;
  try{
    _primaryAllyCode = String(state.primaryAllyCode || '').trim();
    const allyInput = document.getElementById('ally-code-input');
    if(allyInput && _primaryAllyCode) allyInput.value = _primaryAllyCode;

    if(state.cmMode === 'pct' || state.cmMode === 'count'){
      cmMode = state.cmMode;
      updateCmModeUi();
    }
    if(state.undepMode === 'pct' || state.undepMode === 'flat'){
      undepMode = state.undepMode;
      updateUndepModeUi();
    }

    const settings = state.settings || {};
    if(settings.guildGp != null) document.getElementById('guild-gp').value = settings.guildGp;
    if(settings.guildMembers != null) document.getElementById('guild-members').value = settings.guildMembers;
    if(settings.cmBase != null) document.getElementById('cm-base').value = settings.cmBase;
    if(settings.cmFalloff != null) document.getElementById('cm-falloff').value = settings.cmFalloff;
    if(settings.fleetBase != null) document.getElementById('fleet-base').value = settings.fleetBase;
    if(settings.fleetFalloff != null) document.getElementById('fleet-falloff').value = settings.fleetFalloff;
    sanitizeMissionEstimateInputs();

    if(Array.isArray(state.dailyUndep)){
      for(let i=0;i<6;i++) dailyUndep[i] = Number(state.dailyUndep[i]) || 0;
    }

    if(allowVolatile && state.guildSummary){
      renderGuildSummary(state.guildSummary, {silent:true, preserveScans:true});
    }
    if(allowVolatile){
      guildRosters = normalizeGuildRostersData(state.guildRosters || {});
      rebuildUnitNameIndex();
    }

    if(state.guideData) guideData = normalizeGuideData(state.guideData);
    if(state.opsDefinitions) _opsDefinitions = normalizeOperationsDefinitionsData(state.opsDefinitions);
    if(state.pState && typeof state.pState === 'object'){
      Object.keys(pState).forEach(pid=>{
        if(!state.pState[pid]) return;
        const next = state.pState[pid];
        const meta = ALL_PLANETS.find(planet=>planet.id===pid);
        const legacyUnlockReady = !!(meta?.smUnlocks && meta?.smThreshold && (Number(next.smCount)||0) >= Number(meta.smThreshold));
        pState[pid] = {
          ...pState[pid],
          ...next,
          smReady: typeof next.smReady === 'boolean' ? next.smReady : legacyUnlockReady,
          ops: Array.isArray(next.ops) ? next.ops.slice(0,6).map(Boolean) : pState[pid].ops
        };
      });
    }

    _platoonAnalysis = (allowVolatile && state.platoonAnalysis && typeof state.platoonAnalysis === 'object')
      ? state.platoonAnalysis
      : {};
    _lastPlanResult = (allowVolatile && state.lastPlanResult && Array.isArray(state.lastPlanResult.days))
      ? state.lastPlanResult
      : null;
    _lastPlanStars = allowVolatile ? (state.lastPlanStars ?? null) : null;
    _optimizerWarningAccepted = !!state.optimizerWarningAccepted;
    _opsSelectedDay = Math.max(1, Number(state.operationsSelection?.day) || 1);
    _opsSelectedPlanet = String(state.operationsSelection?.planet || '').trim();
    _planDirty = false;
    _activeGuide = state.activeGuide || null;
    _expandedPlanets = (state.expandedGuidePlanets && typeof state.expandedGuidePlanets === 'object')
      ? state.expandedGuidePlanets
      : {};

    buildUndepTable();
    renderFalloffViz();
    refreshGuideUnitLinks();

    if(allowVolatile && scannedRosterCount() > 0){
      renderRosterAnalysis(recountKeyUnits(), scannedRosterCount());
    }
    populateMemberDropdown();
    initRosterTab();

    if(allowVolatile){
      const guideSel = document.getElementById('guide-member-sel');
      if(guideSel && state.selectedGuideMember) guideSel.value = state.selectedGuideMember;

      const rosterSel = document.getElementById('roster-member-sel');
      if(rosterSel && state.selectedRosterMember){
        rosterSel.value = state.selectedRosterMember;
        loadMemberRoster(state.selectedRosterMember);
      }
    }

    if(document.getElementById('chain-ds').innerHTML) rebuildPlannerChains();
    if(_activeGuide) renderGuideMission(_activeGuide.pid, _activeGuide.mid);
    updateOperationsTabVisibility();
    renderDayPlanGuide();
    if(allowVolatile && hasCompletedOptimization()){
      renderOptPlan(_lastPlanResult, 'loaded', []);
    } else if(document.getElementById('panel-operations')?.classList.contains('active')){
      initOperationsTab();
    }
    calcSummary();
    updateDayPlanUiState({preserveStatus: allowVolatile && hasCompletedOptimization()});
  } finally {
    _appStateHydrating = false;
  }
}

async function loadPersistedAppState(){
  try{
    const resp = await fetch('/api/app-state', {method:'GET'});
    const data = await resp.json();
    if(data && data.state) applyPersistedAppState(data.state);
  }catch(err){
    console.warn('[ROTE] State restore skipped:', err.message);
  }
}

function calcSummary(){
  let st=0,ot=0,om=0;
  ALL_PLANETS.forEach(p=>{
    if(p.unlockedBy&&!bonusUnlocked(p.id))return;
    const{star}=calcStars(p.id,1);const{opsFilled}=calcPlanetPts(p.id,1);
    st+=star;ot+=opsFilled;om+=6;
  });
  const s=id=>{const e=document.getElementById(id);if(e)e.textContent=arguments[1];};
  // Est. Stars: use last optimization result if available (matches day-by-day plan)
  // Falls back to quick greedy optimizer if no plan has been run yet
  if (_lastPlanStars !== null) {
    document.getElementById('s-stars').textContent='★ '+_lastPlanStars;
    if(_lastPlanResult?.opsSummary){
      ot = _lastPlanResult.opsSummary.totalCompleted;
      om = _lastPlanResult.opsSummary.totalPlatoons;
    }
  } else {
    try {
      const optRes = runOptimizer();
      document.getElementById('s-stars').textContent='★ '+optRes.totalStars;
      if(optRes?.opsSummary){
        ot = optRes.opsSummary.totalCompleted;
        om = optRes.opsSummary.totalPlatoons;
      }
    } catch(e) {
      document.getElementById('s-stars').textContent='★ '+st;
    }
  }
  document.getElementById('s-ops').textContent=ot+'/'+om;
}

// PLANET PLANNER
function capabilityBadge(pid){
  try{
    const cap=calcMemberCapability(pid);
    if(!cap||cap.total===0)return '';
    const clr=cap.cmPct>=80?'var(--mx)':cap.cmPct>=50?'var(--gold2)':'var(--ds)';
    return '<div style="font-size:.58rem;color:'+clr+';margin-top:1px">'+
           cap.canCM+'/'+cap.total+' can do R'+cap.req.cmRelic+'+ CMs</div>';
  }catch(e){return '';}
}

function buildPlanetCard(p,depth){
  const s=pState[p.id];const m=members();const isBonus=!!p.unlockedBy;
  const unlocked=isBonus?bonusUnlocked(p.id):true;
  const missionMeta = getPlanetMissionEstimateMeta(p.id);
  const scoringCombatMissions = missionMeta.combat.length ? missionMeta.combat : Array.from({length:p.cms||0},(_,i)=>({label:'CM '+(i+1),points:p.cmPts||0}));
  const scoringFleetMissions = missionMeta.fleet.length ? missionMeta.fleet : Array.from({length:p.fleets||0},(_,i)=>({label:i===0?'Fleet':'Fleet '+(i+1),points:p.fleetPts||0,type:'fleet'}));
  const specialGuideMissions = missionMeta.nonPointSpecial;
  const unlockMission = specialGuideMissions.find(m=>m.unlocks);
  const regularSpecialMissions = specialGuideMissions.filter(m=>!m.unlocks);
  const{total,cmPts,flPts,opsFilled,cmExpected,flExpected}=calcPlanetPts(p.id,1);
  const p3=Math.min(100,total/p.stars[2]*100);
  let stars=0;for(let i=0;i<3;i++)if(total>=p.stars[i])stars=i+1;
  const starsHtml=[0,1,2].map(i=>`<span class="star${i<stars?' on':''}">${i<stars?'★':'☆'}</span>`).join('');
  const needPts=stars<3?p.stars[stars]-total:0;
  let cardClass=`pcard ${isBonus?'bonus-card':p.align}`;
  if(stars===3)cardClass+=' s3';else if(stars===2)cardClass+=' s2';else if(stars===1)cardClass+=' s1';
  if(isBonus&&!unlocked)cardClass+=' locked-planet';
  const cmDisp=cmMode==='pct'?(s.cmRateOverride!==null?s.cmRateOverride:Math.round(clamp(cmBase()-cmFall()*depth,0,100))):(s.cmCountOverride!==null?s.cmCountOverride:Math.round(m*clamp((cmBase()-cmFall()*depth)/100,0,1)));
  const flDisp=cmMode==='pct'?(s.fleetRateOverride!==null?s.fleetRateOverride:Math.round(clamp(flBase()-flFall()*depth,0,100))):(s.fleetCountOverride!==null?s.fleetCountOverride:Math.round(m*clamp((flBase()-flFall()*depth)/100,0,1)));
  const specialNames = regularSpecialMissions.map(m=>m.label).join(', ');
  const smHtml=unlockMission
    ? `<div class="sm-box"><div class="sm-box-label">${unlockMission.label}</div><label class="ops-slot-row" style="align-items:center;gap:10px;cursor:pointer"><input type="checkbox" ${s.smReady?'checked':''} onchange="setSmReady('${p.id}',this.checked)"><span style="font-size:.78rem;color:var(--text)">Plan to unlock ${(unlockMission.unlocks||'').charAt(0).toUpperCase() + (unlockMission.unlocks||'').slice(1)} on ${p.name}</span></label><div class="sm-note">${s.smReady?`<span style="color:var(--bonus)">✓ ${(unlockMission.unlocks||'').charAt(0).toUpperCase() + (unlockMission.unlocks||'').slice(1)} is enabled for the planner</span>`:'Leave unchecked unless the guild can clear this unlock special mission.'}${specialNames?'<br>Other special missions: '+escHtml(specialNames):''}</div></div>`
    : (regularSpecialMissions.length
      ? `<div class="sm-box"><div class="sm-box-label">${regularSpecialMissions.length>1?'Special Missions':'Special Mission'}</div><div class="sm-note">Guide-only missions on this planet: ${escHtml(specialNames)}. These do not add projected territory points.</div></div>`
      : '');
  const flHtml=scoringFleetMissions.map((mission, idx)=>`<div class="cm-row" data-est-group="fleet" data-points="${Number(mission.points)||0}" data-points-single="${Number(mission.pointsSingle)||0}"><span class="cm-row-label">${escHtml(mission.label || (idx===0?'Fleet':'Fleet '+(idx+1)))}</span><div><div class="mini-label">${cmMode==='pct'?'Comp %':'Comp #'}</div><input class="mini-in" type="number" min="0" max="${cmMode==='pct'?100:m}" value="${flDisp}" oninput="setFleetOv('${p.id}',this.value)"></div><div><div class="mini-label">est pts</div><div class="mini-val">${fmtM(projectFleetMissionPoints(mission, flExpected))}</div></div></div>`).join('');
  const combatRows=scoringCombatMissions.map((mission, idx)=>`<div class="cm-row" data-est-group="cm" data-points="${Number(mission.points)||0}" data-points-single="${Number(mission.pointsSingle)||0}"><span class="cm-row-label">${escHtml(mission.label || ('CM '+(idx+1)))}</span><div><div class="mini-label">${cmMode==='pct'?'Clear %':'Clear #'}</div><input class="mini-in" type="number" min="0" max="${cmMode==='pct'?100:m}" value="${cmDisp}" oninput="setCmOv('${p.id}',this.value)"></div><div><div class="mini-label">est pts</div><div class="mini-val">${fmtM(projectCombatMissionPoints(mission, cmExpected))}</div></div></div>`).join('');
  return`<div class="${cardClass}" id="card-${p.id}">
<div class="pcard-header"><div>
      <div class="pcard-name">${p.name}</div>
      ${capabilityBadge(p.id)}
    </div><span class="align-badge ${isBonus&&!unlocked?'bonus-locked':p.align}">${isBonus?(unlocked?'Bonus ✓':'Bonus 🔒'):p.align==='ds'?'Dark':p.align==='mx'?'Mixed':'Light'}</span></div>
<div class="stars-row">${starsHtml}</div>
<div class="pts-row">Est: <b>${fmtM(total)}</b> / ${fmtM(p.stars[2])} <span style="color:var(--text3)">(3★)</span></div>
<div class="prog-wrap"><div class="prog-fill gold" style="width:${p3.toFixed(1)}%"></div></div>
<div style="margin-top:10px">
<div class="msec-head">Combat / Special Missions (${scoringCombatMissions.length}) <span></span></div>
${combatRows}
${flHtml}</div>
${smHtml}
<div class="msec-head">Operations <span></span></div>
${getPlatoonHtml(p.id)}
<div class="pnote ${stars===3?'maxed':'need'}">${stars===3?'✓ 3 stars achievable':fmt(Math.round(Math.max(0,needPts)))+' pts needed for '+(stars+1)+'★'}</div>
</div>`;
}

function rebuildPlannerChains(){
  ['ds','mx','ls'].forEach(chain=>{
    const arr=chain==='ds'?DS_CHAIN:chain==='mx'?MX_CHAIN:LS_CHAIN;
    const el=document.getElementById('chain-'+chain);el.innerHTML='';
    arr.forEach((p,idx)=>{
      const row=document.createElement('div');row.className='planet-row';
      const col=document.createElement('div');col.className='chain-col';
      if(idx>0){const s=document.createElement('div');s.className='chain-seg '+chain;col.appendChild(s);}
      const dot=document.createElement('div');dot.className='chain-dot '+chain;col.appendChild(dot);
      if(idx<arr.length-1){const s=document.createElement('div');s.className='chain-seg '+chain;col.appendChild(s);}
      row.appendChild(col);
      const cw=document.createElement('div');cw.style.flex='1';cw.style.minWidth='0';
      cw.innerHTML=buildPlanetCard(p,idx);row.appendChild(cw);
      const bonus=BONUS_PLANETS.find(b=>b.unlockedBy===p.id);
      if(bonus){
        const bc=document.createElement('div');bc.style.display='flex';bc.style.flexDirection='column';bc.style.alignItems='flex-start';bc.style.flexShrink='0';
        bc.innerHTML='<div class="bonus-horiz"></div>';
        row.appendChild(bc);
        const bw=document.createElement('div');bw.style.flex='1';bw.style.minWidth='0';
        bw.innerHTML=buildPlanetCard(bonus,idx+0.5);row.appendChild(bw);
      }
      el.appendChild(row);
    });
  });
  calcSummary();
}

function updateCard(pid){
  const p=ALL_PLANETS.find(x=>x.id===pid);const el=document.getElementById('card-'+pid);if(!el)return;
  const{total,cmPts,flPts,opsFilled,cmExpected,flExpected}=calcPlanetPts(pid,1);const p3=Math.min(100,total/p.stars[2]*100);
  let stars=0;for(let i=0;i<3;i++)if(total>=p.stars[i])stars=i+1;
  const st=el.querySelector('.stars-row');if(st)st.innerHTML=[0,1,2].map(i=>`<span class="star${i<stars?' on':''}">${i<stars?'★':'☆'}</span>`).join('');
  const pt=el.querySelector('.pts-row');if(pt)pt.innerHTML=`Est: <b>${fmtM(total)}</b> / ${fmtM(p.stars[2])} <span style="color:var(--text3)">(3★)</span>`;
  const pr=el.querySelector('.prog-fill');if(pr)pr.style.width=p3.toFixed(1)+'%';
  el.querySelectorAll('.cm-row[data-est-group]').forEach(row=>{
    const points = Number(row.dataset.points || 0);
    const pointsSingle = Number(row.dataset.pointsSingle || 0);
    const group = row.dataset.estGroup;
    const val = row.querySelector('.mini-val');
    if(!val) return;
    if(group === 'fleet'){
      val.textContent = fmtM(projectFleetMissionPoints({points, pointsSingle}, flExpected));
      return;
    }
    val.textContent = fmtM(projectCombatMissionPoints({points, pointsSingle}, cmExpected));
  });
  const pn=el.querySelector('.pnote');if(pn){const need=stars<3?p.stars[stars]-total:0;pn.className='pnote '+(stars===3?'maxed':'need');pn.textContent=stars===3?'✓ 3 stars achievable':fmt(Math.round(Math.max(0,need)))+' pts needed for '+(stars+1)+'★';}
  const on=el.querySelector('.ops-pts-note');if(on)on.outerHTML=getPlatoonHtml(pid);
  el.className=el.className.replace(/\bs[123]\b/g,'').trim();
  if(stars===3)el.classList.add('s3');else if(stars===2)el.classList.add('s2');else if(stars===1)el.classList.add('s1');
  calcSummary();
  queueSaveAppState();
}
function setCmOv(pid,v){
  const limit = cmMode==='pct' ? 100 : 50;
  if(cmMode==='pct') pState[pid].cmRateOverride=parseClampedNumber(v,0,0,limit,false);
  else pState[pid].cmCountOverride=parseClampedNumber(v,0,0,limit,true);
  invalidateOperationsCaches();
  updateCard(pid);
}
function setFleetOv(pid,v){
  const limit = cmMode==='pct' ? 100 : 50;
  if(cmMode==='pct') pState[pid].fleetRateOverride=parseClampedNumber(v,0,0,limit,false);
  else pState[pid].fleetCountOverride=parseClampedNumber(v,0,0,limit,true);
  invalidateOperationsCaches();
  updateCard(pid);
}
function setSmReady(pid,checked){pState[pid].smReady=!!checked;invalidateOperationsCaches();updateCard(pid);rebuildPlannerChains();}
// DAY PLAN OPTIMIZER

// Mission + ops points only — GP is allocated separately by the optimizer
// ── Correct mission point model ───────────────────────────────────────
// Each CM completion = fixed pts per player (cmPts), scaled by expected completions
// Fleet completion   = fixed pts per player (fleetPts), scaled by expected completions
// Ops platoon        = fixed opsVal per filled platoon (not per-player)
//
// "Expected completions" = active_members × completion_rate_for_this_zone
// Active members = guild_size × (1 - nonParticipationRate)
// The user sets cm/fleet completion rates per zone via the UI.
// Deployment points are NOT included here — they are the separate "budget"
// the optimizer allocates from the total guild GP pool.

function activeMemberCount() {
  // All guild members are counted; use Daily Undeployed GP to account for absent members
  return members();
}

function nonParticipationRate() {
  return 0; // Handled via Daily Undeployed GP table
}

// Returns total expected recurring mission territory points for a planet
// (CMs + fleet only — operations are planned separately as one-time points)
function missionOnlyPts(pid) {
  const p = ALL_PLANETS.find(x => x.id === pid);
  const active = activeMemberCount();
  const cmR  = effectiveCmRate(pid);   // fraction of active members who complete each CM
  const flR  = effectiveFleetRate(pid); // fraction of active members who complete fleet
  const missionMeta = getPlanetMissionEstimateMeta(pid);
  const fallbackCombatTotal = (p.cms || 0) * (p.cmPts || 0);
  const fallbackFleetTotal = (p.fleets || 0) * (p.fleetPts || 0);
  const cmExpected = active * cmR;
  const flExpected = active * flR;
  const cmPts = missionMeta.combat.length
    ? missionMeta.combat.reduce((sum, mission)=>sum + projectCombatMissionPoints(mission, cmExpected), 0)
    : Math.round(cmExpected) * fallbackCombatTotal;
  const flPts = missionMeta.fleet.length
    ? missionMeta.fleet.reduce((sum, mission)=>sum + projectFleetMissionPoints(mission, flExpected), 0)
    : Math.round(flExpected) * fallbackFleetTotal;

  return cmPts + flPts;
}

function starsAt(planet, pts) {
  let s = 0;
  for (let i = 0; i < 3; i++) if (pts >= planet.stars[i]) s = i + 1;
  return s;
}

// Returns deployable GP for a given day.
// Base = guild GP × participation rate (non-participating members' GP unavailable)
// Minus daily adjustment (undeployed % or flat amount the user sets per day).
// This is the total GP pool available to split across all active territories.
function gpForDay(day) {
  const total  = guildGP();
  const active = total * (1 - nonParticipationRate());
  const u      = dailyUndep[day - 1] || 0;
  return undepMode === 'pct'
    ? active * (1 - u / 100)
    : active - u;
}

// ── Greedy future simulation used to score decision branches ──────
function simulateFuture(todayDecision, todayGP, active, CHAINS, origSt, day) {
  // Clone state and apply today's decisions
  const st = {
    ds: { idx: origSt.ds.idx, banked: origSt.ds.banked },
    mx: { idx: origSt.mx.idx, banked: origSt.mx.banked },
    ls: { idx: origSt.ls.idx, banked: origSt.ls.banked }
  };

  ['ds', 'mx', 'ls'].forEach(c => {
    const a = active[c];
    if (!a) return;
    const d = todayDecision[c];
    const gp = todayGP[c] || 0;
    if (d === 0) {
      // Cap banked points below 1-star threshold — crossing 1-star locks the planet
      st[c].banked = Math.min(a.base, a.p.stars[0] - 1);
    } else {
      const pts = a.base + gp;
      const stars = starsAt(a.p, pts);
      if (stars >= 1) { st[c].idx++; st[c].banked = 0; }
      else { st[c].banked = a.base; }
    }
  });

  // Simulate remaining days with proportional GP allocation.
  // Sequential (DS-first) allocation starves LS when DS+MX exhaust the budget.
  // Instead: compute each chain's GP need, then split the budget proportionally
  // so no chain is left with 0 GP when there's enough to give everyone something.
  let future = 0;
  for (let fd = day + 1; fd <= 6; fd++) {
    const gpDay = gpForDay(fd);
    let dayStars = 0;

    // Pass 1: compute each active chain's GP need for best affordable stars
    const chains3 = ['ds', 'mx', 'ls'];
    const need  = {};  // GP needed to reach best affordable star tier
    const bases = {};  // base mission points

    chains3.forEach(c => {
      if (st[c].idx >= CHAINS[c].length) { need[c] = 0; bases[c] = -1; return; }
      const p = CHAINS[c][st[c].idx];
      const mpts = missionOnlyPts(p.id);
      const base = st[c].banked + mpts;
      bases[c] = base;
      need[c] = Math.max(0, p.stars[2] - base); // target 3★
    });

    // Pass 2: proportional allocation — if total need > budget, scale down fairly
    const totalNeed = chains3.reduce((s,c) => s + need[c], 0);
    const ratio = totalNeed > gpDay ? gpDay / totalNeed : 1;

    chains3.forEach(c => {
      if (bases[c] < 0) return;
      const p = CHAINS[c][st[c].idx];
      const gpUsed = Math.round(need[c] * ratio);
      const pts = bases[c] + gpUsed;
      const stars = starsAt(p, pts);
      if (stars >= 1) { st[c].idx++; st[c].banked = 0; }
      else { st[c].banked = bases[c]; } // bank mission points for tomorrow
      dayStars += stars;
    });

    if (dayStars === 0) break;
    future += dayStars;
  }
  return future;
}

// Alias for genome wrapper — returns {days, totalStars}
function runOptimizerResult() {
  try { return ensureProjectedPlanResult() || runOptimizer(); } catch(e) { return null; }
}

// ── Core optimizer: enumerate all decisions, pick best ────────────
function runOptimizer() {
  const CHAINS = { ds: DS_CHAIN, mx: MX_CHAIN, ls: LS_CHAIN };
  const st = {
    ds: { idx: 0, banked: 0 },
    mx: { idx: 0, banked: 0 },
    ls: { idx: 0, banked: 0 }
  };
  const bonusState = createBonusActivationState();
  const results = [];
  let totalStars = 0;

  for (let day = 1; day <= 6; day++) {
    const gpDay = gpForDay(day);
    const isLast = day === 6;
    const notices = [];
    const activeBonusPlanets = getActiveBonusPlanetsForDay(bonusState, day);

    // Active planet + base points for each chain
    const act = {};
    ['ds', 'mx', 'ls'].forEach(c => {
      if (st[c].idx >= CHAINS[c].length) { act[c] = null; return; }
      const p = CHAINS[c][st[c].idx];
      const mpts = missionOnlyPts(p.id);
      act[c] = { p, base: st[c].banked + mpts, mpts };
    });

    // Decision space per chain: 0=preload, 1/2/3 = commit targeting N stars
    // On last day: no preloading
    const OPTS = isLast ? [1, 2, 3] : [0, 1, 2, 3];

    let bestScore = -Infinity;
    let bestD = null;
    let bestGP = null;

    for (const d_ds of (act.ds ? OPTS : [-1])) {
      for (const d_mx of (act.mx ? OPTS : [-1])) {
        for (const d_ls of (act.ls ? OPTS : [-1])) {
          const d = { ds: d_ds, mx: d_mx, ls: d_ls };
          const gp = { ds: 0, mx: 0, ls: 0 };
          let gpTotal = 0;
          let starsNow = 0;

          ['ds', 'mx', 'ls'].forEach(c => {
            const a = act[c];
            if (!a || d[c] < 0 || d[c] === 0) return; // skip or preload
            // Target d[c] stars
            const tPts = a.p.stars[d[c] - 1];
            const gpNeed = Math.max(0, tPts - a.base);
            gp[c] = gpNeed;
            gpTotal += gpNeed;
            starsNow += starsAt(a.p, a.base + gpNeed);
          });

          if (gpTotal > gpDay) continue;  // can't afford
          if (starsNow === 0) continue;    // 0-star day — TB would end

          // Score = stars today + greedy future simulation
          const future = simulateFuture(d, gp, act, CHAINS, st, day);
          const score = starsNow + future;

          if (score > bestScore) {
            bestScore = score;
            bestD = d;
            bestGP = gp;
          }
        }
      }
    }

    // Fallback: if nothing valid found, commit cheapest option on each chain
    if (!bestD) {
      bestD = { ds: 1, mx: 1, ls: 1 };
      bestGP = { ds: 0, mx: 0, ls: 0 };
      ['ds', 'mx', 'ls'].forEach(c => {
        const a = act[c];
        if (!a) return;
        const need = Math.max(0, a.p.stars[0] - a.base);
        if (need <= gpDay) bestGP[c] = need;
      });
    }

    // Execute the best decision
    const dayRes = { day, gpAvail: gpDay, gpUsed: 0, starsDay: 0, chains: {}, notices, bonusPlanets: [] };
    let spareGP = gpDay;

    ['ds', 'mx', 'ls'].forEach(c => {
      const a = act[c];
      if (!a) { dayRes.chains[c] = { status: 'complete' }; return; }

      const tStar = bestD[c];
      const gp = bestGP[c] || 0;

      if (tStar <= 0) {
        // Preload — cap below 1-star threshold (crossing it locks the planet)
        const maxSafe = a.p.stars[0] - 1;
        const safeBanked = Math.min(a.base, maxSafe);
        const alreadyBanked = st[c].banked > 0; // was preloaded yesterday
        // Never preload same planet 2 days in a row — if we banked yesterday, force commit
        if (alreadyBanked) {
          // Override to commit even at 0 stars — avoids infinite preload loop
          const pts2 = a.base;
          const stars2 = starsAt(a.p, pts2);
          dayRes.chains[c] = {
            status: stars2>=1 ? 'commit' : 'building',
            planet: a.p, pts: pts2, gpDeployed: 0,
            stars: stars2, pctOf3: Math.round(pts2/a.p.stars[2]*100),
            preloadAmt: st[c].banked,
            note: 'Was preloaded yesterday — committing today regardless'
          };
          dayRes.starsDay += stars2;
          if(stars2>=1){
            st[c].idx++;
            st[c].banked=0;
            scheduleUnlockedBonusPlanets(bonusState, a.p.id, day, notices);
          }
          else { st[c].banked = safeBanked; }
        } else {
          st[c].banked = safeBanked;
          const tomorrow = safeBanked + a.mpts;
          dayRes.chains[c] = {
            status: 'preload',
            planet: a.p,
            banked: safeBanked,
            tomorrowEst: tomorrow,
            threshold1star: a.p.stars[0]
          };
        }
      } else {
        const pts = a.base + gp;
        const stars = starsAt(a.p, pts);
        const pctOf3 = Math.min(100, Math.round(pts / a.p.stars[2] * 100));
        dayRes.chains[c] = {
          status: stars >= 1 ? 'commit' : 'building',
          planet: a.p,
          pts,
          gpDeployed: gp,
          stars,
          pctOf3,
          preloadAmt: st[c].banked
        };
        dayRes.starsDay += stars;
        dayRes.gpUsed += gp;
        spareGP -= gp;

        if (stars >= 1) {
          st[c].idx++;
          st[c].banked = 0;
          scheduleUnlockedBonusPlanets(bonusState, a.p.id, day, notices);
        } else {
          st[c].banked = a.base;
        }
      }
    });

    // Bonus planets: use spare GP
    activeBonusPlanets.forEach(({planet:b, state}) => {
      const mpts = missionOnlyPts(b.id);
      const base = state.banked + mpts;
      const gpNeed = Math.max(0, b.stars[2] - base);
      const gpUsed = Math.min(spareGP, gpNeed);
      spareGP -= gpUsed;
      const pts = base + gpUsed;
      const bs = starsAt(b, pts);
      const carryOver = bs >= 1 ? 0 : Math.min(pts, b.stars[0] - 1);
      if (bs >= 1) {
        state.done = true;
        state.banked = 0;
      } else {
        state.banked = carryOver;
      }
      dayRes.bonusPlanets.push({
        planet: b,
        pts,
        stars: bs,
        gpDeployed: gpUsed,
        carryOver,
        activeFromDay: state.activeFromDay,
        unlockedOnDay: state.unlockedOnDay
      });
      dayRes.starsDay += bs;
    });

    totalStars += dayRes.starsDay;
    results.push(dayRes);
  }

  return { days: results, totalStars };
}

// ── AI Deep Planning ──────────────────────────────────────────────
function buildAIPrompt() {
  const CHAINS_MAP = { ds: DS_CHAIN, mx: MX_CHAIN, ls: LS_CHAIN };
  const gpBudgets = Array.from({ length: 6 }, (_, i) => Math.round(gpForDay(i + 1)));

  const formatChain = (chain) => chain.map((p, i) => {
    const mpts = Math.round(missionOnlyPts(p.id));
    return `  Planet ${i + 1}: ${p.name} | ${mpts.toLocaleString()} pts/day from missions | 1-star: ${p.stars[0].toLocaleString()} | 2-star: ${p.stars[1].toLocaleString()} | 3-star: ${p.stars[2].toLocaleString()}`;
  }).join('\n');

  return `You are optimizing a Star Wars Galaxy of Heroes Territory Battle (Rise of the Empire) for maximum stars.

CRITICAL RULES:
1. Three independent chains: Dark Side (DS), Mixed (MX), Light Side (LS) — each with 6 planets unlocking in sequence
2. A planet is "committed" when it reaches its 1-star threshold — it locks and the next planet unlocks the NEXT day
3. "Preloading" = banking mission points on a planet without reaching 1-star. Planet stays open tomorrow
4. CRITICAL: At least 1 star must be earned SOMEWHERE each day or the Territory Battle ends permanently
5. On Day 6 (last day): NEVER preload — commit everything possible
6. Daily GP (Galactic Power) can be split freely across any active planets
7. Missions accumulate each day a planet is open (preloading or committing)
8. A planet can be preloaded for MULTIPLE days to bank more mission points before committing

DAILY GP BUDGETS:
${gpBudgets.map((gp, i) => `Day ${i + 1}: ${gp.toLocaleString()}`).join('\n')}

PLANET DATA (mission pts/day = recurring combat + fleet points; operations are auto-planned separately):
Dark Side Chain:
${formatChain(DS_CHAIN)}

Mixed Chain:
${formatChain(MX_CHAIN)}

Light Side Chain:
${formatChain(LS_CHAIN)}

GUILD: ${members()} members, ${Math.round(guildGP() / 1e6)}M total GP

KEY STRATEGIC INSIGHTS to consider:
- Early planets (1-2 in each chain) are cheaper — often worth 3-starring quickly to unlock harder ones with more preload time
- Later planets have massive thresholds — you often need 2+ days of preloading before committing
- You can preload 2 chains and commit 1 on the same day (still earns stars, keeps TB alive)
- Getting from 0 to 1-star is the biggest GP jump — the jump from 1-star to 3-star is often smaller
- Day 5 is often a "big preload day" where you preload the hardest remaining planet while committing others
- Sometimes 2-starring a planet and advancing the chain is better than 3-starring and being stuck

Provide a day-by-day plan that MAXIMIZES total stars. Respond ONLY with this exact JSON:
{
  "plan": [
    {
      "day": 1,
      "reasoning": "Brief explanation of why this day's decisions maximize long-term stars",
      "ds": {"planet": "Mustafar", "action": "commit3", "gp_deploy": 0, "stars_earned": 3, "note": "Can 3-star with missions alone"},
      "mx": {"planet": "Corellia", "action": "preload", "gp_deploy": 0, "stars_earned": 0, "note": "Need another day of missions to 3-star cheaply"},
      "ls": {"planet": "Coruscant", "action": "commit2", "gp_deploy": 50000000, "stars_earned": 2, "note": "2-star to advance chain, 3-star too expensive"},
      "total_stars": 5
    }
  ],
  "grand_total_stars": 35,
  "strategy_summary": "2-3 sentences on overall approach and key trade-offs made"
}

Action values: "commit1", "commit2", "commit3" (commit targeting 1/2/3 stars), "preload" (bank missions, 0 stars earned)`;
}


// MULTI-ALGORITHM OPTIMIZATION ENGINE
// All algorithms are implemented in-browser with no external dependencies.

// Genome encoding: flat array of 18 integers
// [d0_ds, d0_mx, d0_ls, d1_ds, d1_mx, d1_ls, ... d5_ds, d5_mx, d5_ls]
// Gene values: 0=preload, 1=target 1★, 2=target 2★, 3=target 3★
const OPT_GENES = 18; // 6 days × 3 chains
const OPT_CKEYS = ['ds','mx','ls'];
const OPT_CHAINS = {ds:DS_CHAIN, mx:MX_CHAIN, ls:LS_CHAIN};

// Last completed optimization result — used by calcSummary to sync Est. Stars
let _lastPlanStars = null;

// Yield control to UI thread
const _yield = () => new Promise(r => setTimeout(r, 0));

// ── Fitness evaluation ──────────────────────────────────────────────────────
function simulateGenomePlan(genome, detailed=false) {
  const st = {ds:{idx:0,banked:0}, mx:{idx:0,banked:0}, ls:{idx:0,banked:0}};
  const bonusState = createBonusActivationState();
  const opsState = createOperationsSimState(detailed);
  const days = [];
  let totalStars = 0;

  for (let day=0; day<6; day++) {
    const dayNumber = day + 1;
    const gpDay = gpForDay(dayNumber);
    const notices = [];
    const activeBonusPlanets = getActiveBonusPlanetsForDay(bonusState, dayNumber);
    const previewPlan = {day:dayNumber, chains:{}, bonusPlanets:[]};
    OPT_CKEYS.forEach((c,ci)=>{
      const gene = genome[day*3+ci];
      if(st[c].idx >= OPT_CHAINS[c].length){
        previewPlan.chains[c] = {status:'complete'};
        return;
      }
      const planet = OPT_CHAINS[c][st[c].idx];
      previewPlan.chains[c] = {
        planet,
        status: gene===0 ? 'preload' : 'commit',
        stars: gene
      };
    });
    activeBonusPlanets.forEach(entry=>{
      previewPlan.bonusPlanets.push({
        planet: entry.planet,
        activeFromDay: entry.state.activeFromDay,
        unlockedOnDay: entry.state.unlockedOnDay
      });
    });

    const dayOps = allocateOperationsForDay(dayNumber, previewPlan, opsState, detailed);
    const opsPointsByPlanet = {};
    Object.entries(dayOps.planets || {}).forEach(([pid, planet])=>{
      if(planet.pointsEarned) opsPointsByPlanet[pid] = Number(planet.pointsEarned)||0;
    });

    const targets = {}, gpNeed = {}, bases = {};
    OPT_CKEYS.forEach((c,ci)=>{
      const gene = genome[day*3+ci];
      if(st[c].idx >= OPT_CHAINS[c].length){
        targets[c] = -1;
        gpNeed[c] = 0;
        return;
      }
      const p = OPT_CHAINS[c][st[c].idx];
      const base = st[c].banked + missionOnlyPts(p.id) + (opsPointsByPlanet[p.id] || 0);
      bases[c] = base;
      targets[c] = gene;
      gpNeed[c] = gene===0 ? 0 : Math.max(0, p.stars[gene-1] - base);
    });
    const totalNeed = OPT_CKEYS.reduce((sum, c)=>sum + (gpNeed[c] || 0), 0);
    const ratio = totalNeed > gpDay ? gpDay / totalNeed : 1;

    let starsDay = 0;
    let gpUsed = 0;
    const chains = {};
    OPT_CKEYS.forEach(c=>{
      if(targets[c]===-1 || st[c].idx >= OPT_CHAINS[c].length){
        chains[c] = {status:'complete'};
        return;
      }
      const p = OPT_CHAINS[c][st[c].idx];
      const base = bases[c];
      const opsPts = opsPointsByPlanet[p.id] || 0;
      const missionPts = missionOnlyPts(p.id);
      if(targets[c]===0){
        const carryInPts = st[c].banked;
        const safeBanked = Math.min(base, p.stars[0]-1);
        st[c].banked = safeBanked;
        chains[c] = {
          status:'preload',
          planet:p,
          banked:safeBanked,
          tomorrowEst:safeBanked + missionOnlyPts(p.id),
          threshold1star:p.stars[0],
          carryInPts,
          missionPts,
          opsPts
        };
      } else {
        const carryInPts = st[c].banked;
        const gpAlloc = Math.round((gpNeed[c]||0) * ratio);
        const pts = base + gpAlloc;
        const stars = starsAt(p, pts);
        const pctOf3 = Math.min(100, Math.round(pts / p.stars[2] * 100));
        starsDay += stars;
        gpUsed += gpAlloc;
        chains[c] = {
          status:stars>=1?'commit':'building',
          planet:p,
          pts,
          gpDeployed:gpAlloc,
          stars,
          pctOf3,
          preloadAmt:st[c].banked,
          carryInPts,
          missionPts,
          opsPts
        };
        if(stars>=1){
          st[c].idx++;
          st[c].banked = 0;
          scheduleUnlockedBonusPlanets(bonusState, p.id, dayNumber, notices);
        }
        else { st[c].banked = base; }
      }
    });

    let spareGP = Math.max(0, gpDay - gpUsed);
    const bonusPlanets = [];
    activeBonusPlanets.forEach(({planet:b, state})=>{
      const missionPts = missionOnlyPts(b.id);
      const carryInPts = state.banked;
      const base = state.banked + missionOnlyPts(b.id) + (opsPointsByPlanet[b.id] || 0);
      const gpNeedB = Math.max(0, b.stars[2] - base);
      const gpUsedB = Math.min(spareGP, gpNeedB);
      spareGP -= gpUsedB;
      gpUsed += gpUsedB;
      const pts = base + gpUsedB;
      const stars = starsAt(b, pts);
      const carryOver = stars >= 1 ? 0 : Math.min(pts, b.stars[0]-1);
      bonusPlanets.push({
        planet:b,
        pts,
        stars,
        carryInPts,
        missionPts,
        opsPts:(opsPointsByPlanet[b.id] || 0),
        gpDeployed:gpUsedB,
        carryOver,
        activeFromDay:state.activeFromDay,
        unlockedOnDay:state.unlockedOnDay
      });
      starsDay += stars;
      if(stars>=1){
        state.done = true;
        state.banked = 0;
      } else {
        state.banked = carryOver;
      }
    });

    totalStars += starsDay;
    days.push({
      day: dayNumber,
      gpAvail: gpDay,
      gpUsed,
      starsDay,
      chains,
      notices,
      bonusPlanets,
      opsPoints: dayOps.pointsEarned || 0,
      opsCompleted: dayOps.completedPlatoons || [],
      opsPlanets: dayOps.planets || {}
    });
  }

  const opsSummary = summarizeOperationsState(
    opsState,
    days.map(d=>({
      day: d.day,
      pointsEarned: d.opsPoints || 0,
      completedPlatoons: d.opsCompleted || [],
      slotsFilled: Object.values(d.opsPlanets || {}).reduce((sum, planet)=>sum + (planet.slotsFilled || 0), 0),
      planets: d.opsPlanets || {}
    }))
  );
  return {days, totalStars, opsSummary, opsState};
}

function evalGenome(genome) {
  return simulateGenomePlan(genome, false).totalStars;
}

// ── Random / utility ───────────────────────────────────────────────────────
function rndGenome() { return Array.from({length:OPT_GENES},()=>Math.floor(Math.random()*4)); }
function clampGene(v) { return Math.max(0,Math.min(3,Math.round(v))); }
function seeded(lo,hi) { return lo + Math.floor(Math.random()*(hi-lo+1)); }

// ── Greedy baseline (existing rule-based converted to genome format) ────────
function greedyGenome() {
  if(_greedyGenomeCache) return [..._greedyGenomeCache];
  const genome = new Array(OPT_GENES).fill(1);
  for(let day=0; day<6; day++){
    const opts = day===5 ? [1,2,3] : [0,1,2,3];
    let bestCombo = [1,1,1];
    let bestScore = -Infinity;
    for(const ds of opts){
      for(const mx of opts){
        for(const ls of opts){
          const candidate = [...genome];
          candidate[day*3] = ds;
          candidate[day*3+1] = mx;
          candidate[day*3+2] = ls;
          const score = evalGenome(candidate);
          if(score > bestScore){
            bestScore = score;
            bestCombo = [ds,mx,ls];
          }
        }
      }
    }
    genome[day*3] = bestCombo[0];
    genome[day*3+1] = bestCombo[1];
    genome[day*3+2] = bestCombo[2];
  }
  _greedyGenomeCache = [...genome];
  return [...genome];
}

// ── Genetic Algorithm ───────────────────────────────────────────────────────
async function runGA(onProg, onDone) {
  const POP=160, GENS=140, ELITE=8, MUT=0.12;
  let pop = [greedyGenome(), ...Array.from({length:POP-1},rndGenome)];
  let scores = pop.map(evalGenome);
  let best = {genome:[...pop[0]], score:scores[0]};
  pop.forEach((g,i)=>{ if(scores[i]>best.score) best={genome:[...g],score:scores[i]}; });

  for (let gen=0; gen<GENS; gen++) {
    if (gen%12===0) { await _yield(); onProg(gen/GENS, best.score); }
    const ranked = pop.map((g,i)=>({g,s:scores[i]})).sort((a,b)=>b.s-a.s);
    const newPop = [];
    for (let i=0;i<ELITE;i++) newPop.push([...ranked[i].g]);
    const tour=(k=6)=>{
      let b=Math.floor(Math.random()*POP);
      for(let i=1;i<k;i++){const c=Math.floor(Math.random()*POP);if(scores[c]>scores[b])b=c;}
      return pop[b];
    };
    while (newPop.length<POP) {
      const p1=tour(), p2=tour();
      // Uniform crossover
      const child=p1.map((g,i)=>Math.random()<0.5?g:p2[i]);
      // Mutation (point + block)
      for (let i=0;i<OPT_GENES;i++) if(Math.random()<MUT) child[i]=Math.floor(Math.random()*4);
      // Occasional block mutation (swap a whole day)
      if (Math.random()<0.05) {
        const d=Math.floor(Math.random()*6);
        OPT_CKEYS.forEach((_,ci)=>{ child[d*3+ci]=Math.floor(Math.random()*4); });
      }
      newPop.push(child);
    }
    pop=newPop; scores=pop.map(evalGenome);
    pop.forEach((g,i)=>{ if(scores[i]>best.score) best={genome:[...g],score:scores[i]}; });
  }
  onProg(1, best.score); onDone(best);
}

// ── Simulated Annealing ─────────────────────────────────────────────────────
async function runSA(onProg, onDone) {
  const ITERS=8000, T0=120, Tf=0.05;
  let current = greedyGenome();
  let curScore = evalGenome(current);
  let best = {genome:[...current], score:curScore};
  const cool = Math.pow(Tf/T0, 1/ITERS);
  let T = T0;
  for (let i=0; i<ITERS; i++) {
    if (i%400===0) { await _yield(); onProg(i/ITERS, best.score); }
    const neighbor=[...current];
    // Variable-size perturbation: small near end, larger at start
    const nMut = T>T0*0.5 ? seeded(2,4) : seeded(1,2);
    for (let m=0;m<nMut;m++) {
      const idx=Math.floor(Math.random()*OPT_GENES);
      neighbor[idx]=Math.floor(Math.random()*4);
    }
    const nScore=evalGenome(neighbor);
    const delta=nScore-curScore;
    if (delta>0||Math.random()<Math.exp(delta/T)) { current=neighbor; curScore=nScore; }
    if (curScore>best.score) best={genome:[...current],score:curScore};
    T*=cool;
  }
  onProg(1,best.score); onDone(best);
}

// ── Particle Swarm Optimization ─────────────────────────────────────────────
async function runPSO(onProg, onDone) {
  const SWARM=48, ITERS=220, W=0.72, C1=1.49, C2=1.49;
  const baseG = greedyGenome();
  const particles = Array.from({length:SWARM},(_,pi)=>({
    pos: pi<3 ? baseG.map(g=>g+(Math.random()-0.5)*0.5) : Array.from({length:OPT_GENES},()=>Math.random()*3),
    vel: Array.from({length:OPT_GENES},()=>(Math.random()-0.5)*1.5),
    pBest:null, pBestScore:-Infinity
  }));
  let gBest=null, gBestScore=-Infinity;
  particles.forEach(p=>{
    const g=p.pos.map(clampGene);
    const s=evalGenome(g);
    p.pBest=[...p.pos]; p.pBestScore=s;
    if(s>gBestScore){gBestScore=s;gBest=[...p.pos];}
  });
  for (let iter=0;iter<ITERS;iter++) {
    if (iter%20===0) { await _yield(); onProg(iter/ITERS,gBestScore); }
    particles.forEach(p=>{
      for(let i=0;i<OPT_GENES;i++){
        const r1=Math.random(),r2=Math.random();
        p.vel[i]=W*p.vel[i]+C1*r1*(p.pBest[i]-p.pos[i])+C2*r2*(gBest[i]-p.pos[i]);
        p.vel[i]=Math.max(-2,Math.min(2,p.vel[i]));
        p.pos[i]=Math.max(0,Math.min(3,p.pos[i]+p.vel[i]));
      }
      const g=p.pos.map(clampGene);
      const s=evalGenome(g);
      if(s>p.pBestScore){p.pBestScore=s;p.pBest=[...p.pos];}
      if(s>gBestScore){gBestScore=s;gBest=[...p.pos];}
    });
  }
  onProg(1,gBestScore); onDone({genome:gBest.map(clampGene),score:gBestScore});
}

// ── Adaptive Moment Estimation (Adam) — adapted for discrete space ──────────
async function runAdam(onProg, onDone) {
  const AGENTS=28, ITERS=240, LR=0.45, B1=0.9, B2=0.999, EPS=1e-8;
  const baseG = greedyGenome();
  const agents = Array.from({length:AGENTS},(_,ai)=>({
    pos: ai<2 ? baseG.map(g=>g+(Math.random()-0.5)*0.3) : Array.from({length:OPT_GENES},()=>Math.random()*3),
    m:new Array(OPT_GENES).fill(0),
    v:new Array(OPT_GENES).fill(0),
    t:0
  }));
  let best={genome:baseG.map(clampGene), score:evalGenome(baseG.map(clampGene))};
  for (let iter=0;iter<ITERS;iter++) {
    if (iter%30===0) { await _yield(); onProg(iter/ITERS,best.score); }
    agents.forEach(ag=>{
      const g=ag.pos.map(clampGene);
      const baseScore=evalGenome(g);
      if(baseScore>best.score) best={genome:[...g],score:baseScore};
      // Finite-difference gradient estimate
      const grad=new Array(OPT_GENES).fill(0);
      for(let i=0;i<OPT_GENES;i++){
        // Sample +0.5 and -0.5 perturbation
        const pp=ag.pos.map((x,j)=>j===i?Math.min(3,x+0.5):x);
        const pm=ag.pos.map((x,j)=>j===i?Math.max(0,x-0.5):x);
        const sp=evalGenome(pp.map(clampGene));
        const sm=evalGenome(pm.map(clampGene));
        grad[i]=(sp-sm);  // central difference
      }
      // Adam update (gradient ascent — maximize stars)
      ag.t++;
      for(let i=0;i<OPT_GENES;i++){
        ag.m[i]=B1*ag.m[i]+(1-B1)*grad[i];
        ag.v[i]=B2*ag.v[i]+(1-B2)*grad[i]*grad[i];
        const mh=ag.m[i]/(1-Math.pow(B1,ag.t));
        const vh=ag.v[i]/(1-Math.pow(B2,ag.t));
        ag.pos[i]=Math.max(0,Math.min(3,ag.pos[i]+LR*mh/(Math.sqrt(vh)+EPS)));
      }
    });
  }
  onProg(1,best.score); onDone(best);
}

// ── Greedy algorithm wrapper (existing optimizer as a genome) ───────────────
async function runGreedy(onProg, onDone) {
  onProg(0.5, 0);
  await _yield();
  const g = greedyGenome();
  const score = evalGenome(g);
  onProg(1, score);
  onDone({genome:g, score});
}

// ── Simulate genome → detailed day-by-day result for display ───────────────
function simulateGenomeDetailed(genome) {
  return simulateGenomePlan(genome, true);
}

// ── Main: run selected algorithm(s) and display result ─────────────────────
function getProjectedPointsBreakdown(entry){
  const gpPts = Math.max(0, Number(entry?.gpDeployed) || 0);
  const opsPts = Math.max(0, Number(entry?.opsPts) || 0);
  const carryInPts = Math.max(0, Number(entry?.carryInPts ?? entry?.preloadAmt) || 0);
  const totalPts = Math.max(0, Number(entry?.pts ?? entry?.banked) || 0);
  const missionPts = Math.max(0,
    Number(entry?.missionPts)
    || Math.max(0, totalPts - gpPts - opsPts - carryInPts)
  );
  return {missionPts, gpPts, opsPts, carryInPts};
}

function buildProjectedPointsBreakdownHtml(entry){
  const {missionPts, gpPts, opsPts, carryInPts} = getProjectedPointsBreakdown(entry);
  const breakdown = '<div class="day-breakdown">'
    + fmtM(missionPts) + ' pts from combat & fleet missions'
    + ' || ' + fmtM(gpPts) + ' pts from deployment'
    + ' || ' + fmtM(opsPts) + ' pts from operations bonuses'
    + '</div>';
  const carryNote = carryInPts > 0
    ? '<div class="day-preload">Includes ' + fmtM(carryInPts) + ' banked from earlier days</div>'
    : '';
  return breakdown + carryNote;
}

function buildMainDayChainCardHtml(chainKey, chainEntry, chainNames){
  if (!chainEntry || chainEntry.status === 'complete') {
    return '<div class="day-chain '+chainKey+'"><div class="day-chain-title">'+chainNames[chainKey]+'</div><div class="day-locked">Complete</div></div>';
  }
  const planet = chainEntry.planet;
  let inner = '';
  if (chainEntry.status === 'preload') {
    const tomorrowEst = fmtM(chainEntry.tomorrowEst || chainEntry.banked);
    const breakdownHtml = buildProjectedPointsBreakdownHtml(chainEntry);
    const capNote = chainEntry.threshold1star
      ? '<div class="day-advance" style="color:var(--text3)">Capped at '
        + fmtM(chainEntry.threshold1star - 1) + ' (1-star threshold: ' + fmtM(chainEntry.threshold1star) + ')</div>'
      : '';
    inner = '<div class="day-stars" style="color:#c39bd3">Preloading</div>'
      + '<div class="day-action">Projected total: ' + fmtM(chainEntry.banked) + ' pts</div>'
      + breakdownHtml
      + '<div class="day-advance">Banking below 1-star for tomorrow | Tomorrow est. base: ' + tomorrowEst + '</div>'
      + capNote;
  } else if (chainEntry.status === 'commit') {
    const breakdownHtml = buildProjectedPointsBreakdownHtml(chainEntry);
    const advNote = chainEntry.stars === 3
      ? '<div class="day-advance" style="color:var(--mx)">3-star! Next planet unlocks tomorrow</div>'
      : '<div class="day-advance">' + chainEntry.pctOf3 + '% of 3-star | next planet unlocks tomorrow</div>';
    inner = '<div class="day-stars">' + chainEntry.stars + ' stars</div>'
      + '<div class="day-action">Projected total: ' + fmtM(chainEntry.pts) + ' pts</div>'
      + breakdownHtml
      + advNote;
  } else {
    const breakdownHtml = buildProjectedPointsBreakdownHtml(chainEntry);
    inner = '<div class="day-stars" style="color:var(--ds)">Below 1-star</div>'
      + '<div class="day-action">Projected total: ' + fmtM(chainEntry.pts) + ' pts</div>'
      + breakdownHtml
      + '<div class="day-advance">' + fmtM(chainEntry.pts) + ' / ' + fmtM(planet.stars[0]) + ' for 1-star - needs more GP or preloading</div>';
  }
  return '<div class="day-chain '+chainKey+'"><div class="day-chain-title">'+chainNames[chainKey]+'</div>'
    + '<div class="day-planet-name">'+escHtml(planet.name)+'</div>' + inner + '</div>';
}

function buildBonusDayChainCardHtml(bonusEntry){
  const planet = bonusEntry?.planet;
  if(!planet) return '';
  const breakdownHtml = buildProjectedPointsBreakdownHtml(bonusEntry);
  const sourceName = getPlanetMetaById(planet.unlockedBy)?.name || planet.unlockedBy || 'its unlock planet';
  const unlockNote = bonusEntry.unlockedOnDay
    ? '<div class="day-advance">Unlocked after ' + escHtml(sourceName) + ' hit 1-star on Day ' + bonusEntry.unlockedOnDay + '</div>'
    : '';
  let inner = '';
  if ((Number(bonusEntry.stars) || 0) >= 1) {
    inner = '<div class="day-stars">' + bonusEntry.stars + ' stars</div>'
      + '<div class="day-action">Projected total: ' + fmtM(bonusEntry.pts) + ' pts</div>'
      + breakdownHtml
      + '<div class="day-advance" style="color:#c39bd3">Locks tomorrow after earning stars</div>'
      + unlockNote;
  } else {
    inner = '<div class="day-stars" style="color:#c39bd3">Active</div>'
      + '<div class="day-action">Projected total: ' + fmtM(bonusEntry.pts) + ' pts</div>'
      + breakdownHtml
      + '<div class="day-advance">Carryover into tomorrow: ' + fmtM(bonusEntry.carryOver || 0) + '</div>'
      + unlockNote
      + '<div class="day-advance">' + fmtM(bonusEntry.pts) + ' / ' + fmtM(planet.stars[0]) + ' for 1-star</div>';
  }
  return '<div class="day-chain bonus"><div class="day-chain-title">Bonus Planet</div>'
    + '<div class="day-planet-name">'+escHtml(planet.name)+'</div>' + inner + '</div>';
}

function buildDayPlanCardsHtml(dayPlan, chainNames){
  const cards = OPT_CKEYS.map(chainKey=>
    buildMainDayChainCardHtml(chainKey, dayPlan?.chains?.[chainKey], chainNames)
  );
  (dayPlan?.bonusPlanets || []).forEach(bonusEntry=>{
    const cardHtml = buildBonusDayChainCardHtml(bonusEntry);
    if(cardHtml) cards.push(cardHtml);
  });
  return cards.join('');
}

let _optRunning = false;

// ── Render optimized plan (same display format as existing generateDayPlan) ─
function renderOptPlan(planResult, algoName, allResults) {
  const {days, totalStars} = planResult;
  const out = document.getElementById('day-plan-output');
  const CHAIN_NAMES = {ds:'Dark Side',mx:'Mixed',ls:'Light Side'};
  const algoLabel={ga:'Genetic Algorithm',sa:'Simulated Annealing',
    pso:'Particle Swarm',adam:'Adam (AME)',greedy:'Greedy',all:'All'};

  let html = '';
  // Algorithm comparison header (if multiple ran)
  if (allResults && allResults.length > 1) {
    html += '<div style="background:rgba(240,192,64,.07);border:1px solid rgba(240,192,64,.2);'+
      'border-radius:8px;padding:.6rem .9rem;margin-bottom:.75rem;font-size:.75rem">'+
      '<span style="font-family:Orbitron,monospace;font-size:.6rem;color:var(--gold2);letter-spacing:.1em">'+
      'ALGORITHM COMPARISON </span>';
    html += allResults.map(r =>
      `<span style="display:inline-block;margin:.2rem .4rem;padding:2px 8px;border-radius:4px;`+
      `background:${r.score===Math.max(...allResults.map(x=>x.score))?'rgba(240,192,64,.15)':'transparent'};`+
      `border:1px solid ${r.score===Math.max(...allResults.map(x=>x.score))?'var(--gold2)':'var(--border2)'};`+
      `color:${r.score===Math.max(...allResults.map(x=>x.score))?'var(--gold)':'var(--text2)'}">` +
      `${algoLabel[r.algo]||r.algo}: ${r.score}★</span>`
    ).join('');
    html += '</div>';
  }

  days.forEach(d => {
    const cards = buildDayPlanCardsHtml(d, CHAIN_NAMES);

    let notesHtml=d.notices.map(n=>'<div class="day-note bonus">'+n+'</div>').join('');
    if(d.opsPoints || Object.values(d.opsPlanets || {}).some(planet=>planet.slotsFilled > 0)){
      const opsLines = Object.entries(d.opsPlanets || {})
        .filter(([,planet])=>planet.completedToday > 0 || planet.slotsFilled > 0)
        .sort((a,b)=>(b[1].priority - a[1].priority) || a[0].localeCompare(b[0]))
        .map(([pid, planet])=>{
          const meta = getPlanetMetaById(pid);
          return 'Ops — ' + (meta?.name || pid) + ': '
            + planet.slotsFilled + ' slots'
            + (planet.completedToday ? (' · '+planet.completedToday+' platoon'+(planet.completedToday===1?'':'s')+' complete') : '');
        });
      notesHtml += '<div class="day-note" style="color:var(--mx)">Operations: '+(d.opsPoints?('+'+fmtM(d.opsPoints)):'preloading only')+'</div>';
      opsLines.forEach(line=>{ notesHtml += '<div class="day-note">'+escHtml(line)+'</div>'; });
    }

    html+='<div class="day-block">'+
      '<div class="day-block-header">'+
      '<div class="day-title">Day '+d.day+'</div>'+
      '<div style="display:flex;align-items:center;gap:16px">'+
      '<div style="font-size:.72rem;color:var(--text2)">GP: '+fmtM(d.gpAvail)+' avail / '+fmtM(d.gpUsed)+' used</div>'+
      '<div style="font-family:Orbitron,monospace;font-size:.72rem;color:var(--gold)">'+d.starsDay+' stars</div>'+
      '</div></div>'+
      '<div class="day-chains-grid">'+cards+'</div>'+
      (notesHtml?'<div class="day-notes">'+notesHtml+'</div>':'')+
      '</div>';
  });

  const bc=getActiveBonusPlanetIdsFromPlanDays(days).size;
  const ot = planResult?.opsSummary?.totalCompleted || 0;
  const om = planResult?.opsSummary?.totalPlatoons || 0;
  _lastPlanResult = planResult;
  _lastPlanStars = totalStars;
  document.getElementById('pm-stars').textContent=totalStars+' stars';
  document.getElementById('pm-max').textContent='56 base + '+(bc*3)+' bonus';
  document.getElementById('pm-bonus').textContent=bc+'/2';
  document.getElementById('pm-ops').textContent=ot+'/'+om;
  out.innerHTML=html;
  renderOperationsTab(planResult);
  calcSummary();
}

function getCurrentPlanForExport(){
  return hasCompletedOptimization() ? _lastPlanResult : null;
}

function formatExportPercent(value){
  const num = Number(value);
  if(!Number.isFinite(num)) return 'n/a';
  const rounded = Math.round(num * 10) / 10;
  return (Math.abs(rounded - Math.round(rounded)) < 0.05 ? String(Math.round(rounded)) : rounded.toFixed(1)) + '%';
}

function getUndeployedGpForDay(dayNumber){
  const total = guildGP() * (1 - nonParticipationRate());
  const u = Number(dailyUndep[Math.max(0, Number(dayNumber || 1) - 1)]) || 0;
  return Math.max(0, undepMode === 'pct' ? (total * (u / 100)) : u);
}

function getUndeployedPctForDay(dayNumber){
  const total = guildGP() * (1 - nonParticipationRate());
  if(total <= 0) return 0;
  return clamp((getUndeployedGpForDay(dayNumber) / total) * 100, 0, 100);
}

function averageNumber(values){
  const nums = (values || []).map(value=>Number(value)).filter(Number.isFinite);
  if(!nums.length) return 0;
  return nums.reduce((sum, value)=>sum + value, 0) / nums.length;
}

function getDayExportEstimateSummary(dayPlan){
  const dayNumber = Number(dayPlan?.day || 0) || 1;
  const activePlanetIds = getActivePlanetIdsForPlanDay(dayPlan);
  const cmAvgPct = averageNumber(activePlanetIds.map(pid=>effectiveCmRate(pid) * 100));
  const fleetRelevant = activePlanetIds.filter(pid=>(Number(getPlanetMetaById(pid)?.fleets) || 0) > 0);
  const fleetAvgPct = averageNumber((fleetRelevant.length ? fleetRelevant : activePlanetIds).map(pid=>effectiveFleetRate(pid) * 100));
  const undeployedGp = getUndeployedGpForDay(dayNumber);
  const deployedPct = 100 - getUndeployedPctForDay(dayNumber);
  const overallParticipationPct = averageNumber([cmAvgPct, fleetAvgPct, deployedPct]);
  return {cmAvgPct, fleetAvgPct, undeployedGp, deployedPct, overallParticipationPct};
}

function buildDayExportEstimateLine(dayPlan){
  const summary = getDayExportEstimateSummary(dayPlan);
  return 'Estimated participation: '
    + formatExportPercent(summary.overallParticipationPct)
    + ' overall | Avg CM '
    + formatExportPercent(summary.cmAvgPct)
    + ' | Avg Fleet '
    + formatExportPercent(summary.fleetAvgPct)
    + ' | Undeployed GP '
    + fmtM(summary.undeployedGp);
}

function buildExportDayOverviewHtml(dayPlans){
  const cards = (dayPlans || []).map(dayPlan=>{
    const activePlanetIds = getActivePlanetIdsForPlanDay(dayPlan);
    const targetChips = activePlanetIds.map(pid=>{
      const meta = getPlanetMetaById(pid);
      return '<span class="export-target-chip">'
        + escHtml(meta?.name || pid)
        + ' | '
        + escHtml(getPlanetLabelForSelectedDay(dayPlan, pid))
        + '</span>';
    }).join('');
    return '<div class="export-overview-card">'
      + '<div class="export-overview-day">Day ' + dayPlan.day + '</div>'
      + '<div class="export-overview-stars">' + dayPlan.starsDay + ' stars planned</div>'
      + '<div class="export-overview-label">Target planets</div>'
      + '<div class="export-target-chip-row">' + (targetChips || '<span class="export-target-chip muted">No active targets</span>') + '</div>'
      + '<div class="export-overview-estimate">' + escHtml(buildDayExportEstimateLine(dayPlan)) + '</div>'
      + '</div>';
  }).join('');
  if(!cards) return '';
  return '<section class="export-overview-section">'
    + '<div class="export-overview-title">Day-by-Day Overview</div>'
    + '<div class="export-overview-grid">' + cards + '</div>'
    + '</section>';
}

function buildOperationsPlanetExportHtml(planResult, dayNumber, pid, detailMode='detailed'){
  if(!pid || !_opsDefinitions?.[pid]) return '';
  const planetDef = _opsDefinitions[pid];
  const planetMeta = getPlanetMetaById(pid) || planetDef;
  const {dayPlan, opsDay} = getOperationsDayBundle(planResult, dayNumber);
  const planetToday = opsDay?.planets?.[pid] || null;
  const memberNameMap = getGuildMemberNameMap();
  const daysRemaining = countPlanetActiveDaysRemaining(planResult, pid, dayNumber);
  const summaryInfo = getOperationsPlanetShortfallSummary(planResult, pid, dayNumber);
  const detailedSnapshots = summaryInfo.snapshots.filter(snapshot=>
    !snapshot.impossible
    && (snapshot.completedByDay || snapshot.assignedTodayCount > 0 || snapshot.totalFilled > 0)
  );

  const platoonCards = detailedSnapshots.map(snapshot=>{
    const platoon = planetDef.platoons[snapshot.platoonIdx];
    if(!platoon) return '';
    const statusClass = snapshot.completedByDay
      ? 'complete'
      : snapshot.totalFilled > 0
        ? 'partial'
        : 'ready';
    const statusLabel = snapshot.completedByDay
      ? (snapshot.completedDay === dayNumber ? 'Completed today' : ('Completed on Day '+snapshot.completedDay))
      : snapshot.assignedTodayCount > 0
        ? 'Partial today'
        : snapshot.totalFilled > 0
          ? 'Preloaded'
          : 'Open';

    const slotHtml = snapshot.reqStates.map(entry=>{
      const req = entry.requirement;
      return Array.from({length:Number(req?.need) || 0}, (_, slotIdx)=>{
        const assignment = entry.filledToDay[slotIdx] || null;
        const assignee = assignment
          ? ((memberNameMap[String(assignment.allyCode)] || String(assignment.allyCode))
            + ((Number(assignment?.day) || 0) === Number(dayNumber) ? ' (today)' : (' (Day '+assignment.day+')')))
          : 'Unassigned';
        const reqText = getOpsRequirementLabel(req);
        return '<div class="export-slot-card">'
          + '<div class="export-slot-name">'+escHtml(req.name)+(((Number(req?.need) || 0) > 1) ? (' '+(slotIdx+1)) : '')+'</div>'
          + '<div class="export-slot-assignee'+(assignment?'':' unassigned')+'">- '+escHtml(assignee)+'</div>'
          + '<div class="export-slot-meta">Players available: '+entry.availableCount+' | Requirement: '+escHtml(reqText)+'</div>'
          + '</div>';
      }).join('');
    }).join('');

    return '<div class="export-platoon-card '+statusClass+'">'
      + '<div class="export-platoon-head">'
      + '<div><div class="export-platoon-title">Platoon '+platoon.id+'</div>'
      + '<div class="export-platoon-sub">'+snapshot.totalFilled+'/'+snapshot.totalSlots+' slots filled</div></div>'
      + '<div class="export-platoon-badge '+statusClass+'">'+escHtml(statusLabel)+'</div>'
      + '</div>'
      + '<div class="export-slot-list">'+slotHtml+'</div>'
      + '</div>';
  }).filter(Boolean);
  const leftColumn = platoonCards.slice(0, 3).join('');
  const rightColumn = platoonCards.slice(3).join('');
  const condensedGroups = {complete:[], preload:[], ignore:[]};
  summaryInfo.snapshots.forEach(snapshot=>{
    const platoon = planetDef.platoons[snapshot.platoonIdx];
    if(!platoon) return;
    if(snapshot.completedByDay){
      condensedGroups.complete.push({
        label: 'Platoon ' + platoon.id,
        meta: snapshot.completedDay === dayNumber ? 'Finished today' : ('Finished Day ' + snapshot.completedDay)
      });
      return;
    }
    if(snapshot.assignedTodayCount > 0 || snapshot.totalFilled > 0){
      condensedGroups.preload.push({
        label: 'Platoon ' + platoon.id,
        meta: snapshot.totalFilled + '/' + snapshot.totalSlots + ' filled'
      });
      return;
    }
    condensedGroups.ignore.push({
      label: 'Platoon ' + platoon.id,
      meta: snapshot.impossible ? 'Blocked' : 'Hold'
    });
  });
  const condensedHtml = ['complete','preload','ignore'].map(status=>{
    const entries = condensedGroups[status];
    if(!entries.length) return '';
    const title = status === 'complete'
      ? 'Complete'
      : status === 'preload'
        ? 'Preload'
        : 'Ignore';
    const chips = entries.map(entry=>
      '<div class="export-status-chip ' + status + '">'
      + '<div class="export-status-chip-label">' + escHtml(entry.label) + '</div>'
      + '<div class="export-status-chip-meta">' + escHtml(entry.meta) + '</div>'
      + '</div>'
    ).join('');
    return '<div class="export-status-group ' + status + '">'
      + '<div class="export-status-group-title">' + title + '</div>'
      + '<div class="export-status-chip-grid">' + chips + '</div>'
      + '</div>';
  }).join('');
  const missingSummaryHtml = buildOpsMissingSummaryHtml(planResult, pid, dayNumber, 'export');
  const detailHtml = detailMode === 'condensed'
    ? (condensedHtml || '<div class="export-empty">No platoons were assigned to this planet by this day.</div>')
    : (platoonCards.length
      ? ('<div class="export-platoon-columns">'
        + '<div class="export-platoon-column">'+leftColumn+'</div>'
        + '<div class="export-platoon-column">'+rightColumn+'</div>'
        + '</div>')
      : '<div class="export-empty">No platoons were completed or partially filled for this planet by this day.</div>');

  return '<section class="export-planet-section">'
    + '<div class="export-planet-head">'
    + '<div><div class="export-planet-title">'+escHtml(planetMeta?.name || pid)+'</div>'
    + '<div class="export-planet-sub">'+escHtml(getPlanetLabelForSelectedDay(dayPlan, pid))
    + ' | Zone '+(planetMeta?.zone || '?')
    + ' | '+daysRemaining+' day'+(daysRemaining===1?'':'s')+' remaining active</div></div>'
    + '<div class="export-planet-metrics">'
    + '<div>Today: '+(planetToday ? ((planetToday.slotsFilled || 0)+' slots | '+fmtM(planetToday.pointsEarned || 0)) : 'No new slots')+'</div>'
    + '<div>Completed today: '+(planetToday?.completedToday || 0)+'</div>'
    + '</div></div>'
    + detailHtml
    + missingSummaryHtml
    + '</section>';
}

function buildPlanExportDocumentHtml(planResult, options={}){
  const requestedDays = Array.isArray(options.dayNumbers) && options.dayNumbers.length
    ? new Set(options.dayNumbers.map(day=>Number(day) || 0).filter(Boolean))
    : null;
  const docTitle = String(options.docTitle || 'ROTE Plan Export');
  const autoPrint = !!options.autoPrint;
  const detailMode = String(options.detailMode || 'detailed') === 'condensed' ? 'condensed' : 'detailed';
  const summary = getCurrentGuildSummary();
  const guildName = summary?.name || document.getElementById('guild-name-display')?.dataset?.guildName || 'Current Guild';
  const generatedAt = new Date().toLocaleString();
  const totalStars = Number(planResult?.totalStars || 0);
  const opsSummary = planResult?.opsSummary || {};
  const bonusCount = getActiveBonusPlanetIdsFromPlanDays(planResult?.days || []).size;
  const chainNames = {ds:'Dark Side', mx:'Mixed', ls:'Light Side'};
  const filteredDays = (planResult?.days || []).filter(dayPlan=>
    !requestedDays || requestedDays.has(Number(dayPlan?.day || 0))
  );
  const overviewHtml = buildExportDayOverviewHtml(filteredDays);

  const daySections = filteredDays.map(dayPlan=>{
    const cards = buildDayPlanCardsHtml(dayPlan, chainNames);
    const estimateLine = buildDayExportEstimateLine(dayPlan);
    let notesHtml = (dayPlan?.notices || []).map(note=>'<div class="export-note">'+escHtml(note)+'</div>').join('');
    const opsDay = (planResult?.opsSummary?.days || []).find(entry=>Number(entry?.day || 0) === Number(dayPlan?.day || 0)) || null;
    if(dayPlan?.opsPoints || Object.values(dayPlan?.opsPlanets || {}).some(planet=>planet.slotsFilled > 0)){
      const opsLines = Object.entries(dayPlan?.opsPlanets || {})
        .filter(([,planet])=>planet.completedToday > 0 || planet.slotsFilled > 0)
        .sort((a,b)=>(b[1].priority - a[1].priority) || a[0].localeCompare(b[0]))
        .map(([pid, planet])=>{
          const meta = getPlanetMetaById(pid);
          return '<div class="export-note"><strong>'+escHtml(meta?.name || pid)+'</strong>: '
            + planet.slotsFilled + ' slots'
            + (planet.completedToday ? (' | '+planet.completedToday+' platoon'+(planet.completedToday===1?'':'s')+' completed') : '')
            + '</div>';
        }).join('');
      notesHtml += '<div class="export-note"><strong>Operations</strong>: '
        + (dayPlan.opsPoints ? ('+'+fmtM(dayPlan.opsPoints)) : 'preloading only') + '</div>' + opsLines;
    }

    const activePlanetIds = getActivePlanetIdsForPlanDay(dayPlan);
    const opsSections = activePlanetIds.length
      ? activePlanetIds.map(pid=>buildOperationsPlanetExportHtml(planResult, dayPlan.day, pid, detailMode)).join('')
      : '<div class="export-empty">No active planets were planned for operations on this day.</div>';

    return '<section class="export-day-section">'
      + '<div class="export-day-header">'
      + '<div><div class="export-day-title">Day '+dayPlan.day+'</div>'
      + '<div class="export-day-sub">Available GP: '+fmtM(dayPlan.gpAvail)+' | Used GP: '+fmtM(dayPlan.gpUsed)+'</div></div>'
      + '<div class="export-day-stars">'+dayPlan.starsDay+' stars</div>'
      + '</div>'
      + '<div class="export-estimate-band">'+escHtml(estimateLine)+'</div>'
      + '<div class="export-subtitle">Day Plan</div>'
      + '<div class="export-day-grid">'+cards+'</div>'
      + (notesHtml ? ('<div class="export-note-block">'+notesHtml+'</div>') : '')
      + '<div class="export-subtitle" style="margin-top:18px">Operations</div>'
      + '<div class="export-ops-summary">Ops points today: '+fmtM(opsDay?.pointsEarned || 0)
      + ' | Slots planned: '+Object.values(opsDay?.planets || {}).reduce((sum, planet)=>sum + (Number(planet?.slotsFilled) || 0), 0)
      + ' | Platoons completed today: '+Object.values(opsDay?.planets || {}).reduce((sum, planet)=>sum + (Number(planet?.completedToday) || 0), 0)
      + ' | Layout: ' + (detailMode === 'condensed' ? 'Condensed' : 'Detailed')
      + '</div>'
      + opsSections
      + '</section>';
  }).join('');

  return '<!doctype html><html><head><meta charset="utf-8"><title>'+escHtml(docTitle)+'</title>'
    + '<style>'
    + '@page{size:auto;margin:.45in;}'
    + 'html,body{margin:0;padding:0;background:#f4f6fb;color:#142033;font-family:Segoe UI,Arial,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact;}'
    + 'body{padding:18px 20px 26px;}'
    + '.export-header{border:1px solid #d7deed;border-radius:14px;background:#fff;padding:18px 20px;margin-bottom:18px;}'
    + '.export-title{font:700 24px Orbitron,Segoe UI,Arial,sans-serif;color:#cc9e22;letter-spacing:.04em;margin-bottom:6px;}'
    + '.export-subhead{font-size:13px;color:#5f6f8f;line-height:1.5;}'
    + '.export-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px;}'
    + '.export-metric{border:1px solid #d7deed;border-radius:12px;padding:10px 12px;background:#fafcff;}'
    + '.export-metric-label{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#6f7f9c;margin-bottom:5px;}'
    + '.export-metric-value{font:700 20px Orbitron,Segoe UI,Arial,sans-serif;color:#142033;}'
    + '.export-overview-section{border:1px solid #d7deed;border-radius:14px;background:#fff;padding:16px 18px;margin-bottom:18px;}'
    + '.export-overview-title{font:700 15px Orbitron,Segoe UI,Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#51627f;margin-bottom:12px;}'
    + '.export-overview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}'
    + '.export-overview-card{border:1px solid #d7deed;border-radius:14px;background:#fafcff;padding:14px;}'
    + '.export-overview-day{font:700 18px Orbitron,Segoe UI,Arial,sans-serif;color:#cc9e22;margin-bottom:4px;}'
    + '.export-overview-stars{font-size:13px;color:#22324c;font-weight:700;margin-bottom:10px;}'
    + '.export-overview-label{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#73829d;margin-bottom:7px;}'
    + '.export-target-chip-row{display:flex;flex-wrap:wrap;gap:7px;}'
    + '.export-target-chip{display:inline-flex;align-items:center;padding:5px 9px;border-radius:999px;border:1px solid #d7deed;background:#fff;color:#22324c;font-size:11px;line-height:1.35;}'
    + '.export-target-chip.muted{color:#73829d;background:#f8faff;}'
    + '.export-overview-estimate{margin-top:10px;font-size:12px;color:#556886;line-height:1.5;}'
    + '.export-day-section{page-break-before:always;break-before:page;padding-top:4px;}'
    + '.export-day-section:first-of-type{page-break-before:auto;break-before:auto;}'
    + '.export-day-header{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;margin-bottom:10px;padding:16px 18px;border-radius:16px;background:linear-gradient(135deg,#17253f 0%,#314c7c 100%);border:1px solid #203152;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06);}'
    + '.export-day-title{font:700 24px Orbitron,Segoe UI,Arial,sans-serif;color:#f4c64d;}'
    + '.export-day-sub{font-size:12px;color:#d6def1;margin-top:5px;}'
    + '.export-day-stars{font:700 22px Orbitron,Segoe UI,Arial,sans-serif;color:#f4c64d;white-space:nowrap;padding:8px 12px;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);}'
    + '.export-estimate-band{margin-bottom:12px;padding:10px 12px;border:1px solid #d7deed;border-radius:12px;background:#fffaf0;color:#5d512f;font-size:12px;line-height:1.55;font-weight:600;}'
    + '.export-subtitle{font:700 13px Orbitron,Segoe UI,Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#6f7f9c;margin-bottom:10px;}'
    + '.export-day-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}'
    + '.day-chain{border:1px solid #d7deed;border-radius:14px;background:#ffffff;padding:14px;min-height:118px;box-sizing:border-box;}'
    + '.day-chain.ds{border-left:6px solid #cc5b5b;}.day-chain.mx{border-left:6px solid #3ea87a;}.day-chain.ls{border-left:6px solid #4685d9;}.day-chain.bonus{border-left:6px solid #9b6bd3;}'
    + '.day-chain-title{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#73829d;margin-bottom:8px;font-family:Orbitron,Segoe UI,Arial,sans-serif;}'
    + '.day-planet-name{font:700 16px Rajdhani,Segoe UI,Arial,sans-serif;color:#142033;margin-bottom:6px;}'
    + '.day-stars{font:700 18px Orbitron,Segoe UI,Arial,sans-serif;color:#cc9e22;margin-bottom:5px;}'
    + '.day-action{font-size:13px;color:#22324c;margin-bottom:4px;font-weight:600;}'
    + '.day-advance{font-size:12px;color:#62718f;line-height:1.45;}'
    + '.export-note-block{border:1px solid #d7deed;border-radius:12px;background:#fff;padding:10px 12px;margin-top:12px;}'
    + '.export-note{font-size:12px;color:#4c5d7b;line-height:1.5;margin:4px 0;}'
    + '.export-ops-summary{font-size:12px;color:#4c5d7b;margin-bottom:12px;}'
    + '.export-planet-section{border:1px solid #d7deed;border-radius:14px;background:#fff;padding:14px 14px 12px;margin-bottom:14px;}'
    + '.export-planet-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:12px;}'
    + '.export-planet-title{font:700 18px Rajdhani,Segoe UI,Arial,sans-serif;color:#142033;}'
    + '.export-planet-sub{font-size:12px;color:#62718f;line-height:1.45;margin-top:3px;}'
    + '.export-planet-metrics{font-size:12px;color:#4c5d7b;line-height:1.45;text-align:right;white-space:nowrap;}'
    + '.export-platoon-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start;}'
    + '.export-platoon-column{display:flex;flex-direction:column;gap:12px;}'
    + '.export-platoon-card{border:1px solid #d7deed;border-left:6px solid #9aa7c0;border-radius:12px;padding:12px;background:#fbfcff;}'
    + '.export-platoon-card.complete{border-left-color:#27ae60;}.export-platoon-card.partial{border-left-color:#2980b9;}.export-platoon-card.impossible{border-left-color:#c0392b;}.export-platoon-card.ready{border-left-color:#8c98b3;}'
    + '.export-platoon-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:10px;}'
    + '.export-platoon-title{font:700 14px Orbitron,Segoe UI,Arial,sans-serif;color:#142033;}'
    + '.export-platoon-sub{font-size:11px;color:#73829d;margin-top:2px;}'
    + '.export-platoon-badge{font-size:11px;font-weight:700;padding:4px 8px;border-radius:999px;border:1px solid #d7deed;color:#4c5d7b;background:#fff;white-space:nowrap;}'
    + '.export-platoon-badge.complete{color:#1f8a53;border-color:#9cddbb;background:#f2fcf6;}.export-platoon-badge.partial{color:#216aaf;border-color:#a6ccef;background:#f3f8fe;}.export-platoon-badge.impossible{color:#b1312f;border-color:#efb2af;background:#fff5f5;}'
    + '.export-status-group{border:1px solid #d7deed;border-radius:12px;padding:12px;background:#fbfcff;margin-bottom:10px;}'
    + '.export-status-group.complete{border-left:6px solid #27ae60;}.export-status-group.preload{border-left:6px solid #2980b9;}.export-status-group.ignore{border-left:6px solid #8c98b3;}'
    + '.export-status-group-title{font:700 12px Orbitron,Segoe UI,Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#51627f;margin-bottom:8px;}'
    + '.export-status-chip-grid{display:flex;flex-wrap:wrap;gap:8px;}'
    + '.export-status-chip{min-width:128px;border:1px solid #d7deed;border-radius:10px;background:#fff;padding:8px 10px;}'
    + '.export-status-chip.complete{background:#f2fcf6;border-color:#b4e0c6;}.export-status-chip.preload{background:#f3f8fe;border-color:#b7d5f3;}.export-status-chip.ignore{background:#f8f9fc;border-color:#d6ddeb;}'
    + '.export-status-chip-label{font:700 12px Rajdhani,Segoe UI,Arial,sans-serif;color:#142033;}'
    + '.export-status-chip-meta{font-size:11px;color:#667891;margin-top:3px;}'
    + '.export-slot-list{display:grid;grid-template-columns:1fr;gap:8px;}'
    + '.export-slot-card{border:1px solid #e1e7f2;border-radius:10px;padding:8px 10px;background:#fff;}'
    + '.export-slot-name{font:700 13px Rajdhani,Segoe UI,Arial,sans-serif;color:#142033;}'
    + '.export-slot-assignee{font-size:12px;color:#22324c;margin-top:2px;}.export-slot-assignee.unassigned{color:#9b5a5a;}'
    + '.export-slot-meta{font-size:11px;color:#73829d;margin-top:3px;line-height:1.4;}'
    + '.export-missing-card{margin-top:12px;border:1px dashed #e7b4b2;border-radius:12px;padding:10px 12px;background:#fff6f6;}'
    + '.export-missing-title{font:700 12px Orbitron,Segoe UI,Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#9b4542;margin-bottom:6px;}'
    + '.export-missing-text{font-size:12px;color:#6a4a4a;line-height:1.5;}'
    + '.export-missing-subtitle{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9b4542;margin-top:10px;margin-bottom:4px;}'
    + '.export-missing-line{font-size:12px;color:#6a4a4a;line-height:1.45;padding:2px 0;}'
    + '.export-empty{border:1px dashed #c7d0e1;border-radius:12px;padding:14px;color:#73829d;background:#fff;font-size:12px;}'
    + '@media print{body{padding:0;}.export-header{break-inside:avoid;}.export-planet-section,.export-note-block,.day-chain,.export-platoon-card,.export-missing-card{break-inside:avoid;}}'
    + '</style></head><body>'
    + '<section class="export-header">'
    + '<div class="export-title">'+escHtml(docTitle)+'</div>'
    + '<div class="export-subhead"><strong>'+escHtml(guildName)+'</strong><br>Generated '+escHtml(generatedAt)+'<br>Use your browser\'s <strong>Save as PDF</strong> destination to share this document.</div>'
    + '<div class="export-metrics">'
    + '<div class="export-metric"><div class="export-metric-label">Total Est. Stars</div><div class="export-metric-value">'+totalStars+'</div></div>'
    + '<div class="export-metric"><div class="export-metric-label">Ops Filled</div><div class="export-metric-value">'+(opsSummary.totalCompleted || 0)+'/'+(opsSummary.totalPlatoons || 0)+'</div></div>'
    + '<div class="export-metric"><div class="export-metric-label">Ops Points</div><div class="export-metric-value">'+fmtM(opsSummary.totalPoints || 0)+'</div></div>'
    + '<div class="export-metric"><div class="export-metric-label">Bonus Planets</div><div class="export-metric-value">'+bonusCount+'/2</div></div>'
    + '</div></section>'
    + overviewHtml
    + daySections
    + (autoPrint
        ? '<script>window.addEventListener("load",function(){setTimeout(function(){try{window.focus();window.print();}catch(err){}},320);});<\/script>'
        : '')
    + '</body></html>';
}

function triggerPrintExportDocument(docHtml){
  const printWin = window.open('', '_blank');
  if(!printWin) return false;
  printWin.document.open();
  printWin.document.write(docHtml);
  printWin.document.close();
  setTimeout(()=>{
    try{
      printWin.focus();
      printWin.print();
    }catch(err){}
  }, 300);
  return true;
}

function openSeparatePlanExportHub(planResult, detailMode='detailed'){
  const days = Array.isArray(planResult?.days) ? planResult.days : [];
  if(!days.length) return false;
  const hubWin = window.open('', '_blank');
  if(!hubWin) return false;
  const dayEntries = days.map(dayPlan=>{
    const dayNumber = Number(dayPlan?.day || 0);
    const html = buildPlanExportDocumentHtml(planResult, {
      dayNumbers: [dayNumber],
      docTitle: 'Rise of the Empire - Day '+dayNumber+' Export',
      autoPrint: true,
      detailMode
    });
    const blob = new Blob([html], {type:'text/html'});
    const url = URL.createObjectURL(blob);
    return {dayNumber, url};
  });
  const cards = dayEntries.map(entry=>
    '<button type="button" class="export-hub-btn" onclick="window.open(\''+entry.url+'\', \'_blank\')">'
    + 'Open Day '+entry.dayNumber+' print view'
    + '</button>'
  ).join('');
  hubWin.document.open();
  hubWin.document.write('<!doctype html><html><head><meta charset="utf-8"><title>ROTE Separate Day Exports</title>'
    + '<style>'
    + 'body{margin:0;padding:24px;background:#0b1220;color:#e8eaf0;font-family:Segoe UI,Arial,sans-serif;}'
    + '.wrap{max-width:720px;margin:0 auto;}'
    + '.title{font:700 24px Orbitron,Segoe UI,Arial,sans-serif;color:#f0c040;margin-bottom:8px;}'
    + '.sub{font-size:14px;line-height:1.6;color:#a9b4c8;margin-bottom:18px;}'
    + '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;}'
    + '.export-hub-btn{width:100%;padding:14px 16px;border-radius:12px;border:1px solid rgba(240,192,64,.3);background:#162033;color:#f0c040;font:600 14px Segoe UI,Arial,sans-serif;cursor:pointer;}'
    + '.export-hub-btn:hover{background:#1b2942;}'
    + '.note{margin-top:18px;font-size:13px;color:#7f8da8;line-height:1.55;}'
    + '</style></head><body><div class="wrap">'
    + '<div class="title">Separate Day Exports</div>'
    + '<div class="sub">Browsers usually block multiple print windows from one click. Use the buttons below to open each day as its own printable document. Current layout: <strong>' + escHtml(detailMode === 'condensed' ? 'Condensed' : 'Detailed') + '</strong>.</div>'
    + '<div class="grid">'+cards+'</div>'
    + '<div class="note">Each day opens in its own window and triggers the print dialog automatically. Choose <strong>Save as PDF</strong> in each print dialog.</div>'
    + '</div></body></html>');
  hubWin.document.close();
  return true;
}

function exportCurrentPlanPdf(){
  const planResult = getCurrentPlanForExport();
  if(!planResult){
    showImportStatus('Run the optimizer first to export a day-by-day plan PDF.', 'err');
    updateDayPlanUiState();
    return;
  }
  const mode = String(document.getElementById('export-plan-mode')?.value || 'all');
  const detailMode = String(document.getElementById('export-plan-detail-mode')?.value || 'detailed');
  if(mode === 'separate'){
    const ok = openSeparatePlanExportHub(planResult, detailMode);
    if(!ok){
      showImportStatus('The separate-day export window was blocked. Please allow pop-ups for the planner and try again.', 'err');
      return;
    }
    showImportStatus('Opened the separate-day export helper. Use each day button to open and save its PDF.', 'ok');
    return;
  }
  const ok = triggerPrintExportDocument(buildPlanExportDocumentHtml(planResult, {
    docTitle: 'Rise of the Empire - Full Plan Export',
    detailMode
  }));
  if(!ok){
    showImportStatus('The export window was blocked. Please allow pop-ups for the planner and try again.', 'err');
    return;
  }
  showImportStatus('Export opened. Choose Save as PDF in the print dialog to share the full plan.', 'ok');
}

function downloadJsonFile(data, filename){
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportPlannerSnapshot(){
  const planResult = getCurrentPlanForExport();
  if(!planResult){
    showImportStatus('Run the optimizer first to save a full planning snapshot.', 'err');
    updateDayPlanUiState();
    return;
  }
  const stamp = new Date().toISOString().replace(/[:]/g,'-').replace(/\..+/,'');
  downloadJsonFile(buildAppStateSnapshot({includeVolatile:true}), 'rote-plan-snapshot-'+stamp+'.json');
  showImportStatus('Planning snapshot saved. This file can restore the exact guild, rosters, plan, and operations later.', 'ok');
}

async function importPlannerSnapshot(input){
  const file = input.files?.[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = async e=>{
    try{
      const state = JSON.parse(e.target.result);
      if(!state || typeof state !== 'object') throw new Error('Invalid snapshot format');
      if(!state.guildRosters || !state.lastPlanResult) throw new Error('Snapshot is missing roster or plan data');
      const resp = await fetch('/api/import-session-state', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({guildRosters: normalizeGuildRostersData(state.guildRosters || {})})
      });
      const data = await resp.json();
      if(data?.error) throw new Error(data.error);
      applyPersistedAppState(state, {allowVolatile:true});
      queueSaveAppState();
      showImportStatus('Snapshot loaded — restored guild, rosters, day plan, and operations from '+file.name, 'ok');
    }catch(err){
      alert('Failed to load planning snapshot: '+err.message);
    }
    input.value = '';
  };
  reader.readAsText(file);
}

// ── Rule-based plan (fast) ────────────────────────────────────────
function generateDayPlan() {
  const out = document.getElementById('day-plan-output');
  try {
    const planResult = runOptimizerResult() || runOptimizer();
    const { days, totalStars } = planResult;
    let html = '';
    const CHAIN_NAMES = { ds: 'Dark Side', mx: 'Mixed', ls: 'Light Side' };

    days.forEach(d => {
      const cards = buildDayPlanCardsHtml(d, CHAIN_NAMES);

      let notesHtml = d.notices.map(n => '<div class="day-note bonus">' + n + '</div>').join('');

      html += '<div class="day-block">'
            + '<div class="day-block-header">'
            + '<div class="day-title">Day ' + d.day + '</div>'
            + '<div style="display:flex;align-items:center;gap:16px">'
            + '<div style="font-size:.72rem;color:var(--text2)">GP: ' + fmtM(d.gpAvail) + ' avail / ' + fmtM(d.gpUsed) + ' used</div>'
            + '<div style="font-family:Orbitron,monospace;font-size:.72rem;color:var(--gold)">' + d.starsDay + ' stars</div>'
            + '</div></div>'
            + '<div class="day-chains-grid">' + cards + '</div>'
            + (notesHtml ? '<div class="day-notes">' + notesHtml + '</div>' : '')
            + '</div>';
    });

    const bc = getActiveBonusPlanetIdsFromPlanDays(days).size;
    const ot = planResult?.opsSummary?.totalCompleted || 0;
    const om = planResult?.opsSummary?.totalPlatoons || 0;
    document.getElementById('pm-stars').textContent = totalStars + ' stars';
    document.getElementById('pm-max').textContent = '56 base + ' + (bc * 3) + ' bonus';
    document.getElementById('pm-bonus').textContent = bc + '/2';
    document.getElementById('pm-ops').textContent = ot + '/' + om;
    out.innerHTML = html;
    _lastPlanResult = planResult;
    renderOperationsTab(planResult);
    calcSummary();
  } catch (err) {
    console.error('Optimizer error:', err);
    out.innerHTML = '<div style="padding:1rem;background:rgba(192,57,43,.12);border:1px solid var(--ds-dim);border-radius:8px;color:var(--ds);font-size:.82rem"><b>Error:</b> ' + err.message + '</div>';
  }
}

function showChain(c){
  document.querySelectorAll('.chain-pill').forEach(p=>p.classList.remove('active'));
  document.querySelector('.chain-pill.'+c).classList.add('active');
  ['ds','mx','ls'].forEach(ch=>document.getElementById('chain-'+ch).style.display=ch===c?'':'none');
}

// SHUTDOWN
function shutdown(){if(confirm('Stop the ROTE Planner server?'))fetch('/shutdown').then(()=>document.body.innerHTML='<div style="background:#080c14;color:#f0c040;font-family:monospace;padding:3rem;font-size:1.2rem;text-align:center;min-height:100vh;display:flex;align-items:center;justify-content:center">Server stopped. You can close this tab.</div>');}

// PLATOON ANALYSIS
async function scanAndAnalyze() {
  await scanRosters();
  await runPlatoonAnalysis();
}

async function fetchUnitNames(){
  const btn = document.getElementById('unit-names-btn');
  if(btn){ btn.disabled=true; btn.textContent='Fetching...'; }
  showImportStatus('Fetching unit name translations from comlink...','loading');
  try{
    const r = await fetch('/api/fetch-unit-names',{method:'POST',
      headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    if(d.count > 0){
      // Merge into UNIT_NAMES lookup table
      Object.entries(d.names).forEach(([k,v])=>{
        if(!v) return;
        UNIT_NAMES[k]=v;
        PLAYABLE_NAME_BY_DEFID[k]=v;
        if(!SHIP_NAME_BY_DEFID[k]) CHARACTER_NAME_BY_DEFID[k]=v;
      });
      rebuildUnitNameIndex();
      refreshGuideUnitLinks();
      queueSaveAppState();
      showImportStatus('Loaded '+d.count+' unit names from comlink. Re-scan rosters to see updated names.','ok');
    } else {
      const errMsg = (d.errors||[]).slice(0,3).join('; ');
      showImportStatus('Unit name fetch returned 0 results. Sources tried: '+(d.sources||[]).join(', ')+'. Errors: '+errMsg,'err');
    }
  } catch(e){
    showImportStatus('Unit name fetch failed: '+e.message,'err');
  } finally {
    if(btn){ btn.disabled=false; btn.textContent='📋 Fetch Unit Names'; }
  }
}

async function runPlatoonAnalysis() {
  showImportStatus('Refreshing operations definitions and roster availability...', 'loading');
  try {
    await ensureOperationsDefinitions(true);
    const sourceNote = _opsDefinitionsSourceLabel ? (' using ' + _opsDefinitionsSourceLabel.toLowerCase()) : '';
    if(!scannedRosterCount()){
      _platoonAnalysis = {};
      renderOperationsTab(_lastPlanResult);
      showImportStatus('Operations definitions loaded'+sourceNote+'. Scan rosters to build assignments.', 'ok');
      return;
    }
    const resp = await fetch('/api/platoon-analysis', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:'{}'});
    const data = await resp.json();
    if (data.error) { showImportStatus('Analysis error: ' + data.error, 'err'); return; }
    _platoonAnalysis = data.analysis || {};
    invalidateOperationsCaches();
    const projected = ensureProjectedPlanResult();
    renderOperationsTab(projected);
    let fillable=0, total=0;
    Object.values(_platoonAnalysis).forEach(ps=>ps.forEach(p=>{total++;if(p.fillable)fillable++;}));
    if (document.getElementById('chain-ds').innerHTML) rebuildPlannerChains();
    queueSaveAppState();
    showImportStatus('Operations refreshed'+sourceNote+' — '+fillable+'/'+total+' platoons fillable in isolation across '+
      Object.keys(_platoonAnalysis).length+' planets ('+data.roster_count+' members)', 'ok');
  } catch(e) {
    showImportStatus('Operations refresh failed: '+e.message, 'err');
  }
}

let _platoonAnalysis = {};

async function ensureOperationsDefinitions(force=false){
  if(!force && hasOperationsDefinitions()) return _opsDefinitions;
  if(_opsLoadPromise && !force) return _opsLoadPromise;
  _opsLoadPromise = (async ()=>{
    const resp = await fetch('/api/ops-definitions', {method:'POST',
      headers:{'Content-Type':'application/json'}, body:'{}'});
    const data = await resp.json();
    if(data.status !== 'ok' || !data.defs){
      throw new Error(data.error || 'Operations definitions unavailable');
    }
    _opsDefinitions = normalizeOperationsDefinitionsData(data.defs);
    _lastPlanResult = null;
    _lastPlanStars = null;
    _greedyGenomeCache = null;
    queueSaveAppState();
    return _opsDefinitions;
  })();
  try{
    return await _opsLoadPromise;
  } finally {
    _opsLoadPromise = null;
  }
}

function ensureProjectedPlanResult(){
  if(_lastPlanResult?.opsSummary) return _lastPlanResult;
  if(!scannedRosterCount() || !hasOperationsDefinitions()) return null;
  try{
    const projected = simulateGenomeDetailed(greedyGenome());
    _lastPlanResult = projected;
    _lastPlanStars = projected.totalStars;
    return projected;
  }catch(err){
    console.warn('[ROTE] Operations projection skipped:', err.message);
    return null;
  }
}

function getProjectedOpsPlanetStats(pid){
  return _lastPlanResult?.opsSummary?.planetStats?.[pid] || null;
}

function buildOperationsDayOverviewHtml(planResult){
  const days = planResult?.opsSummary?.days || [];
  if(!days.length){
    return '<div class="ops-empty">Run an optimization or refresh operations after scanning rosters to generate the day-by-day platoon plan.</div>';
  }
  const memberNameMap = getGuildMemberNameMap();
  return days.map(day=>{
    const lines = Object.entries(day.planets || {})
      .filter(([,planet])=>planet.completedToday > 0 || planet.slotsFilled > 0)
      .sort((a,b)=>(b[1].priority - a[1].priority) || a[0].localeCompare(b[0]))
      .map(([pid, planet])=>{
        const meta = getPlanetMetaById(pid);
        const completedText = planet.completedToday ? (' · '+planet.completedToday+' complete') : '';
        const assignmentLines = (planet.assignments || []).map(group=>{
          const byMember = {};
          (group.entries || []).forEach(entry=>{
            const name = memberNameMap[String(entry.allyCode)] || String(entry.allyCode);
            if(!byMember[name]) byMember[name] = [];
            byMember[name].push(entry.name);
          });
          return Object.entries(byMember).map(([memberName, units])=>
            '<div class="ops-day-line" style="padding-left:10px;color:var(--text3)">'
            + escHtml(memberName)+': '+escHtml(units.join(', '))
            + ' <span style="color:var(--text3)">(P'+(group.platoonIdx+1)+')</span></div>'
          ).join('');
        }).join('');
        return '<div class="ops-day-line"><strong>'+escHtml(meta?.name || pid)+'</strong>: '
          + planet.slotsFilled + ' slots' + completedText + ' <span style="color:var(--text3)">('
          + escHtml(planet.label || 'Auto') + ')</span></div>' + assignmentLines;
      }).join('');
    return '<div class="ops-day-card">'
      + '<div class="ops-day-head"><div class="ops-day-title">Day '+day.day+'</div><div class="ops-day-points">'
      + fmtM(day.pointsEarned || 0) + '</div></div>'
      + (lines || '<div class="ops-day-line">No new operations filled.</div>')
      + '</div>';
  }).join('');
}

function buildOperationsPlanetCardHtml(pid, planResult){
  const planetDef = _opsDefinitions[pid];
  if(!planetDef) return '';
  const planetMeta = getPlanetMetaById(pid) || planetDef;
  const baseline = _platoonAnalysis[pid] || [];
  const planetState = planResult?.opsState?.planets?.[pid] || null;
  const stats = planResult?.opsSummary?.planetStats?.[pid] || null;
  const simState = planResult?.opsState || createOperationsSimState(false);
  const completedCount = stats?.completedPlatoons ?? baseline.filter(p=>p.fillable).length ?? 0;
  const platoonCount = stats?.totalPlatoons ?? planetDef.platoons.length;
  const points = stats?.points ?? (completedCount * (Number(planetDef.opsVal)||0));
  const zoneRelic = ({1:5,2:6,3:7,4:8,5:9,6:9})[Number(planetMeta.zone)||0] || '?';
  const metaLabel = 'Zone '+(planetMeta.zone||'?')+' · R'+zoneRelic+' requirements';
  const platoonsHtml = planetDef.platoons.map((platoon, platoonIdx)=>{
    const progress = planetState?.platoons?.[platoonIdx];
    const baselineSlots = baseline[platoonIdx]?.slots || [];
    const filledTotal = progress ? progress.filled.reduce((sum, value)=>sum + (Number(value)||0), 0) : 0;
    const canComplete = canEventuallyCompletePlatoon(pid, platoonIdx, simState);
    const statusLabel = progress?.completed
      ? ('Completed on Day '+progress.completedDay)
      : !canComplete
        ? 'Unavailable with current roster'
      : (filledTotal ? (filledTotal+'/'+platoon.totalSlots+' filled') : 'Unfilled');
    const reqHtml = platoon.requirements.map((requirement, reqIdx)=>{
      const filled = progress?.filled?.[reqIdx] || 0;
      const baseReq = baselineSlots.find(slot=>normalizeDefId(slot.defId).toUpperCase() === requirement.defId) || null;
      const have = baseReq?.have ?? 0;
      const countClass = filled >= requirement.need ? 'good' : (have >= requirement.need ? 'warn' : '');
      const relicText = requirement.combatType === 1 && requirement.minRelic > 0 ? (' · R'+requirement.minRelic+'+') : '';
      const rarityText = (Number(requirement.minRarity)||7) + '★';
      return '<div class="ops-req-row">'
        + '<div><div class="ops-req-name">'+escHtml(requirement.name)+'</div>'
        + '<div class="ops-req-sub">Need '+requirement.need+' · '+rarityText+relicText+(baseReq ? (' · guild has '+have) : '')+'</div></div>'
        + '<div class="ops-req-count '+countClass+'">'+filled+'/'+requirement.need+'</div>'
        + '</div>';
    }).join('');
    return '<div class="ops-platoon'+(progress?.completed?' complete':'')+'">'
      + '<div class="ops-platoon-header"><div class="ops-platoon-title">Platoon '+platoon.id+'</div>'
      + '<div class="ops-platoon-status'+(progress?.completed?' complete':'')+'">'+escHtml(statusLabel)+'</div></div>'
      + reqHtml + '</div>';
  }).join('');
  return '<div class="ops-planet-card">'
    + '<div class="ops-planet-head"><div><div class="ops-planet-name">'+escHtml(planetMeta.name || pid)+'</div>'
    + '<div class="ops-planet-meta">'+escHtml(metaLabel)+'</div></div>'
    + '<div class="ops-planet-summary"><strong>'+completedCount+'/'+platoonCount+'</strong><br>platoons<br>'
    + '<span style="color:var(--gold)">'+fmtM(points)+'</span></div></div>'
    + platoonsHtml + '</div>';
}

function getOpsDayAccent(dayNumber){
  return ['#f0c040','#27ae60','#2980b9','#8e44ad','#c0392b','#16a085'][(Math.max(1, Number(dayNumber)||1)-1)%6];
}

function getActivePlanetIdsForPlanDay(dayPlan){
  const ids = [];
  Object.values(dayPlan?.chains || {}).forEach(chain=>{
    const pid = chain?.planet?.id;
    if(pid && _opsDefinitions[pid]) ids.push(pid);
  });
  (dayPlan?.bonusPlanets || []).forEach(entry=>{
    const pid = entry?.planet?.id;
    if(pid && _opsDefinitions[pid]) ids.push(pid);
  });
  return [...new Set(ids)].sort((a,b)=>{
    const ai = ALL_PLANETS.findIndex(planet=>planet.id === a);
    const bi = ALL_PLANETS.findIndex(planet=>planet.id === b);
    return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi);
  });
}

function countPlanetActiveDaysRemaining(planResult, pid, fromDay){
  return (planResult?.days || []).filter(dayPlan=>
    Number(dayPlan?.day || 0) >= Number(fromDay || 0)
    && getActivePlanetIdsForPlanDay(dayPlan).includes(pid)
  ).length;
}

function getOperationsDayBundle(planResult, dayNumber){
  const dayPlan = (planResult?.days || []).find(entry=>Number(entry?.day || 0) === Number(dayNumber)) || null;
  const opsDay = (planResult?.opsSummary?.days || []).find(entry=>Number(entry?.day || 0) === Number(dayNumber)) || null;
  const activePlanetIds = dayPlan ? getActivePlanetIdsForPlanDay(dayPlan) : [];
  return {dayPlan, opsDay, activePlanetIds};
}

function getPlanetLabelForSelectedDay(dayPlan, pid){
  const chainEntry = Object.values(dayPlan?.chains || {}).find(entry=>entry?.planet?.id === pid);
  if(chainEntry){
    if(chainEntry.status === 'preload') return 'Preload focus';
    if(chainEntry.status === 'commit'){
      return chainEntry.stars >= 3 ? '3-star push'
        : chainEntry.stars === 2 ? '2-star push'
        : '1-star push';
    }
    if(chainEntry.status === 'building') return 'Still building';
  }
  if((dayPlan?.bonusPlanets || []).some(entry=>entry?.planet?.id === pid)) return 'Bonus planet';
  return 'Active planet';
}

function getRequirementAvailabilityCount(pid, platoonIdx, requirement){
  const baselineSlots = _platoonAnalysis?.[pid]?.[platoonIdx]?.slots || [];
  const match = baselineSlots.find(slot=>
    normalizeDefId(slot?.defId).toUpperCase() === normalizeDefId(requirement?.defId).toUpperCase()
  );
  if(match && match.have != null) return Number(match.have) || 0;
  const owners = new Set();
  getPotentialOpsCandidates(requirement).forEach(candidate=>owners.add(String(candidate.allyCode)));
  return owners.size;
}

function getOpsRequirementLabel(requirement){
  const rarity = (Number(requirement?.minRarity) || 7) + '★';
  const combatType = Number(requirement?.combatType) || inferUnitCombatType({defId:requirement?.defId});
  return combatType === 2
    ? (rarity + ' ship')
    : (rarity + ' | R' + (Number(requirement?.minRelic) || 0) + '+');
}

function getOpsRequirementShortfallKey(requirement){
  return [
    normalizeDefId(requirement?.defId).toUpperCase(),
    Number(requirement?.minRarity) || 7,
    Number(requirement?.combatType) || inferUnitCombatType({defId:requirement?.defId}),
    Number(requirement?.minRelic) || 0
  ].join('|');
}

function summarizeOpsRequirementShortfalls(entries){
  const grouped = {};
  (entries || []).forEach(entry=>{
    const requirement = entry?.requirement || entry;
    const needed = Number(entry?.needed != null ? entry.needed : entry?.remaining) || 0;
    const availableCount = Number(entry?.availableCount) || 0;
    if(!requirement || needed <= 0) return;
    const key = getOpsRequirementShortfallKey(requirement);
    if(!grouped[key]){
      grouped[key] = {
        key,
        requirement,
        needed: 0,
        availableCount,
        missing: 0
      };
    }
    grouped[key].needed += needed;
    grouped[key].availableCount = Math.max(grouped[key].availableCount, availableCount);
  });
  return Object.values(grouped)
    .map(item=>({
      ...item,
      missing: Math.max(0, item.needed - item.availableCount)
    }))
    .filter(item=>item.missing > 0)
    .sort((a,b)=>
      (b.missing - a.missing)
      || defIdToName(a.requirement?.defId, a.requirement?.name).localeCompare(defIdToName(b.requirement?.defId, b.requirement?.name))
    );
}

function formatOpsShortfallText(item){
  const name = defIdToName(item?.requirement?.defId, item?.requirement?.name);
  return name + ' x' + (Number(item?.missing) || 0) + ' (' + getOpsRequirementLabel(item?.requirement) + ')';
}

function getOperationsPlanetShortfallSummary(planResult, pid, dayNumber){
  const planetDef = _opsDefinitions?.[pid];
  if(!planetDef) return {snapshots:[], planetShortfalls:[], impossiblePlatoons:[]};
  const snapshots = (planetDef.platoons || []).map((platoon, platoonIdx)=>{
    const snapshot = buildOperationsPlatoonSnapshot(planResult, pid, platoonIdx, dayNumber);
    return snapshot ? {
      ...snapshot,
      platoonIdx,
      platoonId: platoon.id
    } : null;
  }).filter(Boolean);
  const remainingEntries = snapshots
    .filter(snapshot=>!snapshot.completedByDay)
    .flatMap(snapshot=>snapshot.reqStates.map(entry=>({
      requirement: entry.requirement,
      availableCount: entry.availableCount,
      needed: entry.remaining
    })));
  const planetShortfalls = summarizeOpsRequirementShortfalls(remainingEntries);
  const impossiblePlatoons = snapshots
    .filter(snapshot=>snapshot.impossible)
    .map(snapshot=>({
      platoonIdx: snapshot.platoonIdx,
      platoonId: snapshot.platoonId,
      totalFilled: snapshot.totalFilled,
      totalSlots: snapshot.totalSlots,
      shortfalls: summarizeOpsRequirementShortfalls(snapshot.reqStates.map(entry=>({
        requirement: entry.requirement,
        availableCount: entry.availableCount,
        needed: entry.remaining
      })))
    }))
    .filter(entry=>entry.shortfalls.length);
  return {snapshots, planetShortfalls, impossiblePlatoons};
}

function buildOpsMissingSummaryHtml(planResult, pid, dayNumber, classPrefix='ops'){
  const summary = getOperationsPlanetShortfallSummary(planResult, pid, dayNumber);
  if(!summary.planetShortfalls.length && !summary.impossiblePlatoons.length) return '';
  const planetLine = summary.planetShortfalls.length
    ? summary.planetShortfalls.map(item=>escHtml(formatOpsShortfallText(item))).join(' · ')
    : 'None';
  const impossibleLines = summary.impossiblePlatoons.length
    ? summary.impossiblePlatoons.map(entry=>
        '<div class="'+classPrefix+'-missing-line"><strong>Platoon '+entry.platoonId+'</strong>: '
        + entry.shortfalls.map(item=>escHtml(formatOpsShortfallText(item))).join(' · ')
        + '</div>'
      ).join('')
    : '<div class="'+classPrefix+'-missing-line">No impossible platoons on this planet by this day.</div>';
  return '<div class="'+classPrefix+'-missing-card">'
    + '<div class="'+classPrefix+'-missing-title">Missing units summary</div>'
    + '<div class="'+classPrefix+'-missing-text">To complete all remaining platoons on this planet in one day, the guild is still short: '
    + planetLine + '</div>'
    + '<div class="'+classPrefix+'-missing-subtitle">Impossible platoon blockers</div>'
    + impossibleLines
    + '</div>';
}

function buildOperationsPlatoonSnapshot(planResult, pid, platoonIdx, dayNumber){
  const planetDef = _opsDefinitions?.[pid];
  const platoonDef = planetDef?.platoons?.[platoonIdx];
  const finalPlanetState = planResult?.opsState?.planets?.[pid];
  const finalPlatoonState = finalPlanetState?.platoons?.[platoonIdx];
  if(!planetDef || !platoonDef || !finalPlatoonState) return null;

  const daysRemaining = countPlanetActiveDaysRemaining(planResult, pid, dayNumber);
  const reqStates = (platoonDef.requirements || []).map((requirement, reqIdx)=>{
    const assignmentHistory = [...(finalPlatoonState?.assignments?.[reqIdx] || [])].sort((a,b)=>
      (Number(a?.day) || 0) - (Number(b?.day) || 0)
      || String(a?.allyCode || '').localeCompare(String(b?.allyCode || ''))
    );
    const filledToDay = assignmentHistory.filter(entry=>(Number(entry?.day) || 0) <= Number(dayNumber));
    const filledToday = assignmentHistory.filter(entry=>(Number(entry?.day) || 0) === Number(dayNumber));
    const availableCount = getRequirementAvailabilityCount(pid, platoonIdx, requirement);
    const remaining = Math.max(0, (Number(requirement?.need) || 0) - filledToDay.length);
    return {requirement, reqIdx, filledToDay, filledToday, availableCount, remaining};
  });

  const totalFilled = reqStates.reduce((sum, entry)=>sum + entry.filledToDay.length, 0);
  const totalSlots = Number(platoonDef?.totalSlots) || reqStates.reduce((sum, entry)=>sum + (Number(entry.requirement?.need) || 0), 0);
  const completedDay = Number(finalPlatoonState?.completedDay) || 0;
  const completedByDay = completedDay > 0 && completedDay <= Number(dayNumber);
  const assignedTodayCount = reqStates.reduce((sum, entry)=>sum + entry.filledToday.length, 0);
  const impossible = !completedByDay && reqStates.some(entry=>
    entry.remaining > 0 && (entry.availableCount * Math.max(1, daysRemaining)) < entry.remaining
  );

  return {
    platoonDef,
    reqStates,
    totalFilled,
    totalSlots,
    completedDay,
    completedByDay,
    assignedTodayCount,
    daysRemaining,
    impossible,
  };
}

function setOperationsDay(dayNumber){
  _opsSelectedDay = Math.max(1, Number(dayNumber) || 1);
  const bundle = getOperationsDayBundle(_lastPlanResult, _opsSelectedDay);
  if(!bundle.activePlanetIds.includes(_opsSelectedPlanet)){
    _opsSelectedPlanet = bundle.activePlanetIds[0] || '';
  }
  renderOperationsTab(_lastPlanResult);
  queueSaveAppState();
}

function setOperationsPlanet(pid){
  _opsSelectedPlanet = String(pid || '').trim();
  renderOperationsTab(_lastPlanResult);
  queueSaveAppState();
}

function buildOperationsDayPickerHtml(planResult){
  const days = planResult?.days || [];
  if(!days.length){
    return '<div class="ops-empty">Run the day-by-day optimizer once to unlock the Operations planner.</div>';
  }
  return days.map(dayPlan=>{
    const dayNumber = Number(dayPlan?.day || 0);
    const accent = getOpsDayAccent(dayNumber);
    const {opsDay, activePlanetIds} = getOperationsDayBundle(planResult, dayNumber);
    const slotsToday = Object.values(opsDay?.planets || {}).reduce((sum, planet)=>sum + (Number(planet?.slotsFilled) || 0), 0);
    const completeToday = Object.values(opsDay?.planets || {}).reduce((sum, planet)=>sum + (Number(planet?.completedToday) || 0), 0);
    const active = _opsSelectedDay === dayNumber;
    return '<div class="ops-day-card ops-day-picker'+(active?' active':'')+'" onclick="setOperationsDay('+dayNumber+')"'
      + ' style="border-color:'+accent+';background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(0,0,0,.18))">'
      + '<div class="ops-day-head"><div class="ops-day-title">Day '+dayNumber+'</div>'
      + '<div class="ops-day-points">'+fmtM(opsDay?.pointsEarned || 0)+'</div></div>'
      + '<div class="ops-day-kicker">'+activePlanetIds.length+' active planet'+(activePlanetIds.length===1?'':'s')+'</div>'
      + '<div class="ops-day-sub">'+slotsToday+' slots planned'
      + (completeToday ? (' | '+completeToday+' platoon'+(completeToday===1?'':'s')+' completed') : '')
      + '</div></div>';
  }).join('');
}

function buildOperationsPlanetStripHtml(planResult, dayNumber, activePlanetIds){
  if(!activePlanetIds.length){
    return '<div class="ops-empty">No active planets were planned for this day.</div>';
  }
  const {dayPlan, opsDay} = getOperationsDayBundle(planResult, dayNumber);
  if(!activePlanetIds.includes(_opsSelectedPlanet)){
    _opsSelectedPlanet = activePlanetIds[0] || '';
  }
  return '<div class="ops-planet-strip">' + activePlanetIds.map(pid=>{
    const meta = getPlanetMetaById(pid);
    const planetToday = opsDay?.planets?.[pid] || null;
    const isActive = _opsSelectedPlanet === pid;
    return '<button type="button" class="ops-planet-pill'+(isActive?' active':'')+'" onclick="setOperationsPlanet(\''+pid+'\')">'
      + '<div class="ops-planet-pill-name">'+escHtml(meta?.name || pid)+'</div>'
      + '<div class="ops-planet-pill-meta">'+escHtml(getPlanetLabelForSelectedDay(dayPlan, pid))+' | Zone '+(meta?.zone || '?')+'</div>'
      + '<div class="ops-planet-pill-today">'+(planetToday
          ? ((Number(planetToday?.slotsFilled) || 0) + ' slots today'
            + ((Number(planetToday?.completedToday) || 0) ? (' | '+planetToday.completedToday+' complete') : ''))
          : 'No new slots planned today')
      + '</div></button>';
  }).join('') + '</div>';
}

function buildOperationsPlatoonDetailHtml(planResult, dayNumber, pid){
  if(!pid || !_opsDefinitions?.[pid]){
    return '<div class="ops-empty">Select one of the active planets above to view that day&apos;s platoon plan.</div>';
  }
  const planetDef = _opsDefinitions[pid];
  const planetMeta = getPlanetMetaById(pid) || planetDef;
  const {dayPlan, opsDay} = getOperationsDayBundle(planResult, dayNumber);
  const planetToday = opsDay?.planets?.[pid] || null;
  const memberNameMap = getGuildMemberNameMap();
  const daysRemaining = countPlanetActiveDaysRemaining(planResult, pid, dayNumber);

  const platoonHtml = (planetDef.platoons || []).map((platoon, platoonIdx)=>{
    const snapshot = buildOperationsPlatoonSnapshot(planResult, pid, platoonIdx, dayNumber);
    if(!snapshot) return '';
    const statusClass = snapshot.completedByDay
      ? 'complete'
      : snapshot.impossible
        ? 'impossible'
        : snapshot.totalFilled > 0
          ? 'partial'
          : 'ready';
    const statusLabel = snapshot.completedByDay
      ? (snapshot.completedDay === dayNumber ? 'Completed today' : ('Completed on Day '+snapshot.completedDay))
      : snapshot.impossible
        ? ('Impossible with current roster | '+snapshot.totalFilled+'/'+snapshot.totalSlots+' filled')
        : snapshot.assignedTodayCount > 0
          ? ('Partial today | '+snapshot.totalFilled+'/'+snapshot.totalSlots+' filled')
          : snapshot.totalFilled > 0
            ? ('Partially loaded | '+snapshot.totalFilled+'/'+snapshot.totalSlots+' filled')
            : ('Unfilled | '+daysRemaining+' day'+(daysRemaining===1?'':'s')+' left');

    const slotHtml = snapshot.reqStates.map(entry=>{
      const req = entry.requirement;
      return Array.from({length:Number(req?.need) || 0}, (_, slotIdx)=>{
        const assignment = entry.filledToDay[slotIdx] || null;
        const assignee = assignment
          ? ('- ' + (memberNameMap[String(assignment.allyCode)] || String(assignment.allyCode))
            + ((Number(assignment?.day) || 0) === Number(dayNumber) ? ' (today)' : (' (Day '+assignment.day+')')))
          : '- Unassigned';
        const reqText = getOpsRequirementLabel(req);
        return '<div class="ops-slot-card">'
          + '<div class="ops-slot-name">'+escHtml(req.name)+(((Number(req?.need) || 0) > 1) ? (' '+(slotIdx+1)) : '')+'</div>'
          + '<div class="ops-slot-assignee'+(assignment?'':' unassigned')+'">'+escHtml(assignee)+'</div>'
          + '<div class="ops-slot-meta">Players available: '+entry.availableCount+' | Requirement: '+escHtml(reqText)+'</div>'
          + '</div>';
      }).join('');
    }).join('');

    return '<div class="ops-platoon-day '+statusClass+'">'
      + '<div class="ops-platoon-day-head">'
      + '<div><div class="ops-platoon-day-title">Platoon '+platoon.id+'</div>'
      + '<div class="ops-planet-meta">'+snapshot.totalFilled+'/'+snapshot.totalSlots+' slots filled</div></div>'
      + '<div class="ops-platoon-day-badge"><span class="ops-platoon-day-dot"></span><span>'+escHtml(statusLabel)+'</span></div>'
      + '</div>'
      + '<div class="ops-slot-list">'+slotHtml+'</div>'
      + '</div>';
  }).join('');
  const missingSummaryHtml = buildOpsMissingSummaryHtml(planResult, pid, dayNumber, 'ops');

  return '<div class="ops-stage-card">'
    + '<div class="ops-stage-head">'
    + '<div><div class="ops-stage-title">'+escHtml(planetMeta?.name || pid)+' - Day '+dayNumber+'</div>'
    + '<div class="ops-stage-sub">'+escHtml(
        getPlanetLabelForSelectedDay(dayPlan, pid)
        + '. Green platoons are completed by this day, blue platoons are only partially filled by this day, and red platoons cannot be finished with the current roster before the planet closes.'
      )+'</div></div>'
    + '<div class="ops-stage-meta">'
    + 'Today: '+(planetToday ? ((planetToday.slotsFilled || 0)+' slots | '+fmtM(planetToday.pointsEarned || 0)) : 'No new slots')+'<br>'
    + 'Days remaining active: '+daysRemaining+'<br>'
    + 'Zone '+(planetMeta?.zone || '?')+' requirements'
    + '</div></div>'
    + '<div class="ops-platoon-grid">'+(platoonHtml || '<div class="ops-empty">No platoons are available for this planet.</div>')+'</div>'
    + missingSummaryHtml
    + '</div>';
}

function getPlatoonHtml(pid) {
  const projected = getProjectedOpsPlanetStats(pid);
  const baseline = _platoonAnalysis[pid];
  if(!projected && (!baseline || !baseline.length)) return '<div class="ops-pts-note">Operations auto-planned in the Operations tab.</div>';
  if(projected){
    return '<div class="ops-pts-note">Projected ops: '+projected.completedPlatoons+'/'+projected.totalPlatoons
      +' platoons | '+fmtM(projected.points)+'</div>';
  }
  const fillable = baseline.filter(platoon=>platoon.fillable).length;
  return '<div class="ops-pts-note">Isolated fillability: '+fillable+'/'+baseline.length+' platoons</div>';
}

function calcSummary(){
  let st=0,ot=0,om=0;
  ALL_PLANETS.forEach(p=>{
    if(p.unlockedBy&&!bonusUnlocked(p.id)) return;
    const {star} = calcStars(p.id,1);
    const {opsFilled} = calcPlanetPts(p.id,1);
    st += star;
    ot += opsFilled;
    om += 6;
  });
  document.getElementById('s-stars').textContent = 'Stars ' + (_lastPlanStars !== null ? _lastPlanStars : st);
  if(_lastPlanResult?.opsSummary && !_planDirty){
    ot = _lastPlanResult.opsSummary.totalCompleted;
    om = _lastPlanResult.opsSummary.totalPlatoons;
  }
  document.getElementById('s-ops').textContent = ot + '/' + om;
}

function invalidateOperationsCaches(){
  const hadPlan = hasCompletedOptimization() || !!document.getElementById('day-plan-output')?.textContent.trim();
  _opsPoolByDefId = null;
  _lastPlanResult = null;
  _lastPlanStars = null;
  _greedyGenomeCache = null;
  _planDirty = hadPlan;
  updateOperationsTabVisibility();
  updateDayPlanUiState();
}

async function ensureOperationsDefinitions(force=false){
  if(!force && hasOperationsDefinitions()) return _opsDefinitions;
  if(_opsLoadPromise && !force) return _opsLoadPromise;
  _opsLoadPromise = (async ()=>{
    const resp = await fetch('/api/ops-definitions', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:'{}'
    });
    const data = await resp.json();
    if(data.status !== 'ok' || !data.defs){
      throw new Error(data.error || 'Operations definitions unavailable');
    }
    _opsDefinitions = normalizeOperationsDefinitionsData(data.defs);
    _opsDefinitionsSourceLabel = String(data.sourceLabel || data.source || '').trim();
    _greedyGenomeCache = null;
    queueSaveAppState();
    return _opsDefinitions;
  })();
  try{
    return await _opsLoadPromise;
  } finally {
    _opsLoadPromise = null;
  }
}

function ensureProjectedPlanResult(){
  return canViewOperationsTab() ? _lastPlanResult : null;
}

function renderOperationsTab(planResult){
  const planetsEl = document.getElementById('ops-planet-list');
  const daysEl = document.getElementById('ops-day-overview');
  if(!planetsEl || !daysEl) return;

  document.getElementById('ops-def-status').textContent = hasOperationsDefinitions()
    ? (Object.keys(_opsDefinitions).length + ' planets' + (_opsDefinitionsSourceLabel ? (' · ' + _opsDefinitionsSourceLabel) : ''))
    : 'Unavailable';
  document.getElementById('ops-roster-status').textContent = scannedRosterCount() + ' scanned';

  if(!canViewOperationsTab() || !planResult){
    document.getElementById('ops-total-platoons').textContent = '--';
    document.getElementById('ops-total-points').textContent = '--';
    daysEl.innerHTML = '<div class="ops-empty">Run the day-by-day optimizer once to unlock the Operations planner.</div>';
    planetsEl.innerHTML = '<div class="ops-empty">Operations assignments appear here after a successful optimizer run.</div>';
    return;
  }

  const isolatedCounts = Object.entries(_platoonAnalysis || {}).reduce((acc, [pid, platoons])=>{
    const meta = getPlanetMetaById(pid);
    if(meta?.unlockedBy && !bonusUnlocked(pid)) return acc;
    const fillable = Array.isArray(platoons) ? platoons.filter(platoon=>platoon.fillable).length : 0;
    acc.total += Array.isArray(platoons) ? platoons.length : 0;
    acc.fillable += fillable;
    acc.points += fillable * (Number(meta?.opsVal)||0);
    return acc;
  }, {fillable:0,total:0,points:0});

  const opsSummary = planResult?.opsSummary || null;
  document.getElementById('ops-total-platoons').textContent = opsSummary
    ? (opsSummary.totalCompleted + '/' + opsSummary.totalPlatoons)
    : (isolatedCounts.total ? (isolatedCounts.fillable + '/' + isolatedCounts.total) : '--');
  document.getElementById('ops-total-points').textContent = opsSummary
    ? fmtM(opsSummary.totalPoints || 0)
    : (isolatedCounts.total ? fmtM(isolatedCounts.points || 0) : '--');
  if(!hasOperationsDefinitions()){
    daysEl.innerHTML = '<div class="ops-empty">Built-in operations definitions are unavailable in this build.</div>';
    planetsEl.innerHTML = '<div class="ops-empty">Built-in operations definitions are unavailable in this build.</div>';
    return;
  }
  const availableDays = (planResult?.days || []).map(entry=>Number(entry?.day) || 0).filter(Boolean);
  if(!availableDays.includes(_opsSelectedDay)){
    _opsSelectedDay = availableDays[0] || 1;
  }
  daysEl.innerHTML = buildOperationsDayPickerHtml(planResult);

  const {activePlanetIds} = getOperationsDayBundle(planResult, _opsSelectedDay);
  if(!activePlanetIds.includes(_opsSelectedPlanet)){
    _opsSelectedPlanet = activePlanetIds[0] || '';
  }
  planetsEl.innerHTML = '<div class="ops-main-stage">'
    + buildOperationsPlanetStripHtml(planResult, _opsSelectedDay, activePlanetIds)
    + buildOperationsPlatoonDetailHtml(planResult, _opsSelectedDay, _opsSelectedPlanet)
    + '</div>';
}

async function refreshOperationsPlanning(forceDefinitions=false){
  try{
    await ensureOperationsDefinitions(forceDefinitions);
  }catch(err){
    renderOperationsTab(_lastPlanResult);
    throw err;
  }
  const projected = ensureProjectedPlanResult();
  renderOperationsTab(projected);
  if(scannedRosterCount() && !Object.keys(_platoonAnalysis).length){
    try{
      const resp = await fetch('/api/platoon-analysis', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:'{}'});
      const data = await resp.json();
      if(!data.error){
        _platoonAnalysis = data.analysis || {};
        queueSaveAppState();
        renderOperationsTab(projected || _lastPlanResult);
      }
    }catch(err){}
  }
}

function initOperationsTab(){
  if(!canViewOperationsTab()){
    renderOperationsTab(null);
    return;
  }
  refreshOperationsPlanning(false).catch(err=>{
    renderOperationsTab(_lastPlanResult);
    showImportStatus('Operations page: '+err.message, 'err');
  });
}

async function runAdam(onProg, onDone) {
  const AGENTS=10, ITERS=90, LR=0.28, B1=0.9, B2=0.999, EPS=1e-8, STEP=0.45;
  const baseG = greedyGenome();
  const agents = Array.from({length:AGENTS},(_,ai)=>({
    pos: ai<3 ? baseG.map(g=>g + (Math.random()-0.5)*0.35) : Array.from({length:OPT_GENES},()=>Math.random()*3),
    m:new Array(OPT_GENES).fill(0),
    v:new Array(OPT_GENES).fill(0),
    t:0
  }));
  let best={genome:baseG.map(clampGene), score:evalGenome(baseG.map(clampGene))};

  for (let iter=0; iter<ITERS; iter++) {
    for (let ai=0; ai<agents.length; ai++) {
      if(((iter * AGENTS) + ai) % 4 === 0){
        await _yield();
        onProg((iter + (ai / AGENTS)) / ITERS, best.score);
      }
      const ag = agents[ai];
      const current = ag.pos.map(clampGene);
      const baseScore = evalGenome(current);
      if(baseScore > best.score) best = {genome:[...current], score:baseScore};

      const delta = Array.from({length:OPT_GENES},()=>Math.random()<0.5 ? -1 : 1);
      const plus = ag.pos.map((x,i)=>Math.max(0, Math.min(3, x + STEP * delta[i]))).map(clampGene);
      const minus = ag.pos.map((x,i)=>Math.max(0, Math.min(3, x - STEP * delta[i]))).map(clampGene);
      const sp = evalGenome(plus);
      const sm = evalGenome(minus);
      if(sp > best.score) best = {genome:[...plus], score:sp};
      if(sm > best.score) best = {genome:[...minus], score:sm};

      const scale = (sp - sm) / (2 * STEP);
      ag.t++;
      for(let i=0; i<OPT_GENES; i++){
        const grad = scale * delta[i];
        ag.m[i] = B1*ag.m[i] + (1-B1)*grad;
        ag.v[i] = B2*ag.v[i] + (1-B2)*grad*grad;
        const mh = ag.m[i] / (1 - Math.pow(B1, ag.t));
        const vh = ag.v[i] / (1 - Math.pow(B2, ag.t));
        const pull = (best.genome[i] - current[i]) * 0.05;
        ag.pos[i] = Math.max(0, Math.min(3, ag.pos[i] + LR*mh/(Math.sqrt(vh)+EPS) + pull));
      }
    }
  }
  onProg(1, best.score);
  onDone(best);
}

async function startOptimization() {
  if (_optRunning) return;
  const btn = document.getElementById('quick-plan-btn');
  const fill = document.getElementById('opt-pfill');
  const status = document.getElementById('opt-status-line');
  const sel = document.getElementById('algo-sel');
  const algoKey = String(sel?.value || '').trim();
  if(!_optimizerWarningAccepted || !algoKey){
    updateDayPlanUiState();
    return;
  }

  _optRunning = true;
  updateDayPlanUiState({preserveStatus:true});
  let keepStatus = false;

  try{
    await ensureOperationsDefinitions(false);

    const algos = algoKey === 'all'
      ? ['greedy','sa','pso','ga','adam']
      : [algoKey];
    const runners = {ga:runGA, sa:runSA, pso:runPSO, adam:runAdam, greedy:runGreedy};
    const algoLabel = key => getAlgoMeta(key).label;
    btn.textContent = 'Running ' + algoLabel(algoKey) + '...';
    fill.style.width = '0%';
    status.textContent = 'Preparing optimization run...';

    const setProgress = (frac, score, algo) => {
      fill.style.width = (frac * 100) + '%';
      const pct = Math.round(frac * 100);
      status.textContent = algoLabel(algo) + ' - ' + pct + '% complete'
        + (score > 0 ? (' | best so far: ' + score + ' stars') : '');
    };

    let bestResult = null;
    const allResults = [];
    for (let ai=0; ai<algos.length; ai++) {
      const algo = algos[ai];
      const runner = runners[algo];
      if (!runner) continue;
      await new Promise((resolve, reject) => {
        try{
          const maybePromise = runner(
            (p, score) => setProgress((ai + p) / algos.length, score, algo),
            result => {
              allResults.push({algo, ...result});
              if (!bestResult || result.score > bestResult.score) bestResult = {algo, ...result};
              resolve();
            }
          );
          Promise.resolve(maybePromise).catch(reject);
        }catch(err){
          reject(err);
        }
      });
    }

    if(!bestResult) throw new Error('No optimization result was produced.');

    const result = simulateGenomeDetailed(bestResult.genome);
    _planDirty = false;
    renderOptPlan(result, bestResult.algo, allResults);
    updateOperationsTabVisibility();
    queueSaveAppState();

    fill.style.width = '100%';
    const summary = allResults.map(r => `${algoLabel(r.algo)}: ${r.score} stars`).join(' | ');
    status.textContent = 'Complete - Best: ' + bestResult.score + ' stars (' + algoLabel(bestResult.algo) + ')'
      + (allResults.length > 1 ? (' | ' + summary) : '');
    keepStatus = true;
    setTimeout(()=>{ if(!_optRunning) fill.style.width='0%'; }, 3000);
  } catch(err){
    console.error('Optimization error:', err);
    status.textContent = 'Optimization failed: ' + err.message;
    fill.style.width = '0%';
    keepStatus = true;
  } finally {
    _optRunning = false;
    btn.textContent = 'Run Optimization';
    updateDayPlanUiState({preserveStatus: keepStatus});
  }
}

function showTab(name){
  if(name === 'operations' && !canViewOperationsTab()){
    name = 'dayplan';
  }
  document.querySelectorAll('.nav-tab').forEach(tab=>{
    tab.classList.toggle('active', tab.dataset.tab === name);
  });
  document.querySelectorAll('.panel').forEach(panel=>panel.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
  if(name === 'planner' && !document.getElementById('chain-ds').innerHTML) rebuildPlannerChains();
  if(name === 'dayplan'){
    renderDayPlanGuide();
    updateDayPlanUiState({preserveStatus: hasCompletedOptimization() && !_planDirty});
  }
  if(name === 'operations') initOperationsTab();
  if(name === 'guides') initGuideTab();
  if(name === 'roster') initRosterTab();
}

// INIT
checkComlinkStatus();
buildUndepTable();
renderDayPlanGuide();
updateOperationsTabVisibility();
updateDayPlanUiState();
renderFalloffViz();
calcSummary();
loadPersistedAppState();
</script>

<!-- floating shutdown button -->
<div style="position:fixed;bottom:16px;right:16px;z-index:999">
  <button class="btn" onclick="shutdown()" style="font-size:.6rem;padding:5px 12px;background:rgba(8,12,20,.9);border-color:var(--ds-dim);color:var(--ds)">Stop Server</button>
</div>
</body>
</html>"""

# ─── PLATFORM DETECTION ──────────────────────────────────────────────────────
def get_platform():
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        arch = "arm64" if "arm" in machine else "x64"
        return ("win", arch, ".exe", ".zip")
    elif system == "Darwin":
        arch = "arm64" if ("arm" in machine or "m1" in machine or "m2" in machine or "m3" in machine) else "x64"
        return ("macos", arch, "", ".zip")
    elif system == "Linux":
        arch = "arm64" if "arm" in machine or "aarch" in machine else "x64"
        return ("linux", arch, "", ".tar.gz")
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

# ─── COMLINK MANAGEMENT ───────────────────────────────────────────────────────
comlink_proc  = None
_comlink_binary = None  # set after first successful start

def find_or_download_comlink():
    os_name, arch, exe_ext, arc_ext = get_platform()
    binary_name = f"swgoh-comlink{exe_ext}"
    binary_path = COMLINK_DIR / binary_name

    # Accept versioned filenames placed manually e.g. swgoh-comlink-4.1.1.exe
    if not binary_path.exists():
        candidates = sorted(
            [p for p in COMLINK_DIR.glob(f"swgoh-comlink*{exe_ext}") if p.is_file()],
            key=lambda p: len(p.name)
        )
        if candidates:
            print(f"   Found versioned binary '{candidates[0].name}' — copying as {binary_name}")
            shutil.copy2(candidates[0], binary_path)
            if os_name != "win":
                os.chmod(binary_path, 0o755)

    if binary_path.exists():
        print(f"   Using comlink binary: {binary_path.name}")
        return binary_path

    print(f"⬇  Downloading swgoh-comlink for {os_name}-{arch}...")
    COMLINK_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch latest release metadata from GitHub
    req = urllib.request.Request(COMLINK_REPO, headers={"User-Agent": APP_NAME})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            release = json.loads(r.read())
    except Exception as e:
        raise RuntimeError(f"Could not fetch release info from GitHub: {e}")

    assets = release.get("assets", [])
    tag = release.get("tag_name", "unknown")
    print(f"   Latest release: {tag}")

    # Match asset by OS and arch
    def score(name):
        n = name.lower()
        s = 0
        if os_name in n: s += 10
        if arch in n: s += 5
        if arc_ext in n: s += 3
        if "comlink" in n: s += 2
        return s

    assets_scored = sorted(assets, key=lambda a: score(a["name"]), reverse=True)
    if not assets_scored or score(assets_scored[0]["name"]) < 5:
        avail = [a["name"] for a in assets]
        raise RuntimeError(f"No matching binary found for {os_name}-{arch}.\nAvailable: {avail}\nDownload manually from: https://github.com/swgoh-utils/swgoh-comlink/releases")

    asset = assets_scored[0]
    url = asset["browser_download_url"]
    size_mb = asset["size"] // 1024 // 1024
    print(f"   Downloading {asset['name']} ({size_mb}MB)...")

    archive_path = COMLINK_DIR / asset["name"]
    urllib.request.urlretrieve(url, archive_path)
    print("   Extracting...")

    if arc_ext == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(COMLINK_DIR)
    elif arc_ext == ".tar.gz":
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(COMLINK_DIR)
    archive_path.unlink(missing_ok=True)

    # Find the binary (may be nested)
    for f in sorted(COMLINK_DIR.rglob(f"*comlink*{exe_ext}"), key=lambda x: len(str(x))):
        if f.is_file() and f != archive_path:
            dest = COMLINK_DIR / binary_name
            shutil.copy2(f, dest)
            if os_name != "win":
                os.chmod(dest, 0o755)
            print(f"   Installed: {dest.name}")
            return dest

    if binary_path.exists():
        if os_name != "win":
            os.chmod(binary_path, 0o755)
        return binary_path

    raise RuntimeError("Could not locate comlink binary after extraction.")


def _comlink_post(path, payload=None, timeout=5):
    """POST request to comlink. Comlink 4.x requires POST for all endpoints."""
    if payload is None:
        payload = {}
    data = json.dumps({"payload": payload, "enums": False}).encode()
    req = urllib.request.Request(
        f"http://localhost:{COMLINK_PORT}/{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def is_comlink_running():
    """Check if comlink is already responding on COMLINK_PORT (POST for v4.x compat)."""
    try:
        _comlink_post("metadata", timeout=2)
        return True
    except Exception:
        return False


def start_comlink(binary_path):
    global comlink_proc
    env = os.environ.copy()
    env["APP_NAME"] = APP_NAME

    # If comlink is already running (e.g. user started it manually), don't start another
    if is_comlink_running():
        print(f"   Comlink already responding on port {COMLINK_PORT} — skipping launch.")
        return

    global _comlink_binary
    _comlink_binary = binary_path
    print(f"🚀 Starting swgoh-comlink on port {COMLINK_PORT}...")
    print(f"   Binary: {binary_path}")

    # Pass app name as both env var and CLI arg (-n) for maximum compatibility
    cmd = [str(binary_path), "-n", APP_NAME]

    # On Windows, CREATE_NO_WINDOW prevents a console popup for the subprocess
    kwargs = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    comlink_proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(COMLINK_DIR),
        **kwargs,
    )

    # Drain stdout/stderr in background threads so pipe buffers never fill.
    # If buffers fill (~64KB on Windows), comlink blocks trying to log and
    # appears "crashed" — this is the most common cause of mid-scan failures.
    def _drain(pipe, label):
        try:
            for line in iter(pipe.readline, b""):
                # Uncomment below to see comlink debug output:
                # print(f"  [comlink {label}] {line.decode(errors='replace').rstrip()}")
                pass
        except Exception:
            pass
    threading.Thread(target=_drain, args=(comlink_proc.stdout, "out"), daemon=True).start()
    threading.Thread(target=_drain, args=(comlink_proc.stderr, "err"), daemon=True).start()

    # Wait up to 15 seconds for comlink to respond
    for attempt in range(30):
        time.sleep(0.5)
        if comlink_proc.poll() is not None:
            msg = "(check terminal for comlink output)"
            print("\n   Comlink exited. Output: " + msg + "\n")
            if "already in use" in msg or "bind" in msg.lower():
                raise RuntimeError(
                    f"Port {COMLINK_PORT} is already in use. "
                    "Close the program using it, or change COMLINK_PORT at the top of this script."
                )
            raise RuntimeError(
                "Comlink failed to start. Output: " + msg + "\n\n"
                "If Windows SmartScreen or antivirus blocked it:\n"
                "  1. Open File Explorer, navigate to the .comlink folder next to the exe\n"
                "  2. Right-click the comlink exe, Properties, check Unblock, click OK\n"
                "  3. Re-run the planner."
            )
        try:
            _comlink_post("metadata", timeout=2)
            print("   ✓ Comlink is ready.")
            return
        except Exception:
            pass

    if comlink_proc.poll() is None:
        print("   ⚠  Comlink process is running but did not respond to health check.")
        print("      Live import may still work — check the app after it opens.")
    else:
        raise RuntimeError("Comlink failed to start.")


def restart_comlink():
    """Kill and restart comlink if it has crashed."""
    global comlink_proc
    print("  Attempting comlink auto-restart...")
    stop_comlink()
    time.sleep(1)
    if _comlink_binary and _comlink_binary.exists():
        try:
            start_comlink(_comlink_binary)
            print("  Comlink restarted successfully.")
            return True
        except Exception as e:
            print(f"  Restart failed: {e}")
    return False


def stop_comlink():
    global comlink_proc
    if comlink_proc and comlink_proc.poll() is None:
        comlink_proc.terminate()
        try:
            comlink_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            comlink_proc.kill()


import threading as _threading
# ─── PLATOON ANALYSIS ──────────────────────────────────────────────────────────
_guild_rosters  = {}    # allyCode -> [{defId, rarity, gear, relic}]
_unit_name_map  = {}    # defId (uppercase) -> in-game display name
_rosters_lock   = _threading.Lock()
_tb_defs_cache  = None  # None=not attempted  {}=failed  dict=success
_tb_defs_lock   = _threading.Lock()
_tb_defs_source = "bundled-wiki"
_tb_defs_fallback_cache = None
_unit_name_reverse_index = None
APP_STATE_FILE  = COMLINK_DIR / "app_state.json"
_VOLATILE_APP_STATE_KEYS = {
    "guildSummary",
    "guildRosters",
    "lastPlanResult",
    "lastPlanStars",
    "platoonAnalysis",
    "selectedGuideMember",
    "selectedRosterMember",
}

_EXTRA_UNIT_NAME_MAP = {
    "4LOM":"4-LOM",
    "APPO":"CC-1119 \"Appo\"",
    "ASAJJDARKDISCIPLE":"Asajj Ventress (Dark Disciple)",
    "BATCHERS3":"Batcher",
    "BAYLANSKOLL":"Baylan Skoll",
    "BRUTUS":"Brutus",
    "CAPTAINENOCH":"Captain Enoch",
    "CAPTAINSILVO":"Captain Silvo",
    "CASSIANUNDERCOVER":"Cassian Andor (Undercover)",
    "CINTA":"Cinta Kaz",
    "CROSSHAIRS3":"Crosshair (Scarred)",
    "DARKREY":"Rey (Dark Side Vision)",
    "DEATHTROOPERPERIDEA":"Death Trooper (Peridea)",
    "DEDRAMEERO":"Dedra Meero",
    "DEPABILLABA":"Depa Billaba",
    "DISGUISEDCLONETROOPER":"Disguised Clone Trooper",
    "EZRAEXILE":"Ezra Bridger (Exile)",
    "GENERALSYNDULLA":"General Syndulla",
    "GLAHSOKATANO":"Ahsoka Tano",
    "GLHONDO":"Pirate King Hondo Ohnaka",
    "GREATMOTHERS":"Great Mothers",
    "HUNTERS3":"Hunter (Mercenary)",
    "HUYANG":"Huyang",
    "IG90":"IG-90",
    "INQUISITORBARRISS":"Inquisitor Barriss",
    "ITHANO":"Captain Ithano",
    "JEDIMASTERMACEWINDU":"Jedi Master Mace Windu",
    "JOCASTANU":"Jocasta Nu",
    "KIX":"Kix",
    "KLEYA":"Kleya Marki",
    "KXSECURITYDROID":"KX Security Droid",
    "MAULHATEFUELED":"Maul (Hate-Fueled)",
    "MAJORPARTAGAZ":"Major Partagaz",
    "MARROK":"Marrok",
    "MAZKANATA":"Maz Kanata",
    "MORGANELSBETH":"Morgan Elsbeth",
    "NIGHTTROOPER":"Night Trooper",
    "OMEGAS3":"Omega (Fugitive)",
    "OPERATIVE":"CX-2",
    "PADAWANSABINE":"Padawan Sabine Wren",
    "QUIGGOLD":"Quiggold",
    "SCORCH":"RC-1262 \"Scorch\"",
    "SHINHATI":"Shin Hati",
    "SM33":"SM-33",
    "STORMTROOPERLUKE":"Stormtrooper Luke",
    "STRANGER":"The Stranger",
    "VADERDUELSEND":"Darth Vader (Duel's End)",
    "VANE":"Vane",
    "VANGUARDTEMPLEGUARD":"Temple Guard",
    "VEL":"Vel Sartha",
    "WRECKERS3":"Wrecker (Mercenary)",
    "YODACHEWBACCA":"Yoda & Chewie",
    "ZUCKUSS":"Zuckuss",
}

_SHIP_NAME_MAP = {
    "ARC170CLONESERGEANT":"Clone Sergeant's ARC-170",
    "ARC170REX":"Rex's ARC-170",
    "BWINGREBEL":"Rebel B-wing",
    "CAPITALCHIMAERA":"Chimaera",
    "CAPITALEXECUTOR":"Executor",
    "CAPITALFINALIZER":"Finalizer",
    "CAPITALJEDICRUISER":"Endurance",
    "CAPITALLEVIATHAN":"Leviathan",
    "CAPITALMALEVOLENCE":"Malevolence",
    "CAPITALMONCALAMARICRUISER":"Home One",
    "CAPITALNEGOTIATOR":"Negotiator",
    "CAPITALPROFUNDITY":"Profundity",
    "CAPITALRADDUS":"Raddus",
    "CAPITALSTARDESTROYER":"Executrix",
    "COMEUPPANCE":"Comeuppance",
    "COMMANDSHUTTLE":"Kylo Ren's Command Shuttle",
    "EBONHAWK":"Ebon Hawk",
    "EMPERORSSHUTTLE":"Emperor's Shuttle",
    "FIRSTORDERTIEECHELON":"TIE Echelon",
    "FURYCLASSINTERCEPTOR":"Fury-class Interceptor",
    "GAUNTLETSTARFIGHTER":"Gauntlet Starfighter",
    "GEONOSIANSTARFIGHTER1":"Sun Fac's Geonosian Starfighter",
    "GEONOSIANSTARFIGHTER2":"Geonosian Soldier's Starfighter",
    "GEONOSIANSTARFIGHTER3":"Geonosian Spy's Starfighter",
    "GHOST":"Ghost",
    "HOUNDSTOOTH":"Hound's Tooth",
    "HYENABOMBER":"Hyena Bomber",
    "IG2000":"IG-2000",
    "JEDISTARFIGHTERAHSOKATANO":"Ahsoka Tano's Jedi Starfighter",
    "JEDISTARFIGHTERANAKIN":"Anakin's Eta-2 Starfighter",
    "JEDISTARFIGHTERCONSULAR":"Jedi Consular's Starfighter",
    "BLADEOFDORIN":"Plo Koon's Jedi Starfighter",
    "MARAUDER":"Marauder",
    "MG100STARFORTRESSSF17":"MG-100 StarFortress SF-17",
    "MILLENNIUMFALCON":"Han's Millennium Falcon",
    "MILLENNIUMFALCONEP7":"Rey's Millennium Falcon",
    "MILLENNIUMFALCONPRISTINE":"Lando's Millennium Falcon",
    "OUTRIDER":"Outrider",
    "PHANTOM2":"Phantom II",
    "PUNISHINGONE":"Punishing One",
    "RAVENSCLAW":"Raven's Claw",
    "RAZORCREST":"Razor Crest",
    "ROGUEONESHIP":"Rogue One",
    "SCYTHE":"Scythe",
    "SITHBOMBER":"B-28 Extinction-class Bomber",
    "SITHFIGHTER":"Sith Fighter",
    "SITHINFILTRATOR":"Scimitar",
    "SLAVE1":"Slave I",
    "SITHSUPREMACYCLASS":"Mark VI Interceptor",
    "TIEADVANCED":"TIE Advanced x1",
    "TIEBOMBERIMPERIAL":"Imperial TIE Bomber",
    "TIEDAGGER":"TIE Dagger",
    "TIEDEFENDER":"TIE Defender",
    "TIEFIGHTERFIRSTORDER":"First Order TIE Fighter",
    "TIEFIGHTERFOSF":"First Order SF TIE Fighter",
    "TIEFIGHTERIMPERIAL":"Imperial TIE Fighter",
    "TIEINTERCEPTOR":"TIE/IN Interceptor Prototype",
    "TIEREAPER":"TIE Reaper",
    "TIESILENCER":"TIE Silencer",
    "UMBARANSTARFIGHTER":"Umbaran Starfighter",
    "UWINGROGUEONE":"Cassian's U-wing",
    "UWINGSCARIF":"Bistan's U-wing",
    "VULTUREDROID":"Vulture Droid",
    "XANADUBLOOD":"Xanadu Blood",
    "XWINGBLACKONE":"Poe Dameron's X-wing",
    "XWINGRED2":"Wedge Antilles's X-wing",
    "XWINGRED3":"Biggs Darklighter's X-wing",
    "XWINGRESISTANCE":"Resistance X-wing",
    "YWINGCLONEWARS":"BTL-B Y-wing Starfighter",
    "YWINGREBEL":"Rebel Y-wing",
}

_UNIT_NAME_ALIASES = {
    "bam": "THEMANDALORIANBESKARARMOR",
    "mandobeskar": "THEMANDALORIANBESKARARMOR",
    "mandobeskararmor": "THEMANDALORIANBESKARARMOR",
    "bokatanmandalor": "MANDALORBOKATAN",
    "dtmg": "MOFFGIDEONS3",
    "darkrey": "DARKREY",
    "reydarksidevision": "DARKREY",
    "padmeamidala": "PADMEAMIDALA",
    "bladeofdorin": "BLADEOFDORIN",
    "plokoonsjedistarfighter": "BLADEOFDORIN",
    "sunfacsgeonosianstarfighter": "GEONOSIANSTARFIGHTER1",
    "geonosiansoldiersstarfighter": "GEONOSIANSTARFIGHTER2",
    "geonosianspysstarfighter": "GEONOSIANSTARFIGHTER3",
    "btlbywingstarfighter": "YWINGCLONEWARS",
    "rebelywing": "YWINGREBEL",
    "scythe": "SCYTHE",
    "omegafugitive": "OMEGAS3",
    "padawansabinewren": "PADAWANSABINE",
    "sabinewrenpadawan": "PADAWANSABINE",
    "rc1262scorch": "SCORCH",
    "templeguard": "VANGUARDTEMPLEGUARD",
    "vanguardtempleguard": "VANGUARDTEMPLEGUARD",
    "wreckermercenary": "WRECKERS3",
    "omega": "BADBATCHOMEGA",
    "wrecker": "BADBATCHWRECKER",
}

_KNOWN_SHIP_DEFIDS = {str(k).upper().replace("_", "") for k in _SHIP_NAME_MAP.keys()}
_KNOWN_CHARACTER_DEFIDS = {str(k).upper().replace("_", "") for k in _EXTRA_UNIT_NAME_MAP.keys()}
_ability_name_map = {}
_localization_value_map = {}
_localization_maps_attempted = False
_skill_meta_map = {}
_unit_skill_reference_map = {}
_unit_crew_map = {}
_unit_crew_skill_reference_map = {}
_statcalc_instance = None
_statcalc_lock = threading.Lock()
_statcalc_calc_lock = threading.Lock()
_statcalc_last_attempt = 0.0
_statcalc_last_error = ""
_STATCALC_RETRY_SECONDS = 30.0


def _canonical_defid(value):
    return str(value or "").split(":")[0].strip()


def _canonical_defid_key(value):
    return _canonical_defid(value).upper().replace("_", "")


def _lookup_unit_name(def_id, fallback=""):
    raw = _canonical_defid(def_id)
    upper = raw.upper()
    key = upper.replace("_", "")
    return (_unit_name_map.get(raw)
            or _unit_name_map.get(upper)
            or _unit_name_map.get(key)
            or _EXTRA_UNIT_NAME_MAP.get(raw)
            or _EXTRA_UNIT_NAME_MAP.get(upper)
            or _EXTRA_UNIT_NAME_MAP.get(key)
            or _SHIP_NAME_MAP.get(raw)
            or _SHIP_NAME_MAP.get(upper)
            or _SHIP_NAME_MAP.get(key)
            or fallback
            or "")


def _coerce_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def _extract_unit_power(unit):
    if not isinstance(unit, dict):
        return 0
    for key in ("gp", "power", "galacticPower", "unitPower"):
        value = unit.get(key)
        if value not in (None, ""):
            coerced = _coerce_int(value, 0)
            if coerced > 0:
                return coerced
    return 0


def _ensure_statcalc(force=False):
    global _statcalc_instance, _statcalc_last_attempt, _statcalc_last_error
    if _statcalc_instance is not None and not force:
        return _statcalc_instance
    now = time.time()
    if (not force and _statcalc_instance is None and _statcalc_last_error
            and (now - _statcalc_last_attempt) < _STATCALC_RETRY_SECONDS):
        return None
    with _statcalc_lock:
        if _statcalc_instance is not None and not force:
            return _statcalc_instance
        _statcalc_last_attempt = now
        if _LocalStatCalc is None or _StatCalcComlinkClient is None or _StatCalcGameDataBuilder is None:
            _statcalc_last_error = _STATCALC_IMPORT_ERROR or "swgoh-comlink Python package is unavailable."
            return None
        try:
            print("Initializing local StatCalc for unit power...")
            with _StatCalcComlinkClient(url=f"http://127.0.0.1:{COMLINK_PORT}") as comlink_client:
                game_data = _StatCalcGameDataBuilder(comlink_client).build()
            _statcalc_instance = _LocalStatCalc(game_data=game_data)
            _statcalc_last_error = ""
            print("Local StatCalc ready.")
            return _statcalc_instance
        except Exception as exc:
            _statcalc_instance = None
            _statcalc_last_error = str(exc)
            print(f"Local StatCalc init failed: {_statcalc_last_error}")
            return None


def _apply_roster_power(player):
    global _statcalc_last_error
    roster = []
    if isinstance(player, dict):
        roster = player.get("rosterUnit") or []
    if not isinstance(roster, list) or not roster:
        return False
    if all(_extract_unit_power(unit) > 0 for unit in roster if isinstance(unit, dict)):
        return True
    calc = _ensure_statcalc()
    if calc is None:
        return False

    def _normalized_skills(unit):
        out = []
        for skill in (unit.get("skill") or unit.get("skills") or []):
            if not isinstance(skill, dict):
                continue
            skill_id = str(skill.get("id") or skill.get("skillId") or skill.get("abilityId") or "").strip()
            if not skill_id:
                continue
            try:
                raw_tier = int(skill.get("tier") or 0)
            except Exception:
                raw_tier = 0
            out.append({"id": skill_id, "tier": raw_tier + 2})
        return out

    def _normalized_char(unit):
        def_id = _canonical_defid(unit.get("definitionId") or unit.get("defId") or unit.get("baseId"))
        return {
            "defId": def_id,
            "rarity": _coerce_int(unit.get("currentRarity") or unit.get("rarity"), 0),
            "level": _coerce_int(unit.get("currentLevel") or unit.get("level"), 0),
            "gear": _coerce_int(unit.get("currentTier") or unit.get("gear"), 0),
            "equipped": unit.get("equipment") or unit.get("equipped") or [],
            "equippedStatMod": unit.get("equippedStatMod"),
            "mods": unit.get("mods"),
            "relic": unit.get("relic"),
            "skills": _normalized_skills(unit),
            "purchasedAbilityId": list(unit.get("purchasedAbilityId") or []),
        }

    def _normalized_ship(unit):
        def_id = _canonical_defid(unit.get("definitionId") or unit.get("defId") or unit.get("baseId"))
        return {
            "defId": def_id,
            "rarity": _coerce_int(unit.get("currentRarity") or unit.get("rarity"), 0),
            "level": _coerce_int(unit.get("currentLevel") or unit.get("level"), 0),
            "skills": _normalized_skills(unit),
        }

    errors = []
    try:
        with _statcalc_calc_lock:
            char_lookup = {}
            ship_units = []
            for unit in roster:
                if not isinstance(unit, dict):
                    continue
                def_id = _canonical_defid(unit.get("definitionId") or unit.get("defId") or unit.get("baseId"))
                if not def_id:
                    continue
                combat_type = unit.get("combatType") or unit.get("type")
                if _infer_combat_type(def_id, combat_type) == 2:
                    ship_units.append(unit)
                    continue
                normalized = _normalized_char(unit)
                try:
                    unit["gp"] = calc.calc_char_gp(normalized)
                    char_lookup[_normalize_loc_key(def_id)] = normalized
                except Exception as exc:
                    errors.append(f"{def_id}: {exc}")
            for unit in ship_units:
                def_id = _canonical_defid(unit.get("definitionId") or unit.get("defId") or unit.get("baseId"))
                crew_ids = _unit_crew_map.get(_normalize_loc_key(def_id), [])
                crew = [char_lookup[cid] for cid in crew_ids if cid in char_lookup]
                try:
                    unit["gp"] = calc.calc_ship_gp(_normalized_ship(unit), crew)
                except Exception as exc:
                    errors.append(f"{def_id}: {exc}")
        _statcalc_last_error = "; ".join(errors[:3]) if errors else ""
        return any(_extract_unit_power(unit) > 0 for unit in roster if isinstance(unit, dict))
    except Exception as exc:
        _statcalc_last_error = str(exc)
        print(f"Local StatCalc roster power failed: {_statcalc_last_error}")
        return False


def _normalize_unit_name_lookup(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", text).strip()


def _add_unit_name_reverse(index, name, def_id):
    clean_name = _normalize_unit_name_lookup(name)
    clean_def = _canonical_defid(def_id)
    if not clean_name or not clean_def:
        return
    existing = index.get(clean_name)
    if not existing:
        index[clean_name] = clean_def
        return
    if existing == clean_def:
        return
    if isinstance(existing, list):
        if clean_def not in existing:
            existing.append(clean_def)
        return
    index[clean_name] = [existing, clean_def]


def _rebuild_unit_name_reverse_index():
    global _unit_name_reverse_index
    index = {}
    for mapping in (_unit_name_map, _EXTRA_UNIT_NAME_MAP, _SHIP_NAME_MAP):
        for def_id, name in mapping.items():
            _add_unit_name_reverse(index, name, def_id)
    for roster in _guild_rosters.values():
        for unit in roster or []:
            def_id = unit.get("defId") or unit.get("baseId") or unit.get("definitionId")
            name = unit.get("name") or _lookup_unit_name(def_id)
            _add_unit_name_reverse(index, name, def_id)
    _unit_name_reverse_index = index
    return index


def _resolve_unit_name_to_defid(name):
    raw = _canonical_defid(name)
    raw_key = _canonical_defid_key(raw)
    if raw_key in _KNOWN_SHIP_DEFIDS or raw_key in _KNOWN_CHARACTER_DEFIDS:
        return raw
    alias_match = _UNIT_NAME_ALIASES.get(_normalize_unit_name_lookup(name))
    if alias_match:
        return _canonical_defid(alias_match)
    index = _unit_name_reverse_index or _rebuild_unit_name_reverse_index()
    match = index.get(_normalize_unit_name_lookup(name))
    if isinstance(match, list):
        return match[0] if len(match) == 1 else ""
    return match or ""


def _placeholder_ops_defid(name):
    clean = _normalize_unit_name_lookup(name).upper()
    return f"WIKI_{clean}" if clean else "WIKI_UNKNOWN"


def _is_ship_name_or_defid(name="", def_id=""):
    key = _canonical_defid_key(def_id or name)
    if key in _KNOWN_SHIP_DEFIDS:
        return True
    if key in _KNOWN_CHARACTER_DEFIDS:
        return False
    clean_name = _normalize_unit_name_lookup(name)
    if not clean_name:
        return False
    return any(_normalize_unit_name_lookup(ship_name) == clean_name for ship_name in _SHIP_NAME_MAP.values())


def _build_hardcoded_tb_defs():
    global _tb_defs_fallback_cache
    if _tb_defs_fallback_cache is not None:
        return _tb_defs_fallback_cache
    if _build_wiki_tb_defs_from_module is None:
        _tb_defs_fallback_cache = {}
        return _tb_defs_fallback_cache
    _tb_defs_fallback_cache = _build_wiki_tb_defs_from_module(
        _resolve_unit_name_to_defid,
        _placeholder_ops_defid,
        _is_ship_name_or_defid,
    )
    if _tb_defs_fallback_cache:
        print("  Using built-in wiki operations fallback definitions.")
    return _tb_defs_fallback_cache


def _infer_combat_type(def_id, raw_ctype=None):
    key = _canonical_defid_key(def_id)
    if key in _KNOWN_SHIP_DEFIDS:
        return 2
    if key in _KNOWN_CHARACTER_DEFIDS:
        return 1
    if raw_ctype is not None and str(raw_ctype).strip() != "":
        raw = str(raw_ctype).strip().upper()
        if raw in ("2", "SHIP", "FLEET"):
            return 2
        if raw in ("1", "CHARACTER", "UNIT"):
            return 1
        if str(raw_ctype).isdigit():
            return 2 if int(raw_ctype) == 2 else 1
    return 1


def _normalize_loc_key(value):
    return str(value or "").strip().upper()


def _cache_name_maps():
    try:
        if _unit_name_map:
            (COMLINK_DIR / "unit_names.json").write_text(
                json.dumps(_unit_name_map, indent=2), encoding="utf-8"
            )
    except Exception:
        pass
    try:
        if _ability_name_map:
            (COMLINK_DIR / "ability_names.json").write_text(
                json.dumps(_ability_name_map, indent=2), encoding="utf-8"
            )
    except Exception:
        pass
    try:
        if _skill_meta_map:
            (COMLINK_DIR / "skill_meta.json").write_text(
                json.dumps(_skill_meta_map, indent=2), encoding="utf-8"
            )
    except Exception:
        pass
    try:
        if _unit_skill_reference_map:
            (COMLINK_DIR / "unit_skill_refs.json").write_text(
                json.dumps(_unit_skill_reference_map, indent=2), encoding="utf-8"
            )
    except Exception:
        pass
    try:
        if _unit_crew_map:
            (COMLINK_DIR / "unit_crew_map.json").write_text(
                json.dumps(_unit_crew_map, indent=2), encoding="utf-8"
            )
    except Exception:
        pass
    try:
        if _unit_crew_skill_reference_map:
            (COMLINK_DIR / "unit_crew_skill_refs.json").write_text(
                json.dumps(_unit_crew_skill_reference_map, indent=2), encoding="utf-8"
            )
    except Exception:
        pass


def _load_cached_name_maps():
    changed = False
    try:
        unit_file = COMLINK_DIR / "unit_names.json"
        if unit_file.exists() and not _unit_name_map:
            data = json.loads(unit_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                _unit_name_map.update(data)
                changed = True
    except Exception:
        pass
    try:
        ability_file = COMLINK_DIR / "ability_names.json"
        if ability_file.exists() and not _ability_name_map:
            data = json.loads(ability_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                _ability_name_map.update(data)
                changed = True
    except Exception:
        pass
    try:
        skill_meta_file = COMLINK_DIR / "skill_meta.json"
        if skill_meta_file.exists() and not _skill_meta_map:
            data = json.loads(skill_meta_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                _skill_meta_map.update({
                    _normalize_loc_key(skill_id): _normalize_skill_meta_entry(meta)
                    for skill_id, meta in data.items()
                })
                changed = True
    except Exception:
        pass
    try:
        skill_ref_file = COMLINK_DIR / "unit_skill_refs.json"
        if skill_ref_file.exists() and not _unit_skill_reference_map:
            data = json.loads(skill_ref_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                _unit_skill_reference_map.update(data)
                changed = True
    except Exception:
        pass
    try:
        crew_map_file = COMLINK_DIR / "unit_crew_map.json"
        if crew_map_file.exists() and not _unit_crew_map:
            data = json.loads(crew_map_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                _unit_crew_map.update(data)
                changed = True
    except Exception:
        pass
    try:
        crew_skill_ref_file = COMLINK_DIR / "unit_crew_skill_refs.json"
        if crew_skill_ref_file.exists() and not _unit_crew_skill_reference_map:
            data = json.loads(crew_skill_ref_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                _unit_crew_skill_reference_map.update(data)
                changed = True
    except Exception:
        pass
    return changed


def _merge_localization_bundle(loc_data):
    added_units = 0
    added_abilities = 0
    if not isinstance(loc_data, dict):
        return added_units, added_abilities
    for key, value in loc_data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        display = value.strip()
        if not display:
            continue
        key_up = _normalize_loc_key(key)
        _localization_value_map[key_up] = display
        if key_up.startswith("UNIT_") and key_up.endswith("_NAME"):
            defid = key_up[5:-5]
            if defid and defid not in _unit_name_map:
                _unit_name_map[defid] = display
                added_units += 1
            continue
        if key_up.endswith("_NAME"):
            ability_id = key_up[:-5]
            if ability_id and ability_id not in _ability_name_map:
                _ability_name_map[ability_id] = display
                added_abilities += 1
    return added_units, added_abilities


def _parse_localization_text(loc_text):
    loc_map = {}
    if not isinstance(loc_text, str):
        return loc_map
    for raw_line in loc_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        key, value = line.split("|", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            loc_map[key] = value
    return loc_map


def _extract_localization_bundle(loc_payload):
    if not isinstance(loc_payload, dict):
        return {}
    bundle = loc_payload.get("localizationBundle")
    if isinstance(bundle, dict) and bundle:
        return bundle
    if isinstance(bundle, str) and bundle.strip():
        try:
            raw = base64.b64decode(bundle)
        except Exception:
            raw = bundle.encode("utf-8", errors="ignore")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                target = next((name for name in zf.namelist() if name.upper().endswith("LOC_ENG_US.TXT")), None)
                if not target and zf.namelist():
                    target = zf.namelist()[0]
                if target:
                    return _parse_localization_text(zf.read(target).decode("utf-8", errors="replace"))
        except Exception:
            pass
        try:
            return _parse_localization_text(raw.decode("utf-8", errors="replace"))
        except Exception:
            return {}
    return loc_payload if isinstance(loc_payload, dict) else {}


def _lookup_localized_text(key, fallback=""):
    normalized = _normalize_loc_key(key)
    if not normalized:
        return fallback or ""
    return (_localization_value_map.get(normalized)
            or _localization_value_map.get(normalized.replace("_", ""))
            or fallback
            or "")


def _store_ability_name_map_entry(raw_id, display_name):
    key = _normalize_loc_key(raw_id)
    if not key or not display_name:
        return False
    changed = False
    for candidate in (raw_id, key, key.replace("_", "")):
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        if _ability_name_map.get(normalized) != display_name:
            _ability_name_map[normalized] = display_name
            changed = True
    return changed


def _extract_skill_ids(skill_refs, first_only=False):
    out = []
    seen = set()
    refs = skill_refs or []
    if first_only and refs:
        refs = refs[:1]
    for entry in refs:
        if isinstance(entry, dict):
            skill_id = str(entry.get("skillId") or entry.get("id") or entry.get("abilityId") or "").strip()
        else:
            skill_id = str(entry or "").strip()
        if not skill_id:
            continue
        skill_key = _normalize_loc_key(skill_id)
        if skill_key in seen:
            continue
        seen.add(skill_key)
        out.append(skill_id)
    return out


def _skill_row_from_meta(skill_id, raw_tier=0, unlocked=False):
    meta = _normalize_skill_meta_entry(_skill_meta_map.get(_normalize_loc_key(skill_id), {}))
    try:
        roster_tier = int(raw_tier)
    except Exception:
        roster_tier = 0
    level = _skill_level_from_tier(roster_tier, meta.get("maxTier"))
    zeta_tiers = set(meta.get("zetaTiers") or [])
    omicron_tiers = set(meta.get("omicronTiers") or [])
    is_zeta_skill = bool(meta.get("isZeta"))
    is_omicron_skill = bool(meta.get("isOmicron"))
    # Live roster tiers from Comlink land one step below the cached skillDefinition markers.
    # Example: a zeta marker at 7 is represented as raw roster tier 6 once unlocked.
    has_zeta = any((tier_idx - 1) <= roster_tier for tier_idx in zeta_tiers)
    has_omicron = any((tier_idx - 1) <= roster_tier for tier_idx in omicron_tiers)

    return {
        "id": skill_id,
        "skillId": skill_id,
        "name": _lookup_ability_name(skill_id),
        "tier": roster_tier,
        "level": level,
        "maxTier": int(meta.get("maxTier") or 0),
        "kind": meta.get("kind") or _infer_skill_kind(skill_id),
        "isZeta": is_zeta_skill,
        "isOmicron": is_omicron_skill,
        "omicronArea": int(meta.get("omicronArea") or 0),
        # Comlink rosterUnit.skill.tier lines up with the tier markers we cache from skillDefinition.
        "hasZeta": has_zeta,
        "hasOmicron": has_omicron,
        "unlocked": bool(unlocked),
    }


def _collect_unit_skill_ids(def_id, combat_type=1):
    base_key = _normalize_loc_key(def_id)
    ordered = []
    seen = set()

    def _push(skill_ids):
        for skill_id in skill_ids or []:
            skill_id = str(skill_id or "").strip()
            if not skill_id:
                continue
            skill_key = _normalize_loc_key(skill_id)
            if skill_key in seen:
                continue
            seen.add(skill_key)
            ordered.append(skill_id)

    _push(_unit_skill_reference_map.get(base_key, []))
    if int(combat_type or 1) == 2:
        crew_skills = _unit_crew_skill_reference_map.get(base_key, [])
        if crew_skills:
            _push(crew_skills)
        else:
            for crew_unit_id in _unit_crew_map.get(base_key, []):
                _push((_unit_skill_reference_map.get(_normalize_loc_key(crew_unit_id), []) or [])[:1])
    return ordered


def _build_guide_tb_omicron_map():
    _ensure_localization_maps(force=not (_skill_meta_map and _unit_skill_reference_map))
    result = {}
    tb_omicron_area = 7
    for unit_id in sorted(_unit_skill_reference_map.keys()):
        if _infer_combat_type(unit_id, raw_ctype=1) != 1:
            continue
        seen = set()
        skills = []
        for skill_id in _collect_unit_skill_ids(unit_id, combat_type=1):
            skill_key = _normalize_loc_key(skill_id)
            if skill_key in seen:
                continue
            seen.add(skill_key)
            meta = _normalize_skill_meta_entry(_skill_meta_map.get(skill_key, {}))
            if not meta.get("isOmicron"):
                continue
            if int(meta.get("omicronArea") or 0) != tb_omicron_area:
                continue
            skills.append({
                "skillId": skill_id,
                "name": _lookup_ability_name(skill_id, skill_id),
                "kind": meta.get("kind") or _infer_skill_kind(skill_id),
                "omicronArea": tb_omicron_area,
            })
        if skills:
            result[_normalize_loc_key(unit_id)] = skills
    return result


def _populate_gamedata_name_maps(version):
    global _skill_meta_map, _unit_skill_reference_map, _unit_crew_map, _unit_crew_skill_reference_map
    if not version:
        return False
    changed = False
    try:
        skill_data = _comlink_post("data", payload={"version": version, "includePveUnits": False, "requestSegment": 1}, timeout=45)
        ability_data = _comlink_post("data", payload={"version": version, "includePveUnits": False, "requestSegment": 2}, timeout=45)
        unit_data = _comlink_post("data", payload={"version": version, "includePveUnits": False, "requestSegment": 3}, timeout=45)
    except Exception:
        return False

    ability_name_by_id = {}
    for ability in (ability_data.get("ability") or []):
        if not isinstance(ability, dict):
            continue
        ability_id = str(ability.get("id") or "").strip()
        name = _lookup_localized_text(ability.get("nameKey"))
        if not ability_id or not name:
            continue
        ability_key = _normalize_loc_key(ability_id)
        ability_name_by_id[ability_key] = name
        changed = _store_ability_name_map_entry(ability_key, name) or changed

    for skill in (skill_data.get("skill") or []):
        if not isinstance(skill, dict):
            continue
        skill_id = str(skill.get("id") or "").strip()
        ability_ref = str(skill.get("abilityReference") or "").strip()
        name = ""
        if ability_ref:
            name = ability_name_by_id.get(_normalize_loc_key(ability_ref), "")
        if not name:
            name = _lookup_localized_text(skill.get("nameKey"))
        if skill_id and name:
            changed = _store_ability_name_map_entry(skill_id, name) or changed
        if skill_id:
            tier_rows = skill.get("tier") or []
            zeta_tiers = []
            omicron_tiers = []
            for idx, tier_row in enumerate(tier_rows, start=1):
                if not isinstance(tier_row, dict):
                    continue
                if tier_row.get("isZetaTier"):
                    zeta_tiers.append(idx)
                if tier_row.get("isOmicronTier"):
                    omicron_tiers.append(idx)
            _skill_meta_map[_normalize_loc_key(skill_id)] = _normalize_skill_meta_entry({
                "maxTier": (len(tier_rows) + 1) if isinstance(tier_rows, list) else 0,
                "isZeta": bool(skill.get("isZeta")),
                "isOmicron": bool(skill.get("omicronMode")),
                "omicronArea": int(skill.get("omicronMode") or 0),
                "kind": _infer_skill_kind(skill_id),
                "zetaTiers": zeta_tiers,
                "omicronTiers": omicron_tiers,
            })

    for unit in (unit_data.get("units") or []):
        if not isinstance(unit, dict):
            continue
        base_id = _normalize_loc_key(unit.get("baseId") or unit.get("id") or "")
        name = _lookup_localized_text(unit.get("nameKey"))
        if base_id and name and _unit_name_map.get(base_id) != name:
            _unit_name_map[base_id] = name
            changed = True
        if base_id:
            _unit_skill_reference_map[base_id] = _extract_skill_ids(unit.get("skillReference") or [])
            crew_unit_ids = []
            crew_skill_ids = []
            for crew_entry in (unit.get("crew") or []):
                if not isinstance(crew_entry, dict):
                    continue
                crew_unit_id = str(crew_entry.get("unitId") or "").strip()
                if crew_unit_id:
                    crew_unit_ids.append(_normalize_loc_key(crew_unit_id))
                crew_skill_ids.extend(_extract_skill_ids(crew_entry.get("skillReference") or [], first_only=True))
            _unit_crew_map[base_id] = crew_unit_ids
            _unit_crew_skill_reference_map[base_id] = crew_skill_ids

    return changed


def _ensure_localization_maps(force=False):
    global _localization_maps_attempted
    _load_cached_name_maps()
    if _localization_maps_attempted and not force:
        return
    if _unit_name_map and _ability_name_map and _skill_meta_map and _unit_skill_reference_map and not force:
        _localization_maps_attempted = True
        return

    bundle_id = ""
    game_version = ""
    try:
        meta = _comlink_post("metadata", timeout=10)
        if isinstance(meta, dict):
            bundle_id = str(meta.get("latestLocalizationBundleVersion") or "").strip()
            game_version = str(meta.get("latestGamedataVersion") or "").strip()
    except Exception:
        bundle_id = ""
        game_version = ""

    payloads = []
    if bundle_id:
        payloads.append({"id": bundle_id})
    payloads.extend([
        {"id": "Loc_ENG_US.txt", "unzip": True},
        {"id": "Loc_ENG_US.txt"},
        {"language": "ENG_US"},
        {},
    ])
    for payload in payloads:
        try:
            loc = _comlink_post("localization", payload=payload, timeout=10)
        except Exception:
            continue
        loc_data = _extract_localization_bundle(loc)
        unit_added, ability_added = _merge_localization_bundle(loc_data)
        if unit_added or ability_added:
            break

    if _localization_value_map and game_version:
        _populate_gamedata_name_maps(game_version)

    if _unit_name_map or _ability_name_map:
        _cache_name_maps()
    _localization_maps_attempted = True


def _infer_skill_kind(skill_id):
    raw = str(skill_id or "").strip().lower()
    if raw.startswith("basicskill"):
        return "basic"
    if raw.startswith("specialskill"):
        return "special"
    if raw.startswith("leaderskill"):
        return "leader"
    if raw.startswith("uniqueskill"):
        return "unique"
    if raw.startswith("contract"):
        return "contract"
    if raw.startswith("crew"):
        return "crew"
    if raw.startswith("hardware"):
        return "hardware"
    if raw.startswith("ultimateability"):
        return "ultimate"
    return "ability"


def _fallback_ability_name(skill_id):
    kind = _infer_skill_kind(skill_id)
    return {
        "basic": "Basic",
        "special": "Special",
        "leader": "Leader",
        "unique": "Unique",
        "contract": "Contract",
        "crew": "Crew",
        "hardware": "Hardware",
        "ultimate": "Ultimate",
    }.get(kind, "Ability")


def _lookup_ability_name(skill_id, fallback=""):
    raw = str(skill_id or "").strip()
    upper = _normalize_loc_key(raw)
    flat = upper.replace("_", "")
    candidates = [raw, upper, flat]

    def _extend_with(prefix, suffix):
        clean_suffix = _normalize_loc_key(suffix)
        if not clean_suffix:
            return
        candidates.extend([
            f"{prefix}_{clean_suffix}",
            f"{prefix}_{clean_suffix}_NAME",
            f"{prefix}{clean_suffix}",
            f"{prefix}{clean_suffix}_NAME",
        ])

    lower = raw.lower()
    if lower.startswith("basicskill_"):
        _extend_with("BASICABILITY", raw[len("basicskill_"):])
    elif lower.startswith("specialskill_"):
        _extend_with("SPECIALABILITY", raw[len("specialskill_"):])
    elif lower.startswith("leaderskill_"):
        _extend_with("LEADERABILITY", raw[len("leaderskill_"):])
    elif lower.startswith("uniqueskill_"):
        _extend_with("UNIQUEABILITY", raw[len("uniqueskill_"):])
    elif lower.startswith("contractskill_"):
        suffix = raw[len("contractskill_"):]
        _extend_with("CONTRACTABILITY", suffix)
        _extend_with("PAYOUTABILITY", suffix)
        _extend_with("CONTRACT", suffix)
    elif lower.startswith("crew_"):
        _extend_with("CREWABILITY", raw[len("crew_"):])
    elif lower.startswith("hardware_"):
        _extend_with("HARDWAREABILITY", raw[len("hardware_"):])
    elif lower.startswith("ultimateability_"):
        _extend_with("ULTIMATEABILITY", raw[len("ultimateability_"):])

    seen = set()
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        value = (_ability_name_map.get(candidate)
                 or _ability_name_map.get(_normalize_loc_key(candidate))
                 or _ability_name_map.get(_normalize_loc_key(candidate).replace("_", "")))
        if value:
            return value
    return fallback or ""


def _skill_level_from_tier(raw_tier, max_tier=0):
    try:
        tier = int(raw_tier)
    except Exception:
        return 0
    try:
        max_tier = int(max_tier or 0)
    except Exception:
        max_tier = 0
    if max_tier > 0 and max_tier <= 3:
        if tier <= 0:
            return 2
        return min(max_tier, tier + 2)
    return tier + 2 if tier > 0 else 0


def _normalize_skill_meta_entry(entry):
    if not isinstance(entry, dict):
        entry = {}

    def _clean_tiers(values):
        cleaned = []
        seen = set()
        for value in values or []:
            try:
                tier = int(value)
            except Exception:
                continue
            if tier <= 0 or tier in seen:
                continue
            seen.add(tier)
            cleaned.append(tier)
        return sorted(cleaned)

    zeta_tiers = _clean_tiers(entry.get("zetaTiers"))
    omicron_tiers = _clean_tiers(entry.get("omicronTiers"))
    try:
        omicron_area = int(entry.get("omicronArea") or 0)
    except Exception:
        omicron_area = 0

    return {
        "maxTier": int(entry.get("maxTier") or 0),
        "isZeta": bool(entry.get("isZeta")) or bool(zeta_tiers),
        # omicronMode=1 appears on many non-omicron skills in cached live data,
        # so the actual omicron tier markers are the reliable signal here.
        "isOmicron": bool(omicron_tiers),
        "omicronArea": omicron_area if omicron_tiers else 0,
        "kind": entry.get("kind") or "",
        "zetaTiers": zeta_tiers,
        "omicronTiers": omicron_tiers,
    }


def _hydrate_skill_names_in_rosters(rosters):
    changed = False
    if not isinstance(rosters, dict) or not rosters:
        return changed
    _ensure_localization_maps()
    if not _ability_name_map and not _unit_name_map:
        return changed
    for roster in rosters.values():
        if not isinstance(roster, list):
            continue
        for unit in roster:
            if not isinstance(unit, dict):
                continue
            def_id = unit.get("defId") or unit.get("baseId") or unit.get("definitionId") or ""
            combat_type = unit.get("combatType") or _infer_combat_type(def_id)
            if not str(unit.get("name") or "").strip():
                display_name = _lookup_unit_name(def_id)
                if display_name:
                    unit["name"] = display_name
                    changed = True
            current_skills = unit.get("skills") or []
            if _skill_meta_map and _unit_skill_reference_map:
                expanded_skills = _simplify_skills(unit, def_id=def_id, combat_type=combat_type)
                needs_refresh = len(expanded_skills) != len(current_skills)
                if not needs_refresh and expanded_skills:
                    for idx, skill in enumerate(expanded_skills):
                        current = current_skills[idx] if idx < len(current_skills) and isinstance(current_skills[idx], dict) else {}
                        if (
                            current.get("name") != skill.get("name")
                            or current.get("level") != skill.get("level")
                            or current.get("maxTier") != skill.get("maxTier")
                            or current.get("hasZeta") != skill.get("hasZeta")
                            or current.get("hasOmicron") != skill.get("hasOmicron")
                        ):
                            needs_refresh = True
                            break
                if needs_refresh and expanded_skills:
                    unit["skills"] = expanded_skills
                    current_skills = expanded_skills
                    changed = True
                if current_skills:
                    zetas = sum(1 for skill in current_skills if isinstance(skill, dict) and skill.get("hasZeta"))
                    omicrons = sum(1 for skill in current_skills if isinstance(skill, dict) and skill.get("hasOmicron"))
                    if unit.get("zetas") != zetas:
                        unit["zetas"] = zetas
                        changed = True
                    if unit.get("omicrons") != omicrons:
                        unit["omicrons"] = omicrons
                        changed = True
            for skill in current_skills:
                if not isinstance(skill, dict):
                    continue
                if str(skill.get("name") or "").strip():
                    continue
                skill_id = str(skill.get("id") or skill.get("skillId") or skill.get("abilityId") or "").strip()
                if not skill_id:
                    continue
                ability_name = _lookup_ability_name(skill_id)
                if ability_name:
                    skill["name"] = ability_name
                    changed = True
    return changed


def _simplify_skills(unit, def_id="", combat_type=1):
    roster_skill_tiers = {}
    purchased_skill_ids = []
    for skill in (unit.get("skill") or unit.get("skills") or []):
        if not isinstance(skill, dict):
            continue
        skill_id = str(skill.get("id") or skill.get("skillId") or skill.get("abilityId") or "").strip()
        if not skill_id:
            continue
        try:
            roster_skill_tiers[_normalize_loc_key(skill_id)] = int(skill.get("tier") or 0)
        except Exception:
            roster_skill_tiers[_normalize_loc_key(skill_id)] = 0

    seen = set()
    skills = []

    def _push_skill(skill_id, raw_tier=0, unlocked=False):
        skill_id = str(skill_id or "").strip()
        if not skill_id:
            return
        skill_key = _normalize_loc_key(skill_id)
        if skill_key in seen:
            return
        seen.add(skill_key)
        row = _skill_row_from_meta(skill_id, raw_tier=raw_tier, unlocked=unlocked)
        if not row.get("name"):
            row["name"] = _fallback_ability_name(skill_id)
        skills.append(row)

    for skill_id in _collect_unit_skill_ids(def_id, combat_type):
        _push_skill(skill_id, raw_tier=roster_skill_tiers.get(_normalize_loc_key(skill_id), 1))

    for skill_key, raw_tier in roster_skill_tiers.items():
        if skill_key in seen:
            continue
        source_id = next(
            (str(skill.get("id") or skill.get("skillId") or skill.get("abilityId") or "").strip()
             for skill in (unit.get("skill") or unit.get("skills") or [])
             if _normalize_loc_key(skill.get("id") or skill.get("skillId") or skill.get("abilityId")) == skill_key),
            skill_key,
        )
        _push_skill(source_id, raw_tier=raw_tier)

    for skill_id in (unit.get("purchasedAbilityId") or []):
        skill_id = str(skill_id or "").strip()
        if not skill_id:
            continue
        purchased_skill_ids.append(skill_id)
        _push_skill(skill_id, raw_tier=0, unlocked=True)

    return skills

def _sanitize_persisted_app_state(state):
    if not isinstance(state, dict):
        return {}, False
    sanitized = dict(state)
    changed = False
    for key in _VOLATILE_APP_STATE_KEYS:
        if key in sanitized:
            sanitized.pop(key, None)
            changed = True
    return sanitized, changed

def _load_app_state():
    try:
        if APP_STATE_FILE.exists():
            data = json.loads(APP_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data, changed = _sanitize_persisted_app_state(data)
                if _hydrate_skill_names_in_rosters(data.get("guildRosters")):
                    changed = True
                if changed:
                    try:
                        APP_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                return data
    except Exception:
        pass
    return {}

def _save_app_state(state):
    try:
        state, _ = _sanitize_persisted_app_state(state)
        APP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        APP_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

_PLANET_NAME_MAP = {
    "mustafar":"mustafar","corellia":"corellia","coruscant":"coruscant",
    "geonosis":"geonosis","felucia":"felucia","bracca":"bracca",
    "dathomir":"dathomir","tatooine":"tatooine","kashyyyk":"kashyyyk",
    "zeffo":"zeffo","medical":"medstation","haven":"medstation",
    "hcms":"medstation","kessel":"kessel","lothal":"lothal",
    "mandalore":"mandalore","malachor":"malachor","vandor":"vandor",
    "kafrene":"kafrene","death":"deathstar","hoth":"hoth","scarif":"scarif",
}
_POSITIONAL = [
    ["mustafar","corellia","coruscant"],
    ["geonosis","felucia","bracca"],
    ["dathomir","tatooine","kashyyyk","zeffo"],
    ["medstation","kessel","lothal","mandalore"],
    ["malachor","vandor","kafrene"],
    ["deathstar","hoth","scarif"],
]
_GAME_DATA_ITEMS_GUILD_DEFINITIONS = 536870912
_GAME_DATA_ITEMS_UNITS = 137438953472


def _map_territory(raw_id, ph, te):
    r = raw_id.lower()
    for pat, pid in _PLANET_NAME_MAP.items():
        if pat in r:
            return pid
    if ph < len(_POSITIONAL) and te < len(_POSITIONAL[ph]):
        return _POSITIONAL[ph][te]
    return f"ph{ph}_te{te}"


def _extract_tb_list_from_game_data(resp):
    best_list = None
    best_path = ""
    stack = [("root", resp)]
    seen = set()
    while stack:
        path, node = stack.pop()
        node_id = id(node)
        if node_id in seen:
            continue
        seen.add(node_id)
        if isinstance(node, dict):
            for key, value in node.items():
                next_path = f"{path}.{key}"
                key_l = str(key).lower()
                if isinstance(value, list):
                    if ("territorybattle" in key_l or "territory_battle" in key_l) and "definition" in key_l:
                        return value, next_path
                    sample = [item for item in value[:5] if isinstance(item, dict)]
                    if sample and any(("phase" in item or "phases" in item) for item in sample):
                        best_list = value
                        best_path = next_path
                if isinstance(value, (dict, list)):
                    stack.append((next_path, value))
        elif isinstance(node, list):
            sample = [item for item in node[:5] if isinstance(item, dict)]
            if sample and any(("phase" in item or "phases" in item) for item in sample):
                best_list = node
                best_path = path
            for idx, item in enumerate(node):
                if isinstance(item, (dict, list)):
                    stack.append((f"{path}[{idx}]", item))
    return best_list, best_path


def _identify_rote_tb(tb_list):
    if not isinstance(tb_list, list):
        return None
    for tb in tb_list:
        if not isinstance(tb, dict):
            continue
        tid = str(tb.get("id", "")).upper()
        tkey = str(tb.get("nameKey", "") or tb.get("name", "")).upper()
        if tid in ("T05D", "T05", "TB05", "TB_05"):
            print(f"  ROTE identified by id: {tb.get('id', '?')}")
            return tb
        if any(k in tid or k in tkey for k in
               ["ROTE", "RISE_OF", "RISEOF", "EMPIRE_TB", "TB_ROTE", "TB05", "TB_05", "TB_5"]):
            print(f"  ROTE identified by name: {tb.get('id', '?')}")
            return tb
    for tb in tb_list:
        if isinstance(tb, dict):
            phases = tb.get("phase", []) or tb.get("phases", [])
            if len(phases) == 6:
                print(f"  ROTE identified by 6 phases: {tb.get('id', '?')}")
                return tb
    return None


def _extract_ops_default_relic(node, inherited=0):
    if not isinstance(node, dict):
        return inherited
    for key in ("unitRelicTier", "requiredRelicTier", "minimumRelicTier", "minRelic"):
        value = node.get(key)
        if value is None or value == "":
            continue
        try:
            raw = int(value)
            return max(0, raw - 2) if raw >= 3 else max(0, raw)
        except Exception:
            continue
    return inherited


def _looks_like_unit_requirement(node):
    if not isinstance(node, dict):
        return False
    if node.get("unitDefId") or node.get("baseId") or node.get("unitId"):
        return True
    if node.get("defId") and any(k in node for k in ("requiredRarity", "requiredRelicTier", "rarity", "relicTier", "minRelic")):
        return True
    if node.get("definitionId") and any(k in node for k in ("requiredRarity", "requiredRelicTier", "rarity", "relicTier", "minRelic")):
        return True
    if node.get("id") and any(k in node for k in ("requiredRarity", "requiredRelicTier", "rarity", "relicTier", "minRelic", "unitTier")):
        return True
    return False


def _flatten_ops_unit_slots(node, inherited_relic=0):
    if isinstance(node, list):
        slots = []
        for item in node:
            slots.extend(_flatten_ops_unit_slots(item, inherited_relic))
        return slots
    if not isinstance(node, dict):
        return []

    local_relic = _extract_ops_default_relic(node, inherited_relic)
    if _looks_like_unit_requirement(node):
        def_id = (node.get("unitDefId") or node.get("baseId") or node.get("unitId")
                  or node.get("defId") or node.get("definitionId") or node.get("id", ""))
        min_rarity = int(node.get("requiredRarity")
                         or node.get("minRarity")
                         or node.get("rarity")
                         or 7)
        relic_raw = node.get("requiredRelicTier")
        if relic_raw is None:
            relic_raw = (node.get("minimumRelicTier") or node.get("minRelic")
                         or node.get("relicTier") or node.get("relic")
                         or local_relic)
        try:
            relic_raw = int(relic_raw)
        except Exception:
            relic_raw = local_relic
        min_relic = max(0, relic_raw - 2) if relic_raw >= 3 else max(0, relic_raw)
        if def_id:
            return [{
                "defId": _canonical_defid(def_id),
                "minRarity": min_rarity,
                "minRelic": min_relic
            }]

    slots = []
    for value in node.values():
        if isinstance(value, (dict, list)):
            slots.extend(_flatten_ops_unit_slots(value, local_relic))
    return slots


def _extract_platoons_from_candidate_list(items, inherited_relic=0):
    if not isinstance(items, list) or not items:
        return []
    item_slots = [_flatten_ops_unit_slots(item, inherited_relic) for item in items]
    non_empty = [slots for slots in item_slots if slots]
    if not non_empty:
        return []

    if 1 <= len(items) <= 6 and all(5 <= len(slots) <= 30 for slots in non_empty) and len(non_empty) == len(items):
        return non_empty

    total_slots = []
    for slots in non_empty:
        total_slots.extend(slots)
    if 10 <= len(total_slots) <= 20:
        return [total_slots]
    return []


def _find_ops_platoon_sets(node, inherited_relic=0):
    found = []
    if isinstance(node, list):
        candidate = _extract_platoons_from_candidate_list(node, inherited_relic)
        if candidate:
            found.append(candidate)
        for item in node:
            found.extend(_find_ops_platoon_sets(item, inherited_relic))
        return found

    if not isinstance(node, dict):
        return found

    local_relic = _extract_ops_default_relic(node, inherited_relic)
    for value in node.values():
        if isinstance(value, (dict, list)):
            found.extend(_find_ops_platoon_sets(value, local_relic))
    return found


def _build_conflict_zone_planet_map(rote):
    zone_map = {}
    for key in ("conflictZoneDefinition", "bonusZoneDefinition"):
        for zone in rote.get(key, []) or []:
            zone_def = zone.get("zoneDefinition") if isinstance(zone, dict) else None
            zone_def = zone_def if isinstance(zone_def, dict) else (zone if isinstance(zone, dict) else {})
            raw_values = [
                zone_def.get("zoneId"),
                zone_def.get("id"),
                zone_def.get("linkedConflictId"),
                zone_def.get("prefabName"),
                zone_def.get("nameKey"),
                zone.get("id") if isinstance(zone, dict) else None,
            ]
            raw_values = [str(v).strip() for v in raw_values if str(v or "").strip()]
            if not raw_values:
                continue
            pid = None
            for raw in raw_values:
                mapped = _map_territory(raw, 0, 0)
                if not mapped.startswith("ph0_"):
                    pid = mapped
                    break
            if not pid:
                continue
            for raw in raw_values:
                zone_map[str(raw).lower()] = pid
    return zone_map


def _parse_tb_defs_from_recon_zones(rote):
    result = {}
    zone_map = _build_conflict_zone_planet_map(rote)
    recon_zones = rote.get("reconZoneDefinition", []) or []
    for recon in recon_zones:
        if not isinstance(recon, dict):
            continue
        zone_def = recon.get("zoneDefinition") if isinstance(recon.get("zoneDefinition"), dict) else {}
        raw_refs = [
            zone_def.get("linkedConflictId"),
            zone_def.get("zoneId"),
            zone_def.get("prefabName"),
            zone_def.get("nameKey"),
            recon.get("id"),
        ]
        raw_refs = [str(v).strip() for v in raw_refs if str(v or "").strip()]
        planet_id = None
        for raw in raw_refs:
            lowered = raw.lower()
            if lowered in zone_map:
                planet_id = zone_map[lowered]
                break
            mapped = _map_territory(raw, 0, 0)
            if not mapped.startswith("ph0_"):
                planet_id = mapped
                break
        if not planet_id:
            continue

        platoon_sets = _find_ops_platoon_sets(recon, _extract_ops_default_relic(recon, 0))
        if not platoon_sets:
            continue
        platoon_sets.sort(key=lambda set_list: (len(set_list) == 6, len(set_list), sum(len(p) for p in set_list)), reverse=True)
        chosen = platoon_sets[0]
        if len(chosen) >= 6:
            chosen = chosen[:6]
        if chosen:
            result[planet_id] = chosen
    return result


def _parse_tb_defs_from_rote(rote):
    result = {}
    phases = rote.get("phase", []) or rote.get("phases", [])
    for ph_i, phase in enumerate(phases):
        territories = phase.get("territory", []) or phase.get("territories", [])
        for te_i, territory in enumerate(territories):
            raw_id = (str(territory.get("id", ""))
                      or str(territory.get("definitionId", ""))
                      or str(territory.get("nameKey", ""))).lower()
            planet_id = _map_territory(raw_id, ph_i, te_i)

            ops = (territory.get("operation", [])
                   or territory.get("operations", [])
                   or territory.get("platoon", [])
                   or territory.get("squad", [])
                   or [])

            planet_platoons = []
            for op in ops:
                squads = (op.get("squad", []) or op.get("squads", [])
                          or op.get("platoon", []) or op.get("unit", []) or [])
                slots = []
                for squad in squads:
                    units = (squad.get("unit", []) or squad.get("units", [])
                             or squad.get("platoonUnit", []) or [])
                    if not units and (squad.get("unitDefId") or squad.get("baseId")
                                      or squad.get("defId") or squad.get("definitionId")):
                        units = [squad]
                    for unit in units:
                        def_id = (unit.get("unitDefId") or unit.get("baseId")
                                  or unit.get("defId") or unit.get("definitionId")
                                  or unit.get("id", ""))
                        min_rarity = int(unit.get("requiredRarity")
                                         or unit.get("minRarity")
                                         or unit.get("rarity") or 7)
                        relic_raw = int(unit.get("requiredRelicTier")
                                        or unit.get("minimumRelicTier")
                                        or unit.get("minRelic")
                                        or unit.get("relicTier")
                                        or unit.get("relic") or 0)
                        min_relic = max(0, relic_raw - 2) if relic_raw >= 3 else max(0, relic_raw)
                        if def_id:
                            slots.append({
                                "defId": _canonical_defid(def_id),
                                "minRarity": min_rarity,
                                "minRelic": min_relic
                            })
                if slots:
                    planet_platoons.append(slots)

            if planet_platoons:
                result[planet_id] = planet_platoons
    if result:
        return result
    return _parse_tb_defs_from_recon_zones(rote)


def _fetch_tb_defs():
    """Load cached ROTE platoon requirements from the bundled wiki dataset."""
    global _tb_defs_cache, _tb_defs_source
    if _tb_defs_cache is not None:
        return _tb_defs_cache
    with _tb_defs_lock:
        if _tb_defs_cache is not None:
            return _tb_defs_cache

        try:
            _tb_defs_cache = _build_hardcoded_tb_defs() or {}
            _tb_defs_source = "bundled-wiki"
            if _tb_defs_cache:
                print("  Using built-in wiki operations definitions.")
            else:
                print("  Built-in ROTE platoon definitions are unavailable.")
            return _tb_defs_cache
        except Exception as fallback_exc:
            print(f"  Built-in TB definitions load error: {fallback_exc}")
            _tb_defs_cache = {}
            _tb_defs_source = "unavailable"
            return _tb_defs_cache


def _analyze_platoons(tb_defs, member_rosters):
    """Cross-reference guild rosters against platoon requirements.

    Returns {planet_id: [platoon_result * N]}
    Each platoon_result: {fillable, slots: [{defId, need, have, minRarity, minRelic, ok}]}
    """
    out = {}
    for planet_id, platoons in tb_defs.items():
        planet_out = []
        for platoon_slots in platoons:
            needs = {}
            for slot in platoon_slots:
                d = slot["defId"]
                if d not in needs:
                    needs[d] = {"defId": d, "need": 0,
                                "name": slot.get("name") or _lookup_unit_name(d),
                                "minRarity": slot["minRarity"],
                                "minRelic":  slot["minRelic"]}
                needs[d]["need"] += 1

            slot_analysis = []
            for d, req in needs.items():
                requirement_is_ship = _is_ship_name_or_defid(req.get("name"), d)
                target_name_key = _normalize_unit_name_lookup(req.get("name"))
                have = sum(
                    1 for roster in member_rosters.values()
                    for unit in roster
                    if (
                        (
                            (_canonical_defid(unit.get("defId")) == _canonical_defid(d) and not str(d).startswith("WIKI_"))
                            or (
                                str(d).startswith("WIKI_")
                                and _normalize_unit_name_lookup(unit.get("name") or _lookup_unit_name(unit.get("defId"))) == target_name_key
                            )
                        )
                        and unit.get("rarity", 0) >= req["minRarity"]
                        and (requirement_is_ship or unit.get("relic", 0) >= req["minRelic"])
                    )
                )
                slot_analysis.append({
                    "defId":     d,
                    "name":      req.get("name") or _lookup_unit_name(d),
                    "need":      req["need"],
                    "have":      have,
                    "minRarity": req["minRarity"],
                    "minRelic":  req["minRelic"],
                    "ok":        have >= req["need"]
                })
            slot_analysis.sort(key=lambda x: (x["ok"], x["have"] - x["need"]))
            planet_out.append({
                "fillable": all(s["ok"] for s in slot_analysis),
                "slots":    slot_analysis
            })
        out[planet_id] = planet_out
    return out


# ─── HTTP SERVER ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress noise

    def handle_error(self, request, client_address):
        """Suppress harmless socket-level errors from filling the console."""
        import traceback, sys
        exc = sys.exc_info()[1]
        if exc is None:
            return
        err_str = str(exc)
        # Suppress: client closed connection (10053), comlink refused (10061)
        noisy = ("10053", "10061", "BrokenPipeError", "ConnectionAbortedError",
                 "ConnectionResetError", "ConnectionRefusedError")
        if any(n in err_str or n in type(exc).__name__ for n in noisy):
            return  # silently drop
        # Print all others normally
        traceback.print_exc()

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass  # Client closed connection before response completed — harmless

    def proxy(self, endpoint, payload):
        # Always ensure enums:false so field names are consistent strings
        if "enums" not in payload:
            payload = dict(payload, enums=False)
        url = f"http://localhost:{COMLINK_PORT}/{endpoint}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read()), 200
        except urllib.error.HTTPError as e:
            return {"error": f"Comlink HTTP {e.code}: {e.read().decode()[:200]}"}, 502
        except Exception as e:
            return {"error": str(e)}, 503

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML_APP.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                pass

        elif self.path == "/api/status":
            try:
                meta = _comlink_post("metadata", timeout=4)
                # v4.x returns {latestGamedataVersion, ...}
                # v3.x returns similar structure
                ver = (meta.get("latestGamedataVersion")
                       or meta.get("gameVersion")
                       or meta.get("version", "?"))
                self.send_json({
                    "comlink": "online",
                    "port":    COMLINK_PORT,
                    "version": str(ver)[:20],
                })
            except urllib.error.HTTPError as e:
                # comlink responded but with an error - still means it's running
                # Try root endpoint as fallback
                try:
                    req2 = urllib.request.Request(
                        f"http://localhost:{COMLINK_PORT}/",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req2, timeout=3) as r2:
                        r2.read()
                    self.send_json({"comlink": "online", "port": COMLINK_PORT,
                                    "version": "unknown (v4+)"})
                except Exception:
                    self.send_json({"comlink": "offline",
                                    "reason": f"HTTP {e.code}: {e.reason}",
                                    "tip": ("Comlink is running but POST /metadata returned "
                                            f"HTTP {e.code}. Check comlink terminal output.")})
            except Exception as e:
                # Connection refused = comlink process died; attempt auto-restart
                err_str = str(e)
                restarted = False
                if "10061" in err_str or "Connection refused" in err_str or "actively refused" in err_str:
                    proc_dead = (comlink_proc is None or comlink_proc.poll() is not None)
                    if proc_dead and _comlink_binary:
                        print("  Comlink died — attempting auto-restart...")
                        restarted = restart_comlink()
                self.send_json({
                    "comlink":   "offline",
                    "reason":    err_str[:200],
                    "restarted": restarted,
                    "tip":       ("Comlink not responding. " +
                                  ("Auto-restart attempted — click Retry in ~5s." if restarted
                                   else "Check the terminal window for startup errors."))
                })

        elif self.path == "/api/app-state":
            self.send_json({"state": _load_app_state()})

        elif self.path == "/shutdown":
            self.send_json({"status": "shutting_down"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global _unit_name_map, _unit_name_reverse_index
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}

        if self.path == "/api/player":
            ac = str(payload.get("allyCode", "")).replace("-", "").strip()
            _ensure_localization_maps(force=not (_skill_meta_map and _unit_skill_reference_map))
            data, status = self.proxy("player", {"payload": {"allyCode": ac}})
            self.send_json(data, status)

        elif self.path == "/api/guild-by-allycode":
            ac_str = str(payload.get("allyCode", "")).replace("-", "").strip()
            # Try ally code as both int and string — v4 comlink may require int
            player = None
            player_err = ""
            for ac_val in [int(ac_str), ac_str]:
                try:
                    p, s1 = self.proxy("player", {"payload": {"allyCode": ac_val}})
                    if s1 == 200 and isinstance(p, dict) and not p.get("message"):
                        player = p
                        break
                    player_err = str(p)
                except Exception as e:
                    player_err = str(e)

            if not player:
                self.send_json({
                    "error": f"Player lookup failed for ally code '{ac_str}'. "
                             f"Comlink response: {player_err[:300]}"
                }, 502); return

            # Dig out guildId — handle v4 nesting variations
            guild_id = (player.get("guildId")
                        or player.get("guild_id")
                        or (player.get("guild") or {}).get("id")
                        or "")
            if not guild_id:
                keys = list(player.keys())[:20]
                self.send_json({
                    "error": f"Could not find guildId in player response. "
                             f"Top-level keys: {keys}",
                    "_debug_player": {k: str(v)[:100] for k, v in list(player.items())[:15]}
                }, 400); return

            guild, s2 = self.proxy("guild", {
                "payload": {"guildId": guild_id,
                            "includeRecentGuildActivityInfo": True},
                "enums": False
            })

            # Attach the raw top-level keys so the browser can adapt parsing
            if isinstance(guild, dict):
                guild["_debug_keys"] = list(guild.keys())
                if "profile" in guild and isinstance(guild["profile"], dict):
                    guild["_debug_profile_keys"] = list(guild["profile"].keys())
            self.send_json(guild, s2)

        elif self.path == "/api/debug-comlink":
            # Raw diagnostic: call any comlink endpoint and return full response
            ep  = payload.get("endpoint", "player")
            pay = payload.get("payload", {})
            try:
                raw, status = self.proxy(ep, {"payload": pay})
                # For player, show top-level keys and first rosterUnit field names
                debug = {"status": status, "top_keys": list(raw.keys()) if isinstance(raw, dict) else []}
                if isinstance(raw, dict) and "rosterUnit" in raw:
                    units = raw["rosterUnit"]
                    debug["roster_unit_count"] = len(units)
                    debug["first_unit_keys"] = list(units[0].keys()) if units else []
                    debug["first_unit_sample"] = {k: str(v)[:60] for k,v in list(units[0].items())[:12]} if units else {}
                else:
                    debug["raw_sample"] = str(raw)[:500]
                self.send_json(debug)
            except Exception as e:
                self.send_json({"error": str(e)})

        elif self.path == "/api/guild":
            gid = payload.get("guildId", "")
            data, status = self.proxy("guild", {
                "payload": {"guildId": gid, "includeRecentGuildActivityInfo": True},
                "enums": False
            })
            self.send_json(data, status)

        elif self.path == "/api/roster":
            raw_input = str(payload.get("allyCode", "")).strip()
            # Only strip hyphens from numeric ally codes (e.g. "659-388-776")
            # NOT from base64 GUIDs like "fo8f8goIT2mjZKtRXZh8-w" where '-' is significant
            if raw_input.replace("-","").replace(" ","").isdigit():
                raw = raw_input.replace("-","").replace(" ","")
            else:
                raw = raw_input  # preserve hyphens in GUIDs
            player, status = None, 502

            # Detect whether input is a GUID (playerId from guild member list)
            # or a numeric ally code
            is_guid = (not raw.isdigit()) and len(raw) > 10

            if is_guid:
                # Use playerId — guild members have this but not allyCode
                for pay in [{"playerId": raw}, {"allyCode": raw}]:
                    try:
                        p, s = self.proxy("player", {"payload": pay})
                        if s == 200 and isinstance(p, dict) and not p.get("message"):
                            player, status = p, s
                            break
                    except Exception:
                        pass
            else:
                # Numeric ally code — v4 requires integer
                for ac_val in [int(raw), raw]:
                    try:
                        p, s = self.proxy("player", {"payload": {"allyCode": ac_val}})
                        if s == 200 and isinstance(p, dict) and not p.get("message"):
                            player, status = p, s
                            break
                    except Exception:
                        pass

            if player is None or status != 200:
                self.send_json({"error": f"Roster fetch failed for '{raw}'"}, 502)
                return
            _ensure_localization_maps(force=not (_skill_meta_map and _unit_skill_reference_map))
            statcalc_ready = _apply_roster_power(player)
            roster = player.get("rosterUnit", [])
            simplified = []
            scan_errors = []
            for unit in roster:
                relic_tier = 0
                relic_obj = unit.get("relic") or unit.get("relicTier") or {}
                if isinstance(relic_obj, dict):
                    relic_tier = relic_obj.get("currentTier") or relic_obj.get("tier") or 0
                elif isinstance(relic_obj, (int, float)):
                    relic_tier = int(relic_obj)
                # CG relic tiers: 1 = not reliced, 3 = R1, 4 = R2 ... 9 = R7
                relic_level = max(0, relic_tier - 2)
                # ── Robust field extraction with multiple fallback names ──
                # defId — the character definition ID string
                # comlink v4 uses "definitionId" in format "BASEUNIT:SEVEN_STARS"
                # or "definitionId" as plain "BASEUNIT" — strip the rarity suffix
                raw_did = (unit.get("defId")
                           or unit.get("baseId")
                           or unit.get("definitionId")
                           or unit.get("unitDefId")
                           or unit.get("id")
                           or "")
                def_id = raw_did.split(":")[0].strip() if raw_did else ""

                # star level: comlink v4 uses "currentRarity" (confirmed from scan log)
                rarity_val = (unit.get("currentRarity")
                              or unit.get("rarity")
                              or unit.get("starLevel")
                              or unit.get("stars")
                              or 0)

                # gear level — comlink v4 uses "currentTier" (G1-G13)
                gear_val = (unit.get("currentTier")
                            or unit.get("gear")
                            or unit.get("currentGear")
                            or unit.get("gearLevel")
                            or unit.get("gearTier")
                            or 0)

                mods_present = "equippedStatMod" in unit
                raw_ctype = unit.get("combatType") or unit.get("type")
                ctype = _infer_combat_type(def_id, raw_ctype)

                # ── Speed ──────────────────────────────────────────────────────────
                # comlink v4 confirmed uses "unitStat" field (from scan_log raw_unit_debug)
                speed = 0
                for stat_root in [unit.get("unitStat"), unit.get("stat"),
                                   unit.get("stats"), unit.get("statList")]:
                    if not stat_root:
                        continue
                    if isinstance(stat_root, dict):
                        stat_list = (stat_root.get("stat") or stat_root.get("stats")
                                     or stat_root.get("statList") or [])
                    elif isinstance(stat_root, list):
                        stat_list = stat_root
                    else:
                        continue
                    for s in stat_list:
                        if not isinstance(s, dict):
                            continue
                        sid = str(s.get("unitStatId") or s.get("statId") or
                                  s.get("id") or s.get("statType") or "")
                        if sid in ("5", "UNIT_STAT_SPEED", "speed"):
                            try:
                                raw_val = (s.get("statValueDecimal")
                                           or s.get("value") or s.get("statValue")
                                           or (s.get("statValueList") or ["0"])[0]
                                           or "0")
                                speed = int(float(str(raw_val).split(".")[0]))
                            except Exception:
                                pass
                            break
                    if speed > 0:
                        break

                if not def_id:
                    scan_errors.append({"issue":"missing_defId","unit_keys":list(unit.keys())[:8]})
                    continue
                ability_rows = _simplify_skills(unit, def_id=def_id, combat_type=ctype)
                zetas = sum(1 for row in ability_rows if row.get("hasZeta"))
                omicrons = sum(1 for row in ability_rows if row.get("hasOmicron"))
                power = _extract_unit_power(unit)
                simplified.append({
                    "defId":      def_id,
                    "name":       _lookup_unit_name(
                        def_id,
                        unit.get("nameKey") or unit.get("name") or ""
                    ),
                    "rarity":     rarity_val,
                    "gear":       gear_val,
                    "relic":      relic_level,
                    "combatType": ctype,
                    "modsPresent": mods_present,
                    "speed":      speed,
                    "power":      power,
                    "zetas":      zetas,
                    "omicrons":   omicrons,
                    "skills":     ability_rows,
                })
            with _rosters_lock:
                _guild_rosters[raw] = simplified
            _unit_name_reverse_index = None

            # Write scan log entry — include raw unit fields on first unit for diagnosis
            try:
                log_path = COMLINK_DIR / "scan_log.json"
                # Raw first unit fields so we can debug stat/skill/gear extraction
                raw_unit_debug = {}
                if roster:
                    u0 = roster[0]
                    # Find highest-relic unit to check zeta/omicron data
                    def _relic_tier(u):
                        r = u.get("relic") or {}
                        return (r.get("currentTier",0) if isinstance(r,dict) else 0)
                    hr = max(roster, key=_relic_tier, default=u0)
                    raw_unit_debug = {
                        "all_keys":          list(u0.keys()),
                        "unitStat_raw":      str(u0.get("unitStat","MISSING"))[:400],
                        "stat_raw":          str(u0.get("stat","MISSING"))[:200],
                        "skill_first2":      str((u0.get("skill") or [])[:2])[:300],
                        "purchasedAbility":  u0.get("purchasedAbilityId","MISSING"),
                        "currentTier_gear":  u0.get("currentTier","MISSING"),
                        "combatType":        u0.get("combatType","MISSING"),
                        "power":             _extract_unit_power(u0),
                        "equippedStatMod":   "present" if "equippedStatMod" in u0 else "absent",
                        "nameKey":           u0.get("nameKey","MISSING"),
                        "definitionId":      u0.get("definitionId","MISSING"),
                        "high_relic_defId":  hr.get("definitionId","?"),
                        "high_relic_purchased": hr.get("purchasedAbilityId",[]),
                        "high_relic_skills": str(hr.get("skill",[]))[:400],
                        "high_relic_tier":   _relic_tier(hr),
                        "statcalc_ready":    statcalc_ready,
                        "statcalc_error":    _statcalc_last_error,
                    }
                log_entry = {
                    "allyCode": raw,
                    "units_stored": len(simplified),
                    "units_skipped": len(scan_errors),
                    "errors": scan_errors[:5],
                    "sample_unit": simplified[0] if simplified else None,
                    "raw_unit_debug": raw_unit_debug,
                    "timestamp": str(__import__("datetime").datetime.now().isoformat())
                }
                existing = []
                if log_path.exists():
                    try:
                        existing = json.loads(log_path.read_text())[-49:]  # keep last 50
                    except Exception:
                        existing = []
                existing.append(log_entry)
                log_path.write_text(json.dumps(existing, indent=2))
            except Exception as _le:
                pass  # log failures are non-fatal

            self.send_json({"allyCode": raw, "roster": simplified,
                            "units": len(simplified), "skipped": len(scan_errors),
                            "powerReady": statcalc_ready,
                            "powerError": _statcalc_last_error if not statcalc_ready else ""})

        elif self.path == "/api/fetch-unit-names":
            # Try multiple sources for a defId→name mapping:
            # 1. comlink /data with various segment formats
            # 2. comlink /localization endpoint
            # 3. swgoh.gg public API (characters + ships)
            name_map = {}
            errors = []
            sources_tried = []

            # Source 1: comlink /data endpoint (units collection)
            data_payloads = []
            try:
                meta = _comlink_post("metadata", timeout=10)
                version = str(meta.get("latestGamedataVersion") or meta.get("gameVersion") or "").strip() if isinstance(meta, dict) else ""
            except Exception:
                version = ""
            if version:
                data_payloads.extend([
                    {"payload":{"version": version, "includePveUnits": False, "requestSegment": 3}},
                    {"payload":{"version": version, "includePveUnits": False, "items": _GAME_DATA_ITEMS_UNITS}},
                ])
            data_payloads.extend([
                {"payload":{"includePveUnits": False, "requestSegment": 3}},
                {"payload":{"includePveUnits": False, "items": _GAME_DATA_ITEMS_UNITS}},
            ])
            for pay in data_payloads:
                try:
                    data, status = self.proxy("data", pay)
                    if status == 200 and isinstance(data, dict):
                        for key, val in data.items():
                            if isinstance(val, list) and len(val) > 5:
                                sample = val[0]
                                if isinstance(sample, dict) and (
                                    "baseId" in sample or "definitionId" in sample):
                                    for unit in val:
                                        bid = (unit.get("baseId") or
                                               str(unit.get("definitionId","")).split(":")[0])
                                        nk  = (unit.get("nameKey") or unit.get("name",""))
                                        if bid and nk and not nk.isupper():
                                            name_map[bid.upper()] = nk
                        pay_info = pay.get("payload", {})
                        src_label = "comlink/data("
                        if pay_info.get("requestSegment") is not None:
                            src_label += f"requestSegment={pay_info.get('requestSegment')}"
                        elif pay_info.get("items") is not None:
                            src_label += f"items={pay_info.get('items')}"
                        else:
                            src_label += "default"
                        src_label += ")"
                        sources_tried.append(src_label)
                        if name_map: break
                except Exception as e:
                    errors.append(f"comlink data: {e}")

            # Source 2: swgoh.gg public characters API
            if len(name_map) < 100:
                try:
                    for endpoint in ["https://swgoh.gg/api/characters/",
                                     "https://swgoh.gg/api/ships/"]:
                        req = urllib.request.Request(endpoint,
                            headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
                        with urllib.request.urlopen(req, timeout=10) as r:
                            units_list = json.loads(r.read())
                        if isinstance(units_list, list):
                            for u in units_list:
                                bid = u.get("base_id","")
                                nm  = u.get("name","")
                                if bid and nm:
                                    name_map[bid.upper()] = nm
                    sources_tried.append("swgoh.gg/api")
                except Exception as e:
                    errors.append(f"swgoh.gg: {e}")

            # Source 3: comlink localization — all unit names are in Loc_ENG_US.txt
            # Keys follow pattern "UNIT_{DEFID}_NAME" → "Display Name"
            # Also tries "localization" endpoint various formats
            if len(name_map) < 100:
                for loc_pay in [
                    {"payload":{"id":"Loc_ENG_US.txt","unzip":True},"enums":False},
                    {"payload":{"id":"Loc_ENG_US.txt"},"enums":False},
                    {"payload":{"language":"ENG_US"},"enums":False},
                    {"payload":{},"enums":False},
                ]:
                    try:
                        loc, ls = self.proxy("localization", loc_pay)
                        if ls == 200 and isinstance(loc, dict):
                            loc_data = loc
                            # v4 might wrap in {"localizationBundle": {...}}
                            if "localizationBundle" in loc:
                                loc_data = loc["localizationBundle"]
                            if isinstance(loc_data, dict) and loc_data:
                                before = len(name_map)
                                for k, v in loc_data.items():
                                    # Pattern: UNIT_MAGMATROOPER_NAME → Magna Trooper
                                    if isinstance(k, str) and isinstance(v, str):
                                        k_up = k.upper()
                                        if k_up.startswith("UNIT_") and k_up.endswith("_NAME"):
                                            defid = k_up[5:-5]  # strip UNIT_ and _NAME
                                            if defid and v and not v.isupper():
                                                name_map[defid] = v
                                added = len(name_map) - before
                                if added > 0:
                                    sources_tried.append(f"comlink/localization (+{added})")
                                    break
                    except Exception as e:
                        errors.append(f"localization {loc_pay}: {str(e)[:80]}")

            # Save to disk for persistence
            if name_map:
                try:
                    nf = COMLINK_DIR / "unit_names.json"
                    nf.write_text(json.dumps(name_map, indent=2))
                    _unit_name_map = name_map
                except Exception: pass

            self.send_json({
                "count":   len(name_map),
                "sources": sources_tried,
                "errors":  errors,
                "sample":  dict(list(name_map.items())[:15]),
                "names":   name_map,
            })

        elif self.path == "/api/comlink-health":
            # Check if comlink is alive; if not, try to restart it
            alive = is_comlink_running()
            restarted = False
            if not alive and _comlink_binary:
                # Check if the process died
                proc_dead = (comlink_proc is None or comlink_proc.poll() is not None)
                if proc_dead:
                    restarted = restart_comlink()
                    alive = is_comlink_running()
            self.send_json({
                "alive":     alive,
                "restarted": restarted,
                "proc_alive": comlink_proc is not None and comlink_proc.poll() is None
            })

        elif self.path == "/api/tb-platoons":
            defs = _fetch_tb_defs()
            if defs:
                self.send_json({"status": "ok", "count": len(defs),
                                "planets": list(defs.keys())})
            else:
                self.send_json({"status": "unavailable",
                    "error": ("Built-in TB definitions are unavailable. "
                              "Check the terminal window for diagnostic details.")})

        elif self.path == "/api/ops-definitions":
            defs = _fetch_tb_defs()
            if defs:
                self.send_json({
                    "status": "ok",
                    "defs": defs,
                    "count": len(defs),
                    "source": _tb_defs_source,
                    "sourceLabel": "Bundled wiki definitions" if _tb_defs_source == "bundled-wiki" else _tb_defs_source
                })
            else:
                self.send_json({"status": "unavailable",
                    "error": ("Built-in operations definitions are unavailable. "
                              "Check the terminal window for diagnostic details.")}, 503)

        elif self.path == "/api/guide-tb-omicrons":
            try:
                self.send_json({
                    "status": "ok",
                    "units": _build_guide_tb_omicron_map(),
                    "omicronArea": 7,
                    "areaLabel": "Territory Battles",
                })
            except Exception as exc:
                self.send_json({
                    "status": "error",
                    "error": f"Could not load Territory Battle omicron metadata: {exc}",
                }, 500)

        elif self.path == "/api/platoon-analysis":
            rosters = dict(_guild_rosters)
            if not rosters:
                self.send_json({"error": "No roster data available. "
                                "Run Scan Rosters first."}, 400)
                return
            defs = _fetch_tb_defs()
            if not defs:
                self.send_json({"error": "TB platoon definitions unavailable. "
                                "Check terminal for details."}, 503)
                return
            analysis = _analyze_platoons(defs, rosters)
            self.send_json({"status": "ok",
                            "analysis":      analysis,
                            "planet_count":  len(analysis),
                            "roster_count":  len(rosters)})

        elif self.path == "/api/debug-roster-sample":
            # Returns the raw first rosterUnit from the first scanned member
            sample_ac = next(iter(_guild_rosters), None)
            if sample_ac:
                simplified = _guild_rosters[sample_ac]
                self.send_json({
                    "member_key": sample_ac,
                    "unit_count": len(simplified),
                    "sample_units": simplified[:3],
                    "all_keys": list(simplified[0].keys()) if simplified else []
                })
            else:
                self.send_json({"error": "No rosters scanned yet"})

        elif self.path == "/api/dump-raw-comlink-unit":
            # ── DIAGNOSTIC: returns the raw JSON of first 2 units from comlink
            # so we can see the exact field names comlink v4 returns
            # Usage: POST /api/dump-raw-comlink-unit {"allyCode": "..."}
            raw_ac = str(payload.get("allyCode","")).replace("-","").strip()
            if not raw_ac:
                # Use first guild member if available
                guild_m = getattr(self.server, "_last_guild_members", [])
                if guild_m:
                    raw_ac = str(guild_m[0].get("allyCode") or
                                 guild_m[0].get("playerId") or
                                 guild_m[0].get("memberExternalId",""))
            is_guid = (not raw_ac.isdigit()) and len(raw_ac) > 10
            player_raw = None
            for pay in ([{"playerId": raw_ac}, {"allyCode": raw_ac}]
                        if is_guid else [{"allyCode": int(raw_ac)}, {"allyCode": raw_ac}]):
                try:
                    r, s = self.proxy("player", {"payload": pay})
                    if s == 200 and isinstance(r, dict) and r.get("rosterUnit"):
                        player_raw = r
                        break
                except Exception as e:
                    pass
            if not player_raw:
                self.send_json({"error": "Could not fetch player", "tried_ac": raw_ac})
                return
            units = player_raw.get("rosterUnit", [])
            if not units:
                self.send_json({"error": "No rosterUnit in response",
                                "top_level_keys": list(player_raw.keys())[:20]})
                return
            # Return FULL raw unit objects (not simplified) for first 2 units
            # This shows us exactly what comlink v4 returns
            u0 = units[0]
            u1 = units[1] if len(units) > 1 else {}
            self.send_json({
                "unit_count": len(units),
                "unit_0_all_keys": list(u0.keys()),
                "unit_0_full": {k: str(v)[:200] for k,v in u0.items()},
                "unit_0_stat_raw": u0.get("stat","MISSING"),
                "unit_0_skill_raw": str(u0.get("skill","MISSING"))[:500],
                "unit_0_gear_raw": u0.get("gear","MISSING"),
                "unit_0_combat_raw": u0.get("combatType","MISSING"),
                "unit_1_keys": list(u1.keys()),
            })

        elif self.path == "/api/log-scan-failure":
            # Log a scan failure entry so missing members appear in scan_log
            try:
                log_path = COMLINK_DIR / "scan_log.json"
                entry = {
                    "allyCode":    payload.get("allyCode","?"),
                    "memberIndex": payload.get("memberIndex","?"),
                    "status":      "FAILED",
                    "error":       payload.get("error","?"),
                    "responseKeys":payload.get("responseKeys",[]),
                    "timestamp":   str(__import__("datetime").datetime.now().isoformat())
                }
                existing = []
                if log_path.exists():
                    try: existing = json.loads(log_path.read_text())
                    except: pass
                existing.append(entry)
                log_path.write_text(json.dumps(existing[-100:], indent=2))
            except Exception as _e:
                pass
            self.send_json({"logged": True})

        elif self.path == "/api/reset-scan-session":
            try:
                with _rosters_lock:
                    _guild_rosters.clear()
                log_path = COMLINK_DIR / "scan_log.json"
                log_path.write_text("[]", encoding="utf-8")
                self.send_json({"reset": True})
            except Exception as e:
                self.send_json({"reset": False, "error": str(e)}, 500)

        elif self.path == "/api/import-session-state":
            rosters = payload.get("guildRosters") or {}
            if not isinstance(rosters, dict):
                self.send_json({"error": "guildRosters must be an object"}, 400)
                return
            normalized = {}
            total_units = 0
            for ally_code, roster in rosters.items():
                ally_code = str(ally_code or "").strip()
                if not ally_code:
                    continue
                clean_roster = roster if isinstance(roster, list) else []
                normalized[ally_code] = clean_roster
                total_units += len(clean_roster)
            with _rosters_lock:
                _guild_rosters.clear()
                _guild_rosters.update(normalized)
            self.send_json({
                "imported": True,
                "members": len(normalized),
                "units": total_units,
            })

        elif self.path == "/api/app-state":
            ok = _save_app_state(payload if isinstance(payload, dict) else {})
            if ok:
                self.send_json({"saved": True})
            else:
                self.send_json({"saved": False, "error": "Could not write app state file"}, 500)

        elif self.path == "/api/reset-tb-cache":
            global _tb_defs_cache
            _tb_defs_cache = None
            self.send_json({"status": "reset"})

        else:
            self.send_response(404)
            self.end_headers()

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    _install_startup_log()
    print()
    print("======================================================")
    print("  Rise of the Empire - TB Planner")
    print("  Star Wars: Galaxy of Heroes")
    print("======================================================")
    print(f"Startup log: {APP_LOG_PATH}")
    print()

    comlink_available = False
    try:
        binary = find_or_download_comlink()
        start_comlink(binary)
        comlink_available = True
    except Exception as e:
        print()
        print("="*54)
        print("  COMLINK COULD NOT START")
        print("="*54)
        print(str(e))
        print()
        print("WINDOWS TROUBLESHOOTING STEPS:")
        print()
        print("Step 1 - Unblock the binary (most common fix):")
        print("  Open File Explorer and go to:")
        print("  " + str(COMLINK_DIR))
        print("  Right-click swgoh-comlink.exe -> Properties")
        print("  Check the 'Unblock' box at the bottom -> OK")
        print("  Then re-run this program.")
        print()
        print("Step 2 - Test comlink manually:")
        print("  Open a NEW Command Prompt and run:")
        print('  cd /d "' + str(COMLINK_DIR) + '"')
        print("  swgoh-comlink.exe -n test")
        print("  Then open http://localhost:3000/ in your browser.")
        print("  Paste any error you see here for help.")
        print()
        print("Step 3 - Check if port 3000 is in use:")
        print("  Run this in Command Prompt: netstat -ano | findstr :3000")
        print("  If something is using it, change COMLINK_PORT at top of this file.")
        print()
        print("Running in paste-import mode (live import disabled).")
        print("="*54)
        print()

    # Load saved unit name map if available
    global _unit_name_map, _ability_name_map
    _nm_file = COMLINK_DIR / "unit_names.json"
    if _nm_file.exists():
        try:
            _unit_name_map = json.loads(_nm_file.read_text())
            print(f"   Loaded {len(_unit_name_map)} unit names from cache")
        except Exception:
            pass

    _ab_file = COMLINK_DIR / "ability_names.json"
    if _ab_file.exists():
        try:
            _ability_name_map = json.loads(_ab_file.read_text())
            print(f"   Loaded {len(_ability_name_map)} ability names from cache")
        except Exception:
            pass

    # Watchdog: restart comlink if it dies unexpectedly mid-session
    def _comlink_watchdog():
        while True:
            time.sleep(15)
            try:
                if comlink_proc is not None and comlink_proc.poll() is not None:
                    print("  Watchdog: comlink process died - auto-restarting...")
                    restart_comlink()
            except Exception:
                pass
    threading.Thread(target=_comlink_watchdog, daemon=True, name="comlink-watchdog").start()

    try:
        server, app_port = _bind_app_server(APP_PORT)
    except Exception as e:
        print(f"Could not start the local web server near port {APP_PORT}: {e}")
        raise
    if app_port != APP_PORT:
        print(f"Port {APP_PORT} is busy. Using http://localhost:{app_port} instead.")

    print(f"Starting web server on http://localhost:{app_port} ...")
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://localhost:{app_port}"
    print(f"   App ready: {url}")
    print()
    if AUTO_OPEN_BROWSER:
        print("   A browser window should open automatically.")
    else:
        print("   Open the URL above in your browser when you are ready.")
    print("   Press Ctrl+C or click 'Stop Server' in the browser to quit.")
    print("------------------------------------------------")
    print()

    if AUTO_OPEN_BROWSER:
        time.sleep(0.4)
        try:
            webbrowser.open(url)
        except Exception as exc:
            print(f"   Browser auto-open skipped: {exc}")

    try:
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

    print("\nShutting down...")
    server.shutdown()
    if comlink_available:
        stop_comlink()
    print("   Done. Goodbye!\n")
    sys.exit(0)

if __name__ == "__main__":
    main()

