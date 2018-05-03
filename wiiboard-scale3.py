#!/usr/bin/env python
# frostymccool - April 2018
# https://github.com/frostymccool/piscales

# Press the redbutton on the wii, what on screen instructions for when calibaration has been performed and get weighed :)
# runs in a constant loop so that the wiiboard red button is the only thing that is needed to be pressed
# Thus can be run completely headless if desired

# all credits go for the main part of the code to
# https://github.com/initialstate/smart-scale/wiki/Part-1.-Equipment
# https://github.com/skorokithakis/gr8w8upd8m8
# and for oled / screen handling 
# https://github.com/rm-hull/luma.examples

# typical use - provided the MAC (: separator) or leave blank for discovery
# ./wiiboard-scale3.py <MAC>

import os
import collections
import time
import bluetooth
import sys
import subprocess
import requests
import select
import socket
from random import randint
from keys import * #file containing local secret keys - MAKER_KEY etc

# OLED driver / code support
# OLED Driver https://github.com/rm-hull/luma.examples
from luma.core.interface.serial import spi
from luma.oled.device import sh1106
from luma.core.virtual import terminal
from PIL import ImageFont


#from __future__ import print_function

# --------- User Settings ---------
WEIGHT_SAMPLES = 300
MIN_WEIGHT_TO_POST = 130.0 #lbs - min value below which post wil not be sent to IFTTT
# ---------------------------------

# Wiiboard Parameters
CONTINUOUS_REPORTING = "04"  # Easier as string with leading zero
COMMAND_LIGHT = 11
COMMAND_REPORTING = 12
COMMAND_REQUEST_STATUS = 15
COMMAND_REGISTER = 16
COMMAND_READ_REGISTER = 17
INPUT_STATUS = 20
INPUT_READ_DATA = 21
EXTENSION_8BYTES = 32
BUTTON_DOWN_MASK = 8
TOP_RIGHT = 0
BOTTOM_RIGHT = 1
TOP_LEFT = 2
BOTTOM_LEFT = 3
BLUETOOTH_NAME = "Nintendo RVL-WBC-01"
#IFTTT
#IFTTT_MAKER_KEY="your unique key from IFFT here"
urlfront = 'https://maker.ifttt.com/trigger/' # add trigger string name here
urlback = '/with/key/' + IFTTT_MAKER_KEY # Set destination URL here

oldweight = 0.0 # oldweight currently not working / not being preserved / TBD for display of previous value taken



class EventProcessor:
    def __init__(self):
        self._measured = False
        self.done = False
        self._measureCnt = 0
        self._events = range(WEIGHT_SAMPLES)

    def mass(self, event):
        successful_mass = 0;
        if (event.totalWeight > 2):
            self._events[self._measureCnt] = event.totalWeight*2.20462
            self._measureCnt += 1
            if self._measureCnt == WEIGHT_SAMPLES:
                self._sum = 0
                for x in range(0, WEIGHT_SAMPLES-1):
                    self._sum += self._events[x]
                self._weight = self._sum/WEIGHT_SAMPLES
                self._measureCnt = 0
                
                weighVal = float("{0:.2f}".format(self._weight))
                successful_mass = weighVal
            else:
#                successful_mass = self._events[self._measureCnt]
                successful_mass = 1

            if not self._measured:
                self._measured = True

        return successful_mass

    @property
    def weight(self):
        if not self._events:
            return 0
        histogram = collections.Counter(round(num, 1) for num in self._events)
        return histogram.most_common(1)[0][0]

    def resetdatasamples(self):
        self._measureCnt = 0
        self._measured = False

class BoardEvent:
    def __init__(self, topLeft, topRight, bottomLeft, bottomRight, buttonPressed, buttonReleased):

        self.topLeft = topLeft
        self.topRight = topRight
        self.bottomLeft = bottomLeft
        self.bottomRight = bottomRight
        self.buttonPressed = buttonPressed
        self.buttonReleased = buttonReleased
        #convenience value
        self.totalWeight = topLeft + topRight + bottomLeft + bottomRight

