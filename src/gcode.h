#ifndef GCODE_H
#define GCODE_H

#include <Arduino.h>

// The target position in percent, updated by G-code commands
extern float targetPercent;

// Call in loop to process any new G-code lines
void gcodeSerialLoop();

// Optionally, parse a G-code line directly (for testing or expansion)
void parseGCode(String line);

#endif
