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
globalvar Scoreboard_DisplayLegend 31
globalvar Scoreboard_GroupMode 32
globalvar Scoreboard_Size 33
globalvar Scoreboard_DisplayMatchTime 34
globalvar SetupAddTime_CaptainMode 35
globalvar SetupAddTime_Step 36
globalvar SetupAddTime_Max 37

#Player variables

playervar ReadyUp_PlayerReady 0
playervar ReadyUp_CurrentHoldTime 1

#Only remove the following directive if the gamemode does not use tricks such as A+0, A*0, A or "", "am" == "**", etc which would otherwise be optimized out.
#!optimizeStrict

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
    Scoreboard_GroupMode = createWorkshopSettingEnum("5. Spectator Scoreboard", "Player Grouping Style", 0, ["Group by role, sort by team", "Group by team, sort by role", "Group by team, sort by slot"], 2)
    Scoreboard_DisplayLegend = createWorkshopSettingBool("5. Spectator Scoreboard", "Display Legend", true, 3)
    Scoreboard_DisplayMatchTime = createWorkshopSettingBool("5. Spectator Scoreboard", "Display Match Time", true, 4)
    Scoreboard_AllowHideScoreboard = createWorkshopSettingBool("5. Spectator Scoreboard", "Allow Host Spectator to Toggle Scoreboard", true, 5)


rule "Settings: Keybind Options":
    Keybind_ButtonArray = [Button.PRIMARY_FIRE, Button.SECONDARY_FIRE, Button.ABILITY_1, Button.ABILITY_2, Button.ULTIMATE, Button.INTERACT, Button.JUMP, Button.CROUCH, Button.MELEE, Button.RELOAD]
    Keybind_Command = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Command", 5, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"])]
    Keybind_Ready = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Ready Up Toggle / Force Team Ready", 9, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 1)]
    Keybind_DefenderTeleport = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Defender Teleport", 6, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 2)]
    Keybind_AddSetupTime = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Add Setup Time", 4, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 3)]


rule "Initialisation: Match":
    disableInspector()


rule "Initialisation: Colours":
    Colour_TeamOne = rgb(50, 185, 240)
    Colour_TeamTwo = rgb(250, 5, 30)
    Colour_TextTypeA = rgb(255, 255, 255)
    Colour_TextTypeB = rgb(255, 155, 0)
    Colour_TextTypeC = rgb(40, 205, 60)


rule "Initialisation: Player":
    @Event eachPlayer
    
    eventPlayer.ReadyUp_PlayerReady = false


rule "HUD Setup: Setup Info":
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    
    hudSubtext(getAllPlayers(), "OWDB SCRIM", HudPosition.LEFT, 0, Colour_TextTypeB, HudReeval.VISIBILITY_AND_STRING)
    hudSubheader(getAllPlayers(), "Countdown will start when", HudPosition.LEFT, 0.1, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    hudSubheader(getAllPlayers(), "both teams are ready" if ReadyUp_CaptainMode == 1 else "{2} [{0}/{1}]".format(len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady)), max(getNumberOfPlayers(Team.ALL), ReadyUp_MinimumPlayersToStart), "all players are ready"), HudPosition.LEFT, 0.1, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    hudSubtext(getAllPlayers(), Team.1, HudPosition.LEFT, 1, Colour_TeamOne, HudReeval.VISIBILITY_AND_STRING)
    hudSubtext(getAllPlayers(), Team.2, HudPosition.LEFT, 3, Colour_TeamTwo, HudReeval.VISIBILITY_AND_STRING)


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


