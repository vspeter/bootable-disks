""" Drive utilities """

from ctypes import cdll, POINTER, pointer, c_int, c_char_p, create_string_buffer
import os
import re
import glob
from subprocess import Popen, PIPE
from libdrive_h import drive_info, smart_attribs, PROTOCOL_TYPE_ATA, PROTOCOL_TYPE_SCSI

__VERSION__ = '2.6.0'

libdrive = cdll.LoadLibrary( 'libdrive.so.' + __VERSION__.split( '.' )[0] )

_set_verbose_ident = libdrive.set_verbose
_set_verbose_ident.argtypes = [ c_int ]
_set_verbose_ident.restype = None

_get_drive_info_ident = libdrive.get_drive_info
_get_drive_info_ident.argtypes = [ c_char_p, POINTER( drive_info ), c_char_p ]
_get_drive_info_ident.restype = c_int

_get_smart_attrs_ident = libdrive.get_smart_attrs
_get_smart_attrs_ident.argtypes = [ c_char_p, POINTER( smart_attribs ), c_char_p ]
_get_smart_attrs_ident.restype = c_int

_smart_status_ident = libdrive.smart_status
_smart_status_ident.argtypes = [ c_char_p, POINTER( c_int ), POINTER( c_int ), c_char_p ]
_smart_status_ident.restype = c_int

_drive_last_selftest_passed_ident = libdrive.drive_last_selftest_passed
_drive_last_selftest_passed_ident.argtypes = [ c_char_p, POINTER( c_int ), c_char_p ]
_drive_last_selftest_passed_ident.restype = c_int

_log_entry_count_ident = libdrive.log_entry_count
_log_entry_count_ident.argtypes = [ c_char_p, POINTER( c_int ), c_char_p ]
_log_entry_count_ident.restype = c_int

_MegaRAIDCLI = None
_3WareCLI = None

_driveCache = None


def _kernelCompare( version ): # returns true if the current kernel is >= version
  tmp = [ int( i ) for i in os.uname()[2].split( '-' )[0].split( '.' ) ]
  return tmp >= [ int( i ) for i in version.split( '.' ) ]


def setVerbose( verbose ):
  _set_verbose_ident( verbose )


def setCLIs( tw_cli=None, megaraid=None ):
  global _3WareCLI, _MegaRAIDCLI

  if tw_cli:
    _3WareCLI = tw_cli
  if megaraid:
    _MegaRAIDCLI = megaraid


##### Port and Drive
class Port( object ):
  def __init__( self ):
    super( Port, self ).__init__()
    self.drive = None
    self.host = None

  def __getattr__( self, name ):
    if name == 'location':
      return 'Unknown'

    if name == 'type':
      return 'Unknown'

    raise AttributeError( name )

  def setFault( self, value ):
    pass

  def __str__( self ):
    return "Port %s" % self.location

  def __cmp__( self, other ):
    if other is None:
      return 1
    return cmp( self.type, other.type ) or cmp( len( self.location ), len( other.location ) ) or cmp( self.location, other.location )


