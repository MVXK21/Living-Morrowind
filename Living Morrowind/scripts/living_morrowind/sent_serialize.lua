-- Living Morrowind Serializer & Targeting Module for OpenMW 0.51
local self   = require('openmw.self')
local types  = require('openmw.types')
local nearby = require('openmw.nearby')
local camera = require('openmw.camera')
local util   = require('openmw.util')

local serialize = {}

function serialize.getNPCName(actor)
    if not actor then return "Narrator" end
    local name = nil
    pcall(function()
        if actor.type == types.NPC and types.NPC.record then
            local r = types.NPC.record(actor)
            if r and r.name then name = r.name end
        elseif actor.type == types.Creature and types.Creature.record then
            local r = types.Creature.record(actor)
            if r and r.name then name = r.name end
        end
        if not name and actor.recordId then
            name = actor.recordId
        end
    end)
    return name or "Unknown"
end

function serialize.getNPCDisposition(actor)
    if not actor then return nil end
    local ok, disp = pcall(function()
        if types.NPC.stats and types.NPC.stats.disposition then
            return types.NPC.stats.disposition(actor):current()
        end
        return nil
    end)
    if ok and disp then return math.floor(disp) end
    return nil
end

local core   = require('openmw.core')

function serialize.getClassName(classId, fallback)
    local defFallback = fallback or "Adventurer"
    if not classId or classId == "" then return defFallback end
    local resolvedName = nil
    pcall(function()
        if types.NPC.classes then
            if types.NPC.classes.record then
                local cRec = types.NPC.classes.record(classId)
                if cRec and cRec.name and cRec.name ~= "" then
                    resolvedName = cRec.name
                end
            end
            if not resolvedName and types.NPC.classes.records then
                local cRec = types.NPC.classes.records[classId]
                if cRec and cRec.name and cRec.name ~= "" then
                    resolvedName = cRec.name
                end
            end
        end
    end)
    if not resolvedName or resolvedName == "" then
        resolvedName = classId
    end
    if resolvedName:find("^[Gg]enerated:") then
        return defFallback
    end
    return resolvedName
end

function serialize.getPlayerData()
    local ok, rec = pcall(function() return types.Player.record(self) end)
    local rawClass = (ok and rec and rec.class) or "Adventurer"
    local className = serialize.getClassName(rawClass, "Adventurer")
    return {
        name   = (ok and rec and rec.name) or "Traveler",
        race   = (ok and rec and rec.race) or "Unknown",
        gender = (ok and rec and rec.isFemale and "female") or "male",
        class  = className,
        level  = (ok and rec and rec.level) or 1,
    }
end

local storage = require('openmw.storage')
local saveStorage = storage.playerSection('SentientSaveMapping')  -- same name as Sentient Morrowind, so existing saves keep their memories

local activeSessionID = nil
local lastPlayerName = nil

function serialize.resetActiveSession()
    activeSessionID = nil
end

function serialize.getGameWorldID()
    local pData = serialize.getPlayerData()
    local safeName = pData.name:gsub("%s+", "_"):gsub("[^%w_]", "")
    if safeName == "" then safeName = "Traveler" end

    if lastPlayerName and lastPlayerName ~= safeName then
        activeSessionID = nil
    end
    lastPlayerName = safeName

    local isFrozen = saveStorage:get('isSavePointFrozen')
    local parentSaveID = nil
    if isFrozen then
        parentSaveID = saveStorage:get('activeSaveID')
        if parentSaveID and not parentSaveID:find("^world_" .. safeName) then
            parentSaveID = nil
        end
    end

    if not activeSessionID then
        local baseID = parentSaveID or ("world_" .. safeName .. "_" .. tostring(os.time()))
        activeSessionID = baseID .. "_session_" .. tostring(os.time())
    end

    return activeSessionID, parentSaveID
end

function serialize.onSaveGame()
    local pData = serialize.getPlayerData()
    local safeName = pData.name:gsub("%s+", "_"):gsub("[^%w_]", "")
    if safeName == "" then safeName = "Traveler" end

    local prevSessionID = activeSessionID or serialize.getGameWorldID()
    local frozenSaveID = "world_" .. safeName .. "_" .. tostring(os.time())
    
    saveStorage:set('activeSaveID', frozenSaveID)
    saveStorage:set('isSavePointFrozen', true)

    activeSessionID = frozenSaveID .. "_session_" .. tostring(os.time() + 1)
    return frozenSaveID, prevSessionID, activeSessionID
end

