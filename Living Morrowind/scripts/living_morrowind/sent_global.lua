-- Living Morrowind Global Engine Handler for OpenMW 0.51
local world = require('openmw.world')
local types = require('openmw.types')

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

local function isProtectedQuestItem(recId)
    if not recId or recId == "" then return false end
    local lower = recId:lower():match("^%s*(.-)%s*$")
    if PROTECTED_QUEST_ITEMS[lower] then return true end
    if lower:sub(1, 6) == "bk_a1_" or lower:sub(1, 6) == "bk_a2_" then return true end
    if lower:sub(1, 6) == "index_" or lower:sub(1, 11) == "key_chargen" then return true end
    return false
end

return {
    eventHandlers = {
        LivingMW_GiveItem = function(data)
            local target = data.target or (world.players and world.players[1])
            local items  = data.items
            if not target or not items then
                print("[LIVINGMW_GLOBAL ERROR] LivingMW_GiveItem: missing target or items")
                return
            end
            local targetInv = nil
            pcall(function() targetInv = types.Actor.inventory(target) end)
            if not targetInv then
                print("[LIVINGMW_GLOBAL ERROR] LivingMW_GiveItem: could not resolve target inventory")
                return
            end

            for _, it in ipairs(items) do
                local recId = (it.id or ""):lower()
                local count = tonumber(it.count) or 1
                if isProtectedQuestItem(recId) then
                    print(string.format("[LIVINGMW_GLOBAL SECURITY] Blocked attempt to give/spawn protected quest item/artifact '%s'", recId))
                else
                    local ok, err = pcall(function()
                        local obj = world.createObject(recId, count)
                        obj:moveInto(targetInv)
                        print(string.format("[LIVINGMW_GLOBAL] LivingMW_GiveItem: successfully spawned & gave '%s' (x%d)", recId, count))
                    end)
                    if not ok then
                        print(string.format("[LIVINGMW_GLOBAL ERROR] LivingMW_GiveItem failed for '%s': %s", tostring(recId), tostring(err)))
                    end
                end
            end
        end,

        LivingMW_TakeItem = function(data)
            local source = data.source or (world.players and world.players[1])
            local target = data.target
            local items  = data.items
            if not source or not items then
                print("[LIVINGMW_GLOBAL ERROR] LivingMW_TakeItem: missing source or items")
                return
            end
            local sourceInv = nil
            pcall(function() sourceInv = types.Actor.inventory(source) end)
            if not sourceInv then
                print("[LIVINGMW_GLOBAL ERROR] LivingMW_TakeItem: could not resolve source inventory")
                return
            end
            local targetInv = nil
            if target then
                pcall(function() targetInv = types.Actor.inventory(target) end)
            end

            for _, it in ipairs(items) do
                local recId = (it.id or ""):lower()
                local count = tonumber(it.count) or 1
                if isProtectedQuestItem(recId) then
                    print(string.format("[LIVINGMW_GLOBAL SECURITY] Blocked attempt to take protected quest item/document '%s' from player!", recId))
                else
                    local ok, err = pcall(function()
                        local found = sourceInv:find(recId)
                        if not found then
                            print(string.format("[LIVINGMW_GLOBAL WARNING] LivingMW_TakeItem: item '%s' not found in source inventory", recId))
                            return
                        end

                        local currentCount = found.count or 1
                        if currentCount <= count then
                            if targetInv then
                                found:moveInto(targetInv)
                            else
                                found:remove()
                            end
                            print(string.format("[LIVINGMW_GLOBAL] LivingMW_TakeItem: moved full stack (%d) of '%s'", currentCount, recId))
                        else
                            local splitItem = found:split(count)
                            if targetInv then
                                splitItem:moveInto(targetInv)
                            else
                                splitItem:remove()
                            end
                            print(string.format("[LIVINGMW_GLOBAL] LivingMW_TakeItem: split & moved %d of '%s'", count, recId))
                        end
                    end)
                    if not ok then
                        print(string.format("[LIVINGMW_GLOBAL ERROR] LivingMW_TakeItem failed for '%s': %s", tostring(recId), tostring(err)))
                    end
                end
            end
        end,
    }
}

