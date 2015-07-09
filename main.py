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

import time
from time import sleep
import sys, select, threading
import hashlib
import re
import copy
import json

# Google sheets
import gspread
from oauth2client.client import SignedJwtAssertionCredentials

# Hardware interface
import lcddriver
import RPi.GPIO as GPIO

MYMAC = open('/sys/class/net/eth0/address').read()
MACHINE = 'tormach'

ESTOP_CHANNEL = 17
RELAY_CHANNEL = 21

def setMachineEnable(state = False):
   """Open and close the e-stop relay"""
   ### !!!BEWARE, RELAY MODULE IS ACTIVE LOW!!!
   if state:
      GPIO.output(RELAY_CHANNEL, GPIO.LOW) # closes relay
   else:
      GPIO.output(RELAY_CHANNEL, GPIO.HIGH) # opens relay
   print 'Machine enabled?:', state

def updateSpreadsheetWorker(config):
   """Thread updating the local config file from google sheets"""
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
         print "Opened spreadsheet."   
         
         try:
            # Open up worksheets and import lists
            userConfig = configSpreadsheet.worksheet('userConfig').get_all_values()
            machineConfig = configSpreadsheet.worksheet('machineConfig').get_all_values()
            
            # Update file and local data
            config.setFile({'userConfig':userConfig, 'machineConfig':machineConfig})

            print "Successfully updated config.json"
         except:
            print "Something went wrong trying to update the config file..."
      except:
         print "Can't get to spreadsheet, internet down?"

      # Update every so often
      sleep(600)

class configuration():
   """Takes care of all handling config storage and access"""
   def __init__(self):
      with open('config.json','r') as f:
         self._configFile = json.load(f)
      self._configDict = self.parseConfigFile(self._configFile)
      
      # We need this to protect shared access to configDict
      self._configLock = threading.Lock()
      
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

      for c in config
         worksheet = content[configWorksheets[c]]
         for row in worksheet[1:]:
            config[c][row[0]] = dict(zip(worksheet[0][1:], row[1:]))
      
      return config

class display():
   """Handles what gets displayed on the LCD"""
   def __init__(self, session):
      self._session = session
      
      # Setup hardware
      self._lcd = lcddriver.lcd()
      self._lcd.lcd_clear()
      
      self._state = 'locked'

      self._timestr = ''
      self._messageTimeout = 0
      self.update()

   def setState(self, state):
      self._state = state
      
      if self._state == 'locked':      
         self._lcd.lines = \
            ["*******LOCKED*******",
            "  Ready to swipe.   ",
            "",
            time.ctime()[:20]]
      elif self._state == 'estop':      
         self._lcd.lines = \
            ["*******LOCKED*******",
            "E-Stop is depressed.",
            "",
            time.ctime()[:20]]
      elif self._state == 'unlocked':
         expires = self._session.getTimeEnd()
         remaining = time.strftime('%H:%M:%S', time.gmtime(expires - time.time()))
         self._lcd.lines = \
            ["  MACHINE UNLOCKED  ",
            self._session.getUserName(),
            "Unlocked:  " + time.ctime(self._session.getTimeStart())[11:19] ,
            #"Remaining: " + time.ctime(self._session.getTimeEnd())[11:16] ]
            "Remaining: " + remaining ]
      
   def showMessage(self, message, duration = 3):
      """Show a message string for duration seconds"""
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
      self._lcd.writeLines()

class useSession():
   def __init__(self, config):
      self._config = config
      
      self._userName = ''
      self._timeStart = 0
      self._timeEnd = 0
   
   def getTimeEnd(self):
      return self._timeStart + (float(self._config.getDict()['machine'][MYMAC]['timeout']) * 60)
   
   def getTimeStart(self):
      return self._timeStart
      
   def getUserName(self):
      return self._userName
      
   def new(self, hash):
      self._userName = self._config.getDict()['user'][hash]['name']
      self._timeStart = time.time()

def main():
   # Setup hardware
   try:
      GPIO.setmode(GPIO.BCM)
      
      # Estop on model B+ GPIO 17 (pin 11)
      GPIO.setup(ESTOP_CHANNEL, GPIO.IN, pull_up_down=GPIO.PUD_UP)
      #GPIO.add_event_detect(ESTOP_CHANNEL, GPIO.FALLING)
      
      # Relay on model B+ GPIO 21 (pin 40)
      GPIO.setup(RELAY_CHANNEL, GPIO.OUT, initial=GPIO.HIGH)
   except:
      print "Unable to setup GPIO. Need sudo?"
   
   state = 'locked'
   
   config = configuration()
   session = useSession(config)

   disp = display(session)
   disp.setState(state)
   
   ssDaemon = threading.Thread(target=updateSpreadsheetWorker, args=(config,))
   ssDaemon.setDaemon(True)
   ssDaemon.start()
   
   while(True):
      # Check if a card has been swiped
      if select.select([sys.stdin,],[],[],0.0)[0]:
         raw = sys.stdin.readline()
      
         # Validate ID
         try:
            id = re.search('[0-9]+',raw).group(0)
            idhash = hashlib.sha256(id).hexdigest()
            level = int(config.getDict()['user'][idhash][MACHINE])
            print "Access level:", level
         except:
            disp.showMessage('Unknown ID.')
            continue
            
         # Determine state change
         if state == 'estop':
            disp.showMessage("Estop is depressed!")
         elif level < 10:
            disp.showMessage('Sorry, you need to be trained to use this machine.')
         else:
            if state == 'locked':
               # Unlock the machine
               session.new(idhash)
               print "Welcome", session.getUserName()
               state = 'unlocked'
               disp.setState(state)
               setMachineEnable(True)
               
            elif state == 'unlocked':
               # Extend session
               session.new(idhash)
               disp.showMessage("Extending session.")
      
      if not GPIO.input(ESTOP_CHANNEL):
         # Estop is depressed!
         if state != 'estop':
            # Estop pressed, lock machine
            disp.showMessage("EStop, Locking machine!")
            state = 'estop'
            disp.setState(state)
            setMachineEnable(False)  
      else:
         # Normal operation
         if state == 'estop':
            # Estop released, set to locked state
            state = 'locked'
            disp.setState(state)
            setMachineEnable(False)
         elif state == 'unlocked':
            if time.time() >= session.getTimeEnd():
               # Session timeout exceeded, lock machine
               disp.showMessage("Timeout, Locking machine!")
               state = 'locked'
               disp.setState(state)
               setMachineEnable(False)     
      
      disp.update()
      sleep(1)

if __name__ == "__main__":
   main()