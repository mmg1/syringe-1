import ptypes
from ptypes import pstruct,parray,ptype
from ptypes import dyn,pint,pstr
from ptypes.pint import uint8_t,uint16_t,uint32_t,int16_t
from ptypes import utils

## primitive types
class ULONG(uint32_t): pass
class USHORT(uint16_t): pass

class OFFSET(int16_t): pass
class SECT(pint.penum, ULONG):
    _fields_ = [
        ('DIFSECT', 0xfffffffc),
        ('FATSECT', 0xfffffffd),
        ('ENDOFCHAIN', 0xfffffffe),
        ('FREESECT', 0xffffffff)
    ]
class FSINDEX(ULONG): pass
class FSOFFSET(USHORT): pass
class DFSIGNATURE(ULONG): pass

class BYTE(uint8_t): pass
class WORD(uint16_t): pass
class DWORD(uint32_t): pass

class DFPROPTYPE(WORD): pass
class SID(ULONG): pass

class CLSID(dyn.block(16)): pass
class GUID(CLSID): pass

class TIME_T(pstruct.type):
    _fields_ = [(DWORD, 'dwLowDateTime'), (DWORD, 'dwHighDateTime')]
FILE_TIME = TIME_T

class WCHAR(pstr.wchar_t): pass

## file header
class StructuredStorageHeader(pstruct.type):
    _fields_ = [
        (dyn.array(BYTE, 8), '_abSig'),
        (CLSID, '_clid'),
        (USHORT, '_uMinorVersion'),
        (USHORT, '_uDllVersion'),
        (USHORT, '_uByteOrder'),

        (USHORT, '_uSectorShift'),
        (USHORT, '_uMiniSectorShift'),

        (USHORT, '_usReserved'),
        (ULONG, '_ulReserved1'),
        (ULONG, '_ulReserved2'),

        (FSINDEX, '_csectFat'),     # number of sectors for the fat
        (SECT, '_sectDirStart'),    # directory sid
        (DFSIGNATURE, '_signature'),

        (ULONG, '_ulMiniSectorCutoff'),
        (SECT, '_sectMiniFatStart'),
        (FSINDEX, '_csectMiniFat'),

        (SECT, '_sectDifStart'),    # contains rest of FAT
        (FSINDEX, '_csectDif'),

        (dyn.array(SECT, 109), '_sectFat') # FAT
    ]

    def getminisectorsize(self):
        return 1 << int(self['_uMiniSectorShift'])
    def getsectorsize():
        return 1 << int(self['_uSectorShift'])

    def getsector(self, n):
        if n in SECT.enumerations(): # enumeration
            raise ValueError('Invalid sector number %d'% n)
            
        size = 1<<int(self['_uSectorShift'])
        ofs = self.size() + (n * size)
        return self.newelement(dyn.block(size), 'Sector[%d]'% n, ofs)

    def getallocationtable(self, n):
        ''' Gets an actual allocation table given a sector '''
        # XXX: check that n is not End-of-Chain, or any of our other SECT.consants
        assert n not in SECT.enumerations()

        sector = self.getsector(n)
        count = sector.load().size() / SECT.length
        return self.newelement(dyn.array(SECT, count), 'AllocationTable[%d]'% n, sector.getoffset())

    def getdirectorytable(self, n):
        assert n not in SECT.enumerations()

        sector = self.getsector(n)
        count = sector.load().size() / StructuredStorageDirectoryEntry_size
        return self.newelement(dyn.clone(DirectoryTable, length=count), 'DirectoryTable[%d]'% n, sector.getoffset())

class structuredStorageFile(object):
    dif = fat = minifat = list

    def __init__(self, structuredstorageheader):
        o = structuredstorageheader
        self.object = o.load()         # we are now in bed with this object....and i don't care

    def getfatchain(self, n):   #getglucose?
        result = []
        while True:
            x = self.fat[n]
            if x == x.ENDOFCHAIN:
                break

            if x in SECT.enumerations():
                raise NotImplementedError( repr(x) )

            result.append(x)
            n += 1
            continue
        return result

    def getminifatchain(self, n):
        result = []
        while True:
            x = self.minifat[n]
            if x == x.ENDOFCHAIN:
                break

            if x in SECT.enumerations():
                raise NotImplementedError( repr(x) )

            result.append(x)
            n += 1
            continue
        return result

    def getdif(self):
        o = self.object
        dif = [ s for s in o['_sectFat'] ] + self.getlinkeddif()
        return [x for i,x in zip(range(int(o['_csectFat'])), dif)]

    def getlinkeddif(self):
        o = self.object
        currentSector = o['_sectDifStart']
        dif = []
        while int(currentSector) != currentSector.ENDOFCHAIN:
            raise NotImplementedError
            s = o.getallocationtable(int(currentSector))
            nextSector = s.load()[-1]
            dif.append(currentSector)
            currentSector = nextSector
        return dif

    def getfat(self, dif):
        o = self.object
        result = []
        for s in dif:
            data = o.getallocationtable(s)
            result.extend(data.load())
        return result
        
    def getminifat(self):
        o = self.object
        sectors = [ o['_sectMiniFatStart'] ]    # XXX: does this really point to the sector? or the stream?

        result = []
        for x in sectors:
            result.extend( o.getallocationtable(int(x)).load() )
        return result

    def getdirectory(self):
        o = self.object
        chain = self.getfatchain( int(o['_sectDirStart']) )
        sectors = [ o.getdirectorytable(int(x)) for x in chain ]

        # flatten
        result = DirectoryTable()
        for x in sectors:
            result.extend(x.load())
        return result

    def getminidirectory(self):
        root = self.directory[0]
        chain = self.getfatchain( int(root['_sectStart']) )
        result = [ self.object.getdirectorytable(int(x)) for x in chain ]
        
        x = DirectoryTable()
        for t in result:
            x.extend(t.load())
        return x

    def extractfatchain(self, chain):
        o = self.object
        return ''.join([ o.getsector(int(x)).load().serialize() for x in chain ])

    def extractminifatchain(self, chain):
        raise NotImplementedError
        o = self.object
        return ''.join([ o.getsector(int(x)).load().serialize() for x in chain ])

