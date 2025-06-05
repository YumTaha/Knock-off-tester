#include <Arduino.h>
#include "move.h"

// Pin assignments (set these in main.h and define in main.cpp)
extern const int dirPin;
extern const int pwmPin;

void moveActuator(int speed) {
  // speed: -255 (full retract) ... 0 (stop) ... 255 (full extend)
  if (speed > 0) {
    digitalWrite(dirPin, LOW);     // Extend
    analogWrite(pwmPin, abs(speed));
  } else if (speed < 0) {
    digitalWrite(dirPin, HIGH);      // Retract
    analogWrite(pwmPin, abs(speed));    // must be positive
  } else {
    analogWrite(pwmPin, 0);         // Stop
  }
}