class Wiiboard:
    def __init__(self, processor,term):
        # Sockets and status
        self.receivesocket = None
        self.controlsocket = None

        self.processor = processor
        self.term = term
        self.display = term
        self.calibration = []
        self.calibrationRequested = False
        self.LED = False
        self.address = None
        self.buttonDown = False
        self.buttonbeenreleased = False
        for i in xrange(3):
            self.calibration.append([])
            for j in xrange(4):
                self.calibration[i].append(10000)  # high dummy value so events with it don't register

        self.status = "Disconnected"
        self.lastEvent = BoardEvent(0, 0, 0, 0, False, False)

        try:
            self.receivesocket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
            self.controlsocket = bluetooth.BluetoothSocket(bluetooth.L2CAP)
        except ValueError:
            raise Exception("Error: Bluetooth not found")

    def isConnected(self):
        return self.status == "Connected"

    # Connect to the Wiiboard at bluetooth address <address>
    def connect(self, address):
        if address is None:
            print "Non existant address"
            return
        self.receivesocket.connect((address, 0x13))
        self.controlsocket.connect((address, 0x11))
        if self.receivesocket and self.controlsocket:
            print "Connected to Wiiboard at address " + address
            self.status = "Connected"
            self.address = address
        
            self.term.println("PiScales connected")
            print "oldweight " + str(oldweight)
            if (oldweight>0.0):
                self.term.println("last W: ".format(oldweight))
            
            #self.term.println("Wiiboard connected:\n{0} ".format(address));
        
            # now wait 5 secs to allow board to be set flat before calibration
            # flash slowly to indiate waiting to start cal
            # ideally measure to determine when flat and then calibrate...
        
            # Add local screen write
            print "Place flat for calibration "
            self.term.puts("Flat for calibration")
            for mill in range(0, 10):
                self.term.puts(".")
                self.term.flush()
                self.wait(500)
        
            print "stable, now calibrating.."
            self.calibrate()
            useExt = ["00", COMMAND_REGISTER, "04", "A4", "00", "40", "00"]
            self.send(useExt)
            self.setReportingType()
            self.term.puts("\rCalibrated")
            self.term.puts("\nStep onto the scales")
            self.term.flush()
            print "Wiiboard connected"
        else:
            print "Could not connect to Wiiboard at address " + address
            self.term.println("\rError connecting")

    def receive(self):
        flushreceive = False
        while self.status == "Connected" and not self.processor.done:
            data = self.receivesocket.recv(25)
            #print '.' + data[2:4] + '.',
            intype = int(data.encode("hex")[2:4])
            if intype == INPUT_STATUS:
                # TODO: Status input received. It just tells us battery life really
                self.setReportingType()
            elif intype == INPUT_READ_DATA:
                if self.calibrationRequested:
                    packetLength = (int(str(data[4]).encode("hex"), 16) / 16 + 1)
                    self.parseCalibrationResponse(data[7:(7 + packetLength)])

                    if packetLength < 16:
                        self.calibrationRequested = False
                        print "calibrated ??? - " + str(packetLength)
                        for i in xrange(3):
                            self.wait(200)
                            self.setLight(False)
                            self.wait(800)
                            self.setLight(True)

            elif intype == EXTENSION_8BYTES:
                value = self.processor.mass(self.createBoardEvent(data[2:12]))
                    
                if (not flushreceive): # only process if not flushing
                    if (value>1):
                        # flash the wii fit board in case this is headless on completion of reading
                        print "final measured weight value"
                        self.term.println("\rWeight:{0}lbs  ".format(value))
                        print "Weight: " + str(value) + " lbs"
                        oldweight = value
                        print "oldweight " + str(oldweight)

                        # put check in place to only send to fitbit if > 130lbs#                
                        tmpVar = time.strftime("%x %I:%M %p")
                        if (value > MIN_WEIGHT_TO_POST):
                            requests.post(urlfront + WIIFIT_TRIGGER + urlback, data = {'value1': value, 'value2' : tmpVar})
                        print "Wiipost -"+ urlfront + WIIFIT_TRIGGER + urlback + ' value1 ' + str(value) + ' value2 ' + tmpVar

                        print "Flash the board to indicate complete"
                        for x in xrange(16): #even num - make sure even ending to keep light on
                            self.setLight(x%2)
                            self.wait(350)
                        #print "Flashed the board"
                    
                        # once a collection of data has been received and processes, there will be a buffer
                        #  of more data to receive (flush the cache)
                        #  so setup a flag to receive the data/flush it but not toggle any displays
                        flushreceive = True

                    elif (value==1):
                            #toggle while reading weight - show its measuring
                            #for x in xrange(16): #even num - make sure even ending to keep light on
                        if (self.processor._measureCnt%(WEIGHT_SAMPLES/10)==1):
                            self.toggleLight()
                            self.term.puts(".")
                            self.term.flush()
                        
                # values being received are now small enough that nothing is on the wiiboard
                #  and thus can begin again
                if (value==0):
                    flushreceive = False
                    self.processor.resetdatasamples()

                if (self.buttonbeenreleased == True):
                    print "Bdown - disconnecting"
                    self.term.println("\nShutting Down")
                    self.term.println("Have a fun day..")

                    for x in xrange(16): #make sure even ending to keep light on
                        self.toggleLight()
                        self.wait(150)
                    self.disconnect()
                    #print "Bdown - disconnecting ...."
                    raise NameError("Button - exit time")
                    break
            else:
                print "ACK to data write received"

    def disconnect(self):
        if self.status == "Connected":
            self.status = "Disconnecting"
            #while self.status == "Disconnecting":
            #    self.wait(100)
        try:
            self.receivesocket.close()
        except:
            pass
        try:
            self.controlsocket.close()
        except:
            pass
        print "WiiBoard disconnected"

    # Try to discover a Wiiboard
    def discover(self):
        print "Press the red sync button on the board now"
        address = None
        bluetoothdevices = bluetooth.discover_devices(duration=6, lookup_names=True)
        for bluetoothdevice in bluetoothdevices:
            if bluetoothdevice[1] == BLUETOOTH_NAME:
                address = bluetoothdevice[0]
                print "Found Wiiboard at address " + address
        if address is None:
            print "No Wiiboards discovered."
            self.term.println("No Wiiboards found")
        return address

    def createBoardEvent(self, bytes):
        buttonBytes = bytes[0:2]
        bytes = bytes[2:12]
        buttonPressed = False
        buttonReleased = False

        state = (int(buttonBytes[0].encode("hex"), 16) << 8) | int(buttonBytes[1].encode("hex"), 16)
        if state == BUTTON_DOWN_MASK:
            buttonPressed = True
            self.buttonbeenreleased = False;
            if not self.buttonDown:
                print "Button pressed"
                self.buttonDown = True

        elif not buttonPressed:
            if self.buttonDown:
                self.buttonbeenreleased = True;
                buttonReleased = True
                self.buttonDown = False
                print "Button released"

        rawTR = (int(bytes[0].encode("hex"), 16) << 8) + int(bytes[1].encode("hex"), 16)
        rawBR = (int(bytes[2].encode("hex"), 16) << 8) + int(bytes[3].encode("hex"), 16)
        rawTL = (int(bytes[4].encode("hex"), 16) << 8) + int(bytes[5].encode("hex"), 16)
        rawBL = (int(bytes[6].encode("hex"), 16) << 8) + int(bytes[7].encode("hex"), 16)

        topLeft = self.calcMass(rawTL, TOP_LEFT)
        topRight = self.calcMass(rawTR, TOP_RIGHT)
        bottomLeft = self.calcMass(rawBL, BOTTOM_LEFT)
        bottomRight = self.calcMass(rawBR, BOTTOM_RIGHT)
        boardEvent = BoardEvent(topLeft, topRight, bottomLeft, bottomRight, buttonPressed, buttonReleased)
        return boardEvent

    def calcMass(self, raw, pos):
        val = 0.0
        #calibration[0] is calibration values for 0kg
        #calibration[1] is calibration values for 17kg
        #calibration[2] is calibration values for 34kg
        if raw < self.calibration[0][pos]:
            return val
        elif raw < self.calibration[1][pos]:
            val = 17 * ((raw - self.calibration[0][pos]) / float((self.calibration[1][pos] - self.calibration[0][pos])))
        elif raw > self.calibration[1][pos]:
            val = 17 + 17 * ((raw - self.calibration[1][pos]) / float((self.calibration[2][pos] - self.calibration[1][pos])))

        return val

    def getEvent(self):
        return self.lastEvent

    def getLED(self):
        return self.LED

    def parseCalibrationResponse(self, bytes):
        index = 0
        if len(bytes) == 16:
            for i in xrange(2):
                for j in xrange(4):
                    self.calibration[i][j] = (int(bytes[index].encode("hex"), 16) << 8) + int(bytes[index + 1].encode("hex"), 16)
                    index += 2
        elif len(bytes) < 16:
            for i in xrange(4):
                self.calibration[2][i] = (int(bytes[index].encode("hex"), 16) << 8) + int(bytes[index + 1].encode("hex"), 16)
                index += 2

    # Send <data> to the Wiiboard
    # <data> should be an array of strings, each string representing a single hex byte
    def send(self, data):
        if self.status != "Connected":
            return
        data[0] = "52"

        senddata = ""
        for byte in data:
            byte = str(byte)
            senddata += byte.decode("hex")

        self.controlsocket.send(senddata)

    #Turns the power button LED on if light is True, off if False
    #The board must be connected in order to set the light
    def setLight(self, light):
        if light:
            val = "10"
        else:
            val = "00"

        message = ["00", COMMAND_LIGHT, val]
        self.send(message)
        self.LED = light

    def toggleLight(self):
        if self.LED:
            val = "00"
        else:
            val = "10"
        message = ["00", COMMAND_LIGHT, val]
        self.send(message)
        self.LED = not self.LED
                

    def calibrate(self):
        message = ["00", COMMAND_READ_REGISTER, "04", "A4", "00", "24", "00", "18"]
        self.send(message)
        self.calibrationRequested = True

    def setReportingType(self):
        bytearr = ["00", COMMAND_REPORTING, CONTINUOUS_REPORTING, EXTENSION_8BYTES]
        self.send(bytearr)

    def wait(self, millis):
        time.sleep(millis / 1000.0)

