--- @since 26.9.1

local snapshot = ya.sync(function()
	return tostring(cx.active.current.cwd)
end)

local function notify(message, level)
	ya.notify { title = "Bookmarks", content = message, level = level or "warn", timeout = 4 }
end

local function marks_dir()
	local root = os.getenv("XDG_STATE_HOME")
	if not root or root == "" then root = os.getenv("HOME") .. "/.local/state" end
	return Url(root .. "/yazi/marks")
end

local function read_mark(file)
	local handle, err = io.open(tostring(file), "rb")
	if not handle then return nil, err end
	local path
	path, err = handle:read("*a")
	handle:close()
	return path, err
end

local function label(path)
	local home = os.getenv("HOME")
	if path == home then return "~" end
	local url = Url(path)
	if not url.parent then return path end
	local parent = tostring(url.parent)
	if parent == home or parent:sub(1, #home + 1) == home .. "/" then
		parent = "~" .. parent:sub(#home + 1)
	end
	-- The native menu clips on the right, so put the directory name first.
	return ui.printable(url.name .. "  " .. parent)
end

local bind = ya.sync(function(state, key, path)
	local rules = km.mgr.rules
	for _, rule in ipairs(state.bindings[key] or {}) do
		rules:remove { id = rule.id }
	end

	local desc = path and label(path) or "Unused"
	-- Native chords capture fast typing before launching the async plugin.
	state.bindings[key] = {
		rules:insert(path and 1 or -1, { on = { "m", key }, run = "plugin marks -- save " .. key, desc = desc }),
	}
	if path then
		table.insert(state.bindings[key], rules:insert(1, {
			on = { "`", key }, run = "plugin marks -- jump " .. key, desc = desc,
		}))
		table.insert(state.bindings[key], rules:insert(1, {
			on = { "m", "-", key }, run = "plugin marks -- delete " .. key, desc = desc,
		}))
	end
end)

return {
	setup = function(state)
		state.bindings = state.bindings or {}
		for _, rule in ipairs(state.cancel_bindings or {}) do
			km.mgr.rules:remove { id = rule.id }
		end
		state.cancel_bindings = {}
		-- Two choices prevent m- from completing early with zero or one mark.
		for _, prefix in ipairs { { "`" }, { "m", "-" } } do
			for _, key in ipairs { "<Esc>", "<C-c>" } do
				local on = { table.unpack(prefix) }
				table.insert(on, key)
				table.insert(state.cancel_bindings, km.mgr.rules:insert(1, {
					on = on, run = "which:dismiss", desc = "Cancel",
				}))
			end
		end
		local keys = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
		local saved = {}
		local dir = marks_dir()
		for i = 1, #keys do
			local key = keys:sub(i, i)
			local path = read_mark(dir:join(tostring(key:byte())))
			if path and path ~= "" then saved[key] = path else bind(key) end
		end
		-- Keep occupied keys visible first, even in a short terminal.
		for i = #keys, 1, -1 do
			local key = keys:sub(i, i)
			if saved[key] then bind(key, saved[key]) end
		end
	end,

	entry = function(_, job)
		local cwd = snapshot()
		local key = job.args[2]
		if not key or not key:match("^[a-zA-Z0-9]$") then return end
		local dir = marks_dir()
		-- Numeric names distinguish a/A even on a case-insensitive filesystem.
		local file = dir:join(tostring(key:byte()))

		if job.args[1] == "save" then
			local ok, err = fs.create("dir_all", dir)
			if not ok then return notify(tostring(err), "error") end
			local tmp
			tmp, err = fs.unique("file", dir:join(".saving"))
			if not tmp then return notify(tostring(err), "error") end
			ok, err = fs.write(tmp, cwd)
			if ok then ok, err = fs.rename(tmp, file) end
			if not ok then
				fs.remove("file", tmp)
				return notify(tostring(err), "error")
			end
			bind(key, cwd)
			notify("Saved " .. key, "info")
		elseif job.args[1] == "delete" then
			local ok, err = fs.remove("file", file)
			if not ok then return notify("Cannot delete bookmark " .. key .. ": " .. tostring(err), "error") end
			bind(key)
			notify("Deleted " .. key, "info")
		elseif job.args[1] == "jump" then
			local path, err = read_mark(file)
			if not path then return notify("Cannot read bookmark " .. key .. ": " .. tostring(err)) end
			if path == "" then return notify("Bookmark " .. key .. " is empty") end
			local target = Url(path)
			local cha
			cha, err = fs.cha(target, true)
			if not cha or not cha.is_dir then
				return notify("Bookmark " .. key .. " is not an accessible directory: " .. tostring(err or path))
			end
			ya.emit("cd", { target })
		end
	end,
}
