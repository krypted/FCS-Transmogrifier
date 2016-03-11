#!/usr/bin/python
# -*- coding: utf-8 -*-


################################
##
##  Transmogrifier: TransmogrifierTargt
##  A Final Cut Server import/export tool 
##
##  This the root class for Transmogrifier Modules. This class provides
##  various methods which assist in the conversion of FCS XML and media files 
##  to a third party format. 
##
#############################################################



import os, os.path, re, glob, hashlib, shutil, sys, types, datetime, time
from ftplib import FTP
from fcsxml import FCSXMLField, FCSXMLObject
from ConfigParser import *

from xml.dom import minidom

  
class TransmogrifierTargetObject:
  """Our main FCS transmogrifier class, used for collecting media files, interpretting
  FCS XML, writing XML and uploading"""
  
  ## FCS fields
  entityID = 0
  title = ""
  emailToNotify = ""
  approver = ""
  serviceName = "default"    ## Name of our service. I.E. 'BrightCove' || 'YouTube'
  eventLocation = ""
  eventYear = ""
  description = ""
  longDescription = ""
  publishHistory = ""
  publisherID = ""
  keywordString = ""
  frameHeight = ""
  frameWidth = ""

  ## Support vars
  ftpHost = ""
  ftpUser = ""
  ftpPassword = ""
  multipleBitRate = False ## whether we check for bitrate specific iterations of a media file
  supportPath = ""    ## Avoid modifying this directly, use setSupportDir accessor method
  supportSubDirs = []
  xmlObject = ""
  fcsXMLObject = ""
  fcsXMLOutObject = ""
  fcsXMLInPath = ""  
  fcsXMLOutDir = ""
  overwriteExistingFiles = ""
  files = {}
  log = []
  lastError = ""
  lastMSG = ""
  baseName = ""
  fileBaseName = ""
  debug = False
  configParser = ""
  
  fcsvr_client = False                ## Whether this module can use fcsvr_client
  fcsvr_client_all = False            ## Whether this module should always use fcsvr_client
  
  neededAttributes = []               ## Specify any attributes which need to be 
                                      ## populated prior to publishing.
  missingAttributes = []
  reqFCSFields = []
  validActions = ["preflightCheck",
                    "printXML",
                    "listFCSFields",
                    "createSupportFolders",
                    "appendField"]


  
  def __init__(self, entityID=0):
    """Our construct, instantiate our members"""
    self.entityID = entityID
    self.title = ""
    self.emailToNotify = ""
    self.approver = ""
    self.supportPath = ""
    self.description = ""
    self.longDescription = ""
    self.serviceName = "default"
    self.keywordString = ""
    self.publishHistory = ""
    self.publisherID = ""
    self.frameHeight = ""
    self.frameWidth = ""
    self.eventLocation = ""
    self.eventYear = ""
    self.ftpHost = ""
    self.ftpUser = ""
    self.ftpPassword = ""

    self.xmlObject = ""  
    self.fcsXMLObject = FCSXMLObject()  
    self.fcsXMLOutObject = ""
    self.overwriteExistingFiles = True
    self.files = {}
    self.log = []
    self.lastError = ""
    self.lastMSG = ""
    self.fileBaseName = ""
    self.supportSubDirs = [];
    self.neededAttributes = []
    self.missingAttributes = []
    self.reqFCSFields = ['(string) Status']
    self.validActions = ["preflightCheck",
                          "printXML",
                          "listFCSFields",
                          "createSupportFolders",
                          "appendField"]
    self.configParser = ""
    
    self.fcsvr_client = False
    self.fcsvr_client_all = False
    
    
  def logger(self, logMSG, logLevel="normal"):
    """(very) Basic Logging Function, we'll probably migrate to msg module"""
    if logLevel == "error" or logLevel == "normal" or self.debug:
      print "%s: %s" % (self.serviceName, logMSG)
      self.lastMSG = logMSG
    if logLevel == "error":
      self.lastError = logMSG
    self.log.append({"logLevel" : logLevel, "logMSG" : logMSG})
    
  def printLogs(self, logLevel="all"):
    """output our logs"""
    for log in self.log:
      if logLevel == "all" or logLevel == log["logLevel"]:
        print "%s:%s:%s" % (self.serviceName,log["logLevel"], log["logMSG"]) 
  
  def loadConfiguration(self, parser):
    """Load from configuration file, expects a ConfigParser type object. If you subclass, 
    you should call this function. If we return false then you should abort. or do your own sanity checks"""
    if not isinstance(parser,ConfigParser):
      self.logger("loadConfiguration() Not passed a valid ConfigParser Object!", "error")
      return False
    try:
      self.configParser = parser
      if not self.supportPath:
        self.supportPath = parser.get("GLOBAL","path")
      self.emailToNotify = parser.get("GLOBAL","emailtonotify")
      self.debug = parser.getboolean("GLOBAL","debug") 
    except:
       self.logger("loadConfiguration() Problem loading configuration records, please double check your configuration", "error") 
    return True

    

  def createSupportFolders(self, path):
    """Creates a support folder at specified path, create subdirectories specified by self.supportSubDirs""" 
    ## var for tracking any occured errors
    returnValue = True
    if not os.path.isdir(os.path.dirname(path)):
      self.logger("Could not create folder structure, invalid path: '%s'" % path, "error")
      return False
    if not os.path.exists(path):
      self.logger("Creating Directory: '%s'" % path)
      os.mkdir(path)
    if not os.path.isdir(path):
      self.logger("Could not create folder structure, invalid object exists at path: '%s'" % path, "error")
      return False
      
    ##self.logger("createSupportFolders() Examining support folder structure at path: '%s'" % path, "detailed")
    for subDir in self.supportSubDirs:
      dir = os.path.join(path, subDir)
      if not os.path.exists(dir):
        self.logger("Creating Directory: '%s'" % dir)
        os.mkdir(dir)
      elif not os.path.isdir(dir):
        self.logger("Could not create subfolder '%s', invalid object exists at path: '%s'" % (path, dir), "error")
        returnValue = False
    return returnValue

  def deleteSupportFiles(self):
    """Delete Registered support files (media and xml)"""
    if len(self.files) > 0:
      for file in self.files.itervalues():
        if os.path.exists(file.path):
          self.logger("Removing file at path: '%s'" % file.path, "detailed")
          os.remove(file.path)
    if self.fcsXMLObject:
      xmlInPath = self.fcsXMLObject.path
    if os.path.exists(xmlInPath):
      self.logger("Removing file at path: '%s'" % xmlInPath, "detailed")
      os.remove(xmlInPath)
          
    xmlOutPath =  os.path.join(self.supportPath, "xmlout", "%s.xml" % self.entityID)
    if os.path.exists(xmlOutPath):
      os.remove(xmlOutPath)
    
    
  def preflightCheck(self):
    """Run a preflight check to ensure all required variables are set"""
    exitCode = 0
    missingAttributesString = ""  
    
    ## check members
    if not self.entityID:
      self.logger("Could not determine entityID, aborting!", "error")
      return False
    if not (self.supportPath):
      self.logger("No support Path specified!", "error")
      return False
    if not os.path.isdir(self.fcsXMLOutDir):
      self.logger("Could not determine fcsXMLOut Path!", "error")
      return False
    
    ## iterate through specified needed attributes and ensure all are set
    for attribute in self.neededAttributes:
      if not attribute or not eval("self.%s" % attribute):
        self.missingAttributes.append(attribute)
        if not missingAttributesString:
          missingAttributesString = attribute
        else:
          missingAttributesString += ", %s" % attribute
          
    currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))
    if len(self.missingAttributes) > 0:
      tempHistString = "%s: Could not process for output. Missing %d Attributes: %s" % (currentTime,len(self.missingAttributes),missingAttributesString)
      self.logger(tempHistString,"error")
      exitCode = 3
    else:
       ## Date/time string used for reporting
      tempHistString = "%s: Beginning processing for output to: '%s' approved by '%s'" % (currentTime,self.serviceName, self.approver)
    ## do our reporting.
    try:
      fieldName = "%s Publish History" % self.serviceName
      self.appendFCSField(fieldName,"%s\n" % tempHistString)
    except:
      self.logger('An error occurred appending field: %s' % fieldName,'error')
       
    ## if we've set an exit code, then return false
    if exitCode > 0:
      return False
    else:
      return True

  def runFunction(self, function):
    """Perform action based on passed function, all functions are defined 
    here in this method"""
    if function == "upload":
      return self.upload()
    if function == "preflightCheck":
      return self.preflightCheck()
    if function == "createSupportFolder":
      return self.createSupportFolder()
    if function == "printXML":
      return self.xmlOut()
    if function == "listFCSFields":
      if self.serviceName == 'default':
        print ("Transmogrifier needs the following FCS Fields:\n\t'%s'\n" 
                                              % "', \n\t'".join(self.reqFCSFields))
      else:
        print ("%s module needs the following FCS Fields:\n\t'%s'\n" 
                    % (self.serviceName,"', \n\t'".join(self.reqFCSFields)))
        
      

   
  def getXMLNodeText(self, nodes):
    """returns text value for passed XML text nodes"""
    text = ""
    for node in nodes:
      if node.nodeType == node.TEXT_NODE:
        text = text + node.data
    return text
    
  def setFCSXMLFile(self,filePath):
    """import FCS XML file and set relevant member vars"""
    self.fcsXMLObject = FCSXMLObject()
    if not self.fcsXMLObject.setFile(filePath):
      self.logger("Could Not Load FCS XML File: '%s'" % filePath, "error")
      return False
    self.logger("Loading FCSXML from path: '%s'" % filePath)

    mediaSize = self.fcsXMLObject.valueForField("Image Size")
    try:
      self.frameWidth = re.sub(r'^(\d*?)x(\d*?)$',r'\1',mediaSize)
      self.frameHeight = re.sub(r'^(\d*?)x(\d*?)$',r'\2',mediaSize)
    except:
      self.logger("Could not determine mediaSize from XML!","error")
            
    self.entityID = self.fcsXMLObject.entityID
     
    try:
      if self.fcsXMLObject.valueForField("Description"):
        self.description = self.fcsXMLObject.valueForField("Description")
    except:
      pass
    try:
      if self.fcsXMLObject.valueForField("Keywords"):
        self.keywordString = self.fcsXMLObject.valueForField("Keywords")
    except:
      pass
      
    try:
      if self.fcsXMLObject.valueForField("Publishing Approver"):
        self.approver = self.fcsXMLObject.valueForField("Publishing Approver")
    except:
      pass
    try:
      if self.fcsXMLObject.valueForField("%s Publish History" % self.serviceName):
        self.publishHistory = self.fcsXMLObject.valueForField("%s Publish History" % self.serviceName)
    except:
      pass
    try:
      if self.fcsXMLObject.valueForField("Long Description"):
        self.longDescription = self.fcsXMLObject.valueForField("Long Description")
      if self.fcsXMLObject.valueForField("Event Location"):
        self.eventLocation =  self.fcsXMLObject.valueForField("Event Location")
      if self.fcsXMLObject.valueForField("Event Year"):
        self.eventYear = self.fcsXMLObject.valueForField("Event Year")      
    except:
      pass

    if not self.title:
      self.title = self.fcsXMLObject.valueForField("Title")
    return True
  
  def setFCSField(self,field,data):
    """Sets the value of field to data"""
    
    ## get our asset's id
    assetid = self.entityID
    myField = ""
    
    ## read in the current value of our field, if we already have an 
    ## fcsXMLOut object, attempt to use it's data.  
    if self.fcsXMLOutObject:
      fcsXMLOut = self.fcsXMLOutObject
      myField = fcsXMLOut.fieldWithName(field)
    else:
      self.fcsXMLOutObject = FCSXMLObject(assetid)
      fcsXMLOut = self.fcsXMLOutObject
      myField = self.fcsXMLObject.fieldWithName(field)
      
    if not myField:
      myField = FCSXMLField(field,data.replace('\\n','\n').replace('\\t','\t'))
    else:
      myField.value = data.replace('\\n','\n').replace('\\t','\t')
    return fcsXMLOut.setField(myField)

  def appendFCSField(self,field,data):
    """Appends data to field, aggregates existing data."""
     
     ## get our assets id
    assetid = self.entityID   
    fieldData = ""
    
    ## read in the current value of our field, if we already have an 
    ## fcsXMLOut object, attempt to use it's data.
    if self.fcsXMLOutObject:
      fcsXMLOut = self.fcsXMLOutObject
      try:
        fieldData = fcsXMLOut.valueForField(field)
      except:
        fieldData = ''
    else:
      self.fcsXMLOutObject = FCSXMLObject(assetid)
      fcsXMLOut = self.fcsXMLOutObject
    
    ## if our field isn't already set in our 'out' object, get our value
    ## from our 'in' FCS object
    if not fieldData:
      fcsXML = self.fcsXMLObject
      try:
        fieldData = fcsXML.valueForField(field)
      except Exception,excp:
        print "An error Occurred: %s" % excp
        

    ## check to see if previous history had data, if so, enter a newline and our text
    if fieldData:
      newData = "%s%s" % (fieldData,data)
    else:
      newData = data
    
    if not self.fcsXMLOutObject:
      self.fcsXMLOutObject = FCSXMLObject(assetid)
    
    fcsXMLOut.setField(FCSXMLField(field, newData.replace('\\n','\n').replace('\\t','\t')))
    
  def setSupportPath(self, dirPath):
    '''Set the base directory path utilized for resource storage'''
    if not os.path.isdir(dirPath):
      self.logger("setSupportPath() Directory does not exist:'%s'" % dirPath, "error")
      return False
    self.supportPath = dirPath
    
    ## determine our FCS xmlin dir. This could be in our support path,
    ## or up one level, prefer the latter
    if os.path.isdir(os.path.join(os.path.dirname(dirPath), "fcsvr_xmlin")):
      self.fcsXMLOutDir = os.path.join(os.path.dirname(dirPath), "fcsvr_xmlin")
    else:
      self.fcsXMLOutDir = os.path.join(dirPath, "fcsvr_xmlin")
    

  def upload1(self, dirPath=""):
    '''Uploads all relative assets to the configured ftpHost, also calls xmlOut and uploads the resulting file'''
    theError = ""
    if not dirPath:
      dirPath = self.supportPath
    if not os.path.isdir(dirPath):
      self.logger("upload() Directory does not exist:'%s'" % dirPath, "error")
      return False
    
    xmlOutPath = os.path.join(dirPath, "xmlout", "manifest.xml")
    if not self.xmlOut(xmlOutPath):
      self.logger("upload() could not write XML, exiting", "error")
      return False
      
    ## Establish our FTP connection
    if self.overwriteExistingFiles:
      ftpCommand = "STOR"
    else:
      ftpCommand = "STOU"
      
    if not self.ftpHost or not self.ftpUser or not self.ftpPassword:
      self.logger("upload() missing parameters, could not establish connection to FTP server!", "error")
    try:
      ftp = FTP(self.ftpHost, self.ftpUser, self.ftpPassword)
    except:
      self.logger("upload() failed to connect to FTP server", "error")
      return False
    
    if len(self.files) > 0:
      for file in self.files.itervalues():
        try:
          if os.path.exists(file.path):
            theFile = open(file.path, "r")
            if not file.uploadFileName:
              theFileName = file.fileName
            else: 
              theFileName = "%s" % file.uploadFileName
              
            self.logger("upload() uplaoding file: '%s' as '%s'" % (file.fileName, theFileName), "normal")
            ftp.storbinary("%s %s" % (ftpCommand,theFileName), theFile)
            theFile.close()
        except:
          theError = file.path,sys.exc_info()[0]
          self.logger("upload() could not uplod file: '%s' Error:\n%s" % (theError), "error")
  
        ## shutil.copy(file.path, dirPath)
        ##if not os.path.isfile (os.path.join(dirPath,file.fileName)):
        ##  theError = "Couldn't copy file: '%s'" % file.path
        ##  self.logger("upload() %s" % theError, "error")
    try:
      if os.path.exists(xmlOutPath):
        theFile = open(xmlOutPath, "r")
        self.logger("upload() uplaoding file: 'manifest.xml'", "detailed")
        ftp.storbinary("%s manifest.xml" % (ftpCommand), theFile)
        theFile.close()
    except:
      theError = xmlOutPath,sys.exc_info()[0]
      self.logger("upload() could not upload file: '%s' Error:\n%s" % (theError), "error")
    if not theError:
      self.appendFCSField("%s Publish History" % self.serviceName,"%s: Successfully uploaded to %s.\\n" % (datetime,target)) 
      return True
    else:
      self.appendFCSField("%s Publish History" % self.serviceName,"%s\n%s: Failed to upload to %s. Please try again. Error:\n\t%s\\n" % (publishHistory,datetime,self.serviceName,self.lastError))
      return False
      
  def appendHistory(self, string):
    """Append contents of passed string to our publishHistory"""
    if self.publishHistory:
      self.publishHistory = "%s\n%s" % (self.publishHistory, string)
    else:
      self.publishHistory = string
      
  def readMediaFiles(self, dirPath="",baseName=""):
    '''Cycle through our media support directory and find related media files'''
    if not dirPath:
      dirPath = os.path.join(self.supportPath,"media")
    if not os.path.isdir(dirPath):
      self.logger("readMediaFiles() Directory does not exist:'%s'" % dirPath, "error")
      return False
    if not baseName:
      baseName = self.fileBaseName
      if not baseName:
        self.logger("readMediaFiles() Directory does not exist:'%s'" % dirPath, "error")
        return False
    
    ## Search in the base directory for our assets. If none are found, look
    ## recursively.
    if not self.multipleBitRate:
      for theFilePath in glob.glob( os.path.join(dirPath, "%s*.mov" % baseName)):
        self.logger("readMediaFiles() adding file found at '%s'" % theFilePath, "detailed")
        self.files[theFilePath] = MediaFile(theFilePath)
        theFile = self.files[theFilePath]
        theFile.title = self.title
        ## set a static dimensions, this works in this particular instance
        ## may need refactoring if upload service allows varying sizes
        if self.frameWidth:
          theFile.frameWidth = int(self.frameWidth)
        if self.frameHeight:
          theFile.frameHeight = int(self.frameHeight)
   
    else:
      self.logger("Could not find any files in root of path, searching sub directories", "detailed")
      for theFolderName in (os.listdir(dirPath)):
        if theFolderName == "thumbs":
          continue
        theFolderPath = os.path.join(dirPath, theFolderName)
        if os.path.isdir(theFolderPath):
          self.logger("   searching directory: %s" % theFolderPath, "detailed")
          ## Folder will be named after the bitrate
          for theFilePath in glob.glob(os.path.join(theFolderPath, "%s*.mov" % baseName)):
            self.files[theFilePath] = MediaFile(theFilePath)
            theFile = self.files[theFilePath]
            self.logger("readMediaFiles() adding file found at '%s'" % theFilePath)

                      
            ## set a static dimensions, this works in this particular instance
            ## may need refactoring if upload service allows varying sizes
            ## easiest way to accomplish this will probably be with additional folders
            ## as Python doesn't seem to have a good built-in media module, we'd need to
            ## use an external module (which we're trynig to avoid)
            theFile.frameWidth = int(self.frameWidth)
            theFile.frameHeight = int(self.frameHeight)
            ## Folder will be named after the bitrate, if it's 
            ## numeric, use it's value.
            if re.match('^\d+$', theFolderName):
              theFile.bitRate = int(theFolderName)
              theFile.refID = "%skbps_%s" % ( theFile.bitRate, theFile.refID)
              theFile.uploadFileName = "%skbps_%s" % ( theFile.bitRate, theFile.fileName)
           
          
  def xmlOut(self, filePath=""):
    '''Output our BrightCove compliant XML, you'll likely want to subclass 
    this and ignore all this code'''
    ## Sanity checks and variable initialization
    theThumbFile = ""
    if not (self.supportPath):
      self.logger("Using supportPath: %s" % self.supportPath, "detailed")
      self.logger("No support Path specified!", "error")
      return False     
    if not len(self.files) > 0:
      self.readMediaFiles()
      if not len(self.files) > 0:
        self.logger("No media files were found to upload!", "error")
        return False
    if not self.approver:
      self.logger("No Approver specified!", "error")
      return False
    if not self.description:
      self.logger("No Description Provided!", "error")
      return False
    if not self.publisherID:
      self.logger("No PublisherID specified!", "error")
      return False
    if not self.emailToNotify:
      self.logger("No notification email address specified!", "error")
      return False
    if not self.title:
      self.logger("No title specified!", "error")
      return False
      
    if (filePath and (not os.path.exists(filePath)  \
    or (os.path.exists(filePath) and self.overwriteExistingFiles))
    and os.path.isdir(os.path.dirname(filePath))) \
    or not filePath : 
      ## create our new xml doc, add our root FCS elements:
      ## <?xml version="1.0"?>
      ## <publisher-upload-manifest publisher-id=\"$PUBLISHER_ID\" preparer=\"$PREPARER\">
      ##  <notify email=\"$EMAIL_TO_NOTIFY\" />       
          
      self.xmlObject = minidom.Document()
      xmlDoc = self.xmlObject    

      manifestElement = xmlDoc.createElement("publisher-upload-manifest")
      xmlDoc.appendChild(manifestElement)
      manifestElement.setAttribute("publisher-id", self.publisherID)
      manifestElement.setAttribute("preparer", self.approver)
      manifestElement.setAttribute("report-success", "true")

      notifyElement = xmlDoc.createElement("notify")
      notifyElement.setAttribute("email", self.emailToNotify)
      manifestElement.appendChild(notifyElement)
      renditionReferences = [];
      
      ## And then our individual fields.
      for file in self.files.itervalues():
        if file.fileType == "video":
          theAssetElement = xmlDoc.createElement("asset")
          theAssetElement.setAttribute("type","%s" % file.bcType)
          theAssetElement.setAttribute("hash-code","%s" % file.checksum)
          theAssetElement.setAttribute("size", "%d" % file.size)
          theAssetElement.setAttribute("frame-width", "%d" % file.frameWidth)
          theAssetElement.setAttribute("frame-height", "%d" % file.frameHeight)
          theAssetElement.setAttribute("refid","%s" % file.refID)
          theAssetElement.setAttribute("h264-no-processing","true")
          
          if file.uploadFileName:
            theAssetElement.setAttribute("filename", "%s" % file.uploadFileName)  
          else:
            theAssetElement.setAttribute("filename", "%s" % file.fileName)  

          if file.bitRate:
            theAssetElement.setAttribute("encoding-rate", "%d000" % file.bitRate)
          else:
            theAssetElement.setAttribute("filename","%s" % file.fileName)        
  
          renditionReferences.append("%s" % file.refID)
        
        ## Append our field element to our "params" element i.e.
        ##   <asset refid="FMX_Open_Full_4Mbps_24i" type="FLV_FULL" \
        ##   hash-code="f0e24166abdf5e542c3c6427738bba8f" size="38218785"\
        ##   filename="FMX_Open_Full_4Mbps_24i.mp4" encoding-rate="3700670"\
        ##   frame-width="640" frame-height="480"/>
        elif file.fileType == "image":
          theThumbFile = file
          theAssetElement = xmlDoc.createElement("asset")
          theAssetElement.setAttribute("refid","%s" % file.refID)  
          theAssetElement.setAttribute("filename","thumb_%s" % file.fileName)        
          theAssetElement.setAttribute("type","%s" % file.bcType)
          theAssetElement.setAttribute("hash-code","%s" % file.checksum)
          theAssetElement.setAttribute("size", "%d" % file.size)
          theAssetElement.setAttribute("frame-width", "%d" % file.frameWidth)
          theAssetElement.setAttribute("frame-height", "%d" % file.frameHeight)
        else:
          self.logger("Unknown media type: '%s' for file: '%s'" % (file.fileType, file.path))
          return False;
          
        renditionReferences.append("%s" % file.refID)
            
        manifestElement.appendChild(theAssetElement)
        del theAssetElement
        
      ## Append our title element
      titleElement = xmlDoc.createElement("title")
      titleElement.setAttribute("name", "%s" % self.title)
      titleElement.setAttribute("refid", "%s" % self.refID)
      titleElement.setAttribute("active", "true")
      if theThumbFile:
        titleElement.setAttribute("thumbnail-refid", "%s" % theThumbFile.refID)
      
      manifestElement.appendChild(titleElement)
      
      descElement = xmlDoc.createElement("short-description")
      if self.description:
        theValueNode = xmlDoc.createTextNode("%s" % self.description)
      else:
        theValueNode = xmlDoc.createTextNode(" ")

      descElement.appendChild(theValueNode) 
      titleElement.appendChild(descElement)
    
      for item in renditionReferences[:]:  
        renditionRefElement = xmlDoc.createElement("rendition-refid")
        theValueNode = xmlDoc.createTextNode(item)
        renditionRefElement.appendChild(theValueNode)
        titleElement.appendChild(renditionRefElement)
        del renditionRefElement
        
      if filePath:
        theFile = open(filePath, "w")
        xmlDoc.writexml(theFile)
        theFile.close()
      else:
        print xmlDoc.toprettyxml()
    elif os.path.exists(filePath) and not self.overwriteExistingFiles: 
      self.logger("File already exists at path: %s, exiting!" % filePath, "error")
      return False
    elif not os.path.exists(os.path.dirname(filePath)): 
      self.logger("Directory does not exist at path: %s, exiting!" % os.path.dirname(filePath), "error")
      return false
    else:
      self.logger("Uncaught Exception: Error writing XML", "error")
      return False

    xmlDoc.unlink()
    return True 

  def reportToFinalCutServer(self, fcsDirPath="",updateLog=False):
    """Report to Final Cut Server, using stored fields in our fcsXMLOut object 
    and our entityID to generate the content."""
    if not self.entityID:
      self.logger("Could not report to FCS, unknown entityID!", "error")
      return False
    if not fcsDirPath:
      fcsDirPath = self.fcsXMLOutDir
    if not self.preflightCheck:
      return False;
    if not self.fcsXMLOutObject:
      self.fcsXMLOutObject = FCSXMLObject(self.entityID)
    
    fcsXML = self.fcsXMLOutObject

    if updateLog and self.publishHistory:
      fcsXML.setField(FCSXMLField("%s Publish History" %  self.serviceName, self.publishHistory)) 
    
    xmlPath = os.path.join(fcsDirPath, "%s_%s.xml" % (self.serviceName, self.entityID))
    self.logger("Reporting to Final Cut Server: '%s'" % xmlPath, "detailed")
    
    fcsXML.xmlOut(xmlPath)



