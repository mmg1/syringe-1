'''Provides a dynamic kind of feel'''
from . import ptype,parray,pstruct,config,error,utils,provider
Config = config.defaults
__all__ = 'block,blockarray,align,array,clone,pointer,rpointer,opointer,union'.split(',')

## FIXME: might want to raise an exception or warning if we have too large of a block
def block(size, **kwds):
    """Returns a ptype.block type with the specified ``size``"""
    if size.__class__ not in (int,long):
        t = ptype.block(length=size)
        raise error.UserError(t, 'block', message='Argument size must be integral : %s -> %s'% (size.__class__, repr(size)))

    if size < 0:
        t = ptype.block(length=size)
        Config.log.error('block : %s : Invalid argument size=%d cannot be < 0. Defaulting to 0'% (t.typename(), size))
        size = 0

    def classname(self):
        return 'dynamic.block(%d)'% self.blocksize()
    kwds.setdefault('classname', classname)
    kwds.setdefault('__module__', 'ptypes.dynamic')
    kwds.setdefault('__name__', 'block')
    return clone(ptype.block, length=size, **kwds)

def blockarray(type, size, **kwds):
    """Returns a parray.block with the specified ``size`` and ``type``"""
    if size.__class__ not in (int,long):
        t = parray.block(_object_=type)
        raise error.UserError(t, 'blockarray', message='Argument size must be integral : %s -> %s'% (size.__class__, repr(size)))

    if size < 0:
        t = parray.block(_object_=type)
        Config.log.error('blockarray : %s : Invalid argument size=%d cannot be < 0. Defaulting to 0'% (t.typename(),size))
        size = 0
 
    class blockarray(parray.block):
        _object_ = type
        def blocksize(self):
            return size

        def classname(self):
            t = type.typename() if ptype.istype(type) else type.__name__
            return 'dynamic.blockarray(%s,%d)'%(t, self.blocksize())
    blockarray.__module__ = 'ptypes.dynamic'
    blockarray.__name__ = 'blockarray'
    blockarray.__getinitargs__ = lambda s: (type,size)
    return blockarray

def align(size, **kwds):
    '''return a block that will align a structure to a multiple of the specified number of bytes'''
    if size.__class__ not in (int,long):
        t = ptype.type(length=0)
        raise error.UserError(t, 'align', message='Argument size must be integral : %s -> %s'% (size.__class__, repr(size)))

    # methods to get assigned
    def repr(self, **options): return self.summary(**options)
    def blocksize(self):
        p = self.parent
        if p is None:
            return 0
        i = p.value.index(self) # XXX: why does this call __repr__?
        offset = p.getoffset()+sum(n.blocksize() for n in p.value[:i])
        return (-offset) & (size-1)
    getinitargs = lambda s: (type,kwds)

    # if alignment is undefined
    if kwds.get('undefined', False):
        class result(ptype.undefined):
            def classname(self): return 'dynamic.undefined(%d, size=%d)'% (size,self.blocksize())
        result.repr,result.blocksize,result.__getinitargs__ = repr,blocksize,getinitargs
        result.__module__,result.__name__ = 'ptypes.dynamic','undefined'
        return result

    # otherwise, padding
    class result(ptype.block):
        initializedQ = lambda self: self.value is not None
        def classname(self): return 'dynamic.align(%d, size=%d)'% (size,self.blocksize())
    result.repr,result.blocksize,result.__getinitargs__ = repr,blocksize,getinitargs
    result.__module__,result.__name__ = 'ptypes.dynamic','align'
    return result

