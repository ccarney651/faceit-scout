#!suppressWarnings w_string_concat w_optimization_change_semantics
#
# OWDB Scrim Code  (v0.1)
# A lean, performance-first Overwatch 2 Workshop script for running scrims.
# Goals:
#   - Setup phase with ready-up, add-time, and defender teleport.
#   - A spectator-only, replay-visible scoreboard at the top-left that the
#     OWDB capture tool can OCR (fixed 5-row blocks per team, slot-indexed
#     so slot N of a team aligns with HUD portrait slot N).
#   - Optional per-player stat counters (K/D/damage/healing) driven by event
#     rules only -- NO per-tick reevaluation and NO log generation, so the
#     host FPS cost stays well below Scrimtime (DKEEH).
#
# The map-flow conventions (Control/Flashpoint "play all points", Hybrid/Escort
# "full attack for both teams", "play it out" extra turns) are lobby settings,
# not workshop logic; see README.md for the recommended lobby configuration.
#
# Compile with:  npx overpy compile -i main.opy -o out/scrim_owdb.txt
# Import in-game: Custom Game > Create > Settings > Import Code.
# Share code is minted in-game (Settings > Copy Settings) -- there is no way to
# mint one programmatically.

# ---------------------------------------------------------------------------
# Tweakable constants (edit here, recompile).
# ---------------------------------------------------------------------------
macro SETUP_TIME_LIMIT    = 90      # seconds of setup shown on the top timer
macro SETUP_TIME_MAX      = 180     # cap after +30s presses
macro SETUP_EXTRA_STEP    = 30      # seconds added per Interact+Q press
macro SETUP_FAST_FORWARD  = 5       # countdown left when everyone is ready
macro FORCE_READY_HOLD    = 3       # seconds to hold Interact+Reload to ready a team
macro STATS_ENABLED       = true    # K/D/damage/healing counters (event-driven)
macro SCOREBOARD_ENABLED  = true    # spectator scoreboard HUD

# ---------------------------------------------------------------------------
# State.
# ---------------------------------------------------------------------------
globalvar initialized
globalvar setup_active
globalvar ready_count
globalvar scoreboard_id

globalvar loop_i
globalvar allp
globalvar cur
globalvar cur2
globalvar cur3
globalvar sb_header
globalvar sb_body

playervar is_ready
playervar ready_edge
playervar time_edge
playervar tp_edge
playervar force_hold
playervar tp_return

playervar kills
playervar deaths
playervar dmg_dealt
playervar dmg_taken
playervar healing

# ---------------------------------------------------------------------------
# Init.
# ---------------------------------------------------------------------------
rule "init":
    @Event global
    @Condition not initialized
    initialized = true
    setup_active = true
    ready_count = 0
    scoreboard_id = null
    setMatchTime(SETUP_TIME_LIMIT)

# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def recountReady():
    @Name "Recount ready players"
    ready_count = 0
    allp = getPlayers(Team.ALL)
    for loop_i in range(0, getNumberOfPlayers(Team.ALL)):
        if allp[loop_i].is_ready:
            ready_count += 1

# ---------------------------------------------------------------------------
# Setup phase.
# ---------------------------------------------------------------------------
rule "setup: ready and gestures":
    @Event eachPlayer
    @Condition setup_active

    # Interact + Reload toggles personal ready.
    cur = eventPlayer.isHoldingButton(Button.INTERACT) and eventPlayer.isHoldingButton(Button.RELOAD)
    if cur and not eventPlayer.ready_edge:
        eventPlayer.is_ready = not eventPlayer.is_ready
        recountReady()
    eventPlayer.ready_edge = cur

    # Holding Interact + Reload force-readies the whole team.
    if cur:
        eventPlayer.force_hold += 0.05
        if eventPlayer.force_hold >= FORCE_READY_HOLD:
            allp = getPlayers(eventPlayer.getTeam())
            for loop_i in range(0, getNumberOfPlayers(eventPlayer.getTeam())):
                allp[loop_i].is_ready = true
            recountReady()
            eventPlayer.force_hold = 0
    else:
        eventPlayer.force_hold = 0

    # Interact + Ultimate adds setup time.
    cur2 = eventPlayer.isHoldingButton(Button.INTERACT) and eventPlayer.isHoldingButton(Button.ULTIMATE)
    if cur2 and not eventPlayer.time_edge:
        setMatchTime(min(getMatchTime() + SETUP_EXTRA_STEP, SETUP_TIME_MAX))
    eventPlayer.time_edge = cur2

    # Interact + Jump teleports between spawn and objective (defense practice).
    cur3 = eventPlayer.isHoldingButton(Button.INTERACT) and eventPlayer.isHoldingButton(Button.JUMP)
    if cur3 and not eventPlayer.tp_edge:
        if eventPlayer.isInSpawnRoom():
            eventPlayer.tp_return = eventPlayer.getPosition()
            eventPlayer.teleport(getObjectivePosition(0))
        elif eventPlayer.tp_return != null:
            eventPlayer.teleport(eventPlayer.tp_return)
            eventPlayer.tp_return = null
    eventPlayer.tp_edge = cur3

    wait(0.05)