## directory
class STGTY(pint.penum, BYTE):
    _fields_ = [
        ('INVALID', 0),
        ('STORAGE', 1),
        ('STREAM', 2),
        ('LOCKBYTES', 3),
        ('PROPERTY', 4),
        ('ROOT', 5)
    ]

class DECOLOR(pint.penum, BYTE):
    _fields_ = [('RED', 0), ('BLACK', 1)]

class StructuredStorageDirectoryEntry(pstruct.type):
    _fields_ = [
        (pstr.new(32, pstr.wstring), '_ab'),
        (WORD, '_cb'),
        (STGTY, '_mse'),
        (DECOLOR, '_bflags'),
        (SID, '_sidLeftSib'),
        (SID, '_sidRightSib'),
        (SID, '_sidChild'),
        (GUID, '_clsId'),
        (DWORD, '_dwUserFlags'),
        (dyn.array(TIME_T,2), '_time'),
        (SECT, '_sectStart'),           # Fat start
        (ULONG, '_ulSize'),             # stream size
        (DFPROPTYPE, '_dptPropType'),
        (lambda self: dyn.block(128 - self.size()), '__padding__')
    ]
    
StructuredStorageDirectoryEntry_size = StructuredStorageDirectoryEntry().load().size()

class DirectoryTable(parray.type):
    _object_ = StructuredStorageDirectoryEntry

    def names(self):
        return [ x['_ab'].get() for x in self ]

    def getentry(self, name):
        for x in self:
            if x['_ab'].get() == name:
                return x
            continue
        raise KeyError(name)

def open(filename):
    ssh = StructuredStorageHeader()
    ssh.source = ptypes.provider.file(filename)
    return structuredStorageFile(ssh)

if __name__ == '__main__':
    import cdoc; reload(cdoc)
    import ptypes
    from ptypes import utils
#    filename = 'blocguadalupe.doc'
    filename = 'org.fpx'
    self = cdoc.open(filename)

    self = cdoc.StructuredStorageHeader()
    self.source = ptypes.provider.file(filename)
    self = cdoc.structuredStorageFile(self)

    self.dif = self.getdif()
    self.fat = self.getfat( map(int, self.dif) )
    self.minifat = self.getminifat()
    self.directory = self.getdirectory()
    self.minidirectory = self.getminidirectory()

#    print [ x.get() for x in self.dif]
#    print [ x.get() for x in self.fat]
#    print [ x.get() for x in self.minifat]

    print self.getdirectory().names()

    print self.object.getminisectorsize()
    minidirectory = self.getminidirectory()
    for x in minidirectory.names():
        d = minidirectory.getentry(x)
        print repr(x), repr(d['_sectStart']), repr(d['_ulSize'])

    # figure out how to ge tthe stream representing our minisector shit
    ministream = self.

    if False:
        # here's our minifat
        print repr(self.object['_sectMiniFatStart']), self.object['_csectMiniFat']
        # or directory
        root = self.directory[0]
        print repr(root['_sectStart'])

        # is it a slot available in our fat?
        print [ x.get() for x in self.fat[:8]]
        print [ x.get() for x in self.minifat[:8]]

        # here is what we know
        #print data from each sector

#    print self.directory.names()
#    print self.minidirectory.names()

    ## every file
#    for n in self.getdirectoryentry(1).load():
#        print repr(n['_ab'].get())
#        print n['_mse']
#        print 'sector', n['_sectStart']
#        print 'size', n['_ulSize'], self['_ulMiniSectorCutoff']
#
#        start = int(n['_sectStart'])
#        size = int(n['_ulSize'])
#        chain = getchain(table[ start: ])
#
#        data = self.getdata(chain)
#        print utils.hexdump(data)

