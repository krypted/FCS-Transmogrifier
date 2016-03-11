#!/usr/bin/python
# -*- coding: utf-8 -*-

################################
##
##  Transmogrifier: transmogrifier.py
##  A Final Cut Server import/export tool 
##
##  This script serves as the command line interface to the Transmogrifier
##  Framework.
## 
##  It's amazing what they do with corrugated cardboard these days...
##
##
##
#############################################################


import sys, getopt, re, os, os.path, string, types, datetime, time
import fcsxml
from brightcove import BrightCoveObject
from youtube import YouTubeObject
from thePlatform import thePlatformObject
from shakeblender import ShakeBlenderObject

#from pcpblender import PCPBlenderObject
#from filemaker import FileMakerObject
#from sftp import sftpObject

from transmogrifierTarget import *
from ConfigParser import *

## init our vars
version = "1.0b"
build = "2011042001"
validActions = [] ## todo: determine these from our validTarget objects
validModules = []

## Change this to 1.0 if you aren't using 1.5 todo: check this dynamically
## Warning: the vast majority of Transmogrifier functionality has not been 
## vetted under 1.0 (Use 1.5)
fcsMajorVersion = "1.5"


global debug
debug = False
forceDebug = True


######################### START FUNCTIONS ###############################

def helpMessage():
  '''This function outputs transmogrifier usage syntax and help.'''
  
  print '''Usage: 
  
  transmogrifier.py [options] [target]
  transmogrifier.py [-f configfile] [-d supportdir] [-a action] [-t mediatitle]
  
  Working with assets:
    transmogrifier.py --setField="Keywords" --value="MyAsset" -t MyAsset
    transmogrifier.py --setField="Keywords" --value="MyAsset" -i /fcsxmlinfile.xml
    transmogrifier.py --appendField="Status" --value="Update!" -i /fcsxmlinfile.xml
        
    transmogrifier.py --getAssetID --assetPath="/FCS/Media/myfile.mpg"
    transmogrifier.py --getEntityPath --assetID=1
    transmogrifier.py --getFilePath --assetID=1
    transmogrifier.py --getArchiveFilePath --assetID=1
    transmogrifier.py --getThumbnailPath --assetID=1
    transmogrifier.py --getProxyPath --assetID=1
    transmogrifier.py --getPosterFramePath --assetID=1
    transmogrifier.py --archive --assetID=1
    transmogrifier.py --restore --assetID=1
    transmogrifier.py --analyze --assetID=1
  
  Working with productions:
    transmogrifier.py --setField="Owner" --value="Calvin" --assetsWithProductionID=1
    transmogrifier.py --restore --productionID=1
    transmogrifier.py --buildProduction --productionID=1
    

  Working with devices:
    transmogrifier.py --getDeviceName --deviceID=1
    transmogrifier.py --getDeviceName --devicePath="/FCS/Media"
    transmogrifier.py --getDevicePath --deviceName="Media"
    transmogrifier.py --getDevicePath --deviceID=1
    transmogrifier.py --getDeviceID --deviceName="Media"
    transmogrifier.py --getDeviceID --devicePath="/FCS/Media"

  Working with Modules:
    transmogrifier.py --module=BrightCove -t MyAsset [-a action]
    transmogrifier.py --module=BrightCove -a preflightCheck|upload -t MyAsset
    transmogrifier.py -a createSupportFolders [-m BrightCove] [-d supportdir] 
    transmogrifier.py --module=BrightCove -a listFCSFields
    
    
Options: 
    -h, --help              Displays this help message
    -v, --version           Display version number
    -f configfilepath       Use specified config file
    -d supportdir           Path to support folder 
    --debug                 Run in debug mode
    
    --xmlout=               Specify a FCS XML file to write out.
    
    -m,--module=MODULE      Delivery Target: 'BrightCove', 'YouTube',etc..
    -a action               Perform the requested action. 
    
    --fcsvr_client          Utilise fcsvr_client for FCS I/O operations
                            This defaults to yes by default on certain operations
                            
    --nofcsvr_client        Under no circumstances utilize fcsvr_client for 
                            operations
    
    --getField=FIELD        Method to retrieve the value of FIELD
    --getDBField=FIELD      Method to retriev the value of FIELD using the 
                            Final Cut Server database field name.
    --setField=FIELD        Method to specify FIELD to set with --value
    --appendField=FIELD     Append the specified field FIELD with --value
        --value=value       Data to append to set or import to --field 
        --withtimestamp     Prepends a time stamp to STRING
        --notimestamp        Omits timestamp, if specified in config file
    
    --getAssetID            Outputs the assetID for specified target asset
    --getAssetPath          Outputs the asset's filesystem path
    --getEntityPath         Outputs the FCS address for specified target asset
    --getEntityMetadataSet  Outputs the metadata set associated with entity
    --getProxyPath          Outputs the asset's proxy path
    --getEditProxyPath      Outputs the asset's edit proxy path
    --getThumbnailPath      Outputs the asset's thumbnail path
    --getPosterFramePath    Outputs the asset's posterframe path
    
    --getDeviceName         Outputs the deviceName for specified target
    --getDevicePath         Outputs the device path for specified target
    --getDeviceID           Outputs the device id for the specified target
    
    --getProductionTitle    Outputs the production name of the specified target 
    --getProductionID       Outputs the production id of the specified target
    --addToProduction       Adds the specified asset to the specified production
    
    --archive               Archive the specified target
    --restore               Restore the specified target
    
    --filterMDSet=mdset     Filters targets to only those with the provided
                            metadaset (experimental)
    

Targets:
    -t title,--title=       Title of the XML file to read in, useful when 
                            using WriteXML response in FCS. 
                            Utilizes paths set in transmogrifier.conf
    --xmlin="/myfile.xml"   Specify a FCS XML file to read in. Overwrites -t
    --assetID=1             Asset with ID 1
    --assetPath="/myfile"   Asset residing at "/myfile"
    --assetTitle="title"    Asset with title "title"
    --productionID=1        Production with ID 1
    --productionTitle='title'     Production with title 'title'
    --productionTitleLike='title' Production with title matching substring 'title'
    --assetsFromProductionID=1  All assets from the specified production.
    --assetsFromProjectID=      All assets linked from the provided FCP project file
    --deviceID=1            Device with ID 1
    --deviceName="Media"    Device with name "Media"

Return Codes:
    0    Clean Execution
    1    Syntax Error
    2    Syntax Error: parameter missing
    3    One or more operations reported an error
    4    Invalid target
    5    Ambiguous/Conflicting Target
    6    Invalid Action
    7    fcsvr_client unavailable
    8    Error reading from source (bad XML, fcsvr_client error)
    9    Target(s) is(are) offline
   99    Unknown Error
    
   '''

def printVersionInfo():
  '''Prints out version info'''
  print (u"\nFCS transmogrifier\n  Version: %s Build: %s\n"
        "  Framework Version: %s Build: %s\n\n"
        "Copyright (C) 2009-2011 Beau Hunter, 318 Inc.\n" % (version,build,
                                                        fcsxml.version,
                                                        fcsxml.build
                                                        ))


