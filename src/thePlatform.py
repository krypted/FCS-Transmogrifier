#!/usr/bin/python
# -*- coding: utf-8 -*-


################################
##
##  Transmogrifier: ThePlatform
##  A Final Cut Server import/export tool 
##
##  This class is a decedent of TransmogrifierObject, and pretty mimics the 
##  interface and functionality of it's parent, with one key addition function. 
##  Once uploaded, YouTube processes the media and XML, and then generates it's 
##  own XML report as to the status of the import. In order to ensure a successful
##  upload, we need to check this file to ensure that if it failed we properly 
##  report the status. To do so, YouTubeObject provides two additional methods, 
##  batchStatusCheck() and checkYouTubeXMLStatusFile(). The former method 
##  actually utilizes the latter, so it will rarely be need to be called directly. 
##
#############################################################

import os, os.path, re, glob, shutil, sys, datetime, time
from ftplib import FTP
from fcsxml import FCSXMLField, FCSXMLObject
from transmogrifierTarget import TransmogrifierTargetObject, MediaFile
from decimal import *

from xml.dom import minidom

version = ".91beta"
build = "2010040101"

class thePlatformObject(TransmogrifierTargetObject):
  '''This class provides an interface for publishing to 
  `thePlatform <http://www.theplatform.com>`_, 
  used for writing compliant XML and uploading it to thePlatform via FTP.
  Media delivery can be handled directly in FCS.
  
  .. note: 
    This module is still a little rough around the edges in regards to wide-
    scale deployment, though it does work. Notably, there are still a few 
    static variables to set in code (see variables 
    ``movLocation`` and ``thumbnailLocation``)
    
  '''


  talent = ""
  author = ""
  copyright = ""
  aspectRatio = ""
  team = ""

  
  fileName = ""
  fileBaseName = ""
  
  conference = ""
  
  airDate = ""
  expirationDate = ""
  availableDate = ""
  
  uploadPath = ""
  movLocation = ""
  thumbnailLocation = ""
  
  validActions = ['upload']
  
  debug = False
  
  def __init__(self,entityID=0):
    
    TransmogrifierTargetObject.__init__(self,entityID)
    self.talent = ""
    self.author = ""
    self.copyright = ""
    self.team = ""
    
    self.fileName = ""
    self.fileBaseName = ""
    self.airDate = ""
    self.expirationDate = ""
    self.availableDate = ""
    self.uploadPath = ""
    self.movLocation = ""
    self.thumbnailLocation = ""
    self.serviceName = "thePlatform"
    self.supportSubDirs = ["media","thumbnails","xmlin","xmlout"]
    self.neededAttributes = ["title","talent","team","airDate","expirationDate"]
    self.neededAttributes = [""]
    
    self.reqFCSFields.extend(['(bool) Published to thePlatform',
                                '(bool) Publish to thePlatform',
                                '(string) thePlatform Publish History'])
    self.validActions = ['upload']
    
  def deleteSupportFiles(self):
    """Delete Registered support files (media and xml)"""
    ## Call our parent, which removes any loaded media or xml files
    if not TransmogrifierTargetObject.deleteSupportFiles(self):
      errorCode = 1
    ## Delete our youtube batch upload file
    if self.supportPath:
      batchFilePath = os.path.join(self.supportPath, "upload", "%s.batch" % self.entityID)
      if os.path.exists(batchFilePath):
        self.logger("Removing file at path: '%s'" % batchFilePath, "detailed")
        os.remove(batchFilePath) 
    if errorCode:
      return False
    else:
      return True

  def loadConfiguration(self, parser):
    """Load from configuration file, expects a ConfigParser type object. If you subclass, 
    you should call this function. If we return false then you should abort. or do your own sanity checks"""
    if not TransmogrifierTargetObject.loadConfiguration(self, parser):
      return False;
    try:
      self.ftpHost = parser.get("thePlatform","host")
      self.ftpUser = parser.get("thePlatform","username")
      self.ftpPassword = parser.get("thePlatform","password") 
    except:
      self.logger("loadConfiguration() Problem loading configuration records, please double check your configuration","error") 
    return True

    
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
      aspectValue = Decimal(self.frameWidth) / Decimal(self.frameHeight)
      if aspectValue > 1.5:
        self.aspectRatio = "16x9"
      else:
        self.aspectRatio = "4x3"
    except:
      self.logger("Could not determine mediaSize from XML!","error")
        
    self.entityID = self.fcsXMLObject.entityID

    
    if self.fcsXMLObject.valueForField("File Name"):
      self.fileName = self.fcsXMLObject.valueForField("File Name")
      self.fileBaseName = os.path.splitext(self.fileName)[0]
    try:
      fieldName = 'Talent'
      self.talent = self.fcsXMLObject.valueForField(fieldName)
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    try:
      fieldName = 'Author'
      self.author = self.fcsXMLObject.valueForField(fieldName)
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    try:
      fieldName = 'Keywords'
      self.keywordString = self.fcsXMLObject.valueForField(fieldName)
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    try:
      fieldName = 'Description'
      self.description = self.fcsXMLObject.valueForField(fieldName)
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    try:
      fieldName = 'Available Date'
      myDateTime = datetime.datetime.strptime(self.fcsXMLObject.valueForField("Available Date"),"%Y-%m-%dT%H:%M:%SZ")
      timeDelta = datetime.timedelta(hours=10)
      adjustedDateTime = myDateTime - timeDelta
      self.availableDate = adjustedDateTime.strftime("%Y-%m-%dT%H:%M:%S")
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    
    try:
      fieldName = 'Expiration Date'
      myDateTime = datetime.datetime.strptime(self.fcsXMLObject.valueForField("Available Date"),"%Y-%m-%dT%H:%M:%SZ")
      timeDelta = datetime.timedelta(hours=10)
      adjustedDateTime = myDateTime - timeDelta
      self.expirationDate = adjustedDateTime.strftime("%Y-%m-%dT%H:%M:%S")
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    
    try:
      fieldName = 'Air Date'
      myDateTime = datetime.datetime.strptime(self.fcsXMLObject.valueForField("Available Date"),"%Y-%m-%dT%H:%M:%SZ")
      timeDelta = datetime.timedelta(hours=10)
      adjustedDateTime = myDateTime - timeDelta
      self.airDate = adjustedDateTime.strftime("%Y-%m-%dT%H:%M:%S")
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
    try:
      fieldName = 'Upload Path'
      self.uploadPath = self.fcsXMLObject.valueForField(fieldName)
    except:
      self.logger('Error: could not read field: %s from XML.' % fieldName,
        'error')
        
    if not self.title:
      self.title = self.fcsXMLObject.valueForField("Title")
    return True
              
  def upload(self, dirPath=""):
    '''Calls xmlOut and uploads the resulting file via FTP'''
    
    self.logger("Uploading XML to thePlatform!")
    
    theError = ""
    
    ## Sanity Checks
    if not dirPath:
      dirPath = self.supportPath
    if not os.path.isdir(dirPath):
      self.logger("thePlatform_xml:upload() Directory does not exist:'%s'" % dirPath, "error")
      return False
    datestamp = datetime.datetime.now()
    xmlFileName = "%s_%s.xml" % (self.team,datestamp.strftime("%m%d%y"))
    xmlOutPath = os.path.join(dirPath,"xmlout",xmlFileName)
    if not self.xmlOut(xmlOutPath):
      self.logger("upload() could not write XML, exiting", "error")
      return False
      
    ## Establish our FTP upload command STOR overrides, STOU fails on existing object
    if self.overwriteExistingFiles:
      ftpCommand = "STOR"
    else:
      ftpCommand = "STOU"
    
    ## Sanity checks and then try our FTP connection
    if not self.ftpHost or not self.ftpUser or not self.ftpPassword:
      self.logger("upload() missing parameters, could not establish connection to FTP server!", "error")
    try:
      ftp = FTP(self.ftpHost, self.ftpUser, self.ftpPassword)
    except:
      self.logger("upload() failed to connect to FTP server", "error")
      return False
    
    try:
      if os.path.exists(xmlOutPath):
        theFile = open(xmlOutPath, "r")
        self.logger("upload() uploading file: '%s'" % xmlFileName, "normal")
        if self.uploadPath:
          uploadPath = os.path.join(self.uploadPath,xmlFileName)
        else: 
          uploadPath = xmlFileName
        ftp.storbinary("%s %s" % (ftpCommand,uploadPath), theFile)
        theFile.close()
      else: 
        self.logger("upload() failed to upload file: 'manifest.xml'", "error")
        theError = self.lastError
    except Exception,excp:
      theError = xmlOutPath,excp
      self.logger("upload() could not upload file: '%s' Error:\n%s" % (theError), "error")
    
    
    ## Build our FCS object for reporting
    if not self.fcsXMLOutObject:
      self.fcsXMLOutObject = FCSXMLObject(self.entityID)
    fcsXMLOut = self.fcsXMLOutObject
    
    currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))
    
    if not theError:
      fcsXMLOut.setField(FCSXMLField("Published to %s" %  self.serviceName, "true", "bool")) 
      fcsXMLOut.setField(FCSXMLField("Publish to %s" %  self.serviceName, "false", "bool")) 
      fcsXMLOut.setField(FCSXMLField("Status", "Verify Publishing")) 
      self.appendFCSField("thePlatform Publish History","%s: Successfully published to %s." % (currentTime,self.serviceName)) 
      self.logger("Successfully published assets to %s." % (self.serviceName)) 
      return True
    else:
      self.appendHistory("%s: Failed to publish to %s. Please try again. Error:\n\t%s" % (currentTime,self.serviceName,self.lastError))
      fcsXMLOut.setField(FCSXMLField("Publish to %s" %  self.serviceName, "false", "bool")) 
      self.logger("Failed to publish all assets to %s." % (self.serviceName), "error") 

      return False

   
     
  def xmlOut(self, filePath=""):
    '''Output our thePlatform compliant XML. If passed a filepath for the second
    Parameter, we write to that file, otherwise we print to stdout'''
    
    self.logger("Writing XML file to path: %s" % filePath)
    
    ## Sanity checks and variable initialization
    ## Set our variables
    
    title = self.title
    airDate = self.airDate
    talent = self.talent
    description = self.description
    author = self.author
    aspectRatio = self.aspectRatio
    keywords = self.keywordString
    availableDate = self.availableDate
    expirationDate = self.expirationDate
    uploadPath = self.uploadPath
    
    filename = self.fileName
    fileBaseName = self.fileBaseName
    
    
    ## Determine our categories
    rawCategories = [ self.team ]

    categories = []              
    for category in rawCategories:
      if category and not category == "Unspecified":
        categories.append(category)

    movLocation = "file://172.16.130.22/MOV_Drop/%s_MOV/%s.mov" % (uploadPath,fileBaseName)
    thumbnailLocation = "file://172.16.130.22/JPEG_Drop/%s_JPEG/%s.jpg" % (uploadPath,fileBaseName)
    
    ## Make sure either that our xml out file doesn't already exist, or 
    ## that we're allowed to overwrite existing files. Then Generate our XML     
    if (filePath and (not os.path.exists(filePath)  \
    or (os.path.exists(filePath) and self.overwriteExistingFiles))
    and os.path.isdir(os.path.dirname(filePath))) \
    or not filePath : 
      
      ## <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      ## <addContent>
      ##   <media>
      ##   <title>SEASON 2 TEASER</title>
      ##   <customData>
      ##     <CustomDataElement>
      ##     <title>Talent</title>
      ##     <value/>
      ##     </CustomDataElement>
      ##     <CustomDataElement>
      ##     <title>AspectRatio</title>
      ##     <value>16x9</value>
      ##     </CustomDataElement>
      ##   </customData>
      ##   <airdate>2010-06-04T00:00:00.000</airdate>
      ##   <availableDate>2010-06-04T00:00:00.000</availableDate>
      ##   <expirationDate>2011-06-04T00:00:00.000</expirationDate>
      ##   <author>Sarah Fowler</author>
      ##   <categories>
      ##     <string>Gatorade</string>
      ##   </categories>
      ##   <description>MyDescription</description>
      ##   <keywords>Gatorade, Replay</keywords>
      ##   </media>
      ##   <mediaFiles>
      ##   <mediaFile>
      ##     <assetTypes>
      ##     <string>video</string>
      ##     </assetTypes>
      ##     <contentType>Video</contentType>
      ##     <encodingProfileTitle>Mezzanine Video</encodingProfileTitle>
      ##     <originalLocation>file://172.16.130.22/MOV_Drop/Microsite_MOV/replay_season2_teaser_r2_063010.mov</originalLocation>
      ##   </mediaFile>
      ##   <mediaFile>
      ##     <assetTypes>
      ##     <string>thumbnail</string>
      ##     </assetTypes>
      ##     <contentType>Image</contentType>
      ##     <encodingProfileTitle>Mezzanine Thumbnail</encodingProfileTitle>
      ##     <originalLocation>file://172.16.130.22/JPEG_Drop/Microsite_JPEG/replay_season2_teaser_r2_063010.jpg</originalLocation>
      ##   </mediaFile>
      ##   </mediaFiles>
      ## </addContent>

      ## Start XML Creation

      ## <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
      ## <addContent>
      ##   <media>
      xmlObject = minidom.Document()
      xmlDoc = xmlObject
      addContentElement = xmlDoc.createElement("addContent")
      xmlDoc.appendChild(addContentElement)
      mediaElement = xmlDoc.createElement("media")
      addContentElement.appendChild(mediaElement)

      ##   <title>SEASON 2 TEASER</title>
      titleElement = xmlDoc.createElement("title")
      titleElement.appendChild(xmlDoc.createTextNode(title))
      mediaElement.appendChild(titleElement)

      ## If talent is set, add a CustomDataElement node for it.
      ##     <CustomDataElement>
      ##     <title>Talent</title>
      ##     <value>Karl Malone</value>
      ##     </CustomDataElement>

      customDataElement = xmlDoc.createElement("customData")
      mediaElement.appendChild(customDataElement)

      if talent:
        customDataTalentElement = xmlDoc.createElement("CustomDataElement")
        customDataTalentTitle = xmlDoc.createElement("title")
        customDataTalentTitle.appendChild(xmlDoc.createTextNode("Talent"))
        customDataTalentElement.appendChild(customDataTalentTitle)
        
        customDataTalentValue = xmlDoc.createElement("value")
        customDataTalentValue.appendChild(xmlDoc.createTextNode(talent))
        customDataTalentElement.appendChild(customDataTalentValue)
        customDataElement.appendChild(customDataTalentElement)

      ## Add CustomDataElement node for our Aspect Ration
      ##     <CustomDataElement>
      ##     <title>AspectRatio</title>
      ##     <value>16x9</value>
      ##     </CustomDataElement>
      ##   </customData>
      customDataAspectRatioElement = xmlDoc.createElement("CustomDataElement")
      customDataAspectRatioTitle = xmlDoc.createElement("title")
      customDataAspectRatioTitle.appendChild(xmlDoc.createTextNode("AspectRatio"))
      customDataAspectRatioElement.appendChild(customDataAspectRatioTitle)
      customDataAspectRatioValue = xmlDoc.createElement("value")
      customDataAspectRatioValue.appendChild(xmlDoc.createTextNode(aspectRatio))
      customDataAspectRatioElement.appendChild(customDataAspectRatioValue)
      customDataElement.appendChild(customDataAspectRatioElement)


      ##   <airdate>2010-06-04T00:00:00.000</airdate>
      airdateElement = xmlDoc.createElement("airdate")
      airdateElement.appendChild(xmlDoc.createTextNode(airDate))  
      mediaElement.appendChild(airdateElement)

      ##   <availableDate>2010-06-04T00:00:00.000</availableDate>
      availableDateElement = xmlDoc.createElement("availableDate")
      availableDateElement.appendChild(xmlDoc.createTextNode(availableDate))  
      mediaElement.appendChild(availableDateElement)

      ##   <expirationDate>2011-06-04T00:00:00.000</expirationDate>
      expirationDateElement = xmlDoc.createElement("expirationDate")
      expirationDateElement.appendChild(xmlDoc.createTextNode(expirationDate))  
      mediaElement.appendChild(expirationDateElement)

      ##   <author>Sarah Fowler</author>
      authorElement = xmlDoc.createElement("author")
      authorElement.appendChild(xmlDoc.createTextNode(author))  
      mediaElement.appendChild(authorElement)

      ##   <categories>
      ##     <string>Gatorade</string>
      ##   </categories>
      if categories and len(categories) > 0:
        categoriesElement = xmlDoc.createElement("categories")
        for category in categories:
          categoryElement = xmlDoc.createElement("string")
          categoryElement.appendChild(xmlDoc.createTextNode(category))
          categoriesElement.appendChild(categoryElement)
        mediaElement.appendChild(categoriesElement)

      ##   <description>MyDescription</description>
      descriptionElement = xmlDoc.createElement("description")
      descriptionElement.appendChild(xmlDoc.createTextNode(description))  
      mediaElement.appendChild(descriptionElement)

      ##   <keywords>Gatorade, Replay</keywords>
      keywordsElement = xmlDoc.createElement("keywords")
      keywordsElement.appendChild(xmlDoc.createTextNode(keywords))  
      mediaElement.appendChild(keywordsElement)

      #### Process our media files
      ##   <mediaFiles>

      mediaFilesElement = xmlDoc.createElement("mediaFiles")
      addContentElement.appendChild(mediaFilesElement)

      #### Process our video file

      ##   <mediaFile>
      ##     <assetTypes>
      ##     <string>video</string>
      ##     </assetTypes>
      ##     <contentType>Video</contentType>
      ##     <encodingProfileTitle>Mezzanine Video</encodingProfileTitle>
      ##     <originalLocation>file://172.16.130.22/MOV_Drop/Microsite_MOV/replay_season2_teaser_r2_063010.mov</originalLocation>
      ##   </mediaFile>mediaFileElement = xmlDoc.createElement("mediaFile")

      mediaFileElement = xmlDoc.createElement("mediaFile")
      mediaFilesElement.appendChild(mediaFileElement)
      assetTypesElement = xmlDoc.createElement("assetTypes")
      stringElement = xmlDoc.createElement("string")
      stringElement.appendChild(xmlDoc.createTextNode("video"))
      assetTypesElement.appendChild(stringElement)
      mediaFileElement.appendChild(assetTypesElement)

      contentTypeElement = xmlDoc.createElement("contentType")
      contentTypeElement.appendChild(xmlDoc.createTextNode("Video"))
      mediaFileElement.appendChild(contentTypeElement)

      encodingProfileTitleElement = xmlDoc.createElement("encodingProfileTitle")
      encodingProfileTitleElement.appendChild(xmlDoc.createTextNode("Mezzanine Video"))
      mediaFileElement.appendChild(encodingProfileTitleElement)

      originalLocationElement = xmlDoc.createElement("originalLocation")
      originalLocationElement.appendChild(xmlDoc.createTextNode(movLocation))
      mediaFileElement.appendChild(originalLocationElement)

      #### Process our thumbnail file

      mediaFileElement = xmlDoc.createElement("mediaFile")
      mediaFilesElement.appendChild(mediaFileElement)
      assetTypesElement = xmlDoc.createElement("assetTypes")
      stringElement = xmlDoc.createElement("string")
      stringElement.appendChild(xmlDoc.createTextNode("thumbnail"))
      assetTypesElement.appendChild(stringElement)
      mediaFileElement.appendChild(assetTypesElement)

      contentTypeElement = xmlDoc.createElement("contentType")
      contentTypeElement.appendChild(xmlDoc.createTextNode("Image"))
      mediaFileElement.appendChild(contentTypeElement)

      encodingProfileTitleElement = xmlDoc.createElement("encodingProfileTitle")
      encodingProfileTitleElement.appendChild(xmlDoc.createTextNode("Mezzanine Thumbnail"))
      mediaFileElement.appendChild(encodingProfileTitleElement)

      originalLocationElement = xmlDoc.createElement("originalLocation")
      originalLocationElement.appendChild(xmlDoc.createTextNode(thumbnailLocation))
      mediaFileElement.appendChild(originalLocationElement)
      
      

      ## Write our XML to file if provided, otherwise echo it     
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
    
 
        


