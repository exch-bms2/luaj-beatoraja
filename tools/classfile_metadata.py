"""Class-file metadata census. Fail closed on unclassified attribute kinds."""

class Reader:
    def __init__(self, data): self.data, self.offset = data, 0
    def take(self, n):
        value = self.data[self.offset:self.offset+n]
        if len(value) != n: raise ValueError('Truncated class file')
        self.offset += n
        return value
    def u1(self): return self.take(1)[0]
    def u2(self): return int.from_bytes(self.take(2), 'big')
    def u4(self): return int.from_bytes(self.take(4), 'big')


def inspect(data):
    r = Reader(data)
    if r.u4() != 0xcafebabe: raise ValueError('Not a class file')
    minor, major, count = r.u2(), r.u2(), r.u2()
    pool = [None] * count
    i = 1
    while i < count:
        tag = r.u1()
        if tag == 1: value = r.take(r.u2()).decode('utf-8', errors='replace')
        elif tag in (3,4): value = r.take(4).hex()
        elif tag in (5,6): value = r.take(8).hex()
        elif tag in (7,8,16,19,20): value = r.u2()
        elif tag in (9,10,11,12,17,18): value = (r.u2(), r.u2())
        elif tag == 15: value = (r.u1(), r.u2())
        else: raise ValueError('Unknown constant pool tag: ' + str(tag))
        pool[i] = (tag, value)
        i += 2 if tag in (5,6) else 1
    def resolve(index):
        if index == 0: return None
        tag, value = pool[index]
        if tag in (7,8,16,19,20): return resolve(value)
        if tag in (9,10,11,12): return [resolve(x) for x in value]
        if tag == 15: return [value[0], resolve(value[1])]
        return value
    census = {}
    generated = {'LineNumberTable','LocalVariableTable','LocalVariableTypeTable','StackMapTable'}
    def attributes(reader):
        result = {}
        for _ in range(reader.u2()):
            name = resolve(reader.u2())
            body = Reader(reader.take(reader.u4()))
            census[name] = census.get(name, 0) + 1
            if name in ('Signature','SourceFile','ConstantValue'):
                value = resolve(body.u2())
            elif name in ('Deprecated','Synthetic'): value = True
            elif name == 'Exceptions': value = [resolve(body.u2()) for _ in range(body.u2())]
            elif name == 'InnerClasses':
                value = [[resolve(body.u2()),resolve(body.u2()),resolve(body.u2()),body.u2()] for _ in range(body.u2())]
                value.sort(key=str)
            elif name == 'EnclosingMethod': value = [resolve(body.u2()),resolve(body.u2())]
            elif name == 'NestHost': value = resolve(body.u2())
            elif name == 'NestMembers': value = sorted(resolve(body.u2()) for _ in range(body.u2()))
            elif name == 'BootstrapMethods':
                value = [[resolve(body.u2()), [resolve(body.u2()) for _ in range(body.u2())]] for _ in range(body.u2())]
            elif name == 'MethodParameters':
                value = [[resolve(body.u2()), body.u2()] for _ in range(body.u1())]
            elif name == 'Code':
                stack, locals_, length = body.u2(), body.u2(), body.u4()
                body.take(length)
                handlers = body.u2(); body.take(8 * handlers)
                nested = attributes(body)
                value = {'max_stack':stack,'max_locals':locals_,'code_length':length,'handlers':handlers,'attributes':nested}
            elif name in generated:
                value = {'generated_bytes':len(body.data)}
                body.take(len(body.data))
            else: raise ValueError('Unclassified class attribute: ' + name)
            if body.offset != len(body.data): raise ValueError('Unread bytes in ' + name)
            result[name] = value
        return result
    def member():
        access, name, descriptor = r.u2(), resolve(r.u2()), resolve(r.u2())
        return name + ':' + descriptor, {'access':access,'attributes':attributes(r)}
    access, this, parent = r.u2(), resolve(r.u2()), resolve(r.u2())
    interfaces = [resolve(r.u2()) for _ in range(r.u2())]
    fields = dict(member() for _ in range(r.u2()))
    methods = dict(member() for _ in range(r.u2()))
    attrs = attributes(r)
    if r.offset != len(data): raise ValueError('Unread class bytes')
    return {'major':major,'minor':minor,'access':access,'class':this,'parent':parent,'interfaces':interfaces,
            'fields':fields,'methods':methods,'attributes':attrs,'attribute_census':census}