function serialize.getActorInventory(actor)
    local invList = {}
    if not actor then return invList end
    pcall(function()
        local inv = types.Actor.inventory and types.Actor.inventory(actor)
        if inv and inv.getAll then
            local items = inv:getAll()
            for _, item in ipairs(items) do
                if item and item.recordId then
                    local recName = item.recordId
                    local cnt = item.count or 1
                    pcall(function()
                        if item.type and item.type.record then
                            local r = item.type.record(item)
                            if r and r.name then recName = r.name end
                        end
                    end)
                    if recName and recName ~= "" then
                        table.insert(invList, { id = item.recordId, name = recName, count = cnt })
                    end
                end
            end
        end
    end)
    return invList
end

function serialize.getActorMagic(actor)
    local powers = {}
    local passiveAbilities = {}
    local spells = {}

    if not actor then return powers, passiveAbilities, spells end

    pcall(function()
        local actorSpells = types.Actor.spells and types.Actor.spells(actor)
        if actorSpells then
            for _, spell in pairs(actorSpells) do
                local sId = nil
                local sName = nil
                local sCost = nil
                local sType = nil
                local rawEffects = nil

                if type(spell) == "string" then
                    sId = spell
                    sName = spell
                elseif spell and (spell.id or spell.name) then
                    sId = spell.id or spell.name
                    sName = spell.name or sId
                    sCost = spell.cost
                    sType = spell.type
                    rawEffects = spell.effects
                end

                if sId then
                    local spRec = nil
                    pcall(function()
                        if types.Spell and types.Spell.record then
                            spRec = types.Spell.record(sId)
                        end
                    end)
                    if not spRec then
                        pcall(function()
                            if core.magic and core.magic.spells and core.magic.spells.records then
                                spRec = core.magic.spells.records[sId]
                            end
                        end)
                    end
                    if spRec then
                        sName = spRec.name or sName
                        if sCost == nil then sCost = spRec.cost end
                        if sType == nil then sType = spRec.type end
                        if not rawEffects then rawEffects = spRec.effects end
                    end
                    sCost = sCost or 0

                    local isPower = false
                    local isAbility = false

                    pcall(function()
                        if core.magic and core.magic.SPELL_TYPE then
                            local ST = core.magic.SPELL_TYPE
                            if sType == ST.Power then isPower = true
                            elseif sType == ST.Ability then isAbility = true
                            end
                        end
                    end)
                    if not (isPower or isAbility) then
                        if sType == 5 or sType == "Power" or sType == "power" then isPower = true
                        elseif sType == 1 or sType == "Ability" or sType == "ability" then isAbility = true
                        elseif sCost == 0 and sType ~= 0 then isAbility = true
                        end
                    end

                    local effList = {}
                    pcall(function()
                        if rawEffects then
                            for _, eff in ipairs(rawEffects) do
                                local effName = eff.id or "Effect"
                                pcall(function()
                                    if core.magic and core.magic.effects and core.magic.effects.records then
                                        local r = core.magic.effects.records[eff.id]
                                        if r and r.name then effName = r.name end
                                    end
                                end)
                                local mag = ""
                                if eff.magnitudeMin and eff.magnitudeMax then
                                    if eff.magnitudeMin == eff.magnitudeMax then
                                        mag = " " .. tostring(eff.magnitudeMin) .. " pts"
                                    else
                                        mag = " " .. tostring(eff.magnitudeMin) .. "-" .. tostring(eff.magnitudeMax) .. " pts"
                                    end
                                end
                                local dur = (eff.duration and eff.duration > 0) and (" for " .. tostring(eff.duration) .. "s") or ""
                                table.insert(effList, effName .. mag .. dur)
                            end
                        end
                    end)
                    local desc = #effList > 0 and table.concat(effList, ", ") or ""
                    local entry = { id = sId, name = sName, description = desc }

                    if isPower then
                        table.insert(powers, entry)
                    elseif isAbility then
                        table.insert(passiveAbilities, entry)
                    else
                        entry.cost = sCost
                        table.insert(spells, entry)
                    end
                end
            end
        end
    end)

    return powers, passiveAbilities, spells
end

