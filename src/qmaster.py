#!/usr/bin/env python
# -*- coding: utf-8 -*-


################################
##
##  Transmogrifier: qmaster
##  A Python interface for submitting and monitoring compressor/qmaster jobs.
##
#############################################################


import HTMLParser
import os
import re
import sys
import datetime
import signal
import subprocess
import time

#import createDailyReel

## init our vars
version = '1.0b'
build = '2011041401'

global debug
debug = False


######################### START FUNCTIONS ###############################


######################### END FUNCTIONS #################################

class QmasterBatch():
  '''Our main qmaster batch class, used to submit and monitor qmaster batches.
  
    :param sourceFile: Specify the source file to be submitted
    :type sourceFile: str
  
    :param destinationFile: Specify the destination file
    :type sourceFile: str  
    
    :param destinationDirectory: Specify the destination directory (the original
      filename will be used with a .mov extension)
    :type sourceFile: str
    
    :param cluster: Specify the Qmaster Cluster name
    :type cluster: str
    
    :param priority: Specify the batch priority
    :type priority: str
    
    :param compressorSettingFile: Specify the full path to the compressor setting file
    :type compressorSettingFile: str
    
    :param batchID: Specify the batchID (used for checking batch status)
    :type batchID: str
    
    :param batchName: Specify the batch name to use for submission
    :type batchName: str
    
  '''
  
  ## Init vars
  sourceFile = ''
  destinationFile = ''
  destinationDirectory = ''

  batchID = ''
  cluster = 'FCS Cluster'
  priority = 'low'
  compressorSettingFile = '/Applications/Compressor.app/Contents/Resources/English.lproj/Formats/QuickTime/Uncompressed 8-bit .setting'
  compressorSubmissionTimeout = 600
  localCompressorFallback = True   ## Fall back to 'This Computer' if specified cluster fails.
  transcodeSuffix = '.mov'         ## suffix of format to be transcoded into.
  monitorSleeptime = 30            ## Sleep time between checking transcode status
    
  batchMonitorPath = '/Applications/Utilities/Batch Monitor.app/Contents/MacOS/Batch Monitor'
  compressorPath = '/Applications/Compressor.app/Contents/MacOS/Compressor'

  ## Logging vars
  log = []
  lastError = ""
  lastMSG = ""
  debug = False
  keepFiles = False
  isError = False
  logOffset = 1
  printLogs = False
  printLogDate = True
  printClassInLog = False

  def __init__(self,sourceFile='',destinationFile='',destinationDirectory='',
      cluster='',priority='',compressorSettingFile='',batchID='',batchName=''):
    
    self.batchID = batchID
    self.batchName = batchName
    self.sourceFile = sourceFile
    self.destinationFile = destinationFile
    self.destinationDirectory = destinationDirectory
    if cluster:
      self.cluster = cluster
    else:
      self.cluster = 'This Computer'
    
    self.compressorSettingFile = '/Applications/Compressor.app/Contents/Resources/English.lproj/Formats/QuickTime/Uncompressed 8-bit .setting'
    self.priority = 'low'
    self.compressorSubmissionTimeout = 600
    self.localCompressorFallback = True
    self.monitorSleeptime = 30
    
    if sourceFile:
      self.sourceFile = sourceFile
    if destinationFile:
      self.destinationFile = destinationFile
    if cluster:
      self.cluster = cluster
    if priority:
      self.priority = priority
    if compressorSettingFile:
      self.compressorSettingFile = compressorSettingFile
    if batchID:
      self.batchID = batchID
    if batchName:
      self.batchName = batchName
  
    ## Logging vars
    self.log = []
    self.lastError = ''
    self.lastMSG = ''
    self.debug = False
    self.keepFiles = False
    self.isError = False
    self.logOffset = 1
    self.printLogs = True
    self.printLogDate = True
    self.printClassInLog = False
  
  def submitBatch(self):
    '''Submits the currently provided batch to compressor/qmaster for transcoding
    
    :raises: qmaster.SourceFileError, qmaster.DestinationError, 
      qmaster.QmasterSubmissionError, qmaster.ClusterNotFound, 
      QmasterSubmissionTimeoutError
    
    '''
    
    ## sanity checks:
    if not self.sourceFile:
       raise SourceFileError('No source file was provided!')
      
    if not os.path.isfile(self.sourceFile):
       raise SourceFileError('No source file was present at path: \'%s\'!' % self.sourceFile )
    
    ## If no destination file was provided, check for destination directory,
    ## if it was provided, determine the new filename and suffix
    if not self.destinationFile:
      if self.destinationDirectory:
        baseFileName = os.path.splitext(os.path.basename(self.sourceFile))[0]
        self.destinationFile = os.path.join(self.destinationDirectory,"%s%s" % (baseFileName,self.transcodeSuffix))
      else:
        raise DestinationError('No destination directory or file path has been provided!')
        
    if not self.batchName:
      self.batchName = "%s Transcode" % os.path.basename(self.sourceFile)
    
    self.logger('Submitting job to Compressor - Transcoding file: "%s" to '
      'destination: "%s"' % (self.sourceFile,self.destinationFile),'detailed')
    
    submitCMDString = ('%s -clustername "%s" -batchname "%s" -priority "%s"'
      ' -jobpath \"%s\" -settingpath \"%s\" -destinationpath \"%s\"' %
          (self.compressorPath,self.cluster,self.batchName,
            self.priority,self.sourceFile,self.compressorSettingFile,
            self.destinationFile))
  
    self.logger('Submission syntax: %s' % submitCMDString,'debug')
    
    ## Set our timeout 
    # Set the signal handler and a 5-second alarm
    signal.signal(signal.SIGALRM, self.qmasterTimeoutHandler)
    signal.alarm(self.compressorSubmissionTimeout)
    try:
      submitCMD = subprocess.Popen(submitCMDString,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
      cmd_STDOUT,cmd_STDERR = submitCMD.communicate()

      ## Throw an error if non-zero return code from compressor
      if not submitCMD.returncode == 0:      
        raise QmasterSubmissionError(error=cmd_STDERR,retCode=submitCMD.returncode)
    except QmasterSubmissionTimeoutError:
        ## If we are Python 2.5, use os to kill the process.
        versionInfo = sys.version_info
        if versionInfo[0] == 2 and versionInfo[1] <= 5:
          os.kill(submitCMD.pid, signal.SIGKILL)
        else:
          submitCMD.kill()
        raise QmasterSubmissionTimeoutError()
        
    ## Cancel our timeout
    signal.alarm(0)
    
    if not cmd_STDERR:
      raise QmasterNullDataError()
      
    ## Parse our submission output, fetch our batchID
    try:
      searchResults = re.search('.*<jobID (.*) />.*<batchID (.*) />.*',cmd_STDERR)
      self.batchID = searchResults.groups()[1]
    except:
      ## If batchID couldn't be fetched, check for a submission error
      try:
        searchResults = re.search('.*Submission Error: (.*)',cmd_STDERR)
        errorString = searchResults.groups()[0]
        raise QmasterSubmissionError(error=errorString)
      except:
        ## If submission error string could not be parsed, search for cluster down
        try:
          searchResults = re.search('.*(Could not find cluster "(.*)").*',cmd_STDERR)
          errorString = searchResults.groups()[0]
          
          ## If we aren't submitting to local instance, and local fallback is on
          ## retry with 'This Computer'
          if not self.cluster == 'This Computer' and self.localCompressorFallback:
            self.logger('Could not find cluster: "%s", falling back to '
              '"This Computer"' % self.cluster,'error')
            self.cluster = 'This Computer'
            return self.submitBatch()
          else:
            raise QmasterClusterNotFound(clusterName = self.cluster)
            
        except:
          ## Report a generic error
          raise QmasterSubmissionError(error=('An unknown error occurred '
            'while submitting file: %s! ' % os.path.basename(self.sourceFile)))
      
    return True

  def submitBatchAndWait(self):
    '''This method will submit a running job and will block until the job
    has completed successfully or failed entirely
    
    :raises: qmaster.SourceFileError, qmaster.DestinationError, 
      qmaster.QmasterSubmissionError, qmaster.ClusterNotFound, 
      qmaster.QmasterSubmissionTimeoutError, qmaster.QmasterJobCancelled,
      qmaster.QmasterJobFailed
      
    '''
    
    transcodeDidTimeout = False
    transcodeStatus = 'Processing'
    
    self.submitBatch()
    transcodeStatus = self.getStatus()
    
    while (transcodeStatus == 'Processing' 
    or transcodeStatus == 'Waiting' or transcodeStatus == 'Waiting '
    or transcodeStatus == 'PostProcessing'
    or transcodeStatus == 'Hold'):
      time.sleep(self.monitorSleeptime)
      transcodeStatus = self.getStatus()
      
    if transcodeStatus == 'Cancelled':
      raise QmasterJobCancelled(fileName=os.path.basename(self.sourceFile))
    elif not transcodeStatus == 'Successful':
      raise QmasterJobFailed(status=transcodeStatus,fileName=os.path.basename(self.sourceFile))

  def getStatus(self):
    '''Returns the status of a running job. 
    
    :returns: (*str*) -- The job status
    
    
    =============== =
    Possible Status  
    =============== =
    Processing
    Waiting
    PostProcessing
    Hold
    Cancelled
    Successful
    =============== =
      
    '''
    
    ## Sanity checks
    if not self.batchID:
      raise SyntaxError(error='Could not check status: no batch ID was provided!')
    
    statusCMDString = ('"%s" -clustername "%s" -batchid "%s" -query 0' %
          (self.batchMonitorPath,self.cluster,self.batchID))
          
    self.logger('Checking batch status using syntax: \'%s\'' % statusCMDString,'debug')
    statusCMD = subprocess.Popen(statusCMDString,shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
    cmd_STDOUT,cmd_STDERR = statusCMD.communicate()
    
    ## Batch Monitor returns malformed markup, we have to modify
    ## the closing tag to parse this properly
    data=cmd_STDOUT.replace('/batchStatus','/').replace('/jobStatus','/')
    batchmonitor = batchmonitorParser(data=data)
    
    return batchmonitor.status

  def qmasterTimeoutHandler(signum,frame):
    raise QmasterSubmissionTimeoutError

  def logger(self, logMSG, logLevel='normal'):
    '''(very) Basic Logging Function, we'll probably migrate to msg module'''
    if logLevel == 'error' or logLevel == 'normal' or self.debug:
        i = 0
        headerText = ''
        while i < self.logOffset:
          headerText+='  '
          i+=1
        if logLevel.lower() == 'error':
          headerText = ' ERROR  : %s' % headerText
        elif logLevel.lower() == 'debug':
          headerText = ' DEBUG  : %s' % headerText
        elif logLevel.lower() == 'warning':
          headerText = 'WARNING : %s' % headerText
        elif logLevel.lower() == 'detailed':
          headerText = ' DETAIL : %s' % headerText
        else:
          headerText = ' INFO   : %s' % headerText
        
        if self.printLogDate:
          dateString = datetime.datetime.today().strftime("%b %d %H:%M:%S")
          headerText = "%s: %s" % (dateString,headerText)
        
        if self.printLogs:
          if self.printClassInLog:
            print '%s%s: %s' % (headerText,self.__class__.__name__,logMSG)
          else:
            print '%s%s' % (headerText,logMSG)
            
          sys.stdout.flush()
        self.lastMSG = logMSG
    if logLevel == 'error':
        self.lastError = logMSG
    self.log.append({'logLevel' : logLevel, 'logMSG' : logMSG})
  
  def logs(self,logLevel=''):
    '''Returns an array of logs matching logLevel'''
    
    returnedLogs = []
    logs = self.log
    for log in logs:
      if logLevel and logLevel.lower() == log['logLevel'].lower():
        returnedLogs.append(log)
  
  def lastError(self):
    '''Returns last error'''
    errorLogs = self.logs('error')
    return errorLogs[len(errorLogs)]

  
class SourceFileError(Exception):
  def __init__(self, error):
    self.error = error
  def __str__(self):
    return repr(self.error)

class DestinationError(Exception):
  def __init__(self, error):
    self.error = error
  def __str__(self):
    return repr(self.error)
    
class QmasterClusterNotFound(Exception):
  def __init__(self, clusterName =''):
    self.clusterName = clusterName
  def __str__(self):
    return repr("Could not find cluster: %s" 
      % (self.clusterName))
  
class QmasterSubmissionError(Exception):
  def __init__(self, error,retCode = ''):
    self.error = error
    self.retCode = retCode
  def __str__(self):
    errorString = 'Submission error: %s ' % self.error
    if self.retCode:
      errorString += 'Qmaster exited with non-zero return code: %s' % self.retCode 
    return repr(errorString)

class QmasterJobCancelled(Exception):
  def __init__(self,fileName=''):
    self.fileName = fileName
  def __str__(self):
    if self.fileName:
      return repr('Processing for file: %s was cancelled by user!' % self.fileName)
    else:
      return repr('Processing was cancelled by user!')

class QmasterJobFailed(Exception):
  def __init__(self,fileName='',status=''):
    self.fileName = fileName
    self.status = status
  def __str__(self):
    returnString = 'Job failed '
    if self.fileName:
      returnString += 'for file: %s ' % self.fileName
    if self.status:
      returnString += ' with status: \'%s\' ' % self.status
    return repr(returnString)
    

            
class QmasterSubmissionTimeoutError(Exception):
  pass

class SyntaxError(Exception):
  def __init__(self, error):
    self.error = error
  def __str__(self):
    return repr(self.error)
          
class JobTimeOutError(Exception):
  def __init__(self, error):
    self.error = error
  def __str__(self):
    return repr(self.error)


class batchmonitorParser(HTMLParser.HTMLParser):
  '''HTMLParser subclass to parse batch monitor output
  
  :param data: Provide the data output by batch monitor
  :type data: str
  
  This object will set value for member ``status`` to the parsed status
  upon execution.
  
  '''
  
  status = ''
  debug = False
  
  def __init__(self, data):
    self.status = ''
    self.debug = False
    HTMLParser.HTMLParser.__init__(self)
    
    if self.debug:
      print 'Parsing data: %s' % data
    self.feed(data)
    if self.debug:
      print "Final Status: %s" % self.status
  
  def handle_startendtag(self,tag,attrs):
    if tag == 'batchstatus':
      if self.debug:
        print 'Found batchStatus tag: => %s' % (attrs)
      for key,value in attrs:
        if key == 'status':
          if self.debug:
            print 'Setting new status: \'%s\'' % value
          self.status = value