class Drive( object ):
  def __init__( self, port, name, block_name, libdrive_name ):
    super( Drive, self ).__init__()
    self._info = {}
    self.port = port
    self.port.drive = self
    self.name = name
    self.block_name = block_name
    self.libdrive_name = libdrive_name
    self.devpath = None
    self.pcipath = None
    self.scsi_generic = None
    if block_name is not None:
      tmp_list = glob.glob( '/sys/block/%s/device/scsi_disk/*' % block_name )
      if tmp_list:
        self.devpath = re.sub( '^/sys', '', os.path.realpath( tmp_list[0] ) ) # for use with udev

      tmp_list = glob.glob( '/sys/block/%s/device' % block_name ) # figure out how to do this for disks that don't have a block device
      if tmp_list:
        self.pcipath = re.sub( '^/sys/devices', '', os.path.realpath( tmp_list[0] ) )

      tmp_list = glob.glob( '/sys/block/%s/device/scsi_generic/sg*' % block_name )
      if tmp_list:
        self.scsi_generic = '/dev/%s' % tmp_list[0].split( '/' )[ -1 ]


  def __getattr__( self, name ):
    if name == 'block_path':
      if self.block_name is not None:
        return '/dev/%s' % self.block_name

      else:
        return None

    if name == 'reporting_info':
      if self.protocol == 'ATA':
        return { 'protocol': 'ATA', 'serial': self.serial, 'model': self.model, 'name': self.name, 'location': self.location, 'firmware': self.firmware }

      elif self.protocol == 'SCSI':
        return { 'protocol': 'SCSI', 'serial': self.serial, 'model': self.model, 'name': self.name, 'location': self.location, 'vendor': self.vendor, 'version': self.version }

      else:
        return { 'protocol': 'Unknown', 'serial': 'Unknown', 'model': 'Unknown', 'name': '', 'location': '', 'vendor': '', 'version': '', 'firmware': '' }

    if name == 'protocol':
      if not self._info:
        self._loadInfo()

      return self._info[ 'protocol' ]

    if name == 'serial':
      if not self._info:
        self._loadInfo()

      return self._info[ 'serial' ]

    if name == 'model':
      if not self._info:
        self._loadInfo()

      return self._info[ 'model' ]

    if name == 'firmware':
      if not self._info:
        self._loadInfo()

      if 'firmware' in self._info:
        return self._info[ 'firmware' ]

      else:
        return None

    if name == 'vendor':
      if not self._info:
        self._loadInfo()

      if 'vendor' in self._info:
        return self._info[ 'vendor' ]

      else:
        return None

    if name == 'version':
      if not self._info:
        self._loadInfo()

      if 'version' in self._info:
        return self._info[ 'version' ]

      else:
        return None

    if name == 'location':
      return self.port.location

    if name == 'isVirtualDisk':
      return self.model.lower() in ( 'virtual disk', 'qemu harddisk', 'vbox harddisk' )

    if name == 'capacity':
      if not self._info:
        self._loadInfo()

      return self._info[ 'capacity' ]

    if name in ( 'SMARTSupport', 'SMARTEnabled', 'supportsSelfTest', 'supportsLBA', 'supportsWriteSame', 'supportsTrim', 'isSSD', 'RPM', 'LogicalSectorSize', 'PhysicalSectorSize', 'LBACount', 'WWN' ):
      if not self._info:
        self._loadInfo()

      return self._info[ name ]

    raise AttributeError( name )

  def _loadInfo( self ):
    errstr = create_string_buffer( 100 )
    tmp = drive_info()

    if _get_drive_info_ident( self.libdrive_name, pointer( tmp ), errstr ):
      raise Exception( 'Error getting drive info "%s"' % errstr.value.strip() )

    if tmp.protocol == PROTOCOL_TYPE_ATA:
      self._info = { 'protocol': 'ATA', 'firmware': tmp.firmware_rev.strip() }

    elif tmp.protocol == PROTOCOL_TYPE_SCSI:
      self._info = { 'protocol': 'SCSI', 'vendor': tmp.vendor_id.strip(), 'version': tmp.version.strip() }

    else:
      raise Exception( 'Unkown Drive protocol "%s"' & tmp.protocol )

    for item in ( 'serial', 'model' ):
      self._info[ item ] = getattr( tmp, item ).strip()

    for item in ( 'SMARTSupport', 'SMARTEnabled', 'supportsSelfTest', 'supportsLBA', 'supportsWriteSame', 'supportsTrim', 'isSSD' ):
      self._info[ item ] = ( getattr( tmp, item ) == '\x01' )

    for item in ( 'RPM', 'LogicalSectorSize', 'PhysicalSectorSize', 'LBACount', 'WWN' ):
      self._info[ item ] = getattr( tmp, item )

    self._info['capacity'] = ( tmp.LogicalSectorSize * tmp.LBACount ) / ( 1024.0 * 1024.0 * 1024.0 ) # in GiB

  def smartAttrs( self ): # returns dict of [id] = ( value, maxValue, threshold, rawValue )
    result = {}

    errstr = create_string_buffer( 100 )
    attrs = smart_attribs()

    if _get_smart_attrs_ident( self.libdrive_name, pointer( attrs ), errstr ):
      raise Exception( 'Error getting drive SMART attributes "%s"' % errstr.value.strip() )

    if attrs.protocol == PROTOCOL_TYPE_ATA:
      for i in range( 0, attrs.count ):
        result[ attrs.data.ata[ i ].id ] = ( attrs.data.ata[ i ].current, attrs.data.ata[ i ].max, attrs.data.ata[ i ].threshold, attrs.data.ata[ i ].raw )

    elif attrs.protocol == PROTOCOL_TYPE_SCSI:
      for i in range( 0, attrs.count ):
        result[ '%s-%s' % ( attrs.data.scsi[ i ].page_code, attrs.data.scsi[ i ].parm_code ) ] = ( attrs.data.scsi[ i ].value )

    else:
      raise Exception( 'Unknown protocol type: %i' % attrs.protocol )

    return result


  def smartStatus( self ):
    errstr = create_string_buffer( 100 )

    fault = c_int( 0 )
    threshold = c_int( 0 )

    if _smart_status_ident( self.libdrive_name, pointer( fault ), pointer( threshold ), errstr ):
      raise Exception( 'Error getting drive SMART status "%s"' % errstr.value.strip() )

    return { 'drive_fault': ( fault.value > 0 ), 'threshold_exceeded': ( threshold.value > 0 ) }


  def lastSelfTestPassed( self ):
    errstr = create_string_buffer( 100 )

    passed = c_int( 0 )

    if _drive_last_selftest_passed_ident( self.libdrive_name, pointer( passed ), errstr ):
      raise Exception( 'Error getting drive selftest info "%s"' % errstr.value.strip() )

    return ( passed.value == 1 )


  def logEntryCount( self ):
    errstr = create_string_buffer( 100 )

    count = c_int( 0 )

    if _log_entry_count_ident( self.libdrive_name, pointer( count ), errstr ):
      raise Exception( 'Error getting drive Log Entry Count "%s"' % errstr.value.strip() )

    return count.value


  def driveReportingStatus( self ):
    #TODO: possibly throw difrent exception on getInfo, to distingish between really dead and less dead/SMART slowness
    drive_status = self.smartStatus()
    drive_status[ 'last_selftest_passed' ] = self.lastSelfTestPassed()
    drive_status[ 'attribs' ] = self.smartAttrs()
    drive_status[ 'log' ] = self.logEntryCount()
    if self.port.type == 'MegaRAID':
      tmp = getMegaRAIDMemberState( self.port )
      if tmp:
        drive_status[ 'controller_state' ] = tmp

    elif self.port.type == '3Ware':
      tmp = get3WareMemberState( self.port )
      if tmp:
        drive_status[ 'controller_state' ] = tmp

    return drive_status

  def setFault( self, value ):
    self.port.setFault( value )

  def __hash__( self ):
    return self.name.__hash__()

  def __str__( self ):
    return "Drive: %s %s(%s)" % ( self.name, self.block_path, self.location )

  def __cmp__( self, other ):
    if other is None:
      return 1

    return self.port.__cmp__( other.port )


