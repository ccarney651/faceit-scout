# OWDB Scrim - lean custom game code for scrim practice / tracking.
#
# This is a stripped derivative of Scrimtime (DKEEH) v1.73 by Caldoran,
# kept for this team's own private scrim use.  Bloat removed:
#   - Log Generator (all ~20 event-driven log rules + per-event tracking)
#   - Multi-language UI (40x7 language strings, Change Language keybind)
#   - Debug mode rules + settings
#   - Legacy scoreboard presets (Legacy Standard, Legacy OWL/OWC)
#   - Disabled mode presets
# Remaining feature set:
#   - Setup phase: ready up, force-team-ready, add setup time, defender teleport
#   - Map completion handling (Assault/Escort/Hybrid full attack, Control @3, Flashpoint @5)
#   - Spectator scoreboard (Standard preset, all sizes + grouping styles),
#     visible to spectators AND in replays (SpecVisibility.ALWAYS) - this is
#     what the OWDB capture tool OCRs.
#   - Match time display, host-spectator scoreboard toggle
# The in-game "Settings" panel (1-5) retains the original tunables.
#
# Build:  npx overpy compile -i scrim_owdb.opy -o scrim_owdb.txt
# Import: Custom Game > Create > Settings > Import Code, paste scrim_owdb.txt

