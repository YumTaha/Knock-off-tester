#include "gcode.h"

float targetPercent = 8;     // Start at 0 percent
const float maxPercent = 99; // Max for your actuator
const float minPercent = 1;  // Min

static String inputLine = ""; // Static so it persists between calls

void gcodeSerialLoop() {
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    if (inChar == '\n' || inChar == '\r') {
      inputLine.trim();
      if (inputLine.length() > 0) {
        parseGCode(inputLine);
        inputLine = "";
      }
    } else {
      inputLine += inChar;
    }
  }
}

void parseGCode(String line) {
  line.toUpperCase();
  if (line.startsWith("G0") || line.startsWith("G1")) {
    int xIndex = line.indexOf('X');
    if (xIndex != -1) {
      String value = "";
      for (int i = xIndex + 1, n = line.length(); i < n; i++) {
        if (isDigit(line[i]) || line[i] == '.' || line[i] == '-') {
          value += line[i];
        } else {
          break;
        }
      }
      float newTarget = value.toFloat();
      if (newTarget >= minPercent && newTarget <= maxPercent) {
        targetPercent = newTarget;
        Serial.print("Target set to: ");
        Serial.println(targetPercent);
      } else {
        Serial.println("Target out of range!");
      }
    }
  } else {
    Serial.print("Unknown or unsupported G-code: ");
    Serial.println(line);
  }
}
