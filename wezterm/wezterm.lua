local wezterm = require 'wezterm'
local config = wezterm.config_builder()

-- Open straight into WSL Ubuntu
config.default_domain = 'WSL:Ubuntu'

-- Text
config.font = wezterm.font('JetBrains Mono', { weight = 'Medium' })
config.font_size = 10.5
config.line_height = 1.2
config.freetype_load_target = 'Light'
config.freetype_render_target = 'HorizontalLcd'

-- Looks
-- Palettes. The mode line below is flipped by ~/.claude/scripts/term-theme
-- (WSL), which the /light and /dark skills call. Edit colours here.
local palettes = {
  -- Dark: pine green with bone text
  dark = {
    foreground = '#EDE6D6',
    background = '#1B2A20',
    cursor_bg = '#F4EFE2',
    cursor_fg = '#1B2A20',
    cursor_border = '#F4EFE2',
    selection_bg = '#34493A',
    selection_fg = '#F7F4EC',
    split = '#2E4034',
    ansi    = { '#2A3B2F', '#E07A5F', '#B5D86B', '#D4B483', '#8FC9B0', '#D9A989', '#BFE3CE', '#EDE6D6' },
    brights = { '#8E9B88', '#EE937A', '#C9EA7E', '#E3C898', '#A8DCC5', '#E6BBA0', '#D4EEDD', '#F7F4EC' },
  },
  -- Light: warm bone paper with dark ink, forest green and tan accents
  light = {
    foreground = '#2B2F28',
    background = '#DCD6C5',
    cursor_bg = '#2B2F28',
    cursor_fg = '#DCD6C5',
    cursor_border = '#2B2F28',
    selection_bg = '#C3CFB0',
    selection_fg = '#1E2A20',
    split = '#D8D2C2',
    -- white/bright-white are dark greys here: apps draw muted text with them
    ansi    = { '#2B2F28', '#B5452F', '#4F7D2A', '#9A7B2E', '#2F6E5E', '#8A5A3C', '#3C7F6A', '#4A5046' },
    brights = { '#5F665A', '#C85A40', '#5E9433', '#B08C3A', '#3B8372', '#A06C4A', '#4A9682', '#2B2F28' },
  },
}
local mode = 'dark' -- term-theme sets this
config.colors = palettes[mode]
config.window_background_opacity = 1.0
config.window_padding = { left = 12, right = 12, top = 8, bottom = 8 }
config.hide_tab_bar_if_only_one_tab = true
config.use_fancy_tab_bar = false
config.window_decorations = 'TITLE | RESIZE'

-- Behaviour
config.scrollback_lines = 10000
config.audible_bell = 'Disabled'

-- Windows habits: Ctrl+V pastes text.
-- Ctrl+Shift+V sends the raw ^V keystroke to the pane instead of pasting, so
-- Claude Code can pull a screenshot off the Windows clipboard (it only sees an
-- image when the terminal lets the key through; WezTerm's paste drops images).
config.keys = {
  { key = 'v', mods = 'CTRL', action = wezterm.action.PasteFrom 'Clipboard' },
  { key = 'V', mods = 'CTRL', action = wezterm.action.PasteFrom 'Clipboard' },
  { key = 'v', mods = 'CTRL|SHIFT', action = wezterm.action.SendKey { key = 'v', mods = 'CTRL' } },
  { key = 'V', mods = 'CTRL|SHIFT', action = wezterm.action.SendKey { key = 'v', mods = 'CTRL' } },
  -- Ctrl+C copies when text is selected, otherwise interrupts, like Windows Terminal.
  { key = 'c', mods = 'CTRL', action = wezterm.action_callback(function(window, pane)
      local sel = window:get_selection_text_for_pane(pane)
      if sel and #sel > 0 then
        window:perform_action(wezterm.action.CopyTo 'Clipboard', pane)
        window:perform_action(wezterm.action.ClearSelection, pane)
      else
        window:perform_action(wezterm.action.SendKey { key = 'c', mods = 'CTRL' }, pane)
      end
    end) },
}

-- Selecting with the mouse only highlights; it no longer overwrites the clipboard
-- (WezTerm's default copies on release, which was replacing screenshots with
-- terminal text when clicking back into a pane). Ctrl+C or Ctrl+Shift+C copies.
-- Mouse release never writes the clipboard: on Windows WezTerm has no separate
-- primary selection, so even CompleteSelection 'PrimarySelection' overwrote a
-- snipped screenshot with terminal text. Ctrl+C (above) is the only copy.
config.mouse_bindings = {
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'NONE', action = wezterm.action.Nop },
  { event = { Up = { streak = 2, button = 'Left' } }, mods = 'NONE', action = wezterm.action.Nop },
  { event = { Up = { streak = 3, button = 'Left' } }, mods = 'NONE', action = wezterm.action.Nop },
  -- Shift/Alt releases default to copying the selection (Shift is also the
  -- bypass for Herdr's mouse capture), so they overwrote the clipboard too.
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'SHIFT', action = wezterm.action.Nop },
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'ALT', action = wezterm.action.Nop },
  { event = { Up = { streak = 1, button = 'Left' } }, mods = 'SHIFT|ALT', action = wezterm.action.Nop },
}

-- Ctrl+click (or Ctrl+Shift+click) opens the link under the cursor. WezTerm
-- ships no Ctrl+click binding, and Herdr captures the mouse, so without the
-- mouse_reporting = true copies the click went to Herdr instead. The Down Nops
-- stop Herdr seeing the press, so it doesn't move focus or start a selection.
for _, mods in ipairs { 'CTRL', 'CTRL|SHIFT' } do
  for _, reporting in ipairs { false, true } do
    table.insert(config.mouse_bindings, {
      event = { Down = { streak = 1, button = 'Left' } }, mods = mods,
      mouse_reporting = reporting, action = wezterm.action.Nop,
    })
    table.insert(config.mouse_bindings, {
      event = { Up = { streak = 1, button = 'Left' } }, mods = mods,
      mouse_reporting = reporting, action = wezterm.action.OpenLinkAtMouseCursor,
    })
  end
end

return config