function serialize.serializeNPC(actor)
    if not actor then return nil end
    local ok, rec = pcall(function() return types.NPC.record(actor) end)
    if not ok or not rec then return nil end
    local disp = serialize.getNPCDisposition(actor)
    local inv = serialize.getActorInventory(actor)
    local rawClass = rec.class or "Commoner"
    local className = serialize.getClassName(rawClass, "Commoner")
    local powers, passives = serialize.getActorMagic(actor)
    return {
        id                = actor.recordId or "unknown",
        name              = rec.name or "Unknown",
        race              = rec.race or "Unknown",
        gender            = rec.isFemale and "female" or "male",
        class             = className,
        level             = rec.level or 1,
        disposition       = disp,
        powers            = #powers > 0 and powers or nil,
        passive_abilities = #passives > 0 and passives or nil,
        inventory         = inv,
    }
end

function serialize.getObjectName(ref)
    if not ref then return nil end
    local name = nil
    pcall(function()
        if ref.recordId then name = ref.recordId end
        if ref.type and ref.type.record then
            local r = ref.type.record(ref)
            if r and r.name then name = r.name end
        end
    end)
    return name
end

function serialize.getRaycastObject()
    local targetObj = nil
    pcall(function()
        local eyePos = self.position + util.vector3(0, 0, 110)
        local lookDir = self.rotation:apply(util.vector3(0, 1, 0))
        -- 1. Forward eye ray
        local res = nearby.castRay(eyePos, eyePos + (lookDir * 450), { ignore = self })
        if res and res.hitObject then
            targetObj = res.hitObject
            return
        end
        -- 2. Downward angled ray for floor chests, crates, urns, corpses
        local downDir = (lookDir - util.vector3(0, 0, 0.5)):normalize()
        local resDown = nearby.castRay(eyePos, eyePos + (downDir * 450), { ignore = self })
        if resDown and resDown.hitObject then
            targetObj = resDown.hitObject
            return
        end
        -- 3. Waist-level ray
        local waistPos = self.position + util.vector3(0, 0, 50)
        local resWaist = nearby.castRay(waistPos, waistPos + (downDir * 350), { ignore = self })
        if resWaist and resWaist.hitObject then
            targetObj = resWaist.hitObject
            return
        end
    end)
    return targetObj
end

function serialize.performEyeRaycast()
    local ok, res = pcall(function()
        local eyePos = self.position + util.vector3(0, 0, 120)
        local lookDir = self.rotation:apply(util.vector3(0, 1, 0))
        local rayEnd  = eyePos + (lookDir * 800)

        local result = nearby.castRay(eyePos, rayEnd, { ignore = self })
        if result and result.hitObject and result.hitObject.type == types.NPC then
            return result.hitObject
        end

        local bestActor = nil
        local bestDist  = 999999
        for _, actor in ipairs(nearby.actors) do
            if actor ~= self and actor.type == types.NPC then
                local toActor = (actor.position - self.position)
                local dist    = toActor:length()
                if dist <= 500 then
                    local dirTo = toActor:normalize()
                    local dot   = dirTo:dot(lookDir)
                    if dot > 0.5 and dist < bestDist then
                        bestDist  = dist
                        bestActor = actor
                    end
                end
            end
        end
        return bestActor
    end)
    if ok then return res end
    return nil
end

serialize.getRaycastNPC = serialize.performEyeRaycast

function serialize.getPlayerEquipment()
    local equipped = {}
    pcall(function()
        local getEq = types.Actor.getEquipment or types.Actor.equipment
        if getEq then
            local eq = getEq(self)
            if eq then
                for slot, item in pairs(eq) do
                    if item and item.recordId then
                        local recName = item.recordId
                        pcall(function()
                            if item.type and item.type.record then
                                local r = item.type.record(item)
                                if r and r.name then recName = r.name end
                            end
                        end)
                        table.insert(equipped, { id = item.recordId, name = recName })
                    end
                end
            end
        end
    end)
    return equipped
end

function serialize.getAllInventoryItems()
    return serialize.getActorInventory(self)
end

