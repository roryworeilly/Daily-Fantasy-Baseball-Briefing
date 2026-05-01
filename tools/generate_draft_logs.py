#!/usr/bin/env python3
"""
generate_draft_logs.py
======================
Generates 3 detailed pick-by-pick draft simulations using the FDB and ESPN
ranking models, then writes draft_logs.json for the HTML Draft Room section.

10-team snake draft, 15 rounds.
Team 0 = FDB model. Teams 1-9 = ESPN model.
"""

import json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# ── Reuse data + scoring from model_comparison ─────────────────────────────
from model_comparison import (
    _sample_batters, _sample_pitchers,
    fdb_project_bat, fdb_project_pit,
    espn_project_bat, espn_project_pit,
    calc_fdb_bat, calc_fdb_pit,
    rank_by_score,
)

# ═══════════════════════════════════════════════════════════════════════════
# SYNTHETIC FILLER PLAYERS  (rounds 6-15, replacement-level depth)
# ═══════════════════════════════════════════════════════════════════════════

_FILLER_BATTERS = [
    # name, team, PA, H, 2B, 3B, HR, RBI, R, SB, BB, SO, AVG, OBP, SLG
    {"Name":"Cody Bellinger","Team":"CHC","PA":560,"H":128,"2B":25,"3B":2,"HR":18,"RBI":78,"R":71,"SB":8,"BB":52,"SO":141,"AVG":".253","OBP":".325","SLG":".420"},
    {"Name":"Teoscar Hernandez","Team":"LAD","PA":544,"H":136,"2B":28,"3B":1,"HR":26,"RBI":89,"R":76,"SB":5,"BB":38,"SO":148,"AVG":".272","OBP":".326","SLG":".482"},
    {"Name":"Eugenio Suarez","Team":"SEA","PA":520,"H":110,"2B":22,"3B":1,"HR":21,"RBI":72,"R":58,"SB":2,"BB":48,"SO":162,"AVG":".232","OBP":".307","SLG":".415"},
    {"Name":"Nathaniel Lowe","Team":"TEX","PA":596,"H":152,"2B":31,"3B":2,"HR":15,"RBI":74,"R":78,"SB":4,"BB":66,"SO":118,"AVG":".268","OBP":".349","SLG":".411"},
    {"Name":"Ha-Seong Kim","Team":"SD","PA":504,"H":118,"2B":24,"3B":3,"HR":11,"RBI":55,"R":69,"SB":22,"BB":44,"SO":114,"AVG":".267","OBP":".338","SLG":".396"},
    {"Name":"Jake Cronenworth","Team":"SD","PA":488,"H":112,"2B":23,"3B":1,"HR":14,"RBI":60,"R":54,"SB":3,"BB":46,"SO":98,"AVG":".252","OBP":".324","SLG":".394"},
    {"Name":"Daulton Varsho","Team":"TOR","PA":512,"H":118,"2B":26,"3B":3,"HR":18,"RBI":62,"R":68,"SB":16,"BB":44,"SO":138,"AVG":".243","OBP":".311","SLG":".419"},
    {"Name":"Trea Turner","Team":"PHI","PA":572,"H":148,"2B":28,"3B":4,"HR":19,"RBI":80,"R":88,"SB":26,"BB":40,"SO":128,"AVG":".272","OBP":".321","SLG":".446"},
    {"Name":"Gleyber Torres","Team":"NYY","PA":528,"H":130,"2B":26,"3B":1,"HR":17,"RBI":65,"R":72,"SB":6,"BB":48,"SO":112,"AVG":".257","OBP":".324","SLG":".408"},
    {"Name":"Ryan Mountcastle","Team":"BAL","PA":536,"H":134,"2B":27,"3B":1,"HR":22,"RBI":84,"R":66,"SB":2,"BB":38,"SO":138,"AVG":".263","OBP":".315","SLG":".435"},
    {"Name":"Ian Happ","Team":"CHC","PA":524,"H":126,"2B":28,"3B":2,"HR":16,"RBI":66,"R":72,"SB":8,"BB":62,"SO":122,"AVG":".254","OBP":".340","SLG":".406"},
    {"Name":"Yordan Alvarez","Team":"HOU","PA":496,"H":138,"2B":28,"3B":1,"HR":31,"RBI":101,"R":78,"SB":1,"BB":72,"SO":96,"AVG":".299","OBP":".393","SLG":".570"},
    {"Name":"Riley Greene","Team":"DET","PA":568,"H":148,"2B":32,"3B":4,"HR":19,"RBI":74,"R":82,"SB":11,"BB":58,"SO":136,"AVG":".277","OBP":".356","SLG":".451"},
    {"Name":"Andrew McCutchen","Team":"PIT","PA":484,"H":106,"2B":20,"3B":1,"HR":14,"RBI":58,"R":54,"SB":4,"BB":54,"SO":112,"AVG":".241","OBP":".324","SLG":".378"},
    {"Name":"Jeimer Candelario","Team":"CIN","PA":508,"H":118,"2B":25,"3B":1,"HR":18,"RBI":68,"R":62,"SB":3,"BB":52,"SO":124,"AVG":".256","OBP":".334","SLG":".416"},
    {"Name":"Nick Castellanos","Team":"PHI","PA":548,"H":142,"2B":30,"3B":2,"HR":19,"RBI":79,"R":68,"SB":3,"BB":36,"SO":128,"AVG":".272","OBP":".318","SLG":".438"},
    {"Name":"Gavin Sheets","Team":"CWS","PA":468,"H":108,"2B":22,"3B":1,"HR":17,"RBI":64,"R":51,"SB":1,"BB":38,"SO":118,"AVG":".253","OBP":".314","SLG":".408"},
    {"Name":"J.D. Davis","Team":"SF","PA":440,"H":106,"2B":22,"3B":1,"HR":14,"RBI":57,"R":49,"SB":2,"BB":44,"SO":104,"AVG":".265","OBP":".340","SLG":".406"},
    {"Name":"Alex Verdugo","Team":"NYY","PA":528,"H":130,"2B":26,"3B":2,"HR":13,"RBI":61,"R":68,"SB":6,"BB":44,"SO":108,"AVG":".260","OBP":".323","SLG":".390"},
    {"Name":"Isaac Paredes","Team":"TB","PA":540,"H":126,"2B":24,"3B":0,"HR":21,"RBI":72,"R":62,"SB":1,"BB":68,"SO":106,"AVG":".252","OBP":".345","SLG":".413"},
    {"Name":"Manny Machado","Team":"SD","PA":552,"H":144,"2B":30,"3B":1,"HR":21,"RBI":80,"R":74,"SB":4,"BB":58,"SO":98,"AVG":".272","OBP":".346","SLG":".445"},
    {"Name":"Jorge Soler","Team":"MIA","PA":496,"H":108,"2B":22,"3B":1,"HR":24,"RBI":72,"R":61,"SB":2,"BB":56,"SO":148,"AVG":".243","OBP":".329","SLG":".449"},
    {"Name":"Bryan Reynolds","Team":"PIT","PA":556,"H":148,"2B":30,"3B":3,"HR":18,"RBI":74,"R":74,"SB":7,"BB":54,"SO":124,"AVG":".279","OBP":".350","SLG":".443"},
    {"Name":"CJ Abrams","Team":"WSH","PA":580,"H":154,"2B":26,"3B":5,"HR":15,"RBI":61,"R":84,"SB":37,"BB":44,"SO":138,"AVG":".281","OBP":".340","SLG":".422"},
    {"Name":"Dominic Smith","Team":"NYM","PA":420,"H":98,"2B":18,"3B":1,"HR":11,"RBI":52,"R":42,"SB":1,"BB":40,"SO":98,"AVG":".258","OBP":".330","SLG":".386"},
    {"Name":"Luke Raley","Team":"TB","PA":464,"H":108,"2B":22,"3B":3,"HR":17,"RBI":59,"R":58,"SB":10,"BB":46,"SO":132,"AVG":".253","OBP":".325","SLG":".422"},
    {"Name":"Cavan Biggio","Team":"TOR","PA":480,"H":106,"2B":22,"3B":2,"HR":13,"RBI":52,"R":61,"SB":8,"BB":62,"SO":118,"AVG":".246","OBP":".345","SLG":".385"},
    {"Name":"Owen Miller","Team":"CLE","PA":436,"H":104,"2B":22,"3B":1,"HR":10,"RBI":48,"R":46,"SB":3,"BB":34,"SO":88,"AVG":".261","OBP":".318","SLG":".385"},
    {"Name":"Brett Baty","Team":"NYM","PA":480,"H":112,"2B":23,"3B":2,"HR":15,"RBI":61,"R":54,"SB":5,"BB":46,"SO":128,"AVG":".254","OBP":".328","SLG":".406"},
    {"Name":"Josh Bell","Team":"CLE","PA":500,"H":116,"2B":24,"3B":1,"HR":16,"RBI":66,"R":56,"SB":2,"BB":54,"SO":118,"AVG":".256","OBP":".337","SLG":".408"},
    {"Name":"Kevin Newman","Team":"CIN","PA":452,"H":112,"2B":20,"3B":2,"HR":7,"RBI":43,"R":51,"SB":7,"BB":28,"SO":72,"AVG":".262","OBP":".313","SLG":".360"},
    {"Name":"Brandon Drury","Team":"LAA","PA":484,"H":114,"2B":24,"3B":1,"HR":16,"RBI":62,"R":52,"SB":2,"BB":36,"SO":116,"AVG":".259","OBP":".313","SLG":".419"},
    {"Name":"Eduardo Escobar","Team":"NYM","PA":440,"H":98,"2B":20,"3B":1,"HR":14,"RBI":56,"R":46,"SB":2,"BB":36,"SO":108,"AVG":".249","OBP":".312","SLG":".398"},
    {"Name":"Enrique Hernandez","Team":"BOS","PA":476,"H":108,"2B":23,"3B":2,"HR":14,"RBI":54,"R":59,"SB":6,"BB":40,"SO":114,"AVG":".250","OBP":".315","SLG":".404"},
    {"Name":"DJ LeMahieu","Team":"NYY","PA":456,"H":110,"2B":20,"3B":1,"HR":8,"RBI":46,"R":52,"SB":4,"BB":42,"SO":78,"AVG":".262","OBP":".332","SLG":".363"},
    {"Name":"Joc Pederson","Team":"SF","PA":448,"H":102,"2B":20,"3B":1,"HR":18,"RBI":58,"R":54,"SB":2,"BB":52,"SO":108,"AVG":".252","OBP":".340","SLG":".432"},
    {"Name":"Max Kepler","Team":"MIN","PA":480,"H":112,"2B":23,"3B":1,"HR":15,"RBI":58,"R":58,"SB":4,"BB":46,"SO":118,"AVG":".255","OBP":".327","SLG":".402"},
    {"Name":"Jake McCarthy","Team":"ARI","PA":460,"H":112,"2B":20,"3B":4,"HR":8,"RBI":42,"R":58,"SB":19,"BB":34,"SO":108,"AVG":".259","OBP":".315","SLG":".377"},
    {"Name":"Lars Nootbaar","Team":"STL","PA":496,"H":116,"2B":24,"3B":2,"HR":14,"RBI":56,"R":64,"SB":9,"BB":58,"SO":128,"AVG":".257","OBP":".343","SLG":".402"},
    {"Name":"Nolan Jones","Team":"COL","PA":508,"H":118,"2B":24,"3B":3,"HR":17,"RBI":62,"R":61,"SB":12,"BB":56,"SO":148,"AVG":".259","OBP":".345","SLG":".427"},
    {"Name":"Wilyer Abreu","Team":"BOS","PA":436,"H":104,"2B":21,"3B":2,"HR":10,"RBI":44,"R":54,"SB":8,"BB":42,"SO":112,"AVG":".262","OBP":".336","SLG":".386"},
    {"Name":"Wenceel Perez","Team":"DET","PA":432,"H":108,"2B":18,"3B":3,"HR":6,"RBI":38,"R":58,"SB":18,"BB":28,"SO":88,"AVG":".272","OBP":".322","SLG":".369"},
    {"Name":"Sal Frelick","Team":"MIL","PA":476,"H":118,"2B":20,"3B":3,"HR":7,"RBI":40,"R":62,"SB":14,"BB":38,"SO":90,"AVG":".271","OBP":".330","SLG":".380"},
    {"Name":"Spencer Torkelson","Team":"DET","PA":500,"H":108,"2B":22,"3B":1,"HR":18,"RBI":64,"R":58,"SB":2,"BB":54,"SO":138,"AVG":".242","OBP":".322","SLG":".403"},
    {"Name":"Dillon Dingler","Team":"DET","PA":380,"H":88,"2B":18,"3B":1,"HR":10,"RBI":44,"R":40,"SB":3,"BB":28,"SO":98,"AVG":".255","OBP":".312","SLG":".386"},
    {"Name":"Tom Murphy","Team":"BAL","PA":320,"H":72,"2B":14,"3B":0,"HR":11,"RBI":40,"R":34,"SB":1,"BB":22,"SO":96,"AVG":".254","OBP":".309","SLG":".420"},
    {"Name":"Patrick Wisdom","Team":"CHC","PA":408,"H":86,"2B":17,"3B":1,"HR":18,"RBI":57,"R":46,"SB":3,"BB":44,"SO":148,"AVG":".238","OBP":".318","SLG":".424"},
    {"Name":"Mike Yastrzemski","Team":"SF","PA":456,"H":104,"2B":22,"3B":2,"HR":13,"RBI":50,"R":56,"SB":5,"BB":50,"SO":118,"AVG":".252","OBP":".335","SLG":".399"},
    {"Name":"Jake Fraley","Team":"CIN","PA":448,"H":106,"2B":21,"3B":2,"HR":14,"RBI":52,"R":56,"SB":11,"BB":48,"SO":118,"AVG":".263","OBP":".345","SLG":".409"},
    {"Name":"Leody Taveras","Team":"TEX","PA":452,"H":108,"2B":20,"3B":3,"HR":9,"RBI":40,"R":58,"SB":17,"BB":36,"SO":108,"AVG":".260","OBP":".319","SLG":".378"},
]

