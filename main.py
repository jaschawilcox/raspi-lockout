#!/usr/bin/python
###  _____ _            _____                 _                   _
### |_   _| |          /  __ \               | |                 | |
###   | | | |__   ___  | /  \/ ___  _ __  ___| |_ _ __ _   _  ___| |_
###   | | | '_ \ / _ \ | |    / _ \| '_ \/ __| __| '__| | | |/ __| __|
###   | | | | | |  __/ | \__/\ (_) | | | \__ \ |_| |  | |_| | (__| |_
###   \_/ |_| |_|\___|  \____/\___/|_| |_|___/\__|_|   \__,_|\___|\__|
###
### Machine Lockout controller
### Jascha Wilcox 2015

# Built-in
import time
from time import sleep

import sys, select, threading
import hashlib
import re
import copy
import json, csv
import logging

# Google sheets
import gspread
from oauth2client.client import SignedJwtAssertionCredentials

# Hardware interface
import lcddriver
import RPi.GPIO as GPIO

# Fetch this machine's wifi MAC address
with open('/sys/class/net/wlan0/address') as f:
    MYMAC = f.read()[:17]

# Globals
ESTOP_CHANNEL       = 17 # Estop on model B+ GPIO 17 (pin 11)
RELAY_CHANNE        = 4  # Relay on model B+ GPIO 4 (pin 7)
BUZZER_CHANNEL      = 27 # Buzzer on model B+ GPIO 27 (pin 13)
LED_CHANNEL_RED     = 22 # Red LED on model B+ GPIO 22 (pin 15)
LED_CHANNEL_GREEN   = 23 # Green LED on model B+ GPIO 22 (pin 16)

class states():
    """
    Enumerated operating states
    """
    locked      = 0
    unlocked    = 1
    estop       = 2

def setMachineEnable(state = False):
    """
    Open and close the e-stop relay
    """
    ### !!!BEWARE, RELAY MODULE IS ACTIVE LOW!!!
    if state:
        GPIO.output(RELAY_CHANNEL, GPIO.LOW) # closes relay
    else:
        GPIO.output(RELAY_CHANNEL, GPIO.HIGH) # opens relay
    print 'Machine enabled?:', state