# Right-align a number in a fixed field. The HUD font is monospace - measured
# off a real frame, six strings of different letters all came out at 10.2-10.7
# pixels per character - so padding by character count genuinely aligns columns.
#
# Numbers can be padded because their magnitude is known. A NAME cannot: the
# Workshop has no runtime string length (len() compiles to Count Of, which does
# not count characters) and no string slicing, so there is no way to pad a name
# to a fixed width. That is why the name goes LAST in a row, after everything
# that needs to line up.
settings {
    "main": {
        "description": "OWDB Scrim (lean strip of workshop.codes/scrimtime)",
        "modeName": "OWDB Scrim"
    },
    "lobby": {
        "mapRotation": "afterGame",
        "spectatorSlots": 12,
        "pauseGameOnDisconnect": true,
        "returnToLobby": "afterGame"
    },
    "gamemodes": {
        "clash": {
            "captureSpeed%": 45,
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "control": {
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "scoreToWin": 3,
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "escort": {
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "flashpoint": {
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "scoreToWin": 5,
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "hybrid": {
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "push": {
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "tankPassiveHealthBonus": "alwaysEnabled"
        }
    },
    "workshop": {
        "Add Setup Time": [
            4
        ],
        "Command": [
            5
        ],
        "Control Point Progress Increment": 33.3,
        "Defender Teleport": [
            6
        ],
        "Payload Progress Increment": 10,
        "Ready Up Toggle  Force Team Ready": [
            9
        ]
    }
}

#Global variables

globalvar Keybind_ButtonArray 0
globalvar Keybind_Command 1
globalvar Keybind_Ready 2
globalvar Keybind_DefenderTeleport 3
globalvar Keybind_AddSetupTime 4
globalvar Ban_Enabled 38
globalvar Ban_Team1 39
globalvar Ban_Team2 40
globalvar Keybind_BanHero 41
globalvar Debug_DisplayServerLoad 42
globalvar Ban_HudTo 43
globalvar Ban_HoldTime 45
globalvar Colour_Heading 46
globalvar Colour_Key 47
# Session-wide server load statistics. Every value Overwatch exposes is a
# TWO-SECOND window - getAverageServerLoad() and getPeakServerLoad() both say so
# in their own tooltips - so "peak" decays and nothing tells you what a whole map
# actually did. These accumulate instead, and only exist while 6. Debug is on.
globalvar Debug_LoadMax 48
globalvar Debug_LoadSum 49
globalvar Debug_LoadSamples 50
globalvar Debug_LoadOver200 51
globalvar Debug_LoadText 52
# Raw samples, kept so the DISTRIBUTION can be reported and not just its mean.
# Capped at 1200 (20 minutes at 1 Hz); n on the readout shows whether you hit it.
globalvar Debug_LoadHistory 31
globalvar Debug_LoadSorted 53
globalvar Debug_LoadText2 54
# Bounds the board for the capture tool - see "Scoreboard: Create Capture Markers".
globalvar Scoreboard_CaptureMarkers 55
globalvar Keybind_ClearBan 44
globalvar Colour_TeamOne 5
globalvar Colour_TeamTwo 6
globalvar Colour_TextTypeA 7
globalvar Colour_TextTypeB 8
globalvar Colour_TextTypeC 9
globalvar Match_CurrentMatchTime 10
globalvar Setup_RemoveAssemblingHeroes 11
globalvar Setup_SetupTimeOverride 12
globalvar Setup_AllowDefendersTeleport 13
globalvar ReadyUp_FreqMode 14
globalvar ReadyUp_CaptainMode 15
globalvar ReadyUp_EnableReadyVoiceLine 16
globalvar ReadyUp_MinimumPlayersToStart 17
globalvar ReadyUp_SetupCountdownTime 18
globalvar ReadyUp_FreezeSetupTime 19
globalvar ReadyUp_AllowForceTeamReady 20
globalvar ReadyUp_ForceTeamReadyHoldTime 21
globalvar MapComp_EnableMapCompletion 22
globalvar MapComp_ForceAsymTwoRounds 23
globalvar MapComp_ForceControlThreeRounds 24
globalvar MapComp_ForceFlashpointFiveCaps 25
globalvar MapComp_TeamOneScore 26
globalvar MapComp_TeamTwoScore 27
globalvar Scoreboard_EnableScoreboard 28
globalvar Scoreboard_AllowHideScoreboard 29
globalvar Scoreboard_HideScoreboardID 30
globalvar Scoreboard_GroupMode 32
globalvar Scoreboard_Size 33
globalvar Scoreboard_DisplayMatchTime 34
globalvar SetupAddTime_CaptainMode 35
globalvar SetupAddTime_Step 36
globalvar SetupAddTime_Max 37

#Player variables

playervar ReadyUp_PlayerReady 0
playervar ReadyUp_CurrentHoldTime 1
# How long this player has been holding the ban (or clear-ban) chord.
# One variable for both because you cannot hold both at once, and one
# progress bar reads it.
playervar Ban_CurrentHoldTime 2
# The player's scoreboard row, rebuilt on a timer instead of inside the
# HUD string - see "Scoreboard: Build Row Text".
playervar Scoreboard_Row 3
# The row's SORT ORDER, rebuilt on the same timer and for the same reason.
# A hud text created with SORT_ORDER re-evaluation resolves its sort
# expression continuously, and in the role-grouped layout that expression
# was two Array Contains scans over the hero lists - per player, forever.
# Resolving a variable instead is, in Blizzard's own words about Event
# Player, "practically free". See "Scoreboard: Build Row Text".
playervar Scoreboard_Sort 4

#Only remove the following directive if the gamemode does not use tricks such as A+0, A*0, A or "", "am" == "**", etc which would otherwise be optimized out.
#!optimizeStrict

# Two bans may not share a role. A macro rather than a subroutine because
# Workshop subroutines take no parameters and return no value. The role getters
# are dynamic, so a new Overwatch hero needs no change here.
macro Ban_SameRole(hero, other):
    other != null and ((hero in getTankHeroes() and other in getTankHeroes())
        or (hero in getDamageHeroes() and other in getDamageHeroes())
        or (hero in getSupportHeroes() and other in getSupportHeroes()))


def Ban_Apply():
    @Name "Subroutine: Apply hero bans"
    # "If a player's current hero becomes unavailable, the player is forced to
    # choose a different hero and respawn" - which doubles as the visible
    # confirmation that the ban took. `null` never equals a hero, so one ban,
    # two bans and none all fall out of the same filter.
    if Ban_Team1 == null and Ban_Team2 == null:
        getAllPlayers().resetHeroAvailability()
    else:
        getAllPlayers().setAllowedHeroes(getAllHeroes().filter(
            lambda h: h != Ban_Team1 and h != Ban_Team2))


rule "Settings: Debug Options":
    # Default OFF: with the setting false the rule's condition never holds, no
    # HUD text is created, and this costs nothing in a normal scrim. Panel 6 was
    # free because the strip removed the Log Generator.
    Debug_DisplayServerLoad = createWorkshopSettingBool("6. Debug", "Display Server Load", false)


rule "Settings: Hero Ban Options":
    Ban_Enabled = createWorkshopSettingBool("1. Hero Bans", "Enable Hero Bans", true)
    # Banning is HELD, not pressed. A ban applies to both teams for the whole
    # map and force-swaps anyone already on the hero, so a stray keypress in
    # setup is expensive to undo - and Command+Melee is exactly the kind of
    # thing a player does by accident while warming up in spawn.
    Ban_HoldTime = createWorkshopSettingInt("1. Hero Bans", "Ban Hold Time", 2, 1, 5, 1)


rule "Settings: Ready Up Options":
    ReadyUp_FreqMode = createWorkshopSettingEnum("2. Ready Up System", "Enable Ready Up System", 0, ["Every Round", "Only Round One", "Off"])
    ReadyUp_CaptainMode = createWorkshopSettingEnum("2. Ready Up System", "Who Needs To Ready Up", 0, ["All Players", "Only Players in First Slot"], 1)
    ReadyUp_AllowForceTeamReady = createWorkshopSettingBool("2. Ready Up System", "Allow Players to Force Team Ready", true, 2)
    ReadyUp_ForceTeamReadyHoldTime = createWorkshopSettingInt("2. Ready Up System", "Force Team Ready Button Hold Time", 3, 1, 5, 3)
    ReadyUp_SetupCountdownTime = createWorkshopSettingInt("2. Ready Up System", "Countdown Timer", 5, 5, 10, 4)
    ReadyUp_MinimumPlayersToStart = createWorkshopSettingInt("2. Ready Up System", "Minimum Number of Players in Game", 10, 1, 10, 5)
    ReadyUp_FreezeSetupTime = createWorkshopSettingBool("2. Ready Up System", "Freeze Setup Timer", false, 6)
    ReadyUp_EnableReadyVoiceLine = createWorkshopSettingBool("2. Ready Up System", "Play Voice Line When Readying", true, 7)


rule "Settings: Setup Phase Options":
    Setup_RemoveAssemblingHeroes = createWorkshopSettingBool("3. Setup Phase", "Remove Assembling Heroes Phase", true)
    Setup_AllowDefendersTeleport = createWorkshopSettingBool("3. Setup Phase", "Allow Defenders to Teleport Between Objective and Spawn", true, 1)
    Setup_SetupTimeOverride = createWorkshopSettingInt("3. Setup Phase", "Base Setup Time", 60, 45, 300, 2)
    SetupAddTime_CaptainMode = createWorkshopSettingEnum("3. Setup Phase", "Who Can Add Setup Time", 0, ["All Players", "Only Players in First Slot", "Off"], 3)
    SetupAddTime_Step = createWorkshopSettingInt("3. Setup Phase", "Setup Time Added", 30, 1, 60, 4)
    SetupAddTime_Max = createWorkshopSettingInt("3. Setup Phase", "Setup Time Maximum", 90, 45, 600, 5)


rule "Settings: Map Completion Options":
    MapComp_EnableMapCompletion = createWorkshopSettingBool("4. Map Completion", "Ensure Full Map is Attacked on Round 2 for Assault, Escort and Hybrid Maps", true)
    MapComp_ForceAsymTwoRounds = createWorkshopSettingEnum("4. Map Completion", "End Assault, Escort and Hybrid Maps After Two Rounds", 0, ["If either team fails to complete map", "Always", "Off"], 1)
    MapComp_ForceControlThreeRounds = createWorkshopSettingBool("4. Map Completion", "End Control Maps After Three Rounds", true, 2)
    MapComp_ForceFlashpointFiveCaps = createWorkshopSettingBool("4. Map Completion", "End Flashpoint Maps After Five Captures", true, 3)


rule "Settings: Spectator Scoreboard Options":
    Scoreboard_EnableScoreboard = createWorkshopSettingBool("5. Spectator Scoreboard", "Enable Spectator Scoreboard", true)
    Scoreboard_Size = createWorkshopSettingEnum("5. Spectator Scoreboard", "Size", 0, ["Small", "Medium", "Large"], 1)
    # "Group by role, sort by team" is GONE. It interleaved the two teams inside
    # each role block, which is the one layout that cannot be attributed to a
    # player - each team's DPS and support pairs are indistinguishable without
    # recognising the hero icon, an image. Both surviving layouts group by team,
    # so the board can carry a TEAM 1 / TEAM 2 header, which is what replaced
    # colour as the thing that separates the sides.
    #
    # Slot ordering is first and the default: row i is slot i, the spectator
    # portrait bar is in slot order too, and the join needs no icon recognition
    # at all. See specs/2026-09-06-scoreboard-capture-design.md.
    Scoreboard_GroupMode = createWorkshopSettingEnum("5. Spectator Scoreboard", "Player Grouping Style", 0, ["Group by team, sort by slot", "Group by team, sort by role"], 2)
    Scoreboard_DisplayMatchTime = createWorkshopSettingBool("5. Spectator Scoreboard", "Display Match Time", true, 4)
    Scoreboard_AllowHideScoreboard = createWorkshopSettingBool("5. Spectator Scoreboard", "Allow Host Spectator to Toggle Scoreboard", true, 5)
    # Default ON: the markers exist so the capture tool can find the board
    # without a human drawing a box over it, and the hand-drawn box was
    # measured to matter - a crop 50% larger than the board halves the read
    # (7/8 frames accepted at the true extent, 4/8 at +50%). A host who
    # dislikes them can switch them off; the tool falls back to its manual box.
    Scoreboard_CaptureMarkers = createWorkshopSettingBool("5. Spectator Scoreboard", "Draw Capture Markers", true, 6)


rule "Settings: Keybind Options":
    Keybind_ButtonArray = [Button.PRIMARY_FIRE, Button.SECONDARY_FIRE, Button.ABILITY_1, Button.ABILITY_2, Button.ULTIMATE, Button.INTERACT, Button.JUMP, Button.CROUCH, Button.MELEE, Button.RELOAD]
    Keybind_Command = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Command", 5, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"])]
    Keybind_Ready = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Ready Up Toggle / Force Team Ready", 9, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 1)]
    Keybind_DefenderTeleport = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Defender Teleport", 6, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 2)]
    Keybind_AddSetupTime = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Add Setup Time", 4, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 3)]
    Keybind_BanHero = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Ban Hero", 8, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 4)]
    Keybind_ClearBan = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Clear Hero Ban", 7, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 5)]


rule "Initialisation: Match":
    disableInspector()


rule "Initialisation: Colours":
    Colour_TeamOne = rgb(50, 185, 240)
    # Since the stat rows went back to white this colours the TEAM 2 HEADER and
    # the ready-up subtext, not a row of digits - so its job is now to be read
    # by a human and by teamFromLine(), one short word and one digit.
    #
    # Was rgb(250,5,30) - a DARK colour wearing a bright one's name, at
    # luminance 54 - then rgb(255,135,140) to lift it. The lift worked and
    # overshot: at blue 140 it reads as PINK rather than red.
    #
    # BACK TO THE ORIGINAL DEEP RED on 2026-09-06, on the operator's call after
    # seeing all three in game. Both lifts were chasing an OCR problem that this
    # colour no longer has: it stopped being a row of digits when the stat rows
    # went white, and what it now carries is the word "TEAM 2" and its digit.
    #
    # The cost is real but bounded, and the measurements below say where it
    # lands. Luminance 54 was the WORST value tested on a dark map (2.75 of six
    # numbers per row against 5.00 at luminance 156) and the JOINT-BEST on a
    # bright one. So this is not simply the worse choice - it is the better half
    # of a trade that reverses with the map, taken on a line whose only reader
    # is teamFromLine(), matching one short word rather than six numbers.
    #
    # What to watch: if team detection starts failing on DARK maps specifically,
    # this is the first thing to suspect, and lifting it is the known fix.
    #
    # The rest of this block is the measurement record for that trade. Luminance
    # 124 was the middle choice it replaces, and the reason a middle existed at
    # all is that THERE IS NO LUMINANCE THAT WINS ON BOTH KINDS OF MAP.
    #
    # Measured on the two 2026-09-06 Busan frames - a BRIGHT map, where the
    # background sits at 200-255, above every colour this board can draw - by
    # recolouring the real TEAM 2 rows in place, same font, same background,
    # same outline, only the glyph colour changed. Those rows are white now, so
    # read this as a luminance curve for the board's text generally, which is
    # what it is; the header sits on the same pixels:
    #
    #   luminance   54    97   124   161   196   228
    #   raw crop    18    14    15    18     8     7   of 48 values
    #   sat pass    28    29    29    30    25    18
    #
    # The ORDER IS INVERTED against the dark-map measurement above. There,
    # luminance 54 recovered 2.75 numbers per row and 156 recovered 5.00. Here,
    # 54 is joint-best and the two brightest are the worst - because on a white
    # map the text needs to be DARKER than its background, not brighter.
    #
    # Both measurements say the same thing: contrast, not colour. They disagree
    # about the sign because the maps do. A fixed colour cannot satisfy both, so
    # the fix belongs on the CAPTURE side, where the same frames go from 27 to
    # 66 of 96 values on a preprocessing change alone - larger than the whole
    # luminance range above. See specs/2026-09-06-scoreboard-capture-design.md.
    #
    # What 124 buys is the middle: inside the readable band at both ends (69-161
    # is flat here; 54 is the failure on a dark map, 196+ the failure on a light
    # one) rather than optimal at either. Hue within that band does not separate,
    # which is what leaves the pink-vs-red call free to be made on looks.
    #
    # Against team blue's 160 and the orange heading's 165, the deep red is the
    # darkest thing on the board by a wide margin, which is exactly what makes
    # it unmistakable as the red team and impossible to confuse with the orange
    # chrome. That separation is what it was picked for.
    Colour_TeamTwo = rgb(250, 5, 30)
    Colour_TextTypeA = rgb(255, 255, 255)
    Colour_TextTypeB = rgb(255, 155, 0)
    Colour_TextTypeC = rgb(40, 205, 60)
    # The board's chrome: ONE orange for the headings and the column key alike,
    # so BANS, MAP and the key read as a single block, separate from the white
    # data and from the two team labels.
    #
    # This was two tones - the key dropped to rgb(205,140,45) to recede - and is
    # one again on 2026-09-06, on the operator's call after seeing it in game.
    # Note it is NOT the arrangement rejected further down under "Create Legend":
    # that one made the KEY the loudest line by giving it orange while the
    # headings took a duller gold. Levelling them removes the hierarchy rather
    # than inverting it, which is a different thing and a defensible one - the
    # key is a heading, so it can look like the other headings.
    #
    # Colour_Heading is Overwatch's own orange, the same value the ready-up
    # hints use (Colour_TextTypeB), because that is the look being matched.
    #
    # It sits at luminance 165 of 255, which is lower than the 194 this was
    # first set to and worth stating plainly: OCR reads by contrast, and 160 is
    # roughly where the team-coloured stat ROWS stopped being readable. BANS
    # survives it where a row would not, for reasons measured rather than hoped
    # - it is one short line of larger text, and engine/banrow.js finds it by a
    # textual anchor that tolerates a mangled read, including the colon going
    # missing entirely, which is what a real frame did.
    #
    # The key is the one line the parser never reads - it recognises it only in
    # order to skip it - so its colour is free to be chosen on looks alone.
    Colour_Heading = rgb(255, 155, 0)
    # Assigned FROM the heading rather than repeating the literal, so the two
    # cannot drift apart: change the heading and the key follows. Kept as its
    # own variable so they can be split again without touching every call site.
    Colour_Key = Colour_Heading


rule "Initialisation: Player":
    @Event eachPlayer
    
    eventPlayer.ReadyUp_PlayerReady = false


rule "HUD Setup: Setup Info":
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    
    # FOUR OF THESE FIVE ARE HudReeval.VISIBILITY, NOT VISIBILITY_AND_STRING.
    # Their strings are literals - a title, a fixed sentence, and the two team
    # constants - so re-evaluating the string re-derives a value that cannot
    # have changed. Visibility still re-evaluates, because getAllPlayers() is
    # genuinely dynamic: somebody joining or leaving has to be picked up.
    #
    # The ready counter below keeps its string re-evaluation. It is the one
    # line here whose text actually changes, and it changing live is the point
    # of it.
    hudSubtext(getAllPlayers(), "OWDB SCRIM", HudPosition.LEFT, 0, Colour_TextTypeB, HudReeval.VISIBILITY)
    hudSubheader(getAllPlayers(), "Countdown will start when", HudPosition.LEFT, 0.1, Colour_TextTypeA, HudReeval.VISIBILITY)
    hudSubheader(getAllPlayers(), "both teams are ready" if ReadyUp_CaptainMode == 1 else "{2} [{0}/{1}]".format(len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady)), max(getNumberOfPlayers(Team.ALL), ReadyUp_MinimumPlayersToStart), "all players are ready"), HudPosition.LEFT, 0.1, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    hudSubtext(getAllPlayers(), Team.1, HudPosition.LEFT, 1, Colour_TeamOne, HudReeval.VISIBILITY)
    hudSubtext(getAllPlayers(), Team.2, HudPosition.LEFT, 3, Colour_TeamTwo, HudReeval.VISIBILITY)


rule "HUD Setup: Ready Toggle":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    
    if ReadyUp_CaptainMode == 0 or ReadyUp_CaptainMode == 1 and eventPlayer.getSlot() == 0:
        hudSubheader(getAllPlayers(), " {0} {1}".format("●" if eventPlayer.ReadyUp_PlayerReady else "○", eventPlayer), HudPosition.LEFT, (2 if eventPlayer.getTeam() == Team.1 else 4) + eventPlayer.getSlot() * 0.1, Colour_TextTypeC if eventPlayer.ReadyUp_PlayerReady else Colour_TextTypeB, HudReeval.VISIBILITY_STRING_AND_COLOR, SpecVisibility.ALWAYS)
        hudSubtext(eventPlayer, "You are readied up" if eventPlayer.ReadyUp_PlayerReady else "You are not readied up", HudPosition.TOP, 5.1, Colour_TextTypeC if eventPlayer.ReadyUp_PlayerReady else Colour_TextTypeB, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)
        if ReadyUp_CaptainMode == 0 and ReadyUp_AllowForceTeamReady:
            hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_Ready), "(Press) Unready / (Hold) Force Team Ready" if eventPlayer.ReadyUp_PlayerReady else "(Press) Ready Up / (Hold) Force Team Ready"), HudPosition.TOP, 5.2, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_Ready) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)
        else:
            hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_Ready), "Unready" if eventPlayer.ReadyUp_PlayerReady else "Ready Up"), HudPosition.TOP, 5.2, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_Ready) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)


