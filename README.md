# Actuator Control System

Personal notes for RevPi actuator control scripts.

## Files Overview

### `task_control.py` - Modern Async Control
**Minimal asyncio-based control with instant cancellation**

- **Main goal**: Move to position (cancellable anytime) + set speed limit
- **Key feature**: True async - can cancel moves instantly while they're happening
- **Best for**: Interactive control, precise movements

### `minimized_control.py` - Original Blocking Control  
**Traditional blocking control with debug output**

- **Main goal**: Position control with detailed debugging
- **Key feature**: Verbose debug prints, blocking movement
- **Best for**: Testing, debugging, understanding system behavior

---


### Commands
| Command | Example | Description |
|---------|---------|-------------|
| `<position>` | `50` | Move to 50mm (blocking) |
| `speed <val>` | `speed 200` | Set max speed (0-1000) |
| `cancel` | `cancel` | **Stop immediately** at current position |
| `pos` | `pos` | Show current position |
| `quit` | `quit` | Exit program |

### Key Features
- **Instant cancellation**: Type `cancel` during any movement → stops immediately
- **Speed control**: `speed 100` = slow, `speed 500` = fast
- **Position deadband**: No hunting/jerking when at target (±0.5mm)
- **Async**: Commands respond instantly, no blocking

### How Cancellation Works
```
> 100          # Start moving to 100mm
> cancel       # IMMEDIATELY stops at current position (e.g., 67mm)
> 50           # Now moves to 50mm from where it stopped
```

---


### Features
- **DEMO_MODE = 1**: Automatic movement sequence
- **DEMO_MODE = 2**: Interactive CLI (enter target positions)
- **Debug output**: Shows position, error, PWM, direction, raw values
- **Blocking**: Must wait for movement to complete

### Interactive Mode
```
Target (30-146 mm): 50
[debug] Pos: 45.23mm | Target: 50.0mm | Error: +4.8mm | PID: +96.5 | PWM: 96% | Dir:EXT | Raw: 2847
Target (30-146 mm): 80
```

---

## Technical Details

### Both Files Share
- **PID Controller**: Kp=20, Ki=0, Kd=0.5
- **PWM Range**: 0-1000 (but limited by `output_limits`)
- **Stroke**: 146mm total travel
- **Deadband**: 10 PWM units (prevents tiny movements)
- **Calibration**: Uses `calibration.py` for raw→mm conversion

### Key Differences

| Feature | task_control.py | chatgpt_control.py |
|---------|-----------------|-------------------|
| **Cancellation** | ✅ Instant (async) | ❌ Must wait |
| **Debug output** | ❌ Minimal | ✅ Verbose |
| **Speed ramping** | ✅ Gentle ramp-down | ✅ Gentle ramp-down |
| **Position deadband** | ✅ 0.5mm (no hunting) | ❌ Will hunt |
| **Emergency stop** | ✅ Sets limits to (0,0) | ✅ Sets limits to (0,0) |

---

## Personal Usage Notes

### When to Use Each

**Use `task_control.py` for:**
- Normal operation
- Need to stop movements quickly
- Interactive control sessions
- Quiet operation (no hunting)

**Use `chatgpt_control.py` for:**
- Debugging issues
- Understanding what's happening
- Testing PID parameters
- Demo/showing others

### Common Commands I Use
```bash
# Quick position check
> pos

# Move and maybe cancel
> 80
> cancel    # if I change my mind

# Slow it down for precision
> speed 150
> 75

# Back to normal speed
> speed 500
```

### Troubleshooting
- **Won't move after cancel**: This is normal - `cancel` locks position until next `move`
- **Hunting/jerking**: Use `task_control.py` (has position deadband)
- **Too slow**: Increase speed with `speed <higher_number>`
- **Too fast**: Decrease speed with `speed <lower_number>`

---

## Code Architecture (task_control.py)

### Core Functions
- `move(target)` - Sets PID setpoint, restores speed if needed
- `cancel_move()` - Saves speed limits, sets to (0,0) for instant stop
- `set_speed_limit(pwm)` - Changes max PWM with gentle ramp-down
- `get_position()` - Raw ADC → calibrated mm position

### Async Magic
- `_control_loop()` - Runs PID continuously in background
- `get_user_input()` - Non-blocking input using executor
- `main()` - Command parser + event loop

### Smart Features
- **Auto-restore speed**: When you `move()` after `cancel()`, speed limits auto-restore
- **Position deadband**: Within 0.5mm of target → no PID correction (quiet)
- **PWM deadband**: PID output <10 → no PWM (prevents tiny movements)
