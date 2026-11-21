"""ARAIP Part 2 - e-puck colour block search (red, green, blue) with a state machine.

What it does
------------
The e-puck searches the arena for three coloured blocks. The whole camera image is
scanned for each colour, so a block is noticed anywhere in the view. When a new colour
is seen the robot turns towards it, drives up to it, reports it, then backs away and
carries on until all three blocks are found (or SEARCH_TIMEOUT seconds have passed).

State machine
-------------
SEARCH   wander: drive forward with gentle random curves and obstacle avoidance,
         looking for an unseen colour
SCAN     (optional, USE_SCAN_SPIN) spin on the spot every SCAN_INTERVAL seconds and look
APPROACH steer towards the target colour until it fills enough of the view
LEAVE    after reporting a block: back up, turn away, return to SEARCH
DONE     all blocks found (or timeout): stop and print the summary

Two modes (set CAPTURE_MODE below)
----------------------------------
True  -> the robot stays still and saves one camera frame (FRAME_FILE) for the CNN
False -> normal colour block search (the demo for Assignments 3 and 5)

Block randomisation
-------------------
At the start of every search run the three blocks are moved to new random positions
inside the arena (see RANDOMISE_BLOCKS). This needs the E-puck's `supervisor` field set
to TRUE in the scene tree. Blocks never overlap each other, the walls, the robot's start
position or the CNN test objects (the cat and the old test box, see OBSTACLES). The seed
is printed, so a layout can be repeated by setting RANDOM_SEED to that number.

Hardware used (e-puck): 'left wheel motor', 'right wheel motor', proximity sensors
ps0/ps1 (front right), ps7/ps6 (front left), and 'camera' (128 x 128 in this world).
"""
import math
import os
import random
import sys
from controller import Supervisor

# ======================= settings =======================
TIME_STEP = 32          # ms, simulation step
MAX_SPEED = 6.28        # rad/s, e-puck wheel limit

# --- obstacle avoidance ---
DIST_LIMIT = 70.0       # averaged proximity value above this means "obstacle close"
TIME_DELAY = 0.5        # seconds between obstacle decisions

# --- colour detection (tune after testing) ---
MIN_BRIGHT = 50         # strong channel must exceed this. Lit block faces are ~200 but
                        # shaded faces only ~60-80, so this must stay low
DOMINANCE = 0.35        # the other two channels must be below this share of the strong one
MIN_FRACTION = 0.01     # a colour must cover >= 1% of the sampled pixels to count
SAMPLE_STEP = 2         # look at every 2nd pixel in x and y (4x faster, still reliable)
ALL_COLOURS = ['red', 'green', 'blue']

# --- search behaviour ---
# Wandering: drive mostly straight, with a gentle random curve every few seconds. The camera
# keeps looking while the robot moves, so no stopping to spin is needed.
WANDER_STRAIGHT_TIME = (3.0, 6.0)   # s of straight driving between curves (random in range)
WANDER_ARC_TIME = (0.6, 1.8)        # s of gentle curve to the left or right (about 35-100 deg)
# Optional look-around spin (off by default because it makes the robot rotate a lot):
USE_SCAN_SPIN = False
SCAN_INTERVAL = 15.0    # s of driving between look-around spins (only if USE_SCAN_SPIN)
SCAN_TIME = 3.5         # s for one spin (a full turn takes about 3.2 s at SPIN_SPEED)
SPIN_SPEED = 0.4        # fraction of MAX_SPEED used when spinning on the spot
APPROACH_FRACTION = 0.15  # block covers this share of the view -> close enough, identify it
TOUCH_MIN_FRACTION = 0.06 # if both front sensors fire, the target must cover at least this much
                          # of the view to count; otherwise the robot is just against a wall/other object
LOST_TIMEOUT = 1.5      # s without seeing the target before giving up and searching again
APPROACH_TIMEOUT = 20.0 # s allowed to reach one block
BACK_TIME = 1.0         # s reversing after a block is reported
TURN_TIME = 1.2         # s turning away afterwards (about 135 degrees)
SEARCH_TIMEOUT = 240.0  # s of simulated time before the run ends with a summary