## FIXME: might want to raise an exception or warning if we have too large of an array
def array(type, count, **kwds):
    '''
    returns an array of the specified length containing elements of the specified type
    '''
    count = int(count)
    if count.__class__ not in (int,long):
        t = parray.type(_object_=type,length=count)
        raise error.UserError(t, 'array', message='Argument count must be integral : %s -> %s'% (count.__class__, repr(count)))

    if count < 0:
        t = parray.type(_object_=type,length=count)
        Config.log.error('dynamic.array : %s : Invalid argument count=%d cannot be < 0. Defaulting to 0.'%( t.typename(), count))
        count = 0

    if Config.parray.max_count > 0 and count > Config.parray.max_count:
        t = parray.type(_object_=type,length=count)
        if Config.parray.break_on_max_count:
            Config.log.fatal('dynamic.array : %s : Requested argument count=%d is larger than configuration max_count=%d.'%( t.typename(), count, Config.parray.max_count))
            raise error.UserError(t, 'array', message='Requested array count=%d is larger than configuration max_count=%d'%(count, Config.parray.max_count))
        Config.log.warn('dynamic.array : %s : Requested argument count=%d is larger than configuration max_count=%d.'%( t.typename(), count, Config.parray.max_count))

    def classname(self):
        obj = type
        t = obj.typename() if ptype.istype(obj) else obj.__name__
        return 'dynamic.array(%s,%s)'%(t, str(self.length))

    kwds.setdefault('classname', classname)
    kwds.setdefault('length', count)
    kwds.setdefault('_object_', type)
    kwds.setdefault('__module__', 'ptypes.dynamic')
    kwds.setdefault('__name__', 'array')
    return ptype.clone(parray.type, **kwds)

def clone(cls, **newattrs):
    '''
    Will clone a class, and set its attributes to **newattrs
    Intended to aid with single-line coding.
    '''
    return ptype.clone(cls, **newattrs)

class _union_generic(ptype.container):
    def __init__(self, *args, **kwds):
        super(_union_generic,self).__init__(*args, **kwds)
        self.__fastindex = {}

    def append(self, object):
        """Add an element as part of a union. Return it's index."""
        name = object.name()

        current = len(self.object)
        self.object.append(object)
        
        self.__fastindex[name.lower()] = current
        return current

    def keys(self):
        return [name for type,name in self._fields_]

    def values(self):
        return list(self.object)

    def items(self):
        return [(k,v) for (_,k),v in zip(self._fields_,self.object)]

    def getindex(self, name):
        return self.__fastindex[name.lower()]

    def __getitem__(self, name):
        index = self.getindex(name)
        return self.object[index]

class union(_union_generic):
    """
    Provides a data structure with Union-like characteristics. If the root type
    isn't defined, it is assumed the first type in the union will be the root.

    The `.object` property contains a list of the instantiated types for each
    defined field. The `.value` property points to an instance of the `.root`
    property.

    i.e.
    class myunion(dynamic.union):
        _fields_ = [
            (structure1, 'a'),
            (structure2, 'b'),
            (structure3, 'c'),
        ]

    In this example, each field 'a', 'b', and 'c' begin at the same offset. Since
    a root object is not defined, it is determined by the size of the first
    field. If `structure2` or `structure3` is larger than `structure1`, then
    these fields will be left partially uninitialized when accessed.

    i.e.
    class myunion(dynamic.union)::
        root = block(256)
        _fields_ = [
            (dyn.array(uint16_t,64), 'a'),
            (dyn.array(uint8_t,64), 'b'),
        ]

    In this example, the union is backed by a `block(256)` object. This object
    will be used to decode the structures used by field 'a' and field 'b'.
    """
    root = None         # root type. determines block size.
    _fields_ = []       # aliases of root type that will act on the same data
    object = None       # objects associated with each alias
    value = None

    initializedQ = lambda self: self.value is not None and self.value.initialized
    def __choose_root(self, objects):
        """Return a ptype.block of a size that contain /objects/"""
        res = self.root
        if res is None:
            size = max(t().a.blocksize() for t in objects)
            self.root = res = clone(ptype.block, length=size)
        return res

    def __alloc_root(self, **attrs):
        t = self.__choose_root(t for t,n in self._fields_)
        self.value = self.new(t,offset=self.getoffset())
        return self.value.alloc(**attrs)

    def __alloc_objects(self, value):
        source = provider.proxy(value)      # each element will write into the offset occupied by value
        self.object = []
        for t,n in self._fields_:
            self.append(self.new(t, __name__=n, offset=0, source=source))
        return self

    def alloc(self, **attrs):
        value = self.__alloc_root(**attrs) if self.value is None else self.value
        self.__alloc_objects(value)
        return self

    def serialize(self):
        return self.value.serialize()

    def load(self, **attrs):
        value = self.__alloc_root(**attrs) if self.value is None else self.value
        self.__alloc_objects(value)
        _ = self.value.load()
        return self

    def deserialize_block(self, block):
        _ = self.value.deserialize_block(block)
        return self

    def properties(self):
        result = super(union,self).properties()
        if self.initializedQ():
            result['object'] = ['%s<%s>'%(v.name(),v.classname()) for v in self.object]
        else:
            result['object'] = ['%s<%s>'%(n,t.typename()) for t,n in self._fields_]
        return result

    def __getitem__(self, key):
        result = super(union,self).__getitem__(key)
        try:
            if not result.initializedQ():
                result.l
        except error.UserError, e:
            Config.log.warning("union.__getitem__ : %s : Ignoring exception %s"% (self.instance(), e))
        return result

    def details(self):
        if self.initializedQ():
            res = repr(self.serialize())
            root = self.value.classname()
        else:
            res = '???'
            root = self.__choose_root(t for t,n in self._fields_).typename()
        return '%s %s'%(root, res)

    def blocksize(self):
        return self.value.blocksize()
    def size(self):
        return self.value.size()
    def contains(self, offset):
        return super(ptype.container,self).contains(offset)

    def setoffset(self, ofs, recurse=False):
        if self.value is not None:
            self.value.setoffset(ofs, recurse=recurse)
        return super(ptype.container,self).setoffset(ofs, recurse=recurse)
    def getoffset(self, **_):
        return super(ptype.container,self).getoffset(**_)