class MediaFile:
  """This object represents each media asset that we will publish to our service"""
  
  refID = ""        ## unique reference ID
  title = ""        ## Title of the file
  fileName = ""       ## Name of the file on the local filesystem
  uploadFileName = ""   ## Name of the file as it will be uploaded
  fileType = ""       ## File type, currently support "video" and "thumbnail"
  bitRate = ""      ## bitrate in kbps
  size = 0        ## size of the file in bytes
  frameWidth = ""     
  frameHeight = ""
  checksum = ""
  type = "VIDEO_FULL"
  path = ""
  log = []
  lastError = ""
  debug = False

  def __init__(self,filePath):
    """init() can accept a filePath as an argument"""
    ## instantiate our vars
    self.refID = ""
    self.title = ""
    self.fileName = ""
    self.size = 0
    self.frameWidth = 0
    self.frameHeight = 0
    self.checksum = ""
    self.bcType = "VIDEO_FULL"
    self.path = ""
    self.setFile(filePath)
    self.log = []
    self.lastError = ""
    self.fileType = "video"

  def logger(self, logMSG, logLevel="normal"):
    """(very) Basic Logging Function"""
    if logLevel == "error" or logLevel == "normal" or self.debug:
      print "MediaFile: %s" % logMSG
      self.lastError = logMSG
    self.log.append({"logLevel" : logLevel, "logMSG" : logMSG})
    
  def printLogs(self, logLevel="all"):
    for log in self.log:
      if logLevel == "all" or logLevel == log["logLevel"]:
        print "MediaFile:%s:%s" % (log["logLevel"], log["logMSG"]) 

  def setFile(self,filePath):
    """import file information from a specific absolute path"""
    if os.path.exists(filePath):
      self.fileName = os.path.basename(filePath)
      if not self.title:
        self.fileName
      self.refID = re.sub(' ','_',re.sub(r'^(.*?)\..*$',r'\1',self.fileName))
      self.size = int(os.path.getsize(filePath))
      self.path = filePath
      self.checksum =  self.md5sum(filePath)
    else:
      self.logger("file() File does not exist at path: %s, exiting!" % filePath, "error")
      
  def md5sum(self, filePath=""):
    """Calculate MD5 checksome of passed file"""
    if not filePath:
      filePath = self.filePath
    if not filePath or not os.path.isfile(filePath):
      self.logger("md5sum() cannot determine filepath!", "error")
      return False
      
    myFile = open(filePath)
    bufferSize = 4096
    checksum = hashlib.md5()
    while True:
      buffer = myFile.read(bufferSize)
      if buffer == "":
        break
      checksum.update(buffer)
    myFile.close()
    return checksum.hexdigest()
    


      
    
    
  