# --- CNN frame capture (Part 2) ---
CAPTURE_MODE = True     # True: stay still and save a frame. False: normal block search
CAPTURE_STEP = 20       # steps to wait so the camera has a valid image
FRAME_FILE = "frame_cat_60cm.png"   # change per test, e.g. "frame_cat_40cm.png"
SAVE_FOUND_FRAMES = True            # save found_<colour>.png when a block is identified

# --- block randomisation (needs the E-puck 'supervisor' field set to TRUE) ---
RANDOMISE_BLOCKS = True
RANDOM_SEED = None      # None = a new layout every run; an integer (e.g. 42) repeats a layout
BLOCK_NAMES = {'red': 'red_block', 'green': 'green_block', 'blue': 'blue_block'}
# Objects the blocks must stay clear of: node `name` -> object radius in metres.
# Missing nodes are skipped, so it is safe to leave the old box listed after deleting it.
# Adjust the cat's radius to about half its longest dimension (nose to tail).
OBSTACLES = {'cat': 0.35, 'cnn_object': 0.15}
OBSTACLE_MARGIN = 0.10  # m, extra free gap around each obstacle
WALL_MARGIN = 0.10      # m, free gap between a block edge and the arena wall
BLOCK_GAP = 0.15        # m, free gap between two blocks
ROBOT_CLEARANCE = 0.20  # m, free gap around the robot's start position
DEFAULT_BLOCK_SIZE = 0.3   # m, used if a block has no `size` field

# state names
SEARCH, SCAN, APPROACH, LEAVE, DONE = "SEARCH", "SCAN", "APPROACH", "LEAVE", "DONE"

# ======================= robot setup =======================
robot = Supervisor()     # a Supervisor is a Robot that can also move other nodes (block randomisation)


def get_device(name):
    """Return a device by name, or stop with a clear message if it does not exist."""
    device = robot.getDevice(name)
    if device is None:
        print(f"ERROR: device '{name}' not found. Check that the robot is an e-puck.")
        sys.exit(1)
    return device


leftMotor = get_device('left wheel motor')
rightMotor = get_device('right wheel motor')
leftMotor.setPosition(float('inf'))      # velocity control
rightMotor.setPosition(float('inf'))

rightSensor1 = get_device('ps0')
rightSensor2 = get_device('ps1')
leftSensor1 = get_device('ps7')
leftSensor2 = get_device('ps6')
for s in (rightSensor1, rightSensor2, leftSensor1, leftSensor2):
    s.enable(TIME_STEP)

cam = get_device('camera')
cam.enable(TIME_STEP)
W = cam.getWidth()
H = cam.getHeight()

seen = []               # colours already found, in order


# ======================= sensing =======================
def get_left_sensor():
    """True if something is close on the front left."""
    return (leftSensor1.getValue() + leftSensor2.getValue()) / 2.0 > DIST_LIMIT


def get_right_sensor():
    """True if something is close on the front right."""
    return (rightSensor1.getValue() + rightSensor2.getValue()) / 2.0 > DIST_LIMIT


def classify_pixel(r, g, b):
    """Return 'red', 'green' or 'blue' if one channel clearly dominates, else None."""
    if r > MIN_BRIGHT and g < DOMINANCE * r and b < DOMINANCE * r:
        return 'red'
    if g > MIN_BRIGHT and r < DOMINANCE * g and b < DOMINANCE * g:
        return 'green'
    if b > MIN_BRIGHT and r < DOMINANCE * b and g < DOMINANCE * b:
        return 'blue'
    return None


def analyse_image():
    """Scan the whole camera image.

    Returns {colour: (fraction, x_centre)} for every colour covering at least
    MIN_FRACTION of the sampled pixels. x_centre runs from 0.0 (left edge) to 1.0 (right).
    Returns an empty dict if there is no image or nothing is found.
    """
    img = cam.getImage()                 # raw bytes, 4 per pixel in B, G, R, A order
    if not img:
        return {}
    count = {c: 0 for c in ALL_COLOURS}
    x_sum = {c: 0 for c in ALL_COLOURS}
    total = 0
    for y in range(0, H, SAMPLE_STEP):
        row = y * W * 4
        for x in range(0, W, SAMPLE_STEP):
            i = row + x * 4
            colour = classify_pixel(img[i + 2], img[i + 1], img[i])
            total += 1
            if colour:
                count[colour] += 1
                x_sum[colour] += x
    found = {}
    for c in ALL_COLOURS:
        if total and count[c] / total >= MIN_FRACTION:
            found[c] = (count[c] / total, x_sum[c] / count[c] / W)
    return found


