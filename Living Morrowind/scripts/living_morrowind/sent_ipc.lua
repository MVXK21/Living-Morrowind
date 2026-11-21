-- Living Morrowind IPC & Communication Layer for OpenMW 0.51
local vfs     = require('openmw.vfs')
local timeAux = require('openmw_aux.time')

local RESPONSE_VFS = "scripts/living_morrowind/ai_response.json"

local ipc = {}

function ipc.escapeJSON(str)
    if not str then return "" end
    return str:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', ' '):gsub('\r', '')
end

function ipc.toJSON(val)
    local t = type(val)
    if t == "nil" then
        return "null"
    elseif t == "boolean" then
        return tostring(val)
    elseif t == "number" then
        return tostring(val)
    elseif t == "string" then
        return '"' .. ipc.escapeJSON(val) .. '"'
    elseif t == "table" then
        local isArray = true
        local n = #val
        for k in pairs(val) do
            if type(k) ~= "number" or k < 1 or k > n or math.floor(k) ~= k then
                isArray = false
                break
            end
        end
        if isArray then
            local parts = {}
            for i = 1, n do
                table.insert(parts, ipc.toJSON(val[i]))
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(val) do
                if type(k) == "string" then
                    table.insert(parts, '"' .. ipc.escapeJSON(k) .. '":' .. ipc.toJSON(v))
                end
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

function ipc.extractReply(json)
    if not json then return nil end
    local s, e = json:find('"reply"%s*:%s*"')
    if not s then
        s, e = json:find('"description"%s*:%s*"')
    end
    if not s then
        s, e = json:find('"text"%s*:%s*"')
    end
    if not s then return nil end
    local vStart = e + 1
    local vEnd   = vStart
    local len    = #json
    while vEnd <= len do
        local ch = json:sub(vEnd, vEnd)
        if ch == "\\" then vEnd = vEnd + 2
        elseif ch == '"' then break
        else vEnd = vEnd + 1 end
    end
    if vEnd > len then return nil end
    return json:sub(vStart, vEnd - 1)
               :gsub("\\\\","\\"):gsub('\\"','"'):gsub("\\n"," "):gsub("\\r","")
end

function ipc.extractItems(json, key)
    if not json or not key then return nil end
    local pattern = '"' .. key .. '"%s*:%s*%['
    local s, e = json:find(pattern)
    if not s then return nil end
    local closeIdx = json:find('%]', e)
    if not closeIdx then return nil end
    local arrStr = json:sub(e + 1, closeIdx - 1)
    local items = {}
    for itemBlock in arrStr:gmatch('%b{}') do
        local id = itemBlock:match('"id"%s*:%s*"([^"]+)"')
        local count = tonumber(itemBlock:match('"count"%s*:%s*(%d+)')) or 1
        if id then
            table.insert(items, { id = id, count = count })
        end
    end
    if #items > 0 then return items end
    return nil
end

function ipc.extractOfferedItems(json)
    return ipc.extractItems(json, "offered_items")
end

function ipc.extractRequestedItems(json)
    return ipc.extractItems(json, "requested_items")
end


function ipc.readResponseFile()
    local ok, data = pcall(function()
        local f = vfs.open(RESPONSE_VFS)
        if not f then return nil end
        local c = f:read("*all")
        f:close()
        return c
    end)
    if ok and data and #data > 5 then return data end
    return nil
end

function ipc.emit(payload, reqId)
    local rId = tostring(reqId or "")
    if #payload <= 900 then
        print("[LIVINGMW_IPC_REQ] " .. payload)
    else
        local chunkSize = 750
        local totalChunks = math.ceil(#payload / chunkSize)
        for i = 1, totalChunks do
            local startIdx = (i - 1) * chunkSize + 1
            local endIdx = math.min(i * chunkSize, #payload)
            local chunk = payload:sub(startIdx, endIdx)
            print(string.format("[LIVINGMW_IPC_CHUNK:%s:%d:%d] %s", rId, i, totalChunks, chunk))
        end
    end
end

function ipc.sendRequest(payload, reqId, currentReqId, pendingCallback, callback)
    ipc.emit(payload, reqId)
    local startTime = os.time()

    local stopFn
    stopFn = timeAux.runRepeatedly(function()
        local data = ipc.readResponseFile()
        if data then
            if data:find('"reply"') or data:find('"description"') or data:find('"text"') or data:find('"error"') then
                local fileId = data:match('"request_id"%s*:%s*"([^"]+)"') or ""
                if fileId == reqId then
                    if stopFn then stopFn() end
                    callback(data, nil)
                    return
                end
            end
        end
        local elapsed = os.time() - startTime
        if elapsed >= 30 then
            if stopFn then stopFn() end
            local reason = data and ("Response ID mismatch (received ID: " .. tostring(data:match('"request_id"%s*:%s*"([^"]+)"')) .. ", expected: " .. tostring(reqId) .. ")") or "Python daemon not active or openmw.log watcher stalled"
            callback(nil, "IPC Timeout (" .. tostring(elapsed) .. "s): " .. reason)
        end
    end, 0.4, { initialDelay = 0 })
end

return ipc
