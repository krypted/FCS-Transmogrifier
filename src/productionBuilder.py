#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
.. This script can be utilized as a framework for customized 
  production automations.

'''

################################
##
##  Transmogrifier: productionBuilder
##  A Final Cut Server integration tool to automate
##  Procedures upon production creation. This script
##  can be utilized as a framework for customized
##  production creation automations.
##  
##  This file is part of Transmogrifier.
#############################################################

import sys,getopt,os.path,shutil,subprocess
import re,datetime,time,tempfile,copy
from fcsxml import *
import ConfigParser

from xml.dom import minidom

## Get our framework version information, which has been imported into our 
## local namespace

frameworkVersion = version
frameworkBuild = build

version = '1.0b'
build = '2011041401'

debug = True
keepFiles = False        


######################### START FUNCTIONS ###############################

def helpMessage():
    print '''
Usage: 
  
  productionBuilder.py --createProductionFromTemplate --productionID=10
      
Options: 
  -h, --help                  Displays this help message
  -v, --version               Display version number
  -c pathtofile,              Utilize pathtofile for configuration parameters.
    --configFile=pathtofile
  --deviceName='Media'        The device to copy the template folder to. If 
                              omitted, this value will be read from our 
                              configuration file (default:
                              /usr/local/etc/transmogrifier.conf).

   '''

def printVersionInfo():
  '''Prints out version info'''
  print ("\nproductionBuilder.py\n  Version: %s Build: %s\n"
        "  Framework Version: %s Build: %s\n\n"
        "Copyright (C) 2009-2011 Beau Hunter, 318 Inc.\n" % (version,build,
                                                        frameworkVersion,
                                                        frameworkBuild))

def main():
  '''Our main function, filters passed arguments and loads the appropriate object'''
  
  ## Behavioral vars
  overwriteExistingFiles = True
  
  ## Init vars
  productionID = ''
  action = ''
  templateFolderPath = ''
  deviceName = ''
  devicePath = ''
  productionTitle = ''
  productionMDSet = ''
  assetMDSet = ''
  configFilePath = ''
  
  global debug
  
  
  ## Get our flags
  try:
    optlist, list = getopt.getopt(sys.argv[1:],':hvc:',['productionID=',
      'configFile=','deviceName=','createProductionFromTemplate','assetMDSet=',
      'productionMDSet=','help',
    'version'])
  except getopt.GetoptError:
    print 'Syntax Error!'
    helpMessage()
    return 1
  
  ## If no options are passed, output help
  if len(optlist) == 0:
    printVersionInfo()
    helpMessage()
    return 1
    
  #### PROCESS OUR PASSED ARGUMENTS ####
  for opt in optlist:
    if opt[0] == '-h' or opt[0] == '--help':
      helpMessage()
      return 0
    elif opt[0] == '-v' or opt[0] == '--version':
      printVersionInfo()
      return 0
    elif opt[0] == '--createProductionFromTemplate':
      action == 'createFromTemplate'
    elif opt[0] == 'assetMDSet=':
      assetMDSet = opt[1]
    elif (opt[0] == '--configFile' or opt[0] == '-c'):
      configFilePath = os.path.abspath(os.path.realpath(os.path.expanduser(opt[1])))
    elif opt[0] == '--productionID':
      productionID = opt[1]
    elif opt[0] == '--deviceName':
      deviceName = opt[1]
  
  if not productionID:
    print 'Must be provided a production id with the --productionID option!'
    return 1
  
  ## Import our configuration settings, if no configFile was provided,
  ## refer to our default of /usr/local/etc/transmogrifier.conf
  if configFilePath and not os.path.isfile(configFilePath):
    print 'Specified configuration file:%s does not exist, exiting!'
    return 3
  elif not configFilePath:
    configFilePath = '/usr/local/etc/transmogrifier.conf'
  try:
    cfgParser = ConfigParser.SafeConfigParser()
    cfgParser.read(configFilePath)
  except Exception,err:
    print ('Error reading configuration data from %s, Error: %s' % (configFilePath,err))

  ## Read in our template folder path
  try:
    templateFolderPath = cfgParser.get('ProductionBuilder','templateFolderPath')
  except:
    try:
      templateFolderPath = cfgParser.get('GLOBAL','templateFolderPath')
    except:
      print ('Could not read templateFolderPath from file: %s, cannot continue!'
              % configFilePath)
      return 4
  ## Read in our asset MD set if none was specified.  
  if not assetMDSet:
    try:
      assetMDSet = cfgParser.get('ProductionBuilder','assetMDSet')
    except:
      print 'Error Reading Asset MD Set, cannot continue!'
      return 4
  
  
  
  
  ## Make sure our template exists
  if not os.path.exists(templateFolderPath):
    print ('Template could not be found at path: %s' % templateFolderPath)
    return 4
  
  ## If we don't have a specified device name, read in our default device location
  if not deviceName:
    try:
      deviceName = cfgParser.get('ProductionBuilder','targetDeviceName')
    except:
      try:
        deviceName = cfgParser.get('GLOBAL','defaultdevicename')
      except:
        print ('Could not read defaultdevicename from file: %s, cannot continue!'
              % configFilePath)
        return 5
  
  ## Extract our field map from our config file, this is a string value with two
  ## delimiters: a comma separates each project/asset field mapping pair,
  ## and a colon delimits the project to asset field mapping. Thus, the string 
  ## 'Title:Project Name,Client:Client' will map production field 'Title' to
  ## asset field 'Project Name' and production field 'Client' to asset field
  ## 'Client'. We extrapolate this string to a key/value dictionary. For 
  ## mappings where both target and source have the same field name, the colon
  ## can be ommited (i.e.: 'Title:Project Name,Client,Neighborhood')
  try:
    productionAssetMapString = cfgParser.get('ProductionBuilder',
                                                'productionAssetFieldMap')
    productionAssetMap = {}
    for fieldPair in productionAssetMapString.split(','):
      fieldPairList = fieldPair.split(':')
      if len(fieldPairList) == 1:
        productionAssetMap[fieldPairList[0]] = fieldPairList[0]
      else:
        productionAssetMap[fieldPairList[0]] = fieldPairList[1]
    
  except:
    print ('Could not extract production/asset field map from config file: %s'
            % configFilePath)
  
  ## Extract our devicepath from our device name (using transmogrifier)
  myFCSVRProd = FCSVRClient(entityType='project')
  myFCSVRProd.initWithProductionID(productionID=productionID)
  try:
    deviceDict = myFCSVRProd.deviceWithName(deviceName)
    devicePath = deviceDict['FSPATH']
  except:
    print 'Error reading information for device:%s, cannot continue!'
    return 6
    
  ## Extract our FCS Production title and current metadata set
  productionTitle = myFCSVRProd.valueForField('Title')
  ## replace forward slash characters '/' with colons as this value will be used
  ## to determine final file name.
  fsSafeProductionTitle = productionTitle.replace('/',':')
  
  productionMDSet = myFCSVRProd.entityMetadataSet
  
  ''' ## Removed: these are YPM specific.
  ## Extract the last segment of our MD set
  assetMDSet = re.sub(r'.*-_(.*)',r'pa_asset_youplus_\1',productionMDSet)
  print 'Found production MDSet: %s, using asset MDSet: %s' % (productionMDSet,
                                                                assetMDSet)
  '''
  
  ## Make sure by this point we have established an asset MD set.
  if not assetMDSet:
    print 'No asset metadata set specified, defaulting to \'asset_project\''
    assetMDSet = 'asset_project'
  
  ## Copy our template production to our device
  print 'Copying template to device: %s with ProjectName: %s' % (deviceName,
                                                                  fsSafeProductionTitle)
  
  ## First create our directory, named after the production Title
  try:
    projectDirectory = os.path.join(devicePath,fsSafeProductionTitle)
    if (not os.path.exists(projectDirectory) and not os.path.isdir(projectDirectory)):
      os.mkdir(projectDirectory)
  except Exception, err:
    print 'ERROR: Could not create directory: %s Error:%s' % (projectDirectory,err)
    return 7
  
  ## Iterate through all items in our template, renaiming "_ProductionTitle_"
  ## to our production title.
  fsList = os.listdir(templateFolderPath)
  for fsName in fsList:
    
    ## if the processed item begins with '.', skip it.
    if fsName[0:1] == '.':
      continue
    
    ## Compute our destination fs name
    destinationFSName = (re.sub(r'_ProductionTitle_',r'%s' 
                                  % fsSafeProductionTitle,fsName))
    
    ## Save our source and destination paths to vars
    sourcePath = os.path.join(templateFolderPath,fsName)
    destinationPath = os.path.join(projectDirectory,destinationFSName)
    
    ## Perform our copy
    if not os.path.exists(destinationPath):
      if os.path.isdir(sourcePath):
        ## If the item is a directory, copy it and loop
        shutil.copytree(sourcePath,destinationPath)
        continue
      elif os.path.isfile(sourcePath):
        ## If the item is a directory, copy it and loop
        shutil.copy(sourcePath,destinationPath)
      else:
        print 'Skipping non file or directory: %s' % sourcePath
        continue
    else:
      print 'Skipping file copy: %s, file already exists!' % destinationPath
      
    ## Create an FCSVRClient object for our asset
    myFCSVRAsset = FCSVRClient()
    
    ## Iterate through our production/asset map and set our asset metedata
    for productionFieldName,assetFieldName in productionAssetMap.iteritems():
      try:
        if debug:
          print 'DEBUG: Reading field: %s from project.' % productionFieldName
        productionField = myFCSVRProd.fieldWithName(productionFieldName)
        productionFieldValue = myFCSVRProd.valueForField(productionFieldName)
        
        ## If the current value is empty, we can move on (unless we're bool).
        if not productionFieldValue and not productionField.dataType == 'bool':
          continue
        
        if debug:
          print 'DEBUG: Setting field: %s on asset.' % assetFieldName
        
        ## Create our FCSField
        assetField = FCSXMLField(name=assetFieldName,
                                    value=productionFieldValue,
                                    dataType=productionField.dataType)
                                                    
        ## Set our field
        myFCSVRAsset.setField(assetField)
      except Exception, err:
        print ('An error occured setting field: \'%s\' Error: \'%s\'' 
            % (assetFieldName,err))
    
    ## Create our asset, setting MD
    myFCSVRAsset.createAssetFromFSPath(path=destinationPath,
                                        deviceName=deviceName,
                                        mdSet=assetMDSet,
                                        relPath=fsSafeProductionTitle,
                                        setMD=True)
    if debug:
      print "DEBUG: asset fields: %s" % myFCSVRAsset.fields.keys()
                                        
    ## Add our new asset to our production
    myFCSVRProd.addMemberToProduction(member=myFCSVRAsset)
                                      
  
  return 0
  
  
## If we called this file directly call main()
if __name__ == '__main__':
    sys.exit(main())
 