rule "HUD Setup: Force Ready Hold Bar":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition ReadyUp_AllowForceTeamReady == true
    
    progressBarHud(eventPlayer if eventPlayer.ReadyUp_CurrentHoldTime >= 0.2 else null, eventPlayer.ReadyUp_CurrentHoldTime / ReadyUp_ForceTeamReadyHoldTime * 100, null, HudPosition.TOP, 5.5, Colour_TextTypeA, null, ProgressHudReeval.VISIBILITY_VALUES_AND_COLOR, SpecVisibility.NEVER)


rule "HUD Setup: Ban Hold Bar":
    @Event eachPlayer
    @Condition Ban_Enabled == true

    # Shared by ban and clear-ban - they cannot be held at once. Sort 5.7 puts it
    # under the ban hints, and the >= 0.2 gate keeps it off the screen until the
    # hold is deliberate rather than flashing on every brush of the key.
    progressBarHud(eventPlayer if eventPlayer.Ban_CurrentHoldTime >= 0.2 else null, eventPlayer.Ban_CurrentHoldTime / Ban_HoldTime * 100, null, HudPosition.TOP, 5.7, Colour_TextTypeA, null, ProgressHudReeval.VISIBILITY_VALUES_AND_COLOR, SpecVisibility.NEVER)


rule "HUD Setup: Defender Teleport":
    @Event eachPlayer
    @Condition Setup_AllowDefendersTeleport == true
    @Condition isInSetup() == true
    @Condition getCurrentGamemode() != Gamemode.PUSH
    @Condition isTeamOnDefense(eventPlayer.getTeam()) == true
    
    hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_DefenderTeleport), "Teleport to the objective" if eventPlayer.isInSpawnRoom() else "Teleport back to spawn"), HudPosition.TOP, 5.3, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_DefenderTeleport) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)


rule "HUD Setup: Add Setup Time":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition SetupAddTime_CaptainMode != 2
    @Condition isInSetup() == true
    
    if eventPlayer.getSlot() == 0 or SetupAddTime_CaptainMode == 0:
        hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_AddSetupTime), "Add {0} sec to setup timer".format(SetupAddTime_Step)), HudPosition.TOP, 5.4, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_AddSetupTime) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)
    else:
        hudSubheader(eventPlayer, "{0} and {1} can add {2} sec to the setup timer".format("{0}".format(getPlayersInSlot(0, Team.1)), "{0}".format(getPlayersInSlot(0, Team.2)), SetupAddTime_Step), HudPosition.TOP, 5.4, Colour_TextTypeA, HudReeval.STRING, SpecVisibility.NEVER)


rule "HUD Setup: Ban Hero":
    @Event eachPlayer
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true

    # Sits under the ready-up and add-setup-time hints (5.2, 5.4) in the same
    # style, so the ban reads as part of the setup controls rather than a
    # secret. SpecVisibility.NEVER: it is an instruction to the player holding
    # the keys, not something a spectator or the capture tool should see.
    hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(
                     inputBindingString(Keybind_Command), inputBindingString(Keybind_BanHero),
                     "Hold to ban {0} for both teams".format(eventPlayer.getHero())),
                 HudPosition.TOP, 5.5,
                 Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command)
                     and eventPlayer.isHoldingButton(Keybind_BanHero) else Colour_TextTypeA,
                 HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)


rule "HUD Setup: Clear Ban":
    @Event eachPlayer
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true

    # NO ban-state condition, deliberately. An earlier version only drew this
    # when your team had something to clear, and every ban-after-clear flipped
    # that condition false->true and created ANOTHER copy of the line - three
    # stacked hints after three bans, because nothing destroys HUD text until
    # destroyAllHudTexts() at round start. A rule that creates HUD text must
    # fire once per phase, not once per state change.
    #
    # The hero is not named here: the per-team "BAN:" lines in the ready-up
    # block already say what is banned, and repeating it is what forced the
    # state-dependent condition in the first place.
    hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(
                     inputBindingString(Keybind_Command), inputBindingString(Keybind_ClearBan),
                     "Hold to clear your team's hero ban"),
                 HudPosition.TOP, 5.6,
                 Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command)
                     and eventPlayer.isHoldingButton(Keybind_ClearBan) else Colour_TextTypeA,
                 HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)


rule "Setup: Remove Assembling Heroes":
    @Condition Setup_RemoveAssemblingHeroes == true
    @Condition isAssemblingHeroes() == true
    
    setMatchTime(1)


rule "Setup: Override Setup Time":
    @Condition isInSetup() == true
    
    wait()
    setMatchTime(Setup_SetupTimeOverride)


rule "Setup: Freeze Setup Time":
    @Condition ReadyUp_FreqMode != 2
    @Condition ReadyUp_FreezeSetupTime == true
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    
    pauseMatchTime()


