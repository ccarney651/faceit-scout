settings {
    "main": {
        "description": "workshop.codes/scrimtimelite",
        "modeName": "ScrimTime Lite"
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
        " Control 6v6": {
            "enabled": false,
            "gamemodeStartTrigger": "immediately",
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "controlBalancedOverwatch": {
            "enabled": false,
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
            "scoreToWin": 3,
            "tankPassiveHealthBonus": "alwaysEnabled"
        },
        "escortBalancedOverwatch": {
            "enabled": false,
            "enableCompetitiveRules": true,
            "gamemodeStartTrigger": "immediately",
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
        "pushBalancedOverwatch": {
            "enabled": false,
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
        "Defender Teleport": [
            6
        ],
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
globalvar Keybind_ChangeLanguage 5
globalvar Text_LanguageTextArray 6
globalvar Text_EnableChangeLanguage 7
globalvar Text_DefaultLanguage 8
globalvar Colour_TeamOne 9
globalvar Colour_TeamTwo 10
globalvar Colour_TextTypeA 11
globalvar Colour_TextTypeB 12
globalvar Colour_TextTypeC 13
globalvar Debug_EnableDebugMode 14
globalvar Debug_DisplayServerLoad 15
globalvar Setup_RemoveAssemblingHeroes 17
globalvar Setup_SetupTimeOverride 18
globalvar Setup_AllowDefendersTeleport 19
globalvar ReadyUp_FreqMode 20
globalvar ReadyUp_CaptainMode 21
globalvar ReadyUp_EnableReadyVoiceLine 22
globalvar ReadyUp_MinimumPlayersToStart 23
globalvar ReadyUp_SetupCountdownTime 24
globalvar ReadyUp_FreezeSetupTime 25
globalvar ReadyUp_AllowForceTeamReady 26
globalvar ReadyUp_ForceTeamReadyHoldTime 27
globalvar MapComp_EnableMapCompletion 28
globalvar MapComp_ForceAsymTwoRounds 29
globalvar MapComp_ForceControlThreeRounds 30
globalvar MapComp_ForceFlashpointFiveCaps 31
globalvar MapComp_TeamOneScore 32
globalvar MapComp_TeamTwoScore 33
globalvar SetupAddTime_CaptainMode 42
globalvar SetupAddTime_Step 43
globalvar SetupAddTime_Max 44
globalvar Logs_AutoMatchEndTime 47

#Player variables

playervar Text_PlayerLanguage 0
playervar ReadyUp_PlayerReady 1
playervar ReadyUp_CurrentHoldTime 2

#Only remove the following directive if the gamemode does not use tricks such as A+0, A*0, A or "", "am" == "**", etc which would otherwise be optimized out.
#!optimizeStrict

rule "Settings: Language Options":
    Text_EnableChangeLanguage = createWorkshopSettingBool("1. Language", "Allow players to change language", true)
    Text_DefaultLanguage = createWorkshopSettingEnum("1. Language", "Default Language", 0, ["English", "Korean (한국어)", "Simplified Chinese (简体中文)", "Japanese (日本語)", "Spanish (Español)", "French (Français)", "Turkish (Türkçe)"])


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


rule "Settings: Keybind Options":
    Keybind_ButtonArray = [Button.PRIMARY_FIRE, Button.SECONDARY_FIRE, Button.ABILITY_1, Button.ABILITY_2, Button.ULTIMATE, Button.INTERACT, Button.JUMP, Button.CROUCH, Button.MELEE, Button.RELOAD]
    Keybind_Command = Keybind_ButtonArray[createWorkshopSettingEnum("5. Keybinds", "Command", 5, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"])]
    Keybind_Ready = Keybind_ButtonArray[createWorkshopSettingEnum("5. Keybinds", "Ready Up Toggle / Force Team Ready", 9, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 1)]
    Keybind_DefenderTeleport = Keybind_ButtonArray[createWorkshopSettingEnum("5. Keybinds", "Defender Teleport", 6, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 2)]
    Keybind_AddSetupTime = Keybind_ButtonArray[createWorkshopSettingEnum("5. Keybinds", "Add Setup Time", 4, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 3)]


rule "Settings: Debug Options":
    Debug_EnableDebugMode = createWorkshopSettingBool("6. Debug", "Enable Debug Mode", false)
    Debug_DisplayServerLoad = createWorkshopSettingBool("6. Debug", "Display Server Load", true, 1)
    Logs_AutoMatchEndTime = createWorkshopSettingInt("6. Debug", "Automatically End Match Time", 3600, 10, 3600, 2)


rule "Initialisation: Colours":
    Colour_TeamOne = rgb(50, 185, 240)
    Colour_TeamTwo = rgb(250, 5, 30)
    Colour_TextTypeA = rgb(255, 255, 255)
    Colour_TextTypeB = rgb(255, 155, 0)
    Colour_TextTypeC = rgb(40, 205, 60)


rule "Initialisation: Language Strings":
    Text_LanguageTextArray[0] = ["ScrimTime Lite", "ScrimTime Lite", "ScrimTime Lite", "ScrimTime Lite", "ScrimTime Lite", "ScrimTime Lite", "ScrimTime Lite"]
    Text_LanguageTextArray[1] = ["Countdown will start when", "카운트다운 시작 조건", "倒计时将在", "カウントダウンの開始条件", "La cuenta regresiva comenzará cuando", "Le compte à rebours commencera quand", "GERİ SAYIM"]
    Text_LanguageTextArray[2] = ["both teams are ready", "양쪽 팀 모두 준비", "双方队伍准备时开始", "両チームの準備が整い次第", "ambos equipos están listos", "les deux équipes sont prêtes", "HER İKİ TAKIM HAZIR OLDUĞUNDA BAŞLAYACAK"]
    Text_LanguageTextArray[3] = ["all players are ready", "모든 플레이어 준비", "所有玩家已准备时开始", "全員の準備が整い次第", "todos los jugadores están listos", "tous les joueurs sont prêts", "TÜM OYUNCULAR HAZIR OLDUĞUNDA BAŞLAYACAK"]
    Text_LanguageTextArray[4] = ["For more information, visit", "상세한 지침은 방문해주세요", "有关完整文档请访问", "フルドキュメンテーションは", "Para mas información, visita", "Pour plus d’informations, visitez", "DAHA FAZLA BİLGİ İÇİN"]
    Text_LanguageTextArray[5] = ["workshop.codes/scrimtimelite", "workshop.codes/scrimtimelite", "workshop.codes/scrimtimelite", "workshop.codes/scrimtimelite", "workshop.codes/scrimtimelite", "workshop.codes/scrimtimelite", "workshop.codes/scrimtimelite"]
    Text_LanguageTextArray[6] = ["Import code", "코드 가져 오기", "导入代码", "コードの読み込み", "Importar código", "Importer le code", "ATÖLYE KODU"]
    Text_LanguageTextArray[7] = ["0PP1T", "0PP1T", "0PP1T", "0PP1T", "0PP1T", "0PP1T", "0PP1T"]
    Text_LanguageTextArray[8] = ["You are readied up", "준비 완료 상태입니다", "你已准备就绪", "あなたは準備完了です", "Estás Preparado", "Vous êtes prêt", "HAZIRSIN"]
    Text_LanguageTextArray[9] = ["You are not readied up", "준비되지 않았습니다", "你未准备就绪", "あなたは準備中です", "No estás Preparado", "Vous n'êtes pas prêt", "HAZIR DEĞİLSİN"]
    Text_LanguageTextArray[10] = ["Ready Up", "준비 완료", "准备就绪", "準備完了", "Marcar Preparado", "Prêt", "HAZIR OL"]
    Text_LanguageTextArray[11] = ["Unready", "준비 취소", "取消准备", "準備中", "Desmarcar Preparado", "Pas prêt", "HAZIR DEĞİL"]
    Text_LanguageTextArray[12] = ["(Press) Ready Up / (Hold) Force Team Ready", "(누르기) 준비 완료 / (길게 누르기) 강제 팀 준비", "(按)准备就绪 / (按住)强制队伍准备", "(押して) 準備完了 / (押し続けて) チームを準備完了にする", "(Presione) Preparado / (Mantener presionado) Forzar Equipo Preparado", "(Appuyez) Prêt / (Maintenez) Forcer le prêt de l'équipe", "(BAS) HAZIR OL / (BASILI TUT) TAKIMI ZORLA HAZIRLA"]
    Text_LanguageTextArray[13] = ["(Press) Unready / (Hold) Force Team Ready", "(누르기) 준비 취소 / (길게 누르기) 강제 팀 준비", "(按)取消准备 / (按住)强制队伍准备", "(押して) 準備中 / (押し続けて) チームを準備完了にする", "(Presione) No preparado / (Mantener presionado) Forzar Equipo Preparado", "(Appuyez) Pas prêt / (Maintenez) Forcer la prêt de l'équipe", "(BAS) HAZIR DEĞİL / (BASILI TUT) TAKIMI ZORLA HAZIRLA"]
    Text_LanguageTextArray[14] = ["All players ready, starting countdown", "모두 준비됐습니다, 카운트다운 시작합니다", "所有玩家已准备就绪，开始倒计时", "全員の準備が整いました\u3000カウントダウンを開始します", "Todos los jugadores están listos, comenzando la cuenta regresiva", "Tous les joueurs sont prêts, début du compte à rebours", "TÜM OYUNCULAR HAZIR, GERİ SAYIM BAŞLIYOR"]
    Text_LanguageTextArray[15] = ["Both teams ready, starting countdown", "양 팀 모두 준비됐습니다 카운트다운 시작합니다", "双方队伍都已准备就绪，开始倒计时", "両チームの準備が整いました\u3000カウントダウンを開始します", "Ambos equipos están listos, comenzando la cuenta regresiva", "Les deux équipes sont prêtes, début du compte à rebours", "HER İKİ TAKIM DA HAZIR, GERİ SAYIM BAŞLIYOR"]
    Text_LanguageTextArray[16] = ["All players ready, but not enough players in game ([MIN_PLAYERS_TO_START])", "모든 플레이어가 준비되었지만 게임 플레이어 수가 충분하지 않음 ([MIN_PLAYERS_TO_START] 명 이상 필요)", "所有玩家已准备就绪，但游戏中玩家数不足([MIN_PLAYERS_TO_START])", "すべてのプレイヤーが準備完了していますが、ゲーム内のプレイヤーが足りません ([MIN_PLAYERS_TO_START])", "Todos los jugadores están listos, pero no hay suficientes jugadores en el juego ([MIN_PLAYERS_TO_START])", "Tous les joueurs sont prêts, mais il n'y a pas assez de joueurs dans le jeu ([MIN_PLAYERS_TO_START])", "TÜM OYUNCULAR HAZIR ANCAK OYUNDA YETERLİ SAYIDA OYUNCU YOK ([MIN_PLAYERS_TO_START])"]
    Text_LanguageTextArray[17] = ["Both teams ready, but not enough players in game ([MIN_PLAYERS_TO_START]", "양 팀 모두 준비되었지만 게임 플레이어 수가 충분하지 않음 ([MIN_PLAYERS_TO_START] 명 이상 필요)", "双方队伍都已准备就绪，但游戏中玩家数不足([MIN_PLAYERS_TO_START])", "両チームが準備完了していますが、ゲーム内のプレイヤーが足りません ([MIN_PLAYERS_TO_START])", "Ambos equipos están listos, pero no hay suficientes jugadores en el juego ([MIN_PLAYERS_TO_START]", "Les deux équipes sont prêtes, mais il n'y a pas assez de joueurs dans le jeu ([MIN_PLAYERS_TO_START])", "HER İKİ TAKIM DA HAZIR ANCAK OYUNDA YETERLİ SAYIDA OYUNCU YOK ([MIN_PLAYERS_TO_START])"]
    Text_LanguageTextArray[18] = ["[EVENT_PLAYER] unreadied, setup timer reset", "[EVENT_PLAYER]님이 준비 취소되었습니다 설정 타이머가 다시 시작합니다", "[EVENT_PLAYER] 取消准备，设置计时器重置", "[EVENT_PLAYER] が準備中になったため、マッチ準備時間がリセットされます", "[EVENT_PLAYER] no está preparado, temporizador de configuración reiniciado", "[EVENT_PLAYER] n'est plus prêt, le minuteur est remis à zéro", "[EVENT_PLAYER] HAZIR DEĞİL, HAZIRLIK SÜRESİ SIFIRLANIYOR"]
    Text_LanguageTextArray[19] = ["A team unreadied, setup timer reset", "한 팀이 준비 취소되었습니다 설정 타이머가 다시 시작합니다", "一支队伍取消准备，设置计时器重置", "チームが準備中になり、マッチ準備時間がリセットされます", "Un equipo no está preparado, temporizador de configuración reiniciado", "Une équipe n'est pas prête, le minuteur est remis à zéro", "BİR TAKIM ARTIK HAZIR DEĞİL, HAZIRLIK SÜRESİ SIFIRLANIYOR"]
    Text_LanguageTextArray[20] = ["[EVENT_PLAYER] set all players on [EVENT_PLAYER_TEAM] ready", "[EVENT_PLAYER]가 [EVENT_PLAYER_TEAM]의 모든 플레이어를 준비 상태로 강제로 변경했습니다", "[EVENT_PLAYER] 将所有玩家设置为 [EVENT_PLAYER_TEAM] 准备", "[EVENT_PLAYER] が [EVENT_PLAYER_TEAM] のメンバーを準備完了にしました", "[EVENT_PLAYER] estableció que todos los jugadores de [EVENT_PLAYER_TEAM] están preparados", "[EVENT_PLAYER] a mis tous les joueurs de [EVENT_PLAYER_TEAM] prêts", "[EVENT_PLAYER] [EVENT_PLAYER_TEAM] TAKIMINDAKİ TÜM OYUNCULARI HAZIR HALE GETİRDİ"]
    Text_LanguageTextArray[21] = ["Teleport to the objective", "목표지점으로 순간이동합니다", "传送到目标地点", "目標地点にテレポートします", "Teletransportarse al objetivo", "Téléporter à l'objectif", "HEDEFE IŞINLAN"]
    Text_LanguageTextArray[22] = ["Teleport back to spawn", "스폰 지점으로 순간이동합니다", "传送回重生点", "スポーンにテレポートします", "Teletransportarse de vuelta al spawn", "Téléporter au spawn", "BAŞLANGIÇ NOKTASINA GERİ IŞINLAN"]
    Text_LanguageTextArray[23] = ["Teleported to objective", "목표지점으로 순간이동했습니다", "传送到目标地点", "目標地点にテレポートしました", "Teletransportado al objetivo", "Téléporté à l'objectif", "HEDEFE IŞINLANDI"]
    Text_LanguageTextArray[24] = ["Teleported to spawn", "스폰 지점으로 순간이동했습니다", "传送到重生点", "スポーンにテレポートしました", "Teletransportado al spawn", "Téléporté à l'apparition", "BAŞLANGIÇ NOKTASINA IŞINLANDI"]
    Text_LanguageTextArray[25] = ["Unable to teleport, please try again later", "순간이동이 불가능합니다 나중에 다시 시도해주세요", "无法传送，请稍后重试", "テレポートできません、もう一度試してください", "No se puede teletransportar, inténtalo de nuevo más tarde", "Impossible de se téléporter, veuillez réessayer à un autre moment", "IŞINLANAMIYOR, LÜTFEN DAHA SONRA TEKRAR DENEYİN"]
    Text_LanguageTextArray[26] = ["Add [SETUP_TIME_STEP] sec to setup timer", "설정 타이머에 [SETUP_TIME_STEP] 초를 추가합니다", "将 [SETUP_TIME_STEP] 秒添加到设置计时器中", "マッチ準備時間に[SETUP_TIME_STEP]秒追加します", "Añadir [SETUP_TIME_STEP] segundos al temporizador de configuración", "Ajouter [SETUP_TIME_STEP] sec au minuteur de configuration", "HAZIRLIK SÜRESİNE [SETUP_TIME_STEP] SN EKLE"]
    Text_LanguageTextArray[27] = ["[TEAM_1_CAPTAIN] and [TEAM_2_CAPTAIN] can add [SETUP_TIME_STEP] sec to the setup timer", "[TEAM_1_CAPTAIN]과(와) [TEAM_2_CAPTAIN]은(는) 설정 타이머에 [SETUP_TIME_STEP]초를 추가할 수 있습니다", "[TEAM_1_CAPTAIN] 和 [TEAM_2_CAPTAIN] 可以将 [SETUP_TIME_STEP] 秒添加到设置计时器中", "[TEAM_1_CAPTAIN] と [TEAM_2_CAPTAIN] はマッチ準備時間に[SETUP_TIME_STEP]秒追加できます", "[TEAM_1_CAPTAIN] y [TEAM_2_CAPTAIN] pueden agregar [SETUP_TIME_STEP] segundos al temporizador de configuración", "[TEAM_1_CAPTAIN] et [TEAM_2_CAPTAIN] peuvent ajouter [SETUP_TIME_STEP] sec au minuteur de configuration", "[TEAM_1_CAPTAIN] VE [TEAM_2_CAPTAIN] HAZIRLIK SÜRESİNE [SETUP_TIME_STEP] SN EKLEYEBİLİR"]
    Text_LanguageTextArray[28] = ["[EVENT_PLAYER] added [SETUP_TIME_STEP] sec to setup timer", "[EVENT_PLAYER] 이(가) 설정 타이머에 [SETUP_TIME_STEP]초를 추가했습니다", "[EVENT_PLAYER] 将 [SETUP_TIME_STEP] 秒添加到设置计时器中", "[EVENT_PLAYER] がマッチ準備時間に[SETUP_TIME_STEP]秒追加しました", "[EVENT_PLAYER] agregó [SETUP_TIME_STEP] segundos al temporizador de configuración", "[EVENT_PLAYER] a ajouté [SETUP_TIME_STEP] sec au minuteur de configuration", "[EVENT_PLAYER] HAZIRLIK SÜRESİNE [SETUP_TIME_STEP] SN EKLEDİ"]
    Text_LanguageTextArray[29] = ["Setup timer cannot be extended beyond [SETUP_TIME_MAX]", "설정 타이머는 [SETUP_TIME_MAX] 이상으로 연장할 수 없습니다", "设置计时器不能超过 [SETUP_TIME_MAX]", "マッチ準備時間の限界は [SETUP_TIME_MAX] 秒です、これ以上の延長はできません", "El temporizador de configuración no puede extenderse más allá de [SETUP_TIME_MAX]", "Le minuteur de configuration ne peut pas être prolongé au-delà de [SETUP_TIME_MAX]", "HAZIRLIK SÜRESİ EN FAZLA[SETUP_TIME_MAX] OLABİLİR"]
    Text_LanguageTextArray[30] = ["Setting [ATTACKING_TEAM]'s score to [MAP_COMPLETION_SCORE] to ensure map completion", "[ATTACKING_TEAM]의 점수를 [MAP_COMPLETION_SCORE]로 설정하여 맵 완료를 보장합니다", "将 [ATTACKING_TEAM] 的得分设置为 [MAP_COMPLETION_SCORE]，以确保地图完成", "最終目標まで進めれるように、[ATTACKING_TEAM] のスコアを [MAP_COMPLETION_SCORE] に設定します", "Estableciendo la puntuación del equipo [ATTACKING_TEAM] en [MAP_COMPLETION_SCORE] para asegurar la finalización del mapa", "Définir le score de [ATTACKING_TEAM] à [MAP_COMPLETION_SCORE] pour assurer l'achèvement de la carte", "HARİTANIN TAMAMLANMASI İÇİN [ATTACKING_TEAM] TAKIMININ SKORU [MAP_COMPLETION_SCORE] OLARAK AYARLANDI"]
    Text_LanguageTextArray[31] = ["Both teams completed map, match will proceed as normal", "양 팀 모두 맵을 완료했습니다 매치는 일반적으로 진행됩니다", "双方队伍都完成了地图，比赛将按照正常进行", "両チームが最終目標まで進みました、マッチは通常通りに進行します", "Ambos equipos completaron el mapa, el partido continuará normalmente", "Les deux équipes ont terminé la carte, le match se poursuivra normalement", "HER İKİ TAKIM DA HARİTAYI TAMAMLADI, MAÇ NORMAL ŞEKİLDE DEVAM EDECEK"]
    Text_LanguageTextArray[32] = ["Ending match after two rounds", "2라운드 이후 매치를 종료합니다", "进行2轮比赛后结束比赛", "2ラウンド後にマッチを終了します", "Finalizando el partido después de 2 rondas", "Fin de la partie après 2 rounds", "2 TUR SONUNDA MAÇ SONLANDIRILIYOR"]
    Text_LanguageTextArray[33] = ["Ending match after three rounds", "3라운드 이후 매치를 종료합니다", "进行3轮比赛后结束比赛", "3ラウンド後にマッチを終了します", "Finalizando el partido después de 3 rondas", "Fin de la partie après 3 rounds", "3 TUR SONUNDA MAÇ SONLANDIRILIYOR"]
    Text_LanguageTextArray[34] = ["Ending match after five captures", "5라운드 이후 매치를 종료합니다", "进行5轮比赛后结束比赛", "5ラウンド後にマッチを終了します", "Finalizando el partido después de 5 rondas", "Fin de la partie après 5 rounds", "5 TUR SONUNDA MAÇ SONLANDIRILIYOR"]
    Text_LanguageTextArray[35] = ["Host toggled scoreboard on", "호스트가 스코어보드를 켰습니다", "主持人打开了记分牌", "ホストがスコアボードをオンにしました", "El anfitrión activó el marcador", "L'hôte a activé le tableau des scores", "YÖNETİCİ SKOR TABLOSUNU AÇTI"]
    Text_LanguageTextArray[36] = ["Host toggled scoreboard off", "호스트가 스코어보드를 껐습니다", "主持人关闭了记分牌", "ホストがスコアボードをオフにしました", "El anfitrión desactivó el marcador", "L'hôte a désactivé le tableau des scores", "YÖNETİCİ SKOR TABLOSUNU KAPATTI"]
    Text_LanguageTextArray[37] = ["● EN   ○ KR   ○ CN   ○ JP   ○ ES   ○ FR   ○ TR", "○ EN   ● KR   ○ CN   ○ JP   ○ ES   ○ FR   ○ TR", "○ EN   ○ KR   ● CN   ○ JP   ○ ES   ○ FR   ○ TR", "○ EN   ○ KR   ○ CN   ● JP   ○ ES   ○ FR   ○ TR", "○ EN   ○ KR   ○ CN   ○ JP   ● ES   ○ FR   ○ TR", "○ EN   ○ KR   ○ CN   ○ JP   ○ ES   ● FR   ○ TR", "○ EN   ○ KR   ○ CN   ○ JP   ○ ES   ○ FR   ● TR"]
    Text_LanguageTextArray[38] = ["Changed language to English", "한국어로 언어 변경됨", "已更改语言为简体中文", "言語が日本語に変更されました", "Cambiado el idioma a español", "Langue changée en français", "DİL İNGİLİZCE OLARAK DEĞİŞTİRİLDİ"]
    Text_LanguageTextArray[39] = ["Debug Mode is enabled", "디버그 모드가 활성화되었습니다", "调试模式已启用", "デバッグモードが有効です", "El modo de depuración está habilitado", "Le mode de débuggage est activé", "HATA AYIKLAMA MODU ETKİN"]


rule "Initialisation: Player":
    @Event eachPlayer
    
    eventPlayer.Text_PlayerLanguage = Text_DefaultLanguage
    eventPlayer.ReadyUp_PlayerReady = false


rule "HUD Setup: Setup Info":
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    
    #ScrimTime
    hudSubtext(getAllPlayers(), Text_LanguageTextArray[0][localPlayer.Text_PlayerLanguage], HudPosition.LEFT, 0, Colour_TextTypeB, HudReeval.VISIBILITY_AND_STRING)
    #Countdown will start when
    hudSubheader(getAllPlayers(), Text_LanguageTextArray[1][localPlayer.Text_PlayerLanguage], HudPosition.LEFT, 0.1, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    #both teams are ready / all players are ready
    hudSubheader(getAllPlayers(), Text_LanguageTextArray[2][localPlayer.Text_PlayerLanguage] if ReadyUp_CaptainMode == 1 else "{2} [{0}/{1}]".format(len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady)), max(getNumberOfPlayers(Team.ALL), ReadyUp_MinimumPlayersToStart), Text_LanguageTextArray[3][localPlayer.Text_PlayerLanguage]), HudPosition.LEFT, 0.1, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    #Team 1 Header
    hudSubtext(getAllPlayers(), Team.1, HudPosition.LEFT, 1, Colour_TeamOne, HudReeval.VISIBILITY_AND_STRING)
    #Team 2 Header
    hudSubtext(getAllPlayers(), Team.2, HudPosition.LEFT, 3, Colour_TeamTwo, HudReeval.VISIBILITY_AND_STRING)
    #Import Code
    hudSubheader(getAllPlayers(), "{0}".format(Text_LanguageTextArray[6][localPlayer.Text_PlayerLanguage]), HudPosition.RIGHT, 0, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    #DKEEH
    hudSubheader(getAllPlayers(), "{0}".format(Text_LanguageTextArray[7][localPlayer.Text_PlayerLanguage]), HudPosition.RIGHT, 0.1, Colour_TextTypeB, HudReeval.VISIBILITY_AND_STRING)
    #For full do***entation visit
    hudSubheader(getAllPlayers(), "{0}".format(Text_LanguageTextArray[4][localPlayer.Text_PlayerLanguage]), HudPosition.RIGHT, 0.2, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING)
    #workshop.codes/scrimtime
    hudSubheader(getAllPlayers(), "{0}".format(Text_LanguageTextArray[5][localPlayer.Text_PlayerLanguage]), HudPosition.RIGHT, 0.3, Colour_TextTypeB, HudReeval.VISIBILITY_AND_STRING)
    if Debug_EnableDebugMode:
        #Debug mode is enabled
        hudSubtext(getAllPlayers(), "{0} {1} {0}".format(iconString(Icon.WARNING), Text_LanguageTextArray[39][localPlayer.Text_PlayerLanguage]), HudPosition.TOP, 6.1, Colour_TextTypeB, HudReeval.VISIBILITY_AND_STRING)


rule "HUD Setup: Ready Toggle":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition isInSetup() == true
    
    if ReadyUp_CaptainMode == 0 or ReadyUp_CaptainMode == 1 and eventPlayer.getSlot() == 0:
        #Player Ready Status
        hudSubheader(getAllPlayers(), " {0} {1}".format("●" if eventPlayer.ReadyUp_PlayerReady else "○", eventPlayer), HudPosition.LEFT, (2 if eventPlayer.getTeam() == Team.1 else 4) + eventPlayer.getSlot() * 0.1, Colour_TextTypeC if eventPlayer.ReadyUp_PlayerReady else Colour_TextTypeB, HudReeval.VISIBILITY_STRING_AND_COLOR, SpecVisibility.ALWAYS)
        #You are readied up / You are not readied up
        hudSubtext(eventPlayer, Text_LanguageTextArray[8][localPlayer.Text_PlayerLanguage] if eventPlayer.ReadyUp_PlayerReady else Text_LanguageTextArray[9][localPlayer.Text_PlayerLanguage], HudPosition.TOP, 5.1, Colour_TextTypeC if eventPlayer.ReadyUp_PlayerReady else Colour_TextTypeB, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)
        if ReadyUp_CaptainMode == 0 and ReadyUp_AllowForceTeamReady:
            #(Press) Ready Up / Unready • (Hold) Force Team Ready
            hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_Ready), Text_LanguageTextArray[13][localPlayer.Text_PlayerLanguage] if eventPlayer.ReadyUp_PlayerReady else Text_LanguageTextArray[12][localPlayer.Text_PlayerLanguage]), HudPosition.TOP, 5.2, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_Ready) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)
        else:
            #Ready Up / Unready
            hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_Ready), Text_LanguageTextArray[11][localPlayer.Text_PlayerLanguage] if eventPlayer.ReadyUp_PlayerReady else Text_LanguageTextArray[10][localPlayer.Text_PlayerLanguage]), HudPosition.TOP, 5.2, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_Ready) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)


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
    
    #Teleport to the objective / Teleport back to spawn
    hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_DefenderTeleport), Text_LanguageTextArray[21][localPlayer.Text_PlayerLanguage] if eventPlayer.isInSpawnRoom() else Text_LanguageTextArray[22][localPlayer.Text_PlayerLanguage]), HudPosition.TOP, 5.3, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_DefenderTeleport) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)


