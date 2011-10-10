'''base ptype element'''
__all__ = 'istype,iscontainer,type,container,rethrow,none'.split(',')
import bitmap,provider,utils
import types,logging

## this is all a horrible and slow way to do this...
def isiterator(t):
    return hasattr(t, '__iter__') and hasattr(t, 'next')

def istype(t):
    ''' returns true if specified type is a class and inherits from ptype.type '''
    return t.__class__ is t.__class__.__class__ and not isresolveable(t) and (isinstance(t, types.ClassType) or hasattr(object, '__bases__')) and issubclass(t, type)

def iscontainer(t):
    ''' returns true if specified type inherits from container '''
    return istype(t) and issubclass(t, container)

def isresolveable(p):
    return isinstance(p, (types.FunctionType, types.MethodType)) or isiterator(p)

def forceptype(p, self):
    ''' as long as value is a function, keep calling it with a context until we get a "ptype" '''

    # of type ptype
    if isinstance(p, type) or istype(p):
        return p

    # functions
    if isinstance(p, types.FunctionType):
        res = p(self)
        return forceptype(res, self)

    # bound methods
    if isinstance(p, types.MethodType):
        return forceptype(p(), self)

    if False:
        # and lastly iterators
        if isiterator(p):
            return forceptype(p.next(), self)

    raise ValueError('forceptype %s could not be resolved as asked by %s'% (repr(p), self.name()))

## ...and yeah... now it's done.

# fn must be a method, so args[0] will fetch self
import sys,traceback
def rethrow(fn):
    def catch(*args, **kwds):
        try:
            return fn(*args, **kwds)

        except:
            # FIXME: this code is stupid.
            #        what we want is when an exception is raised in
            #          .load/.deserialize, to display the elements involved,
            #          and display the fields that have been successfully
            #          loaded. in order to debug those, all we care about is
            #          what particular field caused the structure initialization
            #          to fail.
            tb = traceback.format_stack()
            self = args[0]
            type, exception = sys.exc_info()[:2]

            path = ' ->\n\t'.join( self.backtrace() )

            res = []
            res.append('')
            res.append('Caught exception: %s\n'% exception)
            res.append('%s<%x:+??> %s =>'%(self.shortname(),self.getoffset(), path))
            res.append('\t<method name> %s'% fn.__name__)

            if self.initialized:
                if iscontainer(self.__class__):
                    if self.value:
                        res.append('\t<container length> %x'% len(self.value))
                    else:
                        res.append('\t<container value> %s'% repr(self.value))
                else:
                    res.append('\t<type length> %x'% len(self))

            res.append('')
            res.append('Traceback (most recent call last):')
            res.append( ''.join(tb) )
            res.append('')
            sys.stderr.write('\n'.join(res))
            raise

        pass
    catch.__name__ = 'catching(%s)'% fn.__name__
    return catch

def debug(ptype):
    '''Will clone ptype into one containing more detailed debugging information'''
    assert istype(ptype), '%s is not a ptype'% repr(ptype)
    class newptype(ptype):
        @rethrow
        def deserialize_block(self, block):
            return super(newptype, self).deserialize_block(block)

        @rethrow
        def serialize(self):
            return super(newptype, self).serialize()

        @rethrow
        def load(self):
            return super(newptype, self).load()

        @rethrow
        def commit(self):
            return super(newptype, self).commit()

    newptype.__name__ = 'debug(%s)'% ptype.__name__
    return newptype

def debugrecurse(ptype):
    '''Will clone ptype into one containing recursive debugging information'''
    class newptype(debug(ptype)):
        @rethrow
        def newelement(self, ptype, name='', ofs=0, **attrs):
            res = forceptype(ptype, self)
            assert istype(res) or isinstance(res, type), '%s is not a ptype class'% (res.__class__)
            return super(newptype,self).newelement( debug(res), name, ofs, **attrs )

    newptype.__name__ = 'debugrecurse(%s)'% ptype.__name__
    return newptype

