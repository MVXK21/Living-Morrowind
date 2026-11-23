-- Living Morrowind: OpenMW 0.51 Core Orchestrator
local self     = require('openmw.self')
local types    = require('openmw.types')
local nearby   = require('openmw.nearby')
local ui       = require('openmw.ui')
local input    = require('openmw.input')
local util     = require('openmw.util')
local core     = require('openmw.core')
local I        = require('openmw.interfaces')

local sentIPC  = require('scripts.living_morrowind.sent_ipc')
local sentSer  = require('scripts.living_morrowind.sent_serialize')
local sentUI   = require('scripts.living_morrowind.sent_ui')
local sentChat = require('scripts.living_morrowind.sent_dialogue_chat')
local sentGuard = require('scripts.living_morrowind.sent_input_guard')

local UI       = I.UI
local Controls = I.Controls

-- ─── State ───────────────────────────────────────────────────────────────────
local rootWindow        = nil
local activeNPC         = nil
local isInterfaceActive = false
local isListening       = false
local listeningNPCs     = {}
local reqCounter        = 0
local currentReqId      = ""
local isThinking        = false
local lastRequestType   = nil
local pendingCallback   = nil
local chatMessages      = {}
local scrollOffset      = 0
local winPosition       = util.vector2(0, 0)
local winSize           = util.vector2(540, 480)
local isDragging        = false
local dragStartPos      = nil
local isResizing        = false
local resizeStartPos    = nil
local currentOfferedItems   = nil
local currentRequestedItems = nil

local inputText              = ""
local errorMessage           = nil
local lastInterfaceCloseTime = 0   -- stamped when AI chat window closes (for inv grace window)
local rebuildWindow, closeWindow, addMessage, logActionEvent, sendAIRequest

-- Estimates rendered pixel height of a text string at approx 500px width, MWUI font
local CHARS_PER_LINE = 46   -- approx chars per line at content width
local LINE_HEIGHT    = 22   -- px per line including leading
local MSG_SPACING    = 6    -- px spacer widget between messages