function serialize.getPlayerInventory()
    local fullList = serialize.getAllInventoryItems()
    local capped = {}
    for i = 1, math.min(#fullList, 25) do
        table.insert(capped, fullList[i])
    end
    return capped
end

-- ---------------------------------------------------------------------------
-- Landmass awareness: region, grid, weather, door exits, last exterior visited
-- (the Python daemon turns this into Vvardenfell / Solstheim / mainland /
-- Skyrim / Cyrodiil context via landmass.py)
-- ---------------------------------------------------------------------------
local lastExterior = nil

function serialize.getLastExterior()
    return lastExterior
end

function serialize.setLastExterior(t)
    if type(t) == "table" then lastExterior = t end
end

-- Cheap: remember the exterior cell the player is standing in.
function serialize.noteExterior()
    pcall(function()
        local cell = self.cell
        if cell and cell.isExterior then
            local r = cell.region
            if r == "" then r = nil end
            local nm = cell.name
            if nm == "" then nm = nil end
            lastExterior = { region = r, grid_x = cell.gridX, grid_y = cell.gridY, cell = nm }
        end
    end)
end

local function currentWeatherName(cell)
    local name = nil
    pcall(function()
        if core.weather and core.weather.getCurrent then
            local w = core.weather.getCurrent(cell)
            if w then name = w.name or w.recordId end
        end
    end)
    if name == "" then name = nil end
    return name
end

function serialize.getLocationData()
    local loc = {}
    local cell = self.cell
    if not cell then return loc end
    pcall(function()
        if cell.name and cell.name ~= "" then loc.cell = cell.name end
        loc.is_exterior = cell.isExterior and true or false
        if cell.hasTag then
            local okQ, q = pcall(function() return cell:hasTag("QuasiExterior") end)
            if okQ and q then loc.is_quasi_exterior = true end
        end
        if cell.region and cell.region ~= "" then loc.region = cell.region end
        if cell.worldSpaceId and cell.worldSpaceId ~= "" then loc.worldspace = cell.worldSpaceId end
        if cell.isExterior then
            loc.grid_x = cell.gridX
            loc.grid_y = cell.gridY
        end
    end)
    loc.weather = currentWeatherName(cell)

    if loc.is_exterior then
        serialize.noteExterior()
    else
        -- Teleport doors in this interior: where do they lead? Exterior exits first.
        local outside, inside = {}, {}
        pcall(function()
            if not nearby.doors then return end
            for _, door in ipairs(nearby.doors) do
                if #outside >= 3 and #inside >= 3 then break end
                local okT, isTp = pcall(types.Door.isTeleport, door)
                if okT and isTp then
                    local okC, dc = pcall(types.Door.destCell, door)
                    if okC and dc then
                        local e = {}
                        pcall(function()
                            if dc.isExterior then
                                e.grid_x = dc.gridX
                                e.grid_y = dc.gridY
                                if dc.region and dc.region ~= "" then e.region = dc.region end
                            end
                            if dc.name and dc.name ~= "" then e.cell = dc.name end
                        end)
                        if e.grid_x ~= nil and #outside < 3 then
                            table.insert(outside, e)
                        elseif e.grid_x == nil and e.cell and #inside < 3 then
                            table.insert(inside, e)
                        end
                    end
                end
            end
        end)
        local exits = {}
        for _, e in ipairs(outside) do table.insert(exits, e) end
        for _, e in ipairs(inside) do table.insert(exits, e) end
        if #exits > 0 then loc.exits = exits end
        if lastExterior then
            loc.last_ext_region = lastExterior.region
            loc.last_ext_grid_x = lastExterior.grid_x
            loc.last_ext_grid_y = lastExterior.grid_y
            loc.last_ext_cell   = lastExterior.cell
        end
    end
    return loc
end

local function currentStance()
    local state = nil
    pcall(function()
        local stance = types.Actor.getStance(self)
        if stance == types.Actor.STANCE.Weapon then
            state = "weapon_drawn"
        elseif stance == types.Actor.STANCE.Spell then
            state = "spell_readied"
        elseif stance == types.Actor.STANCE.Nothing then
            state = "sheathed"
        end
    end)
    return state
end

function serialize.getPlayerDataFull()
    local baseData = serialize.getPlayerData()
    local cellName = "Unknown Cell"
    pcall(function()
        if self.cell then
            cellName = self.cell.name
            if not cellName or cellName == "" then
                cellName = string.format("Cell (%d, %d)", self.cell.gridX or 0, self.cell.gridY or 0)
            end
        end
    end)

    local health = { current = 100, base = 100 }
    local magicka = { current = 100, base = 100 }
    local fatigue = { current = 100, base = 100 }
    local attrs = {}
    local skills = {}

    pcall(function()
        if types.Actor.stats then
            local dyn = types.Actor.stats.dynamic
            if dyn then
                if dyn.health then
                    local h = dyn.health(self)
                    health = { current = math.floor(h.current or 100), base = math.floor(h.base or 100) }
                end
                if dyn.magicka then
                    local m = dyn.magicka(self)
                    magicka = { current = math.floor(m.current or 100), base = math.floor(m.base or 100) }
                end
                if dyn.fatigue then
                    local f = dyn.fatigue(self)
                    fatigue = { current = math.floor(f.current or 100), base = math.floor(f.base or 100) }
                end
            end
            local att = types.Actor.stats.attributes
            if att then
                local attrList = { "strength", "intelligence", "willpower", "agility", "speed", "endurance", "personality", "luck" }
                for _, a in ipairs(attrList) do
                    if att[a] then
                        local stat = att[a](self)
                        attrs[a:sub(1,1):upper() .. a:sub(2)] = math.floor(stat.modified or stat.current or 50)
                    end
                end
            end
            local sk = types.NPC.stats and types.NPC.stats.skills
            if sk then
                local skillList = {
                    "block", "armorer", "mediumarmor", "heavyarmor", "bluntweapon", "longblade", "axe", "spear", "athletics",
                    "enchant", "destruction", "alteration", "illusion", "conjuration", "mysticism", "restoration", "alchemy", "unarmored",
                    "security", "sneak", "acrobatics", "lightarmor", "shortblade", "marksman", "mercantile", "speechcraft", "handtohand"
                }
                for _, s in ipairs(skillList) do
                    pcall(function()
                        if sk[s] then
                            local stat = sk[s](self)
                            local val = math.floor(stat.modified or stat.base or stat.current or 15)
                            local prettyName = s:sub(1,1):upper() .. s:sub(2)
                            skills[prettyName] = val
                        end
                    end)
                end
            end
        end
    end)

    local powers, passives, spells = serialize.getActorMagic(self)

    return {
        name              = baseData.name,
        race              = baseData.race,
        gender            = baseData.gender,
        class             = baseData.class,
        level             = baseData.level,
        cell              = cellName,
        location          = serialize.getLocationData(),
        combat_stance     = currentStance(),
        health            = health,
        magicka           = magicka,
        fatigue           = fatigue,
        attributes        = attrs,
        skills            = skills,
        powers            = powers,
        passive_abilities = passives,
        known_spells      = spells,
        equipped_gear     = serialize.getPlayerEquipment(),
        inventory         = serialize.getPlayerInventory()
    }
end

function serialize.getNearbyEntities()
    local entities = {}
    local pPos = self.position
    local pCell = self.cell

    local function isInPlayerCell(ref)
        if not ref then return false end
        local dist = (ref.position - pPos):length()
        if pCell and not pCell.isExterior then
            local ok, c = pcall(function() return ref.cell end)
            if ok and c then
                if c.name and pCell.name and c.name ~= "" and pCell.name ~= "" then
                    return c.name == pCell.name
                end
                if c.id and pCell.id then
                    return c.id == pCell.id
                end
                return c == pCell
            end
            return dist <= 5000
        else
            -- In exterior, either match grid coordinates, matching cell name, or within cell radius (8192 units)
            local ok, c = pcall(function() return ref.cell end)
            if ok and c then
                if c.gridX and pCell and pCell.gridX and c.gridX == pCell.gridX and c.gridY == pCell.gridY then
                    return true
                end
                if c.name and pCell and pCell.name and c.name ~= "" and c.name == pCell.name then
                    return true
                end
            end
            return dist <= 8192
        end
    end

    local seenRefs = {}
    local function processRef(ref, fallbackType)
        if not ref or ref == self then return end
        if seenRefs[ref] then return end
        seenRefs[ref] = true
        if ref.id then seenRefs[ref.id] = true end

        local isPlr = false
        pcall(function()
            if types.Player.objectIsInstance(ref) then isPlr = true end
        end)
        if isPlr then return end

        local recId = (ref.recordId or ""):lower()
        if recId == "player" then return end

        pcall(function()
            if not isInPlayerCell(ref) then return end
            local dist = math.floor((ref.position - pPos):length())

            local recName = ref.recordId or "Unknown"
            local typeStr = fallbackType or "Object"
            local actorStats = nil

            if ref.type == types.NPC or ref.type == types.Creature then
                actorStats = {}
                pcall(function()
                    if types.Actor.stats and types.Actor.stats.dynamic then
                        local hp  = types.Actor.stats.dynamic.health(ref)
                        local mag = types.Actor.stats.dynamic.magicka(ref)
                        local fat = types.Actor.stats.dynamic.fatigue(ref)
                        if hp then actorStats.health = { current = math.floor(hp.current or 0), max = math.floor(hp.base or 0) } end
                        if mag then actorStats.magicka = { current = math.floor(mag.current or 0), max = math.floor(mag.base or 0) } end
                        if fat then actorStats.fatigue = { current = math.floor(fat.current or 0), max = math.floor(fat.base or 0) } end
                    end
                end)
            end

            if ref.type == types.NPC then
                local isDead = false
                pcall(function()
                    if types.Actor.stats and types.Actor.stats.dynamic and types.Actor.stats.dynamic.health then
                        if types.Actor.stats.dynamic.health(ref).current <= 0 then isDead = true end
                    end
                end)
                typeStr = isDead and "Dead NPC (Corpse)" or "NPC"
                pcall(function()
                    local r = types.NPC.record(ref)
                    if r then
                        if r.name then recName = r.name end
                        if actorStats then
                            actorStats.race   = r.race or "Unknown"
                            actorStats.gender = r.isFemale and "female" or "male"
                            actorStats.class  = r.class or "Commoner"
                            actorStats.level  = r.level or 1
                        end
                    end
                    if actorStats then actorStats.disposition = serialize.getNPCDisposition(ref) end
                end)
            elseif ref.type == types.Creature then
                local isDead = false
                pcall(function()
                    if types.Actor.stats and types.Actor.stats.dynamic and types.Actor.stats.dynamic.health then
                        if types.Actor.stats.dynamic.health(ref).current <= 0 then isDead = true end
                    end
                end)
                typeStr = isDead and "Dead Creature (Corpse)" or "Creature"
                pcall(function()
                    local r = types.Creature.record(ref)
                    if r and r.name then recName = r.name end
                end)
            elseif ref.type == types.Weapon then typeStr = "Weapon"
            elseif ref.type == types.Armor then typeStr = "Armor"
            elseif ref.type == types.Clothing then typeStr = "Clothing"
            elseif ref.type == types.Container then typeStr = "Container"
            elseif ref.type == types.Door then typeStr = "Door"
            elseif ref.type == types.Potion or ref.type == types.Book or ref.type == types.Ingredient then typeStr = "Item"
            elseif ref.type == types.Activator then typeStr = "Activator"
            elseif ref.type == types.Static then typeStr = "Static"
            else
                pcall(function()
                    if ref.type and ref.type.record then
                        local r = ref.type.record(ref)
                        if r and r.name then recName = r.name end
                    end
                end)
            end

            if not recName or recName == "" then return end

            local entry = {
                id = ref.recordId or "unknown",
                name = recName,
                type = typeStr,
                x = math.floor(ref.position.x),
                y = math.floor(ref.position.y),
                z = math.floor(ref.position.z),
                distance = dist
            }
            if actorStats then entry.stats = actorStats end
            table.insert(entities, entry)
        end)
    end

    pcall(function()
        if nearby.actors then
            for _, actor in ipairs(nearby.actors) do processRef(actor, "Actor") end
        end
        if nearby.items then
            for _, item in ipairs(nearby.items) do processRef(item, "Item") end
        end
        if nearby.containers then
            for _, container in ipairs(nearby.containers) do processRef(container, "Container") end
        end
        if nearby.doors then
            for _, door in ipairs(nearby.doors) do processRef(door, "Door") end
        end
        if nearby.activators then
            for _, act in ipairs(nearby.activators) do processRef(act, "Activator") end
        end
    end)

    -- Static Vision Raycasting: detect architecture, furniture, and landmarks in the cell
    pcall(function()
        local eyePos = self.position + util.vector3(0, 0, 120)
        local baseRot = self.rotation
        local fwd = baseRot:apply(util.vector3(0, 1, 0))
        local right = baseRot:apply(util.vector3(1, 0, 0))
        local up = baseRot:apply(util.vector3(0, 0, 1))

        local angles = {
            fwd,                                   -- center gaze
            (fwd + right * 0.35):normalize(),      -- right
            (fwd - right * 0.35):normalize(),      -- left
            (fwd + right * 0.75):normalize(),      -- far right
            (fwd - right * 0.75):normalize(),      -- far left
            (fwd - up * 0.35):normalize(),         -- downward (ground / desks / tables)
            (fwd + up * 0.35):normalize(),         -- upward (ceilings / roofs / signposts)
            (fwd - right * 0.35 - up * 0.3):normalize(),
            (fwd + right * 0.35 - up * 0.3):normalize()
        }

        for _, dir in ipairs(angles) do
            local rayEnd = eyePos + (dir * 2500)
            local res = nearby.castRay(eyePos, rayEnd, { ignore = self, collisionType = nearby.COLLISION_TYPE.World })
            if res and res.hitObject then
                processRef(res.hitObject, "Static")
            end
        end
    end)

    table.sort(entities, function(a, b) return a.distance < b.distance end)
    return entities
end

return serialize
