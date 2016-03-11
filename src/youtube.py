#!/usr/bin/python
# -*- coding: utf-8 -*-



################################
##
##  Transmogrifier: YouTube
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

from xml.dom import minidom

version = ".91beta"
build = "2010040101"

class YouTubeObject(TransmogrifierTargetObject):
  '''
  This provides an interface for uploading assets and XML to 
  `YouTube <http://www.youtube.com>`. In addition to basic delivery this script
  also facilitates status checks on the encoding process once uploaded. When 
  uploaded YouTube will processes the media and XML, and then generates an XML 
  report as to the status of the import. In order to ensure a successful upload, 
  we perform checks on this file to ensure that if it failed, we properly report 
  the status. To do so, YouTubeObject provides two additional methods,
  :func:`YouTubeObject.batchStatusCheck()` and
  :func:`YouTubeObject.checkYouTubeXMLStatusFile()`. The former method 
  actually utilizes the latter, so `'checkYouTubeXMLStatusFile`' will 
  rarely be need to be called directly.
  
  A batch status check can be performed by running the command: 
  
  >>> transmogrifier.py -m YouTube -a batchstatuscheck
  
  
  '''
    
  ytUsername = ""
  ytPassword = ""
  ytOwnerName = ""
  ytSFTPServer = ""
  ytXML = ""
  ytXMLFilePath = ""
  ytCustomID = ""
  retryCount = ""
  
  validActions = ['upload','batchStatusCheck']

  
  debug = False
  
  def __init__(self,entityID=0):
    TransmogrifierTargetObject.__init__(self,entityID)
    self.ytUsername = ""
    self.ytPassword = ""
    self.multipleBitRate = False
    self.ytSFTPServer = ""
    self.ytOwnerName = ""
    self.files = {}
    self.log = []
    self.serviceName = "YouTube"
    self.supportSubDirs = ["xmlin", "xmlout", "media","upload","inprogress"]
    self.neededAttributes = ["entityID", "approver", "title", "description", 
                              "ytOwnerName", "ytUsername", "ytSFTPServer"]
    self.reqFCSFields = ["(string) YouTube Publish History",
                          "(bool) Publish to YouTube",
                          "(bool) Published to YouTube",
                          "(string) YouTube GeneratedID",
                          "(string) Publishing Approver"]
    self.retryCount = int (5)
    self.validActions = ['upload','batchStatusCheck']
 
  def batchStatusCheck(self):
    '''Checks on the status of any inprogress batches, as indicated by the
    presence of \*.xml files in the ``inprogress`` folder residing in our 
    YouTube support folder.'''

    ## Iterate through our files:
    for theFilePath in glob.glob( os.path.join(self.supportPath,"inprogress", "*.xml")):
      processingSuccessfull = False
      entityID = re.sub(' ','_',re.sub(r'^(.*?)\.xml$',r'\1',os.path.basename(theFilePath)))
      self.logger("Checking batch status for job: %s" % entityID, "detailed")
      print "/usr/bin/sftp %s@%s:%s/status-%s.xml '%s/status-%s.xml'" % (self.ytUsername,self.ytSFTPServer,entityID,entityID,os.path.join(self.supportPath, "xmlin"),entityID)
      if not os.system("/usr/bin/sftp %s@%s:%s/status-%s.xml \'%s/status-%s.xml\'" % (self.ytUsername,self.ytSFTPServer,entityID,entityID,os.path.join(self.supportPath, "xmlin"),entityID)):
        ## at this point we have sftp'd the status file locally to the xmlin
        ## directory. Check the file for any reported problems:
        ytXMLInPath = os.path.join(self.supportPath, "xmlin", "status-%s.xml" % entityID)
        fcsXMLInPath = theFilePath
        if not self.checkYouTubeXMLStatusFile(ytXMLInPath):
          histString = "%s" % self.lastError 
        else:
          histString = "YouTube reports that media successfully published!"
          processingSuccessfull = True
      
        
        ## Read our FCS XML. This will be stale, don't know a great
        ## way around that. Mb we could script something with fcsvr_client
        ## For now we just assume our YT history hasn't changed for this
        ## Asset (any changes will be over-ridden)
        fcsXMLIn = FCSXMLObject()
        fcsXMLIn.setFile(fcsXMLInPath)
        entityID = fcsXMLIn.entityID
              
        ## Date/time string used for reporting
        currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))

        historyField = "%s Publish History" % self.serviceName
        publishHistory = fcsXMLIn.valueForField(historyField)
        if publishHistory:
          publishHistory = "%s\n%s: %s" % (publishHistory,currentTime,histString)
        else:
          publishHistory = "%s: %s" % (currentTime,histString)
          
        ## Create our XML object and set vars
        fcsXMLOut = FCSXMLObject(entityID)
        fcsXMLOut.overwriteExistingFiles = True
        xmlOutPath = os.path.join(os.path.dirname(self.supportPath),"fcsvr_xmlin","%s_%s.xml" % (self.serviceName,entityID))
        ## Report our history.
        fcsXMLOut.setField(FCSXMLField("%s Publish History" %  self.serviceName, publishHistory)) 
        fcsXMLOut.setField(FCSXMLField("Publish to %s" %  self.serviceName, "false", "bool"))
        if processingSuccessfull:
          fcsXMLOut.setField(FCSXMLField("Published to %s" %  self.serviceName, "true", "bool"))
          ## We may want to do this, but if other targets were specified, it may be premature
          ##fcsXMLOut.setField(FCSXMLField("Status", "Published", "string"))
        
        if self.ytCustomID:
          fcsXMLOut.setField(FCSXMLField("YouTube Generated ID", self.ytCustomID)) 
        
        print "Hist String :%s" % histString
        if not fcsXMLOut.xmlOut(xmlOutPath):
          print "Failed to output FCS XML to: '%s' Error:\n%s" % (xmlOutPath, fcsXMLOut.lastError)
      
        ## Get rid of our local YT xmlin file (xmlin/status-123.xml), 
        ## if processing failed or isn't finished, we will simply 
        ## redownload this file at next check
        if os.path.exists(ytXMLInPath):
          os.remove(ytXMLInPath)
        
        ## At this point we have transferred our YT status file and 
        ## it reported failure. Get Rid of our inprogress watcher
        os.remove(fcsXMLInPath)
        
  def checkYouTubeXMLStatusFile(self, filePath):
    """import YouTube XML status file, verify that our publishing worked"""
    errorCode = ""
    self.logger("ytCheck hit", "detailed")

    if os.path.exists(filePath):
      ytXML = minidom.parse(filePath).documentElement      
      self.logger("Loading XML from File: %s" % filePath, "info")
    else:
      self.logger("File does not exist at path: %s, exiting!" % filePath, "error")
      return False
  
    for item in ytXML.getElementsByTagName('item_status'):
      self.logger("iterating through YT item", "detailed")
      actionElement = item.getElementsByTagName('action')[0]
      commandTxt = self.getXMLNodeText(actionElement.getElementsByTagName('command')[0].childNodes)
      try:
        if self.getXMLNodeText(item.getElementsByTagName('id')[0].childNodes):
          self.ytCustomID = self.getXMLNodeText(item.getElementsByTagName('id')[0].childNodes)
      except:
        self.ytCustomID = ""
        
      statusTxt = self.getXMLNodeText(actionElement.getElementsByTagName('status')[0].childNodes)
      statusDetailTxt = self.getXMLNodeText(actionElement.getElementsByTagName('status_detail')[0].childNodes)
      
      test = self.getXMLNodeText(actionElement.getElementsByTagName('command')[0].childNodes)
      
      self.logger("StatusTxt: '%s' for command: '%s'" % (statusTxt, commandTxt), "detailed")
      
      if statusTxt == "Failure":
          self.logger("Youtube reports an error with command: '%s'\n\tError: '%s'" % (commandTxt, statusDetailTxt),"error")
          errorCode = 1
      elif not statusTxt == "Success":
        errorCode = 3
      
    if not errorCode:
      self.logger("Youtube reports upload successful!", "detailed")
      return True
    else:
      self.logger("Youtube reports upload failed! ErrorCode: %s" % errorCode, "detailed")
      return False
        
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
      self.ytSFTPServer = parser.get("YouTube","host")   
      self.ytUsername = parser.get("YouTube","username")
      self.ytOwnerName = parser.get("YouTube","ownername")  
    except:
      self.logger("loadConfiguration() Problem loading configuration records, please double check your configuration") 

    try:
      self.retryCount = int (parser.get("YouTube","retryCount"))
    except:
      try:
        self.retryCount = int (parser.get("GLOBAL","retryCount"))
      except:
        self.retryCount = int (5);
    return True
    
  def setFCSXMLFile(self,filePath):
    """import FCS XML file, and set applicable local values"""
    TransmogrifierTargetObject.setFCSXMLFile(self, filePath)
    self.ytCustomID = self.fcsXMLObject.valueForField("Youtube Generated ID")
           
  def runFunction(self, function):
    """Perform action based on passed function"""
    if function == "batchStatusCheck":
      return self.batchStatusCheck()
    else:
      return TransmogrifierTargetObject.runFunction(self,function)
              
  def upload(self, dirPath=""):
    '''Uploads all relative assets to the configured SFTP host via the 
    member variable ``ytSFTPServer``. This is achived by creating an SFTP
    batch file and then passing to the ``sftp`` system binary. This method
    will also call :func:`youtube.YouTubeObject.xmlOut` and will upload the
    resulting XML file. We will attempt the SFTP transfer as defined by our
    ``retryCount`` configuration variable.'''
    theError = ""
    
    retryCount = self.retryCount
    currentRetryNum = 1
    
    ## Sanity checks
    if not dirPath:
      dirPath = self.supportPath
    if not os.path.isdir(dirPath):
      self.logger("upload() Directory does not exist:'%s'" % dirPath, "error")
      return False
    
    ## generate our xml
    xmlOutPath = os.path.join(dirPath, "xmlout", "%s.xml" % self.entityID)
    if not self.xmlOut(xmlOutPath):
      self.logger("upload() could not write XML, exiting", "error")
      return False
      
    ## Create/open our batch file (used for sftp batch uploads)
    uploadDirPath = os.path.join(dirPath,"upload")
    batchFilePath = os.path.join(uploadDirPath, "%s.batch" % self.entityID)
    if not os.path.isdir(uploadDirPath):
      os.mkdir(uploadDirPath)
      
    ## If our batch file exists and we are not allowed to overwrite it, bail
    if not self.overwriteExistingFiles and os.path.exists(batchFilePath):
      self.logger("upload() Batch file already exists at path: '%s' and we are not allowed to overwrite, exiting!" % batchFilePath, "error")
      return False
    
    batchFile = open(batchFilePath, "w")
    batchFile.write("-mkdir '%s'\n" % self.entityID)
    batchFile.write("chdir '%s'\n" % self.entityID)
    
    ## Iterate through our files and append their paths to our batchfile
    if len(self.files) > 0:
      for file in self.files.itervalues():
        if os.path.exists(file.path):
          self.logger("upload() adding file to batch upload: '%s'" % (file.fileName), "normal")
          batchFile.write("put '%s'\n" % file.path)
        else:
          theError = file.path,sys.exc_info()[0]
          self.logger("upload() could not uplod file: '%s' Error:\n%s" % (theError), "error")
        
    ## Add our XML file
    if os.path.exists(xmlOutPath):
      self.logger("upload() adding file to batch upload: '%s'" % os.path.basename(xmlOutPath), "detailed")
      batchFile.write("put '%s'\n" % xmlOutPath)
    else:
      theError = xmlOutPath,sys.exc_info()[0]
      self.logger("upload() could not upload file: '%s' Error:\n%s" % (theError), "error")
   
            
    ## Build our FCS object for reporting
    if not self.fcsXMLOutObject:
      self.fcsXMLOutObject = FCSXMLObject(self.entityID)
    fcsXMLOut = self.fcsXMLOutObject
    
     
    batchFile.close()
    ## If no errors so far, generate our delivery.complete file and do our
    ## uploads
    if not theError:
      if not os.path.exists(uploadDirPath):
        currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))
        self.logger("upload() failed: directory: '%s' does not exist" % uploadDirPath, "error")
        self.appendFCSField("%s Publish History" % self.serviceName, "%s: Failed to publish to %s. Please try again. Error:\n\t%s\n" % (currentTime,self.serviceName,self.lastError))
        return False
      else:
        didFinishUpload = False;
        while ((currentRetryNum <= retryCount) and (not didFinishUpload)):
          ## Upload our files based on our batch process list
          if not os.system("/usr/bin/sftp -b '%s' %s@%s" % (batchFilePath, self.ytUsername,self.ytSFTPServer)):
            currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))
            didFinishUpload = True;
            self.logger("upload() successfully uploaded files!", "detailed")
            self.appendFCSField("%s Publish History" % self.serviceName, "%s: Successfully published to %s after %s attempt(s).\n" % (currentTime,self.serviceName,currentRetryNum)) 
    
            fcsXMLOut.setField(FCSXMLField("Published to %s" %  self.serviceName, "true", "bool")) 
            fcsXMLOut.setField(FCSXMLField("Status", "Verify Publishing", "string")) 
            
            ## remove our batch file
            os.remove(batchFilePath)
            
          else:
            print "currentRetryNum: %i, retryCount: %i\n" % (currentRetryNum, retryCount)
            currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))
            if (currentRetryNum < retryCount): 
                self.logger("upload() failed: error uploading files via sftp on attempt %s of %s, will retry!" % (currentRetryNum,retryCount), "error")
                self.appendFCSField("%s Publish History" % self.serviceName, "%s: Failed to upload files to %s on attempt %s of %s, will retry.\n" % (currentTime,self.serviceName,currentRetryNum,retryCount))
                currentRetryNum = currentRetryNum + 1
            else:
                self.logger("upload() failed: error uploading media files via sftp after %s attempts!" % retryCount, "error")
                self.appendFCSField("%s Publish History" % self.serviceName, "%s: Failed to publish to %s. Please try again. Error:\n\t%s\n" % (currentTime,self.serviceName,self.lastError))
                return False
      
      delFilePath = os.path.join(uploadDirPath,"delivery.complete")
      delFile = open(delFilePath, "w")
      delFile.close()
      batchFile = open(batchFilePath, "w")
      batchFile.write("-mkdir '%s'\n" % self.entityID)
      batchFile.write("chdir '%s'\n" % self.entityID)
      batchFile.write("put '%s'\n" % delFilePath)
      batchFile.close()
      currentRetryNum = 1;

      while(currentRetryNum <= retryCount):
        if not os.system("/usr/bin/sftp -b '%s' %s@%s" % (batchFilePath, self.ytUsername,self.ytSFTPServer)):
      
          ## Generate our shell file in our 'inprogress' directory
          ## so that we can keep track of existing is-progress uploads
          ## A SQLlite db is probably better suited here.
          
          inprogressDirPath = os.path.join(dirPath,"inprogress")
          inprogressFilePath = os.path.join(inprogressDirPath, "%s.xml" % self.entityID)
          if not os.path.isdir(inprogressDirPath):
            os.mkdir(inprogressDirPath)
          shutil.copyfile(self.fcsXMLObject.path,inprogressFilePath)
          os.remove(batchFilePath)
          return True;
        else:
          currentRetryNum += 1;
      self.logger("upload() failed: Failed uploading delivery.complete file after %s attempts!" % retryCount, "error")
      self.appendFCSField("%s Publish History" % self.serviceName, "%s: Failed to publish to %s. Please try again. Error:\n\t%s\n" % (currentTime,self.serviceName,self.lastError))
      return False;
      
    else:
      self.appendFCSField("%s Publish History" % self.serviceName, "%s: An error occured publishing to %s. Please try again. Error: %s\n" % (currentTime,self.serviceName, self.lastError)) 
      return False
   
  def xmlOut(self, filePath=""):
    '''Output our YouTube compliant XML. If passed a filepath for the second
    Parameter, we write to that file, otherwise we print to stdout'''
    ## Sanity checks and variable initialization
    theThumbFile = ""
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
    if not self.emailToNotify:
      self.logger("No notification email address specified!", "error")
      return False
    else:
      ## Youtube wants space delimited addresses in their xml
      self.emailToNotify = self.emailToNotify.replace(","," ")
    if not self.entityID:
      self.logger("Entity ID could not be determined!", "error")
    if not self.title:
      self.logger("No title specified!", "error")
      return False
    if not self.ytUsername:
      self.logger("Youtube username or password not specified!", "error")
      return False
    if not self.ytOwnerName:
      self.logger("Youtube ownername not specified!", "error")
      return False      
    
    ## Make sure either that our xml out file doesn't already exist, or 
    ## that we're allowed to overwrite existing files. Then Generate our XML     
    if (filePath and (not os.path.exists(filePath)  \
    or (os.path.exists(filePath) and self.overwriteExistingFiles))
    and os.path.isdir(os.path.dirname(filePath))) \
    or not filePath : 
      ## create our new xml doc, add our root FCS elements:
      ## <?xml version="1.0" encoding="UTF-8"?> 
      ## <rss version="2.0" 
      ## xmlns:media="http://search.yahoo.com/mrss" 
      ## xmlns:yt="http://www.youtube.com/schemas/yt/0.2"> 
      ## <channel> 
      ## <yt:notification_email>sandy@example.com, 
      ## ben@example.com</yt:notification_email> 
      ## <yt:account> 
      ## <yt:username>happypartner</yt:username> 
      ## <yt:password>thec0wg0esm00</yt:password> 
      ## </yt:account> 
      ## <yt:owner_name>Example.com TV</yt:owner_name> 
    
      self.xmlObject = minidom.Document()
      xmlDoc = self.xmlObject
      
      rssElement = xmlDoc.createElement("rss")
      rssElement.setAttribute("xmlns:media", "http://search.yahoo.com/mrss")
      rssElement.setAttribute("xmlns:yt", "http://www.youtube.com/schemas/yt/0.2")
      xmlDoc.appendChild(rssElement)

      channelElement = xmlDoc.createElement("channel")
      rssElement.appendChild(channelElement)  

      notifyElement = xmlDoc.createElement("yt:notification_email")
      notifyElement.appendChild(xmlDoc.createTextNode("%s"% self.emailToNotify))
      channelElement.appendChild(notifyElement)
      
      accountElement = xmlDoc.createElement("yt:account")
      channelElement.appendChild(accountElement)
      
      userElement = xmlDoc.createElement("yt:username")
      userElement.appendChild(xmlDoc.createTextNode(self.ytUsername))
      passElement = xmlDoc.createElement("yt:password")
      passElement.appendChild(xmlDoc.createTextNode(self.ytPassword))
      accountElement.appendChild(userElement)
      accountElement.appendChild(passElement)
      
      ownerElement = xmlDoc.createElement("yt:owner_name")
      passElement.appendChild(xmlDoc.createTextNode(self.ytOwnerName))
      channelElement.appendChild(ownerElement)

      ## And then our individual files.
      for file in self.files.itervalues():
        if file.fileType == "video":
          ## <item> 
          ## <yt:action>Insert</yt:action> 
          ## <media:title>Covert Operations II</media:title> 
          ## <media:content url="file://co2_file.mov" fileSize="12216320"> 
          ## <media:description type="plain"> Ms. World reveals world domination plans. </media:description> 
          ## <media:keywords>covert, operations, spy, pagent</media:keywords> 
          ## <media:category>Entertainment</media:category> 
          ## <media:rating scheme="urn:simple">nonadult</media:rating> 
          ## </media:content> 
                
          itemElement = xmlDoc.createElement("item")
          channelElement.appendChild(itemElement)

          actionElement = xmlDoc.createElement("yt:action")
          actionElement.appendChild(xmlDoc.createTextNode("insert"))
          itemElement.appendChild(actionElement)
          
          titleElement = xmlDoc.createElement("media:title")
          titleElement.appendChild(xmlDoc.createTextNode(file.title))
          itemElement.appendChild(titleElement)
           
          contentElement = xmlDoc.createElement("media:content")
          contentElement.setAttribute("url", "file://%s" % file.fileName)
          contentElement.setAttribute("fileSize", "%s" % file.size)
          itemElement.appendChild(contentElement)

          if self.description:
            mediaDescElement = xmlDoc.createElement("media:description")
            mediaDescElement.appendChild(xmlDoc.createTextNode(self.description))
            contentElement.appendChild(mediaDescElement)

          if self.keywordString:
            keywordElement = xmlDoc.createElement("media:keywords")
            keywordElement.appendChild(xmlDoc.createTextNode(self.keywordString))
            contentElement.appendChild(keywordElement)

          
          categoryElement = xmlDoc.createElement("media:category")
          categoryElement.appendChild(xmlDoc.createTextNode("Entertainment"))
          contentElement.appendChild(categoryElement)
          
          ratingElement = xmlDoc.createElement("media:rating")
          ratingElement.setAttribute("scheme", "urn:simple")
          ratingElement.appendChild(xmlDoc.createTextNode("nonadult"))
          contentElement.appendChild(ratingElement)
        
          ## <yt:language>en</yt:language> 
          ## <yt:date_recorded>2005-08-01</yt:date_recorded> 
          ## <yt:location> 
          ## <yt:country>US</yt:country>
          ## <yt:location_text>Beverly Hills, CA</yt:location_text> 
          ## </yt:location> 
          ## <yt:start_time>2007-07-07T07:07:07</yt:start_time> 
          ## <yt:end_time>2007-12-31T00:00:00</yt:end_time> 
          
          languageElement = xmlDoc.createElement("yt:language")
          languageElement.appendChild(xmlDoc.createTextNode("en"))
          itemElement.appendChild(languageElement)
          
          locationElement = xmlDoc.createElement("yt:location")
          countryElement = xmlDoc.createElement("yt:country")
          countryElement.appendChild(xmlDoc.createTextNode("US"))
          locationElement.appendChild(countryElement)
          
          locTextElement = xmlDoc.createElement("yt:location_text")
          locTextElement.appendChild(xmlDoc.createTextNode("%s" % self.eventLocation))
          locationElement.appendChild(locTextElement)

          dateRecordedElement = xmlDoc.createElement("yt:date_recorded")
          dateRecordedElement.appendChild(xmlDoc.createTextNode("%s" % self.eventYear))
          locationElement.appendChild(dateRecordedElement)
          
          itemElement.appendChild(locationElement)

          ## <yt:community> 
          ## <yt:allow_comments>Always</yt:allow_comments> 
          ## <yt:allow_responses>Never</yt:allow_responses> 
          ## <yt:allow_ratings>true</yt:allow_ratings> 
          ## <yt:allow_embedding>true</yt:allow_embedding> 
          ## </yt:community> 
          ## <yt:policy> 
          ## <yt:commercial>share</yt:commercial> 
          ## <yt:ugc>share</yt:ugc> 
          ## </yt:policy> 
          
          communityElement = xmlDoc.createElement("yt:community")
          itemElement.appendChild(communityElement)
          commentsElement = xmlDoc.createElement("yt:allow_comments")
          commentsElement.appendChild(xmlDoc.createTextNode("Always"))
          communityElement.appendChild(commentsElement)

          responseElement = xmlDoc.createElement("yt:allow_responces")
          responseElement.appendChild(xmlDoc.createTextNode("Always"))
          communityElement.appendChild(responseElement)

          ratingsElement = xmlDoc.createElement("yt:allow_ratings")
          ratingsElement.appendChild(xmlDoc.createTextNode("true"))
          communityElement.appendChild(ratingsElement)

          embedElement = xmlDoc.createElement("yt:allow_embedding")
          embedElement.appendChild(xmlDoc.createTextNode("true"))
          communityElement.appendChild(embedElement)


          policyElement = xmlDoc.createElement("yt:policy")
          itemElement.appendChild(policyElement)

          commercialElement = xmlDoc.createElement("yt:commercial")
          commercialElement.appendChild(xmlDoc.createTextNode("share"))
          policyElement.appendChild(commercialElement)
          
          ugcElement = xmlDoc.createElement("yt:ugc")
          ugcElement.appendChild(xmlDoc.createTextNode("share"))
          policyElement.appendChild(ugcElement)


          ## <yt:movie_metadata> 
          ## <yt:custom_id>000ABC123XYZ</yt:custom_id> 
          ## <yt:title>Covert Operations II (Deluxe extended 
          ## director's cut)</yt:title> 
          ## </yt:movie_metadata> 
          ## <yt:distribution_restriction> 
          ## <yt:distribution_rule>Deny</yt:distribution_rule> 
          ## <yt:adsense_syndication>Deny</yt:adsense_syndication> 
          ## </yt:distribution_restriction> 
          ## <yt:advertising> 
          ## <yt:invideo>Allow</yt:invideo> 
          ## </yt:advertising> 
          ## <yt:target>upload,claim,fingerprint</yt:target> 
          ## <yt:keep_fingerprint>no</yt:keep_fingerprint> 
          ## </item>
          
          movieElement = xmlDoc.createElement("yt:movie_metadata")
          
          itemElement.appendChild(movieElement)
          customidElement = xmlDoc.createElement("yt:custom_id")
          customidElement.appendChild(xmlDoc.createTextNode(self.entityID))
          movieElement.appendChild(customidElement)
          
          titleElement = xmlDoc.createElement("yt:title")
          titleElement.appendChild(xmlDoc.createTextNode(file.title))
          movieElement.appendChild(titleElement)

          
          #movieElement.appendChild(
          #xmlDoc.createElement("yt:custom_id").appendChild(xmlDoc.createTextNode(self.entityID)))

          distributionElement = xmlDoc.createElement("yt:distribution_restriction")
          itemElement.appendChild(distributionElement)
          
          distributionRuleElement = xmlDoc.createElement("yt:distribution_rule")
          distributionRuleElement.appendChild(xmlDoc.createTextNode("Deny"))
          distributionElement.appendChild(distributionRuleElement)
          
          adsenseElement = xmlDoc.createElement("yt:adsense_syndication")
          adsenseElement.appendChild(xmlDoc.createTextNode("Deny"))
          distributionElement.appendChild(adsenseElement)
          
          advertisingElement = xmlDoc.createElement("yt:advertising")
          invideoElement = xmlDoc.createElement("yt:invideo")
          invideoElement.appendChild(xmlDoc.createTextNode("Allow"))
          advertisingElement.appendChild(invideoElement)

          itemElement.appendChild(advertisingElement)
          
          targetElement = xmlDoc.createElement("yt:target")
          targetElement.appendChild(xmlDoc.createTextNode("upload,claim,fingerprint"))
          itemElement.appendChild(targetElement)
          
        else:
          self.logger("Unknown media type: '%s' for file: '%s'" % (file.fileType, file.path))
          return False;

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
    
 
        