union_t = union # alias

import pint
def pointer(target, type=None, **attrs):
    t = ptype.pointer_t._value_ if type is None else type
    def classname(self):
        return 'dynamic.pointer(%s)'% target.typename() if ptype.istype(target) else target.__name__
#    attrs.setdefault('classname', classname)
    return ptype.clone(ptype.pointer_t, _object_=target, _value_=t, **attrs)

def rpointer(target, object=lambda s: list(s.walk())[-1], type=None, **attrs):
    '''a pointer relative to a particular object'''
    t = ptype.pointer_t._value_ if type is None else type
    def classname(self):
        return 'dynamic.rpointer(%s, ...)'% target.typename() if ptype.istype(target) else target.__name__
#    attrs.setdefault('classname', classname)
    return ptype.clone(ptype.rpointer_t, _object_=target, _baseobject_=object, _value_=t, **attrs)

def opointer(target, calculate=lambda s: s.getoffset(), type=None, **attrs):
    '''a pointer relative to a particular offset'''
    t = ptype.pointer_t._value_ if type is None else type
    def classname(self):
        return 'dynamic.opointer(%s, ...)'% target.typename() if ptype.istype(target) else target.__name__
#    attrs.setdefault('classname', classname)
    return ptype.clone(ptype.opointer_t, _object_=target, _calculate_=calculate, _value_=t, **attrs)

if __name__ == '__main__':
    import ptype,parray,pstruct,parray,pint,provider
    import logging,config
    config.defaults.log.setLevel(logging.DEBUG)

    class Result(Exception): pass
    class Success(Result): pass
    class Failure(Result): pass

    TestCaseList = []
    def TestCase(fn):
        def harness(**kwds):
            name = fn.__name__
            try:
                res = fn(**kwds)
                raise Failure
            except Success,e:
                print '%s: %r'% (name,e)
                return True
            except Failure,e:
                print '%s: %r'% (name,e)
            except Exception,e:
                print '%s: %r : %r'% (name,Failure(), e)
            return False
        TestCaseList.append(harness)
        return fn

