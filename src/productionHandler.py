#!/usr/bin/python

'''
.. This script provides the ability to export and import production membership.

'''

################################
##
##  Transmogrifier: productionHandler
##  A Final Cut Server integration tool to import and export group membership.
##  
##  This class provides a generic interface for importing 
##  and exporting production membership.
## 
#############################################################

import sys,getopt,os.path,shutil,subprocess
import re,datetime,time,tempfile,copy
from fcsxml import *


from xml.dom import minidom
frameworkVersion = version
frameworkBuild = build

version = '1.0b'
build = '2011042001'

debug = False
keepFiles = False        



######################### START FUNCTIONS ###############################

def helpMessage():
    print '''Usage: 
  
  productionHandler.py --importFile=/file.xml --productionID=10
  productionHandler.py --exportFile=/production_10.xml --productionID=10
  productionHandler.py --importFile=/file.xml --createProduction
  productionHandler.py --configFile=/etc/my.conf --importFile=file.xml
  productionHandler.py [option]
    
Options: 
  -h, --help                  Displays this help message
  -v, --version               Display version number
  -c pathtofile,              Utilize pathtofile for configuration parameters.
    --configFile=pathtofile


   '''

def printVersionInfo():
  '''Prints out version info'''
  
  print ("\nproductionHandler.py\n  Version: %s Build: %s\n"
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
  filePath = ''
  newProductionMDSet = ''     ## This should be pulled from a conf file.
  tempProductionMDSet = ''    ## This is used to create temporary productions
                              ## which we use to remove assets from a production
                              ## This setting should be pulled from a conf file.
  containerProductionTitle = ''
  containerProductionMDSet = '' ## If we are set to use a parent container via
                                ## containerProductionTitle, and no such 
                                ## production exists, create it with this mdset.

  
  membersField = 'Members'
  missingMembersField = 'Missing Members'
  membershipKey = 'Asset ID'
  exportFields = []
  
  configFilePath = ''
  forceKeepFiles = False
  
  debug = False
  
  ## Get our flags
  try:
    optlist, list = getopt.getopt(sys.argv[1:],':hvc:',['importFile=',
    'exportFile=','productionID=','configFile=','createProduction','help',
    'version','keepFiles','debug'])
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
    elif opt[0] == '--createProduction':
      action == 'create'
    elif opt[0] == '--importFile':
      filePath = os.path.abspath(os.path.realpath(os.path.expanduser(opt[1])))
      if not os.path.isfile(filePath):
        print 'XML file does not exist at path: %s' % filePath
        return 2
      if action and not action == 'create':
        print 'Cannot set importFile, action:%s already specified!' % action
        return 3
      elif not action == 'create':
        action='import'
    elif opt[0] == '--exportFile':
      filePath = os.path.abspath(os.path.realpath(os.path.expanduser(opt[1])))
      if os.path.isfile(filePath):
        if overwriteExistingFiles:
          os.remove(filePath)
        else:
          print 'Cannot export new XML, file already exists at path:%s' % filePath
          return 4
      if action:
        print 'Cannot set exportFile, action:%s already specified!' % action
        return 3
      action='export'
      filePath = opt[1]
    elif (opt[0] == '--configFile' or opt[0] == '-c'):
      configFilePath = os.path.abspath(os.path.realpath(os.path.expanduser(opt[1])))
    elif opt[0] == '--productionID':
      productionID = opt[1]
    elif opt[0] == '--keepFiles':
      forceKeepFiles = True
    elif opt[0] == '--debug':
      debug = True      
  
  ## If we are exporting, make sure we have a productionID
  if not productionID and action == 'export':
    print 'Syntax Error! Must be provided a production ID with --productionID='
    return 1

  
  ## Import our configuration settings, if no configFile was provided,
  ## refer to our default of /usr/local/etc/transmogrifier.conf
  if configFilePath and not os.path.isfile(configFilePath):
    print 'Specified configuration file:%s does not exist, exiting!'
    return 3
  elif not configFilePath:
    configFilePath = '/usr/local/etc/transmogrifier.conf'
  try:
    cfgParser = SafeConfigParser()
    cfgParser.read(configFilePath)
  except:
    print ('Error reading configuration data from %s, proceeding with '
            ' default values' % configFilePath)
  try:
    newProductionMDSet = cfgParser.get('ProductionHandler',
                                                        'newProductionMDset')
  except:
    pass
  
  if not debug:
    try:
      debug = cfgParser.get('ProductionHandler','debug')
    except:
      try:
        debug = cfgParser.get('Global','debug')
      except:
        pass
  try:
    tempProductionMDSet = cfgParser.get('ProductionHandler',
                                                        'tempProductionMDset')
  except:
    pass
  try:
    membersField = cfgParser.get('ProductionHandler','membersField')
  except:
    print 'An error occured reading key: membersField'
    pass
  try:
    exportFields = cfgParser.get('ProductionHandler','exportFields').split(',')
  except:
    pass
  try:
    membershipKey = cfgParser.get('ProductionHandler','membershipKey')
  except:
    pass
  try:
    missingMembersField = cfgParser.get('ProductionHandler','missingMembersKey')
  except:
    pass
  ## Try to read in any parent production values
  try:
    containerProductionTitle = cfgParser.get('ProductionHandler',
                                                    'containerProductionTitle')
    if containerProductionTitle:
      try:
        containerProductionMDSet = cfgParser.get('ProductionHandler',
                                                      'containerProductionMDSet')
      except:
        print ('Error reading containerProductionMDSet value from our '
          ' configuration, using default: %s' % newProductionMDSet)
        containerProductionMDSet = newProductionMDSet
  
        
        
  except:
    if not containerProductionMDSet:
      containerProductionMDSet = newProductionMDSet
      

  ## If new or temp productions aren't set, Try to get our default production
  ## from our fcsvr_client config
  if not newProductionMDSet or not tempProductionMDSet:
    defaultProductionMDSet = 'pa_production_package'
    try:
      defaultProductionMDSet = cfgParser.get('FCSVRClient','defaultproductionmdset')
    except:
      pass
    if not newProductionMDSet:
      newProductionMDSet = defaultProductionMDSet
      print 'Using default production mdset: %s' % newProductionMDSet
    
    if not tempProductionMDSet:
      tempProductionMDSet = defaultProductionMDSet
      print 'Using default temprorary production mdset: %s' % tempProductionMDSet
        
  
  
  ## Do our work
  if action == 'import' or action == 'create':
    
    print 'Importing production from file: %s with action: %s' % (filePath,action)
    
    ## Create our FCSXMLObject based upon our filePath
    myFCSXMLObj = FCSXMLObject()
    myFCSXMLObj.setFile(filePath)
    
    ## Make sure that we're a production, bail if we're not.
    if not myFCSXMLObj.entityType == 'project':
      print ('Specified XML file is not a project, it specifies entityType:%s' 
              % myFCSXMLObj.entityType)
      return 2
  
    ## If we were passed a productionID explicitely, use it from here on out,
    ## otherwise, fetch it from the XML file.
    if productionID:
      myFCSXMLObj.entityID = productionID
    else:
      productionID = myFCSXMLObj.entityID
    

    ## Get our production title
    try:
      productionTitle = myFCSXMLObj.valueForField('Title')
      if not productionTitle or productionTitle == " ":
        raise
    except:
      productionTitle = 'unknown'
    
    ## Create a list based upon XML members attribute.
    try:
      print (" - Determining import values for entity: '%s' from Field: '%s'"
                                      % (myFCSXMLObj.entityPath(),membersField))
      importMemberValues = myFCSXMLObj.valueForField(membersField).split(',')
      if debug:
        print "DEBUG: Found import values: %s" % importMemberValues
    except Exception,excp:
      print ("WARNING: Could not load attribute '%s' from passed XML. Error: %s" 
                                                      % (membersField,excp))
      importMemberValues = []
        
    ## strip white space
    importMemberValues = [memberValue.strip() for memberValue in importMemberValues]
    
    importMembers = {}         ## Dictionary of FCSVRClient objects, keyed by asset path (i.e. /asset/10)
    sortedMemberIndex = []     ## List of members in sorted order
    invalidMembers = []         ## List of invalid memberValues.
    
    ## Iterate through our members and fetch each's asset ID
    count = 0
    for memberValue in importMemberValues:
      if debug:
        print 'DEBUG: processing memberValue: %s' % memberValue
    
      ## Create an FCSVRClient object for our memberID
      memberFCSObj = FCSVRClient(configParser=cfgParser)
      if debug:
        memberFCSObj.debug = True
      try:
        memberFCSObj.initWithAssetFromField(FCSXMLField(name=membershipKey,value=memberValue))
      except Exception, excp:
        print ('   * Cannot find asset for field: \'%s\' with value: \'%s\', '
           'unable to add to production list' % (membershipKey,memberValue))
        invalidMembers.append(memberValue)
        continue
      
      count += 1
      ## Create our productionID field
      try:
        productionIndexField = memberFCSObj.fieldWithName('Production Index')
        productionIndexField.setValue(count)
        memberFCSObj.setMD()
        
        if debug:
          print ('DEBUG: Built new member /asset/%s with production index:%s' 
              % (memberFCSObj.entityID,
                  memberFCSObj.valueForField('Production Index')),'debug')
      except:
        print 'WARNING: Could not set value for field \'Production Index\''
        if debug:
          print 'DEBUG: Built new member /asset/%s' % (memberFCSObj.entityID)

      
      importMembers['/asset/%s' % memberFCSObj.entityID] = memberFCSObj
      
    
    ## Create our FCSVRClient object based upon our productionID, if we
    ## don't have a productionID, extract the production title form the XML
    ## and search for an existing production based on that name. If this
    ## search fails, create a production based on that info.
    myFCSVRProd = FCSVRClient(entityType='project',configParser=cfgParser)
    
    ## Load our production with values in our XML import file
    try:
      print '   - Loading production data from XML file...'
      myFCSVRProd.loadFromFCSXMLObject(myFCSXMLObj)
    except FCSObjectLoadError:
      pass
        
    if debug:
      myFCSVRProd.debug = True
    try:
      if productionID:
        try:
          if debug:
            print '   - Loading Production with ID:%s' % productionID
          myFCSVRProd.initWithProductionID(productionID)
        except:
          print ('Error: Could not load production with ID: %s, no such production '
                    'exists! Attempting to load from Title: \'%s\''
                    % (productionID,productionTitle))
          myFCSVRProd = myFCSVRProd.productionWithTitle(title=productionTitle,mdSet=newProductionMDSet)
          if debug:
            myFCSVRProd.debug = True        
      else:
          ## Search for our production based on title
          if not action == 'create':
            print '   - No production ID specified, loading from title: \'%s\'' %productionTitle

          myFCSVRProd = myFCSVRProd.productionWithTitle(title=productionTitle,mdSet=newProductionMDSet)
          if debug:
            myFCSVRProd.debug = True
          productionID = myFCSVRProd.entityID
    except:
      ## If production does not exist, create it.
      if not action == 'create':
        print ('   - No production with title: \'%s\' could be found, creating new'
                ' production!' % productionTitle)
      elif action == 'create':
        print '   - Creating production with title: \'%s\'' % productionTitle

      ## Create our production.
      try:
        ## If we have a parent production specified via the the 
        ## containerProductionTitle var.Search for the production, create it 
        ## if it doesn't exist.
        
        if containerProductionTitle:
          myFCSVRParentProd = FCSVRClient(entityType='project')
          try:
            myFCSVRParentProd.initWithProductionTitle(containerProductionTitle)
          except:
            print ('Creating parent production: %s with MDSet: %s' 
                          % (containerProductionTitle,containerProductionMDSet))
            myFCSVRParentProd.createProduction(title=containerProductionTitle,
                                                mdSet=containerProductionMDSet)
        
          myFCSVRProd.createProduction(title=productionTitle,
                            parentProjectAddress=myFCSVRParentProd.entityPath(),
                            mdSet=newProductionMDSet)
        else:
          myFCSVRProd.createProduction(title=productionTitle,mdSet=newProductionMDSet)
          
        productionID = myFCSVRProd.entityID
      except FCSProductionLoadError:
        print ('Error: Failed to create production with Title:%s Metadata Set:%'
            % (productionTitle,newProductionMDSet)) 
        return 7
    
    if debug:
      print 'DEBUG: Built production with ID: %s' % myFCSVRProd.entityID
    
    ## Build our current member list.
    try:
      currentMembers = myFCSVRProd.productionAssetAddresses()
    except:
      currentMembers = []
      
    ## Iterate through our FCS productions current members
    for currentMember in currentMembers:
      ## If member (/asset/10) is not in the new list, remove it from the production
      if not currentMember in importMembers:
        print ("%s is no longer a member of importMembers: %s "
            "production:%s productionID:%s" 
            % (currentMember,",".join(importMembers),productionTitle,productionID))
            
        ## Remove the current member from the production.
        myFCSVRProd.removeMemberFromProduction(memberPath=currentMember,
                                        tempProductionMDSet=tempProductionMDSet)
        
    ## Iterate through our XML members attribute, add any new
    ## assets to the production
    for importMemberPath,importMember in importMembers.iteritems():
      ## If XML member is not in the current member list, add it.
      if debug:
        print "DEBUG: ImportMemberPath:%s  %s" % (importMemberPath,currentMembers)
      if not importMemberPath in currentMembers:
        print "Adding asset:%s to production:%s" % (importMemberPath,
                                                    myFCSVRProd.entityPath())
        
        '''myFCSVRProd.fcsvr_client_make_link(linkType=1,
                                          parentPath=myFCSVRProd.entityPath(),
                                          childPath=importMemberPath,
                                          moveLink=False)
        '''
        myFCSVRProd.debug = True
        myFCSVRProd.addMemberToProduction(memberPath=importMemberPath)
    
    
    ## Flag field to check into FM if this is a new production. 
    if action == 'create':
      try:
        exportFieldName = 'Export as Playlist to FM'
        FMExportField = myFCSVRProd.fieldWithName(exportFieldName)
        FMExportField.setValue(True)
      except:
        pass
      
    ## Remove the membersField from our production if it exists
    if membersField in myFCSVRProd.fields:
      del myFCSVRProd.fields[membersField]

    ## If we have invalid members, add them to the missingMembersField.
    if len(invalidMembers) > 0:
      missingMembersField = FCSXMLField(name=missingMembersField,
                                              dataType='string',
                                              value=','.join(invalidMembers))
    else:
      missingMembersField = FCSXMLField(name=missingMembersField,
                                            dataType='string',
                                            value='')  
    try:
      myFCSVRProd.setField(missingMembersField)
    except:
      pass

    ## Commit to FCS if we have any saved fields
    if len(myFCSVRProd.fields) > 0:
      try:
        myFCSVRProd.setMD()
      except Exception,excp:
        print 'ERROR: An error occurred setting metadata! Error: %s' % excp
    ## Cleanup the import file.
    if not keepFiles and not forceKeepFiles:
      os.remove(filePath)
        
  elif action == 'export':

    ## Export vars
    exportMembers = {}
    sortedMemberIDs = []
    sortedMemberPaths = []
    sortedMemberTitles = []
    invalidMembers = []
        
    ## Fetch our Production
    myFCSVRProd = FCSVRClient()
    if debug:
      myFCSVRProd.debug = True
    
    try:  
      myFCSVRProd.initWithProductionID(productionID)
    
    except FCSObjectLoadError:
      print ('Could not continue, production with id:%s does not exist!' 
                                                              % productionID)
      return 4
      
    myFCSVRProdTitle = myFCSVRProd.valueForField('Title')
    
    ## Build our iist of member asset paths 
    assetMemberPaths = myFCSVRProd.productionAssetAddresses(recurse=False)
    
    ## Iterate through members and sort based on Production Index
    for assetMemberPath in assetMemberPaths:
      if debug:
        print "DEBUG: Processing member:%s" % assetMemberPath
      ## Extract the asset id
      match = re.match("/asset/(\d+)",assetMemberPath)
      assetMemberID = match.group(1)
      
      ## Create our FCSVRClient object
      assetMemberFCSObj = FCSVRClient()
      assetMemberFCSObj.initWithAssetID(assetMemberID)
      
      ## Populate our exportMembers dict
      exportMembers[assetMemberID] = assetMemberFCSObj
      
      ## Fetch our production Index
      assetMemberProductionIndex = assetMemberFCSObj.valueForField('Production Index')
      
      ## Iterate through our sorted members list and insert where appropriate
      if len(sortedMemberIDs) == 0 or not assetMemberProductionIndex:
        sortedMemberIDs.append(assetMemberID)
        print "Sorting memberID:%s Inserting at end of list." % (assetMemberID)

      else:
        sortedCount = 0
        didSort = False
        for sortedMemberID in sortedMemberIDs:
          sortedMemberObj = exportMembers[sortedMemberID]
          sortedMemberProdIndex = sortedMemberObj.valueForField('Production Index')
          print "Comparing %s to %s" % (assetMemberProductionIndex,sortedMemberProdIndex)
          if assetMemberProductionIndex < sortedMemberProdIndex:
            print "Sorting memberID:%s Inserting at spot:%s" % (assetMemberID,sortedCount)
            sortedMemberIDs.insert(sortedCount,assetMemberID)
            didSort = True
            break
          sortedCount +=1
        
        print "Current sort order:%s" % sortedMemberIDs

        if not didSort:
          sortedMemberIDs.append(assetMemberID)
          
    
    ## Create string XML field,csvString membersField attribute is built on Title
    sortetMemberTitles = []
    for sortedMemberID in sortedMemberIDs:
      sortedMemberObj = exportMembers[sortedMemberID]
      ## append
      sortedMemberTitles.append(sortedMemberObj.valueForField(membershipKey))
    
    ## Extract our missing members value
    try:
      missingMembers = myFCSVRProd.valueForField(missingMembersKey)
    except:
      missingMembers = ''
      pass
    
    ## Create our csv string, append any missing members onto the back of it
    membersFieldString = ",".join(sortedMemberTitles)
    if missingMembers:
      membersFieldString = "%s,%s" % (sortedMemberTitles,missingMembers)
      
  
    membersField = FCSXMLField(dataType="string",
                          name=membersField,
                          value=membersFieldString)
  
    ## Add to our FCSXML object.
    myFCSXMLObj = FCSXMLObject()
    if debug:
      myFCSXMLObj.debug = True
  
    ## load our export fields
    for fieldName in exportFields:
      myFCSVRProd.loadFieldWithName(fieldName)
      
    ## Load our fcsxml.FCSXMLObject
    myFCSXMLObj.loadFromFCSVRClient(fcsvrClient=myFCSVRProd)
    myFCSXMLObj.appendField(membersField)
    
    ## Write out new XML file.
    print "Finished Processing, exporting XML to file:%s" % filePath
    myFCSXMLObj.xmlOut(filePath=filePath)
  
      
  else:
    print 'No action was provided!'
    return 3
  
  if len(invalidMembers) > 0:
    print ('Failed to add members: %s to productionID: %s' 
              % (','.join(invalidMembers),productionID))
    return 1
  
  return 0
  
  
## If we called this file directly call main()
if __name__ == '__main__':
    sys.exit(main())
 