rule "Setup: Add Setup Time":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition SetupAddTime_CaptainMode != 2
    @Condition isInSetup() == true
    @Condition (eventPlayer.getSlot() == 0 or SetupAddTime_CaptainMode == 0) == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_AddSetupTime) == true
    
    if getMatchTime() < SetupAddTime_Max:
        if isInSetup():
            setMatchTime(min(SetupAddTime_Max + 0.9, SetupAddTime_Step + getMatchTime()))
            smallMessage(getAllPlayers(), "{0} added {1} sec to setup timer".format(eventPlayer, SetupAddTime_Step))
    else:
        smallMessage(eventPlayer, "Setup timer cannot be extended beyond {0}:{1}{2}".format(floor(SetupAddTime_Max / 60), "0" if SetupAddTime_Max % 60 < 10 else "", floor(SetupAddTime_Max % 60)))


rule "Setup: Teleport to Objective/Spawn (Defenders Only)":
    @Event eachPlayer
    @Condition Setup_AllowDefendersTeleport == true
    @Condition getCurrentGamemode() != Gamemode.PUSH
    @Condition isTeamOnDefense(eventPlayer.getTeam()) == true
    @Condition isInSetup() == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_DefenderTeleport) == true
    
    if eventPlayer.isInSpawnRoom():
        if nearestWalkablePosition(getObjectivePosition(getCurrentObjective())) != null:
            eventPlayer.teleport(nearestWalkablePosition(getObjectivePosition(getCurrentObjective())))
            smallMessage(eventPlayer, "Teleported to objective")
        else:
            smallMessage(eventPlayer, "Unable to teleport, please try again later")
    else:
        eventPlayer.teleport(getSpawnPoints(eventPlayer.getTeam()))
        smallMessage(eventPlayer, "Teleported to spawn")


rule "Setup: Toggle Player Ready / Force Team Ready":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition (eventPlayer.getSlot() == 0 or ReadyUp_CaptainMode == 0) == true
    @Condition isInSetup() == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_Ready) == true
    
    if ReadyUp_CaptainMode == 0 and ReadyUp_AllowForceTeamReady:
        eventPlayer.ReadyUp_CurrentHoldTime = 0
        chaseOverTime(eventPlayer.ReadyUp_CurrentHoldTime, ReadyUp_ForceTeamReadyHoldTime, ReadyUp_ForceTeamReadyHoldTime, ChaseTimeReeval.NONE)
        waitUntil(not (eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_Ready)), ReadyUp_ForceTeamReadyHoldTime)
        stopChasing(eventPlayer.ReadyUp_CurrentHoldTime)
        eventPlayer.ReadyUp_CurrentHoldTime = 0
        if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_Ready):
            if isInSetup():
                smallMessage(getAllPlayers(), "{0} set all players on {1} ready".format(eventPlayer, eventPlayer.getTeam()))
                getPlayers(eventPlayer.getTeam()).ReadyUp_PlayerReady = true
                if ReadyUp_EnableReadyVoiceLine:
                    eventPlayer.communicate(Comms.GO)
            return
    if eventPlayer.ReadyUp_PlayerReady:
        eventPlayer.ReadyUp_PlayerReady = false
    else:
        eventPlayer.ReadyUp_PlayerReady = true
        if ReadyUp_EnableReadyVoiceLine:
            eventPlayer.communicate(Comms.READY)


rule "Setup: Both Teams Ready, Start Match (Captain-Only Mode)":
    @Condition ReadyUp_FreqMode != 2
    @Condition ReadyUp_CaptainMode == 1
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    @Condition getPlayersInSlot(0, Team.1).ReadyUp_PlayerReady == true
    @Condition getPlayersInSlot(0, Team.2).ReadyUp_PlayerReady == true
    
    if getNumberOfPlayers(Team.ALL) < ReadyUp_MinimumPlayersToStart:
        smallMessage(getAllPlayers(), "Both teams ready, but not enough players in game ({0})".format(ReadyUp_MinimumPlayersToStart))
        return
    # R3: two bans or none, never one. This guard is in BOTH start rules on
    # purpose - a lobby in the other ready mode would otherwise start with one
    # ban and the captured record would be wrong with nothing saying so.
    if Ban_Enabled and (Ban_Team1 == null) != (Ban_Team2 == null):
        smallMessage(getAllPlayers(), "Both teams ready, but only one hero is banned - ban a second or clear it")
        return
    smallMessage(getAllPlayers(), "Both teams ready, starting countdown")
    if ReadyUp_FreezeSetupTime:
        unpauseMatchTime()
    setMatchTime(ReadyUp_SetupCountdownTime)
    waitUntil(getPlayersInSlot(0, Team.1).ReadyUp_PlayerReady == false or getPlayersInSlot(0, Team.2).ReadyUp_PlayerReady == false, ReadyUp_SetupCountdownTime)
    if isInSetup() and getPlayersInSlot(0, Team.1).ReadyUp_PlayerReady == false or getPlayersInSlot(0, Team.2).ReadyUp_PlayerReady == false:
        smallMessage(getAllPlayers(), "A team unreadied, setup timer reset")
        if ReadyUp_FreezeSetupTime:
            pauseMatchTime()
        setMatchTime(Setup_SetupTimeOverride)


rule "Setup: Both Teams Ready, Start Match (All Players Mode)":
    @Condition ReadyUp_FreqMode != 2
    @Condition ReadyUp_CaptainMode == 0
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    @Condition getAllPlayers().all(lambda player: player.ReadyUp_PlayerReady) == true
    
    if getNumberOfPlayers(Team.ALL) < ReadyUp_MinimumPlayersToStart:
        smallMessage(getAllPlayers(), "All players ready, but not enough players in game ({0})".format(ReadyUp_MinimumPlayersToStart))
        return
    # R3: two bans or none, never one. This guard is in BOTH start rules on
    # purpose - a lobby in the other ready mode would otherwise start with one
    # ban and the captured record would be wrong with nothing saying so.
    if Ban_Enabled and (Ban_Team1 == null) != (Ban_Team2 == null):
        smallMessage(getAllPlayers(), "All players ready, but only one hero is banned - ban a second or clear it")
        return
    smallMessage(getAllPlayers(), "All players ready, starting countdown")
    if ReadyUp_FreezeSetupTime:
        unpauseMatchTime()
    setMatchTime(ReadyUp_SetupCountdownTime)
    waitUntil(len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady == true)) < len(getAllPlayers()), ReadyUp_SetupCountdownTime)
    if isInSetup() and len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady == true)) < len(getAllPlayers()):
        smallMessage(getAllPlayers(), "{0} unreadied, setup timer reset".format((getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady == false))[0]))
        if ReadyUp_FreezeSetupTime:
            pauseMatchTime()
        setMatchTime(Setup_SetupTimeOverride)