_FILLER_PITCHERS = [
    # name, team, IP, W, L, ERA, WHIP, K, BB, SV, HLD, HR
    {"Name":"Merrill Kelly","Team":"ARI","IP":174,"W":11,"L":9,"ERA":3.96,"WHIP":1.25,"K":162,"BB":44,"SV":0,"HLD":0,"HR":18},
    {"Name":"Pablo Lopez","Team":"MIN","IP":194,"W":14,"L":8,"ERA":3.66,"WHIP":1.18,"K":198,"BB":54,"SV":0,"HLD":0,"HR":20},
    {"Name":"Framber Valdez","Team":"HOU","IP":198,"W":13,"L":8,"ERA":3.44,"WHIP":1.19,"K":194,"BB":62,"SV":0,"HLD":0,"HR":14},
    {"Name":"Seth Lugo","Team":"KC","IP":192,"W":14,"L":9,"ERA":3.59,"WHIP":1.17,"K":178,"BB":46,"SV":0,"HLD":0,"HR":18},
    {"Name":"Michael Wacha","Team":"KC","IP":178,"W":13,"L":7,"ERA":3.84,"WHIP":1.22,"K":162,"BB":50,"SV":0,"HLD":0,"HR":20},
    {"Name":"Aaron Nola","Team":"PHI","IP":196,"W":14,"L":8,"ERA":3.58,"WHIP":1.16,"K":214,"BB":52,"SV":0,"HLD":0,"HR":20},
    {"Name":"Andrew Heaney","Team":"TEX","IP":164,"W":10,"L":8,"ERA":4.15,"WHIP":1.27,"K":178,"BB":54,"SV":0,"HLD":0,"HR":22},
    {"Name":"Braxton Garrett","Team":"MIA","IP":166,"W":8,"L":10,"ERA":4.01,"WHIP":1.24,"K":152,"BB":48,"SV":0,"HLD":0,"HR":18},
    {"Name":"Miles Mikolas","Team":"STL","IP":174,"W":10,"L":10,"ERA":4.22,"WHIP":1.26,"K":144,"BB":36,"SV":0,"HLD":0,"HR":22},
    {"Name":"Brady Singer","Team":"KC","IP":178,"W":11,"L":9,"ERA":3.91,"WHIP":1.22,"K":158,"BB":50,"SV":0,"HLD":0,"HR":20},
    {"Name":"Alex Cobb","Team":"SF","IP":152,"W":9,"L":8,"ERA":4.10,"WHIP":1.28,"K":138,"BB":48,"SV":0,"HLD":0,"HR":20},
    {"Name":"JP Sears","Team":"OAK","IP":178,"W":9,"L":11,"ERA":4.30,"WHIP":1.29,"K":162,"BB":52,"SV":0,"HLD":0,"HR":24},
    {"Name":"Joe Ryan","Team":"MIN","IP":188,"W":12,"L":9,"ERA":3.75,"WHIP":1.17,"K":198,"BB":44,"SV":0,"HLD":0,"HR":22},
    {"Name":"Yusei Kikuchi","Team":"TOR","IP":182,"W":10,"L":10,"ERA":3.86,"WHIP":1.19,"K":192,"BB":56,"SV":0,"HLD":0,"HR":18},
    {"Name":"Lance Lynn","Team":"STL","IP":170,"W":11,"L":9,"ERA":4.05,"WHIP":1.28,"K":162,"BB":56,"SV":0,"HLD":0,"HR":22},
    {"Name":"Colin Rea","Team":"MIL","IP":164,"W":9,"L":8,"ERA":4.12,"WHIP":1.27,"K":138,"BB":44,"SV":0,"HLD":0,"HR":20},
    {"Name":"Trevor Williams","Team":"WSH","IP":168,"W":10,"L":9,"ERA":4.21,"WHIP":1.28,"K":144,"BB":46,"SV":0,"HLD":0,"HR":22},
    {"Name":"Nick Pivetta","Team":"BOS","IP":174,"W":9,"L":11,"ERA":4.20,"WHIP":1.28,"K":168,"BB":58,"SV":0,"HLD":0,"HR":22},
    {"Name":"Marcus Stroman","Team":"NYY","IP":166,"W":10,"L":8,"ERA":3.95,"WHIP":1.25,"K":144,"BB":48,"SV":0,"HLD":0,"HR":18},
    {"Name":"David Peterson","Team":"NYM","IP":162,"W":9,"L":9,"ERA":4.08,"WHIP":1.28,"K":148,"BB":52,"SV":0,"HLD":0,"HR":18},
    {"Name":"Eli Morgan","Team":"CLE","IP":148,"W":8,"L":8,"ERA":4.25,"WHIP":1.28,"K":138,"BB":46,"SV":0,"HLD":0,"HR":20},
    {"Name":"Tanner Bibee","Team":"CLE","IP":178,"W":11,"L":8,"ERA":3.86,"WHIP":1.20,"K":178,"BB":52,"SV":0,"HLD":0,"HR":18},
    {"Name":"Garrett Crochet","Team":"CWS","IP":162,"W":8,"L":10,"ERA":3.71,"WHIP":1.19,"K":198,"BB":58,"SV":0,"HLD":0,"HR":14},
    {"Name":"Michael King","Team":"SD","IP":176,"W":11,"L":9,"ERA":3.76,"WHIP":1.19,"K":186,"BB":52,"SV":0,"HLD":0,"HR":18},
    {"Name":"Luis Castillo","Team":"SEA","IP":186,"W":12,"L":9,"ERA":3.63,"WHIP":1.18,"K":194,"BB":54,"SV":0,"HLD":0,"HR":16},
    {"Name":"Javier Assad","Team":"CHC","IP":158,"W":9,"L":8,"ERA":3.94,"WHIP":1.24,"K":142,"BB":46,"SV":0,"HLD":0,"HR":16},
    {"Name":"Chris Bassitt","Team":"TOR","IP":178,"W":11,"L":9,"ERA":4.04,"WHIP":1.24,"K":162,"BB":54,"SV":0,"HLD":0,"HR":22},
    {"Name":"Kyle Gibson","Team":"STL","IP":162,"W":9,"L":10,"ERA":4.35,"WHIP":1.30,"K":132,"BB":48,"SV":0,"HLD":0,"HR":22},
    {"Name":"Wade Miley","Team":"MIL","IP":144,"W":8,"L":8,"ERA":4.11,"WHIP":1.29,"K":118,"BB":44,"SV":0,"HLD":0,"HR":18},
    {"Name":"Kenta Maeda","Team":"DET","IP":156,"W":9,"L":9,"ERA":4.09,"WHIP":1.26,"K":148,"BB":50,"SV":0,"HLD":0,"HR":20},
    {"Name":"Jameson Taillon","Team":"CHC","IP":164,"W":10,"L":9,"ERA":4.06,"WHIP":1.25,"K":148,"BB":46,"SV":0,"HLD":0,"HR":20},
    {"Name":"Zach Eflin","Team":"TB","IP":168,"W":11,"L":8,"ERA":3.88,"WHIP":1.21,"K":156,"BB":42,"SV":0,"HLD":0,"HR":20},
    {"Name":"Dylan Cease","Team":"SD","IP":188,"W":12,"L":8,"ERA":3.54,"WHIP":1.18,"K":208,"BB":68,"SV":0,"HLD":0,"HR":16},
    {"Name":"Eduardo Rodriguez","Team":"DET","IP":158,"W":9,"L":9,"ERA":4.12,"WHIP":1.27,"K":144,"BB":54,"SV":0,"HLD":0,"HR":20},
    {"Name":"Matthew Boyd","Team":"CLE","IP":148,"W":8,"L":8,"ERA":3.98,"WHIP":1.24,"K":154,"BB":48,"SV":0,"HLD":0,"HR":18},
    {"Name":"Reese Olson","Team":"DET","IP":162,"W":8,"L":9,"ERA":4.01,"WHIP":1.25,"K":152,"BB":54,"SV":0,"HLD":0,"HR":18},
    {"Name":"Patrick Corbin","Team":"WSH","IP":154,"W":7,"L":12,"ERA":4.55,"WHIP":1.38,"K":124,"BB":54,"SV":0,"HLD":0,"HR":24},
    {"Name":"Chad Kuhl","Team":"COL","IP":142,"W":7,"L":11,"ERA":4.72,"WHIP":1.40,"K":118,"BB":56,"SV":0,"HLD":0,"HR":26},
    {"Name":"Spencer Strider","Team":"ATL","IP":72,"W":5,"L":5,"ERA":3.88,"WHIP":1.06,"K":94,"BB":18,"SV":0,"HLD":0,"HR":8},
    {"Name":"Josh Hader","Team":"HOU","IP":62,"W":3,"L":4,"ERA":3.15,"WHIP":1.05,"K":86,"BB":22,"SV":28,"HLD":0,"HR":4},
    {"Name":"Jordan Romano","Team":"TOR","IP":58,"W":2,"L":4,"ERA":3.41,"WHIP":1.14,"K":71,"BB":20,"SV":24,"HLD":0,"HR":6},
    {"Name":"Kyle Finnegan","Team":"WSH","IP":62,"W":3,"L":5,"ERA":3.62,"WHIP":1.20,"K":64,"BB":24,"SV":22,"HLD":0,"HR":6},
    {"Name":"Kenley Jansen","Team":"BOS","IP":58,"W":2,"L":4,"ERA":3.50,"WHIP":1.15,"K":62,"BB":18,"SV":20,"HLD":0,"HR":6},
    {"Name":"Andres Munoz","Team":"SEA","IP":64,"W":3,"L":3,"ERA":2.88,"WHIP":1.02,"K":84,"BB":22,"SV":18,"HLD":4,"HR":4},
    {"Name":"Pete Fairbanks","Team":"TB","IP":58,"W":3,"L":3,"ERA":3.24,"WHIP":1.10,"K":74,"BB":20,"SV":18,"HLD":2,"HR":6},
    {"Name":"Alexis Diaz","Team":"CIN","IP":62,"W":3,"L":4,"ERA":3.18,"WHIP":1.12,"K":72,"BB":24,"SV":22,"HLD":2,"HR":4},
    {"Name":"Tanner Scott","Team":"MIA","IP":60,"W":4,"L":3,"ERA":3.05,"WHIP":1.08,"K":78,"BB":26,"SV":16,"HLD":4,"HR":4},
    {"Name":"Jeff Hoffman","Team":"PHI","IP":66,"W":4,"L":3,"ERA":3.28,"WHIP":1.15,"K":76,"BB":22,"SV":6,"HLD":14,"HR":6},
    {"Name":"David Bednar","Team":"PIT","IP":62,"W":3,"L":4,"ERA":3.44,"WHIP":1.18,"K":72,"BB":24,"SV":20,"HLD":2,"HR":8},
    {"Name":"Camilo Doval","Team":"SF","IP":62,"W":3,"L":4,"ERA":3.34,"WHIP":1.16,"K":70,"BB":22,"SV":18,"HLD":2,"HR":6},
    {"Name":"Clay Holmes","Team":"PIT","IP":62,"W":4,"L":3,"ERA":3.21,"WHIP":1.12,"K":68,"BB":24,"SV":15,"HLD":4,"HR":4},
    {"Name":"Sam Moll","Team":"OAK","IP":58,"W":2,"L":3,"ERA":3.44,"WHIP":1.16,"K":64,"BB":20,"SV":0,"HLD":16,"HR":4},
    {"Name":"Phil Maton","Team":"HOU","IP":62,"W":3,"L":3,"ERA":3.58,"WHIP":1.20,"K":62,"BB":22,"SV":0,"HLD":12,"HR":6},
    {"Name":"Yimi Garcia","Team":"TOR","IP":60,"W":3,"L":3,"ERA":3.45,"WHIP":1.18,"K":66,"BB":20,"SV":0,"HLD":14,"HR":6},
    {"Name":"Scott Alexander","Team":"LAD","IP":56,"W":3,"L":2,"ERA":3.05,"WHIP":1.12,"K":52,"BB":20,"SV":0,"HLD":14,"HR":4},
    {"Name":"Ryan Pressly","Team":"HOU","IP":58,"W":3,"L":3,"ERA":3.41,"WHIP":1.16,"K":64,"BB":20,"SV":14,"HLD":0,"HR":6},
]

