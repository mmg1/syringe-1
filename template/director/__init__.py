from ptypes import *

### sort of based on http://www.martinreddy.net/gfx/2d/IFF.txt
class UBYTE(pint.uint8_t): pass
class WORD(pint.int16_t): pass
class UWORD(pint.uint16_t): pass
class LONG(pint.int32_t): pass
#class LONG(pint.bigendian(pint.int32_t)): pass

class ID( dyn.block(4) ): pass

### yay
class Chunk_Type(object): pass
class Chunk(pstruct.type):
    def ckExtra(self):
        expectedsize = int(self['ckSize'])
        if expectedsize & 1:
            expectedsize += 1
        realsize = self['ckData'].size()
        return dyn.block( expectedsize - realsize )

    def ckData(self):
        t = self['ckID'].l.serialize()
        try:
            return Riff_Header_Lookup[t]
        except KeyError:
            pass
        return dyn.block( int(self['ckSize'].l) )

    def size(self):
        size = int(self['ckSize']) + 8
        if size & 1:
            size += 1
        return size

    def __ckSize(self):
        p = self
        while p.parent is not None:
            p = p.parent

        if p['ID'].serialize() == 'XFIR':
            return LONG
        return pint.bigendian(LONG)

    _fields_ = [
        (ID, 'ckID'),
        (__ckSize, 'ckSize'),
        (ckData, 'ckData'),
        (ckExtra, 'ckExtra'),
    ]

class ChunkList(parray.infinite):
    _object_ = Chunk

###
class File(pstruct.type):
    def __Data(self):
        # FIXME: should we bound this element by the size specified in the header?
        return ChunkList

    def __Size(self):
        if self['ID'].l.serialize() == 'XFIR':
            return LONG
        return pint.bigendian(LONG)

    _fields_ = [
        (ID, 'ID'),
        (__Size, 'Size'),
        (ID, 'Format'),
        (__Data, 'Data'),
    ]

###
def getparentclasslookup(parent, key):
    import inspect
    res = {}
    for cls in globals().values():
        if inspect.isclass(cls) and cls is not parent and issubclass(cls, parent):
            res[ key(cls) ] = cls
        continue
    return res

Riff_Header_Lookup = getparentclasslookup(Chunk_Type, lambda cls: (cls.id))

if __name__ == '__main__':
    import ptypes,director; reload(director)
    ptypes.setsource( ptypes.provider.file('./sample.dir', mode='r') )

    z = director.File()
    self = z.load()['Data'].cast(director.ChunkList)

    print 'Number of Records:', len(self)
