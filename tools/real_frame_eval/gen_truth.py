"""Emit ground truth for the frames in screenshots/, as truth.json.

Each frame shows its replay code, which resolves in faceit.sqlite3 to a match
and game and therefore to the exact five-player, role-tagged lineup per team.
The HUD *slot order* is not in the database - it was read off the frames by eye
(see the montages in the crop-eval notes) and is recorded here as `hud`, the
text the HUD actually renders. `hud` and the stored `game_name` differ for
three of the twenty players, which is the point: OCR is scored against what is
on screen, the matcher against what FACEIT stored.
"""
import json
import pathlib
import sqlite3
import sys

# frame stem -> replay code -> side -> HUD slot order, by FACEIT nickname.
FRAMES = {
    '200028': ('K3A6HZ', {
        'a': ['Proxystyle', 'Mappsy', 'sexy_eden', 'Arclite', 'SzatanOW'],
        'b': ['HybridOW', 'NitroxOW', 'kronus_ow', 'zydra_ow', 'scraine'],
    }),
    'image': ('GPJW93', {
        'a': ['mellun', 'twobleed', 'DazedReox', 'envii_ow', 'hzl113'],
        'b': ['Aufy', 'Maquade', 'Ga1rou', 'BuFayez2', 'jamal1505'],
    }),
}
for stem, code in (('231525', 'TJDE6W'), ('231549', 'TJDE6W'), ('231604', 'TJDE6W'),
                   ('231629', 'H6R64B'), ('231639', 'H6R64B'), ('231647', 'H6R64B'),
                   ('231657', 'H6R64B')):
    FRAMES[stem] = (code, FRAMES['200028'][1])

# What the HUD renders, where it differs from players.game_name.
HUD = {'Arclite': 'JODAN', 'hzl113': 'HZL', 'Maquade': 'ØØØØØ'}

db = sqlite3.connect('faceit.sqlite3')
db.row_factory = sqlite3.Row
out = {}
for stem, (code, sides) in FRAMES.items():
    g = db.execute('select match_id, game_no from games where demo_code=?', (code,)).fetchone()
    lineup = {}
    for r in db.execute("""select rp.team_id, rp.role, p.id, p.nickname, p.game_name
                           from round_players rp join players p on p.id=rp.player_id
                           where rp.match_id=? and rp.game_no=?""", (g['match_id'], g['game_no'])):
        lineup[r['nickname']] = dict(r)
    frame = {'code': code, 'match_id': g['match_id'], 'game_no': g['game_no'], 'sides': {}}
    for side, order in sides.items():
        slots = []
        for nick in order:
            p = lineup[nick]
            game, nk = (p['game_name'] or '').strip(), p['nickname'].strip()
            slots.append({
                'id': p['id'], 'nick': nk, 'role': p['role'],
                'names': list(dict.fromkeys(n for n in (game, nk) if n)),
                'hud': HUD.get(nk, game or nk),
            })
        frame['sides'][side] = slots
    out[stem] = frame

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'truth.json')
path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
print('wrote', path, len(out), 'frames')
