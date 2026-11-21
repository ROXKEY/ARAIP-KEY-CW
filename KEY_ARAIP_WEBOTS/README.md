# ARAIP Part 2: Webots colour block search (Assignments 4 and 5)

Author: Min Hein Khant, BEng (Hons) Robotics and Artificial Intelligence, University of Hertfordshire
Module: Applied Robotics and AI Project. Simulator: Webots R2025a. Language: Python 3.

## What is in this package
```
worlds/
  ARAIP CNN WORLD.wbt           the arena, e-puck, three blocks and the CNN test box
  textures/car.jpg              photo used on the CNN test box (the world needs this file)
controllers/
  araip_block_search/           Part 2 controller (colour block search with a state machine)
    araip_block_search.py
  block_controller_key/         early frame-capture test only (reference, not used in the demo)
sample_outputs/                 found_red/green/blue.png and frame_car_60cm.png saved by the controller
```

## How to run (colour block search demo)
1. Install Webots R2025a. The first time the world loads it needs an internet connection, because the robot and block PROTO files are fetched from the Webots repository.
2. Open `worlds/ARAIP CNN WORLD.wbt` (File > Open World).
3. Check that the E-puck's `controller` field is `araip_block_search` and its `supervisor` field is TRUE (needed to randomise the blocks). Both are already set in the world file.
4. Press Play. The console prints the random block layout and then each block as it is found, for example `I see green (8% of the view, touching it)`, and finally a summary. The run ends when all three blocks are found or after 240 s.

## Setup details
| Item | Value |
|---|---|
| Arena | RectangleArena, floorSize 3 x 3 m |
| Blocks | SolidBox red, green and blue (pure RGB colours), size 0.3 x 0.3 x 0.1 m, on the floor |
| Block positions | randomised at the start of every run (not overlapping, not touching the walls or the robot start); the seed is printed, and `RANDOM_SEED` in the controller repeats a layout |
| Robot | e-puck, differential drive, 8 proximity sensors (ps0 to ps7), camera 128 x 128 pixels (`camera_width`, `camera_height`) |
| Devices used | `left wheel motor`, `right wheel motor` (velocity control), `ps0`, `ps1` (front right), `ps7`, `ps6` (front left), `camera` |
| Time step | 32 ms |

## Controller design (araip_block_search.py)
- **Colour detection:** the whole camera image is scanned (every 2nd pixel). A pixel is red, green or blue when that channel is above `MIN_BRIGHT` (50) and the other two are below `DOMINANCE` (0.35) times it. A colour counts when it covers at least `MIN_FRACTION` (1%) of the sampled pixels. The low brightness threshold is deliberate: the shaded sides of a block are only about RGB (0, 60 to 80, 0).
- **State machine:** SEARCH (wander with gentle random curves and obstacle avoidance), APPROACH (steer to the block), LEAVE (back up and turn), DONE (print the summary). SCAN (spin on the spot) is optional (`USE_SCAN_SPIN`).
- **Reporting rule:** a block is reported when it covers at least 15% of the view, or when both front proximity sensors fire and it covers at least 6% (`TOUCH_MIN_FRACTION`). The console line states which rule applied.
- **Error handling:** missing devices stop the controller with a clear message; an empty camera image is skipped; if randomisation is not possible (supervisor FALSE, node missing) it prints why and the search still runs; after 240 s the summary lists the colours that were not found.
- **Modular functions:** `analyse_image`, `classify_pixel`, `best_unseen`, `steer_towards`, `drive_with_avoidance`, `randomise_blocks`, `report`, `print_summary`, `save_frame`.

## Colour space choice and optimisation
- **Why RGB dominance and not HSV:** the blocks are pure red, green and blue, so one channel clearly dominates. Comparing channels (`other < 0.35 x strong`) needs no colour-space conversion per pixel, so it is cheaper and still works on the dark shaded block faces, where HSV hue becomes unstable at very low brightness. If the block colours were less pure (for example orange or purple) HSV hue ranges would be the better choice.
- **Pre-filtering the camera image (optimisation):** `SAMPLE_STEP = 2` checks only every 2nd pixel in x and y, so about 4 times fewer pixels are classified per time step (1024 instead of 4096 on a 128 x 128 image). Blocks are large (up to 15% of the view), so accuracy is not affected. This keeps the pure-Python image loop light so the robot's movement and obstacle avoidance keep running at the 32 ms time step. The same idea (reduce the work per frame) is the basis of the optimisation proposal for running the CNN on the robot: run it only on a cropped region, and only when the colour filter has already found a candidate.

## CNN camera test mode
The CNN part of the project (CIFAR-10 classifier) was trained in Google Colab, so it is not run inside Webots. The controller only saves the camera frame:
1. In the scene tree, select `cnn_object` and set `translation` to `0.6 0 0.15` (it is hidden below the floor in the saved world so it does not block the demo).
2. In the controller set `CAPTURE_MODE = True` and choose a `FRAME_FILE` name, then Reload World and Play.
3. The frame is saved in the controller folder (the console prints the full path). Classify it in the notebook; crop to the object first for best results.

## Settings to tune (top of the controller)
`MIN_BRIGHT`, `DOMINANCE`, `MIN_FRACTION`, `SAMPLE_STEP`, `CRUISE_SPEED`, `CURVE_INNER_SPEED`, `APPROACH_SPEED`, `STEER_GAIN`, `CNN_BOX_RADIUS`, `CNN_BOX_MARGIN`, `APPROACH_FRACTION`, `TOUCH_MIN_FRACTION`, `WANDER_STRAIGHT_TIME`, `WANDER_ARC_TIME`, `USE_SCAN_SPIN`, `SEARCH_TIMEOUT`, `RANDOMISE_BLOCKS`, `RANDOM_SEED`.

## Known limitations
- The wandering search is random, so the last block can take a long time to find (see the evaluation in the report).
- The saved world stores the e-puck slightly away from the arena centre; this does not matter because the robot only needs a clear start.
- Colour thresholds were tuned for the pure RGB blocks under the default Webots lighting.