local function estimateMsgHeight(fullText)
    if not fullText or fullText == "" then return 0 end
    local lineCount = 0
    for line in (fullText .. "\n"):gmatch("([^\r\n]*)\r?\n") do
        if #line == 0 then
            lineCount = lineCount + 1
        else
            lineCount = lineCount + math.max(1, math.ceil(#line / CHARS_PER_LINE))
        end
    end
    return math.max(1, lineCount) * LINE_HEIGHT + MSG_SPACING
end

local function calculateMaxScroll()
    local vpHeight = (winSize and winSize.y) and math.max(180, winSize.y - 160) or 300
    local total = 0
    for _, msg in ipairs(chatMessages) do
        total = total + estimateMsgHeight(msg.sender .. ": " .. msg.text)
    end
    if isThinking then total = total + estimateMsgHeight("[ Thinking... ]") end
    if errorMessage then total = total + 120 end
    return math.max(0, total - vpHeight + 24)
end

local function scrollToBottom()
    scrollOffset = calculateMaxScroll()
end

rebuildWindow = function()
    local canVanillaShop = false
    pcall(function()
        if activeNPC and types.NPC.record then
            local r = types.NPC.record(activeNPC)
            if r and r.servicesOffered and r.servicesOffered.Barter then
                canVanillaShop = true
            end
        end
    end)

    local state = {
        activeNPC      = activeNPC,
        npcName        = sentSer.getNPCName(activeNPC),
        npcDisposition = sentSer.getNPCDisposition(activeNPC),
        chatMessages   = chatMessages,
        isThinking     = isThinking,
        inputText      = inputText,
        scrollOffset   = scrollOffset,
        winPosition    = winPosition,
        winSize        = winSize,
        isMoving       = isDragging,
        errorMessage   = errorMessage,
        offeredItems   = currentOfferedItems,
        requestedItems = currentRequestedItems,
        canShop        = canVanillaShop,
    }

    local callbacks = {
        onInput = function(text)
            inputText = text
        end,
        onTextChanged = function(text)
            inputText = text
        end,
        onSend = function()
            local text = inputText:match("^%s*(.-)%s*$")
            if text and text ~= "" then
                inputText = ""
                sendAIRequest(text, false)
            end
        end,
        onMoveLeft = function()
            winPosition = util.vector2(math.max(-800, winPosition.x - 150), winPosition.y)
            print(string.format("[LIVINGMW_UI] Window shifted Left -> pos=(%d, %d)", winPosition.x, winPosition.y))
            if rootWindow then rootWindow:destroy(); rootWindow = nil end
            rebuildWindow()
        end,
        onMoveCenter = function()
            winPosition = util.vector2(0, 0)
            print("[LIVINGMW_UI] Window centered -> pos=(0, 0)")
            if rootWindow then rootWindow:destroy(); rootWindow = nil end
            rebuildWindow()
        end,
        onMoveRight = function()
            winPosition = util.vector2(math.min(800, winPosition.x + 150), winPosition.y)
            print(string.format("[LIVINGMW_UI] Window shifted Right -> pos=(%d, %d)", winPosition.x, winPosition.y))
            if rootWindow then rootWindow:destroy(); rootWindow = nil end
            rebuildWindow()
        end,
        onToggleSize = function()
            if winSize.x > 600 then
                winSize = util.vector2(540, 480)
            else
                winSize = util.vector2(740, 580)
            end
            print(string.format("[LIVINGMW_UI] Window size toggled -> size=(%d, %d)", winSize.x, winSize.y))
            if rootWindow then rootWindow:destroy(); rootWindow = nil end
            rebuildWindow()
        end,
        onDismissError = function()
            print("[LIVINGMW_UI] Error dismissed")
            errorMessage = nil
            rebuildWindow()
        end,
        onMoveToggle = function()
            isDragging = not isDragging
            rebuildWindow()
        end,
        onDragStart = function(mousePos)
            dragStartPos = mousePos
        end,
        onDrag = function(mousePos)
            if dragStartPos then
                local delta = mousePos - dragStartPos
                winPosition = winPosition + delta
                dragStartPos = mousePos
                rebuildWindow()
            end
        end,
        onDragEnd = function()
            dragStartPos = nil
        end,
        onResizeStart = function(mousePos)
            isResizing = true
            resizeStartPos = mousePos
        end,
        onResize = function(mousePos)
            if isResizing and resizeStartPos then
                local delta = mousePos - resizeStartPos
                local newX = math.max(400, math.min(1000, winSize.x + delta.x))
                local newY = math.max(300, math.min(800, winSize.y + delta.y))
                winSize = util.vector2(newX, newY)
                resizeStartPos = mousePos
                rebuildWindow()
            end
        end,
        onResizeEnd = function()
            isResizing = false
            resizeStartPos = nil
        end,
        onScrollUp = function()
            local maxScroll = calculateMaxScroll()
            scrollOffset = math.max(0, scrollOffset - 60)
            rebuildWindow()
        end,
        onScrollDown = function()
            local maxScroll = calculateMaxScroll()
            scrollOffset = math.min(maxScroll, scrollOffset + 60)
            rebuildWindow()
        end,
        onScroll = function(direction)
            local maxScroll = calculateMaxScroll()
            local dirNum = (type(direction) == "number") and direction or ((type(direction) == "table" and direction.y) or 0)
            if dirNum > 0 then
                scrollOffset = math.max(0, scrollOffset - 45)
            else
                scrollOffset = math.min(maxScroll, scrollOffset + 45)
            end
            rebuildWindow()
        end,
        onShop = function()
            if activeNPC then
                local shopTarget = activeNPC
                closeWindow()
                pcall(function()
                    I.UI.setMode('Barter', { target = shopTarget })
                end)
            end
        end,

        onAcceptOffer = function(items, itemDesc)
            currentOfferedItems = nil
            pcall(function()
                core.sendGlobalEvent("LivingMW_GiveItem", { target = self.object or self, items = items })
            end)
            local sName = activeNPC and sentSer.getNPCName(activeNPC) or "NPC"
            local pName = sentSer.getPlayerData().name or "Player"
            local curCell = (self.cell and self.cell.name) or "Unknown Cell"
            addMessage("YOU", "Accepted " .. (itemDesc or "items") .. " from " .. sName .. ".")
            pcall(function()
                if logActionEvent then
                    logActionEvent(pName .. " accepted " .. (itemDesc or "items") .. " from " .. sName .. " in " .. curCell .. ".")
                end
            end)
            rebuildWindow()
            _G.__smw_sendAI("The player accepted " .. (itemDesc or "items") .. " from you.", false)
        end,
        onDeclineOffer = function(items, itemDesc)
            currentOfferedItems = nil
            local sName = activeNPC and sentSer.getNPCName(activeNPC) or "NPC"
            local pName = sentSer.getPlayerData().name or "Player"
            local curCell = (self.cell and self.cell.name) or "Unknown Cell"
            addMessage("YOU", "Declined " .. (itemDesc or "items") .. " offered by " .. sName .. ".")
            pcall(function()
                if logActionEvent then
                    logActionEvent(pName .. " declined " .. (itemDesc or "items") .. " offered by " .. sName .. " in " .. curCell .. ".")
                end
            end)
            rebuildWindow()
            _G.__smw_sendAI("The player declined " .. (itemDesc or "items") .. " offered by you.", false)
        end,
        onGiveItem = function(items, itemDesc)
            currentRequestedItems = nil
            pcall(function()
                core.sendGlobalEvent("LivingMW_TakeItem", { source = self.object or self, target = activeNPC, items = items })
            end)
            local sName = activeNPC and sentSer.getNPCName(activeNPC) or "NPC"
            local pName = sentSer.getPlayerData().name or "Player"
            local curCell = (self.cell and self.cell.name) or "Unknown Cell"
            addMessage("YOU", "Handed over " .. (itemDesc or "items") .. " to " .. sName .. ".")
            pcall(function()
                if logActionEvent then
                    logActionEvent(pName .. " traded/handed over " .. (itemDesc or "items") .. " to " .. sName .. " in " .. curCell .. ".")
                end
            end)
            rebuildWindow()
            _G.__smw_sendAI("The player handed over " .. (itemDesc or "items") .. " to you.", false)
        end,
        onRefuseItem = function(items, itemDesc)
            currentRequestedItems = nil
            local sName = activeNPC and sentSer.getNPCName(activeNPC) or "NPC"
            local pName = sentSer.getPlayerData().name or "Player"
            local curCell = (self.cell and self.cell.name) or "Unknown Cell"
            addMessage("YOU", "Refused to give " .. (itemDesc or "items") .. " to " .. sName .. ".")
            pcall(function()
                if logActionEvent then
                    logActionEvent(pName .. " refused to give " .. (itemDesc or "items") .. " to " .. sName .. " in " .. curCell .. ".")
                end
            end)
            rebuildWindow()
            _G.__smw_sendAI("The player refused to give you " .. (itemDesc or "items") .. ".", false)
        end,
        onDescribe = function()
            _G.__smw_describe()
        end,
        onListen = function()
            _G.__smw_listen()
        end,
        onClose = function()
            _G.__smw_close()
        end
    }

    local fullLayout = sentUI.renderWindow(state, callbacks)
    if rootWindow then
        rootWindow.layout = fullLayout
        rootWindow:update()
    else
        rootWindow = ui.create(fullLayout)
    end
end

closeWindow = function()
    if rootWindow then rootWindow:destroy(); rootWindow = nil end
    activeNPC             = nil
    isInterfaceActive     = false
    isDragging            = false
    currentOfferedItems   = nil
    currentRequestedItems = nil
    isThinking            = false
    isListening           = false
    listeningNPCs         = {}
    chatMessages          = {}
    pendingCallback       = nil
    inputText             = ""
    -- Stamp close time so inventory tracker's grace window covers async
    -- item transfers (LivingMW_GiveItem global event) that fire after close.
    pcall(function() lastInterfaceCloseTime = core.getRealTime() end)
    pcall(function() UI.setMode(nil) end)
    Controls.overrideMovementControls(false)
    Controls.overrideCombatControls(false)
    Controls.overrideUiControls(false)
end

_G.__smw_close = closeWindow

local thinkingStartTime = nil

local function sendIPCRequest(payload, callback, reqId)
    currentReqId      = reqId
    pendingCallback   = callback
    thinkingStartTime = os.time()

    sentIPC.sendRequest(payload, reqId, currentReqId, pendingCallback, function(data, err)
        if pendingCallback then
            local cb = pendingCallback
            pendingCallback = nil
            currentReqId   = ""
            cb(data, err)
        end
    end)
end

-- Insert message, keep last 30, auto-scroll to show newest at bottom
addMessage = function(sender, text)
    table.insert(chatMessages, { sender = sender, text = text })
    while #chatMessages > 30 do table.remove(chatMessages, 1) end
    scrollToBottom()
end


logActionEvent = function(evtText)
    if not evtText or evtText == "" then return end
    local worldId = sentSer.getGameWorldID()
    local pData   = sentSer.getPlayerDataFull()
    local evtPayload = string.format(
        '{"command":"record_event","event":"%s","world_id":"%s","player_data":%s}',
        sentIPC.escapeJSON(evtText), sentIPC.escapeJSON(worldId),
        sentIPC.toJSON(pData)
    )
    reqCounter = reqCounter + 1
    local evtReqId = "evt_" .. tostring(os.time()) .. "_" .. tostring(reqCounter)
    sentIPC.emit(evtPayload, evtReqId)
end

local PROTECTED_QUEST_ITEMS = {
    ["bk_a1_1_caiuspackage"] = true,
    ["bk_a1_1_directionscaiuscosades"] = true,
    ["dwemer_puzzle_box"] = true,
    ["misc_dwrv_ark_cube00"] = true,
    ["skull_llevule"] = true,
    ["bk_sharn_necromancynotes"] = true,
    ["bk_huleeyanotes"] = true,
    ["bk_mehraamunotes"] = true,
    ["bk_hassournotes"] = true,
    ["corprus weepings_unique"] = true,
    ["misc_6th_ash_statue_01"] = true,
    ["wraithguard"] = true,
    ["misc_wraithguard_no_equip"] = true,
    ["wraithguard_jury_rig"] = true,
    ["keening"] = true,
    ["sunder"] = true,
    ["moon_and_star"] = true,
    ["shadow_shield"] = true,
    ["teeth_of_the_urshilaku"] = true,
    ["madstone"] = true,
    ["robe_hortator"] = true,
    ["ring_hortator"] = true,
    ["belt_hortator"] = true,
    ["amulet_hortator"] = true,
    ["bk_processus_tax"] = true,
    ["note to hrisskar"] = true,
    ["chargen captain's door"] = true,
    ["chargen door key"] = true,
    ["key_chargen_doors"] = true,
    ["key_chargen_cabinet"] = true,
    ["chargendoorjournal"] = true,
    ["artifact_azura_star"] = true,
    ["artifact_bittercup"] = true,
    ["claymore_chrysamere"] = true,
    ["katana_goldbrand_unique"] = true,
    ["volendrung"] = true,
    ["longsword_umbra_unique"] = true,
    ["boots_apostle_unique"] = true,
    ["boots_blind_unique"] = true,
    ["boots_speed_unique"] = true,
    ["cuirass_savior_unique"] = true,
    ["ebon_plate_cuirass_unique"] = true,
    ["cuirass_dragonbone_unique"] = true,
    ["helm_oreyn_bearclaw_unique"] = true,
    ["helm_clavicusvile"] = true,
    ["shield_auriel"] = true,
    ["shield_eleidon_unique"] = true,
    ["shield_spellbreaker"] = true,
    ["staff_magnus_unique"] = true,
    ["staff_hasedoki_unique"] = true,
    ["mace_molag_bal_unique"] = true,
    ["mace_slurring_unique"] = true,
    ["dagger_fang_unique"] = true,
    ["bow_of_shadows"] = true,
    ["blade_nornal"] = true,
    ["pyroil_tar"] = true,
}

local function filterProtectedItems(itemList)
    if not itemList then return nil end
    local safe = {}
    for _, it in ipairs(itemList) do
        local recId = (it.id or ""):lower():match("^%s*(.-)%s*$")
        local isProtected = PROTECTED_QUEST_ITEMS[recId]
            or recId:sub(1, 6) == "bk_a1_" or recId:sub(1, 6) == "bk_a2_"
            or recId:sub(1, 6) == "index_" or recId:sub(1, 11) == "key_chargen"
        if not isProtected then
            table.insert(safe, it)
        else
            print(string.format("[LIVINGMW_UI SECURITY] Filtered protected quest item/artifact: '%s'", recId))
        end
    end
    if #safe > 0 then return safe end
    return nil
end

sendAIRequest = function(promptText, isSystemMsg)
    if not promptText or promptText == "" then return end
    if not isSystemMsg then
        addMessage("YOU", promptText)
    end
    isThinking = true
    rebuildWindow()

    local ok, err = pcall(function()
        local targetNPC = nil
        if lastRequestType ~= "describe" then
            targetNPC = activeNPC or (sentSer.performEyeRaycast and sentSer.performEyeRaycast()) or (sentSer.getRaycastNPC and sentSer.getRaycastNPC())
        end

        local targetData = targetNPC and sentSer.serializeNPC(targetNPC) or {}
        local worldId, parentId = sentSer.getGameWorldID()
        local pDataFull  = sentSer.getPlayerDataFull()
        local nearbyData = sentSer.getNearbyEntities()
        local promptNearby = nearbyData or {}
        local parentClause = (parentId and parentId ~= "") and string.format(',"parent_world_id":"%s"', sentIPC.escapeJSON(parentId)) or ""

        local npcName = (targetNPC and targetNPC.recordId) or "Narrator"
        local npcId   = (targetNPC and targetNPC.recordId) or "Narrator"
        pcall(function()
            if targetNPC and targetNPC.type and targetNPC.type.record then
                local r = targetNPC.type.record(targetNPC)
                if r and r.name then npcName = r.name end
            end
        end)

        reqCounter = reqCounter + 1
        local reqId = tostring(os.time()) .. "_" .. tostring(reqCounter)

        local payload = string.format(
            '{"command":"dialogue","prompt":"%s","npc":"%s","npc_id":"%s","world_id":"%s"%s,"entity_type":"NPC","intelligence":"50","system_prompt":"","request_id":"%s","player_data":%s,"target_data":%s,"nearby_entities":%s}',
            sentIPC.escapeJSON(promptText), sentIPC.escapeJSON(npcName), sentIPC.escapeJSON(npcId),
            sentIPC.escapeJSON(worldId), parentClause, reqId,
            sentIPC.toJSON(pDataFull), sentIPC.toJSON(targetData or {}), sentIPC.toJSON(promptNearby)
        )

        sendIPCRequest(payload, function(raw, err)
            isThinking = false
            if raw then
                local reply = sentIPC.extractReply(raw) or raw
                currentOfferedItems = filterProtectedItems(sentIPC.extractOfferedItems(raw))
                currentRequestedItems = filterProtectedItems(sentIPC.extractRequestedItems(raw))
                local sender = (lastRequestType == "listen_to_conversation") and "OVERHEARD" or (lastRequestType == "describe" and "SCENE" or npcName)
                addMessage(sender, reply)
            else
                addMessage("SYSTEM", "Error: " .. tostring(err))
            end
            rebuildWindow()
        end, reqId)
    end)

    if not ok then
        isThinking = false
        addMessage("SYSTEM", "Error initiating request: " .. tostring(err))
        rebuildWindow()
    end
end
_G.__smw_sendAI = sendAIRequest

_G.__smw_describe = function()
    lastRequestType = "describe"
    addMessage("SYSTEM", "Describing current scene...")
    sendAIRequest("Describe what you observe in the immediate vicinity.", true)
end

_G.__smw_listen = function()
    lastRequestType = "listen_to_conversation"

    local candidates = {}
    for _, actor in ipairs(nearby.actors) do
        -- Exclude self AND any Player-type actors (no eavesdropping on yourself)
        local isPlayer = pcall(function()
            if types.Player.objectIsInstance(actor) then error("player") end
        end)
        if actor ~= self and isPlayer and actor.recordId ~= "player" then
            local ok, hp = pcall(function() return types.Actor.stats.dynamic.health(actor).current end)
            if ok and hp and hp > 0 and (actor.position - self.position):length() <= 2000 then
                table.insert(candidates, actor)
            end
        end
    end

    if not isListening then
        if #candidates < 1 then
            addMessage("SYSTEM", "Listen failed: no living characters nearby.")
            rebuildWindow()
            return
        end
        for i = #candidates, 2, -1 do
            local j = math.random(i)
            candidates[i], candidates[j] = candidates[j], candidates[i]
        end
        listeningNPCs = { candidates[1] }
        for i = 2, #candidates do
            if #listeningNPCs >= 3 then break end
            if (candidates[i].position - candidates[1].position):length() <= 500 then
                table.insert(listeningNPCs, candidates[i])
            end
        end
        local names = {}
        for _, a in ipairs(listeningNPCs) do table.insert(names, sentSer.getNPCName(a)) end
        local msg = #names == 1 and ("Observing " .. names[1] .. "...") or ("Listening to: " .. table.concat(names, ", ") .. "...")
        addMessage("SYSTEM", msg)
    else
        local alive = 0
        for _, a in ipairs(listeningNPCs) do
            local ok, hp = pcall(function() return types.Actor.stats.dynamic.health(a).current end)
            if ok and hp and hp > 0 then alive = alive + 1 end
        end
        if alive < 1 then
            addMessage("SYSTEM", "Subjects are no longer alive.")
            isListening = false; listeningNPCs = {}; rebuildWindow(); return
        end
        addMessage("SYSTEM", "Continuing to listen...")
    end

    local parts = {}
    local pData = sentSer.getPlayerData()
    for i = 1, math.min(#listeningNPCs, 3) do
        local d = sentSer.serializeNPC(listeningNPCs[i])
        if d then
            table.insert(parts, string.format(
                '{"id":"%s","name":"%s","type":"NPC","race":"%s","gender":"%s","class":"%s","level":%d}',
                sentIPC.escapeJSON(d.id), sentIPC.escapeJSON(d.name), sentIPC.escapeJSON(d.race), d.gender, sentIPC.escapeJSON(d.class), d.level
            ))
        end
    end

    local worldId = sentSer.getGameWorldID()

    reqCounter = reqCounter + 1
    local reqId = tostring(os.time()) .. "_" .. tostring(reqCounter)

    local lisPayload = string.format(
        '{"command":"listen_to_conversation","world_id":"%s","is_continue":"%s","participants":[%s],"request_id":"%s"}',
        sentIPC.escapeJSON(worldId), isListening and "true" or "false", table.concat(parts, ","), reqId
    )

    isListening = true
    isThinking  = true
    rebuildWindow()

    sendIPCRequest(lisPayload, function(raw, err)
        isThinking = false
        if raw then
            local reply = sentIPC.extractReply(raw) or raw
            local sender = (lastRequestType == "listen_to_conversation") and "OVERHEARD" or (lastRequestType == "describe" and "SCENE" or "AI")
            addMessage(sender, reply)
        else
            errorMessage = "FAILED TO RECEIVE AI RESPONSE:\n" .. tostring(err)
            addMessage("SYSTEM", "Error: " .. tostring(err))
        end
        rebuildWindow()
    end, reqId)
end

local trackerTimer             = 0
local lastCellName             = nil
local lastEquippedMap          = {}
local lastInvMap               = {}
local lastLivingActors         = {}
local lastMagicka              = nil
local lastActorMagicka         = {}
local lastUIMode               = nil
local lastLootSource           = nil
local isLootSourceCorpse       = false
local lastContainerTime         = 0
local lastContainerName         = nil
local lastBarterTime           = 0
local lastBarterMerchant        = nil
local lastDialogueTime          = 0
local containerLoggedForSession = false
local barterLoggedForSession    = false
local dialogueLoggedForSession  = false
local lastJournalCount         = nil
local lastTopicEntriesCount     = nil
local lastActiveSpells         = {}
local lastActorActiveSpells    = {}
local lastKnownPassives        = {}
local _dlgInfoDumpDone         = false  -- one-shot debug flag: dump info field names once (reset if broken dump was consumed)

local pendingDialogueNPC     = nil
local pendingDialogueTime    = 0
local lastDialogueText       = nil
local lastDialogueActor      = nil
local recentDialogueTexts    = {}

local function isDuplicateDialogue(text)
    if not text or text == "" then return true end
    local now = core.getRealTime()
    for t, timestamp in pairs(recentDialogueTexts) do
        if now - timestamp > 15 then
            recentDialogueTexts[t] = nil
        end
    end
    if recentDialogueTexts[text] then
        return true
    end
    recentDialogueTexts[text] = now
    return false
end

local function getDialogueRecord(dType, recordId)
    if not core.dialogue or not dType or not core.dialogue[dType] or not core.dialogue[dType].records then
        return nil
    end
    local recs = core.dialogue[dType].records
    if recs[recordId] then return recs[recordId] end
    if type(recordId) == "string" then
        local lower = recordId:lower()
        if recs[lower] then return recs[lower] end
        for k, v in pairs(recs) do
            if tostring(k):lower() == lower then
                return v
            end
        end
    end
    return nil
end


local function detectChoiceCondition(info)
    if not info then return nil end
    -- Conditions may not be accessible in all OpenMW builds.
    -- Try every known field name for conditions list.
    local condList = info.conditions or info.filters or info.selects
    if not condList then return nil end
    local choiceNum = nil
    for _, c in pairs(condList) do
        pcall(function()
            local isChoiceCond = false
            -- OpenMW may name the "function" field differently since
            -- "function" is a Lua keyword. Try bracket and alias forms.
            local candidates = {
                c.type, c["function"], c.fn, c.func, c.functionName,
                c.functionId, c.conditionType, c.selectVar, c.mSelectVar,
                c.variable, c.name, c.argument, c.id, c.functionType,
            }
            for _, f in ipairs(candidates) do
                if f ~= nil then
                    local s = tostring(f):lower()
                    -- "choice" string OR mwscript function number 46
                    if s:find("choice") or s == "46" or s == "46.0" then
                        isChoiceCond = true
                        break
                    end
                end
            end
            if isChoiceCond then
                local val = c.value or c.val or c.comparisonValue
                            or c.compareValue or c.argument or c.mI or c.mF
                if val ~= nil then
                    choiceNum = tonumber(val)
                end
            end
        end)
        if choiceNum then break end
    end
    return choiceNum
end

-- Look up the visible button text for a given choice number.
-- In vanilla Morrowind, choice dialogue labels live in the "choice"
-- dialogue type as separate infos whose conditions require Choice==N.
local function lookupChoiceText(choiceIndex)
    if not choiceIndex then return nil end
    local label = nil
    pcall(function()
        -- The dialogue type is literally "choice" (lower-case key in OpenMW)
        local choiceDialogue = core.dialogue and (
            core.dialogue["choice"] or core.dialogue["Choice"]
        )
        if not choiceDialogue then return end
        local recs = choiceDialogue.records
        if not recs then return end
        for _, rec in pairs(recs) do
            if rec.infos then
                for _, info in pairs(rec.infos) do
                    local cn = detectChoiceCondition(info)
                    if cn and tonumber(cn) == tonumber(choiceIndex) then
                        local t = info.text or rec.id or ""
                        t = t:match("^%s*(.-)%s*$")
                        if #t > 0 and #t < 80 then
                            label = t
                            return
                        end
                    end
                end
            end
            if label then break end
        end
    end)
    return label
end

local function handleDialogueResponse(e)
    if not e then return end
    -- The Chat topic only opens the input bar; it is not a real conversation line.
    if sentChat.onDialogueResponse(e) then return end
    local pData = sentSer.getPlayerData()
    local pName = pData.name or "Player"
    local curCell = (self.cell and self.cell.name) or "Unknown Cell"
    local actor = e.actor or activeNPC
    local actorName = (actor and sentSer.getNPCName(actor)) or (activeNPC and sentSer.getNPCName(activeNPC)) or "an NPC"
    if not actorName or actorName == "" or actorName == "Unknown" then
        actorName = (actor and sentSer.getObjectName(actor)) or (actor and actor.recordId) or "an NPC"
    end

    local text = e.text
    local topicName = nil
    local choiceNum = nil

    pcall(function()
        local rec = getDialogueRecord(e.type, e.recordId)
        if rec then
            topicName = rec.id or rec.name
            if rec.infos then
                for _, info in pairs(rec.infos) do
                    if info.id == e.infoId or tostring(info.id) == tostring(e.infoId) then
                        if not text or text == "" then
                            text = info.text
                        end
                        -- ONE-SHOT DEBUG DUMP: probe each field by name (pairs() fails on userdata)
                        if not _dlgInfoDumpDone and e.type == "topic" then
                            _dlgInfoDumpDone = true
                            local function sf(v)
                                local ok, s = pcall(tostring, v)
                                return ok and s or "<err>"
                            end
                            local function probe(obj, fname)
                                local ok, val = pcall(function() return obj[fname] end)
                                if ok then
                                    print("[SMW_DLG_DEBUG]   info." .. fname .. " = " .. sf(val) .. " (type=" .. type(val) .. ")")
                                    return val
                                else
                                    print("[SMW_DLG_DEBUG]   info." .. fname .. " = <access threw>")
                                    return nil
                                end
                            end
                            print("[SMW_DLG_DEBUG] info probe for infoId=" .. sf(e.infoId))
                            -- Standard known fields
                            for _, fn in ipairs({"id","text","type","actor","race","class","cell",
                                                  "faction","rank","gender","npcRank","pcRank",
                                                  "conditions","filters","selects","filterConditions",
                                                  "infoConditions","selectStructs","selectors",
                                                  "questName","questFinished","questRestart",
                                                  "disposition","pcFaction","soundPath","resultScript"}) do
                                local val = probe(info, fn)
                                -- If it's a sequence-like thing, peek at first element
                                if val ~= nil and type(val) ~= "string" and type(val) ~= "number" and type(val) ~= "boolean" then
                                    pcall(function()
                                        for ci, cv in pairs(val) do
                                            print("[SMW_DLG_DEBUG]     [" .. sf(ci) .. "] = " .. sf(cv) .. " (type=" .. type(cv) .. ")")
                                            if type(cv) == "userdata" or type(cv) == "table" then
                                                pcall(function()
                                                    for ff, fv in pairs(cv) do
                                                        print("[SMW_DLG_DEBUG]       ." .. sf(ff) .. "=" .. sf(fv))
                                                    end
                                                end)
                                            end
                                            break  -- only first entry
                                        end
                                    end)
                                end
                            end
                        end
                        choiceNum = detectChoiceCondition(info)
                        break
                    end
                end
            end
        end
    end)

    if not text or text == "" then
        if e.type == "topic" and e.recordId then
            topicName = tostring(e.recordId)
        end
        return
    end

    text = text:gsub("[\r\n]+", " "):match("^%s*(.-)%s*$")
    if #text == 0 or isDuplicateDialogue(text) then
        return
    end

    local choiceMade = nil
    if choiceNum then
        local optText = lookupChoiceText(choiceNum)
        if optText then
            choiceMade = "'" .. optText .. "'"
        else
            choiceMade = "option " .. tostring(choiceNum)
        end
    end

    local actionText = nil
    local promptText = nil

    if pendingDialogueNPC then
        local n = pendingDialogueNPC
        actionText = pName .. " entered dialogue with " .. n .. " in " .. curCell .. ", who said: \"" .. text .. "\""
        promptText = "Greeting"
        pendingDialogueNPC = nil
    elseif choiceMade then
        actionText = pName .. " said " .. choiceMade .. " to " .. actorName .. " in " .. curCell .. ", who replied: \"" .. text .. "\""
        promptText = choiceMade
    elseif e.type == "topic" then
        local tDesc = topicName or tostring(e.recordId or "a topic")
        actionText = pName .. " asked " .. actorName .. " about '" .. tDesc .. "' in " .. curCell .. ", who replied: \"" .. text .. "\""
        promptText = tDesc
    elseif e.type == "persuasion" then
        local pType = tostring(e.recordId or "persuasion"):gsub("_", " ")
        actionText = pName .. " used " .. pType .. " on " .. actorName .. " in " .. curCell .. ", who responded: \"" .. text .. "\""
        promptText = pType
    elseif e.type == "voice" then
        actionText = actorName .. " voiced in " .. curCell .. ": \"" .. text .. "\""
        promptText = "Voice"
    elseif e.type == "greeting" then
        actionText = actorName .. " said to " .. pName .. " in " .. curCell .. ": \"" .. text .. "\""
        promptText = "Greeting"
    else
        actionText = actorName .. " said to " .. pName .. " in " .. curCell .. ": \"" .. text .. "\""
        promptText = "Dialogue"
    end

    lastDialogueText = text
    lastDialogueActor = actorName
    lastDialogueTime = core.getRealTime()

    if actionText then
        logActionEvent(actionText)
        local worldId = sentSer.getGameWorldID()
        local npcId = (actor and actor.recordId) or actorName:lower()
        local dlgPayload = string.format(
            '{"command":"record_dialogue","world_id":"%s","npc":"%s","npc_id":"%s","prompt":"%s","reply":"%s"}',
            sentIPC.escapeJSON(worldId), sentIPC.escapeJSON(actorName),
            sentIPC.escapeJSON(npcId), sentIPC.escapeJSON(promptText or "Dialogue"),
            sentIPC.escapeJSON(text)
        )
        reqCounter = reqCounter + 1
        local dlgReqId = "dlg_" .. tostring(os.time()) .. "_" .. tostring(reqCounter)
        sentIPC.emit(dlgPayload, dlgReqId)
    end
end

local function formatSpellInfo(spell)
    if not spell then return nil, "Self", "" end
    local name = spell.name or spell.id or "Spell"
    local rangeStr = nil
    local effDescriptions = {}
    pcall(function()
        if spell.effects then
            for _, eff in ipairs(spell.effects) do
                local r = eff.range
                if not rangeStr and r ~= nil then
                    if r == 0 then
                        rangeStr = "Self"
                    elseif r == 1 then
                        rangeStr = "Touch"
                    elseif r == 2 then
                        rangeStr = "Target"
                    end
                end
                local effName = (eff.effect and eff.effect.name) or eff.id or "Magic"
                local mag = ""
                local minM = eff.magnitudeMin or 0
                local maxM = eff.magnitudeMax or 0
                if minM > 0 or maxM > 0 then
                    if minM == maxM then
                        mag = " " .. tostring(minM) .. " pts"
                    else
                        mag = " " .. tostring(minM) .. "-" .. tostring(maxM) .. " pts"
                    end
                end
                local dur = (eff.duration and eff.duration > 0) and (" for " .. tostring(eff.duration) .. "s") or ""
                local area = (eff.area and eff.area > 0) and (" in " .. tostring(eff.area) .. "ft") or ""
                table.insert(effDescriptions, effName .. mag .. dur .. area)
            end
        end
    end)
    rangeStr = rangeStr or "Self"
    local cost = spell.cost or 0
    if cost > 0 then
        table.insert(effDescriptions, "cost " .. tostring(cost) .. " magicka")
    end
    local details = #effDescriptions > 0 and (" (" .. table.concat(effDescriptions, ", ") .. ")") or ""
    return name, rangeStr, details
end

local function isSpellPower(spell)
    if not spell then return false end
    local isPower = false
    pcall(function()
        if core.magic and core.magic.SPELL_TYPE and spell.type == core.magic.SPELL_TYPE.Power then
            isPower = true
        end
    end)
    if not isPower and (spell.type == 5 or spell.type == "Power" or spell.type == "power") then
        isPower = true
    end
    return isPower
end

local function isSpellAbility(spell)
    if not spell then return false end
    local isAbil = false
    pcall(function()
        if core.magic and core.magic.SPELL_TYPE and spell.type == core.magic.SPELL_TYPE.Ability then
            isAbil = true
        end
    end)
    if not isAbil and (spell.type == 1 or spell.type == "Ability" or spell.type == "ability") then
        isAbil = true
    end
    return isAbil
end

local function getSpellRecord(spellOrId)
    if not spellOrId then return nil end
    if type(spellOrId) == "table" and (spellOrId.effects or spellOrId.type) then
        return spellOrId
    end
    local rec = nil
    pcall(function()
        if types.Spell and types.Spell.record then
            rec = types.Spell.record(spellOrId)
        end
    end)
    if not rec then
        pcall(function()
            if core.magic and core.magic.spells and core.magic.spells.records then
                rec = core.magic.spells.records[spellOrId]
            end
        end)
    end
    return rec
end

local function formatContainerName(obj)
    if not obj then return "a container" end
    local name = nil
    pcall(function()
        if obj.type == types.Container and types.Container.record then
            local r = types.Container.record(obj)
            if r and r.name and r.name ~= "" then
                name = r.name
            end
        elseif (obj.type == types.NPC or obj.type == types.Creature) and obj.type.record then
            local r = obj.type.record(obj)
            if r and r.name and r.name ~= "" then
                name = r.name .. "'s corpse"
            end
        end
    end)
    if not name or name == "" then
        local rawId = (obj.recordId or ""):lower()
        if rawId:find("barrel") then name = "barrel"
        elseif rawId:find("chest") then name = "chest"
        elseif rawId:find("crate") then name = "crate"
        elseif rawId:find("sack") then name = "sack"
        elseif rawId:find("urn") then name = "urn"
        elseif rawId:find("basket") then name = "basket"
        elseif rawId:find("treestump") or rawId:find("stump") then name = "hollow tree stump"
        elseif rawId:find("corpse") or rawId:find("dead") then name = "corpse"
        elseif obj.type == types.NPC or obj.type == types.Creature then
            local nName = sentSer.getNPCName(obj)
            if nName and nName ~= "" and nName ~= "Unknown" and nName ~= "Narrator" then
                name = nName .. "'s corpse"
            else
                name = "corpse"
            end
        elseif rawId ~= "" then
            name = rawId:gsub("^contain_", ""):gsub("^chargen_", ""):gsub("^flora_", ""):gsub("_", " ")
        else
            name = "container"
        end
    end
    local lower = name:lower()
    if lower:find("^a ") or lower:find("^an ") or lower:find("^the ") or lower:find("'s") then
        return name
    end
    local firstLetter = lower:sub(1, 1)
    if firstLetter == "a" or firstLetter == "e" or firstLetter == "i" or firstLetter == "o" or firstLetter == "u" then
        return "an " .. name
    else
        return "a " .. name
    end
end

local function findActiveContainerOrCorpse()
    local rayObj = sentSer.getRaycastObject and sentSer.getRaycastObject()
    if rayObj and rayObj.position and (rayObj.position - self.position):length() <= 350 then
        if rayObj.type == types.Container then
            return rayObj
        elseif (rayObj.type == types.NPC or rayObj.type == types.Creature) then
            local isDead = false
            pcall(function()
                if types.Actor.stats and types.Actor.stats.dynamic and types.Actor.stats.dynamic.health then
                    if types.Actor.stats.dynamic.health(rayObj).current <= 0 then isDead = true end
                end
            end)
            if isDead then return rayObj end
        end
    end

    local bestObj = nil
    local bestDist = 350

    -- 1. Check nearby dead actors (corpses)
    if nearby.actors then
        for _, act in ipairs(nearby.actors) do
            if act ~= self then
                local isDead = false
                pcall(function()
                    if types.Actor.stats and types.Actor.stats.dynamic and types.Actor.stats.dynamic.health then
                        if types.Actor.stats.dynamic.health(act).current <= 0 then isDead = true end
                    end
                end)
                if isDead then
                    local d = (act.position - self.position):length()
                    if d < bestDist then
                        bestDist = d
                        bestObj = act
                    end
                end
            end
        end
    end

    -- 2. Check nearby containers
    if not bestObj and nearby.containers then
        for _, cont in ipairs(nearby.containers) do
            local d = (cont.position - self.position):length()
            if d < bestDist then
                bestDist = d
                bestObj = cont
            end
        end
    end

    return bestObj
end

local function findActiveMerchant()
    if activeNPC then return activeNPC end
    local ray = sentSer.performEyeRaycast and sentSer.performEyeRaycast()
    if ray and (ray.type == types.NPC or ray.type == types.Creature) then return ray end
    local best = nil
    local bestDist = 450
    if nearby.actors then
        for _, act in ipairs(nearby.actors) do
            if act ~= self and (act.type == types.NPC or act.type == types.Creature) then
                local isAlive = true
                pcall(function()
                    if types.Actor.stats.dynamic.health(act).current <= 0 then isAlive = false end
                end)
                if isAlive then
                    local d = (act.position - self.position):length()
                    if d < bestDist then
                        bestDist = d
                        best = act
                    end
                end
            end
        end
    end
    return best
end

local function handleUiModeChanged(data)
    local newMode = data and data.newMode
    local oldMode = data and data.oldMode
    local targetObj = data and data.arg

    local pData = sentSer.getPlayerData()
    local pName = pData.name or "Player"
    local curCell = (self.cell and self.cell.name) or "Unknown Cell"
    local now = core.getRealTime()

    if newMode == "Container" then
        if not targetObj then
            targetObj = findActiveContainerOrCorpse()
        end
        local cName = formatContainerName(targetObj)
        lastLootSource = cName
        lastContainerName = cName
        lastContainerTime = now
        containerLoggedForSession = true
        local isCorpse = (targetObj and (targetObj.type == types.NPC or targetObj.type == types.Creature))
            or (cName:lower():find("corpse") ~= nil)
            or (cName:lower():find("dead") ~= nil)
        isLootSourceCorpse = isCorpse
        local verb = isCorpse and "searched " or "opened/searched "
        logActionEvent(pName .. " " .. verb .. cName .. " in " .. curCell .. ".")
    elseif newMode == "Barter" then
        if not targetObj then
            targetObj = findActiveMerchant()
        end
        local mName = targetObj and (sentSer.getNPCName(targetObj) or sentSer.getObjectName(targetObj)) or (activeNPC and sentSer.getNPCName(activeNPC)) or "a merchant"
        lastBarterMerchant = mName
        lastBarterTime = now
        barterLoggedForSession = true
        logActionEvent(pName .. " opened barter/trade window with " .. mName .. " in " .. curCell .. ".")
    elseif newMode == "Dialogue" then
        local nName = targetObj and (sentSer.getNPCName(targetObj) or sentSer.getObjectName(targetObj)) or (activeNPC and sentSer.getNPCName(activeNPC)) or "an NPC"
        dialogueLoggedForSession = true
        pendingDialogueNPC = nName
        pendingDialogueTime = now
    end

    if oldMode == "Container" then
        lastContainerTime = now
        containerLoggedForSession = false
    elseif oldMode == "Barter" then
        lastBarterTime = now
        barterLoggedForSession = false
    elseif oldMode == "Dialogue" then
        lastDialogueTime = now
        dialogueLoggedForSession = false
        pendingDialogueNPC = nil
    end
end

local function checkActionEvents(dt)
    trackerTimer = trackerTimer + (dt or 0.05)
    if trackerTimer < 0.1 then return end
    trackerTimer = 0

    local pData = sentSer.getPlayerData()
    local pName = pData.name or "Player"
    local now = core.getRealTime()

    local curUIMode = nil
    pcall(function()
        if UI.getMode then curUIMode = UI.getMode() end
    end)

    if curUIMode == "Container" then
        lastContainerTime = now
        if not lastLootSource or lastLootSource == "a container" then
            local found = findActiveContainerOrCorpse()
            if found then
                lastLootSource = formatContainerName(found)
                lastContainerName = lastLootSource
                isLootSourceCorpse = (found.type == types.NPC or found.type == types.Creature)
                    or (lastLootSource:lower():find("corpse") ~= nil)
                    or (lastLootSource:lower():find("dead") ~= nil)
            end
        end
    elseif curUIMode == "Barter" then
        lastBarterTime = now
        if not lastBarterMerchant then
            local fMerchant = findActiveMerchant()
            lastBarterMerchant = fMerchant and (sentSer.getNPCName(fMerchant) or sentSer.getObjectName(fMerchant)) or (activeNPC and sentSer.getNPCName(activeNPC)) or "a merchant"
        end
    end

    -- 1. Cell / Location Transition Tracking
    pcall(function() sentSer.noteExterior() end)
    local currentCell = "Unknown Cell"
    pcall(function()
        if self.cell then
            currentCell = self.cell.name
            if not currentCell or currentCell == "" then
                currentCell = string.format("Cell (%d, %d)", self.cell.gridX or 0, self.cell.gridY or 0)
            end
        end
    end)
    if lastCellName == nil then
        lastCellName = currentCell
    elseif lastCellName ~= currentCell then
        logActionEvent(pName .. " traveled from " .. lastCellName .. " to " .. currentCell .. ".")
        lastCellName = currentCell
    end

    -- 2. Equipped Gear Tracking (Handles Single Equips, Unequips, and Slot Swaps)
    local curEq = sentSer.getPlayerEquipment()
    local curEqMap = {}
    for _, item in ipairs(curEq) do
        if item.id then curEqMap[item.id] = item.name or item.id end
    end
    if next(lastEquippedMap) ~= nil then
        local equippedList = {}
        local unequippedList = {}
        for id, name in pairs(curEqMap) do
            if not lastEquippedMap[id] then
                table.insert(equippedList, name)
            end
        end
        for id, name in pairs(lastEquippedMap) do
            if not curEqMap[id] then
                table.insert(unequippedList, name)
            end
        end
        if #equippedList > 0 and #unequippedList > 0 then
            logActionEvent(pName .. " equipped " .. table.concat(equippedList, ", ") .. " (replacing " .. table.concat(unequippedList, ", ") .. ").")
        elseif #equippedList > 0 then
            logActionEvent(pName .. " equipped " .. table.concat(equippedList, ", ") .. ".")
        elseif #unequippedList > 0 then
            logActionEvent(pName .. " unequipped " .. table.concat(unequippedList, ", ") .. ".")
        end
    end
    lastEquippedMap = curEqMap

    -- 3. Batched Inventory Item Tracking (Picking up, Dropping, Looting Containers/Corpses/Plants, Barter)
    local curInv = sentSer.getAllInventoryItems()
    local curInvMap = {}
    for _, item in ipairs(curInv) do
        local itemId = (item.id or ""):lower()
        if itemId ~= "" then
            if not curInvMap[itemId] then
                curInvMap[itemId] = { name = item.name or item.id, count = item.count or 1 }
            else
                curInvMap[itemId].count = curInvMap[itemId].count + (item.count or 1)
            end
        end
    end
    if next(lastInvMap) ~= nil then
        local isContainerActive = (curUIMode == "Container") or (lastContainerTime and (now - lastContainerTime <= 2.5))
        local isBarterActive    = (curUIMode == "Barter") or (lastBarterTime and (now - lastBarterTime <= 2.5))
        local isDialogueActive  = (curUIMode == "Dialogue") or isInterfaceActive
                                   or (lastDialogueTime      and (now - lastDialogueTime      <= 2.5))
                                   or (lastInterfaceCloseTime > 0 and (now - lastInterfaceCloseTime <= 3.0))
        local acquiredList = {}
        local droppedList  = {}
        local goldGained   = 0
        local goldLost     = 0

        for id, data in pairs(curInvMap) do
            local oldData = lastInvMap[id]
            local oldCnt = oldData and oldData.count or 0
            if data.count > oldCnt then
                local diff = data.count - oldCnt
                if id == "gold_001" or id:find("^gold_") then
                    goldGained = goldGained + diff
                else
                    table.insert(acquiredList, data.name .. (diff > 1 and (" (x" .. tostring(diff) .. ")") or ""))
                end
            end
        end
        for id, oldData in pairs(lastInvMap) do
            local data = curInvMap[id]
            local newCnt = data and data.count or 0
            if oldData.count and oldData.count > newCnt then
                local diff = oldData.count - newCnt
                if id == "gold_001" or id:find("^gold_") then
                    goldLost = goldLost + diff
                else
                    table.insert(droppedList, oldData.name .. (diff > 1 and (" (x" .. tostring(diff) .. ")") or ""))
                end
            end
        end

        if isBarterActive then
            local merchantName = lastBarterMerchant or (activeNPC and sentSer.getNPCName(activeNPC)) or "the merchant"
            local goodsAcquired = {}
            local goodsSold = {}
            for _, it in ipairs(acquiredList) do
                if not it:find("Gold$") then table.insert(goodsAcquired, it) end
            end
            for _, it in ipairs(droppedList) do
                if not it:find("Gold$") then table.insert(goodsSold, it) end
            end

            if #goodsAcquired > 0 and #goodsSold > 0 then
                local costPart = ""
                if goldLost > 0 then costPart = " paying " .. tostring(goldLost) .. " Gold" end
                if goldGained > 0 then costPart = " receiving " .. tostring(goldGained) .. " Gold" end
                logActionEvent(pName .. " traded with " .. merchantName .. ": bought " .. table.concat(goodsAcquired, ", ") .. " and sold " .. table.concat(goodsSold, ", ") .. costPart .. " in " .. currentCell .. ".")
            elseif #goodsAcquired > 0 then
                local priceClause = (goldLost > 0) and (" for " .. tostring(goldLost) .. " Gold") or ""
                logActionEvent(pName .. " bought " .. table.concat(goodsAcquired, ", ") .. " from " .. merchantName .. priceClause .. " in " .. currentCell .. ".")
            elseif #goodsSold > 0 then
                local priceClause = (goldGained > 0) and (" for " .. tostring(goldGained) .. " Gold") or ""
                logActionEvent(pName .. " sold " .. table.concat(goodsSold, ", ") .. " to " .. merchantName .. priceClause .. " in " .. currentCell .. ".")
            elseif goldGained > 0 then
                logActionEvent(pName .. " received " .. tostring(goldGained) .. " Gold from " .. merchantName .. " in " .. currentCell .. ".")
            elseif goldLost > 0 then
                logActionEvent(pName .. " paid " .. tostring(goldLost) .. " Gold to " .. merchantName .. " in " .. currentCell .. ".")
            end
            lastBarterTime = 0
        elseif isContainerActive then
            local contName = lastLootSource or lastContainerName or "a container"
            local isCorpse = isLootSourceCorpse
                or (contName:lower():find("corpse") ~= nil)
                or (contName:lower():find("dead") ~= nil)
                or (contName:lower():find("body") ~= nil)
                or (contName:lower():find("skeleton") ~= nil)

            local containerAcquired = {}
            for _, it in ipairs(acquiredList) do table.insert(containerAcquired, it) end
            if goldGained > 0 then
                table.insert(containerAcquired, tostring(goldGained) .. " Gold")
            end

            local containerStored = {}
            for _, it in ipairs(droppedList) do table.insert(containerStored, it) end
            if goldLost > 0 then
                table.insert(containerStored, tostring(goldLost) .. " Gold")
            end

            if #containerAcquired > 0 then
                logActionEvent(pName .. " looted " .. table.concat(containerAcquired, ", ") .. " from " .. contName .. " in " .. currentCell .. ".")
            end
            if #containerStored > 0 then
                local v = isCorpse and "placed " or "stored "
                local p = isCorpse and " on " or " inside "
                logActionEvent(pName .. " " .. v .. table.concat(containerStored, ", ") .. p .. contName .. " in " .. currentCell .. ".")
            end
            if curUIMode ~= "Container" then
                lastContainerTime = 0
            end
        elseif not isDialogueActive then
            -- Only log ground pick-ups/drops when NOT in dialogue
            -- (Dialogue scripts can silently remove/add items; don't mislabel as ground drops)
            local groundAcquired = {}
            for _, it in ipairs(acquiredList) do table.insert(groundAcquired, it) end
            if goldGained > 0 then
                table.insert(groundAcquired, tostring(goldGained) .. " Gold")
            end

            local groundDropped = {}
            for _, it in ipairs(droppedList) do table.insert(groundDropped, it) end
            if goldLost > 0 then
                table.insert(groundDropped, tostring(goldLost) .. " Gold")
            end

            if #groundAcquired > 0 then
                logActionEvent(pName .. " picked up " .. table.concat(groundAcquired, ", ") .. " from the ground in " .. currentCell .. ".")
            end
            if #groundDropped > 0 then
                logActionEvent(pName .. " dropped " .. table.concat(groundDropped, ", ") .. " on the ground in " .. currentCell .. ".")
            end
        end
    end
    lastInvMap = curInvMap

    -- 4. Magic, Powers & Ability Tracking (Player & Nearby NPCs)
    -- A. Active Spell Effects & Powers on Player (Ancestor Guardian, Adrenaline Rush, Berserk, Diseases, Curses)
    pcall(function()
        if types.Actor.activeSpells then
            local act = types.Actor.activeSpells(self)
            if act then
                local curAct = {}
                for id, params in pairs(act) do
                    local spellId = (params and params.id) or id
                    curAct[spellId] = true
                    if next(lastActiveSpells) ~= nil and not lastActiveSpells[spellId] then
                        local spRec = getSpellRecord(spellId)
                        if spRec then
                            local sName, sRange, sDetails = formatSpellInfo(spRec)
                            if isSpellPower(spRec) then
                                logActionEvent(pName .. " invoked power " .. sName .. " [" .. sRange .. "]" .. sDetails .. " in " .. currentCell .. ".")
                            elseif spRec.type == 2 or spRec.type == 3 or spRec.type == "Disease" or spRec.type == "Blight" then
                                logActionEvent(pName .. " contracted " .. sName .. sDetails .. " in " .. currentCell .. ".")
                            elseif spRec.type == 4 or spRec.type == "Curse" then
                                logActionEvent(pName .. " was afflicted by curse " .. sName .. sDetails .. " in " .. currentCell .. ".")
                            end
                        end
                    end
                end
                lastActiveSpells = curAct
            end
        end
    end)

    -- B. Newly Acquired Passive / Racial Abilities on Player
    pcall(function()
        if types.Actor.spells then
            local mySpells = types.Actor.spells(self)
            if mySpells then
                local curPassives = {}
                for _, sp in pairs(mySpells) do
                    if sp and isSpellAbility(sp) then
                        local sId = sp.id or sp.name
                        curPassives[sId] = true
                        if next(lastKnownPassives) ~= nil and not lastKnownPassives[sId] then
                            local sName, _, sDetails = formatSpellInfo(sp)
                            logActionEvent(pName .. " gained passive/racial ability " .. sName .. sDetails .. " in " .. currentCell .. ".")
                        end
                    end
                end
                lastKnownPassives = curPassives
            end
        end
    end)

    -- C. Standard Spell & Enchanted Item Casting on Player
    local curMagicka = nil
    pcall(function()
        if types.Actor.stats and types.Actor.stats.dynamic and types.Actor.stats.dynamic.magicka then
            curMagicka = math.floor(types.Actor.stats.dynamic.magicka(self).current or 0)
        end
    end)
    if curMagicka and lastMagicka and (lastMagicka - curMagicka >= 1) then
        local spell = nil
        pcall(function()
            if types.Actor.getSelectedSpell then
                spell = types.Actor.getSelectedSpell(self)
            end
        end)
        if spell then
            local sName, sRange, sDetails = formatSpellInfo(spell)
            if isSpellPower(spell) then
                logActionEvent(pName .. " invoked power " .. sName .. " [" .. sRange .. "]" .. sDetails .. " in " .. currentCell .. ".")
            else
                logActionEvent(pName .. " cast " .. sName .. " [" .. sRange .. "]" .. sDetails .. " in " .. currentCell .. ".")
            end
        else
            local enchItem = nil
            pcall(function()
                if types.Actor.getSelectedEnchantedItem then
                    enchItem = types.Actor.getSelectedEnchantedItem(self)
                end
            end)
            if enchItem then
                local eName = (enchItem.type and enchItem.type.record and enchItem.type.record(enchItem).name) or enchItem.recordId or "an enchanted item"
                logActionEvent(pName .. " cast magic from " .. tostring(eName) .. " in " .. currentCell .. ".")
            else
                logActionEvent(pName .. " cast a spell in " .. currentCell .. " (cost " .. tostring(lastMagicka - curMagicka) .. " magicka).")
            end
        end
    end
    lastMagicka = curMagicka

    local function isPlayerActor(act)
    if not act then return false end
    if act == self then return true end
    local isPlr = false
    pcall(function()
        if act.recordId == "player" then
            isPlr = true
        elseif types.Player and types.Player.objectIsInstance and types.Player.objectIsInstance(act) then
            isPlr = true
        end
    end)
    return isPlr
end

    -- D. NPC Spell & Power Casting
    if nearby.actors then
        for _, actor in ipairs(nearby.actors) do
            if not isPlayerActor(actor) then
                local aKey = tostring(actor)
                local aMag = nil
                local isAlive = false
                pcall(function()
                    local hp = types.Actor.stats.dynamic.health(actor).current or 0
                    if hp > 0 then
                        isAlive = true
                        aMag = math.floor(types.Actor.stats.dynamic.magicka(actor).current or 0)
                    end
                end)

                -- NPC Active Powers
                pcall(function()
                    if isAlive and types.Actor.activeSpells then
                        local act = types.Actor.activeSpells(actor)
                        if act then
                            local curAct = {}
                            for id, params in pairs(act) do
                                local spellId = (params and params.id) or id
                                curAct[spellId] = true
                                local oldAct = lastActorActiveSpells[aKey]
                                if oldAct and not oldAct[spellId] then
                                    local spRec = getSpellRecord(spellId)
                                    if spRec and isSpellPower(spRec) then
                                        local aName = sentSer.getNPCName(actor) or "An NPC"
                                        local sName, sRange, sDetails = formatSpellInfo(spRec)
                                        logActionEvent(aName .. " invoked power " .. sName .. " [" .. sRange .. "]" .. sDetails .. " in " .. currentCell .. ".")
                                    end
                                end
                            end
                            lastActorActiveSpells[aKey] = curAct
                        end
                    end
                end)

                -- NPC Magicka Spell Casting
                if isAlive and aMag then
                    local oldAMag = lastActorMagicka[aKey]
                    if oldAMag and (oldAMag - aMag >= 1) then
                        local aName = sentSer.getNPCName(actor)
                        if not aName or aName == "" or aName == "Unknown" then
                            aName = sentSer.getObjectName(actor) or actor.recordId or "An NPC"
                        end
                        local aSpell = nil
                        pcall(function()
                            if types.Actor.getSelectedSpell then
                                aSpell = types.Actor.getSelectedSpell(actor)
                            end
                        end)
                        if aSpell then
                            local sName, sRange, sDetails = formatSpellInfo(aSpell)
                            if isSpellPower(aSpell) then
                                logActionEvent(aName .. " invoked power " .. sName .. " [" .. sRange .. "]" .. sDetails .. " in " .. currentCell .. ".")
                            else
                                logActionEvent(aName .. " cast " .. sName .. " [" .. sRange .. "]" .. sDetails .. " in " .. currentCell .. ".")
                            end
                        else
                            logActionEvent(aName .. " cast a spell in " .. currentCell .. " (cost " .. tostring(oldAMag - aMag) .. " magicka).")
                        end
                    end
                    lastActorMagicka[aKey] = aMag
                end
            end
        end
    end

    -- 5. Native Dialogue & UI Stance Tracking
    -- NOTE: pendingDialogueNPC is set by handleUiModeChanged (the DialogueResponse event
    -- fires first to consume it). The 1-second fallback used to log a plain "entered dialogue"
    -- line but now the DialogueResponse handler covers that. We only use the fallback if
    -- no DialogueResponse was received at all (silent NPCs with no dialogue text).
    if pendingDialogueNPC and (now - pendingDialogueTime > 1.5) then
        logActionEvent(pName .. " entered dialogue with " .. pendingDialogueNPC .. " in " .. currentCell .. ".")
        pendingDialogueNPC = nil
    end

    if lastUIMode ~= curUIMode then
        if curUIMode == "Barter" and not barterLoggedForSession then
            local merchantName = activeNPC and sentSer.getNPCName(activeNPC) or lastBarterMerchant or "a merchant"
            logActionEvent(pName .. " opened barter/trade window with " .. merchantName .. " in " .. currentCell .. ".")
            barterLoggedForSession = true
        elseif curUIMode == "Container" and not containerLoggedForSession then
            local sourceName = lastLootSource or lastContainerName or "a container"
            local isCorpse = isLootSourceCorpse or (sourceName:lower():find("corpse") ~= nil) or (sourceName:lower():find("dead") ~= nil)
            local verb = isCorpse and "searched " or "opened/searched "
            logActionEvent(pName .. " " .. verb .. sourceName .. " in " .. currentCell .. ".")
            containerLoggedForSession = true
        end
        if curUIMode ~= "Container" then
            containerLoggedForSession = false
        end
        if curUIMode ~= "Barter" then
            barterLoggedForSession = false
        end
        if curUIMode ~= "Dialogue" then
            dialogueLoggedForSession = false
            pendingDialogueNPC = nil
        end
        lastUIMode = curUIMode
    end

    -- 6. Actor Kills & Death Tracking (Player kills, NPC vs NPC kills, World/Environmental deaths)
    local curLiving = {}
    pcall(function()
        if nearby.actors then
            for _, actor in ipairs(nearby.actors) do
                if not isPlayerActor(actor) then
                    local recName = sentSer.getNPCName(actor)
                    if not recName or recName == "" or recName == "Unknown" then
                        recName = sentSer.getObjectName(actor) or actor.recordId or "A creature"
                    end
                    if recName and recName ~= "" then
                        local actKey = tostring(actor)
                        local ok, hp = pcall(function() return types.Actor.stats.dynamic.health(actor).current end)
                        if ok and hp then
                            if hp > 0 then
                                curLiving[actKey] = true
                            else
                                if lastLivingActors[actKey] == true then
                                    local isPlrKill = false
                                    local pDist = (actor.position - self.position):length()
                                    local pStance = nil
                                    pcall(function() pStance = types.Actor.getStance(self) end)
                                    local pHasWeapon = (pStance == types.Actor.STANCE.Weapon or pStance == types.Actor.STANCE.Spell)
                                    local pRayHit = false
                                    pcall(function() pRayHit = (sentSer.getRaycastObject and sentSer.getRaycastObject() == actor) end)

                                    if pHasWeapon and (pDist <= 450 or pRayHit) then
                                        isPlrKill = true
                                    end

                                    local killer = nil
                                    if not isPlrKill and nearby.actors then
                                        local bestKillerDist = 400
                                        for _, other in ipairs(nearby.actors) do
                                            if other ~= actor and not isPlayerActor(other) then
                                                local otherHp = 0
                                                pcall(function() otherHp = types.Actor.stats.dynamic.health(other).current or 0 end)
                                                if otherHp > 0 then
                                                    local oDist = (other.position - actor.position):length()
                                                    local oStance = nil
                                                    pcall(function() oStance = types.Actor.getStance(other) end)
                                                    local inFight = (oStance == types.Actor.STANCE.Weapon or oStance == types.Actor.STANCE.Spell)
                                                    if inFight and oDist < bestKillerDist then
                                                        bestKillerDist = oDist
                                                        killer = other
                                                    elseif not killer and oDist <= 220 then
                                                        bestKillerDist = oDist
                                                        killer = other
                                                    end
                                                end
                                            end
                                        end
                                    end

                                    if isPlrKill then
                                        logActionEvent(recName .. " was killed by " .. pName .. " in " .. currentCell .. ".")
                                    elseif killer then
                                        local kName = sentSer.getNPCName(killer)
                                        if not kName or kName == "" or kName == "Unknown" then
                                            kName = sentSer.getObjectName(killer) or killer.recordId or "a creature"
                                        end
                                        logActionEvent(recName .. " was killed by " .. kName .. " in " .. currentCell .. ".")
                                    else
                                        local inWater = false
                                        pcall(function() inWater = types.Actor.isSwimming and types.Actor.isSwimming(actor) end)
                                        if inWater then
                                            logActionEvent(recName .. " drowned in " .. currentCell .. ".")
                                        else
                                            logActionEvent(recName .. " died from environmental damage in " .. currentCell .. ".")
                                        end
                                    end
                                    curLiving[actKey] = false
                                end
                            end
                        end
                    end
                end
            end
        end
    end)
    lastLivingActors = curLiving

    -- 7. Vanilla Dialogue & Journal Quest Tracking

    pcall(function()
        if types.Player.journal then
            local pj = types.Player.journal(self)
            if pj then
                -- Journal text entries
                local curJournalCount = #pj.journalTextEntries
                if lastJournalCount == nil then
                    lastJournalCount = curJournalCount
                elseif curJournalCount > lastJournalCount then
                    for idx = lastJournalCount + 1, curJournalCount do
                        local entry = pj.journalTextEntries[idx]
                        if entry and entry.text then
                            logActionEvent("Quest Journal Updated: " .. entry.text)
                        end
                    end
                    lastJournalCount = curJournalCount
                end

                -- Vanilla dialogue topics spoken by NPCs
                if pj.topics then
                    if lastTopicEntriesCount == nil then
                        lastTopicEntriesCount = {}
                        for tName, top in pairs(pj.topics) do
                            lastTopicEntriesCount[tName] = #top.entries
                        end
                    else
                        for tName, top in pairs(pj.topics) do
                            local curCnt = #top.entries
                            local oldCnt = lastTopicEntriesCount[tName] or 0
                            if curCnt > oldCnt then
                                for eIdx = oldCnt + 1, curCnt do
                                    local e = top.entries[eIdx]
                                    if e and e.text and not isDuplicateDialogue(e.text) then
                                        local actorName = e.actor or "an NPC"
                                        local worldId = sentSer.getGameWorldID()
                                        local dlgPayload = string.format(
                                            '{"command":"record_dialogue","world_id":"%s","npc":"%s","npc_id":"%s","prompt":"%s","reply":"%s"}',
                                            sentIPC.escapeJSON(worldId), sentIPC.escapeJSON(actorName),
                                            sentIPC.escapeJSON(actorName:lower()), sentIPC.escapeJSON(top.name or tName),
                                            sentIPC.escapeJSON(e.text)
                                        )
                                        reqCounter = reqCounter + 1
                                        local dlgReqId = "dlg_" .. tostring(os.time()) .. "_" .. tostring(reqCounter)
                                        sentIPC.emit(dlgPayload, dlgReqId)
                                        logActionEvent(pName .. " spoke with " .. actorName .. " about " .. (top.name or tName) .. ", who replied: \"" .. e.text .. "\"")
                                    end
                                end
                                lastTopicEntriesCount[tName] = curCnt
                            end
                        end
                    end
                end
            end
        end
    end)
    lastLivingActors = curLiving
end

local function openWindow(target)
    if isInterfaceActive and activeNPC == target then return end
    closeWindow()
    activeNPC         = target
    isInterfaceActive = true
    isListening       = false
    listeningNPCs     = {}
    chatMessages      = {}
    isThinking        = false
    inputText         = ""
    winPosition       = winPosition or util.vector2(0, 0)
    winSize           = util.vector2(
        math.max(420, math.min(1200, winSize and winSize.x or 540)),
        math.max(350, math.min(900, winSize and winSize.y or 480))
    )

    local npcName = sentSer.getNPCName(activeNPC)
    if activeNPC then
        lastRequestType = "chat"
        sendAIRequest("Greet the player.", true)
    else
        addMessage("SYSTEM", "AI Hub open. Choose an action below.")
    end

    pcall(function() UI.setMode('Interface', { windows = {} }) end)
    Controls.overrideMovementControls(true)
    Controls.overrideCombatControls(true)
    Controls.overrideUiControls(true)

    rebuildWindow()
end

sentChat.init({
    ipc = sentIPC,
    ser = sentSer,
    filterItems = filterProtectedItems,
    makeButton = sentUI.makeButton,
    logAction = function(text) logActionEvent(text) end,
})

local isInitialized = false

local lastRecordedGameTime = 0

return {
    engineHandlers = {
        onActive = function()
            -- Window focus gained; preserve active session
        end,
        onLoad   = function(data)
            pcall(function() sentSer.resetActiveSession() end)
            pcall(function()
                if data and data.sentLastExterior then
                    sentSer.setLastExterior(data.sentLastExterior)
                end
            end)
        end,
        onSave   = function()
            pcall(function()
                local frozenSaveID, prevSessionID, newSessionID = sentSer.onSaveGame()
                local pDataFull  = sentSer.getPlayerDataFull()
                local nearbyData = sentSer.getNearbyEntities()
                local savePayload = string.format(
                    '{"command":"save_game","world_id":"%s","parent_world_id":"%s","new_session_id":"%s","player_data":%s,"nearby_entities":%s}',
                    sentIPC.escapeJSON(frozenSaveID), sentIPC.escapeJSON(prevSessionID), sentIPC.escapeJSON(newSessionID),
                    sentIPC.toJSON(pDataFull), sentIPC.toJSON(nearbyData)
                )
                print("[LIVINGMW_IPC_REQ] " .. savePayload)
            end)
            -- Remember the last exterior cell across save/load (landmass awareness)
            local lastExt = nil
            pcall(function() lastExt = sentSer.getLastExterior() end)
            if lastExt then
                return { sentLastExterior = lastExt }
            end
        end,
        onFrame  = function(dt)
            local curGT = core.getGameTime()

            if lastRecordedGameTime > 0 and curGT < (lastRecordedGameTime - 0.001) then
                isInitialized = false
                pcall(function() sentSer.resetActiveSession() end)
            end
            lastRecordedGameTime = curGT


            if not isInitialized then
                isInitialized = true
                pcall(function() sentChat.reset() end)
                pcall(function() sentGuard.reset() end)
                pcall(function() sentChat.ensureTopic() end)
                pcall(function()
                    sentSer.resetActiveSession()
                    local activeSessionID, parentSaveID = sentSer.getGameWorldID()
                    local pDataFull  = sentSer.getPlayerDataFull()
                    local nearbyData = sentSer.getNearbyEntities()
                    local syncPayload = string.format(
                        '{"command":"load_game","world_id":"%s","parent_world_id":"%s","player_data":%s,"nearby_entities":%s}',
                        sentIPC.escapeJSON(activeSessionID), sentIPC.escapeJSON(parentSaveID or ""),
                        sentIPC.toJSON(pDataFull), sentIPC.toJSON(nearbyData)
                    )
                    sentIPC.emit(syncPayload, "load_game_" .. tostring(os.time()))
                end)
            end
            pcall(function() checkActionEvents(dt) end)
            pcall(sentGuard.onFrame)
            local chatOk, chatErr = pcall(sentChat.onFrame)
            if not chatOk then print("[LIVINGMW_CHAT ERROR] " .. tostring(chatErr)) end
            if isThinking and pendingCallback and currentReqId ~= "" then
                local data = sentIPC.readResponseFile()
                if data then
                    local fileId = data:match('"request_id"%s*:%s*"([^"]+)"') or ""
                    if fileId == currentReqId then
                        local cb = pendingCallback
                        pendingCallback = nil
                        currentReqId   = ""
                        thinkingStartTime = nil
                        cb(data, nil)
                    end
                elseif thinkingStartTime and (os.time() - thinkingStartTime > 25) then
                    local cb = pendingCallback
                    pendingCallback = nil
                    currentReqId   = ""
                    thinkingStartTime = nil
                    cb(nil, "AI request timed out after 25s. Ensure Python daemon is running.")
                end
            end
        end,
        onMouseWheel = function(vertical, horizontal)
            if isInterfaceActive and rootWindow then
                local maxScroll = calculateMaxScroll()
                if maxScroll > 0 then
                    if vertical > 0 then
                        scrollOffset = math.max(0, scrollOffset - 45)
                    else
                        scrollOffset = math.min(maxScroll, scrollOffset + 45)
                    end
                    rebuildWindow()
                end
            end
        end,
        onKeyPress = function(key)
            pcall(sentGuard.onKeyPress)
            local sym  = key.symbol and key.symbol:lower() or ""
            local code = key.code
            if isInterfaceActive then
                if code == input.KEY.Escape then
                    closeWindow()
                    return
                end
                local isPgUp = (input.KEY.PageUp and code == input.KEY.PageUp) or (sym == "pageup")
                local isPgDn = (input.KEY.PageDown and code == input.KEY.PageDown) or (sym == "pagedown")
                if isPgUp then
                    scrollOffset = math.max(0, scrollOffset - 120)
                    rebuildWindow()
                    return
                elseif isPgDn then
                    local maxScroll = calculateMaxScroll()
                    scrollOffset = math.min(maxScroll, scrollOffset + 120)
                    rebuildWindow()
                    return
                end
            end
            if (code ~= input.KEY.K) and (sym ~= "k") then return end
            if isInterfaceActive then
                closeWindow()
            else
                -- The native dialogue menu has its own Chat topic now.
                local mode = nil
                pcall(function() mode = UI.getMode() end)
                if mode == "Dialogue" then return end
                openWindow(sentSer.performEyeRaycast())
            end
        end
    },
    eventHandlers = {
        UiModeChanged = function(data)
            pcall(function() handleUiModeChanged(data) end)
            pcall(sentGuard.onUiModeChanged, data)
            local chatOk, chatErr = pcall(sentChat.onUiModeChanged, data)
            if not chatOk then print("[LIVINGMW_CHAT ERROR] " .. tostring(chatErr)) end
        end,
        DialogueResponse = function(e)
            pcall(function() handleDialogueResponse(e) end)
        end,
    },
}