rule "Debug: Display Server Load":
    @Condition Debug_DisplayServerLoad == true
    @Condition isGameInProgress() == true

    # For comparing this code's cost against ScrimTime and ScrimTime Lite, both
    # of which ship the same readout in their own Debug panels - ours was the
    # only one of the three that could not be measured. Mirrors DKEEH's rule so
    # the numbers mean the same thing.
    #
    # Drawn on the RIGHT deliberately: the capture tool OCRs the top-left of the
    # frame for the BANS row, and a debug readout in that crop is noise it does
    # not need to parse around.
    #
    # BOTH LINES READ A VARIABLE, not live values. The strings are built on the
    # sampler's own timer below, so the readout costs one variable resolve per
    # line instead of re-deriving arithmetic continuously. A measuring
    # instrument that changes what it measures is worth avoiding, and 2 Hz is
    # easier to read off a screen than a number flickering at frame rate.
    wait()
    hudSubheader(getAllPlayers(), "{0} cur / {1} avg / {2} peak server load".format(
                     getServerLoad(), getAverageServerLoad(), getPeakServerLoad()),
                 HudPosition.RIGHT, 100, Colour_TextTypeA,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
    hudSubheader(getAllPlayers(), Debug_LoadText,
                 HudPosition.RIGHT, 101, Colour_TextTypeB,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
    hudSubheader(getAllPlayers(), Debug_LoadText2,
                 HudPosition.RIGHT, 102, Colour_TextTypeC,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)


# THE NUMBERS OVERWATCH GIVES YOU ARE ALL TWO-SECOND WINDOWS. getPeakServerLoad()
# is "the highest CPU load ... over the last two seconds", not a high-water mark,
# and getAverageServerLoad() averages the same two seconds. So the built-in
# readout tells you what just happened and then forgets it, which makes a whole
# map impossible to characterise by eye - the numbers move faster than you can
# read them and every run looks different.
#
# This samples twice a second and keeps what the built-ins throw away:
#
#   max   - a REAL high-water mark. Sampling the 2 s peak every 0.5 s cannot
#           miss a spike, because every 2 s window gets looked at four times.
#   mean  - the true average over the whole map, not over two seconds.
#   >200% - the share of the map spent above 200, which is the number that
#           actually predicts whether a mode is in trouble. A single 255 spike
#           in ten minutes and a mode sitting at 255 look identical on the
#           built-in readout and are completely different problems.
#   n     - sample count, so you can see the run was long enough to mean
#           anything and that the sampler is alive.
#
# Instantaneous load feeds mean and the threshold count (a proper duty cycle);
# the 2 s peak feeds max (so nothing is missed between samples). Mixing them is
# deliberate, not an oversight.
#
# COST: one global rule, ~8 variable operations at 2 Hz, and it only runs with
# 6. Debug switched on. Off by default, so a normal scrim never pays for it.
rule "Debug: Track Server Load":
    @Condition Debug_DisplayServerLoad == true

    while true:
        waitUntil(isGameInProgress(), 99999)
        Debug_LoadMax = max(Debug_LoadMax, getPeakServerLoad())
        Debug_LoadSum += getServerLoad()
        Debug_LoadSamples += 1
        if getServerLoad() > 200:
            Debug_LoadOver200 += 1
        Debug_LoadText = "max {0} / mean {1} / {2}".format(
            Debug_LoadMax,
            round(Debug_LoadSum / Debug_LoadSamples),
            "{0}% over 200 / n {1}".format(
                round(Debug_LoadOver200 / Debug_LoadSamples * 100),
                Debug_LoadSamples))
        wait(0.5)


# THE DISTRIBUTION, because a mean hides exactly what you are hunting. The FPS
# benchmarking convention is the right instinct here: nobody quotes average
# framerate alone, because a run that averages 120 with vicious stutter and a
# run that sits flat at 120 are the same number and completely different
# experiences. Server load is the same, and worse - "mean 75" was true of both
# builds measured on 2026-09-06 while the live readout was flashing 255.
#
#   best1%  - the 1st percentile. What the server looks like when nothing is
#             happening; the floor the mode sits on.
#   med     - the median. More honest than the mean, which a handful of 255s
#             drags upward.
#   worst1% - the 99th percentile: the load exceeded 1% of the time. THIS IS
#             THE ONE THAT MATTERS, and it is the direct analogue of the "1%
#             low" in an FPS benchmark - the difference being that for load,
#             worse means HIGHER.
#
# Exact percentiles off the real samples, not buckets: the samples go into an
# array and Sorted Array does the work, which the workshop.codes guide names as
# the cheap way to do array work ("iterating with For Global Variable can be a
# lot more expensive than doing the exact same thing with Mapped Array /
# Filtered Array / Sorted Array").
#
# SAMPLED AT 1 Hz AND SORTED EVERY FIFTH SAMPLE, both deliberately slow. A
# 1200-element sort is not free, and an instrument that shifts what it is
# measuring is worse than no instrument. Five seconds between sorts makes the
# cost unmeasurable while still converging quickly - after a minute there are
# already 60 samples behind the number.
#
# THE ONE THING THIS CANNOT SEE is a spike between two samples: at 1 Hz a 200 ms
# burst is invisible to it. That is exactly what `max` on the line above is for,
# because that reads getPeakServerLoad(), a 2-second window sampled every 0.5 s,
# which cannot miss one. Read the two together - percentiles for the shape, max
# for "did anything ever hit the ceiling".
rule "Debug: Track Load Distribution":
    @Condition Debug_DisplayServerLoad == true

    while true:
        waitUntil(isGameInProgress(), 99999)
        if len(Debug_LoadHistory) < 1200:
            Debug_LoadHistory.append(getServerLoad())
            # Recompute inside the cap check, so a full history stops re-sorting
            # instead of sorting 1200 elements a second forever for a number
            # that can no longer change.
            if len(Debug_LoadHistory) >= 20 and len(Debug_LoadHistory) % 5 == 0:
                Debug_LoadSorted = sorted(Debug_LoadHistory, key=lambda sample: sample)
                Debug_LoadText2 = "best1% {0} / med {1} / {2}".format(
                    Debug_LoadSorted[floor(len(Debug_LoadSorted) * 0.01)],
                    Debug_LoadSorted[floor(len(Debug_LoadSorted) * 0.5)],
                    "worst1% {0}".format(Debug_LoadSorted[min(len(Debug_LoadSorted) - 1, floor(len(Debug_LoadSorted) * 0.99))]))
        wait(1)


# Per MAP, not per session: the stats reset when round 1 starts, so each map you
# test gives its own independent figure and you are never averaging a scoreboard
# -on map together with a scoreboard-off one. Rounds 2+ keep accumulating, which
# is what you want - a map is the unit being characterised.
rule "Debug: Reset Load Stats At Map Start":
    @Condition Debug_DisplayServerLoad == true
    @Condition getMatchRound() == 1
    @Condition isGameInProgress() == true

    Debug_LoadMax = 0
    Debug_LoadSum = 0
    Debug_LoadSamples = 0
    Debug_LoadOver200 = 0
    Debug_LoadHistory = []
    Debug_LoadSorted = []


rule "Bans: Toggle Ban On Current Hero":
    @Event eachPlayer
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_BanHero) == true

    # R1: one ban per team, so a second confirm REPLACES the first. Pressing
    # again on your own banned hero clears it, which is the only route back to
    # "neither team banned" once a team has banned - and R3 makes that a state
    # teams need to be able to reach.
    # R1: one ban per team, so this always sets or REPLACES. Clearing has its own
    # bind - see "Bans: Clear Your Team's Ban". An earlier version cleared by
    # pressing this again while on your own banned hero, which cannot happen:
    # Ban_Apply() removes the hero from every player including the banning team,
    # so you are force-swapped off it and can never be on it to press anything.
    #
    # R2: checked on EVERY confirm including a change, or team 1 could ban a
    # tank, wait for team 2 to ban a tank, then switch onto one and collide.
    # HELD, not pressed. A ban applies to BOTH teams for the whole map and
    # force-swaps anyone already on the hero, so an accidental one costs a real
    # undo - and the chord is Command+Melee, which a player warming up in spawn
    # can hit without meaning to. Mirrors the force-team-ready hold exactly,
    # including the shared progress bar, so it is one interaction to learn.
    #
    # isInSetup() is re-checked after the hold: the condition was true when the
    # rule fired, and a hold can outlive setup.
    eventPlayer.Ban_CurrentHoldTime = 0
    chaseOverTime(eventPlayer.Ban_CurrentHoldTime, Ban_HoldTime, Ban_HoldTime, ChaseTimeReeval.NONE)
    waitUntil(not (eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_BanHero)), Ban_HoldTime)
    stopChasing(eventPlayer.Ban_CurrentHoldTime)
    eventPlayer.Ban_CurrentHoldTime = 0
    if not (eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_BanHero)) or not isInSetup():
        return
    if Ban_SameRole(eventPlayer.getHero(), Ban_Team2 if eventPlayer.getTeam() == Team.1 else Ban_Team1):
        smallMessage(eventPlayer, "That role is already banned by the other team")
    elif eventPlayer.getTeam() == Team.1:
        Ban_Team1 = eventPlayer.getHero()
    else:
        Ban_Team2 = eventPlayer.getHero()
    Ban_Apply()
    waitUntil(not eventPlayer.isHoldingButton(Keybind_BanHero), 1)


rule "Bans: Clear Your Team's Ban":
    @Event eachPlayer
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_ClearBan) == true

    # Its own bind because there is no other way back. R3 forbids starting a map
    # with exactly one ban, so a team that bans while the other does not has to
    # be able to undo it - and without this the only escape was the setup timer
    # wiping the lone ban at five seconds.
    # Held for the same reason and the same duration as banning: clearing is
    # what lets a map start with no bans at all, so a stray press changes what
    # both teams are playing against.
    eventPlayer.Ban_CurrentHoldTime = 0
    chaseOverTime(eventPlayer.Ban_CurrentHoldTime, Ban_HoldTime, Ban_HoldTime, ChaseTimeReeval.NONE)
    waitUntil(not (eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_ClearBan)), Ban_HoldTime)
    stopChasing(eventPlayer.Ban_CurrentHoldTime)
    eventPlayer.Ban_CurrentHoldTime = 0
    if not (eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_ClearBan)) or not isInSetup():
        return
    if eventPlayer.getTeam() == Team.1:
        Ban_Team1 = null
    else:
        Ban_Team2 = null
    Ban_Apply()
    smallMessage(getAllPlayers(), "{0} cleared their team's hero ban".format(eventPlayer))
    waitUntil(not eventPlayer.isHoldingButton(Keybind_ClearBan), 1)


rule "Bans: New Map Clears Them, Later Rounds Keep Them":
    @Condition isInSetup() == true

    # Round 1 is a new map, so start from no bans. Every later round is the SAME
    # map: the bans carry over by default. Teams can still change them during
    # that round's setup - the toggle rule runs in every setup - but nothing
    # clears them on the teams' behalf.
    #
    # Conditioning the clear on isInSetup() alone was a bug: setup runs at the
    # start of EVERY round, so Escort/Hybrid round 2 and each Control point
    # would have silently un-banned both heroes mid-map.
    if getMatchRound() == 1:
        Ban_Team1 = null
        Ban_Team2 = null
    # Re-assert enforcement either way, in case a round transition restored hero
    # availability. With both bans null this is just resetHeroAvailability().
    Ban_Apply()


# The ban test leads and the CLOCK trails, which is the opposite of the order
# this shipped with. Match time changes continuously, so leading with it meant
# re-checking this rule for the whole setup phase; a lone ban is a state that
# changes when somebody presses a key, and is usually false.
rule "Bans: Clear A Lone Ban Before The Timer Expires":
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true
    @Condition (Ban_Team1 == null) != (Ban_Team2 == null)
    @Condition getMatchTime() <= 5

    # R3's guard only blocks the READY path; setup time expiring ends setup
    # regardless. Clearing keeps the invariant (no map starts with exactly one
    # ban) while failing toward no-bans rather than stalling a live scrim.
    Ban_Team1 = null
    Ban_Team2 = null
    Ban_Apply()
    smallMessage(getAllPlayers(), "Only one hero was banned - bans cleared for this map")