rule "HUD Setup: Add Setup Time":
    @Event eachPlayer
    @Condition ReadyUp_FreqMode != 2
    @Condition (getMatchRound() == 1 or ReadyUp_FreqMode == 0) == true
    @Condition SetupAddTime_CaptainMode != 2
    @Condition isInSetup() == true
    
    if eventPlayer.getSlot() == 0 or SetupAddTime_CaptainMode == 0:
        #Add {0} sec to setup timer
        hudSubheader(eventPlayer, "[{0} + {1}] {2}".format(inputBindingString(Keybind_Command), inputBindingString(Keybind_AddSetupTime), Text_LanguageTextArray[26][localPlayer.Text_PlayerLanguage].replace("[SETUP_TIME_STEP]", SetupAddTime_Step)), HudPosition.TOP, 5.4, Colour_TextTypeB if eventPlayer.isHoldingButton(Keybind_Command) and eventPlayer.isHoldingButton(Keybind_AddSetupTime) else Colour_TextTypeA, HudReeval.STRING_AND_COLOR, SpecVisibility.NEVER)
    else:
        #Add {0} sec to setup timer
        hudSubheader(eventPlayer, Text_LanguageTextArray[27][localPlayer.Text_PlayerLanguage].replace("[TEAM_1_CAPTAIN]", "{0}".format(getPlayersInSlot(0, Team.1))).replace("[TEAM_2_CAPTAIN]", "{0}".format(getPlayersInSlot(0, Team.2))).replace("[SETUP_TIME_STEP]", SetupAddTime_Step), HudPosition.TOP, 5.4, Colour_TextTypeA, HudReeval.STRING, SpecVisibility.NEVER)


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
            smallMessage(getAllPlayers(), Text_LanguageTextArray[28][localPlayer.Text_PlayerLanguage].replace("[SETUP_TIME_STEP]", SetupAddTime_Step).replace("[EVENT_PLAYER]", "{0}".format(eventPlayer)))
    else:
        #Setup timer cannot be extended beyond [SETUP_TIME_MAX]
        smallMessage(eventPlayer, Text_LanguageTextArray[29][localPlayer.Text_PlayerLanguage].replace("[SETUP_TIME_MAX]", "{0}:{1}{2}".format(floor(SetupAddTime_Max / 60), "0" if SetupAddTime_Max % 60 < 10 else "", floor(SetupAddTime_Max % 60))))


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
            #Teleported to objective
            smallMessage(eventPlayer, "{0}".format(Text_LanguageTextArray[23][localPlayer.Text_PlayerLanguage]))
        else:
            #Unable to teleport, please try again later
            smallMessage(eventPlayer, "{0}".format(Text_LanguageTextArray[25][localPlayer.Text_PlayerLanguage]))
    else:
        eventPlayer.teleport(getSpawnPoints(eventPlayer.getTeam()))
        #Teleported to spawn
        smallMessage(eventPlayer, "{0}".format(Text_LanguageTextArray[24][localPlayer.Text_PlayerLanguage]))