class type(object):
    '''
    A very most atomical ptype.
    
    Contains the following settable properties:
        length:int<w>
            size of ptype
        source:ptypes.provider<rw>
            source of input for ptype

    Readable properties:
        value:str<r>
            contents of ptype

        parent:subclass(ptype.type)<r>
            the ptype that created us

        initialized:bool(r)
            if ptype has been initialized yet
    '''
    offset = 0
    length = 0      # int
    value = None    # str
    v = property(fget=lambda s: s.value)   # abbr to get to .value

    initialized = property(fget=lambda self: self.value is not None and len(self.value) == self.length)    # bool
    source = None   # ptype.provider
    p = property(fget=lambda s: s.parent)   # abbr to get to .parent
    parent = type   # ptype.type

    attrs = None    # dict of attributes that will get assigned to any child elements
    __name__ = None # default to unnamed
    
    ## initialization
    def __init__(self, recurse={}, **attrs):
        '''Create a new instance of object. Will assign provided named arguments to self.attrs'''
        try:
            self.source = self.source or provider.memory()
        except AttributeError:
            self.source = provider.memory()
        self.parent = None

        # FIXME: the next block is responsible for conditionally propogating
        #        attributes. i think that some code in pecoff propogates data
        #        to children elements. that code should be rewritten to use the
        #        new 'recurse' parameter.
        if not recurse:
            recurse=attrs   # XXX: copy attrs into recurse, since we conditionaly propogate
        a = set( ('offset','length','value','_fields_', 'parent', '__name__') )
        self.attrs = dict(((k,v) for k,v in recurse.iteritems() if k not in a))

        # update self if user specified
        for k,v in attrs.items():
            setattr(self, k, v)
        return

    def __nonzero__(self):
        return self.initialized

    def size(self):
        '''returns the number of bytes used by type'''
        return int(self.length)

    def blocksize(self):
        '''Can be overloaded to define the block's size. This MUST return an integral type'''

        # XXX: overloading will always provide a side effect of modifying the .source's offset
        #        make sure to fetch the blocksize first before you .getoffset() on something

        return self.size()

    def contains(self, offset):
        nmin = self.getoffset()
        nmax = nmin + self.blocksize()
        return (offset >= nmin) and (offset < nmax)

    def getparent(self, type=None):
        if type is None:
            return self.parent

        if self.__class__ == type:
            return self

        for x in self.traverse():
            if issubclass(x.__class__,type) or x.__class__ == type:
                return x
            continue

        raise ValueError('%s match %s not found in chain: %s'% (self.name(), self.new(type).shortname(), '\n'.join(self.backtrace())))

    def traverse(self, branches=lambda node:(node.parent for x in range(1) if node.getparent() is not None), *args, **kwds):
        '''
        Will walk the elements returned by the generator branches(visitee)
        defaults to getting the path to the root node
        '''
        for self in branches(self, *args, **kwds):
            yield self
            for y in self.traverse(branches, *args, **kwds):
                yield y
            continue
        return

    def backtrace(self):
        '''Return a backtrace to the root element'''
        path = self.traverse()
        path = [ 'type:%s name:%s offset:%x'%(x.shortname(), getattr(x, '__name__', repr(None.__class__)), x.getoffset()) for x in path ]
        return list(reversed(path))

    def set(self, string, **kwds):
        '''set entire type equal to string'''
        last = self.value

        res = str(string)
        self.value = res
        self.length = len(res)
        return res

    a = property(fget=lambda s: s.alloc())   # abbr
    def alloc(self, **kwds):
        '''will initialize a ptype with zeroes'''
        kwds.setdefault('source', provider.empty())        
        state = dict(( (k,getattr(self,k)) for k,v in kwds.iteritems() ))
        [ setattr(self,k,v) for k,v in kwds.iteritems() ]
        self.load()
        [ setattr(self,k,v) for k,v in state.iteritems()]
        return self

    ## operator overloads
    def __cmp__(self, x):
        return [-1,0][id(self) is id(x)]

    def setoffset(self, value, **kwds):
        '''modifies the current offset (should probably be deprecated)'''
        res = self.offset
        self.offset = value
        return res

    def getoffset(self, **kwds):
        '''returns the current offset (should probably be deprecated)'''
        return int(self.offset)

    def newelement(self, ptype, name='', ofs=0, **attrs):
        '''
        create a new element of type ptype with the specified name and offset.
        this will duplicate the source, and set the new element's .parent
        attribute. this will also pass the self.attrs property to the child constructor.
        '''
        res = forceptype(ptype, self)
        assert istype(res) or isinstance(res, type), '%s is not a ptype class'% (res.__class__)

        if istype(res):