def initHardware():
    """
    Setup raspi GPIO
    """
    GPIO.setmode(GPIO.BCM)
    # Estop input active low (pull-up)
    GPIO.setup(ESTOP_CHANNEL, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # RELAY IS ACTIVE LOW!!!
    GPIO.setup(RELAY_CHANNEL, GPIO.OUT, initial=GPIO.HIGH)

    # Buzzer and LED active high
    GPIO.setup(BUZZER_CHANNEL, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(LED_CHANNEL_RED, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(LED_CHANNEL_GREEN, GPIO.OUT, initial=GPIO.LOW)

def spreadsheetWorker(config, session):
    """
    Thread periodically updating the local config file from google sheets
    """
    # These credentials can be obtained for your account at the google developer console
    with open('googleCredentials.json','r') as f:
        json_key = json.load(f)

    scope = ['https://spreadsheets.google.com/feeds']
    credentials = SignedJwtAssertionCredentials(json_key['client_email'], json_key['private_key'], scope)

    while True:
        try:
            # Login to google spreadsheets
            gs = gspread.authorize(credentials)
            configSpreadsheet = gs.open("config")
            logSpreadsheet = gs.open("logs")
            print "Opened spreadsheets."
        except:
            print "Can't get to spreadsheet, internet down?"

        try:
            # Open up worksheets and import lists
            userConfig = configSpreadsheet.worksheet('userConfig').get_all_values()
            machineConfig = configSpreadsheet.worksheet('machineConfig').get_all_values()

            # Update file and local data
            config.setFile({'userConfig':userConfig, 'machineConfig':machineConfig})

            print "Successfully updated config.json"
        except:
            print "Something went wrong trying to update the config file..."

        try:
            thisMachine = config.getDict()['machine'][MYMAC]['name']
            logWorksheet = logSpreadsheet.worksheet(thisMachine)

            logs = session.getLogs()
            if len(logs) > 0:
                for r in logs:
                    logWorksheet.insert_row(r, index = 2)
                session.setLogs([])
                print "Wrote logs to spreadsheet"
        except:
            print "Unable to write logs"

        # Update every so often
        sleep(600)

class Configuration(object):
    """
    Takes care of all handling config storage and access
    """
    def __init__(self):
        with open('config.json','r') as f:
            self._configFile = json.load(f)
        self._configDict = self.parseConfigFile(self._configFile)

        # We need this to protect shared access to configDict
        self._configLock = threading.RLock()

    def getDict(self):
        """Return dict of config spreadsheets"""
        # Is this copy necessary???
        with self._configLock:
            safeDict = copy.deepcopy(self._configDict)
        return safeDict

    def setFile(self, content):
        with open('config.json','w') as f:
            f.write(json.dumps(content))
        self._configFile = content
        with self._configLock:
            self._configDict = self.parseConfigFile(self._configFile)

    def parseConfigFile(self, content):
        config = {'machine':{},'user':{}}
        configWorksheets = {'machine':'machineConfig','user':'userConfig'}

        for c in config:
            worksheet = content[configWorksheets[c]]
            for row in worksheet[1:]:
                config[c][row[0]] = dict(zip(worksheet[0][1:], row[1:]))

        return config

class Display(object):
    """
    Handles what gets displayed on the LCD
    """
    def __init__(self, session):
        self._session = session

        # Setup hardware
        self._lcd = lcddriver.lcd()
        self._lcd.lcd_clear()

        self._state = states.locked

        self._timestr = ''
        self._messageTimeout = 0
        self.update()

    def setState(self, state):
        self._state = state

        if self._state == states.locked:
            self._lcd.setLines(\
                ["*******LOCKED*******",
                "  Ready to swipe.   ",
                "",
                time.ctime()[:20]])
        elif self._state == states.estop:
            self._lcd.setLines(\
                ["*******LOCKED*******",
                "E-Stop is depressed!",
                "",
                time.ctime()[:20]])
        elif self._state == states.unlocked:
            expires = self._session.getTimeEnd()
            remaining = time.strftime('%H:%M:%S', time.gmtime(expires - time.time()))
            self._lcd.setLines(\
                ["  MACHINE UNLOCKED  ",
                self._session.getUserName(),
                "Unlocked:  " + time.ctime(self._session.getTimeStart())[11:19] ,
                "Remaining: " + remaining ])

    def showMessage(self, message, duration = 3):
        """
        Show a message string for duration seconds
        """
        print message
        self._lcd.lines = ['','','','']
        msgLines = re.findall('.{0,19}[ |.|!|?]',message)[:3]
        for i, l in enumerate(msgLines):
            self._lcd.lines[i] = l

        # Display for some time
        self._messageTimeout = time.time() + duration

    def update(self):
        if time.time() >= self._messageTimeout:
            self.setState(self._state)
        self._lcd.update()

class UseSession(object):
    """
    Handle session reading and writing
    """
    def __init__(self, config):
        self._config = config

        self._userName = ''
        self._timeStart = 0
        self._timeEnd = 0
        self._active = False

        self._log = []
        self.lock = threading.RLock()

    def getTimeEnd(self):
        return self._timeEnd

    def getTimeStart(self):
        return self._timeStart

    def getTimeRemain(self):
        return self._timeEnd - time.time()

    def getUserName(self):
        return self._userName

    def new(self, hash):
        self._userName = self._config.getDict()['user'][hash]['name']
        self._timeStart = time.time()
        self._timeEnd = self._timeStart + (int(self._config.getDict()['machine'][MYMAC]['timeout']) * 60)
        self._active = True

    def extend(self):
        self._timeEnd = time.time() + (int(self._config.getDict()['machine'][MYMAC]['timeout']) * 60)

    def getLogs(self):
        with self.lock:
            return self._log

    def setLogs(self, values):
        with self.lock:
            self._log = values

    def end(self, event):
        if self._active:
            self.writeLog(event)
            self._active = False

    def writeLog(self, event='None'):
        with self.lock:
            self._log.append([self._userName, time.ctime(self._timeStart), \
                time.ctime(time.time()), event])
            
            with open('sessionlog.csv', 'wb') as sLog:
                sLogWriter = csv.writer(sLog)
                sLogWriter.writerow(self._log[-1])

class Indicator(object):
    """
    Used for concurrent control of signaling indicators such as buzzers,
    lights, etc
    """
    def __init__(self, pins):
        self.count = 0
        self.continuous = False
        self.invert = False
        self.delay = 1

        self.enabled = False
        self._pins = pins

        self.lock = threading.Condition()
        self.thread = threading.Thread(target = self.blinkWorker)
        self.thread.setDaemon(True)
        self.thread.start()

    def toggle(self):
        with self.lock:
            self.enabled = not self.enabled
        self.writePins(self.enabled)

    def pulse(self, count = 0, continuous = False, invert = False, delay = 1):
        with self.lock:
            self.count, self.continuous = count, continuous
            self.delay, self.invert = delay, invert
            self.lock.notify()

    def setEnable(self, state = False):
        with self.lock:
            self.count, self.continuous = 0, False
            self.enabled = state
        self.writePins(self.enabled)

    def on(self):
        self.setEnable(True)

    def off(self):
        self.setEnable(False)

    def writePins(self, on=True):
        for p in self._pins.values():
            if p['state'] and on:
                GPIO.output(p['pin'], GPIO.HIGH)
            else:
                GPIO.output(p['pin'], GPIO.LOW)

    def blinkWorker(self):
        while True:
            self.lock.acquire()
            if self.continuous or self.count:
                self.toggle()
                if self.count and not (self.invert ^ self.enabled):
                    self.count -= 1
                # Wait for pulse timeout, or wakeup
                self.lock.wait(self.delay)
            else:
                # Wait until wakeup
                self.lock.wait()
            self.lock.release()

class LED(Indicator):
    def setColor(self, color):
        """Set the indicator to red/yellow/green"""
        if color == 'red':
            self._pins['red']['state'] = True
            self._pins['green']['state'] = False
        elif color == 'yellow':
            self._pins['red']['state'] = True
            self._pins['green']['state'] = True
        elif color == 'green':
            self._pins['red']['state'] = False
            self._pins['green']['state'] = True
        self.writePins(self.enabled)

    def on(self, color = None):
        self.setEnable(True)
        if color != None:
            self.setColor(color)

class Machine(object):
    def __init__(self):
        self._state = states.locked
        
    def updateState(self, newState):
        if self._state == states.unlocked:
            if newState == states.locked:
                pass
            elif newState == states.estop:
                pass
            else:
                pass
        elif self._state == states.locked:
            if newState == states.unlocked:
                pass
            elif newState == states.estop:
                pass
            else:
                pass
        elif self._state == states.estop:
            if newState == states.locked:
                pass
            elif newState == states.estop:
                pass
            else:
                pass
        self._state = newState

def main():
    # Setup hardware
    try:
        initHardware()
    except RuntimeError:
        print "Unable to setup GPIO. Need sudo?"
        raise

    state   = states.locked
    timeoutWarning = False

    config  = Configuration()
    session = UseSession(config)

    disp    = Display(session)
    disp.setState(state)

    buzzer  = Indicator({'buzzer':{'pin':BUZZER_CHANNEL,'state':True}})
    led     = LED({'red':{'pin':LED_CHANNEL_RED,'state':True},'green':{'pin':LED_CHANNEL_GREEN,'state':False}})
    led.on(color = 'red')

    ssDaemon = threading.Thread(target=spreadsheetWorker, args=(config,session,))
    ssDaemon.setDaemon(True)
    ssDaemon.start()

    disp.showMessage("Waiting for spreadsheet update.")
    disp.update()
    sleep(10)

    try:
        thisMachine = config.getDict()['machine'][MYMAC]['name']
    except KeyError:
        disp.showMessage('Unknown machine MAC.')
        led.setColor('yellow')
        raise

    while True:
        # Check if a card has been swiped
        if select.select([sys.stdin,],[],[],0.0)[0]:
            raw = sys.stdin.readline()

            # Validate ID
            try:
                uid = re.search('[0-9]+',raw).group(0)
                idhash = hashlib.sha256(uid).hexdigest()
                level = int(config.getDict()['user'][idhash][thisMachine])
                print "Access level:", level
            except:
                disp.showMessage('Unknown ID.')
                buzzer.pulse(count = 3, delay = 0.1)
                continue

            # Determine state change
            if state == states.estop:
                disp.showMessage("Estop is depressed!")
                led.pulse(count = 3, delay = 0.5, invert = True)
                buzzer.pulse(count = 3, delay = 0.1)
            elif level < 10:
                disp.showMessage('Sorry, you need to be trained to use this machine.')
                buzzer.pulse(count = 3, delay = 0.1)
            else:
                if state == states.locked:
                    # Unlock the machine
                    session.new(idhash)
                    print "Welcome", session.getUserName()
                    state = states.unlocked
                    led.on(color = 'green')
                    disp.setState(state)
                    setMachineEnable(True)
                    buzzer.pulse(count = 2, delay = 0.1)
                    timeoutWarning = False
                elif state == states.unlocked:
                    # Extend session
                    session.extend()
                    disp.showMessage("Extending session.")
                    led.on(color = 'green')
                    buzzer.pulse(count = 2, delay = 0.1)
                    timeoutWarning = False

        if not GPIO.input(ESTOP_CHANNEL): # Shorted pull-up
            # Estop is depressed!
            if state != states.estop:
                # Estop pressed, lock machine
                disp.showMessage("EStop, Locking machine!")
                state = states.estop
                session.end("estop")
                led.on(color = 'red')
                disp.setState(state)
                setMachineEnable(False)
        else:
            # Normal operation
            if state == states.estop:
                # Estop released, set to locked state
                state = states.locked
                led.setColor('red')
                led.on()
                disp.setState(state)
                setMachineEnable(False)
            elif state == states.unlocked:
                if session.getTimeRemain() <= 0:
                    # Session timeout exceeded, lock machine
                    disp.showMessage("Timeout, Locking machine!")
                    state = states.locked
                    session.end("timeout")
                    led.on(color = 'red')
                    disp.setState(state)
                    setMachineEnable(False)
                if session.getTimeRemain() <= 600 and not timeoutWarning:
                    # Session ending soon, warn user
                    disp.showMessage("Session expiring soon, extend session!", duration = 10)
                    led.setColor('yellow')
                    led.pulse(continuous = True)
                    buzzer.pulse(count = 5)
                    timeoutWarning = True
        disp.update()
        sleep(1)

if __name__ == "__main__":
    main()
