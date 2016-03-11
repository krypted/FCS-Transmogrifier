#!/usr/bin/python
# -*- coding: utf-8 -*-


################################
##
##  Transmogrifier: fcsxml
##  A Final Cut Server import/export tool 
##
##  
##  This module provides the primary interface for reading and interpreting FCS 
##  generated XML. This class provides also methods which assist in the
##  conversion of FCS XML and media files to a third party format. 
##
##  This code is made available via the GPL3 license as part of the Transmogrifier
##  project available at:
##  http://sourceforge.net/projects/transmogrifier/
##
#############################################################


import sys,os.path,shutil,subprocess
import re,datetime,time,tempfile,copy
import urllib, plistlib
import codecs
from ConfigParser import *
from xml.dom import minidom


version = '1.0b'
build = '2011042001'

class FCSBaseObject:
  '''FCSBaseObject is the Transmogrifier root object upon which all other 
  classes extent. It provides basic error logging capabilities.'''
  
  ## Base vars
  entityType = ''
  entityID = 0
  
  
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
  
  timezoneOffset = 7
  
  def __init__(self):
    '''Our construct.'''
    self.log = []
    self.lastError = ''
    self.lastMSG = ''
    self.debug = False
    self.keepFiles = False
    self.isError = False
    self.logOffset = 1
    self.printLogs = False
    self.printLogDate = True
    self.printClassInLog = False
    
  def entityPath(self):
    '''This function will output the Final Cut Server absolute path for 
    the loaded object.
    
    :returns: (( str)) -- the entity path (i.e. /asset/12).
    :raises: :class:`fcsxml.FCSObjectLoadError`
    '''
    if self.entityType and self.entityID:
      entityPath = '/%s/%s' % (self.entityType,self.entityID)
    else:
      message = 'Could not determine entityPath, entityType or entityID not set!'
      self.logger(message,'error')
      raise FCSObjectLoadError(message)
      
    return entityPath    
    
  def logger(self,logMSG,logLevel='normal',printClassInLog=None):
    '''Provides a basic Logging Function. Prints our message to standard out
    based upon our configured log level.
      
    :param logMSG: The log message
    :type logMSG: str
    :param logLevel: The logging level of the parameter ('normal','debug','error')
    :type logLevel: str
    :param printClassInLog: Flag for whether we will print the class name in our logging output
    :type printClassInLog: bool
    
    :returns: bool - Always returns True
    
    .. note::
    
      At some point we should probably migrate to msg module
      
    '''
            
    if (logLevel == 'error' 
    or logLevel == 'normal' 
    or logLevel == 'detailed' 
    or self.debug):
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
        
        if self.printLogs or self.debug:
          if printClassInLog == None:
            printClassInLog = self.printClassInLog
          
          if printClassInLog:
            print '%s%s: %s' % (headerText,self.__class__.__name__,logMSG)
          else:
            print '%s%s' % (headerText,logMSG)
            
          sys.stdout.flush()
        self.lastMSG = logMSG
    
    if logLevel == 'error':
        self.lastError = logMSG
    self.log.append({'logLevel' : logLevel, 'logMSG' : logMSG})
  
  def logs(self,logLevel=''):
    '''Returns a list of stored log entries.
    
    :param logLevel: Limit returned log entries to those matching this log level.
    :type logLevel: str
    
    :returns: ((list)) -- List of log entries, each entry is a dictionary with keys: logMSG and logLevel
    '''
    
    returnedLogs = []
    logs = self.log
    for log in logs:
      if logLevel and logLevel.lower() == log['logLevel'].lower():
        returnedLogs.append(log)
  
  def printLogs(self, logLevel='all'):
    '''Prints all stored log entries.
    
    :param logLevel: Specify a log level to limit output.
    :type logLevel: str
    
    '''
    
    for log in self.log:
        if logLevel == 'all' or logLevel == log['logLevel']:
            print 'fcsvr_xml:%s:%s' % (log['logLevel'], log['logMSG'])
  
  def lastError(self):
    '''Returns last logged error.
    
    :returns: (dict) -- Log dict with keys: logMSG and logLevel'''
    errorLogs = self.logs('error')
    return errorLogs[len(errorLogs)]


class FCSXMLField(FCSBaseObject):
  '''This object is representative of a field in Final Cut Server. It is used to 
  store field name, the underlying FCS database field name, and the field value.
  This object provides basic data sanity checking and data formatting.
  
  :param name: The field display name.
  :type name: str
  :param value: The field value
  :type value: id
  :param dataType: The field datatype
  :type dataType: str
  :param dbname: The underlying Final Cut Server database field
  :type dbname: str
  :param dbDataType: The underlying Final Cut Server field datatype
  :type dbDataType: str
  
  :raises: :class:`fcsxml.FCSValidationError`
  
  .. note::
  
    If both are specified provided, The value dbDataType will take presidence over
    the provided dataType.
  '''
  
  name = ''
  dbname = ''
  value = ''
  dataType = ''
  dbDataType = ''
  
  dataTypeLoaded = False
  valueLoaded = False
  
  validDataTypes = { 'string' : 'KtString32','varchar' : 'KtString','int':'KtInt',
      'integer':'KtInt','int64':'KtInt64','bigint':'KtInt64','dateTime':'KtDateTime',
      'timestamp':'KtDateTime','timecode':'PxTimecode','float':'KtReal','coords':'KtIntXY',
      'fraction':'KtFraction','bool':'KtBool','list':'KtMdValueMap' }
  
  def __init__(self, name='', value='', dataType='',dbname='',dbDataType=''):
    '''Our construct which allows us to set our field name, dbname, datatype,
    or db datatype
    '''
    
    FCSBaseObject.__init__(self)
          
    self.name = name
    self.dbname = dbname
    self.dataType = ''
    self.dbDataType = ''
    if dataType:
      self.setDataType(dataType)
    if dbDataType:
      self.setDBDataType(dbDataType)
      
    self.setValue(value)
    
    self.dataTypeLoaded = False
    self.valueLoaded = False
    
    self.debug = False
     
  def __str__(self):
    '''Output our field name for string operations.
    :returns: (str) -- The field name. 
    '''
    
    return "FCS Field: %s" % self.name
    
  def setDataType(self,dataType):
    '''This method will set this field to the specified dataType. It will also
    populate the value for dbDataType based upon the provided value.
    
    :param dataType: The datatype to set for this field.
    :type dataType: str
    
    :raises:  RuntimeError
    
    The following table shows acceptable datatypes and their corresponding
    Final Cut Server data types.
    
    =========  =======================================
    DataType   Final Cut Server Data Type (dbDataType)
    =========  =======================================
    string     KtString32
    varchar    KtString
    int        KtInt
    integer    KtInt
    int64      KtInt64
    bigint     KtInt64
    dateTime   KtDateTime
    timestamp  KtDateTime
    timecode   PxTimecode
    float      KtReal
    coords     KtIntXY
    fraction   KtFraction
    bool       KtBool
    list       KtMdValueMap
    =========  =======================================
    '''
    if dataType in self.validDataTypes:
      if dataType == 'integer':
        dataType = 'int'
      elif dataType == 'timestamp':
        dataType = 'dateTime'
      self.dataType = dataType
      self.dbDataType = self.validDataTypes[dataType]
      self.dataTypeLoaded = True
    else:
      raise FCSValidationError('dataType:%s is not defined!' % dataType)
  
  def setDBDataType(self,dbDataType):
    '''This method will set this field to the represent specified dbDataType 
    (The underlying Final Cut Server database field name). This method will also
    populate the value for dataType based upon the provided value. Please refer
    to table shown in :func:`fcsxml.FCSXMLField.setDataType` for acceptable
    dbDataType values.
    
    :param dbDataType: The datatype to set for this field.
    :type dbDataType: str
    
    :raises: :class:`fcsxml.FCSValidationError`
    
    .. note:: 
      KtAtom and KtAtomList datatypes are not supported.
    
    '''
    
    dataType = ''
    for key,value in self.validDataTypes.iteritems():
      if value == dbDataType:
        dataType = key
    
    if dataType:
      self.dataType = dataType
      self.dbDataType = dbDataType
      self.dataTypeLoaded = True
    else:
      if dbDataType == 'KtAtom' or dbDataType == 'KtAtomList':
        print 'Fields with type: %s are not currently supported!' % dbDataType
        return False
      else:
        raise RuntimeError('dbDataType:%s is not defined!' % dbDataType)
      
  def setValue(self,newValue):
    '''Method which will set our field's internal value. This method will
    perform validation checking and enforce conformity when appropriate.
    
    :param newValue: The new value to assign to the field.
    :type newValue: id
    
    :raises: :class:`fcsxml.FCSValidationError`

    
    '''
    
    dataType = self.dataType
    myDateTime = ''
    adjustTimeZone = False
    
    ## String can be either string or varChar
    if dataType == 'string' or dataType == 'varchar':
      self.value = '%s' % newValue
    elif dataType == 'int64':
      if newValue:
        self.value = int(newValue)
      else:
        self.value = 0
    elif dataType == 'dateTime':
      if not newValue or newValue == 'now()':
        newValue = datetime.datetime.now()
        adjustTimeZone = True
        
      inDateTimeFormats = ['%Y-%m-%d %H:%M:%S+0',
                              '%Y-%m-%d %H:%M:%SZ',
                              '%Y-%m-%d %H:%M:%S',
                              '%Y-%m-%dT%H:%M:%SZ',
                              '%Y-%m-%dT%H:%M:%S']
      outDateTimeFormat = '%Y-%m-%dT%H:%M:%SZ'
      if newValue.__class__.__name__ == 'datetime':
        myDateTime = newValue
      else:
        count = 0
        while count < len(inDateTimeFormats) and not myDateTime:
          self.logger('Testing Pattern: \'%s\' against string: \'%s\'' % (inDateTimeFormats[count],newValue),'debug')
          try:
            myDateTime = datetime.datetime.strptime('%s' % newValue,inDateTimeFormats[count])
            if (not newValue[len(newValue)-1:len(newValue)] == 'Z'
            or not newValue[len(newValue)-2:len(newValue)] == '+0'):
              adjustTimeZone = True
          except:
            pass
          count += 1
      
      ## Account for timezone changes (FCS stores timestamps in UTC)
      if myDateTime:
        if adjustTimeZone:
          myDateTime = myDateTime + datetime.timedelta(hours=self.timezoneOffset)
        self.value = myDateTime.strftime(outDateTimeFormat)
      else:
        raise FCSValidationError('Could not conform string to a valid'
          ' datetime', fieldName = self.name,value = newValue) 

    elif dataType == 'bool':
      ##self.logger("setValue() BOOL FIELD:%s HIT WITH VALUE: %s " % (self.name,newValue),'debug')
      if (type('') == type(newValue) or type(u'') == type(newValue)):
        if (newValue.lower() == 'true'):
          self.value = True
        else:
          self.value = False
      elif type(1) == type(newValue):
        if newValue > 0:
          self.value = True
        else:
          self.value = False
      elif type(True) == type(newValue):
        self.value = newValue
      else:
        self.logger("setValue() ACK!! ERRORRRRRz: given type:%s" % type(newValue),'debug')
        validationInfo = ('BOOL Field must be provided a boolean value, an '
          'integer value (0 or 1) or a string value (\'true\' or \'false\')')
        raise FCSValidationError(fieldName=self.name,
                                  value=newValue,
                                  dataType=self.dataType,
                                  validationInfo=validationInfo)
      
      
      self.logger("setValue() - USING VALUE: %s " % self.value,'debug')

    else:
      self.value = '%s' % newValue
  
    self.valueLoaded = True
    return True
      
  def printInfo(self):
      '''Output basic field info, including name, stored value, datatype,
      dbDataType, and dbname.
      
      :returns: (*str*) -- Basic field information
      
      '''
      print ('FieldName: %s\n Value: %s\n DataType: %s\n dbDataType: %s\n'
        ' dbname: %s\n' % (self.name,self.value,self.dataType,
                                    self.dbDataType,self.dbname))
        
class FCSXMLObject(FCSBaseObject):
  '''FCSXMLObject represents a Final Cut Server entity which uses 
  Final Cut Server Read XML and Write XML watcher+response systems for RPC.
  This object can only perform a small subset of the tasks that 
  :class:`fcsxml.FCSVRClient` can perform.
  
  :param entityID: Provide the entity id
  :type entityID: int
  :param entityType: Provide entity type, usually 'asset' or 'project' [default 'asset']
  :type entityType: str
  :param configParser: An optional :mod:`ConfigParser` object to configure 
                        default behavior. Alternatively this can be a file
                        system path to a configuration file to load
  :type configParser: :class:`ConfigParser.SafeConfigParser` or str
  
  '''
  
  entityID = 0
  entityType = 'asset'
  path = ''
  fcsXMLinDir = ''
  fcsXML = ''  
  fields = {}
  deviceDict = {}
  lastError = ''
  log = []
  overwriteExistingFiles = True
  debug = False
  configParser = ''
    
  def __init__(self,entityID=0,entityType='asset',id=0,configParser=''):
    '''construct function, can be called with a specified integer id'''
    FCSBaseObject.__init__(self)
    if entityID:
      self.entityID = entityID
    elif id:
      self.entityID = id
    self.entityType = entityType
    self.path = ''
    self.fcsXML = ''    
    self.fields = {}
    self.deviceDict = {}
    self.lastError = ''
    self.log = []
    self.fcsXMLinDir
    self.configParser = ''
    
    if configParser:
      if type('string') == type(configParser):
        self.loadConfiguration(filePath=configParser)
      else:
        self.loadConfiguration(parser=configParser)
    
  def setFile(self,filePath):
    '''Historical method, use loadFromFile()'''
    return self.loadFromFile(filePath)
  
  def loadConfiguration(self, parser=None,filePath=None):
    '''This method will load internal parameters as specified in the
    provided :class:`ConfigParser.SafeConfigParser` object, or via the 
    configuration file referenced via the filePath parameter.
    
    :param parser: A configuration object.
    :type parser: :class:`ConfigParser.SafeConfigParser`
    :param filePath: An absolute path to a configuration file.
    :type filePath: str
        
    
    .. note:: 
      If you subclass, you should call this parent function. If we raise a 
      RuntimeError Exception, you should abort or perform your own 
      exhaustive sanity checks
      
    '''
    
    if not isinstance(parser,ConfigParser) and not filePath:
      message = 'loadConfiguration() Not passed a valid ConfigParser Object!'
      self.logger(message, 'error')
      raise RuntimeError(message)
    elif not isinstance(parser,ConfigParser):
      if not filePath:
        filePath = '/usr/local/etc/transmogrifier.conf'
      self.logger('Loading configuration from filepath: %s' % filePath,'debug')
      parser = SafeConfigParser()
      parser.read(filePath)
      
    try:
      self.configParser = parser
      
      ## Get Debug status, first from FCSVRClient section, then from global
      try:
        self.printLogs = parser.getboolean('GLOBAL','printLogs') 
      except:
        pass
      try:
        self.debug = parser.getboolean('GLOBAL','debug')
      except:
        pass
      try:
        self.path = parser.get('GLOBAL','path')
      except:
        pass
      try:
        self.keepFiles = parser.getboolean('GLOBAL','keepFiles')
      except:
        pass
    except:
       self.logger('loadConfiguration() Problem loading configuration records, please double check your configuration', 'error') 
    return True
  
  def loadFromFile(self,filePath):
    '''This function will load the object based upon values present in
    the XML file found at the provided filepath. 
    
    :param filePath: The path to the XML file to load.
    :type filePath: str
    
    :returns: (*bool*) True or False
    
    '''
    
    filePath = os.path.abspath(os.path.realpath(os.path.expanduser(filePath)))
    
    ## todo: get entityType 
    if os.path.exists(filePath):
      self.path = filePath
      self.fcsXML = minidom.parse(filePath).documentElement
      self.logger('Loading XML from File: %s' % filePath, 'info')
      return self.loadXML()
    else:
      self.logger('File does not exist at path: %s, exiting!' % filePath, 'error')
      
                                      
  def getXMLNodeText(self, nodes):
    '''This function accepts a list of xml.dom.minidom nodes and
    will return a collated text string comprised of each nodes value.
    
    :param nodes: 
    :type nodes: list
    
    :returns: (*str*) -- Concatenated string of all passed nodes'
      text values.
    
    '''
    text = ''
    for node in nodes:
      if node.nodeType == node.TEXT_NODE:
        text = text + node.data
    return text

  def loadFromFCSVRClient(self,fcsvrClient):
    '''This function will load our object based upon values stored in the
    provided FCSVRClient object, this is limited to entityID, entityType
    and defined fields.
    
    :param fcsvrClient: Provide a loaded FCSVRClient object
    :type fcsvrClient: fcsxml.FCSVRClient
    
    :raises: FCSObjectLoadError
    
    '''
    
    try:
      self.entityID = fcsvrClient.entityID
      self.entityType = fcsvrClient.entityType
      self.fields = fcsvrClient.fields
      if fcsvrClient.configParser:
        self.loadConfiguration(parser=fcsvrClient.configParser)
    except:
      message = 'An error occured loading from the object'
      self.logger(message,'error')
      raise FCSObjectLoadError(message)
    
  def loadXMLFromString(self,xmlString=''):
    '''This method allows our object to load based on the provided XML 
    string. This method utilizes :func:`fcsxml.FCSXMLObject.loadXML`
    to initiate the object.
    
    :param xmlString: Provide a string of XML data.
    :type xmlString: str
    
    :raises: See :func:`mindom.parseString`
    
    '''
    
    if xmlString:
      try:
        self.fcsXML = minidom.parseString(xmlString).documentElement
      except:
        self.logger('An error occurred reading in xmlString, could not create'
        + ' minidom object!','error')
        self.logger("\n########  XML String ######\n'%s'\n######  END XML String #####" % xmlString,'debug')
        return False
    else:
      self.logger('loadXMLFromString() failed! Provided string is empty!','error')
      return False
    
    return self.loadXML()
    
    
  def loadXML(self, xml=''): 
      '''Method which loads our object based upon our stored xml.dom.minidom
      object, which is loaded by 
      :func:`fcsxml.FCSXMLObject.loadFromFile` 
      or :func: `fcsxml.FCSXMLObject.loadXMLFromString` 
      
      :param xml: Provide an XML dom.minidom object for which to load from.
      :type xml: xml.dom.minidom
      
      :raises: FCSObjectLoadError
      
      :returns: (*bool*) True
      
      '''
      self.logger('Loading XML!','debug')
      
      if not xml:
          if not self.fcsXML:
              self.logger('loadXML() XML could not be loaded!', 'error')
              raise FCSObjectLoadError
          else:
              xml = self.fcsXML
      try:
        entity = xml.getElementsByTagName('entity')[0]
        self.entityType = entity.attributes['entityType'].value
        self.entityID = re.sub(r'\/asset\/(\d*?)',r'\1',entity.attributes['entityId'].value)
      except:
        ##self.logger('Error reading XML format, attempting to read FCS WriteXML format','warning')
        #try:
        entity = xml.getElementsByTagName('params')[0]
        requestEntity = xml.getElementsByTagName('request')[0]
        self.entityType = re.sub(r'\/(.*)\/(.*)',r'\1',requestEntity.attributes['entityId'].value)
        self.entityID = re.sub(r'\/(.*)\/(.*)',r'\2',requestEntity.attributes['entityId'].value)
        
        #except:
        #  self.logger('Failed reading FCS WriteXML format, cannot read XML','error')
        #  return False
      
      fields = entity.getElementsByTagName('mdValue')
      for field in fields:
        if len(field.childNodes) > 0:
          theField = FCSXMLField(name=field.attributes['fieldName'].value, 
              value=self.getXMLNodeText(field.childNodes),
              dataType=field.attributes['dataType'].value)
        else:
          theField = FCSXMLField(name=field.attributes['fieldName'].value, 
              value='',
              dataType=field.attributes['dataType'].value)            
        
        self.fields[field.attributes['fieldName'].value] = theField
        ##self.lastError = 'Loaded Key:', theField.name
      return True
    
  def valueForField(self, fieldName):
    '''This method returns the stored value for the passed database field name.
    (i.e. "My Field")
      
      :param fieldName: Provide the name of the field to query.
      :type fieldName: str
    
      :raises: fcsxml.FCSFieldNotFoundError
      :returns: (*str*) Value for the specified field
  
    '''
    if not fieldName in self.fields:
      self.logger('valueForField()  No Field with key: %s exists!' % fieldName, 'warning')
      raise FCSFieldNotFoundError(fieldName)
    else:
      theField = self.fields[fieldName]
      if theField.dataType == 'timecode':
        ## return timecode in seconds
        tempValue = theField.value.replace( '.', ':' )
        tempValue = tempValue.replace( ';', ':' )
        tempValue = tempValue.replace(',',':')
        tempValueArray = tempValue.split(':')
        
        hours = int(tempValueArray[0])
        minutes = int(tempValueArray[1])
        seconds = int(tempValueArray[2])
        frames = int(tempValueArray[3])
        
        ## need to extrapolate framerate to get seconds-per-frame
        frameRate = float(self.valueForField('Video Frame Rate'))
        if frameRate:
          frameSeconds = (frames/frameRate)
        
        
        totalSeconds = (hours * 60 * 60) + (minutes * 60) + seconds + frameSeconds
        return totalSeconds
      else:
        return theField.value
  
  def dataTypeForField(self, fieldName):
    '''This method returns the datatype for the passed field name.
    
    :param fieldName: Provide the name of the field to query.
    :type fieldName: str
    
    :raises: fcsxml.FCSFieldNotFoundError
    
    :returns: (*str*) Datatype for the specified field
    
    
    '''
    if not fieldName in self.fields:
      self.logger('dataTypeForField()  No Field with key: %s exists!' % fieldName, 'warning')
      raise FCSFieldNotFoundError(fieldName)
    else:
      theField = self.fields[fieldName]
      if not theField.dataType:
        theField.dataType = 'string'
      return theField.dataType
     
  def fieldWithName(self, fieldName):
    '''This method returns the :class:`fcsxml.FCSXMLField` object for the
    passed field name.
    
    :param fieldName: Provide the name of the field to query.
    :type fieldName: str
    
    :raises: fcsxml.FCSFieldNotFoundError
    
    :returns: (*fcsxml.FCSXMLField*) -- The stored field object for the 
      specified field
    
    '''
    if not fieldName in self.fields:
      self.logger('fieldWithName()  No Field with key: %s exists!' % fieldName, 'warning')
      raise FCSFieldNotFoundError(fieldName)
    else:
      theField = self.fields[fieldName]
      return theField
        
  def setField(self, field):
    '''This method register's the provided FCSXMLField object, replacing 
    existing field object with same name if it should exist.
    
    :param field: Provide an FCSXMLField object loaded with field name and 
      value
    :type field: fcsxml.FCSXMLField
    
    :returns: (*bool*) True or False
    
    '''
    if field.__class__.__name__ != 'FCSXMLField':
      self.logger('setField() Passed invalid data! Expects FCSXMLField', 'error')
      return False
    else:
      self.fields[field.name] = field
  
  def appendField(self, field):
    '''This method will add a new FCSXMLField to the objects field definition
    list. This function will raise an FCSDuplicate exception if a field 
    object with same name already exists.
    
    :param field: Provide an FCSXMLField object loaded with field name and 
      value
    :type field: fcsxml.FCSXMLField
    
    :returns: (*bool*) True or False
    
    :raises: fcsxml.FCSDuplicateError, RuntimeError
    
    '''
    
    if field.__class__.__name__ != 'FCSXMLField':
      message = 'appendField() Passed invalid data! Expects FCSXMLField'
      self.logger(message, 'error')
      raise RuntimeError(message)
        
    if field.name in self.fields:
      message = 'appendField() Field with name: %s already exists!' % field.name
      self.logger(message, 'error')
      raise FCSDuplicateError(message)
    else:
      self.fields[field.name] = field
     
  def appendValueForField(self,fieldName,value,useTimestamp=False):
    '''Appends a value to field, concatenating with the current field value.
    
    :param fieldName: Provide the field name
    :type fieldName: str
    :param value: Provide the value to append.
    :type value: id
    :param useTimeStamp: If set to true, we will prepend a timestamp to the
      data to be appended.
    :type useTimeStamp: bool
    
    :raises: fcsxml.FCSFieldNotFoundError
    
    .. note: String fields will be concatenated, integer fields will be
      summed, other field types might not work out so well (test!) 
    
    '''
    
    if not fieldName in self.fields:
      message = ('valueForField() No Field with key:\'%s\' exists! '
          'Attempting to load' % fieldName)
      raise FCSFieldNotFoundError(message)
      self.logger(message, 'warning')
        
        
    theField = self.fields[fieldName]
    
    if theField.dataType == 'integer':
      newValue = theField.value + value
    else:
      
      ## Get current field and value       
      currentValue = theField.value
      newValue = value
              
      ## Add a line return. 
      if currentValue:
        currentValue += "\n"
      ## If we are set to use a timestamp, prepend it to the new value
      if useTimestamp:    
        currentTime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        newValue = '%s:  %s' % (currentTime,newValue)    
        self.logger('appendValueForField() Appending timestamp to new value:%s' 
          % (newValue),'debug')
      
      newValue = "%s%s\n" % (currentValue,newValue)
    
    
    theField.setValue(newValue)
    return

                    
  def removeFieldWithName(self, fieldName):
    '''Remove FCSXMLField object registered with passed field name. 
    
    :param fieldName: Provide the field name (or an FCSXMLField object) to 
      be removed from the current object's field list.
    :type fieldName: str or fcsxml.FCSXMLField
    :raises: fcsxml.FCSFieldNotFoundError, RuntimeError
    
    .. note: 
      This will only remove the field from the current loaded object,
      nullifying any value represented by the XML output. It will 
      will **not** have any affect on the asset in Final Cut Server, the
      stored value for the field will remain unchanged..
    
    
    '''
    
    if fieldName.__class__.__name__ == 'FCSXMLField':  
      fieldName = fieldName.name

    if fieldName in self.fields:
      del self.fields[fieldName]
      self.logger('removeFieldWithName()  Field with name: %s removed!' % fieldName, 'info')
      return True
    else:
      raise FCSFieldNotFoundError(fieldName=fieldName)
       
  def setMD(self,filePath=''):
    '''This is a wrapper function for xmlOut, it is included to maintain 
    compatability with the :class:`fcsxml.FCSVRClient` class interface.
    
    '''
    
    if not filePath:
      if self.fcsXMLinDir:
        filePath = os.path.join(self.fcsXMLinDir,
                                              "asset_%s.xml" % self.entityID)
      elif self.path:
        filePath = os.path.join(self.path,'fcsvr_xmlin',
                                              "asset_%s.xml" % self.entityID)
    
    self.logger('setMD() Outputing XML to path: %s' % filePath,'debug')
    return self.xmlOut(filePath=filePath)
             
                              
  def xmlOut(self, filePath=''):
      '''Write our XML out to a file at the provided path. The output format
      will be a Final Cut Server ReadXML compatable file.
      
      :param filePath: Provide the (absolute) destination path for XML output
      :type filePath: str
      
      :raises: IOError 
      
      :returns: (*bool*) - True or False
      
      '''
      
      if not self.entityID > 0: 
          self.logger('xmlOut() entityID not set! Cannot generate XML.', 'warning')
      if not len(self.fields) > 0:
          self.logger('xmlOut() no fields set! Cannot generate XML.', 'error')
          return False
          
      if (filePath and (not os.path.exists(filePath)  \
      or (os.path.exists(filePath) and self.overwriteExistingFiles))
      and os.path.isdir(os.path.dirname(filePath))) \
      or not filePath : 
          ## create our new xml doc, add our root FCS elements:
          ## <?xml version="1.0"?>
          ## <FinalCutServer>
          ##  <getMdReply>
          ##   <entity entityType="asset" entityId="/asset/587344">
          ##    <metadata>            
          
          xmlDoc = minidom.Document()
          fcsElement = xmlDoc.createElement('FinalCutServer')
          xmlDoc.appendChild(fcsElement)
          requestElement = xmlDoc.createElement('request')
          requestElement.setAttribute('entityId', '/%s/%s' % (self.entityType,self.entityID))
          requestElement.setAttribute('reqId', 'setMd')
          fcsElement.appendChild(requestElement)
          paramsElement = xmlDoc.createElement('params')
          requestElement.appendChild(paramsElement)
          
          ## And then our individual fields.
          for field in self.fields.itervalues():
              theFieldElement = xmlDoc.createElement('mdValue')
              theFieldElement.setAttribute('fieldName', field.name)
              theFieldElement.setAttribute('dataType', field.dataType)
              if field.dataType == 'bool':
                if field.value:
                  fieldValue = 'True'
                else:
                  fieldValue = 'False'
              else:
                fieldValue = field.value
              
              if fieldValue:
                  theValueNode = xmlDoc.createTextNode(fieldValue)
                  theFieldElement.appendChild(theValueNode)
              else:
                  theValueNode = ''
                  
              ## Append our field element to our 'params' element i.e.
              ##  <params>
              ##     <mdValue fieldName="Size" dataType="int64">3798309</mdValue>
              paramsElement.appendChild(theFieldElement)
              
              del theFieldElement
              
          if filePath:
              theFile = open(filePath, 'w')
              xmlDoc.writexml(theFile)
              theFile.close()
          else:
              return xmlDoc.toxml()
              ##return xmlDoc.toprettyxml()
              
      elif os.path.exists(filePath) and not self.overwriteExistingFiles: 
          self.logger('xmlOut() File already exists at path: %s, exiting!' % filePath, 'error')
          return False
      elif not os.path.exists(os.path.dirname(filePath)): 
          self.logger('xmlOut() Directory does not exist at path: %s, exiting!' % os.path.dirname(filePath), 'error')
          return False
      else:
          self.logger('xmlOut() Unknown error writing XML', 'error')
          return False

      xmlDoc.unlink()
      return True 
       
            