def best_unseen(found):
    """Pick the largest colour in view that has not been reported yet (or None)."""
    candidates = {c: v for c, v in found.items() if c not in seen}
    if not candidates:
        return None
    return max(candidates, key=lambda c: candidates[c][0])


# ======================= movement =======================
def stop():
    leftMotor.setVelocity(0.0)
    rightMotor.setVelocity(0.0)


def move_forward():
    leftMotor.setVelocity(0.5 * MAX_SPEED)
    rightMotor.setVelocity(0.5 * MAX_SPEED)


def move_backward():
    leftMotor.setVelocity(-0.5 * MAX_SPEED)
    rightMotor.setVelocity(-0.5 * MAX_SPEED)


def turn_left():
    leftMotor.setVelocity(0.1 * MAX_SPEED)
    rightMotor.setVelocity(0.5 * MAX_SPEED)


def turn_right():
    leftMotor.setVelocity(0.5 * MAX_SPEED)
    rightMotor.setVelocity(0.1 * MAX_SPEED)


def spin_in_place():
    """Rotate on the spot (clockwise) to look around."""
    leftMotor.setVelocity(SPIN_SPEED * MAX_SPEED)
    rightMotor.setVelocity(-SPIN_SPEED * MAX_SPEED)


def steer_towards(x_centre):
    """Drive forward while turning so the block moves to the middle of the image."""
    error = x_centre - 0.5                       # negative: block on the left
    base = 0.4 * MAX_SPEED
    turn = 1.5 * error * MAX_SPEED
    leftMotor.setVelocity(max(-MAX_SPEED, min(MAX_SPEED, base + turn)))
    rightMotor.setVelocity(max(-MAX_SPEED, min(MAX_SPEED, base - turn)))


def drive_with_avoidance(now, last_decision):
    """Drive forward, steering away from obstacles. Returns the new decision time."""
    if now - last_decision < TIME_DELAY:
        return last_decision
    blocked_left = get_left_sensor()
    blocked_right = get_right_sensor()
    if blocked_left and blocked_right:
        move_backward()
    elif blocked_left:
        turn_right()
    elif blocked_right:
        turn_left()
    else:
        move_forward()
    return now


# ======================= reporting =======================
def print_summary(timed_out=False):
    missing = [c for c in ALL_COLOURS if c not in seen]
    print("----- Summary -----")
    print("Found:    ", ", ".join(seen) if seen else "none")
    if missing:
        print("Not found:", ", ".join(missing))
        if timed_out:
            print(f"No block found for the missing colours within {SEARCH_TIMEOUT:.0f} s.")
    else:
        print("All three blocks found.")


def report(colour, fraction, reason):
    """Record a newly identified block and print progress."""
    seen.append(colour)
    print(f"[{robot.getTime():.1f} s] I see {colour} ({fraction:.0%} of the view, {reason})")
    remaining = [c for c in ALL_COLOURS if c not in seen]
    print("Encountered so far:", ", ".join(seen))
    print("Not yet encountered:", ", ".join(remaining) if remaining else "none")
    if SAVE_FOUND_FRAMES:
        cam.saveImage(f"found_{colour}.png", 100)


def save_frame():
    """Save the current camera image so the CNN can classify it in Colab."""
    cam.saveImage(FRAME_FILE, 100)       # 100 = best quality
    print(f"[{robot.getTime():.1f} s] Saved {FRAME_FILE} ({W}x{H})")
    print("Full path:", os.path.abspath(FRAME_FILE))


# ======================= block randomisation =======================
def get_scene_children():
    """Return the world's top-level `children` field, or None if this robot is not a supervisor.

    (If the E-puck's `supervisor` field is FALSE, Webots refuses the call and prints an error;
    the returned field is then None.)
    """
    try:
        root = robot.getRoot()
        return root.getField('children') if root is not None else None
    except Exception:
        return None


def find_node(children, name):
    """Return the top-level scene node whose `name` field equals name, or None."""
    for i in range(children.getCount()):
        node = children.getMFNode(i)
        name_field = node.getField('name')
        if name_field is not None and name_field.getSFString() == name:
            return node
    return None