def createSupportFolders(basePath, modules, configParser=''):
  '''Creates Support folder path utilized by various upload services, iterates 
  through modules defined in list 'validFormets' '''
  if not os.path.isdir(os.path.dirname(basePath)):
    print "Could not create folder structure, invalid path: '%s'" % basePath
    return False
      
  if not os.path.exists(basePath):
    print "Creating support folder: '%s'" % basePath
    os.mkdir(basePath)
  else: 
    print "Using support folder: '%s'" % basePath
          
  if not os.path.isdir(basePath):
    print "Non-directory object exists at path: '%s', exiting!" % basePath
    return False   
  
  ## generate our global Final Cut Server XML in folder
  fcsXMLDir = os.path.join(basePath,"fcsvr_xmlin")
  fcsXMLOutDir = os.path.join(basePath,"fcsvr_xmlout")
  if not os.path.isdir(fcsXMLDir):
    print "Creating fcsvr_xmlin directory."
    os.mkdir(fcsXMLDir)
  if not os.path.isdir(fcsXMLOutDir):
    print "Creating fcsvr_xmlout directory."
    os.mkdir(fcsXMLOutDir)
  
  ## test to see if we're passed a string, if so, convert it to a list
  if type(modules) == type("string"):
    modules = [modules]

  ## Iterate through our module objects and run the createSupportFolders method
  for module in modules:
    try:
      print "Creating folder structure for module: '%s'" % module 
      theObject = eval("%sObject()" % module)
      if configParser:
        theObject.loadConfiguration(configParser)
      theObject.debug = debug
      supportPath = os.path.join(basePath,module)
      supportPath = os.path.join(basePath,module)
      if not theObject.createSupportFolders(supportPath):
        print "Could Not create some or all support folders for module: '%s'" % module
    except:
      print "Problem creating module: '%sObject' may not be a valid class" % module
    print ""
        

def validActions(modules=validModules):
  '''Returns a list of all valid actions, based on provided modules.'''
    
  ## init our return var
  validActions = []
  
  ## add our transmogrifier default actions.
  try:
    validActions = TransmogrifierTargetObject.validActions
  except:
    pass
  
  ## Iterate through our loaded modules and aggregate their actions.
  for module in modules:
    #print "Testing module: %s" % module
    try:
      theClass = eval('%sObject()' % module)
    except:
      print 'Could not resolve class for module: %s' % module
    
    try:
      ##print " - module actions: %s" % ', '.join(theClass.validActions)
      validActions.extend(theClass.validActions)
    except:
      print 'Could not resolve actions for module: %s' % module
    
  ##print "DEBUG: resolved actions: %s" % validActions
  return validActions
  
  
  

######################### END FUNCTIONS #################################
       
######################### MAIN SCRIPT START #############################