#OLED Font routine
def make_font(name, size):
    font_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'fonts', name))
    return ImageFont.truetype(font_path, size)

def main():
    #setup local OLED screen
    fontname = "ProggyTiny.ttf"
    size = 16
    font = make_font(fontname, size) if fontname else None
    # if i2c then use i2c()
    serial = spi(device=0, port=0) 
    # change device type here if needed, this also rotates display 180 - i.e. if gpio connector on bottom of display
    device = sh1106(serial, rotate=2) 
    term = terminal(device, font)
#    term.clear()
    term.animate = True

    processor = EventProcessor()
    board = Wiiboard(processor,term)
    
    address = None
    if len(sys.argv) == 1:
        print "Discovering board..."
        #term.puts("\rHunting........\r")
        #term.puts("\nPress the red button\n")
        #term.flush()
        address = board.discover()
    else:
        address = sys.argv[1]
        #term.puts("\rConnecting known dev.\r")
        #term.puts("\nPress the red button\n")
        #term.flush()

    try:
        # Disconnect already-connected devices.
        # This is basically Linux black magic just to get the thing to work.
        subprocess.check_output(["bluez-test-input", "disconnect", address], stderr=subprocess.STDOUT)
        subprocess.check_output(["bluez-test-input", "disconnect", address], stderr=subprocess.STDOUT)
    except:
        pass

    if address is None:
        print ("No address to connect to, bailing out")
        time.sleep (2)
        return
    print "Trying to connect..."
    term.animate = False
    board.connect(address)  # The wii board must be in sync mode at this time
    board.wait(200)
    board.setLight(False)
    board.wait(500)
    board.setLight(True)
    # go weigh :)
    board.receive()


if __name__ == "__main__":
    while 1:
        try:
            main()
        except KeyboardInterrupt:
            #time.sleep(5)
            exit()
        except:
            print "finishd one round sleeping for a bit...."
        # good to let sleep for a while - otherwise 2.4G band tended to get a little slammed
        time.sleep (5)
        print "trying again...."