# ═══════════════════════════════════════════════════════════════════════════
# BUILD PLAYER POOL
# ═══════════════════════════════════════════════════════════════════════════

def build_pool():
    batters  = _sample_batters()  + _FILLER_BATTERS
    pitchers = _sample_pitchers() + _FILLER_PITCHERS

    # Score actual 2024 performance (ground truth)
    actual_bat = rank_by_score(batters,  calc_fdb_bat)
    actual_pit = rank_by_score(pitchers, calc_fdb_pit)
    actual_map = {p["Name"]: round(p["_score"], 1)
                  for p in actual_bat + actual_pit}

    # FDB projected rankings
    fdb_bat = rank_by_score(batters,  fdb_project_bat)
    fdb_pit = rank_by_score(pitchers, fdb_project_pit)
    fdb_all = sorted(fdb_bat + fdb_pit, key=lambda x: x["_score"], reverse=True)
    for i, p in enumerate(fdb_all):
        p["fdb_rank"] = i + 1

    # ESPN projected rankings
    espn_bat = rank_by_score(batters,  espn_project_bat)
    espn_pit = rank_by_score(pitchers, espn_project_pit)
    espn_all = sorted(espn_bat + espn_pit, key=lambda x: x["_score"], reverse=True)
    for i, p in enumerate(espn_all):
        p["espn_rank"] = i + 1

    # Build unified pool keyed by name
    fdb_map  = {p["Name"]: p for p in fdb_all}
    espn_map = {p["Name"]: p for p in espn_all}

    all_names = list({p["Name"] for p in fdb_all + espn_all})
    pool = []
    for nm in all_names:
        fp = fdb_map.get(nm, {})
        ep = espn_map.get(nm, {})
        is_pitcher = ("IP" in fp or "ERA" in fp or
                      "IP" in ep or "ERA" in ep)
        pool.append({
            "name":       nm,
            "team":       fp.get("Team", ep.get("Team", "")),
            "pos":        "P" if is_pitcher else "H",
            "fdb_rank":   fp.get("fdb_rank",  999),
            "espn_rank":  ep.get("espn_rank", 999),
            "actual_pts": actual_map.get(nm, 0.0),
            "signal":     fp.get("signal", ""),
        })

    # Actual rank by real points
    pool.sort(key=lambda x: x["actual_pts"], reverse=True)
    for i, p in enumerate(pool):
        p["actual_rank"] = i + 1

    fdb_order  = sorted(pool, key=lambda x: x["fdb_rank"])
    espn_order = sorted(pool, key=lambda x: x["espn_rank"])

    return pool, fdb_order, espn_order


