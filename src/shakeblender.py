#!/usr/bin/python
# -*- coding: utf-8 -*-


################################
##
##  Transmogrifier: ShakeBlender
##  A Final Cut Server import/export tool 
##
##  This class is a decedent of TransmogrifierObject, and provides no additional
##  interfaces above what is provided via it's parent, TransmogrifyTargetObject. 
##  However, numerous methods have been overridden to provide shake-specific
##  Image manipulation operations. This is provided for reference purposes
##  only, it is not suitable for mass deployment.
##
#############################################################

import os, os.path, re, glob, shutil, sys, types, datetime, time, tempfile
from ftplib import FTP
from fcsxml import FCSXMLField, FCSXMLObject
from transmogrifierTarget import TransmogrifierTargetObject, MediaFile
from ConfigParser import *
import subprocess 


from xml.dom import minidom
    
    
## Date/time string used for reporting
currentTime = datetime.datetime.fromtimestamp(time.mktime(datetime.datetime.now().timetuple()))

class ShakeBlenderObject(TransmogrifierTargetObject):
    """Our main shakeBlender object, used for processing media files with Shake"""
    
    bgFilePath = ""
    backgroundSource = ""
    inFilePath = ""
    outFilePath = ""
    validActions = ['autoKey']
        
    debug = False
    
    def __init__(self,entityID=0):
        """Our construct, instantiate our members"""
        TransmogrifierTargetObject.__init__(self,entityID)
        self.refID = ""
        self.multipleBitRate = True
        self.overwriteExistingFiles = True
        self.serviceName = "ShakeBlender"
        self.backgroundSource = ""
        self.supportSubDirs =  ["xmlin","background","support","support/tmp","out_videocrew1","out_videocrew2"]
        self.neededAttributes = ["title","backgroundSource"]
        self.validActions = ['autoKey']
        
    def setFCSXMLFile(self,filePath):
        """import FCS XML file, and set applicable local values"""
        if not TransmogrifierTargetObject.setFCSXMLFile(self, filePath):
            self.logger("setFCSXMLFile() parent could not load file, exiting","error")
            return False;
        
        device = self.fcsXMLObject.valueForField("Stored On")
        deviceRelPath = self.fcsXMLObject.valueForField("Location")
        fileName = self.fcsXMLObject.valueForField("File Name")
        devicePath = self.pathForDevice(device)
        
        
        if not devicePath:
            self.logger("setFCSXMLFile() could not determine path for device:'%s'," % device,"error")
            inFilePath = filePath
        else: 
            ## make sure we get rid of the leading / on our deviceRelPath
            inFilePath = os.path.join(devicePath,deviceRelPath[1:],fileName)
        
        ## try to read the background Source from the filename.
        fileNameReObj = re.match("(.*)(\d{2})\.mov",fileName)
        if fileNameReObj:
            fileName = "%s.mov" % fileNameReObj.group(1)
            backgroundCode = int(fileNameReObj.group(2))
            if backgroundCode == 1:
                backgroundSource = "snowmen"
            elif backgroundCode == 2:
                backgroundSource = "ornaments"
            elif backgroundCode == 3:
                backgroundSource = "hills"
            
        if not backgroundSource:
            self.logger("setFCSXMLFile() determining background source from XML!")
            backgroundSource = self.fcsXMLObject.valueForField("Background Source")
        
        try:
            videoCrewNum = int(self.fcsXMLObject.valueForField("Video Crew"))
        except:
            self.logger("setFCSXMLFile() Error reading field \"Video Crew\"","error")
            videoCrewNum = 1
        
        if not isinstance(self.configParser,ConfigParser):
            self.logger("setFCSXMLFile() No valid ConfigParser object loaded!", "error")
            return False
        
        ## Get our background file path from settings. Looks for config key
        ## with the name stored in var bgKey
        try:
            parser = self.configParser
            bgKey = "%s_backgroundfile" % backgroundSource
            bgFilePath = parser.get("SHAKE_BLENDER",bgKey)
        except:
            self.logger("setFCSXMLFile() No background defined for source:'%s' at key:'%s' in config file, attempting to use defaults" % (backgroundSource,bgKey), "detailed")
            try:
                bgFilePath = parser.get("SHAKE_BLENDER","default_backgroundfile")
            except:
                self.logger("setFCSXMLFile() Could determine background for source:'%s'" % backgroundSource, "error")
                return False
        
        ## Get our outfile path
        try:
            outFileKey = "%s_outpath" % backgroundSource
            outFilePath = parser.get("SHAKE_BLENDER",outFileKey)
        except:
            self.logger("setFCSXMLFile() No outpath defined for source:'%s' at key:'%s' in config file, attempting to use defaults" % (backgroundSource,outFileKey), "detailed")
            try:
                outFilePathConf = parser.get("SHAKE_BLENDER","default_outpath") 
                outFilePath = os.path.join(outFilePathConf,"out_videocrew%s" % videoCrewNum,backgroundSource)
            except:
                outFilePath = os.path.join(self.supportPath,"out_videocrew%s" % videoCrewNum,backgroundSource)

        
        self.logger("setFCSXMLFile() Determined final outFilePath to be:'%s'" % outFilePath, "detailed")

        if not os.path.isdir(outFilePath):
            if not os.makedirs(outFilePath):
                self.logger("setFCSXMLFile() Output directory:'%s' for background source:'%s' does not exist, make sure that '%s_outpath' is specified in your config file!" %(outFilePath,backgroundSource,backgroundSource), "error")
                return False
        
        ##self.outFilePath = os.path.join(outFilePath,"%s_%s.mov" % (self.title,backgroundSource))
        self.outFilePath = os.path.join(outFilePath,fileName)
        
        self.logger("setFCSXMLFile() Determined final output file to be:'%s'" % self.outFilePath, "detailed")

    
        if os.path.isfile(bgFilePath):
            self.bgFilePath = bgFilePath
        else:
            self.logger("setFCSXMLFile() Could not find file:'%s' for background source: %s, make sure that %s_backgroundfile is specified in your config file!" %(bgFilePath,backgroundSource,backgroundSource), "error")
            return False
        
        if os.path.isfile(inFilePath):
            self.inFilePath = inFilePath
        else:
            self.logger("setFCSXMLFile() Could not find input file for processing at path:'%s'" % inFilePath, "error")
            return False
        return True
        
    def frameCountForInFile(self):
        if os.path.isfile(self.inFilePath):
            frameCount = self.frameCountForMovieAtPath(self.inFilePath)
            if not frameCount:
                self.logger("frameCountForInFile() could not determine framecount from file at path:'%s', reading from XML!" % self.inFilePath,"error")
                frameRate = float(self.fcsXMLObject.valueForField("Video Frame Rate"));
                duration = float(self.fcsXMLObject.valueForField("Duration"));
                frameCount = duration * frameRate
                self.logger("frameCountForInFile() determined framecount: '%s' from XML. frameRate:'%s' duration:'%s'" % (frameCount,frameRate,duration),"error")
            return frameCount
                
    def frameCountForBgFile(self):
        if os.path.isfile(self.bgFilePath):
            frameCount = self.frameCountForMovieAtPath(self.bgFilePath)
            if not frameCount:
                ## hack for webeye, 10.5 can't pull framecount from qtinfo
                ## so we have to statically set this.
                bgSource = self.fcsXMLObject.valueForField("Background Source")
                if bgSource == "ornaments":
                    frameCount =  572
                elif bgSource == "snowmen":
                    frameCount = 326
                else:
                    frameCount = 404
                self.logger("frameCountForBgFile() could not determine framecount from file at path:'%s', using static value:'%s'" % (self.bgFilePath,frameCount),"error")

            return frameCount
        
    def frameCountForMovieAtPath(self, filePath):
        if not os.path.isfile(filePath):
            self.logger("frameCountForMovieAtPath() could not find movie at path:'%s'" % filePath,"error")
            return False
            
        ## this could be Pythonized quite a bit
        durationCMD = subprocess.Popen('/usr/libexec/podcastproducer/qtinfo "%s" | awk -F= \'/duration/ {print$2}\' | perl -p -e \'s/.*?\"(.*?)\".*$/$1/g\'' % filePath,shell=True,stdout=subprocess.PIPE,universal_newlines=True)
        frameRateCMD = subprocess.Popen('/usr/libexec/podcastproducer/qtinfo "%s" | awk -F= \'/frameRate/ {print$2}\' | perl -p -e \'s/(.*?);.*$/$1/g\'' % filePath,shell=True,stdout=subprocess.PIPE,universal_newlines=True)
        
        durationCMD_STDOUT, durationCMD_STDERR = durationCMD.communicate()
        frameRateCMD_STDOUT, frameRateCMD_STDERR = frameRateCMD.communicate()
        
        if not durationCMD_STDOUT:
            self.logger("frameCountForMovieAtPath() could not get duration for movie at path:'%s'" % filePath,"error")
            return False
        if not frameRateCMD_STDOUT:
            self.logger("frameCountForMovieAtPath() could not get framerate for movie at path:'%s'" % filePath,"error")
            return False
        
        ## get our duration and our framerate. Our duration should always
        ## be a float, our framerate can be an int or float
        duration = float(durationCMD_STDOUT)
        
        testNum = frameRateCMD_STDOUT.replace("\n","").replace(" ","").replace('"',"")
                
        try:
            frameRate = float(testNum)
        except:
            frameRate = int(frameRateCMD_STDOUT)
        
        frameCount = duration * frameRate
        self.logger("frameCountForMovieAtPath() path:'%s' frameCount:'%s' Duration:'%s' frameRate:'%s'" % (filePath,frameCount,duration,frameRate))
        
        if int(round(frameCount)) < frameCount:
            return int(round(frameCount)) + 1
        else:
            return int(round(frameCount))

        
        
    def runFunction(self, function):
        """Performs Shake functions"""
        bgFilePath = self.bgFilePath

        if self.bgFilePath and os.path.isfile(self.bgFilePath):
            bgFilePath = self.bgFilePath
        elif self.bgFilePath:
            self.logger("specialFunction() bfFilePath:'%s' is not a file, cannot continue!" % self.bgFilePath,"error")
            return False
        else:
            self.logger("specialFunction() background file could not be determined, cannot continue!" % self.bgFilePath,"error")
            return False
        
        if function == "autoKey":
            ## get some information from our movie file
            
            
            supportDir = os.path.join(self.supportPath,"support")
            templateFilePath = os.path.join(self.supportPath,"support","templateScript.shk")
            
            ## make sure that we have a support dir and template file
            if os.path.isdir(supportDir):
                if os.path.isfile(templateFilePath):
                    templateFileHandler = open(templateFilePath)
                else:
                    self.logger("specialFunction('autoKey') Could not find template shake file at path: '%s' for processing!" % templateFilePath, "error")
                    return False
            else:    
                    self.logger("specialFunction('autoKey') Could not find shakeblender support directory:'%s'" %supportDir, "error")
                    return False
            
            tmpPath = os.path.join(self.supportPath,"support","tmp")
            if not os.path.exists(tmpPath):
                os.makedirs(tmpPath)
                        
            tempDir = tempfile.mkdtemp(prefix=os.path.join(tmpPath,"%s_" % self.title))
            tempAudioFilePath = os.path.join(tempDir,"audiofile.mov")
            tempRenderFilePath = os.path.join(tempDir,"renderfile.mov")
            tempReferenceFilePath = os.path.join(tempDir,"referencefile.mov")
            
            
            ## if we reach this point we have an open file handler in templateFileHandler
            ## create a temp file which will serve as our active shake script
            tempFileDescriptor,tempFilePath = tempfile.mkstemp(prefix="%s_" % self.title,suffix=".shk",dir=tempDir)
            tempFileHandler = os.fdopen(tempFileDescriptor, "w+")
            if tempFileHandler:
                ## iterate through our template file, write it to our tempfile
                ## replace our template file paths
                frameCount = self.frameCountForInFile()
                bgFrameCount = self.frameCountForBgFile()
                if not frameCount:
                    self.logger("specialFunction() autoKey: Could not determine frame count for main clip, cannot continue!","error")
                    return False

                if not bgFrameCount:
                    self.logger("specialFunction() autoKey: Problem determining frame count for background, returning '%s'" % frameCount,"warning")
                    self.bgFrameCount = frameCount 
                
                while True:
                    line = templateFileHandler.readline()
                    if not line: 
                        break;
                    line = line.replace('SetTimeRange("1")','SetTimeRange("1-%d")' % frameCount);
                    line = line.replace("filein_background.mov",self.bgFilePath)
                    line = line.replace("filein_greenscreen.mov",self.inFilePath)
                    line = line.replace("fileout_movie.mov",tempRenderFilePath)
                    line = line.replace('1000, "Freeze"','%s, "Freeze"' % (int(frameCount) + 1))
                    tempFileHandler.write(line)
                templateFileHandler.close()
                tempFileHandler.close()
                print "tempfilepath: %s" % tempFilePath
                
                                
                ## Run our shake script
                shakeRetCode = subprocess.call("/usr/bin/shake -exec '%s'" % (tempFilePath),shell=True,universal_newlines=True)
                if shakeRetCode is not 0:
                    self.logger("specialFunction('autoKey') Shake processing failed return code:'%s'" % shakeRetCode, "error")
                    return False
                
                ## Extract the audio from our source file
                qtextractRetCode = subprocess.call("/usr/libexec/podcastproducer/qttrackextract audio '%s' '%s'" % (self.inFilePath,tempAudioFilePath),shell=True,stdout=subprocess.PIPE,universal_newlines=True)
                if qtextractRetCode is not 0:
                    self.logger("specialFunction('autoKey') Could not extract audio from movie:'%s' return code:'%s'" %(self.inFilePath,qtextractRetCode), "error")
                    return False
                
                ## Reattach the file
                qtTrackAddRetCode = subprocess.call("/usr/libexec/podcastproducer/qttrackadd '%s' '%s' '%s'" % (tempAudioFilePath,tempRenderFilePath,tempReferenceFilePath),shell=True,universal_newlines=True)
                ## "/usr/libexec/podcastproducer/qtjoin qttrackadd /private/tmp/audiofile.mov '" + self.outFilePath + "' '" + self.outFilePathStitched" 
                if qtTrackAddRetCode is not 0:
                    self.logger("specialFunction('autoKey') Could not place audiofile:'%s' into movie:'%s' return code:'%s'" %(tempAudioFilePath,tempRenderFilePath,qtextractRetCode), "error")
                    return False

                ## Save a flattened copy of the movie in it's final destination
                qtFlattenRetCode = subprocess.call("/usr/libexec/podcastproducer/qtflatten '%s' '%s'" % (tempReferenceFilePath,self.outFilePath),shell=True,universal_newlines=True)
                if qtFlattenRetCode is not 0:
                    self.logger("specialFunction('autoKey') Could not flatten movie:'%s' into movie:'%s' return code:'%s'" %(tempReferenceFilePath,self.outFilePath,qtFlattenRetCode), "error")
                    return False

            
            ## cleanup support files
            ## os.rmtree(tempDir)
            return True
            
            
       
    def pathForDevice(self, deviceName):
        """Returns a Path for an FCS device todo: this needs to be moved to master object"""
        path = False
        if deviceName == "Eshots Vid 1 FTP":
            path = os.path.join("/Volumes/FCServer HD/FTPUploads/E Shots/Video Crew 1")
        elif deviceName == "Eshots Video":
            path = os.path.join("/Volumes/FCServer HD/Media/Eshots")
        elif deviceName == "Eshots Video 2 FTP":
            path = os.path.join("/Volumes/FCServer HD/FTPUploads/E SHOTS/Video Crew 2")
        elif deviceName == "Library":
            path = os.path.join("/Volumes/FCServer HD/Library")
        elif deviceName == "Media":
            path = os.path.join("/Volumes/FCServer HD/Media")
        elif deviceName == "Support":
            path = os.path.join("/Volumes/FCServer HD/Support")
        elif deviceName == "Watchers":
            path = os.path.join("/Volumes/FCServer HD/Watchers")
        elif deviceName == "debugtest":
            path = os.path.join("/Users/hunterbj/Desktop/","Shake Project","samples")
        
        if not path:
            self.logger("pathForDevice() Path could not be found for device:'%s'"  % deviceName)
            return False
        elif not os.path.exists(path):
            self.logger("pathForDevice() local path could not be found for device:'%s', resolved path:'%s'"  % (deviceName,path))
            
        return path

    
                  