rule "Scoreboard: Create Legend (Standard)":
    @Condition isGameInProgress() == true
    @Condition Scoreboard_EnableScoreboard == true
    @Condition Scoreboard_DisplayLegend == true
    
    wait()
    if Scoreboard_Size == 0:
        if Scoreboard_GroupMode == 0:
            hudSubheader(null, "{0} {1}".format(abilityIconString(Hero.GENJI, Button.ULTIMATE), "K • D • DD • DT • ACC • UU"), HudPosition.LEFT, 1, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubheader(null, "{0} {1}".format(abilityIconString(Hero.REINHARDT, Button.SECONDARY_FIRE), "K • D • DD • DT • DB • UU"), HudPosition.LEFT, 2, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubheader(null, "{0} {1}".format(abilityIconString(Hero.BAPTISTE, Button.ABILITY_1), "K • D • DD • DT • HD • UU"), HudPosition.LEFT, 3, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
        else:
            hudSubheader(null, "{0} {1}".format(abilityIconString(Hero.GENJI, Button.ULTIMATE), "K • D • DD • DT • ACC • UU"), HudPosition.LEFT, 1.1, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubheader(null, "{0} {1}".format(abilityIconString(Hero.REINHARDT, Button.SECONDARY_FIRE), "K • D • DD • DT • DB • UU"), HudPosition.LEFT, 1.2, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubheader(null, "{0} {1}".format(abilityIconString(Hero.BAPTISTE, Button.ABILITY_1), "K • D • DD • DT • HD • UU"), HudPosition.LEFT, 1.3, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
    else:
        if Scoreboard_GroupMode == 0:
            hudSubtext(null, "{0} {1}".format(abilityIconString(Hero.GENJI, Button.ULTIMATE), "K • D • DD • DT • ACC • UU"), HudPosition.LEFT, 1, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubtext(null, "{0} {1}".format(abilityIconString(Hero.REINHARDT, Button.SECONDARY_FIRE), "K • D • DD • DT • DB • UU"), HudPosition.LEFT, 2, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubtext(null, "{0} {1}".format(abilityIconString(Hero.BAPTISTE, Button.ABILITY_1), "K • D • DD • DT • HD • UU"), HudPosition.LEFT, 3, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
        else:
            hudSubtext(null, "{0} {1}".format(abilityIconString(Hero.GENJI, Button.ULTIMATE), "K • D • DD • DT • ACC • UU"), HudPosition.LEFT, 1.1, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubtext(null, "{0} {1}".format(abilityIconString(Hero.REINHARDT, Button.SECONDARY_FIRE), "K • D • DD • DT • DB • UU"), HudPosition.LEFT, 1.2, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)
            hudSubtext(null, "{0} {1}".format(abilityIconString(Hero.BAPTISTE, Button.ABILITY_1), "K • D • DD • DT • HD • UU"), HudPosition.LEFT, 1.3, Colour_TextTypeA, HudReeval.NONE, SpecVisibility.ALWAYS)


rule "Scoreboard: Create Player Entries (Small)":
    @Event eachPlayer
    @Condition isGameInProgress() == true
    @Condition Scoreboard_EnableScoreboard == true
    @Condition Scoreboard_Size == 0
    
    wait()
    if Scoreboard_GroupMode == 0:
        hudSubheader(null, "{0} {1} • {2}".format(heroIcon(eventPlayer.getHero()), "{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))), HudPosition.LEFT, (1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3) + (0.1 if eventPlayer.getTeam() == Team.1 else 0.2), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)
    elif Scoreboard_GroupMode == 1:
        hudSubheader(null, "{0} {1} • {2}".format(heroIcon(eventPlayer.getHero()), "{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))), HudPosition.LEFT, ((1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3) * 0.1) + (2 if eventPlayer.getTeam() == Team.1 else 3), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)
    else:
        hudSubheader(null, "{0} {1} • {2}".format(heroIcon(eventPlayer.getHero()), "{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))), HudPosition.LEFT, eventPlayer.getSlot() * 0.1 + (2 if eventPlayer.getTeam() == Team.1 else 3), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)


rule "Scoreboard: Create Player Entries (Medium)":
    @Event eachPlayer
    @Condition isGameInProgress() == true
    @Condition Scoreboard_EnableScoreboard == true
    @Condition Scoreboard_Size == 1
    
    wait()
    if Scoreboard_GroupMode == 0:
        hudSubtext(null, "{0} {1} • {2}".format(heroIcon(eventPlayer.getHero()), "{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))), HudPosition.LEFT, (1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3) + (0.1 if eventPlayer.getTeam() == Team.1 else 0.2), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)
    elif Scoreboard_GroupMode == 1:
        hudSubtext(null, "{0} {1} • {2}".format(heroIcon(eventPlayer.getHero()), "{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))), HudPosition.LEFT, ((1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3) * 0.1) + (2 if eventPlayer.getTeam() == Team.1 else 3), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)
    else:
        hudSubtext(null, "{0} {1} • {2}".format(heroIcon(eventPlayer.getHero()), "{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED))), HudPosition.LEFT, eventPlayer.getSlot() * 0.1 + (2 if eventPlayer.getTeam() == Team.1 else 3), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)


rule "Scoreboard: Create Player Entries (Large)":
    @Event eachPlayer
    @Condition isGameInProgress() == true
    @Condition Scoreboard_EnableScoreboard == true
    @Condition Scoreboard_Size == 2
    
    wait()
    if Scoreboard_GroupMode == 0:
        hudText(null, heroIcon(eventPlayer.getHero()), eventPlayer, "{1} • {2}".format("{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED)), null), HudPosition.LEFT, (1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3) + (0.1 if eventPlayer.getTeam() == Team.1 else 0.2), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, Colour_TextTypeA, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)
    elif Scoreboard_GroupMode == 1:
        hudText(null, heroIcon(eventPlayer.getHero()), eventPlayer, "{1} • {2}".format("{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED)), null), HudPosition.LEFT, ((1 if eventPlayer.getHero() in getDamageHeroes() else 2 if eventPlayer.getHero() in getTankHeroes() else 3) * 0.1) + (2 if eventPlayer.getTeam() == Team.1 else 3), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, Colour_TextTypeA, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)
    else:
        hudText(null, heroIcon(eventPlayer.getHero()), eventPlayer, "{1} • {2}".format("{0} • {1} • {2}".format(eventPlayer.getStatistic(Stat.FINAL_BLOWS), eventPlayer.getStatistic(Stat.DEATHS), round(eventPlayer.getStatistic(Stat.HERO_DAMAGE_DEALT))), "{0} • {1} • {2}".format(round(eventPlayer.getStatistic(Stat.DAMAGE_TAKEN)), round(eventPlayer.getStatistic(Stat.DAMAGE_BLOCKED)) if eventPlayer.getHero() in getTankHeroes() else round(eventPlayer.getStatistic(Stat.HEALING_DEALT)) if eventPlayer.getHero() in getSupportHeroes() else "{0}%".format(round(eventPlayer.getHeroStatistic(eventPlayer.getHero(), HeroStat.WEAPON_ACCURACY) * 100)), eventPlayer.getStatistic(Stat.ULTIMATES_USED)), null), HudPosition.LEFT, eventPlayer.getSlot() * 0.1 + (2 if eventPlayer.getTeam() == Team.1 else 3), Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, Colour_TeamOne if eventPlayer.getTeam() == Team.1 else Colour_TeamTwo, Colour_TextTypeA, HudReeval.SORT_ORDER_AND_STRING, SpecVisibility.ALWAYS)


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


rule "Map Completion: Ensure Map Completion (Assault, Escort and Hybrid)":
    @Condition MapComp_EnableMapCompletion == true
    @Condition isMatchBetweenRounds() == true
    @Condition getCurrentGamemode() != Gamemode.CONTROL
    @Condition getCurrentGamemode() != Gamemode.FLASHPOINT
    @Condition getCurrentGamemode() != Gamemode.PUSH
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