def get_arena_bounds(children):
    """Return (xmin, xmax, ymin, ymax) of the RectangleArena floor, or None if not found."""
    for i in range(children.getCount()):
        node = children.getMFNode(i)
        if node.getTypeName() == 'RectangleArena':
            size = node.getField('floorSize').getSFVec2f()
            centre = node.getField('translation').getSFVec3f()
            return (centre[0] - size[0] / 2, centre[0] + size[0] / 2,
                    centre[1] - size[1] / 2, centre[1] + size[1] / 2)
    return None


def block_radius(node):
    """Half the block's footprint width (m), read from its `size` field if it has one."""
    size_field = node.getField('size')
    if size_field is None:
        return DEFAULT_BLOCK_SIZE / 2
    size = size_field.getSFVec3f()
    return max(size[0], size[1]) / 2


def random_layout(rng, bounds, radius, avoid, count):
    """Pick `count` block centres inside bounds.

    avoid is a list of (x, y, clearance) circles that block centres must stay outside.
    Blocks are kept at least 2 * radius + gap apart; the gap is relaxed if the arena is tight.
    Returns a list of (x, y), or None if no layout fits.
    """
    xmin, xmax, ymin, ymax = bounds
    x_lo, x_hi = xmin + radius + WALL_MARGIN, xmax - radius - WALL_MARGIN
    y_lo, y_hi = ymin + radius + WALL_MARGIN, ymax - radius - WALL_MARGIN
    if x_lo >= x_hi or y_lo >= y_hi:
        return None
    for gap in (BLOCK_GAP, BLOCK_GAP / 2, 0.0):          # relax the spacing if needed
        placed = []
        for _ in range(count):
            for _attempt in range(300):
                x, y = rng.uniform(x_lo, x_hi), rng.uniform(y_lo, y_hi)
                clear_of_obstacles = all(math.hypot(x - ax, y - ay) >= c for ax, ay, c in avoid)
                clear_of_blocks = all(math.hypot(x - px, y - py) >= 2 * radius + gap
                                      for px, py in placed)
                if clear_of_obstacles and clear_of_blocks:
                    placed.append((x, y))
                    break
            else:
                break                                      # could not place this block
        if len(placed) == count:
            return placed
    return None


def randomise_blocks(seed=None):
    """Move the red, green and blue blocks to new random positions. Returns True on success.

    Never stops the controller: if anything is missing it prints why and leaves the blocks alone.
    """
    children = get_scene_children()
    if children is None:
        print("Block randomisation skipped: set the E-puck 'supervisor' field to TRUE "
              "(scene tree > E-puck > supervisor), save, and reload the world.")
        return False
    try:
        blocks = {}
        for colour, name in BLOCK_NAMES.items():
            node = find_node(children, name)
            if node is None:
                print(f"Block randomisation skipped: no node named '{name}' in the world.")
                return False
            blocks[colour] = node

        bounds = get_arena_bounds(children)
        if bounds is None:
            print("Block randomisation skipped: no RectangleArena found.")
            return False

        radius = max(block_radius(n) for n in blocks.values())
        avoid = []
        me = robot.getSelf()
        me_field = me.getField('translation') if me is not None else None
        if me_field is not None:                           # keep clear of the robot's start
            x, y, _ = me_field.getSFVec3f()
            avoid.append((x, y, radius + ROBOT_CLEARANCE))
        for obs_name, obs_radius in OBSTACLES.items():     # keep clear of the cat / test box
            obs = find_node(children, obs_name)
            if obs is None:
                continue
            obs_field = obs.getField('translation')
            if obs_field is None:
                continue
            x, y, _ = obs_field.getSFVec3f()
            avoid.append((x, y, radius + obs_radius + OBSTACLE_MARGIN))
            print(f"Keeping blocks clear of '{obs_name}' at x = {x:+.2f} m, y = {y:+.2f} m")

        if seed is None:
            seed = RANDOM_SEED if RANDOM_SEED is not None else random.randrange(1000000)
        layout = random_layout(random.Random(seed), bounds, radius, avoid, len(blocks))
        if layout is None:
            print("Block randomisation skipped: the arena is too small for the blocks.")
            return False

        print(f"Block layout (seed {seed}):")
        for (colour, node), (x, y) in zip(blocks.items(), layout):
            field = node.getField('translation')
            z = field.getSFVec3f()[2]                      # keep each block's own height
            field.setSFVec3f([x, y, z])
            node.resetPhysics()
            print(f"  {colour:<5} at x = {x:+.2f} m, y = {y:+.2f} m")
        return True
    except Exception as err:                               # the search must still run
        print(f"Block randomisation skipped: {err}")
        return False


