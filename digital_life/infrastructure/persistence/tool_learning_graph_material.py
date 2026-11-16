"""Bounded lossless local graph material, never a qualification verdict."""
import sys
from typing import NamedTuple
import zlib
from digital_life.domain.contracts import ContractError


class GraphMaterial(NamedTuple):
    body:bytes
    raw_size:int
    compressed:bool


def storage_size(value):
    return (sys.getsizeof(value)+sys.getsizeof(value.body)
            +sys.getsizeof(value.raw_size)+sys.getsizeof(value.compressed))


def encode_graph(encoded,limit):
    if type(encoded)is not str:raise ContractError('graph material must be local encoded JSON')
    raw=encoded.encode('utf-8')
    if len(raw)>limit:return None
    body=zlib.compress(raw,1)if len(raw)>=1024 else raw
    compressed=len(raw)>=1024 and len(body)<len(raw)*.9
    return GraphMaterial(body if compressed else raw,len(raw),compressed)


def decode_graph(value,limit):
    if (type(value)is not GraphMaterial or type(value.raw_size)is not int
            or not 0<=value.raw_size<=limit or type(value.body)is not bytes
            or len(value.body)>limit or type(value.compressed)is not bool):
        raise ContractError('invalid retained graph material')
    try:
        if value.compressed:
            decoder=zlib.decompressobj();raw=decoder.decompress(value.body,value.raw_size+1)
            if (len(raw)!=value.raw_size or not decoder.eof
                    or decoder.unconsumed_tail or decoder.unused_data):
                raise ValueError('graph material size or stream mismatch')
        else:
            raw=value.body
            if len(raw)!=value.raw_size:raise ValueError('graph material size mismatch')
        return raw.decode('utf-8')
    except (ValueError,zlib.error,UnicodeError)as error:
        raise ContractError('invalid retained graph material')from error
