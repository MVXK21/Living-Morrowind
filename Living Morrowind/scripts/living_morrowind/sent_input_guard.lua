-- Living Morrowind: keeps hotkeys from acting while the dialogue menu is open.
--
-- Mods such as lockpick and torch hotkeys can stay live during dialogue, especially
-- when another mod keeps the world running. This guard:
--   1. forces every Boolean input action to false while dialogue is open,
--   2. turns off OpenMW's own UI, combat and movement hotkeys, and
--   3. undoes equipment, stance or selected-magic changes caused by a stray key.
local self    = require('openmw.self')
local types   = require('openmw.types')
local input   = require('openmw.input')
local async   = require('openmw.async')
local core    = require('openmw.core')
local storage = require('openmw.storage')
local I       = require('openmw.interfaces')

local Actor = types.Actor
local ARM_TIME = 0.35
local CYCLE_ACTIONS = { "CycleSpellLeft", "CycleSpellRight", "CycleWeaponLeft", "CycleWeaponRight" }

local guard = {}
local blocked = false
local gated = {}          -- action key -> "bound" or "unbound"
local snapshot = nil
local armedUntil = 0

local gateCallback = async:callback(function(_, value)
    if blocked then return false end
    return value
end)

-- OpenMW's key binding callback ignores earlier values, so a gate must be added
-- after it. An action that gains its first key binding gets a new gate.
local function refreshGates()
    local bound = {}
    pcall(function()
        for _, binding in pairs(storage.playerSection('OMWInputBindings'):asTable()) do
            if binding.type == 'action' and binding.key then bound[binding.key] = true end
        end
    end)
    pcall(function()
        for key, info in pairs(input.actions) do
            if info.type == input.ACTION_TYPE.Boolean then
                local state = bound[key] and "bound" or "unbound"
                if gated[key] == nil or (gated[key] == "unbound" and state == "bound") then
                    local ok = pcall(input.bindAction, key, gateCallback, {})
                    if ok then gated[key] = state end
                end
            end
        end
    end)
end

local function setControlsLocked(locked)
    pcall(function()
        I.Controls.overrideMovementControls(locked)
        I.Controls.overrideCombatControls(locked)
        I.Controls.overrideUiControls(locked)
    end)
end

local function takeSnapshot()
    local current = nil
    pcall(function()
        current = {
            equipment = Actor.getEquipment(self),
            spell = Actor.getSelectedSpell(self),
            item = Actor.getSelectedEnchantedItem(self),
            stance = Actor.getStance(self),
        }
    end)
    if current then snapshot = current end
end

local function sameObject(a, b)
    if a == nil or b == nil then return a == b end
    return a.id == b.id
end

local function sameEquipment(a, b)
    for slot, object in pairs(a) do
        if not sameObject(object, b[slot]) then return false end
    end
    for slot, object in pairs(b) do
        if not sameObject(a[slot], object) then return false end
    end
    return true
end

local function restoreSnapshot()
    if not snapshot then return end
    pcall(function()
        if not sameEquipment(Actor.getEquipment(self), snapshot.equipment) then
            Actor.setEquipment(self, snapshot.equipment)
        end
    end)
    pcall(function()
        local spell = Actor.getSelectedSpell(self)
        local item = Actor.getSelectedEnchantedItem(self)
        if not sameObject(spell, snapshot.spell) or not sameObject(item, snapshot.item) then
            if snapshot.item then
                Actor.setSelectedEnchantedItem(self, snapshot.item)
            else
                Actor.setSelectedSpell(self, snapshot.spell)
            end
        end
    end)
    pcall(function()
        if Actor.getStance(self) ~= snapshot.stance then
            Actor.setStance(self, snapshot.stance)
        end
    end)
end

local function setBlocked(value)
    if value == blocked then return end
    blocked = value
    setControlsLocked(value)
    armedUntil = 0
    if value then
        refreshGates()
        takeSnapshot()
    else
        snapshot = nil
    end
end

function guard.reset()
    setBlocked(false)
end

function guard.onUiModeChanged(data)
    setBlocked((data and data.newMode) == "Dialogue")
end

-- Only keys that did not go into the text box reach Lua key handlers.
function guard.onKeyPress()
    if blocked then armedUntil = core.getRealTime() + ARM_TIME end
end

function guard.onFrame()
    if not blocked then return end
    local now = core.getRealTime()
    for _, name in ipairs(CYCLE_ACTIONS) do
        local action = input.ACTION[name]
        if action and input.isActionPressed(action) then
            armedUntil = now + ARM_TIME
            break
        end
    end
    if now < armedUntil then
        restoreSnapshot()
    else
        takeSnapshot()
    end
end

return guard
