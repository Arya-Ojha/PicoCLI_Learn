# Context Status Bar Implementation Summary

## Overview
Added a context status bar widget to the PicoCLI TUI that displays:
- Provider name (e.g., "OpenRouter")
- Model name (e.g., "nvidia/nemotron-3.5-lightning:free")
- Thinking indicator (shown when the model is reasoning)
- Context window progress bar (fills as context fills, color-coded by usage level)
- Current token count (formatted with commas, e.g., "38,932")

## Files Modified

### 1. `packages/pico_core/src/pico_core/fsm.py`
- Added public `estimate_tokens()` method to `AgentLoop` class
- This exposes the private `_estimate_tokens()` functionality

### 2. `packages/pico_sdk/src/pico_sdk/session.py`
- Added `provider_name` property to `AgentSession` class
  - Extracts provider name from the provider class name
  - Returns "OpenRouter" for OpenRouterProvider
- Added `context_window` property to `AgentSession` class
  - Returns the context window size from the agent loop
- Added `estimate_tokens()` method to `AgentSession` class
  - Returns current estimated token count from the agent loop

### 3. `packages/pico_tui/src/pico_tui/status_bar.py` (NEW FILE)
- Created `ContextStatusBar` widget extending Textual's `Static`
- Features:
  - Displays provider | model information
  - Shows "thinking" indicator in yellow italic when active
  - Renders a 20-character progress bar for context window usage
  - Color-codes the progress bar:
    - Green: 0-50% usage (░ character)
    - Yellow: 50-70% usage (▒ character)
    - Orange: 70-90% usage (▓ character)
    - Red: 90-100% usage (█ character)
  - Shows token count with comma formatting in cyan
- Methods:
  - `on_mount()`: Renders initial display after widget mount
  - `update_info()`: Updates all status information
  - `set_thinking()`: Updates thinking state
  - `_update_display()`: Renders the status bar with Rich Text

### 4. `packages/pico_tui/src/pico_tui/app.py`
- Imported `ContextStatusBar` widget
- Added CSS styling for `#status-bar`:
  - Docked to bottom
  - Height: 1 line
  - Background: $surface color
  - Padding: 0 1
- Added `ContextStatusBar` to `compose()` method after Input widget
- Added `_update_status_bar()` method to update the status bar with current session info
- Updated `on_mount()` to call `_update_status_bar()` on initialization
- Updated `_run_prompt()` to call `_update_status_bar()` when streaming starts
- Updated `_stream_worker()` to call `_update_status_bar()` when streaming completes

### 5. `tests/test_status_bar.py` (NEW FILE)
- Added 3 tests for the ContextStatusBar widget:
  - `test_status_bar_initialization`: Verifies default values
  - `test_status_bar_stores_info`: Verifies info storage
  - `test_status_bar_set_thinking`: Verifies thinking state updates

## Test Results
All 92 tests pass successfully, including:
- 19 existing TUI tests
- 3 new status bar tests
- All other existing tests remain passing

## Usage
The status bar automatically appears below the input bar in the TUI and updates:
- On application startup (shows initial provider, model, and 0 tokens)
- When a prompt is submitted (shows "thinking" indicator)
- When streaming completes (updates token count and hides "thinking")
- When the model changes via `/model` command

The status bar provides real-time visibility into:
- Which AI provider and model is being used
- Whether the model is currently thinking/reasoning
- How much of the context window is being used
- The exact token count in the current context