#            res.name = lambda s: name
            updateattrs = dict(self.attrs)
            updateattrs.update(attrs)
            res = res(**updateattrs)     # all children will inherit too

        res.parent = self
        if 'source' not in self.attrs:
            res.source = self.source
        res.__name__ = name
        res.setoffset(ofs)
        return res

    ## reading/writing to memory provider
    l = property(fget=lambda s: s.load())   # abbr
    def load(self):
        '''sync self with some specified data source'''
        bs = self.blocksize()
        self.source.seek(self.getoffset())
        block = self.source.consume(bs)
        self.value = ''
        return self.deserialize_block(block)

    def commit(self):
        '''write self to self.source'''
        self.source.seek( self.getoffset() )
        self.source.store( self.serialize() )
        return self

    ## byte stream input/output
    def serialize(self):
        '''return self as a byte stream'''
        if self.initialized:
            result = str(self.value)
            bs = self.blocksize()
            if len(result) < bs:
                padding = (bs - len(result)) * self.attrs.get('padding', '\x00')
                return result + padding
            assert len(result) == bs, 'value of %s is larger than blocksize (%d>%d)'%(self.shortname(), len(result), bs)
            return result
        raise ValueError('%s is uninitialized'% self.name())

    def deserialize_block(self, source):
        bs = self.blocksize()
        block = ''.join( (x for i,x in zip(xrange(bs), source)) )
        if len(block) < bs:
            self.value = block[:self.size()]
            path = ' ->\n\t'.join(self.backtrace())
            raise StopIteration("Failed reading %s at offset %x byte %d of %d\n\t%s"%(self.name(), self.getoffset(), len(block), bs, path))

        self.value = block[:self.size()]
        return self

    def deserialize_block(self, block):
        # size tracking
        bs = self.blocksize()
        if len(block) < bs:
            path = ' ->\n\t'.join(self.backtrace())
            logging.warn("%s - %d bytes left, expected %d\n\t%s", self.shortname(), len(block), bs, path)   # XXX

        # if type will be incomplete
        sz = self.size()
        if len(block) < sz:
            self.value = block[:sz]
            path = ' ->\n\t'.join(self.backtrace())
            raise StopIteration("Failed reading %s at offset %x byte %d of %d\n\t%s"%(self.name(), self.getoffset(), len(block), sz, path))

        # all is good.
        self.value = block[:sz]
        return self

    ## representation
    def name(self):
        return "<class '%s'>"% self.shortname()

    def shortname(self):
        '''intended to be overloaded. should return the short name of the current ptype.'''
        return self.__class__.__name__

    def __repr__(self):
        ofs = '[%x]'% self.getoffset()
        if self.initialized:
            res = repr(''.join(self.serialize()))
        else:
            res = '???'
        name = [lambda:'__name__:%s'%self.__name__, lambda:''][self.__name__ is None]()
        return  ' '.join([ofs, self.name(), name, res])

    def hexdump(self, **kwds):
        if self.initialized:
            return utils.hexdump( self.serialize(), offset=self.getoffset(), **kwds )
        raise ValueError('%s is uninitialized'% self.name())

    def new(self, type, **kwds):
        '''Instantiate a new type as a child of the current ptype'''
        result = self.newelement(type, None, kwds.get('offset', 0))
        result.__name__ = kwds.get('__name__', hex(id(result)) )
        # FIXME: we should probably do something to prevent this from being committed
        return result

    def copy(self):
        '''Return a duplicated instance of the current ptype'''
        result = self.newelement( self.__class__, self.name(), self.getoffset() )
        result.deserialize_block( self.serialize() )
        return result

    def cast(self, t):
        '''Cast the contents of the current ptype to a different ptype'''
        result = self.newelement( t, self.__name__, self.getoffset() )
        result.alloc(source=provider.string(self.serialize()), offset=0, blocksize=lambda : self.blocksize())
        return result

