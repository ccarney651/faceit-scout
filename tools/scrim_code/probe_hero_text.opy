# OWDB probe: does a Hero value render as readable TEXT or as a glyph?
#
# Standalone throwaway. Nothing imports it and it shares no code with
# scrim_owdb.opy - paste it into an empty custom game, look at the screen,
# delete the lobby. It answers the one question specs/2026-08-27-scrim-hero-bans-design.md
# calls load-bearing (see its section 2): the hero-ban feature reads hero names
# off the spectator view with OCR, which only works if a bare Hero renders as
# its name. heroIcon() exists to convert a hero INTO an icon, which implies the
# default is text - but "implies" is not "checked in game".
#
# Every row is SpecVisibility.ALWAYS, so it also answers whether a spectator
# and a replay see the same thing the players do.
#
# Build:  npx overpy compile -i probe_hero_text.opy -o probe_hero_text.txt
# Then:   Custom Game > Settings > Workshop > Import Code > paste the .txt

globalvar Probe_White 0
globalvar Probe_Amber 1
globalvar Probe_Green 2


rule "Probe: Colours":
    Probe_White = rgb(255, 255, 255)
    Probe_Amber = rgb(255, 155, 0)
    Probe_Green = rgb(40, 205, 60)


rule "Probe: Hero rendering":
    hudHeader(getAllPlayers(), "OWDB PROBE - hero name rendering", HudPosition.LEFT, 0,
              Probe_White, HudReeval.VISIBILITY, SpecVisibility.ALWAYS)

    # ROW 1 - the question. A bare Hero embedded in a string.
    # Chosen for the spellings that break naive matching: an accent, a full
    # stop, a colon, an umlaut, and a two-word name.
    hudSubheader(getAllPlayers(), "TEXT A: {0} / {1} / {2}".format(
                     Hero.LUCIO, Hero.DVA, Hero.TORBJORN),
                 HudPosition.LEFT, 1, Probe_Green,
                 HudReeval.VISIBILITY, SpecVisibility.ALWAYS)

    hudSubheader(getAllPlayers(), "TEXT B: {0} / {1} / {2}".format(
                     Hero.SOLDIER, Hero.WRECKING_BALL, Hero.JUNKER_QUEEN),
                 HudPosition.LEFT, 2, Probe_Green,
                 HudReeval.VISIBILITY, SpecVisibility.ALWAYS)

    # ROW 2 - the control. The SAME heroes forced through heroIcon().
    # If row 1 and row 2 look the same, a bare Hero is a glyph and the ban
    # feature needs a workshop glyph reference set (design section 2).
    hudSubheader(getAllPlayers(), "ICON  : {0} {1} {2}".format(
                     heroIcon(Hero.LUCIO), heroIcon(Hero.DVA), heroIcon(Hero.TORBJORN)),
                 HudPosition.LEFT, 3, Probe_Amber,
                 HudReeval.VISIBILITY, SpecVisibility.ALWAYS)

    # ROW 3 - the second assumption, free to check while you are here.
    # If this reads as the map's name, capture can verify the map off the HUD
    # instead of trusting the operator's panel selection, which closes the
    # "map-name verification is stubbed" item in specs/BACKLOG.md.
    hudSubheader(getAllPlayers(), "MAP   : {0}".format(getCurrentMap()),
                 HudPosition.LEFT, 4, Probe_White,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)

    # ROW 4 - the shape the real feature would draw, so you can judge it in
    # place against the scoreboard rather than in the abstract.
    hudSubheader(getAllPlayers(), "BANS  : {0} | {1}".format(Hero.SOMBRA, Hero.MAUGA),
                 HudPosition.LEFT, 5, Probe_White,
                 HudReeval.VISIBILITY, SpecVisibility.ALWAYS)
