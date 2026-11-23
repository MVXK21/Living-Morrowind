-- Living Morrowind: free-text chat inside the native dialogue menu.
--
-- Clicking the "* Chat *" topic (living_morrowind_chat.esp) opens a slim input
-- bar docked to the dialogue window. What you say and what the NPC answers are
-- written into the real dialogue history with ui.showMessage.
local self    = require('openmw.self')
local types   = require('openmw.types')
local ui      = require('openmw.ui')
local util    = require('openmw.util')
local core    = require('openmw.core')
local async   = require('openmw.async')
local input   = require('openmw.input')
local storage = require('openmw.storage')
local vfs     = require('openmw.vfs')
local I       = require('openmw.interfaces')

local MWUI = I.MWUI.templates

local CHAT_TOPIC    = "* Chat *"
local LAYOUT_VFS    = "scripts/living_morrowind/chat_layout.json"
local LAYER         = "Popup"
local BAR_H         = 34
local LABEL_W       = 52
local ACTION_W      = 116
local GAP           = 3
local POLL_INTERVAL = 0.1
local TIMEOUT       = 60
local LATE_WINDOW   = 120

local barStorage = storage.playerSection('LivingMWChatBar')

local chat = {}
local deps = nil

-- Session
local active       = false   -- the player clicked Chat in this conversation
local inDialogue   = false
local sessionActor = nil
local sessionName  = "NPC"
local inputText    = ""
local queued       = {}      -- replies that arrived while a sub-menu was open
local offered      = nil
local requested    = nil

-- Request in flight
local pending      = nil     -- { id, startedAt, name, detached }
local lateRequest  = nil     -- timed out, but its reply may still arrive
local lastPoll     = 0
local reqCounter   = 0

-- Widgets
local labelEl, inputEl, actionEl, offerEl = nil, nil, nil, nil
local anchor   = nil
local dragX    = 0
local dragY    = 0
local dragFrom = nil

local missingTopicWarned = false

-- ─── Helpers ─────────────────────────────────────────────────────────────────

local function trim(s)
    return ((s or ""):match("^%s*(.-)%s*$"))
end

-- '#' starts MyGUI colour codes and #{...} localisation tags.
local function cleanForHistory(s)
    return (trim(s):gsub("#", ""))
end

local function showInHistory(text)
    ui.showMessage(cleanForHistory(text), { showInDialogue = true })
end

local function deliver(text, detached)
    if detached then
        ui.showMessage(cleanForHistory(text), { showInDialogue = false })
    elseif inDialogue then
        showInHistory(text)
    elseif active then
        table.insert(queued, text)
    else
        ui.showMessage(cleanForHistory(text), { showInDialogue = false })
    end
end

local function sameActor(a, b)
    if not a or not b then return false end
    local ok, same = pcall(function() return a.id == b.id end)
    return ok and same
end

local function itemDescription(items)
    local names = {}
    for _, it in ipairs(items or {}) do
        local label = (it.id or "item"):gsub("_", " ")
        if it.count and it.count > 1 then
            label = tostring(it.count) .. " " .. label
        end
        table.insert(names, label)
    end
    return table.concat(names, ", ")
end

-- ─── Placement ───────────────────────────────────────────────────────────────

local function readWindowRect()
    local rect = { x = 0.15, y = 0.5, w = 0.7, h = 0.45 }
    pcall(function()
        local f = vfs.open(LAYOUT_VFS)
        if not f then return end
        local data = f:read("*all")
        f:close()
        for _, key in ipairs({ "x", "y", "w", "h" }) do
            local v = tonumber(data:match('"' .. key .. '"%s*:%s*([%d%.]+)'))
            if v then rect[key] = v end
        end
    end)
    return rect
end

local function layerHeight()
    local h = nil
    pcall(function()
        h = ui.layers[ui.layers.indexOf(LAYER)].size.y
    end)
    return h or ui.screenSize().y
end

local function computeAnchor()
    local rect = readWindowRect()
    local height = layerHeight()
    local below = rect.y + rect.h
    local a = { x = rect.x, w = rect.w }
    if (1 - below) * height >= BAR_H + 2 then
        a.y, a.dy = below, 2                     -- directly under the window
    elseif rect.y * height >= BAR_H + 2 then
        a.y, a.dy = rect.y, -BAR_H - 2           -- directly above it
    else
        a.y, a.dy = below, -BAR_H - 8            -- no room: inside the bottom edge
    end
    a.sig = string.format("%.4f,%.4f,%.4f,%.4f", rect.x, rect.y, rect.w, rect.h)

    -- A position the player dragged to is kept until the window itself moves.
    dragX, dragY = 0, 0
    if barStorage:get('sig') == a.sig then
        dragX = barStorage:get('dragX') or 0
        dragY = barStorage:get('dragY') or 0
    end
    return a
