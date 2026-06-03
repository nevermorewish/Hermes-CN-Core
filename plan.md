# Plan: Add Custom base_url Support to Anthropic Model Flow

## 1. Context / Where the Code Lives

### Anthropic-specific provider/model flow
- **File:** `hermes_cli/main.py`
- **Function:** `_model_flow_anthropic()` — lines **5968–6118**
- **What it does:**
  - Handles auth method choice (OAuth vs API key)
  - Prompts for model name when the provider model list is empty
  - Saves `model.provider = "anthropic"` in config

### Shared interactive model picker
- **File:** `hermes_cli/auth.py`
- **Function:** `_prompt_model_selection()` — lines **6050–6220**
- **What it does:**
  - Displays `"Select default model:"` — line **6114**
  - Displays `"Enter model name:"` — lines **6177** and **6212**
  - Uses `simple_term_menu` arrow-key menu when available, falls back to numbered list

### Call chain for `hermes model` → Anthropic
1. `cmd_model()` (`main.py:2117`) calls `select_provider_and_model()`
2. When user picks **Anthropic**, it dispatches to `_model_flow_anthropic()` (`main.py:5968`)
3. That calls `_prompt_model_selection()` (`auth.py:~6050`) for the actual model list UI

### Runtime base_url resolution (already supports it)
- **File:** `hermes_cli/runtime_provider.py`
- **Lines:** **1470–1477** and **1067–1072**
- The runtime already reads `model_cfg.get("base_url")` when `provider == "anthropic"` and uses it instead of the hardcoded `https://api.anthropic.com`.

## 2. Problem

`_model_flow_anthropic` explicitly **removes** `base_url` from config before saving:

```python
# main.py:6099-6118 (current)
if selected:
    _save_model_choice(selected)

    # Update config with provider — clear base_url since
    # resolve_runtime_provider() always hardcodes Anthropic's URL.
    # Leaving a stale base_url in config can contaminate other
    # providers if the user switches without running 'hermes model'.
    cfg = load_config()
    model = cfg.get("model")
    if not isinstance(model, dict):
        model = {"default": model} if model else {}
        cfg["model"] = model
    model["provider"] = "anthropic"
    model.pop("base_url", None)   # <-- BLOCKER
    save_config(cfg)
    deactivate_provider()

    print(f"Default model set to: {selected} (via Anthropic)")
```

## 3. Proposed Change

Replace the config-save block at the end of `_model_flow_anthropic` (`main.py:6099-6118`) with:

```python
    if selected:
        _save_model_choice(selected)

        cfg = load_config()
        model = cfg.get("model")
        if not isinstance(model, dict):
            model = {"default": model} if model else {}
            cfg["model"] = model
        model["provider"] = "anthropic"

        # Optional custom base_url
        current_base_url = model.get("base_url", "")
        print()
        prompt = f"Custom base URL [{current_base_url or 'https://api.anthropic.com'}]: "
        try:
            custom_url = input(prompt).strip().rstrip("/")
        except (KeyboardInterrupt, EOFError):
            custom_url = ""
        if custom_url:
            model["base_url"] = custom_url
        else:
            # User hit Enter with no input — keep existing if present,
            # otherwise clear stale value so it falls back to the default.
            if not current_base_url:
                model.pop("base_url", None)

        save_config(cfg)
        deactivate_provider()

        print(f"Default model set to: {selected} (via Anthropic)")
```

## 4. What This Achieves

1. **Prompts** for an optional custom base URL after model selection.
2. **Pre-fills** with the current `model.base_url` if one already exists.
3. **Saves** the URL if the user enters one.
4. **Preserves fallback behavior:** if user leaves it blank and no prior URL exists, pops it so the runtime falls back to `https://api.anthropic.com`.
5. **No runtime changes needed:** `runtime_provider.py` already reads `model.base_url` for the `anthropic` provider.

## 5. Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `hermes_cli/main.py` | 6099–6118 | Replace config-save block in `_model_flow_anthropic` to prompt for optional `base_url` instead of unconditionally popping it |
