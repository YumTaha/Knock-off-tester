#include "gcode.h"

// Global state
float targetPercent = 0;     // Absolute target (0-21)
float feedrate = 100;        // Default speed
const float maxPercent = 98;
const float minPercent = 1;
bool isRelative = false;     // G91 mode flag

static String inputLine = "";

// Utility: extract float after given letter, or return default
float extractParam(String& line, char letter, float def = 0) {
  int idx = line.indexOf(letter);
  if (idx == -1) return def;
  String val = "";
  for (int i = idx + 1, n = line.length(); i < n; i++) {
    if (isDigit(line[i]) || line[i] == '.' || line[i] == '-') val += line[i];
    else break;
  }
  return val.length() ? val.toFloat() : def;
}

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

  // Find G-code command (G0, G1, G91, etc.)
  if (line.startsWith("G0") || line.startsWith("G00")) {
    float x = extractParam(line, 'X', isRelative ? 0 : targetPercent);
    if (isRelative) targetPercent += x;
    else            targetPercent = x;
    targetPercent = constrain(targetPercent, minPercent, maxPercent);
    Serial.print("Absolute move to: ");
    Serial.println(targetPercent);
  }
  else if (line.startsWith("G1") || line.startsWith("G01")) {
    float x = extractParam(line, 'X', isRelative ? 0 : targetPercent);
    float f = extractParam(line, 'F', feedrate);
    if (isRelative) targetPercent += x;
    else            targetPercent = x;
    feedrate = f;
    targetPercent = constrain(targetPercent, minPercent, maxPercent);
    Serial.print("Linear move to: ");
    Serial.print(targetPercent);
    Serial.print(" at feedrate: ");
    Serial.println(feedrate);
  }
  else if (line.startsWith("G91")) {
    isRelative = true;
    Serial.println("Switched to relative (incremental) positioning (G91)");
  }
  else if (line.startsWith("G90")) {
    isRelative = false;
    Serial.println("Switched to absolute positioning (G90)");
  }
  else {
    Serial.print("Unknown or unsupported G-code: ");
    Serial.println(line);
  }
}