rule "Setup: Change Player Language":
    @Event eachPlayer
    @Condition Text_EnableChangeLanguage == true
    @Condition isInSetup() == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_ChangeLanguage) == true
    
    eventPlayer.Text_PlayerLanguage = (eventPlayer.Text_PlayerLanguage + 1) % len(Text_LanguageTextArray[0])
    #Changed language to English
    smallMessage(eventPlayer, Text_LanguageTextArray[38][eventPlayer.Text_PlayerLanguage])


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
                #[EVENT_PLAYER] set all players on [EVENT_PLAYER_TEAM] ready
                smallMessage(getAllPlayers(), Text_LanguageTextArray[20][localPlayer.Text_PlayerLanguage].replace("[EVENT_PLAYER]", "{0}".format(eventPlayer)).replace("[EVENT_PLAYER_TEAM]", "{0}".format(eventPlayer.getTeam())))
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
        #Both teams ready, but not enough players in game ([MIN_PLAYERS_TO_START])
        smallMessage(getAllPlayers(), Text_LanguageTextArray[17][localPlayer.Text_PlayerLanguage].replace("[MIN_PLAYERS_TO_START]", ReadyUp_MinimumPlayersToStart))
        return
    #Both teams ready, starting countdown
    smallMessage(getAllPlayers(), Text_LanguageTextArray[15][localPlayer.Text_PlayerLanguage])
    if ReadyUp_FreezeSetupTime:
        unpauseMatchTime()
    setMatchTime(ReadyUp_SetupCountdownTime)
    waitUntil(getPlayersInSlot(0, Team.1).ReadyUp_PlayerReady == false or getPlayersInSlot(0, Team.2).ReadyUp_PlayerReady == false, ReadyUp_SetupCountdownTime)
    if isInSetup() and getPlayersInSlot(0, Team.1).ReadyUp_PlayerReady == false or getPlayersInSlot(0, Team.2).ReadyUp_PlayerReady == false:
        #A team unreadied, setup timer reset
        smallMessage(getAllPlayers(), Text_LanguageTextArray[19][localPlayer.Text_PlayerLanguage])
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
        #All players ready, but not enough players in game ([MIN_PLAYERS_TO_START])
        smallMessage(getAllPlayers(), Text_LanguageTextArray[16][localPlayer.Text_PlayerLanguage].replace("[MIN_PLAYERS_TO_START]", ReadyUp_MinimumPlayersToStart))
        return
    #All players ready, starting countdown
    smallMessage(getAllPlayers(), Text_LanguageTextArray[14][localPlayer.Text_PlayerLanguage])
    if ReadyUp_FreezeSetupTime:
        unpauseMatchTime()
    setMatchTime(ReadyUp_SetupCountdownTime)
    waitUntil(len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady == true)) < len(getAllPlayers()), ReadyUp_SetupCountdownTime)
    if isInSetup() and len(getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady == true)) < len(getAllPlayers()):
        #[EVENT_PLAYER] unreadied, setup timer reset
        smallMessage(getAllPlayers(), Text_LanguageTextArray[18][localPlayer.Text_PlayerLanguage].replace("[EVENT_PLAYER]", (getAllPlayers().filter(lambda player: player.ReadyUp_PlayerReady == false))[0]))
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
        smallMessage(getAllPlayers(), (Text_LanguageTextArray[30][localPlayer.Text_PlayerLanguage].replace("[ATTACKING_TEAM]", Team.1 if isTeamOnOffense(Team.1) else Team.2)).replace("[MAP_COMPLETION_SCORE]", 2 + 0))
        setTeamScore(Team.1 if isTeamOnOffense(Team.1) else Team.2, 2)
    else:
        smallMessage(getAllPlayers(), (Text_LanguageTextArray[30][localPlayer.Text_PlayerLanguage].replace("[ATTACKING_TEAM]", Team.1 if isTeamOnOffense(Team.1) else Team.2)).replace("[MAP_COMPLETION_SCORE]", 3 + 0))
        setTeamScore(Team.1 if isTeamOnOffense(Team.1) else Team.2, 3)