# ======================= main loop =======================
def main():
    start = robot.getTime()
    state = SEARCH
    state_t0 = start
    last_scan = start
    last_avoid = start
    wander_next = start + random.uniform(*WANDER_STRAIGHT_TIME)
    wander_until = start
    arcing = False
    target = None
    target_last_seen = start
    step_count = 0

    if CAPTURE_MODE:
        stop()
    else:
        if RANDOMISE_BLOCKS:
            randomise_blocks()
        move_forward()

    while robot.step(TIME_STEP) != -1:
        step_count += 1
        now = robot.getTime()

        # Capture mode: stay still, save one frame, then do nothing
        if CAPTURE_MODE:
            if step_count == CAPTURE_STEP:
                save_frame()
            continue

        if state == DONE:
            continue

        # Give up if the run takes too long
        if now - start > SEARCH_TIMEOUT:
            stop()
            print_summary(timed_out=True)
            state = DONE
            continue

        # --- SEARCH and SCAN: look for a colour we have not reported yet ---
        if state in (SEARCH, SCAN):
            candidate = best_unseen(analyse_image())
            if candidate:
                target, target_last_seen = candidate, now
                state, state_t0 = APPROACH, now
                print(f"[{now:.1f} s] Spotted {target}, approaching")
            elif state == SCAN:
                if now - state_t0 >= SCAN_TIME:
                    state, last_scan = SEARCH, now
                    move_forward()
            elif USE_SCAN_SPIN and now - last_scan >= SCAN_INTERVAL:
                state, state_t0 = SCAN, now
                spin_in_place()
            elif get_left_sensor() or get_right_sensor():
                # obstacle avoidance always has priority over wandering
                arcing = False
                last_avoid = drive_with_avoidance(now, last_avoid)
            elif now < wander_until:
                pass                                  # keep the current gentle curve
            elif now >= wander_next:
                # start a short random curve, then plan the next one
                wander_until = now + random.uniform(*WANDER_ARC_TIME)
                wander_next = wander_until + random.uniform(*WANDER_STRAIGHT_TIME)
                arcing = True
                random.choice((turn_left, turn_right))()
            else:
                if arcing:                            # the curve has finished
                    arcing = False
                    move_forward()
                last_avoid = drive_with_avoidance(now, last_avoid)

        # --- APPROACH: steer to the block, identify it when close enough ---
        elif state == APPROACH:
            found = analyse_image()
            if target in found:
                fraction, x_centre = found[target]
                target_last_seen = now
                touching = get_left_sensor() and get_right_sensor()
                reason = None
                if fraction >= APPROACH_FRACTION:
                    reason = "close enough"
                elif touching and fraction >= TOUCH_MIN_FRACTION:
                    reason = "touching it"
                elif now - state_t0 > APPROACH_TIMEOUT:
                    reason = "approach timeout"
                if reason:
                    stop()
                    report(target, fraction, reason)
                    if len(seen) == len(ALL_COLOURS):
                        print(f"[{now:.1f} s] All three blocks found. Search complete.")
                        print_summary()
                        state = DONE
                    else:
                        state, state_t0 = LEAVE, now
                elif touching:
                    # something else (a wall or another block) is in the way: back off and retry
                    last_avoid = drive_with_avoidance(now, last_avoid)
                else:
                    steer_towards(x_centre)
            elif now - target_last_seen > LOST_TIMEOUT:
                print(f"[{now:.1f} s] Lost sight of {target}, searching again")
                state, last_scan = SEARCH, now
                move_forward()

        # --- LEAVE: back away from the block, turn, then carry on searching ---
        elif state == LEAVE:
            elapsed = now - state_t0
            if elapsed < BACK_TIME:
                move_backward()
            elif elapsed < BACK_TIME + TURN_TIME:
                spin_in_place()
            else:
                state, last_scan = SEARCH, now
                move_forward()


if __name__ == '__main__':
    main()