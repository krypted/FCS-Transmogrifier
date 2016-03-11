#!/usr/bin/python
# -*- coding: utf-8 -*-

################################
##
##  Transmogrifier: fcsarchiver
##  A Final Cut Server archival integration tool 
##
##  
##  This class provides a generic command line interface for integrating 
##  archival systems with Final Cut Server.
##
#############################################################

import sys,getopt,os.path,shutil,subprocess
import re,datetime,time,tempfile,copy
import sqlite3
import hashlib
import socket
import ConfigParser
import smtplib
import fcsxml


from xml.dom import minidom

version = '1.0b'
build = '2011042001'


class fcsArchiver(fcsxml.FCSBaseObject):
  '''Our primary archive object'''

  supportPath = ''          ## path to the support directory.
  archivePath = ''          ## path to our archive directory
  
  useOffsitePlan = False    ## (bool) value on whether to spool files
                            ## to both an onsite and offsite archivePlan
  trustRestoreChecksumMismatch = False  ## If a file exists on the local archive
                                        ## storage and has been requested for 
                                        ## restore, if the checksum doesn't match
                                        ## our history, do we use the file?
  preventArchiveDuplicates = False      ## If set to true, we won't archive a
                                        ## file which has already been archived
                                        ## provided the checksum matches the 
                                        ## previously archived asset, we will
                                        ## instead simply remove it from disk.

  archiveSetName = ''       ## Name of backup software selection set
  archiveBatchSize = ''      ## Number of files per batch submission.

  archiveQueue = {}         ## A dict of objects to archive, keyed by archiveSet
  restoreQueue = {}         ## A dict of objects to restore, keyed by restoreSet
  
  archivePlan = ''          ## PresStore ArchivePlan
  offsiteArchivePlan = ''   ## PresStore ArchivePlan for our offsite set
  backupSystem = 'PresStore'## Name of the backup system
  nsdchatpath = ''          ## Path to the nsdchat binary
  nsdchatUseSSL = False     ## Whether we use SSL to run nsdchat on a remote host
  nsdchatSSLHost = ''       ## Hostname or IP of the remote host
  nsdchatRemoteUser = ''    ## Remote user of the remote host
  nsdchatUseSudo = False    ## Bool value on whether we wrap nsdchat with a sudo call
    
  SMTPServer = ''            ## Hostname or IP of our email relay
  SMTPPort = 25
  SMTPUser = ''              ## (optional) SMTP user for authenticated relay
  SMTPPassword = ''          ## (optional) SMTP password for authenticated relay
  emailToNotify = ''        ## Email address to use for notifications
  emailFromAddress = ''      ## From email address
  
  configParser = ''
      
  statusMap =  {  'archive' : { 'queued' : 'archiveQueued', 
                                  'submitted' : 'archiveSubmitted',
                                  'started' : 'archiveRunning',
                                  'pending':'archiveRunning',
                                  'running':'archiveRunning',
                                  'cancelled':'archiveCancelled',
                                  'died':'archiveDied',
                                  'archiveDied':'archiveDied',
                                  'terminated':'archiveDied',
                                  'completed':'archiveCompleted',
                                  'failed':'archiveFailed',
                                  'fatal':'fatalError'
                              },
                          'offsiteArchive' : { 'queued' : 'offsiteQueued', 
                                  'submitted' : 'offsiteSubmitted',
                                  'started' : 'offsiteRunning',
                                  'pending':'offsiteRunning',
                                  'running':'offsiteRunning',
                                  'cancelled':'offsiteCancelled',
                                  'died':'offsiteDied',
                                  'archiveDied':'offsiteDied',
                                  'terminated':'offsiteDied',
                                  'completed':'offsiteCompleted',
                                  'failed':'offsiteFailed',
                                  'fatal':'fatalError'
                              },
                          'restore' : { 'queued' : 'restoreQueued', 
                                'submitted':'restoreSubmitted',
                                'pending':'restoreRunning',
                                'running':'restoreRunning',
                                'started':'restoreRunning',
                                'cancelled':'restoreCancelled',
                                'died':'restoreDied',
                                'archiveDied':'restoreDied',
                                'terminated':'restoreDied',
                                'completed':'restoreCompleted',
                                'failed':'restoreFailed',
                                'fatal':'fatalError'
                              }
                }  
  def __init__(self):
    '''Initialize members'''
    
    self.supportPath = ''
    self.archiveSetName = 'SELECTION_%s' % datetime.datetime.today().strftime('%Y-%m-%d:%H%M')
    self.archiveBatchSize = 100
    self.archivePath = ''
    self.archiveQueue = {}
    self.restoreQueue = {}
    self.configParser = ''

    self.backupSystemName = 'PresStore'
    self.nsdchatpath = '/usr/local/aw/bin/nsdchat'
    self.nsdchatSSLHost = ''
    self.nsdchatRemoteUser = ''
    
    self.archivePlan = '10001'    
    self.offsiteArchivePlan = '10001'   
    self.useOffsitePlan = False
    self.trustRestoreChecksumMismatch = False
    self.preventArchiveDuplicates = False
    
    self.SMTPServer = ''
    self.SMTPPort = 25
    self.SMTPUser = ''
    self.SMTPPassword = ''
    self.emailToNotify = ''
    self.debug = False
    self.printLogs = True
    

  
  def loadConfiguration(self,parser='',filePath=''):
    '''Load from configuration file, expects a ConfigParser type object. If 
    you subclass, you should call this function.'''
    
    if parser and not isinstance(parser,ConfigParser.ConfigParser):
      msg = 'loadConfiguration() Not passed a valid ConfigParser Object!'
      self.logger(msg, 'error')
      raise RuntimeError(msg)
    elif not parser:
      if not filePath:
        filePath = '/usr/local/etc/fcsArchiver.conf'
      parser = ConfigParser.SafeConfigParser()
      parser.read(filePath)
        
      
    ## Store our parser object
    self.configParser = parser
    
    try:
      self.configParser = parser
      self.debug = parser.getboolean('GLOBAL','debug') 
      try:
        self.supportPath = parser.get('GLOBAL','supportPath')
      except:
        pass
      try:
        self.archivePath = parser.get('GLOBAL','archivePath')
      except:
        pass
      try:
        self.useOffsitePlan = parser.getboolean('BACKUP','useOffsitePlan')
      except:
        pass
      try:
        self.archivePlan = parser.get('BACKUP','archivePlan')
      except:
        pass
      try:
        self.offsiteArchivePlan = parser.get('BACKUP','offsiteArchivePlan')
      except:
        pass
      try:
        self.backupSystem = parser.get('BACKUP','backupSystem')
      except:
        pass
      try:
        self.nsdchatpath = parser.get('BACKUP','nsdchatpath')
      except:
        pass
      try:
        self.trustRestoreChecksumMismatch = parser.getboolean('BACKUP','trustRestoreChecksumMismatch')
      except:
        pass
      try:
        self.preventArchiveDuplicates = parser.getboolean('BACKUP','preventArchiveDuplicates')
      except:
        pass
      try:
        self.nsdchatUseSSL = parser.getboolean('BACKUP','nsdchatUseSSL')
        if self.nsdchatUseSSL:
          try:
            self.nsdchatSSLHost = parser.get('BACKUP','remoteSSLHost')
            self.nsdchatRemoteUser = parser.get('BACKUP','remoteSSLUserName')
          except:
            self.logger('Error loading configuration, nsdchatUseSSL is enabled but remoteSSLHost or remoteSSLUserName is not defined!','error')
            raise RuntimeError('Error loading configuration, nsdchatUseSSL is enabled but remoteSSLHost or remoteSSLUserName is not defined!')
      except:
        pass
      try:
        self.SMTPServer = parser.get('NOTIFICATIONS','SMTPServer')
        self.emailToNotify = parser.get('NOTIFICATIONS','emailToNotify')
        self.emailFromAddress = parser.get('NOTIFICATIONS','emailFromAddress')
      except:
        pass
      try:
        self.SMTPPort = parser.get('NOTIFICATIONS','SMTPPort')
      except:
        pass
      try:
        SMTPUser = parser.get('NOTIFICATIONS','SMTPUser')
        SMTPPassword = parser.get('NOTIFICATIONS','SMTPPassword')
        if SMTPUser and SMTPPassword:
          self.SMTPUser = SMTPUser
          self.SMTPPassword = SMTPPassword
      except:
        pass

    except Exception,msg:
      self.logger('An error occured loading configuration:%s' % msg,'error')
      raise
    

  def connectToSQL(self):
    '''Open a connection to sqlite db and save the connection at self.sqlConn'''
    sqlConn = ''
    if not self.supportPath:
      self.logger('Support path not set, using PWD: %s!' % os.getcwd(),'warning')
      
    dbPath = os.path.join(self.supportPath,'backupHistory.db')
    self.logger('connectToSQL() using DBPath:%s' % dbPath,'debug')
    
    if dbPath and not os.path.exists(dbPath):
      if os.path.exists(os.path.dirname(dbPath)):
        self.logger('Creating SQL database at path:\'%s\'' % dbPath,'detailed')
        try:
          sqlConn = sqlite3.connect(dbPath)
          sqlConn.row_factory = sqlite3.Row
          myCursor = sqlConn.cursor()
          myCursor.execute('CREATE TABLE archiveHistory(fcsID,'
            'filePath,checksum,barcode,tapeSet,archiveSet,jobID,completionDate,status)')
          myCursor.execute('CREATE TABLE archiveQueue(fcsID,filePath,checksum,'
            'archiveSet,tapeSet,jobID,jobSubmitDate,retryCount,status)')
          myCursor.execute('CREATE TABLE restoreQueue(fcsID,filePath,'
            'archiveSet,tapeSet,barcode,jobID,jobSubmitDate,retryCount,status)')
          sqlConn.commit()
          myCursor.close()
        except Exception,err:
          self.logger('An error occured creating sqlite db at path: %s'
            ' Error:%s' % (dbPath,err),'error')
          raise
    else:
      try:
        sqlConn = sqlite3.connect(dbPath)
        sqlConn.row_factory = sqlite3.Row
      except Exception, err:
        self.logger('An error occured opening sqlitedb at: %s Error:%s' % (dbPath,err))
        raise
        
    return sqlConn
    
  #############
  ## archiveQueue methods
    
  def archiveFilesFromQueue(self):
    '''Submit loaded objects in our Queue for archive'''
    
    if not len(self.archiveQueue) > 0:
      raise FCSArchiveEmptyQueueError
    
    self.logger('Submitting files in Archive Queue.')
    
    ## Get our path to nsdchat
    nsdchatCMD = self.nsdchatCMD()
    archivePlan = self.archivePlan
    
    ## Get our archiveQueue
    archiveQueue = self.archiveQueue
    
    ## Fetch our archive sets with status 'archiveQueued'
    archiveSets = self.archiveSetsWithStatus(status='archiveQueued')
    if self.useOffsitePlan:
      self.logger('archiveFilesFromQueue() looking for offsite queues','debug')
      archiveSets.update(self.archiveSetsWithStatus(status='offsiteQueued'))
    else:
      self.logger('archiveFilesFromQueue() we are not using an offsite queue!','debug')
    
    ## If we have no found archive sets, abort.
    if len(archiveSets) == 0:
      self.logger('Found no files to archive.')
      return False
    
    ## Set up some vars for reporting
    numSetsSubmitted = 0
    numFilesSubmitted = 0
    numFileErrors = 0
    setSubmissionErrors = {}
    fileSubmissionErrors = {}
    
    ## Iterate through our archive sets and create appropriate PresStorePlans
    for setName,set in archiveSets.iteritems():
      ## Submit a new PresStore job for the set. 
      self.logger('Committing set \'%s\' for archive to tapeset \'%s\'. Set '
          'contains %s files.' % (setName,set.getTapeSet(),len(set.archiveObjects)))
      self.logOffset +=1
      jobID = self.nsdchatSubmitArchiveJobForArchiveSet(archiveSet=set)
      self.logOffset -=1

      if not jobID:
        msg = 'An error occurred submitting set:%s to PresStore' % setName
        self.logger(msg,'error')
        setSubmissionErrors[setName] = set
        continue

      numSetsSubmitted += 1
      numFileErrors += len(set.errorObjects)
      numFilesSubmitted += (len(set.archiveObjects) - len(set.errorObjects))
        
      
      ## Update the status for our archive queue
      set.setArchiveSetForArchiveObjects(setName=set.name)
      set.setStatusForArchiveObjects(status='archiveSubmitted')
      set.setJobIDForArchiveObjects(jobID=jobID)

      ## Commit our archiveObjects to FCS and SQL
      self.commitArchiveObjectsInArchiveSet(set)
    
    ## Done iterating through sets.
    
    ## Report how we did 
    self.logger('Finished processing archiveQueue. Successfully submitted %s files accross %s set(s)'
                  % (numFilesSubmitted,numSetsSubmitted))
    
    ## If we have errors report failings
    if not len(setSubmissionErrors) == 0 or not len(fileSubmissionErrors) == 0:
      self.logger('Failed to submit %s sets and %s files!' % (len(setSubmissionErrors),numFileErrors),'error') 
      return False

    return True
  
  def createArchiveQueueFromFile(self,queueFile=''):
    '''Reads file from path queueFile, which should be a line delimited list
    of file paths. We check the filePath against loaded values in our SQL
    archiveQueue table, merging where appropriate. We also check against our
    archiveHistory table to ensure that the asset hasn't already been archived.
    
    .. warning:
      If ``fcsArchiver.py`` is terminated while this method is running,
      any unprocessed entries present in the queue file will be lost.
    
    '''
    if not queueFile:
      queueFile = os.path.join(self.supportPath,'filesToArchive')
    
    if not os.path.exists(queueFile):  
      self.logger('The archive queue is empty, file:\'%s\' does not exist!' 
        % queueFile,'debug')
      return False
    
    ## Build our current queuelist
    failedFilePaths = []
    
    ## Create a random directory, move our queue file into it.
    randomDir = tempfile.mkdtemp(dir='/tmp',prefix='fcsArchive_')
    shutil.move(queueFile,randomDir)
    queueFile = os.path.join(randomDir,'filesToArchive')
    
    myFileH = open(queueFile,'r')
    filePaths = []
    for filePath in myFileH:
      filePath = filePath.rstrip('\r\n')
      filePaths.append(filePath)
    
    ## Close and remove the file
    myFileH.close()
    try:
      shutil.rmtree(randomDir)
    except:
      pass
      
    for filePath in filePaths:
      self.logger("Found new file: '%s'" % filePath)
      self.logOffset += 1
      try:
        archiveObject = self.createArchiveObjectFromFilePath(filePath)
        self.addToArchiveQueue(archiveObject)
      except fcsxml.FCSEntityNotFoundError, err:
        self.logger('%s, skipping!' % eval(err.__str__()),'error')
      except Exception,err:
        failedFilePaths.append(filePath)
        self.logger('Failed adding file at path:\'%s\' Error: %s' % (filePath,err),'error')
        raise
        self.logOffset -= 1
        continue
        #raise FCSArchiveFileSubmitError('Failed adding file at path:%s' % filePath)
      
      self.logOffset -= 1

    if len(filePaths) == 0:
      return False
    else:
      return True
     
  def addToArchiveQueue(self,archiveObject):
    '''Adds the specified archiveObject to the archive queue. We 
    retrieve FCS data via fcsxml.FCSVRClient calls. For XML based workflows, utilize
    addFileFromXMLPath'''
    
    self.logger('addToArchiveQueue() Hit! for file: %s' % archiveObject.filePath,'debug')
    
    self.logger('Adding file to archive queue.','detailed')

    self.logger('Searching archive history for previous activity.')
    
    ## Init our SQL handlers  
    try:
      sqlConn = self.connectToSQL()
      sqlConn.row_factory = sqlite3.Row
      myCursor = sqlConn.cursor()
    except:
      self.logger('An error occured connecting to SQL database.')
      return False
      
    filePath = archiveObject.filePath
    
    ## Search for an existing record with the same filepath, if it has a 
    ## different checksum or fcsID, update it. Set status to 'archiveQueued'
    args = (filePath,)
    myCursor.execute('SELECT * FROM archiveQueue WHERE filePath = ?', args)
    isDuplicate = False
    onsiteDuplicate = False
    offsiteDuplicate = False
    isConflict = True
    alreadyArchived = False
    
    row = myCursor.fetchone()
    if row:
      ## If we are Python 2.5, convert our row to a dict
      versionInfo = sys.version_info
      if versionInfo[0] == 2 and versionInfo[1] == 5:
        myRow = self.createDictFromSQLRow(row,table='archiveQueue')
      else:
        myRow = row
        
      if (myRow['checksum'] != archiveObject.checksum 
        or myRow['fcsID'] != archiveObject.fcsID):
          self.logger("Conflicting Filepath:'%s' exists in archiveQueue but has conflicting information, updating!" % filePath)
      else:
        isDuplicate = True
        self.logger("Filepath:'%s' exists in archiveQueue!" % filePath)
      
    ## Note: If the filepath isn't already queued up, check the archiveHistory to
    ## ensure that it hasn't already been archived.
    myCursor.execute("SELECT * FROM archiveHistory WHERE filePath = ? and (status = 'archiveCompleted' or status = 'offsiteCompleted')", args)
    for row in myCursor:
      ## If we are Python 2.5, convert our row to a dict
      versionInfo = sys.version_info
      if versionInfo[0] == 2 and versionInfo[1] == 5:
        myRow = self.createDictFromSQLRow(row,table='archiveQueue')
      else:
        myRow = row
      if (myRow["checksum"] and myRow["checksum"] == archiveObject.checksum and myRow["fcsID"] == archiveObject.fcsID):
        if myRow['tapeSet'] == 'onsite':
          ## If our history reports a previous onsite backup, verify through 
          ## PresStore that the filepath has in fact been backed up.
          try:
            onsiteBarcode = self.barcodeForArchiveObject(archiveObject=archiveObject,tapeSet='onsite')
            if onsiteBarcode:
              if self.preventArchiveDuplicates:
                self.logger("An identical version of file '%s' has already been"
                  " archived to %s tapeset, skipping." 
                  % (os.path.basename(filePath),myRow['tapeSet']))
              else:
                self.logger("An identical version of file '%s' has already been"
                  " archived to the %s tapeset, but preventArchiveDuplicates is set"
                  " to False, re-archiving!" % filePath)              
              onsiteDuplicate = True
            else:
              self.logger("Archive history reports an identical version of "
                " file '%s' has already been archived to the %s tapeset,"
                " however a tape barcode could not be provided by %s, so we are "
                " resubmitting." % (os.path.basename(filePath),myRow['tapeSet']
                ,self.backupSystem),'warning')
          except:
            self.logger('File: "%s" has not been cataloged in %s index, though our history indicates that it has!'
              % (filePath,myRow['tapeSet']),'error')
            
        if myRow['tapeSet'] == 'offsite' and self.useOffsitePlan:
          ## If our history reports a previous onsite backup, verify through 
          ## PresStore that the filepath has in fact been backed up.
          try:
            offsiteBarcode = self.barcodeForArchiveObject(archiveObject=archiveObject,tapeSet='offsite')
            if offsiteBarcode:
              offsiteDuplicate = True
              if self.preventArchiveDuplicates:
                self.logger("An identical version of file '%s' has already been"
                  " archived to %s tapeset, skipping." 
                  % (os.path.basename(filePath),myRow['tapeSet']))
              else:
                self.logger("An identical version of file '%s' has already been "
                  "archived to the %s tapeset, but preventArchiveDuplicates is set "
                  "to False, re-archiving!" % filePath)              
              onsiteDuplicate = True
            else:
              self.logger("Archive history reports an identical version of "
                " file '%s' has already been archived to the %s tapeset,"
                " however a tape barcode could not be provided by %s, so we are "
                " resubmitting." % (os.path.basename(filePath),myRow['tapeSet']
                ,self.backupSystem),'warning')
          except:
            self.logger('File: "%s" has not been cataloged in %s index, though our history indicates that it has!'
                % (filePath,myRow['tapeSet']),'error')
      else:
        pass
    
    ## If we detected an onsite backup, but not an offsite, change status to offsite
    if self.useOffsitePlan:
      if onsiteDuplicate and not offsiteDuplicate:
        archiveObject.setTapeSet('offsite')
        archiveObject.status = 'offsiteQueued'
        isDuplicate = False
      if onsiteDuplicate and offsiteDuplicate:
        isDuplicate = True
        alreadyArchived = True
    elif onsiteDuplicate:
      isDuplicate = True
      alreadyArchived = True
    
    ## If we're here and haven't detected a duplicate, add the file to the
    ## Queue.
    if ((alreadyArchived and not self.preventArchiveDuplicates) 
    or (not isDuplicate and not alreadyArchived)):
      ## If no status has been set, change it to archiveQueued
      if not archiveObject.status:
        archiveObject.status = 'archiveQueued'
      if  archiveObject.isLoaded:
        sqlVars = (archiveObject.fcsID,
            archiveObject.filePath,
            archiveObject.checksum,
            archiveObject.tapeSet,
            archiveObject.retryCount,
            archiveObject.status,
        )
        self.logger("Adding filePath:'%s' to archiveQueue" % filePath)
        myCursor.execute("INSERT INTO archiveQueue (fcsID,filePath,checksum,tapeSet,retryCount,status) VALUES (?,?,?,?,?,?)", sqlVars)
      elif not archiveObject.isLoaded and archiveObject.filePath:
        sqlVars = (archiveObject.fcsID,
            archiveObject.filePath,
            archiveObject.checksum,
            archiveObject.tapeSet,
            archiveObject.retryCount,
            archiveObject.status,
        )
        self.logger("Failed to load FCSObject for filePath:'%s', submitting to archiveQueue" % filePath)
        myCursor.execute("INSERT INTO archiveQueue (fcsID,filePath,checksum,tapeSet,retryCount,status) VALUES (?,?,?,?,?,?)", sqlVars)
    
      commitResult = sqlConn.commit()
      
      ## Set our archiveSetName
      archiveSetName = self.archiveSetName
      
      ## Fetch our current archiveSet
      if not archiveSetName in self.archiveQueue:
        myArchiveSet = archiveSet(name=archiveSetName,type='archive',jobID=archiveSet.jobID)
        if self.debug:
          archiveSet.debug = True
        self.archiveQueue[archiveSetName] = myArchiveSet
      else:
        ## If the archive set already exists, make sure it doesn't have more
        ## files then our archiveBatchSize specifies, if so, create a new 
        ## archive set.
        myArchiveSet = self.archiveQueue[archiveSetName]
        currentSetCount = 1
        archiveSetBaseName = archiveSetName
        while len(myArchiveSet.archiveObjects) >= self.archiveBatchSize:
          newArchiveSetName = '%s.batch%03d' % (archiveSetBaseName,currentSetCount)
          self.logger('addToArchiveQueue() Archive set: %s contains %s, which '
            'is our preferred batch size, checking batch: %s' % 
            (archiveSetName,len(myArchiveSet.archiveObjects),newArchiveSetName),'debug')
          archiveSetName = newArchiveSetName
          if not archiveSetName in self.archiveQueue:
            myArchiveSet = archiveSet(name=archiveSetName,type='archive',jobID=archiveSet.jobID)
            if self.debug:
              myArchiveSet.debug = True
            self.archiveQueue[archiveSetName] = myArchiveSet
          currentSetCount += 1
      
      
      ## Append our archive object to our current set.
      myArchiveSet.archiveObjects.append(archiveObject)
    
    elif isDuplicate:
      if alreadyArchived and self.preventArchiveDuplicates:
        archiveObject.statusMessage = 'File has already been archived, removing '
        'from local archive storage!'
        ## Here if the file has already been archived. If this is the case,
        ## Remove the file from the filesystem.
        if os.path.exists(archiveObject.filePath):
          self.logger('File at path:%s has already been archived, removing from ' 
                        'local archive storage!' % archiveObject.filePath)
          os.remove(archiveObject.filePath)
        if self.useOffsitePlan:
          archiveObject.status = 'offsiteCompleted'
        else:
          archiveObject.status = 'onsiteCompleted'
      elif alreadyArchived:
        self.logger('File at path: %s has already been archived, but will not '
          ' be removed from disk.' % archiveObject.filePath,'error')
      else:
        ## Here if file is already in the queue but hasn't been archived.
        self.logger('File at path:%s already exists in archive queue, skipping'
          % archiveObject.filePath)
      return False
    
      
    return True

  def loadArchiveQueue(self):
    '''Function which reads our sqlite database and generates archiveSet objects
    for queued files'''
    
    ## Load our SQL connection
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    archiveQueue = {}
    
    ## Query for all entries in our archiveQueue
    sqlQuery = 'SELECT rowid,* FROM archiveQueue'
    self.logger('loadArchiveQueue() executing with query: %s'%sqlQuery,'debug')
    myCursor.execute(sqlQuery)
    isDuplicate = False
    isConflict = True
    myResults = myCursor.fetchall()
    for row in myResults:
      ## If we are Python 2.5, convert our row to a dict
      versionInfo = sys.version_info
      if versionInfo[0] == 2 and versionInfo[1] == 5:
        myRow = self.createDictFromSQLRow(row,table='archiveQueue')
      else:
        myRow = row
      ##self.logger('loadArchiveQueue() result row keys:%s rowID:%s' % (myRow.keys(),myRow['rowid']),'debug')
      
      ## Get our archiveSetName
      archiveSetName = myRow['archiveSet']
      if not archiveSetName:
        archiveSetName = self.archiveSetName
      archiveSetJobID = myRow['jobID']
      
      ## Fetch our current archiveSet
      if not archiveSetName in archiveQueue:
        myArchiveSet = archiveSet(name=archiveSetName,type='archive',jobID=archiveSetJobID)
        if self.debug:
          myArchiveSet.debug = True
        archiveQueue[archiveSetName] = myArchiveSet
      else: 
        ## If the archive set already exists, make sure it doesn't have more
        ## files then our archiveBatchSize specifies, if so, create a new 
        ## archive set.
        myArchiveSet = archiveQueue[archiveSetName]
        '''
        currentSetCount = 1
        archiveSetBaseName = archiveSetName
        while len(myArchiveSet.archiveObjects) >= self.archiveBatchSize:
          newArchiveSetName = '%s.batch%03d' % (archiveSetBaseName,currentSetCount)
          self.logger('loadArchiveQueue() Archive set: %s contains %s files, '
            'which is our preferred batch size, checking batch: %s' 
            % (archiveSetName,len(myArchiveSet.archiveObjects),newArchiveSetName),'debug')
          archiveSetName = newArchiveSetName
          if not archiveSetName in self.archiveQueue:
            myArchiveSet = archiveSet(name=archiveSetName,type='archive',jobID=archiveSet.jobID)
            if self.debug:
              myArchiveSet.debug = True
            self.archiveQueue[archiveSetName] = myArchiveSet
          else:
            myArchiveSet = self.archiveQueue[archiveSetName]
          currentSetCount += 1
        '''
      
      ## Create our archive object from our SQL result and append it to our current set
      myArchiveObject = archiveObject(action='archive')
      myArchiveObject.loadFromSQLResult(myRow)
      self.logger('loadArchiveQueue() Adding file to archive batch: %s. Current file count: %s of %s'
        % (archiveSetName,len(myArchiveSet.archiveObjects),self.archiveBatchSize),'debug')
      myArchiveSet.archiveObjects.append(myArchiveObject)
      
    ## self.archiveQueue.update(archiveQueue)
    self.archiveQueue = archiveQueue
        
    return
  
  def commitArchiveObjectsInArchiveSet(self,archiveSet):
    '''Commits each archiveObject in the provided archiveSet both to the SQL
    DB as well as FCS'''
        
    self.logger('Updating files from set: %s in FCS and Archive DataBase' % archiveSet.name)
    self.logger('commitArchiveObjectsInArchiveSet() committing record for objects in archiveSet:%s' 
      % archiveSet,'debug')

    ## Iterate through each object
    for archiveObject in archiveSet.archiveObjects:
      ## If the object doesn't show an error, set our archiveSet.
      if not archiveObject.isError:
        archiveObject.archiveSetName = archiveSet.name
        archiveObject.submitDate = datetime.datetime.today()

      else:
        self.logger('commitArchiveObjectsInArchiveSet() archiveObject with fcsID:%s'
            ' reports an error: %s' % (archiveObject.fcsID,archiveObject.statusMessage))

      self.commitArchiveObject(archiveObject)
      try:
        self.commitArchiveObjectToFCS(archiveObject)
      except Exception,excp:
        self.logger('An error occured commiting FCS Asset with ID: %s, ERROR: %s' 
          % archiveObject.fcsID,excp,'error')
    return True

  def commitArchiveObject(self,archiveObject,sqlConn=None):
    '''Commits the passed archiveObject to our archiveQueue'''
    
    ## Connect to SQL if we weren't provided an sqlConn 
    if sqlConn == None:
      sqlConn = self.connectToSQL()
      sqlConn.row_factory = sqlite3.Row
      
    myCursor = sqlConn.cursor()
    
    if archiveObject.action == 'archive' or archiveObject.action == 'offsiteArchive':
      self.logger('commitArchiveObject() committing record with id:%s' % archiveObject.recordID,'debug')
      dbValues = (archiveObject.fcsID,
          archiveObject.filePath,
          archiveObject.checksum,
          archiveObject.archiveSetName,
          archiveObject.jobID,
          archiveObject.tapeSet,
          archiveObject.submitDate,
          archiveObject.status,
          archiveObject.retryCount,
          archiveObject.recordID,
        )
      
      ## Execute our SQL Query
      myCursor.execute('UPDATE archiveQueue set fcsID = ?,filePath = ?,'
        'checksum = ?,archiveSet = ?,jobID = ?,tapeSet = ?, jobSubmitDate = ?,status = ?,'
        'retryCount = ? WHERE rowid = ?', dbValues)
    elif archiveObject.action == 'restore':
      self.logger('commitArchiveObject() committing record with id:%s' % archiveObject.recordID,'debug')
      dbValues = (archiveObject.fcsID,
          archiveObject.filePath,
          archiveObject.archiveSetName,
          archiveObject.tapeSet,
          archiveObject.barcode,
          archiveObject.jobID,
          archiveObject.submitDate,
          archiveObject.retryCount,
          archiveObject.status,
          archiveObject.recordID,
        )
      
      ## Execute our SQL Query
      myCursor.execute('UPDATE restoreQueue set fcsID = ?,filePath = ?,'
        'archiveSet = ?,tapeSet = ?,barcode = ?,jobID = ?,jobSubmitDate = ?,'
        'retryCount = ?,status = ? WHERE rowid = ?', dbValues)
        
    commitResult = sqlConn.commit()
    return True

  def commitArchiveObjectToFCS(self,archiveObject):
    '''Reports archive object to FCS'''
    
    ## Get our FCS ID
    fcsID = archiveObject.fcsID
    
    ## Create our fcsxml.FCSVRClient object and load our config
    if not archiveObject.fcsObject:
      try:
        archiveObject.loadFCSObject()
      except:
        self.logger("Could not commit file: %s to FCS, object could not be"
          " loaded!" % archiveObject.filePath,'error')
        return False
        
    fcsObj = archiveObject.fcsObject
        
    ## Get our tapeset
    tapeSet = archiveObject.tapeSet
        
    ## Get our barcode, if set, report it to FCS
    barcode = archiveObject.barcode
    if barcode:
      if tapeSet == 'offsite':
        barcodeField = fcsxml.FCSXMLField(name='Tape Barcode - Offsite',value=barcode)
      else:
        barcodeField = fcsxml.FCSXMLField(name='Tape Barcode',value=barcode)
      fcsObj.appendField(barcodeField)

    ## Declare our statusMap, which is a dictionary mapping FCSArchiver statuses
    ## to FCS statuses.
    statusMap = {  'archiveQueued' : {'fcsState' : 'ondisk',
                                    'statusMessage' : 'Asset has been queued for archive.' 
                                  },
                  'restoreQueued'  : {'fcsState' : 'ontape',
                                    'statusMessage' : 'Asset is queued for restore. %s' % archiveObject.statusMessage 
                                  },
                  'offsiteQueued' : {'fcsState' : 'ondiskandtape',
                                    'statusMessage' : 'Asset has been queued for offsite archive.' 
                                  },
                  'archiveSubmitted' : {'fcsState' : 'ondisk',
                                    'statusMessage' : 'Asset has been submitted to %s for archive.' % self.backupSystem 
                                  },
                  'offsiteSubmitted' : {'fcsState' : 'ondiskandtape',
                                    'statusMessage' : 'Asset has been submitted '
                                    ' to %s for offsite archive.' % self.backupSystem
                                  },
                  'restoreSubmitted'  : {'fcsState' : 'ontape',
                                    'statusMessage' : ('Asset has been submitted '
                                      'to %s for restore using tape: %s.' 
                                      % (self.backupSystem,archiveObject.barcode))
                                  },
                  'archiveRunning' : {'fcsState' : 'ondisk',
                                    'statusMessage' : '%s reports that the archive is in progress.' % self.backupSystem
                                  },                                  
                  'offsiteRunning' : {'fcsState' : 'ondiskandtape',
                                    'statusMessage' : '%s reports that the offsite archive is in progress.' % self.backupSystem
                                  },
                  'restoreRunning'  : {'fcsState' : 'ontape',
                                    'statusMessage' : '%s reports that the restore is in progress.' % self.backupSystem
                                  },
                  'archiveDied' : {'fcsState' : 'ondisk',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage
                                  },
                   
                  'offsiteDied' : {'fcsState' : 'ondiskandtape',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage
                                  },  
                  'restoreDied'  : {'fcsState' : 'ontape',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage 
                                  }, 
                  'archiveFailed' : {'fcsState' : 'ondisk',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage
                                  },  
                  'offsiteFailed' : {'fcsState' : 'ondiskandtape',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage
                                  },  
                  'restoreFailed'  : {'fcsState' : 'ontape',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage 
                                  }, 
                  'archiveCancelled' : {'fcsState' : 'ondisk',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage
                                  },  
                  'offsiteCancelled' : {'fcsState' : 'ondiskandtape',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage
                                  },  
                  'restoreCancelled'  : {'fcsState' : 'ontape',
                                    'statusMessage' : 'Error: %s' % archiveObject.statusMessage 
                                  },
                  'archiveCompleted' : {'fcsState' : 'ontape',
                                    'statusMessage' : 'Asset successfully archived to tape: %s!' % archiveObject.barcode
                                  },  
                  'offsiteCompleted' : {'fcsState' : 'ontapeandoffsite',
                                    'statusMessage' : ('Asset successfully archived to offsite tape: %s! Asset will'
                                                        ' be removed from disk by %s!' % (archiveObject.barcode,self.backupSystem))
                                  },
                  'restoreCompleted'  : {'fcsState' : 'ondisk',
                                    'statusMessage' : 'Asset successfully restored to disk.'
                                  },
                  }
    ## Get our state from our status and statusMap
    status = archiveObject.status
    fcsState = statusMap[status]['fcsState']
    fcsMessage = statusMap[status]['statusMessage']
    
    ## Little bit of logic
    if status == 'archiveCompleted':
      if self.useOffsitePlan:
        fcsMessage += ' Starting offsite archive...'
      else:
        fcsMessage += ' Asset will be removed from disk by %s!' % self.backupSystem
    elif status == 'restoreCompleted':
      if archiveObject.statusMessage:
        fcsMessage += "  " + archiveObject.statusMessage
    
    ## Add our state field
    stateField = fcsxml.FCSXMLField(name='Archive State',value=fcsState)
    fcsObj.appendField(stateField)
    
    ## Append our message
    fcsObj.appendValueForField('Archive History',value=fcsMessage,useTimestamp=True)
  
    fcsObj.setMD()
    
    ## If the status is 'restoreCompleted', tell the restore object to restore 
    ## in FCS. This will ensure that the asset is properly restored even if the 
    ## actual restore from tape takes too long and the FCS restore job times out.
    if status == 'restoreCompleted' and archiveObject.didRestore:
      self.logger('Restoring asset in Final Cut Server')
      try:
        fcsObj.restore()
      except fcsxml.FCSDuplicateError, ex:
        self.logger('Restore action failed, asset is already online.','detailed')
      except Exception, ex:
        self.logger('An error occurred restoring the asset! Error: %s:%s' 
          % (ex.__class__.__name__,ex),'error')
    
    return
    
    ''' OLD CODE
    ## Get our status, and determine our state based on it
    status = archiveObject.status
    if archiveObject.status == 'archiveQueued':
      fcsState = 'queuedforarchive'
      fcsMessage = 'Asset has been queued for archive.'
    elif archiveObject.status == 'offsiteQueued':
      fcsState = 'queuedforoffsite'
      fcsMessage = 'Asset has been queued for offsite archive.'
    elif archiveObject.status == 'archiveSubmitted':
      fcsState = 'queuedforarchive'
      fcsMessage = 'Asset has been submitted to %s.' % self.backupSystem
    elif archiveObject.status == 'offsiteSubmitted':
      fcsState = 'queuedforoffsite'
      fcsMessage = 'Asset has been queued for offsite archive.'
    elif archiveObject.status == 'archiveRunning':
      fcsState = 'archiveinprogress'
      fcsMessage = 'Archive in progress.'
    elif archiveObject.status == 'offsiteRunning':
      fcsState = 'offsiteinprogress'
      fcsMessage = 'Offsite Archive in progress.'
    elif archiveObject.status == 'archiveDied':
      fcsState = 'ondisk'
      fcsMessage = 'Error: %s' % archiveObject.statusMessage
    elif archiveObject.status == 'offsiteDied':
      fcsState = 'ondiskandtape'
      fcsMessage = 'Error: %s' % archiveObject.statusMessage
    elif archiveObject.status == 'archiveFailed':        
      fcsState = 'ondisk'
      fcsMessage = 'Error: %s' % archiveObject.statusMessage
    elif archiveObject.status == 'offsiteFailed':
      fcsState = 'ondiskandtape'
      fcsMessage = 'Error: %s' % archiveObject.statusMessage
    elif archiveObject.status == 'archiveCancelled':
      fcsState = 'ondisk'
      fcsMessage = 'Error: %s' % archiveObject.statusMessage
    elif archiveObject.status == 'offsiteCancelled':
      fcsState = 'ondiskandtape'
      fcsMessage = 'Error: %s' % archiveObject.statusMessage
    elif archiveObject.status == 'archiveCompleted':
      fcsState = 'ontape'
      fcsMessage = 'Asset successfully archived!'
      if self.useOffsitePlan:
        fcsMessage += ' Starting offsite archive...'
    elif archiveObject.status == 'offsiteCompleted':
      fcsState = 'ontapeandoffsite'
      fcsMessage = ('Asset successfully archived to offsite tape set! Asset will'
        ' be removed from disk by %s!' % self.backupSystem)
    '''
    
 
    
    


  def commitArchiveObjectToArchiveHistory(self,archiveObject):
    '''Commits an archive object to our archiveHistory SQL table'''
    self.logger('commitArchiveObjectToArchiveHistory() committing record '
      ' with path:%s' % archiveObject.filePath,'debug')
    if archiveObject.action == 'restore':   
      completionDate = archiveObject.restoreDate
    else:
       completionDate = archiveObject.archiveDate
    
    ## Build our values array
    dbValues = (archiveObject.fcsID,
        archiveObject.filePath,
        archiveObject.checksum,
        archiveObject.barcode,
        archiveObject.tapeSet,
        archiveObject.archiveSetName,
        archiveObject.jobID,
        completionDate,
        archiveObject.status,
    )
    
    ## Connect to SQL
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    
    ## Perform our commit
    myCursor = sqlConn.cursor()
    myCursor.execute('INSERT INTO archiveHistory (fcsID,filePath,checksum,'
      'barcode,tapeSet,archiveSet,jobID,completionDate,status) '
      'VALUES(?,?,?,?,?,?,?,?,?)',dbValues)
    commitResult = sqlConn.commit()
    
    return
    
    
  def removeArchiveObjectFromArchiveQueue(self,archiveObject):
    '''Removes an archive object from the archiveQueue SQL table'''
    
    ## Connect to SQL
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    if archiveObject.recordID:
      self.logger('removeArchiveObjectFromArchiveQueue() removing record with '
        ' id:%s tapeSet:%s' % (archiveObject.recordID,archiveObject.tapeSet),'debug')
      dbValues = (archiveObject.recordID,archiveObject.tapeSet)    
      myCursor.execute('DELETE FROM archiveQueue WHERE rowid = ? AND tapeSet = ?', dbValues)
    elif archiveObject.filePath:
      self.logger('removeArchiveObjectFromArchiveQueue() removing record with'
        ' filePath:%s tapeSet:%s' % (archiveObject.recordID,archiveObject.tapeSet),'debug')
      dbValues = (archiveObject.filePath,archiveObject.tapeSet)
      myCursor.execute('DELETE FROM archiveQueue WHERE filePath = ? AND tapeSet = ?', dbValues)
   
    ## Execute our SQL Query
    commitResult = sqlConn.commit()
    
    return

  def removeArchiveObjectFromRestoreQueue(self,restoreObject):
    '''Removes an archive object from the archiveQueue SQL table'''
    
    ## Connect to SQL
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    if restoreObject.recordID:
      self.logger('removeRestoreObjectFromRestoreQueue() removing record with '
        ' id:%s' % (restoreObject.recordID),'debug')
      dbValues = (restoreObject.recordID,)    
      myCursor.execute('DELETE FROM restoreQueue WHERE rowid = ?', dbValues)
    elif restoreObject.filePath:
      self.logger('removeArchiveObjectFromRestoreQueue() removing record with'
        ' filePath:%s' % (restoreObject.filePath),'debug')
      dbValues = (restoreObject.filePath,)
      myCursor.execute('DELETE FROM restoreQueue WHERE filePath = ?', dbValues)
   
    ## Execute our SQL Query
    commitResult = sqlConn.commit()
    
    return



  def changeStatusForArchiveSet(self,status,archiveSet = ''):
    '''Changes the status for all archive objects loaded in the provided, can
    be provided a string name for the set, or the archiveSet object itself'''
    
    ## Connect to SQL
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    ## submit our SQL UPDATE Query
    myCursor.execute("UPDATE archiveQueue set status = ? "
      "WHERE archiveSet = ?", (u"%s" % status,u"%s" % archiveSet))
    commitResult = self.sqlConn.commit()
    
    return

  def setJobIDForArchiveSet(self,jobID,archiveSet = ''):
    '''Changes the jobID for all archive objects in the SQL queue, can
    be provided a string name for the set, or the archiveSet object itself'''
    
    ## Connect to SQL
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    ## submit our SQL UPDATE Query
    myCursor.execute("UPDATE archiveQueue set jobID = ? "
      "WHERE archiveSet = ?", (u"%s" % jobID,u"%s" % archiveSet))
    commitResult = sqlConn.commit()
    
    return

  def archiveSetsWithStatus(self,status):
    '''Method which returns a dictionary, keyed by the selection set name,
    which match the provided status, if a set contains multiple objects with
    different status, we will return a set only with objects matching the 
    provided status'''
    
    matchedSets = {}
    
    for setName,set in self.archiveQueue.iteritems():
      self.logger('archiveSetsWithStatus() Checking set: %s for objects with status: %s'
        % (setName,status),'debug')
      modifiedSet = copy.copy(set)
      modifiedSet.archiveObjects = []
      for theArchiveObject in set.archiveObjects:
        ##self.logger('archiveSetsWithStatus() Checking entry: %s with status: %s'
        ##  % (theArchiveObject.fcsID,archiveObject.status),'debug')
        if theArchiveObject.status == status:
          ##self.logger('archiveSetsWithStatus() Found matching entry: %s with status: %s'
          ##  % (archiveObject.fcsID,archiveObject.status),'debug')
          modifiedSet.archiveObjects.append(theArchiveObject)
        else:
          ##self.logger('archiveSetsWithStatus() Found non-matching entry: %s with status: %s, removing from results!'
          ##  % (theArchiveObject.fcsID,theArchiveObject.status),'debug')
          pass
          
      if len(modifiedSet.archiveObjects) > 0:
        self.logger('archiveSetsWithStatus() Set %s contains %s objects with status: %s'
          % (setName,len(modifiedSet.archiveObjects),status),'debug')
        matchedSets[setName] = modifiedSet
    
    self.logger('archiveSetsWithStatus() found %s matching sets with status: %s' 
      % (len(matchedSets),status),'debug')
    return matchedSets
  
  def performArchiveStatusCheck(self):
    '''Depricated: use processArchiveQueue()'''
    return self.processArchiveQueue()
  
  def processArchiveQueue(self):
    '''Method which checks on the status of submitted archive jobs. Jobs
    with a status of 'archiveSubmitted' or 'archiveRunning' are checked with nsdchat, 
    jobs with a status of 'archiveFailed','archiveDied', or 'archiveCancelled' are resubmitted.'''
    
    self.logger('processArchiveQueue() Processing archive Queue','debug')
  
    ## Load our archive queue
    ##self.loadArchiveQueue()
    
    ## Build a dictionary of archiveSets with 'archiveSubmitted' or 'archiveRunning' status
    myArchiveSets = self.archiveSetsWithStatus(status='archiveSubmitted')
    myArchiveSets.update(self.archiveSetsWithStatus(status='archiveRunning'))
    myArchiveSets.update(self.archiveSetsWithStatus(status='offsiteSubmitted'))
    myArchiveSets.update(self.archiveSetsWithStatus(status='offsiteRunning'))
    
    
    ## Build a dictionary of archiveSets with 'archiveFailed' status
    myFailedArchiveSets = self.archiveSetsWithStatus(status='archiveFailed')
    myFailedArchiveSets.update(self.archiveSetsWithStatus(status='archiveDied'))
    myFailedArchiveSets.update(self.archiveSetsWithStatus(status='archiveCancelled'))
    myFailedArchiveSets.update(self.archiveSetsWithStatus(status='offsiteFailed'))
    myFailedArchiveSets.update(self.archiveSetsWithStatus(status='offsiteDied'))
    myFailedArchiveSets.update(self.archiveSetsWithStatus(status='offsiteCancelled'))

    
    ## Process our submitted and running archiveSets
    self.logger('Found %s running archive jobs.' % len(myArchiveSets))
    self.logOffset += 1
    if len(myArchiveSets) > 0:
      for setName,set in myArchiveSets.iteritems():
        jobID = set.getJobID()
        self.logger('Checking set:\'%s\' jobID:\'%s\'. Current status:\'%s\'' 
            % (setName,jobID,set.getStatus()))
        if jobID:
          self.logger('Checking %s for new status.' % self.backupSystem,'detailed')
          newStatus = self.nsdchatStatusForJobID(jobID=jobID)
          ## If our new status matches our old status, continue the loop
          if not newStatus in self.statusMap[set.type]:
            self.logger('Recieved unknown status:\'%s\' from '
              ' PresStore for set:\'%s\'. Cannot continue!' 
              % (newStatus,setName),'error')
            continue
          if set.getStatus() == self.statusMap[set.type][newStatus]:
            self.logger('Status: \'%s\' did not change '
              'for jobID: \'%s\'' % (self.statusMap[set.type][newStatus],jobID),'detailed')
            continue
          else:
            self.logger('Found new status: %s' % (newStatus),'detailed')
            if newStatus == 'failed':
              set.wasError(error='Job failed! Will Retry.',status='archiveFailed')
            elif newStatus == 'cancelled':
              set.wasError(error='Job was cancelled by operator! Will Retry.',status='archiveCancelled')
            elif newStatus == 'died':
              set.wasError(error='Submitted job has died unexpectedly! Will Retry.',status='archiveDied')
            else:
              set.setStatusForArchiveObjects(status=newStatus)
        else:
          set.wasError(error='Submitted job lost it\'s jobID! Will Retry.',status='archiveDied')
  
        ## Don't report if our new status is 'completed'
        if not newStatus == 'completed':
          self.commitArchiveObjectsInArchiveSet(archiveSet=set)
      
    self.logOffset -= 1

    ## Process our failed archiveSets
    if len(myFailedArchiveSets) > 0:
      self.logger('Found %s failed archive jobs.' % len(myFailedArchiveSets),'warning') 
      self.logOffset += 1
      
      for setName,set in myFailedArchiveSets.iteritems():
        retryCount = set.getRetryCount()
        ## flag an error if our retry count exceeds 5
        ## Todo: add email notification
        if retryCount > 0 and retryCount < 5:
          self.logger('Found selection set: %s, this selection set has failed '
            ' %s times!' % (setName,retryCount),'warning')
        set.clearErrorsForArchiveObjects()
        if set.getTapeSet() == 'offsite':
          set.setStatusForArchiveObjects(status='offsiteQueued')
        else:
          set.setStatusForArchiveObjects(status='archiveQueued')
      
      ## Trigger an archive for our queued sets
      if len(myFailedArchiveSets) > 0:
        self.logger('Resubmitting failed archive jobs.') 
        self.archiveFilesFromQueue()
      self.logOffset -= 1

      
    ## Fetch our completed sets
    completeDate = datetime.datetime.today()
    myCompletedArchiveSets = self.archiveSetsWithStatus(status='archiveCompleted')
    myCompletedArchiveSets.update(self.archiveSetsWithStatus(status='offsiteCompleted'))
    if len(myCompletedArchiveSets) > 0:
      self.logger('Cleaning up completed archive sets','detailed')
      self.logOffset += 1 

      for setName,set in myCompletedArchiveSets.iteritems():
        ## For each object in the set, lookup and set the tape barcode label
        for theArchiveObject in set.archiveObjects:
          try:
            barcode = self.barcodeForArchiveObject(theArchiveObject)
            theArchiveObject.barcode = barcode
            theArchiveObject.archiveDate = completeDate
            ## Submit the archive object for inclusion into our archiveHistory table
            self.commitArchiveObjectToArchiveHistory(theArchiveObject)
          except FCSArchiveFileNotFoundInIndex:
            message = ("An error occured cleaning up file: \'%s\' %s reports"
              " that the file could not be found in the %s index!"
              % (theArchiveObject.filePath,self.backupSystem,theArchiveObject.tapeSet))
            self.logger(error=message,status='error')
            theArchiveObject.wasError(error=message,status='error')
            self.commitArchiveObject(theArchiveObject)
            set.errorObjects.append(archiveObject)
            continue
          except Exception, exp:
            message = ("An error occured cleaning up file: \'%s\' %s reports an"
              " unknown error cleaning up the file. Error: %s"
              % (theArchiveObject.filePath,self.backupSystem,exp))
            theArchiveObject.wasError(error=message,status='error')
            self.commitArchiveObject(theArchiveObject)
            set.errorObjects.append(theArchiveObject)
            continue
          
          ## Report to FCS
          try:
            self.commitArchiveObjectToFCS(theArchiveObject)
          except Exception,excp:
            self.logger('An error occured commiting FCS Asset with ID: %s, ERROR: %s' 
              % archiveObject.fcsID,excp,'error')

          
          ## If the tapeSet is onsite, and we are set to generate offsite archives
          ## Change the object status to 'archiveQueued' and tapeset to 'offsite'
          if theArchiveObject.tapeSet == 'onsite' and self.useOffsitePlan:
            theArchiveObject.setTapeSet('offsite')
            theArchiveObject.setStatus('offsiteQueued')
            self.commitArchiveObject(theArchiveObject)
          else:
            ## Clear the archive object out of our archive queue
            self.removeArchiveObjectFromArchiveQueue(theArchiveObject)
        
      self.logOffset -= 1 
 