rule "Map Completion: Force Match End After Two Rounds (Assault, Escort and Hybrid)":
    @Condition MapComp_ForceAsymTwoRounds != 2
    @Condition getCurrentGamemode() != Gamemode.CONTROL
    @Condition getCurrentGamemode() != Gamemode.FLASHPOINT
    @Condition getCurrentGamemode() != Gamemode.PUSH
    @Condition isMatchBetweenRounds() == true
    @Condition getMatchRound() == 2
    
    if MapComp_ForceAsymTwoRounds == 0 and (MapComp_TeamOneScore + MapComp_TeamTwoScore == (4 if getCurrentGamemode() == Gamemode.ASSAULT else 6)):
        #Both teams completed map, match will proceed as normal
        smallMessage(getAllPlayers(), Text_LanguageTextArray[31][localPlayer.Text_PlayerLanguage])
    else:
        #Ending match after two rounds
        smallMessage(getAllPlayers(), Text_LanguageTextArray[32][localPlayer.Text_PlayerLanguage])
        wait(1)
        declareDraw()


rule "Map Completion: Force Match End After Three Rounds (Control)":
    @Condition MapComp_ForceControlThreeRounds == true
    @Condition getCurrentGamemode() == Gamemode.CONTROL
    @Condition teamScore(Team.1) + teamScore(Team.2) == 3
    
    #Ending match after three rounds
    smallMessage(getAllPlayers(), Text_LanguageTextArray[33][localPlayer.Text_PlayerLanguage])
    wait(1)
    declareTeamVictory(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2)