if __name__ == '__main__':
    import ptypes,zlib
    from ptypes import *
    from ptypes import config

    ptypes.setsource(ptypes.provider.string('A'*50000))

    string1='ABCD'  # bigendian
    string2='DCBA'  # littleendian

    s1 = 'the quick brown fox jumped over the lazy dog'
    s2 = s1.encode('zlib')

    @TestCase
    def test_dynamic_union_rootstatic():
        import dynamic,pint,parray
        class test(dynamic.union): 
            root = dynamic.array(pint.uint8_t,4)
            _fields_ = [
                (dynamic.block(4), 'block'),
                (pint.uint32_t, 'int'),
            ] 

        a = test(source=ptypes.provider.string('A'*4))
        a=a.l
        if a.value[0].int() != 0x41:
            raise Failure

        if a['block'].size() == 4 and a['int'].int() == 0x41414141:
            raise Success

    @TestCase
    def test_dynamic_alignment():
        import dynamic,pint,pstruct
        class test(pstruct.type):
            _fields_ = [
                (pint.uint32_t, 'u32'),
                (pint.uint8_t, 'u8'),
                (dynamic.align(4), 'alignment'),
                (pint.uint32_t, 'end'),
            ]

        a = test(source=ptypes.provider.string('A'*12))
        a=a.l
        if a.size() == 12:
            raise Success

    @TestCase
    def test_dynamic_pointer_bigendian():
        ptype.setbyteorder(config.byteorder.bigendian)

        s = ptype.provider.string(string1)
        p = dynamic.pointer(dynamic.block(0))
        x = p(source=s).l
        if x.d.getoffset() == 0x41424344 and x.serialize() == string1:
            raise Success

    @TestCase
    def test_dynamic_pointer_littleendian_1():
        ptype.setbyteorder(config.byteorder.littleendian)
        s = ptype.provider.string(string2)

        t = dynamic.pointer(dynamic.block(0))
        x = t(source=s).l
        if x.d.getoffset() == 0x41424344 and x.serialize() == string2:
            raise Success

    @TestCase
    def test_dynamic_pointer_littleendian_2():
        ptype.setbyteorder(config.byteorder.littleendian)
        string = '\x26\xf8\x1a\x77'
        s = ptype.provider.string(string)
        
        t = dynamic.pointer(dynamic.block(0))
        x = t(source=s).l
        if x.d.getoffset() == 0x771af826 and x.serialize() ==  string:
            raise Success

    @TestCase
    def test_dynamic_pointer_bigendian_deref():
        ptype.setbyteorder(config.byteorder.bigendian)

        s = ptype.provider.string('\x00\x00\x00\x04\x44\x43\x42\x41')
        t = dynamic.pointer(dynamic.block(4))
        x = t(source=s)
        if x.l.d.getoffset() == 4:
            raise Success

    @TestCase
    def test_dynamic_pointer_littleendian_deref():
        ptype.setbyteorder(config.byteorder.littleendian)

        s = ptype.provider.string('\x04\x00\x00\x00\x44\x43\x42\x41')
        t = dynamic.pointer(dynamic.block(4))
        x = t(source=s)
        if x.l.d.getoffset() == 4:
            raise Success

    @TestCase
    def test_dynamic_pointer_littleendian_64bit_deref():
        ptype.setbyteorder(config.byteorder.littleendian)
        t = dynamic.pointer(dynamic.block(4), type=pint.uint64_t)
        x = t(source=ptype.provider.string('\x08\x00\x00\x00\x00\x00\x00\x00\x41\x41\x41\x41')).l
        if x.l.d.getoffset() == 8:
            raise Success

    @TestCase
    def test_dynamic_array_1():
        v = dynamic.array(pint.int32_t, 4)
        if len(v().a) == 4:
            raise Success

    @TestCase
    def test_dynamic_array_2():
        v = dynamic.array(pint.int32_t, 8)
        i = range(0x40,0x40+v.length)
        x = ptype.provider.string(''.join(chr(x)+'\x00\x00\x00' for x in i))
        z = v(source=x).l
        if z[4].num() == 0x44:
            raise Success

    @TestCase
    def test_dynamic_union_rootchoose():
        class test(dynamic.union):
            _fields_ = [
                (pint.uint32_t, 'a'),
                (pint.uint16_t, 'b'),
                (pint.uint8_t, 'c'),
            ]

        a = test()
        a=a.a
        if a['a'].blocksize() == 4 and a['b'].size() == 2 and a['c'].size() == 1 and a.blocksize() == 4:
            raise Success
        
if __name__ == '__main__':
    results = []
    for t in TestCaseList:
        results.append( t() )