# ═══════════════════════════════════════════════════════════════════════════
# DETAILED SNAKE DRAFT
# ═══════════════════════════════════════════════════════════════════════════

def _roster_needs(roster, by_name, n_rounds_left):
    """
    Return (need_pitcher, need_hitter) booleans for a team's current roster.

    Typical 15-round snake target: 9 hitters + 6 pitchers.
    We enforce positional balance by tracking H/P counts and flagging
    when a team is too skewed in either direction given remaining rounds.
    """
    h = sum(1 for nm in roster if by_name.get(nm, {}).get("pos") == "H")
    p = sum(1 for nm in roster if by_name.get(nm, {}).get("pos") == "P")
    total = h + p
    remaining = n_rounds_left

    # Target: roughly 9H + 6P over 15 rounds
    target_p = 6
    target_h = 9

    # Need pitcher if: 0 pitchers after 4+ picks, or trending to finish under target
    need_pitcher = (
        (h >= 4 and p == 0) or                            # 4+ hitters, no pitchers yet
        (h >= 6 and p <= 1) or                            # 6+ hitters, only 1 pitcher
        (h >= 8 and p <= 3) or                            # 8+ hitters, only 3 pitchers
        (remaining <= (target_p - p) and p < target_p)   # must draft P to hit target
    )
    # Need hitter if: too many pitchers without enough hitters
    need_hitter = (
        (p >= 4 and h <= 4) or
        (remaining <= (target_h - h) and h < target_h)
    )
    return need_pitcher, need_hitter