rule "Map Completion: Force Match End After Five Captures (Flashpoint)":
    @Condition MapComp_ForceFlashpointFiveCaps == true
    @Condition getCurrentGamemode() == Gamemode.FLASHPOINT
    @Condition teamScore(Team.1) + teamScore(Team.2) == 5
    
    #Ending match after five captures
    smallMessage(getAllPlayers(), Text_LanguageTextArray[34][localPlayer.Text_PlayerLanguage])
    #Because of a bug with the Declare Team Victory action (it doesn't work), we'll need to use this workaround for now
    setTeamScore(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2, 10)
    declareRoundVictory(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2)
    waitUntil(isMatchComplete(), 99999)
    setTeamScore(Team.1 if teamScore(Team.1) > teamScore(Team.2) else Team.2, 5 - (teamScore(Team.2) if teamScore(Team.1) > teamScore(Team.2) else teamScore(Team.1)))


rule "Debug: Force Ready (Interact + Ability 1)":
    @Event eachPlayer
    @Condition Debug_EnableDebugMode == true
    @Condition isInSetup() == true
    @Condition hostPlayer.isHoldingButton(Button.INTERACT) == true
    @Condition hostPlayer.isHoldingButton(Button.ABILITY_1) == true
    
    getAllPlayers().ReadyUp_PlayerReady = true