class FCSVRClient(FCSBaseObject):
  '''Our FCSVRClient object, it is our interface for reading and manipulating 
  data from Final Cut Server via the fcsvr_client executable installed at 
  ``/Library/Application Support/Final Cut Server/Final Cut Server.bundle/Contents/MacOS/fcsvr_client``
  
  :param entityType: The Type of entity: 'asset' or 'project' (production)
  :type entityType: str
  :param entityID: The unique numeric FCS id of this object
  :type entityID: int
  :param entityPath: The FCS entity path for this object (i.e. '/asset/10')
  :type entityPath: str
  :param configParser: An optional :mod:`ConfigParser` object to configure 
                        default behavior. Alternatively this can be a file
                        system path to a configuration file to load
  :type configParser: :class:`ConfigParser.SafeConfigParser` or str
  
  .. note::
    If an entityPath value is provided, it will override values for entityType and id
    
  If upon creation the object is provided enough information to uniquely
  resolve the FCS object (either via specifying entityType,id, or entityPath),
  the object will init via :func:`FCSVRClient.initWithAssetID`.
  
  Thus, this:
  
  >>> myFCSObj = fcsxml.FCSVRClient()
  >>> myFCSObj.initWithProductionID(10)
  True
  
  Is equivalent to:
  
  >>> myFCSObj = fcsxml.FCSVRClient(entityPath='/project/10')
  
  Is equivalent to:
  
  >>> myFCSObj = fcsxml.FCSVRClient(entityType='project',entityID=10)
  
  Other notable ways to init an FCSVRClientObject:
  
  >>> myFCSObj = fcsxml.FCSVRClient().initWithAssetTitle(title='my great file')
  >>> myFCSObj = fcsxml.FCSVRClient().initWithProductionTitle(title='My Production')
  >>> myFCSObj = fcsxml.FCSVRClient().initWithAssetFromFSPath(FSPath='/FinalCutServer/Library/my great file.mov')
  >>> myFCSObj = fcsxml.FCSVRClient().initWithAssetFromFSPath(FSPath='/FinalCutServer/Library/my great file.mov')

  '''
  
  entityType = ''
  entityID = ''
  entityMetadataSet = ''
  entityTitle = ''
  
  defaultProductionMetadataSet = 'pa_production_package'
  defaultAssetMetadataSet = 'pa_asset_media'
  defaultThumbnailMetadataSet = 'pa_asset_thumbnail'
  
  defaultDeviceName = 'Library'
  
  fields = {}
  deviceDict = {}
  supportDir = '/tmp'
  overwriteExistingFiles = True
  
  thumbnailPath = ''
  posterFramePath = ''
  proxyPath = ''
  editProxyPath = ''
  
  thumbnailDeviceName = ''
  
  parentXMLObject = ''
  childXMLObject = ''
  
  FCSUID = 0          ## Our FCS User ID. If this is not set we will attempt
                      ## to read it in from /Library/Preferences/com.apple.FinalCutServer.settings.plist
  
  useSudo = False      ## Call /usr/bin/sudo before calling fcsvr_client commands
                      ## that require root access. You'll want to make sure that
                      ## You have modified your sudoers file if you set this to true.
  
  pathToFCSVRClient = '/Library/Application Support/Final Cut Server/Final Cut Server.bundle/Contents/MacOS/fcsvr_client'

  configParser = ''
  devicesMap = ''

  
  registeredEntities = ['asset','project','dev','field','mdgroup','group']
  
  def __init__(self,entityType='asset',entityID=0,id=0,entityPath='',configParser=''):
    '''Our constructor.'''
    
    FCSBaseObject.__init__(self)
    if entityPath:
      pathMatch = re.match('\/(.*)\/(.*)',entityPath)
      if pathMatch:
        self.entityType = pathMatch.groups()[0]
        self.entityID = pathMatch.groups()[1]
    else:
      self.entityType = entityType
      if entityID:
        self.entityID = entityID
      elif id:
        self.entityID = id
      
    self.entityMetadataSet = ''
    self.overwriteExistingFiles = True
    self.thumbnailPath = ''
    self.parentXMLObject = ''
    self.childXMLObject = ''
    self.thumbnailDeviceName = 'Library'
    self.debug = False
    self.keepFiles = False
    self.devicesMap = ''
    self.fields = {}
    self.deviceDict = {}
    self.FCSUID = self.getFCSUID()
    self.thumbnailPath = ''
    self.posterFramePath = ''
    self.proxyPath = ''
    self.editProxyPath = ''
    self.defaultProductionMetadataSet = 'pa_production_package'
    self.defaultAssetMetadataSet = 'pa_asset_media'
    self.defaultDeviceName = 'Library'

    self.useSudo = True
    self.printClassInLog = True
    self.debug = False
    self.printLogs = True
    
    if configParser:
      if type('string') == type(configParser):
        self.loadConfiguration(filePath=configParser)
      else:
        self.loadConfiguration(parser=configParser)
        
    if self.entityID and self.entityType == 'asset':
      self.initWithAssetID(assetID=self.entityID)
    elif self.entityID and self.entityType == 'project':
      self.initWithProductionID(productionID=self.entityID)
        
  def loadConfiguration(self, parser=None,filePath=None):
    '''This method will load internal parameters as specified in the
    provided :class:`ConfigParser.SafeConfigParser` object, or via the 
    configuration file referenced via the filePath parameter.
    
    :param parser: A configuration object.
    :type parser: :class:`ConfigParser.SafeConfigParser`
    :param filePath: An absolute path to a configuration file.
    :type filePath: str
        
    
    .. note:: 
      If you subclass, you should call this parent function. If we raise a 
      RuntimeError Exception, you should abort or perform your own 
      exhaustive sanity checks
      
    '''
    
    
    if not isinstance(parser,ConfigParser) and not filePath:
      message = 'loadConfiguration() Not passed a valid ConfigParser Object!'
      self.logger(message, 'error')
      raise RuntimeError(message)
    elif not isinstance(parser,ConfigParser):
      if not filePath:
        filePath = '/usr/local/etc/transmogrifier.conf'
      self.logger('Loading configuration from filepath: %s' % filePath,'debug')
      parser = SafeConfigParser()
      parser.read(filePath)
      
    try:
      self.configParser = parser
      
      ## Get Debug status, first from FCSVRClient section, then from global
      try:
        self.printLogs = parser.getboolean('FCSVRClient','printLogs')
      except:
        try:
          self.printLogs = parser.getboolean('GLOBAL','printLogs') 
        except:
          pass 
      try:
        self.debug = parser.getboolean('FCSVRClient','debug')
      except:
        try:
          self.debug = parser.getboolean('GLOBAL','debug') 
        except:
          pass     
      try:
        self.keepFiles = parser.getboolean('FCSVRClient','keepFiles')
      except:
        try:
          self.keepFiles = parser.getboolean('GLOBAL','keepFiles') 
        except:
          pass
      try:
        self.defaultProductionMetadataSet = parser.get('FCSVRClient','defaultproductionmdset')
      except:
        pass
      try:
        self.defaultAssetMetadataSet = parser.get('FCSVRClient','defaultassetmdset')
      except:
        pass
      try:
        self.defaultThumbnailMetadataSet = parser.get('FCSVRClient','defaultthumbnailmdset')
      except:
        pass
      try:
        self.useSudo = parser.getboolean('FCSVRClient','useSudo')
      except:
        pass
      try:
        self.defaultDeviceName = parse.get('FCSVRClient','defaultDeviceName')
      except:
        pass
        
    except:
       self.logger('loadConfiguration() Problem loading configuration records, please double check your configuration', 'error') 
    return True


  def getFCSUID(self):
    '''Determine the UID of the running FCS User, this is stored in 
    /Library/Preferences/com.apple.FinalCutServer.settings.plist
    
    :returns: (*int*) -- The user ID of the Final Cut Server runtime user.
    
    '''
    
    plistFile = '/Library/Preferences/com.apple.FinalCutServer.settings.plist'
    UID = 0

    if self.FCSUID:
      return self.FCSUID

    plistDict = {}
    if os.path.isfile(plistFile):
      try:
        plistObj = plistlib.readPlist(plistFile)
      except:
        self.logger('loadFromFile() Error Reading File!','error')
        return False
      if 'USER_ID' in plistObj:
        self.FCSUID = plistObj['USER_ID']
        return self.FCSUID    

  def getDevicesMap(self,useCache=True):
    '''This method will load device information from FCS, returning a 
    multi dimensional dictionary containing information about all configured
    FCS devices. The top level of the dictionary is keyed by device id. Each
    device entry in this dictionary will be populated with the following 
    key+value entries:
    
    ===================  ======================================================
    Key                  Description
    ===================  ======================================================
    DEVICE_NAME          (*str*) The name of the device
    DEV_ROOT_PATH        (*str*) The path to the device on the file system.
    FSPATH               (*str*) An alias for DEV_ROOT_PATH
    DEVICE_TYPE          (*str*) The type of device (filesystem vs contentbase)
    DEVICE_ID            (*int*) The device's unique ID
    DESC_DEVICE_ADDRESS  (*str*) The device's FCS entity path (i.e. /dev/2)
    DEV_ARCHIVE          (*bool*) True if the device is an archive device.
    ===================  ======================================================
    
    .. note:
      FCSVRClient currently only supports operations on local filesystem devices.
      
    :returns: (*dict*) -- A dict object populated with the above information
      for all devices configured in FCS.
    
    '''
    
    if self.devicesMap and len(self.devicesMap) > 0 and useCache:
      return self.devicesMap

    ## Run our fcsvr_client command.
    fcsvrCMDTXT = "'%s' search /dev --xml" % (self.pathToFCSVRClient)
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,shell=True,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    if not fcsvrCMD.returncode == 0:
      ##self.logger('%s' % fcsvrCMD_STDOUT,'error')
      ##raise RuntimeError('Could not parse output from fcsvr_client')
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                        cmdString='fcsvr_client %s' % cmdString)

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client','error')
      raise RuntimeError('Could not parse output from fcsvr_client')

    devicesMap = {}
    for rootValues in myDom.getElementsByTagName('values'):
      deviceDict = {}
      for rootValue in rootValues.getElementsByTagName('value'):
        if rootValue.attributes['id'].value == 'METADATA':
          for values in rootValue.getElementsByTagName('values'):
            for value in values.getElementsByTagName('value'):
              valueID = value.attributes['id'].value
              if valueID == 'DEV_ROOT_PATH':
                deviceDict['DEV_ROOT_PATH'] = value.childNodes[1].childNodes[0].data
                deviceDict['FSPATH'] = value.childNodes[1].childNodes[0].data
              elif valueID == 'DEVICE_TYPE':
                deviceDict['DEVICE_TYPE'] = value.childNodes[1].childNodes[0].data
              elif valueID == 'DEVICE_NAME':
                deviceDict['DEVICE_NAME'] = value.childNodes[1].childNodes[0].data
              elif valueID == 'DEVICE_ID':
                deviceDict['DEVICE_ID'] = int(value.childNodes[1].childNodes[0].data)
                deviceDict['DESC_DEVICE_ADDRESS'] = '/dev/%s' % deviceDict['DEVICE_ID']
              elif valueID == 'DEV_ARCHIVE':
                archiveValue = value.childNodes[1].childNodes[0].data
                if archiveValue == 'true':
                  deviceDict['DEV_ARCHIVE'] = True
                else:
                  deviceDict['DEV_ARCHIVE'] = False
        if 'DEVICE_ID' in deviceDict and deviceDict['DEVICE_ID']:
          devicesMap[deviceDict['DEVICE_ID']] = deviceDict

    self.devicesMap = devicesMap
    return self.devicesMap
        
  def deviceWithID(self,id):
    '''This method will return a dict entry containing pertinent device 
    information for the device matching the provided device id. See the 
    table listed in :func:`fcsxml.FCSVRClient.getDevicesMap` for a list of 
    values contained in this dict.
    
    :param id: Provide the device id
    :type id: int
    
    :returns: (*dict*) -- A dictionary populated with information detailing the
      requested device.
      
    :raises: fcsxml.FCSEntityNotFoundError
    
    '''

    deviceIDMap = self.getDevicesMap()
    self.logger('deviceWithID() Called with ID: %s' % id,'debug')
    myID = int(id)
    
    if myID in deviceIDMap:
      return deviceIDMap[myID]
    else:
      raise FCSEntityNotFoundError(entityType='device',entityID=id)
      #self.logger('DeviceID: %s has not been registered!' % id,'error')
      #return False
      
  def deviceWithName(self,id):
    '''This method will return a dict entry containing pertinent device 
    information for the device matching the provided device name. See the 
    table listed in :func:`fcsxml.FCSVRClient.getDevicesMap` for a list of 
    values contained in this dict.
    
    :param id: Provide the device name
    :type id: str
    
    :returns: (*dict*) -- A dictionary populated with information detailing the
      requested device.
      
    :raises: fcsxml.FCSEntityNotFoundError, fcsxml.FCSError
    
    '''

    deviceIDMap = self.getDevicesMap()
    self.logger('deviceWithName() Called with Name: %s' % id,'debug')

    if not deviceIDMap:
      message = 'Could not generate deviceMap, cannot continue!'
      self.logger(message,'error')
      raise FCSError(message)

    for deviceID,deviceDict in deviceIDMap.iteritems():
      if 'DEVICE_NAME' in deviceDict and deviceDict['DEVICE_NAME'] == id:
        return deviceIDMap[deviceID]

    ## We are here if we found no match.
    raise FCSEntityNotFoundError(entityType='device',entityTitle=id)


  def deviceWithPath(self,path):
    '''This method will return a dict entry containing pertinent device 
    information for the device configured at the provided POSIX filesystem path.   
    See the table listed in :func:`fcsxml.FCSVRClient.getDevicesMap` for a
    list of values contained in this dict.
    
    :param path: Provide a full file system path
    :type id: str
    
    :returns: (*dict*) -- A dictionary populated with information detailing the
      requested device.
      
    :raises: fcsxml.FCSEntityNotFoundError, fcsxml.FCSError
    
    '''
    
    deviceIDMap = self.getDevicesMap()
    
    if not deviceIDMap:
      message = 'Could not generate deviceMap, cannot continue!'
      self.logger(message,'error')
      raise FCSError(message)
      
    myDevice = {}
    self.logger('deviceWithName() Called with path: %s' % path,'debug')
    for deviceID,deviceDict in deviceIDMap.iteritems():
      if 'FSPATH' in deviceDict:
        subPath = path[0:len(deviceDict['FSPATH'])]
        self.logger('deviceWithName() comparing subPath: %s to path:%s' % (subPath,deviceDict['FSPATH']),'debug')
        if subPath == deviceDict['FSPATH']:
          myDevice = deviceDict
          break
    if myDevice:
      return myDevice
    else:
      raise FCSEntityNotFoundError(entityType='device',entityPath=path)
      
  def valueForDBField(self,dbFieldName):
    '''This method returns the value for the passed FCS database field.
    (i.e. "pa_cust_md_my_field")
        
    :param dbFieldName: Provide the FCS database name of the field to query.
    :type dbFieldName: str
    
    :raises: fcsxml.FCSFieldNotFoundError
    :returns: (*str*) Value for the specified field
    
    .. note: This method will dynamically look up the field using 
      :func:`fcsxml.FCSVRClient.loadField` regardless of whether the field 
      is cached or not.
      
    
    '''

    self.logger('valueForDBField() hit','debug')

    ## Create our FCSXMLField object
    myField = self.loadField(FCSXMLField(dbname=dbFieldName))
    return self.valueForField(myField.name)
  
  def valueForField(self, fieldName):
    '''This method returns the stored value for the passed database field name.
      (i.e. "My Field")
        
        :param fieldName: Provide the name of the field to query.
        :type fieldName: str
      
        :raises: fcsxml.FCSFieldNotFoundError
        :returns: (*str*) Value for the specified field
      
      .. note: If the requested field is locally cached, we will return the 
        cached value. If it is not cached, we will dynamically look it up
        using :func:`fcsxml.FCSVRClient.loadFieldWithName`.
        
    
    '''
    
    self.logger('valueForField() hit')

    if not fieldName in self.fields:
        self.logger('valueForField() No Field with key:\'%s\' exists! Attempting to load' % fieldName, 'warning')
        if not self.loadFieldWithName(fieldName):
          self.logger('valueForField() Could not load field with key:\'%s\'' % fieldName, 'warning')
          raise FCSFieldNotFoundError(fieldName)
        
        
    theField = self.fields[fieldName]
    if theField.dataType == 'timecode':
        ## return timecode in seconds
        tempValue = theField.value.replace( '.', ':' )
        tempValue = tempValue.replace( ';', ':' )
        tempValue = tempValue.replace(',',':')
        tempValueArray = tempValue.split(':')
        
        hours = int(tempValueArray[0])
        minutes = int(tempValueArray[1])
        seconds = int(tempValueArray[2])
        frames = int(tempValueArray[3])
        
        ## need to extrapolate framerate to get seconds-per-frame
        frameRate = float(self.valueForField('Video Frame Rate'))
        if frameRate:
          frameSeconds = (frames/frameRate)
        
        
        totalSeconds = (hours * 60 * 60) + (minutes * 60) + seconds + frameSeconds
        return totalSeconds
    elif theField.dataType == 'bool':
      if theField.value:
        return True
      elif theField.value:
        return False
    
    elif theField.dataType == 'string':
      if not theField.value:
        theField.value = ''
      return theField.value
    else:
        return theField.value
  
  def appendValueForField(self,fieldName,value,useTimestamp=False):
    '''Appends a value to field, concatenating with the current field value.
      
      :param fieldName: Provide the field name
      :type fieldName: str
      :param value: Provide the value to append.
      :type value: id
      :param useTimeStamp: If set to true, we will prepend a timestamp to the
        data to be appended.
      :type useTimeStamp: bool
      
      :raises: fcsxml.FCSFieldNotFoundError
      
      .. note: String fields will be concatenated, integer fields will be
        summed, other field types might not work out so well (test!) 
      
      '''
    
    if not fieldName in self.fields:
        self.logger('valueForField() No Field with key:\'%s\' exists! '
          'Attempting to load' % fieldName, 'warning')
        if not self.loadFieldWithName(fieldName):
          self.logger('valueForField() Could not load field with key:\'%s\'' 
            % fieldName, 'warning')
        
    theField = self.fields[fieldName]
    
    if (theField.dataType == 'integer' 
    or theField.dataType == 'int'
    or theField.dataType == 'int64'
    or theField.dataType == 'bigint'):
      newValue = int(theField.value) + int(value)
    else:
      
      ## Get current field and value       
      currentValue = theField.value
      newValue = value
              
      ## Add a line return. 
      if currentValue:
        currentValue += "\n"
      ## If we are set to use a timestamp, prepend it to the new value
      if useTimestamp:    
        currentTime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        newValue = '%s:  %s' % (currentTime,newValue)    
        self.logger('appendValueForField() Appending timestamp to new value:%s' 
          % (newValue),'debug')
      
      newValue = "%s%s\n" % (currentValue,newValue)
    
    
    theField.setValue(newValue)
    return
  
  def dataTypeForField(self, field):
    '''This method returns the datatype for the passed field name.
      
    :param field: Provide the FCSXMLField or field name of the field to query.
    :type field: fcsxml.FCSXMLField, str
    
    :raises: fcsxml.FCSFieldNotFoundError
    
    :returns: (*str*) Datatype for the specified field
      
    '''
    if type(field) == type('string'):
      name = field
      field = self.initFieldWithFieldName(name)
      return field.dataType
    else:
      dbname = field.dbname
      name = field.name
      dataType = field.dataType
        
    
    if not dbname and not name:
      ##self.logger('dataTypeForField() Passed field has no name!', 'error')
      raise RuntimeError('Could not determine Data Type: requested field has '
        'no name specified');
    elif name:
      dbname = self.dbFieldNameForFieldName(name)

    self.logger("Loading dataType for name:'%s' dbname:'%s'" % (name,dbname),
      'debug')

    dataType = self.dataTypeForDBFieldName(dbname)
    
    field.dataType = dataType
    
    return dataType
        
        
  def dbDataTypeForField(self, field):
    ''' This function returns the FCS DB datatype for the requested field. 
    Please see the table outlined in :func:`fcsxml.FCSVRClient.setDataType` 
    for information about available FCS DB Data types
      
    :param field: Provide the FCSXMLField or field name of the field to query.
    :type field: fcsxml.FCSXMLField, str
    
    :raises: fcsxml.FCSFieldNotFoundError
    
    :returns: (*str*) FCS DB Datatype for the specified field
    '''
        
    if type(field) == type('string'):
      name = field
      field = self.initFieldWithFieldName(name)
      return field.dbDataType
    else:
      dbname = field.dbname
      name = field.name
      dataType = field.dataType
      
    if not dbname and not name:
      self.logger('dataTypeForField() Field has no name!', 'error')
      raise RuntimeError('Could not determine Data Type: requested field has no'
        ' name specified');
    elif name:
      dbname = self.dbFieldNameForFieldName(name)
    elif dbname:
      name = self.fieldNameForField(dbname)

    self.logger("Loading field name for name:'%s' dbname:'%s'" % (name,dbname),
      'debug')

    dbDataType = self.dbDataTypeForDBFieldName(dbname)
    
    field.dbDataType = dbDataType
    
    return dbDataType
     
  def fieldWithName(self, fieldName):
    '''This method returns the :class:`fcsxml.FCSXMLField` object for the 
    passed field name.
      
    :param fieldName: Provide the name of the field to query.
    :type fieldName: str
      
    :raises: fcsxml.FCSFieldNotFoundError
      
    :returns: (*fcsxml.FCSXMLField*) -- The stored field object for the 
      specified field
      
    .. note: If the provided field is cached, we will return the cached 
        instance, otherwise we will look up the field using 
        :func:`fcsxml.FCSVRClient.loadFieldWithName`
        
    '''
    
    self.logger('fieldWithName() hit','debug')
    
    if fieldName in self.fields:
      theField = self.fields[fieldName]
      return theField
        
    else:
      if self.loadFieldWithName(fieldName):          
        return self.fields[fieldName]
      else:
        self.logger("Could not Retrieving Field with name: %s" % fieldName,
          'warning')
            
      return False
  
  
  def loadField(self,field):
    '''Function which loads the specified field. If the field is not defined 
    for our entity in Final Cut Server, we will still return a FCSXMLField 
    object with all members populated, short of the value field. 
    
    
    :param field: Provide the field object to load
    :type field: fcsxml.FCSXMLField
      
    :raises: fcsxml.FCSFieldNotFoundError, fcsxml.FCSVRClientError, 
      fcsxml.FCSError,fcsxml.FCSVRClientError
      
    :returns: (*fcsxml.FCSXMLField*) -- The loaded field object
      
    .. note: We will look up the field using 
      :func:`fcsxml.FCSVRClient.loadFieldWithName`, regardless of it's cached
      state.
        
    '''
    
    self.logger('loadField() hit','debug')
    
    dbFieldName = ''
    fieldName = ''

    if field.dbname:
      dbFieldName = field.dbname
    if field.name:
      fieldName = field.name
      
    if not fieldName and dbFieldName:
      fieldName = self.fieldNameForDBFieldName(dbFieldName)
    elif not dbFieldName and fieldName:
      dbFieldName = self.dbFieldNameForFieldName(fieldName)
    elif fieldName and dbFieldName:
      testName = self.fieldNameForDBFieldName(dbFieldName)
      testDBName = self.dbFieldNameForFieldName(fieldName)
      if (not testName == fieldName or not testDBName == dbFieldName):
        raise FCSError('Ambiguous data provided, please provide either a '
          'name or dbname');
    else:
      self.logger('loadField() No fieldname provided!','error');
      raise RuntimeError('Could not load field name: no data provided');
    
    self.logger("loadField() Loading field with name:'%s' dbname:'%s'" 
      % (fieldName,dbFieldName),'debug')
        
    ## If we have a registered entityID, try to fetch the actual field value
    if self.entityID:
      ## Run our fcsvr_client command.
      fcsvrCMDTXT = "'%s' getmd /%s/%s --xml" % (self.pathToFCSVRClient,
                                                  self.entityType,self.entityID)
      fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,shell=True,
                                              stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE,
                                              universal_newlines=True)
      fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
        
      self.logger("fcsvr_client command: fcsvr_client getmd /%s/%s --xml" 
                                    % (self.entityType,self.entityID),'debug')

      if not fcsvrCMD.returncode == 0:
        ##self.logger("%s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'error')
        ##return False
        return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                            cmdString=fcsvrCMDTXT)
          
      ## Create a dom object from our string:
      try:
        myDom = minidom.parseString(fcsvrCMD_STDOUT)
      except:
        message = ("Could not parse output from fcsvr_client command: "
          "fcsvr_client getmd /%s/%s --xml" % (self.entityType,
                                                        self.entityID))
        self.logger(message,'error')
        raise FCSError(message)
      
      try:
        for rootElement in myDom.childNodes[0].childNodes:
          ##self.logger("Nodename: %s" %rootElement.nodeName,'debug')
          if rootElement.nodeName == "values":
            for value in rootElement.getElementsByTagName("value"):
              valueID = value.attributes["id"].value
              ##self.logger("valueID: %s" % valueID,'debug')
              if valueID == dbFieldName:
                self.testNode = value
                fieldValueNode = value.childNodes[1]
                fieldType = fieldValueNode.nodeName
                try:
                  self.logger('Found field: %s, reading value.' % dbFieldName,
                    'debug')
                  fieldData = fieldValueNode.childNodes[0].data
                except Exception, inst:
                  self.logger('An error occured reading value for field: %s'
                    % inst,'error')
                  fieldData = ""
                self.logger('Found field: \'%s\', with data: \'%s\'' 
                  % (dbFieldName,fieldData),'debug')
                FCSField = FCSXMLField(name=fieldName,value=fieldData,
                                        dataType=fieldType,dbname=dbFieldName)
                self.fields[fieldName] = FCSField
                return FCSField
      except:
        message = ("Error extracting field:'%s' from fcsvr_client command: "
          "fcsvr_client getmd /%s/%s --xml" % (dbFieldName,self.entityType,
                                                self.entityID))
        self.logger(message,'error')
        raise FCSError(message)
    
    ## If we have gotten to this point, then the asset did not have a value for
    ## the requested field. If we can query the dataType for the field, return
    ## a bare FCSXMLField object 
    
    dataType = self.dataTypeForDBFieldName(dbFieldName)
    dbDataType = self.dbDataTypeForDBFieldName(dbFieldName)
    
    self.logger('Creating new field with name:\'%s\' dbname:\'%s\'' 
      ' dataType:\'%s\' dbDataType:%s'
      % (fieldName,dbFieldName,dataType,dbDataType),'debug')
    if (dataType):
      FCSField = FCSXMLField(name=fieldName,dbname=dbFieldName,
                                    dataType=dataType,dbDataType=dbDataType);
      self.fields[fieldName] = FCSField
      return FCSField

    return False
  
  def loadFieldWithName(self,name='',dbname=''):
    '''Function which loads the specified field. If the field is not defined 
    for our entity in Final Cut Server, we will still return a FCSXMLField 
    object with all members populated, short of the value field. 
    
    
    :param name: Provide the field name to load
    :type name: str
    
    :param dbname: Provide the field db name to load
    :type dbname: str
    
      
    :raises: fcsxml.FCSFieldNotFoundError,fcsxml.FCSVRClientError,RuntimeError,
      fcsxml.FCSError
      
    :returns: (*fcsxml.FCSXMLField*) -- The loaded field object
      
    .. note: We will look up the field using fcsvr_client regardless of it's 
      cached state.
    
    '''

    self.logger('loadFieldWithName() hit','debug')


    dbFieldName = ''
    fieldName = ''

    if dbname:
      dbFieldName = dbname
    if name:
      fieldName = name
      
    if not fieldName and dbFieldName:
      fieldName = self.fieldNameForDBFieldName(dbFieldName)
    elif not dbFieldName and fieldName:
      dbFieldName = self.dbFieldNameForFieldName(fieldName)
    elif fieldName and dbFieldName:
      testName = self.fieldNameForDBFieldName(dbFieldName)
      testDBName = self.dbFieldNameForFieldName(fieldName)
      if (not testName == fieldName or not testDBName == dbFieldName):
        raise RuntimeError('Ambiguous data provided, please provide either a'
          ' name or dbname');
    else:
      self.logger('loadFieldWithName() No fieldname provided!','error');
      raise RuntimeError('Could not load field name: no data provided');
    
    self.logger("Loading field name for name:'%s' dbname:'%s'" 
                                              % (fieldName,dbFieldName),'debug')
    
    ## If we have a registered entityID, try to fetch the actual field value
    if self.entityID:
      ## Run our fcsvr_client command.
      fcsvrCMDString = "'%s' getmd /%s/%s --xml" % (self.pathToFCSVRClient,
                                                      self.entityType,
                                                      self.entityID)
      fcsvrCMD = subprocess.Popen(fcsvrCMDString,shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True)
      fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
        
      self.logger("fcsvr_client command: %s" % fcsvrCMDString,'debug')

      if not fcsvrCMD.returncode == 0:
        ##errorString = '%s %s' % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR)
        ##self.logger(errorString,'error')
        ##raise FCSVRClientError('%s' % errorString,cmdString)
        return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                            cmdString=fcsvrCMDTXT)

        
        
      ## Create a dom object from our string:
      try:
        myDom = minidom.parseString(fcsvrCMD_STDOUT)
      except:
        errorString = 'Could not parse output from fcsvr_client command.'
        self.logger('%s fcsvr_client cmd:%s' % (errorString,fcsvrCMDString),'error')
        raise FCSVRClientError(errorString,fcsvrCMDString)
      
      try:
        for rootElement in myDom.childNodes[0].childNodes:
          ##self.logger("loadFieldWithName() Nodename: %s" % rootElement.nodeName,'debug')
          if rootElement.nodeName == "values":
            for value in rootElement.getElementsByTagName("value"):
              valueID = value.attributes["id"].value
              ##self.logger("loadFieldWithName() valueID: %s" % valueID,'debug')
              if valueID == dbFieldName:
                ##self.logger('loadFieldWithName() found field with name:%s' % dbFieldName,'debug')
                self.testNode = value
                fieldValueNode = value.childNodes[1]
                fieldType = fieldValueNode.nodeName
                try:
                  fieldData = fieldValueNode.childNodes[0].data
                except:
                  self.logger('loadFieldWithName() An error occured reading '
                    ' data for field:%s' % dbFieldName,'debug')
                  fieldData = ''
                  
                self.logger('loadFieldWithName() Found field with dbname:\'%s\''
                  'value:\'%s\' type:\'%s\'' % (dbFieldName,fieldData,fieldType),
                  'debug')
                FCSField = FCSXMLField(name=fieldName,value=fieldData,
                                          dataType=fieldType,dbname=dbFieldName)
                self.fields[fieldName] = FCSField
                return FCSField
      except:
        self.logger("Error extracting field:'%s' from fcsvr_client command: "
          "fcsvr_client getmd /%s/%s --xml" % (dbFieldName,self.entityType,
                                                self.entityID),'error')
        raise FCSFieldNotFoundError(fieldName)
        
    
    ## If we have gotten to this point, then the asset did not have a value for
    ## the requested field. If we can query the dataType for the field, return
    ## a bare FCSXMLField object 
    
    dataType = self.dataTypeForDBFieldName(dbFieldName)
    dbDataType = self.dbDataTypeForDBFieldName(dbFieldName)
    
    self.logger('loadFieldWithName() Creating new field with name:\'%s\' dbname:\'%s\' '
      'dataType:\'%s\' dbDataType:%s'
      % (fieldName,dbFieldName,dataType,dbDataType),'debug')
    
    if (dataType):
      FCSField = FCSXMLField(name=fieldName,dbname=dbFieldName,
                              dataType=dataType,dbDataType=dbDataType);
      self.fields[name] = FCSField
      if self.debug:
        FCSField.debug = True
      return FCSField

    raise FCSFieldNotFoundError(fieldName)
              
    
  def setField(self, field):
    '''This method register's the provided FCSXMLField object, replacing 
    existing field object with same name if it should exist.
    
    :param field: Provide an FCSXMLField object loaded with field name and 
      value
    :type field: fcsxml.FCSXMLField
    
    :returns: (*bool*) True or False
    
    '''      
      
    if field.__class__.__name__ != "FCSXMLField":
      self.logger("setField() Passed invalid data! Expects FCSXMLField", 'error')
      return False
    
    fieldName = field.name
    dbname = field.dbname
    dataType = field.dataType;
    
    if not fieldName and not dbname:
      self.logger("setField() provided field has no fieldname or dbname!",'error')
      return False
    
    if not fieldName and dbname:
      fieldName = self.fieldNameForDBFieldName(dbname)
      field.name = fieldName
    if not dbname and fieldName:
      dbname = self.dbFieldNameForFieldName(fieldName)
      field.dbname = dbname
    
    if not dataType:
      self.logger('setField() loading dataType for field: %s' %field.name,'debug')
      dataType = self.dataTypeForField(field);
      field.setDataType(dataType)
      
    if not field.dataType:
      self.logger('setField() could not produce dataType for field: %s' % fieldName,'error');
      raise RuntimeError('Could not determine datatype!');
    
    self.fields[field.name] = field
    return True
  
  def appendField(self, field):
    '''This method will add a new FCSXMLField to the objects field definition
    list. This function will raise an FCSDuplicate exception if a field 
    object with same name already exists.
    
    :param field: Provide an FCSXMLField object loaded with field name and 
      value
    :type field: fcsxml.FCSXMLField
    
    :returns: (*bool*) True or False
    
    :raises: fcsxml.FCSDuplicateError, RuntimeError    
    '''
    if field.__class__.__name__ != 'FCSXMLField':
      message = 'appendField() Passed invalid data! Expects FCSXMLField'
      self.logger(message, 'error')
      raise RuntimeError(message)
        
    if field.name in self.fields:
      message = 'appendField() Field with name: %s already exists!' % field.name
      self.logger(message, 'error')
      raise FCSDuplicateError(message)
    else:
      self.fields[field.name] = field
          
  def removeFieldWithName(self, fieldName):
    '''Remove FCSXMLField object registered with passed field name. 
      
    :param fieldName: Provide the field name (or an FCSXMLField object) to 
      be removed from the current object's field list.
    :type fieldName: str or fcsxml.FCSXMLField
    :raises: fcsxml.FCSFieldNotFoundError, RuntimeError
    
    .. note: 
      This will only remove the field from the current loaded object,
      nullifying any value represented by the XML output. It will 
      will **not** have any affect on the asset in Final Cut Server, the
      stored value for the field will remain unchanged..
      
      
    '''      
    if fieldName.__class__.__name__ == "FCSXMLField":  
      fieldName = fieldName.name

    if fieldName in self.fields:
      del self.fields[fieldName]
      self.logger("removeFieldWithName()  Field with name: %s removed!" % fieldName, "info")
      return True
    else:
      raise FCSFieldNotFoundError(fieldName=fieldName)
  
  def fieldNameForDBFieldName(self,dbname):
    '''Returns a field name for a dbname (FCS Read XML field name from 
    FCSVR_CLIENT field name. 
    
    :param dbname: The FCS DB name for the field to be queried.
    :type dbname: str
    
    :returns: (*str*) -- The field name.
    '''

    self.logger("Retrieving field name for dbname:%s" % dbname,'debug')

     ## Run our fcsvr_client command.
    fcsvrCMDTXT = "'%s' getmd /field/%s --xml" % (self.pathToFCSVRClient,dbname)
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger("fcsvr_client command: fcsvr_client getmd /field/%s --xml" % dbname,'debug')

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)
    
    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger("Could not parse output from fcsvr_client command: fcsvr_client getmd /field/%s --xml" % dbname,'error')
      return False
    
    try:
      fieldName = ""
      for rootElement in myDom.childNodes[0].childNodes:
        self.logger("Nodename: %s" %rootElement.nodeName,'debug')
        if rootElement.nodeName == "values":
          for value in rootElement.getElementsByTagName("value"):
            valueID = value.attributes["id"].value
            #self.logger("valueID: %s" % valueID,'debug')
            if valueID == "FIELD_NAME":
              fieldName = value.childNodes[1].childNodes[0].data
              break
    except:
      self.logger("Uncaught exception reading field name for dbname:%s" % dbname,'debug')
      return False
      
    if fieldName:
      self.logger("Found fieldname: %s for dbname: %s"% (fieldName,dbname),'debug')
      return fieldName
    else:
      return False

  def dataTypeForDBFieldName(self,dbname):
    '''Returns a dataType value for field with dbname (we use FCSXMLField Object
    and self.dbDataTypeForDBFieldName for this).
    
    :param dbname: The FCS DB Field name
    :type dbname: str
    
    :returns: (*str*) -- The data type for the requested db field name.
    
    '''
    
    self.logger("dataTypeForDBFieldName() Retrieving dataType for dbname:'%s'" % (dbname),'debug')
    myField = self.initFieldWithDBName(dbname)
    
    return myField.dataType

  def dbDataTypeForDBFieldName(self,dbname):
    '''Returns a FCS DB dataType value for field with dbname (we use FCSXMLField 
    Object and self.dbDataTypeForDBFieldName for this).
    
    :param dbname: The FCS DB Field name
    :type dbname: str
    
    :returns: (*str*) -- The FCS DB data type for the requested db field name
    
    '''
    
    self.logger("dbDataTypeForDBFieldName() Retrieving dbDataType for dbname:'%s'" % (dbname),'debug')
    myField = self.initFieldWithDBName(dbname)
    
    return myField.dbDataType

  def dbFieldNameForFieldName(self,fieldName):
    '''Returns a FCS DB field name for a standard field name (fcsvr_client field 
    name from FCS Read XML field name. 
    
    :param fieldName: The field name to be queried.
    :type fieldName: str
    
    :returns: (*str*) -- The fcsvr_client compatable DB field name.
    '''

    self.logger('Retrieving dbFieldName for field: %s' %fieldName,'debug')
    theField = self.initFieldWithFieldName(fieldName)
    
    if theField:
      return theField.dbname
    else:
      raise FCSFieldNotFoundError(fieldName)

  def initFieldWithDBName(self,dbname):
    '''Returns a FCSXMLField object from a dbname. Uses fcsvr_client
    to retrieve all the necessary parameters for the field. This method differs
    from :func:`loadFieldWithDBName` in that this method will only init a 
    generic FCSXMLField object, the resulting object will NOT be cached as a 
    member of this object, and no value will be populated for the field (as
    it is not associated to any particular entity).
    
    :param dbname: The field name to be queried.
    :type dbname: str
    
    :returns: (*fcsxml.FCSXMLField*) -- The associated FCSXMLField object.
    
    
    '''
    
    self.logger("initFieldWithDBName() Constructing field with dbname:%s" 
      % dbname,'debug')
    
    ## URL encode our fieldname
    encodedDBName = urllib.quote(dbname)
    
    ## Run our fcsvr_client command.
    fcsvrCMDTXT = ("'%s' getmd /field/%s --xml" 
      % (self.pathToFCSVRClient,encodedDBName))
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
    
    self.logger("initFieldWithDBName() fcsvr_client command: "
      "fcsvr_client getmd /field/%s --xml" % dbname,'debug')
      
    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)


    
    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger("Could not parse output from fcsvr_client command: fcsvr_client getmd /field/%s --xml" % dbname,'error')
      return False
    try:
      myField = FCSXMLField()
      for rootElement in myDom.childNodes[0].childNodes:
        ##self.logger("Nodename: %s" %rootElement.nodeName,'debug')
        if rootElement.nodeName == "values":
          for value in rootElement.getElementsByTagName("value"):
            valueID = value.attributes["id"].value
            #self.logger("valueID: %s" % valueID,'debug')
            if valueID == "FIELD_NAME":
              myField.name = value.childNodes[1].childNodes[0].data
            if valueID == "FIELD_DATA_TYPE":
              myField.setDBDataType(value.childNodes[1].childNodes[0].data)
            if valueID == "FIELD_ID":
              myField.dbname = value.childNodes[1].childNodes[0].data
    except:
      self.logger("Uncaught exception reading field name for dbname:%s" % dbname,'debug')
      return False
      
    if myField and myField.dbname == dbname:
      self.logger("Found field for dbname: %s, dataType:%s"% (dbname,myField.dataType),'debug')
      return myField
    elif not myField.dbname == dbname:
      raise RuntimeError("Constructed field does not match dbname:%s" % dbname)
    else:
      raise FCSFieldNotFoundError(dbname=dbname)



  
  def initFieldWithFieldName(self,fieldName):
    '''Returns a FCSXMLField object from a provided fieldName. Uses fcsvr_client
    to retrieve all the necessary parameters for the field. This method differs
    from :func:`loadFieldWithName` in that this method will only init a 
    generic FCSXMLField object, the resulting object will NOT be cached as a 
    member of this object, and no value will be populated for the field (as
    it is not associated to any particular entity).
    
    :param fieldName: The field name to be queried.
    :type fieldName: str
    
    :returns: (*fcsxml.FCSXMLField*) -- The associated FCSXMLField object
    
    '''
    
    
    self.logger("Constructing field with name:%s" % fieldName,'debug')

    ## Run our fcsvr_client command.
    fcsvrCMDTXT = '"%s" search --crit  "%s" /field --xml' % (self.pathToFCSVRClient,fieldName)
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command: fcsvr_client  search --crit  "%s" /field --xml' % fieldName,'debug')

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)
    
    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: fcsvr_client  search --crit  "%s" /field --xml' % fieldName,'error')
      return False
      
    didComplete = False
    #try:
    testFieldName = ""
    searchRoot = myDom.childNodes[0]
    searchResultCount = 0
    exactMatches = []
    caseInsensitiveMatches = []
    partialMatches = []
    for searchResult in searchRoot.childNodes:
      ## self.logger("initFieldWithFieldName() Searching nodename: %s" % searchResult.nodeName,'debug')
      if searchResult.nodeName == "values":
        didFindMatch = False
        matchType = ""
        dbFieldName = ""
        for rootValue in searchResult.getElementsByTagName("value"):
          ## self.logger("initFieldWithFieldName() rootValue nodename: %s" % rootValue.nodeName,'debug')          
          rootValueID = rootValue.attributes["id"].value
          ## self.logger("initFieldWithFieldName() Searching rootValueID: %s" % rootValueID,'debug')
          if rootValueID == "COMPLETE":
            didComplete = rootValue.childNodes[1].childNodes[0].data
            if not didComplete:
              break;
            searchResultCount += 1
          elif rootValueID == "METADATA":
            myField = FCSXMLField()
            for value in rootValue.getElementsByTagName("values")[0].childNodes:
              if not value.nodeType == 1:
                ##self.logger("initFieldWithFieldName() Skipping nodetype: %s" % value.nodeType,'debug')  
                continue
                        
              try:
                valueID = value.attributes["id"].value
                ##self.logger("initFieldWithFieldName() - Found METADATA value node"
                ##" with ID: %s" % valueID,'debug')  
              except: 
                continue
              if valueID == "FIELD_NAME":
                myField.name = value.childNodes[1].childNodes[0].data
                ##self.logger("initFieldWithFieldName() Testing field with name: %s" % myField.name,'debug')
                if not myField.name:
                  break;
                elif myField.name == fieldName:
                  didFindMatch = True
                  matchType = "exact"
                elif myField.name.lower() == fieldName.lower():
                  didFindMatch = True
                  matchType = "caseinsensitive"                    
                else:
                  if len(myField.name) > len(fieldName):
                    if testFieldName[0:len(fieldName)].lower() == fieldName.lower():
                      didFindMatch = True
                      matchType = "substring"
                  else:
                    if fieldName[0:len(myField.name)].lower() == myField.name.lower():
                      didFindMatch = True
                      matchType = "substring"
              elif valueID == "FIELD_ID":
                myField.dbname = value.childNodes[1].childNodes[0].data
              elif valueID == "FIELD_DATA_TYPE":
                dbDataType = value.childNodes[1].childNodes[0].data
                ## if datatype is ktAtom, then we are a system field.
                if dbDataType == 'KtAtom' or dbDataType == 'KtAddress':
                  continue
                try:
                  myField.setDBDataType(dbDataType)
                except:
                  self.logger('An unknown error occurred setting dataType:%s'
                      ', skipping field.)' % dbDataType,'warning')
                  continue
              
            if didFindMatch and myField:
              self.logger("initFieldWithFieldName() Found match:%s for fieldname: %s" % (matchType,myField.name),'debug')
              if matchType == "exact":
                exactMatches.append(myField)
              elif matchType == "caseinsensitive":
                caseInsensitiveMatches.append(myField)
              elif matchType == "substring":
                partialMatches.append(myField)
              
                
                                           
    #except:
    #  self.logger("Uncaught exception reading field name for dbFieldName:%s" % dbFieldName,'debug')
    #  return False
    
    myField = ""
    ## analyze our findings
    if len(exactMatches) == 1:
      self.logger("Found exact match for field name:%s, dbname:%s" % (fieldName,exactMatches[0].dbname),'warning')
      myField = exactMatches[0]
    elif len(exactMatches) > 1:
      self.logger("Found %s exact matches for field name:%s, determining best result" % (len(exactMatches),fieldName),'warning')
      result = ""
      ## Determine the most appropriate match based on DB Name, order of preference:
      ## PA_MD_CUST_, CUST_
      currentResultPriority = 0
      for field in exactMatches:
        dbname = field.dbname
        ## First look for an exact match for our field, using our field name
        ## with caps.
        idealPartialDBName = field.name.replace(" ","_").upper()
        ##self.logger('initFieldWithFieldName() idealPartialName:%s, %s' 
          ##% (idealPartialDBName,dbname[0:5+len(idealPartialDBName)]),'debug')
        if dbname[0:11+len(idealPartialDBName)] == "PA_MD_CUST_%s" % idealPartialDBName:
          self.logger("Found match for ideal DB Name: %s for field name:%s" 
            % (field.dbname,field.name),'debug')
          myResultPriority = 10
          if myResultPriority > currentResultPriority:
            result = field
            currentResultPriority = myResultPriority
        elif dbname[0:5+len(idealPartialDBName)] == "CUST_%s" % idealPartialDBName:
          self.logger("Found match for ideal DB Name: %s for field name:%s" 
            % (dbname,field.name),'debug')
          myResultPriority = 9
          if myResultPriority > currentResultPriority:
            result = field
            currentResultPriority = myResultPriority
        elif dbname[0:11] == "PA_MD_CUST_":
          self.logger("Found PA_MD_CUST type field:%s for field name:%s" 
            % (dbname,field.name),'debug')
          result = field
          myResultPriority = 8
          if myResultPriority > currentResultPriority:
            result = field
            currentResultPriority = myResultPriority
        elif dbname[0:5] == "CUST_":
          self.logger("Found CUST_ type field:%s for field name:%s" 
            % (dbname,field.name),'debug')
          result = field
          myResultPriority = 7
          if myResultPriority > currentResultPriority:
            result = field
            currentResultPriority = myResultPriority
      
      if result:
        myField = result
      else:
        self.logger("Returning last result:%s for field name:'%s'" % (dbname,fieldName),'warning')
        myField = field
    elif len(caseInsensitiveMatches) == 1:
      myField = caseInsensitiveMatches[0]
    elif len(caseInsensitiveMatches) > 1:
      self.logger("Found %s matches for field name:%s, returning first result!" % (len(exactMatches),fieldName),'warning')
      myField = caseInsensitiveMatches[0]      
    elif len(partialMatches) == 1:
      self.logger("Found more than one partial match for field name:%s, returning first result" % fieldName,'warning')
      myField = partialMatches[0]
    elif len(partialMatches) > 1:
      self.logger("Found %s matches for field name:%s, returning first result!" % (len(exactMatches),fieldName),'warning')
      myField = partialMatches[0]  
    else:
      raise RuntimeError("An error occured while determining preferred value from matches for fieldName:%s!" % fieldName)
    
    if myField:
      self.logger("Found dbFieldName: %s for fieldName: %s with dataType: %s"
                     % (myField.dbname,myField.name,myField.dataType),'debug')
      return myField
    else:
      return False

  def assetWithField(self,field,mdSet='',matchType='exact'):
    '''Returns a new FCSVRClient object matching the provided 
    :class:`fcsxml.FCSXMLObject`.
    
    :param field: Provide the field to match
    :type field: fcsxml.FCSXMLObject
    :param mdSet: An optional parameter that can be provided to limit search
      results to a specific FCS metadata set. This should be the FCS metadata
      set id (i.e. "pa_asset_media") 
    :type mdSet: str
    :param matchType: An optional parameter to specify the search behavior.
      Currently two matchType's are supported: 'exact' (default), and 'substring'
    :type matchType: str
    
    :returns: (*fcsxml.FCSVRClient*) -- Asset entity matching provided parameters.
    
    :raises: FCSEntityNotFoundError
    
    .. versionadded:: 1.0b
    
    '''
    
    self.logger('Retrieving Asset for field:%s' % field.name,'debug')
    
    ## Run our fcsvr_client command.
    '''
    fcsvrCMDTXT = ('"%s" search --crit  "%s" /asset --xml' 
                              % (self.pathToFCSVRClient,title))
    '''
    #### Generate our search XML file
    ## Create our title field
    XMLSearchFilePath = self.generateSearchXML(fields=[field],
                                                         matchType=matchType)
                                                         
    if field.dbname:
      dbname = field.dbname
    else:
      dbname = self.dbFieldNameForFieldName(field.name)

    fieldValue = field.value
      
    self.logger("Searching for field with DBNAME: %s with value: %s" 
                                          % (dbname,fieldValue),'debug')
      
    
    fcsvrCMDTXT = ('"%s" search /asset --xml --xmlcrit < "%s"' 
                              % (self.pathToFCSVRClient,XMLSearchFilePath))
                              
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
                                  
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command:\'%s\'' % fcsvrCMDTXT,'debug')

    ## Delete our temp search file
    if not self.keepFiles:
      os.remove(XMLSearchFilePath)

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)   

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: \'%s\''
                       % fcsvrCMDTXT,'error')
      raise RuntimeError('fcsvr_client returned unexpected results!')

      
    didComplete = False
    #try:
    matches = []    
    searchRoot = myDom.childNodes[0]
    searchResultCount = 0
    
    ## Iterate through the DOM and extract our results.
    for searchResult in searchRoot.childNodes:
      ##self.logger("productionWithTitle() Searching nodename: %s" % searchResult.nodeName,'debug')
      if searchResult.nodeName == 'values':
        searchResultDict = {} 
        didFindMatch = False
        for rootValue in searchResult.getElementsByTagName('value'):
          ## This is the result level, here for each result
          ##self.logger("productionWithTitle() rootValue nodename: %s" % rootValue.nodeName,'debug')          
          rootValueID = rootValue.attributes['id'].value
          ##self.logger('productionWithTitle() Searching rootValueID: %s' % rootValueID,'debug')
          if rootValueID == 'COMPLETE':
            didComplete = rootValue.childNodes[1].childNodes[0].data
            if not didComplete:
              break;
            searchResultCount += 1
          elif rootValueID == 'METADATA':
            for value in rootValue.getElementsByTagName('value'):
              valueID = value.attributes['id'].value
              '''self.logger('Comparing node: %s, looking for %s' 
                % (valueID,dbname),'debug')'''
              if valueID == dbname:
                theFieldValue = value.childNodes[1].childNodes[0].data
                '''self.logger(' - FOUND NODE:%s with value:%s' 
                                        % (dbname,theFieldValue),'debug')'''
                if not theFieldValue:
                  break;
                elif fieldValue == theFieldValue:
                  didFindMatch = True
                  searchResultDict['matchType'] = 'exact'
                elif fieldValue.strip() == theFieldValue.strip():
                  didFindMatch = True
                  searchResultDict['matchType'] = 'exact_whitespace'
                elif fieldValue.lower() == theFieldValue.lower():
                  didFindMatch = True
                  searchResultDict['matchType'] = 'caseinsensitive'                    
                elif fieldValue.lower().strip() == theFieldValue.lower().strip():
                  didFindMatch = True
                  searchResultDict['matchType'] = 'caseinsensitive_whitespace'
                elif fieldValue in theFieldValue:
                  didFindMatch = True
                  searchResultDict['matchType'] = 'substring'
                else:
                  if len(fieldValue) > len(theFieldValue):
                    if fieldValue[0:len(theFieldValue)].lower() == theFieldValue.lower():
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
                    elif fieldValue.lower() in theFieldValue.lower():
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
                  else:
                    if theFieldValue[0:len(fieldValue)].lower() == fieldValue.lower():
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
                    elif fieldValue in theFieldValue:
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
              if valueID == 'ASSET_TYPE':
                searchResultDict['ASSET_TYPE'] = value.childNodes[1].childNodes[0].data
              if valueID == 'ASSET_NUMBER':
                searchResultDict['ASSET_NUMBER'] = value.childNodes[1].childNodes[0].data

              
        if didFindMatch and 'ASSET_NUMBER' in searchResultDict:
          matches.append(searchResultDict)
           
                                           
    #except:
    #  self.logger("Uncaught exception reading field name for dbFieldName:%s" % dbFieldName,'debug')
    #  return False
    
    #### Analyze our findings
    
    ## If only one match was found, return it 
    theMatch = ''
    if len(matches) == 1:
      self.logger('Found Asset: /asset/%s for search string: \'%s\'' 
                                % (matches[0]['ASSET_NUMBER'],fieldValue),'detailed')
      self.logger('   Match Type: %s' % matches[0]['matchType'],'debug') 
      theMatch = matches[0]
    elif not matches:
      self.logger('Found no assets matching search string: \'%s\'' % fieldValue,'error')
      raise FCSEntityNotFoundError(entityType='asset',entityTitle=fieldValue)
    elif matches > 1:

      self.logger('Found %s assets matching search string: \'%s\'' 
                                            % (len(matches),fieldValue),'detailed')

      
      rankedMatches = []
      topScore = 0
      topScoreConflict = False
      
      ## Iterate through our matches for ranking.
      for result in matches:
        searchScore = 0      
        if result['matchType'] == 'exact':
          searchScore += 50
        elif result['matchType'] == 'exact_whitespace':
          searchScore += 45
        elif result['matchType'] == 'caseinsensitive':
          searchScore += 25
        elif result['matchType'] == 'caseinsensitive_whitespace':
          searchScore += 20
        elif result['matchType'] == 'substring_whitespace':
          searchScore += 2
        elif result['matchType'] == 'substring':
          searchScore += 1
        if 'ASSET_TYPE' in result and mdSet and result['ASSET_TYPE'].lower() == mdSet.lower():
          searchScore += 50
        result['searchScore'] = searchScore
        
        ## Insert it in the appropriate rank, based on searchScore, break when we 
        ## get to an object who's score is less then ours
        count=0
        while count < len(rankedMatches):
          if rankedMatches[count]['searchScore'] < result['searchScore']:
            break
          elif (rankedMatches[count]['searchScore'] == result['searchScore'] 
          and result['searchScore'] == topScore):
            self.logger('assetWithTitle() Found top score conflict: %s asset:'
                      ' /project/%s' % (topScore,result['ASSET_NUMBER']),'debug')
            topScoreConflict = True
            count += 1
          else:
            count += 1

        ## insert our object
        if count == 0:
          if result['searchScore'] > topScore:
            self.logger('assetWithTitle() Found new top score: %s asset: /asset/%s' 
                          % (result['searchScore'],result['ASSET_NUMBER']),'debug')
            topScore = result['searchScore']
            topScoreConflict = False
          
        rankedMatches.insert(count,result)
      
      if topScoreConflict:
        self.logger('Found more than one Asset with same search score: %s,'
          ' returning first result! (/asset/%s) ' 
          % (topScore,rankedMatches[0]['ASSET_NUMBER']),'warning')
        theMatch = rankedMatches[0]
      else:
        self.logger('Found more than one Asset, returning result with '
          'highest search score:%s! (/asset/%s)  '
          % (rankedMatches[0]['searchScore'],
              rankedMatches[0]['ASSET_NUMBER'])
              ,'detailed')
        theMatch = rankedMatches[0]
    
    if theMatch:
      theAsset = FCSVRClient(configParser=self.configParser)
      if self.debug:
        theAsset.debug = True
      if self.printLogs:
        theAsset.printLogs = True
        
      theAsset.entityType = 'asset'
      theAsset.entityID = theMatch['ASSET_NUMBER']
      theAsset.entityMetadataSet = theMatch['ASSET_TYPE']
      if mdSet and not mdSet == theAsset.entityMetadataSet:
        raise FCSEntityNotFoundError(entityTitle=fieldValue,entityMDSet=mdSet)
    else:
      raise FCSEntityNotFoundError(entityTitle=fieldValue)
    
    return theAsset


  def assetWithTitle(self,title,mdSet='',matchType='exact'):
    '''Returns a new FCSVRClient object matching the provided title. 
    
    :param title: Provide the asset title to search for
    :type title: str
    :param mdSet: An optional parameter that can be provided to limit search
      results to a specific FCS metadata set. This should be the FCS metadata
      set id (i.e. "pa_asset_media") 
    :type mdSet: str
    :param matchType: An optional parameter to specify the search behavior.
      Currently two matchType's are supported: 'exact' (default), and 'substring'
    :type matchType: str
    
    :returns: (*fcsxml.FCSVRClient*) -- Asset entity matching provided parameters.
    
    :raises: FCSEntityNotFoundError
    
    .. versionadded:: .96b
    
    '''
    
    title = title.replace('`',"'").replace('"',"'")
    
    self.logger('Retrieving Asset for name:%s' % title,'debug')
    
    ## Run our fcsvr_client command.
    '''
    fcsvrCMDTXT = ('"%s" search --crit  "%s" /asset --xml' 
                              % (self.pathToFCSVRClient,title))
    '''
    #### Generate our search XML file
    ## Create our title field
    myTitleField = FCSXMLField(name='Title',dbname='CUST_TITLE',value=title)

    XMLSearchFilePath = self.generateSearchXML(fields=[myTitleField],
                                                         matchType=matchType)
    
    fcsvrCMDTXT = ('"%s" search /asset --xml --xmlcrit < "%s"' 
                              % (self.pathToFCSVRClient,XMLSearchFilePath))
                              
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
                                  
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command:\'%s\'' % fcsvrCMDTXT,'debug')

    ## Delete our temp search file
    if not self.keepFiles:
      os.remove(XMLSearchFilePath)

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)   

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: \'%s\''
                       % fcsvrCMDTXT,'error')
      raise RuntimeError('fcsvr_client returned unexpected results!')

      
    didComplete = False
    #try:
    matches = []    
    searchRoot = myDom.childNodes[0]
    searchResultCount = 0
    
    ## Iterate through the DOM and extract our results.
    for searchResult in searchRoot.childNodes:
      ##self.logger("productionWithTitle() Searching nodename: %s" % searchResult.nodeName,'debug')
      if searchResult.nodeName == 'values':
        searchResultDict = {} 
        didFindMatch = False
        for rootValue in searchResult.getElementsByTagName('value'):
          ## This is the result level, here for each result
          ##self.logger("productionWithTitle() rootValue nodename: %s" % rootValue.nodeName,'debug')          
          rootValueID = rootValue.attributes['id'].value
          ##self.logger('productionWithTitle() Searching rootValueID: %s' % rootValueID,'debug')
          if rootValueID == 'COMPLETE':
            didComplete = rootValue.childNodes[1].childNodes[0].data
            if not didComplete:
              break;
            searchResultCount += 1
          elif rootValueID == 'METADATA':
            for value in rootValue.getElementsByTagName('value'):
              valueID = value.attributes['id'].value
              ##self.logger('assetWithTitle() Searching value: %s' % valueID,'debug')
              if valueID == 'CUST_TITLE':
                testTitle = value.childNodes[1].childNodes[0].data
                if not testTitle:
                  break;
                elif testTitle == title:
                  didFindMatch = True
                  searchResultDict['matchType'] = 'exact'
                elif testTitle.strip() == title.strip():
                  didFindMatch = True
                  searchResultDict['matchType'] = 'exact_whitespace'
                elif testTitle.lower() == title.lower():
                  didFindMatch = True
                  searchResultDict['matchType'] = 'caseinsensitive'                    
                elif testTitle.lower().strip() == title.lower().strip():
                  didFindMatch = True
                  searchResultDict['matchType'] = 'caseinsensitive_whitespace'
                elif testTitle in title:
                  didFindMatch = True
                  searchResultDict['matchType'] = 'substring'
                else:
                  if len(testTitle) > len(title):
                    if testTitle[0:len(title)].lower() == title.lower():
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
                    elif testTitle.lower() in title.lower():
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
                  else:
                    if title[0:len(testTitle)].lower() == testTitle.lower():
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
                    elif testTitle in title:
                      didFindMatch = True
                      searchResultDict['matchType'] = 'substring'
              elif valueID == 'ASSET_TYPE':
                searchResultDict['ASSET_TYPE'] = value.childNodes[1].childNodes[0].data
              elif valueID == 'ASSET_NUMBER':
                searchResultDict['ASSET_NUMBER'] = value.childNodes[1].childNodes[0].data

              
        if didFindMatch and 'ASSET_NUMBER' in searchResultDict:
          matches.append(searchResultDict)
           
                                           
    #except:
    #  self.logger("Uncaught exception reading field name for dbFieldName:%s" % dbFieldName,'debug')
    #  return False
    
    #### Analyze our findings
    
    ## If only one match was found, return it 
    theMatch = ''
    if len(matches) == 1:
      self.logger('Found Asset: /asset/%s for search string: \'%s\'' 
                                % (matches[0]['ASSET_NUMBER'],title),'detailed')
      self.logger('   Match Type: %s' % matches[0]['matchType'],'debug') 
      theMatch = matches[0]
    elif not matches:
      self.logger('Found no assets matching search string: \'%s\'' % title,'error')
      raise FCSEntityNotFoundError(entityType='asset',entityTitle=title)
    elif matches > 1:

      self.logger('Found %s assets matching search string: \'%s\'' 
                                            % (len(matches),title),'detailed')

      
      rankedMatches = []
      topScore = 0
      topScoreConflict = False
      
      ## Iterate through our matches for ranking.
      for result in matches:
        searchScore = 0      
        if result['matchType'] == 'exact':
          searchScore += 50
        elif result['matchType'] == 'exact_whitespace':
          searchScore += 45
        elif result['matchType'] == 'caseinsensitive':
          searchScore += 25
        elif result['matchType'] == 'caseinsensitive_whitespace':
          searchScore += 20
        elif result['matchType'] == 'substring_whitespace':
          searchScore += 2
        elif result['matchType'] == 'substring':
          searchScore += 1
        if 'ASSET_TYPE' in result and mdSet and result['ASSET_TYPE'].lower() == mdSet.lower():
          searchScore += 50
        result['searchScore'] = searchScore
        
        ## Insert it in the appropriate rank, based on searchScore, break when we 
        ## get to an object who's score is less then ours
        count=0
        while count < len(rankedMatches):
          if rankedMatches[count]['searchScore'] < result['searchScore']:
            break
          elif (rankedMatches[count]['searchScore'] == result['searchScore'] 
          and result['searchScore'] == topScore):
            self.logger('assetWithTitle() Found top score conflict: %s asset:'
                      ' /project/%s' % (topScore,result['ASSET_NUMBER']),'debug')
            topScoreConflict = True
            count += 1
          else:
            count += 1

        ## insert our object
        if count == 0:
          if result['searchScore'] > topScore:
            self.logger('assetWithTitle() Found new top score: %s asset: /asset/%s' 
                          % (result['searchScore'],result['ASSET_NUMBER']),'debug')
            topScore = result['searchScore']
            topScoreConflict = False
          
        rankedMatches.insert(count,result)
      
      if topScoreConflict:
        self.logger('Found more than one Asset with same search score: %s,'
          ' returning first result! (/asset/%s) ' 
          % (topScore,rankedMatches[0]['ASSET_NUMBER']),'warning')
        theMatch = rankedMatches[0]
      else:
        self.logger('Found more than one Asset, returning result with '
          'highest search score:%s! (/asset/%s)  '
          % (rankedMatches[0]['searchScore'],
              rankedMatches[0]['ASSET_NUMBER'])
              ,'detailed')
        theMatch = rankedMatches[0]
    
    if theMatch:
      theAsset = FCSVRClient(configParser=self.configParser)
      if self.debug:
        theAsset.debug = True
      if self.printLogs:
        theAsset.printLogs = True
        
      theAsset.entityType = 'asset'
      theAsset.entityID = theMatch['ASSET_NUMBER']
      theAsset.entityMetadataSet = theMatch['ASSET_TYPE']
      if mdSet and not mdSet == theAsset.entityMetadataSet:
        raise FCSEntityNotFoundError(entityTitle=title,entityMDSet=mdSet)
    else:
      raise FCSEntityNotFoundError(entityTitle=title)
    
    return theAsset

  
  def productionWithTitle(self,title,mdSet="",matchType='exact'):
    '''Returns a new FCSVRClient production/project object matching the 
    provided production title. 
    
    :param title: Provide the production title to search for
    :type title: str
    :param mdSet: An optional parameter that can be provided to limit search
      results to a specific FCS metadata set. This should be the FCS metadata
      set id (i.e. "pa_production_show") 
    :type mdSet: str
    :param matchType: An optional parameter to specify the search behavior.
      Currently two matchType's are supported: 'exact' (default), and 'substring'
    :type matchType: str
    
    :returns: (*fcsxml.FCSVRClient*) -- Asset entity matching provided parameters.
    
    :raises: FCSEntityNotFoundError
    
    
    '''
    
    title = title.replace("`","'").replace('"',"'")
    
    if not title or title == " ":
      msg = 'Could not load production, an empty title was provided!'
      self.logger(msg,'error')
      raise FCSProductionLoadError(msg)
      
    self.logger("Retrieving Production for name:%s" % title,'debug')
    
    ## Run our fcsvr_client command.
    ##fcsvrCMDTXT = '"%s" search --crit  "%s" /project --xml' % (self.pathToFCSVRClient,title)
    
    #### Generate our search XML file
    ## Create our title field
    myTitleField = FCSXMLField(name='Title',dbname='CUST_TITLE',value=title)

    XMLSearchFilePath = self.generateSearchXML(fields=[myTitleField],
                                                            matchType=matchType)
    
    fcsvrCMDTXT = ('"%s" search /project --xml --xmlcrit < "%s"' 
                              % (self.pathToFCSVRClient,XMLSearchFilePath))
    
    fcsvrCMD = subprocess.Popen(fcsvrCMDTXT,shell=True,stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command: fcsvr_client  search /project --xml'
      ' --xmlcrit < "%s"' % XMLSearchFilePath,'debug')

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)
    
    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: '
        'fcsvr_client  search /project --xml --xmlcrit < "%s"' % XMLSearchFilePath,
        'error')
      raise RuntimeError("fcsvr_client returned unexpected results!")

    ## remove our file from disk
    if not self.keepFiles:
      os.remove(XMLSearchFilePath)
      
    didComplete = False
    #try:
    matches = []    
    searchRoot = myDom.childNodes[0]
    searchResultCount = 0
    
    ## Iterate through the DOM and extract our results.
    for searchResult in searchRoot.childNodes:
      ##self.logger("productionWithTitle() Searching nodename: %s" % searchResult.nodeName,'debug')
      if searchResult.nodeName == "values":
        searchResultDict = {} 
        didFindMatch = False
        for rootValue in searchResult.getElementsByTagName("value"):
          ## This is the result level, here for each result
          ##self.logger("productionWithTitle() rootValue nodename: %s" % rootValue.nodeName,'debug')          
          rootValueID = rootValue.attributes["id"].value
          ##self.logger("productionWithTitle() Searching rootValueID: %s" % rootValueID,'debug')
          if rootValueID == "COMPLETE":
            didComplete = rootValue.childNodes[1].childNodes[0].data
            if not didComplete:
              break;
            searchResultCount += 1
          elif rootValueID == "METADATA":
            for value in rootValue.getElementsByTagName("value"):
              valueID = value.attributes["id"].value
              self.logger("productionWithTitle() Searching value: %s" % valueID,'debug')
              if valueID == "CUST_TITLE":
                testTitle = value.childNodes[1].childNodes[0].data
                if not testTitle:
                  break;
                elif testTitle == title:
                  didFindMatch = True
                  searchResultDict["matchType"] = "exact"
                elif testTitle.lower() == title.lower():
                  didFindMatch = True
                  searchResultDict["matchType"] = "caseinsensitive"                    
                else:
                  if len(testTitle) > len(title):
                    if testTitle[0:len(title)].lower() == title.lower():
                      didFindMatch = True
                      searchResultDict["matchType"] = "substring"
                  else:
                    if title[0:len(testTitle)].lower() == testTitle.lower():
                      didFindMatch = True
                      searchResultDict["matchType"] = "substring"
              elif valueID == "PROJECT_TYPE":
                searchResultDict["PROJECT_TYPE"] = value.childNodes[1].childNodes[0].data
              elif valueID == "PROJECT_NUMBER":
                searchResultDict["PROJECT_NUMBER"] = value.childNodes[1].childNodes[0].data

              
        if didFindMatch and "PROJECT_NUMBER" in searchResultDict:
          matches.append(searchResultDict)
           
                                           
    #except:
    #  self.logger("Uncaught exception reading field name for dbFieldName:%s" % dbFieldName,'debug')
    #  return False
    
    #### Analyze our findings
    
    ## If only one match was found, return it 
    theMatch = ""
    if len(matches) == 1:
      self.logger("Found Production: /project/%s for search string: '%s'" % (matches[0]["PROJECT_NUMBER"],title),"detailed")
      theMatch = matches[0]
    elif not matches:
      self.logger("Found no productions matching search string: '%s'" % title,'error')
      raise RuntimeError("No production found for title: '%s'" % title)
    elif matches > 1:

      self.logger("Found %s productions matching search string: '%s'" % (len(matches),title),"detailed")

      
      rankedMatches = []
      topScore = 0
      topScoreConflict = False
      
      ## Iterate through our matches for ranking.
      for result in matches:
        searchScore = 0      
        if result["matchType"] == "exact":
          searchScore += 50
        elif result["matchType"] == "caseinsensitive":
          searchScore += 25
        elif result["matchType"] == "substring":
          searchScore += 1
        if "PROJECT_TYPE" in result and mdSet and result["PROJECT_TYPE"].lower() == mdSet.lower():
          searchScore += 50
        result["searchScore"] = searchScore
        
        ## Insert it in the appropriate rank, based on searchScore, break when we 
        ## get to an object who's score is less then ours
        count=0
        while count < len(rankedMatches):
          if rankedMatches[count]["searchScore"] < result["searchScore"]:
            break
          elif rankedMatches[count]["searchScore"] == result["searchScore"] and result["searchScore"] == topScore:
            self.logger("productionWithTitle() Found top score conflict: %s production: /project/%s" % (topScore,result["PROJECT_NUMBER"]),'debug')
            topScoreConflict = True
            count += 1
          else:
            count += 1

        ## insert our object
        if count == 0:
          if result["searchScore"] > topScore:
            self.logger("productionWithTitle() Found new top score: %s production: /project/%s" % (result["searchScore"],result["PROJECT_NUMBER"]),'debug')
            topScore = result["searchScore"]
            topScoreConflict = False
          
        rankedMatches.insert(count,result)
      
      if topScoreConflict:
        self.logger("Found more than one Production with same search score: %s, returning first result! (/project/%s) " % (topScore,rankedMatches[0]["PROJECT_NUMBER"]),'warning')
        theMatch = rankedMatches[0]
      else:
        self.logger("Found more than one Production, returning result with higest search score:%s! (/project/%s)  " % (rankedMatches[0]["searchScore"],rankedMatches[0]["PROJECT_NUMBER"]),"detailed")
        theMatch = rankedMatches[0]
    
    if theMatch:
      theProduction = FCSVRClient(configParser=self.configParser)
      theProduction.entityType = "project"
      theProduction.entityID = theMatch["PROJECT_NUMBER"]
      theProduction.entityMetadataSet = theMatch["PROJECT_TYPE"]
    else:
      raise RuntimeError("No production found for title: '%s'" % title)
    
    
    return theProduction
    
  
  def createProduction(self,title="",mdSet="",parentProjectAddress="",setMD=False):
    '''This method will create a new production based upon loaded and provided
    values.
    
    :param title: Provide the new production's title.
    :type title: str
    :param mdSet: specify the metadata set for the new production. If none
      is provided, we will use the default.
    :type mdSet: str
    :param parentProjectAddress: If desired, provide an entity path 
      (i.e. /project/10) to link this production to.
    :type parentProjectAddress: str
    :param setMD: Flag to determine if stored fields will be written to the newly
      created production.
    :type setMD: bool
    
    :returns: (:class:`fcsxml.FCSVRClient`) -- The new FCSVRClient object loaded
      with the provided information; if our current object was a 'project' type
      entity, values will be loaded locally as well.
    
    :raises: FCSProductionLoadError
    
    .. note: Although the title parameter itself is not mandatory, a title
      itself is: If a title isn't defined explicitely, then a FCSXMLField
      object with name "Title" must be loaded in our current object.
      
      
    
    '''
    ## Method to create a production, If our entity type is not 'project', 
    ## and we are not passed a title abort. If our entity type is 'project',
    ## try to read our title from our fields. 
    
    if not mdSet:
      mdSet = self.defaultProductionMetadataSet
    
    if not mdSet:
      self.logger("Could not create production: no metadata set specified!",'error')
      raise FCSProductionLoadError("Could not create production! No metadata set specified!")

    
    if not title:
      title = self.valueForField("Title")
      if not title:
        self.logger("Could not create production: no title specified!",'error')
        raise FCSProductionLoadError("Could not create production! No title specified!")

    ## if we are currently a project type asset, load ourselves, otherwise,
    ## return a duplicated object.
    if self.entityType == "project":
      obj = self
    else:
      obj = copy.copy(self)
      
    ## If setMD is set to true and we have no fields at this point, throw a 
    ## warning and change setMD to false
    if setMD and not self.fields:
      self.logger("Creating production with metadata, but no fields are loaded! (No metadata to set)",'warning')
      setMD = False
        
    ## Set our title field
    titleField = FCSXMLField(name="Title",dbname="CUST_TITLE",value=title)
    obj.setField(titleField)
    
    ## Construct our fcsvr_client arguments
    cmdArgs = ' create /project --type %s' % mdSet
    if parentProjectAddress:
      cmdArgs += ' --linkparentaddr %s --linkparentlinktype 16' % parentProjectAddress
    
    ## If we are importing MD, insert our file args
    ## note 2/7/09: this is temporarily disable until I fix the XML output
    ## to ensure proper formatting during asset creation, for now we're 
    ## just calling setMD after the asset is created, which works fine.
    '''
    tempFilePath = ""
    if setMD:
      tempFilePath = self.generateTempXMLFile()
      if os.path.isfile(tempFilePath):
        cmdArgs += ' --xml "%s"' % tempFilePath
      else:
        self.logger("XML File does not exist at path:'%s', cannot import metadata!",'error')
        cmdArgs += ' CUST_TITLE="%s"' % (title.replace('"',"'"))
    else:
      cmdArgs += ' CUST_TITLE="%s"' % (title.replace('"',"'"))
    '''
    cmdArgs += ' CUST_TITLE="%s"' % (title.replace('"',"'"))
    
    if not os.geteuid() == 0:
      if not self.useSudo:
        self.logger("Could not set Metadata, root privileges are required!",'error')
        raise FCSProductionLoadError("Updating metadata requires root privileges!")
      useSudo = True
    else:
      useSudo = False
      
    if useSudo:
      fcsvrCMDTXT = "/usr/bin/sudo '%s' %s" % (self.pathToFCSVRClient,cmdArgs)
    else:
      fcsvrCMDTXT = "'%s' %s" % (self.pathToFCSVRClient,cmdArgs)
      
    self.logger('fcsvrCMD:\n  %s' % fcsvrCMDTXT,'debug')
    
    ## run fcsvr_client
    fcsvrCMD = subprocess.Popen('%s' % fcsvrCMDTXT ,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger("fcsvr_client output: %s" % fcsvrCMD_STDOUT,'debug')

    if not fcsvrCMD.returncode == 0:
      errorString = '%s\n%s' % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR)
      self.logger("FCSVRClient Error: %s" % errorString,'error')
      raise FCSProductionLoadError('Could not create production!',errorString,fcsvrCMDTXT)
  
    ## Resolve our entity ID from STDOUT
    try:
      match = re.match("/project/(\d+)",fcsvrCMD_STDOUT)
      projectID = match.group(1)
    except:
      self.logger("Could not retrieve project id from string: %s" % fcsvrCMD_STDOUT,'error')
      raise FCSProductionLoadError('Could not find /project/id in results!',fcsvrCMD_STDOUT,'fcsvrCMDTXT')
    
    self.logger("Created new Production with ID:%s" % projectID,'debug')
    obj.entityID = projectID
    obj.entityType = "project"
    obj.entityMetadataSet = mdSet
  
    if setMD:
      obj.setMD()
    
    return obj
  
  def removeMemberFromProduction(self,member='',memberPath='',production='',
                                  productionPath='',tempProductionMDSet=''):
    ''' Removes a member from a production. Accepts either an FCSVRClient object
    (member) or a FCS entity path '/asset/10' (memberPath) in a addition
    to a FCSVRClient object with project entityType (production) or a 
    production path '/project/10' (productionPath). If calling instance
    is either a production or an asset, you can omit the appropriate arguments.
    We also accept tempProductionMDSet: which is the md set used to create
    a temporary production. (We do this because FCS can't explicitely delete an
    existing link, but it CAN relocate links).
    
    :param member: Provide an FCSVRClient object to remove. (optional)
    :type member: fcsxml.FCSVRClient
    :param memberPath: Provide an FCS entity Path (optional)
    :type memberPath: str
    :param production: Provide an FCSVRClient object representative of the
      production who's member will be removed. (optional)
    :type production: fcsxml.FCSVRClient
    :param productionPath: Provide an FCS entity Path representative of the 
      production who's member will be removed. (optional)
    :type productionPath: str
    :param tempProductionMDSet: Provide a metadata set type that will be used 
      to create a temporary production.
      
    :raises: FCSError, FCSValidationError
      
    .. note:
      Due to the fact that Final Cut Server has no native capabilities to remove
      production membership, we achieve this objective by creating a new 
      (temporary) production, moving the entities links to this new temp 
      production, and then deleting the temporary production. 
    
    For instance, if we have a loaded asset, we can remove it from our 
    production as follows:
    
    >>> myObj = fcsxml.FCSVRClient(entityType='asset',entityID=20)
    >>> myObj.removeMemberFromProduction(productionPath='/project/10')
    
    Or, alternatively, if we are a loaded production, we can remove an asset
    as follows (accomplishing the exact same thing as above):
    
    >>> myObj = fcsxml.FCSVRClient(entityType='project',entityID=10)
    >>> myObj.removeMemberFromProduction(memberPath='/asset/20')
    
    ''' 
    
    ## Resolve our child (asset or production) and parent (production)
    childObject = ''
    parentObject = ''
    
    ## Resolve our child (asset or production)
    if member:
      childObject = member
    elif memberPath:
      self.logger("Resolving member from entityPath:%s" % memberPath,'debug')
      pathMatch = re.match('\/(.*)\/(.*)',memberPath)
      if pathMatch:
        memberType = pathMatch.groups()[0]
        memberID = pathMatch.groups()[1]
        childObject = FCSVRClient(entityType=memberType,
                                              id=memberID,
                                              configParser=self.configParser)

    else:
      if (self.entityType == 'asset' or self.entityType == 'project') and self.entityID:
        childObject = self 
        
    if not tempProductionMDSet:
      tempProductionMDSet = self.defaultProductionMetadataSet
    
    ## Resolve our parent (production)
    if production:
      parentObject = production
    elif productionPath:
      self.logger("Resolving parent production from entityPath:%s" % productionPath,'debug')
      pathMatch = re.match('\/(.*)\/(.*)',memberPath)
      if pathMatch:
        memberType = pathMatch.groups()[0]
        memberID = pathMatch.groups()[1]
        parentObject = FCSVRClient(entityType=memberType,
                                                id=memberID,
                                                configParser=self.configParser)
      else:
        raise FCSValidationError('Could not remove member from production, parentPath:%s is invalid!')
    else:
      self.logger("Resolving parent production from local instance!",'debug')
      if self.entityType == 'project' and self.entityID:
        ##print "self:%s" % self
        parentObject = self
        ##print "parent:%s" % parentObject
        ##print "parentObject.entityPath:%s" % parentObject.debug

      else:
        raise FCSValidationError('Could not remove member from production, parentPath:%s is invalid!')
      
      
    ## At this point we should have both a child and parent object, perform
    ## sanity checks.
    
    ## Verify we have a parent object and it is a production
    if not parentObject:
      self.logger('removeMemberFromProduction() cannot continue: could not resolve parent production!','error')
      raise FCSValidationError('Cannot continue: could not resolve parent production!')
    elif parentObject.entityType != 'project':
      self.logger('removeMemberFromProduction() cannot continue: provided parent is not a production!','error')
      raise FCSValidationError('Cannot continue: provided parent is not a production!')
    
    ## Verify we have a child object.
    if not childObject:
      self.logger('removeMemberFromProduction() cannot continue: could not resolve member!','error')
      raise FCSError('removeMemberFromProduction() cannot continue: could not resolve member!','error')
    
    ## Verify the child and parent aren't referencing the same entity.
    parentEntityPath = parentObject.entityPath()
    childEntityPath = childObject.entityPath()
    if parentEntityPath == childEntityPath:
      self.logger('removeMemberFromProduction() cannot continue: provided '
                    ' member and production are the same:%s!' 
                    % parentObject.entityPath,'error')
      raise FCSError('removeMemberFromProduction() cannot continue: provided '
                    ' member and production reference the same entity: %s!' 
                    % parentObject.entityPath,'error')
                    
    ## At this point we have a legitimate child and parent, proceed to remove
    ## child from parent.
    
    ## Get current production members
    try:
      currentMembers = parentObject.productionMemberAddresses()
    except:
      currentMembers = []
      
    if not childEntityPath in currentMembers:
      self.logger('Could not remove entity:%s from production:%s, %s is not a '
                  'current member!' % (childEntityPath,
                                        parentEntityPath,
                                        childEntityPath),'error')
      return False
    
    ## Get a list of all our child's current parents
    childCurrentParents = childObject.parentProductions()
    
    ## Create a new temp production and use --movelink, which will destroy 
    ## all of the assets production memberships,we then rebuild all of 
    ## the memberships, short of the production which we are being removed
    ## from. Necessarily convoluted until fcsvr_client can explicitely remove
    ## links, but it works.
    tempProd = FCSVRClient(entityType='project',configParser=self.configParser)
    self.logger('removeMemberFromProduction() Creating temporary production'
                  ' with mdset:%s' % tempProductionMDSet)
    tempProd.createProduction(title='_temp_',mdSet=tempProductionMDSet)
    tempProd.fcsvr_client_make_link(linkType=1,
                                  parentPath=tempProd.entityPath(),
                                  childPath=childEntityPath,
                                  moveLink=True)
    ## Delete the temp production, the asset is now no longer a member of 
    ## ANY productions.
    tempProd.delete()
    
    ## Iterate through each pre-exsisting production link, and
    ## re-establish membership (provided it is not the provided parent 
    ## production, which we will NOT rejoin). (We do this 
    ## this way because fcsvr_client does not have support to explicitely
    ## remove links, all we have is --movelink)
    for parentPath in childCurrentParents:
      ## if we match our current production, which we are being removed 
      ## from, skip it.
      if parentEntityPath == parentPath:
        print "Removing asset:%s from production:%s" % (childEntityPath,
                                                            parentPath)
        continue
      
      
      ## re-establish membership to the current parentPath
      self.fcsvr_client_make_link(linkType=1,
                                    parentPath=parentPath,
                                    childPath=childEntityPath,
                                    moveLink=False)

    ## Flush our caches
    self.flushCaches()
    return True  
      
    
  
  def addMemberToProduction(self,member="",memberPath="",production="",productionPath="",moveLink=False):
    ''' Adds entity to the specified production. Accepts either a FCSVRClient 
    object (member) or a FCS entity path '/asset/10' (memberPath) in addition
    to a FCSVRClient object with entityType 'production', or a production
    path '/project/10'. If the local entity is either the member to be added,
    or is a production, then you can omit that information.
    
    :param member: Provide an FCSVRClient object to add. (optional)
    :type member: fcsxml.FCSVRClient
    :param memberPath: Provide an FCS entity Path (optional)
    :type memberPath: str
    :param production: Provide an FCSVRClient object representative of the
      production to which the member will be added. (optional)
    :type production: fcsxml.FCSVRClient
    :param productionPath: Provide an FCS entity Path representative of the 
      production to which the member will be added. (optional)
    :type productionPath: str
    :param moveLink: Specify whether this is an additional link for the asset,
      or if it will cancel out any other memberships. 
    :param moveLink: bool
    
    :raises: FCSError

    For instance, if we are a loaded production I can call:
    
    >>> myObj = fcsxml.FCSVRClient(entityType='project',entityID=10)
    >>> myObj.addMemberToProduction(memberPath='/asset/20')
    
    Which will add asset with ID 20 to our own membership. Likewise, we will
    accomplish the exact same thing if we call:
    
    >>> myObj = fcsxml.FCSVRClient(entityType='asset',entityID=20)
    >>> myObj.addMemberToProduction(productionPath='/project/10')
    
    Lastly, if we call:
    
    >>> myObj = fcsxml.FCSVRClient(entityType='project',entityID=10)
    >>> myObj.addMemberToProduction(productionPath='/project/12')
    
    We will add ourself (a production) as a child production to ``/project/12``. 

    
    .. versionadded:: .96b
    
    '''
    
    ## If no member information is given, assume that we are the member
    if not member and not memberPath:
      theMemberPath = self.entityPath()
    elif member and not memberPath:
      theMemberPath = member.entityPath()
    elif memberPath:
      theMemberPath = memberPath
    
    if not production and not productionPath and self.entityType == 'project':
      theProductionPath = self.entityPath()
    elif production and not productionPath and production.entityType == 'project':
      theProductionPath = production.entityPath()
    elif productionPath:
      theProductionPath = productionPath
      
    ## Make sure that our memberPath references either an asset or project
    ## Address
    try:
      memberType = theMemberPath.split('/')[1]
      if not memberType == "project" and not memberType == "asset":
        raise FCSError('Member type: %s not supported!' % memberType)
    except:
      self.logger('Member path: %s is not a project or asset, cannot continue!'
        % theMemberPath,'error')
      raise FCSValidationError('Could not add member to the production, member is neither'
        ' a production nor an asset')
    
    ## Make sure that our productionPath references a project address
    try:
      productionType = theProductionPath.split('/')[1]
      if not productionType == "project":
        raise
    except:
      message = ('Production path: %s is not a project or asset, cannot'
        ' continue!' % theProductionPath)
      self.logger(message,'error')
      raise FCSValidationError(message)
    
    ## Make sure we never add ourself to ourself
    if theProductionPath == theMemberPath:
      message = ('Cannot add Member Path: %s to Production path: %s, '
        ' one cannot add one to oneself!' % (theMemberPath,theProductionPath))
      self.logger(message,'error')
      raise FCSError(message)
    
    ''' movelink is now a passable argument.
    ## Create our link
    if memberType == 'project':
      moveLink = True
    else:
      moveLink = False
    '''
    return self.fcsvr_client_make_link(1,parentPath=theProductionPath,childPath=theMemberPath,moveLink=moveLink)

  
  def addAssetToProduction(self,asset="",assetID="",assetPath="",productionPath="",productionID=""):
    ''' Adds an asset to production.
     
    .. warning::
    
      This function is depricated as of 07/22/10, use the :py:func:`fcsxml.FCSVRClient.addMemberToProduction`
      class! 
      
    '''
    
    ## Resolve our asset information
    if not asset and not assetID and not assetPath:
        self.logger("addAssetToProduction() No asset information provided, aborting",'error')
        return False 
    if asset:
      if assetID and not asset.entityID == assetID:
        self.logger("addAssetToProduction() provided conflicting asset:%s and assetID:%s" % (asset.entityID,assetID),'error')
        return False
      if assetPath and not asset.entityPath() == assetPath:
        self.logger("addAssetToProduction() provided conflicting asset:%s and assetPath:%s"  % (asset.entityPath(),assetPath),'error')
        return False
      
      assetPath = asset.entityPath()
      assetID = asset.entityID
    elif assetID:
      if assetPath and not "/asset/%s" % assetID == assetPath:
        self.logger("addAssetToProduction() provided conflicting assetID:%s and assetPath:%s" % (assetID,assetPath),'error')
        return False
      else:
        assetPath = "/asset/%s" % assetID
      
    ## Resolve our production information
    if not productionPath and not productionID and not self.entityType == "project":
      self.logger("addAssetToProduction() No production information provided, aborting",'error')
      return False 
    elif not productionPath and not productionID and self.entityType == "project":
      productionID = self.entityID
      productionPath = self.entityPath()
    elif productionID:
      if productionPath and not "/project/%s" % productionID == productionPath:
        self.logger("addAssetToProduction() provided conflicting assetID:%s and assetPath:%s" % (assetID,assetPath),'error')
        return False
      assetPath = "/asset/%s" % assetID
      
    ## At this point we should have an assetPath and a productionPath
    if not assetPath and not productionPath:
      self.logger("addAssetToProduction() Could not resolve assetPath or productionPath,cannot continue!",'error')
      return False     
    
    ## Create our link
    self.logger("Adding asset:%s to production:%s" % (assetPath,productionPath),'error')

    return self.fcsvr_client_make_link(1,parentPath=productionPath,childPath=assetPath)
  
  def assetsFromProduction(self,productionID="",productionTitle="",recurse=False,mdSet=""):
    '''Function which returns a list of associated :class:`FCSVRClient` asset 
    objects. If recurse is set to true, we will return assets for subproductions 
    as well. If mdSet is provided, we will return only assets which have the 
    provided metadataset. This function utilizes 
    :func:`fcsxml.FCSVRClient.productionMemberAddresses`
    
    :param productionID: Specify the production ID to query (optional)
    :type productionID: int
    :param productionTitle: Specify a production title to query (optional)
    :type productionTitle: str
    :param recurse: Specify whether we will recurse through sub-productions
    :type recurse: bool
    :param mdSet: Specify a metadata set by which to filter results
    :type mdSet: str
    
    :raises: FCSValidationError, FCSProductionLoadError
    :returns: (*list*) -- A list of :class:`FCSVRClient` entries.
    
    
    .. note:  If no production ID or title is loaded, we will try to determine
      the target production from the calling object, in which case must have
      an entityType of 'project' 
      
    '''
    ## Determine our target production ID, which will be passed via
    ## the productionID or productionTitle parameters, if not, utilize the
    ## local object (if it's a 'project' entityType)
    
    if not productionID and not productionTitle:
      if self.entityType == "project" and self.entityID:
        productionID = self.entityID
      elif not self.entityType == "project":
        message = "Loaded entity is not a project and no ID or Title specified!"
        self.logger(message,'error')
        raise FCSValidationError(message,'error')
      else:
        message = "Must provide production ID or Title to search!"
        self.logger(message,'error')
        raise FCSValidationError(message,'error')
    elif not productionID and productionTitle:
      try: 
       production = self.productionWithTitle(title=productionTitle)
       productionID = production.entityID
      except:
        raise FCSProductionLoadError("Could not load production with Title: %s" % productionTitle)
    
    ## 
    if not productionID:
      self.logger("")
      raise FCSError("No production could be found!")
      
    ## Retrieve all asset addresses in the production.
    assetAddresses = self.productionAssetAddresses(productionID=productionID,
                        recurse=recurse)
    assets = []
    
    ## Iterate through each returned asset address and instantiate.
    for assetAddress in assetAddresses:
      regexMatch = re.match('/(.*)/(.*)',assetAddress)
      memberType = regexMatch.group(1)
      memberID = regexMatch.group(2)
      myAsset = FCSVRClient(id=memberID,configParser=self.configParser)
      myAsset.initWithAssetID(memberID)
      
      ## If no mdSet parameter was passed, otherwise ensure that our 
      ## mdSet matches.
      if not mdSet:
        assets.append(myAsset)
      elif mdSet and myAsset.entityMetadataSet == mdSet:
        assets.append(myAsset)
      elif mdSet and not myAsset.entityMetadataSet == mdSet:
        self.logger('assetsFromProduction() Asset: %s with mdSet: %s does not match'
        ' mdSet: %s, excluding!' 
        % (myAsset.entityPath(),myAsset.entityMetadataSet,mdSet),'debug')
        
      
    return assets
  
  def productionAssetAddresses(self,productionID="",
                                      productionTitle="",
                                      recurse=False):
                                      
    '''Function which returns asset addresses '/asset/12' from a production.
    If recurse is set to true, we will recurse through any nested productions 
    and collate their addresses. 
        
    :param productionID: Specify the production ID to query (optional)
    :type productionID: int
    :param productionTitle: Specify a production title to query (optional)
    :type productionTitle: str
    :param recurse: Specify whether we will recurse through sub-productions
    :type recurse: bool
   
    
    :raises: FCSValidationError, FCSProductionLoadError
    
    '''
    
    if not productionID and not productionTitle:
      if self.entityType == "project" and self.entityID:
        productionID = self.entityID
      elif not self.entityType == "project":
        self.logger("Loaded entity is not a project and no ID or Title specified!",'error')
        raise FCSValidationError("Loaded entity is not a project and no ID or Title specified!",'error')
      else:
        self.logger("Must provide production ID or Title to search!",'error')
        raise FCSValidationError("Loaded entity is not a project and no ID or Title specified!",'error')
    
    elif not productionID and productionTitle:
     production = self.productionWithTitle(title=productionTitle)
     productionID = production.entityID
      
    
    if not productionID:
      self.logger("")
      raise RuntimeError("No production could be found!")
    
    memberAddresses = self.productionMemberAddresses(productionID=productionID,
                                                productionTitle=productionTitle,
                                                recurse=recurse)
    
    assetAddresses = []
    productionAddresses = []
    processedProductionAddresses = ["/project/%s" % productionID]
    
    for memberAddress in memberAddresses:
      self.logger('productionAssetAddresses() processing member address: %s'
        % memberAddress,'debug')
      regexMatch = re.match('/(.*)/(.*)',memberAddress)
      memberType = regexMatch.group(1)
      memberID = regexMatch.group(2)
      if memberType == "asset":
        if memberAddress not in assetAddresses:
          assetAddresses.append(memberAddress)
      
      ''' Old code, this is now handled by productionMemberAddresses
      elif (memberType == "project" and recurse
      and memberAddress not in processedProductionAddresses):
        memberAddresses.extend(self.productionMemberAddresses(productionID=memberID))
      '''
      
    return assetAddresses
  
  def productionMemberAddresses(self,productionID="",productionTitle="",
                                    recurse=False,_processedMemberAddresses=None):
    '''Function which returns all entity addresses ['/asset/12','/project/10']
    from a production. If recurse is set to true, we will recurse through any 
    nested productions and collate their memberships. The 
    _processedMemberAddresses parameter is a list of previously processed 
    production addresses to prevent infinite recursion scenarios
    
    :param productionID: Specify the production ID to query (optional)
    :type productionID: int
    :param productionTitle: Specify a production title to query (optional)
    :type productionTitle: str
    :param recurse: Specify whether we will recurse through sub-productions
    :type recurse: bool
    :param _processedMemberAddresses: Specify a list of previously processed 
      production addresses (used internally to prevent infinite recursion)
    :type _processedMemberAddresses: list
    
    :raises: FCSValidationError, FCSProductionLoadError, FCSEntityNotFoundError
    
    '''
    
    if not productionID and not productionTitle:
      if self.entityType == "project" and self.entityID:
        productionID = self.entityID
      elif not self.entityType == "project":
        message = "Loaded entity is not a project and no ID or Title specified!"
        self.logger(message,'error')
        raise FCSValidationError(message,'error')
      else:
        message = "Must provide production ID or Title to search!"
        self.logger(message,'error')
        raise FCSValidationError(message,'error')
    
    elif not productionID and productionTitle:
     production = self.productionWithTitle(title=productionTitle)
     productionID = production.entityID
      
    
    if not productionID:
      self.logger("")
      raise FCSEntityNotFoundError(entityType='project',
                                                  entityTitle=productionTitle)
    
    ## Get our asset members.
    assetAddresses = self.getValueForLinkType(value="ADDRESS",
                                      linkType=1,id=productionID,type="project")
    
    ## Get our production members.
    try:
      projectAddresses = self.getValueForLinkType(value="ADDRESS",
                                     linkType=16,id=productionID,type="project")
    except:
      projectAddresses = []
    
    ## Create our resultant memberAddresses list
    memberAddresses = []
    
    ## Append our found assets.
    memberAddresses.extend(assetAddresses)
    memberAddresses.extend(projectAddresses)
    
    ## If no member addresses were provided, create an empty list
    if _processedMemberAddresses == None:
      _processedMemberAddresses = []

    ## If we are set to recurse, do so.
    if recurse:
      _processedMemberAddresses.append('/project/%s' % productionID)
      for projectAddress in projectAddresses:
        if not projectAddress in _processedMemberAddresses:
          regexMatch = re.match('/(.*)/(.*)',projectAddress)
          memberProductionType = regexMatch.group(1)
          memberProductionID = regexMatch.group(2)
          if not memberProductionType == 'project':
            self.logger('Found unknown project type: \'%s\' when processing '
              'member: \'%s\' from production: \'/project/%s\''
              % (memberProductionType,projectAddress,productionID),'warning')
            continue
          self.logger('productionMemberAddresses() recursing through '
            'production: %s' % projectAddress,'debug')
            
          ## Query the sub production, pass our processed addresses so they
          ## aren't processed again.
          self.logOffset += 1
          resultAddresses = self.productionMemberAddresses(
                          productionID=memberProductionID,
                          recurse=True,
                          _processedMemberAddresses=_processedMemberAddresses)
          self.logOffset -= 1
                                          
          ## Iterate through result addresses, append any new entries.
          for resultAddress in resultAddresses:
            if not resultAddress in memberAddresses:
              memberAddresses.append(resultAddress)
            if not resultAddress in _processedMemberAddresses:
              _processedMemberAddresses.extend(resultAddresses)
     
      
    if len(memberAddresses) == 0:
      self.logger("No member addresses were found for production with id:'%s'" 
        % productionID,'detailed')
      
    return memberAddresses
    
  
  def assetsFromProject(self,projectID="",mdSet=''):
    '''Function which returns a list of associated :class:`FCSVRClient` asset 
    objects for the provided Final Cut Pro project file. This project file is
    referenced via the file's Final Cut Server asset id. If mdSet is provided, 
    we will return only assets which match the provided metadata set. This
    function utilizes :func:`fcsxml.FCSVRClient.projectElementAddresses`
    
    :param projectID: Specify the FCS Asset ID for the project file
    :type projectID: int
    :param mdSet: Specify a FCS metadata set to filter by (i.e. 'pa_asset_media')
    :type mdSet: str
    
    :returns: (*list*) -- A list of qualifying FCSVRClient asset objects.
    
    '''    
      
    assetAddresses = self.projectElementAddresses(id=projectID,addressType='asset')
    assets = []
    
    for assetAddress in assetAddresses:
      regexMatch = re.match('/(.*)/(.*)',assetAddress)
      memberType = regexMatch.group(1)
      memberID = regexMatch.group(2)
      
      myAsset = FCSVRClient(id=memberID,configParser=self.configParser)
      
      ## If no mdSet parameter was passed add our asset to the list, 
      ## otherwise ensure that our mdSet matches.
      if not mdSet:
        assets.append(myAsset)
      elif mdSet and myAsset.entityMetadataSet == mdSet:
        assets.append(myAsset)
      elif mdSet and not myAsset.entityMetadataSet == mdSet:
        self.logger('assetsFromProject() Asset: %s with mdSet: %s does not match'
        ' mdSet: %s, excluding!' 
        % (myAsset.entityPath(),myAsset.entityMetadataSet,mdSet),'debug')
      
      return assets
  
  def projectElementAddresses(self,id='',addressType='asset'):
    '''Function which returns a list of element addresses associated to an FCP
    project file. An optional argument, addressType, can be provided.
    When set to 'asset', we return /asset/ addresses for any linked elements.
    if set to 'element', we return /element/ addresses for all linked alements.
  
    
    :param id: Specify the FCS Asset ID for the project file (optional)
    :type id: int
    :param addressType: Specify the link type to return ('asset' or 'element')
    :type addressType: str
    
    :returns: (*list*) -- A list of qualifying entity addresses.
    
    .. note:
      If we are a loaded asset with '.fcp' in the file name, we will work off 
      of our loaded instance, otherwise we will create a new object. 
      
    '''
    
    ## If we aren't provided an ID, check to make sure we are a loaded asset
    if not id and self.entityID and self.entityType == 'asset':
      myObject = self
    elif id and self.entityID == id:
      myObject = self
    elif id and not self.entityID == id:
      myObject = FCSVRClient(entityType='asset',
                                        id=id,
                                        configParser=self.configParser)
    else:
      msg = ('Could not load element addresses: no asset id provided and '
          ' local instance is not a project file!')
      self.logger('projectElementAddresses() %s' % msg,'error')
      raise FCSObjectLoadError(msg)
    
    ## Make sure our resolved object is an FCP project asset (based on filename)
    fileName = myObject.valueForField('File Name')
    if not fileName[-4:] == '.fcp' and not fileName[-4:] == u'.fcp':
      msg = ('Could not load element addresses: no asset id provided and '
        ' local instance is not a project file!')
      self.logger('projectElementAddresses() %s' % msg,'error')
      raise FCSObjectLoadError(msg)
    
    ## At  this point we have our FCP asset loaded at myObject, fetch all
    ## child links with type 1, but first, flush our cache.
    self.flushCaches()
    elementList  = self.getValueForLinkType(value="ADDRESS",
                                          linkType=1,
                                          id=myObject.entityID,
                                          type=myObject.entityType)
    
    ## If we are not filtering our results, return our current links
    if addressType == 'element':
      return elementList
    
    ## Iterate through our element list, create separate memberList based
    ## upon which elements have linked media assets.
    memberList = []
    self.logger('projectElementAddresses() found elements: %s, processing!'
      % ','.join(elementList),'debug')
    for elementAddress in elementList:
      self.logger('projectElementAddresses() processing element: %s'
                    % elementAddress,'debug')
      try:
        match = re.match('/(.*)/(.*)',elementAddress)
        elementEntityID = match.groups()[1]
        elementEntityType = match.groups()[0]
        memberAddress = self.getValueForLinkType(value='ADDRESS',
                                                  linkType=12,
                                                  id=elementEntityID,
                                                  type=elementEntityType,
                                                  origin='child')
        if memberAddress:
          memberList.append(memberAddress[0])
        else:
          raise
          
      except:
        self.logger('projectElementAddresses() skipping element address:%s,'
          ' could not load asset address!' % elementAddress,'debug')
        continue
      
    return memberList
        
    
      
  def parentProductions(self,id='',entityType='asset'):
    '''Function which returns a list of associated project addresses: 
      ["/project/11"] representative of all productions that an entity 
      is a member of, based on passed integer value entity. The ID
      can be omitted if we are a loaded asset or project.
      
      :param id: Specify the entity ID for which to resolve parent links
      :type id: int
      :param entityType: Specify the entityType
      :type entityType: str
      
      :raises: fcsxml.FCSValidationError
      
      :returns: (*list*) -- A list containing all parent entity addresses
    '''
    
    if not id and self.entityID and (self.entityType == 'asset' 
                                      or self.entityType == 'project'):
      id = self.entityID
      entityType = self.entityType
    else:
      msg = "Loaded entity is not an asset or project and no ID was provided!"
      self.logger(msg,'error')
      raise FCSValidationError(msg,'error')
    
    
    ## Get our parent production
    ## Fetch our XML DOM for our child links.
    childLinkDOM = self.getChildLinksXML(id=id,type=entityType)
    if entityType == 'project':
      linkType = 16
    else:
      linkType = 1
    parentAddresses = self.getValueForLinkType(value="ADDRESS",
                                                linkType=linkType,
                                                xmlDOM=childLinkDOM,
                                                id=id,
                                                type=entityType)
    
    ## Make sure we have parents
    if len(parentAddresses) == 0:
      raise RuntimeError("No parent productions found for entity:'/%s/%s'" % (entityType,id))
      
    return parentAddresses
  
  def archive(self,deviceID='',deviceDict='',recurseProductions=False):
    '''This method archives the loaded entity. If this is a production, then we 
    will archive all assets which are members of the production. If 
    recurseProductions is true, then we will archive it's members as well. 
    Either deviceID or a deviceDict must be provided to specify the destination
    archive device.
    
    
    
    :param deviceID: Specify the device ID to archive to.
    :type deviceID: int
    :param deviceDict: Specify the device dict profile to archive to *(optional)*
    :type deviceDict: dict
    :param recurseProductions: Specify whether to recurse productions for 
      archiving (assuming the calling entity is a production).
    :type recurseProductions: bool
    
    :raises: FCSAssetOfflineError, FCSError, 
    
    
    '''
    
    ## Make sure that we have a specified archive device, if none are 
    ## specified, archive to the first archive device found.
    if not deviceID and not deviceDict:
      self.logger('No archive device was provided, searching for applicable device','detailed')
      devicesMap = self.getDevicesMap()
      for deviceName,deviceDict in devicesMap.iteritems():
        if 'DEV_ARCHIVE' in deviceDict and deviceDict['DEV_ARCHIVE']:
          deviceID = deviceDict['DEVICE_ID']
          self.logger(' - Using archive device: %s' % deviceDict['DEVICE_NAME'],'detailed')
          break
    elif deviceID:
      deviceID = deviceID
    elif deviceDict:
      deviceID = deviceDict['DEVICE_ID']
    
    ## If this is a production, restore all members of the production.
    if self.entityType == 'project':
      if recurseProductions:
        members = self.productionMemberAddresses()
      else:
        members = self.productionAssetAddresses()
      
      ## Iterate through our members and restore them
      for member in members:
        memberObj = FCSVRClient(entityPath=member,
                                    configParser=self.configParser)
        memberObj.archive(recurseProductions=recurseProductions)        
      
    ## If this is an asset, simply archive it.
    elif self.entityType == 'asset':
      ## Archive the asset 
         
      ## Basic sanity checks.
      if not self.entityID:
        msg = 'Could not archive entity, no entityID is loaded.'
        self.logger(msg,'error')
        raise FCSError(msg)
        
      ## Run our fcsvr_client command.
      if not os.geteuid() == 0:
        if not self.useSudo:
          self.logger('Could not archive entity: root privileges are required!','error')
          raise FCSProductionLoadError("Archiving entities requires root privileges!")
        useSudo = True
      else:
        useSudo = False
      if useSudo:
        fcsvrCMDString = ('/usr/bin/sudo "%s" archive %s /dev/%s' 
                                  % (self.pathToFCSVRClient,self.entityPath(),deviceID))
      else:
        fcsvrCMDString = ('"%s" archive %s /dev/%s' 
                                  % (self.pathToFCSVRClient,self.entityPath(),deviceID))
                                                      
                                                      
      self.logger('fcsvrCMD:\n  %s' % fcsvrCMDString,'debug')

      fcsvrCMD = subprocess.Popen(fcsvrCMDString,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
      fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

      self.logger("fcsvr_client output: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'debug')

      if not fcsvrCMD.returncode == 0:
        ## If fcsvr_client reports an error, search the text for the string
        ## 'The asset is already offline' (we must do this because 
        ## fcsvr_client archive does return xml)
        if 'The asset is already offline' in fcsvrCMD_STDOUT:
          raise FCSAssetOfflineError(assetID=self.entityID)
        elif 'Archiving FCP Project assets is not supported' in fcsvrCMD_STDOUT:
          self.logger('Archiving FCP Project assets is not supported!','error')
        else:
          self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                            cmdString=fcsvrCMDString)
     
  def restore(self,recurseProductions=False):
    '''Restores the loaded entity. If this is a production, then we will
    restore all assets which are members of the production. If recurseProductions
    is true, then we will restore it's members as well. 
    
    :param recurseProductions: Specify whether we recursively restore assets
      for the provided production.
    :type recurseProductions: bool
        
    :raises: FCSError, FCSVRClientPermissionDenied, FCSVRClientFileError
    
    '''
    
    ## If this is a production, restore all members of the production.
    if self.entityType == 'project':
      if recurseProductions:
        members = self.productionMemberAddresses()
      else:
        members = self.productionAssetAddresses()
      
      ## Iterate through our members and restore them
      for member in members:
        memberObj = FCSVRClient(entityPath=member,configParser=self.configParser)
        memberObj.restore(recurseProductions=recurseProductions)        
      
    ## If this is an asset, simply restore it.
    elif self.entityType == 'asset':
      ## Restore the asset    
      
      ## Basic sanity checks.
      if not self.entityID:
        msg = 'Could not restore entity, no entityID is loaded.'
        self.logger(msg,'error')
        raise FCSError(msg)
      
      
      ## Run our fcsvr_client command.
      if not os.geteuid() == 0:
        if not self.useSudo:
          self.logger('Could not restore entity: root privileges are required!','error')
          raise FCSVRClientPermissionDenied("Restoring entities requires root privileges!")
        useSudo = True
      else:
        useSudo = False
      if useSudo:
        fcsvrCMDString = ('/usr/bin/sudo "%s" restore %s' 
                                  % (self.pathToFCSVRClient,self.entityPath()))
      else:
        fcsvrCMDString = ('"%s" restore %s' 
                                  % (self.pathToFCSVRClient,self.entityPath()))
                                                      
                                                      
      self.logger('fcsvrCMD:\n  %s' % fcsvrCMDString,'debug')

      fcsvrCMD = subprocess.Popen(fcsvrCMDString,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
      fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

      self.logger("fcsvr_client output: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'debug')

      if not fcsvrCMD.returncode == 0:
        ##self.logger("FCSVRClient Error: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'error')
        ##return False
        try:
          return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                            cmdString=fcsvrCMDString)
        except FCSVRClientFileError:
          self.logger('Could not restore asset, no file is not available on '
            'archive device!','error')
          return False
      return True
    
  def analyze(self,force=False,FCP=False,recurseProductions=False):
    '''This method will force FCS to analyze the loaded entity.
    
    :param force: Specify whether we call fcsvr_client with the --force option
    :type force: bool
    :param FCP: Specify whether we call fcsvr_client with the --fcp option
    :type FCP: bool
    :param recurseProductions: Specify whether we recurse production membership
      when analyzing assets.
    :type recurseProductions: bool
    
    
    
    '''
    
    ## If this is a production, analyze all members of the production.
    if self.entityType == 'project':
      if recurseProductions:
        members = self.productionMemberAddresses()
      else:
        members = self.productionAssetAddresses()
      
      ## Iterate through our members and analyze them
      for member in members:
        memberObj = FCSVRClient(entityPath=member,
                                      configParser=self.configParser)
        memberObj.analyze(force=force,FCP=FCP)        
      
    ## If this is an asset, simply restore it.
    elif self.entityType == 'asset':
      ## Analyze the asset    
      
      ## Basic sanity checks.
      if not self.entityID:
        msg = 'Could not analyze entity, no entityID is loaded.'
        self.logger(msg,'error')
        raise FCSError(msg)
      
      ## Run our fcsvr_client command.
      cmdOpts = ''
      if force:
        cmdOpts += ' --force'
      if FCP:
        cmdOpts += ' --fcp'
        
      fcsvrCMDString = ('"%s" analyze %s %s' 
                                  % (self.pathToFCSVRClient,cmdOpts,self.entityPath()))
                                                      
                                                      
      self.logger('fcsvrCMD:\n  %s' % fcsvrCMDString,'debug')

      fcsvrCMD = subprocess.Popen(fcsvrCMDString,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
      fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

      self.logger("fcsvr_client output: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'debug')

      if not fcsvrCMD.returncode == 0:
        self.logger("FCSVRClient Error: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'error')
        self.fcsvr_client_error(fcsvrCMD_STDOUT)    
                  
  def delete(self):
    '''Deletes the loaded entity.
    
    :raises: FCSValidationError, FCSVRClientPermissionDenied
    
    '''
    
    
    if not self.entityType or not self.entityID:
      message = "Could not delete entity, entityType or entityID not set!"
      self.logger(message,'error')
      raise FCSValidationError(message)
    
    ## Delete the asset    
    ## Run our fcsvr_client command.
    if not os.geteuid() == 0:
      if not self.useSudo:
        self.logger('Could not delete entity: root privileges are required!','error')
        raise FCSVRClientPermissionDenied("Deleting entities requires root privileges!")
      useSudo = True
    else:
      useSudo = False
    if useSudo:
      fcsvrCMDString = '/usr/bin/sudo "%s" delete --confirm /%s/%s' % (self.pathToFCSVRClient,
                                                      self.entityType,
                                                      self.entityID)
    else:
      fcsvrCMDString = '"%s" delete --confirm /%s/%s' % (self.pathToFCSVRClient,
                                                      self.entityType,
                                                      self.entityID)
                                                      
                                                      
    self.logger('fcsvrCMD:\n  %s' % fcsvrCMDString,'debug')

    fcsvrCMD = subprocess.Popen('%s' % fcsvrCMDString,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger("fcsvr_client output: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'debug')

    if not fcsvrCMD.returncode == 0:
      self.logger("FCSVRClient Error: %s %s" % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'error')
      return fcsvr_client_error(fcsvrCMD_STDOUT)
    
  def createAssetFromFSPath(self,path,deviceName="",deviceID="",mdSet="",
                                                relPath="",
                                                overwriteExistingFiles="ignore",
                                                setMD=True,
                                                backgroundAnalyze=True):
                                                
    '''This function takes a filesystem path and will create an asset from the
    file. Can be passed a deviceName or deviceID, metadata set, and an optional
    relative path to be uploaded. An option overwriteExistingFiles determines
    behavior if a file already exists, options are 'ignore','iterate', and 
    'overwrite'.
    
    :param path: Specify the absolute path to the asset to be added.
    :type path: str
    :param deviceName: Specify the deviceName to which the asset will be added 
      (optional - deviceID MUST be specified if deviceName is not)
    :type deviceName: str
    :param deviceID: Specify the deviceID to which the asset will be added
      (optional - deviceName MUST be specified if deviceID is not)
    :param mdSet: Specify the FCS metadata set to use for the new asset.
    :type mdSet: str
    :param relPath: Specify the path, relative to the root of the specified 
      device
    :type relPath: str
    :param overWriteExistingFiles: Specify the behavior to undertake in the event
      that a file already exists at the specified path. Options include 'ignore',
      'iterate', or 'overwrite'
    :type overWriteExistingFiles: str
    :param setMD: Specify whether we commit loaded field data to the new object.
    :type setMD: bool
    :param backgroundAnalyze: Specify whether the new asset will be analyzed by
      FCS in the background (default True)
    :type backgroundAnalyze: bool
    
    :raises: FCSVRClientFileError,FCSEntityNotFoundError,FCSEntityNotFoundError,
      FCSValidationError, IOError
    '''
    
    ## Make sure our asset exists
    if not os.path.exists(path):
      message = "Cannot create asset, no file could be found at path: '%s'" % path
      self.logger(message,'error')
      raise FCSVRClientFileError(message)
    
    assetPath = path
    assetName = os.path.basename(assetPath)

    if not mdSet:
      mdSet = self.defaultAssetMetadataSet
    
    ## Fetch our device
    myDeviceDict = {}
    if not deviceName and not deviceID:
      message = "Cannot create asset, deviceName or deviceID not specified!"
      self.logger(message,'error')
      raise FCSValidationError(message)
    if deviceName:
      myDeviceDict = self.deviceWithName(deviceName)
      if not myDeviceDict:
        message = "Could not find device with name: %s!" % deviceName
        self.logger(message,'error')
        raise FCSEntityNotFoundError(entityType='device',entityTitle=deviceName)
    if deviceID:
      if myDeviceDict:
        if not myDeviceDict["DEVICE_ID"]:
          message = ("Device with name: %s has a deviceID: %s, which "
            "conflicts with specified deviceID: %s, cannot continue" 
            % (deviceName,myDeviceDict["DEVICE_ID"],deviceID))
          self.logger(message,'error')
          raise FCSValidationError(message)
        deviceName = myDeviceDict["DEVICE_NAME"]
      else:
        myDeviceDict = self.deviceWithID(deviceID)
        
    ## Construct or path
    targetDir = myDeviceDict["FSPATH"]
    fcsDir = myDeviceDict["DESC_DEVICE_ADDRESS"]
    if not os.path.exists(targetDir):
      self.logger("Path: %s for Device: %s does not exist, cannot continue!" %(targetDir,assetDeviceName),'error')
      raise FCSEntityNotFoundError(entityType='device',entityPath='targetDir')
    
    ## If we have a relative path, clean it up and append it
    if relPath:
      ## Replace some problematic characters, this probably needs to be greatly expanded
      relPath = relPath.replace("`","'").replace('"',"'")
      if relPath[0:1] == "/":
        relPath = relPath[1:]
      targetDir = os.path.join(targetDir,relPath)
      fcsDir = os.path.join(fcsDir,relPath)

    ## At this point we have passed validation, announce our presence
    self.logger("Creating asset %s from filesystem path: '%s' to device:'%s' fcspath:'%s' "%(mdSet,assetPath,deviceName,fcsDir))
    
    ## Create our directory if it doesn't exist
    if not os.path.exists(targetDir):
      theDir = targetDir
      try:
        while not os.path.exists(targetDir):
          theDir = targetDir
          while not os.path.exists(theDir):
            if not os.path.exists(theDir) and os.path.exists(os.path.dirname(theDir)):
              self.logger("Creating directory:%s with userID:%s" % (theDir,self.FCSUID),'debug')
              os.mkdir(theDir)
              os.chown(theDir,self.FCSUID,-1)
              break
            else:
                theDir = os.path.dirname(theDir)
      except:
        self.logger("Error creating directory: %s, cannot continue!" % theDir,'error')
        return False
    
    
    ## If the target already exists, act based upon overwriteExistingFiles
    targetPath = os.path.join(targetDir,assetName)
    fcsPath = os.path.join(fcsDir,assetName)
    copyFile = True
    if os.path.exists(targetPath):
      if overwriteExistingFiles.lower() == "ignore":
        self.logger("File exists at path:'%s', skipping copy" % targetPath)
        copyFile = False
      elif overwriteExistingFiles.lower() == "iterate":
        iterCount = 1
        fileBase,fileExtension = os.path.splitext(assetName)
        while os.path.exists(targetPath):
          targetPath = os.path.join(targetDir,"%s-%s%s" % (fileBase,iterCount,fileExtension))
          fcsPath = os.path.join(fcsDir,"%s-%s%s" % (fileBase,iterCount,fileExtension))

          iterCount += 1
      elif overwriteExistingFiles.lower() == "replace":
        self.logger("Found existing file at path:'%s', removing!")
        shutil.rmtree(targetPath)
      else:
        self.logger("Found existing object at path:'%s'," % targetPath()
          + " and invalid overwriteExistingFiles option:%s" % overwriteExistingFiles
          + " was specified. (expects 'ignore','iterate', or 'replace'), cannot continue" ,'error')
        return False
            
    if copyFile:
      ## Copy our file
      self.logger(" - Copying File to '%s'" % targetPath)
      shutil.copy(assetPath,targetPath)
            
      ## Set proper ownership
      self.logger(" - Updating ownership to UID:%s" % self.FCSUID)
      os.chown(targetPath,self.FCSUID,-1)
      self.logger(" - Copy Finished, creating asset")
    
    ## URLEncode our fcsPath
    ## Todo: add more logic to ensure we don't double quote.
    qoutedFCSPath = urllib.quote(fcsPath)
    
    if self.fcsvr_client_createasset(qoutedFCSPath,
                                      mdSet,
                                      backgroundAnalyze=backgroundAnalyze,
                                      setMD=setMD):
      self.logger("Successfully Created Asset /asset/%s" % self.entityID)
      return True
    else:
      return False
  
    
  def createThumbnail(self,newThumbnailPath,assetID="",deviceName="",
                                          deviceID="",mdSet="asset_graphic"):
    '''This function will generate a new thumbnail for the provided asset
    based upon the provided path to the new thumbnail file. This thumbnail file
    is **not** directly used as the thumbnail, rather FCS will generate a 
    new thumbnail using it's standard defined parameters, and will then use 
    this generated file as the asset's new thumbnail. This is accomplished 
    by creating a new FCS asset for the thumbnail file, allowing FCS to create 
    the thumbnail link to the asset, getting the new asset's thumbnail path, 
    linking it to our asset, and then deleting the new thumbnail asset. If you
    wish to use a file for a thumbnail as-is, use 
    :func:`fcsxml.FCSVRClient.replaceThumbnail`
    
    :param newThumbnailPath: Provide the full path to the image file from which  
      the new thumbnail will be generated
    :type newThumbnailPath: str
    :param assetID: Provide the asset ID for the asset which will recieve the
      new thumbnail
    :type assetID: int
    :param deviceName: Specify the device name to which the temporary thumbnail
      asset will be copied
    :type deviceName: str
    :param deviceID: Specify the device id to which the temporary thumbnail
      asset will be copied
    :type deviceID: int
    :param mdSet: Provide the metadata set that will be used for the temporary
      thumbnail asset. The default value is 'asset_graphic'
    :type mdSet: str

    '''
    
    linkType = 5
    
    ## Make sure the replacement file exists:
    if not os.path.isfile(newThumbnailPath):
      if os.path.exists(newThumbnailPath):
        message = "Non-file object exists at path:%s" % newThumbnailPath
        self.logger(message,'error')
        raise FCSVRClientFileError(message)
      else:
        message = "File does not exist at path:%s" % newThumbnailPath
        self.logger(message,'error')
        raise FCSVRClientFileError(message)
    
    if not assetID:
      if self.entityID and self.entityType == "asset":
        assetID = self.entityID
    
    if not deviceName and not deviceID:
      if self.thumbnailDeviceName:
        deviceName = self.thumbnailDeviceName
    elif deviceID:
      deviceName = self.deviceWithID(id=deviceID)['DEVICE_NAME']
    
    if not deviceName:
      deviceName = self.defaultDeviceName
    
    if not mdSet:
      mdSet = self.defaultThumbnailMetadataSet
    
    ## Import our asset into FCS, this will also update the asset's MD
    self.logger("Importing thumbnail at path:'%s' with MD set:'%s' to device: '%s'" 
                                  % (newThumbnailPath,mdSet,deviceName),'debug') 
  
    ## Create an FCSVRClient object for our thumbnail
    myFCSVRClient = FCSVRClient(configParser=self.configParser)
   
    myFCSVRClient.createAssetFromFSPath(path=newThumbnailPath,mdSet=mdSet,
      deviceName=deviceName,backgroundAnalyze=False,setMD=False)
    
    time.sleep(2)
    
    ## Get the thumbnail for our thumbnail
    createdFCSThumbnailPath = myFCSVRClient.getFCSPathForLinkType(linkType=linkType)
    self.logger('Found thumbnail path: %s for new thumbnail asset.' 
      % createdFCSThumbnailPath,'debug')
    
    if not createdFCSThumbnailPath:
      self.logger("Could not find thumbnail reference for imported thumbnail file!",'error')
      return False
    
    ## Create our link
    self.fcsvr_client_make_link(linkType,
                                childPath=createdFCSThumbnailPath,
                                moveLink=True)
  
    ## Delete the thumbnail asset
    myFCSVRClient.delete()

    return True
    
        
  def replaceThumbnail(self,newThumbnailPath,assetID=""):
    '''Method which will replace the thumbnail file for the specified/stored 
    assetID with file provided at newThumbnailPath. Unlike 
    :func:`fcsxml.FCSVRClient.createThumbnail`, this function **will** use
    the provided file directly as the new thumbnail by simply replacing the
    existing thumbnail file on disk.
    
    :param newThumbnailPath: Specify the full path to the new thumbnail image
    :type newThumbnailPath: str
    :param assetID: Specify the asset id for the asset which will recieve the
      new thumbnail image
    :type assetID: int
    
    .. note:
      If a thumbnail does not already exist for this asset, we will raise
      an fcsxml.FCSVRFileNotFound exception.
    
    '''
    
    ## Make sure the replacement file exists:
    if not os.path.isfile(newThumbnailPath):
      if os.path.exists(newThumbnailPath):
        self.logger("Non-file object exists at path:%s" % newThumbnailPath,'error')
        return False
      else:
        self.logger("File does not exist at path:%s" % newThumbnailPath,'error')
        return False
    
    if not assetID:
      if self.entityID and self.entityType == "asset":
        assetID = self.entityID
        
    ## Get our old thumbnail path:
    thumbnailPath = self.getFilePathForThumbnail(id=assetID)
    
    ## Copy our thumbnail over the existing thumbnail
    try:
      shutil.copy(newThumbnailPath,thumbnailPath)
      os.chown(thumbnailPath,self.FCSUID,-1)
    except:
      self.logger("Error copying new thumbnail from: %s to %s" % (newThumbnailPath,thumbnailPath),'error')
      return False
    
    return True

  def createPosterFrame(self,newPosterFramePath,assetID="",deviceName="",
                                          deviceID="",mdSet="asset_graphic"):
    '''This function will generate a new poster frame for the provided asset
    based upon the provided path to the new file. This posterframe file
    is **not** directly used as the poster frame, rather FCS will generate a 
    new posterframe using it's standard defined parameters, and will then use 
    this generated file as the asset's new poster frame. This is accomplished 
    by creating a new FCS asset for the poster frame file, allowing FCS to create 
    the posterframe link to the asset, getting the new asset's posterframe path, 
    linking it to our asset, and then deleting the new poster frame asset. If you
    wish to use a file for a posterframe as-is, use 
    :func:`fcsxml.FCSVRClient.replacePosterFrame`
    
    :param newPosterFramePath: Provide the full path to the image file from which  
      the new poster frame will be generated
    :type newPosterFramePath: str
    :param assetID: Provide the asset ID for the asset which will recieve the
      new thumbnail
    :type assetID: int
    :param deviceName: Specify the device name to which the temporary thumbnail
      asset will be copied
    :type deviceName: str
    :param deviceID: Specify the device id to which the temporary thumbnail
      asset will be copied
    :type deviceID: int
    :param mdSet: Provide the metadata set that will be used for the temporary
      thumbnail asset. The default value is 'asset_graphic'
    :type mdSet: str

    '''
    
    linkType = 6
    
    ## Make sure the replacement file exists:
    if not os.path.isfile(newPosterFramePath):
      if os.path.exists(newPosterFramePath):
        message = "Non-file object exists at path:%s" % newPosterFramePath
        self.logger(message,'error')
        raise FCSVRClientFileError(message)
      else:
        message = "File does not exist at path:%s" % newPosterFramePath
        self.logger(message,'error')
        raise FCSVRClientFileError(message)
    
    if not assetID:
      if self.entityID and self.entityType == "asset":
        assetID = self.entityID
    
    if not deviceName and not deviceID:
      if self.thumbnailDeviceName:
        deviceName = self.thumbnailDeviceName
    elif deviceID:
      deviceName = self.deviceWithID(id=deviceID)['DEVICE_NAME']
    
    if not deviceName:
      deviceName = self.defaultDeviceName
    
    if not mdSet:
      mdSet = self.defaultThumbnailMetadataSet
    
    ## Import our asset into FCS, this will also update the asset's MD
    self.logger("Importing posterframe at path:'%s' with MD set:'%s' to device: '%s'" 
                                % (newPosterFramePath,mdSet,deviceName),'debug') 
  
    ## Create an FCSVRClient object for our thumbnail
    myFCSVRClient = FCSVRClient(configParser=self.configParser)
   
    myFCSVRClient.createAssetFromFSPath(path=newPosterFramePath,mdSet=mdSet,
      deviceName=deviceName,backgroundAnalyze=False,setMD=False)
    
    time.sleep(2)
    
    ## Get the thumbnail for our thumbnail
    createdFCSPosterFramePath = myFCSVRClient.getFCSPathForLinkType(linkType=linkType)
    self.logger('Found posterframe path: %s for new thumbnail asset.' 
      % createdFCSPosterFramePath,'debug')
    
    if not createdFCSPosterFramePath:
      self.logger("Could not find poster frame reference for imported "
        "posterframe file!",'error')
      return False
    
    ## Create our link
    self.fcsvr_client_make_link(linkType,childPath=createdFCSPosterFramePath,
                                                                  moveLink=True)
  
    ## Delete the thumbnail asset
    myFCSVRClient.delete()

    return True
       
  def replacePosterFrame(self,newPosterFramePath,assetID=""):
    '''Method which will replace the poster frame file for the specified/stored 
    assetID with file provided at newPosterFramePath. Unlike 
    :func:`fcsxml.FCSVRClient.createPosterFrame`, this function **will** use
    the provided file directly as the new posterFrame by simply replacing the
    existing posterframe file on disk.
    
    :param newPosterFramePath: Specify the full path to the new thumbnail image
    :type newPosterFramePath: str
    :param assetID: Specify the asset id for the asset which will recieve the
      new thumbnail image
    :type assetID: int
    
    .. note:
      If a posterframe does not already exist for this asset, we will raise
      an fcsxml.FCSVRFileNotFound exception.
    
    '''
    
    ## Make sure the replacement file exists:
    if not os.path.isfile(newPosterFramePath):
      if os.path.exists(newPosterFramePath):
        self.logger("Non-file object exists at path:%s" % newPosterFramePath,'error')
        return False
      else:
        self.logger("File does not exist at path:%s" % newPosterFramePath,'error')
        return False
    
    if not assetID:
      if self.entityID and self.entityType == "asset":
        assetID = self.entityID
        
    ## Get our old thumbnail path:
    thumbnailPath = self.getFilePathForPosterFrame(id=assetID)
    
    ## Copy our thumbnail over the existing thumbnail
    try:
      shutil.copy(newThumbnailPath,thumbnailPath)
      os.chown(thumbnailPath,self.FCSUID,-1)
    except:
      self.logger("Error copying new thumbnail from: %s to %s" % (newThumbnailPath,thumbnailPath),'error')
      return False
    
    return True
  
  def generateSearchXML(self,fields,matchType='exact'):
    '''Generates an XML file for use by fcsvr_client search --xmlcrit, should
    be past a list of FCSXMLFields (with their appropriate values set). Returns
    an absolute path to the XML file.
    
    :param fields: Provide a list of FCSXMLField objects with populated values
      to use for searching.
    :type fields: list
    :param matchType: An optional parameter to specify the search behavior.
      Currently two matchType's are supported: 'exact' (default), and 'substring'
    :type matchType: str
    
    :returns: (*str*) POSIX Filesystem Path to temporary XML file.
    
    .. versionadded:: .96b

    '''
    
    ## Iterate through each of our passed fields, generate
    ## a string of our field names and init each field.
    
    fieldNames = ""
    searchFields = []
    for field in fields:
      ## Generate a new field object for each field for validation 
      ## Purposes.
      if field.dbname:
        newField = self.initFieldWithDBName(field.dbname)
      elif field.name:
        newField = self.initFieldWithFieldName(field.name)
      
      ## Transfer the value of our passed field to our validated field
      newField.value = field.value
      searchFields.append(newField)
      
    
      if not fieldNames:
        fieldNames = field
      else:
        fieldNames += ", %s" % field
        
    self.logger('generateSearchXML() Generating search XML with fields:%s'
      ' match type:%s' % (fieldNames,matchType),'debug')
    
    ## create our new xml doc, add our root FCS elements:
    ## <?xml version="1.0"?>
    ## <session>
    ## <values>
    ##   <value id="CRIT_TYPE">
    ##     <int>3</int>
    ##   </value>
    ##   <value id="CRIT_INTERSECT">
    ##     <valuesList>
    ##       <values>
    ##         <value id="CRIT_CMP_VALUE">
    ##           <value id="CUST_TITLE">
    ##             <string>02-Ducati-Camera A-Color</string>
    ##           </value>
    ##         </value>
    ##         <value id="CRIT_CMP_OP">
    ##           <atom>eq</atom>
    ##         </value>
    ##         <value id="CRIT_TYPE">
    ##           <int>1</int>
    ##         </value>
    ##       </values>
    ##     </valuesList>
    ##   </value>
    ## </values>
    ## </session>


    xmlDoc = minidom.Document()
    fcsElement = xmlDoc.createElement('session')
    xmlDoc.appendChild(fcsElement)
    valuesElement = xmlDoc.createElement('values')
    fcsElement.appendChild(valuesElement)
    
    ##   <value id="CRIT_TYPE">
    ##     <int>3</int>
    ##   </value>

    critTypeElement = xmlDoc.createElement('value')
    critTypeElement.setAttribute('id', 'CRIT_TYPE')
    critTypeValueElement = xmlDoc.createElement('int')
    critTypeValueNode = xmlDoc.createTextNode('3')
    critTypeValueElement.appendChild(critTypeValueNode)
    critTypeElement.appendChild(critTypeValueElement)
    valuesElement.appendChild(critTypeElement)
    
    ##   <value id="CRIT_INTERSECT">
    ##     <valuesList>
    ##       <values>
    ##         <value id="CRIT_CMP_VALUE">
    critIntersectElement = xmlDoc.createElement('value')
    critIntersectElement.setAttribute('id', 'CRIT_INTERSECT')
    valuesListElement = xmlDoc.createElement('valuesList')
    critIntersectElement.appendChild(valuesListElement)
    critIntersectValuesElement = xmlDoc.createElement('values')
    valuesListElement.appendChild(critIntersectValuesElement)
    critCMPValueElement = xmlDoc.createElement('value')
    critCMPValueElement.setAttribute('id', 'CRIT_CMP_VALUE')
    critIntersectValuesElement.appendChild(critCMPValueElement)
    valuesElement.appendChild(critIntersectElement)
    
    ## Iterate through our passed field for XML and add our individual field 
    ## criteria.
    for field in searchFields:
      try:
        fieldName = field.name
        dbname = field.dbname
        if not fieldName and not dbname:
          self.logger('xmlOut() found field with no fieldname or dbname! skipping!','error')
          continue
        if not fieldName and dbname:
          fieldName = self.fieldNameForDBFieldName(dbname)
          field.name = fieldName
          self.logger('xmlOut() fieldName not set for field:%s, resolved:%s' % (dbname,fieldName),'debug')
        elif not dbname and fieldName:
          dbname = self.dbFieldNameForFieldName(fieldName)
          field.dbname = dbname
          self.logger('xmlOut() dbname not set for field:%s, resolved:%s' % (fieldName,dbname),'debug')
        
        if dbname and field.value:
          theFieldElement = xmlDoc.createElement('value')
          theFieldElement.setAttribute('id', field.dbname)
          ## generate our dataType specific XML nodes, if no
          ## dataType is set, assume string
          if field.dataType[0:6] == 'string' or not field.dataType:
            fieldSourceElement = xmlDoc.createElement('string')
            fieldSourceElement.setAttribute('xml:space','preserve')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'dateTime':
            fieldSourceElement = xmlDoc.createElement('timestamp')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'timecode':
            fieldSourceElement = xmlDoc.createElement('timecode')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'float':
            fieldSourceElement = xmlDoc.createElement('real')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'int64':
            fieldSourceElement = xmlDoc.createElement('bigint')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)                
          elif (field.dataType == 'int' or field.dataType == 'integer'):
            fieldSourceElement = xmlDoc.createElement('int')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'fraction':
            fieldSourceElement = xmlDoc.createElement('fraction')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)  
          elif field.dataType == 'coords':
            fieldSourceElement = xmlDoc.createElement('intpair')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)                     
          elif field.dataType == 'bool':
            fieldSourceElement = xmlDoc.createElement('bool')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          else:
            self.logger('Unknown dataType: \'%s\'' % field.dataType,'error')
            continue
          
          theFieldElement.appendChild(fieldSourceElement)
        
          ## Append our field element to our "values" element i.e.
          ##  <values>
          ##     <value id="MYFIELD">
          ##        <bool>true</bool>
          critCMPValueElement.appendChild(theFieldElement)
          
          del theFieldElement
      except:
        theErrorMsg = 'An error occured processing field: \'%s\', skipping!' % field.name 
        self.logger(theErrorMsg,'error')
    
    
    ##         <value id="CRIT_CMP_OP">
    ##           <atom>eq</atom>
    ##         </value>    
    critCMPOPElement = xmlDoc.createElement('value')
    critCMPOPElement.setAttribute('id','CRIT_CMP_OP')
    critCMPAtomElement = xmlDoc.createElement('atom')
    if matchType == 'exact':
      critCMPAtomElement.appendChild(xmlDoc.createTextNode('eq'))
    else:
      critCMPAtomElement.appendChild(xmlDoc.createTextNode('contains'))
      
    critCMPOPElement.appendChild(critCMPAtomElement)
    critIntersectValuesElement.appendChild(critCMPOPElement)

    ##         <value id="CRIT_TYPE">
    ##           <int>1</int>
    ##         </value>
    critTypeElement = xmlDoc.createElement('value')    
    critTypeElement.setAttribute('id','CRIT_TYPE')
    critTypeIntElement = xmlDoc.createElement('int')
    critTypeIntElement.appendChild(xmlDoc.createTextNode('1'))
    critTypeElement.appendChild(critTypeIntElement)
    critIntersectValuesElement.appendChild(critTypeElement)
      
    ## We have finished building our fields, at this point, write out our
    ## XML
    tempFileHandle,tempFilePath = tempfile.mkstemp(dir=self.supportDir,
                                                          suffix="_search.xml")
    self.logger("generateSearchXML() Using temp file: %s" % tempFilePath,'debug')    
    os.fdopen(tempFileHandle).close()
    
    theFile = codecs.open(tempFilePath, 'w','utf-8')
    xmlDoc.writexml(theFile)
    theFile.close()
    
    return tempFilePath
  
  def generateTempXMLFile(self):
    '''This file generates a temporary XML file constructed based upon
    our stored fields, used by various metadata activities utilized by
    fcsvr_client. 
    
    :returns: (*str*) -- File path to the temporary file.
    
    :raises: FCSValidationError, IOError
    
    '''
    
    if not self.fields:
      message = "No fields are set, cannot generate xml file!"
      self.logger(message,'error')
      raise FCSValidationError(message)

    ## Create a temporary directory
    tempFileHandle,tempFilePath = tempfile.mkstemp(dir=self.supportDir,suffix="_%s%s.xml" % (self.entityType,self.entityID))
        
    ## Generate our XML,write to our temp file
    if not self.xmlOut(tempFilePath):
      self.logger("No XML was generated",'error')
      tempFileHandle.close()
      tempFilePath = False
      
    ## Close out our temp file.
    try:
      ## Fetch and close our file descriptor
      fd = os.fdopen(tempFileHandle)
      fd.close()
    except:
      pass
    
    return tempFilePath
    
  
  def setMD(self):
    '''If we have a valid entityType and ID, we will attempt to run an fcsvr_client
    --setmd operation. This is performed by writing a temporary XML file
    (utilizing :func:`fcsxml.FCSVRClient.generateTempXMLFile` and reading
    it in with fcsvr_client --xml setmd
    
    :raises: FCSVRClientPermissionDenied,FCSValidationError,IOError
    '''
  
    ## Setting metadata with fcsvr_client requires root access. Make sure we're
    ## running under effective UID 0, or that we have useSudo set (requires
    ## modified sudoers file).
    
    if not os.geteuid() == 0:
      if not self.useSudo:
        self.logger("Could not set Metadata",'error')
        raise FCSVRClientPermissionDenied(action='setMD')
      useSudo = True
    else:
      useSudo = False
  
    if not self.entityType or not self.entityID:
      self.logger("Could not create entity, id or type is not set!" % entityType,'error')
      raise FCSValidationError("Could not create entity, id or type is not set!")

    tempFilePath = self.generateTempXMLFile()
    if not tempFilePath:
      raise IOError('Temporary file path is empty!')
    
    ## Run our fcsvr_client command.
    if useSudo:
      fcsvrCMDTXT = "/usr/bin/sudo '%s' setmd /%s/%s --xml '%s'" % (self.pathToFCSVRClient,self.entityType,self.entityID,tempFilePath)
    else:
      fcsvrCMDTXT = "'%s' setmd /%s/%s --xml '%s'" % (self.pathToFCSVRClient,self.entityType,self.entityID,tempFilePath)
      
    fcsvrCMD = subprocess.Popen("%s" % fcsvrCMDTXT,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger("fcsvr_client command:  %s" % "%s" % fcsvrCMDTXT,'debug')
    self.logger("fcsvr_client output: %s  tempfilepath: %s" % (fcsvrCMD_STDOUT,tempFilePath),'debug')

    ## Remove the temp file
    if not self.keepFiles:
      os.remove(tempFilePath)

    if not fcsvrCMD.returncode == 0:
      self.logger("%s %s" % (fcsvrCMD_STDERR,fcsvrCMD_STDOUT),'error')
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDTXT)

    return True


  def xmlOut(self,filePath):
    '''Output our XML to the specified file, this will be a fcsvr_client 
    compatable XML file (which is **not** compatable with FCS ReadXML responses)
    
    :param filePath: Specify the filePath for which to output XML
    :type filePath: str
    
    :returns: (*bool*)
    '''
        
    if not self.entityType:
      messsage = 'Could not create entity, entityType is not set!' % entityType
      self.logger(message,'error')
      raise FCSValidationError(message)
      
    if not self.entityType in self.registeredEntities:
      message = 'Could not set metadata, entityType:% is not valid!' % entityType
      self.logger(message,'error')
      raise FCSValidationError(message)

    if not self.entityID > 0: 
      message = 'xmlOut() entityID not set! Cannot generate XML.'
      self.logger(message, 'warning')
      raise FCSValidationError(message)
        
    if not len(self.fields) > 0:
      message = 'xmlOut() no fields set! Cannot generate XML.'
      self.logger(message, 'error')
      raise FCSValidationError(message)

    if not os.path.exists(filePath) and not os.path.isdir(os.path.dirname(filePath)):
      message = 'xmlOut() could not create file at %s' % filePath
      self.logger(message,'error')
      raise IOError(message)
    if os.path.exists(filePath) and not self.overwriteExistingFiles:
      message = 'xmlOut() file already exists at %s' % filePath
      self.logger(message,'error')
      raise IOError(message)

    ## create our new xml doc, add our root FCS elements:
    ## <?xml version="1.0"?>
    ## <session>
    ## <values>
    ## <value id="CUST_DESCRIPTION">
    ##   <string xml:space="preserve">this is my new description</string>
    ##  </value>
    ## </values>
    ##</session>

    xmlDoc = minidom.Document()
    fcsElement = xmlDoc.createElement('session')
    xmlDoc.appendChild(fcsElement)
    valuesElement = xmlDoc.createElement('values')
    fcsElement.appendChild(valuesElement)

    ## And then our individual fields.
    for field in self.fields.itervalues():
      try:
        fieldName = field.name
        dbname = field.dbname
        if not fieldName and not dbname:
          self.logger('xmlOut() found field with no fieldname or dbname! skipping!','error')
          continue
        if not fieldName and dbname:
          fieldName = self.fieldNameForDBFieldName(dbname)
          field.name = fieldName
          self.logger('xmlOut() fieldName not set for field:%s, resolved:%s' % (dbname,fieldName),'debug')
        elif not dbname and fieldName:
          dbname = self.dbFieldNameForFieldName(fieldName)
          field.dbname = dbname
          self.logger('xmlOut() dbname not set for field:%s, resolved:%s' % (fieldName,dbname),'debug')
        
        if dbname and field.value:
          theFieldElement = xmlDoc.createElement('value')
          theFieldElement.setAttribute('id', field.dbname)
          ## generate our dataType specific XML nodes, if no
          ## dataType is set, assume string
          if field.dataType[0:6] == 'string' or not field.dataType:
            fieldSourceElement = xmlDoc.createElement('string')
            fieldSourceElement.setAttribute('xml:space','preserve')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'dateTime':
            fieldSourceElement = xmlDoc.createElement('timestamp')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'timecode':
            fieldSourceElement = xmlDoc.createElement('timecode')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'float':
            fieldSourceElement = xmlDoc.createElement('real')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'int64':
            fieldSourceElement = xmlDoc.createElement('bigint')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)                
          elif (field.dataType == 'int' or field.dataType == 'integer'):
            fieldSourceElement = xmlDoc.createElement('int')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          elif field.dataType == 'fraction':
            fieldSourceElement = xmlDoc.createElement('fraction')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)  
          elif field.dataType == 'coords':
            fieldSourceElement = xmlDoc.createElement('intpair')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)                     
          elif field.dataType == 'bool':
            fieldSourceElement = xmlDoc.createElement('bool')
            theValueNode = xmlDoc.createTextNode(field.value)
            fieldSourceElement.appendChild(theValueNode)
          else:
            self.logger('Unknown dataType: \'%s\'' % field.dataType,'error')
            continue
          
          theFieldElement.appendChild(fieldSourceElement)
        
          ## Append our field element to our "values" element i.e.
          ##  <values>
          ##     <value id="MYFIELD">
          ##        <bool>true</bool>
          valuesElement.appendChild(theFieldElement)
          
          del theFieldElement
      except:
        theErrorMsg = 'An error occured processing field: \'%s\', skipping!' % field.name 
        self.logger(theErrorMsg,'error')
        
    ## We have finished building our fields, at this point, write out our
    ## XML
    theFile = open(filePath, 'w')
    xmlDoc.writexml(theFile)
    theFile.close()
    
    return True
    
  def getFilePath(self,id=''):
    '''Returns the file path to the primary representation for the loaded asset
    or the provided asset id.
    
    :param id: Specify the asset ID to query
    :type id: int

    :returns: (*str*) -- The full POSIX path to the entity's primary 
      representation

    '''
    
    if id:
      myObj = FCSVRClient(id=id,configParser=self.configParser)
    elif not id and self.entityType == 'asset' and self.entityID:
      myObj = self
    
    deviceDict = myObj.deviceWithName(self.valueForField('Stored On'))
    location = myObj.valueForField('Location')
    fileName = myObj.valueForField('File Name')

    self.logger('getFilePath() Found deviceDict: %s' % deviceDict,'debug')

    deviceFSPath = deviceDict['FSPATH']
  
    ## If our location has a leading /, remove it
    if location[0:1] == "/":
      location = location[1:]
  
    assetPath = os.path.join(deviceFSPath,location,fileName)
    return assetPath

  def getArchiveFilePath(self,deviceName=''):
    '''This method will return the filesystem path for the asset as it exists
    on the specified device.
    
    :param deviceName: Specify the name of the device to query.
    :type deviceName: str
    
    :returns: (*str*) -- The full POSIX path to the entity as it exists when 
      archived.
    
    .. versionadded:: 1.0b

    '''
      
    if not deviceName:
      self.logger('No archive device was provided, searching for applicable device','detailed')
      devicesMap = self.getDevicesMap()
      for deviceName,deviceDict in devicesMap.iteritems():
        if 'DEV_ARCHIVE' in deviceDict and deviceDict['DEV_ARCHIVE']:
          deviceID = deviceDict['DEVICE_ID']
          self.logger(' - Using archive device: %s' % deviceDict['DEVICE_NAME'],'detailed')
          myDevice = deviceDict
          break
    else:
      myDevice = self.deviceWithName(deviceName)
      
    location = self.valueForField('Location')
    fileName = self.valueForField('File Name')

    self.logger('getArchiveFilePath() Found device: %s' % myDevice,'debug')

    deviceFSPath = myDevice['FSPATH']
  
    ## If our location has a leading /, remove it
    if location[0:1] == "/":
      location = location[1:]
  
    filePath = os.path.join(deviceFSPath,location,fileName)
    
    return filePath
    
    

  def getFilePathForThumbnail(self,id='',xmlDOM=''):
    '''Returns the filesystem thumbnail path for asset given ID, 
    loads from fcsvr_client.
    
    :param id: Specify the asset ID to query
    :type id: int
    :param xmlDOM: Specify a XML DOM object to evaluate
    :type xmlDOM: xml.dom.minidom
    
    :raises: RuntimeError, fcsxml.FCSVRClient.FCSVRClientError
    :returns: (*str*) -- The absolute path to the file.
    
    '''
    
    if not id:
      if self.entityID and self.entityType == 'asset':
        assetID = self.entityID
      else:
        self.logger('Asset ID was not provided and is not stored, cannot continue!','error')
        raise RuntimeError('Asset ID was not provided and is not stored, cannot continue!')
    else:
      assetID = id
   

    self.logger('Determining thumbnailpath for id:%s' % id,'debug')
    
    ## If our assetID lookup matches our entityID and we have a cached value, return it
    if assetID == self.entityID and self.thumbnailPath and not xmlDOM:
      return self.thumbnailPath
    
    
    ## if we have an xmlDOM, use it, otherwise grab it from our object
    if not xmlDOM:
      xmlDOM = self.getParentLinksXML(id=assetID)
    
    if not xmlDOM:
      message = 'Could not generate xml!'
      self.logger(message,'error')
      raise RuntimeError(message)
    
    thumbnailPath = self.getFSPathForLinkType(linkType=5,id=assetID,xmlDOM=xmlDOM)
    if not thumbnailPath:
      message = 'Could not determine thumbnail path for asset:%s' % assetID
      self.logger(message,'error')
      raise FCSVRClientFileError(message)
    
    ## If our assetID lookup matches our entityID, cache our value
    if assetID == self.entityID and thumbnailPath:  
      self.thumbnailPath = thumbnailPath
    
    return thumbnailPath
    
    
  def getFilePathForProxy(self,id='',xmlDOM=''):
    '''Returns filesystem path to the associated proxy file.
    
    :param id: Specify the asset ID to query
    :type id: int
    :param xmlDOM: Specify a XML DOM object to evaluate
    :type xmlDOM: xml.dom.minidom
    
    :raises: RuntimeError, fcsxml.FCSVRClient.FCSVRClientError
    :returns: (*str*) -- The absolute path to the file.
    
    '''
    
    if not id:
      if self.entityID and self.entityType == 'asset':
        entityID = self.entityID
      else:
        self.logger('Asset ID was not provided and is not stored, cannot continue!','error')
        raise RuntimeError('Asset ID was not provided and is not stored, cannot continue!')
    else:
      entityID = id
      
    if not entityID:
      self.logger('assetID is not set, cannot determine proxyPath','error')
      raise FCSValidationError('assetID is not set, cannot determine proxyPath')
    
    ## If our assetID lookup matches our entityID and we have a cached value, return it
    if entityID == self.entityID and self.proxyPath and not xmlDOM:
      return self.proxyPath
    
    ## if we have an xmlDOM, use it, otherwise grab it from our object
    if not xmlDOM:
      xmlDOM = self.getParentLinksXML(id=entityID)
    
    if not xmlDOM:
      message = 'Could not generate xml!'
      self.logger(message,'error')
      raise RuntimeError(message)
          
    proxyPath = self.getFSPathForLinkType(linkType=4,id=entityID,xmlDOM=xmlDOM)
    if not proxyPath:
      message = 'Could not determine proxy path for asset:%s' % entityID
      self.logger(message,'error')
      raise FCSVRClientFileError(message)
    
    ## If our assetID lookup matches our entityID, cache our value
    if entityID == self.entityID and proxyPath:  
      self.proxyPath = proxyPath
    
    return proxyPath
  
  def getFilePathForPosterFrame(self,id='',xmlDOM=''):
    '''Returns filesystem path to the associated poster frame
    
    :param id: Specify the asset ID to query
    :type id: int
    :param xmlDOM: Specify a XML DOM object to evaluate
    :type xmlDOM: xml.dom.minidom
    
    :raises: RuntimeError, fcsxml.FCSVRClient.FCSVRClientError
    :returns: (*str*) -- The absolute path to the file.

    '''
    
    if not id:
      if self.entityID and self.entityType == 'asset':
        assetID = self.entityID
      else:
        self.logger('Asset ID was not provided and is not stored, cannot continue!','error')
        raise RuntimeError('Asset ID was not provided and is not stored, cannot continue!')
    else:
      assetID = id
    
    ## If our assetID lookup matches our entityID and we have a cached value, return it
    if assetID == self.entityID and self.posterFramePath and not xmlDOM:
      return self.posterFramePath
    
    ## if we have an xmlDOM, use it, otherwise grab it from our object
    if not xmlDOM:
      xmlDOM = self.getParentLinksXML(id=assetID)
    
    if not xmlDOM:
      message = 'Could not generate xml!'
      self.logger(message,'error')
      raise RuntimeError(message)
    
    posterFramePath = self.getFSPathForLinkType(linkType=6,id=assetID,xmlDOM=xmlDOM)
    if not posterFramePath:
      message = 'Could not determine poster frame path for asset:%s' % assetID
      self.logger(message,'error')
      raise FCSVRClientFileError(message)
    
    ## If our assetID lookup matches our entityID, cache our value
    if assetID == self.entityID and posterFramePath:  
      self.posterFramePath = posterFramePath
    
    return posterFramePath

  def getFilePathForEditProxy(self,id='',xmlDOM=''):
    '''Returns filesystem path to the associated thumbnail.
    
    :param id: Specify the asset ID to query
    :type id: int
    :param xmlDOM: Specify a XML DOM object to evaluate
    :type xmlDOM: xml.dom.minidom
    
    :raises: RuntimeError, fcsxml.FCSVRClient.FCSVRClientError
    :returns: (*str*) -- The absolute path to the file.

    '''
    
    if not id:
      if self.entityID and self.entityType == 'asset':
        assetID = self.entityID
      else:
        self.logger('Asset ID was not provided and is not stored, cannot continue!','error')
        raise RuntimeError('Asset ID was not provided and is not stored, cannot continue!')
    else:
      assetID = id
        
    ## If our assetID lookup matches our entityID and we have a cached value, return it
    if assetID == self.entityID and self.editProxyPath and not xmlDOM:
      return self.editProxyPath
    
    ## if we have an xmlDOM, use it, otherwise grab it from our object
    if not xmlDOM:
      xmlDOM = self.getParentLinksXML(id=assetID)
    
    if not xmlDOM:
      message = 'Could not generate xml!'
      self.logger(message,'error')
      raise RuntimeError(message)
    
    editProxyPath = self.getFSPathForLinkType(linkType=5,id=assetID,xmlDOM=xmlDOM)
    if not editProxyPath:
      message = 'Could not determine edit proxy path for asset:%s' % assetID
      self.logger(message,'error')
      raise FCSVRClientFileError(message)
    
    ## If our assetID lookup matches our entityID, cache our value
    if assetID == self.entityID and editProxyPath:  
      self.editProxyPath = editProxyPath
    
    return editProxyPath

  def initWithProductionTitle(self,title,matchType='exact'):
    '''Inits the local instance with a production based on the provided
    title. A second parameter, matchType, can be provided which will dictate
    the type of search that is used. Possible options are 'exact' and
    'substring'
    
    :param title: Specify the production title to init with
    :type title: str
    :param matchType: Specify the search criteria, possible values are 'exact'
      and 'substring'
    :type matchType: str
    
    
    '''
    
    ## lookup our production with the requested title
    theProduction = self.productionWithTitle(title,matchType=matchType)
    self.entityID = theProduction.entityID
    self.entityType = theProduction.entityType
    self.entityTitle = theProduction.entityTitle
    self.entityMetadataSet = theProduction.entityMetadataSet
    self.fields = theProduction.fields
    
    return True
    

  def initWithProductionID(self,productionID):
    '''Inits the local instance with a production based on the provided
    production id. 
    
    :param productionID: Specify the production id to init with
    :type productionID: int
    
    '''
        
    ## Set our id and type
    self.entityID = productionID
    self.entityType = 'project'
    
    ## Make sure we have a productionID, if not, bail
    if not productionID:
      raise FCSObjectLoadError('Could not init production: no production id was'
        ' provided')
    
    ## delete our stored fields
    if self.fields:
      self.fields = {}
    
    ## Get our project metadata
    cmdString = 'getmd "/project/%s" --xml' % productionID

    ## todo: add timeout to detect if FCSVR is down
    fcsvrCMD = subprocess.Popen('"%s" %s' % (self.pathToFCSVRClient,cmdString),
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    universal_newlines=True)
                                    
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command: fcsvr_client %s' % cmdString,'debug')

    if not fcsvrCMD.returncode == 0:
      self.logger('ERROR:%s' % fcsvrCMD_STDOUT,'error')
      return False
    
    ##self.logger("fcsvr_client output: %s  fcsPath: %s" % (fcsvrCMD_STDOUT,self.pathToFCSVRClient),'debug')

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: fcsvr_client %s' % cmdString,'error')
      return False
    
    self.dom = myDom
    
    #try:
    sessionRoot = myDom.childNodes[0]
    searchResultCount = 0
    resolvedFileName = ''
    resolvedMetadataSet = ''
    resolvedTitle = ''
    resolvedProjectID = ''
    resolvedDBEntityID = ''
    
    for value in sessionRoot.getElementsByTagName('value'):
      #self.logger('dbFieldNameForFieldName() rootValue nodename: %s' % rootValue.nodeName,'debug')          
      valueID = value.attributes['id'].value
      #self.logger('dbFieldNameForFieldName() Searching value: %s' % valueID,'debug')
      if valueID == 'PROJECT_NUMBER':
        try:
          resolvedProjectID = value.childNodes[1].childNodes[0].data
        except:
          pass
      elif valueID == 'DB_ENTITY_ID':
        try:
          resolvedDBEntityID = value.childNodes[1].childNodes[0].data
        except:
          pass
      elif valueID == 'PROJECT_TYPE':
        resolvedMetadataSet = value.childNodes[1].childNodes[0].data
      elif valueID == 'CUST_TITLE':
        try:
          resolvedTitle = value.childNodes[1].childNodes[0].data
        except:
          resolvedTitle = ''
        
    if (not resolvedDBEntityID or resolvedDBEntityID == '0'):
      msg = ('Could not init production with id:%s, production does not exist!' 
              % productionID)
      self.logger(msg,'error')
      raise FCSObjectLoadError(msg)

        
    self.logger('Finished init. projectID: %s, entityMetadataSet: %s,'
      ' entityTitle: %s DBEntityID: %s' % (resolvedProjectID,
        resolvedMetadataSet,resolvedTitle,resolvedDBEntityID)
      ,'debug')
    
    self.entityID = resolvedProjectID
    self.entityMetadataSet = resolvedMetadataSet
    self.entityTitle = resolvedTitle
  
    if self.entityID:
      return True
  
  def initWithAssetID(self,assetID):
    '''Inits the local instance with an asset based on the provided
    asset id. 
    
    :param assetID: Specify the production id to init with
    :type assetID: int
    
    :raises: FCSEntityNotFoundError, FCSObjectLoadError, RuntimeError
    
    '''
    
    ## Make sure we have an assetID, if not, bail
    if not assetID:
      raise FCSObjectLoadError('Could not init asset: no asset id was'
        ' provided')
    
    ## Get our asset metadata
    cmdString = 'getmd "/asset/%s" --xml' % assetID

    ## todo: add timeout to detect if FCSVR is down
    fcsvrCMD = subprocess.Popen('"%s" %s' % (self.pathToFCSVRClient,cmdString),
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command: fcsvr_client %s' % cmdString,'debug')

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString='fcsvr_client %s' % cmdString)
    
    ##self.logger("fcsvr_client output: %s  fcsPath: %s" % (fcsvrCMD_STDOUT,self.pathToFCSVRClient),'debug')

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      message = ('Could not parse output from fcsvr_client command: '
        'fcsvr_client %s' % cmdString)
      self.logger(message,'error')
      raise RuntimeError(message)
    
    self.dom = myDom
    
    #try:
    sessionRoot = myDom.childNodes[0]
    searchResultCount = 0
    noMatch = False
    resolvedRelPath = ''
    resolvedDeviceID = '' 
    resolvedDevice = ''
    resolvedFileName = ''
    resolvedAssetID = ''
    resolvedMetadataSet = ''
    resolvedTitle = ''
    resolvedDBEntityID = ''
    
    for value in sessionRoot.getElementsByTagName('value'):
      #self.logger('dbFieldNameForFieldName() rootValue nodename: %s' % rootValue.nodeName,'debug')          
      valueID = value.attributes['id'].value
      ##self.logger('dbFieldNameForFieldName() Searching value: %s' % valueID,'debug')
      if valueID == 'CUST_LOCATION':
        try:
          resolvedRelPath = value.childNodes[1].childNodes[0].data
          if not resolvedRelPath or not resolvedRelPath == relPath:
            self.logger('Found Location: \'%s\' does not match our requested '
                          'location:\'%s\',skipping search result!' 
                          % (resolvedRelPath,relPath),'debug')
            noMatch = True
            break;
        except:
          pass
      elif valueID == 'ASSET_NUMBER':
        resolvedAssetID = value.childNodes[1].childNodes[0].data
      elif valueID == 'DB_ENTITY_ID':
        try:
          resolvedDBEntityID = value.childNodes[1].childNodes[0].data
        except:
          pass
      elif valueID == 'PA_MD_CUST_FILENAME':
        resolvedFileName = value.childNodes[1].childNodes[0].data
      elif valueID == 'CUST_DEVICE':
        resolvedDeviceName = value.childNodes[1].childNodes[0].data
        resolvedDevice = self.deviceWithName(resolvedDeviceName)
        resolvedDeviceID = resolvedDevice['DEVICE_ID']          
      elif valueID == 'ASSET_TYPE':
        resolvedMetadataSet = value.childNodes[1].childNodes[0].data
      elif valueID == 'CUST_TITLE':
        try:
          resolvedTitle = value.childNodes[1].childNodes[0].data
        except:
          resolvedTitle = ''
    
    if not resolvedDBEntityID or resolvedDBEntityID == '0':
      msg = ('Could not init asset with id:%s, asset does not exist!' 
              % assetID)
      self.logger(msg,'error')
      raise FCSEntityNotFoundError(entityType='asset',entityID=assetID)
    
    self.logger('Finished init. entityID: %s, entityMetadataSet: %s,'
      ' entityTitle: %s' % (resolvedAssetID,resolvedMetadataSet,resolvedTitle)
      ,'debug')
    self.deviceDict = resolvedDevice
    self.entityID = resolvedAssetID
    self.entityMetadataSet = resolvedMetadataSet
    self.entityTitle = resolvedTitle
  
    if self.entityID:
      return True

  def initWithAssetFromField(self,field,matchType='exact'):
    '''Inits the local instance with an asset which has the provided
    field. A second parameter, matchType, can be provided which will 
    dictate the type of search that is used. Possible options are 'exact' and
    'substring'
    
    :param field: Specify the field to search with
    :type field: fcsxml.FCSXMLField
    :param matchType: Specify the search criteria, possible values are 'exact'
      and 'substring'
    :type matchType: str
    
    :raises: FCSEntityNotFoundError, FCSObjectLoadError, RuntimeError
    
    .. versionadded: 1.0b
    
    Example usage: ::
    
      >>> import fcsxml
      >>> myObj = fcsxml.FCSVRClient(configParser='/usr/local/etc/transmogrifier.conf')
      >>> myObj.initWithAssetField(field=fcsxml.FCSXMLField(name='Title',dbname='CUST_TITLE',value='photo 1'))
      >>> myObj.entityPath()
        /asset/43
        
    '''
    
    ## Get our asset with title.
    myAsset = self.assetWithField(field=field,matchType=matchType)
    self.entityID = myAsset.entityID
    self.entityType = myAsset.entityType
    self.entityTitle = myAsset.entityTitle
    self.entityMetadataSet = myAsset.entityMetadataSet
    self.fields = myAsset.fields
    
    return self

  def initWithAssetTitle(self,title,matchType='exact'):
    '''Inits the local instance with an asset which has the provided
    asset title. A second parameter, matchType, can be provided which will 
    dictate the type of search that is used. Possible options are 'exact' and
    'substring'
    
    :param title: Specify the asset title to init with
    :type title: str
    :param matchType: Specify the search criteria, possible values are 'exact'
      and 'substring'
    :type matchType: str
    
    :raises: FCSEntityNotFoundError, FCSObjectLoadError, RuntimeError
    
    '''
    
    ## Get our asset with title.
    myAsset = self.assetWithTitle(title=title,matchType=matchType)
    self.entityID = myAsset.entityID
    self.entityType = myAsset.entityType
    self.entityTitle = myAsset.entityTitle
    self.entityMetadataSet = myAsset.entityMetadataSet
    self.fields = myAsset.fields
    
    return self
    
  def initWithAssetFromFSPath(self,FSPath):
    '''Inits the local instance with an asset based on the provided
    file system path. 
    
    :param FSPath: Specify the file system path for the asset to init with
    :type FSPath: str
    
    :raises: FCSEntityNotFoundError, FCSObjectLoadError, RuntimeError
    
    '''
    ## Get our FCSPath
    self.logger('initWithAssetFromFSPath() looking up fcsPath for path:%s'
      % FSPath,'debug')
    
    try:
      fcsPath = self.getFCSPathFromFSPath(FSPath)
    except:
      ## Attempt to resolve from an archive path
      onlinePath = self.getFSPathFromArchivePath(FSPath)
      fcsPath = self.getFCSPathFromFSPath(onlinePath)
    self.logger('initWithAssetFromFSPath() found fcsPath:%s for path:%s'
      % (fcsPath,FSPath),'debug')
    
    try:
      return self.initWithAssetFromFCSPath(fcsPath)
    except (FCSEntityNotFoundError,FCSVRClientError):
      raise FCSEntityNotFoundError(entityPath=FSPath)
  
  def initWithAssetFromFCSPath(self,FCSPath):
    '''Inits the local instance with an asset based on the provided
    FCS device relative path (i.e. '/dev/4/myfile.mov') . 
    
    :param FCSPath: Specify the Final Cut Server relative path to init with
    :type FCSPath: str
    
    :raises: FCSEntityNotFoundError, FCSObjectLoadError, RuntimeError
    
    '''
        
    self.logger('initFromFCSPath() initing as asset from FCSPath:\'%s\'' 
      % FCSPath,'debug')
    
    ## Extract the asset name from the path
    fileName = os.path.basename(FCSPath)
    
    ## Extract the devID and relPath from the path
    partialPath = os.path.dirname(FCSPath)
    try:
      match = re.match('^/dev/(\d+)/(.*)$',partialPath)
      deviceID = match.group(1)
      relPath = match.group(2)
    except:
      try:
        match = re.match('^/dev/(\d+)$',partialPath)
        deviceID = match.group(1)
        relPath = ''
      except:
        self.logger('Could not extract deviceID or partial path, path:\'%s\'' 
          % partialPath)
        return False
    
    ## Perform a search for our asset
    cmdString = 'list_child_links %s --xml' % FCSPath

    ## todo: add timeout to detect if FCSVR is down
    fcsvrCMD = subprocess.Popen('"%s" %s' % (self.pathToFCSVRClient,cmdString),
                  shell=True,
                  stdout=subprocess.PIPE,
                  stderr=subprocess.PIPE,
                  universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command: fcsvr_client %s' % cmdString,'debug')

    ## IF fcsvrCMD didn't return quickly, consult with fcsvr_client_error 
    ## to determine the problem. If it throws exception FCSClientFileError,
    ## then we raise a FCSClientEntityNotFoundError
    if not fcsvrCMD.returncode == 0:
      try:
        self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                        cmdString='fcsvr_client %s' % cmdString)
      except FCSVRClientFileError:
        raise FCSEntityNotFoundError(entityPath=FCSPath)
    
    ##self.logger('fcsvr_client output: %s  fcsPath: %s' % (fcsvrCMD_STDOUT,self.pathToFCSVRClient),'debug')

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: fcsvr_client %s' % cmdString,'error')
      return False
    
    self.dom = myDom
    
    #try:
    sessionRoot = myDom.childNodes[0]

    resolvedEntityPath = ''
        
    for value in sessionRoot.getElementsByTagName('value'):
      #self.logger('dbFieldNameForFieldName() rootValue nodename: %s' % rootValue.nodeName,'debug')          
      valueID = value.attributes['id'].value
      ##self.logger('initWithAssetFromFCSPath() Searching value: %s' % valueID,'debug')
      if valueID == 'ADDRESS':
        try:
          resolvedEntityPath = value.childNodes[1].childNodes[0].data
        except:
          pass
    
    resolvedAssetID = resolvedEntityPath.split('/')[2]
    
    self.logger('initWithAssetID() found entityPath:%s, assetID:%s for FCS Address:%s' 
      % (resolvedEntityPath,resolvedAssetID,FCSPath),'debug')
    
    return self.initWithAssetID(resolvedAssetID)
            
                      
  def old_initAssetFromFCSPath(self,FCSPath):
    '''loads our object based upon a FCS path
    
    .. warning:
      As indicated by the name, this function is depricated, use
      :func:`fcsxml.FCSVRClient.initAssetFromFCSPath`
      
    '''
    self.logger("initFromFCSPath() initing as asset from FCSPath:'%s'" % FCSPath,'debug')
    
    ## Extract the asset name from the path
    fileName = os.path.basename(FCSPath)
    
    ## Extract the devID and relPath from the path
    partialPath = os.path.dirname(FCSPath)
    try:
      match = re.match('^/dev/(\d+)/(.*)$',partialPath)
      deviceID = match.group(1)
      relPath = match.group(2)
    except:
      try:
        match = re.match('^/dev/(\d+)$',partialPath)
        deviceID = match.group(1)
        relPath = ''
      except:
        self.logger("Could not extract deviceID or partial path, path:'%s'" % partialPath)
        return False
    
    ## Perform a search for our asset
    cmdString = 'search --crit "%s" /asset --xml' % fileName

    ## todo: add timeout to detect if FCSVR is down
    fcsvrCMD = subprocess.Popen('"%s" %s' % (self.pathToFCSVRClient,cmdString),
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()
      
    self.logger('fcsvr_client command: fcsvr_client %s' % cmdString,'debug')

    if not fcsvrCMD.returncode == 0:
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                        cmdString='fcsvr_client %s' % cmdString)
    
    ##self.logger("fcsvr_client output: %s  fcsPath: %s" % (fcsvrCMD_STDOUT,self.pathToFCSVRClient),'debug')

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      self.logger('Could not parse output from fcsvr_client command: fcsvr_client %s' % cmdString,'error')
      return False
    
    self.dom = myDom
    
    #try:
    sessionRoot = myDom.childNodes[0]
    searchResultCount = 0
    noMatch = False
    resolvedRelPath = ''
    resolvedDeviceID = '' 
    resolvedFileName = ''
    resolvedAssetID = ''
    resolvedMetadataSet = ''
    resolvedTitle = ''
    for searchResult in sessionRoot.childNodes:
      #self.logger('dbFieldNameForFieldName() Searching nodename: %s' % searchResult.nodeName,'debug')
      if searchResult.nodeName == 'values':
        resolvedRelPath = ''
        resolvedDeviceID = '' 
        resolvedFileName = ''
        resolvedAssetID = ''
        resolvedMetadataSet = ''
        resolvedTitle = ''
        
        
        noMatch = False
        for rootValue in searchResult.getElementsByTagName('value'):
          #self.logger('dbFieldNameForFieldName() rootValue nodename: %s' % rootValue.nodeName,'debug')          
          rootValueID = rootValue.attributes['id'].value
          #self.logger('dbFieldNameForFieldName() Searching rootValueID: %s' % rootValueID,'debug')
          if rootValueID == 'COMPLETE':
            didComplete = rootValue.childNodes[1].childNodes[0].data
            if not didComplete:
              break;
            searchResultCount += 1
          elif rootValueID == 'METADATA':
            noMatch = False
            for value in rootValue.getElementsByTagName('value'):
              valueID = value.attributes['id'].value
              ##self.logger('dbFieldNameForFieldName() Searching value: %s' % valueID,'debug')
              if valueID == 'CUST_LOCATION':
                try:
                  resolvedRelPath = value.childNodes[1].childNodes[0].data
                  if not resolvedRelPath or not resolvedRelPath == relPath:
                    self.logger('Found Location: \'%s\' does not match our '
                          'requested location:\'%s\',skipping search result!'
                          % (resolvedRelPath,relPath),'debug')
                    noMatch = True
                    break;
                except:
                  pass
              elif valueID == 'ASSET_NUMBER':
                resolvedAssetID = value.childNodes[1].childNodes[0].data
              elif valueID == 'PA_MD_CUST_FILENAME':
                resolvedFileName = value.childNodes[1].childNodes[0].data
                if not resolvedFileName or not resolvedFileName == fileName:
                  self.logger('Found File Name: \'%s\' does not match our '
                    'requested filename:\'%s\',skipping search result!' 
                    % (resolvedFileName,fileName),'debug')
                  noMatch = True
                  break
              elif valueID == 'CUST_DEVICE':
                resolvedDeviceName = value.childNodes[1].childNodes[0].data
                resolvedDevice = self.deviceWithName(resolvedDeviceName)
                resolvedDeviceID = resolvedDevice['DEVICE_ID']
                try: 
                  if not int(resolvedDeviceID) == int(deviceID):
                    self.logger('Found DeviceID: \'%s\' does not match our' 
                          'requested Device ID:\'%s\',skipping search result!'
                          % (resolvedDeviceID,deviceID),'debug')
                    noMatch = True
                    break 
                except:
                  self.logger('Error converting \'%s\' or \'%s\' to int!' 
                    % (resolvedDeviceID,deviceID),'debug')
                  
              elif valueID == 'ASSET_TYPE':
                resolvedMetadataSet = value.childNodes[1].childNodes[0].data
              elif valueID == 'CUST_TITLE':
                try:
                  resolvedTitle = value.childNodes[1].childNodes[0].data
                except:
                  resolvedTitle = ''
                  
      if not noMatch and resolvedAssetID:
        resolvedPath = u'%s' % os.path.join('/dev','%s' % resolvedDeviceID,
                                      resolvedRelPath,
                                      resolvedFileName)
        originalPath = u'%s' % FCSPath
        if resolvedPath == originalPath:
          self.deviceDict = resolvedDevice
          self.entityID = resolvedAssetID
          self.entityMetadataSet = resolvedMetadataSet
          self.entityTitle = resolvedTitle
          return True
        else:
          self.logger('Match failed! resolved path:\'%s\', requested path:\'%s\''
                     % (resolvedPath,FCSPath))
          noMatch = True
            
              
    return False
              

  def getFCSPathFromFSPath(self,FSPath):
    '''Resolves a FCS Relative device path ('/dev/4/myfile.mov') 
      from a filesystem POSIX path ('/Users/Shared/FCSStore/Library/myfile.mov')
    
    :param FSPath: Specify the file system path to convert
    :type FSPath: str
    
    :returns: (*str*) -- A Final Cut Server relative path
            
    '''
    
    newPath = ''
    self.logger('getFCSPathFromFSPath() resolving path:%s' % FSPath,'debug')
    devicesMap = self.getDevicesMap() 
    if not devicesMap or not len(devicesMap) > 0:
      message = 'devicesMap could not be loaded!'
      self.logger('getFCSPathFromFSPath() %s' % message,'error')
      raise FCSValidationError(message)
    for deviceID,device in devicesMap.iteritems():
      if FSPath[0:len(device['DEV_ROOT_PATH'])] == device['DEV_ROOT_PATH']:
        if device['DEVICE_TYPE'] == 'filesystem':
          newPath = os.path.join(device['DESC_DEVICE_ADDRESS'],
                                      FSPath[len(device['DEV_ROOT_PATH']) + 1:])
        elif device['DEVICE_TYPE'] == 'contentbase':
          try:
            parentDirName = os.path.basename(os.path.dirname(FSPath))
            decimalNameVal = int(parentDirName,16)
            newPath = (os.path.join(device['DESC_DEVICE_ADDRESS'],'%s_%s' 
                                 % (decimalNameVal,os.path.basename(FSPath))))
          except:
            message = 'Unexpected error converting contentbase path!'
            self.logger('getFCSPathFromFSPath() %s' % message,'error')
            raise FCSError(message)
        else:
          message = 'Unexpected DEVICE_TYPE:%s' % device['DEVICE_TYPE']
          self.logger('getFCSPathFromFSPath() %s' % message ,'error')
          raise FCSError(message)
        break;

    self.logger('getFCSPathFromFSPath() resolved unquoted path:%s' % newPath
                                                                      ,'debug')
    
    ## Encode FCS path with standard URL chars (i.e. ' ' = '%20')
    quotedPath = self.quoteString(newPath)

    self.logger('getFCSPathFromFSPath() resolved path:%s' % quotedPath,'debug')
    return quotedPath
    
    
  
  def getFSPathFromFCSPath(self,fcsPath):
    '''Resolves a POSIX file system path 
    ('/Users/Shared/FCSStore/Library/myfile.mov') from a FCS Relative device 
    path ('/dev/4/myfile.mov') 
    
    :param fcsPath: Specify the file system path to convert
    :type fcsPath: str
    
    :returns: (*str*) -- A POSIX file system path
    '''
            
    self.logger('getFSPathFromFCSPath() resolving fcsPath:%s' % fcsPath,'debug')
    
    ## Blow up the FCS Path
    pathArray = fcsPath.split('/')
    ##self.logger('pathArray:%s' % pathArray,'debug')
    newPath = ''
    
    ## Ensure it's a /dev path
    if not pathArray[1] == 'dev':
      message = ('Passed path:%s does not seem to be a valid FCS path!' 
                                                          % fcsPath)
      self.logger(message,'error')
      raise FCSValidationError(message)
    
    ## Abstract the device ID and dictionary
    deviceID = pathArray[2]
    self.logger('getFSPathFromFCSPath() found deviceID: %s' % pathArray[2],
                                                                      'debug')
    deviceDict = self.deviceWithID(deviceID)
    
    if not deviceDict:
      message = ('Could not load Device for id:%s, cannot continue!' 
                                                          % deviceID)
      self.logger(message,'debug')
      raise FCSError(message)
      
    deviceFSPath = deviceDict['DEV_ROOT_PATH']
    
    ## Get the remainder of the path:
    if deviceDict['DEVICE_TYPE'] == 'contentbase':
      if not len(pathArray) == 4:
        message = ('Unexpected element count in path: %s for ContentBase '
               'device, expected 3 items, found %s ' % (fcsPath,len(pathArray)))
        self.logger(message,'error')
        raise FCSError(message)
      try:
        regexMatch = re.match('^(\d+)_(.*)$',pathArray[3])
        fileID = int(regexMatch.group(1))
        fileHexID = '%016X' % fileID
        fileName = regexMatch.group(2)
        
        ## Get Our subpaths from the hex substr
        path1 = fileHexID[12:14]
        path2 = fileHexID[10:12]
        
        newPath = os.path.join(deviceFSPath,path1,path2,fileHexID,fileName)
      except:
        message = 'Could not determine fileID from filename:%s' % pathArray[3]
        self.logger(message,'error')
        raise FCSError(message)
    
    elif deviceDict['DEVICE_TYPE'] == 'filesystem':
      count=4
      newPath = ''
      while count < len(pathArray):
        newPath = os.path.join(deviceFSPath,pathArray[count])
        count += 1
    else:
      message = ('Unexpected DEVICE_TYPE encountered:%s' 
                                        % deviceDict['DEVICE_TYPE'])
      self.logger(message,'error')
      raise FCSError(message)
     
    unQuotedPath = self.unquoteString(newPath)
    
    return unQuotedPath

  def getFSPathFromArchivePath(self,archiveFilePath):
    '''Resolves a POSIX 'online' Path from a POSIX archive PATH
    i.e.:  /MyArchiveDevicePath/4/myfile.mov -> /LibraryDevicePath/myfile.mov
    
    :param archiveFilePath: Specify the assets file system path as it exists
      on the archive device.
    :type archiveFilePath: str
    :raises: FCSObjectLoadError
    :returns: (*str*) -- The full path to the asset when it is in an online state
    
    '''
    
    ## Determine our archive device
    myArchiveDevice = self.deviceWithPath(archiveFilePath)
    
    archiveBasePath = myArchiveDevice['FSPATH']
    
    ## Determine the non-archive path for the file, extract the archive portion
    ## of the path and determine original location of the file.
    relFilePath = ''
    if archiveFilePath[0:len(archiveBasePath)] == archiveBasePath:
      ## First get our relative path extracted from our archive-relative path 
      ## (/4/testfolder/myfile.mov)
      relFilePathTemp = archiveFilePath[len(archiveBasePath):]
      ## Extract the deviceID and save our device-relative path
      deviceID = relFilePathTemp.split('/')[1]
      relFilePath = relFilePathTemp[len('/%s' % deviceID):]
      
    else:
      self.logger('loadForFileAtPath() File Path:%s does not reside in Archive Path:%s','error')
      raise FCSObjectLoadError('File Path:%s does not exist in Archive Path:%s')

    ## Fetch our device info from our FCSVRClient object
    myDevice = self.deviceWithID(deviceID)
  
    ## Determine online asset path
    resolvedPath = u"%s%s" % (myDevice['FSPATH'],relFilePath)
    
    self.logger('loadForFileAtPath() determined relative path: %s deviceID: %s'  
      ' resolvedPath: %s' % (relFilePath,deviceID,resolvedPath),'debug')
    self.logger('loadForFileAtPath() - device path:%s' % myDevice['FSPATH'],'debug')
    
    return resolvedPath

  def quoteString(self,path):
    '''This method returns a quoted string acceptable for use by 
    fcsvr_client. This is similar to a URL encode, but FCS has some special
    needs outside of this as well.
    
    :param path: Specify the path to quote.
    :type path: str
    
    :returns: (*str*) -- The encoded string.
    
    .. warning: 
      Passing an unquoted string to fcsvr_client can cause **major** problems,
      if your entity titles or file paths rely heavily on unicode characters,
      it is **strongly** advised that you test all functions you wish to 
      implement in a test environment against representative data sets before 
      performing operations on your production environment. 
      
    '''
     
    ## Quote our string using urllib's quote function, skipping a few
    ## special escape characters.
    quotedString = urllib.quote(path,'&()/*!\'~$')
    quotedString = quotedString.replace('(','\(')
    quotedString = quotedString.replace(')','\)')
    quotedString = quotedString.replace('&','\&')
    quotedString = quotedString.replace('*','\*')
    quotedString = quotedString.replace('!','\!')
    quotedString = quotedString.replace("'","\\'")
    quotedString = quotedString.replace('~','\~')
    quotedString = quotedString.replace('$','\$')

    
    return quotedString
    
  def unquoteString(self,path):
    '''This method will reverse any string encoding performed by it's sister
    method :func:`fcsxml.FCSVRClient.quoteString`
    
    :param path: Specify the path to quote.
    :type path: str
    
    :returns: (*str*) -- The unencoded string.
    
    '''
     
    ## Quote our string using urllib's quote function, skipping a few
    ## special escape characters.
    unquotedString = urllib.unquote(path)
    unquotedString = unquotedString.replace('\(','(')
    unquotedString = unquotedString.replace('\)',')')
    unquotedString = unquotedString.replace('\&','&')
    unquotedString = unquotedString.replace('\*','*')
    unquotedString = unquotedString.replace('\!','!')
    unquotedString = unquotedString.replace("\'","'")
    unquotedString = unquotedString.replace('\~','~')
    unquotedString = unquotedString.replace('\$','$')

    
    return unquotedString


  def loadFromFCSXMLObject(self,fcsXMLObject):
    '''This method will load our object based upon values stored in the
    provided :class:`fcsxml.FCSXMLObject`
    
    :param fcsXMLObject: Provide the FCSXMLObject to load from
    :type fcsXMLObject: fcsxml.FCSXMLObject
    
    '''
    
    if fcsXMLObject.entityID:
      self.entityID = fcsXMLObject.entityID
    if fcsXMLObject.entityType:
      self.entityType = fcsXMLObject.entityType
    if len(fcsXMLObject.fields) > 0:
      self.fields = fcsXMLObject.fields
  
    ## Attempt to load to verify that the entity exists. An exception
    ## will be thrown if we fail.
    if fcsXMLObject.configParser:
      cfgParser = fcsXMLObject.configParser
    else:
      cfgParser = self.configParser
      
    myFCSVRClient = FCSVRClient(configParser=cfgParser)
    if self.entityType == 'project':
      myFCSVRClient.initWithProductionID(self.entityID)
    else:
      myFCSVRClient.initWithAssetID(self.entityID)

        
    
  def getValueForLinkType(self,value,linkType,xmlDOM='',id='',type='',origin='parent'):
    '''This method is used to interpret results from an fcsvr_client
    get_link operation. It will parse the provided information and returns the value 
    of <value> node with id of value and LINK_TYPE of linkType. 
    If xmlDOM is provided, we will search it, otherwise we will 
    generate our own xmlDOM for the search using provided or stored values of
    entityID and entityType. Argument 'origin' can be provided to denote whether
    we are fetching parent (:func:`fcsxml.FCSVRClient.getParentLinksXML`)
    or child (:func:`fcsxml.FCSVRClient.getChildLinksXML`) links.
    
    :param value: The name of the XML node who's value we should return
    :type value: str
    :param linkType: The FCS Link type to return
    :type linkType: int
    :param xmlDOM: Provide the XML DOM object to evaluate (*optional* - if none 
      is provided we will utilize :func:`fcsxml.FCSVRClient.getParentLinksXML`
      or :func:`fcsxml.FCSVRClient.getChildLinksXML`)
     
    :param id: Specify the entity id for which to analyze links
    :type id: int
    :param type: Specify the entity type for which to analyze links
    :type type: str
    :param origin: Specify the origin of the link ('parent' or 'child')
    :type origin: str
    
    :returns: (*str*) -- The value of the provided nodename and linktype
    
    Appropriate asset link types:
    
    =========  ===============================  =======
    linkType   Description                      Origin
    =========  ===============================  =======
    1          Asset's Parent Production        Child
    2          Asset's Primary Representation   Parent
    4          Asset's Proxy                    Parent
    5          Asset's Thumbnail                Parent
    6          Asset's Poster frame             Parent
    16         Production Nesting               Parent
    =========  ===============================  =======
    
    '''
    
    ## Assign new var (for readability)
    requestedValue = value
    
    if not xmlDOM:
      if not id and self.entityID:
        entityID = self.entityID
      elif not id:
        self.logger('Could not determine ID to search!');
        raise RuntimeError('Could not determine ID to search!')
      else:
        entityID = id
      entityType = type
      if origin == 'child':
        xmlDOM = self.getChildLinksXML(id=entityID,type=entityType)
      else:
        xmlDOM = self.getParentLinksXML(id=entityID,type=entityType)

    ## Do our work on the DOM    
    matchedEntries = []    ## List of matching dicts
    matchedValues = []    ## List of specific matching values
    linkAddress = ''
    for myValues in xmlDOM.getElementsByTagName('values'):
      loopDied = False
      assetDict = {}
      for myValue in myValues.getElementsByTagName('value'):
        valueID = myValue.attributes['id'].value
        ##self.logger('VALUE ID ATTRIB:%s' % valueID,'debug')
        if valueID == 'LINK_TYPE':
          ## Check to see if it's the thumbnail (LINK_TYPE of 5)
          assetDict['LINK_TYPE'] = int(myValue.childNodes[1].childNodes[0].data)
          if not assetDict['LINK_TYPE'] == linkType:
            loopDied = True
            assetDict = {}
            break

        if valueID == requestedValue:
          assetDict[requestedValue] = myValue.childNodes[1].childNodes[0].data
          
      if (not loopDied and 'LINK_TYPE' in assetDict 
        and assetDict['LINK_TYPE'] == linkType
        and requestedValue in assetDict):
        self.logger("Found matched value:'%s' (linkType:%s RequestedValue:'%s')" 
          % (requestedValue,
            assetDict['LINK_TYPE'],
            assetDict[requestedValue])
            ,'debug')
        matchedEntries.append(assetDict)
        matchedValues.append(assetDict[requestedValue])
            
    if not len(matchedValues) > 0:
      ##raise FCSError("Could not find entries with VALUE:%s LINK_TYPE:%s"
      ##  " in XML object!" % (requestedValue,linkType))
      return []
    else:
      self.logger('Found %s matching entries for LINK_TYPE:%s in XML object!' 
        % (len(matchedValues),linkType),'debug')
    
    return matchedValues
  
  def getFCSPathForLinkType(self,linkType,id='',xmlDOM=''):
    '''Returns a Final Cut server relative path for linked assets'''
    
    entityID = False
  
    if not id:
      if self.entityID and self.entityType == 'asset':
        entityID = self.entityID      
    else:
      entityID = id
      
    if not entityID:
      self.logger('Could not determine ID for asset, cannot continue!','error')
      raise RuntimeError('Could not determine ID for asset, cannot continue!')
    
    responses = self.getValueForLinkType(value='ADDRESS',linkType=linkType,
                                          id=entityID,type='asset',
                                          xmlDOM=xmlDOM)
    
    if not len(responses) > 0:
      self.logger('No responses returned for asset!','error')
      return ''
    
    return responses[0]
      
    '''
    ## If we weren't passed our DOM, load it
    if not xmlDOM:
      xmlDOM = self.getParentLinksXML(id=id)
    
    ## If we still have no DOM, exit
    if not xmlDOM:
      self.logger('Could not retrieve FCSPath, no xmlDOM loaded!','error')
      return False
    
    assetDict = {}
    linkAddress = ''
    for values in xmlDOM.getElementsByTagName('values'):
      loopDied = False
      for value in values.getElementsByTagName('value'):
        valueID = value.attributes['id'].value
        ##self.logger("VALUE ID ATTRIB:%s" % valueID,'debug')
        if valueID == 'LINK_TYPE':
          ## Check to see if it's the thumbnail (LINK_TYPE of 5)
          assetDict['LINK_TYPE'] = int(value.childNodes[1].childNodes[0].data)
          if not assetDict['LINK_TYPE'] == linkType:
            loopDied = True
            break

        if valueID == 'ADDRESS':
          assetDict['ADDRESS'] = value.childNodes[1].childNodes[0].data
        if valueID == 'DESC_DEVICE':
          assetDict['DESC_DEVICE'] = value.childNodes[1].childNodes[0].data
        if valueID == 'DESC_DEVICE_ADDRESS':
          assetDict['DESC_DEVICE_ADDRESS'] = value.childNodes[1].childNodes[0].data
          
      if not loopDied and 'LINK_TYPE' in assetDict and assetDict['LINK_TYPE'] == linkType:
        self.logger('link type:%s Address: %s ' % (assetDict['LINK_TYPE'],assetDict['ADDRESS']),'debug')
        break

    if not 'ADDRESS' or not 'ADDRESS' in assetDict or 'ADDRESS' in assetDict and not assetDict['ADDRESS']:
      self.logger('Could not find LINK_TYPE:%s in XML object!' % linkType,'error')
      return False
    
    return assetDict['ADDRESS']
    '''
    
  def getFSPathForLinkType(self,linkType,id='',xmlDOM=''):
    '''Returns a filesystem path from a linked asset'''
    
    ## todo: document xmlDOM functionality.
    
    if not id:
      if self.entityID and self.entityType == 'asset':
        assetID = self.entityID
      else:
        self.logger('Asset ID was not provided and is not stored, cannot continue!','error')
        raise RuntimeError('Asset ID was not provided and is not stored, cannot continue!')
    else:
      assetID = id
    
    
    if not xmlDOM:
      xmlDOM = self.getParentLinksXML(id=assetID)
      
    if not xmlDOM:
      self.logger('Could not retrieve FCPath, no xmlDOM loaded!','error')
      return False
    
    ## Get our FCS Address for the link
    assetAddress = self.getFCSPathForLinkType(linkType,id=assetID,xmlDOM=xmlDOM)
    if not assetAddress:
      return False
    
    ## Convert the FCS Path to an FS Path
    self.logger('Converting address: %s to known FileSystem address!' 
      % assetAddress)
    assetPath = self.getFSPathFromFCSPath(assetAddress)
    if assetPath:
      self.logger('Using address: %s' % assetPath,'debug')
      return assetPath
    else:
      self.logger('Could not convert address: %s' % assetAddress,'error')
      return False
      
  def getChildLinksXML(self,id='',type=''):
    '''This method returns an xml.dom.minidom object of child links data 
    utilizing fcsvr_client This is the sister object to 
    :func:`fcsxml.FCSVRClient.getParentLinksXML`
    
    :param id: Specify the entity id to determine child links for
    :type id: int
    
    :param type: Specify the entity type
    :type type: str
    
    :raises: FCSError,FCSValidationError
    :returns: (*xml.dom.minidom*) -- An XML DOM object base upon fcsvr_client
      XML output
    
    '''
    
    ## Determine our entityType
    entityType = ''
    if not type and self.entityType: 
        entityType = self.entityType
    elif not self.entityType:
        entityType = 'asset'
    elif type:
      entityType = type
    
    ## Determine our id
    entityID = ''
    if not id and self.entityType == entityType:
       entityID = self.entityID
    elif not id and not self.entityType == entityType:
      message = 'Requested entity type does not match stored values!'
      self.logger(message,'error')
      raise FCSValidationError(message)
    elif id:
      entityID = id
    
    if not entityID or not entityType:
      message = 'Passed invalid entity data, type or id missing!'
      self.logger(message)
      raise FCSValidationError(message)
      
    
    ## If our assetID lookup matches our entityID and we have a cached value, return it
    if entityID == self.entityID and type == self.entityType and self.childXMLObject:
      return self.childXMLObject
    
    ## Fetch our data from FCSVRXML
    fcsvrCMDString = "'%s' list_child_links /%s/%s --xml" % (self.pathToFCSVRClient,
                          entityType,
                          entityID)
    fcsvrCMD = subprocess.Popen(fcsvrCMDString,shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger('fcsvr_client command:%s' % fcsvrCMDString,'debug')
    ##self.logger('fcsvr_client output: %s  tempfilepath: %s' % (fcsvrCMD_STDOUT,tempFilePath),'debug')

    if not fcsvrCMD.returncode == 0:
      ##self.logger('fcsvr_client reported an error: %s%s' % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR),'error')
      ##raise RuntimeError('fcsvr_client reported an error: %s' % (fcsvrCMD_STDOUT,fcsvrCMD_STDERR))
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                          cmdString=fcsvrCMDString)

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      message = ('Could not parse output from fcsvr_client, it does not appear ' 
        'to be valid XML')
      self.logger(message,'error')
      raise FCSError(message)
    
    if entityID == self.entityID:
      self.parentXMLObject = myDom
      
    return myDom

  def getParentLinksXML(self,id='',type=''):
    ''''Returns an xml.dom.minidom object of parent link data utilizing 
    fcsvr_client. This is the sister object to 
    :func:`fcsxml.FCSVRClient.getChildLinksXML`
    
    :param id: Specify the entity id to determine parent links for
    :type id: int
    
    :param type: Specify the entity type
    :type type: str
    
    :raises: FCSError,FCSValidationError
    :returns: (*xml.dom.minidom*) -- An XML DOM object base upon fcsvr_client
      XML output
    
    '''
    
    ## Determine our entityType
    entityType = ''
    if not type and self.entityType: 
        entityType = self.entityType
    elif not self.entityType:
        entityType = 'asset'
    elif type:
      entityType = type
    
    ## Determine our id
    entityID = ''
    if not id and self.entityType == entityType:
       entityID = self.entityID
    elif not id and not self.entityType == entityType:
      message = 'Requested entity type does not match stored values!'
      self.logger(message,'error')
      raise FCSValidationError(message)
    elif id:
      entityID = id
    
    ## If our assetID lookup matches our entityID and we have a cached value, return it
    if entityID == self.entityID and self.parentXMLObject:
      return self.parentXMLObject
    
    ## Fetch our data from FCSVRXML
    fcsvrCMDString = '"%s" list_parent_links /%s/%s --xml' % (self.pathToFCSVRClient,
                          entityType,
                          entityID)
    fcsvrCMD = subprocess.Popen(fcsvrCMDString,shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger('fcsvr_client command:%s' % fcsvrCMDString,'debug')
    ##self.logger('fcsvr_client output: %s  tempfilepath: %s' % (fcsvrCMD_STDOUT,tempFilePath),'debug')

    if not fcsvrCMD.returncode == 0:
      ##self.logger('fcsvr_client reported an error: %s' % fcsvrCMD_STDERR,'error')
      ##raise RuntimeError('fcsvr_client reported an error: %s' % fcsvrCMD_STDERR)
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                                  cmdString=fcsvrCMDString)

    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(fcsvrCMD_STDOUT)
    except:
      message = ('Could not parse output from fcsvr_client, it does not appear '
        'to be valid XML')
      self.logger(message,'error')
      raise FCSError(message)
    
    if entityID == self.entityID:
      self.parentXMLObject = myDom
      
    return myDom
  
  def getThumbnailPath(self,assetID='',xmlDOM=''):
    '''This function will return a file system path for the given asset.
    
    .. warning::
      This method has been DEPRICATED: use :func:`fcsxml.FCSVRClient.getFilePathForThumbnail`
    
    '''
    
    return self.getFilePathForThumbnail(id=assetID)

  def flushCaches(self):
    '''This function will flush any cached data: currently this is limited
    to any cached XML data returned from fcsvr_client.'''
    
    self.parentXMLObject = ''
    self.childXMLObject = ''
    return True

  def fcsvr_client_create(self,address='',entityType='',parentAddress='',parentLinkType=''):
    '''This is a wrapper around fcsvr_client, if there are fields set in self.fields,
    it will import with generate XML to a temp file and pass it during creation
    
    .. warning::
    
      This is currently a placeholder function and is not implemented.

    
    '''
    
    ##currently a place holder
    return False
  
  def fcsvr_client_createasset(self,fcsPath,mdSet='pa_asset_media',
                            backgroundAnalyze=False,projAddress='',setMD=True):
    '''This is the createasset wrapper around fcsvr_client. If there are fields
    set in self.fields, It will output XML to a temp file and then
    call fcsvr_client to create the entity. If self.entityType is 'asset', then
    we load from fcsvr_client and return our self, if our entityType is not asset,
    we clone ourself and return a new FCSVRClient object with entityType 'asset'
    
    .. warning: 
    
      fcsPath should be a quoted path, as returned by quoteFSPath()
      failure to comply with this CAN result in a database crash, or possible
      corruption if fcsvr_client is passed special characters!!!
    
    '''
    
    if not self.entityType == 'asset':
      self.logger('Object entityType is %s, not %s, cloning object!' 
                                                      % entityType,'warning')
      obj = copy.copy(self)
    else:
      obj = self
    
    if not obj.entityType in obj.registeredEntities:
      self.logger('Could not create entity, entityType:% is not valid!' 
                                                          % entityType,'error')
      return False
    
    cmdArgs = ' createasset '
    if backgroundAnalyze:
      cmdArgs += '--background '
    if projAddress:
      if projAddress[0:9] == '/project/':
        cmdArgs += '--projaddr %s' % projAddress
      else:
        self.logger('Found invalid project address: %s, cannot link!' 
                                                        % projAddress,'warning')
    
    
    cmdArgs += ' %s %s' % (mdSet,fcsPath)
    
    
    ## If we can escalate to root, do so
    if self.useSudo and not os.geteuid() == 0:
      fcsvrCMDTXT = '/usr/bin/sudo \'%s\' %s' % (self.pathToFCSVRClient,cmdArgs)
    else:
      if not os.geteuid() == 0:
        self.logger('Could not create asset, permission denied!','error')
        raise FCSVRClientPermissionDenied('createasset',cmdArgs)
      else:
        self.useSudo = False
        fcsvrCMDTXT = '\'%s\' %s' % (self.pathToFCSVRClient,cmdArgs)
    
    ## Run our fcsvr_client command.
    fcsvrCMD = subprocess.Popen('%s' % fcsvrCMDTXT,shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger('fcsvrCMD:\n  %s' % "'%s' %s" % (obj.pathToFCSVRClient,cmdArgs),'debug')
    self.logger('fcsvr_client output: %s  fcsPath: %s' % (fcsvrCMD_STDOUT,fcsPath),'debug')

    if not fcsvrCMD.returncode == 0:
      ##self.logger('FCSVRClient Error: %s\n%s\nCommand Syntax: %s' 
                    ##% (fcsvrCMD_STDOUT,fcsvrCMD_STDERR,fcsvrCMDTXT),'error')
      ##return False
      if fcsvrCMD_STDOUT:
        reportString = fcsvrCMD_STDOUT
      else:
        reportString = fcsvrCMD_STDERR
        
      return self.fcsvr_client_error(errorString=reportString,
                                          cmdString=fcsvrCMDTXT)      
      
    ## Resolve our entity ID from STDOUT
    try:
      match = re.match('/asset/(\d+)',fcsvrCMD_STDOUT)
      assetID = match.group(1)
    except:
      self.logger('Could not retrieve asset id from string: %s' 
                                                    % fcsvrCMD_STDOUT,'error')
      return False
    
    self.logger('Created new Asset with ID:%s' % assetID,'debug')
    obj.entityType = 'asset'
    obj.entityID = assetID
    if obj.fields and setMD:
      obj.setMD()
    
    return obj

  def fcsvr_client_make_link(self,linkType,parentPath='',childPath='',moveLink=False):
    '''This is a wrapper function around fcsvr_client make_link. See the table
    defined in :func:`fcsxml.FCSVRClient.getValueForLinkType` for more 
    information about linkTypes. 
    
    :param linkType: Specify the type of link to create
    :type linkType: int
    :param parentPath: Specify the FCS entity path representing the parent 
      (i.e. '/project/22')
    :type parentPath: str
    :param childPath: Specify the FCS entity path representing the child 
      (i.e. '/asset/10')
    :type childPath: str
    :param moveLink: Specify whether we are creating a new link (::False::) or
      moving the existing link (::true::)
    :type moveLink: bool
    
    :raises: FCSValidationError, FCSError, FCSVRClientPermissionDenied
    
    '''
    
    if not childPath:
      message = 'fcsvr_client_make_link() no childPath provided!'
      self.logger(message,'error')
      raise FCSValidationError(message)
    
    if not parentPath:
      if self.entityType and self.entityID:
        parentPath = '/%s/%s' % (self.entityType,self.entityID)
      else:
        message = ('fcsvr_client_make_link() cannot make link, parentPath '
          'not provided, entityType,entityID not set!')
        self.logger(message,'error')
        raise FCSValidationError(message)
    
    linkType = int(linkType)
    
    ## Create our link
    cmdArgs = 'make_link --linktype %s' % linkType
    if moveLink:
      cmdArgs += ' --movelink'
    cmdArgs += ' \'%s\' \'%s\'' % (parentPath,childPath)
    
    ## Creating links with fcsvr_client requires root access. Make sure we're
    ## running under effective UID 0, or that we have useSudo set (requires
    ## modified sudoers file).    
    if self.useSudo and not os.geteuid() == 0:
      fcsvrCMDTXT = '/usr/bin/sudo \'%s\' %s' % (self.pathToFCSVRClient,cmdArgs)
    else:
      if not os.geteuid() == 0:
        self.logger('Could not create link, permission denied!','error')
        raise FCSVRClientPermissionDenied('make_link',cmdArgs)
      else:
        self.useSudo = False
        fcsvrCMDTXT = '\'%s\' %s' % (self.pathToFCSVRClient,cmdArgs)
    
    ## Run our fcsvr_client command.
    fcsvrCMD = subprocess.Popen('%s' % fcsvrCMDTXT,shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True)
    fcsvrCMD_STDOUT,fcsvrCMD_STDERR = fcsvrCMD.communicate()

    self.logger('fcsvrCMD:\n  %s' % fcsvrCMDTXT,'debug')

    if not fcsvrCMD.returncode == 0:
      ##errorString = 'Failed to create link! %s %s' % (fcsvrCMD_STDERR,fcsvrCMD_STDOUT)
      ##self.logger(errorString,'error')
      ##raise FCSVRClientError(errorString,fcsvrCMDTXT)
      return self.fcsvr_client_error(errorString=fcsvrCMD_STDOUT,
                                              cmdString=fcsvrCMDTXT) 
     
    ## Flush our caches
    self.flushCaches()
    return True
  
  def fcsvr_client_error(self,errorString='',cmdString=''):
    '''This method interprets an fcsvr_client error string and will throw
    the appropriate exception, it should be called if fcsvr_client returns
    a non-0 exit code.
    
    :param errorString: Provide the text string returned by fcsvr_client
    :type errorString: str
    :param cmdString: Provide the command string resulting in the error (optional)
    :type cmdString: str
    
    :raises: FCSVRClientError, FCSVRClientFileError, FCSVROfflineError, 
      FCSDuplicateError
      
    :returns: This function will **always** raise an exception from the above 
      list 
    
    
    '''
    
    self.logger('fcsvr_client_error() Hit!','debug')

    resolvedCode = ''
    resolvedDesc = ''
    resolvedNode = ''
    resolvedSourceFile = ''
    resolvedSourceLine = ''
  
    ## Create a dom object from our string:
    try:
      myDom = minidom.parseString(errorString)
      sessionRoot = myDom.childNodes[0]
      for value in sessionRoot.getElementsByTagName('value'):
        #self.logger('dbFieldNameForFieldName() rootValue nodename: %s' % rootValue.nodeName,'debug')          
        valueID = value.attributes['id'].value
        self.logger('fcsvr_client_error() Searching value: %s' % valueID,'debug')
        if valueID == 'CODE':
          resolvedCode = value.childNodes[1].childNodes[0].data
          self.logger('fcsvr_client_error() found error code:%s' 
                                                        % resolvedCode,'debug')
        elif valueID == 'DESC':
          resolvedDesc = value.childNodes[1].childNodes[0].data
        elif valueID == 'NODE':
          resolvedNode = value.childNodes[1].childNodes[0].data
        elif valueID == 'SRC_FILE':
          resolvedSourceFile = value.childNodes[1].childNodes[0].data
        elif valueID == 'SRC_LINE':
          resolvedSourceLine = value.childNodes[1].childNodes[0].data 
    except:
      ## If the DOM failed, attempt to extract from string (some fcsvr_client 
      ## actions do not support -xml
      try:
        stringSearchResults = re.search('{.*CODE = (.*), DESC = (.*)'
              ', NODE = (.*), SRC_FILE = (.*), SRC_LINE = (.*) }',errorString)
        resolvedCode = stringSearchResults.groups()[0]
        resolvedDesc = stringSearchResults.groups()[1]
        resolvedNode = stringSearchResults.groups()[2]
        resolvedSourceFile = stringSearchResults.groups()[3]
        resolvedSourceLine = stringSearchResults.groups()[4]
      except:
        raise FCSVRClientError(errorString='An Unknown error occurred, could '
          'not parse fcsvr_client output: %s' % errorString,cmdString=cmdString)
  
    #try:
    
    if resolvedCode == 'E_COM':
      if resolvedDesc:
        msg = resolvedDesc
      else:
        msg = ('Server is not running!')
      raise FCSVROfflineError(errorString=msg)
    elif resolvedCode == 'E_FILE':
      if resolvedDesc:
        msg = resolvedDesc
      else:
        msg = ('No such file or directory!')
      raise FCSVRClientFileError(msg)
    elif resolvedCode == 'E_DUPLICATE':
      if resolvedDesc:
        msg = resolvedDesc
      else:
        msg = ('A duplicate action has been recorded: this action may have '
          'already been applied!')
      raise FCSDuplicateError(msg)
    elif resolvedCode == 'E_NOTSUPP':
      if resolvedDesc:
        msg = resolvedDesc
      else:
        msg = ('Action is not supported!!')
      raise FCSVRClientError(msg)
          
    else:
      raise FCSVRClientError(errorString='An Unknown error occurred. Code: \'%s\'' 
        ' Desc: \'%s\' ErrorString:\'%s\'' % (resolvedCode,resolvedDesc,errorString)
        ,cmdString=cmdString)

    return False

#### BEGIN EXCEPTIONS ####

class FCSFieldNotFoundError(Exception):
  '''This exception is thrown when an FCS field cannot be loaded based on 
  provided parameters.'''
  def __init__(self, fieldName='',dbname=''):
    self.fieldName = fieldName
    self.dbname = dbname
  def __str__(self):
    if self.dbname:
      returnString = 'No Field with dbkey:\'%s\' exists!' % self.dbname 
      return repr(returnString)
    else:
      returnString = 'No Field with key:\'%s\' exists!' % self.fieldName
      return repr(returnString)
  
class FCSAssetOfflineError(Exception):
  '''This exception is thrown when an asset is offline and a file sensative
  operation has been requested.'''
  def __init__(self,assetID='',assetPath='',assetTitle=''):
    self.assetID = assetID
    self.assetPath = assetPath
    self.assetTitle = assetTitle
  def __str__(self):
    returnString = 'Asset is offline.'
    if self.assetID:
      returnString += ' AssetID:%s' % self.assetID
    if self.assetPath:
      returnString += ' AssetPath:\'%s\'' % self.assetID
    if self.assetTitle:
      returnString += ' Title:\'%s\'' % self.assetTitle
    
    return repr(returnString)

class FCSEntityNotFoundError(Exception):
  '''This exception is thrown when an entity cannot be loaded because it does 
  not exist as defined in our loading parameters.'''
  
  def __init__(self,entityType='asset',
                      entityID='',
                      entityPath='',
                      entityTitle='',
                      entityMDSet=''):
                      
    self.entityType = entityType
    self.entityID = entityID
    self.entityPath = entityPath
    self.entityTitle = entityTitle
  def __str__(self):
    if self.entityID:
      message = ' id:\'%s\'' % self.entityID
    if self.entityPath:
      message +=' path:\'%s\'' % self.entityPath
    if self.entityTitle:
      message +=' Title:\'%s\'' % self.entityTitle
    
    if message:
      message = 'No %s with: %s could be found!' % (self.entityType,message)
    else:
      message = 'No %s could be found!' % (self.entityType)
    
    return repr(message)
        
class FCSValidationError(Exception):
  '''This Exception is raised when a data validation failure occurs.'''

  def __init__(self,errorString='',fieldName='', dataType='', value='', validationInfo=''):
    self.fieldName = fieldName
    self.dataType = dataType
    self.value = value
    self.validationInfo = validationInfo
    self.errorString = errorString
  def __str__(self):
    string = ('Could not set new value for field:\'%s\', dataType:\'%s\', '
            'value:\'%s\' did not pass validation! %s' 
            % (self.fieldName,self.dataType,self.value,self.validationInfo))

    if self.errorString:
     string += 'Error: %s' % self.errorString

    return repr(string)

class FCSDuplicateError(Exception):
  '''This Exception is raised when fcsvr_client reports back an E_DUPLICATE
  error string''' 
  def __init__(self, error=''):
    self.error = error
  def __str__(self):
    return repr(self.error)

class FCSError(Exception):
  '''This Exception is raised when a generic FCS related runtime issue occurs.'''
  def __init__(self, errorString):
    self.errorString = errorString
  def __str__(self):
    return repr('FCS Error: %s\n' % self.errorString)


class FCSVRClientError(Exception):
  '''This exception serves as our catch-all for unknown fcsvr_client errors.'''
  
  def __init__(self,errorString,cmdString=''):
    self.errorString = errorString
    self.cmdString = cmdString
  def __str__(self):
    return repr('fcsvr_client Error: %s\nCommand Syntax:%s\n' 
                  % (self.errorString,self.cmdString))

class FCSVRClientFileError(Exception):  
  def __init__(self,errorString,cmdString=''):
    self.errorString = errorString
    self.cmdString = cmdString
  def __str__(self):
    message = ('fcsvr_client Error: %s\nCommand Syntax:%s\n' 
                  % (self.errorString,self.cmdString))
    return repr(message)
                  
class FCSVROfflineError(Exception):
  '''This exception is thrown when Final Cut Server is not running.'''
  def __init__(self,errorString):
    self.errorString = errorString
  def __str__(self):
    return repr(self.errorString)

class FCSVRClientPermissionDenied(Exception):
  '''This exception is thrown when fcsvr_client tries to perform write operation
  without admin priviliges'''
  
  def __init__(self,action,cmdString=''):
    self.action = action
    self.cmdString = cmdString
  def __str__(self):
    return repr('fcsvr_client Permission denied for action: %s cmdString: %s'
         % (self.action,self.cmdString))

class FCSObjectLoadError(Exception):
  '''This exception is thrown when an asset fails to load properly.'''
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

class FCSProductionLoadError(Exception):
  '''This exception is thrown when a production fails to load properly.'''
  
  def __init__(self,errorString,retString,cmdString):
    self.errorString = errorString
    self.retString = retString
    self.cmdString = cmdString
    
  def __str__(self):
    retString = self.errorString
    if self.cmdString:
      retString += '\nCommand: %s' % (self.cmdString)
    if self.retString:
      retString += '\nReturned Text: %s' % self.retString
    return retString   

        