def run_draft(fdb_order, espn_order, n_teams=10, n_rounds=15,
              noise_pct=0.18, seed=42):
    """
    Full snake draft.  Team 0 = FDB.  Teams 1-9 = ESPN.
    Returns: picks list, roster per team, final_scores per team.

    All teams now use need-based positional enforcement so the simulated
    draft reflects realistic roster construction (hitters + pitchers) rather
    than pure BPA which would draft all hitters when hitter scores dominate.
    """
    rng = random.Random(seed)
    available = {p["name"] for p in fdb_order}

    # name → player dict for quick lookup
    by_name = {p["name"]: p for p in fdb_order}

    picks   = []          # all 150 picks in draft order
    rosters = [[] for _ in range(n_teams)]

    pick_num = 0
    for rnd in range(1, n_rounds + 1):
        forward = (rnd % 2 == 1)
        slots   = range(n_teams) if forward else range(n_teams - 1, -1, -1)
        rounds_left = n_rounds - rnd + 1   # including this round

        for slot in slots:
            pick_num += 1
            rank_list = fdb_order if slot == 0 else espn_order

            # Determine positional need for this team
            need_pitcher, need_hitter = _roster_needs(
                rosters[slot], by_name, rounds_left
            )

            if need_pitcher:
                # Force a pitcher pick — take best available pitcher
                filtered = [p for p in rank_list
                            if p["name"] in available and p["pos"] == "P"]
                chosen = next(iter(filtered), None)
                if chosen is None:
                    # No pitcher available — fall through to BPA
                    chosen = next((p for p in rank_list if p["name"] in available), None)
            elif need_hitter:
                # Force a hitter pick
                filtered = [p for p in rank_list
                            if p["name"] in available and p["pos"] == "H"]
                chosen = next(iter(filtered), None)
                if chosen is None:
                    chosen = next((p for p in rank_list if p["name"] in available), None)
            else:
                # Best player available — pure rank ordering
                chosen = next((p for p in rank_list if p["name"] in available), None)

            if chosen is None:
                continue

            available.discard(chosen["name"])
            rosters[slot].append(chosen["name"])

            picks.append({
                "overall": pick_num,
                "round":   rnd,
                "slot":    slot + 1,       # 1-indexed team number
                "is_fdb":  slot == 0,
                "name":    chosen["name"],
                "pos":     chosen["pos"],
                "fdb_rank":   chosen["fdb_rank"],
                "espn_rank":  chosen["espn_rank"],
                "actual_rank":chosen["actual_rank"],
                "actual_pts": chosen["actual_pts"],
                "signal":     chosen["signal"],
            })

    # Score each team with noise (to simulate a real season)
    final_scores = []
    for i, roster in enumerate(rosters):
        total = 0.0
        for nm in roster:
            base  = by_name[nm]["actual_pts"]
            noise = rng.gauss(0, base * noise_pct)
            total += max(0, base + noise)
        final_scores.append(round(total, 1))

    return picks, rosters, final_scores


