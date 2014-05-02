import logging,itertools
import ptypes
from ptypes import pstruct,parray,dyn,ptype,pstr
from __base__ import *

class IMAGE_SYM(ptypes.pint.enum, uint16):
    _values_ = [
        ('UNDEFINED', 0),
        ('ABSOLUTE', 0xffff),   #-1),
        ('DEBUG', 0xfffe)       #-2)
    ]

    def getSection(self):
        '''Returns the physical section number index if defined, otherwise None'''
        n = self.num()
        if n in (0, 0xffff, 0xfffe, -1, -2):
            return None
        return n - 1

class IMAGE_SYM_TYPE(ptypes.pint.enum, uint16):
    _values_ = [
        ('NULL', 0),
        ('VOID', 1),
        ('CHAR', 2),
        ('SHORT', 3),
        ('INT', 4),
        ('LONG', 5),
        ('FLOAT', 6),
        ('DOUBLE', 7),
        ('STRUCT', 8),
        ('UNION', 9),
        ('ENUM', 10),
        ('MOE', 11),
        ('BYTE', 12),
        ('WORD', 13),
        ('UINT', 14),
        ('DWORD', 15),
        ('FUNCTION', 0x20),
    ]

class IMAGE_SYM_DTYPE(ptypes.pint.enum, uint16):
    _values_ = [
        ('NULL', 0),
        ('POINTER', 1),
        ('FUNCTION', 2),
        ('ARRAY', 3)
    ]

class IMAGE_SYM_CLASS(ptypes.pint.enum, uint8):
    _values_ = [
        ('END_OF_FUNCTION', 0xff),
        ('NULL', 0),
        ('AUTOMATIC', 1),
        ('EXTERNAL', 2),
        ('STATIC', 3),
        ('REGISTER', 4),
        ('EXTERNAL_DEF', 5),
        ('LABEL', 6),
        ('UNDEFINED_LABEL', 7),
        ('MEMBER_OF_STRUCT', 8),
        ('ARGUMENT', 9),
        ('STRUCT_TAG', 10),
        ('MEMBER_OF_UNION', 11),
        ('UNION_TAG', 12),
        ('TYPE_DEFINITION', 13),
        ('UNDEFINED_STATIC', 14),
        ('ENUM_TAG', 15),
        ('MEMBER_OF_ENUM', 16),
        ('REGISTER_PARAM', 17),
        ('BIT_FIELD', 18),
        ('BLOCK', 100),
        ('FUNCTION', 101),
        ('END_OF_STRUCT', 102),
        ('FILE', 103),
        ('SECTION', 104),
        ('WEAK_EXTERNAL', 105),
        ('CLR_TOKEN', 106),
    ]

class ShortName(pstruct.type):
    _fields_ = [
        (dword, 'IsShort'),
        (off_t, 'Offset')
    ]

    def str(self):
        '''resolve the Name of the object utilizing the provided StringTable if necessary'''
        if self['IsShort'].num() != 0x00000000:
            return ptypes.utils.strdup( self.serialize(), terminator='\x00')
        stringtable = self.getparent(SymbolTableAndStringTable)
        return stringtable.extract( self['Offset'].num() )

    def get(self):
        return self.str()

    def set(self, string):
        if len(string) <= 8:
            data = string + '\x00'*(8-len(string))
            self.load(source=ptypes.provider.string(data), offset=0)
            return self

        stringtable = self.getparent(SymbolTableAndStringTable)
        self['IsShort'].set(0)
        ofs = stringtable.add(string)
        self['Offset'].set(ofs)
        return self

