"""App-owned presentation theme: one palette, one stylesheet, a few bundled icons.

No external fonts, scripts or images. Colors carry meaning consistently:
cyan/blue = measurements, teal/green = healthy, orange = warning, red = critical/fault.
Resource gauges (CPU, memory) are always neutral cyan; orange/red appear only for
alert and fault states reported by the collector, never as invented thresholds.
"""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

CYAN, BLUE, TEAL = "#22D3EE", "#3B82F6", "#2DE0C4"
GREEN, ORANGE, RED = "#34D399", "#F59E0B", "#F87171"
BG, PANEL, PANEL_2, BORDER, GRID = "#050A14", "#0B1424", "#101B30", "#1B2A44", "#17233A"
TEXT, MUTED = "#E6EEFB", "#8FA3C4"

_CSS = """
.stApp{--pm-bg:%(BG)s;--pm-panel:%(PANEL)s;--pm-panel2:%(PANEL_2)s;--pm-border:%(BORDER)s;--pm-grid:%(GRID)s;
  --pm-text:%(TEXT)s;--pm-muted:%(MUTED)s;--pm-cyan:%(CYAN)s;--pm-blue:%(BLUE)s;--pm-teal:%(TEAL)s;
  --pm-green:%(GREEN)s;--pm-orange:%(ORANGE)s;--pm-red:%(RED)s;
  background:radial-gradient(1100px 520px at 88%% -10%%,rgba(34,211,238,.10),transparent 60%%),
             radial-gradient(900px 480px at -5%% 105%%,rgba(59,130,246,.08),transparent 60%%),var(--pm-bg);}
.block-container{padding-top:2.2rem;padding-bottom:3rem;max-width:1500px}

/* ---- sidebar ---- */
[data-testid="stSidebar"]{background:linear-gradient(180deg,#08101F 0%%,#060C18 100%%);border-right:1px solid var(--pm-border)}
[data-testid="stSidebarNavLink"],[data-testid="stSidebarNav"] a{border-radius:12px;padding:.55rem .75rem;margin-bottom:.15rem;color:var(--pm-text)}
[data-testid="stSidebarNavLink"]:hover{background:rgba(34,211,238,.08)}
[data-testid="stSidebarNavLink"][aria-current="page"]{background:linear-gradient(90deg,rgba(45,224,196,.95),rgba(34,211,238,.85));color:#03131A;font-weight:700}
[data-testid="stSidebarNavLink"][aria-current="page"] *{color:#03131A!important}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]{justify-content:flex-start;background:transparent;border:1px solid transparent;color:var(--pm-text);border-radius:12px}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover{background:rgba(34,211,238,.08);border-color:var(--pm-border);color:var(--pm-cyan)}
.pm-brand{display:flex;align-items:center;gap:.65rem;margin:.2rem 0 .2rem}
.pm-brand b{font-size:1.45rem;font-weight:780;letter-spacing:-.04em;color:var(--pm-text)}
.pm-brand b span{color:var(--pm-cyan)}
.pm-tagline{color:var(--pm-muted);font-size:.78rem;margin:0 0 1.2rem}
.pm-section{color:var(--pm-muted);font-size:.68rem;font-weight:700;letter-spacing:.16em;margin:.9rem 0 .35rem}
.pm-sidechip{display:inline-block;font-size:.74rem;font-weight:650;border-radius:999px;padding:.12rem .6rem;margin:-.2rem 0 .4rem .75rem;border:1px solid}
.pm-sidechip.warn{color:var(--pm-orange);border-color:rgba(245,158,11,.5);background:rgba(245,158,11,.10)}
.pm-sidechip.bad{color:var(--pm-red);border-color:rgba(248,113,113,.5);background:rgba(248,113,113,.10)}

/* ---- page header ---- */
.pm-eyebrow{color:var(--pm-cyan);letter-spacing:.18em;font-size:.72rem;font-weight:750;margin:0 0 .1rem;display:flex;align-items:center;gap:.6rem}
.pm-eyebrow::before{content:"";width:4px;height:1.1rem;border-radius:3px;background:linear-gradient(180deg,var(--pm-teal),var(--pm-blue))}
.pm-pills{display:flex;flex-wrap:wrap;gap:.45rem;justify-content:flex-end;max-width:100%%}
.pm-pill{display:inline-flex;align-items:center;gap:.45rem;font-size:.78rem;color:var(--pm-text);border:1px solid var(--pm-border);background:var(--pm-panel);border-radius:999px;padding:.28rem .8rem;white-space:nowrap}
.pm-pill .dot{width:.5rem;height:.5rem;border-radius:50%%;background:var(--pm-muted)}
.pm-pill.ok{border-color:rgba(52,211,153,.55);background:rgba(52,211,153,.12);color:#9AF0CB}.pm-pill.ok .dot{background:var(--pm-green);box-shadow:0 0 8px var(--pm-green)}
.pm-pill.warn{border-color:rgba(245,158,11,.55);background:rgba(245,158,11,.10);color:#FBD38D}.pm-pill.warn .dot{background:var(--pm-orange)}
.pm-pill.bad{border-color:rgba(248,113,113,.6);background:rgba(248,113,113,.10);color:#FECACA}.pm-pill.bad .dot{background:var(--pm-red)}

/* ---- cards ---- */
[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(180deg,rgba(16,27,48,.72),rgba(11,20,36,.72));border-radius:16px}
[data-testid="stMetric"]{background:transparent}
[data-testid="stMetricLabel"]{color:var(--pm-muted);font-size:.8rem}
[data-testid="stMetricValue"]{font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.pm-sub{color:var(--pm-muted);font-size:.78rem;margin-top:.15rem}
.pm-ring{--p:0;position:relative;width:78px;height:78px;border-radius:50%%;display:grid;place-items:center;margin-left:auto;
  background:conic-gradient(var(--pm-teal) 0,var(--pm-cyan) calc(var(--p)*1%%),var(--pm-grid) 0)}
.pm-ring::before{content:"";position:absolute;inset:8px;border-radius:50%%;background:#0B1424}
.pm-ring span{position:relative;font-size:.82rem;font-weight:700;color:var(--pm-text);font-variant-numeric:tabular-nums}
.pm-bar{--p:0;height:8px;border-radius:999px;background:var(--pm-grid);overflow:hidden;margin:.45rem 0 .25rem}
.pm-bar>i{display:block;height:100%%;width:calc(var(--p)*1%%);background:linear-gradient(90deg,var(--pm-teal),var(--pm-cyan));border-radius:999px}
.pm-na{color:var(--pm-muted);font-size:.8rem}

/* ---- this-computer strip ---- */
.pm-hw{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem 2rem;padding:.9rem 1.2rem;margin:.2rem 0 .9rem;border:1px solid var(--pm-border);border-radius:16px;
  background:linear-gradient(100deg,rgba(34,211,238,.10),rgba(16,27,48,.6) 45%%,rgba(11,20,36,.6))}
.pm-hw-item{display:flex;align-items:center;gap:.75rem}
.pm-hw-item b{display:block;font-size:1rem;color:var(--pm-text)}
.pm-hw-item span{display:block;font-size:.76rem;color:var(--pm-muted)}
.pm-hw-main b{font-size:1.2rem}
.pm-hw-sep{width:1px;align-self:stretch;background:var(--pm-border)}

/* ---- health list / chips ---- */
.pm-health{list-style:none;margin:.4rem 0 0;padding:0;display:flex;flex-direction:column;gap:.55rem}
.pm-health li{display:flex;gap:.6rem;align-items:flex-start;font-size:.88rem;color:var(--pm-text);line-height:1.3}
.pm-health li b{flex:none;width:1.25rem;height:1.25rem;border-radius:50%%;display:grid;place-items:center;font-size:.75rem;color:#03131A}
.pm-health li.ok b{background:var(--pm-green)}.pm-health li.warn b{background:var(--pm-orange)}
.pm-health li.bad b{background:var(--pm-red)}.pm-health li.info b{background:var(--pm-blue);color:#fff}
.pm-chips{display:flex;flex-wrap:wrap;gap:.5rem;margin:.1rem 0 .8rem}
.pm-chip{font-size:.8rem;color:var(--pm-text);border:1px solid var(--pm-border);background:var(--pm-panel);border-radius:10px;padding:.3rem .7rem}
.pm-chip b{color:var(--pm-cyan);font-variant-numeric:tabular-nums;margin-left:.25rem}

/* ---- controls ---- */
[data-testid="stBaseButton-primary"]{background:linear-gradient(90deg,var(--pm-teal),var(--pm-cyan));color:#03131A;border:0;font-weight:700}
[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.08);color:#03131A}
[data-testid="stBaseButton-primary"] *{color:#03131A!important}
[data-testid="stAlert"]{border-radius:12px}
@media (max-width:900px){.pm-pills{justify-content:flex-start}.pm-hw-sep{display:none}}
""" % dict(BG=BG, PANEL=PANEL, PANEL_2=PANEL_2, BORDER=BORDER, GRID=GRID, TEXT=TEXT, MUTED=MUTED, CYAN=CYAN,
           BLUE=BLUE, TEAL=TEAL, GREEN=GREEN, ORANGE=ORANGE, RED=RED)


