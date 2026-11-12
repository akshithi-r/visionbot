# SCIENCE EXHIBITION PROJECT PROPOSAL

## VisionBot – A Computer Vision Guided Autonomous Robot

**Theme:** Artificial Intelligence (AI) and Robotics  

---

## 1. Abstract

VisionBot is a small autonomous robot that uses computer vision to identify its location and navigate towards a destination selected by a visitor.

The project uses a camera mounted above a small arena. Two specially designed visual markers called ArUco markers are used: one is attached to the robot, while the other is printed on a destination card.

When a visitor places the destination card anywhere inside the arena and presses the START button, the computer identifies both markers using a camera. It calculates the distance and direction between the robot and the destination using mathematical formulas.

The computer then sends movement instructions to a NodeMCU (ESP8266) microcontroller, which controls the robot's motors. The camera continuously tracks the robot, allowing the computer to correct its movement until it reaches the destination.

This project demonstrates how computer vision, mathematics, programming and robotics can work together to create an autonomous system.

## 2. Introduction

Robots are increasingly being used in industries, warehouses, hospitals and transportation systems.

Modern autonomous robots need to understand their surroundings, identify their position, determine where they need to go and move towards their destination without continuous human intervention.

VisionBot demonstrates these concepts on a small scale.

Unlike a conventional remote-controlled car, VisionBot does not require a person to control its direction. Instead, a computer observes the robot through a camera, calculates its movement and sends instructions automatically.

The project demonstrates a simplified version of the navigation technology used in autonomous vehicles and warehouse robots.

## 3. Problem Statement

Can we build a small robot that can independently identify a destination, calculate the distance and direction to that destination, and navigate towards it without human control?

The objective is to demonstrate how a computer can use visual information and mathematical calculations to guide a physical robot.

## 4. Objectives

The main objectives of this project are:

1. To understand how computers interpret visual information through computer vision.
2. To identify objects and positions using ArUco visual markers.
3. To understand coordinate geometry and distance calculations.
4. To control a physical robot using a NodeMCU (ESP8266) microcontroller.
5. To implement autonomous navigation using continuous camera feedback.
6. To demonstrate how computers, mathematics and robotics work together.

## 5. Components Required

### Hardware

| Component | Purpose |
|---|---|
| NodeMCU (ESP8266) development board | Main robot controller |
| 2 DC BO geared motors | Drive the robot |
| 2 wheels | Robot movement |
| 1 caster wheel | Mechanical support and balance |
| L298N motor driver | Controls motor speed and direction |
| Rechargeable battery pack | Supplies power to the robot |
| USB webcam | Captures the arena |
| Laptop | Processes images and calculates navigation |
| ArUco marker ID 10 | Identifies the robot |
| ArUco marker ID 20 | Identifies the destination card |
| Robot chassis | Holds all components |
| Jumper wires | Electrical connections |

### Software

- Python – Main programming language.
- OpenCV – Image processing and ArUco marker detection.
- NumPy – Mathematical calculations.
- PySerial or Wi-Fi communication – Laptop-to-NodeMCU communication.
- ESP8266 Arduino framework (PlatformIO) – Motor control programming.

## 6. System Architecture

The project consists of four main sections.

### A. Vision System

A USB camera is mounted above the arena and connected to the laptop.

The camera captures the entire arena and identifies two ArUco markers:

- Marker ID 10: Attached to the robot.
- Marker ID 20: Attached to the destination card.

The camera provides the position and orientation information needed for navigation.

### B. Intelligence and Navigation System

The laptop acts as the brain of the robot.

Using Python and OpenCV, it:

- Detects both markers.
- Identifies the robot's current position.
- Identifies the destination position.
- Calculates the distance and direction.
- Determines the required movement.

### C. Communication System

The laptop communicates with the NodeMCU and sends movement commands.

For example:

- FORWARD
- TURN LEFT
- TURN RIGHT
- STOP

Wi-Fi can be used to avoid a trailing communication cable during movement. USB serial communication can also be used during initial development and testing.

### D. Robotics System

The NodeMCU receives the movement commands and controls the L298N motor driver.

The motor driver independently controls the left and right motors, allowing the robot to move forward, turn and stop.

## 7. Working Methodology

The project works through the following sequence.

**Step 1: Initial Setup**

The robot is placed inside a predefined starting area of the arena.

The destination card is placed at any location within the arena.

**Step 2: Start the System**

The visitor presses the START button on the laptop.

The camera captures the arena.

**Step 3: Marker Detection**

The computer identifies the robot marker (ID 10) and destination marker (ID 20).