class Symbol(pstruct.type):
    _fields_ = [
        (ShortName, 'Name'),
        (uint32, 'Value'),
        (IMAGE_SYM, 'SectionNumber'),   ## XXX: TODO -> would be neat to go from symbol to the actual physical section number
        (IMAGE_SYM_TYPE, 'Type'),
        (IMAGE_SYM_CLASS, 'StorageClass'),
        (uint8, 'NumberOfAuxSymbols')
    ]

    def summary(self, **options):
        if self.initialized:
            name = self['Name'].str()
            value = self['Value'].num()
            sym_section = self['SectionNumber']
            sym_type = self['Type']
            sym_class = self['StorageClass']

            aux = AuxiliaryRecord.lookup(sym_class.num())
            return '"{}":0x{:x} Section:{} (Type:{}, Class:{}) Aux:{}[{:d}]'.format(name, value, sym_section.summary(), sym_type.summary(), sym_class.summary(), aux.typename(), self['NumberOfAuxSymbols'].num())
        return super(Symbol, self).summary()

    def repr(self):
        return self.summary()

    @property
    def auxiliary(self):
        argh = self.parent.value
        index = argh.index(self)+1
        return tuple(argh[index:index+self['NumberOfAuxSymbols'].num()])
    aux = auxiliary

class SymbolTable(parray.terminated):
    def _object_(self):
        if len(self.value) == 0:
            self.__auxiliary = []
        if len(self.__auxiliary) > 0:
            return self.__auxiliary.pop(0)
        return Symbol

    def isTerminator(self, value):
        if isinstance(value, Symbol):
            auxCount = value['NumberOfAuxSymbols'].num()
            auxSymbol = AuxiliaryRecord.lookup( value['StorageClass'].num() )
            self.__auxiliary.extend((auxSymbol for _ in range(auxCount)))
        return False

    def iterate(self):
        result = list(self.value)
        while len(result) > 0:
            sym = result.pop(0)
            assert isinstance(sym, Symbol)
            aux = [ result.pop(0) for t in range(sym['NumberOfAuxSymbols'].num()) ]
            yield sym,aux
        return

    def getsymbolandaux(self, symbol):
        '''Fetch Symbol and all its Auxiliary data'''
        index = self.value.index(symbol)
        return self.value[index : index+1 + symbol['NumberOfAuxSymbols'].num()]

    #def summary(self, **options):
    #    return ', '.join('"{}":({},{},{})'.format(s['Name'].str(),s['SectionNumber'].summary(),s['Type'].str(),s['StorageClass'].str()) for s,a in self.iterate())

    def details(self, **options):
        result = []
        for s,a in self.iterate():
            result.append(repr(s))
            if s['NumberOfAuxSymbols'].num() > 0:
                result.extend(ptypes.utils.indent('\n'.join(map(repr,a))).split('\n'))
        return '\n'.join(result)
        #return '\n'.join(repr(s) for s,a in self.iterate())

    def repr(self):
        return self.details()

    def properties(self):
        res = super(SymbolTable,self).properties()
        res['count'] = len(list(self.iterate()))
        return res

class AuxiliaryRecord(ptype.definition): cache = {}

@AuxiliaryRecord.define
class NullAuxiliaryRecord(pstruct.type):
    type = 0
    _fields_ = []

@AuxiliaryRecord.define
class FunctionDefinitionAuxiliaryRecord(pstruct.type):
    type = 2
    _fields_ = [
        (dword, 'TagIndex'),
        (uint32, 'TotalSize'),
        (off_t, 'PointerToLinenumber'),
        (off_t, 'PointerToNextFunction'),
        (word, 'Unused')
    ]

@AuxiliaryRecord.define
class FunctionBoundaryAuxiliaryRecord(pstruct.type):
    type = 101
    _fields_ = [
        (dword, 'Unused[0]'),
        (word, 'Linenumber'),
        (dyn.block(6), 'Unused[1]'),
        (off_t, 'PointerToNextFunction'),
        (word, 'Unused[2]')
    ]

@AuxiliaryRecord.define
class WeakExternalAuxiliaryRecord(pstruct.type):
    type = 105
    _fields_ = [
        (dword, 'TagIndex'),
        (dword, 'Characteristics'),
        (dyn.block(10), 'Unused')
    ]

@AuxiliaryRecord.define
class FileAuxiliaryRecord(pstruct.type):
    type = 103
    _fields_ = [
        #(dyn.block(18), 'File Name')
        (dyn.clone(pstr.string, length=18), 'File Name')
    ]

    def summary(self):
        return ptypes.utils.strdup(self['File Name'].str(), terminator='\x00')

