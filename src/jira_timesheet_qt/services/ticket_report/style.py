"""Aussehen des Berichts - Design nach dem Template after-action-report.

Dunkler Command-Header, massstabsgetreue Zeitachse mit Statusband,
Kennzahlen-Kacheln, Ledger der Beteiligten. Alles eingebettet, keine
externe Datei, keine Schriftart aus dem Netz.
"""

CSS = """
:root{
--paper:#f3f5f3;--card:#ffffff;--ink:#16201c;--mut:#5a6b62;--faint:#8a978f;
--line:#dbe1dc;--hold:#0e7a52;--pine:#0a5c3f;--clock:#b04812;--dorm:#c3ccc5;
--disp:"Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;
--body:"Segoe UI",system-ui,sans-serif;
--mono:"Cascadia Mono",Consolas,ui-monospace,"Courier New",monospace;}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);font:14px/1.45 var(--body);padding:16px 30px 26px;
min-height:100vh;background-color:var(--paper);
background-image:
 radial-gradient(1200px 520px at 88% -12%,rgba(14,122,82,.07) 0%,rgba(14,122,82,0) 55%),
 linear-gradient(0deg,rgba(22,32,28,.032) 1px,transparent 1px),
 linear-gradient(90deg,rgba(22,32,28,.032) 1px,transparent 1px);
background-size:100% 100%,34px 34px,34px 34px}
::selection{background:#0e7a5233}

/* Command-Header */
.mast{position:relative;overflow:hidden;margin:-16px -30px 20px;padding:18px 30px 16px;
background:radial-gradient(900px 320px at 82% -45%,rgba(14,122,82,.30) 0%,rgba(14,122,82,0) 60%),
linear-gradient(135deg,#17251f 0%,#0b140f 100%);border-bottom:3px solid var(--clock)}
.mrow{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap}
.eyebrow{font:600 12px/1 var(--mono);letter-spacing:3px;text-transform:uppercase;
color:#e0954e;margin:0 0 8px}
.mast h1{font:800 clamp(21px,2.5vw,29px)/1.06 var(--disp);letter-spacing:-.022em;
margin:0;color:#f4f8f6;max-width:44ch}
.idbox{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:9px;
padding-top:2px}
.idtag{font:600 12px/1 var(--mono);letter-spacing:.5px;color:#93a99e}
.jlink{color:#7fc0a4;text-decoration:none;border-bottom:1px dotted #4f7a67}
.jlink:hover{color:#9ad9bd;border-bottom-color:#7fc0a4}
.pill{font:700 12px/1 var(--mono);letter-spacing:1.5px;text-transform:uppercase;
color:#43d99a;border:1.5px solid #2f8f63;border-radius:4px;padding:5px 11px;
background:rgba(67,217,154,.09);display:inline-flex;align-items:center;gap:7px}
.pill:before{content:"";width:7px;height:7px;border-radius:50%;background:#43d99a;
box-shadow:0 0 8px #43d99a}
.stats{display:flex;gap:0;margin-top:14px;flex-wrap:wrap}
.stat{padding:0 22px;border-left:1px solid rgba(255,255,255,.13)}
.stat:first-child{padding-left:0;border-left:0}
.stat .k{font:600 11px/1 var(--mono);letter-spacing:1.2px;text-transform:uppercase;
color:#8ea89c;margin-bottom:6px}
.stat .v{font:700 16px/1 var(--disp);color:#f1f6f3}

/* Section-Kopf */
.sec{margin-bottom:18px}
.h{display:flex;align-items:center;gap:10px;font:600 12px/1 var(--mono);letter-spacing:2px;
text-transform:uppercase;color:var(--mut);margin:0 0 11px}
.h:before{content:"";width:14px;height:2px;background:var(--clock)}
.hnote{margin-left:auto;letter-spacing:.4px;text-transform:none;font-weight:400;
color:var(--faint)}

/* --- Signature: massstabsgetreue Zeitachse --- */
.railbox{background:var(--card);border:1px solid var(--line);padding:16px 26px 10px;
box-shadow:0 1px 2px #16201c0a;overflow:hidden}
.rail{position:relative;height:206px;margin:0 8px}
.axis{position:absolute;left:0;right:0;top:88px;height:2px;background:var(--dorm)}
.offlayer{position:absolute;left:0;right:0;top:88px;height:30px;display:none;z-index:2}
.offlayer.on{display:block}
.off{position:absolute;top:0;bottom:0;background:repeating-linear-gradient(135deg,
rgba(60,74,67,.30) 0 4px,rgba(60,74,67,0) 4px 9px);border-left:1px solid rgba(60,74,67,.35);
border-right:1px solid rgba(60,74,67,.35)}
.band{position:absolute;left:0;right:0;top:92px;height:25px}
.seg{position:absolute;top:0;height:25px;background:color-mix(in srgb,var(--c) 22%,#fff);
border-left:2px solid var(--c);overflow:hidden}
.seg span{position:absolute;left:6px;top:7px;font:700 10.5px/1 var(--mono);letter-spacing:.4px;
text-transform:uppercase;color:var(--c);white-space:nowrap}
.seglab{position:absolute;top:121px;left:0;right:0;height:14px}
.sl{position:absolute;font:600 10.5px/1 var(--mono);letter-spacing:.3px;color:var(--mut);
white-space:nowrap}
.days{position:absolute;left:0;right:0;top:139px;height:14px}
.day{position:absolute;font:600 10px/1 var(--mono);letter-spacing:.5px;color:var(--faint);
white-space:nowrap;padding-left:4px;border-left:1px solid var(--line);height:11px}
.mk{position:absolute;background:none;border:0;padding:0;font:inherit;color:inherit;
cursor:pointer;transform:translateX(-50%);text-align:center;animation:rise .5s ease both}
.mk .dot{width:15px;height:15px;border-radius:50%;background:var(--card);
border:3px solid var(--c);margin:0 auto;position:relative;z-index:3;transition:.18s}
/* Statuswechsel sind die Gelenke des Ablaufs - eigene Form, gefuellt,
   und eine Trennlinie durch die Achse. Alles andere ist Aktivitaet. */
.mk.st .dot{width:17px;height:17px;border-radius:2px;transform:rotate(45deg);
background:var(--c);border-width:2px;box-shadow:0 0 0 3px var(--card)}
.mk.st:hover .dot,.mk.st.on .dot{transform:rotate(45deg) scale(1.25)}
.mk.st .lab{color:var(--c);font-weight:700}
.mk.st .chip{display:inline-block;font:700 10.5px/1 var(--mono);letter-spacing:.5px;
text-transform:uppercase;color:#fff;background:var(--c);padding:4px 7px;margin-top:3px;
white-space:nowrap}
.phaseline{position:absolute;top:60px;height:86px;width:1px;
background:repeating-linear-gradient(180deg,var(--c) 0 3px,transparent 3px 6px);opacity:.5;
z-index:1}
.mk:hover .dot,.mk.on .dot{transform:scale(1.3);
box-shadow:0 0 0 5px color-mix(in srgb,var(--c) 16%,transparent)}
.mk.on .dot{background:var(--c)}
.mk .cnt{position:absolute;top:-6px;right:-9px;font:700 9px/1 var(--mono);color:#fff;
background:var(--c);border-radius:8px;padding:2px 4px;z-index:4}
.mk .stem{width:1px;background:var(--dorm);margin:0 auto}
.mk .lab{font:600 11px/1.3 var(--mono);color:var(--mut);white-space:nowrap;max-width:210px;
overflow:hidden;text-overflow:ellipsis}
.mk .clk{font:700 10px/1.3 var(--mono);letter-spacing:.4px;color:var(--faint)}
.mk:hover .lab,.mk.on .lab{color:var(--ink);font-weight:700}
.mk.up{bottom:118px;display:flex;flex-direction:column;justify-content:flex-end}
.mk.dn{top:88px;display:flex;flex-direction:column}
.mk.up .dot{margin-bottom:-8px}
.mk.dn .dot{margin-top:-8px}
/* Randmarker: Beschriftung nach innen kippen, damit nichts abgeschnitten wird.
   Der Punkt bleibt dabei exakt auf seiner Zeitposition. */
.mk.el .lab,.mk.el .clk{transform:translateX(50%);text-align:left}
.mk.er .lab,.mk.er .clk{transform:translateX(-50%);text-align:right}
.mk:focus-visible{outline:2px solid var(--ink);outline-offset:3px}

/* Layout */
.grid{display:grid;grid-template-columns:1.05fr .95fr;gap:24px;align-items:start}
@media(max-width:1040px){.grid{grid-template-columns:1fr}}

/* Detail-Panel */
.panel{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c,#ccc);
box-shadow:0 1px 2px #16201c0a;overflow:hidden}
.phd{background:color-mix(in srgb,var(--c) 8%,var(--card));padding:12px 20px 11px;
border-bottom:1px solid var(--line)}
.pbody{padding:12px 20px 15px}
.badge{display:inline-flex;align-items:center;gap:8px;font:700 11px/1 var(--mono);
letter-spacing:1px;text-transform:uppercase;color:var(--c);margin-bottom:9px}
.badge:before{content:"";width:6px;height:6px;border-radius:50%;background:var(--c)}
.panel h3{margin:0 0 5px;font:700 17px/1.25 var(--disp);letter-spacing:-.01em}
.panel .lead{color:var(--mut);margin:0;font-size:13.5px}
.pbody ul{margin:0;padding-left:0;list-style:none}
.pbody li{margin:7px 0;padding-left:20px;position:relative;font-size:13px;
font-family:var(--mono);line-height:1.5;word-break:break-word}
.pbody li:before{content:"";position:absolute;left:0;top:7px;width:7px;height:7px;
border-radius:1px;background:var(--c);opacity:.5}
.hint{color:var(--mut);font-size:13px;text-align:center;padding:40px 12px;
font-family:var(--mono)}

/* Ledger Beteiligte */
.led{border-top:1px solid var(--line)}
.lrow{display:flex;align-items:center;gap:13px;width:100%;padding:9px 15px;
border-bottom:1px solid var(--line);border-left:3px solid var(--c);background:var(--card);
cursor:pointer;text-align:left;font:inherit;color:inherit;transition:.14s}
.lrow:hover{background:#fbfcfb}
.lrow.on{background:color-mix(in srgb,var(--c) 6%,var(--card))}
.lsw{width:9px;height:9px;border-radius:50%;background:var(--c);flex:none}
.ltxt{flex:1;min-width:0}
.llab{font:700 14px/1.2 var(--disp);display:block}
.lnm{color:var(--mut);font-size:12px;display:block;margin-top:2px;font-family:var(--mono)}
.lbar{position:relative;height:7px;background:#eef1ef;margin-top:6px;overflow:hidden}
.lbar span{position:absolute;left:0;top:0;bottom:0;background:var(--c);opacity:.75}
.lpct{font:700 12px/1 var(--mono);color:var(--ink);flex:none;width:52px;text-align:right}
.hb{font:700 10px/1 var(--mono);letter-spacing:.5px;background:#fff4d6;color:#8a6206;
border:1px solid #e6c667;border-radius:3px;padding:4px 7px;white-space:nowrap;flex:none}
.toggle{cursor:pointer;background:var(--card);border:1px solid var(--line);color:var(--mut);
font:600 11.5px/1 var(--mono);letter-spacing:.5px;padding:7px 13px;border-radius:6px;
margin-bottom:10px;transition:.15s}
.toggle:hover{border-color:var(--clock);color:var(--clock)}
.toggle.act{background:#fdf2e9;border-color:#eecab0;color:var(--clock)}

/* Liegezeit-Balken: brutto hell, netto gefuellt */
.dur{border-top:1px solid var(--line)}
.drow{display:flex;align-items:center;gap:12px;padding:8px 15px;
border-bottom:1px solid var(--line);background:var(--card);border-left:3px solid var(--c)}
.dnm{font:700 12.5px/1.2 var(--disp);width:158px;flex:none}
.dsub{display:block;font:600 10px/1.3 var(--mono);color:var(--faint);margin-top:3px;
letter-spacing:.2px}
.dbar{flex:1;position:relative;height:15px;background:#f2f5f3}
.dbar .g{position:absolute;left:0;top:0;bottom:0;background:var(--c);opacity:.2}
.dbar .n{position:absolute;left:0;top:0;bottom:0;background:var(--c);opacity:.72}
.dval{font:600 11.5px/1.4 var(--mono);color:var(--mut);width:132px;flex:none;text-align:right}
.dval b{color:var(--ink);font-weight:700}
.legend{display:flex;gap:16px;padding:0 15px 10px;font:600 10.5px/1 var(--mono);
letter-spacing:.4px;color:var(--faint);text-transform:uppercase}
.legend>span>span{display:inline-block;width:11px;height:11px;margin-right:6px;
vertical-align:-1px;background:var(--mut)}
.legend .g>span{opacity:.2}.legend .n>span{opacity:.72}

/* Kennzahlen */
.mgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
@media(max-width:1240px){.mgrid{grid-template-columns:repeat(2,1fr)}}
.mc{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--c);
padding:12px 15px 13px;box-shadow:0 1px 2px #16201c0a;display:flex;flex-direction:column}
.mlab{font:600 10.5px/1 var(--mono);letter-spacing:1.4px;text-transform:uppercase;
color:var(--mut)}
.mval{font:800 26px/1.1 var(--disp);letter-spacing:-.02em;color:var(--c);margin:7px 0 6px}
.mnote{margin:0;font-size:12px;line-height:1.45;color:var(--mut)}

/* Befunde */
.finds{display:grid;gap:10px;margin-top:2px}
.fc{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);
padding:11px 16px;box-shadow:0 1px 2px #16201c08}
.fc h4{margin:0 0 5px;font:700 13.5px/1.25 var(--disp);display:flex;align-items:center;gap:9px}
.fc h4:before{content:"";width:7px;height:7px;background:var(--c);flex:none}
.fc p{margin:0;font-size:13px;color:var(--mut);line-height:1.5}

/* Verwandte Tickets */
.rel{display:flex;flex-wrap:wrap;gap:9px}
.rc{display:block;background:var(--card);border:1px solid var(--line);padding:9px 14px;
text-decoration:none;color:inherit;transition:.15s;border-left:3px solid var(--dorm)}
.rc:hover{border-left-color:var(--clock);background:#fbfcfb}
.rk{font:700 12.5px/1 var(--mono);letter-spacing:.4px;color:var(--hold);display:block}
.ro{font-size:11.5px;color:var(--mut);display:block;margin-top:4px}

.foot{color:var(--faint);font:11.5px/1.5 var(--mono);margin-top:18px;padding-top:12px;
border-top:1px solid var(--line)}
@keyframes rise{from{opacity:0;transform:translateX(-50%) translateY(8px)}
to{opacity:1;transform:translateX(-50%)}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
"""