end

local function placedProps(offsetX, size, relWidth, extraY)
    return {
        relativePosition = util.vector2(anchor.x, anchor.y),
        position = util.vector2(offsetX + dragX, anchor.dy + dragY + (extraY or 0)),
        relativeSize = util.vector2(relWidth or 0, 0),
        size = size,
    }
end

-- ─── Layouts ─────────────────────────────────────────────────────────────────

local submit -- forward declaration

local function centeredText(text)
    return {
        template = MWUI.textNormal,
        type = ui.TYPE.Text,
        props = {
            text = text,
            relativePosition = util.vector2(0.5, 0.5),
            anchor = util.vector2(0.5, 0.5),
        },
    }
end

local refreshPositions -- forward declaration

-- MWUI box templates shrink to their content, so the bar uses fixed-size panels.
local panelTexture = ui.texture({ path = 'white' })

local function panelBackground()
    return {
        type = ui.TYPE.Image,
        props = {
            resource = panelTexture,
            color = util.color.rgb(0, 0, 0),
            alpha = 0.85,
            relativeSize = util.vector2(1, 1),
        },
    }
end

local function panel(props, events, child)
    return {
        layer = LAYER,
        type = ui.TYPE.Widget,
        template = MWUI.borders,
        props = props,
        events = events or {},
        content = ui.content({ panelBackground(), child }),
    }
end

local function labelLayout()
    return panel(placedProps(0, util.vector2(LABEL_W, BAR_H)), {
            mousePress = async:callback(function(e)
                dragFrom = e.position
            end),
            mouseMove = async:callback(function(e)
                if dragFrom then
                    local delta = e.position - dragFrom
                    dragFrom = e.position
                    dragX = dragX + delta.x
                    dragY = dragY + delta.y
                    refreshPositions()
                end
            end),
            mouseRelease = async:callback(function()
                if dragFrom then
                    dragFrom = nil
                    barStorage:set('sig', anchor.sig)
                    barStorage:set('dragX', dragX)
                    barStorage:set('dragY', dragY)
                end
            end),
        }, centeredText("Say:"))
end

local function inputLayout()
    return panel(placedProps(LABEL_W + GAP,
            util.vector2(-(LABEL_W + ACTION_W + 2 * GAP), BAR_H), anchor.w), nil, {
                template = MWUI.textEditLine,
                type = ui.TYPE.TextEdit,
                props = {
                    text = inputText,
                    position = util.vector2(5, 0),
                    relativeSize = util.vector2(1, 1),
                    size = util.vector2(-10, 0),
                    autoSize = false,
                    textAlignV = ui.ALIGNMENT.Center,
                },
                events = {
                    textChanged = async:callback(function(text)
                        inputText = text
                    end),
                    keyPress = async:callback(function(e)
                        if e.code == input.KEY.Enter or (input.KEY.NP_Enter and e.code == input.KEY.NP_Enter) then
                            submit()
                        end
                    end),
                },
            })
end

local function actionLayout()
    local busy = pending ~= nil
    return panel({
            relativePosition = util.vector2(anchor.x + anchor.w, anchor.y),
            position = util.vector2(-ACTION_W + dragX, anchor.dy + dragY),
            size = util.vector2(ACTION_W, BAR_H),
        }, busy and {} or {
            mouseClick = async:callback(function() submit() end),
        }, centeredText(busy and "Thinking..." or "Send"))
end

-- ─── Item offers ─────────────────────────────────────────────────────────────

local sendToNpc -- forward declaration
local refreshOffers

local function resolveItems(verb, event, eventData, followUp, items)
    local desc = itemDescription(items)
    offered, requested = nil, nil
    refreshOffers()
    if event then
        pcall(function() core.sendGlobalEvent(event, eventData) end)
    end
    showInHistory("You " .. verb .. " " .. desc .. ".")
    local who = deps.ser.getPlayerData().name or "Player"
    local cell = (self.cell and self.cell.name) or "Unknown Cell"
    pcall(function()
        deps.logAction(who .. " " .. verb .. " " .. desc .. " (" .. sessionName .. ", " .. cell .. ").")
    end)
    sendToNpc(string.format(followUp, desc))