# ═══════════════════════════════════════════════════════════════════════════
# ANNOTATE NOTABLE PICKS
# ═══════════════════════════════════════════════════════════════════════════

def notable_picks(picks):
    """
    Find picks where FDB and ESPN diverged significantly.
    Returns list of annotation dicts.
    """
    notes = []
    for p in picks:
        diff = p["espn_rank"] - p["fdb_rank"]   # positive = FDB ranked higher
        if not p["is_fdb"]:
            continue

        if diff >= 15:
            # FDB valued this player much higher than ESPN
            beat = p["actual_rank"] <= p["espn_rank"]
            notes.append({
                "overall": p["overall"],
                "round":   p["round"],
                "name":    p["name"],
                "fdb_rank":  p["fdb_rank"],
                "espn_rank": p["espn_rank"],
                "actual_rank": p["actual_rank"],
                "actual_pts":  p["actual_pts"],
                "diff":    diff,
                "signal":  p["signal"],
                "type":    "VALUE_STEAL",
                "hit":     beat,
                "note":    (f"FDB ranked #{p['fdb_rank']} vs ESPN #{p['espn_rank']} "
                            f"({diff:+d} spots higher). "
                            f"Actual finish: #{p['actual_rank']} — "
                            f"{'✓ Correct call' if beat else '✗ Miss'}."),
            })
        elif diff <= -15:
            # ESPN valued this player much higher; FDB passed
            notes.append({
                "overall": p["overall"],
                "round":   p["round"],
                "name":    p["name"],
                "fdb_rank":  p["fdb_rank"],
                "espn_rank": p["espn_rank"],
                "actual_rank": p["actual_rank"],
                "actual_pts":  p["actual_pts"],
                "diff":    diff,
                "signal":  p["signal"],
                "type":    "ESPN_HIGHER",
                "hit":     False,
                "note":    (f"ESPN ranked #{p['espn_rank']} vs FDB #{p['fdb_rank']}. "
                            f"Actual finish: #{p['actual_rank']}."),
            })

    # Also find BUST picks made by ESPN teams that FDB avoided
    busts = []
    for p in picks:
        if p["is_fdb"]:
            continue
        diff = p["espn_rank"] - p["fdb_rank"]
        if diff >= 20 and p["actual_rank"] > p["espn_rank"]:
            # ESPN team over-drafted; player underperformed
            busts.append({
                "overall": p["overall"],
                "round":   p["round"],
                "team_slot": p["slot"],
                "name":    p["name"],
                "fdb_rank":  p["fdb_rank"],
                "espn_rank": p["espn_rank"],
                "actual_rank": p["actual_rank"],
                "actual_pts":  p["actual_pts"],
                "signal":  p["signal"],
                "note":    (f"ESPN team (Team {p['slot']}) took at pick {p['overall']} "
                            f"(ESPN #{p['espn_rank']}). "
                            f"FDB ranked #{p['fdb_rank']} — avoided. "
                            f"Actual finish: #{p['actual_rank']}."),
            })
    return notes[:6], busts[:4]