def main():
  '''Our main function, filters passed arguments and loads the appropriate object'''
 
  ## Init vars
  basePath = ""
  fileTitle = ""
  configFile = ""
  module = ""
  action = ""
  xmlinPath = ""
  newString = ""
  fcsvr_client = True         ## Disabled by --nofcsvr_client
  fcsvr_client_all = False    ## Set by --fcsvr_client
  useTimeStamp=False
  keepFiles = False
  expectsValue = False    ## Used by our loop, the next opt should be a --value
  fields = {}             ## Fields as specified by our passed parameters
  targets = {}            ## Targets as specified by our passed parameters
  filters = {}            ## Target filters.
  useSecondTarget = False ## Whether our command has a second target.
  actions = []            ## Our actions
  exitCode = 0            ## Our Exit code
  
  global debug

  ## Get our flags
  try:
    optlist, list = getopt.getopt(sys.argv[1:],':hva:f:m:t:d::',["archive-type=",
      "action=","setField=","getField=","getDBField=","setBoolField=","title=",
      "action=","module=","appendField=","value=","xmlin","withtimestamp",
      "notimestamp","fcsvr_client","nofcsvr_client","help","version",
      "getAssetID","getAssetPath","getEntityPath","getEntityMetadataSet","getFilePath",
      "getProxyPath","getEditProxyPath","getPosterFramePath","getThumbnailPath",
      "getAssetTitle","getDeviceName","getDevicePath","getDeviceID","debug",
      "addToProduction","getProductionTitle","getProductionID","assetID=",
      "assetTitle=","assetPath=","assetsFromProductionID=","assetsFromProjectID=",
      "deviceID=","deviceName=","devicePath=","productionID=","productionTitle=",
      "productionTitleLike=","createProductionWithTitle=","filterMDSet=",
      "archive","restore","analyze","getArchivePath"])
  except getopt.GetoptError:
    print "Syntax Error!"
    helpMessage()
    return 1
  
  ## If no options are passed, output help
  if len(optlist) == 0:
    printVersionInfo()
    helpMessage()
    return 1
    
  #### PROCESS OUR PASSED ARGUMENTS ####
  for opt in optlist:
    if expectsValue:
      if opt[0] == '--value':
        newValue = opt[1].replace('\\n','\n').replace('\  ','  ')
        myField = fields[fieldName]
        myField["value"] = newValue
        expectsValue = False
        continue
      else:
        print "Syntax Error! --field or --appendField must be followed by --value="
        helpMessage()
        return 2
    else:
      if opt[0] == '--value':
        print "Syntax Error! --value must follow --field or --appendField!"
        helpMessage()
        return 2
    if opt[0] == '-h' or opt[0] == "--help":
      helpMessage()
      return 0
    elif opt[0] == '-v' or opt[0] == "--version":
      printVersionInfo()
      return 0
    elif opt[0] == '-d':
      basePath = opt[1]
    elif opt[0] == '-f':
      configFile = opt[1]
    elif opt[0] == '--filterMDSet':
      filters['mdSet'] = opt[1]
    elif opt[0] == "--fcsvr_client":
      fcsvr_client = True
      fcsvr_client_all = True
    elif opt[0] == "--nofcsvr_client":
      fcsvr_client = False
      fcsvr_client_all = False
    elif opt[0] == '-m' or opt[0] == "--module":
      module = opt[1]
    
    ## Read in our possible actions
    elif opt[0] == "--debug":
      debug = True
      forceDebug = True
    elif opt[0] == "--appendField":
      fieldName = opt[1]
      myaction = {"action":"appendField","fieldName":fieldName,"value":"",
              "timestamp":useTimeStamp,"targets":["asset","assets","project"],
              "sources":["fcsvr_client","fcsxml"]}
      fields[fieldName] = myaction
      action="appendField"
      if not fcsvr_client and not fcsvr_client_all:
        module="TransmogrifierTarget"
      actions.append(myaction)
      expectsValue = True      
    elif opt[0] == "--getField":
      fieldName = opt[1]
      myaction = {"action":"getField","fieldName":fieldName,"value":"",
                                    "targets":["asset","assets","project"],
                                    "sources":["fcsvr_client","fcsxml"]}
      fields[fieldName] = myaction
      actions.append(myaction)
      fields[fieldName] = myaction
      action="getField"
      if not fcsvr_client:
        module="TransmogrifierTarget"
    elif opt[0] == "--getDBField":
      fieldName = opt[1]
      myaction = {"action":"getDBField","fieldName":fieldName,"value":"",
                                    "targets":["asset","assets","project"],
                                    "sources":["fcsvr_client"]}
      fields[fieldName] = myaction
      actions.append(myaction)
      fields[fieldName] = myaction
      action="getField"
    elif opt[0] == "--setField":
      fieldName = opt[1]
      myaction = {"action":"setField","fieldName":fieldName,"value":"",
                               "timestamp":useTimeStamp,
                               "targets":["asset","assets","project"],
                               "sources":["fcsvr_client","fcsxml"]}
      fields[fieldName] = myaction
      actions.append(myaction)
      fields[fieldName] = myaction
      action="setField"
      if not fcsvr_client:
        module="TransmogrifierTarget"
      expectsValue = True 
    elif opt[0] == "--setBoolField":
      fieldName = opt[1]
      myaction = {"action":"setBoolField","fieldName":fieldName,"value":"",
                                "timestamp":useTimeStamp,
                                "targets":["asset","assets","project"],
                                "sources":["fcsvr_client","fcsxml"]}
      fields[fieldName] = myaction
      actions.append(myaction)
      fields[fieldName] = myaction
      action="setField"
      if not fcsvr_client:
        module="TransmogrifierTarget"
      expectsValue = True 
    elif opt[0] == "--archive":
      myaction = {"action":"archive","targets":["asset","assets","project"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--restore":
      myaction = {"action":"restore","targets":["asset","assets","project"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--analyze":
      myaction = {"action":"analyze","targets":["asset","assets","project"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getAssetTitle":
      myaction = {"action":"getAssetTitle","targets":["asset"],
                                     "sources":["fcsvr_client","fcsxml"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getAssetPath":
      myaction = {"action":"getAssetPath","targets":["asset","assets"],
                                     "sources":["fcsvr_client","fcsxml"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getAssetID":
      myaction = {"action":"getAssetID","targets":["asset","assets"],
                                     "sources":["fcsvr_client","fcsxml"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getEntityPath":
      myaction = {"action":"getEntityPath","targets":["device","asset","assets"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getEntityMetadataSet":
      myaction = {"action":"getEntityMetadataSet","targets":["device","asset"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)    
    elif opt[0] == "--getFilePath":
      myaction = {"action":"getFilePath","targets":["asset","assets","device"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getArchivePath":
      myaction = {"action":"getArchivePath","targets":["asset","assets","device"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getProxyPath":
      myaction = {"action":"getProxyPath","targets":["asset"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getEditProxyPath":
      myaction = {"action":"getEditProxyPath","targets":["asset"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getPosterFramePath":
      myaction = {"action":"getPosterFramePath","targets":["asset"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getThumbnailPath":
      myaction = {"action":"getThumbnailPath","targets":["asset"],
                                     "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getProductionID":
      myaction = {"action":"getProductionID","targets":["project"],
                                     "sources":["fcsvr_client","fcsxml"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getProductionTitle":
      myaction = {"action":"getProductionTitle","targets":["project"],
                                     "sources":["fcsvr_client","fcsxml"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--addToProduction":
      ##print "DEBUG: hit --addToProduction"
      myaction = {"action":"addToProduction",
                                     "targets":["asset","assets","project"],
                                     "target2":["project"],
                                     "sources":["fcsvr_client"]}
      action = "addToProduction"
      useSecondTarget = True
      actions.append(myaction)
    elif opt[0] == "--getDeviceID":
      myaction = {"action":"getDeviceID","targets":["device","asset"],
                                      "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getDeviceName":
      myaction = {"action":"getDeviceName","targets":["device","asset"],
                                      "sources":["fcsvr_client","fcsxml"]}
      action="internal"
      actions.append(myaction)
    elif opt[0] == "--getDevicePath":
      myaction = {"action":"getDevicePath","targets":["device","asset"],
                                      "sources":["fcsvr_client"]}
      action="internal"
      actions.append(myaction) 
    
    ## Read in our possible target
    elif opt[0] == '-t' or opt[0] == "--title":
      mytarget = {"target":"xmltitle","type":"asset","value":opt[1],
                                       "sources":["fcsxml"]}
      if "asset" in targets:
        print ("Error! Specified conflicting targets: --title and --%s!!" 
                                    % targets["asset"]["target"])
        helpMessage()
        return 5
      targets["asset"] = mytarget
      fileTitle = opt[1]
    elif opt[0] == '-i' or opt[0] == "--xmlin":
      mytarget = {"target":"xmlin","type":"asset","value":opt[1],
                                           "sources":["fcsxml"]}
      if "asset" in targets:
        print ("Error! Specified conflicting targets: --xmlin and --%s!!" 
                                     % targets["asset"]["target"])
        helpMessage()
        return 5
      targets["asset"] = mytarget
      xmlinPath == 'opt[1]'
    elif opt[0] == "--assetID":
      mytarget = {"target":"assetID","value":opt[1],"type":"asset",
                                 "sources":["fcsvr_client","fcsxml","stdin"]}
      if "asset" in targets and not useSecondTarget:
        print ("Error! Specified conflicting targets: --assetID and --%s!!" 
                                           % targets["asset"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
                                           % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--assetTitle":
      mytarget = {"target":"assetTitle","value":opt[1],"type":"asset",
                                            "sources":["fcsvr_client","stdin"]}
      if "asset" in targets and not useSecondTarget:
        print ("Error! Specified conflicting targets: --assetTitle and --%s!!" 
                                           % targets["asset"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
                                          % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--assetsFromProductionID":
      mytarget = {"target":"assetsFromProductionID","value":opt[1],
                                    "type":"assets",
                                    "sources":["fcsvr_client","fcsxml","stdin"]}
      if "asset" in targets and not secondTarget:
        print ("Error! Specified conflicting targets: --assetsFromProductionID "
          " and --%s!!" % targets["asset"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
                                                 % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--assetsFromProjectID":
      mytarget = {"target":"assetsFromProjectID","value":opt[1],
                                      "type":"assets",
                                      "sources":["fcsvr_client","stdin"]}
      if "asset" in targets and not secondTarget:
        print ("Error! Specified conflicting targets: --assetsFromProjectID "
          " and --%s!!" % targets["asset"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
                                                    % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--entityPath":
      entityPath = opt[1]
      mytarget = {"target":"entityPath","value":entityPath,
                                      "type":"asset",
                                      "sources":["fcsvr_client"]}
      entityType = entityPath.split("/")[1]
      if entityType in targets and not secondTarget:
        print ("Error! Specified conflicting targets: --assetPath and --%s!!" 
                                                % targets["asset"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!"
                                                % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets[entityType] = mytarget
    elif opt[0] == "--assetPath":
      mytarget = {"target":"assetPath","value":opt[1],
                                  "type":"asset",
                                  "sources":["fcsvr_client"]}
      if "asset" in targets and not useSecondTarget:
        print ("Error! Specified conflicting targets: --assetPath and --%s!!"
                                    % targets["asset"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!"
                                    % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--productionID":
      mytarget = {"target":"productionID","value":opt[1],
                                  "type":"project",
                                  "sources":["fcsvr_client",]}
      if "project" in targets and not useSecondTarget:
        print ("Error! Specified conflicting targets: --productionID "
                     " and --%s!!" % targets["project"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
                          % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--productionTitle":
      mytarget = {"target":"productionTitle","value":opt[1],
                                     "type":"project",
                                     "sources":["fcsvr_client",]}
      if "project" in targets and not useSecondTarget:
        print ("Error! Specified conflicting targets: --productionID and --%s!!"
                                                % targets["project"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
                                                % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--productionTitleLike":
      mytarget = {"target":"productionTitleLike","value":opt[1],
                                         "type":"project",
                                         "sources":["fcsvr_client",]}
      if "project" in targets and not useSecondTarget:
        print ("Error! Specified conflicting targets: --productionID "
           "and --%s!!" % targets["project"]["target"])
        helpMessage()
        return 5
      elif useSecondTarget and 'secondTarget' in targets:
        print ("Error! You have already specified a second target: --%s!!" 
             % secondTarget["target"])
        helpMessage()
        return 5      
      elif useSecondTarget and len(targets) > 0:
        targets['secondTarget'] = mytarget
      else:
        targets["asset"] = mytarget
    elif opt[0] == "--createProductionWithTitle":
      mytarget = {"target":"createProductionWithTitle","value":opt[1],
                                    "type":"project",
                                    "sources":["fcsvr_client",]}
      myaction = {"action":"createProductionWithTitle",
                                    "targets":["project"],
                                    "sources":["fcsvr_client"]}
      if "project" in targets:
        print ("Error! Specified conflicting targets: --productionID and --%s!!"
                  % targets["project"]["target"])
        helpMessage()
        return 5
      else:
        targets["project"] = mytarget
        actions.append(myaction)
    elif opt[0] == "--deviceID":
      mytarget = {"target":"deviceID","value":opt[1],
                                  "type":"device","sources":["fcsvr_client"]}
      if "device" in targets:
        print ("Error! Specified conflicting targets: --deviceID and --%s!!"
             % targets["device"]["target"])
        helpMessage()
        return 5
      targets["device"] = mytarget
    elif opt[0] == "--deviceName":
      mytarget = {"target":"deviceName","value":opt[1],
                                  "type":"device",
                                  "sources":["fcsvr_client","fcsxml"]}
      if "device" in targets:
        print ("Error! Specified conflicting targets: --deviceName and --%s!!"
                                    % targets["device"]["target"])
        helpMessage()
        return 5
      targets["device"] = mytarget
    elif opt[0] == "--devicePath":
      mytarget = {"target":"devicePath","value":opt[1],
                                 "type":"device",
                                 "sources":["fcsvr_client"]}
      if "device" in targets:
        print ("Error! Specified conflicting targets: --devicePath and --%s!!"
                                    % targets["device"]["target"])
        helpMessage()
        return 5
      targets["device"] = mytarget
    elif opt[0] == '--withtimestamp':
      ## If we have fields set, apply the timestamp value to only the last 
      ## specified field. If no fields are specified, we enable it globally
      if len(fields) > 0 and fieldName in fields:
        myField = fields[fieldName]
        myField["timestamp"] = True
      else:
        useTimeStamp = True          
    elif opt[0] == '--notimestamp':
      ## If we have fields set, apply the timestamp value to only the last 
      ## specified field. If no fields are specified, we disable it globally
      if len(fields) > 0 and fieldName in fields:
        myField = fields[fieldName]
        myField["timestamp"] = False
      else:
        useTimeStamp = False
    elif opt[0] == '-a' or opt[0] == '--action':
      action = opt[1]
      

  ## If no config file was specified, set default of /usr/local/etc/transmogrifier.conf
  if not configFile or not os.path.isfile(configFile):
    configFile = os.path.join("/", "usr", "local", "etc", "transmogrifier.conf")
    if not os.path.isfile(configFile):
      configFile = "transmogrifier.conf"
        
  ## Make sure the config file we plan to use exists and can be read by our parser
  cfgParser = ""
  if os.path.isfile(configFile):
    try:
      cfgParser = SafeConfigParser()
      cfgParser.read(configFile)
      if not basePath:
          basePath = cfgParser.get("GLOBAL","path")
      validModules = cfgParser.get("GLOBAL","modules").split(",")
    except:
      print ("Error! Could reading global attributes from file at path: '%s' "
           "Error: %s" % (configFile,sys.exc_info()[0]))
    
    try:
      ## Get our debug status from our config only if we haven't already set it
      ## to true.
      if not debug:
        debug = cfgParser.getboolean("GLOBAL","debug")
      keepFiles = cfgParser.getboolean("GLOBAL", "keepfiles")
    except:
      settingsError=True
  else:
    print "Error! Could not find valid configuration file!"
    ##print "DEBUG: Actions:%s Targets:%s module:%s" % (actions,targets,module)

  ## If we have pooled actions and targets, and no module defined, process them
  if not module and actions and targets:
    myTargetObject = ""
    myTargetObjects = ""
    ## Make sure we have a target for each action that we have defined
    for theAction in actions:
      try:
        foundActionTargets = []
        actionName = theAction["action"]
        if debug:
          print "DEBUG: Processing Action: %s" % actionName
        ## Make sure that our attempted targets jive with whether we're using 
        ## fcsxml or fcsvr_client
        if "fcsvr_client" in theAction["sources"]:
          if len(theAction["sources"]) == 1 and not fcsvr_client:
            print ("Action: %s requires fcsvr_client, cannot continue!" 
                                                              % actionName)
            return 7
          elif (len(theAction["sources"]) > 1 
          and fcsvr_client and fcsvr_client_all):
            theAction["activeSource"] = "fcsvr_client"
          elif len(theAction["sources"]) > 1 and not fcsvr_client:
            theSource = ""
            if (not "activeSource" in theAction 
            or theAction["activeSource"] == "fcsvr_client"):
              count = 0
              while (count < len(theAction["sources"]) 
              and not theSource == "fcsvr_client"):
                theSource = theAction["sources"][count]
                count += 1
              if theSource:
                theAction["activeSource"] = theSource
              else:
                print ("Error! Could not establish active source for action:%s" 
                         % actionName)
                return 8
        
        #### DETERMINE APPLICABLE TARGETS FOR ACTION ####
        
        ## Make sure that there is only one valid target. Here we build two
        ## lists for future use: 'myActionTarget' and 'myActionSecondTarget' 
        ## (if applicable)
        myActionTarget = ''
        myActionSecondTarget = ''
        for theTarget in theAction["targets"]:
          ##print "theTarget: %s" % theTarget
          for myTargetKey,myTargetDict in targets.iteritems():
            ##print "Searching for target: %s currentIndex: %s theTarget: %s" % (theTarget,myTargetKey,myTargetDict) 
            if theTarget == myTargetDict['type'] and not myTargetKey == "secondTarget":
              foundActionTargets.append(myTargetKey)
        if len(foundActionTargets) > 1:
          print ("Error! Ambiguous targets:%s specified for action:'--%s'" 
                                          % (foundActionTargets,actionName))
          return 5
        elif len(foundActionTargets) == 0:
          print ("Error! No targets found for action:'--%s', requires one "
                        "of: %s" % (actionName,",".join(theAction["targets"])))
          return 4        
        elif len(foundActionTargets) == 1:
          myActionTarget = targets[foundActionTargets[0]]
          
        ## If we are set to use a secondTarget, check it
        if useSecondTarget:
          if not 'secondTarget' in targets:
            print "Error! Action: %s requires more than one target!" % actionName
          foundSecondTarget = False
          for theTargetType in theAction["target2"]:
            ##print "theTargetType: %s, secondTargetType: %s" % (theTargetType,targets['secondTarget']['type'])
            if targets['secondTarget']['type'] == theTargetType:
              foundSecondTarget = True
          if foundSecondTarget:
            foundActionTargets.append('secondTarget')
            myActionSecondTarget = targets['secondTarget']
          else:
            print ("Error! Action: %s The specified second target does not "
                                                      "meet our requirements!")
            return 5
        
        ### BUILD TARGET OBJECTS FOR ACTION ####
        
        ## Iterate through each of our found targets and build their objects
        try:
          for targetName in foundActionTargets:
            if debug:
              print "DEBUG: Building object for target:%s" % targetName
            myTargetDict = targets[targetName]
            myDict = {}
            if (myTargetDict["type"] == "asset" 
            or myTargetDict["type"] == "assets"):
              ## check to see if there is a loaded object for our target type
              if not "object" in myTargetDict or not myTargetDict["object"]:
                ## If not, build it based on the target's parameters
                if myTargetDict["target"] == "assetID":
                  ##print "Building from assetID"
                  assetID = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSVRClient(id=assetID,
                                                      configParser=cfgParser)
                  if debug:
                    myTargetObject.debug = True
                    
                elif myTargetDict["target"] == "assetTitle":
                  ## print "Building from assetTitle"
                  assetTitle = myTargetDict["value"];
                  myTargetObject = fcsxml.FCSVRClient(configParser=cfgParser)
                  myTargetObject.initWithAssetTitle(assetTitle)
                  if debug:
                    myTargetObject.debug = True
                elif myTargetDict["target"] == "assetPath":
                  fsPath = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSVRClient(configParser=cfgParser)
                  if debug:
                    myTargetObject.debug = True
                    
                  if not myTargetObject.initWithAssetFromFSPath(fsPath):
                    raise fcsxml.FCSEntityNotFoundError(entityPath=fsPath)

                elif myTargetDict["target"] == "xmlin":
                  xmlPath = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSXMLObject(configParser=cfgParser)
                  if debug:
                    myTargetObject.debug = True

                  if not myTargetObject.setFile(xmlPath):
                    print "Error! Could not read XML from path: '%s'" % xmlPath
                    return 1
                
                #### Apply filters to myTargetObject. ####
                ## If we don't meet our parameters, then clear out our 
                ## target object
                if myTargetObject and filters:
                  if ('mdSet' in filters 
                  and not myTargetObject.entityMetadataSet == filters['mdSet']):
                    if debug:
                      print ("Found Object: %s, but it does not match our"
                        " metadata set of %s" % (myTargetObject.entityPath(),
                                                              filters['mdSet']))
                    myTargetObject = False
                    
              #### At this point we should have myTargetObject built.
                
              if (not "objectList" in myTargetDict 
              or not myTargetDict["objectList"]
              and myTargetDict["type"] == "assets"):
                if myTargetDict["target"] == "assetsFromProductionID":
                  productionID = myTargetDict["value"]
                  myProduction = fcsxml.FCSVRClient(id=productionID,
                                                          entityType="project",
                                                          configParser=cfgParser)
                  if debug:
                    myProduction.debug = True

                  ## Lookup our productions assets, apply filters if specified ####
                  if filters:
                    if 'mdSet' in filters:
                      myTargetObjects = myProduction.assetsFromProduction(
                                                recurse=False,
                                                mdSet=filters['mdSet'])
                    else:
                      myTargetObjects = myProduction.assetsFromProduction(
                                                recurse=False)
                  else:
                    myTargetObjects = myProduction.assetsFromProduction(
                                                recurse=False)
              
              if (not "objectList" in myTargetDict 
              or not myTargetDict["objectList"]
              and myTargetDict["type"] == "assets"):
                if myTargetDict["target"] == "assetsFromProjectID":
                  projectID = myTargetDict["value"]
                  myProject = fcsxml.FCSVRClient(id=projectID,entityType="asset",
                                                        configParser=cfgParser)
                  if debug:
                    myProject.debug = True
                    
                    ## Lookup our productions assets, apply filters if specified ####
                  if filters:
                    if 'mdSet' in filters:
                      myTargetObjects = myProduction.assetsFromProject(
                                                      recurse=False,
                                                      mdSet=filters['mdSet'])
                    else:
                      myTargetObjects = myProduction.assetsFromProject(
                                                                recurse=False)
                  else:
                    myTargetObjects = myProject.assetsFromProject()
                    
            elif myTargetDict["type"] == "project":
              ## check to see if there is a loaded object for our target type
              if not "object" in myTargetDict or not myTargetDict["object"]:
                ## If not, build it based on the target's parameters
                if myTargetDict["target"] == "productionID":
                  productionID = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSVRClient(id=productionID,
                                                          entityType="project",
                                                          configParser=cfgParser)

                  if debug:
                    myTargetObject.debug = True
                elif myTargetDict["target"] == "productionTitle":
                  productionTitle = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSVRClient(entityType="project",
                        configParser=cfgParser)
                  if debug:
                    myTargetObject.debug = True
                  
                  myTargetObject.initWithProductionTitle(productionTitle,
                        matchType='exact')
                elif myTargetDict["target"] == "productionTitleLike":
                  productionTitle = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSVRClient(entityType="project",
                    configParser=cfgParser)
                  if debug:
                    myTargetObject.debug = True
                  myTargetObject.initWithProductionTitle(productionTitle,
                    matchType='substring')
                elif myTargetDict["target"] == "createProductionWithTitle":
                  productionTitle = myTargetDict["value"]
                  try:
                    newObject = fcsxml.FCSVRClient(entityType="project",
                                                        configParser=cfgParser)
                    if debug:
                      myTargetObject.debug = True                                    
                    try:
                      myTargetObject = newObject.productionWithTitle(productionTitle)
                    except:
                      myTargetObject = newObject

                  except:
                    pass
                  

                elif myTargetDict["target"] == "assetPath":
                  fsPath = myTargetDict["value"]
                  myTargetObject = fcsxml.FCSVRClient(configParser=cfgParser)
                  if debug:
                    myTargetObject.debug = True
                  if not myTargetObject.initWithAssetFromFSPath(fsPath):
                    print ("Error! Could not resolve asset from path: '%s'" 
                                                                  % fsPath)
                    return 1
            
            elif myTargetDict["type"] == "device":
              ## check to see if there is a loaded dict for our device target 
              if not "deviceDict" in myTargetDict:
                ## If not, build it based on the target's parameters
                if myTargetDict["target"] == "deviceID":
                  myDeviceID = myActionTarget["value"]
                  myFCSVRClient = fcsxml.FCSVRClient(configParser=cfgParser)
                  myDict = myFCSVRClient.deviceWithID(myDeviceID)
                elif myTargetDict["target"] == "deviceName":
                  myDeviceName = myActionTarget["value"]
                  myFCSVRClient = fcsxml.FCSVRClient(configParser=cfgParser)
                  myDict = myFCSVRClient.deviceWithName(myDeviceName)
                elif myTargetDict["target"] == "devicePath":
                  myDevicePath = myActionTarget["value"]
                  myFCSVRClient = fcsxml.FCSVRClient(configParser=cfgParser)
                  myDict = myFCSVRClient.deviceWithPath(myDevicePath)
                  print "Error! devicePath not implemented!"
                  return 1
                if myDict:
                  myTargetDict["deviceDict"] = myDict
            
            
            if myTargetObject:
              myTargetDict['object'] = myTargetObject
            elif myTargetObjects:
              myTargetDict['objectList'] = myTargetObjects
            elif not myTargetObject and not myTargetObjects and not myDict:
              raise RuntimeError('No qualifying object found')
        except Exception,err:
          if debug:
            raise 
          print ("Error! Could not determine target from specified criteria "
            "for action: %s! Error: %s" % (actionName,err))
          exitCode=4
          continue
          
        ### END BUILD TARGETS FOR ACTION ####
          
        ## At this point we should have up to two valid target dictionaries
        ## build: myActionTarget and myActionSecondTarget
        ## Each of these dicts should have an object loaded at index 'object' or
        ## 'objectList'
        if debug:
          print 'DEBUG: myActionTarget: %s' % myActionTarget
          if useSecondTarget:
            print 'DEBUG myActionSecondTarget: %s' % myActionSecondTarget
          
                
        #### PROCESS ACTION ####
        
        actionTargetType = myActionTarget["type"]
        
        ## Process Actions that use asset or production targets
        if actionName == "getField":
          myTargetObject = myActionTarget['object']
          myValue = myTargetObject.valueForField(theAction['fieldName'])
          print '%s: %s' % (theAction['fieldName'],myValue)
        elif actionName == "getDBField":
          myTargetObject = myActionTarget['object']
          myValue = myTargetObject.valueForDBField(theAction['fieldName'])
          print '%s: %s' % (theAction['fieldName'],myValue)
        elif actionName == "setField":
          #print "Setting Field:%s to value:%s" % (theAction["fieldName"],theAction["value"])
          myTargetObjects = []
          if 'objectList' in myActionTarget:
            myTargetObjects.extend(myActionTarget['objectList'])
          if 'object' in myActionTarget:
            myTargetObjects.append(myActionTarget['object'])
            
          theField = fcsxml.FCSVRClient(configParser=cfgParser).initFieldWithFieldName(
                                              fieldName=theAction['fieldName'])
          ##theField = FCSXMLField(name=theAction["fieldName"])
          if debug:
            theField.debug = True
          theField.setValue(theAction["value"])
          
          if len(myTargetObjects) > 0:
            for theObject in myTargetObjects:
              theObject.setField(theField)
              theObject.setMD()
              ## Sleep for a few seconds between values
              time.sleep(.5)
        elif actionName == "appendField":
          #print "Setting Field:%s to value:%s" % (theAction["fieldName"],theAction["value"])
          ## Get the current value
          myTargetObjects = []
          if 'objectList' in myActionTarget:
            myTargetObjects.extend(myActionTarget['objectList'])
          if 'object' in myActionTarget:
            myTargetObjects.append(myActionTarget['object'])         
          
          ## If we have targets, iterate through them and append the field
          if len(myTargetObjects) > 0:
            for target in myTargetObjects:   
              ## Get current field and value       
              currentField = target.appendValueForField(
                                      fieldName=theAction['fieldName'],
                                      value=theAction['value'],
                                      useTimestamp = theAction['timestamp'])
              target.setMD()
          
        elif actionName == "setBoolField":
          #print "Setting Field:%s to value:%s" % (theAction["fieldName"],theAction["value"])
          if not theAction["value"] or theAction["value"] == "false":
            theField = FCSXMLField(name=theAction["fieldName"],value=False,dataType="bool")
          else:
            theField = FCSXMLField(name=theAction["fieldName"],value=True,dataType="bool")
          if myTargetObject: 
            myTargetObject.setField(theField)
            myTargetObject.setMD()
          if myTargetObjects:
            for theObject in myTargetObjects:
              if theObject.setField(theField):
                theObject.setMD()
              else:
                exitCode = 15
        elif actionName == "getAssetID":
          if myTargetObject:
            print "ASSET_ID: %s" % myTargetObject.entityID
          if myTargetObjects:
            for myObject in myTargetObjects:
              print "ASSET_ID: %s" % myObject.entityID
        elif actionName == "getAssetPath":
          if myTargetObject:
            print "ASSET_PATH: %s" % myTargetObject.getFilePath()
          if myTargetObjects:
            for myObject in myTargetObjects:
              print "ASSET_PATH: %s" % myObject.getFilePath()
        elif actionName == "getEntityPath":
          if myTargetObject:
             print "ENTITY_PATH: %s" % myTargetObject.entityPath()
          elif myActionTarget['type'] == 'device':
            print "ENTITY_PATH: /dev/%s" % myDeviceDict['DEVICE_ID']
          elif myTargetObjects:
            for myObject in myTargetObjects:
              print "ENTITY_PATH: %s" % myObject.entityPath()
        elif actionName == "getEntityMetadataSet":
          if myTargetObject:
             print "ENTITY_METADATASET: %s" % myTargetObject.entityMetadataSet
        elif actionName == "getFilePath":
          if myTargetObject:
            myFilePath = myTargetObject.getFilePath()
            if not myFilePath:
              myFilePath = ""
            print "FILE_PATH: %s" % myFilePath
          if myTargetObjects:
            for myObject in myTargetObjects:
              print "FILE_PATH: %s" % myObject.myFilePath()
        elif actionName == "getArchivePath":
          if myTargetObject:
            print "ARCHIVE_PATH: %s" % myTargetObject.getArchiveFilePath()
          if myTargetObjects:
            for myObject in myTargetObjects:
              print "ARCHIVE_PATH: %s" % myObject.getArchiveFilePath()
        elif actionName == "getProxyPath":
          if myTargetObject:
            myFileProxyPath = myTargetObject.getFilePathForProxy()
            if not myFileProxyPath:
              myFileProxyPath = ""
            print "PROXY_PATH: %s" % myFileProxyPath
        elif actionName == "getEditProxyPath":
          if myTargetObject:
            myEditProxyPath = myTargetObject.getFilePathForEditProxy()
            if not myEditProxyPath:
              myEditProxyPath = ""
            print "EDITPROXY_PATH: %s" % myEditProxyPath
        elif actionName == "getThumbnailPath":
          if myTargetObject:
            myThumbnailPath = myTargetObject.getFilePathForThumbnail()
            if not myThumbnailPath:
              myThumbnailPath = ""
            print "THUMBNAIL_PATH: %s" % myThumbnailPath
        elif actionName == "getPosterFramePath":
          if myTargetObject:
            myPosterFramePath = myTargetObject.getFilePathForPosterFrame()
            if not myPosterFramePath:
              myPosterFramePath = ""
            print "POSTERFRAME_PATH: %s" % myPosterFramePath
        elif actionName == "getAssetTitle":
          if myTargetObject:
            myTitle = myTargetObject.valueForField("Title")
            if not myTitle:
              myTitle = ""
            print "ASSET_TITLE: %s" % myTitle
        elif actionName == "archive":
          if myTargetObject:
            print "Archiving Asset: %s" % myTargetObject.entityPath()
            try:
              myTargetObject.archive()
            except fcsxml.FCSAssetOfflineError,err:
              print " - %s" % eval(err.__str__())
              return 9
          if myTargetObjects:
            myRetCode = 0
            for theObject in myTargetObjects:
              print "Archiving Asset: %s" % theObject.entityPath()
              try:
                theObject.archive()
              except fcsxml.FCSAssetOfflineError,err:
                print " - %s" % eval(err.__str__())
                myRetCode = 9
            if myRetCode == 9:
              return myRetCode
                
        elif actionName == "restore":
          if myTargetObject:
            print "Restoring Asset: %s" % myTargetObject.entityPath()
            myTargetObject.restore()
          if myTargetObjects:
            for theObject in myTargetObjects:
              print "Restoring Asset: %s" % theObject.entityPath()
              theObject.restore()
        elif actionName == "analyze":
          if myTargetObject:
            print "Analyzing Asset: %s" % myTargetObject.entityPath()
            myTargetObject.analyze(force=True)
          if myTargetObjects:
            for theObject in myTargetObjects:
              print "Analyzing Asset: %s" % theObject.entityPath()
              theObject.analyze(force=True)
        elif actionName == "getProductionID":
          if myTargetObject:
            print "PRODUCTION_ID: %s" % myTargetObject.entityID
        elif actionName == "getProductionTitle":
          if myTargetObject:
            print "PRODUCTION_TITLE: %s" % myTargetObject.valueForField('Title')
        elif actionName == "createProductionWithTitle":
          myTargetObject = myActionTarget['object']
          productionTitle = myActionTarget['value']
          if not myTargetObject.entityID:
            if debug:
              print ("DEBUG: Creating production with title: '%s'" 
                                                              % productionTitle)
            if not myTargetObject.createProduction(title=productionTitle):
              raise RuntimeError("Could not create production with title: %s!" 
                                                  % productionTitle)
          print "PRODUCTION_ID: %s" % myTargetObject.entityID
        elif actionName == "addToProduction":
          myTargetObject = ''
          myTargetObjects = ''
          if 'object' in myActionTarget:
            myTargetObject = myActionTarget['object']
          if 'objectList' in myTargetObjects:
            myTargetObjects = myActionTarget['objectList']
          
          myProduction = myActionSecondTarget['object']
                    
          if myTargetObject:
            try:
              myProduction.addMemberToProduction(member = myTargetObject)
            except fcsxml.FCSError, excp:
              print ("ERROR Could not add entity: %s to production: %s. "
                " Reported Error: %s " % (myTargetObject.entityPath(),
                                           myProduction.entityPath(),
                                          excp))
              exitCode = 3
          
          if myTargetObjects:
            for theObject in myTargetObjects:
              try:
                myProduction.addMemberToProduction(member = myTargetObject)
              except fcsxml.FCSError, excp:
                print ("ERROR Could not add entity: %s to production: %s. "
                  " Reported Error: %s " % (theObject.entityPath(),
                                           myProduction.entityPath(),
                                          excp))
                exitCode = 3
                        
          
        
        ## If this is a device-centric action, make sure we have a loaded 
        ## device dict.
        elif 'Device' in actionName or 'device' in actionName:
          if not 'deviceDict' in myActionTarget:
            myTargetObject = myActionTarget['object']
            ## Create our device field.
            myDeviceField = myTargetObject.loadField(fcsxml.FCSXMLField(
                                  name='Stored On',
                                  dbname='CUST_DEVICE'))
            myDeviceName = myDeviceField.value
            if debug:
              print "DEBUG: looking up device with name:%s" % myDeviceName
            myDeviceDict = myTargetObject.deviceWithName(myDeviceName)
          else:
            myDeviceDict = myActionTarget['deviceDict']  
          
          
          if actionName == 'getDeviceID':
            print "DEVICE_ID: %s" % myDeviceDict["DEVICE_ID"]
          if actionName == 'getDeviceName':
            print "DEVICE_NAME: %s" % myDeviceDict["DEVICE_NAME"]
          if actionName == 'getDevicePath':
            print 'DEVICE_PATH: %s' % myDeviceDict['DEV_ROOT_PATH']

      except Exception, inst:
        if debug:
          raise
        print "ERROR: Failed to process action:%s Error: %s" % (actionName,inst)
        return 25

    ## Return a 0 exit code on success 
    return exitCode
          
  ## We are here if we bipassed the newer FCS-centric commands. From here no we
  ## are historical Code used for XML delivery and custom processing.
  
  
  if debug:
    print "DEBUG: Running older Codebase!"
    if module:
      print ("DEBUG: Running for module: %s validModules: %s" % (module,
                                                   ','.join(validModules)))
        

  ## Make sure we have a valid module if we're not just creating the support 
  ## folder. This step is very important as we dynamically create our objects
  ## based on the module string.
  if not module:
    module = "TransmogrifierTarget";
  elif not module in validModules and not action == "createSupportFolders":
    print ("Invalid module: '%s'\n  Allowed values: %s" 
                        % (module,",".join(validModules)))
    return 1


  ## If our action is to upload or preflightCheck, we require a title to be 
  ## specified (for every action but createSupportFolders) 
  ## Todo: this all needs to be much more dynamic, the individual module needs 
  ## a check against this
  if not action:
    print ("No action has been provided, cannot continue! "
              "Run with --help to see syntax.\n")
    return 1
    
  myActions = validActions(modules=validModules)
  if not action in myActions:
    print ("Invalid Action: %s!\nAvailable Actions: %s" 
                                      % (action,",".join(myActions)))
    return 6
  if (action != "createSupportFolders" 
  and action != "batchStatusCheck" 
  and action != "listFCSFields"):
    if not fileTitle:
      print ("An asset title must be provided when used with action: '%s'" 
                                                                    % action)
      return 2 
  elif action == "listFCSFields":
    if module == "TransmogrifierTarget":
      myObject = TransmogrifierTargetObject()
      myObject.runFunction('listFCSFields')
      for module in validModules:
        try:
          theModule = eval("%sObject()" % module)
          theModule.loadConfiguration(cfgParser)
        except Exception,excp:
          print "Could not load module: %s, Error: %s" % (module,excp)
          continue
        theModule.runFunction('listFCSFields')
      return 0

  elif action == "createSupportFolders": 
    ## make sure we have a base path
    if basePath:
      if not module == "TransmogrifierTarget":
        if createSupportFolders(basePath,module):
            return 0
        else:
            return 10
      else:
        if createSupportFolders(basePath, validModules, cfgParser):
            return 0
        else:
            return 10
    else:
      helpMessage()
      return 1
 
  ## Start our timer
  startTime = datetime.datetime.now()

 
  ## create our object base on our active module
  try:
    myObject = eval("%sObject()" % module)
  except:
    print "Could not create object: %sObject(), using default object!" % module
    myObject = TransmogrifierTargetObject()

  ## Set our debug status
  myObject.debug = debug
  if debug:
    myObject.printLogs = True

  if fcsvr_client:
    myObject.fcsvr_client = True
  if fcsvr_client_all:
    myObject.fcsvr_client_all = True

  ## load up the config file
  myObject.loadConfiguration(cfgParser)

  ## Determine our filename, FCS will not always output a file with it's full 
  ## title. If the title has a '.' in it, it will truncate the filename to
  ## contain only chars preceeding the first . in the title, thus the file 
  ## with title: "mymovie.foexport.mov" will be exported as mymovie.xml
  if fcsMajorVersion == "1.5":
    fileNameBase = os.path.splitext(fileTitle)[0]
  else:
    fileNameBase = re.sub(r'^(.*?)\..*$', r'\1', fileTitle)
  if not os.path.isdir(basePath):
    print "Path: '%s' does not exist!" % basePath
    return 2
  if module == "TransmogrifierTarget":
    modulePath = basePath
  elif module == "sftp":
    modulePath = basePath
  else:
    modulePath = os.path.join(basePath, module)
  fileFound = False

  ## If we specified an XML file via the -i flag, we use that (it has already
  ## passed validation and will be set in xmlinPath. If no file was specified,
  ## we attempt to find it based on title passed with the -t flag.
  if xmlinPath:
    fileFound=True
  elif os.path.exists(os.path.join(modulePath,"xmlin",
                                                "%s.xml" % (fileNameBase))):
    xmlinPath = os.path.join(modulePath,"xmlin","%s.xml" % (fileNameBase))
  elif os.path.exists(os.path.join(basePath,"xmlin","%s.xml" % (fileNameBase))):
    xmlinPath = os.path.join(basePath,"xmlin","%s.xml" % (fileNameBase))
  elif os.path.exists(os.path.join(basePath,
                                    "fcsvr_xmlout","%s.xml" % (fileNameBase))):
    xmlinPath = os.path.join(basePath,"fcsvr_xmlout","%s.xml" % (fileNameBase))
  elif os.path.exists(os.path.join(basePath,"FCS/xmlin",
                                                  "%s.xml" % (fileNameBase))):
    ## if our xmlin file is found in the FCS dir, use that as our support dir
    modulePath = os.path.join(basePath,"FCS")
    fileFound=True
  if (not xmlinPath 
  and not (action == "batchStatusCheck" 
  or action == "createSupportFolders" 
  or action == "listFCSFields" 
  or action == 'uploadMovies' 
  or action == 'uploadImages')):
    print ("Could not find file: '%s.xml' in paths: '%s/xmlin/', '%s/xmlin/',"
          " '%s/fcsvr_xmlout'" % (fileNameBase, modulePath, basePath,basePath))
    return 2
  else:
    if not xmlinPath:
      xmlinPath = os.path.join(modulePath,"xmlin","%s.xml" % fileNameBase)
    
  ## Target-agnostic setup. 
  myObject.setSupportPath(modulePath)
  myObject.fileBaseName = fileNameBase
  
  #### Perform our action ####
  if action == "batchStatusCheck" or action == "listFCSFields":
    if myObject.runFunction(action):
      return 0
    else:
      return 1
  elif action == "appendField" or action == "setField":
    if len(fields) > 0:
      myObject.setFCSXMLFile(xmlinPath)
      myFCSXML = myObject.fcsXMLObject
      for fieldName,field in fields.iteritems():
        if field["action"] == "appendField":
          if field["value"]:
            newValue = field["value"]
          else:
            newValue = "\n"
          if field["timestamp"]:    
            currentTime = datetime.datetime.fromtimestamp(
                               time.mktime(datetime.datetime.now().timetuple()))
            newValue = "\n%s: %s\n" % (currentTime,newValue)    
          myObject.appendFCSField(fieldName,"%s" % newValue)
        elif field["action"] == "setField":
          myObject.setFCSField(fieldName,"%s" % newValue)

  elif not action == "upload":
    ## If we're not uploading or doing a batchStatusCheck, load xml
    ## and pass action to the object.
    myObject.setFCSXMLFile(xmlinPath)

    if action == "autoKey":
      currentTime = datetime.datetime.fromtimestamp(
                              time.mktime(datetime.datetime.now().timetuple()))
      myObject.appendFCSField("Shake History", 
                                 "%s: Beginning Processing...\n" % currentTime)
      myObject.reportToFinalCutServer()
    
    if myObject.runFunction(action):
      endTime = datetime.datetime.now()
      processTime = endTime - startTime;
      statusMSG = ("Action: %s successfully completed for module: %s. "
                           "Elapsed time:'%s'" % (action, module,processTime))
      exitStatus = 0
    else:
      statusMSG = ("Action: %s failed to complete for module: %s\n  Error: %s" 
                                    % (action, module, myObject.lastError))
      print statusMSG
      exitStatus = 1

    if action == "autoKey":
      currentTime = datetime.datetime.fromtimestamp(
                              time.mktime(datetime.datetime.now().timetuple()))
      myObject.appendFCSField("Shake History",
                                    "%s: %s\n" %(currentTime,statusMSG))
      myObject.reportToFinalCutServer()
          
      return exitStatus
  else:
    myObject.setFCSXMLFile(xmlinPath)
    
    ## If we're uploading, log a message that we are uploading and report 
    ## to FCS immediately.
    if myObject.preflightCheck():
      ## Date/time string used for reporting
      currentTime = datetime.datetime.fromtimestamp(
                              time.mktime(datetime.datetime.now().timetuple()))
        
    ## Update status prior to upload
    myObject.reportToFinalCutServer()
    
    ## Perform Upload
    myObject.upload()
    
    ## Delete our support files:
    if not keepFiles:
      print "Cleaning up files"
      myObject.deleteSupportFiles()
    else: 
      print "keepfiles option set; skipping file cleanup"
   

  ## Report in for our final time.
  myObject.reportToFinalCutServer()
  return 0

## If we called this file directly call main()
if __name__ == "__main__":
  try:
    sys.exit(main())
  except Exception as inst:
    print "An unknown error occurred: %s:%s." % (inst.__class__.__name__,inst)
    raise
    sys.exit(99)