def Ban_DrawRows():
    @Name "Subroutine: Draw the ban rows"
    # SpecVisibility.ALWAYS so it renders for spectators AND in replays, which
    # is where captures are actually taken from. The label is the capture
    # tool's textual anchor - do not remove the colon or reword "BANS".
    # A bare Hero renders as its NAME (confirmed in game 2026-08-27);
    # heroIcon() would draw a glyph that OCR cannot read.
    #
    # The NONE branch is not cosmetic: an absent row means "could not read" and
    # a present row reading NONE means "known, no bans". engine/banrow.js
    # depends on telling those apart.
    #
    # Ban_HudTo decides who sees it, because Workshop subroutines take no
    # parameters. During setup that is every player - you need to know what is
    # banned before you pick. During the round it is `null`, which with
    # SpecVisibility.ALWAYS means SPECTATORS AND REPLAYS ONLY: the scoreboard
    # uses exactly this trick, which is why a player sees no legend mid-fight.
    # Players complained about the clutter, and capture reads the replay anyway.
    #
    # HudReeval.STRING, not VISIBILITY_AND_STRING: the audience is fixed when the
    # row is created. Re-evaluating visibility would re-read Ban_HudTo, so a live
    # setup row would flip to spectator-only the moment the in-game rule set the
    # global. The string still updates, which is what a changing ban needs.
    hudSubheader(Ban_HudTo, "BANS  : {0}".format(
                     "NONE" if Ban_Team1 == null and Ban_Team2 == null else
                     "{0} | {1}".format(Ban_Team1, Ban_Team2)),
                 HudPosition.LEFT, 0.2, Colour_Heading,
                 HudReeval.STRING, SpecVisibility.ALWAYS)
    hudSubheader(Ban_HudTo, "MAP   : {0}".format(getCurrentMap()),
                 HudPosition.LEFT, 0.3, Colour_Heading,
                 HudReeval.STRING, SpecVisibility.ALWAYS)


# TWO rules, because "Game: Clean Up HUD Text" calls destroyAllHudTexts() the
# moment the match starts and again between rounds. Anything created once by a
# condition that never transitions again is destroyed and never comes back -
# which is exactly what happened on the first in-game test: the rows showed in
# setup and vanished at "DEFEND OBJECTIVE A". The scoreboard survives by being
# conditioned on isGameInProgress() with a wait(), so it is RECREATED after each
# cleanup. These mirror that, and the wait() is what orders them after it.
rule "Bans: HUD Row (Setup)":
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true

    wait()
    # Spectator-only in setup as well as in game. Players read the per-team
    # lines in "HUD Setup: Team Bans" instead, which say the same thing with the
    # attribution the combined row cannot carry. Keeping the combined row for
    # spectators through setup matters: a replay includes the setup phase, and
    # the capture parser needs its anchor present in every frame it might read.
    Ban_HudTo = null
    Ban_DrawRows()
    # The players' view of the same facts, slotted into the ready-up block:
    # TEAM 1 sits at sort 1 with its players at 2.x and TEAM 2 at 3 with players
    # at 4.x, so 1.5 and 3.5 put each team's ban directly under its own header,
    # in that team's colour. HudReeval.STRING so it updates the moment someone
    # bans. SpecVisibility.ALWAYS and VISIBILITY_STRING_AND_COLOR mirror the
    # player-ready rows exactly, which are known to render for players.
    #
    # An earlier version used SpecVisibility.NEVER to keep spectators clean and
    # rendered for NOBODY. Every NEVER row in this file targets `eventPlayer`;
    # every getAllPlayers() row uses ALWAYS or default. getAllPlayers() + NEVER
    # is a combination nothing else here uses, and it does not display. Do not
    # reintroduce it to tidy the spectator view.
    #
    # The label is "BAN", which normalizes to "ban" - it cannot be mistaken for
    # the combined row's "bans" anchor by engine/banrow.js. Do not rename it.
    hudSubheader(getAllPlayers(),
                 "   BAN: {0}".format(Ban_Team1) if Ban_Team1 != null else "   BAN: none yet",
                 HudPosition.LEFT, 1.5, Colour_TeamOne,
                 HudReeval.VISIBILITY_STRING_AND_COLOR, SpecVisibility.ALWAYS)
    hudSubheader(getAllPlayers(),
                 "   BAN: {0}".format(Ban_Team2) if Ban_Team2 != null else "   BAN: none yet",
                 HudPosition.LEFT, 3.5, Colour_TeamTwo,
                 HudReeval.VISIBILITY_STRING_AND_COLOR, SpecVisibility.ALWAYS)


rule "Bans: HUD Row (In Game)":
    @Condition Ban_Enabled == true
    @Condition isGameInProgress() == true

    wait()
    Ban_HudTo = null
    Ban_DrawRows()


rule "Game: Clean Up HUD Text":
    while true:
        waitUntil(isGameInProgress(), 99999)
        destroyAllHudTexts()
        waitUntil(isMatchBetweenRounds(), 99999)
        destroyAllHudTexts()


rule "Game: Reset Player Ready Status":
    @Condition ReadyUp_FreqMode != 2
    @Condition isGameInProgress() == true
    
    wait()
    getAllPlayers().ReadyUp_PlayerReady = false
    stopChasing(getAllPlayers().ReadyUp_CurrentHoldTime)
    getAllPlayers().ReadyUp_CurrentHoldTime = 0


rule "Scoreboard: Update Match Time":
    Match_CurrentMatchTime = 0
    while true:
        waitUntil(isGameInProgress(), 99999)
        chaseAtRate(Match_CurrentMatchTime, 99999, 1, ChaseRateReeval.NONE)
        waitUntil(not isGameInProgress(), 99999)
        stopChasing(Match_CurrentMatchTime)


rule "Scoreboard: Create Match Time Display":
    @Condition Scoreboard_DisplayMatchTime == true
    @Condition isGameInProgress() == true
    
    wait()
    if Scoreboard_Size == 0:
        hudSubheader(null, "{0} Match Time: {1}".format(abilityIconString(Hero.LUCIO, Button.ABILITY_2), "{0}:{1}{2}".format(floor(Match_CurrentMatchTime / 60), "0" if Match_CurrentMatchTime % 60 < 10 else "", floor(Match_CurrentMatchTime % 60))), HudPosition.LEFT, 4, Colour_TextTypeA, HudReeval.STRING, SpecVisibility.ALWAYS)
    else:
        hudSubtext(null, "{0} Match Time: {1}".format(abilityIconString(Hero.LUCIO, Button.ABILITY_2), "{0}:{1}{2}".format(floor(Match_CurrentMatchTime / 60), "0" if Match_CurrentMatchTime % 60 < 10 else "", floor(Match_CurrentMatchTime % 60))), HudPosition.LEFT, 4, Colour_TextTypeA, HudReeval.STRING, SpecVisibility.ALWAYS)


# TWO GREEN BARS THAT BOUND THE BOARD, so the capture tool can find it without
# a human dragging a box over it. Everything about them is chosen for a machine
# that has to locate them in a frame full of Overwatch.
#
# WHY AT ALL: the crop is not forgiving. Measured over the eight Colosseo frames,
# the true extent accepts 7 of 8 frames; the same crop with a 50% margin accepts
# 4 and halves the values recovered. "Roughly the right area" is not good enough,
# and asking every host to drag an accurate box is not a plan.
#
# WHY GREEN: it is the only colour in this mode's palette that nothing draws on
# the spectator view DURING A GAME. Blue and red are the TEAM headers, orange is
# the chrome, white is the rows; Colour_TextTypeC is used solely by the ready-up
# list, which is setup-only. So the markers cost no new colour, sit inside a
# palette a human already reads as deliberate, and cannot be confused with any
# other line on the board.
#
# WHY A ROW OF DOTS: a solid glyph gives large blocks of near-pure colour, which
# is what makes the detector cheap - and it is the SHAPE that keeps green safe.
# Foliage is green, but foliage is textured; nothing on an Overwatch map draws a
# 56-character uniform horizontal bar. The detector looks for a long run, not
# for a hue. U+25CF is used deliberately over a block character: the ready-up
# list already renders it in this mode, so it is known to exist in the font
# rather than being a guess that costs an in-game test to disprove.
#
# WHY 56 WIDE: every HUD line is CENTRE-aligned, so a bar wider than the widest
# line bounds the board horizontally as well as vertically, and two bars are a
# whole box. The widest line is the column key at 47 characters; overshooting
# costs a little background either side, which the capture side's local-contrast
# pass handles, while undershooting would CLIP the key and the longest rows.
#
# The tool crops strictly BETWEEN the two bars, so the markers never enter the
# image handed to OCR and cannot add junk lines of their own.
rule "Scoreboard: Create Capture Markers":
    @Condition Scoreboard_CaptureMarkers == true
    @Condition Scoreboard_EnableScoreboard == true
    @Condition isGameInProgress() == true

    wait()
    if Scoreboard_Size == 0:
        hudSubheader(null, "●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●", HudPosition.LEFT, 0.1, Colour_TextTypeC, HudReeval.NONE, SpecVisibility.ALWAYS)
        hudSubheader(null, "●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●", HudPosition.LEFT, 4.5, Colour_TextTypeC, HudReeval.NONE, SpecVisibility.ALWAYS)
    else:
        hudSubtext(null, "●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●", HudPosition.LEFT, 0.1, Colour_TextTypeC, HudReeval.NONE, SpecVisibility.ALWAYS)
        hudSubtext(null, "●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●", HudPosition.LEFT, 4.5, Colour_TextTypeC, HudReeval.NONE, SpecVisibility.ALWAYS)


