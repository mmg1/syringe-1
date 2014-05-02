import ptypes,headers
from ptypes import ptype,pstruct,pbinary,dyn,parray,bitmap
from __base__ import *
import array

## per symbol relocations
class IMAGE_REL_I386(ptypes.pint.enum, uint16):
    _values_ = [
        ('ABSOLUTE', 0x0000),
        ('DIR16', 0x0001),
        ('REL16', 0x0002),
        ('DIR32', 0x0006),
        ('DIR32NB', 0x0007),
        ('SEG12', 0x0009),
        ('SECTION', 0x000A),
        ('SECREL', 0x000B),
        ('TOKEN', 0x000C),
        ('SECREL7', 0x000D),
        ('REL32', 0x0014)
    ]

class Relocation(pstruct.type):
    _fields_ = [
        (addr_t, 'VirtualAddress'),
        (uint32, 'SymbolTableIndex'),
        (IMAGE_REL_I386, 'Type')
    ]

    def summary(self):
        fields = [('VirtualAddress', lambda v: '%x'% v), ('SymbolTableIndex', int), ('Type', str)]
        res = ', '.join(['%s=%s'% (k,t(self[k])) for k,t in fields])
        return '{%s}'% res

    def relocate(self, data, symboltable, namespace):
        '''
        data = a string
        symboltable = an array of symbols
        namespace = a dict for looking up symbol and segment values by name
        '''
        currentsection = self.getparent(headers.SectionTable)
        sectionarray = currentsection.parent
        currentsectionname = currentsection['Name'].str()
        symbol = symboltable[self['SymbolTableIndex'].int()]

        # figure out the section name our address points into
        symbolsectionnumber,targetsectionname = symbol['SectionNumber'].num(),None
        if symbolsectionnumber is not None:
            targetsection = currentsection.parent[symbolsectionnumber]
            targetsectionname = targetsection['Name'].str()
        
        data = array.array('c',data)
        return self.__relocate(data, symbol, sectionarray, currentsectionname, targetsectionname, namespace).tostring()

    def __relocate(self, data, symbol, sectionarray, currentsectionname, targetsectionname, namespace):
        relocationva,relocationtype = self['VirtualAddress'].int(),self['Type'].num()
        name = symbol['Name'].str()
        storageclass,value = symbol['StorageClass'].num(), namespace[name]

        if value is None:
            raise ValueError('Attempted relocation for an undefined symbol `%s\'.'% name)

        result = bitmap.new(0,0)
        generator = ( bitmap.new(ord(x),8) for x in data[relocationva:relocationva+4] )
        for x in generator:
            result = bitmap.insert(result, x)
        result = result[0]

        currentva = relocationva + 4

        if targetsectionname is None:       # externally defined
            result = value

        elif relocationtype == 0:
            pass

        # XXX: will these relocations work?
        elif relocationtype == 6:                                           # 32-bit VA
            result = (value+result)
#            print '>',name,hex(result),targetsectionname,hex(namespace[targetsectionname])

        elif relocationtype == 0x14:                                        # 32-bit relative displacement
            result = (value+result+4) - (currentva)
            raise NotImplementedError(relocationtype)
        elif relocationtype == 7:                                           # use real virtual address (???)
            result = value
        elif relocationtype in [0xA, 0xB]:                                  # [section index, offset from section]
            raise NotImplementedError(relocationtype)
        else:
            raise NotImplementedError(relocationtype)

        result,serialized = bitmap.new(result, 32),array.array('c','')
        while result[1] > 0:
            result,value = bitmap.consume(result, 8)
            serialized.append(chr(value))
        assert len(serialized) == 4

        data[relocationva:relocationva+len(serialized)] = serialized
        return data

## per data directory relocations
class BaseRelocationEntry(pbinary.struct):
    _fields_ = [
        (4, 'Type'),
        (12, 'Offset'),
    ]
BaseRelocationEntry = pbinary.new(BaseRelocationEntry, byteorder=pbinary.littleendian)

class BaseRelocationArray(parray.type):
    _object_ = BaseRelocationEntry

class BaseRelocationBlock(ptype.block):
    def getRelocations(self):
        return self.cast(BaseRelocationArray, length=self.length/2)