###### ESX Utils
def getESXHBAList( driver_list ): # only complitable with esx5
  tmp = Popen( [ '/sbin/esxcli', 'storage', 'core', 'adapter', 'list' ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'got return code "%s" when getting list of adapters' % tmp.returncode )

  hba_list = []
  for line in stdout.splitlines():
    parts = line.split( None )
    if parts[1] in driver_list:
      hba_list.append( parts[0] )

  return hba_list


def getESXVolumeMap( hba_list ): # only complitable with esx5
  tmp = Popen( [ '/sbin/esxcli', 'storage', 'core', 'path', 'list' ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'got return code "%s" when getting list of volums' % tmp.returncode )

  volume_map = {}
  name = None
  device = None
  adapter = None
  for line in stdout.splitlines():
    try:
      ( key, value ) = line.strip().split( ':', 1 )

    except ValueError:
      continue

    key = key.strip()
    if key == 'Runtime Name':
      name = value.strip() # vmhba1:C0:T0:L0

    elif key == 'Device':
      device = value.strip() # naa.600050e07c52bc000c7d0000a8e10000

    elif key == 'Adapter':
      adapter = value.strip() # vmhba1

    if name is not None and device is not None and adapter is not None:
      if adapter in hba_list:
        volume_map[ name.split( ':', 1 )[-1] ] = device  # C0:T0:L0

      name = None
      device = None
      adapter = None

  return volume_map


###### IDE
class IDEPort( Port ):
  def __init__( self, port, *args, **kwargs  ):
    super( IDEPort, self ).__init__( *args, **kwargs )
    self.port = port
    self.host = None

  def __getattr__( self, name ):
    if name == 'location':
      return 'IDE %s' % self.port

    if name == 'type':
      return 'IDE'

    raise AttributeError( name )

  def __hash__( self ):
    return ( 'IDE %s' % ( self.port ) ).__hash__()


def getIDEPorts():
  ports = {}

  if _kernelCompare( '2.6.28' ):
    globfilter = '/sys/class/ide_port/%s/device/*/block/hd*'
    globdelim = '/'

  else: # for <= 2.6.26 kernel, when move off etch/lenny, can be removed
    globfilter = '/sys/class/ide_port/%s/device/*/block:hd*'
    globdelim = ':'

  ide_list = []
  tmp_list = glob.glob( '/sys/class/ide_port/ide*' )
  for name in tmp_list:
    ide_list.append( name.split( '/' )[-1] )

  i = 0

  for ide in ide_list:
    port = IDEPort( i )
    tmp_list = glob.glob( globfilter % ide )
    if len( tmp_list ) > 0:
      tmp = tmp_list[0].split( globdelim )[-1]
      ports[ port ] = tmp

    else:
      ports[ port ] = None
    i += 1

  return ports


### ATA
class ATAPort( Port ):
  def __init__( self, host, port, *args, **kwargs  ):
    super( ATAPort, self ).__init__( *args, **kwargs )
    self.port = port
    self.host = host

  def __getattr__( self, name ):
    if name == 'location':
      return 'ATA %s' % self.port

    if name == 'type':
      return 'ATA'

    raise AttributeError( name )

  def __hash__( self ):
    return ( 'ATA %s' % ( self.port ) ).__hash__()


def getATAPorts():
  ports = {}
  exclude_hosts = []
  double_hosts = []

  if _kernelCompare( '2.6.28' ):
    globfilter = '/sys/class/scsi_host/%s/device/target*/*/block/sd*'
    globdelim = '/'
  else: # for <= 2.6.26 kernel, when move off etch/lenny, can be removed
    globfilter = '/sys/class/scsi_host/%s/device/target*/*/block:sd*'
    globdelim = ':'

  # add usb disks to exclude list
  tmp_list = glob.glob( '/sys/bus/usb/devices/*/host*' )
  for name in tmp_list:
    exclude_hosts.append( name.split( '/' )[-1] )

  # add 3ware disks to exclude list
  tmp_list = glob.glob( '/sys/bus/pci/drivers/3w-*/*/host*' )
  for name in tmp_list:
    exclude_hosts.append( name.split( '/' )[-1] )

  # add mearaid_sas disks to exclude list
  tmp_list = glob.glob( '/sys/bus/pci/drivers/megaraid_sas/*/host*' )
  for name in tmp_list:
    exclude_hosts.append( name.split( '/' )[-1] )

  # add mptspi disks to exclude list
  tmp_list = glob.glob( '/sys/bus/pci/drivers/mpt*/*/host*' )
  for name in tmp_list:
    exclude_hosts.append( name.split( '/' )[-1] )

  # do intel's ata_piix driver
  tmp_list = glob.glob( '/sys/bus/pci/drivers/ata_piix/*/ata*/host*' )
  for name in tmp_list:
    double_hosts.append( name.split( '/' )[-1] )

  tmp_list = glob.glob( '/sys/bus/pci/drivers/ata_piix/*/host*' )
  for name in tmp_list:
    double_hosts.append( name.split( '/' )[-1] )

  i = 0

  # we are sorting by pci bus then disk host, this way we are not affected by drive load order, thanks for the pointer Paul Cannon
  tmp_list = []
  for item in glob.glob( '/sys/devices/pci[0-9]*/[0-9]*/[0-9]*/[0-9]*/ata*/host*' ):
    tmp = item.replace( ':', '' ).replace( '.', '' ).split( '/' )
    tmp_list.append( ( '%s %s %s %s %04d' % ( tmp[3], tmp[4], tmp[5], tmp[6], int( re.sub( '[^0-9]', '', tmp[8] ) ) ), tmp[8] ) )

  for item in glob.glob( '/sys/devices/pci[0-9]*/[0-9]*/[0-9]*/[0-9]*/host*' ):
    tmp = item.replace( ':', '' ).replace( '.', '' ).split( '/' )
    tmp_list.append( ( '%s %s %s %s %04d' % ( tmp[3], tmp[4], tmp[5], tmp[6], int( re.sub( '[^0-9]', '', tmp[7] ) ) ), tmp[7] ) )

  for item in glob.glob( '/sys/devices/pci[0-9]*/[0-9]*/[0-9]*/ata*/host*' ):
    tmp = item.replace( ':', '' ).replace( '.', '' ).split( '/' )
    tmp_list.append( ( '%s %s %s 000000000 %04d' % ( tmp[3], tmp[4], tmp[5], int( re.sub( '[^0-9]', '', tmp[7] ) ) ), tmp[7] ) )

  for item in glob.glob( '/sys/devices/pci[0-9]*/[0-9]*/[0-9]*/host*' ):
    tmp = item.replace( ':', '' ).replace( '.', '' ).split( '/' )
    tmp_list.append( ( '%s %s %s 000000000 %04d' % ( tmp[3], tmp[4], tmp[5], int( re.sub( '[^0-9]', '', tmp[6] ) ) ), tmp[6] ) )

  for item in glob.glob( '/sys/devices/pci[0-9]*/[0-9]*/ata*/host*' ):
    tmp = item.replace( ':', '' ).replace( '.', '' ).split( '/' )
    tmp_list.append( ( '%s %s 000000000 000000000 %04d' % ( tmp[3], tmp[4], int( re.sub( '[^0-9]', '', tmp[6] ) ) ), tmp[6] ) )

  for item in glob.glob( '/sys/devices/pci[0-9]*/[0-9]*/host*' ):
    tmp = item.replace( ':', '' ).replace( '.', '' ).split( '/' )
    tmp_list.append( ( '%s %s 000000000 000000000 %04d' % ( tmp[3], tmp[4], int( re.sub( '[^0-9]', '', tmp[5] ) ) ), tmp[5] ) )

  tmp_list.sort()

  name_map = {}  # hosts's and their order
  for ( _, name ) in tmp_list: # don't need tmp anymore, it was there for the sorting
    if os.access( '/sys/class/scsi_host/%s/device/sas_host' % name, os.F_OK ):
      continue

    if name in exclude_hosts:
      continue

    name_map[ name ] = i
    if name in double_hosts:
      i += 2

    else:
      i += 1

  for name in name_map:
    port = ATAPort( int( re.sub( '[^0-9]', '', name ) ), name_map[ name ] )
    tmp_list = glob.glob( globfilter % name )
    if name in double_hosts:
      port2 = ATAPort( int( re.sub( '[^0-9]', '', name ) ), ( name_map[ name ] + 1 ) )
      if len( tmp_list ) > 1:
        ports[ port ] = tmp_list[0].split( globdelim )[-1]
        ports[port2] = tmp_list[1].split( globdelim )[-1]

      elif len( tmp_list ) > 0:
        ports[ port ] = tmp_list[0].split( globdelim )[-1]
        ports[port2] = None

      else:
        ports[ port ] = None
        ports[port2] = None

    else:
      if len( tmp_list ) > 0:
        ports[ port ] = tmp_list[0].split( globdelim )[-1]

      else:
        ports[ port ] = None

  return ports


def getATAPorts_ESX():
  hba_list = getESXHBAList( ( 'ahci' ) )

  if not hba_list:
    return {}

  ports = {}

  #volume_map = getESXVolumeMap( hba_list )

  """
  for name in name_map:
    port = ATAPort( int( re.sub( '[^0-9]', '', name ) ), name_map[ name ], 'Unknown' )
    tmp_list = glob.glob( globfilter % name )
    if name in double_hosts:
      port2 = ATAPort( int( re.sub( '[^0-9]', '', name ) ), ( name_map[ name ] + 1 ), 'Unknown' )
      if len( tmp_list ) > 1:
        ports[ port ] = tmp_list[0].split( globdelim )[-1]
        ports[port2] = tmp_list[1].split( globdelim )[-1]
      elif len( tmp_list ) > 0:
        ports[ port ] = tmp_list[0].split( globdelim )[-1]
        ports[port2] = None
      else:
        ports[ port ] = None
        ports[port2] = None
    else:
      if len( tmp_list ) > 0:
        ports[ port ] = tmp_list[0].split( globdelim )[-1]
      else:
        ports[ port ] = None
   """
  return ports


##### 3ware
class ThreeWarePort( Port ):
  def __init__( self, host, controller, enclosure, slot, port, *args, **kwargs  ):
    super( ThreeWarePort, self ).__init__( *args, **kwargs )
    self.controller = controller
    self.enclosure = enclosure
    self.slot = slot
    self.port = port
    self.host = int( host )

  def __getattr__( self, name ):
    if name == 'location':
      if self.enclosure is None:
        if self.port is None:
          return '3Ware %s:Unknown' % ( self.controller )

        else:
          return '3Ware %s:%s' % ( self.controller, self.port )

      else:
        return '3Ware %s:%s:%s' % ( self.controller, self.enclosure, self.slot )

    if name == 'type':
      return '3Ware'

    if name == 'physical_location':
      if self.enclosure is None:
        if self.port is None:
          return None

        else:
          return '/c%s/p%s' % ( self.controller, self.port )

      else:
        return '/c%s/e%s/slot%s' % ( self.controller, self.enclosure, self.slot )

    if name == 'vport':
      if self.port is None:
        return None

      else:
        return '/c%s/p%s' % ( self.controller, self.port )

    raise AttributeError( name )

  def setFault( self, value ):
    set3WareFault( self.physical_location, value )

  def __hash__( self ):
    return ( '3Ware %s %s' % ( self.controller, self.port ) ).__hash__()


def _get3WareLists():
  tmp = Popen( [ _3WareCLI, 'show' ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'got return code "%s" when getting list of 3ware controllers' % tmp.returncode )

  controller_list = []
  enclosure_list = []
  for line in stdout.splitlines():
    result = re.match( 'c([0-9]+) ', line )
    if result:
      controller_list.append( int( result.group( 1 ) ) )

    result = re.match( '/c([0-9]+)/e([0-9]+) ', line )
    if result:
      enclosure_list.append( ( int( result.group( 1 ) ), int( result.group( 2 ) ) ) )

  return ( controller_list, enclosure_list )


def get3WareSlots():
  if not _3WareCLI or not( os.access( '/sys/bus/pci/drivers/3w-sas', os.R_OK ) or os.access( '/sys/bus/pci/drivers/3w-9xxx', os.R_OK ) ):
    return {}

  # I can't find anyway to get this info with out the cli...
  if not os.access( _3WareCLI, os.X_OK ):
    raise Exception( '3ware driver loaded but no 3ware cli' )

  ports = {}

  ( controller_list, enclosure_list ) = _get3WareLists()

  if not controller_list:
    return {}

  if len( controller_list ) > 1:
    raise Exception( 'I haven\'t figure out how to map multiple cards to hosts yet, now I get too!' )

  host_list = []
  host_list += glob.glob( '/sys/bus/pci/drivers/3w-sas/*/host*' )
  host_list += glob.glob( '/sys/bus/pci/drivers/3w-9xxx/*/host*' )

  if host_list:
    host = int( re.sub( '[^0-9]', '', host_list[0].split( '/' )[-1] ) )
  else:
    raise Exception( 'Don\'t know where to go to get the host' )

  if not enclosure_list:
    for controller in controller_list:
      tmp = Popen( [ _3WareCLI, '/c%s' % controller, 'show', 'drivestatus' ], stdout=PIPE, stderr=PIPE )
      ( stdout, stderr ) = tmp.communicate()
      if tmp.returncode != 0:
        raise Exception( 'Got return code "%s" when getting list of ports on controller "%s"' % ( tmp.returncode, controller ) )

      for line in stdout.splitlines():
        result = re.match( 'p([0-9]+).*u([0-9]+)', line )
        if result:
          port = ThreeWarePort( host, controller, None, None, int( result.group( 1 ) ) )
          tmp_list = glob.glob( '/sys/class/scsi_host/host%s/device/target%s:0:%s/*/block/sd*' % ( host, host, int( result.group( 2 ) ) ) )
          ports[ port ] = ( tmp_list[0].split( '/' )[-1], 'twa%s:%s' % ( controller, int( result.group( 1 ) ) ) )

        else:
          result = re.match( 'p([0-9]+).*-', line )
          if result:
            port = ThreeWarePort( host, controller, None, None, int( result.group( 1 ) ) )
            ports[ port ] = ( None, 'twa%s:%s' % ( controller, int( result.group( 1 ) ) ) )

  else: # update _ESX version
    slot_unit_map = {}

    #print enclosure_list

    for controller in controller_list:
      tmp = Popen( [ _3WareCLI, '/c%s' % controller, 'show', 'drivestatus' ], stdout=PIPE, stderr=PIPE )
      ( stdout, stderr ) = tmp.communicate()
      if tmp.returncode != 0:
        raise Exception( 'Got return code "%s" when getting list of ports on controller "%s"' % ( tmp.returncode, controller ) )

      for line in stdout.splitlines():
        #print line
        result = re.match( 'p[0-9]+.*u([0-9]+).*/c([0-9]+)/e([0-9]+)/slt([0-9]+)', line )
        if result:
          slot_unit_map[ ( int( result.group( 2 ) ), int( result.group( 3 ) ), int( result.group( 4 ) ) ) ] = int( result.group( 1 ) )

    #print slot_unit_map

    for enclosure in enclosure_list:
      ( controller, enclosure ) = enclosure
      tmp = Popen( [ _3WareCLI, '/c%s/e%s' % ( controller, enclosure ), 'show', 'slots' ], stdout=PIPE, stderr=PIPE )
      ( stdout, stderr ) = tmp.communicate()

      if tmp.returncode != 0:
        raise Exception( 'Got return code "%s" when getting list of ports on enclosure "%s"' % ( tmp.returncode, enclosure ) )

      for line in stdout.splitlines():
        line = line.lower().split()
        if len( line ) != 4:
          continue

        result = re.match( 'slot([0-9]+)', line[0] )
        if result:
          slot = int( result.group( 1 ) )
          result = re.match( '/c[0-9]+/p([0-9]+)', line[2] )

          if result:
            port = ThreeWarePort( host, controller, enclosure, slot, int( result.group( 1 ) ) )
            tmp_list = glob.glob( '/sys/class/scsi_host/host%s/device/target%s:0:%s/*/block/sd*' % ( host, host, slot_unit_map[ ( controller, enclosure, slot ) ]  ) ) # this is for singles, what about groups?
            ports[ port ] = ( tmp_list[0].split( '/' )[-1], 'twl%s:%s' % ( controller, int( result.group( 1 ) ) ) )

          else: # empty
            port = ThreeWarePort( host, controller, enclosure, slot, None )
            ports[ port ] = ( None, None )

  return ports


def get3WareSlots_ESX():
  hba_list = getESXHBAList( ( '3w-9xxx', '3w-sas' ) )

  if not hba_list:
    return {}

  # I can't find anyway to get this info with out the cli...
  if not os.access( _3WareCLI, os.X_OK ):
    raise Exception( '3ware driver loaded but no 3ware cli' )

  ports = {}

  ( controller_list, enclosure_list ) = _get3WareLists()

  if not controller_list:
    return {}

  if len( controller_list ) > 1 or len( hba_list ) > 1:
    raise Exception( 'I haven\'t figure out how to map multiple cards to hosts yet, now I get too!' )

  host = 0 # do hosts matter in ESX?

  volume_map = getESXVolumeMap( hba_list )

  if not enclosure_list:
    for controller in controller_list:
      tmp = Popen( [ _3WareCLI, '/c%s' % controller, 'show', 'drivestatus' ], stdout=PIPE, stderr=PIPE )
      ( stdout, stderr ) = tmp.communicate()
      if tmp.returncode != 0:
        raise Exception( 'Got return code "%s" when getting list of ports on controller "%s"' % ( tmp.returncode, controller ) )

      for line in stdout.splitlines():
        result = re.match( 'p([0-9]+).*u([0-9]+)', line )
        if result:
          port = ThreeWarePort( host, controller, None, None, int( result.group( 1 ) ) )
          ports[ port ] = ( volume_map[ 'C0:T%s:L0' % int( result.group( 2 ) ) ], 'twavm%s:%s' % ( controller, int( result.group( 1 ) ) ) )

  else:
    raise Exception( 'Not implemented yet' )

  return ports


def get3WareMemberState( port ):
  if not os.access( _3WareCLI, os.X_OK ):
    raise Exception( '3ware drive requested but no 3ware cli' )

  tmp = Popen( [ _3WareCLI, port.vport, 'show', 'status' ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'Got return code "%s" when getting 3Ware disk info for %s' % ( tmp.returncode, port.vport ) )

  for line in stdout.splitlines():
    result = re.match( '/c[0-9]+/p[0-9]+ Status = (.*)', line )
    if result:
      state = result.group( 1 ).strip()
      if state not in ( 'OK' ):
        return state

      else:
        return None


def set3WareFault( physical_location, state ):
  if not os.access( _3WareCLI, os.X_OK ):
    raise Exception( '3ware drive requested but no 3ware cli' )

  if not physical_location:
    return

  if state:
    state = 'on'
  else:
    state = 'off'

  tmp = Popen( [ _3WareCLI, physical_location, 'set', 'identify=%s' % state ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'got return code "%s" when setting identify indicator on %s' % ( tmp.returncode, physical_location ) )


def get3WareBBUStatus():
  if not _3WareCLI or not( os.access( '/sys/bus/pci/drivers/3w-sas', os.R_OK ) or os.access( '/sys/bus/pci/drivers/3w-9xxx', os.R_OK ) ):
    return {}

  if not os.access( _3WareCLI, os.X_OK ):
    raise Exception( '3ware drive requested but no 3ware cli' )

  ( controller_list, enclosure_list ) = _get3WareLists()

  if not controller_list:
    return {}

  status = {}

  for controller in controller_list:
    tmp = Popen( [ _3WareCLI, '/c%s/bbu' % controller, 'show', 'all' ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()

    if tmp.returncode == 1: # returncode == 1 when there is no BBU
      continue

    elif tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting 3Ware BBU info on controller "%s"' % ( tmp.returncode, controller ) )

    status[ controller ] = {}

    for line in stdout.splitlines():
      result = re.match( '/c[0-9]+/bbu Online State[ ]*= (.*)', line )
      if result:
        status[ controller ][ 'Online State' ] = result.group( 1 ).strip()

      result = re.match( '/c[0-9]+/bbu BBU Status[ ]*= (.*)', line )
      if result:
        status[ controller ][ 'BBU Status' ] = result.group( 1 ).strip()

      result = re.match( '/c[0-9]+/bbu BBU Ready[ ]*= (.*)', line )
      if result:
        status[ controller ][ 'BBU Ready' ] = result.group( 1 ).strip()

      result = re.match( '/c[0-9]+/bbu Last Capacity Test[ ]*= (.*)', line )
      if result:
        status[ controller ][ 'Last Test' ] = result.group( 1 ).strip()

      result = re.match( '/c[0-9]+/bbu Battery Installation Date[ ]*= (.*)', line )
      if result:
        status[ controller ][ 'Install Date' ] = result.group( 1 ).strip()

      result = re.match( '/c[0-9]+/bbu Battery Temperature Value[ ]*= (.*)', line )
      if result:
        status[ controller ][ 'Battery Temp' ] = result.group( 1 ).strip()

    return status


def get3WareUnitStatus():
  if not _3WareCLI or not( os.access( '/sys/bus/pci/drivers/3w-sas', os.R_OK ) or os.access( '/sys/bus/pci/drivers/3w-9xxx', os.R_OK ) ):
    return {}

  if not os.access( _3WareCLI, os.X_OK ):
    raise Exception( '3ware drive requested but no 3ware cli' )

  ( controller_list, enclosure_list ) = _get3WareLists()

  if not controller_list:
    return {}

  status = {}

  for controller in controller_list:
    tmp = Popen( [ _3WareCLI, '/c%s' % controller, 'show', 'unitstatus' ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()
    if tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting 3Ware unitstatus info on controller "%s"' % ( tmp.returncode, controller ) )

    status[ controller ] = []

    for line in stdout.splitlines():
      parts = line.split()
      if not parts:
        continue
      if parts[0].startswith( 'u' ):
        status[ controller ].append( { 'Name': parts[0], 'Type': parts[1], 'Status': parts[2], 'Size': parts[6], 'Cache': parts[7], 'Auto Verify': parts[8] } )

    return status


######## MegaRAID
class MegaRAIDPort( Port ):
  def __init__( self, host, controller, enclosure, port, *args, **kwargs  ):
    super( MegaRAIDPort, self ).__init__( *args, **kwargs )
    self.controller = controller
    self.enclosure = enclosure
    self.port = port
    self.host = int( host )

  def __getattr__( self, name ):
    if name == 'location':
      return 'MegaRAID %s:%s:%s' % ( self.controller, self.enclosure, self.port )

    if name == 'type':
      return 'MegaRAID'

    raise AttributeError( name )

  def setFault( self, value ):
    setMegaRAIDFault( self.controller, self.enclosure, self.port, value )

  def __hash__( self ):
    return ( 'MegaRAID %s %s' % ( self.controller, self.port ) ).__hash__()


def _getMegaRAIDLists():
  tmp = Popen( [ _MegaRAIDCLI, '-EncInfo', '-aALL' ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'got return code "%s" when getting list of MegaRAID controllers' % tmp.returncode )

  controller_list = []
  enclosure_list = []
  tmpController = None
  for line in stdout.splitlines():
    result = re.match( '\s*Number of enclosures on adapter ([0-9]+)', line )
    if result:
      tmpController = result.group( 1 )
      controller_list.append( tmpController )

    result = re.match( '\s*Enclosure ([0-9]+):', line )
    if result:
      enclosure_list.append( '%s-%s' % ( tmpController, result.group( 1 ) ) )

  return ( controller_list, enclosure_list )


def _getMegaRAIDLogicalVolumes( controller_list ):
  logicalVolumes_list = {}

  for controller in controller_list:
    logicalVolumes_list[ controller ] = []

    tmp = Popen( [ _MegaRAIDCLI, '-LDInfo', '-Lall', '-a%s' % controller ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()
    if tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting list of logical volumes on controller "%s"' % ( tmp.returncode, controller ) )

    for line in stdout.splitlines():
      result = re.match( 'Virtual Drive: ([0-9])* (Target Id: \([0-9])*\)', line )
      if result:
        logicalVolumes_list[ controller ].append( ( int( result.group( 1 ) ), int( result.group( 2 ) ) ) )

  return logicalVolumes_list


def getMegaRAIDPorts():
  if not _MegaRAIDCLI or not( os.access( '/sys/bus/pci/drivers/megaraid_sas', os.R_OK ) ):
    return {}

  # I can't find anyway to get this info with out the cli...
  if not os.access( _MegaRAIDCLI, os.X_OK ):
    raise Exception( 'MegaRAID driver loaded but no MegaRAID cli' )

  ports = {}

  ( controller_list, enclosure_list ) = _getMegaRAIDLists()

  if not controller_list:
    return {}

  #logicalVolumes_list = _getMegaRAIDLogicalVolumes( controller_list )

  if len( controller_list ) > 1:
    raise Exception( 'I haven\'t figure out how to map multiple cards to hosts yet, now I get too!' )

  host_list = []
  host_list += glob.glob( '/sys/bus/pci/drivers/megaraid_sas/*/host*' )

  if host_list:
    host = int( re.sub( '[^0-9]', '', host_list[0].split( '/' )[-1] ) )
  else:
    raise Exception( 'Don\'t know where to go to get the host' )

  for controller in controller_list:
    tmp = Popen( [ _MegaRAIDCLI, '-PDList', '-a%s' % controller ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()
    if tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting list of ports on controller "%s"' % ( tmp.returncode, controller ) )

    slot = None
    device = None
    enclosure = None

    for line in stdout.splitlines():
      try:
        ( key, value ) = line.strip().split( ':', 1 )

      except ValueError:
        continue

      key = key.strip()

      if key == 'Enclosure Device ID':
        enclosure = int( value.strip() )

      elif key == 'Slot Number':
        slot = int( value.strip() )

      elif key == 'Device Id':
        device = int(  value.strip() )

      if enclosure is not None and slot is not None and device is not None:
        port = MegaRAIDPort( host, controller, enclosure, slot )
        tmp_list = glob.glob( '/sys/class/scsi_host/host%s/device/target%s:0:%s/*/block/sd*' % ( host, host, device ) )
        if tmp_list:
          ports[ port ] = ( tmp_list[0].split( '/' )[-1], 'host%s:%s' % ( host, device ) )

        else:
          ports[ port ] = ( None, 'host%s:%s' % ( host, device ) )

        #else:
        #  ldmember_list something to get tmp_list and look for it in a volume

        slot = None
        device = None
        enclosure = None

  return ports


#MeagaRAID Targets seem to be ....
# X == host
# for LD targetX:2:Y   (Firmware state: Online, Spun Up )
#   where y is the target from -LDInfo
# for JBOD targetX:0:Y  (Firmware state: JBOD)
#    where y is the Device Id
def getMegaRAIDPorts_ESX():
  hba_list = getESXHBAList( ( 'megaraid_sas' ) )

  if not hba_list:
    return {}

  # I can't find anyway to get this info with out the cli...
  if not os.access( _MegaRAIDCLI, os.X_OK ):
    raise Exception( 'MegaRAID driver loaded but no MegaRAID cli' )

  ports = {}

  ( controller_list, enclosure_list ) = _getMegaRAIDLists()

  if not controller_list:
    return {}

  if len( controller_list ) > 1 or len( hba_list ) > 1:
    raise Exception( 'I haven\'t figure out how to map multiple cards to hosts yet, now I get too!' )

  host = 6  # how to find this?

  volume_map = getESXVolumeMap( hba_list )

  for controller in controller_list:
    tmp = Popen( [ _MegaRAIDCLI, '-PDList', '-a%s' % controller ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()
    if tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting list of ports on controller "%s"' % ( tmp.returncode, controller ) )

    slot = None
    device = None
    enclosure = None

    for line in stdout.splitlines():
      try:
        ( key, value ) = line.strip().split( ':', 1 )
      except ValueError:
        continue

      key = key.strip()

      if key == 'Enclosure Device ID':
        enclosure = int( value.strip() )

      elif key == 'Slot Number':
        slot = int( value.strip() )

      elif key == 'Device Id':
        device = int( value.strip() )

      if enclosure is not None and slot is not None and device is not None:
        port = MegaRAIDPort( host, controller, enclosure, slot )
        ports[ port ] = ( volume_map[ 'C2:T%s:L0' % controller ], 'host%s:%s' % ( host, device ) )

        slot = None
        device = None
        enclosure = None

  return ports


def getMegaRAIDMemberState( port ):
  if not os.access( _MegaRAIDCLI, os.X_OK ):
    raise Exception( 'MegaRAID drive requested but no MeagaRAID cli' )

  tmp = Popen( [ _MegaRAIDCLI, '-pdInfo', '-PhysDrv[%s:%s]' % ( port.enclosure, port.port ), '-a%s' % port.controller ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'Got return code "%s" when getting MEGARaid disk info for [%s:%s], c: %s' % ( tmp.returncode, port.enclosure, port.port, port.controller  ) )

  for line in stdout.splitlines():
    if line.startswith( 'Firmware state:' ):
      state = line.split( ':' )[-1].strip()
      if state not in ( 'Unconfigured(good)', 'Unconfigured(good), Spun down', 'Unconfigured(good), Spun Up', 'Online, Spun down', 'Online, Spun Up', 'JBOD' ):
        return state
      else:
        return None


def setMegaRAIDFault( controller, enclosure, port, value ):
  if not os.access( _MegaRAIDCLI, os.X_OK ):
    raise Exception( 'MegaRAID drive requested but no MeagaRAID cli' )

  if value:
    option = '-start'
  else:
    option = '-stop'

  tmp = Popen( [ _MegaRAIDCLI, '-PdLocate', option, '-physdrv[%s:%s]' % ( port.enclosure, port.port ), '-a%s' % port.controller  ], stdout=PIPE, stderr=PIPE )
  ( stdout, stderr ) = tmp.communicate()
  if tmp.returncode != 0:
    raise Exception( 'got return code "%s" when setting identify indicator on MEGARaid disk [%s:%s], c: %s' % ( tmp.returncode, port.enclosure, port.port, port.controller  ) )


def getMegaBBUStatus():
  if not _MegaRAIDCLI or not( os.access( '/sys/bus/pci/drivers/megaraid_sas', os.R_OK ) ):
    return {}

  if not os.access( _MegaRAIDCLI, os.X_OK ):
    raise Exception( 'MegaRAID driver loaded but no MegaRAID cli' )

  ( controller_list, enclosure_list ) = _getMegaRAIDLists()

  if not controller_list:
    return {}

  status = {}

  for controller in controller_list:
    tmp = Popen( [ _MegaRAIDCLI, '-AdpBbuCmd', '-a%s' % controller ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()
#    if tmp.returncode == 1: # returncode == 1 when there is no BBU
#      continue
#    elif tmp.returncode != 0:
    if tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting MEGARaid BBU info on controller "%s"' % ( tmp.returncode, controller ) )

    status[ controller ] = {}

    for line in stdout.splitlines():
      result = re.match( 'Battery State[ ]*:(.*)', line )
      if result:
        status[ controller ][ 'Battery State' ] = result.group( 1 ).strip()

      result = re.match( '[ ]*Charging Status[ ]*: (.*)', line )
      if result:
        status[ controller ][ 'Charging Status' ] = result.group( 1 ).strip()

      result = re.match( '[ ]*Battery Replacement required[ ]*: (.*)', line )
      if result:
        status[ controller ][ 'Replacement Required' ] = result.group( 1 ).strip()

      result = re.match( '[ ]*Pack is about to fail & should be replaced[ ]*: (.*)', line )
      if result:
        status[ controller ][ 'About To Fail' ] = result.group( 1 ).strip()

      result = re.match( '[ ]*Next Learn time[ ]*: (.*)', line )
      if result:
        status[ controller ][ 'Next Learn' ] = result.group( 1 ).strip()

      result = re.match( 'Temperature: (.*)', line )
      if result:
        status[ controller ][ 'Battery Temp' ] = result.group( 1 ).strip()

    return status


def getMegaUnitStatus():
  if not _MegaRAIDCLI or not( os.access( '/sys/bus/pci/drivers/megaraid_sas', os.R_OK ) ):
    return {}

  if not os.access( _MegaRAIDCLI, os.X_OK ):
    raise Exception( 'MegaRAID driver loaded but no MegaRAID cli' )

  ( controller_list, enclosure_list ) = _getMegaRAIDLists()

  if not controller_list:
    return {}

  status = {}

  for controller in controller_list:
    tmp = Popen( [ _MegaRAIDCLI, '-LDInfo', '-LALL', '-a%s' % controller ], stdout=PIPE, stderr=PIPE )
    ( stdout, stderr ) = tmp.communicate()
    if tmp.returncode != 0:
      raise Exception( 'Got return code "%s" when getting MEGARaid unitstatus info on controller "%s"' % ( tmp.returncode, controller ) )

    status[ controller ] = {}

    ld = -1

    for line in stdout.splitlines():
      result = re.match( 'Virtual Drive: ([0-9]*)', line )
      if result:
        ld = result.group( 1 ).strip()

      result = re.match( 'State[ ]*: (.*)', line )
      if result:
        status[ controller ][ ld ] = result.group( 1 ).strip()

    return status


##### SAS
class SASPort( Port ):
  def __init__( self, sas_address, scsi_id, slot, slot_name, *args, **kwargs  ):
    super( SASPort, self ).__init__( *args, **kwargs )
    self.sas_address = sas_address
    self.scsi_id = scsi_id
    self.slot = slot
    self.slot_name = slot_name
    self.host = int( scsi_id.split( ':' )[0] )

  def __getattr__( self, name ):
    if name == 'location':
      return 'SAS %s:%s' % ( self.sas_address, self.slot )

    if name == 'type':
      return 'SAS'

    raise AttributeError( name )

  def setFault( self, value ):
    if self.slot_name:
      setSASFault( self.scsi_id, self.slot_name, value )

  def __hash__( self ):
    return ( 'SAS %s %s' % ( self.sas_address, self.slot ) ).__hash__()


def getSASEnclosureList():
  enclosure_list = {}

  if not os.access( '/sys/class/sas_expander/', os.F_OK ) or not os.access( '/sys/class/enclosure/', os.F_OK ):
    return enclosure_list

  for name in os.listdir( '/sys/class/sas_expander/' ): # .sort( cmp=lambda x,y: cmp( int( re.sub( '[^0-9]', '', x ) ), int( re.sub( '[^0-9]', '', y ) ) ) ):
    tmp_list = glob.glob( '/sys/class/sas_expander/%s/device/port-*/end_device-*/target*/[0-9:]*/enclosure' % name )
    if len( tmp_list ) < 1:
      continue

    if not os.access( '/sys/class/sas_device/%s/sas_address' % name, os.F_OK ):
      continue

    enclosure_list[ tmp_list[0].split( '/' )[-2] ] = open( '/sys/class/sas_device/%s/sas_address' % name, 'r' ).read().strip()

  return enclosure_list


def _getEnclosurePortMap( enclosure ): # TODO: Cache this? save some globbing?
  # "port" names found so far "Slot 01", "SLOT 001", "001", "1", "ArrayDevice01", starting at 0 or 1
  # gen3 voyager: A00 -> E11
  # pikes peak: SLOT  1 [A, 1]

  ports = list( set( [ i.split( '/' )[-1] for i in glob.glob( '/sys/class/enclosure/%s/*' % enclosure ) ] ) - set( [ 'uevent', 'subsystem', 'device', 'components', 'power' ] ) )

  if not ports:
    return {}

  ports.sort()

  if re.match( '[A-E][0-9]+', ports[0] ): # voyager gen3
    return dict( zip( ports, ports ) )

  if re.match( 'SLOT[ 0-9]*\[[A-G],[ ]*[1-9]+\]', ports[0] ): # pikes peak
    result = {}
    for item in ports:
      ( bay, slot ) = item.split( '[' )[1].split( ']' )[0].split( ',' )
      result[ '%s%02i' % ( bay, int( slot ) ) ] = item

    return result

  if re.match( '[0-9]+', ports[0] ): # numeric names
    return dict( zip( range( 0, len( ports ) ), ports ) )

  if re.match( 'Slot[ ]*[0-9]+', ports[0] ) or re.match( 'SLOT[ ]*[0-9]+', ports[0] ) or re.match( 'ArrayDevice[ ]*[0-9]+', ports[0] ):
    return dict( zip( range( 0, len( ports ) ), ports ) )

  raise Exception( 'Unknown Port Naming System' )


def getSASEnclosurePorts( enclosure, sas_address ):
  port_map = _getEnclosurePortMap( enclosure )

  ports = {}
  for i in port_map:
    port = SASPort( sas_address, enclosure, i, port_map[ i ] )
    block_list = glob.glob( '/sys/class/enclosure/%s/%s/device/block/sd*' % ( enclosure, port_map[ i ] ) )
    if len( block_list ) > 0:
      ports[ port ] = block_list[0].split( '/' )[-1]

    else:
      generic_list = glob.glob( '/sys/class/enclosure/%s/%s/device/scsi_generic/sg*' % ( enclosure, port_map[ i ] ) )
      if len( generic_list ) > 0:
        ports[ port ] = generic_list[0].split( '/' )[-1]

      else:
        ports[ port ] = None

  return ports


def setSASFault( enclosure, port, state ):
  path = '/sys/class/enclosure/%s/%s/fault' % ( enclosure, port )

  if os.access( path, os.W_OK ):
    wrkFile = open( path, 'w' )
    if state:
      wrkFile.write( '1' )
    else:
      wrkFile.write( '0' )
    wrkFile.close()


def getSASDirectPorts():
  ports = {}

  block_list = glob.glob( '/sys/class/scsi_host/host*/device/phy-*/port/end_device-*/target*/*/block/sd*' ) # phy not port so we can get the sas address
  for block in block_list:
    block_parts = block.split( '/' )
    phy = '%s/sas_phy/%s' % ( '/'.join( block_parts[ 0:7 ] ), block_parts[6] )

    port = SASPort( open( '%s/sas_address' % phy, 'r' ).read().strip(), block_parts[-3], block_parts[6].split( ':' )[-1], None )

    ports[ port ] = block_parts[-1]

  return ports


##### SCSI
class SCSIPort( Port ):
  def __init__( self, host, port, *args, **kwargs  ):
    super( SCSIPort, self ).__init__( *args, **kwargs )
    self.port = port
    self.host = host

  def __getattr__( self, name ):
    if name == 'location':
      return 'SCSI %s:%s' % ( self.host, self.port )

    if name == 'type':
      return 'SCSI'

    raise AttributeError( name )

  def __hash__( self ):
    return ( 'SCSI %s %s' % ( self.host, self.port ) ).__hash__()


def getSCSIPorts():
  ports = {}

  block_list = glob.glob( '/sys/class/scsi_host/host*/device/target*/*/block/sd*' )
  for block in block_list:
    block_parts = block.split( '/' )
    ( host, _, port, _ ) = block_parts[7].split( ':' )
    port = SCSIPort( host, port )

    ports[ port ] = block_parts[-1]

  return ports


#### Drive Manager
class DriveManager( object ):
  def __init__( self ):
    super( DriveManager, self ).__init__()
    self.rescan()

  def __getattr__( self, name ):
    if name == 'port_list':
      tmp = list( self._port_list ) # make a copy
      tmp.sort()
      return tmp

    if name == 'drive_list':
      tmp = list( self._drive_list ) # make a copy
      tmp.sort()
      return tmp

    if name == 'unknown_list':
      tmp = list( self._unknown_list ) # make a copy
      tmp.sort()
      return tmp

    if name == 'port_map':
      tmp = {}
      for port in self.port_list:
        tmp[ port.location ] = port.drive
      return tmp

    if name == 'drive_map':
      tmp = {}
      for drive in self.drive_list:
        tmp[ '%s' % drive.libdrive_name ] = drive.port
      return tmp

    if name == 'devpath_map':
      tmp = {}
      for drive in self.drive_list:
        tmp[ drive.devpath ] = drive
      return tmp

    raise AttributeError( name )

  def rescan( self ):
    self._port_list = []
    self._drive_list = []
    self._unknown_list = []

    if os.path.isdir( '/vmfs' ): # we are running on esx

      if not os.path.isfile( '/sbin/esxcli' ) or not os.access( '/sbin/esxcli', os.X_OK ):
        raise Exception( 'Unsupported version of ESX or /sbin/esxcli not found.' )
      """
      port_list = getATAPorts_ESX()
      if port_list:
        for port in port_list:
          block = port_list[ port ]
          self._port_list.append( port )
          if block:
            self._drive_list.append( Drive( port, block, block, '/dev/%s' % block ) )
      """
      port_list = get3WareSlots_ESX()
      if port_list:
        for port in port_list:
          ( block, libdrive ) = port_list[ port ]
          self._port_list.append( port )
          if block:
            self._drive_list.append( Drive( port, libdrive, block, '/dev/%s' % libdrive ) )

      port_list = getMegaRAIDPorts_ESX()
      if port_list:
        for port in port_list:
          ( block, libdrive ) = port_list[ port ]
          self._port_list.append( port )
          if block:
            self._drive_list.append( Drive( port, libdrive, block, libdrive ) )

      self._unknown_list = [] # TODO!!!

    else: # regular linux host
      # NOTE: this list is in order of more specific to least, the last one should catch all, but might not be the best fit
      block_list = []
      port_list = getIDEPorts()
      if port_list:
        for port in port_list:
          block = port_list[ port ]
          self._port_list.append( port )
          if block and block not in block_list:
            block_list.append( block )
            self._drive_list.append( Drive( port, block, block, '/dev/%s' % block ) )

      port_list = getATAPorts()
      if port_list:
        for port in port_list:
          block = port_list[ port ]
          self._port_list.append( port )
          if block and block not in block_list:
            block_list.append( block )
            self._drive_list.append( Drive( port, block, block, '/dev/%s' % block ) )

      port_list = get3WareSlots()
      if port_list:
        for port in port_list:
          ( block, libdrive ) = port_list[ port ]
          self._port_list.append( port )
          if libdrive:
            if block is not None and block not in block_list:
              block_list.append( block )
            self._drive_list.append( Drive( port, libdrive, block, '/dev/%s' % libdrive ) )

      port_list = getMegaRAIDPorts()
      if port_list:
        for port in port_list:
          ( block, libdrive ) = port_list[ port ]
          self._port_list.append( port )
          if libdrive:
            if block is not None and block not in block_list:
              block_list.append( block )
            self._drive_list.append( Drive( port, libdrive, block, libdrive ) )

      enclosure_list = getSASEnclosureList()
      for enclosure in enclosure_list:
        port_list = getSASEnclosurePorts( enclosure, enclosure_list[enclosure] )
        for port in port_list:
          block = port_list[ port ]
          self._port_list.append( port )
          if block and block not in block_list:
            block_list.append( block )
            self._drive_list.append( Drive( port, block, block, '/dev/%s' % block ) )

      port_list = getSASDirectPorts()
      for port in port_list:
        block = port_list[ port ]
        self._port_list.append( port )
        if block and block not in block_list:
          block_list.append( block )
          self._drive_list.append( Drive( port, block, block, '/dev/%s' % block ) )

      port_list = getSCSIPorts()
      for port in port_list:
        block = port_list[ port ]
        self._port_list.append( port )
        if block and block not in block_list:
          block_list.append( block )
          self._drive_list.append( Drive( port, block, block, '/dev/%s' % block ) )


      known_drives = [ i.split( '/' )[-1] for i in self.drive_map.keys() ]
      all_drives = [ i for i in [ i.split( '/' )[-1] for i in glob.glob( '/sys/class/block/*' ) ] if not ( re.match( '(loop)|(md)|(sr)|(sg)|(dm)', i ) or re.search( '[0-9]$', i ) ) ]
      self._unknown_list = list( set( all_drives ) - set( known_drives ) )