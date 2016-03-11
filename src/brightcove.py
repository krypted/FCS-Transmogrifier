#!/usr/bin/python
# -*- coding: utf-8 -*-


################################
##
##  Transmogrifier: BrightCove
##  A Final Cut Server import/export tool 
##
##  
##
##  This class is a decedent of TransmogrifierObject, and provides no additional
##  interfaces above what is provided via it's parent, TransmogrifyTargetObject. 
##  However, numerous methods have been overridden to provide BrightCove-specific
##  Operations and XML output
##
##
##
#############################################################

import os, os.path, re, glob, shutil, sys, types, datetime, time
from ftplib import FTP
from fcsxml import FCSXMLField, FCSXMLObject
from transmogrifierTarget import TransmogrifierTargetObject, MediaFile

from xml.dom import minidom
 
version = ".91beta"
build = "2010040101"
    
## Date/time string used for reporting
currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))

class BrightCoveObject(TransmogrifierTargetObject):
    """Our main brightcove object, used for collecting media files, interpretting
    FCS XML, writing brightcove compliant XML and uploading these media files
    to BrightCove."""

    refID = ""
    multipleBitRate = False
    publisherID = ""    
    frameHeight = ""
    frameWidth = ""
    debug = False
    validActions = ['upload']
    
    def __init__(self,entityID=0):
        """Our construct, instantiate our members"""
        TransmogrifierTargetObject.__init__(self,entityID)
        self.refID = ""
        self.multipleBitRate = False
        self.overwriteExistingFiles = True
        self.serviceName = "BrightCove"
        self.supportSubDirs =  ["xmlin", "xmlout", "media", "media/thumbs", "media/stills"]
        self.neededAttributes = ["entityID", "approver", "title", "description", "publisherID", "ftpUser", "ftpPassword", "ftpHost"]
        self.reqFCSFields = ["(string) BrightCove Publish History",
                                "(bool) Publish to BrightCove",
                                "(bool) Published to BrightCove",
                                "(string) Publishing Approver"]
        self.validActions = ['upload']
        
    def createSupportFolders(self, path):
      """Creates a support folder at specified path, create subdirectories 
      specified by self.supportSubDirs. If we are outputting multiple renditions
      via the multiplebitrate flag, we will create some bitrate target folders.
      """ 
      
      ## Call our paernt.
      TransmogrifierTargetObject.createSupportFolders(self,path)
      
      ## If we are using multiple bitrates, create subfolders.
      if self.multipleBitRate:
        supportSubDirs = ["media/500.25","media/700.5", 
                           "media/1500", "media/3000"]
      
        for subDir in supportSubDirs:
          dir = os.path.join(path, subDir)
          if not os.path.exists(dir):
            self.logger("Creating Directory: '%s'" % dir)
            os.mkdir(dir)
          elif not os.path.isdir(dir):
            self.logger("Could not create subfolder '%s', invalid object "
                            "exists at path: '%s'" % (path, dir), "error")
            returnValue = False
        
      
      return returnValue
    
    def deleteSupportFiles(self):
        """Delete Registered support files (media and xml)"""
        errorCode = ""
        
        ## Call our parent, which removes any standard loaded media or xml files
        if not TransmogrifierTargetObject.deleteSupportFiles(self):
            errorCode = 1
        ## Delete our BrightCove manifest.xml
        if self.supportPath:
            xmlOutPath = os.path.join(self.supportPath, "xmlout", "%s_manifest.xml" % self.refID)
            if os.path.exists(xmlOutPath):
                self.logger("Removing file at path: '%s'" % xmlOutPath, "detailed")
                os.remove(xmlOutPath)
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
            self.ftpHost = parser.get("BrightCove","host")
            self.ftpUser = parser.get("BrightCove","username")
            self.ftpPassword = parser.get("BrightCove","password") 
            self.publisherID = parser.get("BrightCove","publisherid")
            self.multipleBitRate = parser.getboolean("BrightCove","multiplebitrate")
        except Exception,excp:
            self.logger("loadConfiguration() Problem loading configuration "
             "records, please double check your configuration. Error: %s"
             % excp,"error") 
        return True
        
    def setFCSXMLFile(self,filePath):
        """import FCS XML file and set relevant member vars"""
        ## Call our parent class, which does most of the work, imports common
        ## variables (stored in member vars)
        
        errorCode = ""
        if not TransmogrifierTargetObject.setFCSXMLFile(self, filePath):
            errorCode = 1
            
        ## Generate our BrightCove refID
        if not self.refID:
            self.refID = re.sub(' ','_',re.sub(r'^(.*?)\..*$',r'\1',self.title))
        
        if not errorCode:
            return True
        else:
            return False
            
    def upload(self, dirPath=""):
        '''Uploads all relative assets to the configured ftpHost, also calls xmlOut and uploads the resulting file'''
        theError = ""
        
        ## Sanity Checks
        if not dirPath:
            dirPath = self.supportPath
        if not os.path.isdir(dirPath):
            self.logger("brightcove_xml:upload() Directory does not exist:'%s'" % dirPath, "error")
            return False
        xmlOutPath = os.path.join(dirPath, "xmlout", "%s_manifest.xml" % self.refID)
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
        
        ## Iterate through our stored files (assembled by self.readMediaFiles)
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
                    self.logger("upload() could not upload file: '%s' Error:\n%s" % (theError), "error")
    
                ## shutil.copy(file.path, dirPath)
                ##if not os.path.isfile (os.path.join(dirPath,file.fileName)):
                ##    theError = "Couldn't copy file: '%s'" % file.path
                ##    self.logger("upload() %s" % theError, "error")
        try:
            if os.path.exists(xmlOutPath):
                theFile = open(xmlOutPath, "r")
                self.logger("upload() uplaoding file: 'manifest.xml'", "normal")
                ftp.storbinary("%s manifest.xml" % (ftpCommand), theFile)
                theFile.close()
            else: 
                self.logger("upload() failed to upload file: 'manifest.xml'", "error")
                theError = self.lastError
        except:
            theError = xmlOutPath,sys.exc_info()[0]
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
            self.appendFCSField("BrightCove Publish History","%s: Successfully published to %s." % (currentTime,self.serviceName)) 
            self.logger("Successfully published assets to %s." % (self.serviceName)) 
            return True
        else:
            self.appendHistory("%s: Failed to publish to %s. Please try again. Error:\n\t%s" % (currentTime,self.serviceName,self.lastError))
            fcsXMLOut.setField(FCSXMLField("Publish to %s" %  self.serviceName, "false", "bool")) 
            self.logger("Failed to publish all assets to %s." % (self.serviceName), "error") 

            return False
            
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
        if self.multipleBitRate:
            self.logger("Multiple bitrate specified, searching sub directories", "detailed")
            for theFolderName in (os.listdir(dirPath)):
                if theFolderName == "thumbs":
                    continue
                theFolderPath = os.path.join(dirPath, theFolderName)
                if os.path.isdir(theFolderPath):
                    self.logger("   searching directory: %s" % theFolderPath, "debug")
                    ## Folder will be named after the bitrate
                    for theFilePath in glob.glob(os.path.join(theFolderPath, "%s*.mov" % baseName)):
                        self.files[theFilePath] = MediaFile(theFilePath)
                        theFile = self.files[theFilePath]
                                            
                        ## set a static dimensions, this works in this particular instance
                        ## may need refactoring if upload service allows varying sizes
                        ## easiest way to accomplish this will probably be with additional folders
                        ## as Python doesn't seem to have a good built-in media module, we'd need to
                        ## use an external module (which we're trynig to avoid)

                        theFile.bcType = "VIDEO_FULL"
                        ## Folder will be named after the bitrate, if it's 
                        ## numeric, use it's value.
                        if re.match('^\d+$', theFolderName):
                            theFile.bitRate = int(theFolderName)
                            theFile.frameWidth = int(self.frameWidth)
                            theFile.frameHeight = int(self.frameHeight)
                            theFile.refID = "%skbps_%s" % ( theFile.bitRate, theFile.refID)
                            theFile.uploadFileName = "%skbps_%s" % ( theFile.bitRate, theFile.fileName)
                            self.logger("readMediaFiles() adding file found at '%s' with bitrate: '%s'" % (theFilePath, theFile.bitRate))

                        elif re.match('^\d+\..*', theFolderName):
                            reObj = re.search('(^\d+)(\..*)$', theFolderName)
                            bitRate = int(reObj.group(1))
                            resolutionPercentage = float(reObj.group(2)) 
                            theFile.frameWidth = int(int(self.frameWidth) * resolutionPercentage)
                            theFile.frameHeight = int(int(self.frameHeight) * resolutionPercentage)
                            theFile.bitRate = int(bitRate)
                            theFile.refID = "%skbps_%s" % ( theFile.bitRate, theFile.refID)
                            theFile.uploadFileName = "%skbps_%s" % ( theFile.bitRate, theFile.fileName)

                            self.logger("readMediaFiles() adding file found at '%s' with resolution modifier of: '%s' with bitrate: '%s'" % (theFilePath, resolutionPercentage,theFile.bitRate))

        else:
            for theFilePath in glob.glob( os.path.join(dirPath, "%s.mov" % baseName)):
                self.logger("readMediaFiles() adding file found at '%s'" % theFilePath)
                self.files[theFilePath] = MediaFile(theFilePath)
                theFile = self.files[theFilePath]
                theFile.title = self.title
                theFile.bcType = "VIDEO_FULL"

                ## set a static dimensions, this works in this particular instance
                ## may need refactoring if upload service allows varying sizes
                theFile.frameWidth = int(self.frameWidth)
                theFile.frameHeight = int(self.frameHeight)
     
                              
        ## Try to grab our thumbnail
        thumbPath = ""
        if os.path.isdir(os.path.join(dirPath,"thumbs")):
            if os.path.isfile(os.path.join(dirPath,"thumbs", "%s.jpg" % baseName)):
                thumbPath = os.path.join(dirPath,"thumbs", "%s.jpg" % baseName)
        else:
            if os.path.isfile(os.path.join(dirPath, "%s.jpg" % baseName)):
                thumbPath = os.path.join(dirPath, "%s.jpg" % baseName)
        if thumbPath:
            self.logger("readMediaFiles() adding file found at '%s'" % thumbPath)
            self.files[thumbPath] = MediaFile(thumbPath)
            thumbFile = self.files[thumbPath]
            thumbFile.fileType = "image"
            thumbFile.frameWidth = int(self.frameWidth)
            thumbFile.frameHeight = int(self.frameHeight)
            thumbFile.refID = "thumb_%s" % thumbFile.refID
            thumbFile.bcType = "THUMBNAIL"
            thumbFile.uploadFileName = "thumb_%s" % thumbFile.fileName
            
        ## Try to grab our vid. still
        stillPath = ""
        if os.path.isdir(os.path.join(dirPath,"stills")):
            if os.path.isfile(os.path.join(dirPath,"stills", "%s.jpg" % baseName)):
                stillPath = os.path.join(dirPath,"stills", "%s.jpg" % baseName)
        else:
            if os.path.isfile(os.path.join(dirPath, "%s.jpg" % baseName)):
                stillPath = os.path.join(dirPath, "%s.jpg" % baseName)
        if stillPath:
            self.logger("readMediaFiles() adding file found at '%s'" % stillPath)
            self.files[stillPath] = MediaFile(stillPath)
            stillFile = self.files[stillPath]
            stillFile.fileType = "image"
            stillFile.frameWidth = int(self.frameWidth)
            stillFile.frameHeight = int(self.frameHeight)
            stillFile.refID = "still_%s" % stillFile.refID
            stillFile.bcType = "VIDEO_STILL"
            stillFile.uploadFileName = "still_%s" % stillFile.fileName

                    
    def xmlOut(self, filePath=""):
        '''Output our BrightCove compliant XML, if we are passed a filePath, we
        output to it. '''
        ## Sanity checks and variable initialization
        theThumbFile = ""
        theStillFile = ""
        theVideoFullFile = ""

        if not os.path.isdir(self.fcsXMLOutDir):
            self.logger("fcsXMLOutDir: '%s' does not exist!" % self.fcsXMLOutDir, "error")
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
            ##    <notify email=\"$EMAIL_TO_NOTIFY\" />           
                  
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
                  if file.bcType == "VIDEO_FULL" and not self.multipleBitRate:
                    theVideoFullFile = file
                  theAssetElement.setAttribute("hash-code",
                                                  "%s" % file.checksum)
                  theAssetElement.setAttribute("size", "%d" % file.size)
                  
                  if self.multipleBitRate:
                    theAssetElement.setAttribute("frame-width",
                                                  "%d" % file.frameWidth)
                    theAssetElement.setAttribute("frame-height",
                                                  "%d" % file.frameHeight)                      
                    theAssetElement.setAttribute("h264-no-processing","true")
                    if file.bitRate:
                      theAssetElement.setAttribute("encoding-rate", "%d000" 
                                                      % file.bitRate)
                  else:
                    theAssetElement.setAttribute("encode-to","MP4")
                    theAssetElement.setAttribute("encode-multiple","true")
                  
                  if file.uploadFileName:
                    theAssetElement.setAttribute("filename", "%s" % file.uploadFileName)  
                  else:
                    theAssetElement.setAttribute("filename", "%s" % file.fileName)  

                  theAssetElement.setAttribute("refid","%s" % file.refID)
                  if self.multipleBitRate:
                    renditionReferences.append("%s" % file.refID)

    
                
                ## Append our field element to our "params" element i.e.
                ##     <asset refid="FMX_Open_Full_4Mbps_24i" type="FLV_FULL" \
                ##     hash-code="f0e24166abdf5e542c3c6427738bba8f" size="38218785"\
                ##     filename="FMX_Open_Full_4Mbps_24i.mp4" encoding-rate="3700670"\
                ##     frame-width="640" frame-height="480"/>
                elif file.fileType == "image":
                    if file.bcType == "THUMBNAIL":
                        ## Generate our thumbnail
                        theThumbFile = file
                        
                    elif file.bcType == "VIDEO_STILL":
                        ## Generate our video still
                        theStillFile = file
                     
                    theAssetElement = xmlDoc.createElement("asset")
                    theAssetElement.setAttribute("refid","%s" % file.refID)  
                    theAssetElement.setAttribute("filename","%s" % file.uploadFileName)                
                    theAssetElement.setAttribute("type","%s" % file.bcType)
                    theAssetElement.setAttribute("hash-code","%s" % file.checksum)
                    theAssetElement.setAttribute("size", "%d" % file.size)
                    theAssetElement.setAttribute("frame-width", "%d" % file.frameWidth)
                    theAssetElement.setAttribute("frame-height", "%d" % file.frameHeight)
                    
                else:
                    self.logger("Unknown media type: '%s' for file: '%s'" % (file.fileType, file.path))
                    return False;
                                            
                manifestElement.appendChild(theAssetElement)
                del theAssetElement
                
            ## Append our title element
            titleElement = xmlDoc.createElement("title")
            titleElement.setAttribute("name", "%s" % self.title)
            titleElement.setAttribute("refid", "%s_title" % self.refID)
            titleElement.setAttribute("active", "true")
            if theThumbFile:
                titleElement.setAttribute("thumbnail-refid", "%s" % theThumbFile.refID)
            if theStillFile:
                titleElement.setAttribute("video-still-refid", "%s" % theStillFile.refID)
            if theVideoFullFile:
              titleElement.setAttribute("video-full-refid","%s" % theVideoFullFile.refID)
            
            manifestElement.appendChild(titleElement)
            
            descElement = xmlDoc.createElement("short-description")
            if self.description:
                theValueNode = xmlDoc.createTextNode("%s" % self.description)
            else:
                theValueNode = xmlDoc.createTextNode(" ")
            descElement.appendChild(theValueNode) 
            titleElement.appendChild(descElement)

            if self.longDescription:
                ldescElement = xmlDoc.createElement("long-description")
                theValueNode = xmlDoc.createTextNode("%s" % self.longDescription)
                ldescElement.appendChild(theValueNode) 
                titleElement.appendChild(ldescElement)

            if self.keywordString:
                for tag in self.keywordString.split(","):
                    tagElement = xmlDoc.createElement("tag")
                    theValueNode = xmlDoc.createTextNode("%s" % tag)
                    tagElement.appendChild(theValueNode)
                    titleElement.appendChild(tagElement)

        
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
       

                  
