#include <Arduino.h>
#include "move.h"
#include "main.h"
#include "gcode.h"

const int dirPin = 2;
const int pwmPin = 3;
const int potPin = A5;
const int speed = 100;

const float tolerance = 0.5; // Tolerance for stopping the actuator
enum ActuatorState { STOPPED, EXTENDING, RETRACTING };
ActuatorState lastState = STOPPED;

void setup() {
  // Set pin modes for direction, PWM, and potentiometer
  pinMode(dirPin, OUTPUT);
  pinMode(pwmPin, OUTPUT);
  pinMode(potPin, INPUT);

  Serial.begin(9600); // Serialize communication
  Serial.println("Ready for G-code");
}

void loop() {
  gcodeSerialLoop(); // Handles incoming G-code

  int potValue = analogRead(potPin);
  if (potValue < 59) potValue = 59; 
  if (potValue > 217) potValue = 217;
  float percent = map(potValue, 59, 217, 0, 100); // Shaved 2 values from the range read by analog for safety

  ActuatorState currentState = STOPPED;
  

  if (abs(percent - targetPercent) > tolerance) {
    if (percent < targetPercent) {
      moveActuator(speed);
      currentState = EXTENDING;
    } else if (percent > targetPercent) {
      moveActuator(-speed);
      currentState = RETRACTING;
    }
  } else {
    moveActuator(0);
    currentState = STOPPED;
  }

  // Only print when state changes
  if (currentState != lastState) {
    switch (currentState) {
      case EXTENDING:
      Serial.print("moving actuator to extend, current percent: ");
      Serial.println(percent);
      break;
    case RETRACTING:
      Serial.print("moving actuator to retract, current percent: ");
      Serial.println(percent);
      break;
    case STOPPED:
      Serial.print("actuator stopped, within tolerance, current percent: ");
      Serial.println(percent);
      break;
    }
    lastState = currentState;
  }

  delay(200); // Adjust as needed for responsiveness
}