rule "setup: fast-forward when ready":
    @Event global
    @Condition setup_active
    if ready_count >= getNumberOfPlayers(Team.ALL) and getNumberOfPlayers(Team.ALL) >= 6:
        if getMatchTime() > SETUP_FAST_FORWARD:
            setMatchTime(SETUP_FAST_FORWARD)

rule "setup: hand off to the match":
    @Event global
    @Condition setup_active
    if getMatchTime() <= 0.5:
        setup_active = false

# ---------------------------------------------------------------------------
# Optional stat counters (event-driven; only while playing).
# NOTE: top-level `if` is NOT a compile-time conditional in OverPy (it becomes
# a runtime rule), so to disable stats/scoreboard, comment out the rules below.
# ---------------------------------------------------------------------------
rule "stats: damage dealt":
    @Event playerDealtDamage
    @Condition not setup_active
    eventPlayer.dmg_dealt += eventDamage

rule "stats: damage taken":
    @Event playerTookDamage
    @Condition not setup_active
    eventPlayer.dmg_taken += eventDamage

rule "stats: healing dealt":
    @Event playerDealtHealing
    @Condition not setup_active
    eventPlayer.healing += eventHealing

rule "stats: final blows":
    @Event playerDealtFinalBlow
    @Condition not setup_active
    eventPlayer.kills += 1

rule "stats: deaths":
    @Event playerDied
    @Condition not setup_active
    eventPlayer.deaths += 1

# ---------------------------------------------------------------------------
# Spectator scoreboard (top-left, rebuilt once per second).
# Row slot numbers align with the observer HUD portrait strips, so the OWDB
# capture tool can map scoreboard rows to comp slots 1:1.
# ---------------------------------------------------------------------------
macro scoreboardRow(p, slot):
    if STATS_ENABLED:
        "{} {} K{} D{} {} | {} {} H{} {}".format(
            slot, p.getEffectiveHero(), round(p.kills), round(p.deaths), round(p.dmg_dealt),
            slot, p.getEffectiveHero(), round(p.healing), round(p.dmg_taken))
    else:
        "{} {}".format(slot, p.getEffectiveHero())

rule "scoreboard: rebuild":
    @Event global
    @Condition not setup_active
    if scoreboard_id != null:
        destroyHudText(scoreboard_id)
    sb_header = "OW SCOUT SCRIM  {} - {}".format(
        teamScore(Team.TEAM_1), teamScore(Team.TEAM_2))
    sb_body = "TEAM 1"
    for loop_i in range(1, 6):
        allp = getPlayersInSlot(loop_i, Team.TEAM_1)
        if allp != null:
            sb_body = sb_body + "\n" + scoreboardRow(allp, loop_i)
        else:
            sb_body = sb_body + "\n{} EMPTY".format(loop_i)
    sb_body = sb_body + "\nTEAM 2"
    for loop_i in range(1, 6):
        allp = getPlayersInSlot(loop_i, Team.TEAM_2)
        if allp != null:
            sb_body = sb_body + "\n" + scoreboardRow(allp, loop_i)
        else:
            sb_body = sb_body + "\n{} EMPTY".format(loop_i)
    hudText(visibleTo=getAllPlayers(), header=sb_header, text=sb_body, location=HudPosition.LEFT, sortOrder=0, headerColor=Color.SKY_BLUE, textColor=Color.WHITE, specVisibility=SpecVisibility.ALWAYS)
    scoreboard_id = getLastCreatedText()
    wait(1)
