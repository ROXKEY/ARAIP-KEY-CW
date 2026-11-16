from controller import Robot

robot = Robot()
timestep = int(robot.getBasicTimeStep())

camera = robot.getDevice("camera")
camera.enable(timestep)

left = robot.getDevice("left wheel motor")
right = robot.getDevice("right wheel motor")
left.setPosition(float('inf'))
right.setPosition(float('inf'))
left.setVelocity(0)
right.setVelocity(0)

step_count = 0
while robot.step(timestep) != -1:
    step_count += 1
    if step_count == 20:   # wait a few steps so the camera has a valid frame
        camera.saveImage("frame.png", 100)
        print("Saved frame.png")