end

local function offerLayout()
    local buttons = {}
    local spacer = { type = ui.TYPE.Widget, props = { size = util.vector2(GAP * 2, 0) } }
    if offered then
        local items = offered
        local desc = itemDescription(items)
        table.insert(buttons, deps.makeButton("Accept " .. desc, function()
            resolveItems("accepted", "LivingMW_GiveItem", { target = self.object or self, items = items },
                "The player accepted %s from you.", items)
        end))
        table.insert(buttons, spacer)
        table.insert(buttons, deps.makeButton("Decline", function()
            resolveItems("declined", nil, nil, "The player declined %s offered by you.", items)
        end))
    elseif requested then
        local items = requested
        local desc = itemDescription(items)
        table.insert(buttons, deps.makeButton("Give " .. desc, function()
            resolveItems("handed over", "LivingMW_TakeItem",
                { source = self.object or self, target = sessionActor, items = items },
                "The player handed over %s to you.", items)
        end))
        table.insert(buttons, spacer)
        table.insert(buttons, deps.makeButton("Refuse", function()
            resolveItems("refused to give", nil, nil, "The player refused to give you %s.", items)
        end))
    end
    return {
        layer = LAYER,
        type = ui.TYPE.Flex,
        props = {
            horizontal = true,
            relativePosition = util.vector2(anchor.x, anchor.y),
            position = util.vector2(dragX, anchor.dy + dragY - BAR_H - 2),
        },
        content = ui.content(buttons),
    }
end

refreshOffers = function()
    if not inputEl then return end
    if offered or requested then
        if offerEl then
            offerEl.layout = offerLayout()
            offerEl:update()
        else
            offerEl = ui.create(offerLayout())
        end
    elseif offerEl then
        offerEl:destroy()
        offerEl = nil
    end
end

local function refreshAction()
    if actionEl then
        actionEl.layout = actionLayout()
        actionEl:update()
    end
end

refreshPositions = function()
    if not inputEl then return end
    labelEl.layout = labelLayout()
    labelEl:update()
    inputEl.layout = inputLayout()
    inputEl:update()
    refreshAction()
    refreshOffers()
end

local function showBar()
    if inputEl then return end
    anchor = computeAnchor()
    labelEl = ui.create(labelLayout())
    inputEl = ui.create(inputLayout())
    actionEl = ui.create(actionLayout())
    refreshOffers()
end

local function hideBar()
    dragFrom = nil
    if labelEl then labelEl:destroy(); labelEl = nil end
    if inputEl then inputEl:destroy(); inputEl = nil end
    if actionEl then actionEl:destroy(); actionEl = nil end
    if offerEl then offerEl:destroy(); offerEl = nil end
end

-- ─── Daemon requests ─────────────────────────────────────────────────────────

sendToNpc = function(promptText)
    if pending or not sessionActor then return false end
    local ipc, ser = deps.ipc, deps.ser
    local ok, err = pcall(function()
        reqCounter = reqCounter + 1
        local reqId = "chat_" .. tostring(os.time()) .. "_" .. tostring(reqCounter)
        local worldId, parentId = ser.getGameWorldID()
        local parentClause = (parentId and parentId ~= "")
            and string.format(',"parent_world_id":"%s"', (ipc.escapeJSON(parentId))) or ""
        local entityType = (sessionActor.type == types.Creature) and "Creature" or "NPC"
        local payload = string.format(
            '{"command":"dialogue","prompt":"%s","npc":"%s","npc_id":"%s","world_id":"%s"%s,"entity_type":"%s","intelligence":"50","system_prompt":"","request_id":"%s","player_data":%s,"target_data":%s,"nearby_entities":%s}',
            (ipc.escapeJSON(promptText)), (ipc.escapeJSON(sessionName)), (ipc.escapeJSON(sessionActor.recordId)),
            (ipc.escapeJSON(worldId)), parentClause, entityType, reqId,
            ipc.toJSON(ser.getPlayerDataFull()), ipc.toJSON(ser.serializeNPC(sessionActor) or {}),
            ipc.toJSON(ser.getNearbyEntities() or {})
        )
        lateRequest = nil
        pending = { id = reqId, startedAt = core.getRealTime(), name = sessionName }
        ipc.emit(payload, reqId)
    end)
    if not ok then
        pending = nil
        print("[LIVINGMW_CHAT ERROR] Could not send message: " .. tostring(err))
        deliver("(Living Morrowind could not send that message. See openmw.log.)")
    end
    refreshAction()
    return ok