#############
## RestoreQueue methods
    
  def restoreFilesFromQueue(self):
    '''Submit loaded objects in our Queue for restore'''
        
    if not len(self.restoreQueue) > 0:
      raise FCSArchiveEmptyQueueError()
    
    self.logger('Restoring files in queue.')
    
    ## Get our path to nsdchat
    nsdchatCMD = self.nsdchatCMD()
    
    ## Get our archive plan info
    archivePlan = self.archivePlan
    offsiteArchivePlan = self.offsiteArchivePlan
    useOffsitePlan = self.useOffsitePlan
  
    ## Get our restoreQueue
    restoreQueue = self.restoreQueue
    restoreSetName = self.archiveSetName
    
    ## Fetch our restore sets with status 'restoreQueued'
    restoreSets = {}
    restoreSets = self.restoreSetsWithStatus(status='restoreQueued')
    
    ## create 3 restore sets for onsite(online) offsite(online) and offline assets
    onsiteRestoreSet = archiveSet(type='restore')     ## archiveSet for assets with online tapes
    offsiteRestoreSet = archiveSet(type='restore')    ## archiveSet for assets with online tapes from the offsite set
    offlineRestoreSet = archiveSet(type='restore')    ## archiveSet of assets with offline tapes
    
    onlineTapes = []
    offlineOnsiteTapes = []
    offlineOffsiteTapes = []
    onsiteOnline = False
    offsiteOnline = False
    
    onsiteBarcode = ''
    offsiteBarcode = ''
    
    ## Set up some vars for reporting
    numSetsSubmitted = 0
    numFilesSubmitted = 0
    setFilesSubmitted = 0
    numFilesAlreadyRestored = 0  ## counter
    numFileErrors = 0
    setSubmissionErrors = {}
    fileSubmissionErrors = {}
    
    ## Iterate through our restore sets and create appropriate PresStorePlans,
    ## Populate our onsite,offsite, and offline restore sets.
    for setName,set in restoreSets.iteritems():
      setFilesSubmitted = 0
      self.logger('Committing set \'%s\' for restore.' % setName)
      self.logOffset += 1
      ## Iterate through each restoreObject, check to see if 
      ## they are online for restore
      for restoreObject in set.archiveObjects:
        self.logger('Processing file: %s' % restoreObject.filePath,'debug')
        
        ## Check to see if the file is already on disk, if so, mark as completed
        assetOnline = self.verifyOnlineAssetForArchiveObject(restoreObject)
        if assetOnline:
          restoreObject.wasError('File is online','restoreCompleted')
          restoreObject.didRestore = False
          restoreObject.archiveSetName = 'ondisk'
          numFilesAlreadyRestored += 1
          self.commitArchiveObject(restoreObject)
          continue
          
        
        ## Fetch our onsite label and see if it's online
        self.logger('Checking %s for tape barcode for file: \'%s\','
          ' tapeset: \'onsite\'' % (self.backupSystem,os.path.basename(restoreObject.filePath)))
        try:
          onsiteLabel = self.nsdchatVolumeLabelForFilePath(filePath=restoreObject.filePath,tapeSet='onsite')
        except FCSArchiveFileNotFoundInIndex:
          self.logger('Could not find label for path: %s' % restoreObject.filePath,'error')
          onsiteOnline = False
                    
        if onsiteLabel:
          onsiteBarcode = self.nsdchatBarcodeForVolumeLabel(label=onsiteLabel)
          if not onsiteBarcode:
            onsiteBarcode = self.predictVolumeBarcodeForLabel(label=onsiteLabel)
          onsiteOnline = self.nsdchatIsVolumeOnline(label=onsiteLabel)
        else:
          self.logger('Could not find label for path: %s' % restoreObject.filePath,'error')
          onsiteOnline = False
          
        if onsiteOnline:
          if not onsiteBarcode in onlineTapes:
            onlineTapes.append(onsiteBarcode)
          restoreObject.label = onsiteLabel
          restoreObject.barcode = onsiteBarcode
          onsiteRestoreSet.archiveObjects.append(restoreObject)
        else:
          ## If we are set to use an offsite plan and the onsite isn't online
          ## then check for offsite tapes in the library. 
          if self.useOffsitePlan:
            self.logger('Checking %s for tape barcode for file: \'%s\','
            ' tapeset: \'offsite\'' % (self.backupSystem,os.path.basename(restoreObject.filePath)))
            try:
              offsiteLabel = self.nsdchatVolumeLabelForFilePath(filePath=restoreObject.filePath,tapeSet='offsite')
              if offsiteLabel:
                offsiteBarcode = self.nsdchatBarcodeForVolumeLabel(label=offsiteLabel)
                if not offsiteBarcode:
                  offsiteBarcode = self.predictVolumeBarcodeForLabel(label=offsiteLabel)
                offsiteOnline = self.nsdchatIsVolumeOnline(label=offsiteLabel)
              else:
                self.logger('Could not find offsite label for path: %s' % restoreObject.filePath,'error')
                offsiteOnline = False
                
              if offsiteOnline:
                restoreObject.setTapeSet('offsite')
                restoreObject.label = offsiteLabel
                restoreObject.barcode = offsiteBarcode
                if not offsiteBarcode in onlineTapes:
                  onlineTapes.append(offsiteBarcode)
                offsiteRestoreSet.archiveObjects.append(restoreObject)
            except FCSArchiveFileNotFoundInIndex:
              self.logger(' - File does not exist in the offsite tapeSet index!','error')
      
        ## IF both onsite and offsite tapes are offline, append our lists
        if not onsiteOnline and not offsiteOnline:
          if onsiteBarcode and offsiteBarcode:
            message = 'Asset could not be submitted for restore... Tapes: %s,%s for file: %s is offline, file will remain queued!' % (onsiteBarcode,offsiteBarcode,restoreObject.filePath)
            restoreObject.statusMessage += message
            self.logger(message)
          elif onsiteBarcode and not offsiteBarcode:
            message = 'Asset could not be submitted for restore... Tape: %s for file: %s is offline, file will remain queued!' % (onsiteBarcode,restoreObject.filePath)           
            restoreObject.statusMessage += message
            self.logger(message)          
          elif offsiteBarcode and not onsiteBarcode:
            message = 'Asset could not be submitted for restore... Tape: %s for file: %s is offline, file will remain queued!' % (offsiteBarcode,restoreObject.filePath)
            restoreObject.statusMessage += message
            self.logger(message)
          else:
            message = 'Asset could not be submitted for restore... Could not find record for file: %s in archive database!' % (restoreObject.filePath)
            restoreObject.wasError(error=message,status='archiveFailed')
            self.logger(message,'error')

          
          offlineRestoreSet.archiveObjects.append(restoreObject)
          if not onsiteBarcode in offlineOnsiteTapes:
            self.logger('Adding tape: %s to offline onsite tape list' % onsiteBarcode,'debug')
            offlineOnsiteTapes.append(onsiteBarcode)
          if self.useOffsitePlan:
            if not offsiteBarcode in offlineOffsiteTapes:
              self.logger('Adding tape: %s to offline offsite tape list' % offsiteBarcode,'debug')
              offlineOffsiteTapes.append(offsiteBarcode)
      
      self.logOffset -= 1

    ## At this point we have collated sets ready for restore: onsiteRestoreSet
    ## and offsiteRestoreSet. A third set, offlineRestoreSet represents
    ## filesystem objects which are not available in the library.
    
    ## Build a list of applicable restore sets
    restoreSetList = []
    if len(onsiteRestoreSet.archiveObjects) > 0:
      onsiteRestoreSet.name='RESTORE_%s' % self.archiveSetName
      onsiteRestoreSet.setTapeSetForArchiveObjects(tapeSet='onsite')
      restoreSetList.append(onsiteRestoreSet)
    if len(offsiteRestoreSet.archiveObjects) > 0:
      offsiteRestoreSet.name='RESTORE_OFFSITE_%s' % self.archiveSetName
      offsiteRestoreSet.setTapeSetForArchiveObjects(tapeSet='offsite')
      restoreSetList.append(offsiteRestoreSet)
    
    for set in restoreSetList:
      try:
        self.logger("Submitting restore set: %s" % set.name)
        self.logOffset += 1
        jobID = self.nsdchatSubmitRestoreJobForRestoreSet(restoreSet=set,tapeSet='onsite')
        self.logOffset -= 1
        numSetsSubmitted +=1
        numFileErrors += len(set.errorObjects)
        numFilesSubmitted += (len(set.archiveObjects) - len(set.errorObjects))
        ## Update the status for our archive queue
        set.setArchiveSetForArchiveObjects(setName=set.name)
        set.setStatusForArchiveObjects(status='restoreSubmitted')
        set.setJobIDForArchiveObjects(jobID=jobID)

      except:
        self.logger('An error occurred submitting restore set:%s' % onsiteRestoreSet.name)
        setSubmissionErrors['onsite'] = onsiteRestoreSet
        raise

      ## Commit our archiveObjects to FCS and SQL
      self.commitArchiveObjectsInArchiveSet(set)        
    
    ## Report how we did 
    self.logger('Finished processing restoreQueue. Submitted %s files accross %s set(s)'
                  % (numFilesSubmitted,numSetsSubmitted))

    if numFilesAlreadyRestored > 0:
      self.logger(' - %s files were already on disk and did not need to be restored.'
                  % (numFilesAlreadyRestored))

    numOfflineFiles = len(offlineRestoreSet.archiveObjects)
    if numOfflineFiles > 0:
      self.logger('Found %s offline files, sending offline media report to %s!' % (numOfflineFiles,self.emailToNotify))
      emailSubject = 'Offline Media Report: %s offline files are queued for restore!' % (numOfflineFiles)
      emailBody = 'The following tapes from the onsite tape set need to be loaded into the library:'
      emailBody += "\n\t" + "\n\t".join(offlineOnsiteTapes)
      if self.useOffsitePlan and len(offlineOffsiteTapes) > 0:
        emailBody += "\n\nAlternatively, the following tapes from the offsite set can be loaded into the library:"
        emailBody += "\n\t" + "\n\t".join(offlineOffsiteTapes)
      ## Get our active tapes
      inUseTapes = self.barcodeListForActiveRestoreJobs()
      if len(inUseTapes) > 0:
        emailBody += ("\n\nThe following tapes are currently in use by queued or"
          " running restore jobs and should remain in the library:")
        emailBody += "\n\t" + "\n\t".join(inUseTapes)
          
      ## Send email
      self.logger('Sending offline volume email notification!')
      self.sendEmail(body=emailBody,subject=emailSubject)
      
      ##offlineRestoreSet.wasError('Asset could not be submitted for restore: required tape is offline!')
      self.commitArchiveObjectsInArchiveSet(offlineRestoreSet)
      #print "EMAILSUBJECT:%s" % emailSubject
      #print "EMAILBODY:\n%s" % emailBody
    
    ## If we have errors report failings
    if not len(setSubmissionErrors) == 0 or not numFileErrors == 0:
      self.logger('Failed to submit %s sets and %s files!' % (len(setSubmissionErrors),numFileErrors),'error') 
      return False

    return True

    
  def createRestoreQueueFromFile(self,queueFile=''):
    '''Reads file from path queueFile, which should be a line delimited list
    of file paths. We check the filePath against loaded values in our SQL
    restoreQueue table, merging where appropriate.
    
    
    .. warning:
      If ``fcsArchiver.py`` is terminated while this method is running,
      any unprocessed entries present in the queue file will be lost.
    '''
    
    if not queueFile:
      queueFile = os.path.join(self.supportPath,'filesToRestore')
    
    if not os.path.exists(queueFile):  
      self.logger("The restore queue is empty, file:'%s' does not exist!" 
        % queueFile,'debug')
      return False
    
    ## Build our current queuelist
    failedFilePaths = []
    
    ## Create a random directory, move our queue file into it.
    randomDir = tempfile.mkdtemp(dir='/tmp',prefix='fcsRestore_')
    shutil.move(queueFile,randomDir)
    queueFile = os.path.join(randomDir,'filesToRestore')
    
    myFileH = open(queueFile,"r")
    filePaths = []
    for filePath in myFileH:
      filePath = filePath.rstrip('\r\n')
      filePaths.append(filePath)
    
    ## Close and remove the file
    myFileH.close()
    try:
      shutil.rmtree(randomDir)
    except:
      pass
    
    
    for filePath in filePaths:
      try:
        restoreObject = self.createRestoreObjectFromFilePath(filePath)
        self.addToRestoreQueue(restoreObject)
      except:
        failedFilePaths.append(filePath)
        self.logger("Failed adding file at path:%s" % (filePath),"error")
        raise
        
    ## Remove the file
    myFileH.close()
    try:
      os.remove(queueFile)
    except:
      pass
    
    if len(filePaths) == 0:
      return False
    else:
      return True
        
  def addToRestoreQueue(self,restoreObject):
    '''Adds the specified restoreObject to the restore queue.'''
      
    ## Fetch our SQL handlers
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    filePath = restoreObject.filePath
      
    ## Check to see if filepath is already queued.
    ## Search for an existing record with the same filepath
    args = (filePath,)
    myCursor.execute("SELECT * FROM restoreQueue WHERE filePath = ?", args)
    isDuplicate = False
    isConflict = True
    row = myCursor.fetchone()
    if row:
      self.logger("Filepath:'%s' already exists in restoreQueue!" % filePath,'error')
      isDuplicate = True
    
    ## If we're here and have detected a duplicate, abort
    if  isDuplicate:
      return False
  
    ## Search for an existing record with the same filepath, if it has a 
    ## different checksum or fcsID, update it. 
    args = (filePath,)
    myCursor.execute("SELECT * FROM archiveHistory WHERE filePath = ? and tapeSet = 'onsite' ORDER BY completionDate LIMIT 1", args)
    histRecord = myCursor.fetchone()
    
    ## If we are Python 2.5, convert our row to a dict
    versionInfo = sys.version_info
    if versionInfo[0] == 2 and versionInfo[1] == 5 and histRecord:
      histRecord = self.createDictFromSQLRow(histRecord,table='archiveHistory')
    
    
    
    ## If file exists at the archive path or at the asset's online path,
    ## check the checksum to see if it's has an appropriate checksum. If 
    ## checksum is the same, skip the file, otherwise continue on.
    onDisk = False
    if histRecord and 'checksum' in histRecord:
      onDisk = self.verifyOnlineAssetForArchiveObject(restoreObject,checksum=histRecord['checksum'])
    else:
      onDisk = self.verifyOnlineAssetForArchiveObject(restoreObject)
      
    ## If we have found the file to exist on disk in an acceptable form,
    ## mark it as restoreCompleted
    if onDisk:
      restoreObject.archiveSet = 'ondisk'
      restoreObject.status = 'restoreCompleted'
      restoreObject.barcode = 'archiveDisk'
    else:
      restoreObject.archiveSet = ''
      restoreObject.status = 'restoreQueued'
    
    ## If we're here we haven't detected a duplicate, add the file to the
    ## Queue.
    sqlVars = (restoreObject.fcsID,
        restoreObject.filePath,
        restoreObject.archiveSet,
        restoreObject.barcode,
        restoreObject.retryCount,
        restoreObject.status,
    )
    self.logger("Adding filePath:'%s' to restoreQueue" % filePath)
    myCursor.execute("INSERT INTO restoreQueue (fcsID,filePath,archiveSet,barcode,retryCount,status) VALUES (?,?,?,?,?,?)", sqlVars)
    
    commitResult = sqlConn.commit()
    
    ## Add to our local restoreQueue
    restoreSetName = self.archiveSetName
    if not restoreSetName in self.restoreQueue:
      newRestoreSet = archiveSet(name=restoreSetName,type='restore')
      if self.debug:
        newRestoreSet.debug = True
      self.restoreQueue[restoreSetName] = newRestoreSet
    
    self.restoreQueue[restoreSetName].archiveObjects.append(restoreObject)
  
  def loadRestoreQueue(self):
    '''Function which reads our sqlite database and generates archiveSet objects
    for queued files'''
    
    ## Load our SQL connection
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    restoreQueue = {}
    
    ## Query for all entries in our archiveQueue
    sqlQuery = 'SELECT rowid,* FROM restoreQueue'
    self.logger('loadRestoreQueue() executing with query: %s' % sqlQuery,'debug')
    myCursor.execute(sqlQuery)
    isDuplicate = False
    isConflict = True
    myResults = myCursor.fetchall()
    for row in myResults:
      
      ## If we are Python 2.5, convert our row to a dict
      versionInfo = sys.version_info
      if versionInfo[0] == 2 and versionInfo[1] == 5:
        myRow = self.createDictFromSQLRow(row,table='restoreQueue')
      else:
        myRow = row
        
      ##self.logger('loadRestoreQueue() result row keys:%s rowID:%s' % (myRow.keys(),myRow['rowid']),'debug')
      restoreSetName = myRow['archiveSet']
      if not restoreSetName:
        restoreSetName = self.archiveSetName
      restoreSetJobID = myRow['jobID']
      if not restoreSetName in restoreQueue:
        newRestoreSet = archiveSet(name=restoreSetName,type='restore',jobID=restoreSetJobID)
        if self.debug:
          newRestoreSet.debug = True
        restoreQueue[restoreSetName] = newRestoreSet
      
      myRestoreSet = restoreQueue[restoreSetName]
      myRestoreObject = archiveObject(action='restore')
      myRestoreObject.loadFromSQLResult(myRow)
      restoreQueue[restoreSetName].archiveObjects.append(myRestoreObject)
      
    ##self.restoreQueue.update(restoreQueue)
    self.restoreQueue = restoreQueue
    return

    
  
  def restoreSetsWithStatus(self,status):
    '''Method which returns a dictionary, keyed by the selection set name,
    which match the provided status'''
    
    matchedSets = {}
    
    for setName,set in self.restoreQueue.iteritems():
      if set.getStatus() == status:
        matchedSets[setName] = set
        
    return matchedSets
  
  def performRestoreStatusCheck(self):
    '''Depricated: use processArchiveQueue()'''
    return self.processRestoreQueue()
  
  def processRestoreQueue(self):
    '''Method which checks on the status of submitted archive jobs. Jobs
    with a status of 'archiveSubmitted' or 'archiveRunning' are checked with nsdchat, 
    jobs with a status of 'archiveFailed','archiveDied', or 'archiveCancelled' are resubmitted.'''
    
    
    ## Build a dictionary of archiveSets with 'restoreSubmitted' or 'restoreRunning' status
    myRestoreSets = self.restoreSetsWithStatus(status='restoreSubmitted')
    myRestoreSets.update(self.restoreSetsWithStatus(status='restoreRunning'))
    
    ## Build a dictionary of archiveSets with 'archiveFailed' status
    myFailedRestoreSets = self.restoreSetsWithStatus(status='restoreFailed')
    myFailedRestoreSets.update(self.restoreSetsWithStatus(status='restoreDied'))
    myFailedRestoreSets.update(self.restoreSetsWithStatus(status='restoreCancelled'))
    
    ## Process our submitted and running archiveSets
    self.logger('Found %s running restore jobs.' % len(myRestoreSets)) 

    if len(myRestoreSets) > 0:
      newStatus = ''
      for setName,set in myRestoreSets.iteritems():
        jobID = set.getJobID()
        self.logger('performRestoreStatusCheck() processing set:%s jobID:%s with status:%s' 
            % (setName,jobID,set.getStatus()),'debug')
        if jobID:
          newStatus = self.nsdchatStatusForJobID(jobID=jobID)
          ## If our new status matches our old status, continue the loop
          if not newStatus in self.statusMap[set.type]:
            self.logger('ERROR: Found unexpected status:%s, skipping set:%s' % (newStatus,setName),'error')
            continue
          if set.getStatus() == self.statusMap[set.type][newStatus]:
            self.logger('performRestoreStatusCheck() status:%s did not change for set:%s' % (set.getStatus(),setName),'debug')
            continue
          else:
            self.logger('Found new status: %s' % (newStatus),'debug')
            if newStatus == 'failed':
              set.wasError(error='Job failed! Will Retry.',status='restoreFailed')
            elif newStatus == 'cancelled':
              set.wasError(error='Job was cancelled by operator! Will Retry.',status='restoreCancelled')
            elif newStatus == 'died':
              set.wasError(error='Submitted job has died unexpectedly! Will Retry.',status='restoreDied')
            else:
              set.setStatusForArchiveObjects(status=newStatus)
        else:
          set.wasError(error='Submitted job lost it\'s jobID! Will Retry.',status='restoreDied')
          newStatus = 'restoreDied'
        
        ## Don't report if our new status is 'completed'
        if not newStatus == 'completed':
          self.commitArchiveObjectsInArchiveSet(archiveSet=set)
    
    ## Process our failed archiveSets
    if len(myFailedRestoreSets) > 0:
      for setName,set in myFailedRestoreSets.iteritems():
        retryCount = set.getRetryCount()
        ## flag an error if our retry count exceeds 5
        ## Todo: add email notification
        if retryCount < 5:
          self.logger('This selection set has failed %s times!' % retryCount,'error')
        set.clearErrorsForArchiveObjects()
        set.setStatusForArchiveObjects(status='restoreQueued')
        
      
      ## Trigger an archive for our queued sets
      if len(myFailedRestoreSets) > 0:
        self.restoreFilesFromQueue()
      
    ## Fetch our completed sets
    completeDate = datetime.datetime.today()
    myCompletedRestoreSets = self.restoreSetsWithStatus(status='restoreCompleted')
    if len(myCompletedRestoreSets) > 0:
      self.logger('Found %s completed restore sets!' % len(myCompletedRestoreSets))
    if len(myCompletedRestoreSets) > 0:
      for setName,set in myCompletedRestoreSets.iteritems():
        ## For each item, submit for inclusion into our archiveHistory table
        for theRestoreObject in set.archiveObjects:
          ## Make sure the asset has the appropriate status
          if not theRestoreObject.status == 'restoreCompleted':
            continue
          message = 'Restore completed for asset with id:%s' % theRestoreObject.fcsID
          if theRestoreObject.barcode:
            message += ' using tape: %s' % theRestoreObject.barcode
          self.logger(message)
          if not theRestoreObject.statusMessage:
            theRestoreObject.statusMessage = message
          theRestoreObject.restoreDate = completeDate
          theRestoreObject.didRestore = True
          ## Submit the archive object for inclusion into our archiveHistory table
          self.commitArchiveObjectToArchiveHistory(theRestoreObject)

          ## Report to FCS
          try:
            self.commitArchiveObjectToFCS(theRestoreObject)
          except Exception,excp:
            self.logger('An error occured commiting FCS Asset with ID: %s, ERROR: %s' 
              % archiveObject.fcsID,excp,'error')
          
          ## Clear the archive object out of our archive queue
          self.removeArchiveObjectFromRestoreQueue(theRestoreObject)
          
          
        
        

  
  def setStatusForRestoreSet(self,status,restoreSet = ''):
    '''Changes the status for all archive objects loaded in this restore set'''
    
    ## Connect to SQL
    sqlConn = self.connectToSQL()
    sqlConn.row_factory = sqlite3.Row
    myCursor = sqlConn.cursor()
    
    ## Fetch our archiveSet
    if not archiveSet:
      archiveSet = self.archiveSet
    
    ## submit our SQL UPDATE Query
    myCursor.execute("UPDATE restoreQueue set status = ? "
      "WHERE restoreSet = ?", (u"%s" % status,u"%s" % restoreSet))
    commitResult = self.sqlConn.commit()
  
  def createArchiveObjectFromFilePath(self,filePath):
    '''Returns an archiveObject loaded from provided filepath. We utilize
    fcsvr_client to fetch FCS data'''
    
    newArchiveObject = archiveObject()
    newArchiveObject.archiveSetName = self.archiveSetName
    newArchiveObject.archivePath = self.archivePath
    if self.debug:
      newArchiveObject.debug = True
    
    newArchiveObject.loadForFileAtPath(filePath)          
    return newArchiveObject 
    
  def createRestoreObjectFromFilePath(self,filePath):
    '''Returns an archiveObject loaded from provided filepath. We utilize
    fcsvr_client to fetch FCS data'''
    
    self.logger('createRestoreObjectFromFilePath() hit for file path: %s' % filePath,'debug')
    
    newRestoreObject = archiveObject(action='restore')
    newRestoreObject.archiveSetName = self.archiveSetName
    newRestoreObject.archivePath = self.archivePath
    if self.debug:
      newRestoreObject.debug = True
    newRestoreObject.loadForFileAtPath(filePath)          
    
    return newRestoreObject 
        
  def verifyOnlineAssetForArchiveObject(self,archiveObject,checksum=''):
    '''Verifies whether an archiveObject's asset is online, either in an 
    archived state or in it's original location.'''
    
    ## If file exists at the archive path or at the asset's online path,
    ## check the checksum to see if it's has an appropriate checksum. If 
    ## checksum is the same, skip the file, otherwise continue on.
    onDisk = False
    
    self.logger('Checking to see if asset: %s is online' % archiveObject.filePath,'detailed')
    
    ## Get our archive and online paths, check to see if a file exists
    ## at either location. todo: this should really just query the FCS record 
    ## for Archive Status rather than look at online path (online path breakes
    ## with network devices).
    archivePath = archiveObject.filePath
    onlinePath = archiveObject.onlinePath
    if not onlinePath:
      if not archiveObject.fcsObject:
        archiveObject.loadFCSObject()
        
      myFCSVRClient = archiveObject.fcsObject
      if self.configParser:
        myFCSVRClient.loadConfiguration(self.configParser)
      onlinePath = myFCSVRClient.getFSPathFromArchivePath(archivePath)
      archiveObject.onlinePath = onlinePath
    
    ## If a file exists in our archive or online paths, then analyze it for use.
    if os.path.exists(archivePath) or os.path.exists(onlinePath):
      if not 'checksum':
        self.logger('File: %s already exists on disk archive, no previous archive'
                        ' history could be found, using on-disk verison!' % archivePath)
        onDisk = True
      elif checksum == archiveObject.checksum:  
        if os.path.exists(archivePath):
          self.logger('File: %s already exists on disk archive with the appropriate'
                        ' checksum, skipping restore from tape!' % archivePath)
          onDisk = True
        elif os.path.exists(onlinePath):
          self.logger('File: %s already exists in online location with the appropriate'
                        ' checksum, skipping restore from tape!' % onlinePath)
          onDisk = True        
      else:
        ## If a file exists at the location, but does not match our recorded 
        ## Checksum, do we use it?
        if self.trustRestoreChecksumMismatch:
          self.logger('File: %s already exists on disk archive with an inappropriate'
                      ' checksum, using anyway: skipping restore from tape!' % archivePath)
          onDisk = True
        else:
          self.logger('File: %s already exists on disk archive with an inappropriate'
                      ' checksum, %s will determine behavior.' % (archivePath,self.backupSystem))
          ##shutil.move(filePath,"%s_saved" % archivePath)
    if onDisk:
      self.logger(' - Asset: %s is online!' % archiveObject.filePath,'debug')
    else:
      self.logger(' - Asset: %s is offline!' % archiveObject.filePath,'debug')
    
    return onDisk 

  def barcodeListForActiveRestoreJobs(self):
    '''Returns a list of barcode numbers in use by active jobs (submitted and running)'''
    
    tapeList = []
    
    ## Get our appropriate restoreSets
    restoreSets = self.restoreSetsWithStatus(status='restoreSubmitted')
    restoreSets.update(self.restoreSetsWithStatus(status='restoreRunning'))    
          
    ##self.logger('loadRestoreQueue() result row keys:%s rowID:%s' % (row.keys(),row['rowid']),'debug')
    for setName,set in restoreSets.iteritems():
      for archiveObject in set.archiveObjects:
        if archiveObject.status == 'restoreSubmitted' or archiveObject.status == 'restoreRunning':
          barcode = archiveObject.barcode
          if not barcode in tapeList:
            tapeList.append(barcode)
      
    self.logger('barcodeListForActiveRestoreJobs() Found %s tapes in use by active restore jobs.' % len(tapeList),'debug')
    return tapeList

  def barcodeForArchiveObject(self,archiveObject,tapeSet=''):
    '''Returns the barcode corresponding to the tape the file for the 
    provided archiveObject'''
    
    ## Get our relevant variables
    filePath = archiveObject.filePath
    ## If we were not passed a tapeSet explicitely, query the archiveObject
    if not tapeSet:
      tapeSet = archiveObject.tapeSet
    
    ## Fetch our PresStore label
    self.logger('Checking %s for tape barcode for file: \'%s\','
          ' tapeset: \'onsite\'' % (self.backupSystem,os.path.basename(archiveObject.filePath)),'detailed')
    volumeLabel = self.nsdchatVolumeLabelForFilePath(filePath=filePath,tapeSet=tapeSet)
    if volumeLabel:
      ## Fetch our barcode from the label
      barcode = self.nsdchatBarcodeForVolumeLabel(label=volumeLabel)
      return barcode
    else:
      return False
  
  def volumeLabelForArchiveObject(self,archiveObject,tapeSet=''):
    '''Returns the barcode corresponding to the tape the file for the 
    provided archiveObject.'''
    
    ## Get our relevant variables
    filePath = archiveObject.filePath
    ## If we were not passed a tapeSet explicitely, query the archiveObject
    if not tapeSet:
      tapeSet = archiveObject.tapeSet
    
    ## Fetch our PresStore label
    if self.backupSystem == 'PresStore':
      volumeLabel = self.nsdchatVolumeLabelForFilePath(filePath=filePath,tapeSet=tapeSet)
    else:
      raise FCSArchiverUnknownBackupSystem()
      
    return volumeLabel

  def volumeIsOnlineForRestoreObject(self,restoreObject,tapeSet=''):
    '''Returns true or false based on whether the tape for the provided 
    restoreObject is online. If no tapeSet is specified, we will return
    true whether an offsite or onsite disk is available, and we will update
    the tapeSet on the restoreObject accordingly'''
    
    ## Get our relevant variables
    filePath = restoreObject.filePath
    
    offsiteOnline = False
    onsiteOnline = False
    
    if not tapeSet or tapeSet == 'onsite':
      ## Fetch our PresStore label from our onsite tapeset
      onsiteLabel = self.nsdchatVolumeLabelForFilePath(filePath=filePath,tapeSet='onsite')  
      onsiteOnline = nsdchatIsVolumeOnline(onsiteLabel)
    
    if self.useOffsitePlan and (not tapeSet or tapeSet == 'offsite'):
      ## Fetch our PresStore label from our onsite tapeset
      offsiteLabel = self.nsdchatVolumeLabelForFilePath(filePath=filePath,tapeSet='offsite')  
      offsiteOnline = nsdchatIsVolumeOnline(offsiteLabel)
      
    if onsiteOnline:
      restoreObject.setTapeSet('onsite')
      restoreObject.label = onsiteLabel
      return True
    elif offsiteOnline:
      restoreObject.setTapeSet('offsite')
      restoreObject.label = offsiteLabel
      return True

    return False
  
  def createDictFromSQLRow(self,row,table='archiveQueue'):
    '''This function creates an associative dictionary from an SQL results row,
    necessary for Python versions previous to 2.6 that do not support 
    sqlite3.Row.keys(). Accepts optional parameter table, which is used to
    specify the table that we are creating the result set for.'''
    
    keyArray = []
    resultsDict = {}
    if table == 'archiveQueue':
      if len(row) == 10:
        keyArray = ['rowid','fcsID','filePath','checksum','archiveSet','tapeSet',
                    'jobID','jobSubmitDate','retryCount','status']
      elif len(row) == 9:
        keyArray = ['fcsID','filePath','checksum','archiveSet','tapeSet',
                    'jobID','jobSubmitDate','retryCount','status']
      else:
        raise RuntimeError('createDictFromSQLRow() Recieved incorrect item count'
                ' for table:%s expected 9 or 10, recieved:%s' %(table,len(row)));
    
    elif table == 'restoreQueue':
      if len(row) == 10:
        keyArray = ['rowid','fcsID','filePath','archiveSet','tapeSet','barcode',
                    'jobID','jobSubmitDate','retryCount','status']
      elif len(row) == 9:
        keyArray = ['fcsID','filePath','archiveSet','tapeSet','barcode',
                    'jobID','jobSubmitDate','retryCount','status']
      else:
        raise RuntimeError('createDictFromSQLRow() Recieved incorrect item count'
                ' for table:%s expected 9 or 10, recieved:%s' %(table,len(row)));
    elif table == 'archiveHistory':
      if len(row) == 10:
        keyArray = ['rowid','fcsID','filePath','checksum','barcode','tapeSet',
                    'archiveSet','jobID','completionDate','status']
      elif len(row) == 9:
        keyArray = ['fcsID','filePath','checksum','barcode','tapeSet',
                    'archiveSet','jobID','completionDate','status']
      else:
        raise RuntimeError('createDictFromSQLRow() Recieved incorrect item count'
                ' for table:%s expected 9 or 10, recieved:%s' %(table,len(row)));
    
    ## Generate our dict based upon index number
    i=0
    while i < len(row):
      resultsDict[keyArray[i]] = row[i]
      i+=1
      
    ## return our resultsDict
    return resultsDict
  
  def nsdchatCMD(self):
    '''Returns nsdchat command, this may be wrapped with sudo or ssh, so
    you should not quote the nsdchat path argument when submitting'''
    
    
    nsdchatpath = self.nsdchatpath
    nsdchatCMD = nsdchatpath
    
    if self.nsdchatUseSudo:
      nsdchatCMD = "/usr/bin/sudo %s" % nsdchatCMD

    if self.nsdchatUseSSL:
      if self.nsdchatSSLHost and self.nsdchatRemoteUser:
        nsdchatCMD = "/usr/bin/ssh %s@%s %s" % (self.nsdchatRemoteUser,self.nsdchatSSLHost,nsdchatCMD)
      else:
        if not self.nsdchatSSLHost and not self.nsdchatRemoteUser:
          message = 'nsdchat is configured to use SSL but remoteSSLHost and remoteSSLUsername are not configured!'
        elif not self.nsdchatSSLHost:
          message = 'nsdchat is configured to use SSL but remoteSSLHost is not configured!'
        elif not self.nsdchatRemoteUser:
          message = 'nsdchat is configured to use SSL but remoteSSLUsername is not configured!'
          
        self.logger(message,'error')
        raise RuntimeError(message)
                
    return nsdchatCMD
    
  
  def nsdchatSubmitArchiveJobForArchiveSet(self,archiveSet,tapeSet=''):
    '''Creates a new selection set and submits the job, returns jobID'''
    
    ## Setup our vars
    setName = archiveSet.name
    numFilesSubmitted = 0
    nsdchatCMD = self.nsdchatCMD()
    if not tapeSet:
      tapeSet = archiveSet.getTapeSet()
    if tapeSet == 'offsite' and self.useOffsitePlan:
      archivePlan = self.offsiteArchivePlan
    else:
      archivePlan = self.archivePlan

    self.logger('Creating new archive job for set:%s using archive plan:%s' 
      % (setName,archivePlan))


    ## If we have no archiveObjects loaded, bail out      
    if not len(archiveSet.archiveObjects) > 0:
      theError = 'Archive selection:"%s" has no files to submit for archive!' % setName
      self.logger(theError,'error')
      raise FCSArchiveEmptyQueueError(theError)
              
    ## Create our ArchiveSelection handler.
    selectionCMDString = '%s -c ArchiveSelection create localhost "%s"' % (nsdchatCMD,archivePlan)
    self.logger('nsdchatSubmitArchiveJobForArchiveSet() Running Command: (%s)' % selectionCMDString,'debug')
    selectionCMD = subprocess.Popen(selectionCMDString,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    selectionCMD_stdout,selectionCMD_stderr = selectionCMD.communicate()

    if not selectionCMD.returncode == 0:
      theError = "An error occured creating the ArchiveSelection: %s" % self.nsdchatError()
      self.logger(theError,"error")
      raise RuntimeError(theError)

      
    ## set our selection handler  
    archiveSelection = selectionCMD_stdout.strip()

    ## Iterate through our sets archive objects and add them to the selection
    for archiveObject in archiveSet.archiveObjects:
    
      if not os.path.exists(archiveObject.filePath):
        self.logger("An error occurred adding file: %s Error: File does not exist on disk." % (archiveObject.filePath),"error")
        archiveObject.wasError(error="An error occured adding to queue. The file does not exist on disk.",status='fatalError')
        archiveSet.errorObjects.append(archiveObject)
        continue
          
      self.logger('Submitting file: \'%s\'' % archiveObject.filePath,'detailed')
      ## add our archiveObject to our ArchiveSelection handler.
      addEntryCMDString = ('%s -c ArchiveSelection "%s" addentry {"%s"}' 
                              % (nsdchatCMD,archiveSelection,archiveObject.filePath))
      self.logger('nsdchatSubmitArchiveJobForArchiveSet() Running Command: (%s)' % addEntryCMDString,'debug')
      addEntryCMD = subprocess.Popen(addEntryCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
      addEntryCMD_stdout,addEntryCMD_stderr = addEntryCMD.communicate()

      if not addEntryCMD.returncode == 0:
        nsdchatError = self.nsdchatError()
        self.logger("An error occurred adding file: %s Error: %s" % (archiveObject.filePath,nsdchatError),"error")
        archiveObject.wasError(error="An error occured adding to queue. Reported Error: %s" % nsdchatError,status='archiveFailed')
        archiveSet.errorObjects.append(archiveObject)
        continue
      
      ## Iterate our file submission counter
      numFilesSubmitted +=1

    ## If no files successfully submitted, abort our restore job
    if numFilesSubmitted == 0:
      self.logger('No files were successfully submitted, skipping archive set %s.' % archiveSelection,'error')
      return False
    
    ## Submit our archive job
    submitJobCMDString = ('%s -c ArchiveSelection "%s" submit 1' 
                              % (nsdchatCMD,archiveSelection))
    self.logger('nsdchatSubmitArchiveJobForArchiveSet() Running Command: (%s)' % submitJobCMDString,'debug')
    submitJobCMD = subprocess.Popen(submitJobCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    submitJobCMD_stdout,submitJobCMD_stderr = submitJobCMD.communicate()

    if not submitJobCMD.returncode == 0:
      theError = ("An error occured submitting job: %s Error:%s" 
                  % (archiveSelection,self.nsdchatError()))
      self.logger(theError,"error")
      for archiveObject in archiveSet.archiveObjects:
        archiveObject.wasError(error=theError,status = 'archiveFailed')
        archiveSet.errorObjects.append(archiveObject)
    else:
      self.logger("Successfully submitted job for selection set:%s"
        " Total Files:%s" % (setName,numFilesSubmitted))
      
    jobID = submitJobCMD_stdout.strip()
    return jobID

  def nsdchatSubmitRestoreJobForRestoreSet(self,restoreSet,tapeSet=''):
    '''Creates a new selection set and submits the job, returns jobID'''
    
    nsdchatCMD = self.nsdchatCMD()
    
    setName = restoreSet.name
    numFilesSubmitted = 0
    
    ## Get our tapeset
    if not tapeSet:
      tapeSet = restoreSet.getTapeSet()
      
    if tapeSet == 'offsite' and self.useOffsitePlan:
      archivePlan = self.offsiteArchivePlan
    else:
      archivePlan = self.archivePlan

    self.logger('Creating new restore job for set:%s using archive plan:%s' 
      % (setName,archivePlan))

      
    ## If we have no restoreObjects loaded, bail out      
    if not len(restoreSet.archiveObjects) > 0:
      theError = 'Restore selection:"%s" has no files to submit for restore!' % setName
      self.logger(theError,'error')
      raise FCSArchiveEmptyQueueError(theError)
           
    ## Create our database handler
    
    dbCMDString = '%s -c ArchivePlan %s database' % (nsdchatCMD,archivePlan)
    self.logger('nsdchatSubmitRestoreJobForRestoreSet() Running Command: (%s)' % dbCMDString,'debug')
    dbCMD = subprocess.Popen(dbCMDString,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    dbCMD_stdout,dbCMD_stderr = dbCMD.communicate()

    if not dbCMD.returncode == 0:
      theError = "An error occured creating the ArchivePlan for restore: %s" % self.nsdchatError()
      self.logger(theError,"error")
      raise RuntimeError(theError)
    dbHandle = dbCMD_stdout.strip()
    self.logger('nsdchatSubmitRestoreJobForRestoreSet() - found dbHandle: %s' % dbHandle,'debug')

                               
    ## Create our ArchiveSelection handler.
    selectionCMDString = '%s -c RestoreSelection create localhost' % nsdchatCMD
    self.logger('nsdchatSubmitRestoreJobForRestoreSet() Running Command: (%s)' % selectionCMDString,'debug')    
    selectionCMD = subprocess.Popen(selectionCMDString,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    selectionCMD_stdout,selectionCMD_stderr = selectionCMD.communicate()

    if not selectionCMD.returncode == 0:
      theError = "An error occured creating the RestoreSelection: %s" % self.nsdchatError()
      self.logger(theError,"error")
      raise RuntimeError(theError)

    ## set our selection handler  
    restoreSelection = selectionCMD_stdout.strip()
    self.logger('nsdchatSubmitRestoreJobForRestoreSet() - found selection: %s' % restoreSelection,'debug')    


    ## Iterate through our sets archive objects and add them to the selection
    for archiveObject in restoreSet.archiveObjects:
      self.logger('Submitting file: \'%s\'' % archiveObject.filePath,'detailed')
      
      ## Get our file handle for the archive object
      ##self.logger('ArchiveObjectType:%s' % type(archiveObject),'debug')
      handleCMDString = '%s -c ArchiveEntry handle localhost {%s} %s' % (nsdchatCMD,archiveObject.filePath,dbHandle)
      self.logger('nsdchatSubmitRestoreJobForRestoreSet() Running Command: (%s)' % handleCMDString,'debug')
      handleCMD = subprocess.Popen(handleCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True,)
                              
      handleCMD_stdout,handleCMD_stderr = handleCMD.communicate()
      handle = handleCMD_stdout.strip()
      self.logger('nsdchatSubmitRestoreJobForRestoreSet() - found handle: %s' % handle,'debug')    

      if not handleCMD.returncode == 0:
        nsdchatError = self.nsdchatError()
        self.logger("An error occurred adding file: %s Error:%s" % (archiveObject.filePath,nsdchatError),"error")
        archiveObject.wasError(error="An error occured adding to queue. Reported Error: %s" % nsdchatError,status='restoreFailed')
        restoreSet.errorObjects.append(archiveObject)
        continue
      
      ## add our archiveObject to our RestoreSelection handler.
      if archiveObject.label:
        addEntryCMDString = '%s -c RestoreSelection "%s" addentry "%s" %s' % (nsdchatCMD,restoreSelection,handle,archiveObject.label)
      else:
        addEntryCMDString = '%s -c RestoreSelection "%s" addentry "%s"' % (nsdchatCMD,restoreSelection,handle)
      
      self.logger('nsdchatSubmitRestoreJobForRestoreSet() Running Command: (%s)' % addEntryCMDString,'debug')
      addEntryCMD = subprocess.Popen(addEntryCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
      addEntryCMD_stdout,addEntryCMD_stderr = addEntryCMD.communicate()

      if not addEntryCMD.returncode == 0:
        nsdchatError = self.nsdchatError()
        self.logger("An error occurred adding file: %s Error:%s" % (archiveObject.filePath,nsdchatError),"error")
        archiveObject.wasError(error="An error occured adding to queue. Reported Error: %s" % nsdchatError,status='archiveFailed')
        archiveSet.errorObjects.append(archiveObject)
        continue
      
      ## Iterate our file submission counter
      numFilesSubmitted +=1
      
    ## If no files successfully submitted, abort our restore job
    if numFilesSubmitted == 0:
      self.logger('No files were successfully submitted, skipping restore set %s.' % restoreSelection,'warning')
      return False
    
      
    submitJobCMDString = '%s -c RestoreSelection "%s" submit 1' % (nsdchatCMD,restoreSelection)
    self.logger('nsdchatSubmitRestoreJobForRestoreSet() Running Command: (%s)' % submitJobCMDString,'debug')
    submitJobCMD = subprocess.Popen(submitJobCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    submitJobCMD_stdout,submitJobCMD_stderr = submitJobCMD.communicate()

    jobID = ''
    if not submitJobCMD.returncode == 0:
      theError = ("An error occured submitting job: %s Error:%s" 
                  % (restoreSelection,self.nsdchatError()))
      self.logger(theError,"error")
      for archiveObject in archiveSet.archiveObjects:
        archiveObject.wasError(error=theError,status = 'archiveFailed')
        restoreSet.errorObjects.append(archiveObject)
    else:
      jobID = submitJobCMD_stdout.strip()
      self.logger("Successfully submitted job for selection set:%s JobID:%s" % (setName,jobID))
    
    return jobID  
    
    
  def nsdchatStatusForJobID(self,jobID):
    '''Uses nsdchat to query the status of job with provided running jobID'''
    nsdchatCMD = self.nsdchatCMD()
    
    cmdString = '%s -c Job %s status' % (nsdchatCMD,jobID)
    
    jobCMD = subprocess.Popen(cmdString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    jobCMD_stdout,jobCMD_stderr = jobCMD.communicate()

    jobStatus = jobCMD_stdout.strip()
    ## If job status is empty, it means the job has disappeared: server restart
    ## power outage, etc. Set it as 'archiveDied' 
    if not jobStatus:
      jobStatus = 'archiveDied'
    return jobStatus


  def nsdchatVolumeBarcodesForFilePathFromArchiveDatabase(self,filePath,archiveDatabase="Default-Archive"):
    '''Returns an array of volume barcodes for the specified path as indexed in the
    provided archive database'''

    self.logger('nsdchatVolumeBarcodesForFilePathFromArchiveDatabase() retrieving'
       ' volume barcodes for file:\'%s\' from archiveDatabase:\'%s\'' 
       % (filePath,archiveDatabase),'debug')
       
    volumeLabels = self.nsdchatVolumeLabelsForFilePathFromArchiveDatabase(filePath=filePath,archiveDatabase=archiveDatabase)
    volumeBarcodes = []
    for label in volumeLabels:
      barcode = self.nsdchatBarcodeForVolumeLabel(label)
      volumeBarcodes.append(barcode)
    
    return volumeBarcodes
  
  def nsdchatVolumeLabelsForFilePathFromArchiveDatabase(self,filePath,archiveDatabase="Default-Archive"):
    '''Returns an array of volume labels for the specified path as indexed in the
    provided archive database'''
    
    ## Get our nsdchatCMD syntax
    nsdchatCMD = self.nsdchatCMD()
    
    self.logger('nsdchatVolumeLabelsForFilePathFromArchiveDatabase() retrieving'
       ' volume labels for file:\'%s\' from archiveDatabase:\'%s\'' 
       % (filePath,archiveDatabase),'debug')
    
    ## Get our file handler
    fhCMDString = '%s -c ArchiveEntry handle localhost {%s} %s' % (nsdchatCMD,filePath,archiveDatabase)
    self.logger('nsdchatVolumeLabelsForFilePathFromArchiveDatabase() Running Command: (%s)' % fhCMDString,'debug')
    fhCMD = subprocess.Popen(fhCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    fhCMD_stdout,fhCMD_stderr = fhCMD.communicate()
    fhHandle = fhCMD_stdout.strip()
    
    ## Make sure we have a handle.
    if not fhHandle:
      self.logger('PresStore returned an empty handle for file: %s' % filePath,'error')
      raise FCSArchiveFileNotFoundInIndex(filePath=filePath,archiveDatabase=archiveDatabase)
    
    if fhHandle == "#":
      message = 'PresStore returned a corrupt \'#\' handle for file: %s' % filePath
      self.logger(message,'error')
      raise PresStoreCorruptDataError(error=message)
    
    ## Get our volume
    volCMDString = '%s -c ArchiveEntry "%s" volume' % (nsdchatCMD,fhHandle)
    self.logger('nsdchatVolumeLabelForFilePath() Running Command: (%s)' % volCMDString,'debug')
    volCMD = subprocess.Popen(volCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    volCMD_stdout,volCMD_stderr = volCMD.communicate()
    volumeOutput = volCMD_stdout.strip()
    
    if not volumeOutput:
      raise FCSArchiveFileNotFoundInIndex(filePath=filePath,archiveDatabase=archiveDatabase)
    elif volumeOutput == "#":
      message = 'PresStore returned \'#\', cannot continue!'
      self.logger(message,'error')
      raise PresStoreCorruptDataError(error=message)
    else:
      volumeArray = volumeOutput.split(' ')

    return volumeArray
    
  
  def nsdchatVolumeLabelForFilePath(self,filePath,tapeSet='onsite'):
    '''Returns the volume label for file archived at path filePath. If PresStore
    returns multiple volume labels, only the first volume is returned.'''
    
    ## Determine our archivePlan based on tapeSet
    if tapeSet == 'onsite':
      archivePlan = self.archivePlan
    else:
      archivePlan = self.offsiteArchivePlan
      
    nsdchatCMD = self.nsdchatCMD()
    
    ## Get our database handler
    cmdString = '%s -c ArchivePlan "%s" database ' % (nsdchatCMD,archivePlan)
    self.logger('nsdchatVolumeLabelForFilePath() Running Command: (%s)' % cmdString,'debug')
    dbCMD = subprocess.Popen(cmdString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    dbCMD_stdout,dbCMD_stderr = dbCMD.communicate()
    dbHandler = dbCMD_stdout.strip()
    
    if dhHandler == "#":
      message = 'PresStore returned a corrupt \'#\' database handle for archivePlan: %s' % archivePlan
      self.logger(message,'error')
      raise PresStoreCorruptDataError(error=message)
    
    volumeArray = self.nsdchatVolumeLabelsForFilePathFromArchiveDatabase(filePath=filePath,archiveDatabase=dbHandler)
    
    volume = volumeArray[0]
    if len(volumeArray) > 1:
      self.logger('Found multiple tapes for file:%s Tapes:%s '
        'Returning volume:%s' % (filePath,",".join(volumeArray),volume),'debug')
     
    self.logger('Found volume label:%s for filePath:%s tapeSet:%s' % (volume,filePath,tapeSet),'detailed')

    return volume
    
  def nsdchatBarcodeForVolumeLabel(self,label):
    '''Returns the volume barcode for provided PresStore tape label'''
      
    nsdchatCMD = self.nsdchatCMD()
    
    if not label or label == 0:
      self.logger('No label was provided, cannot determine volume barcode!','error')
      raise FCSArchiveVolumeNotFound()
    
    ## Finally, get our barcode
    barcodeCMDString = '%s -c Volume "%s" barcode' % (nsdchatCMD,label)
    self.logger('getBarcodeForVolumeLabel() Running Command: (%s)' % barcodeCMDString,'debug')
    barcodeCMD = subprocess.Popen(barcodeCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    barcodeCMD_stdout,barcodeCMD_stderr = barcodeCMD.communicate()
    barcode = barcodeCMD_stdout.strip()
    self.logger('getBarcodeForVolumeLabel() - Found barcode:%s for label:%s' % (barcode,label),'debug')
    
    if barcode == '<empty>':
      return False
      
    return barcode
  
  def nsdchatIsVolumeOnline(self,label):
    '''Returns the status for volume with provided label, returns True
    if the asset is on a tape in the library, false if it is not'''
    
    nsdchatCMD = self.nsdchatCMD()
    
    ## Get our isonline status
    isonlineCMDString = '%s -c Volume "%s" isonline' % (nsdchatCMD,label)
    self.logger('isVolumeWithLabelOnline() Running Command: (%s)' % isonlineCMDString,'debug')
    isonlineCMD = subprocess.Popen(isonlineCMDString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    isonlineCMD_stdout,isonlineCMD_stderr = isonlineCMD.communicate()
    isonline = isonlineCMD_stdout.strip()
    
    if isonline == '1':
      self.logger('nsdchatIsVolumeOnline() Volume with label:%s is online.'% label,'debug')
      return True
    else:
      self.logger('nsdchatIsVolumeOnline() Volume with label:%s is offline!'% label,'debug')
      return False
                   
  def nsdchatError(self):
    '''Returns the last error message reported by nsdchat'''
    
    nsdchatCMD = self.nsdchatCMD()
    
    cmdString = '%s -c geterror' % nsdchatCMD
    
    errorCMD = subprocess.Popen(cmdString,
                              shell=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              universal_newlines=True)
    errorCMD_stdout,errorCMD_stderr = errorCMD.communicate()

    return errorCMD_stdout.strip()
  
  def predictVolumeBarcodeForLabel(self,label=''):
    '''This function predicts the volume barcode for a label which does not 
    have one associated with it.'''
    
    ## declare vars
    previousFoundBarcode = ''
    previousBarcodeOffset = 0
    nextFoundBarcode = ''
    nextBarcodeOffset = 0
    
    barcodeLabel = self.nsdchatBarcodeForVolumeLabel(label)
    if barcodeLabel:
      return barcodeLabel
    
    ## Find our previous barcode
    currentLabel = int(label)
    while not previousFoundBarcode and not currentLabel <= 0:
      previousBarcodeOffset += 1
      print "previousBarcodeOffset:%s" % previousBarcodeOffset
      currentLabel = int(label) - previousBarcodeOffset
      self.logger('predictVolumeBarcodeForLabel() Looking up barcode for label: %s' % currentLabel)
      previousFoundBarcode = self.nsdchatBarcodeForVolumeLabel(currentLabel)

    self.logger('predictVolumeBarcodeForLabel() Found previous barcode: %s' 
      % previousFoundBarcode,'debug')
      
    ## Find our next barcode
    currentLabel = int(label)
    while not nextFoundBarcode and not currentLabel >= 10000000:
      nextBarcodeOffset += 1
      print "nextBarcodeOffset:%s" % nextBarcodeOffset
      currentLabel = int(label) + nextBarcodeOffset
      self.logger('predictVolumeBarcodeForLabel() Looking up barcode for label: %s' % currentLabel)
      nextFoundBarcode = self.nsdchatBarcodeForVolumeLabel(currentLabel)

    self.logger('predictVolumeBarcodeForLabel() Found next barcode: %s' 
      % nextFoundBarcode,'debug')

    
    ## Determine our previous barcode
    searchRE = re.search('([A-Z]{0,4})([0-9]{2,5})',previousFoundBarcode)
    previousBarcodeAlpha = searchRE.groups()[0]
    previousBarcodeNumber = int(searchRE.groups()[1])
    barcodePredictedFromPrevious = ("%s%05d"
         % (previousBarcodeAlpha,previousBarcodeNumber + previousBarcodeOffset))
    barcodeStartRange = ("%s%05d"
         % (previousBarcodeAlpha,previousBarcodeNumber + 1))
            
    ## Determine our next barcode
    searchRE = re.search('([A-Z]{0,4})([0-9]{2,5})',nextFoundBarcode)
    nextBarcodeAlpha = searchRE.groups()[0]
    nextBarcodeNumber = int(searchRE.groups()[1])
    barcodePredictedFromNext = ("%s%05d"
         % (nextBarcodeAlpha,nextBarcodeNumber - nextBarcodeOffset))
    barcodeEndRange = ("%s%05d"
         % (nextBarcodeAlpha,nextBarcodeNumber - 1))
    
    
    self.logger('predictVolumeBarcodeForLabel() Predicting barcode for label: %s'
      ' Preceding Barcode: %s  Next Barcode: %s Barcode predicted from previous: %s'
      ' Barcode predicted from next: %s' % (label,previousFoundBarcode,
                                              nextFoundBarcode, 
                                              barcodePredictedFromPrevious,
                                              barcodePredictedFromNext),'debug')
    
    message = 'PresStore returned empty barcode for label: %s' % label
    if barcodePredictedFromPrevious == barcodePredictedFromNext:
      message += (', the system has determined that the most likely '
        'barcode is: %s' % barcodePredictedFromNext)
    else:
      message += (', the system could not determine the exact tape, it '
        'should reside on %s - %s' % (barcodeStartRange,barcodeEndRange))
    
    return message
        
  def sendEmail(self,recipient='',subject='',body='',cc=''):
    '''Sends an email with the provided subject and body to the provided 
    recipients. If no recipient is provided, we will load from our config.
    All server settings are loaded from config.'''
    
    
    ## Get our host connection information from our local vars
    host = self.SMTPServer
    port = self.SMTPPort
    smtpuser = self.SMTPUser
    smtppass = self.SMTPPassword
    fromAddress = self.emailFromAddress

    ## Determine our to and cc addresses
    toAddress = ''
    ccAddress = ''
    
    ## If no recipient is explicitely provided, use emailToNotify
    if not recipient:
      toAddress = self.emailToNotify
    else:
      toAddress = recipient
    
    ## If no recipient exists and a cc is provided, use the cc as the primary
    ## recipient
    if not toAddress and cc:
      toAddress = cc
      cc = ''
    elif cc:
      ccAddress = cc
      
    toAddressArray = toAddress.split(',')
    if ccAddress:
      toAddressArray.append(ccAddress)
    
    ## If we still don't have a recipient, bail
    if not toAddress:
      self.logger('Could not send email: both subject and body are empty!','error')
      raise RuntimeError('Could not send email: both subject and body are empty!')
    
    ## If we have no subject or body, bail    
    if not subject and not body:
      self.logger('Could not send email: both subject and body are empty!','error')
      raise RuntimeError('Could not send email: both subject and body are empty!')
    
    ## Open up our connection
    try:
      mymailjob = smtplib.SMTP(host, port)
    except socket.error,msg:
      print "ERROR: Could not connect to host %s:%s, Socket Error: %s" % (host,port,msg)
      return False
    except smtplib.SMTPConnectError,msg:
      print "ERROR: could not connect to host %s:%s, connection refused: %s" % (host,port,msg)
    except:
      print "ERROR: Could not send Email to host %s:%s!" % (host,port)
      return False
    
    # Add the From:, To:, and Subject: headers to our body!
    myBody = ("From: %s\nTo: %s\nSubject: %s\n\n%s\n" % (fromAddress, ", ".join(toAddressArray),subject,body))
    
    ## Attempt to send the mail
    try:
      mymailjob.sendmail(fromAddress, toAddressArray, myBody)
      mymailjob.quit()
    except smtplib.SMTPHeloError,e:
      self.logger("Could not send email, server reported a HELO error: '%s'" % e,'error')
      return False
    except smtplib.SMTPRecipientsRefused,e:
      self.logger("Could not send email, server refused recipients: '%s'" % ",".join(e.recipients),'error')
      return False
    except smtplib.SMTPSenderRefused,e:
      print "ERROR: Could not send email, server refused sender: '%s'" % e
      return False
    except SMTPDataError,e:
      print "ERROR: Could not send mail, server reports Data error: '%s'" % e
      return False
    return True
    
    
class archiveObject(fcsxml.FCSBaseObject):
  '''Our base archive object which represents a single file entity.'''
  
  ## File info
  fcsID = ''
  filePath = ''            ## Path to the file as it exists on the archive dev
  onlinePath = ''          ## Path to the file as it exists when online
  checksum = ''
  action = 'archive'
  
  ## Archive Info
  recordID = ''             ## sqlite rowID
  archiveSetName = ''       ## Selection set name created at time of submission
  archivePath = ''          ## Path to archive device
  jobID = ''                ## Backup system job identifier
  submitDate = ''           ## Date of submission
  archiveDate = ''          ## Date of completion
  restoreDate = ''          ## Date of restore
  didRestore = False        ## Bool value on whether or not we performed a restore from archive.
  label = ''                ## Backup system label
  barcode = ''              ## Tape barcode label
  tapeSet = 'onsite'        ## The name of the tapeSet,'onsite' or 'offsite'
  retryCount = 0            ## archive and restore retry counters: increment
                            ## when an object fails to archive or restore.
  
  statusMap = {}

  status  = ''      
  
  ## State
  isLoaded = False
  isError = False
  statusMessage = ''
  
  configParser = ''
  
  ## Our FCS Object
  def __init__(self,action='archive'):
    self.recordID =''
    self.fcsID = ''
    self.action = action
    self.fcsObject = ''
    self.filePath = ''
    self.archivePath = ''
    self.archiveSetName = ''
    self.jobID = ''
    self.submitDate = ''
    self.archiveDate = ''
    self.restoreDate = ''
    self.didRestore = False
    self.status = ''
    self.isError = False
    self.retryCount = 0
    self.statusMessage = ''
    self.tapeSet = 'onsite'
    self.isLoaded = False
    self.configParser = ''
    
    self.statusMap = fcsArchiver.statusMap
    
        
  def setTapeSet(self,tapeSet):
    '''Set the tapeSet for the object'''
    if tapeSet == 'offsite' and self.action == 'archive':
      self.action = 'offsiteArchive'
    self.tapeSet = tapeSet
  
  def setStatus(self,status):
    '''Set the status for the object'''
    
    statusMap = self.statusMap
    
    ## Pull our passed status out of our statusMap
    validatedStatus = ''
    try:
      validatedStatus = statusMap[self.action][status]
    except:
      for key,value in statusMap[self.action].iteritems():
        if value == status:
          validatedStatus = status
      if not validatedStatus:
        ## If we don't have a validated status at this point, and we are 
        ## an offsite archive, check to see if we were passed an onsite status.
        theKey = ''
        if self.action == 'offsiteArchive':
          for key,value in statusMap['archive'].iteritems():
            if value == status:
              theKey = key
          if theKey:
            validatedStatus = statusMap[self.action][theKey]
        if not theKey:
          self.logger('setStatus() passed unmapped status:%s action:%s tapeSet:%s' % (status,self.action,self.tapeSet),'error')
          validatedStatus = statusMap[self.action]['failed']

    self.logger('setStatus() set status to:%s action:%s' % (validatedStatus,self.action),'debug')
    self.status = validatedStatus

  
  def loadFromXMLFile(self,xmlFilePath=''):
    '''Loads archiveObject based upon a file path. We expect the filepath to 
    represent a FCS XML file, and will load in the appropriate entityID as well
    as perform a checksum of the file.'''
    
    ## Read in XML File and create fcsxml.FCSXMLObject instance
    
    ## Determine the archive path of the file
      ## Get our original device and location
      
      ## Determine our path on the archive device
      
      ## Make sure we have a file 
      
    ## Set our local values
    
  
  def loadForFileAtPath(self,filePath=''):
    '''Loads archiveObject based upon a file path. We expect the filepath to 
    represent a FCS XML file, and will load in the appropriate entityID as well
    as perform a checksum of the file.'''
    
    self.logger('loadForFileAtPath() hit for filePath:%s' % filePath,'debug')
    
    filePath = os.path.abspath(os.path.realpath(os.path.expanduser(filePath)))

    self.filePath = filePath
    
    ## Generate our fcsxml.FCSVRClient object
    myFCSObject = fcsxml.FCSVRClient()
    if self.configParser:
      myFCSVRObject.loadConfiguration(self.configParser)
    
    ## Load our online path
    onlinePath = myFCSObject.getFSPathFromArchivePath(filePath)
  
    ## Calculate our checksum
    if os.path.exists(filePath):
      self.logger('Calculating checksum for file: %s' % filePath,'detailed')
      self.checksum = self.md5sum(filePath)
    
    self.logger('loadForFileAtPath() initing with onlinePath: \'%s\'' % onlinePath,'debug')
    self.logger('Looking up file in FinalCut Server.')
    if myFCSObject.initWithAssetFromFSPath(onlinePath):
      self.fcsID = myFCSObject.entityID
      self.onlinePath = onlinePath
      self.fcsObject = myFCSObject
    else:
      errMSG = ("Could not load fcsxml.FCSVRClient Object from path:'%s',"
        " error:'%s'" % (filePath,myFCSObject.lastError))
      self.logger(errMSG,'error')
      raise fcsxml.FCSObjectLoadError(errMSG)
  
    self.isLoaded = True
    
    return True
  
  def loadFromFCSObject(self,object):
    '''Loads archiveObject from an FCS Object'''
    return True
    
  def loadFCSObject(self):
    '''Loads the archive objects respective FCS object and saves to 
    self.fcsObject'''
    
    ## Generate our fcsxml.FCSVRClient object
    myFCSObject = fcsxml.FCSVRClient()
    if self.configParser:
      myFCSVRObject.loadConfiguration(self.configParser)
      
    fcsID = self.fcsID
    myFCSObject = fcsxml.FCSVRClient(entityType='asset',id=fcsID)
    myFCSObject.initWithAssetID(assetID=fcsID)
    
    self.fcsObject = myFCSObject
    
    return myFCSObject
  
  
  def loadFromSQLResult(self,results):
    '''Load internal values from a sqlite3 result row'''
    
    ##self.logger('loadFromSQLResult() loading with results: %s keys:%s' % (results,results.keys()))
    if 'rowid' in results.keys():
      self.logger('loadFromSQLResult() loading rowid: %s' % results['rowid'],
                                                                  'debug')
      self.recordID = results['rowid']
    else:
      self.logger('loadFromSQLResult() no rowid found in sql results!','error')
    if 'archiveSet' in results.keys():
      self.archiveSetName = results['archiveSet']
    if 'tapeSet' in results.keys():
      self.setTapeSet(results['tapeSet'])
    if 'barcode' in results.keys():
      self.barcode = results['barcode']
    if self.tapeSet == 'offsite' and self.action == 'archive':
      self.action = 'offsiteArchive'
    if 'jobID' in results.keys():
      self.jobID = results['jobID']
    if 'fcsID' in results.keys():
      self.fcsID = results['fcsID']
    if 'filePath' in results.keys():
      self.filePath = results['filePath']
    if 'checksum' in results.keys():
      self.checksum = results['checksum']
    if 'status' in results.keys():
      self.setStatus(results['status'])  
    if 'retryCount' in results.keys():
      self.retryCount = results['retryCount']

    
    
    return True
  
  def fileSize(self):
    '''Returns the file size for the loaded archiveObject'''
    filePath = self.filePath
    onlinePath = self.onlinePath
    
    try:
      if os.path.exists(filePath):
        return os.path.getsize(filePath)
      elif os.path.exists(onlinePath):
        return os.path.getsize(onlinePath)
      else:
        raise
    except:
      raise RuntimeError('File could not be found online, cannot determine size!')
        
  def wasError(self,error='',status='failed'):
    '''This function is called whenever the object fails to archive, set our
    error status, archive status, and clear out our archiveSetName'''
    self.statusMessage = error
    self.isError = True
    self.setStatus(status)
    self.archiveSetName = ''
    self.retryCount += 1
    
    return True
    
    
  def md5sum(self, filePath=''):
    ''"Calculate MD5 checksome of passed file''"
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
      if buffer == '':
        break
      checksum.update(buffer)
    myFile.close()
    return checksum.hexdigest()
    

class archiveSet(fcsxml.FCSBaseObject):
  '''Our base archive object which represents a selection set.'''
  
  ## plan info
  name = ''             ## The name of our plan
  jobID = ''           ## Our jobID as understood by the backup system
  type = 'archive'      ## Our plan type: 'archive' or 'restore'
  
  ## Archive Info
  archiveObjects = []    ## Array of archiveObjects
  errorObjects = []      ## Array of archiveObjects which reported errors
  
  def __init__(self,name='',type='archive',jobID=''):
    if name:
      self.name = name
    else:
      self.name = 'SELECTION_%s' % datetime.datetime.today().strftime("%Y-%m-%d:%H%M")
    self.jobID = jobID
    self.type = type
    self.archiveObjects = []
    self.errorObjects = []

    
  def __str__(self):
    return self.name
  
  def setArchiveSetForArchiveObjects(self,setName):
    '''Updates the archiveSet of all loaded objects to the value supplied. This does
    NOT commit changes to SQL, use 
    fcsArchiver.commitArchiveObjectsInArchiveSet(). This does NOT update the 
    status on objects which report an error'''
    self.logger('Setting archiveSet to:%s for set:%s' % (setName,self.name),'debug')
    for archiveObject in self.archiveObjects:
      if not archiveObject.isError:
        archiveObject.archiveSetName = setName

    return True

  def setActionForArchiveObjects(self,action):
    '''Updates the status of all loaded objects to the value supplied. This does
    NOT commit changes to SQL, use 
    fcsArchiver.commitArchiveObjectsInArchiveSet(). This does NOT update the 
    status on objects which report an error'''
    self.logger('Setting action to:%s for set:%s' % (action,self.name),'debug')
    for archiveObject in self.archiveObjects:
      if not archiveObject.isError:
        archiveObject.action = action

    return True

  def setStatusForArchiveObjects(self,status):
    '''Updates the status of all loaded objects to the value supplied. This does
    NOT commit changes to SQL, use 
    fcsArchiver.commitArchiveObjectsInArchiveSet(). This does NOT update the 
    status on objects which report an error'''
    self.logger('Setting status to:%s for set:%s' % (status,self.name),'debug')
    for archiveObject in self.archiveObjects:
      if not archiveObject.isError:
        archiveObject.setStatus(status)

    return True

  def setJobIDForArchiveObjects(self,jobID):
    '''Updates the jobID of all loaded objects to the value supplied. This does
    NOT commit changes to SQL, use fcsArchiver.commitArchiveObjectsInArchiveSet().
    This does NOT update the status on objects which report an error'''
    self.logger('Setting jobID to:%s for set:%s' 
      % (jobID,self.name),'debug')

    for archiveObject in self.archiveObjects:
      if not archiveObject.isError:
        archiveObject.jobID = jobID

    return True
  
  def getTapeSet(self):
    '''Returns jobID as defined by our loaded objects'''
    ## Todo: this should do a lot more than return the first objects tapeset
    ## Perhaps take a tally of different tapeSets?
    return self.archiveObjects[0].tapeSet  
  
  def setTapeSetForArchiveObjects(self,tapeSet):
    '''Updates the jobID of all loaded objects to the value supplied. This does
    NOT commit changes to SQL, use fcsArchiver.commitArchiveObjectsInArchiveSet().
    This does NOT update the status on objects which report an error'''
    self.logger('Setting tapeSet to:%s for set:%s' 
      % (tapeSet,self.name),'debug')  
    for archiveObject in self.archiveObjects:
      if not archiveObject.isError:
        archiveObject.setTapeSet(tapeSet)

    return
  
  def clearErrorsForArchiveObjects(self):
    '''Clears any error flags set on loaded objects'''
    self.logger('Clearing errors for objects in set:%s' % self.name,'debug')
    for archiveObject in self.archiveObjects:
      archiveObject.isError = False
    
    return 
  
  def wasError(self,error,status=''):
    '''Report an error, update all related objects'''
    for object in self.archiveObjects:
      object.wasError(error=error,status=status)
    
    return True
    
  def getJobID(self):
    '''Returns jobID as defined by our loaded objects'''
    ## Todo: this should do a lot more than return the first objects status
    ## Perhaps take a tally of different status'?
    try:
      jobID = self.archiveObjects[0].jobID  
    except:
      jobID = 0
    return jobID    
    
  
  def getStatus(self):
    '''Returns status as defined by our loaded objects'''
    ## Todo: this should do a lot more than return the first objects status
    ## Perhaps take a tally of different status'?
    return self.archiveObjects[0].status
    
  def getRetryCount(self):
    '''Returns retryCount as defined by our loaded objects'''
    ## Todo: this should do a lot more than return the first objects count
    ## Perhaps take a tally of different retryCount'?
    return self.archiveObjects[0].retryCount

class PresStoreCorruptDataError(Exception):
  def __init__(self,error):
    self.error = error
  def __str__(self):
    return repr(self.error)

class PresStoreJobSubmissionError(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

class FileNotFoundError(Exception):
  def __init__(self, value):
    self.value = value

class FCSArchiverUnknownBackupSystem(Exception):
  pass

class FCSArchiveVolumeNotFound(Exception):
  pass

class FCSArchiveFileNotFoundInIndex(Exception):
  def __init__(self,filePath='',archiveDatabase=''):
    self.filePath = filePath
    self.archiveDatabase = archiveDatabase
  def __str__(self):
    message = "Could not find archive index for filePath: '%s'" % self.filePath
    if (self.archiveDatabase):
      message += " using archive database: '%s'" % self.archiveDatabase
    return repr(message)

class FCSArchiveFileSubmitError(Exception):
  def __init__(self, error=''):
    self.error = error
  def __str__(self):
    if self.error:
      error = self.error
    else:
      error = 'Failed to submit file to archive!'
    return repr(error)
    
class FCSArchiveEmptyQueueError(Exception):
  def __init__(self, error=''):
    self.error = error
  def __str__(self):
    if self.error:
      error = self.error
    else:
      error = 'Queue has no files to archive!'
    return repr(error)

######################### START FUNCTIONS ###############################

def helpMessage():
    print '''Usage: 
  
  fcsArchiver [option]
    
Options: 
    -h, --help                   Displays this help message
    -v, --version                Display version number
    -f configfilepath,           Use specified config file
      --configFile=configfilepath
    -p, --processQueue           Process archive and restore queues
        --processRestoreQueue    Process restore queues
        --processArchiveQueue    Process archive queues
        
    --getVolumeBarcode           Lists volume barcode for the requested file
    --getVolumeLabel             (must be used with --file option)
    --file='/path/to/file'
    
    --getVolumeBarcodeForFile=   Outputs barcode for specified file
    --getVolumeLabelForFile=     Outputs label for specified file
    --getVolumeBarcodeForLabel=  Outputs the barcode for the specified label

Examples:
  fcsArchiver --processArchiveQueue
  fcsArchiver --getVolumeBarcode --file='/myfile.txt'
  fcsArchiver --getVolumeBarcodeForFile='/myfile.txt'
  fcsArchiver --getVolumeBarcodeForLabel=10001
  
   '''

def printVersionInfo():
  '''Prints out version info'''
  
  print ("\nFCS Archiver\n  Version: %s Build: %s\n"
        "  Framework Version: %s Build: %s\n\n"
        "Copyright (C) 2009-2011 Beau Hunter, 318 Inc.\n" % (version,build,
                                                        fcsxml.version,
                                                        fcsxml.build))

def main():
  '''Our main function, filters passed arguments and loads the appropriate object'''
  
  ## Init vars
  supportPath = ''
  configFilePath = '/usr/local/etc/fcsarchiver.conf'
  actions = []          ## used to spool actions
  filePath = ''         ## used when file-specific action is requested
  tapeSet = 'onsite'    ## used when querying archive informaiton.
  volumeLabel = ''      ## used when querying archive volume information
  exitCode = 0          ## used for tracking errors during processing
  

  ## Get our flags
  try:
    optlist, list = getopt.getopt(sys.argv[1:],':hvpf::',['processQueue',
    'processRestoreQueue','processArchiveQueue','help',
      'configFile=','tapeSet=','version',
      'getVolumeBarcode','getVolumeLabel','file=',
      'getVolumeBarcodeForFile=','getVolumeLabelForFile=',
      'getVolumeBarcodeForLabel='])
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
    elif opt[0] == '-f' or opt[0] == '--configFile':
      configFile = opt[1]
      if not os.path.isfile(configFile):
        print 'Config file does not exist at path:%s' % configFile
        return 2
    elif opt[0] == '-p' or opt[0] == '--processQueue':
      actions.append('processQueue')
    elif opt[0] == '--processArchiveQueue':
      actions.append('processArchiveQueue')
    elif opt[0] == '--processRestoreQueue':
      actions.append('processRestoreQueue')
    elif opt[0] == '--getVolumeLabelForFile':
      actions.append('getVolumeLabelForFile')
      filePath = opt[1]
    elif opt[0] == '--getVolumeBarcodeForFile':
      actions.append('getVolumeBarcodeForFile')
      filePath = opt[1]
    elif opt[0] == '--getVolumeLabel':
      actions.append('getVolumeLabelForFile')
    elif opt[0] == '--getVolumeBarcode':
      actions.append('getVolumeBarcodeForFile')
    elif opt[0] == '--getVolumeBarcodeForLabel':
      actions.append('getVolumeBarcodeForLabel')
      volumeLabel = opt[1]
    elif opt[0] == '--file':
      filePath = opt[1]
    elif opt[0] == '--tapeSet':
      tapeSet = opt[1].tolower()
      
  ## Read in our config file data
  ## If no config file was specified or doesn't exist, look in PWD
  if not configFilePath or not os.path.isfile(configFilePath):
    configFilePath = 'fcsArchiver.conf'
        
  ## Make sure the config file we plan to use exists and can be read by our parser
  cfgParser = ''
  if os.path.isfile(configFilePath):
    try:
      cfgParser = ConfigParser.SafeConfigParser()
      cfgParser.read(configFilePath)
    except:
      raise
      print 'Error! Could not read global attributes from file at path: \'%s\' Error: %s' % (configFilePath,sys.exc_info()[0])
      return 2
  else:
    print 'Error! Could not find valid configuration file at /usr/local/etc/fcsArchiver.conf'
    return 2
  
  ## Create our fcsArchiver object
  
  fcs = fcsArchiver()  
  try:
    fcs.loadConfiguration(cfgParser)
  except:
    print 'An error occured processing our config file: %s' % configFilePath
    raise
    return 2
  
  ## Do our work, make sure we have actions specified.
  if len(actions) == 0:
    print 'No action was provided!'
    return 3

  ## Process Queues  
  if ('processQueue' in actions 
  or 'processArchiveQueue' in actions 
  or 'processRestoreQueue' in actions):    
    if 'processQueue' in actions or 'processRestoreQueue' in actions:
      ## Process our restore queues first
      fcs.logger('Processing Restore Queues...')
      fcs.logOffset += 1
      try:
        fcs.loadRestoreQueue()
        fcs.processRestoreQueue()
      except FCSArchiveEmptyQueueError,err:
        fcs.logger('Restore Queue is empty.')
      '''except Exception, err:
        print 'ERROR: An unknown error occured: %s' % err'''
        
      fcs.logOffset -= 1
      fcs.logger('Checking for new restore files...')
      fcs.logOffset += 1   
      try:
        fcs.createRestoreQueueFromFile()
        fcs.loadRestoreQueue()
        fcs.restoreFilesFromQueue()        
      except FCSArchiveEmptyQueueError,err:
        fcs.logger('Restore Queue is empty.')
      '''except Exception, err:
        print 'ERROR: An unknown error occured: %s' % err'''
      fcs.logOffset -= 1
      fcs.logger('Finished processing all restore queues.')

    
    if 'processQueue' in actions or 'processArchiveQueue' in actions:
      ## Process our archive queues
      fcs.logger('Processing Archive Queues...')
      fcs.logOffset += 1
      try:
        fcs.loadArchiveQueue()
        fcs.processArchiveQueue()
      except FCSArchiveEmptyQueueError,err:
        fcs.logger('Archive Queue is empty.')
      '''except Exception, err:
        print 'ERROR: An unknown error occured: %s' % err'''
      
      fcs.logOffset -= 1
      fcs.logger('Checking for new archive files...') 
      fcs.logOffset += 1

      try:
        fcs.createArchiveQueueFromFile()
        fcs.loadArchiveQueue()
        fcs.archiveFilesFromQueue()
      except FCSArchiveEmptyQueueError,err:
        fcs.logger('Archive Queue is empty.')
      '''except Exception, err:
        print 'ERROR: An unknown error occured: %s' % err'''
      fcs.logOffset -= 1
      fcs.logger('Finished processing all archive queues.')

  
  ## Request archive information
  if 'getVolumeLabelForFile' in actions or 'getVolumeBarcodeForFile' in actions:
    if not filePath:
      print 'Error: specified action requires a filepath!'
      return 3
    
    if 'getVolumeLabelForFile' in actions:
      try:
        myVolumeLabel = fcs.nsdchatVolumeLabelForFilePath(filePath=filePath,tapeSet=tapeSet)
        print 'LABEL: %s' % myVolumeLabel
      except FCSArchiveVolumeNotFound:
        print ('No entry could be found in index for file:\'%s\' using tapeset:\'%s\''
          % (filePath,tapeSet))
        exitCode = 19
      except FCSArchiveFileNotFoundInIndex:
        print ('No entry could be found in index for file:\'%s\' using tapeset:\'%s\''
          % (filePath,tapeSet))
        exitCode = 21
      except Exception, err:
        print 'An error occured reading volume label: %s' % err
        exitCode = 20
    if 'getVolumeBarcodeForFile' in actions:
      try:
        myVolumeLabel = fcs.nsdchatVolumeLabelForFilePath(filePath=filePath,tapeSet=tapeSet)
        volumeBarcode = fcs.nsdchatBarcodeForVolumeLabel(label=myVolumeLabel)
        if myVolumeLabel and not volumeBarcode:
          volumeBarcode = fcs.predictVolumeBarcodeForLabel(label=myVolumeLabel)
        print 'BARCODE: %s' % volumeBarcode
      except FCSArchiveVolumeNotFound:
        print ('No entry could be found in index for file:\'%s\' using tapeset:\'%s\''
          % (filePath,tapeSet))
        exitCode = 19
      except FCSArchiveFileNotFoundInIndex:
        print ('No entry could be found in index for file:\'%s\' using tapeset:\'%s\''
          % (filePath,tapeSet))
        exitCode = 21
      except Exception, err:
        print 'An unknown error occured reading volume barcode: %s' % err
        exitCode = 25
  
  if 'getVolumeBarcodeForLabel' in actions:
    if not volumeLabel:
      print 'Error: specified action requires a filepath!'
      return 3
    try:
      volumeBarcode = fcs.nsdchatBarcodeForVolumeLabel(label=volumeLabel)
      if volumeLabel and not volumeBarcode:
          volumeBarcode = fcs.predictVolumeBarcodeForLabel(label=volumeLabel)
      print '%s_BARCODE: %s' % (volumeLabel,volumeBarcode)
    except FCSArchiveFileNotFoundInIndex:
      print ('No entry could be found in index for file:\'%s\' using tapeset:\'%s\''
        % (filePath,tapeSet))
      exitCode = 21
    except Exception, err:
      print 'An unknown error occured reading volume barcode: %s' % err
      exitCode = 25

                    
  ## Return our stored exit code.
  return exitCode
  
## If we called this file directly call main()
if __name__ == '__main__':
    sys.exit(main())
 