class IMAGE_BASERELOC_DIRECTORY_ENTRY(pstruct.type):
    _fields_ = [
        (addr_t, 'Page RVA'),
        (uint32, 'Block Size'),
#        (lambda s: dyn.clone(BaseRelocationArray, length=(int(s['Block Size'].load())-8)/2), 'Relocations'),   # XXX: this is too slow, heh...
#        (lambda s: dyn.block(int(s['Block Size'].load())-8), 'Relocations')
        (lambda s: dyn.clone(BaseRelocationBlock, length=s['Block Size'].l.int()-8), 'Relocations'),
    ]

    def fetchrelocations(self):
        block = self['Relocations'].serialize()
        #block = self.newelement(dyn.block(int(self['Block Size'])), 'Relocations', self.getoffset()+8).load().serialize()
        relocations = array.array('H')
        relocations.fromstring(block)
        return [((v&0xf000)/0x1000, v&0x0fff) for v in relocations]

    def getrelocations(self, section):
        pageoffset = self['Page RVA'].num() - section['VirtualAddress'].num()
        assert pageoffset >= 0 and pageoffset < section.getloadedsize()

        for type,offset in self.fetchrelocations():
            if type == 0:
                continue
            o = pageoffset + offset
            yield type,o
        return

# yeah i really made this an object
class relocationtype(object):
    length = 0
    def read(self, string, offset):
        value = reversed( string[offset : offset+self.length] )
        result = reduce(lambda total,x: total*256 + ord(x), value, 0)
        return result

    def write(self, address, sectiondelta):
        raise NotImplementedError

    def _write(self, value):
        res = bitmap.new( value, self.length*8 )
        string = ''
        while res[1] > 0:
            res,value = bitmap.consume(res, 8)
            string += chr(value)
        return string

if False:       # deprecated because we would like to be able to separate segments from one another
    class relocation_1(relocationtype):
        length = 2
        def write(self, address, sectiondelta):
            value = address + (sectiondelta & 0xffff0000) / 0x10000
            return super(relocation_1, self)._write(value)

    class relocation_2(relocationtype):
        length = 2
        def write(self, address, sectiondelta):
            value = address + (sectiondelta & 0x0000ffff)
            return super(relocation_2, self)._write(value)

    class relocation_3(relocationtype):
        length = 4
        def write(self, address, sectiondelta):
            value = (address + sectiondelta) & 0xffffffff
            return super(relocation_3, self)._write(value)

    class relocation_10(relocationtype):
        length = 8
        def write(self, address, sectiondelta):
            value = address + (sectiondelta & 0xffffffffffffffff)
            return super(relocation_10, self)._write(value)

class IMAGE_BASERELOC_DIRECTORY(parray.terminated):
    _object_ = IMAGE_BASERELOC_DIRECTORY_ENTRY
    currentsize = 0
    maxsize = 0

    def isTerminator(self, v):
        self.currentsize += v.size()
        if self.currentsize < self.maxsize:
            return False
        return True

    def getbysection(self, section):
        return ( entry for entry in self if section.containsaddress(entry['Page RVA'].num()) )

    def relocate(self, data, section, namespace):
        assert data.__class__ is array.array, 'data argument must be formed as an array'

        sectionname = section['Name'].str()
        imagebase = self.getparent(headers.NtHeader)['OptionalHeader']['ImageBase'].num()

        sectionarray = section.parent
        sectionvaLookup = dict( ((s['Name'].str(),s['VirtualAddress'].num()) for s in sectionarray) )

        # relocation type 3
        t = relocationtype()
        t.length = 4
        t.write = lambda o, b: t._write(o+b)

        for entry in self.getbysection(section):
            for type,offset in entry.getrelocations(section):
                if type != 3:
                    raise NotImplementedError("Relocations other than type 3 aren't implemented because I couldn't find any to test with")
                currentva = sectionvaLookup[sectionname]+offset

                targetrva = t.read(data, offset)
                targetva = targetrva-imagebase

                try:
                    targetsection = sectionarray.getsectionbyaddress(targetrva-imagebase)

                except KeyError:
                    currentrva = imagebase+currentva
                    print "Relocation target at %x to %x lands outside section space"% (currentrva, targetrva)

                    # XXX: is it possible to hack support for relocations to the
                    #      'mz' header into this? that only fixes that case...but why else would you legitimately need something outside a section?
                    continue

                targetsectionname = targetsection['Name'].str()
                targetoffset = targetva - sectionvaLookup[targetsectionname]

#                relo = t.write(targetva, imagebase)
                relo = t.write(targetoffset, namespace[targetsectionname])
                data[offset:offset+len(relo)] = array.array('c',relo)
            continue

        return data