end

submit = function()
    if pending then return end
    local text = trim(inputText)
    if text == "" then return end
    inputText = ""
    if inputEl then
        inputEl.layout = inputLayout()
        inputEl:update()
    end
    offered, requested = nil, nil
    refreshOffers()
    showInHistory("You: " .. text)
    sendToNpc(text)
end

local function deliverReply(req, raw, allowOffers)
    local reply = trim(deps.ipc.extractReply(raw) or "")
    if reply == "" or reply == "..." then
        deliver("(" .. req.name .. " says nothing. The AI service may be busy; try again.)", req.detached)
        return
    end
    deliver(req.name .. ": " .. reply, req.detached)
    if allowOffers and not req.detached then
        offered = deps.filterItems(deps.ipc.extractOfferedItems(raw))
        requested = deps.filterItems(deps.ipc.extractRequestedItems(raw))
    end
end

local function finishRequest(raw)
    local req = pending
    pending = nil
    if raw then
        deliverReply(req, raw, true)
    else
        deliver("(Still waiting on the AI service. The reply will appear here if it arrives.)", req.detached)
        lateRequest = req
    end
    refreshAction()
    refreshOffers()
end

-- ─── Engine hooks ────────────────────────────────────────────────────────────

function chat.init(dependencies)
    deps = dependencies
end

function chat.ensureTopic()
    local ok, err = pcall(function()
        types.Player.addTopic(self, CHAT_TOPIC)
    end)
    if not ok and not missingTopicWarned then
        missingTopicWarned = true
        print("[LIVINGMW_CHAT WARNING] Chat topic unavailable; enable living_morrowind_chat.esp. " .. tostring(err))
    end
end

function chat.reset()
    hideBar()
    active, inDialogue, sessionActor = false, false, nil
    inputText, queued, offered, requested, pending, lateRequest = "", {}, nil, nil, nil, nil
end

-- Returns true when the response belongs to the Chat topic.
function chat.onDialogueResponse(e)
    if not e or e.type ~= "topic" then return false end
    local id = tostring(e.recordId or ""):lower()
    if not id:match("^%*%s*chat%s*%*$") then return false end
    if not sameActor(sessionActor, e.actor) then
        if pending then pending.detached = true end
        if lateRequest then lateRequest.detached = true end
        offered, requested = nil, nil
        hideBar()
    end
    active = true
    inDialogue = true
    sessionActor = e.actor
    sessionName = deps.ser.getNPCName(e.actor) or "NPC"
    showBar()
    return true
end

function chat.onUiModeChanged(data)
    local newMode = data and data.newMode
    if newMode == "Dialogue" then
        inDialogue = true
        if active and data.arg and not sameActor(data.arg, sessionActor) then
            if pending then pending.detached = true end
            if lateRequest then lateRequest.detached = true end
            active, sessionActor, offered, requested = false, nil, nil, nil
            hideBar()
        end
        if active then
            showBar()
            for _, text in ipairs(queued) do showInHistory(text) end
            queued = {}
        end
        return
    end

    inDialogue = false
    hideBar()
    if newMode == nil then
        -- Conversation over: anything still on its way appears as a message box.
        for _, text in ipairs(queued) do
            ui.showMessage(cleanForHistory(text), { showInDialogue = false })
        end
        queued = {}
        if pending then pending.detached = true end
        if lateRequest then lateRequest.detached = true end
        active, sessionActor, offered, requested = false, nil, nil, nil
        inputText = ""
    end
end

function chat.onFrame()
    if not pending and not lateRequest then return end
    local now = core.getRealTime()
    if now - lastPoll < POLL_INTERVAL then return end
    lastPoll = now

    local data = deps.ipc.readResponseFile()
    local fileId = data and (data:match('"request_id"%s*:%s*"([^"]+)"') or "") or ""
    if pending then
        if fileId == pending.id then
            finishRequest(data)
        elseif now - pending.startedAt > TIMEOUT then
            finishRequest(nil)
        end
    elseif lateRequest then
        if fileId == lateRequest.id then
            local req = lateRequest
            lateRequest = nil
            deliverReply(req, data, false)
        elseif now - lateRequest.startedAt > LATE_WINDOW then
            lateRequest = nil
        end
    end
end

return chat