It calculates the centre coordinates of both markers.

**Step 4: Mathematical Calculation**

The computer calculates the distance and direction between the robot and the destination.

**Step 5: Movement Decision**

Based on the calculations, the computer decides whether the robot should move forward, turn left or turn right.

**Step 6: Motor Control**

The computer sends movement instructions to the NodeMCU.

The NodeMCU controls the motors through the motor driver.

**Step 7: Continuous Monitoring**

The camera continuously observes the robot's movement.

The computer recalculates its position and corrects the movement whenever necessary.

**Step 8: Destination Reached**

When the robot reaches the destination card within the predefined tolerance, the computer sends a STOP command.

The robot parks over the destination card.

## 8. Mathematics Behind the Project

Mathematics plays an important role in autonomous navigation.

The camera provides the coordinates of the robot and the destination.

Let:

Robot position:

R = (x₁, y₁)

Destination position:

T = (x₂, y₂)

### A. Distance Calculation

The distance between two points is calculated using the distance formula:

d = √[(x₂ - x₁)² + (y₂ - y₁)²]

This helps the computer determine how far the robot is from its destination.

### B. Direction Calculation

The direction towards the destination is calculated using:

θ = atan2(y₂ - y₁, x₂ - x₁)

The robot's current orientation is also detected using its ArUco marker.

The computer compares the desired direction with the robot's current direction to determine whether it needs to turn.

### C. Coordinate Conversion

The camera initially identifies positions in pixels.

Using the known dimensions of the arena, pixel coordinates can be converted into approximate distances in centimetres.

This makes navigation calculations more meaningful.

## 9. Continuous Feedback and Control

One of the most important concepts demonstrated by VisionBot is feedback control.

A conventional remote-controlled car follows instructions from a human operator.

VisionBot follows a different approach.

1. The camera observes the robot.
2. The computer calculates its current position.
3. The computer compares the current position with the destination.
4. It sends corrective movement instructions.
5. The camera observes the new position.

This process repeats until the robot reaches the destination.

This is called a closed-loop feedback control system.

The robot does not simply follow a fixed movement sequence. It continuously adjusts its movement based on what the camera observes.

## 10. Applications in the Real World

The concepts demonstrated in this project are used in many real-world applications.

**Autonomous Vehicles:** Cars use cameras and other sensors to understand their surroundings and navigate roads.

**Warehouse Automation:** Autonomous mobile robots transport goods between different locations in warehouses.

**Industrial Robotics:** Robots use visual information to identify objects and perform tasks accurately.

**Smart Parking Systems:** Computer vision and automated control can assist vehicles in identifying and reaching parking spaces.

**Healthcare Robotics:** Robots can navigate hospitals and transport medicines or medical supplies.

## 11. Expected Outcome

At the end of the project, we expect to demonstrate a robot that:

- Identifies its own position using a camera.
- Identifies a destination card placed by a visitor.
- Calculates the distance and direction to the destination.
- Moves autonomously using motor commands.
- Continuously corrects its movement using camera feedback.
- Stops when it reaches the destination.

The destination can be changed simply by moving the card to another location within the arena.

## 12. Safety Measures

- The robot will operate inside a designated arena.
- Motor speed will be kept low for safe demonstration.
- The electrical connections will be insulated properly.
- The battery voltage will be checked before operation.
- The motors will stop if the camera loses track of the robot or destination.
- The robot will have an emergency STOP option.

## 13. Limitations

The project is a simplified autonomous navigation system.

Its performance depends on camera visibility, lighting conditions, marker detection and motor calibration.

The robot may not always reach the exact centre of the destination because of motor speed differences and mechanical friction.

It is designed for a controlled indoor environment and does not include obstacle avoidance.

## 14. Future Improvements

The project can be extended in several ways:

1. Introduce artificial intelligence-based object recognition instead of relying only on visual markers.
2. Add obstacle detection and avoidance.
3. Introduce multiple destination points.
4. Improve navigation accuracy using wheel encoders and advanced control algorithms.
5. Develop a mobile application to select destinations remotely.
6. Explore more advanced autonomous navigation techniques.

## 15. Conclusion

VisionBot demonstrates how computer vision, mathematics, programming and robotics can be combined to build an autonomous machine.

The project shows that a robot can identify its position, recognise a destination, calculate the required movement and navigate independently with continuous feedback from a camera.

It also demonstrates the importance of mathematics in real-world engineering applications.

Through this project, we learn that autonomous robots are not simply machines that move. They are systems that observe, calculate, make decisions and take action.

---
