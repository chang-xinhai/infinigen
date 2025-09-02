# Temporary Changes - CXH

## 🏗️ Static Assets Integration

1. **Asset Import Setup**
   - Follow instructions in `docs/StaticAssets.md` to modify `infinigen/assets/static_assets`
   - **Known Issue:** Rotation alignment problems
   - **Workaround:** Apply rotation corrections during USD export

## 🏠 Kitchen-Only Generation

### Files Modified

1. **`infinigen_examples/configs_indoor/kitchen_only.gin`** - New config file
2. **`infinigen_examples/constraints/home.py`** - Added `kitchen_only` mode support
3. **`infinigen/core/constraints/example_solver/room/solver.py`** - Fixed crash bug

```python
# Key fix in solver.py
def swap_room(self, state, k):
    valid_targets = [r.target_name for r in state[k].relations if r.value.length > 0]
  
    if not valid_targets:  # Prevent crash
        return set()
      
    j = np.random.choice(valid_targets)
    state[k].polygon, state[j].polygon = state[j].polygon, state[k].polygon
    return {k, j}
```

### Usage

**Single Kitchen:**

```bash
python -m infinigen_examples.generate_indoors --seed 42 --task coarse \
  --output_folder outputs/kitchen_test/0827_1 --configs kitchen_only.gin
```

**Batch Generation:**

```bash
bash scripts/automoma/generate_kitchen_rooms.sh
```

### Status

- ✅ Single generation works
- ✅ Kitchen-only constraints produce larger, more complex kitchens
- ⚠️ Batch script needs testing

---

Last Updated: July 21, 2025