# Setting first, isGameInProgress() second - see the block above
# "Scoreboard: Create Player Entries (Small)" for why that order.
rule "Scoreboard: Create Legend":
    @Condition Scoreboard_EnableScoreboard == true
    @Condition isGameInProgress() == true

    wait()
    # One line, in the row's own order, so a reader can map value to meaning by
    # counting across. It cannot be ALIGNED with the rows - the HUD centres every
    # line and eats runs of spaces - but it does not need to be: it needs to say
    # what the sixth number is, which changes by role and is the one thing a
    # bare row cannot tell you.
    # The key follows the size setting exactly as the rows do, because
    # hudSubtext is LARGER than hudSubheader, not smaller - which this file
    # already says out loud if you read it: the Size setting maps Small to
    # hudSubheader and Medium to hudSubtext. An attempt to drop the key "one
    # size down" by pinning it to hudSubtext therefore made it the biggest thing
    # on the board, which is the opposite of what a key should be.
    #
    # Subheader is the smallest text the HUD offers, so at Small the key cannot
    # be smaller than the rows; matching them is the closest thing available.
    #
    # COLOUR is a separate question from size, and the answer changed on
    # 2026-09-06: the key now takes the heading's orange exactly (Colour_Key is
    # assigned from Colour_Heading), so BANS, MAP and this line read as one
    # block of chrome. What is still rejected is the arrangement that made this
    # line the LOUDEST - orange here against a duller gold on BANS/MAP. Equal is
    # fine; louder than the headings is not, and five competing hues in a
    # fifteen-line block over an uncontrolled background read as noise.
    #
    # Hue still carries meaning in exactly one place, the two TEAM labels, and
    # the chrome staying a single hue is what keeps that signal legible.
    if Scoreboard_Size == 0:
        hudSubheader(null, "PLAYER • K • D • DMG • TKN • ACC/BLK/HEAL • ULT", HudPosition.LEFT, 1.5, Colour_Key, HudReeval.NONE, SpecVisibility.ALWAYS)
    else:
        hudSubtext(null, "PLAYER • K • D • DMG • TKN • ACC/BLK/HEAL • ULT", HudPosition.LEFT, 1.5, Colour_Key, HudReeval.NONE, SpecVisibility.ALWAYS)


rule "Scoreboard: Create Team Headers":
    @Condition Scoreboard_EnableScoreboard == true
    @Condition isGameInProgress() == true

    wait()
    # In team colour, because these are the two lines that can afford it: they
    # are for a human, they carry no digits, and the parser does not depend on
    # reading them - a ten-row board with no team headers is split five and five
    # by position instead. The stat rows are white; see the block above the
    # "Scoreboard: Build Row Text" rule for what that is and is not measured on.
    #
    # Rows sort
    # to 2.x and 3.x by team, so 1.9 and 2.9 head their blocks. This is a
    # better anchor than colour ever was: the five/five split stops being
    # inferred from pixels and becomes something the parser can simply see.
    if Scoreboard_Size == 0:
        hudSubheader(null, "TEAM 1", HudPosition.LEFT, 1.9, Colour_TeamOne, HudReeval.NONE, SpecVisibility.ALWAYS)
        hudSubheader(null, "TEAM 2", HudPosition.LEFT, 2.9, Colour_TeamTwo, HudReeval.NONE, SpecVisibility.ALWAYS)
    else:
        hudSubtext(null, "TEAM 1", HudPosition.LEFT, 1.9, Colour_TeamOne, HudReeval.NONE, SpecVisibility.ALWAYS)
        hudSubtext(null, "TEAM 2", HudPosition.LEFT, 2.9, Colour_TeamTwo, HudReeval.NONE, SpecVisibility.ALWAYS)