@AuxiliaryRecord.define
class SectionAuxiliaryRecord(pstruct.type):
    type = 3
    _fields_ = [
        (uint32, 'Length'),
        (uint16, 'NumberOfRelocations'),
        (uint16, 'NumberOfLinenumbers'),
        (dword, 'CheckSum'),
        (word, 'Number'),
        (IMAGE_COMDAT_SELECT, 'Selection'),
        (dyn.block(3), 'Unused')
    ]

@AuxiliaryRecord.define
class CLRAuxiliaryRecord(pstruct.type):
    type = 106
    _fields_ = [
        (byte, 'bAuxType'),
        (byte, 'bReserved'),
        (dword, 'SymbolTableIndex'),
        (dyn.block(12), 'Reserved')
    ]

# XXX: the following code is a hack that should be rewritten

class StringTable(pstruct.type):
    def fetchData(self):
        if not self['Size'].initialized:    # XXX: this doesn't seem right
            self['Size'].load()
        count = self['Size'].num()
        cls = dyn.block(count - 4)
        return self.new(cls, __name__=cls.__name__)

    def initialized(cls, value):
        def fn(self):
            res = self.new(cls, __name__=cls.__name__, offset=self.getoffset() + self.size())
            res.set(value)
            return res
        return fn

    _fields_ = [
        (initialized(uint32, 4), 'Size'),
        (fetchData, 'Data')
    ]

    if False:
        def get(self, offset):
            import logging
            warnings.warn('%s.get(offset) is deprecated for %s.extract(offset)'%(self.__class__.__name__,self.__class__.__name__), DeprecationWarning, stacklevel=2)
            return self.extract(offset)

    def extract(self, offset):
        '''return the string associated with a particular offset'''
        string = self.serialize()
        string = string[offset:]
        return ptypes.utils.strdup(string, terminator='\x00')

    def add(self, string):
        '''appends a string to string table, returns offset'''
        ofs, data = self.size(), self['Data']
        data.value = data.serialize() + string + '\x00'
        data.length = len(data.value)
        self['Size'].set( data.size() + self['Size'].size() )
        return ofs

class SymbolTableAndStringTable(pstruct.type):
    def __Symbols(self):
        res = self.getparent(headers.NtHeader.FileHeader)
        return dyn.clone(SymbolTable, length=res['NumberOfSymbols'].num())

    _fields_ = [
        (__Symbols, 'Symbols'),
        (StringTable, 'Strings'),
    ]

    # XXX: the following code is possible garbage. rewrite this when able...

    ## this is all done in O(n) time...   FIXME: pull this functionality into an object that manages symbols instead of using ptypes
    def names(self):
        return [s['Name'].str() for s,_ in self['Symbols'].iterate()]

    def walk(self):
        for s,_ in self['Symbols'].iterate():
            yield s
        return

    def getSymbol(self, name=None):
        if not self.initialized:
            self.load()
        if name:
            return self.fetch(name)[0]
        return [s for s,a in self['Symbols'].iterate()]

    def fetch(self, name):
        for s,a in self['Symbols'].iterate():
            if s['Name'].str() == name:
                return tuple(x for x in itertools.chain([x],a))
            continue
        raise KeyError('symbol %s not found'% name)

    def getaux(self, name):
        res = self.fetch(name)
        if len(res) > 1:
            return tuple(res[1:])
        return ()

    def assign(self, name, value):
        try:
            sym = self.fetch(name)[0]
            sym['Value'].set(value)
            sym['SectionNumber'].set(-1)    # absolute address

        except KeyError:
            self.add(name)
            return self.assign(name, value)
        return

    def add(self, name):
        logging.info('pecoff.symbols.SymbolTablesAndString : adding new symbol %s'% name)
        if ptype.istype(name):
            name = name.serialize()
        else:
            name = str(name)

        symbols = self['Symbols']

        v = symbols.new(Symbol, __name__=len(self.value), offset=self.getoffset() + self.size())
        v.source = None
        v.alloc()
        v['Name'].set(name)
        v['SectionNumber'].set(0)      # XXX: set as undefined since we aren't gonna be placing it anywhere
        symbols.append(v)

import headers  # XXX: recursive