rule "Debug: Reduce Timer to 5 (Interact + Alt Fire)":
    @Event eachPlayer
    @Condition Debug_EnableDebugMode == true
    @Condition hostPlayer.isHoldingButton(Button.INTERACT) == true
    @Condition hostPlayer.isHoldingButton(Button.SECONDARY_FIRE) == true
    
    setMatchTime(5)


rule "Debug: Spawn Test Bot (Interact + Melee)":
    @Condition Debug_EnableDebugMode == true
    @Condition hostPlayer.isHoldingButton(Button.INTERACT) == true
    @Condition hostPlayer.isHoldingButton(Button.MELEE) == true
    
    createDummy(Hero.REAPER, getOppositeTeam(hostPlayer.getTeam()), -1, hostPlayer.getPosition())


rule "Debug: Automatically End Match":
    @Condition Debug_EnableDebugMode == true
    @Condition Logs_AutoMatchEndTime < 3600
    
    wait(Logs_AutoMatchEndTime)
    declareTeamVictory(Team.ALL)


rule "Debug: Display Server Loads":
    @Condition Debug_EnableDebugMode == true
    @Condition Debug_DisplayServerLoad == true
    @Condition isGameInProgress() == true
    
    wait()
    hudSubheader(getAllPlayers(), "{0} Current Server Load\r\n{1} Average Server Load\r\n{2} Peak Server Load".format(getServerLoad(), getAverageServerLoad(), getPeakServerLoad()), HudPosition.LEFT, 100, Colour_TextTypeA, HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)


