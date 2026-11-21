-- Living Morrowind UI Component Module for OpenMW 0.51
local ui    = require('openmw.ui')
local input  = require('openmw.input')
local util   = require('openmw.util')
local async  = require('openmw.async')
local I      = require('openmw.interfaces')
local auxUi = require('openmw_aux.ui')

local MWUI   = I.MWUI.templates
local UI     = I.UI

local uiModule = {}

function uiModule.makeButton(label, onClick)
    return {
        template = MWUI.boxSolid,
        events   = { mouseClick = async:callback(onClick) },
        content  = ui.content({
            {
                type  = ui.TYPE.Flex,
                props = {
                    position = util.vector2(6, 4),
                },
                content = ui.content({
                    {
                        template = MWUI.textNormal,
                        type     = ui.TYPE.Text,
                        props    = { text = label },
                    }
                })
            }
        })
    }
end

function uiModule.renderWindow(state, callbacks)
    local isNPC     = (state.activeNPC ~= nil)
    local npcName   = state.npcName or "Narrator"
    local dispText  = (state.npcDisposition and (" (" .. tostring(state.npcDisposition) .. ")")) or ""
    local titleText = isNPC and (npcName .. dispText) or "Chronicle of Tamriel"
    if #titleText > 24 then
        titleText = titleText:sub(1, 21) .. "..."
    end

    local winW = (state.winSize and state.winSize.x) or 540
    local winH = (state.winSize and state.winSize.y) or 480
    winW = math.max(420, winW)
    winH = math.max(350, winH)

    local contentW = winW - 24
    local chatLogH = math.max(180, winH - 150)

    local msgLayouts = {}

    if state.errorMessage then
        table.insert(msgLayouts, {
            template = MWUI.boxThick,
            props    = { size = util.vector2(contentW - 26, 0) },
            content  = ui.content({
                {
                    type  = ui.TYPE.Flex,
                    props = { horizontal = false, position = util.vector2(8, 8) },
                    content = ui.content({
                        {
                            template = MWUI.textHeader,
                            type     = ui.TYPE.Text,
                            props    = { text = "!! ERROR / FAILURE DETECTED !!" }
                        },
                        { type = ui.TYPE.Widget, props = { size = util.vector2(0, 4) } },
                        {
                            template = MWUI.textNormal,
                            type     = ui.TYPE.Text,
                            props    = {
                                text      = state.errorMessage,
                                multiline = true,
                                wordWrap  = true,
                                size      = util.vector2(contentW - 46, 0),
                            }
                        },
                        { type = ui.TYPE.Widget, props = { size = util.vector2(0, 8) } },
                        uiModule.makeButton("Dismiss Error", function()
                            if callbacks.onDismissError then callbacks.onDismissError() end
                        end)
                    })
                }
            })
        })
        table.insert(msgLayouts, { type = ui.TYPE.Widget, props = { size = util.vector2(0, 10) } })
    end

    -- Messages in chronological order: oldest at top, newest at bottom
    local msgs = state.chatMessages or {}
    for i = 1, #msgs do
        local msg = msgs[i]
        local prefix = msg.sender .. ": "
        table.insert(msgLayouts, {
            template = MWUI.textParagraph,
            props    = {
                text = prefix .. msg.text,
                size = util.vector2(contentW - 16, 0),
            }
        })
        table.insert(msgLayouts, {
            type  = ui.TYPE.Widget,
            props = { size = util.vector2(0, 6) }
        })
    end

    -- Thinking indicator at bottom (most recent)
    if state.isThinking then
        table.insert(msgLayouts, {
            template = MWUI.textParagraph,
            props    = {
                text = "[ Thinking... ]",
                size = util.vector2(contentW - 16, 0),
            }
        })
        table.insert(msgLayouts, {
            type  = ui.TYPE.Widget,
            props = { size = util.vector2(0, 6) }
        })
    end

    local btnLayouts = {}
    if isNPC then
        local editW = math.max(120, contentW - 270)
        table.insert(btnLayouts, {
            template = MWUI.box,
            props    = {
                size = util.vector2(editW, 26),
            },
            content  = ui.content({
                {
                    template = MWUI.textEditLine,
                    type     = ui.TYPE.TextEdit,
                    props    = {
                        text         = state.inputText or "",
                        relativeSize = util.vector2(1, 1),
                    },
                    events = {
                        textChanged = async:callback(function(newText)
                            if callbacks.onTextChanged then callbacks.onTextChanged(newText) end
                        end),
                        keyPress = async:callback(function(e)
                            if (e.code == input.KEY.Enter or (input.KEY.NP_Enter and e.code == input.KEY.NP_Enter)) and not state.isThinking then
                                if callbacks.onSend then callbacks.onSend() end
                            end
                        end)
                    }
                }
            })
        })
        table.insert(btnLayouts, { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } })
        if not state.isThinking then
            table.insert(btnLayouts, uiModule.makeButton("Send", function()
                if callbacks.onSend then callbacks.onSend() end
            end))
            table.insert(btnLayouts, { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } })
            if state.canShop then
                table.insert(btnLayouts, uiModule.makeButton("Shop", function()
                    if callbacks.onShop then callbacks.onShop() end
                end))
                table.insert(btnLayouts, { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } })
            end
        end
    else
        if not state.isThinking then
            table.insert(btnLayouts, uiModule.makeButton("Describe Current Scene", function()
                if callbacks.onDescribe then callbacks.onDescribe() end
            end))
            table.insert(btnLayouts, { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } })
            table.insert(btnLayouts, uiModule.makeButton("Listen to Conversation", function()
                if callbacks.onListen then callbacks.onListen() end
            end))
            table.insert(btnLayouts, { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } })
        end
    end
    table.insert(btnLayouts, uiModule.makeButton("Goodbye", function()
        if callbacks.onClose then callbacks.onClose() end
    end))

    local winPos = state.winPosition or util.vector2(0, 0)

    local moveLabel = state.isMoving and "[ Lock Position ]" or "[ Move ]"
    local sizeLabel = (state.winSize and state.winSize.x > 600) and "Normal" or "Large"

    local headerLayout = {
        type = ui.TYPE.Flex,
        props = {
            horizontal = true,
            size = util.vector2(contentW, 24),
        },
        content = ui.content({
            {
                template = MWUI.textHeader,
                type     = ui.TYPE.Text,
                props    = { text = titleText },
            },
            { type = ui.TYPE.Widget, props = { size = util.vector2(8, 0) } },
            uiModule.makeButton("< Left", function()
                if callbacks.onMoveLeft then callbacks.onMoveLeft() end
            end),
            { type = ui.TYPE.Widget, props = { size = util.vector2(4, 0) } },
            uiModule.makeButton("Center", function()
                if callbacks.onMoveCenter then callbacks.onMoveCenter() end
            end),
            { type = ui.TYPE.Widget, props = { size = util.vector2(4, 0) } },
            uiModule.makeButton("Right >", function()
                if callbacks.onMoveRight then callbacks.onMoveRight() end
            end),
            { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } },
            uiModule.makeButton(sizeLabel, function()
                if callbacks.onToggleSize then callbacks.onToggleSize() end
            end),
            { type = ui.TYPE.Widget, props = { size = util.vector2(6, 0) } },
            uiModule.makeButton("^ Up", function()
                if callbacks.onScrollUp then callbacks.onScrollUp() end
            end),
            { type = ui.TYPE.Widget, props = { size = util.vector2(4, 0) } },
            uiModule.makeButton("v Down", function()
                if callbacks.onScrollDown then callbacks.onScrollDown() end
            end),
        })
    }

    local windowBox = {
        template = MWUI.boxSolid,
        props    = {
            size     = util.vector2(winW, winH),
        },

        content  = ui.content({
            {
                type  = ui.TYPE.Flex,
                props = {
                    horizontal   = false,
                    position     = util.vector2(12, 12),
                    relativeSize = util.vector2(1, 1),
                    size         = util.vector2(-24, -24),
                },
                content = ui.content({
                    headerLayout,
                    { template = MWUI.horizontalLine, props = { size = util.vector2(contentW, 0) } },
                    { type = ui.TYPE.Widget, props = { size = util.vector2(0, 8) } },

                    -- Chat Log: clipped scroll viewport
                    {
                        type  = ui.TYPE.Widget,
                        props = {
                            size = util.vector2(contentW, chatLogH),
                            clip = true,
                        },
                        events = {
                            mouseScroll = async:callback(function(e)
                                if callbacks.onScroll then callbacks.onScroll(e) end
                            end)
                        },
                        content = ui.content({
                            {
                                name  = "msgFlex",
                                type  = ui.TYPE.Flex,
                                props = {
                                    horizontal = false,
                                    position   = util.vector2(8, 8 - (state.scrollOffset or 0)),
                                },
                                content = ui.content(msgLayouts)
                            }
                        })
                    },

                    { type = ui.TYPE.Widget, props = { size = util.vector2(0, 8) } },
                    { template = MWUI.horizontalLine, props = { size = util.vector2(contentW, 0) } },
                    { type = ui.TYPE.Widget, props = { size = util.vector2(0, 8) } },

                    -- Action Bar (Fixed Bottom)
                    {
                        type    = ui.TYPE.Flex,
                        props   = { horizontal = true },
                        content = ui.content(btnLayouts)
                    },
                    (function()
                        if state.offeredItems and #state.offeredItems > 0 then
                            local names = {}
                            for _, it in ipairs(state.offeredItems) do
                                table.insert(names, (it.count and it.count > 1 and (tostring(it.count) .. " ") or "") .. it.id:gsub("_", " "))
                            end
                            local itemDesc = table.concat(names, ", ")
                            return {
                                type  = ui.TYPE.Flex,
                                props = { horizontal = true, position = util.vector2(0, 4) },
                                content = ui.content({
                                    uiModule.makeButton("Accept " .. itemDesc, function()
                                        if callbacks.onAcceptOffer then callbacks.onAcceptOffer(state.offeredItems, itemDesc) end
                                    end),
                                    { type = ui.TYPE.Widget, props = { size = util.vector2(8, 0) } },
                                    uiModule.makeButton("Decline", function()
                                        if callbacks.onDeclineOffer then callbacks.onDeclineOffer(state.offeredItems, itemDesc) end
                                    end),
                                })
                            }
                        elseif state.requestedItems and #state.requestedItems > 0 then
                            local names = {}
                            for _, it in ipairs(state.requestedItems) do
                                table.insert(names, (it.count and it.count > 1 and (tostring(it.count) .. " ") or "") .. it.id:gsub("_", " "))
                            end
                            local itemDesc = table.concat(names, ", ")
                            return {
                                type  = ui.TYPE.Flex,
                                props = { horizontal = true, position = util.vector2(0, 4) },
                                content = ui.content({
                                    uiModule.makeButton("Give " .. itemDesc, function()
                                        if callbacks.onGiveItem then callbacks.onGiveItem(state.requestedItems, itemDesc) end
                                    end),
                                    { type = ui.TYPE.Widget, props = { size = util.vector2(8, 0) } },
                                    uiModule.makeButton("Refuse", function()
                                        if callbacks.onRefuseItem then callbacks.onRefuseItem(state.requestedItems, itemDesc) end
                                    end),
                                })
                            }
                        end
                        return { type = ui.TYPE.Widget, props = { size = util.vector2(0, 0) } }
                    end)(),
                })
            }
        })
    }


    return {
        layer = 'Windows',
        type  = ui.TYPE.Widget,
        props = {
            relativePosition = util.vector2(0.5, 0.5),
            position         = winPos,
            anchor           = util.vector2(0.5, 0.5),
            size             = util.vector2(winW, winH),
        },
        content = ui.content({ windowBox })
    }
end


return uiModule