# EVERY SCOREBOARD ROW IS WHITE, AND CARRIES NO HERO ICON. Both are OCR
# decisions, measured against real spectator frames rather than assumed. White
# is the best-scoring text colour there is ON A DARK MAP: per row, across five
# frames, with the background luminance controlled, white recovered 5.39 of six
# numbers against team blue's 4.55 and team red's 3.40.
#
# The rows were tried in team colour on 2026-09-06 and are back to white the
# same day. Three REAL frames, real white rows, no simulation, all read through
# the shipped capture path with no preprocessing changes:
#
#   Nepal            flat dark surfaces    45/48 values  6/8 rows  8/8 names
#   Blizzard World   lantern-lit roof      18/48         0/8       8/8
#   Busan            white interior        (team colour there: 27/96, 0 rows)
#
# Nepal is the best result anything has produced on this board. So white is not
# the problem, and neither is colour.
#
# THE DOMINANT VARIABLE IS WHAT IS BEHIND THE BOARD. Same colour, same font,
# same code, same resolution - a 2.5x spread from background alone. The HUD
# draws this text on NO PLATE, straight over the world, so the map decides the
# read. That is why the two team-colour experiments both produced confusing
# numbers: each was measured on a different map from the one before it, and the
# map moved more than the colour did.
#
# What follows from that: a colour change is not a lever worth pulling again
# without holding the map fixed, and the real lever is capture-side
# preprocessing - specs/2026-09-06-scoreboard-capture-design.md section 8.3.
#
# What is NOT claimed any more: the original note here said colour was "the one
# variable that separated the lines that read from the lines that did not". It
# was not, and neither is luminance on its own. Contrast against a background
# that changes every map is - which is why every colour ranking measured so far
# has reversed itself on the next frame set.
#
# The hero icon went for the same reason: it is an image, so OCR emits junk for
# it ("&b", "Fog", "$'"), and that junk merges into the first number of the row.
# The row names its player now, so the icon was carrying no information the row
# did not already have. The Large preset still draws it, on its own line where
# it cannot corrupt a number.
#
# The cost is that a human loses the team colour cue. Slot ordering keeps the
# two teams in two blocks of five and every row is named, so the information is
# still there - it is just no longer carried by colour.
rule "Scoreboard: Build Row Text":
    @Event eachPlayer
    @Condition Scoreboard_EnableScoreboard == true

    # The row's numbers are built HERE, on a timer, instead of inside the HUD
    # text's own string. A hud text with HudReeval.STRING re-evaluates its whole
    # expression continuously, and this one is fourteen stat lookups deep - times
    # ten players, it was the single most expensive thing in the mode. Written to
    # a player variable four times a second, the HUD's expression becomes one
    # variable read and the numbers are at most 250 ms stale, which no human and
    # no capture read can tell apart.
    #
    # Measure before and after with "6. Debug > Display Server Load" rather than
    # trusting this comment.
    #
    # THE ROW CARRIES ITS PLAYER'S NAME, FIRST, AND THE NAME IS BUILT IN HERE
    # rather than added by the hud text. Both halves of that are deliberate and
    # both replace an earlier decision, so the reasoning is worth keeping.
    #
    # The name is on the row because the alternative lost on measurement. The
    # argument against it was real: the HUD centres every line, so columns only
    # align when rows are the same LENGTH, and a name is variable length - on a
    # real frame, six lines' left edges span 67 pixels while their centres land
    # within three of each other. Identity was supposed to come from slot
    # position and the spectator portrait bar instead. But the frames in the
    # block above read 8/8 NAMES on the same rows where they read 6/8 sets of
    # numbers, which makes the name the most reliable thing on the row. A row
    # that names itself needs no cross-reference to be worth anything.
    #
    # It is built INTO this variable because of what the alternative cost the
    # server. A hud text re-evaluates its string continuously, so while the name
    # was joined on at the hud text, that was a Custom String concatenation
    # re-resolved per player forever - to attach a name that never changes to a
    # variable that changes four times a second. Folded in here, the hud text's
    # string is one bare variable read and the join happens on the timer.
    #
    # That was measured, not assumed: with 10 bots on one map this mode peaked
    # at 121 server load with the scoreboard OFF against 190 with it ON, so
    # everything on this path is the dominant cost in the whole mode and worth
    # being fussy about.
    #
    # The hero icon that used to end the row is gone entirely - see the block
    # above this rule for why.
    #
    # THE SORT ORDER IS BUILT HERE TOO, for the same reason the numbers are.
    # The three "Create Player Entries" rules used to carry the sort expression
    # inline, under HudReeval.SORT_ORDER_AND_STRING - so in the role-grouped
    # layout the server re-resolved `Array Contains(All Damage Heroes, Hero Of
    # (Event Player))` and then the tank list, per player, for as long as the
    # board existed. The value it computes changes only on a hero swap.
    #
    # Computing it here means the hud text resolves one player variable. It also
    # collapses each of those three rules from an If/Else pair down to a single
    # Create HUD Text, because the group mode is now read once, here.
    #
    # The expression is the two originals verbatim, selected by group mode - NOT
    # merged with the role test in the row below. They disagree on a null hero
    # (the row falls through to accuracy, the sort falls through to 3) and that
    # difference is preserved rather than tidied away.
    #
    # THE WAIT IS 0.200-0.245, A RANGE RATHER THAN A FLAT 0.25, and the spread
    # is the only part of it that is an optimisation.
    #
    # Ten Ongoing-Each-Player loops on an identical period all land on the same
    # server frame - ten rebuilds at once and nothing in between, which is the
    # shape the workshop.codes stability guide warns about when it says "a quick
    # peak from 100 to 255 server load can be worse than a consistent 200". Five
    # ms between neighbours de-phases them within a second of the round starting
    # and keeps them apart. Every period is <= the 0.25 s this replaced, so the
    # spread costs no freshness at all.
    #
    # THIS RAN AT 0.90-0.99 s FOR PART OF 2026-09-06 AND WAS PUT BACK, and the
    # reason is worth keeping because it is the one number in this file that was
    # actually priced. The operator authorised a full second of staleness on the
    # assumption the loop was expensive. Measuring it against a build with the
    # wait cranked to 0.016 - 60x the rate - moved the whole distribution by a
    # near-uniform +17 (mean 51 to 68, median 46 to 63, worst1% 125 to 142),
    # which works out at about 0.28 load per rebuild-per-second-per-player.
    #
    # At this period that is a cost of roughly 0.3 against a mean of 51: about
    # 0.6% of the mode. The full second bought back around one single load unit.
    # It was not worth a quarter-second of extra lag on the board, so the lag
    # went back. Do not trade freshness here again without pricing it first -
    # the tools are in the README under "Measuring server load".
    while true:
        waitUntil(isGameInProgress(), 99999)
        eventPlayer.Scoreboard_Sort = (eventPlayer.getSlot() if Scoreboard_GroupMode == 0 else (1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3)) * 0.1 + (2 if eventPlayer.getTeam() == Team.1 else 3)
        eventPlayer.Scoreboard_Row = "{0} • {1}".format(eventPlayer, "{0} • {1}".format("{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))))
        wait(0.2 + (eventPlayer.getSlot() * 2 + (0 if eventPlayer.getTeam() == Team.1 else 1)) * 0.005)


# THE SIZE CHECK IS THE FIRST CONDITION IN ALL THREE OF THESE RULES, and that
# ordering is deliberate. Conditions are checked in order and short-circuit on
# the first false one, so whichever condition leads decides how much work the
# other rules do. These three used to lead with isGameInProgress(), which is
# the worst possible choice: it is the condition they all share and the one
# that changes, so every round start walked into all three rules before the
# size setting ruled two of them out.
#
# Leading with the size setting - fixed for the whole lobby - means two of the
# three stop at their first condition and stay stopped. The workshop.codes
# stability guide names both halves of this: "avoid multiple rules sharing the
# same conditions as the first condition", and put "the least frequently
# changing condition first".
#
# The group-mode branch is gone from all three: the sort order is a player
# variable now, built alongside the row. See "Scoreboard: Build Row Text".
rule "Scoreboard: Create Player Entries (Small)":
    @Event eachPlayer
    @Condition Scoreboard_Size == 0
    @Condition Scoreboard_EnableScoreboard == true
    @Condition isGameInProgress() == true

    wait()
    hudSubheader(null, eventPlayer.Scoreboard_Row, HudPosition.LEFT, eventPlayer.Scoreboard_Sort, Colour_TextTypeA, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)


rule "Scoreboard: Create Player Entries (Medium)":
    @Event eachPlayer
    @Condition Scoreboard_Size == 1
    @Condition Scoreboard_EnableScoreboard == true
    @Condition isGameInProgress() == true

    wait()
    hudSubtext(null, eventPlayer.Scoreboard_Row, HudPosition.LEFT, eventPlayer.Scoreboard_Sort, Colour_TextTypeA, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)


rule "Scoreboard: Create Player Entries (Large)":
    @Event eachPlayer
    @Condition Scoreboard_Size == 2
    @Condition Scoreboard_EnableScoreboard == true
    @Condition isGameInProgress() == true

    wait()
    hudText(null, null, null, eventPlayer.Scoreboard_Row, HudPosition.LEFT, eventPlayer.Scoreboard_Sort, Colour_TextTypeA, Colour_TextTypeA, Colour_TextTypeA, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)


rule "Scoreboard: Host Spectator Toggle":
    @Condition Scoreboard_EnableScoreboard == true
    @Condition Scoreboard_AllowHideScoreboard == true
    @Condition isGameInProgress() == true
    @Condition hostPlayer.isHoldingButton(Button.ULTIMATE) == true
    @Condition hostPlayer.isHoldingButton(Button.ABILITY_1) == true
    @Condition hostPlayer.getTeam() == Team.ALL
    
    if Scoreboard_HideScoreboardID == null:
        smallMessage(getAllPlayers(), "Host toggled scoreboard off")
        hudSubtext(null, " \n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n", HudPosition.LEFT, 0, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
        Scoreboard_HideScoreboardID = getLastCreatedText()
    else:
        smallMessage(getAllPlayers(), "Host toggled scoreboard on")
        destroyHudText(Scoreboard_HideScoreboardID)
        Scoreboard_HideScoreboardID = null


rule "Map Completion: Save Team Scores on Round End":
    @Condition getCurrentGamemode() != Gamemode.CONTROL
    @Condition getCurrentGamemode() != Gamemode.FLASHPOINT
    @Condition getCurrentGamemode() != Gamemode.PUSH
    @Condition isMatchBetweenRounds() == true
    
    if isTeamOnOffense(Team.1):
        MapComp_TeamOneScore = teamScore(Team.1)
    else:
        MapComp_TeamTwoScore = teamScore(Team.2)


# Gamemode before round state, so that on Control, Flashpoint and Push this
# rule stops at its second condition for the whole map instead of waking up at
# every round transition. "Save Team Scores on Round End" above already orders
# it this way; this rule did not.
rule "Map Completion: Ensure Map Completion (Assault, Escort and Hybrid)":
    @Condition MapComp_EnableMapCompletion == true
    @Condition getCurrentGamemode() != Gamemode.CONTROL
    @Condition getCurrentGamemode() != Gamemode.FLASHPOINT
    @Condition getCurrentGamemode() != Gamemode.PUSH
    @Condition isMatchBetweenRounds() == true
    @Condition (teamScore(Team.1 if isTeamOnOffense(Team.1) else Team.2)) < (2 if getCurrentGamemode() == Gamemode.ASSAULT else 3)
    
    wait()
    if getCurrentGamemode() == Gamemode.ASSAULT:
        smallMessage(getAllPlayers(), "Setting {0}'s score to {1} to ensure map completion".format(Team.1 if isTeamOnOffense(Team.1) else Team.2, 2))
        setTeamScore(Team.1 if isTeamOnOffense(Team.1) else Team.2, 2)
    else:
        smallMessage(getAllPlayers(), "Setting {0}'s score to {1} to ensure map completion".format(Team.1 if isTeamOnOffense(Team.1) else Team.2, 3))
        setTeamScore(Team.1 if isTeamOnOffense(Team.1) else Team.2, 3)


rule "Map Completion: Force Match End After Two Rounds (Assault, Escort and Hybrid)":
    @Condition MapComp_ForceAsymTwoRounds != 2
    @Condition getCurrentGamemode() != Gamemode.CONTROL
    @Condition getCurrentGamemode() != Gamemode.FLASHPOINT
    @Condition getCurrentGamemode() != Gamemode.PUSH
    @Condition isMatchBetweenRounds() == true
    @Condition getMatchRound() == 2
    
    if MapComp_ForceAsymTwoRounds == 0 and (MapComp_TeamOneScore + MapComp_TeamTwoScore == (4 if getCurrentGamemode() == Gamemode.ASSAULT else 6)):
        smallMessage(getAllPlayers(), "Both teams completed map, match will proceed as normal")
    else:
        smallMessage(getAllPlayers(), "Ending match after two rounds")
        wait(1)
        declareDraw()


rule "Map Completion: Force Match End After Three Rounds (Control)":
    @Condition MapComp_ForceControlThreeRounds == true
    @Condition getCurrentGamemode() == Gamemode.CONTROL
    @Condition teamScore(Team.1) + teamScore(Team.2) == 3
    
    smallMessage(getAllPlayers(), "Ending match after three rounds")
    wait(1)
    declareTeamVictory(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2)


rule "Map Completion: Force Match End After Five Captures (Flashpoint)":
    @Condition MapComp_ForceFlashpointFiveCaps == true
    @Condition getCurrentGamemode() == Gamemode.FLASHPOINT
    @Condition teamScore(Team.1) + teamScore(Team.2) == 5
    
    smallMessage(getAllPlayers(), "Ending match after five captures")
    #Because of a bug with the Declare Team Victory action (it doesn't work), we'll need to use this workaround for now
    setTeamScore(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2, 10)
    declareRoundVictory(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2)
    waitUntil(isMatchComplete(), 99999)
    setTeamScore(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2, 5 - (teamScore(Team.2) if teamScore(Team.1) > teamScore(Team.2) else teamScore(Team.1)))