class container(type):
    '''
    This class is capable of containing other ptypes

    Readable properties:
        value:str<r>
            list of all elements that are being contained
    '''
    value = None    # list

    def isInitialized(self):
        if self.value is None or None in self.value:
            return False
        return not(False in [x.initialized for x in self.value])
    initialized = property(fget=isInitialized)  # bool

    def commit(self):
        '''will commit values of all children back to source'''
        for n in self.value:
            n.commit()
        return self

    def size(self):
        '''Calculate the total used size of a container'''
        return reduce(lambda x,y: x+y.size(), self.value, 0)

    def getoffset(self, field=None, **attrs):
        '''fetch the offset of the specified field'''
        if not field:
            return super(container, self).getoffset()

        if field.__class__ is list:
            name,res = (field[0], field[1:])
            return self.getoffset(name) + self[name].getoffset(res)

        index = self.getindex(field)
        return self.getoffset() + reduce(lambda x,y: x+y, [ x.size() for x in self.value[:index]], 0)

    def getindex(self, name):
        '''intended to be overloaded. should return the index into self.value of the specified name'''
        raise NotImplementedError('Developer forgot to overload this method')

    def contains(self, offset):
        for x in self.value:
            if x.contains(offset):
                logging.warn("structure %s is unaligned. found element %s to contain offset %x", self.shortname(), x.shortname(), offset)
                return True
        return False

    def __repr__(self):
        ofs = '[%x]'% self.getoffset()
        if self.initialized:
            res = repr(''.join(self.serialize()))
        else:
            res = '???'
        return  ' '.join([ofs, self.name(), res])

    def at(self, offset, recurse=True, **kwds):
        if not recurse:
            for i,n in enumerate(self.value):
                if n.contains(offset):
                    return n
                continue
            raise ValueError('%s (%x:+%x) - Offset 0x%x not found in a child element. returning encompassing parent.'%(self.shortname(), self.getoffset(), self.blocksize(), offset))
    
        try:
            res = self.at(offset, False, **kwds)
        except ValueError, msg:
            print 'non-fatal exception raised',ValueError,msg
            return self

        # drill into containees for more detail
        try:
            return res.at(offset, recurse=recurse, **kwds)
        except (NotImplementedError, AttributeError):
            pass
        return res
        
    def walkto(self, offset, **kwds):
        '''will walk all the objects needed to reach a particular offset'''
        obj = self

        # drill into containees for more detail
        try:
            while True:
                yield obj
                obj = obj.at(offset, recurse=False, **kwds)
            assert False is True
        except (NotImplementedError, AttributeError):
            pass
        return

    def setoffset(self, value, recurse=False):
        '''modifies the current offset, set recurse=True to update all offsets in all children'''
        res = super(container, self).setoffset(value)
        if recurse:
            assert self.initialized
            for n in self.value:
                n.setoffset(value, recurse=recurse)
                value += n.blocksize()
            pass
        return res

    def serialize(self):
        result = ''.join( (x.serialize() for x in self.value) )
        bs = self.blocksize()
        if len(result) < bs:
            padding = (bs - len(result)) * self.attrs.get('padding', '\x00')
            return result + padding
        if len(result) > bs:
            #XXX: serialized contents is larger than user allowed us to be
            #result = result[:bs]
            pass
        return result

    def load(self):
        assert self.value is not None, 'Parent must initialize self.value'
        bs = self.blocksize()
        self.source.seek(self.getoffset())
        block = self.source.consume(bs)
        return self.deserialize_block(block)

    def deserialize_block(self, block):
        assert self.value is not None, 'Parent must initialize self.value'
        ofs = self.getoffset()
        for n in self.value:
            bs = n.blocksize()
            n.setoffset(ofs)
            n.deserialize_block(block[:bs])
            block = block[bs:]
            ofs += bs
        return self

class empty(type):
    '''empty ptype that occupies no space'''
    length = 0

class none(empty): pass

class block(none):
    def __getslice__(self, i, j):
        return self.serialize()[i:j]
    def __getitem__(self, index):
        return self.serialize()[index]
    def shortname(self):
        return 'block(%d)'% self.length

# FIXME: would be cool to remove the pointer class' reliance on pint, so we can somehow
#        fit pointer creation in this module.
if False:
    if sys.byteorder == 'big':
        byteorder = pint.bigendian
    elif sys.byteorder == 'little':
        byteorder = pint.littleendian

    def setbyteorder(endianness):
        '''Set the global byte order for all pointer types'''
        global byteorder
        byteorder = endianness

    class pointer(byteorder(type)):
        _target_ = None
        def shortname(self):
            return 'pointer<%s>'% (parentname)
        def dereference(self):
            name = '*%s'% self.name()
            p = int(self)
            return self.newelement(self._target_, name, p)
        
        deref=lambda s: s.dereference()
        d = property(fget=deref)

        def __cmp__(self, other):
            if issubclass(other.__class__, self.__class__):
                return cmp(int(self),int(other))
            return super(pointer, self).__cmp__(other)

    import dyn  # XXX
    def addr_t(type):
        global byteorder
        parent = byteorder(type)        # XXX: this is how we enforce the byte order
        parentname = parent().shortname()
        return dyn.clone(pointer, _target_=type)

if __name__ == '__main__':
    import ptype
    if True:
        class p10bytes(ptype.type):
            length = 10

        import provider

        x = p10bytes()
        print repr(x)
    #    x.load()
    #    print repr(x)

        x.source = provider.memory()
        x.setoffset(id(x))
        x.load()
        print repr(x)

    if False:
        x.value = '\x7fHAI\x01\x01\x01\x00\x00\x00'
        x.commit()

        x.alloc()
        x.deserialize(input.file.read())
        x.set('hello there okay')

        x.set("okay, what the fuck. please work. i'm tired.")
        x.commit()

    if True:
        class u8(ptype.type): length=1
        class u16(ptype.type): length=2
        class u32(ptype.type): length=4
        
        x = ptype.container(value=[])
        x.v.append( u8() )
        x.v.append( u32() )
        x.v.append( u16() )
        x.v.append( u16() )
        x.v.append( u32() )
        x.v.append( u16() )
        x.v.append( u8() )
        x.v.append( u8() )
        x.v.append( u16() )
        x.source=provider.empty()
        print x.l