ASSETS = Path(__file__).resolve().parent / "assets" / "icons"
# CSS key -> icon file. Sidebar entries are keyed containers/buttons in app.py.
NAV_ICONS = {"nav_overview": "nav_overview_home", "nav_explorer": "nav_process_explorer", "nav_analytics": "nav_performance_analytics",
             "nav_history": "nav_time_machine", "ctl_alerts": "nav_alerts_bell", "ctl_health": "nav_collector_health",
             "ctl_settings": "nav_settings_gear", "ctl_exit": "nav_exit_power"}


@lru_cache(maxsize=None)
def icon_uri(name):
    """Base64 data URI of a bundled icon; empty (icon simply absent) if the file is unreadable."""
    try:
        return "data:image/webp;base64," + base64.b64encode((ASSETS / f"{name}.webp").read_bytes()).decode()
    except OSError:
        return ""


def ico(name, size=28, label=""):
    uri = icon_uri(name)
    if not uri:
        return ""
    return f'<img class="pm-ico" src="{uri}" width="{size}" height="{size}" alt="{label}"' + ('' if label else ' aria-hidden="true"') + ">"


_CSS2 = """
.block-container{max-width:1600px;padding:1.6rem 2.2rem 2.5rem}
.stMainBlockContainer [data-testid="stHorizontalBlock"]{gap:1rem}
.stMainBlockContainer [data-testid="stVerticalBlock"]{gap:1rem}
[data-testid="stHeading"] h1{font-size:2.35rem;font-weight:780;letter-spacing:-.03em;line-height:1.1;padding:0 0 .15rem}
[data-testid="stHeaderActionElements"]{display:none}
.pm-ico{display:block;flex:none;object-fit:contain}

/* ---- sidebar navigation and controls (icons are bundled WebP, inlined as data URIs) ---- */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.25rem}
[class*="st-key-nav_"] a,[class*="st-key-ctl_"] button{display:flex;align-items:center;justify-content:flex-start;gap:.7rem;width:100%%;min-height:2.8rem;
  padding:.4rem .75rem;border-radius:12px;color:var(--pm-text);text-decoration:none;font-size:.94rem;font-weight:500;background:transparent;border:1px solid transparent}
[class*="st-key-nav_"] a::before,[class*="st-key-ctl_"] button::before{content:"";flex:none;width:24px;height:24px;background:center/contain no-repeat}
[class*="st-key-nav_"] a:hover,[class*="st-key-ctl_"] button:hover{background:rgba(34,211,238,.09);color:var(--pm-text);border-color:var(--pm-border)}
[class*="st-key-nav_"] a p,[class*="st-key-ctl_"] button p{margin:0;font-size:.94rem;line-height:1.2;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;text-align:left}
.st-key-navon a{background:linear-gradient(90deg,rgba(45,224,196,.96),rgba(34,211,238,.88));color:#03131A;font-weight:700;box-shadow:0 6px 22px rgba(34,211,238,.18)}
.st-key-navon a:hover{color:#03131A;border-color:transparent}
.st-key-navon a *{color:#03131A!important}
.st-key-navon a::before{filter:brightness(.1)}
[class*="st-key-ctl_"]{border-bottom:1px solid rgba(27,42,68,.8)}
.st-key-ctl_alerts_wrap{position:relative}
.st-key-ctl_alerts_wrap .stElementContainer:has(.pm-badge){position:absolute;right:.85rem;top:.7rem;width:auto;z-index:2;pointer-events:none}
.pm-badge{display:inline-grid;place-items:center;min-width:1.6rem;height:1.6rem;padding:0 .4rem;border-radius:999px;font-size:.78rem;font-weight:750;color:#03131A;background:var(--pm-teal)}
.pm-badge.bad{background:var(--pm-red)}

/* ---- panel headers ---- */
.pm-panel-h{display:flex;align-items:center;gap:.65rem;min-height:32px;margin:0 0 .35rem}
.pm-panel-h h4{margin:0;padding:0;font-size:1.1rem;font-weight:700;letter-spacing:-.01em;color:var(--pm-text);line-height:1.2}
.pm-panel-h small{color:var(--pm-muted);font-size:.8rem;font-weight:500;margin-left:.15rem}

/* ---- this-computer strip: four equal items ---- */
.pm-hw{display:grid;grid-template-columns:1.25fr 1px 1.1fr 1.1fr 1.1fr;align-items:center;gap:1.4rem;padding:1.05rem 1.6rem;margin:0}
.pm-hw-item{gap:.95rem}
.pm-hw-item b{font-size:1.02rem;line-height:1.25}
.pm-hw-item span{margin-top:.1rem}
.pm-hw-main b{font-size:1.28rem}

/* ---- metric cards ---- */
.pm-na{font-size:.85rem;line-height:1.35}
.pm-sub{font-size:.82rem}
.pm-ring{width:84px;height:84px}
.pm-bar{height:9px;margin:.5rem 0 .3rem}
.pm-barrow{display:flex;align-items:center;gap:.8rem}
.pm-barrow .pm-bar{flex:1;margin:.5rem 0 .3rem}
.pm-barrow em{font-style:normal;font-size:.9rem;font-weight:650;color:var(--pm-text);font-variant-numeric:tabular-nums}
[data-testid="stMetricValue"]{font-size:2.05rem}
[data-testid="stMetricLabel"]{font-size:.88rem}

/* ---- time machine panel ---- */
.pm-timeline{position:relative;display:flex;justify-content:space-between;align-items:center;margin:1.3rem .5rem 1.3rem}
.pm-timeline::before{content:"";position:absolute;left:0;right:0;top:50%%;height:2px;background:linear-gradient(90deg,var(--pm-cyan),var(--pm-blue),#8B7CF6)}
.pm-timeline i{position:relative;width:11px;height:11px;border-radius:50%%;background:var(--pm-cyan);box-shadow:0 0 8px rgba(34,211,238,.7)}
.pm-timeline i.now{width:22px;height:22px;background:#0B1424;border:3px solid var(--pm-cyan);box-shadow:0 0 14px rgba(34,211,238,.9)}
[data-testid="stBaseButton-primary"]{min-height:2.9rem;border-radius:12px;font-size:1rem}
@media (max-width:1100px){.pm-hw{grid-template-columns:1fr 1fr}.pm-hw-sep{display:none}}
@media (max-width:700px){.pm-hw{grid-template-columns:1fr}}

/* ---- toolbar and responsive layout ---- */
[data-testid="stAppDeployButton"],.stAppDeployButton{display:none!important}
@media (min-width:992px){[data-testid="stSidebar"][aria-expanded="true"]{min-width:272px}}
[data-testid="stSidebar"][aria-expanded="false"]{min-width:0!important}
[class*="st-key-card_"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.6rem!important}
[class*="st-key-card_"] [data-testid="stHorizontalBlock"]>:is([data-testid="stColumn"],[data-testid="column"]){flex:1 1 0!important;min-width:0!important;width:auto!important}
[class*="st-key-card_"] [data-testid="stHorizontalBlock"]>:is([data-testid="stColumn"],[data-testid="column"]):first-child{flex:0 0 58px!important;min-width:58px!important;width:58px!important}
.st-key-card_cpu [data-testid="stHorizontalBlock"]>:is([data-testid="stColumn"],[data-testid="column"]):last-child{flex:0 0 92px!important;min-width:92px!important;width:92px!important}
[data-testid="stMetricDelta"],[data-testid="stMetricDelta"] *{white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
@media (max-width:1200px){.block-container{padding:1.2rem 1.2rem 2rem}[data-testid="stHeading"] h1{font-size:1.9rem}}
@media (max-width:1100px){
  .stMainBlockContainer [data-testid="stHorizontalBlock"]:not([data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"]){flex-wrap:wrap}
  .stMainBlockContainer [data-testid="stHorizontalBlock"]:not([data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"])>[data-testid="stColumn"],
  .stMainBlockContainer [data-testid="stHorizontalBlock"]:not([data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"])>[data-testid="column"]{flex:1 1 calc(50%% - 1rem)!important;min-width:calc(50%% - 1rem)!important}
}
@media (max-width:700px){
  .stMainBlockContainer [data-testid="stHorizontalBlock"]:not([data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"])>[data-testid="stColumn"],
  .stMainBlockContainer [data-testid="stHorizontalBlock"]:not([data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"])>[data-testid="column"]{flex:1 1 100%%!important;min-width:100%%!important}
  .pm-pills{justify-content:flex-start}
}
""".replace("%%", "%")


@lru_cache(maxsize=None)
def _nav_css():
    return "".join(f'.st-key-{key} a::before,.st-key-{key} button::before{{background-image:url("{icon_uri(name)}")}}\n' for key, name in NAV_ICONS.items() if icon_uri(name))


def inject():
    st.html(f"<style>{_CSS}{_CSS2}{_nav_css()}</style>")