# ═══════════════════════════════════════════════════════════════════════════
# BUILD DRAFT BOARD (15×10 matrix)
# ═══════════════════════════════════════════════════════════════════════════

def build_board(picks, n_teams=10, n_rounds=15):
    """Return a 2D list [round][team_slot] → pick dict."""
    board = [[None] * n_teams for _ in range(n_rounds)]
    for p in picks:
        r = p["round"] - 1
        s = p["slot"]  - 1
        board[r][s] = p
    return board


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("Building player pool…")
    pool, fdb_order, espn_order = build_pool()

    print(f"Pool: {len(pool)} players | "
          f"FDB top-5: {[p['name'] for p in fdb_order[:5]]} | "
          f"ESPN top-5: {[p['name'] for p in espn_order[:5]]}")

    seeds  = [42, 137, 999]
    drafts = []

    for i, seed in enumerate(seeds, 1):
        print(f"\nSimulating Draft #{i} (seed={seed})…")
        picks, rosters, final_scores = run_draft(
            fdb_order, espn_order, seed=seed)

        value_notes, bust_notes = notable_picks(picks)
        board = build_board(picks)

        fdb_pts   = final_scores[0]
        fdb_rank  = sorted(final_scores, reverse=True).index(fdb_pts) + 1
        opponent_avg = round(sum(final_scores[1:]) / len(final_scores[1:]), 1)

        # Condensed board for JSON (just name + pts per cell)
        board_slim = []
        for row in board:
            board_slim.append([
                {"name": c["name"], "pts": c["actual_pts"],
                 "pos": c["pos"],   "signal": c["signal"],
                 "fdb_r": c["fdb_rank"], "espn_r": c["espn_rank"],
                 "act_r": c["actual_rank"]}
                if c else None
                for c in row
            ])

        drafts.append({
            "draft_num":    i,
            "seed":         seed,
            "final_scores": final_scores,
            "fdb_pts":      fdb_pts,
            "fdb_rank":     fdb_rank,
            "opponent_avg": opponent_avg,
            "pts_vs_avg":   round(fdb_pts - opponent_avg, 1),
            "value_steals": value_notes,
            "busts_avoided":bust_notes,
            "board":        board_slim,
            "fdb_roster":   [p for p in picks if p["is_fdb"]],
        })

        print(f"  FDB team: {fdb_pts:.0f} pts → "
              f"finished #{fdb_rank}/10 | "
              f"opp avg: {opponent_avg:.0f} | "
              f"value steals: {len(value_notes)}")

    out = ROOT / "tools" / "draft_logs.json"
    with open(out, "w") as f:
        json.dump({"drafts": drafts, "n_teams": 10, "n_rounds": 15}, f, indent=2)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
